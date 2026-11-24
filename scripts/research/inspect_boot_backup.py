#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect version-2 Android boot headers in a verified private backup.

Emit only numeric layout, component hashes and compression signatures. Never
print command lines, product-name fields, image IDs, ramdisk paths or contents.
This is format inspection, not AVB signature/rollback or bootability checking.
Layout reference: https://source.android.com/docs/core/architecture/bootloader/boot-image-header
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import struct
import tarfile


def digest_file(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def inspect(source, partition_size):
    header = source.read(4096)
    if len(header) < 1660 or header[:8] != b'ANDROID!':
        raise ValueError('not a complete Android boot header')
    names = ('kernel_size', 'kernel_addr', 'ramdisk_size', 'ramdisk_addr',
             'second_size', 'second_addr', 'tags_addr', 'page_size',
             'header_version', 'os_version')
    values = dict(zip(names, struct.unpack_from('<10I', header, 8)))
    if values['header_version'] != 2:
        raise ValueError('only the explicitly reviewed version-2 layout is supported')
    values.update(zip(('recovery_dtbo_size', 'recovery_dtbo_offset', 'header_size',
                       'dtb_size', 'dtb_addr'), struct.unpack_from('<IQIIQ', header, 1632)))
    page = values['page_size']
    if page < 2048 or page > 65536 or page & (page - 1) or values['header_size'] != 1660:
        raise ValueError('unexpected header or page size')
    offset = page
    components = []
    for name in ('kernel', 'ramdisk', 'second', 'recovery_dtbo', 'dtb'):
        size = values[name + '_size']
        if not size:
            continue
        if name == 'recovery_dtbo' and values['recovery_dtbo_offset'] != offset:
            raise ValueError('noncanonical recovery DTBO location')
        if offset + size > partition_size:
            raise ValueError('component exceeds the copied partition')
        source.seek(offset)
        digest = hashlib.sha256()
        remaining = size
        prefix = b''
        release_strings = set()
        previous_tail = b''
        while remaining:
            data = source.read(min(1024**2, remaining))
            if not data:
                raise ValueError('truncated component')
            if not prefix:
                prefix = data[:64]
            if name == 'kernel':
                release_strings.update(match.decode('ascii') for match in re.findall(
                    rb'Linux version ([0-9][0-9A-Za-z._+\-]{0,95}) ', previous_tail + data))
                previous_tail = data[-128:]
            digest.update(data)
            remaining -= len(data)
        signature = ('gzip' if prefix[:2] == b'\x1f\x8b' else
                     'lz4_legacy' if prefix[:4] == b'\x02\x21\x4c\x18' else
                     'lz4_frame' if prefix[:4] == b'\x04\x22\x4d\x18' else
                     'fdt' if prefix[:4] == b'\xd0\x0d\xfe\xed' else
                     'arm64_image' if prefix[56:60] == b'ARM\x64' else 'unclassified')
        component = {'name': name, 'offset': offset, 'bytes': size,
                     'sha256': digest.hexdigest(), 'signature': signature}
        if name == 'kernel':
            if len(release_strings) > 8:
                raise ValueError('unexpected number of kernel release strings')
            component['release_strings'] = sorted(release_strings)
            if signature == 'arm64_image':
                component['arm64_image_header'] = dict(zip(
                    ('text_offset', 'image_size', 'flags'), struct.unpack_from('<3Q', prefix, 8)))
        components.append(component)
        offset += (size + page - 1) // page * page
    return {'header': values, 'components': components,
            'page_aligned_payload_end': offset,
            'partition_padding_or_trailer_bytes': partition_size - offset}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup-directory', type=Path, required=True)
    args = parser.parse_args()
    base = args.backup_directory.resolve(strict=True)
    receipt_path = base / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    archive_path = base / 'current-boot.tar.gz'
    if (receipt.get('status') != 'verified_off_device_current_copies'
            or digest_file(archive_path) != receipt.get('archive_sha256')):
        raise SystemExit('off-device archive verification failed')
    records = {r['name']: r for r in receipt['verified_partitions']}
    result = {'schema_version': 1,
              'inspection_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'numeric Android v2 boot layout, no private ramdisk data',
              'script_sha256': digest_file(Path(__file__)),
              'receipt_sha256': digest_file(receipt_path),
              'archive_sha256': receipt['archive_sha256'],
              'avb_signature_verified': False, 'rollback_compatibility_verified': False,
              'bootability_tested': False, 'images': {}}
    with tarfile.open(archive_path, 'r:gz') as archive:
        for name in ('boot_a', 'boot_b', 'recovery_a', 'recovery_b'):
            member = archive.getmember(name + '.img')
            if not member.isfile() or member.size != records[name]['bytes']:
                raise ValueError('partition member does not match receipt')
            with archive.extractfile(member) as source:
                details = inspect(source, member.size)
            details['partition_sha256'] = records[name]['sha256']
            result['images'][name] = details
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
