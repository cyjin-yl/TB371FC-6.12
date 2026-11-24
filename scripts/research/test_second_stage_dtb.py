#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import derive_second_stage_dtb as d


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "base.dtb"
        src = self.root / "test.dts"
        src.write_text("""/dts-v1/;
/ {
    compatible = "lenovo,tb371fc", "qcom,sm8250";
    #address-cells = <2>;
    #size-cells = <2>;
    memory@80000000 { device_type = "memory"; reg = <0 0x80000000 0 0>; };
    reserved-memory {
        #address-cells = <2>;
        #size-cells = <2>;
        ranges;
        region@80000000 { reg = <0 0x80000000 0 0x1000>; no-map; };
    };
};""")
        subprocess.run(["dtc", "-I", "dts", "-O", "dtb", "-o", str(self.path), str(src)],
                       check=True, capture_output=True)
        self.base = self.path.read_bytes()
        self.obs = (Path(__file__).resolve().parents[2] /
            "docs/research/2026-11-24/evidence/native-dt/live-android.json").read_bytes()

    def mutate(self, node, prop, cells, type="x"):
        subprocess.run(["fdtput", "-t", type, str(self.path), node, prop, *cells],
                       check=True, capture_output=True)
        return self.path.read_bytes()

    def valid(self):
        return self.mutate(d.MEMORY, "reg",
                           [f"{n:x}" for n in struct.unpack(">8I", d.RAM_BYTES)])

    def test_delta_accepts_only_ram(self):
        self.assertEqual(d.check_delta(self.base, self.valid())[0]["property"], "reg")

    def test_delta_rejects_wrong_ram(self):
        bad = self.mutate(d.MEMORY, "reg", ["0", "80000000", "0", "1000"])
        with self.assertRaisesRegex(ValueError, "incorrect final RAM"):
            d.check_delta(self.base, bad)

    def test_delta_rejects_other_property_change(self):
        self.valid()
        bad = self.mutate("/", "compatible", ["qcom,sm8250"], "s")
        with self.assertRaisesRegex(ValueError, "unexpected semantic changes"):
            d.check_delta(self.base, bad)

    def test_delta_rejects_property_addition(self):
        self.valid()
        bad = self.mutate("/", "model", ["abc"], "s")
        with self.assertRaisesRegex(ValueError, "property inventory"):
            d.check_delta(self.base, bad)

    def test_delta_rejects_reserve_change(self):
        self.valid()
        bad = self.mutate("/reserved-memory/region@80000000", "reg",
                          ["0", "80000000", "0", "2000"])
        with self.assertRaisesRegex(ValueError, "unexpected semantic changes"):
            d.check_delta(self.base, bad)

    def test_delta_rejects_header_change(self):
        bad = bytearray(self.valid())
        struct.pack_into(">I", bad, 28, 1)
        with self.assertRaisesRegex(ValueError, "header or reservation"):
            d.check_delta(self.base, bytes(bad))

    def test_exact_owner_observation(self):
        self.assertEqual(len(d.observation(self.obs)["reserved_memory"]["nodes"]), 35)
        with self.assertRaisesRegex(ValueError, "observation identity"):
            d.observation(self.obs + b" ")

    def test_wrong_board_hash_no_output(self):
        out = self.root / "candidate"
        with self.assertRaisesRegex(ValueError, "frozen R5"):
            d.derive(self.base, self.obs, out)
        self.assertFalse(out.exists())

    def test_synthetic_derivation_and_no_overwrite(self):
        # Only the synthetic fixture hash is substituted; all structural gates run.
        out = self.root / "candidate"
        with patch.object(d, "R5_SHA", d.sha(self.base)):
            report = d.derive(self.base, self.obs, out)
            old = (out / "receipt.json").read_bytes()
            with self.assertRaises(FileExistsError):
                d.derive(self.base, self.obs, out)
        self.assertEqual(old, (out / "receipt.json").read_bytes())
        self.assertEqual(self.path.read_bytes(), self.base)
        self.assertEqual(d.sha((out / "board.dtb").read_bytes()), report["candidate"]["sha256"])
        self.assertEqual(len(report["android_unresolved_dynamic"]), 12)
        self.assertEqual(len(report["reserved_memory_comparison"]["android"]), 35)
        self.assertFalse(report["runtime_memory_map_verified"])
        self.assertFalse(report["physical_boot_verified"])
        self.assertEqual(report["owner_native_linux_passes_added"], 0)

    def test_fixed_reader_rejects_symlink(self):
        link = self.root / "link"
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "regular input"):
            d.read_fixed(link, d.sha(self.base))


if __name__ == "__main__":
    unittest.main()
