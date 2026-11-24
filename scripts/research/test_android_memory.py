# SPDX-License-Identifier: GPL-2.0-only
import copy
import json
import unittest

from android_memory import compare, parse_cpu_list, parse_iomem, parse_meminfo, subtract, union


class MemoryParsingTests(unittest.TestCase):
    def test_iomem_inclusive_end_and_over_4g(self):
        parsed = parse_iomem(b"80000000-80000fff : System RAM\n  80000800-80000fff : reserved\n100000000-100001fff : System RAM\n")
        self.assertEqual(parsed["system_ram"][0]["end"], 0x80001000)
        self.assertEqual(parsed["system_ram"][1]["end"], 0x100002000)
        self.assertEqual(parsed["ram_children"][0]["end"] - parsed["ram_children"][0]["start"], 2048)

    def test_private_unknown_resource_label_not_returned(self):
        parsed = parse_iomem(b"80000000-80000fff : System RAM\n  80000800-80000fff : personal-secret-label\n")
        self.assertNotIn("personal-secret-label", json.dumps(parsed))
        self.assertEqual(parsed["ram_children"][0]["kind"], "other")

    def test_redacted_addresses_are_not_one_byte_memory(self):
        parsed = parse_iomem(b"00000000-00000000 : System RAM\n  00000000-00000000 : Kernel code\n00000000-00000000 : System RAM\n")
        self.assertFalse(parsed["geometry_qualified"])
        self.assertEqual(parsed["system_ram"], [])

    def test_bad_resource_tree_rejected(self):
        cases = (
            b"80000000-80000fff : System RAM\n  80001000-80001fff : reserved\n",
            b"80000000-80000fff : System RAM\n80000800-80001fff : System RAM\n",
            b"  80000000-80000fff : System RAM\n",
            b"80000fff-80000000 : System RAM\n",
            b"80000000-80000fff : System RAM\nmalformed\n",
            b"80000000-80000fff : System RAM\n" * 5000,
        )
        for data in cases:
            with self.subTest(data=data[:90]), self.assertRaises(ValueError):
                parse_iomem(data)

    def test_repeated_child_geometry_is_not_double_counted(self):
        parsed = parse_iomem(b"80000000-80000fff : System RAM\n  80000800-80000fff : reserved\n    80000800-80000fff : reserved\n")
        self.assertEqual(union((row["start"], row["end"]) for row in parsed["ram_children"]), [(0x80000800, 0x80001000)])

    def test_full_width_last_address_can_be_exclusive_u64_end(self):
        parsed = parse_iomem(b"fffffffffffff000-ffffffffffffffff : System RAM\n")
        self.assertEqual(parsed["system_ram"][0]["end"], 1 << 64)

    def test_meminfo_units_and_allowlist(self):
        data = b"MemTotal:        7891124 kB\nCmaTotal:         356352 kB\nPrivateCounter: 12345 kB\n"
        self.assertEqual(parse_meminfo(data), {"MemTotal": 8080510976, "CmaTotal": 364904448})

    def test_duplicate_or_wrong_unit_meminfo_rejected(self):
        for data in (b"MemTotal: 3 MB\n", b"MemTotal: 3 kB\nMemTotal: 4 kB\n", b"CmaTotal: 3 kB\n"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_meminfo(data)

    def test_cpu_list_and_empty_offline(self):
        self.assertEqual(parse_cpu_list(b"0-3,7\n"), [0, 1, 2, 3, 7])
        self.assertEqual(parse_cpu_list(b"\n"), [])
        for data in (b"0-99", b"7-2", b"0-3,3", b"0,,1", b"-1"):
            with self.subTest(data=data), self.assertRaises(ValueError):
                parse_cpu_list(data)

    def test_subtraction_boundaries_and_union(self):
        self.assertEqual(subtract([(0x80000000, 0x90000000)], [(0x7ff00000, 0x81000000), (0x88000000, 0x8a000000)]),
                         [(0x81000000, 0x88000000), (0x8a000000, 0x90000000)])
        self.assertEqual(union([(100, 200), (200, 250), (120, 180)]), [(100, 250)])
        with self.assertRaises(ValueError):
            union([(False, 10)])


def fixtures():
    dt = {"schema": "tb371fc-android-native-dt-observation-v1", "kernel_release": "fixture",
          "running_fdt": {"stable_across_two_reads": True, "sha256": "a" * 64, "bytes": 1024,
                          "inspection": {
                              "memory": [{"enabled": True, "reg": [{"start": 0x80000000, "size": 0x10000000}]}],
                              "reserved_memory": {"physical_address_interpretation_qualified": True, "nodes": [
                                  {"enabled": True, "allocation": "static", "no_map": True,
                                   "reg": [{"start": 0x80000000, "size": 0x01000000}]},
                                  {"path": "/reserved-memory/a", "enabled": True, "allocation": "dynamic",
                                   "no_map": False, "reusable": True, "size": 0x01000000},
                                  {"path": "/reserved-memory/b", "enabled": True, "allocation": "dynamic",
                                   "no_map": False, "reusable": True, "size": 0x01000000},
                                  {"path": "/reserved-memory/mailbox", "enabled": True, "allocation": "dynamic",
                                   "no_map": True, "reusable": False, "size": 0x20000,
                                   "alignment": 0x400000, "alloc_ranges": [{"start": 0, "size": 1 << 32}]},
                              ]}}}}
    memory = {"schema": "tb371fc-android-memory-observation-v1", "kernel_release": "fixture", "capture_utc": "fixture",
              "fdt": {"stable_across_two_reads": True, "sha256": "a" * 64, "bytes": 1024},
              "iomem": {"stable_across_two_reads": True, "parsed": parse_iomem(
                  b"81000000-8bffffff : System RAM\n  8a000000-8bffffff : reserved\n8c020000-8fffffff : System RAM\n")},
              "meminfo": {"values_bytes": {"MemTotal": 0x0e000000, "CmaTotal": 0x02000000}}}
    return dt, memory


class CorrelationTests(unittest.TestCase):
    def test_aggregate_geometry_does_not_resolve_allocation_ownership(self):
        dt, observation = fixtures()
        result = compare(dt, observation)
        self.assertTrue(result["cma_total_equals_dynamic_reusable_request_sum"])
        self.assertEqual(result["reserved_children_equal_to_cma_request_sum"], [{"start": 0x8a000000, "end": 0x8c000000, "size": 0x02000000}])
        self.assertEqual(result["dynamic_no_map_gap_candidates"][0]["matching_gap_geometry"], [{"start": 0x8c000000, "end": 0x8c020000, "size": 0x20000}])
        self.assertEqual(result["individual_dynamic_allocations_resolved"], 0)
        self.assertFalse(result["complete_memory_ownership_verified"])
        self.assertFalse(result["safe_load_addresses_selected"])
        self.assertEqual(result["owner_native_linux_passes_added"], 0)

    def test_size_match_outside_alloc_range_does_not_become_candidate(self):
        dt, observation = fixtures()
        dt["running_fdt"]["inspection"]["reserved_memory"]["nodes"][-1]["alloc_ranges"] = [{"start": 0, "size": 0x80000000}]
        result = compare(dt, observation)
        self.assertEqual(result["dynamic_no_map_gap_candidates"][0]["matching_gap_geometry"], [])

    def test_exact_fdt_and_stability_are_required(self):
        dt, observation = fixtures()
        changes = [("fdt", "sha256", "b" * 64), ("fdt", "bytes", 2048),
                   ("fdt", "stable_across_two_reads", False), ("iomem", "stable_across_two_reads", False)]
        for group, key, value in changes:
            bad = copy.deepcopy(observation)
            bad[group][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                compare(dt, bad)

    def test_redacted_resources_rejected_for_correlation(self):
        dt, observation = fixtures()
        observation["iomem"]["parsed"] = parse_iomem(b"00000000-00000000 : System RAM\n")
        with self.assertRaises(ValueError):
            compare(dt, observation)

    def test_meminfo_cma_mismatch_is_reported_not_hidden(self):
        dt, observation = fixtures()
        observation["meminfo"]["values_bytes"]["CmaTotal"] += 4096
        self.assertFalse(compare(dt, observation)["cma_total_equals_dynamic_reusable_request_sum"])


if __name__ == "__main__":
    unittest.main()
