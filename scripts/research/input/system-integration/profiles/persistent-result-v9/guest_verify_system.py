#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guarded verification inside this project's generic ARM64 system VM only."""
import hashlib
import errno
import secrets
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import struct
import stat
import subprocess
import sys
import time
import traceback

from tb371fc_fd_route import probe as query_fd_route
from tb371fc_transient_protocol import run_transient
from tb371fc_result_file import publish as publish_result

PROFILE = Path('/usr/share/tb371fc/system-profile.json')
UNIT = 'tb371fc-r4f-validation.service'
DIAGNOSTICS_READY = False
POLICY_BYTES = None
ROUTE_SCOPE = None
ACTIVE_PROFILE = None
RESULT_IDENTITY = None
PROGRESS_RECORDS = []
PROGRESS_BYTES = 0
API_CONTEXTS = {
    "/dev/null": "system_u:object_r:null_device_t:s0",
    "/dev/kmsg": "system_u:object_r:kmsg_device_t:s0",
    "/run": "system_u:object_r:var_run_t:s0",
    "/run/log": "system_u:object_r:syslogd_var_run_t:s0",
    "/run/log/journal": "system_u:object_r:syslogd_var_run_t:s0",
}


def run(*args, check=True, timeout=60):
    result = subprocess.run(args, text=True, capture_output=True, check=check, timeout=timeout)
    if len(result.stdout.encode()) > 4 * 1024**2:
        raise RuntimeError('bounded guest command output exceeded')
    return result.stdout.strip()


def digest(path, bound=None):
    result = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
            count += len(block)
            if bound is not None and count > bound:
                raise RuntimeError('guest read exceeds its bound: ' + str(path))
    return result.hexdigest(), count


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def emit(message):
    # Only short receipts/status markers use the console. Complete evidence
    # is read from its fsynced ordinary file after the owned QEMU has exited.
    with Path('/dev/console').open('w') as console:
        console.write('\n' + message + '\n')
        console.flush()


def progress(stage, details):
    global PROGRESS_BYTES
    require(re.fullmatch(r'[a-z0-9_]{1,80}', stage), 'invalid progress stage name')
    record = {
        'stage': stage, 'details': details, 'complete_system_pass': False,
        'physical_hardware_tested': False,
    }
    raw = json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    require(len(PROGRESS_RECORDS) < 80 and PROGRESS_BYTES + len(raw) <= 3 * 1024**2,
            'bounded complete progress evidence exceeded')
    PROGRESS_RECORDS.append(json.loads(raw))
    PROGRESS_BYTES += len(raw)
    emit('TB371FC_R4F_VM_PROGRESS seq=' + str(len(PROGRESS_RECORDS)) + ' stage=' + stage + ' END')


def seal_result(status, result=None, failure=None):
    require(RESULT_IDENTITY is not None, 'result publication requires completed VM identity guards')
    receipt = publish_result(**RESULT_IDENTITY, status=status, result=result,
                             progress=PROGRESS_RECORDS, failure=failure)
    emit(receipt)


def diagnostic_command(command, timeout=8, limit=32768):
    """Diagnostic only: limits/truncation never turn a failed gate into a pass."""
    try:
        value = subprocess.run(command, capture_output=True, timeout=timeout)
        result = {'command': command, 'exit_code': value.returncode}
        for name in ('stdout', 'stderr'):
            raw = getattr(value, name)
            result[name] = raw[:limit].decode(errors='replace')
            result[name + '_bytes'] = len(raw)
            result[name + '_truncated'] = len(raw) > limit
        return result
    except Exception as error:
        return {'command': command, 'error_type': type(error).__name__, 'error': str(error)[:1024]}


def process_context(pid):
    """Read only the identity/resource fields relevant to this isolated VM."""
    value = {'pid': pid}
    try:
        root = Path('/proc') / str(pid)
        value['selinux_context'] = (root / 'attr/current').read_text().strip('\0\n')
        value['status'] = [line for line in (root / 'status').read_text().splitlines()
                           if line.startswith(('Name:', 'State:', 'PPid:', 'Threads:', 'FDSize:'))]
        value['command_line'] = (root / 'cmdline').read_bytes()[:4096].rstrip(b'\0').decode(errors='replace').split('\0')
        value['open_file_limit'] = [line for line in (root / 'limits').read_text().splitlines()
                                   if line.startswith('Max open files')]
        value['open_fd_count'] = len(list((root / 'fd').iterdir()))
    except (OSError, ValueError) as error:
        value['unavailable'] = {'type': type(error).__name__, 'message': str(error)[:1024]}
    return value


