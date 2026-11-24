#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guarded verification inside this project's generic ARM64 system VM only."""
import hashlib
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

from tb371fc_loaded_policy import probe as query_loaded_policy

PROFILE = Path('/usr/share/tb371fc/system-profile.json')
UNIT = 'tb371fc-r4b-validation.service'
DIAGNOSTICS_READY = False


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
    # journal+console prefixes service stdout with timestamps/PIDs. After the
    # VM guards pass, write the proof as its own console line so the host can
    # require an exact marker/JSON line, even if a getty prompt was unfinished.
    with Path('/dev/console').open('w') as console:
        console.write('\n' + message + '\n')
        console.flush()


def progress(stage, details):
    emit('TB371FC_R4B_VM_PROGRESS ' + json.dumps({
        'stage': stage, 'details': details, 'complete_system_pass': False,
        'physical_hardware_tested': False,
    }, sort_keys=True))


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


def transient(name, properties, command):
    """Only a fresh, explicitly named unit can be cleaned up by this helper."""
    require(name in ('tb371fc-r4b-pids-proof.service', 'tb371fc-r4b-fs-proof.service', 'tb371fc-r4b-bus-proof.service'), 'unowned transient name')
    state = run('/usr/bin/systemctl', 'show', '--property=LoadState', '--value', name, check=False)
    require(state == 'not-found', 'transient proof name already exists')
    args = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect', '--unit=' + name,
            '--property=RuntimeMaxSec=8s', '--setenv=LC_ALL=C']
    args += ['--property=' + value for value in properties]
    result = None
    try:
        # Same --wait/--pipe system-bus route as R3. Keep the actual pipe FDs
        # observable; never substitute PID1's private socket for this gate.
        environment = os.environ.copy()
        environment['SYSTEMD_LOG_LEVEL'] = 'debug'
        child = subprocess.Popen([*args, *command], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, env=environment)
        try:
            descriptors = {'creator': process_context(os.getpid()),
                           'stdin': descriptor_context(0),
                           'stdout_pipe': descriptor_context(child.stdout.fileno()),
                           'stderr_pipe': descriptor_context(child.stderr.fileno())}
            progress('transient_client_started', {'unit': name, 'command': command,
                     'properties': properties, **descriptors,
                     'client': process_context(child.pid), 'systemd_client_debug_logging': True})
            require(descriptors['creator'].get('selinux_context') == 'system_u:system_r:initrc_t:s0',
                    'actual descriptor creator is not the qualified service domain')
            for pipe_name in ('stdout_pipe', 'stderr_pipe'):
                pipe = descriptors[pipe_name]
                require(stat.S_ISFIFO(pipe.get('mode', 0)) and
                        pipe.get('inode_selinux_context') == 'system_u:system_r:initrc_t:s0',
                        'actual transient pipe type/label differs from queried policy target')
            stdout, stderr = child.communicate(timeout=12)
            result = subprocess.CompletedProcess([*args, *command], child.returncode, stdout, stderr)
            result.descriptor_proof = descriptors
        finally:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            child.stdout.close()
            child.stderr.close()
    finally:
        # The name was absent before this attempt and cannot refer to another
        # job created by this workflow. RuntimeMaxSec also bounds its lifetime.
        state = run('/usr/bin/systemctl', 'show', '--property=LoadState', '--value', name, check=False)
        if state != 'not-found':
            run('/usr/bin/systemctl', 'stop', name, check=False, timeout=5)
        deadline = time.monotonic() + 4
        while state != 'not-found' and time.monotonic() < deadline:
            time.sleep(0.1)
            state = run('/usr/bin/systemctl', 'show', '--property=LoadState', '--value', name, check=False)
        require(state == 'not-found', 'owned transient proof unit was not collected')
    require(len(result.stdout.encode()) + len(result.stderr.encode()) < 65536, 'transient output bound exceeded')
    return result


