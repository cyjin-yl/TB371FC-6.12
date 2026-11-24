#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Qualify research5 Image, complete signed modules, BTF and joint native DT.

Offline only. Separate NixOS and Nura system VM runs own runtime acceptance. No
module is loaded and no physical device is accessed by this inspector.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import stat
import struct
import subprocess
import sys
import tempfile

import build_system as profile

INVENTORY_HELPER_SHA = "2cac7d0bfdf13d449349e6482c75ceda261ec7d67acd0c677490843f8591a875"
SIGNATURE_HELPER_SHA = "ad270d83f89ce08d2488906b8246167227e0e352a91294042489d0a0737908df"
OLD_CERT_SHA = "6ee402403dbba5b40e6c0012aa5271b20b8bee376914416d891a791c5aca56e1"


def command(argv):
    result = subprocess.run(list(map(str, argv)), text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(str(argv[0]) + " failed: " + result.stderr[:4000])
    return result.stdout.strip()


def btf_header(data):
    if len(data) < 24:
        raise ValueError("BTF header truncated")
    magic, version, flags, header_len, type_off, type_len, string_off, string_len = struct.unpack_from("<HBBIIIII", data)
    if magic != 0xEB9F or version != 1 or flags != 0 or header_len != 24:
        raise ValueError("unexpected little-endian BTF header")
    if not type_len or not string_len or header_len + type_off + type_len > len(data) or header_len + string_off + string_len != len(data):
        raise ValueError("BTF sections outside their declared extent")
    if data[header_len + string_off] != 0:
        raise ValueError("BTF string table does not start with its empty entry")
    return {"magic": "0xeb9f", "version": version, "type_bytes": type_len, "string_bytes": string_len,
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def dt_summary(work, input_manifest):
    recipe = work / "source-input/input-recipe/scripts/research/input"
    helper = recipe / "inspect_input.py"
    expected = input_manifest["input_copies"]["scripts/research/input/inspect_input.py"]
    if profile.digest(helper) != expected:
        raise RuntimeError("frozen input DT parser changed")
    sys.path.insert(0, str(recipe))
    try:
        helper_api = runpy.run_path(str(helper))
    finally:
        sys.path.pop(0)
    decode, strings, cells = (helper_api[name] for name in ("dt_nodes", "text", "cells"))
    nodes = decode(work / "artifacts/board.dtb")
    baseline = decode(work / "source-input/baseline-abi/display.dtb")
    spi = "/soc@0/geniqup@8c0000/spi@880000"
    touch = spi + "/touchscreen@0"
    keyboards = [n for n in nodes if n.endswith("/i2c@a94000/keyboard-cover@60")]
    if len(keyboards) != 1:
        raise ValueError("expected exactly one keyboard-cover node")
    keyboard = keyboards[0]
    changes = {(node, prop) for node in nodes.keys() | baseline.keys()
               for prop in nodes.get(node, {}).keys() | baseline.get(node, {}).keys()
               if nodes.get(node, {}).get(prop) != baseline.get(node, {}).get(prop)}
    if nodes.keys() != baseline.keys() or changes != {("/", "model"), (spi, "status"), (touch, "status"), (keyboard, "status")}:
        raise ValueError("joint DT has changes outside the qualified input overlay")
    if strings(nodes["/"]["compatible"]) != ["lenovo,tb371fc", "qcom,sm8250"]:
        raise ValueError("native DT compatible changed")

    def available(node):
        current = node
        while True:
            if strings(nodes[current].get("status", b"okay\0"))[0] not in ("ok", "okay"):
                return False
            if current == "/":
                return True
            current = current.rsplit("/", 1)[0] or "/"

    for node in (spi, touch, keyboard, keyboard.rsplit("/", 1)[0]):
        if not available(node):
            raise ValueError("input node or ancestor unavailable: " + node)
    if "touchscreen-x-mm" in nodes[touch] or "touchscreen-y-mm" in nodes[touch]:
        raise ValueError("unmeasured touchscreen physical dimensions introduced")
    mdss = "/soc@0/display-subsystem@ae00000"
    display = [mdss, mdss + "/display-controller@ae01000", mdss + "/phy@ae94400", mdss + "/phy@ae96400",
               mdss + "/dsi@ae94000", mdss + "/dsi@ae96000", mdss + "/dsi@ae94000/panel@0"]
    if any(not available(node) for node in display):
        raise ValueError("qualified display node is unavailable")

    gpu = "/soc@0/gpu@3d00000"
    iommu = "/soc@0/iommu@3da0000"
    expected_compat = ["qcom,sm8250-smmu-500", "qcom,adreno-smmu", "qcom,smmu-500", "arm,mmu-500"]
    if strings(nodes[iommu]["compatible"]) != expected_compat or nodes[iommu].get("dma-coherent") != b"":
        raise ValueError("GPU IOMMU compatible/dma-coherent contract changed")
    refs = {cells(props["phandle"])[0]: name for name, props in nodes.items() if "phandle" in props}
    raw = cells(nodes[gpu]["iommus"])
    resolved, pos = [], 0
    while pos < len(raw):
        phandle = raw[pos]; pos += 1
        target = refs.get(phandle)
        if target is None:
            raise ValueError("GPU iommus has an unresolved phandle")
        n = cells(nodes[target]["#iommu-cells"])
        if len(n) != 1 or pos + n[0] > len(raw):
            raise ValueError("GPU iommus argument length mismatch")
        resolved.append({"path": target, "phandle": phandle, "arguments": raw[pos:pos + n[0]]})
        pos += n[0]
    if not resolved or any(item["path"] != iommu for item in resolved):
        raise ValueError("GPU iommus does not point at the qualified Adreno SMMU")
    if nodes[gpu]["iommus"] != baseline[gpu]["iommus"]:
        raise ValueError("GPU IOMMU reference changed from research2")
    return {"parser_sha256": expected, "model": strings(nodes["/"]["model"])[0],
            "root_compatible": strings(nodes["/"]["compatible"]),
            "joint_dtb_matches_qualified_sha256": True,
            "exact_changes_from_display_only": [{"path": n, "property": p} for n, p in sorted(changes)],
            "display_nodes_available": display,
            "input_nodes": {"spi": spi, "touchscreen": touch, "keyboard": keyboard, "all_available": True,
                            "physical_touchscreen_dimensions_mm": None,
                            "boe_firmware": strings(nodes[touch]["novatek,boe-firmware-name"]),
                            "tianma_firmware": strings(nodes[touch]["novatek,tianma-firmware-name"])},
            "gpu_iommu": {"gpu_path": gpu, "gpu_available": available(gpu), "iommu_path": iommu,
                          "iommu_available": available(iommu), "compatible": expected_compat,
                          "dma_coherent": True, "gpu_iommus_raw_cells": raw, "gpu_iommus_resolved": resolved,
                          "reference_unchanged_from_research2": True,
                          "historical_adreno_smmu_removal_applied": False,
                          "runtime_per_process_address_spaces_verified": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("/work/research5-services"))
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--baseline-repo", type=Path, default=Path("/work/research2-repo"))
    parser.add_argument("--attempt", type=int, default=1)
    args = parser.parse_args()
    work, repo = args.work.resolve(), args.repo.resolve()
    artifacts = work / "artifacts"
    destination = artifacts / "research5-services-build.json"
    attempt = work / f"inspection-attempt-{args.attempt:02d}.json"
    if destination.exists() or attempt.exists() or args.attempt < 1:
        raise SystemExit("preserve earlier inspection records")
    record = {"schema_version": 1, "profile": "research5-services", "evidence_class": "host_build",
              "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "kernel_release": profile.RELEASE, "work_directory": str(work),
              "physical_hardware_tested": False, "generic_vm_test_performed_by_this_inspector": False,
              "recipes": {"build_system.py": profile.identity(Path(profile.__file__)),
                          "inspect_system.py": profile.identity(Path(__file__)),
                          "system.config": profile.identity(work / "system.config")}}
    try:
        input_manifest = profile.verify_source(work)
        checked = profile.verify_config(work)
        cfg_record = json.loads((work / "configuration.json").read_text())
        if profile.digest(artifacts / "kernel.config") != cfg_record["config_sha256"]:
            raise ValueError("artifact configuration is not the reviewed configuration")
        if (artifacts / "kernel.release").read_text().strip() != profile.RELEASE:
            raise ValueError("artifact kernel release differs")
        if profile.digest(artifacts / "board.dtb") != profile.DTB_SHA:
            raise ValueError("compiled joint DT does not match its qualification")
        for name in ("source-manifest.json", "configuration.json"):
            if profile.digest(artifacts / name) != profile.digest(work / name):
                raise ValueError("artifact/source metadata mismatch: " + name)
        image = (artifacts / "Image").read_bytes()
        if len(image) < 64 or image[56:60] != b"ARM\x64":
            raise ValueError("artifact is not an ARM64 Image")
        offset, effective_size, flags = struct.unpack_from("<QQQ", image, 8)
        if effective_size < len(image):
            raise ValueError("invalid ARM64 effective image size")
        for value in (b"lenovo,tb371fc-dpu\0", b"lenovo,tb371fc-dsi-phy-7nm\0"):
            if value not in image:
                raise ValueError("native display compatible absent from linked Image")
        cert = artifacts / "signing-cert.der"
        cert_bytes = cert.read_bytes()
        if profile.digest(cert) in (OLD_CERT_SHA, profile.R4_CERT_SHA) or cert_bytes not in image:
            raise ValueError("new Image does not contain its independent public signing certificate")
        key = work / "kernel-out/certs/signing_key.pem"
        if key.is_symlink() or not key.is_file() or stat.S_IMODE(key.stat().st_mode) & 0o077:
            raise ValueError("new private key is absent or not owner-only")
        btf = (artifacts / "kernel.btf").read_bytes()
        btf_record = btf_header(btf)
        if btf not in image:
            raise ValueError("extracted kernel BTF bytes absent from uncompressed Image")
        btf_record["exact_bytes_present_in_image"] = True
        record["arm64_header"] = {"text_offset": offset, "image_size": effective_size,
                                  "flags": flags, "stored_bytes": len(image)}
        record["kernel_btf"] = btf_record
        record["native_dtb"] = dt_summary(work, input_manifest)

        inventory_path = args.baseline_repo / "scripts/research/build/inspect_kernel.py"
        signature_path = repo / "scripts/research/input/signing/stage_signed.py"
        if profile.digest(inventory_path) != INVENTORY_HELPER_SHA or profile.digest(signature_path) != SIGNATURE_HELPER_SHA:
            raise ValueError("reused inventory/signature helper differs from its pin")
        inventory_api = runpy.run_path(str(inventory_path))
        signature_api = runpy.run_path(str(signature_path))
        modules, inventory = inventory_api["module_inventory"](work, profile.RELEASE)
        reference = {}
        for line in (artifacts / "Module.symvers").read_text().splitlines():
            fields = line.split()
            if len(fields) < 2:
                raise ValueError("invalid exported symbol record")
            crc, name = int(fields[0], 16), fields[1]
            if name in reference and reference[name] != crc:
                raise ValueError("ambiguous exported symbol CRC")
            reference[name] = crc
        verification = work / "verification"
        verification.mkdir(exist_ok=True)
        pem = verification / "signing-cert.pem"
        if pem.exists():
            raise ValueError("preserve existing verification prefix")
        command(["openssl", "x509", "-inform", "DER", "-in", cert, "-out", pem])
        if b"PRIVATE KEY" in pem.read_bytes():
            raise ValueError("unexpected private material in public certificate")
        module_records, checksums, identities = [], [], set()
        for path in modules:
            relative = path.relative_to(work / "modules").as_posix()
            raw = path.read_bytes()
            if raw[:6] != b"\x7fELF\x02\x01" or int.from_bytes(raw[18:20], "little") != 183:
                raise ValueError("module is not AArch64 ELF: " + relative)
            info = signature_api["module_info"](path)
            if info["vermagic"].split()[0] != profile.RELEASE or info["sig_hashalgo"] != "sha512":
                raise ValueError("module release/signature hash mismatch: " + relative)
            identities.add(tuple(info[name] for name in ("signer", "sig_key", "sig_hashalgo", "vermagic")))
            imports = {}
            for line in command(["modprobe", "--show-modversions", path]).splitlines():
                crc, name = line.split()
                if name in imports or reference.get(name) != int(crc, 16):
                    raise ValueError("module imported symbol CRC mismatch: " + relative + ":" + name)
                imports[name] = crc
            if not imports or "module_layout" not in imports:
                raise ValueError("module version imports absent: " + relative)
            sections = command(["llvm-readelf", "--section-headers", "--wide", path])
            names = set(re.findall(r"\]\s+(\S+)\s+\S+", sections))
            if ".BTF" not in names or any(n.startswith(".debug_") for n in names):
                raise ValueError("module BTF/strip contract differs: " + relative)
            payload, signature = signature_api["split_signature"](raw)
            with tempfile.TemporaryDirectory(prefix="cms-", dir=verification) as tmp:
                content_path, sig_path = Path(tmp) / "payload.elf", Path(tmp) / "signature.der"
                content_path.write_bytes(payload); sig_path.write_bytes(signature)
                signature_api["verify_cms"](sig_path, content_path, pem)
            entry = {"path": relative, **profile.identity(path), **info,
                     "imported_symbol_crc_count": len(imports), "all_imported_crcs_match": True,
                     "import_map_sha256": hashlib.sha256(json.dumps(imports, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                     "payload_sha256": hashlib.sha256(payload).hexdigest(),
                     "cms_sha256": hashlib.sha256(signature).hexdigest(), "cms_verified": True,
                     "module_btf_present": True, "dwarf_debug_sections_stripped": True}
            if any(s in relative for s in ("nt36523/", "/autofs/", "tb371fc", "panel-novatek", "/venus/", "ath11k")):
                entry["aliases"] = command(["modinfo", "-F", "alias", path]).splitlines()
                entry["firmware_names"] = command(["modinfo", "-F", "firmware", path]).splitlines()
            module_records.append(entry)
            checksums.append(entry["sha256"] + "  " + relative + "\n")
        if len(identities) != 1:
            raise ValueError("module signer/key/hash/vermagic are not uniform")
        if not any(item["path"].endswith("/kernel/fs/autofs/autofs4.ko") for item in module_records):
            raise ValueError("new autofs4 module absent")
        baseline_index = work / "baseline-r4/modules.SHA256SUMS"
        before = {line.split(None, 1)[1].split("/kernel/", 1)[1] for line in baseline_index.read_text().splitlines()}
        after = {item["path"].split("/kernel/", 1)[1] for item in module_records}
        if len(before) != 84 or len(module_records) != 84 or before != after:
            raise ValueError("builtin service additions must preserve the complete R4 module path set")
        for item in module_records:
            if profile.digest(work / "modules" / item["path"]) != item["sha256"]:
                raise ValueError("module bytes changed during inspection")
        checksum_path = artifacts / "modules.SHA256SUMS"
        with checksum_path.open("x") as stream:
            stream.write("".join(checksums))
        module_metadata = {}
        for name in ("modules.order", "modules.builtin", "modules.builtin.modinfo"):
            relative = Path("lib/modules") / profile.RELEASE / name
            source = work / "modules" / relative
            target = artifacts / name
            if source.is_symlink() or not source.is_file() or target.exists():
                raise ValueError("installed module metadata missing/unsafe or already staged: " + name)
            shutil.copyfile(source, target)
            target.chmod(0o644)
            module_metadata[name] = {"installed_path": relative.as_posix(),
                                     "artifact_name": name, **profile.identity(target)}
        packages = artifacts / "builder-packages.tsv"
        with packages.open("x") as stream:
            stream.write(command(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n"]) + "\n")
        jobs = {}
        for path in sorted((work / "jobs").glob("*.json")):
            log = path.with_suffix(".log")
            jobs[path.stem] = {"result": json.loads(path.read_text()), "result_sha256": profile.digest(path),
                               "log_sha256": profile.digest(log)}
        files = {p.name: profile.identity(p) for p in sorted(artifacts.iterdir()) if p.is_file()}
        record.update({"passed": True, "full_image_built": True, "complete_modules_installed": True,
                       "joint_native_dtb_built": True, "module_loaded_by_inspector": False,
                       "files": files, "configuration_changes": checked["changes"],
                       "resolved_config": checked["required"], "preserved_security": checked["preserved_security"],
                       "source_manifest": json.loads((artifacts / "source-manifest.json").read_text()),
                       "module_count": len(modules), "module_inventory": inventory, "modules": module_records,
                       "module_metadata": module_metadata,
                       "module_set_changes_from_research4": {"added": sorted(after - before), "removed": sorted(before - after)},
                       "all_module_vermagic_matches": True, "all_modules_elf_aarch64": True,
                       "all_module_imported_crcs_match_new_build": True,
                       "all_module_cms_signatures_verified": True, "all_module_btf_present": True,
                       "all_module_dwarf_debug_sections_stripped": True,
                       "signing": {"public_certificate": profile.identity(cert),
                                   "public_certificate_exact_bytes_in_image": True,
                                   "all_modules_same_signer_key_hash_vermagic": True,
                                   "module_identity": dict(zip(("signer", "sig_key", "sig_hashalgo", "vermagic"), next(iter(identities)))),
                                   "new_private_key_owner_only": True, "private_key_copied_from_old_build": False,
                                   "private_key_read_or_hashed_by_inspector": False,
                                   "openssl_cms_signature_checked": True, "public_ca_chain_checked": False},
                       "reused_helpers": {"module_inventory_sha256": INVENTORY_HELPER_SHA,
                                          "module_signature_parser_sha256": SIGNATURE_HELPER_SHA},
                       "jobs": jobs, "bit_identical_independent_rebuild_proven": False,
                       "limits": ["New module-signing key changes artifact bytes; package versions are recorded, not snapshot-pinned.",
                                  "Offline inspection does not establish runtime BPF LSM attachment, automount or PIDs enforcement.",
                                  "NixOS/Nura generic system VM validation is recorded separately; physical tablet entry and hardware remain untested."]})
        profile.write_new(destination, record)
        index = {**files, destination.name: profile.identity(destination)}
        with (artifacts / "qualified-artifacts.SHA256SUMS").open("x") as stream:
            stream.write("".join(value["sha256"] + "  " + name + "\n" for name, value in sorted(index.items())))
    except Exception as exc:
        record["passed"] = False
        record["failure"] = str(exc)
        raise
    finally:
        profile.write_new(attempt, record)
    print(json.dumps({"passed": True, "kernel_release": profile.RELEASE, "module_count": record["module_count"],
                      "report": str(destination), "report_sha256": profile.digest(destination),
                      "kernel_btf_sha256": record["kernel_btf"]["sha256"], "physical_hardware_tested": False}))


if __name__ == "__main__":
    main()