def descriptor_context(fd):
    value = {'fd': fd}
    try:
        info = os.fstat(fd)
        value.update({'target': os.readlink('/proc/self/fd/' + str(fd)),
                      'mode': info.st_mode, 'device': info.st_dev, 'inode': info.st_ino})
        try:
            value['inode_selinux_context'] = os.getxattr(fd, 'security.selinux').decode().strip('\0\n')
        except OSError as error:
            value['inode_context_unavailable_errno'] = error.errno
    except OSError as error:
        value['unavailable_errno'] = error.errno
    # The inode label is separate from the security SID captured when a file
    # description was opened. The creating process context is recorded below.
    return value


def broker_context():
    value = {'validation_process': process_context(os.getpid()),
             'pid1': process_context(1)}
    result = diagnostic_command(['/usr/bin/systemctl', 'show', '--property=MainPID', '--value',
                                 'dbus-broker.service'])
    value['broker_mainpid_lookup'] = result
    raw = result.get('stdout', '').strip()
    if result.get('exit_code') == 0 and raw.isdigit() and int(raw) > 0:
        pid = int(raw)
        value['broker_launcher'] = process_context(pid)
        # CONFIG_CHECKPOINT_RESTORE is not required. Scan only comm/PPid,
        # then inspect the actual broker child rather than assuming launcher
        # domain, descriptor limits, or descriptor count apply to that child.
        children = []
        for entry in Path('/proc').iterdir():
            if not entry.name.isdigit():
                continue
            try:
                if (entry / 'comm').read_text().strip() != 'dbus-broker':
                    continue
                parent = next(line for line in (entry / 'status').read_text().splitlines()
                              if line.startswith('PPid:')).split()[1]
                if parent == str(pid):
                    children.append(int(entry.name))
            except (OSError, StopIteration):
                continue
        value['broker_children'] = [process_context(child) for child in sorted(children)[:8]]
        value['broker_children_truncated'] = len(children) > 8
    return value


def failure_diagnostics(error_trace):
    # This runs only after the exact virt/root/profile and Enforcing guards.
    # Emit and sync the useful tail BEFORE the host's terminal failure marker.
    progress('failure_context', {'traceback': error_trace[-8192:], **broker_context()})
    for name, command in (
        ('journal_sync', ['/usr/bin/journalctl', '--sync']),
        ('broker_journal', ['/usr/bin/journalctl', '--boot=0', '--unit=dbus-broker.service',
                            '--lines=80', '--output=short-monotonic', '--no-pager']),
        ('kernel_security_journal', ['/usr/bin/journalctl', '--boot=0', '--dmesg',
                                    '--grep=avc:|audit:|denied|BPF|bpf|Out of memory',
                                    '--lines=100', '--output=short-monotonic', '--no-pager']),
        ('transport_journal', ['/usr/bin/journalctl', '--boot=0',
                               '--grep=Peer |disconnected|protocol|file descriptor|Connection reset|pids-proof|fs-proof|bus-proof',
                               '--lines=100', '--output=short-monotonic', '--no-pager']),
    ):
        progress(name, diagnostic_command(command))
    progress('failure_evidence_sync', diagnostic_command(['/usr/bin/sync'], timeout=15))


