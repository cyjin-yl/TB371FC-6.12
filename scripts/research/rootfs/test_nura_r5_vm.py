# SPDX-License-Identifier: GPL-2.0-only
import copy
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import nura_r5_vm as vm
from nura_r5_guest import crashed_services, verify_files


def accepted_fixture():
    profile = {"nonce": "a" * 32, "original_services": {"sysinit": ["udev"],
               "boot": ["hwclock"], "default": ["dbus", "rfkill"]},
               "original_files": {"etc/inittab": {}}, "runtime_files": {"module": {}, "firmware": {}},
               "added_files": {"verifier": {}}}
    gates = ("root_device", "original_files", "runtime_files", "added_files",
             "signature_enforced", "openrc_default", "udev", "dbus", "dbus_roundtrip",
             "signed_module_loaded", "pid1", "kernel_release", "root_label", "root_type",
             "service_status_complete")
    guest = {"schema_version": 1, **vm.SCOPE, "nonce": profile["nonce"], "run": "run-01",
             "profile_sha256": "b" * 64, "kernel_release": vm.common.RELEASE,
             "pid1": "/usr/bin/busybox", "root_type": "ext4", "root_source": "/dev/root",
             "root_label": vm.LABEL, "signature_enforced": True, "openrc_runlevel": "default",
             "core_boot_passed": True, "gates": {key: True for key in gates},
             "original_service_states": {"udev": ["started"], "hwclock": ["started"],
                                         "dbus": ["started"], "rfkill": ["failed"]},
             "default_runlevel_all_services_started": False}
    for name in ("original_files", "runtime_files", "added_files"):
        guest[name] = {"files": len(profile[name]), "mismatches": [], "passed": True}
    return guest, profile


class AcceptanceTest(unittest.TestCase):
    def test_core_boot_does_not_claim_failed_original_hardware_service_passed(self):
        guest, profile = accepted_fixture()
        self.assertTrue(vm.guest_acceptance(guest, profile, "b" * 64, "run-01"))
        self.assertFalse(guest["default_runlevel_all_services_started"])

    def test_reject_replay_and_wrong_kernel_init_root_scope(self):
        for key, bad in (("nonce", "wrong"), ("run", "run-02"), ("profile_sha256", "wrong"),
                         ("kernel_release", "7.3.5"), ("pid1", "/bin/sh"),
                         ("root_type", "tmpfs"), ("root_label", "wrong"),
                         ("signature_enforced", False), ("owner_native_linux_passes_added", 1)):
            with self.subTest(key=key):
                guest, profile = accepted_fixture()
                guest[key] = bad
                with self.assertRaises(ValueError):
                    vm.guest_acceptance(guest, profile, "b" * 64, "run-01")

    def test_reject_failed_or_inconsistent_guest_evidence(self):
        guest, profile = accepted_fixture()
        cases = []
        for name in guest["gates"]:
            bad = copy.deepcopy(guest)
            bad["gates"][name] = False
            cases.append(bad)
        for name, value in (("core_boot_passed", False), ("original_service_states", {}),
                            ("default_runlevel_all_services_started", True),
                            ("runtime_files", {"files": 1, "mismatches": [], "passed": True}),
                            ("original_files", {"files": 1, "mismatches": ["etc/inittab"], "passed": True})):
            bad = copy.deepcopy(guest)
            bad[name] = value
            cases.append(bad)
        for bad in cases:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                vm.guest_acceptance(bad, profile, "b" * 64, "run-01")

    def test_incomplete_stage_is_rejected_before_copy_or_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            stage = Path(temporary)
            (stage / "rootfs").mkdir()
            (stage / "nura-r5-stage.json").write_text(json.dumps({"complete": False}))
            before = sorted(str(p) for p in stage.rglob("*"))
            with patch.object(vm, "owned_directory"), self.assertRaisesRegex(ValueError, "successful"):
                vm.qualify_stage(stage / "unavailable-repo", stage)
            self.assertEqual(before, sorted(str(p) for p in stage.rglob("*")))


class RuntimeTest(unittest.TestCase):
    def test_openrc_crashed_status_exit_code_contract(self):
        self.assertEqual(crashed_services({"exit_code": 1, "stdout": "", "stderr": ""}),
                         (True, set()))
        self.assertEqual(crashed_services({"exit_code": 0, "stdout": "udev\nchronyd\n", "stderr": ""}),
                         (True, {"udev", "chronyd"}))
        for record in ({"exit_code": 0, "stdout": "", "stderr": ""},
                       {"exit_code": 1, "stdout": "udev", "stderr": ""},
                       {"exit_code": 1, "stdout": "", "stderr": "unknown option"},
                       {"exit_code": None, "error": "timeout"}):
            self.assertFalse(crashed_services(record)[0])

    def test_runtime_file_mismatch_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "module.ko"
            path.write_bytes(b"actual staged bytes")
            expected = vm.common.identity(path)
            name = str(path).lstrip("/")
            self.assertTrue(verify_files({name: expected})["passed"])
            path.write_bytes(b"replaced bytes")
            self.assertEqual(verify_files({name: expected})["mismatches"], [name])

    def test_owned_child_ignoring_term_is_killed_and_reaped(self):
        child = subprocess.Popen([sys.executable, "-c",
            "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            "print('ready',flush=True);time.sleep(60)"], stdout=subprocess.PIPE,
            text=True, start_new_session=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "ready")
            vm.stop_child(child, grace=0.2)
            self.assertEqual(child.returncode, -signal.SIGKILL)
            self.assertIsNotNone(child.poll())
            vm.stop_child(child, grace=0.2)
        finally:
            vm.stop_child(child, grace=0.2)
            child.stdout.close()


if __name__ == "__main__":
    unittest.main()
