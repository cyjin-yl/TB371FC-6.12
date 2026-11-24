#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Small owned transient-unit check: at most three two-second child attempts."""
import errno
import json
from pathlib import Path
import subprocess

GROUP = '/system.slice/tb371fc-r3-pids-proof.service'


def main():
    if Path('/proc/self/cgroup').read_text().strip() != '0::' + GROUP:
        raise RuntimeError('not inside the owned pids proof cgroup')
    root = Path('/sys/fs/cgroup') / GROUP.lstrip('/')
    if (root / 'pids.max').read_text().strip() != '3':
        raise RuntimeError('the transient TasksMax=3 setting is not active')
    if b'linux,dummy-virt' not in Path('/proc/device-tree/compatible').read_bytes().split(b'\0'):
        raise RuntimeError('not the isolated generic VM')
    if 'tb371fc.r3-phase=verify' not in Path('/proc/cmdline').read_text().split():
        raise RuntimeError('not the explicit new verification boot')
    events = lambda: dict(line.split() for line in (root / 'pids.events').read_text().splitlines())
    before = int(events()['max'])
    children = []
    denied = []
    after = None
    try:
        for attempt in range(3):
            try:
                children.append(subprocess.Popen(['/usr/bin/sleep', '2'],
                                                  stdin=subprocess.DEVNULL,
                                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
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
    passed = len(children) == 2 and len(denied) == 1 and after is not None and after > before
    result = {'passed': passed, 'tasks_max': 3, 'attempted_children': 3,
              'created_children': len(children), 'denied': denied,
              'pids_events_max_before': before, 'pids_events_max_after': after,
              'all_owned_children_reaped': all(child.poll() is not None for child in children)}
    print('TB371FC_R3_PIDS_PROOF ' + json.dumps(result, sort_keys=True), flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
