#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded generic ARM virt boot of the independently staged research4 system.

No board DT, network, device passthrough, host share or monitor is configured.
SIGINT/SIGTERM preserve evidence and terminate only this runner's QEMU child.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import signal
import subprocess
import time

from system_common import IMAGE, LABEL, PROFILE, ROOT, WORK, check, profile, sha
from read_vm_result import extract as extract_result_file

cancelled = None
MANAGEMENT_CONTEXT = 'system_u:system_r:sysadm_t:s0'
AUDIT_PRINTK_MARKER = re.compile(
    r'TB371FC_EARLY_SELINUX_V4 AUDIT_PRINTK_UNLIMITED scope=generic-vm opt_in=1 '
    r'compatible=linux,dummy-virt before=([0-9]+) after=0 '
    r'burst_before=([0-9]+) burst_after=([0-9]+) policy_load_attempted=0')
API_CONTEXTS = {
    '/dev/null': 'system_u:object_r:null_device_t:s0',
    '/dev/kmsg': 'system_u:object_r:kmsg_device_t:s0',
    '/run': 'system_u:object_r:var_run_t:s0',
    '/run/log': 'system_u:object_r:syslogd_var_run_t:s0',
    '/run/log/journal': 'system_u:object_r:syslogd_var_run_t:s0',
}


def descriptor_route_matches(proof, mode, restriction, data, profile_sha):
    """Independently compare the forwarded/READY-held-worker observations."""
    try:
        units = {'noop': 'tb371fc-r4f-bus-proof.service',
                 'pids': 'tb371fc-r4f-pids-proof.service',
                 'proc-read': 'tb371fc-r4f-fs-proof.service'}
        worker, properties = proof['actual_worker'], proof['unit_properties']
        client = proof['actual_client']
        argv = worker['argv']
        if not (proof['creator']['selinux_context'] == MANAGEMENT_CONTEXT and
                client['selinux_context'] == MANAGEMENT_CONTEXT and
                client['observed_while_worker_waiting_for_go'] is True and
                type(client['pid']) is int and client['pid'] > 1 and
                type(client['starttime_ticks']) is int and
                worker['selinux_context'] == MANAGEMENT_CONTEXT and
                worker['observed_while_waiting_for_go'] is True and
                type(worker['pid']) is int and worker['pid'] > 1 and
                type(worker['starttime_ticks']) is int and
                proof['worker_premise_verified_by_actual_readback'] is True and
                proof['installed_worker_sha256'] == data['transient_worker_sha256'] and
                worker['cgroup'] == '0::/system.slice/' + units[mode] and
                len(argv) == 7 and argv[:3] == ['/usr/bin/python3',
                    '/usr/libexec/tb371fc-r4f-worker.py', mode] and
                argv[3] == '--nonce' and re.fullmatch('[0-9a-f]{32}', argv[4]) and
                argv[5:] == ['--profile-sha256', profile_sha] and
                properties['MainPID'] == str(worker['pid']) and
                properties['ControlGroup'] == '/system.slice/' + units[mode] and
                properties['SELinuxContext'] == MANAGEMENT_CONTEXT and
                properties['RuntimeMaxUSec'] == '8s' and
                properties['RestrictFileSystems'] == restriction and
                (mode != 'pids' or properties['TasksMax'] == '3')):
            return False
        if set(proof['forwarded']) != {'0', '1', '2'} or set(worker['descriptors']) != {'0', '1', '2'}:
            return False
        for fd in ('0', '1', '2'):
            first, last = proof['forwarded'][fd], worker['descriptors'][fd]
            direction = 0 if fd == '0' else 1
            if not (first['creator_context'] == MANAGEMENT_CONTEXT and
                    first['inode_selinux_context'] == last['inode_selinux_context'] == MANAGEMENT_CONTEXT and
                    (first['mode'] & 0o170000) == (last['mode'] & 0o170000) == 0o010000 and
                    first['access_mode'] == last['access_mode'] == direction and
                    (first['flags'] & 3) == (last['flags'] & 3) == direction and
                    first['device'] == last['device'] and first['inode'] == last['inode'] and
                    last['target'] == 'pipe:[' + str(first['inode']) + ']'):
                return False
        return True
    except (KeyError, TypeError, ValueError, IndexError):
        return False


