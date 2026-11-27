#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Negative cases for R7 input boundaries and offline module ABI inspection."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load("build_rpmh_candidate")
abi = load("verify_module_abi")
REL = build.RELEASE


def module_fixture(*, crc=0x12345678, vermagic=None, no_btf=False, debug=False,
                   required_import="test_symbol", versions=None):
    """Minimal ARM64 ET_REL, not a real loadable or cryptographically signed module."""
    symbols = [b"", b"test_symbol", b"module_layout"]
    st = b"\0test_symbol\0module_layout\0"
    version_rows = versions or [("test_symbol", crc), ("module_layout", 0xabcdef12)]
    items = [("", 0, b"", 0, 0),
             (".modinfo", 1, b"vermagic=" + (vermagic or REL + " SMP preempt mod_unload modversions aarch64").encode() + b"\0", 0, 0),
             ("__versions", 1, b"".join(struct.pack("<Q56s", value, name.encode()) for name, value in version_rows), 0, 64),
             (".strtab", 3, st, 0, 0)]
    symbol_offset = st.index(required_import.encode()) if required_import in ("test_symbol", "module_layout") else 0
    symdata = b"\0" * 24 + struct.pack("<IBBHQQ", symbol_offset, 0x10, 0, 0, 0, 0)
    items.append((".symtab", 2, symdata, 3, 24))
    if not no_btf:
        items.append((".BTF", 1, struct.pack("<HBBIIIII", 0xeb9f, 1, 0, 24, 0, 4, 4, 1) + b"\0" * 5, 0, 0))
    if debug:
        items.append((".debug_info", 1, b"debug", 0, 0))
    strings = b"\0" + b"\0".join(x[0].encode() for x in items[1:]) + b"\0.shstrtab\0"
    shstr = len(items)
    items.append((".shstrtab", 3, strings, 0, 0))
    body = bytearray(b"\0" * 64)
    headers = []
    for name, kind, data, link, entsize in items:
        offset = len(body)
        body.extend(data)
        headers.append((strings.index(name.encode() + b"\0") if name else 0, kind, 0, 0, offset, len(data), link, 0, 1, entsize))
    shoff = len(body)
    for row in headers:
        body.extend(struct.pack("<IIQQQQIIQQ", *row))
    ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    struct.pack_into("<16sHHIQQQIHHHHHH", body, 0, ident, 1, 183, 1, 0, 0, shoff, 0, 64, 0, 0, 64, len(items), shstr)
    return bytes(body)


