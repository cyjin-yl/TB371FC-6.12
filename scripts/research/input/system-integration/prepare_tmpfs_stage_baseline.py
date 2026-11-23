#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare the fresh v6 userspace copy and the unchanged qualified R4 inputs.

This runs no initrd, VM, PRoot or tablet operation. The original filesystem is
read/copy-only. Existing failed v5 evidence and artifacts remain untouched.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

WORK = Path('/work/fedora-input-system-v6')
COPY_SHA = 'e47bb6f6f59af80bd1fc1014e3d83db1537371f641ec7997dae7bacc7ffbbf6b'
RUNTIME_SHA = 'da19f1c9e2a75b3f384411708048ddf5272a2e0ad2351391adc587e9690ff4d0'
QUIESCENT_STREAM_SHA = '1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96'
V5_FAILURE = Path('/work/fedora-input-system-v5/fedora-input-system-attempt.json')
V5_FAILURE_SHA = '679c225df602523acf3f0c4775b3b94ba98da539dfc01826f2fe5f6340dd88fd'


def sha(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary frozen source/record required')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, expected):
    if sha(path) != expected:
        raise ValueError('frozen helper identity changed')
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copy-helper', type=Path, required=True)
    parser.add_argument('--runtime-helper', type=Path, required=True)
    args = parser.parse_args()
    if sha(V5_FAILURE) != V5_FAILURE_SHA or json.loads(V5_FAILURE.read_text()).get('overall_passed') is not False:
        raise ValueError('the actual v5 failure must remain retained')
    copy = load(args.copy_helper, COPY_SHA)
    runtime = load(args.runtime_helper, RUNTIME_SHA)
    if WORK.exists() or WORK.is_symlink():
        raise ValueError('fresh v6 project prefix required')
    copy.WORK, copy.ROOT = WORK, WORK / 'rootfs'
    record = {'schema_version': 1, 'qualified': False,
              'expected_quiescent_stream_sha256': QUIESCENT_STREAM_SHA,
              'prior_v5_failure': {'path': str(V5_FAILURE), 'sha256': V5_FAILURE_SHA},
              'copy_helper_sha256': COPY_SHA, 'runtime_helper_sha256': RUNTIME_SHA,
              'wrapper_sha256': sha(Path(__file__)),
              'source_timestamps_reset': False, 'old_failed_candidate_modified': False,
              'proot_or_initrd_or_vm_executed': False, 'physical_tablet_tested': False}
    try:
        copy.main()
        copied = json.loads((WORK / 'baseline-copy.json').read_text())
        source = copied['canonical_streams']['source']
        destination = copied['canonical_streams']['destination']
        if not copied['complete'] or source != destination or source['sha256'] != QUIESCENT_STREAM_SHA:
            raise ValueError('fresh copy differs from the already qualified quiescent source')
        record['baseline_copy_sha256'] = sha(WORK / 'baseline-copy.json')
        record['canonical_stream'] = source
        record['qualified'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        if WORK.is_dir():
            with (WORK / 'baseline-copy-qualification.json').open('x') as stream:
                json.dump(record, stream, sort_keys=True, indent=2)
                stream.write('\n')
    runtime.WORK, runtime.DESTINATION = WORK, WORK / 'kernel-inputs'
    runtime.main()
    print(json.dumps({'work': str(WORK), 'baseline_qualified': True,
                      'baseline_qualification_sha256': sha(WORK / 'baseline-copy-qualification.json'),
                      'runtime_transfer_sha256': sha(WORK / 'kernel-transfer.json'),
                      'new_vm_started': False}, sort_keys=True))


if __name__ == '__main__':
    main()
