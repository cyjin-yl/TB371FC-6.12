#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare a fresh, unchanged Fedora baseline for the next R4 service profile.

Only the destination of the already qualified copy helper is changed. No
SELinux policy, label, kernel, module, failed image or old recipe is modified.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

COPY_SHA = 'e47bb6f6f59af80bd1fc1014e3d83db1537371f641ec7997dae7bacc7ffbbf6b'
WORK = Path('/work/fedora-input-system-v4')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--copy-helper', type=Path, required=True)
    args = parser.parse_args()
    helper = args.copy_helper
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
    record = {'schema_version': 1, 'copy_helper_sha256': COPY_SHA,
              'wrapper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'only_override': {'WORK': str(WORK), 'ROOT': str(module.ROOT)},
              'new_baseline_copy_sha256': hashlib.sha256((WORK / 'baseline-copy.json').read_bytes()).hexdigest(),
              'selinux_policy_or_domain_changed': False, 'system_or_kernel_tested': False}
    with (WORK / 'baseline-copy-recipe.json').open('x') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
