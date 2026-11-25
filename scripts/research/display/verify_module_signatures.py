#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only ARM64 .ko and detached PKCS#7 verification with a public certificate.

Linux v6.12 module_signature.h/module_signature.c define the trailer. OpenSSL
CMS verifies the original module bytes using only the supplied certificate.
This does not load modules or establish trust in a running kernel keyring.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import tempfile

MAGIC = b"~Module signature appended~\n"
TRAILER = struct.Struct(">5B3sI")
MAX_MODULE = 256 * 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_file(path, maximum):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, "bounded regular file required")
        data = stream.read(maximum + 1)
        require(len(data) == before.st_size and snapshot(before) == snapshot(os.fstat(stream.fileno()))
                == snapshot(path.lstat()), "input changed while reading")
    return data, snapshot(before)


def der_children(data, expected_tag):
    """Decode only definite DER framing; cryptography remains OpenSSL's job."""
    def element(offset):
        require(offset + 2 <= len(data), "truncated DER header")
        tag, length = data[offset], data[offset + 1]
        cursor = offset + 2
        if length & 0x80:
            count = length & 0x7f
            require(0 < count <= 4 and cursor + count <= len(data), "invalid DER length")
            encoded = data[cursor:cursor + count]
            require(encoded[0] != 0, "noncanonical DER length")
            length = int.from_bytes(encoded, "big")
            require(length >= 128, "noncanonical short DER length")
            cursor += count
        end = cursor + length
        require(end <= len(data), "truncated DER value")
        return tag, data[cursor:end], end
    tag, body, end = element(0)
    require(tag == expected_tag and end == len(data), "unexpected DER tag or trailing bytes")
    # Reuse the small element reader with the container's body as its input.
    data, offset, result = body, 0, []
    while offset < len(data):
        start = offset
        tag, value, offset = element(offset)
        result.append((tag, value, data[start:offset]))
    return result


def split_module(data):
    require(len(data) > 64 + TRAILER.size + len(MAGIC) and data.endswith(MAGIC), "missing module signature trailer")
    trailer_start = len(data) - len(MAGIC) - TRAILER.size
    algo, hash_id, id_type, signer_len, key_len, padding, sig_len = TRAILER.unpack_from(data, trailer_start)
    require(id_type == 2 and not any((algo, hash_id, signer_len, key_len)) and padding == b"\0" * 3,
            "trailer violates Linux PKCS#7 parameter requirements")
    require(0 < sig_len < trailer_start, "invalid signature length")
    unsigned, signature = data[:trailer_start - sig_len], data[trailer_start - sig_len:trailer_start]
    require(len(unsigned) >= 64, "truncated ELF64 header")
    elf = struct.unpack_from("<16sHHIQQQIHHHHHH", unsigned)
    require(elf[0][:7] == b"\x7fELF\x02\x01\x01" and elf[1:4] == (1, 183, 1) and elf[8] == 64,
            "expected little-endian AArch64 ELF64 relocatable object")
    require(elf[10] == 0 and elf[11] == 64 and 0 < elf[12] < 65535 and elf[13] < elf[12]
            and 64 <= elf[6] <= len(unsigned) - elf[11] * elf[12], "invalid ELF section table")
    for offset in range(elf[6], elf[6] + elf[11] * elf[12], elf[11]):
        section = struct.unpack_from("<IIQQQQIIQQ", unsigned, offset)
        require(section[1] == 8 or (section[4] <= len(unsigned) and section[5] <= len(unsigned) - section[4]),
                "ELF section extends beyond unsigned module")
    content = der_children(signature, 0x30)
    require(len(content) == 2 and content[0][:2] == (6, bytes.fromhex("2a864886f70d010702"))
            and content[1][0] == 0xa0, "signature is not CMS SignedData")
    wrapped = der_children(content[1][2], 0xa0)
    require(len(wrapped) == 1 and wrapped[0][0] == 0x30, "invalid SignedData wrapper")
    signed = der_children(wrapped[0][2], 0x30)
    require(len(signed) >= 4 and [item[0] for item in signed[:3]] == [2, 0x31, 0x30]
            and signed[-1][0] == 0x31, "invalid SignedData layout")
    encapsulated = der_children(signed[2][2], 0x30)
    require(len(encapsulated) == 1 and encapsulated[0][:2] == (6, bytes.fromhex("2a864886f70d010701")),
            "CMS must contain a detached data signature")
    require(len(der_children(signed[-1][2], 0x31)) == 1, "exactly one module signer required")
    return unsigned, signature, {
        "elf": {"class": 64, "byte_order": "little", "machine": 183, "type": "ET_REL", "sections": elf[12]},
        "signature_info": {"algo": algo, "hash": hash_id, "id_type": id_type,
            "signer_len": signer_len, "key_id_len": key_len, "padding_hex": padding.hex(),
            "signature_bytes": sig_len, "signature_sha256": sha(signature), "detached": True, "signers": 1}}


