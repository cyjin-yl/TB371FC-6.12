#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a fresh Fedora copy after the original source was made quiescent.

Only the destination of the already qualified copy helper is changed. No
SELinux policy, label, kernel, module, failed image or old recipe is modified.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

COPY_SHA = 'e47bb6f6f59af80bd1fc1014e3d83db1537371f641ec7997dae7bacc7ffbbf6b'
WORK = Path('/work/fedora-input-system-v5')
FAILED_WORK = Path('/work/fedora-input-system-v4')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copy-helper', type=Path, required=True)
    args = parser.parse_args()
    helper = args.copy_helper
    failure_path = FAILED_WORK / 'baseline-copy.json'
    failure = json.loads(failure_path.read_text())
    if failure.get('complete') is not False or failure.get('error', {}).get('message') != 'canonical tar failed: source-tree: 1':
        raise ValueError('the retained concurrent-source-change failure is missing')
    if (FAILED_WORK / 'source-tree.stderr').read_text() != 'tar: .: file changed as we read it\n':
        raise ValueError('unexpected preceding copy failure')
    if helper.is_symlink() or not helper.is_file():
        raise ValueError('ordinary frozen copy helper required')
    if hashlib.sha256(helper.read_bytes()).hexdigest() != COPY_SHA:
        raise ValueError('copy helper differs from the retained R3 public template')
    spec = importlib.util.spec_from_file_location('frozen_baseline_copy', helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WORK = WORK
    module.ROOT = WORK / 'rootfs'
    module.main()
    copied = json.loads((WORK / 'baseline-copy.json').read_text())
    record = {'schema_version': 1, 'copy_helper_sha256': COPY_SHA,
              'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'only_override': {'WORK': str(WORK), 'ROOT': str(module.ROOT)},
              'new_baseline_copy_sha256': hashlib.sha256((WORK / 'baseline-copy.json').read_bytes()).hexdigest(),
              'selinux_policy_or_domain_changed': False, 'system_or_kernel_tested': False,
              'retained_failed_copy': str(FAILED_WORK),
              'retained_failed_copy_metadata_sha256': hashlib.sha256(failure_path.read_bytes()).hexdigest(),
              'historical_canonical_stream_sha256': '4e789f5471821ded7c395cc11c665951b15a41a34d35358faa3c97d9e56a83e8',
              'historical_stream_matches': copied['canonical_streams']['source']['sha256'] ==
                  '4e789f5471821ded7c395cc11c665951b15a41a34d35358faa3c97d9e56a83e8',
              'source_timestamps_reset': False,
              'source_changes_since_original_baseline_require_separate_explanation': True}
    with (WORK / 'baseline-copy-recipe.json').open('x') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
