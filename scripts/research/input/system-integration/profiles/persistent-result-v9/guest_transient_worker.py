#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Three fixed owned-VM workers, held until the parent proves the FD route.

This candidate is not a successful VM result. The parent verifies the actual
process domain/cgroup through /proc while this same process waits on stdin.
The proc-read mode never reads /proc for self-identification: its only /proc
operation is the intended /proc/version open/read after GO. No exec occurs
between that external observation and the behavior being tested.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import subprocess
import time

PROFILE = Path('/usr/share/tb371fc/system-profile.json')
PROFILE_NAME = 'research4-display-input-fedora45-v9-persistent-result'
CONTEXT = 'system_u:system_r:sysadm_t:s0'
UNITS = {'noop': 'tb371fc-r4f-bus-proof.service',
         'pids': 'tb371fc-r4f-pids-proof.service',
         'proc-read': 'tb371fc-r4f-fs-proof.service'}
READY = 'TB371FC_R4F_WORKER_READY '
RESULT = 'TB371FC_R4F_WORKER_RESULT '


def require(value, message):
    if not value:
        raise RuntimeError(message)


def write_all(fd, payload):
    view = memoryview(payload)
    while view:
        count = os.write(fd, view)
        if count <= 0:
            raise RuntimeError('owned output made no progress')
        view = view[count:]


def emit(prefix, data):
    payload = (prefix + json.dumps(data, sort_keys=True, separators=(',', ':')) + '\n').encode()
    require(len(payload) <= 8192, 'bounded worker protocol exceeded')
    write_all(2, payload)


def descriptor(fd):
    info = os.fstat(fd)
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    context = os.getxattr(fd, 'security.selinux').decode('ascii').strip('\0\n')
    require(stat.S_ISFIFO(info.st_mode), 'each forwarded standard descriptor must be an owned FIFO')
    require((flags & os.O_ACCMODE) == (os.O_RDONLY if fd == 0 else os.O_WRONLY),
            'forwarded descriptor access direction differs')
    require(context == CONTEXT, 'forwarded FIFO inode has an unexpected security context')
    return {'fd': fd, 'device': info.st_dev, 'inode': info.st_ino,
            'mode': info.st_mode, 'flags': flags, 'access_mode': flags & os.O_ACCMODE,
            'inode_selinux_context': context}


def await_go(nonce):
    deadline = time.monotonic() + 3.0
    received = bytearray()
    while b'\n' not in received:
        remaining = deadline - time.monotonic()
        require(remaining > 0, 'parent did not qualify the route before the bounded GO deadline')
        readable, _, _ = select.select([0], [], [], remaining)
        require(bool(readable), 'bounded GO input timeout')
        block = os.read(0, 65 - len(received))
        require(bool(block), 'parent closed the control input before GO')
        received.extend(block)
        require(len(received) <= 64, 'GO input exceeds its fixed bound')
    require(bytes(received) == ('GO ' + nonce + '\n').encode('ascii'),
            'GO input does not identify this owned worker')


