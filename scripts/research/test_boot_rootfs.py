#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic, isolated negative cases for offline rootfs module qualification."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from boot_rootfs import inspect_root_module_tree


RELEASE = "6.12.114-tb371fc-fixture"
MODULES = {"kernel/drivers/a.ko": b"synthetic module A\n",
           "kernel/crypto/b.ko": b"synthetic module B\n"}
METADATA = {"modules.builtin": b"kernel/fs/ext4/ext4.ko\n",
            "modules.builtin.modinfo": b"ext4.license=GPL\0",
            "modules.order": b"kernel/drivers/a.ko\nkernel/crypto/b.ko\n"}
INDEXES = {"modules.dep": b"kernel/drivers/a.ko: kernel/crypto/b.ko\nkernel/crypto/b.ko:\n",
           "modules.dep.bin": b"opaque-dependency-index",
           "modules.alias": b"alias fixture fixture_a\n",
           "modules.alias.bin": b"opaque-alias-index",
           "modules.symbols": b"alias symbol:fixture fixture_b\n",
           "modules.symbols.bin": b"opaque-symbol-index",
           "modules.softdep": b"",
           "modules.builtin.bin": b"opaque-builtin-index"}


class RootfsContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "rootfs"
        self.base = self.root / "usr/lib/modules" / RELEASE
        self.base.mkdir(parents=True)
        (self.root / "lib").symlink_to("usr/lib")
        self.contract = {"kernel": {"release": RELEASE, "module_count": 2}, "kernel_files": []}
        for name, data in {**MODULES, **METADATA, **INDEXES}.items():
            path = self.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(0o644)
            if name in MODULES or name in METADATA:
                self.contract["kernel_files"].append({
                    "path": f"modules/lib/modules/{RELEASE}/{name}",
                    "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mode": 0o644})

    def check(self):
        return inspect_root_module_tree(self.root, self.contract)

    def assert_failed(self, contains):
        result = self.check()
        self.assertFalse(result["passed"])
        self.assertIn(contains, result["errors"][0]["message"])
        self.assertFalse(result["rootfs_runtime_ready"])
        return result

    def test_merged_usr_pass_is_limited_to_offline_evidence(self):
        result = self.check()
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["resolved_module_directory"], f"usr/lib/modules/{RELEASE}")
        self.assertTrue(result["module_bytes_verified"])
        self.assertTrue(result["text_dependency_graph_verified"])
        self.assertTrue(result["binary_indexes_recorded"])
        # Deliberately opaque synthetic binaries are inventoried; this tool
        # does not pretend that hashing them qualifies kmod's binary format.
        self.assertFalse(result["binary_index_semantics_verified"])
        self.assertTrue(result["native_depmod_provenance_not_verified"])
        self.assertFalse(result["physical_hardware_tested"])
        self.assertFalse(result["rootfs_runtime_ready"])
        self.assertFalse(result["target_code_executed"])

    def test_absolute_merged_usr_alias_is_root_relative(self):
        (self.root / "lib").unlink()
        (self.root / "lib").symlink_to("/usr/lib")
        self.assertTrue(self.check()["passed"])

    def test_unmerged_lib_directory_is_supported(self):
        (self.root / "lib").unlink()
        (self.root / "usr/lib").rename(self.root / "lib")
        self.assertTrue(self.check()["passed"])

    def test_other_installed_release_is_not_used_for_dependencies(self):
        other = self.root / "usr/lib/modules/other-release"
        other.mkdir()
        (other / "foreign.ko").write_bytes(b"foreign")
        self.assertTrue(self.check()["passed"])
        (self.base / "modules.dep").write_text(
            "kernel/drivers/a.ko: ../other-release/foreign.ko\nkernel/crypto/b.ko:\n")
        self.assert_failed("traversing")

    def test_modified_module_bytes_are_rejected(self):
        (self.base / "kernel/drivers/a.ko").write_bytes(b"synthetic module Z\n")
        result = self.assert_failed("module bytes or mode differ")
        self.assertFalse(result["module_bytes_verified"])

    def test_modified_module_mode_is_rejected(self):
        (self.base / "kernel/drivers/a.ko").chmod(0o755)
        self.assert_failed("module bytes or mode differ")

    def test_missing_and_extra_modules_are_reported(self):
        (self.base / "kernel/drivers/a.ko").unlink()
        (self.base / "kernel/drivers/extra.ko.zst").write_bytes(b"extra")
        result = self.assert_failed("module set differs")
        self.assertEqual(result["module_set_difference"], {
            "missing": ["kernel/drivers/a.ko"], "extra": ["kernel/drivers/extra.ko.zst"]})

    def test_modified_kbuild_metadata_is_rejected(self):
        (self.base / "modules.order").write_text("kernel/crypto/b.ko\n")
        result = self.assert_failed("Kbuild metadata")
        self.assertTrue(result["module_bytes_verified"])
        self.assertFalse(result["kbuild_metadata_verified"])

    def test_module_leaf_symlink_is_never_followed(self):
        outside = Path(self.temp.name) / "outside.ko"
        outside.write_bytes(MODULES["kernel/drivers/a.ko"])
        module = self.base / "kernel/drivers/a.ko"
        module.unlink()
        module.symlink_to(outside)
        self.assert_failed("nonordinary node")

    def test_escaping_root_lib_alias_is_rejected(self):
        (self.root / "lib").unlink()
        (self.root / "lib").symlink_to("../outside")
        self.assert_failed("inside rootfs")

    def test_root_symlink_is_rejected(self):
        alias = Path(self.temp.name) / "root-alias"
        alias.symlink_to(self.root)
        result = inspect_root_module_tree(alias, self.contract)
        self.assertFalse(result["passed"])

    def test_required_index_missing_is_blocked(self):
        (self.base / "modules.dep.bin").unlink()
        result = self.assert_failed("required depmod indexes missing")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["missing_required_indexes"], ["modules.dep.bin"])

    def test_optional_kmod_indexes_are_recorded_without_assuming_version(self):
        result = self.check()
        self.assertTrue(result["passed"])
        self.assertIn("modules.builtin.alias.bin", result["optional_indexes_missing"])
        (self.base / "modules.builtin.alias.bin").write_bytes(b"opaque-optional-index")
        result = self.check()
        self.assertTrue(result["passed"])
        self.assertNotIn("modules.builtin.alias.bin", result["optional_indexes_missing"])
        self.assertIn("modules.builtin.alias.bin", [entry["path"] for entry in result["indexes"]])

    def test_empty_binary_index_is_rejected(self):
        (self.base / "modules.alias.bin").write_bytes(b"")
        self.assert_failed("empty binary depmod index")

    def test_invalid_dependency_graphs_fail(self):
        cases = {
            "missing module key": "kernel/drivers/a.ko: kernel/crypto/b.ko\n",
            "duplicate module key": "kernel/drivers/a.ko:\nkernel/drivers/a.ko:\nkernel/crypto/b.ko:\n",
            "missing dependency": "kernel/drivers/a.ko: kernel/nope.ko\nkernel/crypto/b.ko:\n",
            "duplicate dependency": "kernel/drivers/a.ko: kernel/crypto/b.ko kernel/crypto/b.ko\nkernel/crypto/b.ko:\n",
            "dependency cycle": "kernel/drivers/a.ko: kernel/crypto/b.ko\nkernel/crypto/b.ko: kernel/drivers/a.ko\n",
            "self dependency": "kernel/drivers/a.ko: kernel/drivers/a.ko\nkernel/crypto/b.ko:\n",
            "absolute dependency": "kernel/drivers/a.ko: /etc/passwd\nkernel/crypto/b.ko:\n",
            "foreign release": "kernel/drivers/a.ko: lib/modules/other/kernel/foreign.ko\nkernel/crypto/b.ko:\n",
        }
        for name, value in cases.items():
            with self.subTest(name=name):
                (self.base / "modules.dep").write_text(value)
                result = self.check()
                self.assertFalse(result["passed"])
                self.assertTrue(result["module_bytes_verified"])
                self.assertFalse(result["text_dependency_graph_verified"])

    def test_changed_during_read_is_rejected(self):
        path = self.base / "kernel/drivers/a.ko"
        target_inode = path.stat().st_ino
        original = os.read
        changed = False

        def mutate_then_read(fd, size):
            nonlocal changed
            if not changed and os.fstat(fd).st_ino == target_inode:
                changed = True
                with path.open("ab") as stream:
                    stream.write(b"race")
            return original(fd, size)

        with patch("boot_rootfs.os.read", side_effect=mutate_then_read):
            self.assert_failed("changed during inspection")
        self.assertTrue(changed)

    def test_duplicate_contract_path_is_rejected(self):
        self.contract["kernel_files"].append(dict(self.contract["kernel_files"][0]))
        self.assert_failed("duplicate kernel_files")

    def test_module_changed_after_its_read_is_rejected_at_final_snapshot(self):
        path = self.base / "kernel/drivers/a.ko"
        trigger_inode = (self.base / "modules.dep").stat().st_ino
        original = os.read
        changed = False

        def change_previous_file(fd, size):
            nonlocal changed
            if not changed and os.fstat(fd).st_ino == trigger_inode:
                changed = True
                path.write_bytes(b"synthetic module Z\n")
            return original(fd, size)

        with patch("boot_rootfs.os.read", side_effect=change_previous_file):
            result = self.assert_failed("previously read file changed")
        self.assertTrue(changed)
        self.assertFalse(result["module_bytes_verified"])
        self.assertFalse(result["input_snapshot_stable"])

    def test_missing_metadata_identity_is_not_inferred(self):
        self.contract["kernel_files"] = [entry for entry in self.contract["kernel_files"]
                                         if not entry["path"].endswith("/modules.order")]
        self.assert_failed("three installed Kbuild")

    def test_invalid_contract_count_is_rejected(self):
        self.contract["kernel"]["module_count"] = True
        self.assert_failed("module count")


if __name__ == "__main__":
    unittest.main()
