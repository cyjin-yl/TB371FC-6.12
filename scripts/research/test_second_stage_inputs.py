#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Input-binding tests; tiny synthetic bundles never claim a real R5 boot."""
from contextlib import ExitStack
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import second_stage_inputs as inputs
from qualify_boot_bundle import fingerprint
from test_boot_bundle import fixture_bundle


def identity(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def fixed_manifest(root):
    """Only structural validation: these private payload files are absent."""
    return {
        'schema_version': 1,
        'release': inputs.RELEASE,
        'kernel_bundle': str(root / 'bundle'),
        'kernel_load_base': 0xa0000000,
        'bootargs': ' '.join(k + '=' + v for k, v in inputs.REQUIRED_ARGS.items()),
        'files': {
            **{name: {'path': str(root / name), 'bytes': size, 'sha256': digest}
               for name, (size, digest) in inputs.FIXED.items()},
            'qemu': {'path': str(root / 'qemu'), 'bytes': 128, 'sha256': 'a' * 64},
        },
    }


class FileBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'payload'
        self.path.write_bytes(b'known payload\n')

    def test_stable_bytes_are_hashed_and_optional_capture_is_exact(self):
        expected = identity(self.path)
        actual, stamp, raw = inputs.read_file(self.path, expected=expected, capture=True)
        self.assertEqual(actual, expected)
        self.assertEqual(stamp, fingerprint(self.path.stat()))
        self.assertEqual(raw, b'known payload\n')
        self.assertIsNone(inputs.read_file(self.path)[2])

    def test_same_size_corruption_and_wrong_size_fail_separately(self):
        expected = identity(self.path)
        self.path.write_bytes(b'KNOWN payload\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            inputs.read_file(self.path, expected=expected)
        expected['bytes'] += 1
        with self.assertRaisesRegex(ValueError, 'size mismatch'):
            inputs.read_file(self.path, expected=expected)

    def test_zero_length_and_upper_bound_are_rejected_before_capture(self):
        with self.assertRaisesRegex(ValueError, 'bounded ordinary'):
            inputs.read_file(self.path, maximum=self.path.stat().st_size - 1)
        self.path.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'bounded ordinary'):
            inputs.read_file(self.path)

    def test_fifo_directory_and_symlink_cannot_be_read_as_payloads(self):
        fifo = self.root / 'fifo'
        os.mkfifo(fifo)
        for path in (fifo, self.root):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'bounded ordinary'):
                inputs.read_file(path)
        alias = self.root / 'alias'
        alias.symlink_to(self.path)
        with self.assertRaises(OSError):
            inputs.read_file(alias)

    def test_parent_symlink_and_noncanonical_paths_are_rejected(self):
        target = self.root / 'dir'
        target.mkdir()
        (target / 'payload').write_bytes(b'known')
        alias = self.root / 'alias'
        alias.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'ancestor'):
            inputs.read_file(alias / 'payload')
        values = ['relative', str(self.root) + '/./payload',
                  str(self.root) + '/dir/../payload', str(self.root) + '//payload',
                  str(self.path) + '/', str(self.root / 'comma,payload'),
                  str(self.root / 'newline\npayload')]
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                inputs.checked_path(value)

    def mutate_while_hashing(self, mutation, message, **kwargs):
        real_sha256 = hashlib.sha256
        class MutatingDigest:
            def __init__(self):
                self.digest = real_sha256()
                self.mutated = False
            def update(self, chunk):
                if not self.mutated:
                    self.mutated = True
                    mutation()
                self.digest.update(chunk)
            def hexdigest(self):
                return self.digest.hexdigest()
        with patch.object(inputs.hashlib, 'sha256', MutatingDigest):
            with self.assertRaisesRegex(ValueError, message):
                inputs.read_file(self.path, **kwargs)

    def test_replacement_during_read_is_detected_even_for_identical_bytes(self):
        original = self.path.read_bytes()
        def replace():
            replacement = self.root / 'replacement'
            replacement.write_bytes(original)
            os.replace(replacement, self.path)
        self.mutate_while_hashing(replace, 'changed during read')

    def test_growth_during_read_is_bounded(self):
        maximum = self.path.stat().st_size
        def grow():
            with self.path.open('ab') as stream:
                stream.write(b'extra')
        self.mutate_while_hashing(grow, 'grew while reading', maximum=maximum)

    def test_metadata_change_during_read_is_detected(self):
        self.path.chmod(0o600)
        self.mutate_while_hashing(lambda: self.path.chmod(0o640), 'changed during read')


class ManifestBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = fixed_manifest(self.root)

    def test_complete_frozen_manifest_is_structurally_valid(self):
        self.assertIs(inputs.validate_manifest(self.manifest), self.manifest)
        # Validation does not pretend missing private payloads were read.
        self.assertFalse((self.root / 'kernel').exists())

    def test_published_contract_and_kernel_artifact_bindings_match(self):
        raw = inputs.CONTRACT.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), inputs.CONTRACT_SHA256)
        contract = json.loads(raw)
        self.assertEqual(contract['kernel']['release'], inputs.RELEASE)
        files = {item['path']: item for item in contract['kernel_files']}
        for name, artifact in [('kernel', 'image'), ('config', 'config'),
                               ('certificate', 'certificate')]:
            item = files[contract['kernel']['artifacts'][artifact]]
            self.assertEqual(inputs.FIXED[name], (item['bytes'], item['sha256']))

    def test_each_frozen_artifact_size_and_hash_are_mandatory(self):
        for name in inputs.FIXED:
            for field in ('bytes', 'sha256'):
                altered = copy.deepcopy(self.manifest)
                item = altered['files'][name]
                item[field] = item[field] + 1 if field == 'bytes' else '0' * 64
                with self.subTest(name=name, field=field):
                    with self.assertRaisesRegex(ValueError, 'frozen completed R5'):
                        inputs.validate_manifest(altered)

    def test_missing_extra_and_invalid_identity_fields_fail(self):
        cases = []
        missing = copy.deepcopy(self.manifest)
        del missing['files']['rootfs']
        cases.append(missing)
        extra = copy.deepcopy(self.manifest)
        extra['files']['other'] = copy.deepcopy(extra['files']['qemu'])
        cases.append(extra)
        foreign_release = copy.deepcopy(self.manifest)
        foreign_release['release'] = '6.12.114-other-kernel'
        cases.append(foreign_release)
        unknown = copy.deepcopy(self.manifest)
        unknown['physical_boot_verified'] = True
        cases.append(unknown)
        for value in (True, 128.0, 0, -1, inputs.MAX_FILE + 1):
            altered = copy.deepcopy(self.manifest)
            altered['files']['qemu']['bytes'] = value
            cases.append(altered)
        for value in ('A' * 64, 'a' * 63, None):
            altered = copy.deepcopy(self.manifest)
            altered['files']['qemu']['sha256'] = value
            cases.append(altered)
        extra_identity = copy.deepcopy(self.manifest)
        extra_identity['files']['qemu']['approved'] = True
        cases.append(extra_identity)
        for index, value in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                inputs.validate_manifest(value)

    def test_schema_and_load_addresses_require_exact_bounded_integers(self):
        for value in (True, 1.0, 2):
            altered = copy.deepcopy(self.manifest)
            altered['schema_version'] = value
            with self.subTest(schema=value), self.assertRaisesRegex(ValueError, 'schema'):
                inputs.validate_manifest(altered)
        for value in (True, float(0xa0000000), 0x7fe00000, 0x280000000,
                      0xbbc00000, 0xa0000001):
            altered = copy.deepcopy(self.manifest)
            altered['kernel_load_base'] = value
            with self.subTest(load=value), self.assertRaisesRegex(ValueError, 'load base'):
                inputs.validate_manifest(altered)

    def test_duplicate_json_keys_are_rejected_at_every_depth(self):
        for raw in ('{"release":1,"release":2}',
                    '{"files":{"kernel":{"bytes":1,"bytes":2}}}'):
            with self.subTest(raw=raw), self.assertRaisesRegex(ValueError, 'duplicate JSON'):
                json.loads(raw, object_pairs_hook=inputs.unique_object)

    def test_required_boot_arguments_cannot_be_missing_duplicated_or_overridden(self):
        for key, value in inputs.REQUIRED_ARGS.items():
            token = key + '=' + value
            cases = [self.manifest['bootargs'].replace(token, ''),
                     self.manifest['bootargs'] + ' ' + token,
                     self.manifest['bootargs'].replace(token, key + '=0')]
            for args in cases:
                altered = copy.deepcopy(self.manifest)
                altered['bootargs'] = args
                with self.subTest(key=key, args=args):
                    with self.assertRaisesRegex(ValueError, 'missing or conflicting'):
                        inputs.validate_manifest(altered)

    def test_parameter_alias_delimiter_and_unsafe_handoff_overrides_fail(self):
        suffixes = ['module.sig-enforce=0', '-- module.sig_enforce=0',
                    'init=/bin/sh', 'selinux=0', 'mem=16M', 'memmap=16M@0',
                    'efi=debug', 'acpi=force', 'dtb=other', 'fdt=other']
        for suffix in suffixes:
            altered = copy.deepcopy(self.manifest)
            altered['bootargs'] += ' ' + suffix
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                inputs.validate_manifest(altered)
        for suffix in [' "quoted"', " 'quoted'", '\nconsole=ttyS0']:
            altered = copy.deepcopy(self.manifest)
            altered['bootargs'] += suffix
            with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError, 'syntax'):
                inputs.validate_manifest(altered)


