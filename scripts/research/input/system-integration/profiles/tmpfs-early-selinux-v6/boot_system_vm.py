#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded generic ARM virt boot of the independently staged research4 system.

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
    marker = 'TB371FC_R4C_VM_LABEL_COMPLETE' if phase == 'label' else 'TB371FC_R4C_VM_SYSTEM_COMPLETE'
    # The guarded guest writes exact raw /dev/console lines, independent of
    # journal's timestamp/PID formatting. Only those lines are accepted here.
    marker_count = sum(line.strip() == marker for line in lines)
    failures = {'validation_failure_seen': any('TB371FC_R4C_VM_VALIDATION_FAILED' in line for line in lines),
                'kernel_panic_seen': any('Kernel panic - not syncing' in line for line in lines),
                'invalid_initramfs_seen': any('rootfs image is not initramfs' in line for line in lines)}
    needles = {'autofs4_module_warning_count': "Failed to find module 'autofs4'",
               'pids_max_read_warning_count': 'Failed to read pids.max',
               'bpf_lsm_not_supported_count': 'BPF LSM not supported',
               'virtual_gpio_failure_count': 'gpio-keys: failed to get gpio',
               'udev_event_fd_loss_count': "Failed to store deserialized fd 'event-serialization'"}
    warnings = {key: sum(needle in line for line in lines) for key, needle in needles.items()}
    warnings['selinux_avc_denial_count'] = sum(bool(re.search(r'\bavc:\s+denied\b', line)) for line in lines)
    bpf_attached = [line for line in lines if 'bpf-restrict-fs: LSM BPF program attached' in line]
    result = {'expected_marker_seen': marker_count == 1, 'marker_exact_line_count': marker_count,
              'observed_warning_counts': warnings, 'systemd_lsm_bpf_attached_messages': bpf_attached, **failures}
    records = []
    progress = []
    for line in lines:
        prefix = 'TB371FC_R4C_VM_RESULT '
        if line.startswith(prefix):
            records.append(json.loads(line[len(prefix):]))
        partial_prefix = 'TB371FC_R4C_VM_PROGRESS '
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
                    'validation_selinux_context': data['validation_selinux_context'],
                    'early_selinux_opt_in': True, 'kernel_rdinit': '/init.tmpfs', 'tmpfs_root_opt_in': True,
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
                 guest.get('bpf_lsm_deny_probe', {}).get('owned_unit_collected') is True and
                 guest.get('system_bus_proof', {}).get('broker_get_id_roundtrip') is True and
                 guest.get('system_bus_proof', {}).get('manager_version_roundtrip') is True and
                 guest.get('system_bus_proof', {}).get('wait_pipe_true_exit_code') == 0 and
                 guest.get('system_bus_proof', {}).get('wait_pipe_true_stdout_empty') is True and
                 guest.get('system_bus_proof', {}).get('owned_unit_collected') is True and
                 guest.get('system_bus_proof', {}).get('private_socket_used_for_transient_probe') is False)
        descriptors = guest.get('system_bus_proof', {}).get('actual_descriptor_proof', {})
        gates = (gates and descriptors.get('creator', {}).get('selinux_context') ==
                 'system_u:system_r:initrc_t:s0' and all(
                     (descriptors.get(name, {}).get('mode', 0) & 0o170000) == 0o010000 and
                     descriptors.get(name, {}).get('inode_selinux_context') == 'system_u:system_r:initrc_t:s0'
                     for name in ('stdout_pipe', 'stderr_pipe')))
        early = [line for line in lines if line.startswith('TB371FC_EARLY_SELINUX_V1 ')]
        domain_records = [json.loads(line.split(' ', 1)[1]) for line in lines
                          if line.startswith('TB371FC_R4C_INITRD_DOMAINS ')]
        initrd_proof = guest.get('initrd_process_domains', {})
        policy_access = guest.get('loaded_policy_access', {})
        gates = (gates and len(domain_records) == 1 and domain_records[0] == initrd_proof and
                 initrd_proof.get('schema_version') == 2 and
                 initrd_proof.get('kernel_rdinit') == '/init.tmpfs' and
                 initrd_proof.get('tmpfs_root_opt_in') is True and
                 initrd_proof.get('root_filesystem') == 'tmpfs' and
                 initrd_proof.get('root_source') == 'tb371fc-initroot' and
                 bool(re.fullmatch(r'[0-9]+:[0-9]+', initrd_proof.get('root_device', ''))) and
                 'rw' in initrd_proof.get('root_mount_options', '').split(',') and
                 not {'nosuid', 'noexec'}.intersection(set((initrd_proof.get('root_mount_options', '') + ',' +
                     initrd_proof.get('root_super_options', '')).split(','))) and
                 initrd_proof.get('pid1_context') == 'system_u:system_r:init_t:s0' and
                 initrd_proof.get('udevd_context', '').split(':')[2:3] == ['udev_t'] and
                 any(' POLICY_LOADED enforcing=1 context=system_u:system_r:kernel_t:s0' in line for line in early) and
                 any(' EXEC_SYSTEMD enforcing=1 flags=0x828c' in line for line in early) and
                 not any(' FAILED ' in line for line in early) and
                 policy_access.get('query_completed') is True and
                 policy_access.get('actual_service_fd_and_fifo_allowed') is True and
                 policy_access.get('unconfined_service_fifo_restriction_retained') is True and
                 policy_access.get('input_policy', {}).get('sha256') == guest.get('loaded_policy_sha256'))
        serialized = [int(match.group(1)) for line in lines
                      if (match := re.search(r'\bSerialized ([0-9]+) events\.', line))]
        stage0_pattern = re.compile(r'TB371FC_TMPFS_STAGE0_V1 COPY_COMPLETE old_dev=([0-9]+:[0-9]+) new_dev=([0-9]+:[0-9]+) policy_load_attempted=0')
        stage1_pattern = re.compile(r'TB371FC_TMPFS_STAGE1_V1 CLEANUP_COMPLETE old_dev=([0-9]+:[0-9]+) new_dev=([0-9]+:[0-9]+) cleanup_children=1 old_root_empty=1 policy_load_attempted=0')
        stage0 = [(i, match) for i, line in enumerate(lines) if (match := stage0_pattern.fullmatch(line))]
        stage1 = [(i, match) for i, line in enumerate(lines) if (match := stage1_pattern.fullmatch(line))]
        policy_indices = [i for i, line in enumerate(lines)
                          if line.startswith('TB371FC_EARLY_SELINUX_V1 POLICY_LOADED enforcing=1 ')]
        exec_indices = [i for i, line in enumerate(lines)
                        if line.startswith('TB371FC_EARLY_SELINUX_V1 EXEC_SYSTEMD enforcing=1 flags=0x828c')]
        domain_indices = [i for i, line in enumerate(lines) if line.startswith('TB371FC_R4C_INITRD_DOMAINS ')]
        migration = {'stage0_count': len(stage0), 'stage1_count': len(stage1),
                     'policy_load_count': len(policy_indices), 'systemd_exec_count': len(exec_indices),
                     'postexec_domain_proof_count': len(domain_indices), 'passed': False}
        if len(stage0) == len(stage1) == len(policy_indices) == len(exec_indices) == len(domain_indices) == 1:
            old0, new0 = stage0[0][1].groups()
            old1, new1 = stage1[0][1].groups()
            migration.update({'old_device': old0, 'new_device': new0,
                              'stage0_line': stage0[0][0] + 1, 'stage1_line': stage1[0][0] + 1,
                              'policy_line': policy_indices[0] + 1,
                              'exec_line': exec_indices[0] + 1, 'domain_proof_line': domain_indices[0] + 1})
            migration['passed'] = (old0 == old1 and new0 == new1 and old0 != new0 and
                new0 == initrd_proof.get('root_device') and
                stage0[0][0] < stage1[0][0] < policy_indices[0] < exec_indices[0] < domain_indices[0])
        gates = gates and migration['passed']
        result['tmpfs_migration_proof'] = migration
        deserializing_indices = [i for i, line in enumerate(lines) if 'Deserializing state' in line]
        root_lines = lines[deserializing_indices[-1]:] if deserializing_indices else []
        restored = [int(match.group(1)) for line in root_lines
                    if (match := re.search(r'\bDeserialized ([0-9]+) events\.', line))]
        accepted_event_fd = [line for line in root_lines if re.search(
            r'systemd-udevd\.service: Added fd [0-9]+ \(event-serialization\) to fd store\.', line)]
        transfer_lines = [line for line in lines if 'event-serialization' in line]
        # If udev actually queued events, require root-side PID1 acceptance
        # and root udevd deserialization. No queued events is not a fabricated
        # positive handoff, and an initrd-side first receipt cannot satisfy it.
        positive_serialized = [count for count in serialized if count > 0]
        positive_restored = [count for count in restored if count > 0]
        handoff_ok = (not positive_serialized or
                      (bool(accepted_event_fd) and positive_serialized == positive_restored))
        gates = gates and handoff_ok
        result.update({'guest_result': guest, 'guest_result_count': len(records), 'guest_gates_match': bool(gates),
                       'early_bootstrap_lines': early, 'initrd_domain_records': domain_records,
                       'udev_event_serialization': {'serialized_counts': serialized, 'restored_counts': restored,
                           'handoff_lines': transfer_lines, 'root_side_accepted_fd_lines': accepted_event_fd,
                           'positive_event_counts_equal': positive_serialized == positive_restored,
                           'conditional_restore_gate_passed': handoff_ok}})
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
    manifest_name = 'maintenance-initramfs.json' if args.phase == 'label' else 'initramfs.json'
    initrd_record = json.loads((WORK / manifest_name).read_text())
    initrd = Path(initrd_record['path'])
    expected_name = ('initramfs-' + release + '-maintenance.img' if args.phase == 'label' else
                     'initramfs-' + release + '.img')
    if initrd != ROOT / 'boot' / expected_name:
        raise ValueError('phase-specific initramfs path differs from its explicit profile')
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
                    'systemd.unit=tb371fc-r4c-validation.target systemd.show_status=yes '
                    'systemd.log_target=console systemd.log_level=debug selinux=1 enforcing=' +
                    ('0' if args.phase == 'label' else '1 rd.tb371fc.early-selinux=1 rd.tb371fc.tmpfs-root=1 rdinit=/init.tmpfs') +
                    f' tb371fc.r4c-phase={args.phase} tb371fc.r4c-profile={profile_sha}')
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
    record['initramfs_role'] = 'maintenance-label-only' if args.phase == 'label' else 'production-tmpfs-early-selinux'
    record['early_selinux_argument'] = None if args.phase == 'label' else 'rd.tb371fc.early-selinux=1'
    record['kernel_rdinit_argument'] = None if args.phase == 'label' else 'rdinit=/init.tmpfs'
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
                if b'TB371FC_R4C_VM_VALIDATION_FAILED' in tail or b'Kernel panic - not syncing' in tail:
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
