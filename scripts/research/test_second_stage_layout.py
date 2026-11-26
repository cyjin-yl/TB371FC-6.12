#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Synthetic paused-handoff regressions, including the cases that block cont."""
import copy
import struct
import unittest

from second_stage_layout import (
    BOARD_COMPATIBLE, FIRMWARE_HOLE, PSCI_PROPERTIES, LayoutError,
    validate_observed_layout,
)
from test_boot_formats import Tree, image

RAM = [{"start": 0x80000000, "size": 0x3BB00000},
       {"start": 0xC0000000, "size": 0x1C0000000}]
BOOTARGS = "console=ttyMSM0 root=/dev/sda module.sig_enforce=1"
CONFIG = b'''CONFIG_MODULES=y
CONFIG_MODULE_SIG=y
# CONFIG_MODULE_SIG_FORCE is not set
CONFIG_CMDLINE="cgroup_disable=pressure"
CONFIG_CMDLINE_FROM_BOOTLOADER=y
# CONFIG_CMDLINE_FORCE is not set
# CONFIG_CMDLINE_EXTEND is not set
'''


def dt(*, final=False, compatible=None, child_compatible=False, ram=None,
       reserved=(), dynamic=False, memreserve=(), bootargs=BOOTARGS,
       initrd_start=0xA8000000, initrd_end=0xA8000010, unrelated=b"okay\0",
       extra_chosen=False, psci=None, hole=True, nested=False, usable_memory=False):
    tree = Tree().begin("")
    tree.prop("compatible", compatible or b"lenovo,tb371fc\0qcom,sm8250\0")
    tree.prop("#address-cells", struct.pack(">I", 2))
    tree.prop("#size-cells", struct.pack(">I", 2))
    tree.begin("memory@80000000").prop("device_type", b"memory\0")
    chosen_ram = (RAM if final else [{"start": 0x80000000, "size": 0}]) if ram is None else ram
    tree.prop("reg", b"".join(struct.pack(">QQ", row["start"], row["size"]) for row in chosen_ram)).end()
    tree.begin("reserved-memory").prop("#address-cells", struct.pack(">I", 2))
    tree.prop("#size-cells", struct.pack(">I", 2)).prop("ranges", b"")
    for i, (start, size, flag) in enumerate(reserved):
        tree.begin("region" + str(i)).prop("reg", struct.pack(">QQ", start, size))
        if flag:
            tree.prop(flag, b"")
        tree.end()
    if dynamic:
        tree.begin("dynamic").prop("size", struct.pack(">Q", 0x200000)).end()
    if final and hole:
        tree.begin(FIRMWARE_HOLE.rsplit("/", 1)[1])
        tree.prop("reg", struct.pack(">QQ", 0xBBB00000, 0x4500000)).prop("no-map", b"").end()
    tree.end()
    tree.begin("chosen")
    if final:
        tree.prop("bootargs", bootargs.encode("ascii") + b"\0")
        tree.prop("linux,initrd-start", struct.pack(">Q", initrd_start))
        tree.prop("linux,initrd-end", struct.pack(">Q", initrd_end))
    if extra_chosen:
        tree.prop("unexpected", b"new\0")
    if usable_memory:
        tree.prop("linux,usable-memory-range", struct.pack(">QQ", 0x80000000, 0x100000))
    tree.end()
    tree.begin("psci")
    props = (PSCI_PROPERTIES if final else {"compatible": b"arm,psci-1.0\0", "method": b"smc\0"}) if psci is None else psci
    for key, value in props.items():
        tree.prop(key, value)
    if nested:
        tree.begin("child").end()
    tree.end()
    tree.begin("soc").prop("status", unrelated)
    if child_compatible:
        tree.prop("compatible", b"lenovo,tb371fc\0")
    tree.end().end()
    return tree.finish(reservations=memreserve)


def observed(**changes):
    result = {"kernel_address": 0xA0200000, "initramfs_address": 0xA8000000,
              "dtb_address": 0xAA000000, "ram": copy.deepcopy(RAM),
              "loader_reserved": [{"start": 0xA0000000, "size": 4096}],
              "bootargs": BOOTARGS}
    result.update(changes)
    return result


def validate(**changes):
    args = {"image": image(), "input_dtb": dt(), "final_dtb": dt(final=True),
            "initrd": b"0123456789abcdef", "kernel_config": CONFIG, "observed": observed()}
    args.update(changes)
    return validate_observed_layout(**args)


