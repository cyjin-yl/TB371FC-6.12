#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Adversarial format/memory-map tests; fixtures are not physical boot evidence."""
import gzip
import hashlib
import json
import struct
import unittest
from unittest.mock import patch
import zlib

import native_dt as nd


def cells(*values):
    return struct.pack(">" + "I" * len(values), *values)


def reg(start, size, ac=2, sc=2):
    return start.to_bytes(ac * 4, "big") + size.to_bytes(sc * 4, "big")


def node(name="", props=None, children=()):
    return (name, list((props or {}).items()) if isinstance(props, dict) else list(props or []), list(children))


def fdt(tree=None, memreserve=()):
    if tree is None:
        tree = board()
    names, strings = {}, bytearray()

    def emit(n):
        name, props, children = n
        output = bytearray(cells(1) + name.encode("ascii") + b"\0")
        output.extend(bytes(-len(output) % 4))
        for prop, raw in props:
            if prop not in names:
                names[prop] = len(strings)
                strings.extend(prop.encode("ascii") + b"\0")
            output.extend(cells(3, len(raw), names[prop]) + raw)
            output.extend(bytes(-len(output) % 4))
        for child in children:
            output.extend(emit(child))
        output.extend(cells(2))
        return output

    structure = emit(tree) + cells(9)
    reserved = b"".join(struct.pack(">QQ", *r) for r in memreserve) + bytes(16)
    struct_offset = 40 + len(reserved)
    strings_offset = struct_offset + len(structure)
    header = cells(nd.FDT_MAGIC, strings_offset + len(strings), struct_offset,
                   strings_offset, 40, 17, 16, 0, len(strings), len(structure))
    return bytes(header + reserved + structure + strings)


def board(*, memory=None, reservations=None, chosen=None, root_extra=None,
          reserved_extra=None, root_cells=(2, 2)):
    props = {"compatible": b"lenovo,tb371fc\0qcom,sm8250\0",
             "model": b"Lenovo TB371FC fixture\0",
             "#address-cells": cells(root_cells[0]), "#size-cells": cells(root_cells[1]),
             "qcom,msm-id": cells(356, 0x20000), "qcom,board-id": cells(1, 0)}
    props.update(root_extra or {})
    children = [node("memory@80000000", memory if memory is not None else {
        "device_type": b"memory\0", "reg": reg(0x80000000, 0x100000000, *root_cells)})]
    if reservations is not None:
        rp = {"#address-cells": cells(root_cells[0]), "#size-cells": cells(root_cells[1]), "ranges": b""}
        rp.update(reserved_extra or {})
        children.append(node("reserved-memory", rp, reservations))
    if chosen is not None:
        children.append(node("chosen", chosen))
    return node(props=props, children=children)


def table(payloads, version=0, compression=None, shared=None, padding=b""):
    compression = compression or [0] * len(payloads)
    count = len(payloads)
    pos = 32 + 32 * count
    entries, body, locations = [], bytearray(), []
    for i, (payload, method) in enumerate(zip(payloads, compression)):
        stored = zlib.compress(payload) if method == 1 else gzip.compress(payload, mtime=0) if method == 2 else payload
        if shared is not None and i in shared:
            offset, size = locations[shared[i]]
        else:
            offset, size = pos, len(stored)
            body.extend(stored)
            pos += size
        locations.append((offset, size))
        optional = [method, 11, 12, 13] if version else [10, 11, 12, 13]
        entries.append(cells(size, offset, 100 + i, i, *optional))
    return cells(nd.DT_TABLE_MAGIC, pos, 32, 32, count, 32, 4096, version) + b"".join(entries) + bytes(body) + padding


def overwrite(raw, offset, value):
    changed = bytearray(raw)
    struct.pack_into(">I", changed, offset, value)
    return bytes(changed)


