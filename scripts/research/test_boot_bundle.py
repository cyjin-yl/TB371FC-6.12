#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Regression checks for provenance, input isolation and readiness boundaries."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

import derive_boot_candidate as derive
import qualify_boot_bundle as bundle

REPO = Path(__file__).resolve().parents[2]


def fixture_dtb():
    """An independently encoded v17 two-property tree, without dtc dependency."""
    def word(value):
        return struct.pack('>I', value)
    def padded(raw):
        return raw + b'\0' * (-len(raw) % 4)
    def prop(name_offset, raw):
        return word(3) + word(len(raw)) + word(name_offset) + padded(raw)
    strings = b'compatible\0model\0'
    tree = word(1) + b'\0' * 4
    tree += prop(0, b'lenovo,tb371fc\0qcom,sm8250\0')
    tree += prop(11, b'Synthetic qualification fixture\0')
    tree += word(2) + word(9)
    header = struct.pack('>10I', 0xd00dfeed, 56 + len(tree) + len(strings),
                         56, 56 + len(tree), 40, 17, 16, 0, len(strings), len(tree))
    return header + b'\0' * 16 + tree + strings


def fixture_bundle(root):
    """Exercise byte matching; these synthetic modules have no signature proof."""
    cert = b'fixture-public-certificate-bytes'
    image = struct.pack('<II6QII', 0, 0, 0, 4096, 10, 0, 0, 0, 0x644d5241, 0) + cert
    release = 'fixture-kernel'
    payloads = {
        'artifacts/Image': image,
        'artifacts/board.dtb': fixture_dtb(),
        'artifacts/signing-cert.der': cert,
        'artifacts/kernel.config': ''.join(key + '=' + value + '\n'
                                          for key, value in bundle.REQUIRED_CONFIG.items()).encode(),
        'artifacts/kernel.release': (release + '\n').encode(),
        'modules/lib/modules/fixture-kernel/kernel/example.ko': b'fixture-module-not-a-signed-ELF',
    }
    files = []
    for name, raw in payloads.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        target.chmod(0o644)
        files.append({'path': name, 'bytes': len(raw),
                      'sha256': hashlib.sha256(raw).hexdigest(), 'mode': 0o644})
    return {'kernel_files': files, 'kernel': {
        'release': release, 'module_count': 1,
        'artifacts': {'image': 'artifacts/Image', 'dtb': 'artifacts/board.dtb',
                      'certificate': 'artifacts/signing-cert.der', 'config': 'artifacts/kernel.config'},
        'compatible': ['lenovo,tb371fc', 'qcom,sm8250'],
        'arm64_header': {'stored_bytes': len(image), 'text_offset': 0,
                         'image_size': 4096, 'flags': 10}}}


