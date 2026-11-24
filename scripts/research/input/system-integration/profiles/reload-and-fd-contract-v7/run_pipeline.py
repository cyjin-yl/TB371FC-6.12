#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute explicit sequential phases with retained logs in the new prefix."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from system_common import WORK, sha

HERE = Path(__file__).resolve().parent
cancelled = None


def on_signal(number, frame):
    global cancelled
    cancelled = number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--bundle-sha256', required=True)
    parser.add_argument('--recipe-manifest-sha256', required=True)
    parser.add_argument('--attempt', type=int, default=1)
    parser.add_argument('--start', choices=('stage', 'configure', 'initramfs', 'image', 'vm-label', 'vm-verify', 'post-qualify', 'finalize'), default='stage')
    args = parser.parse_args()
    for value in (args.report_sha256, args.bundle_sha256, args.recipe_manifest_sha256):
        if not re.fullmatch('[0-9a-f]{64}', value):
            parser.error('all three externally fixed SHA-256 inputs are required')
    manifest = HERE / 'recipe-manifest.json'
    if manifest.is_symlink() or not manifest.is_file() or sha(manifest) != args.recipe_manifest_sha256:
        raise ValueError('materialized recipe manifest differs from the explicit launch identity')
    sources = json.loads(manifest.read_text())
    expected = {'assemble_system.py', 'boot_system_vm.py', 'early_initramfs.py',
        'finalize_system.py', 'guest_verify_system.py', 'run_pipeline.py',
        'stage_system.py', 'system_common.py', 'qualify_udev_handoff.py',
        'initrd-domain-proof.sh', 'initrd-domain-proof.service',
        'guest_transient_worker.py', 'transient_protocol.py', 'probe_fd_route_v2.py',
        'retain_policy_export.py', 'verify_initramfs.py',
        'verify_early_policy_initramfs.py', 'verify_reload_map_initramfs.py'}
    if set(sources) != expected:
        raise ValueError('exact complete v7 execution source set required')
    for name, item in sources.items():
        path = HERE / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != item['size'] or sha(path) != item['sha256']:
            raise ValueError('materialized execution source changed: ' + name)
    if not 1 <= args.attempt <= 99:
        parser.error('attempt must be in 1..99')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, on_signal)
    jobs = WORK / 'jobs'
    jobs.mkdir(exist_ok=True)
    suffix = f'{args.attempt:02d}'
    phases = [
        ('stage', ['stage_system.py', '--report-sha256', args.report_sha256,
                      '--bundle-sha256', args.bundle_sha256]),
        ('configure', ['assemble_system.py', 'configure']),
        ('initramfs', ['assemble_system.py', 'initrd']),
        ('image', ['assemble_system.py', 'image']),
        ('vm-label', ['boot_system_vm.py', 'label', '--run', 'vm-label-' + suffix]),
        ('vm-verify', ['boot_system_vm.py', 'verify', '--run', 'vm-verify-' + suffix]),
        ('post-qualify', ['qualify_udev_handoff.py', '--run', 'vm-verify-' + suffix]),
        ('finalize', ['finalize_system.py']),
    ]
    start_index = next(i for i, (name, _) in enumerate(phases) if name == args.start)
    for phase, arguments in phases[start_index:]:
        name = phase + '-' + suffix
        command = [sys.executable, str(HERE / arguments[0]), *arguments[1:]]
        started = time.monotonic()
        record = {'name': name, 'command': command,
                  'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  'recipe_sha256': sha(HERE / arguments[0]), 'exit_code': None}
        child = None
        try:
            with (jobs / (name + '.log')).open('xb') as output:
                if cancelled:
                    raise InterruptedError('pipeline cancelled before phase creation')
                child = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT,
                                         start_new_session=True)
                while child.poll() is None:
                    if cancelled:
                        raise InterruptedError('pipeline received signal ' + str(cancelled))
                    time.sleep(0.5)
                record['exit_code'] = child.returncode
                if cancelled:
                    raise InterruptedError('pipeline interrupted at phase completion')
        except BaseException as error:
            record['error'] = {'type': type(error).__name__, 'message': str(error)}
            raise
        finally:
            if child is not None and child.poll() is None:
                # Only this newly created phase session is signalled. The VM
                # controller handles TERM by reaping its separate QEMU child.
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
                record['exit_code'] = child.returncode
            record['cancelled_signal'] = cancelled
            record['elapsed_seconds'] = time.monotonic() - started
            record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with (jobs / (name + '.json')).open('x') as output:
                json.dump(record, output, indent=2, sort_keys=True)
                output.write('\n')
        print(json.dumps(record, sort_keys=True), flush=True)
        if record['exit_code']:
            raise SystemExit(record['exit_code'])
    print('FEDORA_RESEARCH4D_SYSTEM_PIPELINE_COMPLETE', flush=True)


if __name__ == '__main__':
    main()