def policy_route_matches(record, proof, policy_sha, policy_size):
    """Check the complete AV matrix and bind its premises to real FD records."""
    try:
        flags = ('query_completed', 'all_receivers_fd_and_fifo_allowed', 'service_entry_allowed',
                 'source_policy_map_allowed', 'source_policy_read_and_load_allowed',
                 'manager_read_policy_denied', 'management_read_policy_allowed',
                 'management_policy_export_path_allowed', 'unconfined_service_fifo_restriction_retained',
                 'manager_same_domain_setcon_allowed', 'all_requested_contracts_satisfied')
        if not (all(record[name] is True for name in flags) and
                record['input_policy'] == {'size': policy_size, 'sha256': policy_sha} and
                record['query_count'] == record['expected_query_count'] == len(record['queries']) == 82 and
                record['worker_context_is_requested_premise'] is True and
                record['actual_worker_context_observed_by_probe'] is False and
                record['kernel_policy_loaded_or_written'] is False and
                record['policy_version_converted'] is False and record['booleans_changed'] is False and
                record['process_context_inputs'] == {
                    'manager': 'system_u:system_r:init_t:s0',
                    'broker': 'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023',
                    'creator': MANAGEMENT_CONTEXT, 'requested_worker': MANAGEMENT_CONTEXT}):
            return False
        manager = 'system_u:system_r:init_t:s0'
        broker = 'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023'
        previous = 'system_u:system_r:unconfined_service_t:s0'
        security = 'system_u:object_r:security_t:s0'
        policy_file = 'system_u:object_r:semanage_store_t:s0'
        entry_file = 'system_u:object_r:bin_t:s0'
        fifo_permissions = ('read', 'write', 'append', 'getattr', 'ioctl')
        expected_rows = {}

        def expect(group, source, target, klass, permissions, allowed, fd=None, receiver=None):
            for permission in permissions:
                key = (group, source, target, klass, permission, fd, receiver)
                if key in expected_rows:
                    raise ValueError('duplicate expected AV tuple')
                expected_rows[key] = allowed

        for fd in ('0', '1', '2'):
            for receiver, source in {'broker': broker, 'manager': manager,
                                     'requested_worker': MANAGEMENT_CONTEXT}.items():
                expect('descriptor_route', source, MANAGEMENT_CONTEXT, 'fd', ('use',), True, fd, receiver)
                expect('descriptor_route', source, MANAGEMENT_CONTEXT, 'fifo_file',
                       fifo_permissions, True, fd, receiver)
        expect('entry', manager, manager, 'process', ('setexec',), True)
        expect('entry', manager, MANAGEMENT_CONTEXT, 'process', ('transition',), True)
        expect('entry', MANAGEMENT_CONTEXT, entry_file, 'file',
               ('entrypoint', 'execute', 'read', 'open', 'getattr', 'map'), True)
        expect('source_policy_map', manager, policy_file, 'file', ('map',), True)
        expect('source_policy_read_and_load', manager, policy_file, 'file', ('read', 'open', 'getattr'), True)
        expect('source_policy_read_and_load', manager, security, 'security', ('load_policy',), True)
        expect('manager_policy_export', manager, security, 'security', ('read_policy',), False)
        expect('management_policy_export', MANAGEMENT_CONTEXT, security, 'security', ('read_policy',), True)
        expect('management_policy_export_path', MANAGEMENT_CONTEXT, security, 'file', ('open', 'read', 'getattr'), True)
        expect('management_policy_export_path', MANAGEMENT_CONTEXT, security, 'dir', ('search', 'getattr'), True)
        expect('previous_service_fifo', broker, previous, 'fifo_file', fifo_permissions, False)
        expect('previous_service_fd', broker, previous, 'fd', ('use',), True)
        expect('manager_same_domain_setcon', manager, manager, 'process', ('setcurrent', 'dyntransition'), True)
        actual_rows = {}
        fields = ('group', 'source_context', 'target_context', 'class', 'permission', 'descriptor', 'receiver')
        for row in record['queries']:
            key = tuple(row[field] for field in fields)
            if key in actual_rows or row['return_code'] != 0:
                return False
            requested = row['requested_mask']
            if (type(requested) is not int or requested <= 0 or requested & (requested - 1) or
                    row['permission_allowed'] is not bool(row['raw_decision']['allowed'] & requested)):
                return False
            actual_rows[key] = row['permission_allowed']
        if len(expected_rows) != 82 or actual_rows != expected_rows:
            return False
        for fd in ('0', '1', '2'):
            for key in ('device', 'inode', 'mode', 'flags', 'access_mode',
                        'creator_context', 'inode_selinux_context'):
                if record['descriptor_inputs'][fd][key] != proof['forwarded'][fd][key]:
                    return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def on_signal(number, frame):
    global cancelled
    cancelled = number


