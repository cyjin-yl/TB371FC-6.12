#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded owned-unit protocol with three observable forwarded FIFO endpoints.

The policy callback runs before launch on the actual newly created pipe
labels, actual creator, manager/broker and the explicit requested worker
domain. Its worker premise becomes qualified only after READY and the real
worker context readback match. No permission inference replaces that match.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

CONTEXT = 'system_u:system_r:sysadm_t:s0'
WORKER = Path('/usr/libexec/tb371fc-r4f-worker.py')
UNITS = {'noop': 'tb371fc-r4f-bus-proof.service',
         'pids': 'tb371fc-r4f-pids-proof.service',
         'proc-read': 'tb371fc-r4f-fs-proof.service'}
READY = b'TB371FC_R4F_WORKER_READY '
RESULT = b'TB371FC_R4F_WORKER_RESULT '
ERROR = b'TB371FC_R4F_WORKER_ERROR '
LIMIT = 65536


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def bounded_read(path, limit=65536):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'bounded observation exceeded: ' + str(path))
    return raw


def context(pid):
    return bounded_read('/proc/' + str(pid) + '/attr/current', 1024).decode('ascii').strip('\0\n')


def show_unit(name, fields, timeout=2):
    value = subprocess.run(['/usr/bin/systemctl', 'show', '--no-pager',
                            '--property=' + ','.join(fields), name],
                           capture_output=True, timeout=timeout)
    require(value.returncode == 0 and len(value.stdout) + len(value.stderr) <= 16384,
            'owned unit property read failed or exceeded its bound')
    result = {}
    for line in value.stdout.decode('utf-8', errors='strict').splitlines():
        key, separator, item = line.partition('=')
        require(separator and key in fields and key not in result, 'unexpected/duplicate unit property')
        result[key] = item
    require(set(result) == set(fields), 'requested unit properties missing')
    return result


def own_fd(fd, opener_context):
    info = os.fstat(fd)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    label = os.getxattr(fd, 'security.selinux').decode('ascii').strip('\0\n')
    require(stat.S_ISFIFO(info.st_mode) and label == CONTEXT, 'owned FIFO type/context differs')
    return {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
            'flags': flags, 'access_mode': flags & os.O_ACCMODE,
            'inode_selinux_context': label, 'creator_context': opener_context,
            'opener_provenance': 'pipe2 in the observed unchanged creator process; no relabel or exec'}


def process_start(pid):
    # The comm field can contain spaces; everything after its last ')' has a
    # fixed layout. starttime is field 22, index 19 after the state field.
    text = bounded_read('/proc/' + str(pid) + '/stat', 4096).decode('ascii')
    tail = text[text.rfind(')') + 2:].split()
    require(len(tail) > 19 and tail[19].isdigit(), 'worker start identity missing')
    return int(tail[19])


def observe_worker(ready, mode, nonce, profile_sha256, argv, forwarded):
    require(ready.get('schema_version') == 1 and ready.get('mode') == mode and
            ready.get('nonce') == nonce and ready.get('profile_sha256') == profile_sha256 and
            ready.get('expected_unit') == UNITS[mode] and
            ready.get('uid') == ready.get('euid') == 0,
            'worker READY does not identify this invocation')
    pid = ready.get('pid')
    require(type(pid) is int and 1 < pid < 2**31, 'worker PID outside explicit bound')
    start_before = process_start(pid)
    root = Path('/proc') / str(pid)
    actual_context = context(pid)
    actual_argv = bounded_read(root / 'cmdline', 8192).rstrip(b'\0').decode().split('\0')
    cgroup = bounded_read(root / 'cgroup', 4096).decode().strip()
    executable = os.readlink(root / 'exe')
    require(actual_context == CONTEXT and actual_argv == argv and
            executable == os.path.realpath('/usr/bin/python3') and
            cgroup == '0::/system.slice/' + UNITS[mode],
            'actual held worker domain/executable/argv/cgroup differs')
    actual = {}
    for fd in (0, 1, 2):
        path = root / 'fd' / str(fd)
        info = path.stat()
        target = os.readlink(path)
        label = os.getxattr(path, 'security.selinux').decode('ascii').strip('\0\n')
        lines = bounded_read(root / 'fdinfo' / str(fd), 4096).decode('ascii').splitlines()
        flags = [line.split(':', 1)[1].strip() for line in lines if line.startswith('flags:')]
        require(len(flags) == 1 and re.fullmatch('[0-7]+', flags[0]), 'actual worker FD flags missing')
        flags = int(flags[0], 8)
        expected = forwarded[str(fd)]
        reported = ready.get('descriptors', {}).get(str(fd), {})
        access_mode = os.O_RDONLY if fd == 0 else os.O_WRONLY
        require(stat.S_ISFIFO(info.st_mode) and target == 'pipe:[' + str(info.st_ino) + ']' and
                label == CONTEXT and (flags & os.O_ACCMODE) == access_mode,
                'actual worker standard descriptor type/direction/label differs')
        for key, value in {'device': info.st_dev, 'inode': info.st_ino,
                           'mode': info.st_mode, 'access_mode': access_mode,
                           'inode_selinux_context': label}.items():
            require(expected[key] == value and reported.get(key) == value,
                    'forwarded / worker / READY descriptor identity mismatch: ' + key)
        actual[str(fd)] = {'device': info.st_dev, 'inode': info.st_ino, 'mode': info.st_mode,
                           'target': target, 'flags': flags, 'access_mode': access_mode,
                           'inode_selinux_context': label}
    require(process_start(pid) == start_before, 'worker PID identity changed during observation')
    return {'pid': pid, 'starttime_ticks': start_before, 'selinux_context': actual_context,
            'executable': executable, 'argv': actual_argv, 'cgroup': cgroup,
            'descriptors': actual, 'observed_while_waiting_for_go': True}


