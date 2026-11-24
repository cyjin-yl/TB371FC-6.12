#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Actual archived run04 evidence plus targeted negative tests; no VM run."""
import copy
from pathlib import Path
import tempfile
import unittest

import seal_r5_run04 as seal


class Run04SealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[3]
        cls.collection, cls.verify, cls.summary = seal.evidence_only(cls.repo)

    def check_mutation(self, target, path, value):
        collection = copy.deepcopy(self.collection)
        verify = copy.deepcopy(self.verify)
        obj = collection if target == "collection" else verify
        for key in path[:-1]:
            obj = obj[key]
        obj[path[-1]] = value
        with self.assertRaises(ValueError):
            seal.validate_records(collection, verify)

    def test_archived_originals(self):
        self.assertEqual(self.summary["final_image"]["sha256"],
                         "f3d260f5e91ed6a2b67e84fd4f7b3d07b1ff2dda5c88be43d1dac242774043ad")
        self.assertEqual(self.summary["owner_native_linux_passes_added"], 0)
        self.assertEqual(self.summary["native_boot_readiness"], "blocked")

    def test_failed_phase(self):
        self.check_mutation("collection", ["run_receipts", "verify.exit"], "1")

    def test_broken_lineage(self):
        self.check_mutation("collection", ["records", "lineage-verify/after.json",
                            "content", "before", "image", "sha256"], "0" * 64)

    def test_changed_result_identity(self):
        self.check_mutation("collection", ["records", "lineage-verify/after.json",
                            "content", "result", "sha256"], "0" * 64)

    def test_failed_production(self):
        self.check_mutation("verify", ["persistent_result_qualified"], False)

    def test_warning(self):
        self.check_mutation("verify", ["observed_warning_counts", "selinux_avc_denial_count"], 1)

    def test_false_is_not_zero(self):
        self.check_mutation("verify", ["observed_warning_counts", "selinux_avc_denial_count"], False)

    def test_incomplete_routes(self):
        self.check_mutation("verify", ["independent_same_boot_av_gates"], {})

    def test_signature_enforcement(self):
        self.check_mutation("verify", ["guest_result", "module_sig_enforce_sysfs"], "N")

    def test_native_overclaim(self):
        self.check_mutation("verify", ["physical_hardware_tested"], True)

    def test_guest_image_repair(self):
        self.check_mutation("verify", ["persistent_result_metadata",
                            "filesystem_replayed_or_repaired"], True)

    def test_tampered_exact_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "result.json"
            path.write_bytes(b"{}")
            expected = seal.identity(path)
            path.write_bytes(b"[]")
            with self.assertRaises(ValueError):
                seal.exact(path, expected)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "original"
            path.write_bytes(b"result")
            link = path.with_name("alias")
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                seal.exact(link, seal.identity(path))


if __name__ == "__main__":
    unittest.main()
