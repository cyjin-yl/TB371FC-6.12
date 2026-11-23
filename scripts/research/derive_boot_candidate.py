#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive the R5 boot candidate from frozen public evidence, never from a device.

This checks the recorded build/transfer relationships. It does not re-read the
remote kernel bytes or qualify a root loader, root filesystem, or native entry.
Those still-missing qualifications remain explicit candidate requirements.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys


EVIDENCE = "docs/research/2026-11-23/evidence/"
REPORT = EVIDENCE + "research5-services-build.json"
BUNDLE = EVIDENCE + "research5-services-records/control/shared-transfer/bundle.json"
TRANSFER = EVIDENCE + "research5-services-records/control/shared-transfer/transfer.json"
VERIFICATION = EVIDENCE + "research5-services-verification.json"
FIRMWARE = EVIDENCE + "stock-firmware-staging.json"
INITRAMFS = EVIDENCE + "initramfs-validation.json"
READINESS = "docs/research/2026-11-23/boot-readiness.md"
RELEASE = "6.12.114-tb371fc-research5-services"

# These are published evidence bytes, not a mutable external approval record.
# A later build needs a separately reviewed candidate and new source bindings.
FROZEN_SOURCES = {
    REPORT: (136930, "69d0b558c99bdfb339df8b3b9baca8bb1ee4d0cb2e46dd9b3b7fef3ab69aaad2"),
    BUNDLE: (22269, "b540b71d3d5719265bed35b05016c9e0cbfc988ab17ccb351d14c42610d46c04"),
    TRANSFER: (83440, "6892cdb643e8ab58e55f10e86f7ce45f2ef6bdd22ddaaf400b935900cfc9cb5e"),
    VERIFICATION: (34559, "e1bb04fba61b8d64177853580f826e1e45a1c472670512248d31520162f9f654"),
    FIRMWARE: (222527, "844149c7127d24be684da5e8789755badb210fbef142e1bb5ba001894f1bdb14"),
    INITRAMFS: (104383, "ac4368aaf3d28d545d4c9ff7eb3e5756fc311a8c8b3d586c6936a5850f4ebe0f"),
    READINESS: (8816, "d174996e28f26251789749b5104f99963542e427abfe5cd080604d8bb245254b"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical_path(value):
    require(isinstance(value, str) and bool(value), "empty or non-string path")
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value
            and all(part not in ("", ".", "..") for part in path.parts)
            and "\\" not in value and not any(char.isspace() for char in value),
            "noncanonical relative path: " + repr(value))
    return path


def read_regular(path, limit):
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode), "not an ordinary file: " + str(path))
        require(0 <= before.st_size <= limit, "file outside size bound: " + str(path))
        raw = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    stable = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(stable(before) == stable(after) and len(raw) == before.st_size,
            "file changed while reading: " + str(path))
    return raw


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def record_identity(value):
    require(isinstance(value, dict), "file identity must be an object")
    require(type(value.get("size")) is int and value["size"] >= 0,
            "invalid recorded byte length")
    require(isinstance(value.get("sha256"), str)
            and re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is not None,
            "invalid recorded SHA-256")
    return {"size": value["size"], "sha256": value["sha256"]}


