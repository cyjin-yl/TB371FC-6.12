#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Reference-profile gate tests; QMP is a fixture and no guest executes."""
import base64
import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

import launch_second_stage as launch
import second_stage_firmware as fw
from test_launch_second_stage import FakeProcess, FakeQMP
from test_boot_formats import image
from test_second_stage_layout import BOOTARGS, CONFIG, dt, psci_domains


# Golden public synthetic CommandDB, independently assembled from all 98
# resources in qemu-tb371fc 6287cd9a tb371fc/fixtures/rpmh-reference.json.
# zlib only removes the long zero padding; this is not a private firmware blob.
COMMAND_DB_ZLIB = (
    'eNrt1rFP3GUcx/HnAk0x6cDgwNCBwaGDMddCW5oYcwZNMBHFVE0HB4SKGA+5aGIYb3RkdGR0ZHS80ZGxiQu2iyN/'
    'gr97QO7zsJuY5vVafuGdh9893+d33NErpfzZn7sz110nZaGUXqnmy35v7fZ71z/fKmu3X7xx9/rn/8rR4TvDn4cR'
    'zufqZfeo7YtdX+quBzf6cu1L5eCg/Y1+7f3y7V77C4PaN8rwxgts1b5dhjdeYLv2o/LNzndNH9V+PN1Z9yqDMu5O'
    's/QGvXHvpDfpnff+b334w87u8Puv78/Oeb5ervqD2Tk3fWV2zpf9x732Nv2mr8Q5X/afDkaxenrOs/4g+nb0leij'
    '6KvRx9EfRj+O/ij6SfTH0U+jr0WfRH8S/Szn6sfb9t9ze37YzHsRPectf816zrsYPeddjp7z9qPnvIPoOe9W9Jx3'
    'O3rOO4qe846zx8DH2WPgk+wx8Gn2GHiSPQY+yx4Dn2ePgS+y58Avr5/jbj6vxej5vJaj5/PqR8/nNYiez2srej6v'
    '7ej5vEbRc/vjl9dzNfs/jp77P4me+z+NnvufRM/9n0XP/Z9Hz/1fRM/9l1eznu+3xej5flvOHgP3r/rO4U5zDoNX'
    '1+e213z+RG8+f2b3b9aPouf6cfQ8z+PoeZ4n0fM8T6PneU6i53meXfWPtvrtF+n5rem3eXl//csmz9e+UDbX2/UL'
    'tS+Wpxttv1P7UtncbPti7ctl/cO2v1n7vW79/aYv1d7v7t986pW7ta9169u+XPugfPZFO9hbtW9091lp1t+rfau7'
    'T9vfrv1Zt3616f3at8vTT9r9r9a+X9Y/bfta7aOyfmP9u7Ufdfdp5x3UPu56O9cHtf/S3b/tG7Ufd+vb/X9c+69d'
    'b/e/VftJ1x82/fPaf+v6o6Y/q/2064+b/lXtv3e9+Wvsvn+nfdL1J01/Xvsf03mbgfdrP5v2ZrBh7S/K33OX/zq+'
    'rlcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'
    'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACA19U/Y9dx'
    'XA=='
)


def reference_bytes():
    """Independent ABI assembly for the two fixed cold reference RAM images."""
    smem = bytearray(0x200000)
    put = lambda b, off, fmt, *values: struct.pack_into("<" + fmt, b, off, *values)
    put(smem, 0x5c, "I", 12 << 16)
    put(smem, 0xc0, "I", 1)
    smem[0x1ff000:0x1ff004] = b"$TOC"
    put(smem, 0x1ff004, "II", 1, 1)
    put(smem, 0x1ff020, "IIIHHI", 0x3000, 0x1fc000, 0, 0xfffe, 0xfffe, 64)
    smem[0x3000:0x3004] = b"$PRT"
    put(smem, 0x3004, "HHIII", 0xfffe, 0xfffe, 0x1fc000, 32, 0x1fc000)
    smem[0x1ff050:0x1ff054] = b"SIII"
    put(smem, 0x1ff054, "II", 0x200000, 0x80900000)
    put(smem, 0x1ff060, "H", 512)
    aop = bytearray(0x1000)
    fields = {0: 0x4d41494c, 4: 1, 0xc: 0xffff,
              0x10: 0xffff0000, 0x14: 0xffff0000, 0x18: 0xffff0000,
              0x1c: 0x100, 0x20: 0x100, 0x24: 0xffff0000,
              0x28: 0xffff0000, 0x2c: 0xffff0000, 0x30: 0xffff0000,
              0x34: 0x100, 0x38: 0x200}
    for off, value in fields.items():
        put(aop, off, "I", value)
    return {"command-db": zlib.decompress(base64.b64decode(COMMAND_DB_ZLIB)),
            "aop-msgram": bytes(aop), "smem": bytes(smem)}


