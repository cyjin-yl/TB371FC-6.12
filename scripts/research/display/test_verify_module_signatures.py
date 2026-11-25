# SPDX-License-Identifier: GPL-2.0-only
"""Small crypto/parser fixtures, not loadable kernel modules or runtime tests."""
import hashlib
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

import verify_module_signatures as verifier


def run(*command):
    subprocess.run([str(value) for value in command], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)


def arm64_object():
    names = b"\0.text\0.shstrtab\0"
    ident = b"\x7fELF\x02\x01\x01" + b"\0" * 9
    header = struct.pack("<16sHHIQQQIHHHHHH", ident, 1, 183, 1, 0, 0, 96, 0, 64, 0, 0, 64, 3, 2)
    body = header + bytes.fromhex("c0035fd6") + names
    body += b"\0" * (96 - len(body))
    return body + b"\0" * 64 + struct.pack("<IIQQQQIIQQ", 1, 1, 6, 0, 64, 4, 0, 0, 4, 0) + \
        struct.pack("<IIQQQQIIQQ", 7, 3, 0, 0, 68, len(names), 0, 0, 1, 0)


class SignatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="tb371fc-signature-selftest-")
        cls.work = Path(cls.temporary.name)
        for name in ("candidate", "wrong"):
            run("openssl", "req", "-new", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-keyout", cls.work / (name + ".test-key.pem"), "-out", cls.work / (name + ".pem"),
                "-days", "1", "-subj", "/CN=Ephemeral module selftest " + name)
            run("openssl", "x509", "-in", cls.work / (name + ".pem"), "-outform", "DER",
                "-out", cls.work / (name + ".x509"))
        cls.unsigned = arm64_object()
        (cls.work / "unsigned.o").write_bytes(cls.unsigned)
        cls.signed = {}
        for name, certificate_flag in (("normal", ["-nocerts"]), ("embedded", [])):
            run("openssl", "cms", "-sign", "-binary", "-noattr", "-md", "sha256", *certificate_flag,
                "-in", cls.work / "unsigned.o", "-signer", cls.work / "candidate.pem",
                "-inkey", cls.work / "candidate.test-key.pem", "-outform", "DER", "-out", cls.work / (name + ".p7s"))
            signature = (cls.work / (name + ".p7s")).read_bytes()
            cls.signed[name] = cls.unsigned + signature + verifier.TRAILER.pack(0, 0, 2, 0, 0, b"\0" * 3, len(signature)) + verifier.MAGIC

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def verify_sample(self, data, certificate="candidate.x509"):
        with tempfile.TemporaryDirectory(dir=self.work) as directory:
            root = Path(directory)
            module = root / "fixture.ko"
            module.write_bytes(data)
            before = hashlib.sha256(module.read_bytes()).hexdigest()
            result = verifier.inspect(root, self.work / certificate, expected_count=1)
            self.assertEqual(before, hashlib.sha256(module.read_bytes()).hexdigest())
            self.assertFalse(result["runtime_signature_enforcement_verified"])
            self.assertFalse(result["private_key_accessed"])
            return result

    def test_valid_detached_signature_and_public_der_certificate(self):
        result = self.verify_sample(self.signed["normal"])
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["modules"][0]["verified_content_matches"])
        self.assertEqual(result["modules"][0]["verified_signer_der_sha256"],
                         result["public_certificate"]["der_sha256"])

    def test_changed_module_bytes_fail_crypto(self):
        data = bytearray(self.signed["normal"])
        data[64] ^= 1
        result = self.verify_sample(bytes(data))
        self.assertFalse(result["passed"])
        self.assertNotEqual(result["modules"][0]["openssl_exit_code"], 0)

    def test_embedded_correct_certificate_cannot_override_supplied_wrong_one(self):
        result = self.verify_sample(self.signed["embedded"], "wrong.x509")
        self.assertFalse(result["passed"])
        self.assertNotEqual(result["modules"][0]["openssl_exit_code"], 0)

    def test_nonzero_trailer_padding_is_rejected_before_crypto(self):
        data = bytearray(self.signed["normal"])
        data[-len(verifier.MAGIC) - verifier.TRAILER.size + 5] = 1
        result = self.verify_sample(bytes(data))
        self.assertFalse(result["passed"])
        self.assertIn("trailer violates", result["modules"][0]["error"])
        self.assertNotIn("openssl_exit_code", result["modules"][0])


if __name__ == "__main__":
    unittest.main()
