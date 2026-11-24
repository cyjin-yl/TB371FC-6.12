#!/usr/bin/env python3
"""Assemble a separate Fedora ARM system tree in the existing CT102 builder.

The seed tree and earlier research artifacts are read-only inputs. This helper
does not mount a filesystem, access a physical device, install a host bootloader
or register binfmt handlers. Guest commands run through the already qualified
PRoot/QEMU combination. Package versions are resolved once and then pinned.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


WORK = Path('/work/fedora-system-integration-v1')
SEED = Path('/work/fedora-bundle/rootfs')
ROOT = WORK / 'rootfs'
PROOT = Path('/work/fedora-proot-src/src/proot')
HOST_LIBS = Path('/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu')
QEMU = Path('/usr/bin/qemu-aarch64-static')
PACKAGES = (
    'systemd', 'systemd-udev', 'dracut', 'dracut-network', 'e2fsprogs',
    'kmod', 'util-linux', 'policycoreutils', 'libselinux-utils',
    'selinux-policy-targeted', 'NetworkManager', 'bluez', 'pipewire',
    'pipewire-alsa', 'wireplumber', 'alsa-utils',
)
DNF_FLAGS = ('--releasever=45', '--forcearch=aarch64', '--setopt=zchunk=False',
             '--setopt=install_weak_deps=False', '--setopt=keepcache=True',
             '--repo=fedora', '--repo=updates')
RPM_FORMAT = '%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\n'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    with (WORK / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def run_guest(arguments, capture=False):
    if not ROOT.is_dir() or ROOT.is_symlink():
        raise ValueError('prepared, ordinary system root required')
    env = dict(os.environ, LD_LIBRARY_PATH=str(HOST_LIBS), SYSTEMD_OFFLINE='1')
    command = [str(PROOT), '-0', '-r', str(ROOT), '-q', str(QEMU),
               '-b', '/proc', '-b', '/dev/null', '-b', '/dev/zero',
               '-b', '/dev/random', '-b', '/dev/urandom',
               '-b', '/etc/resolv.conf:/etc/resolv.conf', '-w', '/', *arguments]
    return subprocess.run(command, env=env, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None)


def prepare():
    if WORK.exists() or WORK.is_symlink():
        raise ValueError('the new integration directory must not exist')
    if not SEED.is_dir() or SEED.is_symlink():
        raise ValueError('qualified Fedora seed directory unavailable')
    if 'VERSION_ID=45\n' not in (SEED / 'etc/os-release').read_text():
        raise ValueError('seed is not Fedora 45')
    if shutil.disk_usage(WORK.parent).free < 8 * 1024**3:
        raise ValueError('less than 8 GiB available for the separate system tree/image')
    for tool in (PROOT, QEMU):
        if not tool.is_file():
            raise ValueError('qualified execution tool unavailable: ' + str(tool))
    WORK.mkdir(mode=0o755)
    # cp -a retains the distribution's actual symlinks and permissions. This is
    # a new full tree, not a set of compatibility links into the old experiment.
    subprocess.run(['cp', '-a', '--reflink=auto', str(SEED), str(ROOT)], check=True)
    packages = run_guest(['/usr/bin/rpm', '-qa', '--qf', RPM_FORMAT], capture=True).stdout
    (WORK / 'packages.before.tsv').write_text(packages)
    save('seed.json', {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'source_root': str(SEED), 'new_root': str(ROOT),
                      'seed_package_count': len(packages.splitlines()),
                      'seed_packages_sha256': sha(WORK / 'packages.before.tsv'),
                      'proot_sha256': sha(PROOT), 'qemu_sha256': sha(QEMU),
                      'seed_modified': False, 'tablet_accessed': False})
    print('FEDORA_SYSTEM_SEPARATE_TREE_READY', flush=True)


def query():
    output = run_guest(['/usr/bin/dnf5', *DNF_FLAGS, 'repoquery', '--available',
                        '--latest-limit', '1', '--queryformat', '%{name}\t%{evr}\t%{arch}\n',
                        *PACKAGES], capture=True).stdout
    number = 1
    while (WORK / f'package-query-{number:02d}.stdout').exists():
        number += 1
    with (WORK / f'package-query-{number:02d}.stdout').open('x') as stream:
        stream.write(output)
    found = {}
    for line in output.splitlines():
        fields = line.split('\t')
        if len(fields) != 3 or fields[0] not in PACKAGES:
            continue
        name, evr, arch = fields
        if arch not in ('aarch64', 'noarch') or not re.fullmatch(r'[A-Za-z0-9_.+:~^-]+', evr):
            raise ValueError('unexpected package identity: ' + line)
        if name in found and found[name] != {'evr': evr, 'arch': arch}:
            raise ValueError('ambiguous available package: ' + name)
        found[name] = {'evr': evr, 'arch': arch}
    if set(found) != set(PACKAGES):
        raise ValueError('missing package query: ' + repr(sorted(set(PACKAGES) - set(found))))
    save('package-pins.json', {'release': '45', 'architecture': 'aarch64',
                             'flags': list(DNF_FLAGS), 'packages': found})
    print(json.dumps(found, indent=2, sort_keys=True))


def install():
    record = json.loads((WORK / 'package-pins.json').read_text())
    if set(record['packages']) != set(PACKAGES):
        raise ValueError('package pin set differs from the reviewed request')
    selected = [f"{name}-{record['packages'][name]['evr']}.{record['packages'][name]['arch']}"
                for name in PACKAGES]
    run_guest(['/usr/bin/dnf5', '-y', *DNF_FLAGS, 'install', *selected])
    run_guest(['/usr/bin/dnf5', *DNF_FLAGS, '--cacheonly', 'check'])
    run_guest(['/usr/bin/rpm', '--verifydb'])
    run_guest(['/usr/bin/rpm', '-q', *selected])
    packages = run_guest(['/usr/bin/rpm', '-qa', '--qf', RPM_FORMAT], capture=True).stdout
    (WORK / 'packages.after.tsv').write_text(packages)
    print('FEDORA_SYSTEM_PACKAGES_INSTALLED', len(packages.splitlines()), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'query', 'install', 'exec'))
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.phase == 'exec':
        if not args.arguments:
            parser.error('exec requires an explicit guest command')
        run_guest(args.arguments)
    else:
        if args.arguments:
            parser.error('unexpected arguments')
        {'prepare': prepare, 'query': query, 'install': install}[args.phase]()


if __name__ == '__main__':
    main()