def run_transient(mode, properties, nonce, profile_sha256, worker_sha256, policy_callback, progress):
    """Return observations, never a self-declared functional/security pass."""
    require(mode in UNITS and bool(re.fullmatch('[0-9a-f]{32}', nonce)) and
            bool(re.fullmatch('[0-9a-f]{64}', profile_sha256)), 'explicit fixed invocation required')
    allowed = {'noop': [()], 'pids': [('TasksMax=3',)],
               'proc-read': [(), ('RestrictFileSystems=~proc',)]}
    require(tuple(properties) in allowed[mode], 'unreviewed transient property set')
    properties = list(properties)
    require(not WORKER.is_symlink() and WORKER.is_file() and
            hashlib.sha256(bounded_read(WORKER)).hexdigest() == worker_sha256,
            'installed worker source differs from this candidate')
    name = UNITS[mode]
    require(show_unit(name, ['LoadState'])['LoadState'] == 'not-found', 'owned proof name already exists')
    creator = {'pid': os.getpid(), 'selinux_context': context(os.getpid())}
    require(creator['selinux_context'] == CONTEXT, 'unexpected actual FIFO creator domain')
    open_fds = set()
    child = None
    selector = selectors.DefaultSelector()
    outputs = {'stdout': bytearray(), 'stderr': bytearray()}
    line_buffer = bytearray()
    ready = worker_result = worker_observation = actual_properties = client_observation = None
    go_sent = False
    route = None

    def close_owned(fd):
        if fd in open_fds:
            open_fds.remove(fd)
            os.close(fd)

    try:
        stdin_read, stdin_write = os.pipe2(os.O_CLOEXEC)
        open_fds.update((stdin_read, stdin_write))
        stdout_read, stdout_write = os.pipe2(os.O_CLOEXEC)
        open_fds.update((stdout_read, stdout_write))
        stderr_read, stderr_write = os.pipe2(os.O_CLOEXEC)
        open_fds.update((stderr_read, stderr_write))
        forwarded = {str(index): own_fd(fd, creator['selinux_context'])
                     for index, fd in enumerate((stdin_read, stdout_write, stderr_write))}
        for index in range(3):
            require(forwarded[str(index)]['access_mode'] == (os.O_RDONLY if index == 0 else os.O_WRONLY),
                    'new forwarded descriptor has the wrong direction')
        require(context(os.getpid()) == creator['selinux_context'], 'creator domain changed across pipe creation')
        # No transient exists yet. Compute AVs outside the <=3s READY budget.
        # The exact requested worker context must then match its actual /proc
        # context before this provisional contract can authorize GO.
        route = policy_callback(creator['selinux_context'], CONTEXT, forwarded)
        require(isinstance(route, dict) and route.get('query_completed') is True and
                route.get('all_receivers_fd_and_fifo_allowed') is True and
                route.get('all_requested_contracts_satisfied') is True,
                'same-boot policy does not qualify the complete requested FD route')
        argv = ['/usr/bin/python3', str(WORKER), mode, '--nonce', nonce,
                '--profile-sha256', profile_sha256]
        command = ['/usr/bin/systemd-run', '--quiet', '--wait', '--pipe', '--collect',
                   '--unit=' + name, '--property=RuntimeMaxSec=8s',
                   '--property=SELinuxContext=' + CONTEXT, '--setenv=LC_ALL=C']
        command += ['--property=' + value for value in properties]
        command += argv
        environment = os.environ.copy()
        environment['SYSTEMD_LOG_LEVEL'] = 'debug'
        started = time.monotonic()
        child = subprocess.Popen(command, stdin=stdin_read, stdout=stdout_write,
                                 stderr=stderr_write, close_fds=True, env=environment)
        for fd in (stdin_read, stdout_write, stderr_write):
            close_owned(fd)
        for fd, stream in ((stdout_read, 'stdout'), (stderr_read, 'stderr')):
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ, stream)
        deadline = started + 12.0
        while selector.get_map() or child.poll() is None:
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'owned system-bus operation exceeded its 12s deadline')
            for key, _ in selector.select(min(0.2, remaining)):
                block = os.read(key.fd, 8192)
                if not block:
                    selector.unregister(key.fd)
                    close_owned(key.fd)
                    continue
                outputs[key.data].extend(block)
                require(sum(map(len, outputs.values())) < LIMIT, 'owned transient output bound exceeded')
                if key.data == 'stdout':
                    require(go_sent, 'worker produced payload before external qualification')
                    continue
                line_buffer.extend(block)
                while b'\n' in line_buffer:
                    line, _, remainder = line_buffer.partition(b'\n')
                    line_buffer = bytearray(remainder)
                    if line.startswith(ERROR):
                        raise RuntimeError('owned worker reported an explicit protocol/guard error: ' + line.decode()[:2048])
                    if line.startswith(READY):
                        require(ready is None and not go_sent and len(line) <= 8192,
                                'duplicate or oversized worker READY')
                        ready = json.loads(line[len(READY):])
                        observation_started = time.monotonic()
                        worker_observation = observe_worker(ready, mode, nonce, profile_sha256, argv, forwarded)
                        client_observation = {'pid': child.pid, 'selinux_context': context(child.pid),
                            'starttime_ticks': process_start(child.pid),
                            'observed_while_worker_waiting_for_go': True}
                        require(client_observation['selinux_context'] == CONTEXT,
                                'actual systemd-run client domain differs from the controlled creator')
                        # One manager query supplies all relevant unit properties.
                        actual_properties = show_unit(name, ['MainPID', 'ControlGroup', 'SELinuxContext',
                            'RestrictFileSystems', 'TasksMax', 'RuntimeMaxUSec'], timeout=1.5)
                        expected_restriction = '~proc' if properties == ['RestrictFileSystems=~proc'] else '~'
                        require(actual_properties['MainPID'] == str(worker_observation['pid']) and
                                actual_properties['ControlGroup'] == '/system.slice/' + name and
                                actual_properties['SELinuxContext'] == CONTEXT and
                                actual_properties['RestrictFileSystems'] == expected_restriction and
                                actual_properties['RuntimeMaxUSec'] == '8s',
                                'actual unit properties do not implement this controlled operation')
                        if mode == 'pids':
                            require(actual_properties['TasksMax'] == '3', 'actual owned unit TasksMax differs')
                        require(context(worker_observation['pid']) == CONTEXT and
                                process_start(worker_observation['pid']) == worker_observation['starttime_ticks'],
                                'worker identity changed before GO')
                        require(time.monotonic() - observation_started < 2.5,
                                'external qualification exhausted the worker GO budget')
                        go = ('GO ' + nonce + '\n').encode('ascii')
                        require(os.write(stdin_write, go) == len(go), 'GO input was not delivered completely')
                        close_owned(stdin_write)
                        go_sent = True
                        progress('actual_transient_route_qualified', {'unit': name, 'mode': mode,
                            'nonce': nonce, 'creator': creator, 'forwarded_descriptors': forwarded,
                            'client': client_observation, 'worker': worker_observation,
                            'unit_properties': actual_properties,
                            'policy_contract_summary': {key: route.get(key) for key in
                                ('input_policy', 'query_completed', 'query_count',
                                 'all_receivers_fd_and_fifo_allowed', 'all_requested_contracts_satisfied')},
                            'worker_premise_verified_by_actual_readback': True})
                    elif line.startswith(RESULT):
                        require(go_sent and worker_result is None and len(line) <= 8192,
                                'out-of-order, duplicate or oversized worker RESULT')
                        worker_result = json.loads(line[len(RESULT):])
                        require(worker_result.get('schema_version') == 1 and
                                worker_result.get('nonce') == nonce and worker_result.get('mode') == mode and
                                worker_result.get('pid') == worker_observation['pid'] and
                                worker_result.get('profile_sha256') == profile_sha256,
                                'worker RESULT does not match the observed invocation')
        child.wait(timeout=1)
        require(go_sent and worker_result is not None and
                type(worker_result.get('exit_code')) is int and
                child.returncode == worker_result['exit_code'],
                'owned worker/client exit status or completed protocol differs')
        result = subprocess.CompletedProcess(command, child.returncode,
                    outputs['stdout'].decode('utf-8', errors='strict'),
                    outputs['stderr'].decode('utf-8', errors='strict'))
        result.descriptor_proof = {'creator': creator, 'forwarded': forwarded,
            'actual_client': client_observation, 'actual_worker': worker_observation,
            'installed_worker_sha256': worker_sha256, 'unit_properties': actual_properties,
            'worker_premise_verified_by_actual_readback': True}
        result.worker_result = worker_result
        result.policy_contract = route
        result.worker_argv = argv
        return result
    finally:
        selector.close()
        for fd in list(open_fds):
            close_owned(fd)
        if child is not None:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)
            state = show_unit(name, ['LoadState'])['LoadState']
            if state != 'not-found':
                stopped = subprocess.run(['/usr/bin/systemctl', 'stop', name],
                                         capture_output=True, timeout=5)
                require(stopped.returncode == 0, 'owned transient unit could not be stopped')
            deadline = time.monotonic() + 4
            while state != 'not-found' and time.monotonic() < deadline:
                state = show_unit(name, ['LoadState'], timeout=1)['LoadState']
                if state != 'not-found':
                    time.sleep(0.05)
            require(state == 'not-found', 'owned transient unit was not collected')
