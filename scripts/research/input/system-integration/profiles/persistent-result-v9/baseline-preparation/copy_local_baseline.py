#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Copy the qualified Fedora tree inside its existing standard HDD builder.

The SSD bind mount cannot preserve this distribution's POSIX ACLs. Keep that
failed attempt, and create a separate tree on the original capable filesystem.
All content, numeric ownership, links, modes, ACLs and xattrs are compared by a
canonical GNU tar stream before the destination can be used as an input.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

BASE = Path('/work/fedora-system-integration-v1')
WORK = Path('/work/fedora-input-system-v2')
ROOT = WORK / 'rootfs'
REPORT_SHA = '66ac854b2bc938aed147afe0355b57fcbba856c874e9d82cec4cad663b1c87d9'
RUNTIME_SHA = '10a373bfc3291aabe564c8f7af90265900763eadfe3167a7384cc4dcd596544b'
VM_SHA = '223f73b253a48995dd238575e64aad055e11f311c658aa03534b49c570095675'
PROOT = Path('/work/fedora-proot-src/src/proot')
PROOT_SHA = '313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f'
QEMU = Path('/usr/bin/qemu-aarch64')
QEMU_SHA = '73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def guard():
    expected = {
        BASE / 'fedora-system-integration.json': REPORT_SHA,
        BASE / 'runtime.json': RUNTIME_SHA,
        BASE / 'vm-verify-01/result.json': VM_SHA,
        PROOT: PROOT_SHA, QEMU: QEMU_SHA,
    }
    for path, value in expected.items():
        if path.is_symlink() or not path.is_file() or sha(path) != value:
            raise ValueError('frozen input mismatch: ' + str(path))
    vm = json.loads((BASE / 'vm-verify-01/result.json').read_text())
    if not (vm['passed'] and vm['guest_gates_match'] and
            vm['guest_result']['selinux'] == 'Enforcing'):
        raise ValueError('qualified baseline VM verification is absent')
    return {str(p): value for p, value in expected.items()}


def canonical_hash(tree, label):
    command = ['timeout', '--signal=TERM', '--kill-after=10s', '900s', 'tar',
               '--sort=name', '--format=posix',
               '--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime',
               '--numeric-owner', '--acls', '--selinux', '--xattrs', '--xattrs-include=*',
               '-cf', '-', '-C', str(tree), '.']
    digest = hashlib.sha256()
    count = 0
    with (WORK / (label + '.stderr')).open('xb') as log:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log)
        try:
            while block := child.stdout.read(1024 * 1024):
                digest.update(block)
                count += len(block)
            code = child.wait(timeout=20)
            if code:
                raise RuntimeError(f'canonical tar failed: {label}: {code}')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.stdout.close()
    if (WORK / (label + '.stderr')).stat().st_size:
        raise RuntimeError('canonical tar emitted warnings; retained: ' + label)
    return {'sha256': digest.hexdigest(), 'bytes': count, 'exit_code': code}


def main():
    before = guard()
    if WORK.exists() or WORK.is_symlink() or not (BASE / 'rootfs').is_dir():
        raise ValueError('fresh destination and frozen ordinary source required')
    if shutil.disk_usage(WORK.parent).free < 10 * 1024**3:
        raise ValueError('less than 10 GiB available')
    WORK.mkdir(mode=0o755)
    record = {'schema_version': 1, 'complete': False,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'container': 'tb371fc-build-20261123',
              'source_tree': str(BASE / 'rootfs'), 'destination_tree': str(ROOT),
              'input_hashes': before, 'copy_exit_code': None,
              'canonical_streams': {}, 'source_modified': False,
              'previous_ssd_partial_retained': '/work/fedora-input-system-v1',
              'previous_ssd_container': 'tb371fc-build-ssd-20261123',
              'host_storage_or_daemon_modified': False}
    try:
        with (WORK / 'copy.stderr').open('xb') as log:
            result = subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s', '1200s',
                                     'cp', '-a', '--reflink=auto', str(BASE / 'rootfs'), str(ROOT)],
                                    stdout=log, stderr=log)
        record['copy_exit_code'] = result.returncode
        if result.returncode or (WORK / 'copy.stderr').stat().st_size:
            raise RuntimeError('copy failed or warned; retained copy.stderr and partial tree')
        source = canonical_hash(BASE / 'rootfs', 'source-tree')
        record['canonical_streams']['source'] = source
        destination = canonical_hash(ROOT, 'copied-tree')
        record['canonical_streams']['destination'] = destination
        if source != destination:
            raise ValueError('content or metadata differs in canonical copied tree')
        acl_path = Path('var/log/journal')
        acl_names = ('system.posix_acl_access', 'system.posix_acl_default')
        acl_check = {}
        for name in acl_names:
            first = os.getxattr(BASE / 'rootfs' / acl_path, name, follow_symlinks=False)
            second = os.getxattr(ROOT / acl_path, name, follow_symlinks=False)
            if not first or first != second:
                raise ValueError('distribution journal ACL was not preserved')
            acl_check[name] = {'sha256': hashlib.sha256(first).hexdigest(), 'size': len(first),
                               'byte_identical': True}
        record['journal_acl_check'] = acl_check
        records = WORK / 'baseline-records'
        records.mkdir()
        for name in ('fedora-system-integration.json', 'runtime.json', 'packages.after.tsv',
                     'seed.json', 'package-pins.json', 'configured.json', 'initramfs.json',
                     'vm-label-02/result.json', 'vm-verify-01/result.json'):
            src, dst = BASE / name, records / name
            if src.is_symlink() or not src.is_file():
                raise ValueError('ordinary baseline metadata required: ' + name)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if sha(src) != sha(dst):
                raise ValueError('copied metadata changed: ' + name)
        if guard() != before:
            raise ValueError('frozen source guard changed')
        record['complete'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (WORK / 'baseline-copy.json').open('x') as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write('\n')
    print('FEDORA_INPUT_LOCAL_BASELINE_COPY_VERIFIED', flush=True)


if __name__ == '__main__':
    main()
