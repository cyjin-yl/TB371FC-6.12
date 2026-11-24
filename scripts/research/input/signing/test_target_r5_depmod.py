#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import copy
import json
from pathlib import Path
import tempfile
import unittest

import target_r5_depmod as m


class TargetContractTests(unittest.TestCase):
    def test_reject_unaccepted_unsigned_or_partial_stage(self):
        original = json.loads((Path(__file__).resolve().parents[4] /
            "docs/research/2026-11-23/boot-candidate-r5.json").read_text())
        selected = m.common.selected_modules(original)
        receipt = {"complete": True, "frozen_inputs_verified_after": True,
                   "module_loaded": False, "module_count": 84, "unchanged_modules": 83,
                   "kernel_release": m.RELEASE,
                   "public_certificate_sha256": m.stage.CERT_SHA,
                   "original_cms": {"signature_verified": True},
                   "replacement_cms": {"signature_verified": True},
                   "unsigned": {"sha256": m.stage.UNSIGNED_SHA,
                                "bytes": m.stage.UNSIGNED_SIZE},
                   "replacement": {"sha256": "1" * 64, "bytes": 4096,
                                   "mode": selected[m.MODULE]["mode"]}}
        candidate = m.derived_contract(original, receipt)
        self.assertEqual(len(m.common.selected_modules(candidate)), 87)
        for key, value in (("complete", False), ("module_loaded", True),
                           ("unchanged_modules", 82), ("kernel_release", "4.19")):
            changed = copy.deepcopy(receipt)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.derived_contract(original, changed)
        for mutation in (lambda r: r["unsigned"].update(sha256="2" * 64),
                         lambda r: r["replacement"].update(path="another/module.ko"),
                         lambda r: r["replacement"].update(bytes=-1),
                         lambda r: r["replacement_cms"].update(signature_verified=False)):
            changed = copy.deepcopy(receipt)
            mutation(changed)
            with self.assertRaises(ValueError):
                m.derived_contract(original, changed)

    def test_load_plan_rejects_foreign_paths_commands_and_missing_dependencies(self):
        dependency = "kernel/drivers/test/required.ko"
        selected = {m.MODULE: {}, dependency: {}}
        graph = m.MODULE + ": " + dependency + "\n" + dependency + ":\n"
        prefix = "/candidate/lib/modules/" + m.RELEASE + "/"
        valid = "insmod " + prefix + dependency + "\ninsmod " + prefix + m.MODULE + "\n"
        result = m.check_load_plan(valid, graph, selected)
        self.assertEqual(result["modules"], [dependency, m.MODULE])
        self.assertFalse(result["module_loaded"])
        for text in ("", "insmod " + prefix + m.MODULE,
                     valid.replace("/candidate/", "/retained-root/"),
                     valid + "install /bin/true\n", valid + valid,
                     valid.replace("required.ko", "unrecorded.ko"),
                     valid.replace(m.MODULE, m.MODULE + " injected=1")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                m.check_load_plan(text, graph, selected)

    def test_target_aliases_cannot_escape_runtime_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "usr").mkdir()
            (root / "usr/sbin").symlink_to("/outside/usr/bin")
            with self.assertRaisesRegex(ValueError, "sbin alias"):
                m.target_kmod(root)


if __name__ == "__main__":
    unittest.main()
