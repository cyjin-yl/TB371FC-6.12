#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded generic ARM virt boot of the independently staged research3 system.

No board DT, network, device passthrough, host share or monitor is configured.
SIGINT/SIGTERM preserve evidence and terminate only this runner's QEMU child.
"""
import argparse
import datetime
import json
from pathlib import Path
import re
import signal
import subprocess
import time

from system_common import IMAGE, LABEL, PROFILE, ROOT, WORK, check, profile, sha

cancelled = None


def on_signal(number, frame):
    global cancelled
    cancelled = number


def inspect_serial(serial, phase, data, profile_sha):
    lines = serial.decode(errors='replace').splitlines()
    marker = 'TB371FC_R3_VM_LABEL_COMPLETE' if phase == 'label' else 'TB371FC_R3_VM_SYSTEM_COMPLETE'
    # The guarded guest writes exact raw /dev/console lines, independent of
    # journal's timestamp/PID formatting. Only those lines are accepted here.
    marker_count = sum(line.strip() == marker for line in lines)
    failures = {'validation_failure_seen': any('TB371FC_R3_VM_VALIDATION_FAILED' in line for line in lines),
                'kernel_panic_seen': any('Kernel panic - not syncing' in line for line in lines),
                'invalid_initramfs_seen': any('rootfs image is not initramfs' in line for line in lines)}
    needles = {'autofs4_module_warning_count': "Failed to find module 'autofs4'",
               'pids_max_read_warning_count': 'Failed to read pids.max',
               'bpf_lsm_not_supported_count': 'BPF LSM not supported',
               'virtual_gpio_failure_count': 'gpio-keys: failed to get gpio'}
    warnings = {key: sum(needle in line for line in lines) for key, needle in needles.items()}
    warnings['selinux_avc_denial_count'] = sum(bool(re.search(r'\bavc:\s+denied\b', line)) for line in lines)
    bpf_attached = [line for line in lines if 'bpf-restrict-fs: LSM BPF program attached' in line]
    result = {'expected_marker_seen': marker_count == 1, 'marker_exact_line_count': marker_count,
              'observed_warning_counts': warnings, 'systemd_lsm_bpf_attached_messages': bpf_attached, **failures}
    records = []
    progress = []
    for line in lines:
        prefix = 'TB371FC_R3_VM_RESULT '
        if line.startswith(prefix):
            records.append(json.loads(line[len(prefix):]))
        partial_prefix = 'TB371FC_R3_VM_PROGRESS '
        if line.startswith(partial_prefix):
            progress.append(json.loads(line[len(partial_prefix):]))
    result['guest_partial_progress'] = progress
    if phase == 'verify':
        guest = records[0] if len(records) == 1 else {}
        expected = {'profile_sha256': profile_sha, 'kernel_release': data['kernel_release'],
                    'pid1': '/usr/lib/systemd/systemd', 'root_source': '/dev/vda', 'root_type': 'ext4',
                    'root_label': LABEL, 'selinux': 'Enforcing', 'loaded_policy_version': 33,
                    'kernel_supported_policy_version': '33', 'multi_user_target': 'active',
                    'udev': 'active', 'dbus': 'active', 'module_files_verified': data['module_count'],
                    'firmware_files_verified': data['firmware_file_count'], 'all_runtime_hashes_verified': True,
                    'compiled_module_sig_force': data['configured_module_sig_force'],
                    'module_signature_enforced': True,
                    'failed_units': [], 'validation_pids_max': str(data['validation_tasks_max']),
                    'autofs_loaded': True, 'autofs_misc_interface': True,
                    'autofs_module_signature': data['autofs_module_signature'], 'kernel_tainted': 0,
                    'journal_acl_preserved_in_booted_image': {
                        name: {key: entry[key] for key in ('sha256', 'size')}
                        for name, entry in data['journal_acl_check'].items()},
                    'kernel_btf_sha256': data['kernel_btf_sha256'], 'kernel_btf_size': data['kernel_btf_size'],
                    'tablet_hardware_tested': False, 'gpu_acceleration_tested': False}
        gates = len(records) == 1 and all(guest.get(k) == v for k, v in expected.items())
        gates = (gates and guest.get('pid1_selinux_context', '').split(':')[2:3] == ['init_t'] and
                 'pids' in guest.get('cgroup_controllers', []) and
                 {'selinux', 'bpf'}.issubset(set(guest.get('active_lsm', []))) and
                 bool(guest.get('pl061_bound_devices')) and
                 bool(bpf_attached) and guest.get('module_sig_enforce_sysfs') in ('Y', '1') and
                 guest.get('pids_enforcement_probe', {}).get('passed') is True and
                 guest.get('pids_enforcement_probe', {}).get('all_owned_children_reaped') is True and
                 guest.get('bpf_lsm_deny_probe', {}).get('restricted_exit_code') == 1 and
                 guest.get('bpf_lsm_deny_probe', {}).get('owned_unit_collected') is True)
        result.update({'guest_result': guest, 'guest_result_count': len(records), 'guest_gates_match': bool(gates)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('label', 'verify'))
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'vm-(label|verify)-[0-9]{2}', args.run) or not args.run.startswith('vm-' + args.phase + '-'):
        parser.error('run must be vm-PHASE-NN')
    data = profile()
    release = data['kernel_release']
    image = ROOT / 'boot' / ('Image-' + release)
    initrd = ROOT / 'boot' / ('initramfs-' + release + '.img')
    initrd_record = json.loads((WORK / 'initramfs.json').read_text())
    check(image, data['kernel_image_sha256'])
    check(initrd, initrd_record['sha256'], initrd_record['size_bytes'])
    if not initrd_record['archive_verified'] or IMAGE.is_symlink() or not IMAGE.is_file():
        raise ValueError('verified archive and ordinary system image required')
    if args.phase == 'verify':
        label_runs = [json.loads(p.read_text()) for p in WORK.glob('vm-label-[0-9][0-9]/result.json')]
        if not any(r.get('passed') and r.get('profile_sha256') == sha(PROFILE) for r in label_runs):
            raise ValueError('this profile has no successful label boot')
    output = WORK / args.run
    output.mkdir()
    profile_sha = sha(PROFILE)
    command_line = (f'console=ttyAMA0 root=LABEL={LABEL} rootfstype=ext4 rw '
                    'rd.luks=0 rd.lvm=0 rd.md=0 rd.dm=0 rd.neednet=0 '
                    'module.sig_enforce=1 '
                    'systemd.unit=tb371fc-r3-validation.target systemd.show_status=yes '
                    'systemd.log_target=console systemd.log_level=debug selinux=1 enforcing=' +
                    ('0' if args.phase == 'label' else '1') +
                    f' tb371fc.r3-phase={args.phase} tb371fc.r3-profile={profile_sha}')
    command = ['/usr/bin/qemu-system-aarch64', '-machine', 'virt', '-cpu', 'cortex-a72',
               '-smp', '2', '-m', '2048', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(image),
               '-initrd', str(initrd), '-append', command_line,
               '-drive', f'if=none,id=rootfs,format=raw,file={IMAGE}',
               '-device', 'virtio-blk-device,drive=rootfs']
    (output / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    log = output / 'serial.log'
    record = {'schema_version': 1, 'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'phase': args.phase, 'profile_sha256': profile_sha, 'kernel_image_sha256': sha(image),
              'initramfs_sha256': sha(initrd), 'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2,
              'physical_hardware_tested': False, 'physical_device_passthrough': False,
              'network': False, 'board_dtb_used': False, 'host_filesystem_shared': False,
              'systemd_debug_logging_for_this_vm_only': True, 'passed': False}
    record['vm_module_sig_enforce_argument'] = 'module.sig_enforce=1'
    record['compiled_module_sig_force'] = data['configured_module_sig_force']
    previous = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGTERM, signal.SIGINT)}
    start = time.monotonic()
    reason = None
    child = None
    try:
        with log.open('xb') as stream:
            if cancelled:
                raise InterruptedError('cancelled before QEMU creation')
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            while child.poll() is None:
                if cancelled:
                    reason = 'received signal ' + str(cancelled)
                    break
                if time.monotonic() - start > 900:
                    reason = 'timeout'
                    break
                size = log.stat().st_size
                if size > record['log_limit_bytes']:
                    reason = 'serial log size bound'
                    break
                with log.open('rb') as reader:
                    reader.seek(max(0, size - 32000))
                    tail = reader.read(32000)
                if b'TB371FC_R3_VM_VALIDATION_FAILED' in tail or b'Kernel panic - not syncing' in tail:
                    reason = 'guest reported failure'
                    break
                time.sleep(0.5)
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        reason = reason or 'runner exception'
    finally:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
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
        record['termination_reason'] = reason
        if log.is_file():
            with log.open('rb') as stream:
                serial = stream.read(record['log_limit_bytes'] + 1)
            record.update({'serial_log_sha256': sha(log), 'serial_log_bytes': log.stat().st_size})
            if len(serial) <= record['log_limit_bytes']:
                try:
                    record.update(inspect_serial(serial, args.phase, data, profile_sha))
                except Exception as error:
                    record['parse_error'] = {'type': type(error).__name__, 'message': str(error)}
            else:
                record['termination_reason'] = reason or 'completed log exceeded size bound'
        forbidden = ('validation_failure_seen', 'kernel_panic_seen', 'invalid_initramfs_seen')
        record['passed'] = (record.get('qemu_exit_code') == 0 and not record['termination_reason'] and
                            record.get('expected_marker_seen', False) and
                            not any(record.get(name, True) for name in forbidden) and
                            not record.get('parse_error'))
        if args.phase == 'verify':
            record['passed'] = bool(record['passed'] and record.get('guest_gates_match') and
                                    all(value == 0 for value in record['observed_warning_counts'].values()))
        (output / 'result.json').write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(record, indent=2, sort_keys=True), flush=True)
    raise SystemExit(0 if record['passed'] else 1)


if __name__ == '__main__':
    main()