class ABITests(unittest.TestCase):
    exports = {"test_symbol": 0x12345678, "module_layout": 0xabcdef12}

    def test_valid_fixture(self):
        r = abi.module_abi(module_fixture(), REL, self.exports)
        self.assertEqual(r["versioned_import_count"], 2)
        self.assertEqual(r["strong_import_count"], 1)
        self.assertTrue(r["debug_info_stripped"])

    def test_wrong_crc(self):
        with self.assertRaisesRegex(ValueError, "CRC differs"):
            abi.module_abi(module_fixture(crc=42), REL, self.exports)

    def test_wrong_release(self):
        with self.assertRaisesRegex(ValueError, "vermagic"):
            abi.module_abi(module_fixture(vermagic="other"), REL, self.exports)

    def test_missing_btf(self):
        with self.assertRaisesRegex(ValueError, "missing required section"):
            abi.module_abi(module_fixture(no_btf=True), REL, self.exports)

    def test_debug_not_stripped(self):
        with self.assertRaisesRegex(ValueError, "not stripped"):
            abi.module_abi(module_fixture(debug=True), REL, self.exports)

    def test_missing_strong_crc(self):
        with self.assertRaisesRegex(ValueError, "undefined strong symbol"):
            abi.module_abi(module_fixture(versions=[("module_layout", 0xabcdef12)]), REL, self.exports)

    def test_missing_layout(self):
        with self.assertRaisesRegex(ValueError, "module_layout"):
            abi.module_abi(module_fixture(versions=[("test_symbol", 0x12345678)]), REL, self.exports)

    def test_duplicate_version(self):
        with self.assertRaisesRegex(ValueError, "duplicate imported"):
            abi.module_abi(module_fixture(versions=[("module_layout", 0xabcdef12), ("module_layout", 0xabcdef12)]), REL, self.exports)

    def test_truncated_elf(self):
        with self.assertRaisesRegex(ValueError, "truncated ELF"):
            abi.module_abi(module_fixture()[:63], REL, self.exports)

    def test_wrong_elf_arch(self):
        data = bytearray(module_fixture()); data[18] = 62
        with self.assertRaisesRegex(ValueError, "AArch64"):
            abi.module_abi(data, REL, self.exports)

    def test_btf_overflow(self):
        data = bytearray(module_fixture()); sections, _ = abi.sections(data)
        offset = sections[".BTF"]["header"][4]
        struct.pack_into("<I", data, offset + 12, 0xffffffff)
        with self.assertRaisesRegex(ValueError, "bounded BTF"):
            abi.module_abi(data, REL, self.exports)

    def test_btf_overlap(self):
        data = bytearray(module_fixture()); sections, _ = abi.sections(data)
        offset = sections[".BTF"]["header"][4]
        struct.pack_into("<I", data, offset + 16, 0)
        with self.assertRaisesRegex(ValueError, "bounded BTF"):
            abi.module_abi(data, REL, self.exports)

    def test_symvers_rejects_duplicate(self):
        with self.assertRaisesRegex(ValueError, "duplicate Module.symvers"):
            abi.symvers(b"0x12345678\tsym\tvmlinux\tEXPORT_SYMBOL\t\n" * 2)


class ConstructionTests(unittest.TestCase):
    def test_complete_config_delta(self):
        config = HERE.parents[3] / "docs/research/2026-11-26/evidence/tianma-r6-build/kernel.config"
        expected = build.expected_config(config.read_bytes())
        self.assertEqual(hashlib.sha256(expected).hexdigest(), build.R7_CONFIG_SHA)
        self.assertEqual(len(expected), 223386)
        self.assertIn(b"CONFIG_QCOM_CLK_RPMH=y\n", expected)

    def test_config_tamper(self):
        with self.assertRaisesRegex(ValueError, "complete R6 config differs"):
            build.expected_config(b"CONFIG_QCOM_CLK_RPMH=y\n")

    def test_source_external_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "link").symlink_to("/tmp")
            with self.assertRaisesRegex(ValueError, "nonrelocatable"):
                build.source_inventory(root)

    def test_source_old_private_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "certs").mkdir(); (root / "certs/signing_key.pem").write_text("secret")
            with self.assertRaisesRegex(ValueError, "generated source output or key"):
                build.source_inventory(root)

    def test_source_delta_rejects_other_changes(self):
        a = {build.PANEL: {"sha256": build.R5_PANEL_SHA}, "Makefile": {"sha256": "old"}}
        b = {build.PANEL: {"sha256": build.R6_PANEL_SHA}, "Makefile": {"sha256": "changed"}}
        with self.assertRaisesRegex(ValueError, "exceeds"):
            build.compare_sources(a, b)

    def test_source_exact_panel_delta(self):
        a = {build.PANEL: {"sha256": build.R5_PANEL_SHA}, "Makefile": {"sha256": "same"}}
        b = {build.PANEL: {"sha256": build.R6_PANEL_SHA}, "Makefile": {"sha256": "same"}}
        build.compare_sources(a, b)

    def test_work_requires_fresh_canonical_prefix(self):
        with self.assertRaisesRegex(ValueError, "fresh /work"):
            build.build(Path("/tmp"), Path("/tmp"), Path("/tmp"), Path("/tmp/r7-wrong"))


if __name__ == "__main__":
    unittest.main()