class FrozenEvidenceTests(unittest.TestCase):
    def test_actual_r5_config_uses_runtime_enforcement_not_compiled_force(self):
        path = REPO / 'docs/research/2026-11-23/evidence/research5-services-records/container/artifacts/kernel.config.txt'
        config = bundle.parse_config(path.read_bytes())
        self.assertEqual(config['CONFIG_MODULE_SIG_FORCE'], 'n')
        self.assertEqual(config['CONFIG_MODULE_SIG'], 'y')
        self.assertEqual(config['CONFIG_MODULE_SIG_ALL'], 'y')
        self.assertEqual(config['CONFIG_MODULE_SIG_SHA512'], 'y')
        self.assertEqual(config['CONFIG_MODULE_SIG_HASH'], '"sha512"')
        self.assertEqual(config['CONFIG_LOCALVERSION'], '"-tb371fc-research5-services"')
        self.assertEqual({key: config.get(key) for key in bundle.REQUIRED_CONFIG}, bundle.REQUIRED_CONFIG)
        with self.assertRaisesRegex(ValueError, 'duplicate configuration'):
            bundle.parse_config(b'CONFIG_MODULE_SIG_FORCE=y\n# CONFIG_MODULE_SIG_FORCE is not set\n')

    def test_checked_in_candidate_is_deterministic_and_complete(self):
        candidate = derive.derive(REPO)
        self.assertEqual((REPO / bundle.CANDIDATE).read_bytes(), derive.encoded(candidate))
        self.assertEqual(len(candidate['kernel_files']), 106)
        self.assertEqual(sum(row['path'].endswith('.ko') for row in candidate['kernel_files']), 84)
        self.assertGreater(candidate['kernel']['arm64_header']['image_size'],
                           candidate['kernel']['arm64_header']['stored_bytes'])

    def test_historical_success_never_becomes_a_native_pass(self):
        report = bundle.qualify(REPO, derive.derive(REPO))
        self.assertEqual(report['evidence_consistency']['status'], 'verified')
        self.assertEqual(report['kernel_payload']['status'], 'not_provided')
        self.assertEqual(report['native_boot_readiness']['status'], 'blocked')
        self.assertFalse(report['native_boot_attempted'])
        self.assertEqual(report['owner_native_linux_passes_added'], 0)
        self.assertEqual(bundle.exit_status(report, 'evidence'), 0)
        self.assertEqual(bundle.exit_status(report, 'kernel'), 2)
        self.assertEqual(bundle.exit_status(report, 'native'), 2)

    def test_editing_status_or_omitting_one_module_does_not_change_the_contract(self):
        candidate = derive.derive(REPO)
        altered = copy.deepcopy(candidate)
        altered['boot_requirements'][0]['status'] = 'passed'
        with self.assertRaisesRegex(ValueError, 'exact derivation'):
            bundle.qualify(REPO, altered)
        altered = copy.deepcopy(candidate)
        altered['kernel_files'].pop()
        with self.assertRaisesRegex(ValueError, 'exact derivation'):
            bundle.qualify(REPO, altered)

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'candidate.json'
            path.write_text('{"schema_version": 1, "schema_version": 2}')
            with self.assertRaisesRegex(ValueError, 'duplicate JSON'):
                bundle.read_candidate(path)

    def test_json_booleans_or_floats_cannot_replace_integer_contract_fields(self):
        candidate = derive.derive(REPO)
        for key, value in [('schema_version', True), ('schema_version', 1.0)]:
            altered = copy.deepcopy(candidate)
            altered[key] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'exact derivation'):
                bundle.qualify(REPO, altered)
        altered = copy.deepcopy(candidate)
        altered['kernel']['module_count'] = 84.0
        with self.assertRaisesRegex(ValueError, 'exact derivation'):
            bundle.qualify(REPO, altered)

    def test_source_identity_tampering_is_rejected_before_parsing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in derive.FROZEN_SOURCES:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((REPO / relative).read_bytes())
            report = root / derive.REPORT
            original = report.read_bytes()
            report.write_bytes(b'[' + original[1:])
            with self.assertRaisesRegex(ValueError, 'frozen evidence identity mismatch'):
                derive.derive(root)

    def test_report_cannot_modify_a_kernel_or_rootfs_tree_through_an_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'input'
            root.mkdir()
            alias = root.parent / 'alias'
            alias.symlink_to(root, target_is_directory=True)
            for output in (root / 'report.json', alias / 'report.json'):
                with self.subTest(output=output):
                    command = [sys.executable, str(REPO / 'scripts/research/qualify_boot_bundle.py'),
                               '--kernel-root', str(root), '--output', str(output)]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=20)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn('outside every inspected input tree', result.stderr)
                    self.assertEqual(list(root.iterdir()), [])
            with self.assertRaises(ValueError):
                bundle.validate_output_destination(root / 'report.json', (None, root))

    def test_default_cli_reports_blocked_and_preserves_existing_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'report.json'
            command = [sys.executable, str(REPO / 'scripts/research/qualify_boot_bundle.py'),
                       '--repo', str(REPO), '--output', str(path)]
            first = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertEqual(first.returncode, 2, first.stderr)
            original = path.read_bytes()
            self.assertEqual(json.loads(original)['native_boot_readiness']['status'], 'blocked')
            second = subprocess.run(command, capture_output=True, text=True, timeout=20)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(path.read_bytes(), original)


