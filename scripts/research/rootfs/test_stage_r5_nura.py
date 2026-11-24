# SPDX-License-Identifier: GPL-2.0-only
import os
from pathlib import Path
import tarfile
import tempfile
import unittest

from stage_r5_nura import validate_members, target, verify_inventory


def member(name, kind=tarfile.REGTYPE, link="", size=0):
    info = tarfile.TarInfo(name)
    info.type, info.linkname, info.size = kind, link, size
    return info


class LayoutTest(unittest.TestCase):
    def test_ordinary_tree_with_hardlink_and_absolute_guest_symlink(self):
        items = [member(".", tarfile.DIRTYPE),
                 member("./usr", tarfile.DIRTYPE),
                 member("./usr/a", size=4),
                 member("./usr/b", tarfile.LNKTYPE, "./usr/a"),
                 member("./bin", tarfile.SYMTYPE, "/usr")]
        self.assertEqual(validate_members(items),
                         {"members": 5, "regular_bytes": 4, "symlinks": 1, "hardlinks": 1})

    def test_reject_alias_or_escape(self):
        for name in ("../host", "/host", "./usr/../host", "./usr//a", "usr\\a"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_members([member(".", tarfile.DIRTYPE), member(name)])

    def test_reject_duplicate(self):
        with self.assertRaises(ValueError):
            validate_members([member(".", tarfile.DIRTYPE), member("a"), member("./a")])

    def test_reject_write_through_symlink(self):
        for first in (True, False):
            link = member("lib", tarfile.SYMTYPE, "/tmp")
            child = member("lib/host")
            items = [member(".", tarfile.DIRTYPE)] + ([link, child] if first else [child, link])
            with self.assertRaises(ValueError):
                validate_members(items)

    def test_reject_hardlink_to_symlink_or_unseen(self):
        for name in ("a", "missing", "../host"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_members([member(".", tarfile.DIRTYPE),
                                  member("a", tarfile.SYMTYPE, "/tmp"),
                                  member("b", tarfile.LNKTYPE, name)])

    def test_reject_special_file(self):
        with self.assertRaises(ValueError):
            validate_members([member(".", tarfile.DIRTYPE), member("dev", tarfile.CHRTYPE)])

    def test_reject_missing_parent(self):
        with self.assertRaises(ValueError):
            validate_members([member(".", tarfile.DIRTYPE), member("usr/bin/a")])

    def test_expanded_bound(self):
        with self.assertRaises(ValueError):
            validate_members([member(".", tarfile.DIRTYPE), member("large", size=4*1024**3+1)])


class GuestPathTest(unittest.TestCase):
    def test_absolute_link_is_guest_relative(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "usr/bin").mkdir(parents=True)
            (root / "usr/bin/busybox").write_bytes(b"guest")
            (root / "sbin").symlink_to("usr/bin")
            (root / "usr/bin/init").symlink_to("/usr/bin/busybox")
            path, links = target(root, "sbin/init")
            self.assertEqual(path.read_bytes(), b"guest")
            self.assertEqual(len(links), 2)

    def test_escape_and_loop(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "escape").symlink_to("../outside")
            (root / "loop").symlink_to("loop")
            for name in ("escape", "loop"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    target(root, name)

    def test_inventory_keeps_missing_openrc_init_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "sbin").mkdir()
            inv = {"files": [{"path": "sbin/openrc-init", "unavailable": "not found"}],
                   "directories": {}}
            self.assertEqual(verify_inventory(root, inv), {"sbin/openrc-init": "absent"})
            (root / "sbin/openrc-init").touch()
            with self.assertRaises(ValueError):
                verify_inventory(root, inv)


if __name__ == "__main__":
    unittest.main()
