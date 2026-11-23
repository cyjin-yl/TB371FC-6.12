#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Sign a new input-module copy with the existing frozen research2 project key.

Only offline files are processed. The private key is never copied, generated,
printed or hashed into a manifest. This explicitly pinned bundle is not a boot
image, root filesystem, module-load operation or physical device test.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import struct
import subprocess

RELEASE = "6.12.114-tb371fc-research2-display"
MODULE_REL = "kernel/drivers/input/touchscreen/nt36523/nt36523_ts.ko"
BASE = {
    "Image": "181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d",
    "kernel.config": "e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8",
    "Module.symvers": "8e71a956b3c79112228f92cd234a13a39aa7a3193a5d1222d1dab5123043d9d0",
    "modules.SHA256SUMS": "18fc3d022405bb7a1f69424a41cc7af5d7608beb6a2d3e5a0b6f9c51a2ef4dbc",
}
INPUT = {
    "nt36523_ts.ko": "cecbd4709f2e6cbb488586ca24f06de6ffe4f7a27fd15bba5ab4649aa29d3972",
    "board.dtb": "af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730",
    "source-manifest.json": "5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0",
}
CERT_SHA256 = "6ee402403dbba5b40e6c0012aa5271b20b8bee376914416d891a791c5aca56e1"
MAGIC = b"~Module signature appended~\n"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(path):
    return {"sha256": digest(path), "size": path.stat().st_size}


def plain_file(root, relative):
    """Reject symlinks in every component, including the file itself."""
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or ".." in parts.parts:
        raise ValueError("non-relative file selection")
    current = root
    if current.is_symlink() or not current.is_dir():
        raise ValueError("source root must be a real directory")
    for part in parts.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink in selected source path: " + relative)
    if not stat.S_ISREG(current.stat().st_mode):
        raise ValueError("selected input is not a regular file: " + relative)
    return current


def run(argv, timeout=60):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # These commands contain only task paths, public certificate information
        # or module metadata. No command prints private key material.
        raise RuntimeError("command failed: " + str(argv[0]) + "\n" + result.stderr[:4000])
    return result.stdout.strip(), result.stderr.strip()


def module_info(path):
    return {name: run(["modinfo", "-F", name, path])[0]
            for name in ("signer", "sig_key", "sig_hashalgo", "vermagic")}


def split_signature(data):
    if not data.endswith(MAGIC) or len(data) < len(MAGIC) + 12:
        raise ValueError("module signature trailer absent")
    header_at = len(data) - len(MAGIC) - 12
    header = data[header_at:header_at + 12]
    # sign-file's PKCS#7 format stores algorithms in CMS, and no inline names.
    if header[:8] != b"\0\0\2\0\0\0\0\0":
        raise ValueError("unsupported module signature trailer")
    length, = struct.unpack(">I", header[8:])
    if not 0 < length < header_at:
        raise ValueError("signature length outside module")
    start = header_at - length
    return data[:start], data[start:header_at]


