#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Offline boundary and mismatched-candidate checks; no hardware or root needed."""
import copy
import struct
import unittest

import boot_formats as formats


def image(*, stored=80, effective=2 * formats.MIB, text_offset=0, flags=10):
    raw = bytearray(stored)
    struct.pack_into("<6Q", raw, 8, text_offset, effective, flags, 0, 0, 0)
    raw[56:60] = b"ARM\x64"
    return bytes(raw)


class Tree:
    """Small fixture encoder independent of the parser's state machine."""
    def __init__(self):
        self.body = bytearray()
        self.names = bytearray()

    def begin(self, name):
        self.body.extend(struct.pack(">I", 1) + name.encode("ascii") + b"\0")
        self.body.extend(b"\0" * (-len(self.body) % 4))
        return self

    def prop(self, name, value):
        offset = len(self.names)
        self.names.extend(name.encode("ascii") + b"\0")
        self.body.extend(struct.pack(">III", 3, len(value), offset) + value)
        self.body.extend(b"\0" * (-len(self.body) % 4))
        return self

    def end(self):
        self.body.extend(struct.pack(">I", 2))
        return self

    def finish(self, *, reservations=(), tail=b"", reserve_terminator=True):
        body = self.body + struct.pack(">I", 9) + tail
        reserve = b"".join(struct.pack(">QQ", a, b) for a, b in reservations)
        if reserve_terminator:
            reserve += bytes(16)
        off_body = 40 + len(reserve)
        off_names = off_body + len(body)
        total = off_names + len(self.names)
        return (struct.pack(">10I", 0xD00DFEED, total, off_body, off_names, 40,
                            17, 16, 0, len(self.names), len(body))
                + reserve + body + self.names)


def board(*, compatible=b"lenovo,tb371fc\0qcom,sm8250\0", model=True):
    tree = Tree().begin("").prop("compatible", compatible)
    if model:
        tree.prop("model", b"Lenovo TB371FC\0")
    return tree


def header_edit(raw, index, value):
    data = bytearray(raw)
    struct.pack_into(">I", data, index * 4, value)
    return bytes(data)


class ImageTests(unittest.TestCase):
    def test_r5_effective_tail_is_valid_and_remains_distinct(self):
        # The source evidence records these exact lengths; this is synthetic,
        # zero-filled input, not a claim to possess or execute the R5 Image.
        result = formats.parse_arm64_image(image(stored=41091080, effective=42729472))
        self.assertEqual(result["stored_bytes"], 41091080)
        self.assertEqual(result["image_size"], 42729472)
        self.assertEqual(result["text_offset"], 0)
        self.assertEqual(result["page_size"], 4096)
        self.assertEqual(result["endianness"], "little")
        self.assertTrue(result["placement_anywhere_in_48bit_range"])
        self.assertFalse(result["efi_entry_verified"])

    def test_rejects_truncated_wrong_magic_legacy_and_smaller_extent(self):
        broken = [b"ARM\x64", bytes(64), image(effective=0), image(effective=64)]
        for data in broken:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                formats.parse_arm64_image(data)

    def test_rejects_reserved_bits_and_fields(self):
        with self.assertRaisesRegex(ValueError, "reserved.*flags"):
            formats.parse_arm64_image(image(flags=0x1A))
        raw = bytearray(image())
        struct.pack_into("<Q", raw, 32, 1)
        with self.assertRaisesRegex(ValueError, "reserved.*fields"):
            formats.parse_arm64_image(bytes(raw))

    def test_header_does_not_claim_efi_validation(self):
        raw = bytearray(image())
        struct.pack_into("<I", raw, 60, 64)
        result = formats.parse_arm64_image(bytes(raw))
        self.assertEqual(result["pe_header_offset"], 64)
        self.assertFalse(result["efi_entry_verified"])


