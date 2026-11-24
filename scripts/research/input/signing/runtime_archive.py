#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Hash a restricted POSIX tar, sorting only unique records inside PAX headers.

This is not a tar extractor or a general semantic archive comparison. Every
original byte is hashed, except that complete original PAX records within one
local/global extended header are ordered by their unique raw keyword bytes.
No header, value, record length, body, padding, or archive member is rewritten.
Unsupported framing (including size overrides and sparse formats) is rejected.
"""
from __future__ import annotations

import hashlib
import os
import signal
import stat
import subprocess

BLOCK = 512
CHUNK = 1024 * 1024
MAX_PAX_BYTES = 1024 * 1024
NORMALIZATION = 'unique-pax-record-order-v1'
TYPES = {b'\0', b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'x', b'g'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def octal(field, label):
    value = field.strip(b'\0 ')
    require(value and all(48 <= byte <= 55 for byte in value),
            'unsupported or invalid octal tar ' + label)
    return int(value, 8)


def pax_records(payload):
    """Return (keyword, original record) pairs without decoding binary values."""
    require(0 < len(payload) <= MAX_PAX_BYTES, 'unsupported PAX payload size')
    records, keys, offset = [], set(), 0
    while offset < len(payload):
        space = payload.find(b' ', offset, min(offset + 13, len(payload)))
        require(space > offset, 'invalid PAX length prefix')
        digits = payload[offset:space]
        require(all(48 <= byte <= 57 for byte in digits) and digits[:1] != b'0',
                'invalid PAX decimal length')
        length = int(digits)
        end = offset + length
        require(length >= len(digits) + 4 and end <= len(payload), 'invalid PAX record length')
        record = payload[offset:end]
        require(record[-1:] == b'\n', 'PAX record lacks its final newline')
        equals = payload.find(b'=', space + 1, end - 1)
        require(equals > space + 1, 'PAX record lacks a nonempty keyword')
        key = payload[space + 1:equals]
        # Canonical GNU runtime keys are printable ASCII. Reject unsupported
        # keyword encodings/control bytes rather than alias C-string keys.
        require(all(33 <= byte <= 126 for byte in key), 'unsupported PAX keyword bytes')
        require(key not in keys, 'duplicate PAX keyword')
        require(key != b'size', 'PAX size override is unsupported')
        value = payload[equals + 1:end - 1]
        require(not key.startswith(b'GNU.sparse') and key not in (b'SCHILY.realsize', b'SUN.holesdata')
                and not (key == b'SCHILY.filetype' and value == b'sparse'),
                'sparse PAX representation is unsupported')
        keys.add(key)
        records.append((key, record))
        offset = end
    require(offset == len(payload), 'PAX records do not cover their payload')
    return records


class Reader:
    def __init__(self, source, maximum):
        require(isinstance(maximum, int) and maximum > 0, 'positive archive byte bound required')
        self.source, self.maximum = source, maximum
        self.bytes = 0
        self.raw = hashlib.sha256()

    def read(self, size):
        data = self.source.read(size)
        require(isinstance(data, bytes), 'binary blocking stream required')
        self.bytes += len(data)
        require(self.bytes <= self.maximum, 'archive byte bound exceeded')
        self.raw.update(data)
        return data

    def exact(self, size):
        parts, received = [], 0
        while received < size:
            part = self.read(size - received)
            require(part, 'truncated tar stream')
            parts.append(part)
            received += len(part)
        return b''.join(parts)


def fingerprint(source, *, maximum_bytes):
    """Return raw and order-normalized digests, preserving physical tar framing."""
    reader, normalized = Reader(source, maximum_bytes), hashlib.sha256()
    record = {'normalization': NORMALIZATION, 'tar_headers': 0, 'pax_headers': 0,
              'pax_records': 0, 'reordered_pax_headers': 0, 'reordered_pax_records': 0,
              'max_pax_payload_bytes': 0, 'header_types': {}}
    keys = set()
    pending_local = False
    while True:
        header = reader.exact(BLOCK)
        normalized.update(header)
        if header == bytes(BLOCK):
            require(not pending_local, 'orphan local PAX header')
            zero_bytes = BLOCK
            while data := reader.read(CHUNK):
                require(not any(data), 'nonzero data after tar end marker')
                normalized.update(data)
                zero_bytes += len(data)
            require(zero_bytes >= 2 * BLOCK and zero_bytes % BLOCK == 0,
                    'two complete tar end blocks and aligned tail required')
            break
        require(header[257:263] == b'ustar\0' and header[263:265] == b'00',
                'only POSIX ustar/PAX headers are supported')
        checksum = octal(header[148:156], 'checksum')
        require(checksum == sum(header[:148]) + 8 * 32 + sum(header[156:]),
                'tar header checksum mismatch')
        size, kind = octal(header[124:136], 'size'), header[156:157]
        require(kind in TYPES, 'unsupported tar member type, including old GNU sparse')
        if kind in (b'1', b'2', b'3', b'4', b'5', b'6'):
            require(size == 0, 'body on a non-regular tar member is unsupported')
        record['tar_headers'] += 1
        label = kind.decode('ascii') if kind != b'\0' else 'NUL'
        record['header_types'][label] = record['header_types'].get(label, 0) + 1
        if kind in (b'x', b'g'):
            require(not pending_local, 'consecutive or interrupted local PAX headers unsupported')
            require(0 < size <= MAX_PAX_BYTES, 'unsupported PAX payload size')
            payload = reader.exact(size)
            records = pax_records(payload)
            ordered = sorted(records, key=lambda item: item[0])
            normalized.update(b''.join(item[1] for item in ordered))
            normalized.update(reader.exact((-size) % BLOCK))
            changed = sum(a[0] != b[0] for a, b in zip(records, ordered))
            record['pax_headers'] += 1
            record['pax_records'] += len(records)
            record['reordered_pax_headers'] += bool(changed)
            record['reordered_pax_records'] += changed
            record['max_pax_payload_bytes'] = max(record['max_pax_payload_bytes'], size)
            keys.update(item[0] for item in records)
            pending_local = kind == b'x'
        else:
            pending_local = False
            remaining = size + (-size) % BLOCK
            while remaining:
                data = reader.exact(min(CHUNK, remaining))
                normalized.update(data)
                remaining -= len(data)
    record.update(bytes=reader.bytes, raw_sha256=reader.raw.hexdigest(),
                  normalized_sha256=normalized.hexdigest(), pax_keywords=sorted(key.decode('ascii') for key in keys))
    return record


def command_fingerprint(argv, log, *, maximum_bytes):
    """Drain one bounded owned process; terminate/reap it on parser rejection."""
    child = None
    try:
        with log.open('xb') as error:
            child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=error, start_new_session=True)
            result = fingerprint(child.stdout, maximum_bytes=maximum_bytes)
            code = child.wait(timeout=20)
        result.update(argv=argv, exit_code=code, stderr_bytes=log.stat().st_size)
        require(code == 0 and result['stderr_bytes'] == 0, 'archive reader failed or emitted diagnostics')
        return result
    finally:
        if child is not None:
            if child.poll() is None:
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=10)
            if child.stdout is not None:
                child.stdout.close()


def reference_archive(path, log, *, expected_bytes, expected_sha256):
    """Pin the entire original archive before using any normalized identity."""
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size == expected_bytes,
            'ordinary reference archive with exact frozen length required')
    argv = ['timeout', '--signal=TERM', '--kill-after=10s', '1800s', 'cat', '--', str(path)]
    result = command_fingerprint(argv, log, maximum_bytes=expected_bytes)
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode),
            'reference archive changed while reading')
    require(result['bytes'] == expected_bytes and result['raw_sha256'] == expected_sha256,
            'reference archive differs from frozen raw bytes')
    result['identity'] = {'bytes': expected_bytes, 'sha256': result['raw_sha256'],
                          'mode': stat.S_IMODE(after.st_mode)}
    result['path'] = str(path)
    result['raw_frozen_identity_verified'] = True
    return result


def canonical_tree(tree, log, *, maximum_bytes):
    """Use the unchanged canonical tar flags and original 1800-second budget."""
    require(stat.S_ISDIR(tree.lstat().st_mode), 'ordinary runtime tree required')
    argv = ['timeout', '--signal=TERM', '--kill-after=10s', '1800s',
            'tar', '--sort=name', '--format=posix',
            '--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime',
            '--numeric-owner', '--acls', '--selinux', '--xattrs', '--xattrs-include=*',
            '-cf', '-', '-C', str(tree), '.']
    return command_fingerprint(argv, log, maximum_bytes=maximum_bytes)


def require_same_reference(observed, reference):
    require(reference.get('raw_frozen_identity_verified') is True,
            'raw-pinned reference archive required')
    require(observed['normalization'] == reference['normalization'] == NORMALIZATION and
            (observed['bytes'], observed['normalized_sha256']) ==
            (reference['bytes'], reference['normalized_sha256']),
            'runtime differs from the raw-pinned reference beyond unique PAX record order')