def verify_cms(signature, content, certificate):
    # -noverify skips a public-CA chain check, NOT signature verification.
    # Trust is checked separately against the exact certificate in the frozen
    # Image and the original signed module. -nointern requires this explicit cert.
    stdout, stderr = run(["openssl", "cms", "-verify", "-inform", "DER",
                          "-in", signature, "-content", content, "-binary",
                          "-noverify", "-nointern", "-certfile", certificate,
                          "-out", "/dev/null"])
    return {"exit_code": 0, "diagnostic": stderr or stdout,
            "signature_verified": True, "public_ca_chain_checked": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, default=Path("/work/research2-display"))
    p.add_argument("--input", type=Path, default=Path("/work/input-integration-v3"))
    p.add_argument("--output", type=Path, default=Path("/work/input-research2-integration-v1"))
    args = p.parse_args()
    for path in (args.baseline, args.input, args.output):
        if path.is_symlink():
            raise SystemExit("do not follow a root symlink")
    baseline, inputs, output = (path.resolve() for path in (args.baseline, args.input, args.output))
    if output.exists():
        raise SystemExit("retain existing bundle; choose a new output")
    for root in (baseline, inputs):
        if output.is_relative_to(root) or root.is_relative_to(output):
            raise SystemExit("output overlaps a frozen input tree")
    for relative, expected in BASE.items():
        if digest(plain_file(baseline, "artifacts/" + relative)) != expected:
            raise SystemExit("frozen baseline artifact changed: " + relative)
    for relative, expected in INPUT.items():
        if digest(plain_file(inputs, "artifacts/" + relative)) != expected:
            raise SystemExit("input artifact changed: " + relative)
    private_key = plain_file(baseline, "kernel-out/certs/signing_key.pem")
    certificate = plain_file(baseline, "kernel-out/certs/signing_key.x509")
    sign_file = plain_file(baseline, "kernel-out/scripts/sign-file")
    key_stat_before = private_key.stat()
    if digest(certificate) != CERT_SHA256:
        raise SystemExit("existing public certificate is not the frozen research2 certificate")
    cert_bytes = certificate.read_bytes()
    if cert_bytes not in (baseline / "artifacts/Image").read_bytes():
        raise SystemExit("exact public certificate absent from the frozen Image")
    module_root = "lib/modules/" + RELEASE + "/"
    checksums = {}
    for line in (baseline / "artifacts/modules.SHA256SUMS").read_text().splitlines():
        sha, rel = line.split(None, 1)
        if rel in checksums or not rel.startswith(module_root + "kernel/") or not rel.endswith(".ko"):
            raise SystemExit("unexpected frozen module inventory entry")
        if len(sha) != 64 or digest(plain_file(baseline, "modules/" + rel)) != sha:
            raise SystemExit("original module does not match the frozen inventory: " + rel)
        checksums[rel] = sha
    replacement_rel = module_root + MODULE_REL
    if len(checksums) != 83 or replacement_rel not in checksums:
        raise SystemExit("expected the complete 83-module research2 set")
    old_module = baseline / "modules" / replacement_rel
    unsigned = inputs / "artifacts/nt36523_ts.ko"
    old_info = module_info(old_module)
    if old_info["sig_hashalgo"] != "sha512" or old_info["vermagic"].split()[0] != RELEASE:
        raise SystemExit("unexpected original module identity")
    if unsigned.read_bytes().endswith(MAGIC):
        raise SystemExit("the new input artifact is already signed")
    output.mkdir(parents=True)
    verify_dir = output / "verification"
    verify_dir.mkdir()
    cert_copy = output / "signing-cert.der"
    shutil.copyfile(certificate, cert_copy)
    cert_pem = verify_dir / "signing-cert.pem"
    run(["openssl", "x509", "-inform", "DER", "-in", cert_copy, "-out", cert_pem])
    if b"PRIVATE KEY" in cert_pem.read_bytes():
        raise SystemExit("certificate conversion unexpectedly contained private material")
    old_payload, old_signature = split_signature(old_module.read_bytes())
    old_payload_file = verify_dir / "baseline-module-payload.bin"
    old_sig_file = verify_dir / "baseline-signature.der"
    old_payload_file.write_bytes(old_payload); old_sig_file.write_bytes(old_signature)
    old_verification = verify_cms(old_sig_file, old_payload_file, cert_pem)
    # Only the explicit module checksum inventory is copied; never build/source
    # symlinks, signing keys, arbitrary source files or other project data.
    for relative in sorted(checksums):
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(unsigned if relative == replacement_rel else baseline / "modules" / relative, destination)
    new_module = output / replacement_rel
    run([sign_file, "sha512", private_key, certificate, new_module])
    new_payload, new_signature = split_signature(new_module.read_bytes())
    if hashlib.sha256(new_payload).hexdigest() != INPUT["nt36523_ts.ko"] or new_payload != unsigned.read_bytes():
        raise SystemExit("sign-file changed the unsigned module payload")
    new_sig_file = verify_dir / "input-signature.der"
    new_sig_file.write_bytes(new_signature)
    new_verification = verify_cms(new_sig_file, unsigned, cert_pem)
    new_info = module_info(new_module)
    if new_info != old_info:
        raise SystemExit("new signature signer/key/hash or module vermagic differs from research2")
    reference = {parts[1]: int(parts[0], 16) for line in
                 (baseline / "artifacts/Module.symvers").read_text().splitlines()
                 if len(parts := line.split()) >= 2}
    imports = {}
    for line in run(["modprobe", "--show-modversions", new_module])[0].splitlines():
        crc, name = line.split()
        if reference.get(name) != int(crc, 16):
            raise SystemExit("signed module CRC differs from research2: " + name)
        imports[name] = crc
    if len(imports) != 63 or "module_layout" not in imports:
        raise SystemExit("signed module imported-symbol inventory differs")
    # depmod writes only this new staging prefix. It does not load modules.
    for name in ("modules.order", "modules.builtin", "modules.builtin.modinfo"):
        shutil.copyfile(plain_file(baseline, "modules/" + module_root + name), output / module_root / name)
    run(["depmod", "-b", output, RELEASE])
    for name in ("Image", "kernel.config", "Module.symvers"):
        shutil.copyfile(baseline / "artifacts" / name, output / name)
    shutil.copyfile(inputs / "artifacts/board.dtb", output / "board.dtb")
    shutil.copyfile(inputs / "artifacts/source-manifest.json", output / "source-manifest-input.json")
    (output / "kernel.release").write_text(RELEASE + "\n")
    staged_modules = {str(path.relative_to(output)): digest(path) for path in
                      (output / module_root / "kernel").rglob("*.ko")}
    if staged_modules.keys() != checksums.keys():
        raise SystemExit("staged module set differs from the complete baseline")
    changed = [rel for rel in checksums if checksums[rel] != staged_modules[rel]]
    if changed != [replacement_rel]:
        raise SystemExit("modules other than the selected input replacement changed")
    for relative, expected in checksums.items():
        if digest(baseline / "modules" / relative) != expected:
            raise SystemExit("original module changed during staging")
    for relative, expected in BASE.items():
        if digest(baseline / "artifacts" / relative) != expected:
            raise SystemExit("original artifact changed during staging")
    key_stat_after = private_key.stat()
    if (key_stat_before.st_size, key_stat_before.st_mtime_ns) != (key_stat_after.st_size, key_stat_after.st_mtime_ns):
        raise SystemExit("existing private-key file metadata changed")
    files = {}
    for path in sorted(output.rglob("*")):
        if path.is_symlink():
            raise SystemExit("unexpected symlink in newly staged bundle")
        if path.is_file():
            files[str(path.relative_to(output))] = identity(path)
    content_map = {relative: record["sha256"] for relative, record in files.items()}
    composition = {"kernel_release": RELEASE, "files": content_map,
                   "public_certificate_der_sha256": CERT_SHA256}
    composition_hash = hashlib.sha256(json.dumps(composition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    result = {
        "schema_version": 1, "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "profile": "frozen research2 Image + signed patched input module + joint display/input DT",
        "evidence_class": "host_build", "kernel_release": RELEASE, "output_directory": str(output),
        "recipe": {"path": "scripts/research/input/signing/stage_signed.py", **identity(Path(__file__))},
        "base_artifacts": BASE, "input_artifacts": INPUT, "files": files,
        "composition_sha256": composition_hash,
        "composition_hash_definition": "SHA256 of UTF-8 json.dumps({kernel_release,files: path-to-sha256,public_certificate_der_sha256}, sort_keys=True,separators=(',',':')); manifest itself excluded",
        "signing": {"existing_project_key_used": True, "private_key_copied": False,
                    "private_key_generated": False, "private_key_material_output": False,
                    "public_certificate_der_sha256": CERT_SHA256,
                    "exact_public_certificate_found_in_frozen_image": True,
                    "sign_file_binary": identity(sign_file),
                    "algorithm": "sha512", "original_module": {**identity(old_module), **old_info},
                    "signed_module": {**identity(new_module), **new_info},
                    "unsigned_payload_sha256": hashlib.sha256(new_payload).hexdigest(),
                    "payload_exactly_matches_unsigned_artifact": True,
                    "baseline_cms_verification": old_verification, "new_cms_verification": new_verification},
        "module_set": {"total": 83, "unchanged": 82, "replaced": changed,
                       "new_module_imports": len(imports), "all_import_crcs_match_baseline": True,
                       "depmod_exit": 0, "baseline_files_unchanged_after_staging": True},
        "new_image_built": False, "module_loaded": False, "kernel_signature_acceptance_tested": False,
        "device_linux_tested": False, "firmware_included": False, "rootfs_included": False,
        "initramfs_included": False, "boot_image_packaged": False,
    }
    manifest = output / "integration-manifest.json"
    manifest.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"offline_integration": "pass", "manifest": str(manifest),
                      "manifest_sha256": digest(manifest), "composition_sha256": composition_hash,
                      "signed_module_sha256": digest(new_module), "device_linux_tested": False}))


if __name__ == "__main__":
    main()