def pids_probe():
    # The parent already observed this PID in this exact cgroup before GO.
    # Reading this fixed cgroup does not require /proc in the worker.
    group = Path('/sys/fs/cgroup/system.slice') / UNITS['pids']
    require((group / 'pids.max').read_text().strip() == '3', 'TasksMax=3 is not active')
    events = lambda: dict(line.split() for line in (group / 'pids.events').read_text().splitlines())
    before = int(events()['max'])
    children, denied = [], []
    after = None
    try:
        for attempt in range(3):
            try:
                children.append(subprocess.Popen(['/usr/bin/sleep', '2'],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            except OSError as error:
                if error.errno != errno.EAGAIN:
                    raise
                denied.append({'attempt': attempt + 1, 'errno': error.errno})
        after = int(events()['max'])
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=2)
    result = {'tasks_max': 3, 'attempted_children': 3, 'created_children': len(children),
              'denied': denied, 'pids_events_max_before': before, 'pids_events_max_after': after,
              'all_owned_children_reaped': all(child.poll() is not None for child in children)}
    result['passed'] = (len(children) == 2 and len(denied) == 1 and after is not None and
                        after > before and result['all_owned_children_reaped'])
    return result, 0 if result['passed'] else 1


def proc_read():
    descriptor_fd = None
    data = b''
    phase = 'open'
    try:
        descriptor_fd = os.open('/proc/version', os.O_RDONLY | os.O_CLOEXEC)
        phase = 'read'
        while True:
            chunk = os.read(descriptor_fd, min(4096, 65537 - len(data)))
            if not chunk:
                break
            data += chunk
            require(len(data) <= 65536, 'controlled proc response exceeds its bound')
        write_all(1, data)
        return {'operation': 'open/read /proc/version', 'outcome': 'read', 'errno': None,
                'data_bytes': len(data), 'data_sha256': hashlib.sha256(data).hexdigest()}, 0
    except OSError as error:
        # EACCES/EPERM are recorded as observations; only the parent compares
        # the same argv/domain baseline with RestrictFileSystems=~proc.
        return {'operation': 'open/read /proc/version', 'outcome': 'error',
                'failure_phase': phase, 'errno': error.errno, 'data_bytes': len(data),
                'permission_denial': error.errno in (errno.EACCES, errno.EPERM)}, 1
    finally:
        if descriptor_fd is not None:
            os.close(descriptor_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=tuple(UNITS))
    parser.add_argument('--nonce', required=True)
    parser.add_argument('--profile-sha256', required=True)
    args = parser.parse_args()
    require(bool(re.fullmatch('[0-9a-f]{32}', args.nonce)), 'fixed-format invocation nonce required')
    require(bool(re.fullmatch('[0-9a-f]{64}', args.profile_sha256)), 'profile identity required')
    uname = os.uname()
    require(uname.machine == 'aarch64' and uname.release == '6.12.114-tb371fc-research4-system',
            'worker is limited to the owned research4 ARM64 kernel')
    require(os.getuid() == os.geteuid() == 0, 'explicit root administration test identity required')
    # /sys is allowed for the proc-denial test; do not use the /proc/device-tree alias.
    compatible = Path('/sys/firmware/devicetree/base/compatible').read_bytes()
    require(b'linux,dummy-virt' in compatible.rstrip(b'\0').split(b'\0'), 'not the generic owned VM')
    require(not PROFILE.is_symlink() and PROFILE.is_file() and PROFILE.stat().st_size <= 65536,
            'ordinary bounded candidate profile required')
    raw_profile = PROFILE.read_bytes()
    require(hashlib.sha256(raw_profile).hexdigest() == args.profile_sha256, 'candidate profile differs')
    profile = json.loads(raw_profile)
    require(profile['profile'] == PROFILE_NAME and profile['root_label'] == 'tb371fc-r4f-f45' and
            profile['validation_selinux_context'] == CONTEXT and
            profile['transient_selinux_context'] == CONTEXT,
            'not the explicit new management-domain contract')
    info = {'schema_version': 1, 'nonce': args.nonce, 'mode': args.mode,
            'pid': os.getpid(), 'uid': os.getuid(), 'euid': os.geteuid(),
            'kernel_release': uname.release, 'profile_sha256': args.profile_sha256,
            'expected_unit': UNITS[args.mode],
            'descriptors': {str(fd): descriptor(fd) for fd in (0, 1, 2)},
            'own_context_and_cgroup_must_be_observed_by_parent': True}
    emit(READY, info)
    await_go(args.nonce)
    if args.mode == 'noop':
        details, status = {'outcome': 'noop', 'stdout_payload_bytes': 0}, 0
    elif args.mode == 'pids':
        details, status = pids_probe()
    else:
        details, status = proc_read()
    emit(RESULT, {'schema_version': 1, 'nonce': args.nonce, 'pid': os.getpid(),
                  'mode': args.mode, 'profile_sha256': args.profile_sha256,
                  'exit_code': status, 'details': details})
    return status


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        emit('TB371FC_R4F_WORKER_ERROR ', {'type': type(error).__name__, 'message': str(error)[:1024]})
        raise SystemExit(1)