class QualifiedInputTests(unittest.TestCase):
    """Exercise real reads/qualifier with explicitly synthetic pinned inputs."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bundle = self.root / 'bundle'
        self.bundle.mkdir()
        contract = fixture_bundle(self.bundle)
        self.contract = self.root / 'contract.json'
        self.contract.write_text(json.dumps(contract))
        contract_hash = identity(self.contract)['sha256']
        paths = {
            'kernel': self.bundle / contract['kernel']['artifacts']['image'],
            'config': self.bundle / contract['kernel']['artifacts']['config'],
            'certificate': self.bundle / contract['kernel']['artifacts']['certificate'],
            'dtb': self.bundle / contract['kernel']['artifacts']['dtb'],
        }
        for name, data in [('initrd', b'synthetic-initrd'), ('rootfs', b'synthetic-rootfs'),
                           ('qemu', b'synthetic-executable-never-launched')]:
            paths[name] = self.root / name
            paths[name].write_bytes(data)
        paths['qemu'].chmod(0o700)
        self.paths = paths
        self.manifest = fixed_manifest(self.root)
        self.manifest['release'] = contract['kernel']['release']
        self.manifest['files'] = {name: identity(path) for name, path in paths.items()}
        self.manifest_path = self.root / 'manifest.json'
        self.manifest_path.write_text(json.dumps(self.manifest))
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        fixture_pins = {name: (item['bytes'], item['sha256'])
                        for name, item in self.manifest['files'].items() if name != 'qemu'}
        self.stack.enter_context(patch.object(inputs, 'FIXED', fixture_pins))
        self.stack.enter_context(patch.object(inputs, 'RELEASE', contract['kernel']['release']))
        self.stack.enter_context(patch.object(inputs, 'CONTRACT', self.contract))
        self.stack.enter_context(patch.object(inputs, 'CONTRACT_SHA256', contract_hash))

    def test_real_fixture_qualification_captures_evidence_without_native_claim(self):
        report = inputs.verify_inputs(self.manifest_path)
        self.assertEqual(report['kernel_bundle_qualification']['status'], 'verified')
        self.assertEqual(report['identities'], self.manifest['files'])
        self.assertEqual(report['raw']['kernel'], self.paths['kernel'].read_bytes())
        self.assertNotIn('rootfs', report['raw'])
        self.assertNotIn('qemu', report['raw'])
        self.assertFalse(report['evidence_bindings']['physical_boot_verified'])
        self.assertFalse(report['evidence_bindings']['module_signatures_reexecuted'])
        inputs.verify_unchanged(report)

    def test_contract_tampering_is_rejected_before_bundle_qualification(self):
        self.contract.write_text(self.contract.read_text() + '\n')
        with patch.object(inputs, 'qualify_kernel') as qualifier:
            with self.assertRaisesRegex(ValueError, 'contract differs'):
                inputs.verify_inputs(self.manifest_path)
            qualifier.assert_not_called()

    def test_payload_byte_mismatch_is_rejected_even_with_valid_manifest(self):
        raw = self.paths['initrd'].read_bytes()
        self.paths['initrd'].write_bytes(b'X' + raw[1:])
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            inputs.verify_inputs(self.manifest_path)

    def test_copied_kernel_cannot_diverge_from_the_qualified_bundle(self):
        # Separate launch copy: both its declared hash and bytes agree, while
        # the unchanged bundle is independently qualified against its contract.
        copied = self.root / 'launch-Image'
        raw = self.paths['kernel'].read_bytes()
        copied.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        self.manifest['files']['kernel'] = identity(copied)
        self.manifest_path.write_text(json.dumps(self.manifest))
        altered_pins = dict(inputs.FIXED)
        altered_pins['kernel'] = (copied.stat().st_size, identity(copied)['sha256'])
        with patch.object(inputs, 'FIXED', altered_pins):
            with self.assertRaisesRegex(ValueError, 'differs from qualified kernel bundle'):
                inputs.verify_inputs(self.manifest_path)

    def test_bundle_change_after_qualifier_success_is_detected(self):
        real_qualify = inputs.qualify_kernel
        def qualify_then_change(root, contract):
            result = real_qualify(root, contract)
            self.assertEqual(result['status'], 'verified')
            next(self.bundle.rglob('*.ko')).chmod(0o600)
            return result
        with patch.object(inputs, 'qualify_kernel', qualify_then_change):
            with self.assertRaisesRegex(ValueError, 'bundle changed during qualification'):
                inputs.verify_inputs(self.manifest_path)

    def test_module_mutation_fails_actual_bundle_qualification(self):
        module = next(self.bundle.rglob('*.ko'))
        raw = module.read_bytes()
        module.write_bytes(b'X' + raw[1:])
        with self.assertRaisesRegex(ValueError, 'bundle qualification failed'):
            inputs.verify_inputs(self.manifest_path)

    def test_binary_must_be_executable(self):
        self.paths['qemu'].chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'QEMU is not executable'):
            inputs.verify_inputs(self.manifest_path)

    def test_equal_content_replacement_invalidates_pre_cont_stamp(self):
        report = inputs.verify_inputs(self.manifest_path)
        replacement = self.root / 'replacement-rootfs'
        replacement.write_bytes(self.paths['rootfs'].read_bytes())
        os.replace(replacement, self.paths['rootfs'])
        with self.assertRaisesRegex(ValueError, 'changed since qualification'):
            inputs.verify_unchanged(report)

    def test_pre_cont_check_rejects_new_module_and_manifest_edit(self):
        report = inputs.verify_inputs(self.manifest_path)
        extra = self.bundle / 'unexpected.ko'
        extra.write_bytes(b'new module')
        with self.assertRaisesRegex(ValueError, 'bundle changed since qualification'):
            inputs.verify_unchanged(report)
        # Use a new qualified snapshot: removing the extra file does not restore
        # directory timestamps and must not be treated as undoing qualification.
        extra.unlink()
        report = inputs.verify_inputs(self.manifest_path)
        self.manifest_path.write_text(self.manifest_path.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'changed since qualification'):
            inputs.verify_unchanged(report)


if __name__ == '__main__':
    unittest.main()
