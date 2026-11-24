#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage a separate R5 signed 0020+0021 Novatek module set, offline only.

The input is the already built, pinned unsigned module. The original signing
key is used only by sign-file; it is neither copied nor printed. No module is
loaded, no target root is activated, and frozen R5 inputs are never edited.
Host depmod is provisional: target-distribution depmod remains a later gate.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys

import stage_signed as signing

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "rootfs"))
import qualify_boot_bundle as qualification
import boot_rootfs
import stage_r5_fedora as common

RELEASE = common.RELEASE
MODULE = signing.MODULE_REL
UNSIGNED_SHA = "998623b5b8d5666493162b04b01e3b3453777b3586d644d2296b23674881dc69"
UNSIGNED_SIZE = 698512
CERT_SHA = "07a54ba929080f3c5d74cb485afeca7d7acf7c920fde0b26cf003ba45fd57627"
BASE_MODULE_SHA = "898aeaad7fdf7425ca514035ad6b2fe3c32c43ecde78b7dc9fff3098149f8f37"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def elf_btf(data):
    """Read BTF section payload identities from an ordinary ARM64 ET_REL ELF."""
    require(len(data) >= 64 and data[:7] == b"\x7fELF\x02\x01\x01",
            "expected little-endian ELF64")
    require(struct.unpack_from("<HH", data, 16) == (1, 183), "expected AArch64 ET_REL")
    offset, = struct.unpack_from("<Q", data, 40)
    size, count, names = struct.unpack_from("<HHH", data, 58)
    require(size == 64 and 0 < names < count and offset >= 64
            and offset + size * count <= len(data), "invalid section header table")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, offset + i * size)
                for i in range(count)]

    def payload(section):
        require(section[1] != 8 and section[4] + section[5] <= len(data),
                "invalid file-backed ELF section")
        return data[section[4]:section[4] + section[5]]

    require(sections[names][1] == 3, "invalid section name string table")
    strings = payload(sections[names])
    found = {}
    debug_count = 0
    for section in sections:
        name_offset = section[0]
        end = strings.find(b"\0", name_offset)
        require(0 <= name_offset < len(strings) and end >= name_offset,
                "invalid ELF section name")
        name = strings[name_offset:end].decode("ascii")
        if name.startswith((".debug_", ".zdebug_")):
            debug_count += 1
        if name == ".BTF" or name.startswith(".BTF."):
            value = payload(section)
            require(name not in found and len(value) > 0, "duplicate/empty BTF section")
            found[name] = {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    require(".BTF" in found, "module BTF missing")
    return found, debug_count


def parse_versions(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) == 2 and re.fullmatch(r"0x[0-9a-fA-F]{1,8}", fields[0]),
                "invalid imported CRC row")
        crc, symbol = fields
        require(symbol not in result, "duplicate imported CRC symbol")
        result[symbol] = int(crc, 16)
    require("module_layout" in result, "module_layout CRC missing")
    return result


def symvers(text):
    result = {}
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) >= 2 and re.fullmatch(r"0x[0-9a-fA-F]{1,8}", fields[0]),
                "invalid Module.symvers row")
        crc, symbol = fields[:2]
        value = int(crc, 16)
        require(symbol not in result or result[symbol] == value, "conflicting exported CRC")
        result[symbol] = value
    return result


def check_versions(imports, exports):
    require(imports and all(exports.get(k) == v for k, v in imports.items()),
            "imported CRC absent or differs from frozen R5")


def cms(work, name, data, cert):
    payload, signature = signing.split_signature(data)
    p, s = work / (name + ".payload"), work / (name + ".cms")
    p.write_bytes(payload)
    s.write_bytes(signature)
    return payload, signing.verify_cms(s, p, cert)


