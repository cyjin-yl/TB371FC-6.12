# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import json
import os
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import materialize_r5_fedora_recipe as recipe
import r5_system_common as common
import stage_r5_fedora as s


def acl_semantics(raw):
    # ext4 stores short ACL entries without an ID. debugfs reconstructs those
    # unused fields as zero, while Linux getxattr reconstructs ACL_UNDEFINED_ID.
    # Named users/groups must retain their exact numeric IDs and permissions.
    if len(raw) < 4 or (len(raw) - 4) % 8 or struct.unpack_from("<I", raw)[0] != 2:
        raise ValueError("unexpected POSIX ACL representation")
    result = []
    for tag, perm, ident in struct.iter_unpack("<HHI", raw[4:]):
        if not 0 <= perm <= 7:
            raise ValueError("invalid ACL permission")
        if tag in (1, 4, 16, 32):
            if ident not in (0, 0xffffffff):
                raise ValueError("unexpected unused ACL identity")
            ident = None
        elif tag not in (2, 8) or ident == 0xffffffff:
            raise ValueError("invalid named ACL identity")
        result.append((tag, perm, ident))
    return result


class RecipeTests(unittest.TestCase):
    def test_actual_frozen_source_derivation(self):
        repo = Path(__file__).resolve().parents[3]
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "recipe"
            result = recipe.derive_sources(repo, destination)
            self.assertEqual(result["changed_v9_files"],
                             ["assemble_system.py", "guest_verify_system.py"])
            for name in recipe.PINS.keys() | recipe.SUPPLEMENT.keys():
                original = result["originals"][name]["sha256"]
                actual = result["derived"][name]["sha256"]
                if name in result["changed_v9_files"]:
                    self.assertNotEqual(original, actual)
                else:
                    self.assertEqual(original, actual)
            guest = (destination / "guest_verify_system.py").read_text()
            self.assertIn("profile['root_label'] == 'tb371fc-r5-f45'", guest)
            self.assertIn("module.sig_enforce=1", guest)
            self.assertIn("production boot did not select the exact reviewed tmpfs entrypoint", guest)
            self.assertIn("booted ext4 did not retain the qualified journal ACL", guest)
            assemble = (destination / "assemble_system.py").read_text()
            self.assertIn("from system_common import build_image", assemble)
            self.assertIn("install_policy_candidate()", assemble)
            self.assertIn("from early_initramfs import build", assemble)
            with self.assertRaises(FileExistsError):
                recipe.derive_sources(repo, destination)

    def test_stage_source_identity_survives_different_umask(self):
        repo = Path(__file__).resolve().parents[3]
        source = Path(recipe.__file__).with_name("stage_r5_fedora.py")
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "recipe"
            # Force the default output mode to differ from the source in
            # ordinary Git checkouts and git-archive extractions.
            mask = 0o077 if s.identity(source)["mode"] != 0o600 else 0o022
            old_mask = os.umask(mask)
            try:
                result = recipe.derive_sources(repo, destination)
            finally:
                os.umask(old_mask)
            self.assertEqual(result["derived"]["stage_r5_fedora.py"], s.identity(source))
            self.assertEqual(s.identity(destination / "stage_r5_fedora.py"), s.identity(source))

    def test_derivation_rejects_missing_or_duplicate_anchor(self):
        for text in ("none", "anchor anchor"):
            with self.assertRaises(ValueError):
                recipe.replace_once(text, "anchor", "new")

    def test_acl_normalizes_only_unused_identifiers(self):
        header = struct.pack("<I", 2)
        named = lambda ident: struct.pack("<HHI", 2, 4, ident)
        short = lambda ident: struct.pack("<HHI", 1, 6, ident)
        self.assertEqual(acl_semantics(header + short(0)), acl_semantics(header + short(0xffffffff)))
        self.assertNotEqual(acl_semantics(header + named(12345)), acl_semantics(header + named(12346)))
        with self.assertRaises(ValueError):
            acl_semantics(header + short(12345))

    def test_guest_tmpdir_does_not_inherit_host_job_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "var/tmp").mkdir(parents=True)
            with patch.object(common, "ROOT", root), \
                    patch.object(common, "qualified_stage"), \
                    patch.dict(os.environ, {"TMPDIR": "/host/job", "TMP": "/host/tmp",
                                            "TEMP": "/host/temp"}), \
                    patch.object(common.subprocess, "run") as run:
                common.run_guest(["/usr/bin/dracut"], timeout=900)
                env = run.call_args.kwargs["env"]
                for key in ("TMPDIR", "TMP", "TEMP"):
                    self.assertEqual(env[key], "/var/tmp")
                self.assertEqual(os.environ["TMPDIR"], "/host/job")
                self.assertEqual(run.call_args.kwargs["timeout"], 900)
                self.assertTrue(run.call_args.kwargs["check"])
                self.assertEqual(run.call_args.args[0][-1], "/usr/bin/dracut")

    def test_real_ordinary_ext4_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "root"
            root.mkdir()
            payload = root / "payload"
            payload.write_bytes(b"R5 image fixture\n")
            os.setxattr(payload, "user.tb371fc", b"retained-xattr")
            # Linux POSIX ACL xattr: named user makes this a nontrivial ACL.
            acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", tag, perm, uid)
                for tag, perm, uid in [(1, 6, 0xffffffff), (2, 4, 12345),
                                       (4, 4, 0xffffffff), (16, 4, 0xffffffff),
                                       (32, 0, 0xffffffff)])
            os.setxattr(payload, "system.posix_acl_access", acl)
            acl = os.getxattr(payload, "system.posix_acl_access")
            with self.assertRaises(ValueError):
                common.create_ext4(root, root / "recursive.ext4", "tb371fc-r5-f45",
                                   size_bytes=64 * 1024**2, mkfs_timeout=60)
            image = base / "fixture.ext4"
            result = common.create_ext4(root, image, "tb371fc-r5-f45",
                                       size_bytes=64 * 1024**2, mkfs_timeout=60)
            self.assertEqual(result["label"], "tb371fc-r5-f45")
            self.assertFalse(result["physical_block_device_used"])
            self.assertEqual(result["sha256"], s.identity(image)["sha256"])
            data = subprocess.check_output(["/usr/sbin/debugfs", "-R", "cat /payload", str(image)])
            self.assertEqual(data, b"R5 image fixture\n")
            for name, expected in (("user.tb371fc", b"retained-xattr"),
                                   ("system.posix_acl_access", acl)):
                target = base / ("export-" + name)
                subprocess.run(["/usr/sbin/debugfs", "-R",
                    f"ea_get -f {target} /payload {name}", str(image)], check=True)
                actual = target.read_bytes()
                if name == "system.posix_acl_access":
                    # This proves on-disk ACL semantics, not byte equality of
                    # the later guest kernel's getxattr result. The v9 guest
                    # retains its original exact kernel readback gate.
                    self.assertEqual(acl_semantics(actual), acl_semantics(expected))
                else:
                    self.assertEqual(actual, expected)
            for suffix in ("mkfs", "fsck", "label"):
                receipt = json.loads((base / ("fixture.ext4." + suffix + ".json")).read_text())
                self.assertEqual(receipt["exit_code"], 0)
            with self.assertRaises(FileExistsError):
                common.create_ext4(root, image, "tb371fc-r5-f45",
                                   size_bytes=64 * 1024**2, mkfs_timeout=60)
            self.assertEqual(result["sha256"], s.identity(image)["sha256"])


if __name__ == "__main__":
    unittest.main()
