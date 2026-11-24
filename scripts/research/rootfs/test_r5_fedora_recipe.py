# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import tempfile
from types import SimpleNamespace
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
                             ["assemble_system.py", "guest_transient_worker.py",
                              "guest_verify_system.py"])
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
            worker = (destination / "guest_transient_worker.py").read_text()
            self.assertNotIn("6.12.114-tb371fc-research4-system", worker)
            self.assertNotIn("research4-display-input-fedora45-v9-persistent-result", worker)
            self.assertNotIn("tb371fc-r4f-f45", worker)
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


class WorkerIdentityTests(unittest.TestCase):
    """Execute the real derived worker guards with synthetic VM identity.

    Only the noop mode runs, with FD observation and GO replaced by fixtures.
    This is not evidence of a VM boot, SELinux routing or behavior probes.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = Path(__file__).resolve().parents[3]
        self.derived = self.root / "recipe"
        recipe.derive_sources(self.repo, self.derived)

    def run_worker(self, source, *, release=s.RELEASE, machine="aarch64",
                   overrides=None, nonce="a" * 32, digest=None):
        spec = importlib.util.spec_from_file_location("identity_fixture_worker", source)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        profile = {"profile": recipe.PROFILE_NAME, "root_label": recipe.LABEL,
                   "kernel_release": s.RELEASE,
                   "validation_selinux_context": worker.CONTEXT,
                   "transient_selinux_context": worker.CONTEXT}
        profile.update(overrides or {})
        raw = json.dumps(profile).encode()
        path = self.root / "profile.json"
        path.write_bytes(raw)
        supplied_digest = hashlib.sha256(raw).hexdigest() if digest is None else digest
        compatible = SimpleNamespace(read_bytes=lambda: b"linux,dummy-virt\0")
        with patch("sys.argv", [str(source), "noop", "--nonce", nonce,
                                "--profile-sha256", supplied_digest]), \
                patch.object(worker.os, "uname", return_value=SimpleNamespace(
                    machine=machine, release=release)), \
                patch.object(worker.os, "getuid", return_value=0), \
                patch.object(worker.os, "geteuid", return_value=0), \
                patch.object(worker, "PROFILE", path), \
                patch.object(worker, "Path", return_value=compatible), \
                patch.object(worker, "descriptor", side_effect=lambda fd: {"fd": fd}), \
                patch.object(worker, "await_go") as go, \
                patch.object(worker, "emit") as emit:
            status = worker.main()
        return status, go, emit

    def test_frozen_worker_reproduces_observed_r5_rejection(self):
        with self.assertRaisesRegex(RuntimeError, "owned research4 ARM64 kernel"):
            self.run_worker(self.repo / recipe.V9 / "guest_transient_worker.py")

    def test_derived_worker_accepts_exact_r5_contract(self):
        status, go, emit = self.run_worker(self.derived / "guest_transient_worker.py")
        self.assertEqual(status, 0)
        go.assert_called_once_with("a" * 32)
        self.assertEqual([call.args[0] for call in emit.call_args_list],
                         ["TB371FC_R4F_WORKER_READY ", "TB371FC_R4F_WORKER_RESULT "])
        ready = emit.call_args_list[0].args[1]
        self.assertEqual(ready["kernel_release"], s.RELEASE)
        self.assertEqual(ready["nonce"], "a" * 32)
        self.assertTrue(ready["own_context_and_cgroup_must_be_observed_by_parent"])

    def test_derived_worker_rejects_wrong_kernel_arch_or_profile(self):
        cases = [
            {"release": "6.12.114-tb371fc-research4-system"},
            {"release": s.RELEASE + "-unqualified"},
            {"machine": "x86_64"},
            {"overrides": {"profile": "research4-display-input-fedora45-v9-persistent-result"}},
            {"overrides": {"root_label": "tb371fc-r4f-f45"}},
            {"overrides": {"kernel_release": "6.12.114-tb371fc-research4-system"}},
            {"overrides": {"transient_selinux_context": "unconfined_u:unconfined_r:unconfined_t:s0"}},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                self.run_worker(self.derived / "guest_transient_worker.py", **case)

    def test_derived_worker_preserves_nonce_and_profile_digest_guards(self):
        for case in ({"nonce": "not-a-nonce"}, {"digest": "b" * 64}):
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                self.run_worker(self.derived / "guest_transient_worker.py", **case)


if __name__ == "__main__":
    unittest.main()
