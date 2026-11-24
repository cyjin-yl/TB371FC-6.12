#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Receive a current-partition archive over authenticated SSH and verify it.

No tar member is extracted to the filesystem and no block device is opened.
An existing destination is never reused. Only hashes and a receipt are public;
the archive must remain in the owner's private, ignored backup directory.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tarfile

PARTITIONS = {f'{base}_{slot}': size
              for base, size in (('boot', 100663296), ('recovery', 104857600),
                                 ('vbmeta', 65536), ('dtbo', 25165824))
              for slot in ('a', 'b')}
MAX_ARCHIVE_BYTES = 1024**3
CHUNK = 1024**2


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def write_json(path, data):
    with path.open('x') as output:
        json.dump(data, output, indent=2, sort_keys=True)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    parent = args.destination.parent.resolve(strict=True)
    destination = parent / args.destination.name
    if destination.exists() or destination.is_symlink():
        raise SystemExit('Destination exists; retain it and choose a new directory')
    info = parent.stat()
    if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise SystemExit('Parent must be private and owned by the receiver')
    available = os.statvfs(parent)
    if available.f_bavail * available.f_frsize < MAX_ARCHIVE_BYTES + 1024**3:
        raise SystemExit('Insufficient private backup capacity')
    destination.mkdir(mode=0o700)
    receipt = {'schema_version': 1, 'started_utc': utc(),
               'status': 'in_progress', 'scope': 'current boot partition backups',
               'restore_tested': False, 'pristine_factory_images': False,
               'physical_mainline_boot_tested': False,
               'receiver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write_json(destination / 'started.json', receipt)
    try:
        partial = destination / 'current-boot.tar.gz.partial'
        digest = hashlib.sha256()
        received = 0
        with partial.open('xb') as output:
            while block := sys.stdin.buffer.read(CHUNK):
                received += len(block)
                if received > MAX_ARCHIVE_BYTES:
                    raise ValueError('archive exceeds the fixed input limit')
                output.write(block)
                digest.update(block)
            output.flush()
            os.fsync(output.fileno())
        expected_names = {'started.json', 'manifest.json'} | {
            name + suffix for name in PARTITIONS for suffix in ('.img', '.json')}
        verified = []
        with tarfile.open(partial, 'r:gz') as archive:
            members = archive.getmembers()
            if len(members) != len(expected_names) or {m.name for m in members} != expected_names:
                raise ValueError('unexpected, missing or duplicate archive members')
            for member in members:
                if not member.isfile() or member.name != Path(member.name).name:
                    raise ValueError('non-regular or non-basename archive member')
                size = (PARTITIONS[member.name[:-4]] if member.name.endswith('.img') else None)
                if size is not None and member.size != size:
                    raise ValueError('image size mismatch: ' + member.name)
                if size is None and not 0 < member.size <= 65536:
                    raise ValueError('JSON member size is invalid')
            manifest_bytes = archive.extractfile('manifest.json').read(65537)
            manifest = json.loads(manifest_bytes)
            if (manifest.get('status') != 'verified_current_local_copies'
                    or manifest.get('source_open_mode') != 'O_RDONLY'
                    or manifest.get('expected_total_bytes') != sum(PARTITIONS.values())):
                raise ValueError('source manifest contract mismatch')
            records = manifest.get('partitions', [])
            if len(records) != len(PARTITIONS) or {r['name'] for r in records} != set(PARTITIONS):
                raise ValueError('source partition set mismatch')
            for record in records:
                name = record['name']
                if (record.get('bytes') != PARTITIONS[name] or record.get('file') != name + '.img'
                        or record.get('verified') is not True):
                    raise ValueError('source record contract mismatch: ' + name)
                hasher = hashlib.sha256()
                size = 0
                with archive.extractfile(name + '.img') as source:
                    while block := source.read(CHUNK):
                        hasher.update(block)
                        size += len(block)
                sha256 = hasher.hexdigest()
                if (size != PARTITIONS[name] or any(record.get(key) != sha256 for key in
                        ('backup_sha256', 'source_sha256', 'source_recheck_sha256'))):
                    raise ValueError('off-device byte verification failed: ' + name)
                sidecar = json.loads(archive.extractfile(name + '.json').read(65537))
                if sidecar != record:
                    raise ValueError('source sidecar differs: ' + name)
                verified.append({'name': name, 'bytes': size, 'sha256': sha256})
        # Re-read the stored archive independently after the full tar validation.
        with partial.open('rb') as source:
            stored_hash = hashlib.file_digest(source, 'sha256').hexdigest()
        if stored_hash != digest.hexdigest() or partial.stat().st_size != received:
            raise ValueError('stored archive differs from received stream')
        archive_path = destination / 'current-boot.tar.gz'
        partial.rename(archive_path)
        receipt.update({'status': 'verified_off_device_current_copies', 'completed_utc': utc(),
                        'source_capture_started_utc': manifest['started_utc'],
                        'source_capture_completed_utc': manifest['completed_utc'],
                        'source_manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
                        'archive_file': archive_path.name, 'archive_bytes': received,
                        'archive_sha256': stored_hash,
                        'off_device_copy_verified': True, 'verified_partitions': verified})
        write_json(destination / 'receipt.json', receipt)
        directory_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        print(json.dumps(receipt, indent=2, sort_keys=True))
    except BaseException as error:
        receipt.update({'status': 'failed_retained_partial_outputs', 'completed_utc': utc(),
                        'error': {'type': type(error).__name__, 'message': str(error)[:512]}})
        write_json(destination / 'failure.json', receipt)
        raise


if __name__ == '__main__':
    main()