def stage(repo, kernel_root, signing_build, unsigned, work):
    require(work.parent == Path("/work") and work.name.startswith("r5-novatek-signed-"),
            "choose a new dedicated /work/r5-novatek-signed-* directory")
    qualification.validate_output_destination(work, (repo, kernel_root, signing_build, unsigned.parent))
    for p in (repo, kernel_root, signing_build, unsigned, work):
        require(not p.is_symlink(), "symlinked top-level input/output")
    require(not work.exists(), "new output directory required")
    candidate_path = repo / "docs/research/2026-11-23/boot-candidate-r5.json"
    contract = qualification.read_candidate(candidate_path)
    pre = qualification.qualify(repo, contract, kernel_root=kernel_root)
    require(pre["kernel_payload"]["status"] == "verified", "frozen kernel qualification failed")
    selected = common.selected_modules(contract)
    require(selected[MODULE]["sha256"] == BASE_MODULE_SHA, "wrong original Novatek module")
    want = common.check(unsigned, UNSIGNED_SHA)
    require(want["bytes"] == UNSIGNED_SIZE, "wrong unsigned build size")
    original_bytes = unsigned.read_bytes()
    require(not original_bytes.endswith(signing.MAGIC), "input is already signed")
    btf_before, debug_before = elf_btf(original_bytes)
    cert = signing.plain_file(kernel_root, "artifacts/signing-cert.der")
    build_cert = signing.plain_file(signing_build, "kernel-out/certs/signing_key.x509")
    require(signing.digest(cert) == CERT_SHA and cert.read_bytes() == build_cert.read_bytes(),
            "existing certificate does not match R5")
    require(cert.read_bytes() in (kernel_root / "artifacts/Image").read_bytes(),
            "certificate not in frozen Image")
    key = signing.plain_file(signing_build, "kernel-out/certs/signing_key.pem")
    sign_file = signing.plain_file(signing_build, "kernel-out/scripts/sign-file")
    key_meta = key.stat()
    old = kernel_root / "modules/lib/modules" / RELEASE / MODULE
    old_info = signing.module_info(old)
    require(old_info["sig_hashalgo"] == "sha512" and old_info["signer"] and old_info["sig_key"],
            "unexpected baseline signing identity")
    require(signing.module_info(unsigned)["vermagic"] == old_info["vermagic"]
            and old_info["vermagic"].split()[0] == RELEASE, "vermagic mismatch")
    imports = parse_versions(signing.run(["modprobe", "--show-modversions", unsigned])[0])
    check_versions(imports, symvers((kernel_root / "artifacts/Module.symvers").read_text()))
    work.mkdir(mode=0o700)
    report = {"schema_version": 1, "complete": False, "kernel_release": RELEASE,
              "scope": "offline derived module root; host depmod only",
              "owner_native_linux_passes_added": 0, "module_loaded": False,
              "target_depmod_verified": False, "native_boot_readiness": "blocked"}
    try:
        common.save(work / "frozen-kernel-gate.json", pre)
        verify = work / "verification"
        verify.mkdir()
        pem = verify / "cert.pem"
        signing.run(["openssl", "x509", "-inform", "DER", "-in", cert, "-out", pem])
        _, report["original_cms"] = cms(verify, "baseline", old.read_bytes(), pem)
        # Strip only debug sections, before signing. BTF bytes and imported
        # CRCs must survive this actual operation; never strip a signed module.
        stripped = verify / "stripped.ko"
        shutil.copyfile(unsigned, stripped)
        report["strip_tool"] = signing.run(["llvm-strip", "--version"])[0]
        signing.run(["llvm-strip", "--strip-debug", stripped])
        btf_after, debug_after = elf_btf(stripped.read_bytes())
        require(btf_after == btf_before and debug_after == 0,
                "debug stripping changed BTF or retained debug sections")
        require(parse_versions(signing.run(["modprobe", "--show-modversions", stripped])[0]) == imports,
                "debug stripping changed imported CRCs")
        require(signing.module_info(stripped)["vermagic"] == old_info["vermagic"],
                "debug stripping changed vermagic")
        root = work / "rootfs"
        root.mkdir()
        dest = root / "lib/modules" / RELEASE
        dest.mkdir(parents=True)
        source = kernel_root / "modules/lib/modules" / RELEASE
        for name, expected in sorted(selected.items()):
            target = common.under(dest, name, mkdir=True)
            if name == MODULE:
                shutil.copyfile(stripped, target)
                target.chmod(expected["mode"])
            else:
                common.copy_exact(common.under(source, name), target, expected)
        new = dest / MODULE
        signing.run([sign_file, "sha512", key, build_cert, new])
        payload, report["replacement_cms"] = cms(verify, "replacement", new.read_bytes(), pem)
        require(payload == stripped.read_bytes(), "signing changed stripped module bytes")
        require(signing.module_info(new) == old_info, "replacement signing identity differs")
        require(parse_versions(signing.run(["modprobe", "--show-modversions", new])[0]) == imports,
                "signing changed imported CRCs")
        replacement = common.identity(new)
        require(replacement["sha256"] != BASE_MODULE_SHA, "replacement unchanged")
        # A distinct inventory, never a rewrite of the frozen R5 candidate.
        derived = copy.deepcopy(contract)
        derived["candidate_id"] = "tb371fc-r5-novatek-0020-0021-derived-offline"
        selected_path = "modules/lib/modules/" + RELEASE + "/" + MODULE
        matches = [entry for entry in derived["kernel_files"] if entry["path"] == selected_path]
        require(len(matches) == 1, "unexpected replacement inventory count")
        matches[0].update(replacement)
        report["host_depmod_version"] = signing.run(["depmod", "--version"])[0]
        report["host_depmod_argv"] = ["depmod", "-b", str(root), RELEASE]
        signing.run(report["host_depmod_argv"])
        inspected = boot_rootfs.inspect_root_module_tree(root, derived)
        common.save(work / "derived-root-module-gate.json", inspected)
        require(inspected["passed"], "derived root module tree failed offline gate")
        tree = {p.relative_to(dest).as_posix(): common.identity(p)
                for p in sorted(dest.rglob("*")) if p.is_file() and not p.is_symlink()}
        for name, expected in selected.items():
            require(tree.get(name) == (replacement if name == MODULE else expected),
                    "module or Kbuild file changed after depmod")
        post = qualification.qualify(repo, contract, kernel_root=kernel_root)
        require(post["kernel_payload"]["status"] == "verified", "frozen input changed")
        require(common.identity(unsigned) == want, "unsigned input changed")
        now = key.stat()
        require((now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) ==
                (key_meta.st_dev, key_meta.st_ino, key_meta.st_size, key_meta.st_mtime_ns),
                "signing key metadata changed")
        report.update(complete=True, unsigned=want, stripped=common.identity(stripped),
                      replacement=replacement, btf=btf_after, debug_sections_before=debug_before,
                      debug_sections_after=debug_after, imported_crcs=imports,
                      signer=old_info, public_certificate_sha256=CERT_SHA,
                      frozen_inputs_verified_after=True, module_count=84,
                      unchanged_modules=83, host_depmod_exit_code=0, module_tree=tree,
                      recipe=common.identity(Path(__file__)))
        common.save(work / "derived-module-inventory.json", {
            "candidate_id": derived["candidate_id"], "kernel_release": RELEASE,
            "replacement_path": selected_path, "frozen_original": selected[MODULE],
            "replacement": replacement, "module_tree": tree})
    except BaseException as exc:
        report["failure"] = str(exc)
        raise
    finally:
        common.save(work / "r5-novatek-stage.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "kernel-root", "signing-build", "unsigned", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    a = parser.parse_args()
    stage(a.repo, a.kernel_root, a.signing_build, a.unsigned, a.work)


if __name__ == "__main__":
    main()
