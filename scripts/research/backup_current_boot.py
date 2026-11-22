#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Copy eight fixed current TB371FC boot partitions to new private files.

Sources are opened read-only. This tool never restores, flashes, unlocks,
changes a slot, or reboots. Current bytes are not a pristine factory image.
The destination is on userdata: a second independently verified off-device
copy is still required before treating it as a recovery backup.
"""
from __future__ import annotations

import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import sys

DESTINATION = Path('/data/local/tmp/tb371fc-current-boot-backup-20261123')
PARTITIONS = {f'{base}_{slot}': size
              for base, size in (('boot', 100663296), ('recovery', 104857600),
                                 ('vbmeta', 65536), ('dtbo', 25165824))
              for slot in ('a', 'b')}
CHUNK = 4 * 1024 * 1024
BLKGETSIZE64 = 0x80081272


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def block_size(fd):
    if not stat.S_ISBLK(os.fstat(fd).st_mode):
        raise ValueError('source is not a block device')
    return struct.unpack('Q', fcntl.ioctl(fd, BLKGETSIZE64, b'\0' * 8))[0]


def digest_fd(fd, size):
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        block = os.pread(fd, min(CHUNK, size - offset), offset)
        if not block:
            raise ValueError('unexpected short read')
        digest.update(block)
        offset += len(block)
    return digest.hexdigest()


def save_json(directory_fd, name, value):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, 'w') as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    os.fsync(directory_fd)


def main():
    if len(sys.argv) != 1 or os.geteuid() != 0:
        raise SystemExit('Run as root without arguments; no alternate partitions or destination accepted')
    os.umask(0o077)
    # Refuse unexpected devices or inadequate capacity before creating output.
    if DESTINATION.exists() or DESTINATION.is_symlink():
        raise SystemExit('Destination already exists; retain it and inspect its manifest')
    for name, expected_size in PARTITIONS.items():
        fd = os.open('/dev/block/by-name/' + name, os.O_RDONLY | os.O_CLOEXEC)
        try:
            if block_size(fd) != expected_size:
                raise ValueError('unexpected partition size: ' + name)
        finally:
            os.close(fd)
    space = os.statvfs(DESTINATION.parent)
    available = space.f_bavail * space.f_frsize
    total = sum(PARTITIONS.values())
    if available < total + 2 * 1024**3:
        raise SystemExit('Insufficient free capacity including a 2 GiB reserve')
    DESTINATION.mkdir(mode=0o700)
    directory_fd = os.open(DESTINATION, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    result = {'schema_version': 1, 'started_utc': utc(),
              'scope': 'current partition bytes, not pristine factory images',
              'status': 'in_progress', 'destination': str(DESTINATION),
              'source_open_mode': 'O_RDONLY', 'expected_total_bytes': total,
              'off_device_copy_verified': False, 'restore_tested': False,
              'physical_mainline_boot_tested': False, 'partitions': []}
    try:
        owner = os.fstat(directory_fd)
        if owner.st_uid != 0 or stat.S_IMODE(owner.st_mode) != 0o700:
            raise ValueError('destination owner or mode mismatch')
        save_json(directory_fd, 'started.json', result)
        for name, size in PARTITIONS.items():
            source = os.open('/dev/block/by-name/' + name, os.O_RDONLY | os.O_CLOEXEC)
            try:
                if block_size(source) != size:
                    raise ValueError('source changed size: ' + name)
                partial_name = name + '.img.partial'
                target = os.open(partial_name,
                                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=directory_fd)
                digest = hashlib.sha256()
                offset = 0
                with os.fdopen(target, 'wb') as output:
                    while offset < size:
                        block = os.pread(source, min(CHUNK, size - offset), offset)
                        if not block:
                            raise ValueError('unexpected source EOF: ' + name)
                        output.write(block)
                        digest.update(block)
                        offset += len(block)
                    output.flush()
                    os.fsync(output.fileno())
                expected = digest.hexdigest()
                verification_fd = os.open(partial_name, os.O_RDONLY | os.O_NOFOLLOW,
                                          dir_fd=directory_fd)
                try:
                    info = os.fstat(verification_fd)
                    if (not stat.S_ISREG(info.st_mode) or info.st_size != size
                            or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600):
                        raise ValueError('backup file metadata mismatch: ' + name)
                    copied = digest_fd(verification_fd, size)
                finally:
                    os.close(verification_fd)
                source_recheck = digest_fd(source, size)
                if copied != expected or source_recheck != expected or block_size(source) != size:
                    raise ValueError('copy mismatch or source changed during read: ' + name)
                # A new root-only directory prevents an untrusted replacement race.
                os.rename(partial_name, name + '.img',
                          src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
                os.fsync(directory_fd)
                record = {'name': name, 'file': name + '.img', 'bytes': size,
                          'source_sha256': expected, 'backup_sha256': copied,
                          'source_recheck_sha256': source_recheck, 'verified': True}
                result['partitions'].append(record)
                save_json(directory_fd, name + '.json', record)
                print('VERIFIED ' + name + ' ' + str(size), flush=True)
            finally:
                os.close(source)
        result['status'] = 'verified_current_local_copies'
        result['completed_utc'] = utc()
        save_json(directory_fd, 'manifest.json', result)
        print(json.dumps({'status': result['status'], 'partitions': len(result['partitions']),
                          'total_bytes': total, 'manifest': str(DESTINATION / 'manifest.json')}),
              flush=True)
    except BaseException as error:
        result['status'] = 'failed_retained_partial_outputs'
        result['completed_utc'] = utc()
        result['error'] = {'type': type(error).__name__, 'message': str(error)[:512]}
        save_json(directory_fd, 'failure.json', result)
        raise
    finally:
        os.close(directory_fd)


if __name__ == '__main__':
    main()
