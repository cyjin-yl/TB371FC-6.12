#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read selected source members of the fixed Fedora systemd SRPM.

This is source inspection only. It does not execute target programs or modify
any rootfs, policy, mount, service or VM. All outputs require a new directory.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import stat
import subprocess
import tarfile


SRPM = (19165235, 'de8e6ebb2fb7b7aa0e1297c0c27c3339d15c37b24b57ca16a762483580ea7168')
ARCHIVE = (19088198, '100fc873b848b9b0297d8a705e8e2ed326256c8483d9960ee1ffe264c8a5c3e3')


def ident(data):
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def selected(path):
    return (path in ('src/core/socket.c', 'src/core/dbus-socket.c',
                     'src/journal/journald-server.c', 'src/journal/journald-varlink.c',
                     'src/basic/fs-util.c', 'src/shared/label-util.c') or
            path.startswith('src/journalctl/') and path.endswith(('.c', '.h')) or
            path.startswith(('src/libsystemd/', 'src/shared/')) and
            'varlink' in path and path.endswith(('.c', '.h')) or
            path.startswith(('units/systemd-udevd-varlink', 'units/systemd-journald')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--srpm', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    st = args.srpm.lstat()
    if not stat.S_ISREG(st.st_mode):
        raise ValueError('SRPM must be an ordinary file')
    raw = args.srpm.read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != SRPM:
        raise ValueError('unexpected fixed SRPM identity')
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('new output directory required')
    args.output.mkdir(mode=0o700)
    cpio = subprocess.run(['rpm2cpio', str(args.srpm)], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=40, check=True)
    if len(cpio.stdout) > 64 * 1024**2:
        raise ValueError('unexpected SRPM payload size')

    def member(name):
        result = subprocess.run(['cpio', '--extract', '--to-stdout', '--quiet', './' + name],
                                input=cpio.stdout, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=20, check=True)
        if not result.stdout or result.stderr:
            raise ValueError('exact ordinary SRPM member was not read cleanly: ' + name)
        return result.stdout

    archive = member('systemd-262.1.tar.gz')
    if (len(archive), hashlib.sha256(archive).hexdigest()) != ARCHIVE:
        raise ValueError('unexpected embedded source archive identity')
    files = {}
    for name in ('systemd.spec', '30846.patch',
                 '0001-core-create-userdb-root-directory-with-correct-label.patch',
                 '0002-machined-continue-without-resolve.hook-socket.patch'):
        data = member(name)
        target = args.output / 'srpm' / name
        target.parent.mkdir(mode=0o700, exist_ok=True)
        target.write_bytes(data)
        files['srpm/' + name] = ident(data)

    expanded = 0
    archive_roots = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r|gz') as tf:
        for item in tf:
            expanded += item.size
            if expanded > 512 * 1024**2:
                raise ValueError('source archive expansion exceeds bound')
            parts = Path(item.name).parts
            if len(parts) < 2:
                continue
            relative = '/'.join(parts[1:])
            if not selected(relative):
                continue
            if not item.isfile() or item.size > 2 * 1024**2 or '..' in parts:
                raise ValueError('selected source must be a bounded ordinary file')
            archive_roots.add(parts[0])
            data = tf.extractfile(item).read()
            target = args.output / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open('xb') as out:
                out.write(data)
            files[relative] = ident(data)

    if len(archive_roots) != 1 or 'src/core/socket.c' not in files:
        raise ValueError('fixed source root/socket member was not found exactly')

    pattern = re.compile(r'io[.]systemd[.](?:Udev|journal)|varlink_registry|varlink/registry|'
                         r'Symlinks=|symlink|unlink|REGISTER|register|unregister')
    matches = []
    for relative in files:
        if relative.startswith('srpm/'):
            continue
        for line_no, line in enumerate((args.output / relative).read_text().splitlines(), 1):
            if pattern.search(line):
                matches.append({'path': relative, 'line': line_no, 'text': line})
    report = {'schema_version': 1, 'scope': 'fixed official package source inspection only',
              'srpm': {'path': str(args.srpm), **ident(raw)}, 'archive': ident(archive),
              'script': ident(Path(__file__).read_bytes()), 'archive_root': next(iter(archive_roots)),
              'files': files, 'matches': matches,
              'target_program_executed': False, 'rootfs_modified': False,
              'kernel_policy_loaded_or_written': False, 'vm_started': False}
    (args.output / 'source-index.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'source_files': len(files), 'matches': len(matches),
                      'index': str(args.output / 'source-index.json')}))


if __name__ == '__main__':
    main()