def main():
    global DIAGNOSTICS_READY
    words = Path('/proc/cmdline').read_text().split()
    phases = [x.split('=', 1)[1] for x in words if x.startswith('tb371fc.r4b-phase=')]
    identities = [x.split('=', 1)[1] for x in words if x.startswith('tb371fc.r4b-profile=')]
    require(len(phases) == 1 and phases[0] in ('label', 'verify'), 'exact isolated VM phase missing')
    require(len(identities) == 1 and identities[0] == digest(PROFILE, 65536)[0], 'new VM profile token mismatch')
    phase = phases[0]
    profile = json.loads(PROFILE.read_text())
    require(profile['schema_version'] == 1, 'unknown profile version')
    compatible = Path('/proc/device-tree/compatible').read_bytes().rstrip(b'\0').split(b'\0')
    require(b'linux,dummy-virt' in compatible, 'not the owned generic ARM virt machine')
    root_source = run('/usr/bin/findmnt', '-n', '-o', 'SOURCE', '/')
    root_type = run('/usr/bin/findmnt', '-n', '-o', 'FSTYPE', '/')
    require(root_source == '/dev/vda' and root_type == 'ext4', 'unexpected root mount')
    root_label = run('/usr/sbin/blkid', '-s', 'LABEL', '-o', 'value', root_source)
    require(root_label == profile['root_label'] == 'tb371fc-r4b-f45', 'root is not the dedicated new image')
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
            '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430', 'Fedora source policy changed')
    if phase == 'label':
        require(enforce.read_text().strip() == '0', 'maintenance label requires explicit permissive VM boot')
        subprocess.run(['/usr/sbin/setfiles', '-F', '-e', '/proc', '-e', '/sys', '-e', '/dev', '-e', '/run',
                        '/etc/selinux/targeted/contexts/files/file_contexts', '/'], check=True, timeout=500)
        os.sync()
        emit('TB371FC_R4B_VM_LABEL_COMPLETE')
    else:
        require(enforce.read_text().strip() == '1', 'verification boot must enforce SELinux')
        DIAGNOSTICS_READY = True
        require(words.count('rd.tb371fc.early-selinux=1') == 1 and
                len([word for word in words if word.startswith('rd.tb371fc.early-selinux=')]) == 1,
                'explicit early SELinux bootstrap opt-in missing or ambiguous')
        service_context = Path('/proc/self/attr/current').read_text().strip('\0\n')
        require(service_context == profile['validation_selinux_context'] == 'system_u:system_r:initrc_t:s0',
                'strict verification service exec context was not entered')
        initrd_proof_path = Path('/run/tb371fc-r4b-initrd-domains.json')
        require(initrd_proof_path.is_file() and not initrd_proof_path.is_symlink() and
                initrd_proof_path.stat().st_size <= 4096, 'bounded same-boot initrd domain proof missing')
        initrd_proof = json.loads(initrd_proof_path.read_text())
        require(initrd_proof.get('schema_version') == 1 and
                initrd_proof.get('scope') == 'initrd before switch-root' and
                initrd_proof.get('boot_id') == Path('/proc/sys/kernel/random/boot_id').read_text().strip() and
                initrd_proof.get('pid1_context') == 'system_u:system_r:init_t:s0' and
                initrd_proof.get('udevd_context', '').split(':')[2:3] == ['udev_t'] and
                initrd_proof.get('read_only_process_probe') is True,
                'initrd process domain proof differs from this boot or required domains')
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
        loaded_policy_access = query_loaded_policy(loaded, child_context, service_context)
        progress('actual_loaded_policy_access', loaded_policy_access)
        require(loaded_policy_access.get('query_completed') is True and
                loaded_policy_access.get('actual_service_fd_and_fifo_allowed') is True and
                loaded_policy_access.get('unconfined_service_fifo_restriction_retained') is True,
                'actual exported policy did not confirm service access and retained FIFO restriction')
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
        bus_run = transient('tb371fc-r4b-bus-proof.service', [], ['/usr/bin/true'])
        progress('system_bus_pipe_baseline', {'exit_code': bus_run.returncode,
                 'stdout': bus_run.stdout, 'stderr': bus_run.stderr})
        require(bus_run.returncode == 0 and not bus_run.stdout,
                'system-bus --wait/--pipe baseline failed before resource probes')
        system_bus_proof = {'broker_get_id_roundtrip': True, 'manager_version_roundtrip': True,
                            'manager_version_reply': manager['stdout'].strip(),
                            'wait_pipe_true_exit_code': bus_run.returncode,
                            'wait_pipe_true_stdout_empty': True, 'owned_unit_collected': True,
                            'private_socket_used_for_transient_probe': False,
                            'actual_descriptor_proof': bus_run.descriptor_proof}
        pids_run = transient('tb371fc-r4b-pids-proof.service', ['TasksMax=3'],
                             ['/usr/bin/python3', '/usr/libexec/tb371fc-r4b-pids-probe.py'])
        pids_lines = [line for line in pids_run.stdout.splitlines() if line.startswith('TB371FC_R4B_PIDS_PROOF ')]
        progress('pids_probe_attempt', {'exit_code': pids_run.returncode,
                                       'stdout': pids_run.stdout, 'stderr': pids_run.stderr})
        require(pids_run.returncode == 0 and len(pids_lines) == 1, 'controlled pids limit probe did not pass')
        pids_proof = json.loads(pids_lines[0].split(' ', 1)[1])
        require(pids_proof.get('passed') and pids_proof.get('all_owned_children_reaped'), 'controlled pids cleanup/proof failed')
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
        driver = Path('/sys/bus/amba/drivers/pl061')
        if driver.is_dir():
            for child in sorted(driver.iterdir()):
                prop = child / 'of_node/compatible'
                if child.is_symlink() and prop.is_file():
                    names = prop.read_bytes().rstrip(b'\0').split(b'\0')
                    if b'arm,pl061' in names:
                        bound_gpio.append(child.name)
        require(bool(bound_gpio), 'virtual PL061 driver is not bound')
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
            'journal_acl_preserved_in_booted_image': live_acl})
        baseline_run = transient('tb371fc-r4b-fs-proof.service', [], ['/usr/bin/cat', '/proc/version'])
        progress('bpf_same_unit_baseline_attempt', {'exit_code': baseline_run.returncode,
                 'stdout': baseline_run.stdout, 'stderr': baseline_run.stderr})
        require(baseline_run.returncode == 0 and
                baseline_run.stdout.startswith('Linux version ' + profile['kernel_release'] + ' '),
                'same transient-unit baseline proc read failed')
        fs_run = transient('tb371fc-r4b-fs-proof.service', ['RestrictFileSystems=~proc'],
                           ['/usr/bin/cat', '/proc/version'])
        progress('bpf_restricted_read_attempt', {'exit_code': fs_run.returncode,
                 'stdout': fs_run.stdout, 'stderr': fs_run.stderr,
                 'restriction': 'RestrictFileSystems=~proc'})
        denied_line = re.search(r'(?:^|\n)(?:/usr/bin/)?cat: /proc/version: (Permission denied|Operation not permitted)(?:\n|$)',
                                fs_run.stderr)
        require(fs_run.returncode == 1 and not fs_run.stdout and denied_line,
                'BPF LSM did not deny the controlled proc read as expected')
        bpf_deny_proof = {'unrestricted_read_succeeded': True, 'baseline_exit_code': baseline_run.returncode,
                          'baseline_same_transient_unit_and_command': True,
                          'restriction': 'RestrictFileSystems=~proc',
                          'restricted_exit_code': fs_run.returncode, 'restricted_stdout_empty': True,
                          'restricted_error': fs_run.stderr.strip(), 'owned_unit_collected': True}
        tainted = int(Path('/proc/sys/kernel/tainted').read_text().strip())
        require(tainted == 0, 'running kernel became tainted during the behavioral probes')
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
            'loaded_policy_access': loaded_policy_access,
            'initrd_process_domains': initrd_proof,
            'early_selinux_opt_in': True,
            'autofs_loaded': True, 'autofs_misc_interface': True, 'autofs_module_signature': autofs_signature,
            'autofs_module_taint': (Path('/sys/module/autofs4/taint').read_text().strip()
                                    if Path('/sys/module/autofs4/taint').is_file() else None),
            'kernel_tainted': tainted, 'kernel_btf_sha256': btf_hash, 'kernel_btf_size': btf_size,
            'pl061_bound_devices': bound_gpio,
            'journal_acl_preserved_in_booted_image': live_acl,
            'tablet_hardware_tested': False, 'gpu_acceleration_tested': False,
        }
        require(result['pid1_selinux_context'].split(':')[2:3] == ['init_t'], 'systemd did not enter init_t')
        require(result['selinux'] == 'Enforcing' and not result['failed_units'], 'complete system gate failed')
        emit('TB371FC_R4B_VM_RESULT ' + json.dumps(result, sort_keys=True))
        emit('TB371FC_R4B_VM_SYSTEM_COMPLETE')
    # All guards above are required before this private VM is powered off.
    subprocess.run(['/usr/bin/systemctl', '--no-block', 'poweroff'], check=True, timeout=30)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        error_trace = traceback.format_exc()
        if DIAGNOSTICS_READY:
            try:
                failure_diagnostics(error_trace)
            except Exception as error:
                print('TB371FC_R4B_DIAGNOSTICS_ERROR ' + type(error).__name__ + ': ' + str(error), flush=True)
        print(error_trace, file=sys.stderr, flush=True)
        print('TB371FC_R4B_VM_VALIDATION_FAILED', flush=True)
        sys.exit(1)
