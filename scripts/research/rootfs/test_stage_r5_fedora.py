# SPDX-License-Identifier: GPL-2.0-only
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import stage_r5_fedora as s


class StageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_path_escape(self):
        for value in ("../x", "/etc/passwd", "a/../b", "a//b", ".", "a\\b"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                s.relative(value)

    def test_symlink_parent(self):
        (self.root / "alias").symlink_to(self.root)
        with self.assertRaises(ValueError):
            s.under(self.root, "alias/file")

    def test_no_overwrite(self):
        a, b = self.root / "a", self.root / "b"
        a.write_bytes(b"source")
        b.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            s.copy_exact(a, b, s.identity(a))
        self.assertEqual(b.read_bytes(), b"existing")

    def test_copy_identity(self):
        a, b = self.root / "a", self.root / "b"
        a.write_bytes(b"module")
        a.chmod(0o600)
        expected = s.identity(a)
        s.copy_exact(a, b, expected)
        self.assertEqual(s.identity(b), expected)

    def test_copy_wrong_source(self):
        a, b = self.root / "a", self.root / "b"
        a.write_bytes(b"module")
        expected = s.identity(a)
        a.write_bytes(b"wrong!")
        with self.assertRaises(ValueError):
            s.copy_exact(a, b, expected)
        self.assertFalse(b.exists())

    def test_ordinary_file_no_symlink(self):
        a = self.root / "a"
        a.symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            s.identity(a)

    def contract(self):
        prefix = "modules/lib/modules/" + s.RELEASE + "/"
        names = ["kernel/f%03d.ko" % i for i in range(84)] + sorted(s.METADATA)
        return {"kernel": {"release": s.RELEASE, "module_count": 84},
                "kernel_files": [{"path": prefix + n, "bytes": 5,
                                  "sha256": "a"*64, "mode": 0o600}
                                 for n in names]}

    def test_module_selection(self):
        self.assertEqual(len(s.selected_modules(self.contract())), 87)

    def test_wrong_release(self):
        c = self.contract()
        c["kernel"]["release"] = "other"
        with self.assertRaises(ValueError):
            s.selected_modules(c)

    def test_duplicate(self):
        c = self.contract()
        c["kernel_files"].append(c["kernel_files"][0])
        with self.assertRaises(ValueError):
            s.selected_modules(c)

    def test_generated_index_not_input(self):
        c = self.contract()
        c["kernel_files"][0]["path"] = "modules/lib/modules/" + s.RELEASE + "/modules.dep"
        with self.assertRaises(ValueError):
            s.selected_modules(c)

    def test_metadata_required(self):
        c = self.contract()
        c["kernel_files"].pop()
        with self.assertRaises(ValueError):
            s.selected_modules(c)

    def test_baseline_pins_both_digest_and_bytes(self):
        s.require_baseline({"sha256": s.BASE_DIGEST, "bytes": s.BASE_BYTES})
        with self.assertRaises(ValueError):
            s.require_baseline({"sha256": s.BASE_DIGEST, "bytes": s.BASE_BYTES + 1})

    def test_canonical_metadata(self):
        tree = self.root / "tree"
        tree.mkdir()
        file = tree / "data"
        file.write_bytes(b"one")
        a = s.canonical(tree, self.root / "a.log")
        b = s.canonical(tree, self.root / "b.log")
        self.assertEqual(a["sha256"], b["sha256"])
        file.chmod(0o700)
        c = s.canonical(tree, self.root / "c.log")
        self.assertNotEqual(a["sha256"], c["sha256"])

    def test_failed_command_receipt(self):
        with self.assertRaises(RuntimeError):
            s.run(self.root, "failed", ["/bin/sh", "-c", "exit 7"])
        import json
        receipt = json.loads((self.root / "failed.json").read_text())
        self.assertEqual(receipt["exit_code"], 7)
        self.assertIn("error", receipt)

    def test_wrong_work_prefix(self):
        with self.assertRaises(ValueError):
            s.stage(self.root, self.root / "wrong")
        self.assertFalse((self.root / "wrong").exists())


if __name__ == "__main__":
    unittest.main()
