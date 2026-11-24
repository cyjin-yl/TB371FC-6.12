#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the observed journal PAX-order difference and rejection boundaries."""
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

import runtime_archive as archive

FIXTURES = Path(__file__).parent / 'fixtures/runtime-pax-order'
ZERO_END = bytes(1024)


def pax(key, value):
    tail = b' ' + key + b'=' + value + b'\n'
    length = len(tail) + 1
    while len(str(length).encode() + tail) != length:
        length = len(str(length).encode() + tail)
    return str(length).encode() + tail


def member(name, body=b'', kind=tarfile.REGTYPE):
    info = tarfile.TarInfo(name)
    info.type, info.size, info.mode, info.mtime = kind, len(body), 0o600, 123
    return info.tobuf(format=tarfile.USTAR_FORMAT) + body + bytes((-len(body)) % 512)


def sample(records, data=b'ordinary body\x00\n=value'):
    return member('PaxHeaders/item', b''.join(records), tarfile.XHDTYPE) + member('item', data) + ZERO_END


def fingerprint(data):
    return archive.fingerprint(io.BytesIO(data), maximum_bytes=max(len(data), 1))


def update_header(block, offset, value):
    result = bytearray(block)
    result[offset:offset + len(value)] = value
    result[148:156] = b'        '
    result[148:156] = ('%06o\0 ' % sum(result)).encode()
    return bytes(result)


class RuntimeArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        index = json.loads((FIXTURES / 'index.json').read_text())
        for item in index['files']:
            raw = (FIXTURES / item['path']).read_bytes()
            if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
                raise ValueError('actual fixture identity changed: ' + item['path'])
        cls.source = (FIXTURES / 'journal-source.tar').read_bytes()
        cls.target = (FIXTURES / 'journal-target.tar').read_bytes()
        cls.expected = index['normalized_sha256']

    def test_actual_journal_order_difference_only(self):
        source, target = fingerprint(self.source), fingerprint(self.target)
        self.assertNotEqual(source['raw_sha256'], target['raw_sha256'])
        self.assertEqual(source['normalized_sha256'], self.expected)
        self.assertEqual(target['normalized_sha256'], self.expected)
        self.assertEqual((source['bytes'], target['bytes']), (10240, 10240))
        self.assertEqual(source['pax_keywords'], target['pax_keywords'])
        self.assertIn('SCHILY.xattr.system.posix_acl_access', source['pax_keywords'])
        self.assertIn('SCHILY.xattr.system.posix_acl_default', source['pax_keywords'])

    def test_actual_acl_value_change_and_loss_do_not_match(self):
        size = int(self.source[124:136].strip(b'\0 '), 8)
        records = archive.pax_records(self.source[512:512 + size])
        key = b'SCHILY.xattr.system.posix_acl_access'
        selected = next(raw for name, raw in records if name == key)
        position = selected.index(b'=') + 1
        changed = selected[:position] + bytes([selected[position] ^ 1]) + selected[position + 1:]
        changed_payload = b''.join(changed if name == key else raw for name, raw in records)
        altered = self.source[:512] + changed_payload + self.source[512 + size:]
        self.assertNotEqual(fingerprint(altered)['normalized_sha256'], self.expected)
        kept = b''.join(raw for name, raw in records if name != key)
        header = update_header(self.source[:512], 124, ('%011o\0' % len(kept)).encode())
        remainder = self.source[512 + size + (-size) % 512:]
        removed = header + kept + bytes((-len(kept)) % 512) + remainder
        self.assertNotEqual(fingerprint(removed)['normalized_sha256'], self.expected)

    def test_binary_value_and_complete_record_bytes_survive_sorting(self):
        first = pax(b'SCHILY.xattr.user.binary', b'\x00one\ntwo=three\xff\x00')
        second = pax(b'mtime', b'123.000000001')
        a, b = sample([first, second]), sample([second, first])
        self.assertEqual(fingerprint(a)['normalized_sha256'], fingerprint(b)['normalized_sha256'])
        self.assertNotEqual(fingerprint(a)['raw_sha256'], fingerprint(b)['raw_sha256'])
        self.assertEqual(archive.pax_records(first)[0], (b'SCHILY.xattr.user.binary', first))

    def test_body_headers_and_padding_are_not_normalized(self):
        records = [pax(b'mtime', b'123')]
        fake = member('fake-pax', pax(b'size', b'999'), tarfile.XHDTYPE)
        original = sample(records, fake)
        changed_body = sample(records, fake[:-1] + b'X')
        self.assertNotEqual(fingerprint(original)['normalized_sha256'], fingerprint(changed_body)['normalized_sha256'])
        plain = sample(records, b'x')
        member_offset = 1024
        changed_header = plain[:member_offset] + update_header(plain[member_offset:member_offset + 512], 100, b'0000644\0') + plain[member_offset + 512:]
        self.assertNotEqual(fingerprint(plain)['normalized_sha256'], fingerprint(changed_header)['normalized_sha256'])
        changed_padding = bytearray(plain)
        changed_padding[member_offset + 513] = 1
        self.assertNotEqual(fingerprint(plain)['normalized_sha256'], fingerprint(bytes(changed_padding))['normalized_sha256'])
        self.assertNotEqual(fingerprint(plain)['normalized_sha256'], fingerprint(plain + bytes(512))['normalized_sha256'])

    def test_duplicate_keywords_rejected_even_with_identical_values(self):
        for kind in (tarfile.XHDTYPE, tarfile.XGLTYPE):
            with self.subTest(kind=kind):
                data = member('PaxHeaders/item', pax(b'mtime', b'1') * 2, kind) + member('item') + ZERO_END
                with self.assertRaisesRegex(ValueError, 'duplicate'):
                    fingerprint(data)

    def test_repeated_keys_in_distinct_headers_are_not_deduplicated(self):
        one = member('PaxHeaders/one', pax(b'mtime', b'1'), tarfile.XHDTYPE) + member('one')
        two = member('PaxHeaders/two', pax(b'mtime', b'2'), tarfile.XHDTYPE) + member('two')
        self.assertEqual(fingerprint(one + two + ZERO_END)['pax_headers'], 2)
        global_record = member('Global', pax(b'comment', b'global'), tarfile.XGLTYPE)
        self.assertEqual(fingerprint(global_record + one + ZERO_END)['pax_headers'], 2)

    def test_invalid_record_framing_rejected(self):
        invalid = [b'0 a=b\n', b'x a=b\n', b'100 a=b\n', b'8 a=b\n', b'6 =x\n',
                   pax(b'mtime', b'1')[:-1] + b'X', pax(b'bad\x00key', b'value'),
                   pax(b'mtime', b'1') + b'junk']
        for raw in invalid:
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    fingerprint(sample([raw]))

    def test_size_overrides_and_sparse_formats_rejected(self):
        forbidden = [(b'size', b'0'), (b'GNU.sparse.major', b'1'),
                     (b'GNU.sparse.map', b'0,4096'), (b'SCHILY.realsize', b'4096'),
                     (b'SCHILY.filetype', b'sparse'), (b'SUN.holesdata', b'0 4096')]
        for key, value in forbidden:
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    fingerprint(sample([pax(key, value)]))
        with self.assertRaises(ValueError):
            fingerprint(member('sparse', kind=b'S') + ZERO_END)

    def test_header_checksum_and_unsupported_framing_rejected(self):
        data = member('item', b'body') + ZERO_END
        corrupt = bytearray(data)
        corrupt[0] ^= 1
        with self.assertRaisesRegex(ValueError, 'checksum'):
            fingerprint(bytes(corrupt))
        binary_size = update_header(data[:512], 124, b'\x80' + bytes(11)) + data[512:]
        with self.assertRaisesRegex(ValueError, 'octal'):
            fingerprint(binary_size)
        for kind in (tarfile.DIRTYPE, tarfile.LNKTYPE, tarfile.SYMTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE):
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ValueError, 'non-regular'):
                    fingerprint(member('invalid', b'body', kind) + ZERO_END)

    def test_truncation_end_marker_tail_and_byte_bound_rejected(self):
        data = member('item', b'body') + ZERO_END
        invalid = [data[:700], data[:-512], data + b'\0', data + b'X' * 512, data[:-1]]
        for raw in invalid:
            with self.subTest(length=len(raw)):
                with self.assertRaises(ValueError):
                    fingerprint(raw)
        with self.assertRaisesRegex(ValueError, 'bound'):
            archive.fingerprint(io.BytesIO(data), maximum_bytes=len(data) - 1)

    def test_reference_raw_pin_is_mandatory(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            path = base / 'actual-journal.tar'
            path.write_bytes(self.source)
            reference = archive.reference_archive(path, base / 'reference.stderr',
                expected_bytes=len(self.source), expected_sha256=hashlib.sha256(self.source).hexdigest())
            archive.require_same_reference(fingerprint(self.target), reference)
            with self.assertRaisesRegex(ValueError, 'frozen raw'):
                archive.reference_archive(path, base / 'wrong-raw.stderr',
                    expected_bytes=len(self.source), expected_sha256='0' * 64)
            with self.assertRaisesRegex(ValueError, 'raw-pinned'):
                archive.require_same_reference(fingerprint(self.target), fingerprint(self.source))


if __name__ == '__main__':
    unittest.main()
