# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic lineage/negative fixtures, never guest boot evidence."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import run_r5_vm_phase as gate


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / "rootfs"
        self.boot = self.root / "boot"
        self.boot.mkdir(parents=True)
        self.profile = self.root / "usr/share/tb371fc/system-profile.json"
        self.profile.parent.mkdir(parents=True)
        self.recipe = self.work / "recipe"
        self.recipe.mkdir()
        self.runner = self.recipe / "boot_system_vm.py"
        self.runner.write_text("# synthetic runner fixture\n")
        self.kernel = self.boot / ("Image-" + gate.RELEASE)
        self.kernel.write_bytes(b"fixture kernel")
        data = {"root_label": gate.LABEL, "kernel_release": gate.RELEASE,
                "kernel_image_sha256": gate.identity(self.kernel)["sha256"]}
        gate.save(self.profile, data)
        gate.save(self.work / "system-profile.json", data)
        gate.save(self.recipe / "derivation.json",
                  {"derived": {"boot_system_vm.py": gate.identity(self.runner)}})
        self.archives = {}
        for phase, (name, role) in gate.ROLES.items():
            suffix = "-maintenance" if phase == "label" else ""
            path = self.boot / ("initramfs-" + gate.RELEASE + suffix + ".img")
            path.write_bytes(phase.encode())
            info = gate.identity(path)
            gate.save(self.work / name,
                      {"path": str(path), "role": role, "archive_verified": True,
                       "kernel_release": gate.RELEASE, "sha256": info["sha256"],
                       "size_bytes": info["bytes"]})
            self.archives[role] = info["sha256"]
        self.image = self.work / gate.IMAGE
        self.image.write_bytes(b"initial image")
        info = gate.identity(self.image)
        self.manifest = self.work / "image.before-boot.json"
        gate.save(self.manifest, {"path": str(self.image), "label": gate.LABEL,
                  "filesystem": "ext4", "physical_block_device_used": False,
                  "profile_sha256": gate.identity(self.profile)["sha256"],
                  "archives": self.archives, "sha256": info["sha256"],
                  "size_bytes": info["bytes"]})

    def child(self, passed=True, code=0):
        def simulate(argv, check):
            phase = argv[-3]
            run = self.work / argv[-1]
            run.mkdir()
            inputs = gate.boot_inputs(self.work, phase)
            result = {k: inputs[k] for k in
                      ("profile_sha256", "kernel_image_sha256", "initramfs_sha256")}
            result.update(passed=passed, phase=phase, qemu_exit_code=code,
                          termination_reason=None if passed else "synthetic failure")
            gate.save(run / "result.json", result)
            # Simulate a legitimate same-size image mutation by the guest.
            self.image.write_bytes((b"L" if phase == "label" else b"V") * inputs["image"]["bytes"])
            return subprocess.CompletedProcess(argv, code)
        return simulate

    def label(self):
        with patch.object(gate.subprocess, "run", side_effect=self.child()):
            self.assertEqual(gate.run_phase(self.work, "label"), 0)

    def test_complete_pair_binds_label_output_to_verify_input(self):
        self.label()
        with patch.object(gate.subprocess, "run", side_effect=self.child()):
            self.assertEqual(gate.run_phase(self.work, "verify"), 0)
        first = gate.read_json(self.work / "lineage-label/after.json")
        second = gate.read_json(self.work / "lineage-verify/after.json")
        self.assertEqual(first["image_after"], second["before"]["image"])
        self.assertNotEqual(first["before"]["image"], second["image_after"])
        self.assertFalse(second["physical_hardware_tested"])
        with self.assertRaises(ValueError):
            gate.prepare(self.work, "verify")

    def test_wrong_image_before_label(self):
        self.image.write_bytes(b"X" * self.image.stat().st_size)
        with self.assertRaisesRegex(ValueError, "fresh build"):
            gate.prepare(self.work, "label")

    def test_same_size_wrong_image_after_label(self):
        self.label()
        self.image.write_bytes(b"X" * self.image.stat().st_size)
        with self.assertRaisesRegex(ValueError, "current image"):
            gate.prepare(self.work, "verify")

    def test_label_result_tampered(self):
        self.label()
        result = self.work / "vm-label-01/result.json"
        value = gate.read_json(result)
        value["extra"] = "changed"
        result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "current image"):
            gate.prepare(self.work, "verify")

    def test_failed_label_never_qualifies(self):
        with patch.object(gate.subprocess, "run", side_effect=self.child(False, 1)):
            self.assertEqual(gate.run_phase(self.work, "label"), 1)
        self.assertFalse(gate.read_json(self.work / "lineage-label/after.json")["passed"])
        with self.assertRaises(ValueError):
            gate.prepare(self.work, "verify")
        with self.assertRaises(ValueError):
            gate.prepare(self.work, "label")

    def test_missing_child_result_preserved(self):
        with patch.object(gate.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaises(FileNotFoundError):
                gate.run_phase(self.work, "label")
        record = gate.read_json(self.work / "lineage-label/after.json")
        self.assertFalse(record["passed"])
        self.assertIn("FileNotFoundError", record["error"])
        with self.assertRaises(ValueError):
            gate.prepare(self.work, "label")

    def test_unguarded_label_attempt_rejected(self):
        (self.work / "vm-label-01").mkdir()
        with self.assertRaises(ValueError):
            gate.prepare(self.work, "verify")

    def test_changed_runner_rejected(self):
        self.runner.write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "derived VM runner"):
            gate.prepare(self.work, "label")

    def test_changed_maintenance_archive_rejected(self):
        (self.boot / ("initramfs-" + gate.RELEASE + "-maintenance.img")).write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "archive receipt"):
            gate.prepare(self.work, "label")

    def test_hardlink_image_rejected(self):
        os.link(self.image, self.work / "alias")
        with self.assertRaisesRegex(ValueError, "independent ordinary file"):
            gate.prepare(self.work, "label")

    def test_symlink_image_rejected(self):
        target = self.work / "other"
        self.image.rename(target)
        self.image.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "independent ordinary file"):
            gate.prepare(self.work, "label")

    def test_inputs_changed_during_child_rejected(self):
        simulate = self.child()
        def changed(argv, check):
            result = simulate(argv, check)
            self.runner.write_text("# changed during child\n")
            return result
        with patch.object(gate.subprocess, "run", side_effect=changed):
            with self.assertRaises(ValueError):
                gate.run_phase(self.work, "label")
        self.assertFalse(gate.read_json(self.work / "lineage-label/after.json")["passed"])


if __name__ == "__main__":
    unittest.main()
