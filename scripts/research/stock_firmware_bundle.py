#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Capture and verify only the fixed TB371FC stock-firmware evidence set.

collect: read 118 regular files from three explicit Android vendor roots into
a new root-only evidence archive. No /data configuration, device nodes, loader
controls, credentials, or unrelated firmware are read. Only the new capture
directory is written. receive: accept that archive on stdin, verify the exact
source hash and member set, and inspect ELF/MDT structure without extraction.
Neither operation loads firmware or authenticates Qualcomm signatures.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import tarfile


CAPTURE_DIRECTORY = Path('/data/local/tmp/tb371fc-stock-firmware-20261123')
CHUNK = 1024 * 1024
MAX_FILE = 32 * CHUNK
MAX_PAYLOAD = 128 * CHUNK
MAX_ARCHIVE = 128 * CHUNK
MAX_MANIFEST = 128 * 1024
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
PT_LOAD = 1
QCOM_MDT_TYPE_MASK = 7 << 24
QCOM_MDT_TYPE_HASH = 2 << 24


def fixed_sources():
    """Return exact relative paths; never glob or enumerate a source directory."""
    sources = {}

    def add(root, names, group):
        for name in names:
            relative = root.strip('/') + '/' + name
            if relative in sources:
                raise ValueError('duplicate fixed source')
            sources[relative] = group

    image = '/vendor/firmware_mnt/image'
    for stem, numbers in (
        ('adsp', range(19)),
        ('cdsp', [0, 1, 2, 3, 4, 5, 6, 8, 9, 11]),
        ('slpi', range(21)),
        ('venus', [*range(11), 19]),
    ):
        add(image, [stem + '.mdt', *[f'{stem}.b{i:02d}' for i in numbers]], stem)
    add(image + '/qca6390', ['amss20.bin', 'm3.bin', 'regdb.bin'], 'wlan')
    add(image + '/qca6390', [*[f'bdwlan.e{i:02x}' for i in range(1, 27)],
                            'bdwlan.e25', 'bdwlan.elf'], 'wlan_board_candidates')
    add('/vendor/firmware', ['a650_gmu.bin', 'a650_sqe.fw', 'a650_zap.elf',
                             'a650_zap.mdt', 'a650_zap.b00', 'a650_zap.b01',
                             'a650_zap.b02'], 'a650')
    add('/vendor/firmware', [
        'novatek_ts_fw_boe.bin', 'novatek_ts_fw_boe_6.bin',
        'novatek_ts_mp_boe.bin', 'novatek_ts_mp_boe_6.bin',
        'novatek_ts_tm_fw.bin', 'novatek_ts_tm_fw_6.bin',
        'novatek_ts_tm_mp.bin', 'novatek_ts_tm_mp_6.bin',
    ], 'novatek_candidates')
    add('/vendor/firmware', ['tfa98xx_QS.cnt', 'tfa98xx_YC.cnt'], 'tfa9894_candidates')
    add('/vendor/bt_firmware/image',
        ['htbtfw10.tlv', 'htbtfw20.tlv', 'htnv10.bin', 'htnv20.bin'], 'bluetooth')
    if len(sources) != 118:
        raise ValueError('fixed source count differs from the reviewed allowlist')
    return dict(sorted(sources.items()))


SOURCES = fixed_sources()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


@contextmanager
def open_directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('directory must be absolute and contain no parent traversal')
    fd = os.open('/', DIR_FLAGS)
    try:
        for name in path.parts[1:]:
            following = os.open(name, DIR_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = following
        yield fd
    finally:
        os.close(fd)


def read_source(relative):
    if relative not in SOURCES:
        raise ValueError('source is not explicitly allowed')
    path = Path('/') / relative
    with open_directory(path.parent) as parent:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_FILE:
            raise ValueError('source is not a bounded nonempty regular file: ' + relative)
        fd = os.open(path.name, READ_FLAGS, dir_fd=parent)
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or
                    (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)):
                raise ValueError('source identity changed: ' + relative)
            with os.fdopen(os.dup(fd), 'rb') as source:
                data = source.read(MAX_FILE + 1)
            after = os.fstat(fd)
            if (len(data) != before.st_size or len(data) > MAX_FILE or
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns)):
                raise ValueError('source changed while reading: ' + relative)
        finally:
            os.close(fd)
    return data


