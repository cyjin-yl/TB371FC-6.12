#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bind unchanged R7 generic-virt label/verify boots to closed image hashes.

Run in the established HDD build container under the original heavy-job
admission. This modifies only the newly constructed R7 ordinary ext4 image.
The frozen VM acceptance code is regenerated, compared and reused unchanged.
"""
from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone

RELEASE = '6.12.114-tb371fc-research7-rpmh-clock'
LABEL = 'tb371fc-r7-f45'
PROFILE = 'research7-rpmh-clock-fedora45-derived-v9'
SCHEMA = 'tb371fc-r7-generic-vm-v1'
ROOTFS_PHASE = 'generic-vm-verified-v1'
CONSTRUCTOR = 'scripts/research/system-kernel/research7-rpmh-clock/build_rpmh_rootfs.py'
CONSTRUCTOR_SHA = '8786cd5da535ea2ff007eb6a3eef2e393b6ef582fca52890e8adc040315be3ff'
DRIVER_SHA = '4d1f59691bb4faccdcdbd791ae2120a89e56f7712fd63270f0a2204662842736'
TOOLS = {
    '/usr/bin/qemu-system-aarch64': {'bytes': 34073536, 'sha256': '2e7fe3008a900980493a85e606036793fd162153edac0228477579988c53e1f5'},
    '/usr/sbin/debugfs': {'bytes': 255824, 'sha256': 'deb37b9515718738f369dfe0546a50a74fdd7d5837046adac272ef6a3381ccee'},
}
ROOT_BYTES = 4 * 1024**3
CANCEL_SIGNAL = None


def require(value, message):
    if not value:
        raise ValueError(message)


def utc():
    return datetime.now(timezone.utc).isoformat()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(), object_pairs_hook=unique_object)


def identity(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode), 'ordinary file required: ' + str(path))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = os.fstat(descriptor)
        named = path.lstat()
        keys = ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(all(getattr(before, k) == getattr(after, k) == getattr(named, k) for k in keys),
                'file changed while hashing: ' + str(path))
        return {'bytes': before.st_size, 'sha256': digest}
    finally:
        os.close(descriptor)


def pinned(path, expected):
    value = identity(path)
    require(value == expected if isinstance(expected, dict) else value['sha256'] == expected,
            'file identity differs: ' + str(path))
    return value


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def cancelled():
    if CANCEL_SIGNAL is not None:
        raise InterruptedError('R7 generic VM interrupted by signal ' + str(CANCEL_SIGNAL))


def on_signal(number, unused):
    global CANCEL_SIGNAL
    if CANCEL_SIGNAL is None:
        CANCEL_SIGNAL = number


def enable_subreaper():
    # The frozen driver gives its QEMU child a separate session. Adopting
    # orphan descendants lets this wrapper reap that child if the driver dies.
    require(sys.platform == 'linux', 'Linux child-subreaper ownership required')
    libc = ctypes.CDLL(None, use_errno=True)
    require(libc.prctl(36, 1, 0, 0, 0) == 0, 'PR_SET_CHILD_SUBREAPER failed')
    value = ctypes.c_int()
    require(libc.prctl(37, ctypes.byref(value), 0, 0, 0) == 0 and value.value == 1,
            'child-subreaper readback failed')


def descendants():
    # /proc/PID/task/PID/children is optional (CONFIG_CHECKPOINT_RESTORE).
    # PPid is available in proc stat and also covers forks from other threads.
    by_parent = {}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / 'stat').read_text()
        except (FileNotFoundError, ProcessLookupError):
            continue
        fields = raw[raw.rfind(')') + 2:].split()
        require(len(fields) >= 20, 'incomplete proc identity: ' + str(path))
        by_parent.setdefault(int(fields[1]), []).append(int(path.name))
    found = set()
    todo = list(by_parent.get(os.getpid(), []))
    while todo:
        pid = todo.pop()
        if pid not in found:
            found.add(pid)
            todo.extend(by_parent.get(pid, []))
    return found


def kill_owned(pid, sig):
    # A pidfd binds the signal to this process, never to a reused numeric PID.
    try:
        descriptor = os.pidfd_open(pid)
    except ProcessLookupError:
        return
    try:
        if pid in descendants():
            signal.pidfd_send_signal(descriptor, sig)
    except ProcessLookupError:
        pass
    finally:
        os.close(descriptor)


def reap_orphans():
    diagnostic = time.monotonic() + 30
    observed = sorted(descendants())
    while True:
        for pid in sorted(descendants(), reverse=True):
            kill_owned(pid, signal.SIGKILL)
        while True:
            try:
                pid, unused = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if pid == 0:
                break
        if not descendants():
            return observed
        if time.monotonic() >= diagnostic:
            print(json.dumps({'cleanup_pending_owned_pids': sorted(descendants()),
                              'admission_must_remain_held': True, 'utc': utc()}), flush=True)
            diagnostic = time.monotonic() + 30
        time.sleep(.05)


def group_empty(group):
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    return False


def run_owned(argv, log, *, timeout=1200, receipt=None):
    cancelled()
    require(not descendants(), 'wrapper already owns an unexpected child')
    proc = None
    info = receipt if receipt is not None else {}
    info.update(exit_code=None, child_reaped=False, process_group_empty=False,
                all_owned_descendants_reaped=False, orphan_descendants_found=[])
    error = None
    with log.open('xb') as stream:
        try:
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stream,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + timeout
            while proc.poll() is None:
                cancelled()
                require(time.monotonic() < deadline, 'bounded generic VM driver timed out')
                require(log.stat().st_size <= 4 * 1024**2, 'driver output exceeded four MiB')
                time.sleep(.25)
            cancelled()
        except BaseException as caught:
            error = caught
        finally:
            if proc is not None:
                if proc.poll() is None:
                    kill_owned(proc.pid, signal.SIGTERM)
                    deadline = time.monotonic() + 30
                    while proc.poll() is None and time.monotonic() < deadline:
                        time.sleep(.1)
                    if proc.poll() is None:
                        for pid in sorted(descendants(), reverse=True):
                            kill_owned(pid, signal.SIGKILL)
                    diagnostic = time.monotonic() + 30
                    while proc.poll() is None:
                        for pid in sorted(descendants(), reverse=True):
                            kill_owned(pid, signal.SIGKILL)
                        try:
                            proc.wait(timeout=.5)
                        except subprocess.TimeoutExpired:
                            pass
                        if time.monotonic() >= diagnostic:
                            print(json.dumps({'cleanup_pending_owned_pids': sorted(descendants()),
                                              'admission_must_remain_held': True, 'utc': utc()}), flush=True)
                            diagnostic = time.monotonic() + 30
                info['exit_code'] = proc.returncode
                info['child_reaped'] = True
                info['orphan_descendants_found'] = reap_orphans()
                info['all_owned_descendants_reaped'] = not descendants()
                info['process_group_empty'] = group_empty(proc.pid)
    if error is not None:
        raise error
    require(log.stat().st_size <= 4 * 1024**2, 'completed driver output exceeded four MiB')
    require(info['exit_code'] == 0 and info['child_reaped'] and info['process_group_empty']
            and info['all_owned_descendants_reaped'] and not info['orphan_descendants_found'],
            'generic VM driver failed or left an owned process')
    return info


def expected_command(work, phase, profile_sha):
    root = work / 'rootfs'
    image = work / 'fedora45-research7-rpmh-clock.ext4'
    initrd = root / 'boot' / ('initramfs-' + RELEASE + ('-maintenance' if phase == 'label' else '') + '.img')
    command_line = (f'console=ttyAMA0 root=LABEL={LABEL} rootfstype=ext4 rw '
                    'rd.luks=0 rd.lvm=0 rd.md=0 rd.dm=0 rd.neednet=0 '
                    'module.sig_enforce=1 '
                    'systemd.unit=tb371fc-r4f-validation.target systemd.show_status=yes '
                    'systemd.log_target=console systemd.log_level=debug selinux=1 enforcing=' +
                    ('0' if phase == 'label' else '1 rd.tb371fc.early-selinux=1 rd.tb371fc.tmpfs-root=1 rdinit=/init.tmpfs rd.tb371fc.audit-printk-unlimited=1') +
                    f' tb371fc.r4f-phase={phase} tb371fc.r4f-profile={profile_sha}')
    return ['/usr/bin/qemu-system-aarch64', '-machine', 'virt', '-cpu', 'cortex-a72',
            '-smp', '2', '-m', '2048', '-display', 'none', '-monitor', 'none',
            '-serial', 'stdio', '-nic', 'none', '-no-reboot', '-kernel', str(root / 'boot' / ('Image-' + RELEASE)),
            '-initrd', str(initrd), '-append', command_line,
            '-drive', f'if=none,id=rootfs,format=raw,file={image}', '-device', 'virtio-blk-device,drive=rootfs']


def validate_archive_binding(construction, phase, observed):
    require(phase in ('label', 'verify'), 'unknown generic VM phase')
    role = 'maintenance' if phase == 'label' else 'production'
    archived = construction['archive_module_checks'][role]
    require(archived.get('passed') is True and archived.get('kernel_release') == RELEASE
            and archived['image'] == observed, 'phase archive differs from construction: ' + role)
    if phase == 'verify':
        require(observed == {key: construction['initrd'][key] for key in ('bytes', 'sha256')},
                'production initrd identity differs from construction')


def validate_phase_result(result, replay, phase, profile, profile_id, initrd_id, serial_id):
    expected = {'schema_version': 2, 'phase': phase, 'profile_sha256': profile_id['sha256'],
                'kernel_image_sha256': profile['kernel_image_sha256'], 'initramfs_sha256': initrd_id['sha256'],
                'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2,
                'qemu_exit_code': 0, 'termination_reason': None, 'passed': True,
                'physical_hardware_tested': False, 'physical_device_passthrough': False,
                'network': False, 'board_dtb_used': False, 'host_filesystem_shared': False,
                'vm_module_sig_enforce_argument': 'module.sig_enforce=1', 'compiled_module_sig_force': False,
                'systemd_debug_logging_for_this_vm_only': True,
                'initramfs_role': 'maintenance-label-only' if phase == 'label' else 'production-tmpfs-early-selinux',
                'early_selinux_argument': None if phase == 'label' else 'rd.tb371fc.early-selinux=1',
                'kernel_rdinit_argument': None if phase == 'label' else 'rdinit=/init.tmpfs',
                'audit_printk_observation_argument': None if phase == 'label' else 'rd.tb371fc.audit-printk-unlimited=1',
                'serial_log_sha256': serial_id['sha256'], 'serial_log_bytes': serial_id['bytes']}
    require(all(result.get(key) == value and (not isinstance(value, bool) or result.get(key) is value)
                for key, value in expected.items()), 'generic VM result binding or scope differs')
    require(not any(key in result for key in ('error', 'parse_error', 'persistent_result_error')),
            'generic VM result contains an error')
    require(all(result.get(key) == value for key, value in replay.items() if key != 'persistent_result_metadata'),
            'inherited result differs from independent frozen acceptance reparse')
    require(replay.get('expected_marker_seen') is True and replay.get('marker_exact_line_count') == 1
            and all(replay.get(key) is False for key in
                    ('validation_failure_seen', 'kernel_panic_seen', 'invalid_initramfs_seen')),
            'same-boot completion or failure gates differ')
    if phase == 'verify':
        require(replay.get('guest_gates_match') is True and replay.get('persistent_result_qualified') is True
                and replay.get('guest_file_status') == 'pass'
                and all(type(value) is int and value == 0 for value in replay['observed_warning_counts'].values()),
                'production frozen guest gates failed')
        original, actual = result['persistent_result_metadata'], replay['persistent_result_metadata']
        keys = ('qualified', 'receipt', 'guest_inode', 'parent_inodes', 'image_opened_for_write',
                'image_mounted', 'filesystem_replayed_or_repaired', 'source_image_metadata_unchanged')
        require(all(original[key] == actual[key] for key in keys), 'same-boot result readback metadata differs')


def prepare_sources(repo, work, output):
    pinned(repo / CONSTRUCTOR, CONSTRUCTOR_SHA)
    constructor = load_module(repo / CONSTRUCTOR, 'r7_vm_constructor')
    source_ids = {CONSTRUCTOR: identity(repo / CONSTRUCTOR)}
    for name, digest in constructor.FROZEN.items():
        source_ids[name] = pinned(repo / name, digest)
    staging = constructor.load_module(repo / 'scripts/research/rootfs/stage_r5_fedora.py', 'stage_r5_fedora')
    materializer = constructor.load_module(repo / 'scripts/research/rootfs/materialize_r5_fedora_recipe.py', 'r7_vm_materializer')
    derived = constructor.derive_recipe(repo, output / 'expected-r5-template', output / 'expected-recipe', materializer, staging)
    for name in materializer.PINS:
        path = materializer.V9 / name
        source_ids[str(path)] = identity(repo / path)
    for path, unused in materializer.SUPPLEMENT.values():
        source_ids[str(path)] = identity(repo / path)
    require(set(path.name for path in (work / 'recipe').iterdir()) == set(derived['derived']) | {'derivation.json'},
            'executed recipe inventory differs')
    for name, expected in derived['derived'].items():
        require(staging.identity(work / 'recipe' / name) == expected, 'executed recipe differs: ' + name)
    require(read_json(work / 'recipe/derivation.json') == derived, 'recorded recipe derivation differs')
    pinned(work / 'recipe/boot_system_vm.py', DRIVER_SHA)
    load_module(work / 'recipe/stage_r5_fedora.py', 'stage_r5_fedora')
    common = load_module(work / 'recipe/system_common.py', 'system_common')
    reader = load_module(work / 'recipe/read_vm_result.py', 'read_vm_result')
    driver = load_module(work / 'recipe/boot_system_vm.py', 'r7_frozen_vm_driver')
    return source_ids, derived, common, reader, driver


def run(repo, work, construction_sha):
    require(os.environ.get('MAKEFLAGS') == '-j2', 'original admitted two-job environment required')
    require(re.fullmatch('[0-9a-f]{64}', construction_sha) is not None, 'exact construction receipt SHA required')
    for path in (repo, work):
        require(path.is_absolute() and path.is_dir() and not path.is_symlink() and path.resolve() == path,
                'canonical input directory required: ' + str(path))
    require(work.parent == Path('/work') and work.name.startswith('fedora-r7-system-'), 'dedicated R7 work required')
    require(not list(work.glob('vm-*')) and not os.path.lexists(work / 'r7-generic-vm-result.json'),
            'generic VM phases must start once from the constructed image')
    os.umask(0o077)
    sys.dont_write_bytecode = True
    output = work / 'r7-generic-vm'
    output.mkdir(mode=0o700)
    record = {'schema': SCHEMA, 'rootfs_phase': ROOTFS_PHASE, 'passed': False, 'kernel_release': RELEASE,
              'started_utc': utc(), 'finished_utc': None, 'wrapper_source': identity(Path(__file__)),
              'construction_result': None, 'profile': None, 'initial_rootfs': None, 'final_rootfs': None,
              'tools': {}, 'source_inputs': {}, 'phases': [], 'inputs_reverified': False,
              'generic_virt_acceptance': False, 'board_model_verified': False, 'physical_boot_verified': False,
              'native_userspace_verified': False, 'owner_native_linux_passes_added': 0, 'error': None}
    handlers = {number: signal.signal(number, on_signal) for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    image = work / 'fedora45-research7-rpmh-clock.ext4'
    lock = None
    try:
        record['construction_result'] = pinned(work / 'r7-construction-result.json', construction_sha)
        construction = read_json(work / 'r7-construction-result.json')
        require(construction.get('complete') is True and construction.get('kernel_release') == RELEASE
                and construction.get('constructor', {}).get('sha256') == CONSTRUCTOR_SHA
                and construction.get('retained_inputs_reverified') is True
                and construction.get('module_count') == 84 and construction.get('owner_native_linux_passes_added') == 0,
                'qualified completed R7 construction required')
        require(all(construction.get(key) is False for key in
                    ('physical_boot_verified', 'userspace_verified', 'runtime_signature_enforcement_verified')),
                'construction scope differs')
        expected_root = {key: construction['rootfs'][key] for key in ('bytes', 'sha256')}
        require(expected_root['bytes'] == ROOT_BYTES and construction['rootfs']['path'] == str(image)
                and construction['rootfs']['label'] == LABEL and image.lstat().st_nlink == 1,
                'new four-GiB ordinary R7 image required')
        lock = os.open(image, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        record['tools'] = {name: pinned(Path(name), expected) for name, expected in TOOLS.items()}
        source_ids, derived, common, reader, driver = prepare_sources(repo, work, output)
        record['source_inputs'] = source_ids
        profile = common.profile()
        profile_id = pinned(work / 'system-profile.json', construction['profile'])
        pinned(common.PROFILE, profile_id)
        require(profile['profile'] == PROFILE and profile['kernel_release'] == RELEASE and profile['root_label'] == LABEL,
                'exact R7 system profile required')
        record['profile'] = profile_id
        production = {key: construction['initrd'][key] for key in ('bytes', 'sha256')}
        pinned(work / 'initramfs-production-qualified.img', production)
        fixed = {work / 'r7-construction-result.json': record['construction_result'],
                 work / 'system-profile.json': profile_id, common.PROFILE: profile_id,
                 work / 'r7-runtime-stage.json': identity(work / 'r7-runtime-stage.json'),
                 work / 'recipe/derivation.json': identity(work / 'recipe/derivation.json'),
                 work / 'initramfs-production-qualified.img': production,
                 Path(__file__): record['wrapper_source']}
        for name, expected in derived['derived'].items():
            fixed[work / 'recipe' / name] = {key: expected[key] for key in ('bytes', 'sha256')}
        fixed[common.ROOT / 'boot' / ('Image-' + RELEASE)] = pinned(common.ROOT / 'boot' / ('Image-' + RELEASE), profile['kernel_image_sha256'])
        initrd_ids = {}
        for phase, manifest in (('label', 'maintenance-initramfs.json'), ('verify', 'initramfs.json')):
            fixed[work / manifest] = identity(work / manifest)
            value = read_json(work / manifest)
            initrd = common.ROOT / 'boot' / ('initramfs-' + RELEASE + ('-maintenance' if phase == 'label' else '') + '.img')
            require(value['path'] == str(initrd) and value['archive_verified'] is True, 'phase archive binding differs')
            initrd_ids[phase] = pinned(initrd, {'bytes': value['size_bytes'], 'sha256': value['sha256']})
            validate_archive_binding(construction, phase, initrd_ids[phase])
            fixed[initrd] = initrd_ids[phase]
            qualified = work / ('initramfs-' + ('maintenance' if phase == 'label' else 'production') + '-qualified.img')
            fixed[qualified] = pinned(qualified, initrd_ids[phase])
        require(initrd_ids['verify'] == production, 'production archive differs from construction')
        enable_subreaper()
        require(not descendants(), 'fresh wrapper process must have no pre-existing children')
        previous = expected_root
        for phase in ('label', 'verify'):
            cancelled()
            for path, expected in fixed.items():
                pinned(path, expected)
            for name, expected in record['tools'].items():
                pinned(Path(name), expected)
            before = pinned(image, previous)
            if phase == 'label':
                record['initial_rootfs'] = before
            print(json.dumps({'phase_started': phase, 'rootfs_before': before, 'utc': utc()}), flush=True)
            run_name = 'vm-' + phase + '-01'
            row = {'phase': phase, 'run': run_name, 'started_utc': utc(), 'finished_utc': None,
                   'rootfs_before': before, 'rootfs_after': None, 'result': None, 'command': None,
                   'serial': None, 'guest_result': None, 'reparsed_result': None,
                   'driver_source': identity(work / 'recipe/boot_system_vm.py'),
                   'driver_log': None, 'exit_code': None, 'child_reaped': False,
                   'process_group_empty': False, 'all_owned_descendants_reaped': False,
                   'orphan_descendants_found': [], 'acceptance_reparsed': False}
            record['phases'].append(row)
            log = output / (phase + '.driver.log')
            try:
                run_owned([sys.executable, '-B', '-O', str(work / 'recipe/boot_system_vm.py'), phase, '--run', run_name], log,
                          receipt=row)
            except BaseException:
                if row['all_owned_descendants_reaped']:
                    row['rootfs_after'] = identity(image)
                raise
            finally:
                if log.exists():
                    row['driver_log'] = identity(log)
            phase_dir = work / run_name
            for key, name in (('result', 'result.json'), ('command', 'command.json'), ('serial', 'serial.log')):
                row[key] = identity(phase_dir / name)
            require(row['serial']['bytes'] <= 8 * 1024**2, 'bounded full serial required')
            require(read_json(phase_dir / 'command.json') == expected_command(work, phase, profile_id['sha256']),
                    'actual generic VM argv differs')
            serial = (phase_dir / 'serial.log').read_bytes()
            persisted = None
            reparse_dir = output / ('reparse-' + phase)
            reparse_dir.mkdir(mode=0o700)
            if phase == 'verify':
                persisted = reader.extract(image, reparse_dir, serial, profile_id['sha256'])
                row['guest_result'] = identity(phase_dir / 'guest-result.json')
                pinned(reparse_dir / 'guest-result.json', row['guest_result'])
            replay = driver.inspect_serial(serial, phase, profile, profile_id['sha256'], persisted)
            validate_phase_result(read_json(phase_dir / 'result.json'), replay, phase, profile, profile_id,
                                  initrd_ids[phase], row['serial'])
            save(reparse_dir / 'inspection.json', replay)
            row['reparsed_result'] = identity(reparse_dir / 'inspection.json')
            row['acceptance_reparsed'] = True
            require(not descendants(), 'owned process still exists after result reparse')
            row['rootfs_after'] = identity(image)
            require(row['rootfs_after']['bytes'] == ROOT_BYTES, 'generic VM changed the image size')
            row['finished_utc'] = utc()
            previous = row['rootfs_after']
            print(json.dumps({'phase_completed': phase, 'rootfs_after': previous, 'utc': utc()}), flush=True)
        for path, expected in fixed.items():
            pinned(path, expected)
        for name, expected in source_ids.items():
            pinned(repo / name, expected)
        for name, expected in record['tools'].items():
            pinned(Path(name), expected)
        cancelled()
        record.update(passed=True, final_rootfs=previous, inputs_reverified=True, generic_virt_acceptance=True)
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        if lock is not None:
            os.close(lock)
        record['finished_utc'] = utc()
        save(work / 'r7-generic-vm-result.json', record)
        for number, handler in handlers.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--construction-result-sha256', required=True)
    args = parser.parse_args()
    run(args.repo, args.work, args.construction_result_sha256)