def inspect_serial(serial, phase, data, profile_sha, persisted=None):
    lines = serial.decode(errors='replace').splitlines()
    marker = 'TB371FC_R4F_VM_LABEL_COMPLETE' if phase == 'label' else 'TB371FC_R4F_VM_SYSTEM_COMPLETE'
    # The guarded guest writes exact raw /dev/console lines, independent of
    # journal's timestamp/PID formatting. Only those lines are accepted here.
    marker_count = sum(line.strip() == marker for line in lines)
    failures = {'validation_failure_seen': any('TB371FC_R4F_VM_VALIDATION_FAILED' in line for line in lines),
                'kernel_panic_seen': any('Kernel panic - not syncing' in line for line in lines),
                'invalid_initramfs_seen': any('rootfs image is not initramfs' in line for line in lines)}
    needles = {'autofs4_module_warning_count': "Failed to find module 'autofs4'",
               'pids_max_read_warning_count': 'Failed to read pids.max',
               'bpf_lsm_not_supported_count': 'BPF LSM not supported',
               'virtual_gpio_failure_count': 'gpio-keys: failed to get gpio',
               'udev_event_fd_loss_count': "Failed to store deserialized fd 'event-serialization'"}
    warnings = {key: sum(needle in line for line in lines) for key, needle in needles.items()}
    warnings['selinux_avc_denial_count'] = sum(bool(re.search(r'\bavc:\s+denied\b', line)) for line in lines)
    # Fixed R4 kernel/audit.c + lib/ratelimit.c print paths. A missing
    # rejection in a lossy console is not evidence of zero rejection.
    loss_patterns = {
        'audit_printk_suppression': re.compile(r'\b(?:kauditd_printk_skb|audit_log_lost|audit_panic|audit_log_start):\s*[1-9][0-9]* callbacks suppressed\b'),
        # The limiter is shared: another caller may report accumulated
        # suppression that included audit traffic. Conservatively reject it.
        'any_kernel_callback_suppression': re.compile(r'\b[A-Za-z0-9_]+:\s*[1-9][0-9]* callbacks suppressed\b'),
        'audit_lost_positive': re.compile(r'\baudit_lost=[1-9][0-9]*\b'),
        'audit_backlog_overflow': re.compile(r'\baudit_backlog=[0-9]+ > audit_backlog_limit=[0-9]+\b'),
        'audit_loss_reason': re.compile(r'\baudit:\s+(?:kauditd (?:retry|hold) queue overflow|backlog limit exceeded|rate limit exceeded|out of memory in audit_(?:log_start|expand))\b'),
    }
    loss_signals = {name: [{'line': i + 1, 'text': line} for i, line in enumerate(lines)
                           if pattern.search(line)] for name, pattern in loss_patterns.items()}
    warnings.update({name + '_count': len(found) for name, found in loss_signals.items()})
    bpf_attached = [line for line in lines if 'bpf-restrict-fs: LSM BPF program attached' in line]
    result = {'expected_marker_seen': marker_count == 1, 'marker_exact_line_count': marker_count,
              'observed_warning_counts': warnings, 'audit_loss_signals': loss_signals,
              'systemd_lsm_bpf_attached_messages': bpf_attached, **failures}
    qualified_file = isinstance(persisted, dict) and persisted.get('qualified') is True
    envelope = persisted.get('envelope', {}) if qualified_file else {}
    records = ([envelope['result']] if envelope.get('status') == 'pass' and
               isinstance(envelope.get('result'), dict) else [])
    progress = envelope.get('progress', [])
    result['persistent_result_qualified'] = qualified_file
    result['persistent_result_metadata'] = ({key: value for key, value in persisted.items() if key != 'envelope'}
                                            if qualified_file else None)
    result['guest_reported_failure'] = envelope.get('failure')
    result['guest_file_status'] = envelope.get('status')
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
        gates = (qualified_file and envelope.get('status') == 'pass' and len(records) == 1 and
                 all(guest.get(k) == v for k, v in expected.items()))
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
                 guest.get('system_bus_proof', {}).get('wait_pipe_noop_exit_code') == 0 and
                 guest.get('system_bus_proof', {}).get('wait_pipe_noop_stdout_empty') is True and
                 guest.get('system_bus_proof', {}).get('owned_unit_collected') is True and
                 guest.get('system_bus_proof', {}).get('private_socket_used_for_transient_probe') is False)
        descriptors = guest.get('system_bus_proof', {}).get('actual_descriptor_proof', {})
        bpf = guest.get('bpf_lsm_deny_probe', {})
        proofs = {'noop': descriptors, 'pids': guest.get('pids_descriptor_proof', {}),
                  'proc_read_baseline': bpf.get('baseline_descriptor_proof', {}),
                  'proc_read_restricted': bpf.get('restricted_descriptor_proof', {})}
        requests = {'noop': ('noop', '~'), 'pids': ('pids', '~'),
                    'proc_read_baseline': ('proc-read', '~'),
                    'proc_read_restricted': ('proc-read', '~proc')}
        route_gates = {name: descriptor_route_matches(proofs[name], mode, restriction, data, profile_sha)
                       for name, (mode, restriction) in requests.items()}
        policy_gates = {name: policy_route_matches(guest.get('transient_policy_contracts', {}).get(name, {}),
                           proofs[name], guest.get('loaded_policy_sha256'), guest.get('loaded_policy_bytes'))
                        for name in requests}
        result['independent_transient_route_gates'] = route_gates
        result['independent_same_boot_av_gates'] = policy_gates
        gates = gates and all(route_gates.values()) and all(policy_gates.values())
        pids = guest.get('pids_enforcement_probe', {})
        pids_ok = (pids.get('passed') is True and pids.get('tasks_max') == 3 and
                   pids.get('attempted_children') == 3 and pids.get('created_children') == 2 and
                   len(pids.get('denied', [])) == 1 and pids.get('denied', [{}])[0].get('errno') == 11 and
                   pids.get('pids_events_max_after', -1) > pids.get('pids_events_max_before', -1) >= 0 and
                   pids.get('all_owned_children_reaped') is True)
        baseline_payload = bpf.get('baseline_payload', {})
        baseline_stdout = bpf.get('baseline_stdout', '')
        baseline_bytes = baseline_stdout.encode('utf-8')
        direct = bpf.get('restricted_direct_open', {})
        baseline_argv = bpf.get('baseline_worker_argv', [])
        bpf_ok = (bpf.get('baseline_exit_code') == 0 and bpf.get('unrestricted_read_succeeded') is True and
                  baseline_payload.get('outcome') == 'read' and
                  baseline_stdout.startswith('Linux version ' + data['kernel_release'] + ' ') and
                  baseline_payload.get('data_bytes') == len(baseline_bytes) and
                  baseline_payload.get('data_sha256') == hashlib.sha256(baseline_bytes).hexdigest() and
                  bpf.get('restricted_exit_code') == 1 and bpf.get('restricted_stdout_empty') is True and
                  direct.get('outcome') == 'error' and direct.get('failure_phase') == 'open' and
                  direct.get('errno') == 1 and direct.get('permission_denial') is True and
                  direct.get('data_bytes') == 0 and
                  bpf.get('baseline_same_worker_argv_domain_and_unit') is True and
                  baseline_argv == bpf.get('restricted_worker_argv') and bool(baseline_argv) and
                  baseline_argv == proofs['proc_read_baseline'].get('actual_worker', {}).get('argv') and
                  baseline_argv == proofs['proc_read_restricted'].get('actual_worker', {}).get('argv') and
                  all(proofs['proc_read_baseline'].get('unit_properties', {}).get(key) ==
                      proofs['proc_read_restricted'].get('unit_properties', {}).get(key)
                      for key in ('ControlGroup', 'SELinuxContext', 'TasksMax', 'RuntimeMaxUSec')))
        export = guest.get('actual_loaded_policy_export', {})
        export_ok = (export.get('guest_path') == '/var/lib/tb371fc-r4f-proof/loaded-policy.33' and
                     export.get('size') == guest.get('loaded_policy_bytes') and
                     export.get('sha256') == guest.get('loaded_policy_sha256') and
                     export.get('version') == 33 and export.get('mode') == 0o600 and
                     export.get('kernel_policy_written') is False and
                     guest.get('active_policy_unchanged_across_probes') is True)
        result['behavioral_probe_gates'] = {'actual_tasks_max': pids_ok,
                                           'actual_bpf_file_open_eperm': bpf_ok,
                                           'same_boot_policy_export_record': export_ok}
        gates = gates and pids_ok and bpf_ok and export_ok
        pl061 = guest.get('pl061_binding_proof', {})
        devices = pl061.get('devices', [])
        driver_path = '/sys/bus/amba/drivers/pl061_gpio'
        pl061_ok = (pl061.get('actual_sysfs_readback') is True and
                    pl061.get('driver_path') == pl061.get('driver_realpath') == driver_path and
                    isinstance(devices, list) and bool(devices) and
                    [item.get('name') for item in devices] == guest.get('pl061_bound_devices') and
                    len(set(item.get('name') for item in devices)) == len(devices) and
                    all(re.fullmatch(r'[0-9a-f]+\.pl061', item.get('name', '')) and
                        item.get('device_path', '').startswith('/sys/devices/') and
                        item.get('device_path', '').endswith('/' + item['name']) and
                        item.get('driver_back_reference') == driver_path and
                        'arm,pl061' in item.get('compatible', []) for item in devices))
        journal_sync = guest.get('journal_sync_success_path', {})
        sync_ok = (journal_sync.get('command') == ['/usr/bin/journalctl', '--sync'] and
                   journal_sync.get('exit_code') == 0 and journal_sync.get('stdout_truncated') is False and
                   journal_sync.get('stderr_truncated') is False and
                   type(journal_sync.get('stdout_bytes')) is int and
                   type(journal_sync.get('stderr_bytes')) is int)
        result['actual_pl061_binding_gate'] = bool(pl061_ok)
        result['actual_success_path_journal_sync_gate'] = sync_ok
        gates = gates and pl061_ok and sync_ok
        observation = guest.get('audit_printk_observation', {})
        before_tests = observation.get('state_before_tests', {})
        after_tests = observation.get('state_after_tests', {})
        audit_observation_ok = (
            observation.get('explicit_opt_in') is True and
            observation.get('guest_verifier_wrote_sysctl') is False and
            observation.get('audit_or_selinux_disabled') is False and
            before_tests == after_tests and before_tests.get('interval') == 0 and
            type(before_tests.get('burst')) is int and before_tests['burst'] >= 0)
        result['actual_audit_printk_readback_gate'] = audit_observation_ok
        gates = gates and audit_observation_ok
        early = [line for line in lines if line.startswith('TB371FC_EARLY_SELINUX_V4 ')]
        domain_records = [json.loads(line.split(' ', 1)[1]) for line in lines
                          if line.startswith('TB371FC_R4F_INITRD_DOMAINS ')]
        initrd_proof = guest.get('initrd_process_domains', {})
        policy_access = guest.get('loaded_policy_access', {})
        gates = (gates and len(domain_records) == 1 and domain_records[0] == initrd_proof and
                 initrd_proof.get('schema_version') == 3 and
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
                 initrd_proof.get('early_api_contexts') == API_CONTEXTS and
                 initrd_proof.get('journald_context', '').split(':')[2:3] == ['syslogd_t'] and
                 type(initrd_proof.get('actual_journal_files_count')) is int and
                 1 <= initrd_proof['actual_journal_files_count'] <= 8 and
                 initrd_proof.get('actual_journal_files_context') ==
                     'system_u:object_r:syslogd_var_run_t:s0' and
                 export.get('boot_id') == initrd_proof.get('boot_id') and
                 envelope.get('boot_id') == initrd_proof.get('boot_id') and
                 any(' POLICY_LOADED enforcing=1 context=system_u:system_r:kernel_t:s0' in line for line in early) and
                 any(' EXEC_SYSTEMD enforcing=1 flags=0x828c' in line for line in early) and
                 not any(' FAILED ' in line for line in early) and
                 policy_access.get('query_completed') is True and
                 policy_access.get('all_receivers_fd_and_fifo_allowed') is True and
                 policy_access.get('manager_same_domain_setcon_allowed') is True and
                 policy_access.get('all_requested_contracts_satisfied') is True and
                 policy_access.get('unconfined_service_fifo_restriction_retained') is True and
                 policy_access.get('input_policy', {}).get('sha256') == guest.get('loaded_policy_sha256'))
        serialized = [int(match.group(1)) for line in lines
                      if (match := re.search(r'\bSerialized ([0-9]+) events\.', line))]
        stage0_pattern = re.compile(r'TB371FC_TMPFS_STAGE0_V1 COPY_COMPLETE old_dev=([0-9]+:[0-9]+) new_dev=([0-9]+:[0-9]+) policy_load_attempted=0')
        stage1_pattern = re.compile(r'TB371FC_TMPFS_STAGE1_V2 CLEANUP_COMPLETE old_dev=([0-9]+:[0-9]+) new_dev=([0-9]+:[0-9]+) cleanup_children=1 old_root_empty=1 policy_load_attempted=0')
        stage0 = [(i, match) for i, line in enumerate(lines) if (match := stage0_pattern.fullmatch(line))]
        stage1 = [(i, match) for i, line in enumerate(lines) if (match := stage1_pattern.fullmatch(line))]
        audit_printk = [(i, match) for i, line in enumerate(lines)
                       if (match := AUDIT_PRINTK_MARKER.fullmatch(line))]
        policy_indices = [i for i, line in enumerate(lines)
                          if line.startswith('TB371FC_EARLY_SELINUX_V4 POLICY_LOADED enforcing=1 ')]
        exec_indices = [i for i, line in enumerate(lines)
                        if line.startswith('TB371FC_EARLY_SELINUX_V4 EXEC_SYSTEMD enforcing=1 flags=0x828c')]
        domain_indices = [i for i, line in enumerate(lines) if line.startswith('TB371FC_R4F_INITRD_DOMAINS ')]
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
        native_audit = {'marker_count': len(audit_printk), 'passed': False,
                        'scope': 'explicit generic-VM-only pre-policy printk observation'}
        if len(audit_printk) == len(stage1) == len(policy_indices) == 1:
            interval_before, burst_before, burst_after = (int(value) for value in audit_printk[0][1].groups())
            native_audit.update({'line': audit_printk[0][0] + 1, 'interval_before': interval_before,
                'interval_after': 0, 'burst_before': burst_before, 'burst_after': burst_after})
            native_audit['passed'] = (
                stage1[0][0] < audit_printk[0][0] < policy_indices[0] and
                burst_before == burst_after == before_tests.get('burst') == after_tests.get('burst') and
                before_tests.get('interval') == after_tests.get('interval') == 0 and
                data.get('audit_printk_opt_in_required') is True and
                data.get('audit_printk_interval_required') == 0)
        result['native_audit_printk_observation'] = native_audit
        gates = gates and native_audit['passed']
        reload_window = (lines[exec_indices[0] + 1:domain_indices[0]]
                         if len(exec_indices) == len(domain_indices) == 1 else [])
        reload_success = [line for line in reload_window if 'Successfully loaded SELinux policy in ' in line]
        transition_success = [line for line in reload_window if
            "Successfully switched to calculated init label 'system_u:system_r:init_t:s0'." in line]
        transition_errors = [line for line in lines if 'Failed to transition into init label ' in line]
        reload_errors = [line for line in lines if 'Failed to load new SELinux policy' in line]
        reload_proof = {'scope': 'standard systemd loader after native exec and before same-boot initrd proof',
                        'reload_success_lines': reload_success, 'transition_success_lines': transition_success,
                        'transition_error_lines': transition_errors, 'reload_error_lines': reload_errors,
                        'passed': bool(reload_success) and bool(transition_success) and
                                  not transition_errors and not reload_errors}
        result['standard_systemd_early_reload'] = reload_proof
        gates = gates and reload_proof['passed']
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
    check(Path(__file__).with_name('read_vm_result.py'), data['host_result_reader_sha256'])
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
    output.mkdir(mode=0o700)
    profile_sha = sha(PROFILE)
    command_line = (f'console=ttyAMA0 root=LABEL={LABEL} rootfstype=ext4 rw '
                    'rd.luks=0 rd.lvm=0 rd.md=0 rd.dm=0 rd.neednet=0 '
                    'module.sig_enforce=1 '
                    'systemd.unit=tb371fc-r4f-validation.target systemd.show_status=yes '
                    'systemd.log_target=console systemd.log_level=debug selinux=1 enforcing=' +
                    ('0' if args.phase == 'label' else '1 rd.tb371fc.early-selinux=1 rd.tb371fc.tmpfs-root=1 rdinit=/init.tmpfs rd.tb371fc.audit-printk-unlimited=1') +
                    f' tb371fc.r4f-phase={args.phase} tb371fc.r4f-profile={profile_sha}')
    command = ['/usr/bin/qemu-system-aarch64', '-machine', 'virt', '-cpu', 'cortex-a72',
               '-smp', '2', '-m', '2048', '-display', 'none', '-monitor', 'none',
               '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(image),
               '-initrd', str(initrd), '-append', command_line,
               '-drive', f'if=none,id=rootfs,format=raw,file={IMAGE}',
               '-device', 'virtio-blk-device,drive=rootfs']
    (output / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    log = output / 'serial.log'
    record = {'schema_version': 2, 'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'phase': args.phase, 'profile_sha256': profile_sha, 'kernel_image_sha256': sha(image),
              'initramfs_sha256': sha(initrd), 'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2,
              'physical_hardware_tested': False, 'physical_device_passthrough': False,
              'network': False, 'board_dtb_used': False, 'host_filesystem_shared': False,
              'systemd_debug_logging_for_this_vm_only': True, 'passed': False}
    record['vm_module_sig_enforce_argument'] = 'module.sig_enforce=1'
    record['initramfs_role'] = 'maintenance-label-only' if args.phase == 'label' else 'production-tmpfs-early-selinux'
    record['early_selinux_argument'] = None if args.phase == 'label' else 'rd.tb371fc.early-selinux=1'
    record['kernel_rdinit_argument'] = None if args.phase == 'label' else 'rdinit=/init.tmpfs'
    record['audit_printk_observation_argument'] = (None if args.phase == 'label' else
                                                   'rd.tb371fc.audit-printk-unlimited=1')
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
                if b'TB371FC_R4F_VM_VALIDATION_FAILED' in tail or b'Kernel panic - not syncing' in tail:
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
                persisted = None
                if args.phase == 'verify':
                    try:
                        persisted = extract_result_file(IMAGE, output, serial, profile_sha)
                    except Exception as error:
                        record['persistent_result_error'] = {'type': type(error).__name__, 'message': str(error)}
                try:
                    record.update(inspect_serial(serial, args.phase, data, profile_sha, persisted))
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