class FdtTests(unittest.TestCase):
    def test_real_root_and_reservations_are_returned(self):
        raw = (board().begin("soc@0").prop("compatible", b"simple-bus\0")
               .end().end().finish(reservations=[(0x88000000, 0x100000)]))
        result = formats.parse_fdt(raw)
        self.assertEqual(result["compatible"], ["lenovo,tb371fc", "qcom,sm8250"])
        self.assertEqual(result["model"], "Lenovo TB371FC")
        self.assertEqual(result["reservations"], [{"start": 0x88000000, "size": 0x100000}])
        self.assertEqual(result["node_count"], 2)
        formats.require_root_compatible(result, "lenovo,tb371fc")

    def test_first_stage_tree_cannot_borrow_child_compatible(self):
        raw = (board(compatible=b"qcom,kona-qrd\0qcom,kona\0")
               .begin("decoy").prop("compatible", b"lenovo,tb371fc\0")
               .end().end().finish())
        result = formats.parse_fdt(raw)
        self.assertNotIn("lenovo,tb371fc", result["compatible"])
        with self.assertRaisesRegex(ValueError, "selected board"):
            formats.require_root_compatible(result, "lenovo,tb371fc")

    def test_model_may_be_absent_without_inventing_identity(self):
        self.assertIsNone(formats.parse_fdt(board(model=False).end().finish())["model"])

    def test_rejects_missing_or_unterminated_root_stringlist(self):
        broken = [Tree().begin("").end().finish(),
                  board(compatible=b"lenovo,tb371fc").end().finish(),
                  board(compatible=b"lenovo,tb371fc\0\0").end().finish()]
        for raw in broken:
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                formats.parse_fdt(raw)

    def test_rejects_duplicate_property_node_and_late_property(self):
        broken = [board().prop("compatible", b"qcom,sm8250\0").end().finish(),
                  board().begin("child").end().begin("child").end().end().finish(),
                  board().begin("child").end().prop("late", b"value\0").end().finish()]
        for raw in broken:
            with self.subTest(length=len(raw)), self.assertRaises(ValueError):
                formats.parse_fdt(raw)

    def test_rejects_extra_root_and_named_root(self):
        broken = [board().end().begin("").end().finish(),
                  Tree().begin("not-root").prop("compatible", b"lenovo,tb371fc\0").end().finish()]
        for raw in broken:
            with self.assertRaisesRegex(ValueError, "one unnamed root"):
                formats.parse_fdt(raw)

    def test_rejects_unsupported_versions_and_trailing_file_bytes(self):
        raw = board().end().finish()
        for modified in (header_edit(raw, 5, 18), header_edit(raw, 6, 17), raw + bytes(4)):
            with self.assertRaises(ValueError):
                formats.parse_fdt(modified)

    def test_rejects_end_followed_by_hidden_structure_payload(self):
        with self.assertRaisesRegex(ValueError, "not the final"):
            formats.parse_fdt(board().end().finish(tail=struct.pack(">I", 4)))

    def test_rejects_overlapping_and_unaligned_sections(self):
        raw = board().end().finish()
        off_body = struct.unpack_from(">I", raw, 8)[0]
        broken = [header_edit(raw, 4, 41), header_edit(raw, 2, off_body + 1),
                  header_edit(raw, 3, off_body), header_edit(raw, 4, off_body)]
        for modified in broken:
            with self.assertRaises(ValueError):
                formats.parse_fdt(modified)

    def test_rejects_missing_reservation_terminator_and_overflow(self):
        broken = [board().end().finish(reservations=[(0x1000, 0x2000)], reserve_terminator=False),
                  board().end().finish(reservations=[(formats.U64_LIMIT - 16, 32)]),
                  board().end().finish(reservations=[(0x1000, 0x2000), (0x2000, 0x1000)])]
        for raw in broken:
            with self.assertRaises(ValueError):
                formats.parse_fdt(raw)

    def test_rejects_property_payload_outside_structure(self):
        raw = bytearray(board().end().finish())
        off_body = struct.unpack_from(">I", raw, 8)[0]
        # root BEGIN + four-byte empty name, then PROP token and its length.
        struct.pack_into(">I", raw, off_body + 12, 0xFFFFFFFC)
        with self.assertRaises(ValueError):
            formats.parse_fdt(bytes(raw))

    def test_rejects_oversized_names_before_they_amplify_path_memory(self):
        broken = [board().begin("a" * 256).end().end().finish(),
                  board().prop("a" * 256, b"value").end().finish()]
        for raw in broken:
            with self.assertRaisesRegex(ValueError, "name"):
                formats.parse_fdt(raw)


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.header = formats.parse_arm64_image(image(effective=4 * formats.MIB))
        self.layout = {
            "kernel_address": 0x80000000,
            "dtb_address": 0x81000000,
            "initramfs_address": 0x82000000,
            "ram": [{"start": 0x80000000, "size": 256 * formats.MIB}],
            "reserved": [{"start": 0x88000000, "size": formats.MIB}],
        }

    def check(self, layout=None, header=None):
        return formats.validate_memory_layout(header or self.header, 128, 4096,
                                              layout or self.layout)

    def test_valid_layout_reports_only_planned_arithmetic(self):
        result = self.check()
        self.assertEqual(result["status"], "planned_layout_valid")
        self.assertFalse(result["physical_boot_verified"])
        self.assertIn("actual_loader_placement", result["unverified"])
        self.assertIn("dtb_2m_mapping_attributes", result["unverified"])

    def test_effective_tail_overlap_is_rejected_even_after_file_end(self):
        layout = copy.deepcopy(self.layout)
        layout["dtb_address"] = layout["kernel_address"] + 2 * formats.MIB
        self.assertGreater(layout["dtb_address"], layout["kernel_address"] + self.header["stored_bytes"])
        with self.assertRaisesRegex(ValueError, "planned payloads overlap"):
            self.check(layout)

    def test_rejects_bad_kernel_and_dtb_alignment(self):
        for key in ("kernel_address", "dtb_address"):
            layout = copy.deepcopy(self.layout)
            layout[key] += 1
            with self.assertRaisesRegex(ValueError, "aligned"):
                self.check(layout)

    def test_text_offset_applies_to_base_not_image_address(self):
        header = formats.parse_arm64_image(image(text_offset=0x80000))
        layout = copy.deepcopy(self.layout)
        layout["kernel_address"] += 0x80000
        self.assertEqual(self.check(layout, header)["image_base"], 0x80000000)

    def test_rejects_reserved_memory_and_ram_hole(self):
        layout = copy.deepcopy(self.layout)
        layout["reserved"] = [{"start": layout["kernel_address"] + formats.MIB, "size": 8}]
        with self.assertRaisesRegex(ValueError, "reserved"):
            self.check(layout)
        layout = copy.deepcopy(self.layout)
        layout["ram"] = [{"start": 0x80000000, "size": formats.MIB},
                         {"start": 0x80200000, "size": 254 * formats.MIB}]
        with self.assertRaisesRegex(ValueError, "RAM"):
            self.check(layout)

    def test_adjacent_ram_banks_cover_without_inventing_holes(self):
        layout = copy.deepcopy(self.layout)
        layout["ram"] = [{"start": 0x80000000, "size": formats.MIB},
                         {"start": 0x80100000, "size": 255 * formats.MIB}]
        self.assertEqual(self.check(layout)["status"], "planned_layout_valid")

    def test_requires_explicit_reserved_map_and_integer_addresses(self):
        layout = copy.deepcopy(self.layout)
        del layout["reserved"]
        with self.assertRaisesRegex(ValueError, "explicit"):
            self.check(layout)
        for invalid in (False, 0.0, "0x80000000", -1):
            layout = copy.deepcopy(self.layout)
            layout["kernel_address"] = invalid
            with self.assertRaises(ValueError):
                self.check(layout)

    def test_rejects_window_exceeding_32gib_and_48bit_image_placement(self):
        layout = copy.deepcopy(self.layout)
        layout["initramfs_address"] = 33 * formats.GIB + 0x80000000
        layout["ram"].append({"start": layout["initramfs_address"], "size": formats.MIB})
        with self.assertRaisesRegex(ValueError, "common.*window"):
            self.check(layout)
        layout = copy.deepcopy(self.layout)
        shift = 1 << 48
        for key in ("kernel_address", "dtb_address", "initramfs_address"):
            layout[key] += shift
        for name in ("ram", "reserved"):
            for region in layout[name]:
                region["start"] += shift
        with self.assertRaisesRegex(ValueError, "48-bit"):
            self.check(layout)

    def test_rejects_overflowing_maps_and_payloads(self):
        layout = copy.deepcopy(self.layout)
        layout["reserved"] = [{"start": formats.U64_LIMIT - 1, "size": 2}]
        with self.assertRaisesRegex(ValueError, "overflows"):
            self.check(layout)
        layout = copy.deepcopy(self.layout)
        layout["initramfs_address"] = formats.U64_LIMIT - 1
        with self.assertRaisesRegex(ValueError, "overflows"):
            self.check(layout)


if __name__ == "__main__":
    unittest.main()