def invoke(argv):
    result = subprocess.run([str(value) for value in argv], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
    return result


def inventory(root):
    modules, ignored_links, compressed = [], [], []
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs[:]:
            path = Path(directory) / name
            if path.is_symlink():
                ignored_links.append(str(path.relative_to(root)))
                dirs.remove(name)
        for name in names:
            path = Path(directory) / name
            if name.endswith(".ko"):
                modules.append(path)
            elif any(name.endswith(".ko" + suffix) for suffix in (".xz", ".gz", ".zst")):
                compressed.append(str(path.relative_to(root)))
    require(0 < len(modules) <= 4096, "expected a nonempty bounded installed .ko tree")
    return sorted(modules), sorted(ignored_links), sorted(compressed)


def inspect(root, certificate, expected_count=None, openssl="openssl"):
    record = {"schema_version": 1, "started_utc": now(), "passed": False, "modules": [],
              "scope": "offline ARM64 module structure and signature verification only",
              "runtime_signature_enforcement_verified": False, "kernel_keyring_trust_verified": False,
              "module_loadability_verified": False, "private_key_accessed": False,
              "certificate_chain_validation": False, "signer_source": "provided public certificate only"}
    try:
        source, source_snapshot = read_file(Path(__file__), 1024**2)
        record["verifier_source"] = {"sha256": sha(source), "bytes": len(source)}
        require(not root.is_symlink() and root.is_dir(), "module root must be an ordinary directory")
        root = root.resolve(strict=True)
        record["modules_root"] = str(root)
        openssl = str(Path(shutil.which(openssl) or openssl).resolve(strict=True))
        version = invoke([openssl, "version"])
        require(version.returncode == 0, "cannot query OpenSSL version")
        record["openssl"] = {"path": openssl, "version": version.stdout.decode().strip()}
        cert_bytes, cert_snapshot = read_file(certificate, 1024**2)
        pem = cert_bytes.strip().startswith(b"-----BEGIN CERTIFICATE-----")
        if pem:
            require(cert_bytes.strip().endswith(b"-----END CERTIFICATE-----") and
                    cert_bytes.count(b"-----BEGIN") == cert_bytes.count(b"-----END") == 1,
                    "exactly one public PEM certificate required")
        else:
            der_children(cert_bytes, 0x30)
        record["public_certificate"] = {"path": str(certificate), "bytes": len(cert_bytes),
                                         "sha256": sha(cert_bytes), "format": "PEM" if pem else "DER"}
        modules, ignored, compressed = inventory(root)
        record.update(module_count=len(modules), expected_count=expected_count,
                      ignored_directory_symlinks=ignored, compressed_modules_not_verified=compressed)
        snapshots = {}
        with tempfile.TemporaryDirectory(prefix="tb371fc-module-signatures-") as temporary:
            temp = Path(temporary)
            (temp / "input.x509").write_bytes(cert_bytes)
            for form, output in (("PEM", "certificate.pem"), ("DER", "certificate.der")):
                command = [openssl, "x509", "-inform", "PEM" if pem else "DER", "-in", temp / "input.x509",
                           "-outform", form, "-out", temp / output]
                require(invoke(command).returncode == 0, "OpenSSL rejected the public certificate")
            cert_der = (temp / "certificate.der").read_bytes()
            record["public_certificate"]["der_sha256"] = sha(cert_der)
            for path in modules:
                row = {"path": str(path.relative_to(root)), "passed": False}
                record["modules"].append(row)
                try:
                    data, snapshots[path] = read_file(path, MAX_MODULE)
                    row.update(sha256=sha(data), bytes=len(data))
                    unsigned, signature, info = split_module(data)
                    row.update(info, unsigned_bytes=len(unsigned), unsigned_sha256=sha(unsigned))
                    with tempfile.TemporaryDirectory(dir=temp, prefix="module-") as sub:
                        part = Path(sub)
                        (part / "unsigned.ko").write_bytes(unsigned)
                        (part / "signature.der").write_bytes(signature)
                        command = [openssl, "cms", "-verify", "-verify_retcode", "-binary", "-inform", "DER",
                            "-in", part / "signature.der", "-content", part / "unsigned.ko",
                            "-nointern", "-certfile", temp / "certificate.pem", "-noverify",
                            "-signer", part / "signer.pem", "-out", part / "verified-content"]
                        verified = invoke(command)
                        row["openssl_exit_code"] = verified.returncode
                        row["openssl_stderr"] = verified.stderr.decode(errors="replace")[:8192]
                        require(verified.returncode == 0, "CMS signature verification failed")
                        require((part / "verified-content").read_bytes() == unsigned,
                                "CMS verified content differs from original module bytes")
                        require((part / "signer.pem").read_bytes().count(b"-----BEGIN CERTIFICATE-----") == 1,
                                "unexpected verified signer count")
                        signer = invoke([openssl, "x509", "-in", part / "signer.pem", "-outform", "DER"])
                        require(signer.returncode == 0 and signer.stdout == cert_der,
                                "verified signer differs from supplied certificate")
                        row.update(verified_signer_der_sha256=sha(signer.stdout),
                                   verified_content_matches=True, passed=True)
                except (OSError, ValueError, struct.error, subprocess.TimeoutExpired) as error:
                    row["error"] = str(error)
        require(snapshot(certificate.lstat()) == cert_snapshot, "certificate changed during verification")
        require(snapshot(Path(__file__).lstat()) == source_snapshot, "verifier source changed during execution")
        after, ignored_after, compressed_after = inventory(root)
        stable = (after == modules and ignored == ignored_after and compressed == compressed_after and
                  all(snapshot(path.lstat()) == value for path, value in snapshots.items()))
        record["input_snapshot_stable"] = stable
        record["passed"] = bool(stable and not compressed and
            (expected_count is None or len(modules) == expected_count) and all(row["passed"] for row in record["modules"]))
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        record["error"] = str(error)
    record["finished_utc"] = now()
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modules", "--modules-root", dest="modules_root", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--openssl", default="openssl")
    parser.add_argument("--output", type=Path, help="new JSON report outside the inspected module tree")
    args = parser.parse_args()
    if args.output:
        require(not args.output.parent.resolve(strict=True).is_relative_to(args.modules_root.resolve(strict=True)),
                "report must remain outside the module tree")
    result = inspect(args.modules_root, args.certificate, args.expected_count, args.openssl)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(text)
    else:
        print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