def write_new(directory_fd, name, data):
    if name != Path(name).name:
        raise ValueError('output must be a basename')
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=directory_fd)
    with os.fdopen(fd, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    os.fsync(directory_fd)


def add_member(archive, name, data):
    member = tarfile.TarInfo(name)
    member.size = len(data)
    member.mode = 0o600
    member.uid = member.gid = member.mtime = 0
    archive.addfile(member, io.BytesIO(data))


def collect():
    if os.geteuid() != 0:
        raise ValueError('collect requires root for the fixed vendor-file read set')
    os.umask(0o077)
    # Read all inputs before creating output, failing closed on an absent file.
    started = utc()
    payloads, total_bytes = {}, 0
    for name in SOURCES:
        data = read_source(name)
        total_bytes += len(data)
        if total_bytes > MAX_PAYLOAD:
            raise ValueError('fixed source set exceeds the total size bound')
        payloads[name] = data
    records = []
    for name, data in payloads.items():
        if sha(read_source(name)) != sha(data):
            raise ValueError('source content changed on the independent re-read: ' + name)
        records.append({'archive_path': name, 'source_path': '/' + name,
                        'group': SOURCES[name], 'size_bytes': len(data), 'sha256': sha(data),
                        'regular_file': True, 'symlink': False, 'source_recheck_match': True})
    manifest = {
        'schema_version': 1, 'status': 'verified_fixed_vendor_capture',
        'scope': 'Private firmware evidence; no loading or vendor-signature authentication',
        'started_utc': started, 'completed_utc': utc(),
        'source_roots': ['/vendor/firmware', '/vendor/firmware_mnt/image',
                         '/vendor/bt_firmware/image'],
        'collector_sha256': sha(Path(__file__).read_bytes()),
        'source_open_mode': 'O_RDONLY|O_NOFOLLOW', 'source_recheck_match': True,
        'user_configuration_read': False, 'firmware_loaded': False,
        'vendor_signature_authentication_performed': False,
        'file_count': len(records), 'total_payload_bytes': sum(map(len, payloads.values())),
        'files': records,
    }
    manifest_data = json_bytes(manifest)
    with open_directory(CAPTURE_DIRECTORY.parent) as parent:
        os.mkdir(CAPTURE_DIRECTORY.name, 0o700, dir_fd=parent)
        with open_directory(CAPTURE_DIRECTORY) as destination:
            os.fchmod(destination, 0o700)
            write_new(destination, 'manifest.json', manifest_data)
            filename = 'stock-firmware.tar.gz'
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=destination)
            with os.fdopen(fd, 'wb') as output:
                with gzip.GzipFile(filename='', mode='wb', fileobj=output,
                                   compresslevel=6, mtime=0) as compressed:
                    with tarfile.open(fileobj=compressed, mode='w', format=tarfile.USTAR_FORMAT) as archive:
                        for name, data in payloads.items():
                            add_member(archive, name, data)
                        add_member(archive, 'manifest.json', manifest_data)
                output.flush()
                os.fsync(output.fileno())
            archive_path = CAPTURE_DIRECTORY / filename
            with archive_path.open('rb') as stream:
                archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
            result = {'status': 'captured', 'capture_directory': str(CAPTURE_DIRECTORY),
                      'archive_file': filename, 'archive_bytes': archive_path.stat().st_size,
                      'archive_sha256': archive_sha, 'manifest_sha256': sha(manifest_data),
                      'file_count': len(records), 'total_payload_bytes': manifest['total_payload_bytes'],
                      'collector_sha256': manifest['collector_sha256']}
            write_new(destination, 'archive.json', json_bytes(result))
    print(json.dumps(result, indent=2, sort_keys=True))