class CurrentPayloadTests(unittest.TestCase):
    def test_frozen_transport_sidecars_are_separate_and_cannot_mask_corruption(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = fixture_bundle(root)
            raw = b'{"recorded":true}\n'
            contract['kernel_evidence_sidecars'] = [
                {'path': 'bundle.json', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}]
            self.assertEqual(bundle.qualify_kernel(root, contract)['status'], 'verified')
            (root / 'bundle.json').write_bytes(raw)
            result = bundle.qualify_kernel(root, contract)
            self.assertEqual(result['status'], 'verified', result['errors'])
            self.assertEqual(result['file_count'], len(contract['kernel_files']))
            self.assertEqual(result['evidence_sidecar_count'], 1)
            (root / 'bundle.json').write_bytes(raw.replace(b'true', b'null'))
            result = bundle.qualify_kernel(root, contract)
            self.assertEqual(result['status'], 'failed')
            self.assertIn({'code': 'identity_mismatch', 'path': 'bundle.json'}, result['errors'])

    def test_exact_current_bytes_are_distinct_from_a_new_signature_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = fixture_bundle(root)
            result = bundle.qualify_kernel(root, contract)
            self.assertEqual(result['status'], 'verified', result['errors'])
            self.assertTrue(result['module_bytes_match_recorded_qualification'])
            self.assertFalse(result['module_signatures_reexecuted'])
            self.assertFalse(result['module_enforcement']['configured_force'])
            self.assertFalse(result['module_enforcement']['runtime_verified'])
            self.assertEqual(result['module_enforcement']['required_boot_argument'], 'module.sig_enforce=1')
            self.assertFalse(result['physical_hardware_tested'])

    def test_same_size_module_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = fixture_bundle(root)
            module = root / next(row['path'] for row in contract['kernel_files'] if row['path'].endswith('.ko'))
            raw = module.read_bytes()
            module.write_bytes(bytes([raw[0] ^ 1]) + raw[1:])
            result = bundle.qualify_kernel(root, contract)
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(any(row['code'] == 'identity_mismatch' for row in result['errors']))

    def test_old_depmod_index_is_not_an_allowed_kernel_bundle_member(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract = fixture_bundle(root)
            (root / 'modules/lib/modules/fixture-kernel/modules.dep').write_text('old: old.ko\n')
            result = bundle.qualify_kernel(root, contract)
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(any(row['code'] == 'unexpected_files' for row in result['errors']))

    def test_identical_symlink_target_is_not_an_ordinary_bundle_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'bundle'
            root.mkdir()
            contract = fixture_bundle(root)
            cert = root / 'artifacts/signing-cert.der'
            outside = root.parent / 'same-certificate'
            cert.rename(outside)
            cert.symlink_to(outside)
            result = bundle.qualify_kernel(root, contract)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('symlink or special file', result['errors'][0]['reason'])

    def test_nofollow_applies_to_parent_directories_and_fifo_reads_do_not_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'bundle'
            root.mkdir()
            outside = root.parent / 'outside'
            outside.mkdir()
            (outside / 'data').write_bytes(b'not part of bundle')
            (root / 'alias').symlink_to(outside, target_is_directory=True)
            os.mkfifo(root / 'fifo')
            with bundle.BundleReader(root) as reader:
                with self.assertRaises(OSError):
                    reader.read('alias/data')
                with self.assertRaisesRegex(ValueError, 'bounded ordinary file'):
                    reader.read('fifo')


if __name__ == '__main__':
    unittest.main()