class ReferenceQMP(FakeQMP):
    def __init__(self, process, inputs, out, *, corrupt=None, rom_change=None,
                 missing_reservation=False, extra_reservation=False,
                 duplicate_reservation=False, changed_psci=False, changed_node=False,
                 resume_during_capture=False, **kwargs):
        super().__init__(process, inputs, out, **kwargs)
        self.resume_during_capture = resume_during_capture
        regions = reference_bytes()
        for region in fw.REFERENCE_REGIONS:
            raw = bytearray(regions[region["name"]])
            if corrupt == region["name"]:
                raw[-1] ^= 1
            self.payloads[region["start"]] = bytes(raw)
        row = {k: v for k, v in fw.SMEM_ROM.items() if k != "memory"}
        if rom_change:
            row.update(rom_change)
        self.roms.append(row)
        if extra_reservation:
            self.roms.append({"name": "extra", "start": 0x81000000, "size": 16})
        initrd = self.roms[2]
        header = [] if missing_reservation else [(0x80900000, 0x200000)]
        if duplicate_reservation:
            header *= 2
        children = psci_domains()
        if changed_psci:
            children.pop("power-domain-cpu0")
        final = dt(final=True, memreserve=header, bootargs=inputs["bootargs"],
                   initrd_start=initrd["start"], initrd_end=initrd["start"] + initrd["size"],
                   psci_children=children, cpu_domains=list(range(0x101, 0x109)),
                   unrelated=b"changed\0" if changed_node else b"okay\0")
        self.payloads[self.roms[3]["start"]] = final
        self.roms[3]["size"] = len(final)

    def command(self, name, arguments=None, timeout=15):
        if (name == "query-status" and self.resume_during_capture and
                any(n == "pmemsave" and a["val"] == 0x80900000 for n, a in self.commands)):
            self.running = True
        return super().command(name, arguments, timeout)


class FirmwareProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        raw = {"kernel": image(stored=80, effective=4 * launch.MIB),
               "initrd": b"fixture-raw-initrd", "config": CONFIG,
               "dtb": dt(psci_children=psci_domains(), cpu_domains=list(range(0x101, 0x109)))}
        paths = {n: self.root / n for n in ("qemu", "kernel", "initrd", "dtb", "config", "rootfs")}
        self.inputs = {"paths": paths, "raw": raw, "release": "fixture",
                       "bootargs": BOOTARGS, "kernel_load_base": 0xa0000000}
        self.out = self.root / "result"
        self.process = FakeProcess()
        self.qmp = None

    def tearDown(self):
        self.temp.cleanup()

    def run_fixture(self, **options):
        def qmp_factory(path, process, timeout):
            self.qmp = ReferenceQMP(process, self.inputs, self.out, **options)
            return self.qmp
        return launch.run_prepared(self.inputs, self.out, 1,
            firmware_profile=fw.REFERENCE_PROFILE,
            process_factory=lambda *a, **k: self.process, qmp_factory=qmp_factory,
            unchanged=lambda inputs: None)

    def rejected(self, **options):
        result = self.run_fixture(**options)
        self.assertEqual(result["exit_code"], 1)
        self.assertFalse(result["cont_issued"])
        self.assertFalse(result["layout_gate_passed"])
        self.assertNotIn("cont", [n for n, _ in self.qmp.commands])
        self.assertTrue(result["cleanup"]["child_reaped"])
        return result

    def test_explicit_combined_profile_only(self):
        plain = launch.make_command(self.inputs, self.out, Path("/tmp/test.sock"))
        explicit = launch.make_command(self.inputs, self.out, Path("/tmp/test.sock"), fw.REFERENCE_PROFILE)
        self.assertEqual(plain[plain.index("-M") + 1], "tb371fc,kernel-load-base=0xa0000000")
        self.assertNotIn("-global", plain)
        self.assertEqual(explicit[explicit.index("-M") + 1],
            "tb371fc,kernel-load-base=0xa0000000,rpmh-profile=reference,rpmh-boot-configured=on,"
            "aop-profile=reference-qdss-vote,smem-profile=reference-empty")
        self.assertEqual(explicit[explicit.index("-global") + 1], "qcom-tcsr-mutex.boot-unlocked-reference=on")
        explicit[explicit.index("-M") + 1] = plain[plain.index("-M") + 1]
        index = explicit.index("-global")
        del explicit[index:index + 2]
        self.assertEqual(explicit, plain)

    def test_unknown_profiles_or_arbitrary_flags_rejected(self):
        for name in (True, None, "reference", "linux-reference-v1,prng-virtual=on", {"rpmh": "reference"}):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "unknown.*profile"):
                fw.profile_arguments(name)

    def test_all_full_captures_and_original_layout_precede_only_cont(self):
        result = self.run_fixture()
        self.assertEqual(result["exit_code"], 0, result["controller_errors"])
        self.assertTrue(result["cont_issued"])
        layout = result["layout"]
        evidence = layout["reference_firmware"]
        self.assertEqual(evidence["memory_bytes_read"], 2232320)
        self.assertTrue(evidence["synthetic_firmware"])
        self.assertTrue(evidence["smem_memreserve_added"])
        self.assertFalse(evidence["physical_firmware_verified"])
        self.assertFalse(result["userspace_verified"])
        self.assertEqual(layout["validation"]["dtb_fixups"]["psci_preservation"]["descendant_count"], 9)
        commands = self.qmp.commands
        self.assertEqual(sum(n == "cont" for n, _ in commands), 1)
        last_copy = max(i for i, (n, _) in enumerate(commands) if n == "pmemsave")
        self.assertLess(last_copy, next(i for i, (n, _) in enumerate(commands) if n == "cont"))
        captures = {a["val"]: a["size"] for n, a in commands if n == "pmemsave"}
        self.assertEqual({r["start"]: captures[r["start"]] for r in fw.REFERENCE_REGIONS},
                         {0x80860000: 0x20000, 0xc300000: 0x1000, 0x80900000: 0x200000})

    def test_complete_tail_corruption_in_each_region_blocks_cont(self):
        for region in ("command-db", "aop-msgram", "smem"):
            with self.subTest(region=region):
                self.out = self.root / region
                result = self.rejected(corrupt=region)
                self.assertIn("complete reference firmware bytes differ", " ".join(result["controller_errors"]))

    def test_missing_required_smem_reservation_blocks_cont(self):
        result = self.rejected(missing_reservation=True)
        self.assertIn("only one missing SMEM reservation", " ".join(result["controller_errors"]))

    def test_existing_smem_reservation_not_duplicated(self):
        self.inputs["raw"]["dtb"] = dt(memreserve=[(0x80900000, 0x200000)],
            psci_children=psci_domains(), cpu_domains=list(range(0x101, 0x109)))
        result = self.run_fixture()
        self.assertEqual(result["exit_code"], 0, result["controller_errors"])
        self.assertFalse(result["layout"]["reference_firmware"]["smem_memreserve_added"])

    def test_duplicate_header_reservation_rejected_by_unchanged_layout(self):
        result = self.rejected(duplicate_reservation=True)
        self.assertIn("unexpected FDT memory-reservation addition", " ".join(result["controller_errors"]))

    def test_missing_wrong_or_extra_smem_rom_rejected(self):
        for change in ({"name": "unknown"}, {"start": 0x80901000}, {"size": 0x1ff000}):
            with self.subTest(change=change):
                self.out = self.root / ("rom-" + str(len(list(self.root.iterdir()))))
                self.rejected(rom_change=change)
        self.out = self.root / "extra-rom"
        self.rejected(extra_reservation=True)

    def test_original_psci_and_other_device_checks_still_block_cont(self):
        for change in ("changed_psci", "changed_node"):
            with self.subTest(change=change):
                self.out = self.root / change
                self.rejected(**{change: True})

    def test_unexpected_resume_during_capture_blocks_cont(self):
        result = self.rejected(resume_during_capture=True)
        self.assertIn("resumed during reference", " ".join(result["controller_errors"]))


if __name__ == "__main__":
    unittest.main()