def derive(repo: Path) -> dict:
    """Return the exact, still-blocked candidate; perform no writes or commands."""
    repo = Path(repo)
    require(repo.is_dir() and not repo.is_symlink(), "repository root must be a real directory")
    sources, raw_sources = [], {}
    for name, (size, digest) in sorted(FROZEN_SOURCES.items()):
        parts = canonical_path(name).parts
        cursor = repo
        for part in parts[:-1]:
            cursor = cursor / part
            require(cursor.is_dir() and not cursor.is_symlink(), "symlink or missing evidence directory")
        raw = read_regular(repo / name, size)
        require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest,
                "frozen evidence identity mismatch: " + name)
        raw_sources[name] = raw
        sources.append({"path": name, "bytes": size, "sha256": digest})
    documents = {name: json.loads(raw, object_pairs_hook=unique_object)
                 for name, raw in raw_sources.items() if name.endswith(".json")}
    report, bundle, transfer, verification = (documents[name] for name in
                                             (REPORT, BUNDLE, TRANSFER, VERIFICATION))
    for document in (report, bundle, transfer, verification):
        require(document["kernel_release"] == RELEASE, "inconsistent kernel release")
    require(bundle["source_report_sha256"] == FROZEN_SOURCES[REPORT][1], "bundle/report link differs")
    require(record_identity(transfer["kernel_report"]) ==
            {"size": FROZEN_SOURCES[REPORT][0], "sha256": FROZEN_SOURCES[REPORT][1]},
            "transfer/report link differs")
    require(record_identity(transfer["bundle"]) ==
            {"size": FROZEN_SOURCES[BUNDLE][0], "sha256": FROZEN_SOURCES[BUNDLE][1]},
            "transfer/bundle link differs")
    require(record_identity({"size": verification["kernel_report"]["bytes"],
                             "sha256": verification["kernel_report"]["sha256"]}) ==
            {"size": FROZEN_SOURCES[REPORT][0], "sha256": FROZEN_SOURCES[REPORT][1]},
            "verification/report link differs")

    files = bundle["files"]
    require(isinstance(files, dict) and len(files) == 106, "unexpected complete kernel file set")
    for path, item in files.items():
        canonical_path(path)
        record_identity(item)
    for stage in ("source_before", "source_after", "destination_readback"):
        observed = transfer[stage]
        require(set(observed) == set(files), "transfer file set differs: " + stage)
        for path, expected in files.items():
            item = observed[path]
            require(record_identity(item) == record_identity(expected), "transfer identity differs: " + path)
            require(type(item["mode"]) is int and 0 <= item["mode"] <= 0o777
                    and item["uid"] == item["gid"] == 0, "unexpected recorded metadata: " + path)
            require(item == transfer["source_before"][path], "transfer metadata changed: " + path)
    require(transfer["files_verified"] == verification["shared_regular_files_verified"] == 106,
            "file count disagrees with the actual recorded set")
    for side in ("source_stream", "destination_stream"):
        stream = transfer[side]
        require(stream["bytes"] == verification["shared_stream_bytes"]
                and stream["sha256"] == verification["shared_stream_sha256"]
                and stream["exit_codes"] and all(type(code) is int and code == 0 for code in stream["exit_codes"]),
                "recorded transfer stream mismatch: " + side)
    for name, item in report["files"].items():
        require(files.get("artifacts/" + name) == record_identity(item), "build/artifact identity differs: " + name)

    module_prefix = "modules/lib/modules/" + RELEASE + "/kernel/"
    modules = report["modules"]
    require(isinstance(modules, list) and len(modules) == report["module_count"] == bundle["module_count"] == 84,
            "module count differs")
    module_paths = []
    for module in modules:
        path = "modules/" + module["path"]
        canonical_path(path)
        require(path.startswith(module_prefix) and path.endswith(".ko"), "module is outside the in-tree set")
        require(files.get(path) == record_identity(module), "module identity differs: " + path)
        require(all(module[key] == report["signing"]["module_identity"][key]
                    for key in ("vermagic", "signer", "sig_key", "sig_hashalgo")),
                "module signing/release identity differs: " + path)
        module_paths.append(path)
    require(len(set(module_paths)) == 84 and set(module_paths) == {name for name in files if name.endswith(".ko")},
            "duplicate, missing, or undeclared module")
    for name, metadata in report["module_metadata"].items():
        expected = record_identity(metadata)
        require(files.get("artifacts/" + name) == expected
                and files.get("modules/" + metadata["installed_path"]) == expected,
                "installed module metadata differs: " + name)
    require(report["module_inventory"]["installed_order_sha256"] == files["artifacts/modules.order"]["sha256"],
            "module order binding differs")
    require(report["signing"]["public_certificate"] == files["artifacts/signing-cert.der"],
            "certificate identity differs")
    require(report["source_manifest"]["resolved_config_sha256"] == files["artifacts/kernel.config"]["sha256"],
            "config identity differs")
    require(report["source_manifest"]["expected_dtb_sha256"] == verification["joint_dtb_sha256"]
            == files["artifacts/board.dtb"]["sha256"], "joint DT identity differs")
    require(report["native_dtb"]["root_compatible"] == ["lenovo,tb371fc", "qcom,sm8250"],
            "native board compatible differs")
    header = report["arm64_header"]
    require(set(header) == {"stored_bytes", "text_offset", "image_size", "flags"}
            and all(type(value) is int and value >= 0 for value in header.values())
            and header["stored_bytes"] == files["artifacts/Image"]["size"]
            and header["image_size"] > 0, "ARM64 Image header record differs")
    require(bundle["old_depmod_indexes_included"] is False
            and bundle["private_keys_or_firmware_included"] is False
            and verification["owner_native_linux_runs"] == verification["owner_native_linux_passes"] == 0,
            "recorded qualification boundary changed")

    firmware = documents[FIRMWARE]["build"]["staging_outputs"]["canonical-elf"]
    require(firmware["manifest"]["firmware_file_count"] == len(firmware["manifest"]["files"]) == 69,
            "canonical firmware recorded inventory differs")
    require(documents[INITRAMFS]["full_success_result"]["firmware_manifest"]["sha256"]
            == firmware["manifest_file"]["sha256"], "prior archive/firmware-manifest link differs")

    requirements = [
        {"id": "root_loader", "status": "blocked",
         "reason": "A real root-loading initramfs has not been qualified for this exact R5/native candidate; the prior generic VM archive/probe and Nura qemu-profile boot files do not establish that handoff.",
         "evidence": [READINESS, INITRAMFS]},
        {"id": "rootfs_modules_depmod", "status": "blocked",
         "reason": "The final native rootfs and its exact R5 module installation are unselected/unqualified. Regenerate and verify depmod indexes in that final root; the recorded kernel transfer deliberately excluded old depmod indexes.",
         "evidence": [READINESS, BUNDLE, TRANSFER]},
        {"id": "firmware_candidate_binding", "status": "blocked",
         "reason": "A 69-file canonical ELF firmware tree already exists, but its recorded contract targets research2-display and has not been rebound and payload-verified in this exact R5 root/initramfs. R5 enables the joint input DT; do not repeat the older Novatek-disabled status. Firmware availability is not firmware loading or hardware acceptance.",
         "evidence": [FIRMWARE, REPORT, INITRAMFS]},
        {"id": "wlan_board_data", "status": "not_verified",
         "reason": "The canonical tree preserves WLAN executable inputs; runtime board identity and the matching board-2.bin/board.bin are not established. Compiled support for unrelated WLAN adapters does not make their firmware a TB371FC requirement.",
         "evidence": [FIRMWARE]},
        {"id": "bluetooth_rom_selection", "status": "not_verified",
         "reason": "Bluetooth ROM-specific firmware candidates are preserved, but the runtime ROM selection is not verified.",
         "evidence": [FIRMWARE]},
        {"id": "native_entry_memory_layout", "status": "blocked",
         "reason": "A matched native first-stage/loader, image format, DMA quiescence and non-overlapping load/reserved-memory layout have not been qualified. Use ARM64 image_size and text_offset separately from stored Image length. The running Android kernel lacks the assumed kexec entry, and lock-state sources disagree.",
         "evidence": [READINESS, REPORT]},
        {"id": "reachable_recovery", "status": "blocked",
         "reason": "Eight current boot-related partitions have verified local/off-device backups; an actually reachable recovery/console and demonstrated restore/return path remain unverified. A backup alone is not recovery qualification.",
         "evidence": [READINESS]},
        {"id": "owner_native_linux", "status": "not_verified",
         "reason": "The frozen R5 workflow records zero owner native-Linux runs/passes. Host build, transfer and generic VM evidence do not establish a tablet boot or whole-device operation.",
         "evidence": [VERIFICATION, READINESS]},
    ]
    return {
        "schema_version": 1,
        "kind": "tb371fc-r5-boot-candidate",
        "candidate_id": "tb371fc-r5-native-boot-candidate-v1",
        "evidence_sources": sources,
        "kernel": {
            "release": RELEASE,
            "artifacts": {"image": "artifacts/Image", "dtb": "artifacts/board.dtb",
                          "config": "artifacts/kernel.config", "certificate": "artifacts/signing-cert.der"},
            "arm64_header": dict(header),
            "compatible": list(report["native_dtb"]["root_compatible"]),
            "module_count": 84,
        },
        "kernel_files": [{"path": path, "bytes": files[path]["size"], "sha256": files[path]["sha256"],
                          "mode": transfer["destination_readback"][path]["mode"]} for path in sorted(files)],
        "boot_requirements": requirements,
    }


def encoded(candidate):
    return (json.dumps(candidate, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    destination = parser.add_mutually_exclusive_group()
    destination.add_argument("--output", type=Path, help="create this new file exclusively; never replace it")
    destination.add_argument("--check", type=Path, help="compare this existing candidate with deterministic derivation")
    args = parser.parse_args(argv)
    try:
        candidate = derive(args.repo)
        raw = encoded(candidate)
        if args.check:
            require(read_regular(args.check, len(raw)) == raw, "candidate differs from frozen evidence derivation")
            action, path = "checked", args.check
        elif args.output:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644)
            with os.fdopen(fd, "wb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            action, path = "created", args.output
        else:
            sys.stdout.buffer.write(raw)
            return 0
        print(json.dumps({"action": action, "path": str(path), "bytes": len(raw),
                          "sha256": hashlib.sha256(raw).hexdigest(), "kernel_files": len(candidate["kernel_files"]),
                          "module_count": candidate["kernel"]["module_count"], "native_boot_ready": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
