#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Regress recorded public metadata and malformed variants, not hardware behavior."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import correlate_native_dt as c


EVIDENCE = Path(__file__).resolve().parents[2] / "docs/research/2026-11-24/evidence/native-dt"


class CorrelationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.backup_raw = (EVIDENCE / "backup-final.json").read_bytes()
        cls.live_raw = (EVIDENCE / "live-android.json").read_bytes()
        cls.backup = json.loads(cls.backup_raw)
        cls.live = json.loads(cls.live_raw)

    def run_changed(self, *, backup=None, live=None):
        return c.correlate(self.backup_raw if backup is None else json.dumps(backup).encode(),
                           self.live_raw if live is None else json.dumps(live).encode())

    def test_actual_reported_indices_and_layered_ids_have_narrow_scope(self):
        result = self.run_changed()
        self.assertEqual(result["correlation_status"], "reported_indices_consistent")
        self.assertEqual(result["reported_selection"]["slot_suffix"]["value"], "_a")
        base = result["base_dt_by_reported_index"]
        overlay = result["overlays_by_reported_indices"]["entries"][0]
        self.assertEqual((base["index"], overlay["index"]), (0, 2))
        self.assertEqual(base["root_id_comparison"]["qcom,msm-id"]["state"], "equal")
        self.assertEqual(base["root_id_comparison"]["qcom,board-id"]["state"], "different")
        self.assertEqual(overlay["root_id_comparison"]["qcom,board-id"]["state"], "equal")
        self.assertEqual(overlay["root_id_comparison"]["qcom,msm-id"]["state"], "absent_in_candidate")
        self.assertFalse(result["runtime_abl_replayed"])
        self.assertFalse(result["overlay_application_performed"])
        self.assertFalse(result["per_byte_runtime_selection_verified"])
        self.assertFalse(result["physical_mainline_linux_tested"])
        self.assertEqual(result["owner_native_linux_passes_added"], 0)

    def test_input_hashes_bind_exact_json_bytes_and_output_is_deterministic(self):
        result = self.run_changed()
        self.assertEqual(result, self.run_changed())
        self.assertEqual(result["inputs"]["backup"]["sha256"], hashlib.sha256(self.backup_raw).hexdigest())
        self.assertEqual(result["inputs"]["live"]["sha256"], hashlib.sha256(self.live_raw).hexdigest())
        changed_bytes = self.live_raw + b"\n"
        second = c.correlate(self.backup_raw, changed_bytes)
        self.assertNotEqual(result["inputs"]["live"]["sha256"], second["inputs"]["live"]["sha256"])

    def test_actual_memory_placeholder_dynamic_overlap_and_padding_preserved(self):
        result = self.run_changed()
        memory = result["live_memory"]
        self.assertEqual(len(memory["banks"]), 2)
        self.assertEqual(len(memory["static_exclusion_union"]), 7)
        self.assertEqual(len(memory["dynamic_reservations"]), 12)
        self.assertEqual(len(memory["reservation_overlaps"]), 1)
        compared = result["base_dt_by_reported_index"]["memory_comparison"]
        self.assertEqual(compared["candidate"]["banks"], [])
        self.assertEqual(compared["candidate"]["zero_size_placeholders"], [{"path": "/memory", "start": 0, "size": 0}])
        self.assertEqual(compared["changed_reservation_nodes"], [])
        self.assertEqual(compared["live_bank_ranges_not_in_candidate"], memory["bank_union"])
        self.assertFalse(result["live_format"]["format_compliant"])
        self.assertEqual([x["offset"] for x in result["live_format"]["format_issues"]], [821109, 821537])

    def test_duplicate_same_commandline_key_is_ambiguous_not_first_wins(self):
        live = copy.deepcopy(self.live)
        values = live["boot_arguments"]["/proc/cmdline"]["observations"]["androidboot.dtb_idx"]
        values.append(copy.deepcopy(values[0]))
        result = self.run_changed(live=live)
        self.assertEqual(result["correlation_status"], "unresolved")
        self.assertIsNone(result["base_dt_by_reported_index"])
        self.assertIn("dtb_idx:duplicate-reported-key:/proc/cmdline", result["issues"])

    def test_conflicting_property_and_argument_is_unresolved(self):
        for prop, value in (("ro.boot.dtb_idx", {"indices": [1], "valid": True}),
                            ("ro.boot.dtbo_idx", {"indices": [3], "valid": True}),
                            ("ro.boot.slot_suffix", {"slot_suffix": "_b"})):
            live = copy.deepcopy(self.live)
            live["properties"][prop] = value
            with self.subTest(prop=prop):
                result = self.run_changed(live=live)
                self.assertEqual(result["correlation_status"], "unresolved")
                self.assertIsNone(result["reported_selection"][prop.removeprefix("ro.boot.")]["value"])

    def test_missing_every_index_does_not_choose_entry_zero(self):
        live = copy.deepcopy(self.live)
        live["properties"]["ro.boot.dtb_idx"] = {"present": False}
        live["boot_arguments"]["/proc/cmdline"]["observations"]["androidboot.dtb_idx"] = []
        result = self.run_changed(live=live)
        self.assertIsNone(result["base_dt_by_reported_index"])
        self.assertIn("dtb_idx:no-valid-reported-value", result["issues"])

    def test_unavailable_source_is_reported_without_overriding_valid_report(self):
        live = copy.deepcopy(self.live)
        live["properties"]["ro.boot.dtb_idx"] = {"unavailable": "read_failed"}
        result = self.run_changed(live=live)
        self.assertEqual(result["reported_selection"]["dtb_idx"]["value"], [0])
        self.assertEqual(result["reported_selection"]["dtb_idx"]["observations"][0]["state"], "unavailable")

    def test_invalid_bool_float_negative_duplicate_or_multiple_base_indices_block(self):
        for indices in ([True], [0.0], [-1], [2**32], [0, 0], [0, 1], []):
            live = copy.deepcopy(self.live)
            live["properties"]["ro.boot.dtb_idx"] = {"valid": True, "indices": indices}
            with self.subTest(indices=indices):
                result = self.run_changed(live=live)
                self.assertEqual(result["correlation_status"], "unresolved")
                self.assertIsNone(result["base_dt_by_reported_index"])

    def test_invalid_report_is_not_ignored_when_another_source_is_valid(self):
        live = copy.deepcopy(self.live)
        live["properties"]["ro.boot.dtbo_idx"] = {"valid": False}
        result = self.run_changed(live=live)
        self.assertIsNone(result["overlays_by_reported_indices"])
        self.assertIn("dtbo_idx:invalid-reported-value:ro.boot.dtbo_idx", result["issues"])

    def test_out_of_range_base_and_overlay_are_not_clamped_or_partially_used(self):
        for suffix, indices in (("dtb_idx", [100]), ("dtbo_idx", [2, 100])):
            live = copy.deepcopy(self.live)
            value = {"valid": True, "indices": indices}
            live["properties"]["ro.boot." + suffix] = value
            live["boot_arguments"]["/proc/cmdline"]["observations"]["androidboot." + suffix] = [value]
            result = self.run_changed(live=live)
            self.assertEqual(result["correlation_status"], "unresolved")
            field = "base_dt_by_reported_index" if suffix == "dtb_idx" else "overlays_by_reported_indices"
            self.assertIsNone(result[field])

    def test_overlay_order_is_preserved_and_conflicting_order_is_not_sorted_away(self):
        live = copy.deepcopy(self.live)
        live["properties"]["ro.boot.dtbo_idx"] = {"valid": True, "indices": [2, 3]}
        live["boot_arguments"]["/proc/cmdline"]["observations"]["androidboot.dtbo_idx"] = [{"valid": True, "indices": [2, 3]}]
        result = self.run_changed(live=live)
        self.assertEqual([x["index"] for x in result["overlays_by_reported_indices"]["entries"]], [2, 3])
        live["boot_arguments"]["/proc/cmdline"]["observations"]["androidboot.dtbo_idx"][0]["indices"] = [3, 2]
        self.assertIsNone(self.run_changed(live=live)["overlays_by_reported_indices"])

    def test_duplicate_json_key_and_nonfinite_number_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(c.CorrelationError):
                c.correlate(self.backup_raw, raw)

    def test_duplicate_or_bool_entry_indices_rejected(self):
        for index in (0, True, 1.0):
            backup = copy.deepcopy(self.backup)
            backup["images"]["boot_a"]["components"]["dtb"]["inspection"]["entries"][1]["index"] = index
            with self.subTest(index=index), self.assertRaises(c.CorrelationError):
                self.run_changed(backup=backup)

    def test_parser_or_wrapper_identity_mismatch_rejected(self):
        live = copy.deepcopy(self.live)
        live["parser_sha256"] = "0" * 64
        with self.assertRaises(c.CorrelationError):
            self.run_changed(live=live)
        live = copy.deepcopy(self.live)
        live["running_fdt"]["bytes"] = True
        with self.assertRaises(c.CorrelationError):
            self.run_changed(live=live)

    def test_false_stability_or_expanded_proof_scope_rejected(self):
        for key, value in (("physical_mainline_linux_tested", True), ("owner_native_linux_passes_added", True)):
            live = copy.deepcopy(self.live)
            live[key] = value
            with self.subTest(key=key), self.assertRaises(c.CorrelationError):
                self.run_changed(live=live)
        live = copy.deepcopy(self.live)
        live["running_fdt"]["stable_across_two_reads"] = False
        with self.assertRaises(c.CorrelationError):
            self.run_changed(live=live)

    def test_duplicate_memory_node_or_forged_union_rejected(self):
        for variant in ("duplicate", "union"):
            live = copy.deepcopy(self.live)
            dt = live["running_fdt"]["inspection"]
            if variant == "duplicate":
                dt["reserved_memory"]["nodes"].append(copy.deepcopy(dt["reserved_memory"]["nodes"][0]))
            else:
                dt["described_static_exclusion_union"][0]["size"] += 1
            with self.subTest(variant=variant), self.assertRaises(c.CorrelationError):
                self.run_changed(live=live)

    def test_forensic_padding_output_cannot_smuggle_private_bytes(self):
        live = copy.deepcopy(self.live)
        live["running_fdt"]["inspection"]["format_issues"][0]["raw"] = "private secret"
        with self.assertRaises(c.CorrelationError):
            self.run_changed(live=live)
        live = copy.deepcopy(self.live)
        live["boot_arguments"]["/proc/bootconfig"]["observations"] = {"androidboot.dtb_idx": [{"valid": True, "indices": [1]}]}
        with self.assertRaises(c.CorrelationError):
            self.run_changed(live=live)

    def test_interval_difference_handles_holes_overlap_and_u64_top(self):
        self.assertEqual(c.subtract([{"start": 0, "size": 10}], [{"start": 2, "size": 3}, {"start": 7, "size": 8}]),
                         [{"start": 0, "size": 2}, {"start": 5, "size": 2}])
        self.assertEqual(c.subtract([{"start": 2**64 - 4, "size": 4}], [{"start": 2**64 - 2, "size": 2}]),
                         [{"start": 2**64 - 4, "size": 2}])


if __name__ == "__main__":
    unittest.main()