class PausedLayoutTests(unittest.TestCase):
    def test_valid_actual_layout_keeps_native_blocked_and_both_fdt_identities(self):
        result = validate()
        self.assertEqual(result["status"], "simulated_layout_valid")
        self.assertFalse(result["physical_boot_verified"])
        self.assertEqual(result["native_boot_readiness"]["status"], "blocked")
        self.assertEqual(result["owner_native_linux_passes_added"], 0)
        self.assertNotEqual(result["input_dtb"], result["final_dtb"])
        self.assertFalse(result["actual_payload_bytes_verified_by_this_function"])
        self.assertEqual(result["layout"]["kernel_stored_bytes"], 80)
        self.assertEqual(result["layout"]["kernel_effective_bytes"], 0x200000)
        self.assertTrue(result["command_line"]["fallback_overridden"])

    def test_r5_image_effective_extent_uses_real_header_sizes(self):
        result = validate(image=image(stored=41091080, effective=42729472))
        self.assertEqual(result["arm64_header"]["image_size"], 42729472)

    def test_effective_image_tail_overlap_is_rejected_even_when_file_bytes_fit(self):
        with self.assertRaisesRegex(ValueError, "planned payloads overlap"):
            validate(image=image(effective=0x8000000))

    def test_kernel_load_base_is_not_kernel_entry_for_zero_text_offset(self):
        with self.assertRaisesRegex(ValueError, "reserved memory"):
            validate(observed=observed(kernel_address=0xA0000000))

    def test_rejects_noninteger_or_overflowing_addresses(self):
        for value in (True, 1.0, "0xa0200000", -1, 1 << 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate(observed=observed(kernel_address=value))
        with self.assertRaisesRegex(ValueError, "overflows"):
            validate(observed=observed(loader_reserved=[{"start": (1 << 64) - 2, "size": 4}]))

    def test_rejects_supplied_ram_hole_or_disagreement(self):
        contiguous = [{"start": 0x80000000, "size": 0x200000000}]
        with self.assertRaisesRegex(ValueError, "firmware hole"):
            validate(observed=observed(ram=contiguous))
        shorter = copy.deepcopy(RAM)
        shorter[1]["size"] -= 4096
        with self.assertRaisesRegex(ValueError, "independently selected model RAM"):
            validate(observed=observed(ram=shorter))

    def test_rejects_effective_extent_crossing_ram_hole(self):
        with self.assertRaisesRegex(ValueError, "fully covered"):
            validate(observed=observed(kernel_address=0xBBA00000))

    def test_child_compatible_cannot_replace_root_identity(self):
        bad = dt(compatible=b"qcom,kona-qrd\0qcom,kona\0", child_compatible=True)
        with self.assertRaisesRegex(ValueError, "root compatible"):
            validate(input_dtb=bad)

    def test_all_static_reserved_ranges_count_without_no_map(self):
        for flag in (None, "reusable", "no-map"):
            reserved = [(0xA0200000, 0x1000, flag)]
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "reserved memory"):
                validate(input_dtb=dt(reserved=reserved), final_dtb=dt(final=True, reserved=reserved))

    def test_header_reservations_cannot_be_omitted_by_caller(self):
        rsv = [(0xA0200000, 0x1000)]
        with self.assertRaisesRegex(ValueError, "reserved memory"):
            validate(input_dtb=dt(memreserve=rsv), final_dtb=dt(final=True, memreserve=rsv),
                     observed=observed(loader_reserved=[]))

    def test_overlapping_reservation_declarations_are_conservatively_unioned(self):
        static = [(0x88000000, 0x2000, None), (0x88001000, 0x3000, "reusable")]
        headers = [(0x88000000, 0x1000), (0x88000800, 0x1000)]
        result = validate(input_dtb=dt(reserved=static, memreserve=headers),
                          final_dtb=dt(final=True, reserved=static, memreserve=headers))
        self.assertIn({"start": 0x88000000, "size": 0x4000}, result["reserved_union"])

    def test_dropped_or_unknown_added_header_reservation_fails(self):
        with self.assertRaisesRegex(ValueError, "removed an original"):
            validate(input_dtb=dt(memreserve=[(0x88000000, 0x1000)]))
        with self.assertRaisesRegex(ValueError, "unexpected.*reservation addition"):
            validate(final_dtb=dt(final=True, memreserve=[(0x88000000, 0x1000)]))

    def test_explicit_smem_addition_is_recorded_and_excluded(self):
        result = validate(final_dtb=dt(final=True, memreserve=[(0x80900000, 0x200000)]))
        self.assertEqual(result["dtb_fixups"]["memreserve_additions"],
                         [{"start": 0x80900000, "size": 0x200000}])
        self.assertIn({"start": 0x80900000, "size": 0x200000}, result["reserved_union"])

    def test_smem_fixup_does_not_add_duplicate_existing_entry(self):
        existing = [(0x80900000, 0x200000)]
        with self.assertRaisesRegex(ValueError, "unexpected.*reservation addition"):
            validate(input_dtb=dt(memreserve=existing),
                     final_dtb=dt(final=True, memreserve=existing * 2))

    def test_dynamic_allocation_is_reported_and_never_becomes_native_ready(self):
        result = validate(input_dtb=dt(dynamic=True), final_dtb=dt(final=True, dynamic=True))
        self.assertEqual(len(result["unresolved_reservations"]), 2)
        self.assertEqual(result["native_boot_readiness"]["status"], "blocked")

    def test_missing_duplicate_conflicting_post_separator_or_aliased_enforcement_fails(self):
        for line in ("root=/dev/sda", "module.sig_enforce=0", "module.sig_enforce",
                     "module.sig_enforce=1 module.sig_enforce=1",
                     "module.sig_enforce=1 module.sig-enforce=0",
                     "root=/dev/sda -- module.sig_enforce=1", '"module.sig_enforce=1"'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                validate(final_dtb=dt(final=True, bootargs=line), observed=observed(bootargs=line))

    def test_final_command_line_must_equal_request(self):
        with self.assertRaisesRegex(ValueError, "differ from the requested"):
            validate(final_dtb=dt(final=True, bootargs=BOOTARGS + " init=/bin/sh"))

    def test_builtin_force_extend_unknown_modes_and_duplicate_config_fail(self):
        for config in (CONFIG.replace(b"CONFIG_CMDLINE_FORCE is not set", b"unrelated" ) + b"CONFIG_CMDLINE_FORCE=y\n",
                       CONFIG.replace(b"CONFIG_CMDLINE_EXTEND is not set", b"unrelated") + b"CONFIG_CMDLINE_EXTEND=y\n",
                       CONFIG.replace(b"CONFIG_CMDLINE_FROM_BOOTLOADER=y", b"# CONFIG_CMDLINE_FROM_BOOTLOADER is not set"),
                       CONFIG + b"CONFIG_CMDLINE_FROM_BOOTLOADER=y\n",
                       CONFIG.replace(b"CONFIG_MODULE_SIG=y", b"# CONFIG_MODULE_SIG is not set")):
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate(kernel_config=config)

    def test_chosen_initrd_bounds_must_match_actual_rom(self):
        for start, end in ((0xA8000001, 0xA8000010), (0xA8000000, 0xA8000011)):
            with self.assertRaisesRegex(ValueError, "initrd interval"):
                validate(final_dtb=dt(final=True, initrd_start=start, initrd_end=end))

    def test_preserved_crash_memory_restriction_is_not_ignored(self):
        with self.assertRaisesRegex(ValueError, "memory restrictions"):
            validate(input_dtb=dt(usable_memory=True), final_dtb=dt(final=True, usable_memory=True))

    def test_arbitrary_board_or_chosen_mutation_fails(self):
        for final in (dt(final=True, unrelated=b"disabled\0"), dt(final=True, extra_chosen=True)):
            with self.assertRaisesRegex(ValueError, "unexpected"):
                validate(final_dtb=final)

    def test_exact_psci_model_and_firmware_hole_required(self):
        psci = dict(PSCI_PROPERTIES, method=b"hvc\0")
        for final in (dt(final=True, psci=psci), dt(final=True, hole=False), dt(final=True, nested=True)):
            with self.assertRaises(ValueError):
                validate(final_dtb=final)

    def test_legacy_image_and_empty_initrd_fail(self):
        with self.assertRaises(ValueError):
            validate(image=image(effective=0))
        with self.assertRaises(ValueError):
            validate(initrd=b"")

    def test_malformed_observation_cannot_sneak_native_boolean_into_result(self):
        with self.assertRaisesRegex(ValueError, "fields differ"):
            validate(observed=observed(physical_boot_verified=True))


if __name__ == "__main__":
    unittest.main()
