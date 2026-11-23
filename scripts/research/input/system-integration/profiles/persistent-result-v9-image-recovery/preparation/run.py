#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Own one native prepared-root copy and retain its bounded exit evidence."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

HERE = Path('/work/fedora-r4f-recovery-preparation-v1')
HELPER_SHA = '688af25317b84a4dd96de2d8f54a3ba07ee34c108c069998e00ea05c14af2a0e'
cancelled = None


def on_signal(number, frame):
    global cancelled
    cancelled = number


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    helper = HERE / 'copy_prepared_root.py'
    if (helper.is_symlink() or not helper.is_file() or
            hashlib.sha256(helper.read_bytes()).hexdigest() != HELPER_SHA):
        raise ValueError('fixed native prepared-copy helper required')
    names = ('stdout.log', 'stderr.log', 'exit.json')
    if any((HERE / name).exists() or (HERE / name).is_symlink() for name in names):
        raise ValueError('this preparation already has evidence')
    command = [sys.executable, str(helper)]
    record = {'schema_version': 1, 'command': command, 'started_utc': now(),
              'helper_sha256': HELPER_SHA,
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'timeout_seconds': 4800, 'exit_code': None,
              'proot_or_guest_or_vm_executed': False}
    previous = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
    child = None
    started = time.monotonic()
    try:
        with (HERE / 'stdout.log').open('xb') as out, (HERE / 'stderr.log').open('xb') as err:
            if cancelled:
                raise InterruptedError('cancelled before child ownership')
            child = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=True)
            while child.poll() is None:
                if cancelled:
                    raise InterruptedError('preparation received signal ' + str(cancelled))
                if time.monotonic() - started > 4800:
                    raise TimeoutError('native preparation deadline exceeded')
                time.sleep(0.5)
            record['exit_code'] = child.returncode
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        for sig in previous:
            signal.signal(sig, signal.SIG_IGN)
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        if child is not None:
            record['exit_code'] = child.returncode
        record.update({'finished_utc': now(), 'elapsed_seconds': time.monotonic() - started,
                       'cancelled_signal': cancelled})
        with (HERE / 'exit.json').open('x') as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write('\n')
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(record, sort_keys=True), flush=True)
    raise SystemExit(0 if record['exit_code'] == 0 and not record.get('error') and not cancelled else 1)


if __name__ == '__main__':
    main()
