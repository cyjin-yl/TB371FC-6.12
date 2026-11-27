#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Receipt/derivation regressions; these fixtures do not claim an R7 build."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("rpmh_rootfs", HERE / "build_rpmh_rootfs.py")
rootfs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rootfs)
REPO = Path(os.environ.get("TB371FC_R7_TEST_REPO", str(HERE.parents[3])))


def evidence_fixture():
    # Deliberately synthetic identities exercise receipt binding only. No
    # compiler, signature verifier, module or guest is executed by this test.
    r6 = json.loads((REPO / "docs/research/2026-11-26/evidence/tianma-r6-build/build-result.json").read_text())
    names = [name.split("/" + rootfs.R6_RELEASE + "/", 1)[1] for name in r6["modules"]]
    prefix = "modules/lib/modules/" + rootfs.RELEASE + "/"
    pin = {"bytes": 1, "sha256": "0" * 64}
    build = {"passed": True, "kernel_release": rootfs.RELEASE,
        "recipe": {"sha256": rootfs.BUILD_RECIPE_SHA}, "retained_inputs_reverified": True,
        "offline_modules_qualified": True, "old_objects_copied": False, "old_private_key_copied": False,
        "native_hardware_passes_added": 0, "module_count": 84,
        "modules": {prefix + name: dict(pin) for name in names},
        "artifacts": {name: dict(pin) for name in rootfs.ARTIFACTS},
        "module_metadata": {name: {"installed": dict(pin)} for name in rootfs.METADATA}}
    build["artifacts"]["kernel.config"]["sha256"] = rootfs.CONFIG_SHA
    build["artifacts"]["board.dtb"]["sha256"] = rootfs.NATIVE_DTB_SHA
    sig = {"passed": True, "input_snapshot_stable": True, "module_count": 84,
        "public_certificate": {"der_sha256": pin["sha256"]}, "modules": [
            {"path": "lib/modules/" + rootfs.RELEASE + "/" + name, **pin, "passed": True,
             "verified_content_matches": True, "verified_signer_der_sha256": pin["sha256"]} for name in names]}
    abi = {"passed": True, "input_snapshot_stable": True, "module_count": 84,
        "kernel_release": rootfs.RELEASE, "module_symvers": dict(pin), "modules": [
            {"path": name, **pin, "imported_symbol_crcs_match": True, "debug_info_stripped": True} for name in names]}
    return build, sig, abi


class EvidenceTests(unittest.TestCase):
    def test_consistent_receipts_are_bound_to_the_exact_profile(self):
        prefix, names = rootfs.validate_evidence(*evidence_fixture())
        self.assertIn(rootfs.RELEASE, prefix)
        self.assertEqual(len(names), 84)
        self.assertTrue(rootfs.SUPPLIERS <= set(names))

    def test_old_release_cannot_be_relabelled(self):
        b, s, a = evidence_fixture(); b["kernel_release"] = rootfs.R5_RELEASE
        with self.assertRaisesRegex(ValueError, "exact completed R7"):
            rootfs.validate_evidence(b, s, a)

    def test_another_recipe_cannot_claim_qualification(self):
        b, s, a = evidence_fixture(); b["recipe"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "exact completed R7"):
            rootfs.validate_evidence(b, s, a)

    def test_unfinished_build_cannot_construct_a_root(self):
        for field in ("passed", "retained_inputs_reverified", "offline_modules_qualified"):
            b, s, a = evidence_fixture(); b[field] = False
            with self.subTest(field=field), self.assertRaises(ValueError):
                rootfs.validate_evidence(b, s, a)

    def test_signature_certificate_mismatch_is_rejected(self):
        b, s, a = evidence_fixture(); s["public_certificate"]["der_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "different public certificate"):
            rootfs.validate_evidence(b, s, a)

    def test_signature_and_abi_must_cover_the_same_module_bytes(self):
        b, s, a = evidence_fixture(); s["modules"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "signed module bytes"):
            rootfs.validate_evidence(b, s, a)
        b, s, a = evidence_fixture(); a["modules"][0]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "ABI module bytes"):
            rootfs.validate_evidence(b, s, a)

    def test_duplicate_receipt_rows_cannot_hide_a_missing_module(self):
        b, s, a = evidence_fixture(); s["modules"][-1] = copy.deepcopy(s["modules"][0])
        with self.assertRaisesRegex(ValueError, "signed module bytes"):
            rootfs.validate_evidence(b, s, a)

    def test_metadata_and_crc_export_sources_are_bound(self):
        b, s, a = evidence_fixture(); b["module_metadata"]["modules.order"]["installed"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "Kbuild metadata"):
            rootfs.validate_evidence(b, s, a)
        b, s, a = evidence_fixture(); a["module_symvers"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "CRC export source"):
            rootfs.validate_evidence(b, s, a)

    def test_old_private_key_or_objects_are_rejected(self):
        for field in ("old_private_key_copied", "old_objects_copied"):
            b, s, a = evidence_fixture(); b[field] = True
            with self.subTest(field=field), self.assertRaises(ValueError):
                rootfs.validate_evidence(b, s, a)


