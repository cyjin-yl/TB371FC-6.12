#!/usr/bin/env python3
"""Read-only verifier for this project's early-newc + gzip-newc ARM64 image.

This deliberately supports the current 512-byte empty early archive, one gzip
member, and GNU newc with 512-byte final padding. It does not extract anything,
execute an image, repair input, or substitute files from a retained directory.
The Fedora ARM cache and 69-file firmware manifest are fixed experiment inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import zlib

MAX_ARCHIVE = 128 * 1024**2
MAX_EXPANDED = 512 * 1024**2
MAX_ENTRIES = 16384
EARLY_BYTES = 512
FW_MANIFEST_SHA256 = '4feb4264605198fc56114fb8b8044ffcd51f662107270a857f59fdaf2e8bcf7c'
CACHE_SHA256 = '4db2c927ed3e93a02b5bdee416ed121c5cca944223634e09884edc85c47a5452'
HOOK = 'var/lib/dracut/hooks/pre-pivot/50-selinux-loadpolicy.sh'
HOOK_SHA256 = '8fe83554141667c99eda1fa3a96ce621cdea09feae2c2f3617074d8548b28e45'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum,
                'input is not a nonempty, bounded regular file: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(fd)
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                 before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size,
                                        after.st_mtime_ns, after.st_ctime_ns),
                'input changed during read')
        require(len(data) == before.st_size and len(data) <= maximum,
                'input size changed or exceeds limit')
        return data
    finally:
        os.close(fd)


def safe_name(name):
    require(name and not name.startswith('/') and '\\' not in name
            and all(ord(ch) >= 32 and ord(ch) != 127 for ch in name),
            'unsafe archive pathname')
    if name.startswith('./'):
        name = name[2:]
    if name == '.':
        return name
    require(all(part not in ('', '.', '..') for part in name.split('/')),
            'noncanonical or traversing archive pathname')
    return name


def link_destination(parent, target):
    require(target and '\\' not in target and '\0' not in target
            and all(ord(ch) >= 32 and ord(ch) != 127 for ch in target),
            'invalid symlink target')
    parts = [] if target.startswith('/') else list(parent)
    for part in target.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            require(parts, 'symlink traverses above the image root')
            parts.pop()
        else:
            parts.append(part)
    return parts


class Newc:
    def __init__(self, data, label):
        self.data = data
        self.label = label
        self.entries = {}
        self.records = 0
        self.hardlink_groups = 0
        self.hardlink_aliases = 0
        groups = defaultdict(list)
        offset = 0
        while True:
            require(offset % 4 == 0 and offset + 110 <= len(data),
                    label + ': truncated or unaligned newc header')
            header = data[offset:offset + 110]
            require(header[:6] == b'070701' and re.fullmatch(b'[0-9A-Fa-f]{104}', header[6:]),
                    label + ': expected a complete 070701 newc header')
            fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
            ino, mode, uid, gid, nlink, mtime, size, major, minor, rmajor, rminor, namesize, checksum = fields
            require(checksum == 0 and 2 <= namesize <= 4096,
                    label + ': invalid newc checksum/name size')
            name_start = offset + 110
            name_end = name_start + namesize
            require(name_end <= len(data), label + ': truncated filename')
            raw_name = data[name_start:name_end]
            require(raw_name[-1:] == b'\0' and b'\0' not in raw_name[:-1],
                    label + ': malformed filename terminator')
            payload_start = (name_end + 3) & ~3
            payload_end = payload_start + size
            next_offset = (payload_end + 3) & ~3
            require(next_offset <= len(data), label + ': payload exceeds archive')
            require(not any(data[name_end:payload_start]) and not any(data[payload_end:next_offset]),
                    label + ': nonzero newc alignment padding')
            if raw_name == b'TRAILER!!!\0':
                require(mode == 0 and size == 0, label + ': invalid newc trailer')
                padded_end = (next_offset + 511) & ~511
                require(padded_end == len(data) and not any(data[next_offset:]),
                        label + ': trailing data or incorrect 512-byte archive boundary')
                self.trailer_offset = offset
                self.padding_bytes = len(data) - next_offset
                break
            self.records += 1
            require(self.records <= MAX_ENTRIES, label + ': too many archive entries')
            name = safe_name(raw_name[:-1].decode('utf-8', errors='strict'))
            kind = {stat.S_IFREG: 'regular', stat.S_IFDIR: 'directory', stat.S_IFLNK: 'symlink',
                    stat.S_IFCHR: 'character', stat.S_IFBLK: 'block', stat.S_IFIFO: 'fifo'}.get(stat.S_IFMT(mode))
            require(kind is not None and nlink > 0, label + ': unsupported type or invalid link count')
            require(name != '.' or kind == 'directory', label + ': non-directory image root')
            require(kind in ('regular', 'symlink') or size == 0,
                    label + ': unexpected payload for a non-file node')
            require(name not in self.entries or
                    (kind == 'directory' and self.entries[name]['kind'] == 'directory'),
                    label + ': duplicate non-directory pathname: ' + name)
            entry = {'path': name, 'kind': kind, 'mode': mode, 'uid': uid, 'gid': gid,
                     'nlink': nlink, 'inode_key': (major, minor, ino),
                     'stored_size': size, 'payload_offset': payload_start, 'size': size,
                     'sha256': digest(memoryview(data)[payload_start:payload_end]),
                     'payload_source': name}
            if kind == 'symlink':
                require(0 < size <= 4096, label + ': invalid symlink size')
                entry['target'] = data[payload_start:payload_end].decode('utf-8', errors='strict')
                link_destination(name.split('/')[:-1], entry['target'])
            self.entries[name] = entry
            if kind == 'regular' and nlink > 1:
                groups[entry['inode_key']].append(entry)
            offset = next_offset

        # GNU newc emits one data-bearing member for a regular-file hardlink
        # group. Resolve only archive-local inode identities; never read disk.
        for entries in groups.values():
            self.hardlink_groups += 1
            first = entries[0]
            require(len(entries) <= first['nlink'] and all(
                (e['mode'], e['uid'], e['gid'], e['nlink']) ==
                (first['mode'], first['uid'], first['gid'], first['nlink']) for e in entries),
                label + ': inconsistent hardlink metadata')
            populated = [e for e in entries if e['stored_size']]
            require(len(populated) <= 1, label + ': multiple payloads in one hardlink group')
            source = populated[0] if populated else first
            for entry in entries:
                entry.update({key: source[key] for key in ('payload_offset', 'size', 'sha256', 'payload_source')})
                self.hardlink_aliases += entry['path'] != source['path']
        # The fixed producer lists real directories and does not traverse its
        # symlinks. Reject alias-parent entries that could overwrite another
        # archive pathname when unpacked, including links seen later in input.
        for name in self.entries:
            parts = name.split('/')
            for i in range(1, len(parts)):
                parent = self.entries.get('/'.join(parts[:i]))
                require(parent is not None and parent['kind'] == 'directory',
                        label + ': missing or non-directory pathname parent')

    def resolve(self, name):
        parts = link_destination([], name)
        for unused in range(40):
            for i in range(len(parts)):
                entry = self.entries.get('/'.join(parts[:i + 1]))
                require(entry is not None, 'required archive member is missing: ' + '/'.join(parts[:i + 1]))
                if entry['kind'] == 'symlink':
                    parts = link_destination(parts[:i], entry['target']) + parts[i + 1:]
                    break
                require(i == len(parts) - 1 or entry['kind'] == 'directory',
                        'required path crosses a non-directory')
            else:
                result = self.entries.get('/'.join(parts) or '.')
                require(result is not None, 'resolved archive member is absent')
                return result
        raise ValueError('required archive symlink chain loops or is too long')

    def regular(self, name):
        entry = self.resolve(name)
        require(entry['kind'] == 'regular', 'required member is not a regular file: ' + name)
        return entry

    def payload(self, entry):
        return memoryview(self.data)[entry['payload_offset']:entry['payload_offset'] + entry['size']]

    def summary(self):
        return {'bytes': len(self.data), 'sha256': digest(self.data), 'records': self.records,
                'unique_paths': len(self.entries), 'types': dict(Counter(e['kind'] for e in self.entries.values())),
                'trailer_offset': self.trailer_offset, 'zero_padding_bytes': self.padding_bytes,
                'hardlink_groups': self.hardlink_groups, 'hardlink_aliases': self.hardlink_aliases}


def member_record(entry):
    return {key: entry[key] for key in ('path', 'kind', 'size', 'sha256', 'payload_source')}


def arm64_elf(archive, name, require_executable=False):
    entry = archive.regular(name)
    data = archive.payload(entry)
    require(len(data) >= 64 and bytes(data[:7]) == b'\x7fELF\x02\x01\x01',
            'required userspace ELF is not ELF64 little-endian: ' + name)
    elf_type, machine, version = struct.unpack_from('<HHI', data, 16)
    require(machine == 183 and version == 1 and elf_type in (1, 2, 3),
            'non-AArch64 or unsupported ELF in runtime archive: ' + name)
    require(not require_executable or (elf_type in (2, 3) and entry['mode'] & 0o111),
            'required executable has invalid ELF type or mode: ' + name)
    phoff = struct.unpack_from('<Q', data, 32)[0]
    ehsize, phsize, phcount = struct.unpack_from('<HHH', data, 52)
    require(ehsize == 64 and phcount <= 256 and
            (phcount == 0 or (phsize == 56 and phoff + phsize * phcount <= len(data))),
            'invalid ELF program-header bounds: ' + name)
    interpreters = []
    for i in range(phcount):
        off = phoff + i * phsize
        if struct.unpack_from('<I', data, off)[0] == 3:
            start, size = struct.unpack_from('<Q', data, off + 8)[0], struct.unpack_from('<Q', data, off + 32)[0]
            require(2 <= size <= 4096 and start + size <= len(data), 'invalid ELF interpreter bounds')
            value = bytes(data[start:start + size])
            require(value.endswith(b'\0') and b'\0' not in value[:-1], 'invalid ELF interpreter string')
            path = value[:-1].decode('utf-8', errors='strict')
            interpreter = archive.regular(path)
            ident = archive.payload(interpreter)
            require(len(ident) >= 20 and bytes(ident[:7]) == b'\x7fELF\x02\x01\x01'
                    and struct.unpack_from('<H', ident, 18)[0] == 183,
                    'ELF interpreter is missing or not AArch64')
            interpreters.append(interpreter['path'])
    require(len(interpreters) <= 1, 'multiple ELF interpreter segments')
    return {**member_record(entry), 'elf_machine': machine, 'elf_type': elf_type,
            'interpreters': interpreters}


def check_cache(archive):
    entry = archive.regular('etc/ld.so.cache')
    require(entry['size'] == 1855 and entry['sha256'] == CACHE_SHA256,
            'ld.so.cache differs from the fixed Fedora ARM ldconfig output')
    data = bytes(archive.payload(entry))
    # glibc sysdeps/generic/dl-cache.h: 48-byte new header, 24-byte
    # file_entry_new; ldconfig.h: AARCH64_LIB64 0x0a00 + ELF_LIBC6 3.
    require(data[:20] == b'glibc-ld.so.cache1.1' and data[28] & 3 == 2,
            'cache is not the new little-endian glibc format')
    count, strings_size = struct.unpack_from('<II', data, 20)
    start, end = 48 + 24 * count, 48 + 24 * count + strings_size
    require(0 < count <= 256 and end <= len(data), 'invalid cache table bounds')

    def string(offset):
        require(start <= offset < end, 'cache string outside string table')
        limit = data.find(b'\0', offset, end)
        require(limit != -1 and limit - offset <= 4096, 'unterminated cache string')
        return data[offset:limit].decode('utf-8', errors='strict')

    records = []
    for i in range(count):
        flags, key, value, unused, hwcap = struct.unpack_from('<iIIIQ', data, 48 + 24 * i)
        require(flags == 0x0a03 and hwcap == 0, 'unexpected architecture/hwcap cache entry')
        soname, path = string(key), string(value)
        require('/' not in soname and path.startswith('/'), 'invalid cache library path')
        elf = arm64_elf(archive, path)
        records.append({'soname': soname, 'cache_path': path, 'resolved_path': elf['path'],
                        'sha256': elf['sha256'], 'elf_machine': elf['elf_machine']})
    require({'libc.so.6', 'libselinux.so.1', 'ld-linux-aarch64.so.1'} <= {e['soname'] for e in records},
            'cache lacks a required startup library')
    return {**member_record(entry), 'entries': records, 'architecture_flags': '0x0a03',
            'all_cached_payloads_present_and_aarch64': True}


def verify(image, manifest_path):
    result = {'schema_version': 1, 'passed': False, 'stage': 'inputs',
              'scope': 'fixed generic ARM64 initramfs archive validation only',
              'limits': {'archive_bytes': MAX_ARCHIVE, 'expanded_bytes': MAX_EXPANDED},
              'image': {'path': str(image)}, 'extracted': False, 'image_executed': False,
              'firmware_loaded': False, 'kernel_policy_load_tested': False,
              'physical_hardware_tested': False}
    try:
        raw = read_regular(image, MAX_ARCHIVE)
        result['image'].update({'bytes': len(raw), 'sha256': digest(raw)})
        manifest_bytes = read_regular(manifest_path, 1024**2)
        require(digest(manifest_bytes) == FW_MANIFEST_SHA256, 'firmware manifest does not match the fixed canonical ELF tree')
        manifest = json.loads(manifest_bytes)
        require(manifest['firmware_file_count'] == 69 and len(manifest['files']) == 69,
                'unexpected firmware manifest size')
        result['firmware_manifest'] = {'path': str(manifest_path), 'sha256': FW_MANIFEST_SHA256}

        result['stage'] = 'early-newc-order'
        require(raw[:6] == b'070701', 'image must begin with early newc, not gzip or empty data')
        early = Newc(raw[:EARLY_BYTES], 'early')
        require(set(early.entries) <= {'.'}, 'this profile requires an empty 512-byte early archive')
        result['early'] = early.summary()

        result['stage'] = 'gzip-boundary-and-integrity'
        require(raw[EARLY_BYTES:EARLY_BYTES + 2] == b'\x1f\x8b', 'gzip must start immediately at offset 512')
        compressed = memoryview(raw)[EARLY_BYTES:]
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        expanded = decoder.decompress(compressed, MAX_EXPANDED - EARLY_BYTES + 1)
        require(len(expanded) + EARLY_BYTES <= MAX_EXPANDED and not decoder.unconsumed_tail,
                'combined expanded archives exceed limit')
        require(decoder.eof, 'gzip stream is truncated')
        require(not decoder.unused_data, 'gzip stream has trailing data or a second member')
        crc, isize = struct.unpack_from('<II', compressed, len(compressed) - 8)
        require(isize == len(expanded) and crc == zlib.crc32(expanded), 'gzip CRC/size mismatch')
        result['gzip'] = {'offset': EARLY_BYTES, 'bytes': len(compressed),
                          'expanded_bytes': len(expanded),
                          'combined_expanded_bytes': len(expanded) + EARLY_BYTES, 'crc32': f'{crc:08x}',
                          'crc_and_isize_verified': True, 'trailing_bytes': 0, 'members': 1}

        result['stage'] = 'main-newc-members'
        main = Newc(expanded, 'main')
        result['main'] = main.summary()
        result['stage'] = 'firmware-payloads'
        firmware = []
        expected_paths = set()
        for expected in manifest['files']:
            original = safe_name(expected['destination'])
            require(original.startswith('lib/firmware/'), 'firmware manifest path escaped its prefix')
            name = 'usr/' + original
            require(name not in expected_paths, 'duplicate firmware manifest path')
            expected_paths.add(name)
            entry = main.regular(name)
            require(entry['path'] == name and entry['sha256'] == expected['sha256']
                    and entry['size'] == expected['size_bytes'], 'archive firmware payload mismatch: ' + name)
            firmware.append(member_record(entry))
        actual_paths = {name for name, entry in main.entries.items()
                        if name.startswith('usr/lib/firmware/') and entry['kind'] != 'directory'}
        require(actual_paths == expected_paths, 'archive firmware set is not exactly the 69 declared files')
        result['firmware'] = {'files_verified': len(firmware), 'payload_bytes': sum(e['size'] for e in firmware),
                              'source': 'archive payloads, including archive-local hardlinks', 'files': firmware}

        result['stage'] = 'critical-startup-members'
        init = main.resolve('init')
        require(init['path'] == 'usr/lib/systemd/systemd', 'init does not resolve to the expected systemd')
        systemd = arm64_elf(main, 'usr/lib/systemd/systemd', require_executable=True)
        hook = main.regular(HOOK)
        require(hook['sha256'] == HOOK_SHA256 and hook['mode'] & 0o111,
                'SELinux hook differs from the reviewed executable hook')
        first_line = bytes(main.payload(hook)[:4096]).split(b'\n', 1)[0]
        require(first_line == b'#!/usr/bin/sh', 'unexpected SELinux hook interpreter')
        shell = arm64_elf(main, '/usr/bin/sh', require_executable=True)
        result['critical_members'] = {'init_resolves_to': init['path'], 'systemd': systemd,
                                       'selinux_hook': member_record(hook), 'hook_shell': shell}
        result['stage'] = 'arm64-cache-and-elfs'
        result['ld_so_cache'] = check_cache(main)
        elfs = []
        for name, entry in main.entries.items():
            if entry['kind'] == 'regular' and not name.startswith('usr/lib/firmware/'):
                if bytes(main.payload(entry)[:4]) == b'\x7fELF':
                    elfs.append(arm64_elf(main, name))
        result['runtime_elfs'] = {'count': len(elfs), 'all_elf64_little_endian_aarch64': True,
                                   'files': elfs}
        result['stage'] = 'complete'
        result['passed'] = True
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--firmware-manifest', type=Path,
                        default=Path('/work/stock-fw-stage-v1/canonical-elf/stock-firmware-manifest.json'))
    arguments = parser.parse_args()
    outcome = verify(arguments.image, arguments.firmware_manifest)
    print(json.dumps(outcome, indent=2, sort_keys=True), flush=True)
    sys.exit(0 if outcome['passed'] else 1)
