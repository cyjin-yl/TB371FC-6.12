#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Own one explicit R4E pipeline and preserve its exit/log independently."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

WORK = Path('/work/fedora-input-system-v8')
RECIPE = Path('/work/fedora-input-system-recipe-r4-v6')
MANIFEST_SHA = 'c453d67a35b466be76924eceb7f3af96bfd15ed313ee5cba11963a9de91fcb94'
REPORT_SHA = '0db9a7e6164b44ac845a80974c3a369476ede23ac6f094de9c14c8602fa3faa6'
BUNDLE_SHA = '82ffa9d01bd5cab5fe859e0182cac9998f103391ca5dac469b0044234fa18627'
cancelled = None


def on_signal(number, frame):
    global cancelled
    cancelled = number


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    manifest = RECIPE / 'recipe-manifest.json'
    if (manifest.is_symlink() or not manifest.is_file() or
            hashlib.sha256(manifest.read_bytes()).hexdigest() != MANIFEST_SHA):
        raise ValueError('the exact read-back R4E recipe is required')
    if WORK.is_symlink() or not WORK.is_dir():
        raise ValueError('owned prepared R4E directory required')
    paths = [WORK / name for name in ('pipeline-command.json', 'pipeline.log', 'pipeline.exit.json')]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise ValueError('this unique pipeline already has retained evidence')
    command = [sys.executable, str(RECIPE / 'run_pipeline.py'),
        '--report-sha256', REPORT_SHA, '--bundle-sha256', BUNDLE_SHA,
        '--recipe-manifest-sha256', MANIFEST_SHA, '--attempt', '1', '--start', 'stage']
    with paths[0].open('x') as stream:
        json.dump(command, stream, indent=2)
        stream.write('\n')
    record = {'schema_version': 1, 'command': command, 'started_utc': now(),
              'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'recipe_manifest_sha256': MANIFEST_SHA, 'exit_code': None,
              'physical_hardware_tested': False}
    previous = {sig: signal.signal(sig, on_signal) for sig in (signal.SIGINT, signal.SIGTERM)}
    child = None
    started = time.monotonic()
    try:
        with paths[1].open('xb') as output:
            if cancelled:
                raise InterruptedError('cancelled before pipeline creation')
            child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            while child.poll() is None:
                if cancelled:
                    raise InterruptedError('received signal ' + str(cancelled))
                if time.monotonic() - started > 3600:
                    raise TimeoutError('explicit pipeline deadline exceeded')
                if paths[1].stat().st_size > 16 * 1024**2:
                    raise RuntimeError('pipeline output exceeded its bound')
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
                child.wait(timeout=50)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=5)
        if child is not None:
            record['exit_code'] = child.returncode
        record.update({'elapsed_seconds': time.monotonic() - started,
                       'finished_utc': now(), 'cancelled_signal': cancelled})
        with paths[2].open('x') as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write('\n')
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps(record, sort_keys=True), flush=True)
    raise SystemExit(0 if record['exit_code'] == 0 and not record.get('error') and not cancelled else 1)


if __name__ == '__main__':
    main()