class DependencyTests(unittest.TestCase):
    def test_supplier_closure_expands_dependency_chain(self):
        graph = {name: [] for name in rootfs.SUPPLIERS}
        extra = "kernel/lib/example.ko"
        graph[extra] = []
        graph[sorted(rootfs.SUPPLIERS)[0]] = [extra]
        self.assertEqual(set(rootfs.dependency_closure(graph)), rootfs.SUPPLIERS | {extra})

    def test_missing_supplier_fails_closed(self):
        graph = {name: [] for name in rootfs.SUPPLIERS}
        del graph[sorted(graph)[0]]
        with self.assertRaisesRegex(ValueError, "supplier absent"):
            rootfs.dependency_closure(graph)

    def test_foreign_missing_and_duplicate_dependency_rows_fail(self):
        for raw in (b"a.ko: foreign.ko\n", b"a.ko: b.ko b.ko\nb.ko:\n",
                    b"a.ko:\na.ko:\nb.ko:\n", b"a.ko:\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                rootfs.dependency_graph(raw, {"a.ko", "b.ko"})


class DerivationTests(unittest.TestCase):
    def test_actual_frozen_sources_derive_without_weakening_acceptance(self):
        stage = rootfs.load_module(REPO / "scripts/research/rootfs/stage_r5_fedora.py", "stage_r5_fedora")
        materializer = rootfs.load_module(REPO / "scripts/research/rootfs/materialize_r5_fedora_recipe.py", "test_r5_materializer")
        before = {name: rootfs.identity(REPO / name) for name in rootfs.FROZEN}
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            derived = rootfs.derive_recipe(REPO, directory / "template", directory / "recipe", materializer, stage)
            self.assertEqual(derived["changed_from_r5_template"], ["assemble_system.py", "early_initramfs.py",
                "guest_transient_worker.py", "guest_verify_system.py", "system_common.py"])
            for file in derived["byte_identical_acceptance_sources"]:
                self.assertEqual((directory / "template" / file).read_bytes(), (directory / "recipe" / file).read_bytes())
            worker = (directory / "recipe/guest_transient_worker.py").read_text()
            self.assertEqual(worker.count(rootfs.RELEASE), 2)
            self.assertNotIn(rootfs.R5_RELEASE, worker)
            self.assertIn(rootfs.PROFILE, worker)
            self.assertIn(rootfs.LABEL, worker)
            early = (directory / "recipe/early_initramfs.py").read_text()
            self.assertIn("'--add-drivers'", early)
            for module in rootfs.SUPPLIERS:
                self.assertIn(Path(module).stem, early)
            for file in derived["derived"]:
                if file.endswith(".py"):
                    compile((directory / "recipe" / file).read_bytes(), file, "exec")
        self.assertEqual(before, {name: rootfs.identity(REPO / name) for name in rootfs.FROZEN})

    def test_derivation_anchor_changes_fail_instead_of_guessing(self):
        for text in ("missing", "old old"):
            with self.assertRaisesRegex(ValueError, "anchor differs"):
                rootfs.once(text, "old", "new")


if __name__ == "__main__":
    unittest.main()
