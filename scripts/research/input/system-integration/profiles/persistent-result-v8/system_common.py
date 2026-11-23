#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fixed new project prefix and bounded, qualified Fedora execution helpers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

WORK = Path('/work/fedora-input-system-v8')
ROOT = WORK / 'rootfs'
INPUTS = WORK / 'kernel-inputs'
LABEL = 'tb371fc-r4e-f45'
IMAGE = WORK / 'fedora45-research4e-persistent-result.ext4'
PROFILE = ROOT / 'usr/share/tb371fc/system-profile.json'
PROOT = Path('/work/fedora-proot-src/src/proot')
HOST_LIBS = Path('/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu')
QEMU = Path('/usr/bin/qemu-aarch64')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(value):
    p = PurePosixPath(value)
    if not value or p.is_absolute() or '..' in p.parts or str(p) != value:
        raise ValueError('noncanonical relative path: ' + value)
    return p


def check(path, expected, size=None):
    if path.is_symlink() or not path.is_file() or sha(path) != expected:
        raise ValueError('ordinary file hash mismatch: ' + str(path))
    if size is not None and path.stat().st_size != size:
        raise ValueError('file size mismatch: ' + str(path))


def save(name, value):
    path = WORK / relative(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def copy_new(source, destination):
    if source.is_symlink() or not source.is_file():
        raise ValueError('ordinary source required: ' + str(source))
    if destination.exists() or destination.is_symlink():
        raise ValueError('refusing existing output: ' + str(destination))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    check(destination, sha(source), source.stat().st_size)


def preserve_write(name, text):
    path = ROOT / relative(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        backup = path.with_name(path.name + '.before-research4-integration')
        if backup.exists() or backup.is_symlink():
            raise ValueError('configuration backup already exists')
        path.rename(backup)
    with path.open('x') as stream:
        stream.write(text)


def run_guest(arguments, capture=False, timeout=600):
    copied = json.loads((WORK / 'baseline-copy.json').read_text())
    if not copied['complete'] or ROOT.is_symlink() or not ROOT.is_dir():
        raise ValueError('complete verified independent Fedora tree required')
    check(WORK / 'baseline-copy-qualification.json',
          'd1136513b108ebc0a18abe859d28d2a913fbf75446b4ebacb02fd926f281a840')
    qualification = json.loads((WORK / 'baseline-copy-qualification.json').read_text())
    if (qualification.get('qualified') is not True or
            qualification.get('baseline_copy_sha256') != sha(WORK / 'baseline-copy.json') or
            qualification.get('expected_quiescent_stream_sha256') !=
                '1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96'):
        raise ValueError('the exact independently qualified quiescent v8 copy is required')
    for path in (PROOT, QEMU):
        check(path, copied['input_hashes'][str(path)])
    env = dict(os.environ, LD_LIBRARY_PATH=str(HOST_LIBS), SYSTEMD_OFFLINE='1')
    return subprocess.run([str(PROOT), '-0', '-r', str(ROOT), '-q', str(QEMU),
                           '-b', '/proc', '-b', '/dev/null', '-b', '/dev/zero',
                           '-b', '/dev/random', '-b', '/dev/urandom', '-w', '/', *arguments],
                          env=env, check=True, text=True, timeout=timeout,
                          stdout=subprocess.PIPE if capture else None)


def profile():
    data = json.loads(PROFILE.read_text())
    if (data.get('schema_version') != 1 or data.get('root_label') != LABEL or
            not re.fullmatch(r'6\.12\.114-tb371fc-research4-system', data['kernel_release'])):
        raise ValueError('unexpected new system profile')
    return data
