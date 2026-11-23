#!/usr/bin/env python3
"""Boot only the newly built regular-file image in an owned ARM64 QEMU child.

No network, physical-device passthrough, Lenovo DT, host filesystem share,
monitor socket, or incoming control channel is exposed. Logs and failed runs
are retained. A bounded runner always terminates and reaps its own child.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import time

from fedora_system import ROOT, WORK, sha
from assemble_image import IMAGE, INITRD
from stage_runtime import RELEASE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('label', 'verify'))
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'vm-(label|verify)-[0-9]{2}', args.run) or not args.run.startswith('vm-' + args.phase + '-'):
        parser.error('run must be vm-PHASE-NN')
    output = WORK / args.run
    output.mkdir()
    for path in (IMAGE, INITRD, ROOT / 'boot' / ('Image-' + RELEASE)):
        if path.is_symlink() or not path.is_file():
            raise ValueError('ordinary integration file required: ' + str(path))
    initrd = json.loads((WORK / 'initramfs.json').read_text())
    if sha(INITRD) != initrd['sha256']:
        raise ValueError('initramfs changed since its manifest was recorded')
    if sha(ROOT / 'boot' / ('Image-' + RELEASE)) != '5b7dbf8ac810ef4b488d394f6b976d876e52372621428f751f02f8deac5667f5':
        raise ValueError('kernel image changed')
    command_line = ('console=ttyAMA0 root=LABEL=tb371fc-f45 rootfstype=ext4 rw '
                    'rd.luks=0 rd.lvm=0 rd.md=0 rd.dm=0 rd.neednet=0 '
                    'systemd.unit=tb371fc-validation.target '
                    'systemd.show_status=yes systemd.log_target=console '
                    'selinux=1 enforcing=' + ('0' if args.phase == 'label' else '1') +
                    ' tb371fc.vm-phase=' + args.phase)
    command = ['/usr/bin/qemu-system-aarch64', '-machine', 'virt', '-cpu', 'cortex-a72',
               '-smp', '2', '-m', '2048', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot',
               '-kernel', str(ROOT / 'boot' / ('Image-' + RELEASE)),
               '-initrd', str(INITRD), '-append', command_line,
               '-drive', f'if=none,id=rootfs,format=raw,file={IMAGE}',
               '-device', 'virtio-blk-device,drive=rootfs']
    (output / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    log = output / 'serial.log'
    start = time.monotonic()
    record = {'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'phase': args.phase, 'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2,
              'physical_hardware_tested': False, 'physical_device_passthrough': False,
              'network': False, 'board_dtb_used': False,
              'initramfs_sha256': initrd['sha256']}
    reason = None
    child = None
    try:
        with log.open('xb') as stream:
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                     stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            while child.poll() is None:
                if time.monotonic() - start > 900:
                    reason = 'timeout'
                    break
                if log.stat().st_size > 8 * 1024**2:
                    reason = 'serial log size bound'
                    break
                with log.open('rb') as reader:
                    reader.seek(max(0, log.stat().st_size - 16000))
                    tail = reader.read()
                if b'TB371FC_VM_VALIDATION_FAILED' in tail or b'Kernel panic - not syncing' in tail:
                    reason = 'guest reported failure'
                    break
                time.sleep(0.5)
    finally:
        if child is not None:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=10)
            record['qemu_exit_code'] = child.returncode
        record['elapsed_seconds'] = time.monotonic() - start
    serial = log.read_bytes()
    wanted = b'TB371FC_VM_LABEL_COMPLETE' if args.phase == 'label' else b'TB371FC_VM_SYSTEM_COMPLETE'
    record.update({'termination_reason': reason, 'serial_log_sha256': sha(log),
                   'serial_log_bytes': len(serial), 'expected_marker_seen': wanted in serial,
                   'validation_failure_seen': b'TB371FC_VM_VALIDATION_FAILED' in serial,
                   'kernel_panic_seen': b'Kernel panic - not syncing' in serial,
                   'invalid_initramfs_seen': b'rootfs image is not initramfs' in serial})
    # These markers are emitted only by the guard-checked guest service. A
    # kernel/userspace banner on its own cannot pass this validation.
    record['passed'] = (record.get('qemu_exit_code') == 0 and wanted in serial
                        and not reason and not record['validation_failure_seen']
                        and not record['kernel_panic_seen'] and not record['invalid_initramfs_seen'])
    for line in serial.decode(errors='replace').splitlines():
        prefix = 'TB371FC_VM_RESULT '
        if prefix in line:
            try:
                record['guest_result'] = json.loads(line.split(prefix, 1)[1])
            except json.JSONDecodeError:
                pass
    if args.phase == 'verify':
        guest = record.get('guest_result', {})
        expected = {'kernel_release': RELEASE, 'pid1': '/usr/lib/systemd/systemd',
                    'root_source': '/dev/vda', 'root_type': 'ext4', 'root_label': 'tb371fc-f45',
                    'selinux': 'Enforcing', 'loaded_policy_version': 33,
                    'kernel_supported_policy_version': '33',
                    'multi_user_target': 'active', 'udev': 'active', 'dbus': 'active',
                    'module_files_verified': 83, 'firmware_files_verified': 69,
                    'all_runtime_hashes_verified': True, 'failed_units': [],
                    'tablet_hardware_tested': False, 'gpu_acceleration_tested': False}
        record['guest_gates_match'] = bool(guest) and all(guest.get(k) == v for k, v in expected.items())
        record['guest_gates_match'] = (record['guest_gates_match'] and
                                       guest.get('pid1_selinux_context', '').split(':')[2:3] == ['init_t'])
        record['passed'] = bool(record['passed'] and record['guest_gates_match'])
    (output / 'result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
    print(json.dumps(record, indent=2, sort_keys=True), flush=True)
    print(serial.decode(errors='replace')[-12000:], flush=True)
    if not record['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