def export_actual_policy(policy, boot_id):
    directory = Path('/var/lib/tb371fc-r4f-proof')
    for part in (Path('/var'), Path('/var/lib'), directory):
        info = part.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0,
                'ordinary root-owned policy evidence directory required')
    require(stat.S_IMODE(directory.stat().st_mode) == 0o700, 'private evidence directory mode differs')
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        descriptor = os.open('loaded-policy.33', os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(policy)
            stream.flush()
            os.fsync(stream.fileno())
        descriptor = os.open('loaded-policy.33', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            observed = stream.read(32 * 1024**2 + 1)
            label = os.getxattr(stream.fileno(), 'security.selinux').decode().strip('\0\n')
        require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600 and
                info.st_uid == 0 and observed == policy, 'exported ordinary policy copy differs')
        record = {'schema_version': 1, 'boot_id': boot_id,
                  'guest_path': '/var/lib/tb371fc-r4f-proof/loaded-policy.33',
                  'size': len(policy), 'sha256': hashlib.sha256(policy).hexdigest(),
                  'version': 33, 'mode': 0o600, 'inode_selinux_context': label,
                  'source': '/sys/fs/selinux/policy', 'kernel_policy_written': False,
                  'new_profile_ordinary_file_only': True}
        descriptor = os.open('loaded-policy-export.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(record, stream, sort_keys=True)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
        return record
    finally:
        os.close(parent)


def route_policy(creator_context, requested_worker_context, descriptors):
    require(POLICY_BYTES is not None and ROUTE_SCOPE is not None,
            'actual same-boot policy/receiver contexts are not available')
    require(Path('/proc/1/attr/current').read_text().strip('\0\n') == ROUTE_SCOPE['manager_context'] and
            Path('/proc/' + str(ROUTE_SCOPE['broker_pid']) + '/attr/current').read_text().strip('\0\n') ==
                ROUTE_SCOPE['broker_context'], 'actual receiver context changed before the request')
    outcome = query_fd_route(POLICY_BYTES,
        manager_context=ROUTE_SCOPE['manager_context'], broker_context=ROUTE_SCOPE['broker_context'],
        creator_context=creator_context, worker_context=requested_worker_context,
        descriptors=descriptors, policy_file_context=ROUTE_SCOPE['policy_file_context'],
        entry_file_context=ROUTE_SCOPE['entry_file_context'])
    gates = ('query_completed', 'all_receivers_fd_and_fifo_allowed', 'service_entry_allowed',
             'source_policy_map_allowed', 'source_policy_read_and_load_allowed',
             'manager_read_policy_denied', 'management_read_policy_allowed',
             'management_policy_export_path_allowed', 'unconfined_service_fifo_restriction_retained',
             'manager_same_domain_setcon_allowed', 'all_requested_contracts_satisfied')
    closed = all(outcome.get(name) is True for name in gates)
    progress('same_boot_fd_policy_requested_worker_premise',
             {key: outcome.get(key) for key in ('input_policy', 'query_count', *gates)} if closed else outcome)
    require(closed,
            'actual exported policy did not close the complete selected FD/entry contract')
    require(outcome.get('input_policy', {}).get('sha256') == hashlib.sha256(POLICY_BYTES).hexdigest(),
            'AV input differs from this boot policy')
    return outcome


def transient(mode, properties, nonce):
    result = run_transient(mode, properties, nonce, digest(PROFILE, 65536)[0],
                           ACTIVE_PROFILE['transient_worker_sha256'], route_policy, progress)
    # The protocol has now drained/reaped the client and collected its unit;
    # full evidence output can no longer consume the active 12-second budget.
    progress('complete_transient_observation', {'mode': mode, 'nonce': nonce,
        'exit_code': result.returncode, 'worker_result': result.worker_result,
        'descriptor_proof': result.descriptor_proof, 'policy_contract': result.policy_contract})
    return result


def main():
    global DIAGNOSTICS_READY, POLICY_BYTES, ROUTE_SCOPE, ACTIVE_PROFILE, RESULT_IDENTITY
    words = Path('/proc/cmdline').read_text().split()
    phases = [x.split('=', 1)[1] for x in words if x.startswith('tb371fc.r4f-phase=')]
    identities = [x.split('=', 1)[1] for x in words if x.startswith('tb371fc.r4f-profile=')]
    require(len(phases) == 1 and phases[0] in ('label', 'verify'), 'exact isolated VM phase missing')
    require(len(identities) == 1 and identities[0] == digest(PROFILE, 65536)[0], 'new VM profile token mismatch')
    phase = phases[0]
    profile = json.loads(PROFILE.read_text())
    ACTIVE_PROFILE = profile
    require(profile['schema_version'] == 1, 'unknown profile version')
    compatible = Path('/proc/device-tree/compatible').read_bytes().rstrip(b'\0').split(b'\0')
    require(b'linux,dummy-virt' in compatible, 'not the owned generic ARM virt machine')
    root_source = run('/usr/bin/findmnt', '-n', '-o', 'SOURCE', '/')
    root_type = run('/usr/bin/findmnt', '-n', '-o', 'FSTYPE', '/')
    require(root_source == '/dev/vda' and root_type == 'ext4', 'unexpected root mount')
    root_label = run('/usr/sbin/blkid', '-s', 'LABEL', '-o', 'value', root_source)
    require(root_label == profile['root_label'] == 'tb371fc-r4f-f45', 'root is not the dedicated new image')
    require(platform.machine() == 'aarch64' and platform.release() == profile['kernel_release'], 'unexpected kernel/architecture')
    require(words.count('module.sig_enforce=1') == 1 and
            len([s for s in words if s.startswith('module.sig_enforce=')]) == 1,
            'explicit VM module signature policy missing or ambiguous')
    sig_enforce_raw = Path('/sys/module/module/parameters/sig_enforce').read_text().strip()
    require(sig_enforce_raw in ('Y', '1'), 'module signature enforcement is not active')
    pid1 = os.readlink('/proc/1/exe')
    require(pid1 == '/usr/lib/systemd/systemd', 'actual PID1 is not systemd')
    enforce = Path('/sys/fs/selinux/enforce')
    require(enforce.is_file(), 'SELinux control filesystem is not active')
    with Path('/sys/fs/selinux/policy').open('rb') as stream:
        loaded = stream.read(32 * 1024**2 + 1)
    require(1024 < len(loaded) <= 32 * 1024**2, 'loaded SELinux policy outside bound')
    magic, name_length = struct.unpack_from('<II', loaded)
    require(magic == 0xf97cff8c and name_length == 8 and loaded[8:16] == b'SE Linux', 'unexpected SELinux binary policy')
    policy_version = struct.unpack_from('<I', loaded, 16)[0]
    require(policy_version == 33, 'unexpected loaded policy version')
    require(digest(Path('/etc/selinux/targeted/policy/policy.35'))[0] ==
            profile['source_policy_sha256'] ==
            'ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798', 'candidate source policy changed')
    require(digest(Path('/usr/share/tb371fc/research1-policy-archive/policy.35'))[0] ==
            profile['original_source_policy_sha256'] ==
            '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430',
            'original source policy archive changed')
    if phase == 'label':
        require(enforce.read_text().strip() == '0', 'maintenance label requires explicit permissive VM boot')
        subprocess.run(['/usr/sbin/setfiles', '-F', '-e', '/proc', '-e', '/sys', '-e', '/dev', '-e', '/run',
                        '/etc/selinux/targeted/contexts/files/file_contexts', '/'], check=True, timeout=500)
        os.sync()
        emit('TB371FC_R4F_VM_LABEL_COMPLETE')
    else:
        require(enforce.read_text().strip() == '1', 'verification boot must enforce SELinux')
        require(digest(Path('/usr/libexec/tb371fc_result_file.py'), 128 * 1024)[0] ==
                profile['guest_result_writer_sha256'], 'installed result writer differs from this profile')
        DIAGNOSTICS_READY = True
        RESULT_IDENTITY = {'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                           'profile_sha256': identities[0]}
        require(words.count('rd.tb371fc.early-selinux=1') == 1 and
                len([word for word in words if word.startswith('rd.tb371fc.early-selinux=')]) == 1,
                'explicit early SELinux bootstrap opt-in missing or ambiguous')
        require([word for word in words if word.startswith('rdinit=')] == ['rdinit=/init.tmpfs'],
                'production boot did not select the exact reviewed tmpfs entrypoint')
        require([word for word in words if word.startswith('rd.tb371fc.tmpfs-root=')] ==
                ['rd.tb371fc.tmpfs-root=1'], 'explicit tmpfs migration opt-in missing or ambiguous')
        require([word for word in words if word.startswith('rd.tb371fc.audit-printk-unlimited=')] ==
                ['rd.tb371fc.audit-printk-unlimited=1'] and
                profile.get('audit_printk_opt_in_required') is True and
                profile.get('audit_printk_interval_required') == 0,
                'explicit generic-VM audit printk observation opt-in differs')
        audit_printk_before = {
            'interval': int(Path('/proc/sys/kernel/printk_ratelimit').read_text().strip()),
            'burst': int(Path('/proc/sys/kernel/printk_ratelimit_burst').read_text().strip())}
        require(audit_printk_before['interval'] == 0 and audit_printk_before['burst'] >= 0,
                'actual VM printk interval is not unlimited')
        progress('audit_printk_readback', {'state': audit_printk_before,
                 'guest_verifier_wrote_sysctl': False, 'audit_or_selinux_disabled': False})
        service_context = Path('/proc/self/attr/current').read_text().strip('\0\n')
        require(service_context == profile['validation_selinux_context'] == 'system_u:system_r:sysadm_t:s0',
                'strict verification service exec context was not entered')
        initrd_proof_path = Path('/run/tb371fc-r4f-initrd-domains.json')
        require(initrd_proof_path.is_file() and not initrd_proof_path.is_symlink() and
                initrd_proof_path.stat().st_size <= 4096, 'bounded same-boot initrd domain proof missing')
        initrd_proof = json.loads(initrd_proof_path.read_text())
        require(initrd_proof.get('schema_version') == 3 and
                initrd_proof.get('scope') == 'initrd before switch-root' and
                initrd_proof.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip() and
                initrd_proof.get('pid1_context') == 'system_u:system_r:init_t:s0' and
                initrd_proof.get('udevd_context', '').split(':')[2:3] == ['udev_t'] and
                initrd_proof.get('read_only_process_probe') is True and
                initrd_proof.get('kernel_rdinit') == '/init.tmpfs' and
                initrd_proof.get('tmpfs_root_opt_in') is True and
                initrd_proof.get('root_filesystem') == 'tmpfs' and
                initrd_proof.get('root_source') == 'tb371fc-initroot' and
                re.fullmatch(r'[0-9]+:[0-9]+', initrd_proof.get('root_device', '')) and
                'rw' in initrd_proof.get('root_mount_options', '').split(',') and
                not {'nosuid', 'noexec'}.intersection(set((initrd_proof.get('root_mount_options', '') + ',' +
                    initrd_proof.get('root_super_options', '')).split(','))),
                'initrd process domain proof differs from this boot or required domains')
        require(initrd_proof.get('early_api_contexts') == API_CONTEXTS and
                initrd_proof.get('journald_context', '').split(':')[2:3] == ['syslogd_t'] and
                type(initrd_proof.get('actual_journal_files_count')) is int and
                1 <= initrd_proof['actual_journal_files_count'] <= 8 and
                initrd_proof.get('actual_journal_files_context') == 'system_u:object_r:syslogd_var_run_t:s0',
                'same-boot early API/journal labels were not actually verified')
        progress('early_initrd_domains', initrd_proof)
        actual_broker = broker_context()
        progress('system_bus_context', actual_broker)
        require(not actual_broker.get('broker_children_truncated') and
                len(actual_broker.get('broker_children', [])) == 1,
                'exactly one actual broker child must be observed')
        child_context = actual_broker['broker_children'][0].get('selinux_context')
        require(child_context in ('system_u:system_r:system_dbusd_t:s0',
                                  'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023'),
                'actual broker child security context missing or unexpected')
        require(actual_broker['pid1'].get('selinux_context') == 'system_u:system_r:init_t:s0',
                'actual manager receiving context differs')
        POLICY_BYTES = loaded
        ROUTE_SCOPE = {'manager_context': actual_broker['pid1']['selinux_context'],
                       'broker_context': child_context,
                       'broker_pid': actual_broker['broker_children'][0]['pid'],
                       'policy_file_context': os.getxattr('/etc/selinux/targeted/policy/policy.35',
                                                         'security.selinux').decode().strip('\0\n'),
                       'entry_file_context': os.getxattr('/usr/bin/python3',
                                                         'security.selinux').decode().strip('\0\n')}
        exported_policy = export_actual_policy(loaded, initrd_proof['boot_id'])
        progress('actual_loaded_policy_export', exported_policy)
        manifest = Path('/usr/share/tb371fc/runtime.json')
        require(digest(manifest, 1024**2)[0] == profile['runtime_manifest_sha256'], 'runtime manifest identity changed')
        runtime = json.loads(manifest.read_text())
        require(runtime['kernel_release'] == profile['kernel_release'], 'runtime release mismatch')
        for name, expected in runtime['runtime_files'].items():
            path = PurePosixPath(name)
            require(not path.is_absolute() and '..' not in path.parts and str(path) == name, 'noncanonical runtime path')
            require(digest(Path('/') / path)[0] == expected, 'runtime file changed: ' + name)
        systemd_elf = Path(pid1).read_bytes()[:20]
        require(systemd_elf[:6] == b'\x7fELF\x02\x01' and int.from_bytes(systemd_elf[18:20], 'little') == 183,
                'PID1 executable is not ELF64 AArch64')
        progress('runtime_hashes_verified', {'kernel_release': platform.release(),
                 'module_count': runtime['module_count'], 'firmware_count': runtime['firmware_file_count'],
                 'selinux_enforce': enforce.read_text().strip(), 'loaded_policy_version': policy_version})
        controllers = Path('/sys/fs/cgroup/cgroup.controllers').read_text().split()
        require('pids' in controllers, 'actual cgroup pids controller absent')
        group = run('/usr/bin/systemctl', 'show', '--property=ControlGroup', '--value', UNIT)
        require(group == '/system.slice/' + UNIT, 'unexpected validation cgroup')
        group_path = Path('/sys/fs/cgroup') / group.lstrip('/')
        pids_max = (group_path / 'pids.max').read_text().strip()
        require(pids_max == str(profile['validation_tasks_max']) == '128', 'unit pids.max is not the configured finite limit')
        progress('system_bus_context', broker_context())
        bus_id = diagnostic_command(['/usr/bin/busctl', '--system', '--no-pager', 'call',
                                     'org.freedesktop.DBus', '/org/freedesktop/DBus',
                                     'org.freedesktop.DBus', 'GetId'])
        progress('system_bus_get_id', bus_id)
        require(bus_id.get('exit_code') == 0 and
                re.fullmatch(r's "[0-9a-f]{32}"\n?', bus_id.get('stdout', '')),
                'real system-bus broker GetId round-trip failed')
        manager = diagnostic_command(['/usr/bin/busctl', '--system', '--no-pager', 'get-property',
                                      'org.freedesktop.systemd1', '/org/freedesktop/systemd1',
                                      'org.freedesktop.systemd1.Manager', 'Version'])
        progress('system_bus_manager_version', manager)
        require(manager.get('exit_code') == 0 and
                re.fullmatch(r's "[^"\n]+"\n?', manager.get('stdout', '')),
                'real system-bus manager round-trip failed')
        bus_run = transient('noop', [], secrets.token_hex(16))
        progress('system_bus_pipe_baseline', {'exit_code': bus_run.returncode,
                 'stdout': bus_run.stdout, 'stderr': bus_run.stderr})
        require(bus_run.returncode == 0 and not bus_run.stdout and
                bus_run.worker_result.get('details') == {'outcome': 'noop', 'stdout_payload_bytes': 0},
                'system-bus --wait/--pipe baseline failed before resource probes')
        system_bus_proof = {'broker_get_id_roundtrip': True, 'manager_version_roundtrip': True,
                            'manager_version_reply': manager['stdout'].strip(),
                            'wait_pipe_noop_exit_code': bus_run.returncode,
                            'wait_pipe_noop_stdout_empty': True, 'owned_unit_collected': True,
                            'private_socket_used_for_transient_probe': False,
                            'actual_descriptor_proof': bus_run.descriptor_proof,
                            'worker_mode': 'noop', 'worker_result': bus_run.worker_result}
        loaded_policy_access = bus_run.policy_contract
        pids_run = transient('pids', ['TasksMax=3'], secrets.token_hex(16))
        pids_proof = pids_run.worker_result['details']
        progress('pids_probe_attempt', {'exit_code': pids_run.returncode, 'proof': pids_proof,
                                       'stdout': pids_run.stdout, 'stderr': pids_run.stderr})
        require(pids_run.returncode == 0 and not pids_run.stdout and pids_proof.get('passed') is True and
                pids_proof.get('tasks_max') == 3 and pids_proof.get('attempted_children') == 3 and
                pids_proof.get('created_children') == 2 and
                len(pids_proof.get('denied', [])) == 1 and pids_proof['denied'][0].get('errno') == errno.EAGAIN and
                pids_proof.get('pids_events_max_after', -1) > pids_proof.get('pids_events_max_before', -1) >= 0 and
                pids_proof.get('all_owned_children_reaped') is True,
                'controlled actual worker pids limit/cleanup did not pass')
        lsm = Path('/sys/kernel/security/lsm').read_text().strip().split(',')
        require({'selinux', 'bpf'}.issubset(set(lsm)), 'running LSM stack lacks SELinux/BPF')
        btf_hash, btf_size = digest(Path('/sys/kernel/btf/vmlinux'), 64 * 1024**2)
        require(btf_hash == profile['kernel_btf_sha256'] and btf_size == profile['kernel_btf_size'], 'live kernel BTF differs from this build')
        filesystem_names = [line.split()[-1] for line in Path('/proc/filesystems').read_text().splitlines()]
        modules = Path('/proc/modules').read_text().splitlines()
        require('autofs' in filesystem_names and any(line.startswith('autofs4 ') for line in modules), 'autofs4 was not actually loaded')
        require(Path('/sys/module/autofs4').is_dir() and Path('/sys/class/misc/autofs').exists(), 'autofs module/interface missing')
        autofs_signature = {name: run('/usr/sbin/modinfo', '-F', name, 'autofs4')
                            for name in ('signer', 'sig_key', 'sig_hashalgo')}
        require(autofs_signature == profile['autofs_module_signature'], 'loaded autofs module identity differs from signed inventory')
        tainted = int(Path('/proc/sys/kernel/tainted').read_text().strip())
        require(tainted == 0, 'running kernel is tainted')
        bound_gpio = []
        binding_devices = []
        driver = Path('/sys/bus/amba/drivers/pl061_gpio')
        if driver.is_dir():
            for child in sorted(driver.iterdir()):
                prop = child / 'of_node/compatible'
                if child.is_symlink() and prop.is_file():
                    raw = prop.read_bytes()
                    require(0 < len(raw) <= 4096, 'bounded PL061 compatible data required')
                    names = raw.rstrip(b'\0').split(b'\0')
                    if b'arm,pl061' in names:
                        device = child.resolve(strict=True)
                        back_reference = device / 'driver'
                        require(str(device).startswith('/sys/devices/') and
                                re.fullmatch(r'[0-9a-f]+\.pl061', child.name) and
                                back_reference.is_symlink() and
                                back_reference.resolve(strict=True) == driver.resolve(strict=True),
                                'PL061 device/driver symlink binding differs')
                        bound_gpio.append(child.name)
                        binding_devices.append({'name': child.name, 'device_path': str(device),
                            'driver_back_reference': str(back_reference.resolve(strict=True)),
                            'compatible': [name.decode('ascii') for name in names]})
        require(bool(bound_gpio), 'virtual PL061 driver is not bound')
        pl061_binding = {'driver_path': str(driver), 'driver_realpath': str(driver.resolve(strict=True)),
                         'devices': binding_devices, 'actual_sysfs_readback': True}
        live_acl = {}
        for name, expected in profile['journal_acl_check'].items():
            require(name in ('system.posix_acl_access', 'system.posix_acl_default'), 'unexpected ACL probe name')
            raw = os.getxattr('/var/log/journal', name, follow_symlinks=False)
            live_acl[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
            require(live_acl[name] == {key: expected[key] for key in ('sha256', 'size')},
                    'booted ext4 did not retain the qualified journal ACL')
        progress('independent_foundation_checks_verified', {
            'pids_enforcement_probe': pids_proof, 'active_lsm': lsm,
            'module_signature_enforced': True, 'module_sig_enforce_sysfs': sig_enforce_raw,
            'kernel_btf_sha256': btf_hash, 'kernel_btf_size': btf_size,
            'autofs_loaded': True, 'autofs_module_signature': autofs_signature,
            'kernel_tainted_before_bpf_probe': tainted, 'pl061_bound_devices': bound_gpio,
            'pl061_binding_proof': pl061_binding,
            'journal_acl_preserved_in_booted_image': live_acl})
        pair_nonce = secrets.token_hex(16)
        baseline_run = transient('proc-read', [], pair_nonce)
        baseline_proof = baseline_run.worker_result['details']
        progress('bpf_same_worker_baseline_attempt', {'exit_code': baseline_run.returncode,
                 'proof': baseline_proof, 'stdout': baseline_run.stdout, 'stderr': baseline_run.stderr})
        baseline_bytes = baseline_run.stdout.encode('utf-8')
        require(baseline_run.returncode == 0 and baseline_proof.get('outcome') == 'read' and
                baseline_run.stdout.startswith('Linux version ' + profile['kernel_release'] + ' ') and
                baseline_proof.get('data_bytes') == len(baseline_bytes) and
                baseline_proof.get('data_sha256') == hashlib.sha256(baseline_bytes).hexdigest(),
                'same observed worker baseline proc open/read did not match')
        fs_run = transient('proc-read', ['RestrictFileSystems=~proc'], pair_nonce)
        fs_proof = fs_run.worker_result['details']
        progress('bpf_restricted_direct_open_attempt', {'exit_code': fs_run.returncode,
                 'proof': fs_proof, 'stdout': fs_run.stdout, 'stderr': fs_run.stderr})
        require(fs_run.returncode == 1 and not fs_run.stdout and fs_proof.get('outcome') == 'error' and
                fs_proof.get('failure_phase') == 'open' and fs_proof.get('errno') == errno.EPERM and
                fs_proof.get('permission_denial') is True and fs_proof.get('data_bytes') == 0,
                'BPF file_open hook did not produce the source-qualified EPERM with no data')
        actual_baseline = baseline_run.descriptor_proof
        actual_restricted = fs_run.descriptor_proof
        setting_keys = ('ControlGroup', 'SELinuxContext', 'TasksMax', 'RuntimeMaxUSec')
        require(baseline_run.worker_argv == fs_run.worker_argv and
                actual_baseline['actual_worker']['selinux_context'] ==
                actual_restricted['actual_worker']['selinux_context'] == 'system_u:system_r:sysadm_t:s0' and
                all(actual_baseline['unit_properties'][key] == actual_restricted['unit_properties'][key]
                    for key in setting_keys) and
                actual_baseline['unit_properties']['RestrictFileSystems'] == '~' and
                actual_restricted['unit_properties']['RestrictFileSystems'] == '~proc',
                'BPF comparison changed an uncontrolled worker/domain/unit setting')
        bpf_deny_proof = {'method': 'same held worker direct open/read, no intervening exec',
                          'unrestricted_read_succeeded': True, 'baseline_exit_code': baseline_run.returncode,
                          'baseline_same_worker_argv_domain_and_unit': True,
                          'baseline_payload': baseline_proof,
                          'baseline_stdout': baseline_run.stdout,
                          'baseline_worker_argv': baseline_run.worker_argv,
                          'restricted_worker_argv': fs_run.worker_argv,
                          'restriction': 'RestrictFileSystems=~proc',
                          'restricted_exit_code': fs_run.returncode, 'restricted_stdout_empty': True,
                          'restricted_direct_open': fs_proof, 'owned_unit_collected': True,
                          'baseline_descriptor_proof': actual_baseline,
                          'restricted_descriptor_proof': actual_restricted}
        with Path('/sys/fs/selinux/policy').open('rb') as stream:
            policy_after = stream.read(32 * 1024**2 + 1)
        require(policy_after == loaded, 'active policy changed across the actual security comparisons')
        tainted = int(Path('/proc/sys/kernel/tainted').read_text().strip())
        require(tainted == 0, 'running kernel became tainted during the behavioral probes')
        journal_sync = diagnostic_command(['/usr/bin/journalctl', '--sync'])
        progress('journal_sync_success_path', journal_sync)
        require(journal_sync.get('exit_code') == 0 and
                journal_sync.get('stdout_truncated') is False and journal_sync.get('stderr_truncated') is False,
                'actual success-path journalctl --sync did not complete')
        audit_printk_after = {
            'interval': int(Path('/proc/sys/kernel/printk_ratelimit').read_text().strip()),
            'burst': int(Path('/proc/sys/kernel/printk_ratelimit_burst').read_text().strip())}
        require(audit_printk_after == audit_printk_before,
                'audit printk observation setting changed during verification')
        failed = run('/usr/bin/systemctl', 'list-units', '--failed', '--no-legend', '--plain')
        result = {
            'scope': 'generic ARM64 VM with no physical device passthrough',
            'profile_sha256': identities[0], 'kernel_release': platform.release(), 'pid1': pid1,
            'root_source': root_source, 'root_type': root_type, 'root_label': root_label,
            'selinux': run('/usr/sbin/getenforce'),
            'kernel_supported_policy_version': Path('/sys/fs/selinux/policyvers').read_text().strip(),
            'loaded_policy_version': policy_version, 'loaded_policy_bytes': len(loaded),
            'loaded_policy_sha256': hashlib.sha256(loaded).hexdigest(),
            'pid1_selinux_context': Path('/proc/1/attr/current').read_text().strip('\0\n'),
            'systemd': run('/usr/bin/systemctl', '--version').splitlines()[0],
            'multi_user_target': run('/usr/bin/systemctl', 'is-active', 'multi-user.target'),
            'udev': run('/usr/bin/systemctl', 'is-active', 'systemd-udevd.service'),
            'dbus': run('/usr/bin/systemctl', 'is-active', 'dbus.service'),
            'module_files_verified': runtime['module_count'], 'firmware_files_verified': runtime['firmware_file_count'],
            'compiled_module_sig_force': profile['configured_module_sig_force'],
            'module_signature_enforced': True, 'module_sig_enforce_sysfs': sig_enforce_raw,
            'all_runtime_hashes_verified': True, 'failed_units': failed.splitlines() if failed else [],
            'cgroup_controllers': controllers, 'validation_control_group': group, 'validation_pids_max': pids_max,
            'pids_events': (group_path / 'pids.events').read_text().strip(), 'active_lsm': lsm,
            'pids_enforcement_probe': pids_proof, 'bpf_lsm_deny_probe': bpf_deny_proof,
            'system_bus_proof': system_bus_proof,
            'validation_selinux_context': service_context,
            'actual_broker_processes': actual_broker,
            'loaded_policy_access': {key: value for key, value in loaded_policy_access.items()
                                     if key not in ('queries', 'contexts', 'return_codes', 'descriptor_inputs')},
            'actual_loaded_policy_export': exported_policy,
            'active_policy_unchanged_across_probes': True,
            'pids_descriptor_proof': pids_run.descriptor_proof,
            'transient_policy_contracts': {'noop': bus_run.policy_contract,
                'pids': pids_run.policy_contract, 'proc_read_baseline': baseline_run.policy_contract,
                'proc_read_restricted': fs_run.policy_contract},
            'initrd_process_domains': initrd_proof,
            'early_selinux_opt_in': True,
            'kernel_rdinit': '/init.tmpfs', 'tmpfs_root_opt_in': True,
            'autofs_loaded': True, 'autofs_misc_interface': True, 'autofs_module_signature': autofs_signature,
            'autofs_module_taint': (Path('/sys/module/autofs4/taint').read_text().strip()
                                    if Path('/sys/module/autofs4/taint').is_file() else None),
            'kernel_tainted': tainted, 'kernel_btf_sha256': btf_hash, 'kernel_btf_size': btf_size,
            'pl061_bound_devices': bound_gpio,
            'pl061_binding_proof': pl061_binding,
            'journal_sync_success_path': journal_sync,
            'audit_printk_observation': {'state_before_tests': audit_printk_before,
                'state_after_tests': audit_printk_after, 'explicit_opt_in': True,
                'guest_verifier_wrote_sysctl': False, 'audit_or_selinux_disabled': False},
            'journal_acl_preserved_in_booted_image': live_acl,
            'tablet_hardware_tested': False, 'gpu_acceleration_tested': False,
        }
        require(result['pid1_selinux_context'].split(':')[2:3] == ['init_t'], 'systemd did not enter init_t')
        require(result['selinux'] == 'Enforcing' and not result['failed_units'], 'complete system gate failed')
        seal_result('pass', result=result)
        emit('TB371FC_R4F_VM_SYSTEM_COMPLETE')
    # All guards above are required before this private VM is powered off.
    subprocess.run(['/usr/bin/systemctl', '--no-block', 'poweroff'], check=True, timeout=30)


if __name__ == '__main__':
    try:
        main()
    except Exception as original_error:
        error_trace = traceback.format_exc()
        if DIAGNOSTICS_READY:
            try:
                failure_diagnostics(error_trace)
            except Exception as error:
                print('TB371FC_R4F_DIAGNOSTICS_ERROR ' + type(error).__name__ + ': ' + str(error), flush=True)
        if RESULT_IDENTITY is not None:
            try:
                seal_result('fail', failure={'type': type(original_error).__name__,
                    'message': str(original_error)[:2048], 'traceback': error_trace[-8192:]})
            except Exception as error:
                print('TB371FC_R4F_RESULT_FILE_ERROR ' + type(error).__name__ + ': ' + str(error)[:1024], flush=True)
        print(error_trace, file=sys.stderr, flush=True)
        print('TB371FC_R4F_VM_VALIDATION_FAILED', flush=True)
        sys.exit(1)
