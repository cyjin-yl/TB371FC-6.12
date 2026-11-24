#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
import pathlib
import struct
import subprocess
import tempfile
import unittest

import stage_r5_novatek as m
import stage_signed as signing


class ContractTests(unittest.TestCase):
    def test_atomic_signer_replacement_preserves_frozen_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            module = root / "module.ko"
            module.write_bytes(b"unsigned payload")
            module.chmod(0o600)
            signer = root / "atomic-signer"
            signer.write_text("#!/usr/bin/env python3\n"
                              "from pathlib import Path\nimport sys\n"
                              "p = Path(sys.argv[-1])\n"
                              "temporary = p.with_suffix('.tmp')\n"
                              "temporary.write_bytes(p.read_bytes() + b' signed trailer')\n"
                              "temporary.chmod(0o644)\n"
                              "temporary.replace(p)\n")
            signer.chmod(0o700)
            # Reproduce sign-file's actual atomic replacement side effect,
            # independently of the process umask; this fixture is not CMS.
            receipt = m.sign_preserving_mode(signer, root / "unused-key",
                                             root / "unused-cert", module, 0o600)
            self.assertEqual(receipt["before_mode"], 0o644)
            self.assertEqual(receipt["after_mode"], 0o600)
            self.assertEqual(module.stat().st_mode & 0o777, 0o600)
            self.assertEqual(module.read_bytes(), b"unsigned payload signed trailer")
            self.assertEqual(receipt["sha256_before"], receipt["sha256_after"])
            self.assertTrue(receipt["signed_bytes_unchanged"])

    def test_crc_exact(self):
        imported = m.parse_versions("0x1234 module_layout\n0xabcd second\n")
        m.check_versions(imported, m.symvers("0x1234 module_layout vmlinux EXPORT_SYMBOL\n0xabcd second vmlinux EXPORT_SYMBOL\n"))

    def test_crc_mismatch(self):
        for exports in ({}, {"module_layout": 1}, {"module_layout": 2, "other": 1}):
            with self.subTest(exports=exports), self.assertRaises(ValueError):
                m.check_versions({"module_layout": 2, "missing": 3}, exports)

    def test_bad_crc(self):
        for text in ("0x1 other", "not-a-crc module_layout",
                     "0x1 module_layout\n0x1 module_layout"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                m.parse_versions(text)
        with self.assertRaises(ValueError):
            m.symvers("0x1 x\n0x2 x")

    def test_elf_and_strip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "fixture.s"
            binary = root / "fixture.o"
            source.write_text('.text\n.global probe\nprobe: ret\n'
                              '.section .BTF,"",@progbits\n.byte 0x9f,0xeb,1,0\n'
                              '.section .BTF.ext,"",@progbits\n.byte 1,2,3\n'
                              '.section .debug_info,"",@progbits\n.byte 1,2,3,4\n')
            subprocess.run(["clang", "--target=aarch64-linux-gnu", "-c", source,
                            "-o", binary], check=True)
            raw = binary.read_bytes()
            before, count = m.elf_btf(raw)
            self.assertEqual(set(before), {".BTF", ".BTF.ext"})
            self.assertGreater(count, 0)
            subprocess.run(["llvm-strip", "--strip-debug", binary], check=True)
            after, count = m.elf_btf(binary.read_bytes())
            self.assertEqual(after, before)
            self.assertEqual(count, 0)
            bad = bytearray(raw)
            struct.pack_into("<H", bad, 18, 62)
            with self.assertRaises(ValueError):
                m.elf_btf(bad)
            bad = bytearray(raw)
            struct.pack_into("<Q", bad, 40, len(raw))
            with self.assertRaises(ValueError):
                m.elf_btf(bad)
            with self.assertRaises(ValueError):
                m.elf_btf(raw[:63])

    def test_no_btf(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / "fixture.s"
            binary = root / "fixture.o"
            source.write_text(".text\nret\n")
            subprocess.run(["clang", "--target=aarch64-linux-gnu", "-c", source,
                            "-o", binary], check=True)
            with self.assertRaises(ValueError):
                m.elf_btf(binary.read_bytes())

    def test_real_cms_and_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            content = root / "payload"
            signature = root / "signature"
            content.write_bytes(b"synthetic module payload")
            for name in ("one", "two"):
                subprocess.run(["openssl", "req", "-new", "-x509", "-newkey",
                                "rsa:2048", "-nodes", "-days", "1", "-subj",
                                "/CN=" + name, "-keyout", root / (name + ".key"),
                                "-out", root / (name + ".pem")], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["openssl", "cms", "-sign", "-binary", "-md", "sha512",
                            "-in", content, "-signer", root / "one.pem", "-inkey",
                            root / "one.key", "-outform", "DER", "-out", signature],
                           check=True)
            sig = signature.read_bytes()
            header = b"\0\0\2\0\0\0\0\0" + struct.pack(">I", len(sig))
            payload = content.read_bytes()
            blob = payload + sig + header + signing.MAGIC
            actual, receipt = m.cms(root, "valid", blob, root / "one.pem")
            self.assertEqual(actual, payload)
            self.assertTrue(receipt["signature_verified"])
            with self.assertRaises(RuntimeError):
                m.cms(root, "tampered", b"X" + blob[1:], root / "one.pem")
            with self.assertRaises(RuntimeError):
                m.cms(root, "other-cert", blob, root / "two.pem")
            with self.assertRaises(ValueError):
                signing.split_signature(blob[:-1])


if __name__ == "__main__":
    unittest.main()