def inspect_mdt(name, payloads):
    """Apply the frozen Linux 6.12.114 split/header selection rules, not authentication."""
    data = payloads[name]
    if len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01':
        raise ValueError('expected little-endian ELF32 version 1')
    machine = struct.unpack_from('<H', data, 18)[0]
    version = struct.unpack_from('<I', data, 20)[0]
    phoff = struct.unpack_from('<I', data, 28)[0]
    ehsize, phsize, phnum = struct.unpack_from('<HHH', data, 40)
    table_end = phoff + phsize * phnum
    if (version != 1 or ehsize != 52 or phsize != 32 or not 2 <= phnum <= 100 or
            phoff < ehsize or table_end > len(data)):
        raise ValueError('invalid or unsupported ELF program-header table')
    headers = []
    for index in range(phnum):
        kind, offset, _, physical, filesz, memsz, flags, alignment = struct.unpack_from(
            '<8I', data, phoff + index * phsize)
        headers.append({'index': index, 'type': kind, 'file_offset': offset,
                        'file_size': filesz, 'memory_size': memsz, 'flags': flags,
                        'physical_address': physical, 'alignment': alignment})
    first = headers[0]
    if first['type'] == PT_LOAD or not table_end <= first['file_size'] <= len(data):
        raise ValueError('invalid Qualcomm metadata header segment')
    hash_headers = [row for row in headers[1:]
                    if row['flags'] & QCOM_MDT_TYPE_MASK == QCOM_MDT_TYPE_HASH]
    if not hash_headers or not 0 < hash_headers[0]['file_size'] <= MAX_FILE:
        raise ValueError('Qualcomm metadata hash segment absent or invalid')
    hashed = hash_headers[0]
    stem = str(Path(name).with_suffix(''))
    required = {}
    if first['file_size'] + hashed['file_size'] == len(data):
        hash_source = 'packed immediately after metadata header'
    elif hashed['file_offset'] + hashed['file_size'] <= len(data):
        hash_source = 'embedded at hash program-header offset'
    else:
        hash_source = f"{stem}.b{hashed['index']:02d}"
        required[hash_source] = {'index': hashed['index'], 'size_bytes': hashed['file_size'],
                                 'reason': 'metadata hash'}
    split = any(row['file_offset'] + row['file_size'] > len(data)
                for row in headers if row['file_size'])
    valid = [row for row in headers if row['type'] == PT_LOAD and row['memory_size'] and
             row['flags'] & QCOM_MDT_TYPE_MASK != QCOM_MDT_TYPE_HASH]
    if not valid:
        raise ValueError('no non-hash loadable segment')
    for row in valid:
        if row['file_size'] > row['memory_size'] or row['file_size'] > MAX_FILE:
            raise ValueError('invalid payload file/memory sizes')
        if row['file_offset'] + row['file_size'] > 0xffffffff:
            raise ValueError('ELF32 payload file extent overflow')
        if split and row['file_size']:
            required[f"{stem}.b{row['index']:02d}"] = {
                'index': row['index'], 'size_bytes': row['file_size'], 'reason': 'loadable payload'}
    missing, mismatched, verified = [], [], []
    for segment, record in sorted(required.items()):
        if segment not in payloads:
            missing.append(segment)
        elif len(payloads[segment]) != record['size_bytes']:
            mismatched.append({'path': segment, 'expected': record['size_bytes'],
                               'actual': len(payloads[segment])})
        else:
            verified.append({'path': segment, **record, 'sha256': sha(payloads[segment])})
    captured_segments = sorted(path for path in payloads
                               if re.fullmatch(re.escape(stem) + r'\.b[0-9]{2}', path))
    return {'metadata_path': name, 'format': 'ELF32 little endian', 'elf_machine': machine,
            'program_header_count': phnum, 'program_headers': headers,
            'split_payload_required': split, 'metadata_hash_source': hash_source,
            'required_split_files': verified, 'missing_required_files': missing,
            'size_mismatches': mismatched,
            'captured_segments_not_requested_by_this_metadata': sorted(set(captured_segments) - set(required)),
            'loadable_zero_file_size_indices': [row['index'] for row in valid if not row['file_size']],
            'loader_file_set_complete': not missing and not mismatched,
            'scope': 'Required-file and byte-length checks only; no signature, load, memory reservation, ABI or hardware test'}


