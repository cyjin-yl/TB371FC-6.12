#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Copy the fixed R4 regular runtime bundle into the fresh v5 system prefix.

This reuses the byte-verified HDD transfer, never a failed VM filesystem. The
bundle contains public kernel runtime files and no private key or firmware.
"""
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil

SOURCE = Path('/work/fedora-input-system-v3/kernel-inputs')
WORK = Path('/work/fedora-input-system-v5')
DESTINATION = WORK / 'kernel-inputs'
BUNDLE_SHA = '82ffa9d01bd5cab5fe859e0182cac9998f103391ca5dac469b0044234fa18627'
REPORT_SHA = '0db9a7e6164b44ac845a80974c3a369476ede23ac6f094de9c14c8602fa3faa6'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_tree(root, manifest):
    actual = set()
    for path in root.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('non-ordinary input in the fixed runtime bundle')
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(manifest) | {'bundle.json'} or sha(root / 'bundle.json') != BUNDLE_SHA:
        raise ValueError('runtime bundle inventory/manifest changed')
    for name, expected in manifest.items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or str(relative) != name:
            raise ValueError('noncanonical declared runtime path')
        path = root / relative
        if path.stat().st_size != expected['size'] or sha(path) != expected['sha256']:
            raise ValueError('runtime file differs: ' + name)


def main():
    if SOURCE.is_symlink() or not SOURCE.is_dir() or sha(SOURCE / 'bundle.json') != BUNDLE_SHA:
        raise ValueError('fixed ordinary R4 bundle required')
    bundle = json.loads((SOURCE / 'bundle.json').read_text())
    if bundle['source_report_sha256'] != REPORT_SHA or bundle['kernel_release'] != '6.12.114-tb371fc-research4-system':
        raise ValueError('wrong frozen R4 build')
    if not json.loads((WORK / 'baseline-copy.json').read_text())['complete']:
        raise ValueError('the fresh userspace baseline was not verified')
    if DESTINATION.exists() or DESTINATION.is_symlink() or (WORK / 'kernel-transfer.json').exists():
        raise ValueError('new runtime destination required')
    check_tree(SOURCE, bundle['files'])
    record = {'schema_version': 1, 'complete': False,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_container': 'tb371fc-build-20261123',
              'destination_container': 'tb371fc-build-20261123',
              'source_root': str(SOURCE), 'destination_root': str(DESTINATION),
              'bundle_sha256': BUNDLE_SHA, 'kernel_report_sha256': REPORT_SHA,
              'source_transfer_record_sha256': sha(SOURCE.parent / 'kernel-transfer.json'),
              'private_keys_or_firmware_transferred': False, 'old_artifacts_modified': False,
              'source_is_failed_vm_filesystem': False,
              'recipe_sha256': sha(Path(__file__))}
    try:
        shutil.copytree(SOURCE, DESTINATION, copy_function=shutil.copy2)
        check_tree(DESTINATION, bundle['files'])
        check_tree(SOURCE, bundle['files'])
        record['files_verified'] = len(bundle['files'])
        record['complete'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (WORK / 'kernel-transfer.json').open('x') as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write('\n')
    print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
