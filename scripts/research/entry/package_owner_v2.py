#!/usr/bin/env python3
"""Assemble a private, unsigned FORMAT-ONLY entry container from owner recovery_a.

This reads regular backup/artifact files only. It never opens a device, flashes,
boots, signs, changes AVB policy, or changes the source backup's permissions.
Raw owner header strings and official-unpacker stdout stay in the new private
output directory. Public output contains only numeric layout and hashes.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys
import urllib.request

OWNER_SHA = "94649360140db672e861729927011984e9714459b4e19c9aab02b7ab79466668"
OWNER_BYTES = 104857600
OWNER_LAYOUT_SHA = "831ee408abed2e9ca0b3f4ac093cab760f7ee4a53dda0638658c463815ba97a7"
INSPECTOR_SHA = "b24f1c36248cd1203347549be500ef7e3274d1586a4e00bbb9db1a3fc9da87b4"
AOSP_REV = "8d0922bfb932ee532226728b1bf2fe54a2055f5a"
AOSP_TOOLS = {
    "unpack_bootimg.py": "64e5440b190e96a7b51243bcfdc72320a8d77e17b0986ece88607e0868ca2465",
    "mkbootimg.py": "beedcf77c9dd2603ef21f01dcf2bf9043579facc22a9973f749055162e4d510b",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_info(path):
    raw = path.read_bytes()
    return {"path": str(path), "bytes": len(raw), "sha256": sha(raw)}


def module_from(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cpio_entries(compressed):
    """Bounded newc parsing in memory; never extract archive paths/devices."""
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
        raw = source.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("rescue archive exceeds the reviewed limit")
    offset, result = 0, {}
    while offset + 110 <= len(raw):
        header = raw[offset:offset + 110]
        if header[:6] != b"070701":
            raise ValueError("not a newc archive")
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        size, namesize = fields[6], fields[11]
        if not 1 <= namesize <= 1024:
            raise ValueError("invalid newc name size")
        namebytes = raw[offset + 110:offset + 110 + namesize]
        if len(namebytes) != namesize or not namebytes.endswith(b"\0"):
            raise ValueError("truncated newc name")
        name = namebytes[:-1].decode("utf-8")
        begin = (offset + 110 + namesize + 3) & ~3
        end = begin + size
        if end > len(raw):
            raise ValueError("truncated newc file")
        if name == "TRAILER!!!":
            if size or any(raw[(end + 3) & ~3:]):
                raise ValueError("unexpected newc trailer/payload")
            return result
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or name in result:
            raise ValueError("unsafe or duplicate rescue path")
        result[name] = {"mode": fields[1], "data": raw[begin:end]}
        offset = (end + 3) & ~3
    raise ValueError("missing newc trailer")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=Path("/src"))
    ap.add_argument("--owner-recovery-a", required=True, type=Path)
    ap.add_argument("--kernel-manifest", required=True, type=Path)
    ap.add_argument("--userspace-manifest", required=True, type=Path)
    ap.add_argument("--userspace-vm", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()
    if sys.byteorder != "little":
        ap.error("the pinned AOSP tools use native little-endian struct formats")
    os.umask(0o077)
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    record = {"schema": "tb371fc-owner-v2-format-only-v1",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "private unsigned Android v2 container format only",
              "default_action": "hold", "format_verified": False,
              "tablet_booted": False, "bootloader_acceptance_tested": False,
              "runtime_load_addresses_verified": False, "board_driver_contract_verified": False,
              "avb_signature_verified": False, "rollback_compatibility_verified": False,
              "kexec_handoff_tested": False, "recovery_return_tested": False,
              "source_backup_permissions_changed": False,
              "recipe_sha256": sha(Path(__file__).read_bytes())}
    try:
        repo = args.repo.resolve(strict=True)
        inspector_path = repo / "scripts/research/inspect_boot_backup.py"
        layout_path = repo / "docs/research/2026-11-23/evidence/boot-header-inspection.json"
        if sha(inspector_path.read_bytes()) != INSPECTOR_SHA or sha(layout_path.read_bytes()) != OWNER_LAYOUT_SHA:
            raise ValueError("frozen owner layout/inspector drift")
        inspector = module_from(inspector_path, "owner_numeric_boot_inspector")
        expected_owner = json.loads(layout_path.read_text())["images"]["recovery_a"]
        owner_path = args.owner_recovery_a.resolve(strict=True)
        if not owner_path.is_file() or owner_path.stat().st_size != OWNER_BYTES:
            raise ValueError("require the exact regular owner recovery_a backup")
        owner = owner_path.read_bytes()
        if sha(owner) != OWNER_SHA:
            raise ValueError("owner recovery_a hash mismatch")
        original = inspector.inspect(io.BytesIO(owner), len(owner))
        if original["header"] != expected_owner["header"] or original["components"] != expected_owner["components"]:
            raise ValueError("owner component layout differs from the captured backup")
        h = original["header"]
        if h["page_size"] != 4096 or h["second_size"] != 0 or not h["recovery_dtbo_size"] or not h["dtb_size"]:
            raise ValueError("unreviewed owner v2 component shape")
        page = h["page_size"]
        cmdline_bytes = owner[64:576].split(b"\0", 1)[0] + owner[608:1632].split(b"\0", 1)[0]
        tokens = cmdline_bytes.decode("utf-8").split()
        conflicts = []
        for token in tokens:
            key, _, value = token.partition("=")
            if key in {"skip_initramfs", "tb371fc.entry_smoke"} or (key in {"init", "rdinit"} and value != "/init"):
                conflicts.append(key)
        if conflicts:
            # Do not echo the owner's raw command-line values.
            raise ValueError("stored owner command line conflicts with hold init: " + ",".join(sorted(set(conflicts))))
        record["owner"] = {"partition_sha256": OWNER_SHA, "partition_bytes": OWNER_BYTES,
                           "layout_evidence_sha256": OWNER_LAYOUT_SHA,
                           "inspector_sha256": INSPECTOR_SHA,
                           "header_page_sha256": sha(owner[:page]),
                           "stored_cmdline_sha256": sha(cmdline_bytes),
                           "stored_cmdline_token_count": len(tokens),
                           "stored_init_override_conflicts": [],
                           "bootloader_appended_cmdline_observed": False}

        km = args.kernel_manifest.resolve(strict=True)
        um = args.userspace_manifest.resolve(strict=True)
        vm = args.userspace_vm.resolve(strict=True)
        kernel, user, proof = [json.loads(p.read_text()) for p in [km, um, vm]]
        if kernel.get("schema") != "tb371fc-downstream-entry-build-v1" or kernel.get("build_completed") is not True:
            raise ValueError("downstream kernel build not completed")
        if user.get("schema") != "tb371fc-clean-entry-userspace-v1" or user.get("completed") is not True or user.get("default_action") != "hold":
            raise ValueError("userspace is not the clean hold build")
        image = (km.parent / "artifacts/Image").read_bytes()
        ramdisk = (um.parent / "artifacts/entry-initramfs.cpio.gz").read_bytes()
        if sha(image) != kernel["artifacts"]["Image"]["sha256"] or sha(ramdisk) != user["artifacts"]["entry-initramfs.cpio.gz"]["sha256"]:
            raise ValueError("built payload checksum mismatch")
        if image[56:60] != b"ARM\x64" or not ramdisk.startswith(b"\x1f\x8b"):
            raise ValueError("unexpected payload format")
        if proof.get("controller_result") != "pass" or proof.get("initramfs_sha256") != sha(ramdisk) or proof.get("entry_ready_observed") is not True:
            raise ValueError("no matching rescue userspace VM observation")
        entries = cpio_entries(ramdisk)
        if sha(entries["init"]["data"]) != user["recipe_hashes"]["ramdisk-init"] or entries["init"]["mode"] != 0o100755:
            raise ValueError("ramdisk init differs from the reviewed hold source")
        for name in ("busybox", "kexec", "entry-return-bootloader"):
            if sha(entries["bin/" + name]["data"]) != user["artifacts"][name]["sha256"]:
                raise ValueError("ramdisk executable differs from its build")
        if sorted(entries) != sorted(item["path"] for item in user["cpio_entries"]):
            raise ValueError("unexpected rescue archive entries")
        record["build_inputs"] = {"kernel_manifest": file_info(km), "userspace_manifest": file_info(um),
                                   "userspace_vm": file_info(vm), "kernel_release": kernel["release"],
                                   "userspace_vm_scope": proof["scope"],
                                   "init_source_sha256": user["recipe_hashes"]["ramdisk-init"]}
        payloads = {"kernel": image, "ramdisk": ramdisk, "second": b""}
        for comp in original["components"]:
            if comp["name"] in {"recovery_dtbo", "dtb"}:
                payloads[comp["name"]] = owner[comp["offset"]:comp["offset"] + comp["bytes"]]
        header = bytearray(owner[:page])
        struct.pack_into("<I", header, 8, len(image))
        struct.pack_into("<I", header, 16, len(ramdisk))
        dtbo_offset = page + ((len(image) + page - 1) // page) * page + ((len(ramdisk) + page - 1) // page) * page
        struct.pack_into("<Q", header, 1636, dtbo_offset)
        ident = hashlib.sha1()
        for name in ("kernel", "ramdisk", "second", "recovery_dtbo", "dtb"):
            ident.update(payloads[name])
            ident.update(struct.pack("<I", len(payloads[name])))
        header[576:608] = ident.digest() + bytes(12)
        allowed = set(range(8, 12)) | set(range(16, 20)) | set(range(576, 608)) | set(range(1636, 1644))
        changed = [i for i, (a, z) in enumerate(zip(owner[:page], header)) if a != z]
        if not set(changed) <= allowed:
            raise ValueError("unexpected change outside size/offset/image-ID fields")
        assembled = bytearray(header)
        for name in ("kernel", "ramdisk", "second", "recovery_dtbo", "dtb"):
            assembled.extend(payloads[name])
            assembled.extend(bytes(-len(assembled) % page))
        if len(assembled) >= OWNER_BYTES or assembled[-64:-60] == b"AVBf":
            raise ValueError("unexpected candidate extent or AVB footer")
        destination = output / "entry-r1-owner-recovery-a-unsigned-v2.img"
        with destination.open("xb") as stream:
            stream.write(assembled)
        decoded = inspector.inspect(io.BytesIO(assembled), len(assembled))
        if decoded["partition_padding_or_trailer_bytes"] != 0:
            raise ValueError("unexpected candidate trailer")
        expected_names = [n for n in payloads if payloads[n]]
        if [c["name"] for c in decoded["components"]] != expected_names:
            raise ValueError("unexpected candidate component list")
        for comp in decoded["components"]:
            if comp["sha256"] != sha(payloads[comp["name"]]) or comp["bytes"] != len(payloads[comp["name"]]):
                raise ValueError("candidate numeric reinspection mismatch")
        record["candidate"] = dict(file_info(destination), layout=decoded,
                                    header_page_sha256=sha(header), changed_header_byte_offsets=changed,
                                    all_other_header_bytes_identical=True,
                                    owner_dtb_and_recovery_dtbo_identical=True,
                                    source_partition_padding_or_avb_copied=False,
                                    avb_footer_present=False, partition_padded=False)

        # Independent fixed AOSP extraction, with its raw stdout kept private.
        toolroot = output / "aosp-tools"
        toolroot.mkdir(mode=0o700)
        record["aosp_tools"] = {}
        for name, expected in AOSP_TOOLS.items():
            url = f"https://android.googlesource.com/platform/system/tools/mkbootimg/+/{AOSP_REV}/{name}?format=TEXT"
            encoded = urllib.request.urlopen(url, timeout=30).read(128 * 1024)
            raw = base64.b64decode(encoded.strip(), validate=True)
            if sha(raw) != expected:
                raise ValueError("fixed AOSP tool checksum mismatch")
            path = toolroot / name
            with path.open("xb") as stream:
                stream.write(raw)
            record["aosp_tools"][name] = {"commit": AOSP_REV, "url": url, "sha256": expected}
        extracted = output / "aosp-extracted"
        result = subprocess.run([sys.executable, toolroot / "unpack_bootimg.py", "--boot_img", destination,
                                 "--out", extracted], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        (output / "aosp-unpack-private.log").write_bytes(result.stdout)
        if result.returncode:
            raise ValueError("independent AOSP unpack failed; raw details retained privately")
        independent = {}
        for name in expected_names:
            p = extracted / name
            independent[name] = file_info(p)
            if independent[name]["sha256"] != sha(payloads[name]) or independent[name]["bytes"] != len(payloads[name]):
                raise ValueError("independent AOSP payload differs: " + name)
        official = module_from(toolroot / "mkbootimg.py", "fixed_aosp_mkbootimg")
        aosp_id = hashlib.sha1()
        for name in ("kernel", "ramdisk", "second", "recovery_dtbo", "dtb"):
            if payloads[name]:
                with (extracted / name).open("rb") as stream:
                    official.update_sha(aosp_id, stream)
            else:
                official.update_sha(aosp_id, None)
        if aosp_id.digest() + bytes(12) != bytes(header[576:608]):
            raise ValueError("independent AOSP image ID differs")
        record["independent_aosp_verification"] = {"exit_code": result.returncode,
            "payloads": independent, "image_id_matches": True,
            "private_stdout_published": False, "source_hashes_verified": True}
        record["format_verified"] = True
    except Exception as exc:
        record["failure"] = str(exc)
        raise
    finally:
        record["ended_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "format-manifest.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