class FdtMetadataTests(unittest.TestCase):
    def test_real_shaped_memory_and_private_field_exclusion(self):
        raw = fdt(board(reservations=[
            node("firmware@90000000", {"reg": reg(0x90000000, 0x20000), "no-map": b""}),
            node("cma", {"size": (0x8000000).to_bytes(8, "big"), "alignment": (0x200000).to_bytes(8, "big"),
                         "alloc-ranges": reg(0xA0000000, 0x10000000), "reusable": b""})],
            chosen={"linux,initrd-start": (0xC0000000).to_bytes(8, "big"),
                    "linux,initrd-end": (0xC1000000).to_bytes(8, "big"),
                    "bootargs": b"private_cmdline_secret=secret\0",
                    "rng-seed": b"private_entropy_secret", "kaslr-seed": b"secrets!",
                    "stdout-path": b"private_uart_secret\0"},
            root_extra={"serial-number": b"private_serial_secret\0"}),
            memreserve=[(0x91000000, 4096)])
        result = nd.inspect_fdt(raw)
        self.assertEqual(result["bytes"], len(raw))
        self.assertEqual(result["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["memory"][0]["reg"], [{"start": 0x80000000, "size": 0x100000000}])
        self.assertEqual(result["reserved_memory"]["nodes"][1]["allocation"], "dynamic")
        self.assertIn("reserved-memory-allocation-unresolved", result["memory_map_issues"])
        self.assertEqual(result["chosen_numeric"]["linux,initrd-end"], 0xC1000000)
        self.assertEqual(len(result["described_static_exclusion_union"]), 2)
        self.assertNotIn("secret", json.dumps(result))
        self.assertFalse(result["runtime_selection_verified"])
        self.assertEqual(result["owner_native_linux_passes_added"], 0)

    def test_overlay_without_root_compatible_is_not_a_selected_full_tree(self):
        raw = fdt(node(children=[node("fragment@0", {"target": cells(0xFFFFFFFF)}, [
            node("__overlay__", {"status": b"okay\0"})]), node("__fixups__", {"uart": b"/fragment@0:target:0\0"})]))
        result = nd.inspect_fdt(raw)
        self.assertEqual(result["compatible"], [])
        self.assertEqual(result["overlay_fragments"], 1)
        self.assertTrue(result["external_fixups_present"])
        self.assertIn("overlay-not-applied", result["memory_map_issues"])
        self.assertFalse(result["overlay_application_performed"])

    def test_32bit_memory_cells_are_decoded_by_parent(self):
        result = nd.inspect_fdt(fdt(board(memory={"device_type": b"memory\0", "reg": reg(0x80000000, 0x10000000, 1, 1)}, root_cells=(1, 1))))
        self.assertEqual(result["memory"][0]["reg"], [{"start": 0x80000000, "size": 0x10000000}])
        self.assertEqual(result["root_cells"]["address"], 1)

    def test_missing_root_cells_use_spec_defaults_not_descendant_cells(self):
        result = nd.inspect_fdt(fdt(node(children=[node("memory@80000000", {
            "device_type": b"memory\0", "reg": reg(0x80000000, 0x10000000, 2, 1),
            "#address-cells": cells(1), "#size-cells": cells(2)})])))
        self.assertEqual(result["root_cells"], {"address": 2, "size": 1, "address_explicit": False, "size_explicit": False})
        self.assertEqual(result["memory"][0]["reg"][0]["size"], 0x10000000)

    def test_disabled_memory_and_reservations_do_not_become_active_ranges(self):
        result = nd.inspect_fdt(fdt(board(memory={"device_type": b"memory\0", "reg": reg(0x80000000, 0x1000), "status": b"disabled\0"},
            reservations=[node("private@90000000", {"reg": reg(0x90000000, 0x1000), "status": b"disabled\0"})])))
        self.assertFalse(result["memory"][0]["enabled"])
        self.assertEqual(result["described_static_exclusion_union"], [])
        self.assertIn("no-positive-enabled-memory-reg", result["memory_map_issues"])

    def test_reserved_parent_disabled_disables_children(self):
        result = nd.inspect_fdt(fdt(board(reservations=[node("firmware", {"reg": reg(0x90000000, 0x1000)})], reserved_extra={"status": b"disabled\0"})))
        self.assertFalse(result["reserved_memory"]["nodes"][0]["enabled"])
        self.assertEqual(result["described_static_exclusion_union"], [])

    def test_nonempty_ranges_are_not_mistaken_for_physical_addresses(self):
        result = nd.inspect_fdt(fdt(board(reservations=[node("firmware", {"reg": reg(0x90000000, 0x1000)})], reserved_extra={"ranges": bytes(24)})))
        self.assertFalse(result["reserved_memory"]["identity_address_translation"])
        self.assertEqual(result["described_static_exclusion_union"], [])
        self.assertIn("reserved-memory-address-translation-unqualified", result["memory_map_issues"])

    def test_reserved_cells_must_be_explicit_even_when_defaults_match(self):
        raw = fdt(node(props={"#address-cells": cells(2), "#size-cells": cells(1)}, children=[
            node("reserved-memory", {"ranges": b""}, [
                node("firmware", {"reg": reg(0x90000000, 0x1000, 2, 1)})])]))
        result = nd.inspect_fdt(raw)
        self.assertTrue(result["reserved_memory"]["cell_counts_match_root"])
        self.assertFalse(result["reserved_memory"]["address_cells_explicit"])
        self.assertIn("reserved-memory-address-translation-unqualified", result["memory_map_issues"])
        self.assertEqual(result["described_static_exclusion_union"], [])

    def test_zero_size_placeholder_and_reg_priority_remain_explicit(self):
        result = nd.inspect_fdt(fdt(board(memory={"device_type": b"memory\0", "reg": reg(0, 0)},
            reservations=[node("carveout", {"reg": reg(0x90000000, 0), "size": (4096).to_bytes(8, "big")})])))
        self.assertTrue(result["memory"][0]["zero_size_placeholder"])
        item = result["reserved_memory"]["nodes"][0]
        self.assertTrue(item["reg_takes_precedence_over_size"])
        self.assertEqual(item["allocation"], "static")
        self.assertEqual(result["described_static_exclusion_union"], [])

    def test_overlapping_reservations_are_visible_and_union_is_conservative(self):
        result = nd.inspect_fdt(fdt(board(reservations=[node("a", {"reg": reg(0x90000000, 0x2000)}), node("b", {"reg": reg(0x90001000, 0x4000)})]), memreserve=[(0x90000000, 0x1000)]))
        self.assertEqual(len(result["reservation_overlaps"]), 2)
        self.assertEqual(result["described_static_exclusion_union"], [{"start": 0x90000000, "size": 0x5000}])
        self.assertIn("overlapping-reservation-declarations", result["memory_map_issues"])

    def test_reserved_boolean_conflict_and_nonempty_boolean_rejected(self):
        for props in ({"no-map": b"", "reusable": b""}, {"no-map": cells(1)}):
            with self.subTest(props=props), self.assertRaises(nd.DTError):
                nd.inspect_fdt(fdt(board(reservations=[node("a", dict(props, reg=reg(0x90000000, 0x1000)))])))

    def test_malformed_cell_widths_ranges_and_overflow_rejected(self):
        malformed = [board(root_extra={"#address-cells": cells(3)}),
                     board(root_extra={"#size-cells": b"\0"}),
                     board(memory={"device_type": b"memory\0", "reg": bytes(12)}),
                     board(memory={"device_type": b"memory\0", "reg": reg((1 << 64) - 1, 2)}),
                     board(root_extra={"qcom,board-id": b"\x01"})]
        for tree in malformed:
            with self.subTest(tree=tree), self.assertRaises(nd.DTError):
                nd.inspect_fdt(fdt(tree))

    def test_chosen_bad_initrd_pair_is_unresolved_not_success(self):
        result = nd.inspect_fdt(fdt(board(chosen={"linux,initrd-start": cells(0x1000), "linux,initrd-end": cells(0x100)})))
        self.assertIn("chosen-initrd-pair-invalid-or-incomplete", result["memory_map_issues"])
        with self.assertRaises(nd.DTError):
            nd.inspect_fdt(fdt(board(chosen={"linux,initrd-start": b"\0\0"})))

    def test_duplicate_properties_and_nodes_rejected(self):
        for tree in (node(props=[("compatible", b"x\0"), ("compatible", b"y\0")]),
                     node(children=[node("same"), node("same")])):
            with self.subTest(tree=tree), self.assertRaises(nd.DTError):
                nd.inspect_fdt(fdt(tree))

    def test_truncated_wrong_version_or_overlapping_sections_rejected(self):
        good = fdt()
        bad = [good[:-1], overwrite(good, 20, 16), overwrite(good, 12, 40),
               overwrite(good, 16, 56), overwrite(good, 8, 41),
               overwrite(good, 4, len(good) + 1), b"", bytearray(good)]
        for raw in bad:
            with self.subTest(length=len(raw)), self.assertRaises(nd.DTError):
                nd.inspect_fdt(raw)

    def test_bad_token_and_early_end_rejected(self):
        good = fdt()
        for tag in (0, 2, 9, 0xDEADBEEF):
            with self.subTest(tag=tag), self.assertRaises(nd.DTError):
                nd.inspect_fdt(overwrite(good, 56, tag))

    def test_property_padding_diagnostic_is_distinct_from_extent_without_bytes(self):
        good = fdt(node(props={"private-name": b"Q"}))
        padded = bytearray(good)
        self.assertEqual(padded[76:80], b"Q\0\0\0")
        padded[77] = ord("S")
        with self.assertRaisesRegex(nd.DTError, "nonzero FDT property padding at offset 77 length 3 nonzero_count 1") as ctx:
            nd.inspect_fdt(bytes(padded))
        self.assertNotIn("private-name", str(ctx.exception))
        with self.assertRaisesRegex(nd.DTError, "FDT property extent exceeds structure"):
            nd.inspect_fdt(overwrite(good, 68, 0xFFFFFFFF))

    def test_live_padding_mode_is_explicit_noncompliant_and_numeric_only(self):
        raw = bytearray(fdt(node(props={"private-name": b"Q"})))
        raw[77:80] = b"XYZ"
        with self.assertRaisesRegex(nd.DTError, "nonzero FDT property padding"):
            nd.inspect_fdt(bytes(raw))
        result = nd.inspect_fdt(bytes(raw), allow_nonzero_padding=True)
        self.assertFalse(result["format_compliant"])
        self.assertTrue(result["diagnostic_nonzero_padding_allowed"])
        self.assertEqual(result["format_issues"], [{"offset": 77, "length": 3, "nonzero_count": 3}])
        self.assertNotIn("XYZ", json.dumps(result))
        self.assertNotIn("private-name", json.dumps(result))
        self.assertFalse(result["runtime_selection_verified"])
        for bundle in (bytes(raw), table([bytes(raw)])):
            with self.assertRaisesRegex(nd.DTError, "nonzero FDT property padding"):
                nd.inspect_dt_bundle(bundle)

    def test_live_padding_mode_retains_extent_duplicate_and_type_checks(self):
        good = fdt(node(props={"private-name": b"Q"}))
        duplicate = fdt(node(props=[("x", b"y"), ("x", b"z")]))
        for raw in (overwrite(good, 68, 0xFFFFFFFF), duplicate, overwrite(good, 8, 41)):
            with self.subTest(raw=raw[:40]), self.assertRaises(nd.DTError):
                nd.inspect_fdt(raw, allow_nonzero_padding=True)
        with self.assertRaisesRegex(nd.DTError, "must be bool"):
            nd.inspect_fdt(good, allow_nonzero_padding=1)
        pristine = nd.inspect_fdt(good)
        self.assertTrue(pristine["format_compliant"])
        self.assertFalse(pristine["diagnostic_nonzero_padding_allowed"])
        self.assertEqual(pristine["format_issues"], [])


class BundleTests(unittest.TestCase):
    def test_concat_uses_totalsize_without_implicit_alignment(self):
        first, second = fdt(), fdt(board(root_extra={"model": b"Second fixture\0"}))
        self.assertNotEqual(len(first) % 4, 0)
        result = nd.inspect_dt_bundle(first + second)
        self.assertEqual(result["entry_count"], 2)
        self.assertEqual(result["entries"][1]["offset"], len(first))
        self.assertEqual(result["entries"][1]["dt"]["model"], "Second fixture")
        self.assertFalse(result["runtime_selection_verified"])
        with self.assertRaises(nd.DTError):
            nd.inspect_dt_bundle(first + bytes(-len(first) % 4) + second)

    def test_concat_bad_second_header_extent_and_tail_rejected(self):
        good = fdt()
        for raw in (good + b"\0", good + good[:20], good + overwrite(good, 4, len(good) + 1)):
            with self.subTest(length=len(raw)), self.assertRaises(nd.DTError):
                nd.inspect_dt_bundle(raw)

    def test_v0_table_and_explicit_partition_tail(self):
        good = table([fdt(), fdt(board(root_extra={"model": b"Second\0"}))])
        result = nd.inspect_dt_bundle(good)
        self.assertEqual(result["kind"], "android-dt-table")
        self.assertEqual(result["entries"][0]["custom"], [10, 11, 12, 13])
        self.assertEqual(result["entries"][1]["index"], 1)
        with self.assertRaises(nd.DTError):
            nd.inspect_dt_bundle(good + b"AVBf_private_tail")
        padded = nd.inspect_dt_table(good + b"AVBf_private_tail", allow_partition_tail=True)
        self.assertEqual(padded["partition_tail"]["bytes"], 17)
        self.assertFalse(padded["partition_tail"]["avb_verified"])
        self.assertNotIn("private_tail", json.dumps(padded))

    def test_v1_zlib_gzip_and_uncompressed_are_exact(self):
        payload = fdt()
        result = nd.inspect_dt_table(table([payload] * 3, version=1, compression=[0, 1, 2]))
        self.assertEqual([e["compression"] for e in result["entries"]], [0, 1, 2])
        self.assertEqual({e["dt"]["sha256"] for e in result["entries"]}, {hashlib.sha256(payload).hexdigest()})
        self.assertEqual(result["entries"][0]["custom"], [11, 12, 13])

    def test_exact_shared_payload_allowed_but_partial_overlap_rejected(self):
        good = table([fdt()] * 2, shared={1: 0})
        result = nd.inspect_dt_table(good)
        self.assertEqual(result["unique_payload_count"], 1)
        self.assertEqual(result["entries"][0]["sha256"], result["entries"][1]["sha256"])
        with self.assertRaises(nd.DTError):
            nd.inspect_dt_table(overwrite(good, 64 + 4, 97))

    def test_metadata_overlap_unknown_flags_and_header_shapes_rejected(self):
        v0, v1 = table([fdt()]), table([fdt()], version=1)
        invalid = [overwrite(v0, 36, 32), overwrite(v0, 8, 36),
                   overwrite(v0, 12, 36), overwrite(v0, 16, 1025),
                   overwrite(v0, 20, 0xFFFFFFFC), overwrite(v0, 24, 123),
                   overwrite(v0, 28, 2), overwrite(v1, 48, 0x10), overwrite(v1, 48, 3),
                   overwrite(v0, 32, 0), overwrite(v0, 32, 0xFFFFFFFF)]
        for raw in invalid:
            with self.subTest(header=raw[:32]), self.assertRaises(nd.DTError):
                nd.inspect_dt_table(raw)
        with self.assertRaises(nd.DTError):
            nd.inspect_dt_table(v0, allow_partition_tail=1)

    def test_shared_payload_cannot_have_conflicting_compression(self):
        raw = table([fdt()] * 2, version=1, shared={1: 0})
        with self.assertRaises(nd.DTError):
            nd.inspect_dt_table(overwrite(raw, 64 + 16, 1))

    def test_compression_bomb_truncation_and_concatenated_stream_rejected(self):
        def compressed_table(payload):
            return cells(nd.DT_TABLE_MAGIC, 64 + len(payload), 32, 32, 1, 32, 4096, 1) + cells(len(payload), 64, 0, 0, 1, 0, 0, 0) + payload
        for stored in (zlib.compress(bytes(nd.MAX_FDT_BYTES + 1)), zlib.compress(fdt())[:-2],
                       zlib.compress(fdt()) + zlib.compress(fdt()), gzip.compress(fdt())):
            with self.subTest(length=len(stored)), self.assertRaises(nd.DTError):
                nd.inspect_dt_table(compressed_table(stored))

    def test_decoded_aggregate_budget_is_enforced_for_unique_spans(self):
        raw = table([fdt()] * 2, version=1, compression=[1, 1])
        with patch.object(nd, "MAX_DECODED_TABLE_BYTES", len(fdt()) * 2 - 1):
            with self.assertRaisesRegex(nd.DTError, "aggregate"):
                nd.inspect_dt_table(raw)
        shared = table([fdt()] * 2, version=1, compression=[1, 1], shared={1: 0})
        with patch.object(nd, "MAX_DECODED_TABLE_BYTES", len(fdt())):
            self.assertEqual(nd.inspect_dt_table(shared)["entry_count"], 2)


if __name__ == "__main__":
    unittest.main()