def receive(args):
    os.umask(0o077)
    if any(not re.fullmatch('[0-9a-f]{64}', value) for value in
           (args.expected_archive_sha256, args.expected_manifest_sha256)):
        raise ValueError('expected hashes must be explicit SHA256 values')
    if not 0 < args.expected_archive_bytes <= MAX_ARCHIVE:
        raise ValueError('expected archive size exceeds its bound')
    destination = args.destination
    with open_directory(destination.parent) as parent:
        owner = os.fstat(parent)
        if owner.st_uid != os.geteuid() or stat.S_IMODE(owner.st_mode) & 0o022:
            raise ValueError('destination parent must be receiver-owned and not writable by others')
        os.mkdir(destination.name, 0o700, dir_fd=parent)
        with open_directory(destination) as directory:
            os.fchmod(directory, 0o700)
            result = {'schema_version': 1, 'started_utc': utc(), 'status': 'in_progress',
                      'scope': 'Private fixed stock-firmware transfer and structural evidence',
                      'receiver_sha256': sha(Path(__file__).read_bytes()),
                      'vendor_signature_authentication_performed': False,
                      'firmware_loaded': False, 'tablet_linux_tested': False,
                      'canonical_firmware_tree_generated': False, 'video_decode_tested': False}
            write_new(directory, 'started.json', json_bytes(result))
            try:
                partial_name = 'stock-firmware.tar.gz.partial'
                fd = os.open(partial_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
                digest, received = hashlib.sha256(), 0
                with os.fdopen(fd, 'wb') as output:
                    while block := sys.stdin.buffer.read(CHUNK):
                        received += len(block)
                        if received > args.expected_archive_bytes or received > MAX_ARCHIVE:
                            raise ValueError('received archive exceeds the exact source size')
                        digest.update(block)
                        output.write(block)
                    output.flush()
                    os.fsync(output.fileno())
                if received != args.expected_archive_bytes or digest.hexdigest() != args.expected_archive_sha256:
                    raise ValueError('received archive does not match the source size/hash')
                partial = destination / partial_name
                payloads = {}
                total = 0
                with gzip.open(partial, 'rb') as compressed:
                    with tarfile.open(fileobj=compressed, mode='r|') as archive:
                        for member in archive:
                            if (member.name not in SOURCES and member.name != 'manifest.json') or member.name in payloads:
                                raise ValueError('unexpected or duplicate archive member')
                            bound = MAX_MANIFEST if member.name == 'manifest.json' else MAX_FILE
                            if not member.isfile() or not 0 < member.size <= bound:
                                raise ValueError('archive member is not a bounded regular file')
                            total += member.size
                            if total > MAX_PAYLOAD + MAX_MANIFEST:
                                raise ValueError('uncompressed source size exceeds the fixed bound')
                            data = archive.extractfile(member).read(bound + 1)
                            if len(data) != member.size:
                                raise ValueError('short or overlong archive member')
                            payloads[member.name] = data
                    # Check the gzip footer even when tar stops at its end blocks.
                    trailer_bytes = 0
                    while block := compressed.read(CHUNK):
                        trailer_bytes += len(block)
                        if trailer_bytes > CHUNK:
                            raise ValueError('excess data after the tar end marker')
                if set(payloads) != set(SOURCES) | {'manifest.json'}:
                    raise ValueError('missing archive member')
                manifest_data = payloads.pop('manifest.json')
                if sha(manifest_data) != args.expected_manifest_sha256:
                    raise ValueError('source manifest hash mismatch')
                manifest = json.loads(manifest_data)
                records = manifest.get('files', [])
                if (manifest.get('status') != 'verified_fixed_vendor_capture' or
                        manifest.get('source_open_mode') != 'O_RDONLY|O_NOFOLLOW' or
                        manifest.get('collector_sha256') != result['receiver_sha256'] or
                        manifest.get('file_count') != len(SOURCES) or
                        manifest.get('source_recheck_match') is not True or
                        len(records) != len(SOURCES) or
                        {row.get('archive_path') for row in records} != set(SOURCES)):
                    raise ValueError('source manifest contract mismatch')
                for row in records:
                    name = row['archive_path']
                    if (row.get('source_path') != '/' + name or row.get('group') != SOURCES[name] or
                            row.get('size_bytes') != len(payloads[name]) or row.get('sha256') != sha(payloads[name]) or
                            row.get('regular_file') is not True or row.get('symlink') is not False or
                            row.get('source_recheck_match') is not True):
                        raise ValueError('source/received firmware mismatch: ' + name)
                if manifest.get('total_payload_bytes') != sum(map(len, payloads.values())):
                    raise ValueError('manifest payload total mismatch')
                layouts = {}
                for name in payloads:
                    if name.endswith('.mdt') or name.endswith('/a650_zap.elf'):
                        try:
                            layouts[name] = inspect_mdt(name, payloads)
                        except (ValueError, struct.error) as error:
                            layouts[name] = {'loader_file_set_complete': False,
                                             'structural_error': str(error),
                                             'scope': 'No load or authentication attempted'}
                with partial.open('rb') as stored:
                    stored_sha = hashlib.file_digest(stored, 'sha256').hexdigest()
                if stored_sha != args.expected_archive_sha256 or partial.stat().st_size != received:
                    raise ValueError('stored archive re-read mismatch')
                os.rename(partial_name, 'stock-firmware.tar.gz', src_dir_fd=directory, dst_dir_fd=directory)
                write_new(directory, 'manifest.json', manifest_data)
                result.update({'status': 'verified_off_device_fixed_vendor_capture',
                               'completed_utc': utc(), 'archive_file': 'stock-firmware.tar.gz',
                               'archive_bytes': received, 'archive_sha256': stored_sha,
                               'source_manifest_sha256': sha(manifest_data),
                               'source_manifest': manifest, 'file_count': len(payloads),
                               'total_payload_bytes': sum(map(len, payloads.values())),
                               'off_device_copy_verified': True, 'gzip_integrity_verified': True,
                               'archive_members_verified': True, 'mdt_layouts': layouts,
                               'all_inspected_loader_file_sets_complete': all(
                                   item['loader_file_set_complete'] for item in layouts.values()),
                               'private_directory_mode': oct(stat.S_IMODE(os.fstat(directory).st_mode)),
                               'private_archive_mode': oct(stat.S_IMODE((destination / 'stock-firmware.tar.gz').stat().st_mode))})
                write_new(directory, 'receipt.json', json_bytes(result))
                print(json.dumps({key: value for key, value in result.items()
                                  if key not in ('source_manifest', 'mdt_layouts')}, indent=2, sort_keys=True))
            except BaseException as error:
                result.update({'status': 'failed_retained_partial_outputs', 'completed_utc': utc(),
                               'error': {'type': type(error).__name__, 'message': str(error)[:512]}})
                write_new(directory, 'failure.json', json_bytes(result))
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    commands.add_parser('collect')
    receiving = commands.add_parser('receive')
    receiving.add_argument('--destination', type=Path, required=True)
    receiving.add_argument('--expected-archive-sha256', required=True)
    receiving.add_argument('--expected-manifest-sha256', required=True)
    receiving.add_argument('--expected-archive-bytes', type=int, required=True)
    args = parser.parse_args()
    if args.operation == 'collect':
        collect()
    else:
        receive(args)


if __name__ == '__main__':
    main()
