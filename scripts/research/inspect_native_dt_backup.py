#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect exact backed-up DT inputs without extracting private image bytes.

The compressed backup and every inspected partition must match the published
2026-11-23 backup receipt. No device is opened and no overlay is applied.
Output is hash/numeric/public board metadata, not raw private firmware.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

import inspect_boot_backup
import native_dt
from inspect_boot_backup import inspect as inspect_boot
from native_dt import inspect_dt_bundle, inspect_dt_table

EXPECTED_ARCHIVE_SHA = "6fb0d1964bef82d0b1bcb91282da48a6223910f5987ab1c8466d5746e7ead8e2"
EXPECTED_ARCHIVE_BYTES = 93319878
PARTITIONS = {f"{base}_{slot}": size for base, size in
              (("boot", 100663296), ("recovery", 104857600),
               ("vbmeta", 65536), ("dtbo", 25165824)) for slot in ("a", "b")}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def inspect_backup(archive_path, reference):
    if reference.get("archive_sha256") != EXPECTED_ARCHIVE_SHA or reference.get("archive_bytes") != EXPECTED_ARCHIVE_BYTES:
        raise ValueError("reference is not the frozen owner backup")
    records = reference.get("verified_partitions", [])
    if len(records) != len(PARTITIONS) or {r["name"] for r in records} != set(PARTITIONS):
        raise ValueError("reference partition set differs")
    expected = {r["name"]: r for r in records}
    fd = os.open(archive_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size != EXPECTED_ARCHIVE_BYTES:
            raise ValueError("require the exact regular archive file")
        if hashlib.file_digest(stream, "sha256").hexdigest() != EXPECTED_ARCHIVE_SHA:
            raise ValueError("backup archive hash differs")
        stream.seek(0)
        result = {
            "schema": "tb371fc-owner-backup-dt-inspection-v1",
            "inspected_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "evidence_class": "owner_backup_format_inspection",
            "archive_sha256": EXPECTED_ARCHIVE_SHA,
            "archive_bytes": EXPECTED_ARCHIVE_BYTES,
            "images": {}, "dtbo_partitions": {},
            "bootloader_selection_verified": False,
            "overlays_applied": False, "native_load_layout_verified": False,
            "avb_signature_verified": False, "restore_tested": False,
            "owner_native_linux_passes_added": 0,
        }
        with tarfile.open(fileobj=stream, mode="r:gz") as archive:
            members = archive.getmembers()
            names = {"started.json", "manifest.json"} | {n+s for n in PARTITIONS for s in (".img", ".json")}
            if len(members) != len(names) or {m.name for m in members} != names:
                raise ValueError("archive member set differs")
            for m in members:
                limit = PARTITIONS.get(m.name[:-4]) if m.name.endswith(".img") else None
                if not m.isfile() or (limit is not None and m.size != limit) or (limit is None and not 0 < m.size <= 65536):
                    raise ValueError("invalid archive member type or size")
            for name in PARTITIONS:
                if name.startswith("vbmeta"):
                    continue
                member = archive.getmember(name + ".img")
                with archive.extractfile(member) as source:
                    data = source.read(member.size + 1)
                if len(data) != PARTITIONS[name] or len(data) != expected[name]["bytes"] or digest(data) != expected[name]["sha256"]:
                    raise ValueError("inspected partition differs from reference: " + name)
                if name.startswith("dtbo"):
                    result["dtbo_partitions"][name] = {
                        "partition_bytes": len(data), "partition_sha256": digest(data),
                        "inspection": inspect_dt_table(data, allow_partition_tail=True),
                    }
                    continue
                layout = inspect_boot(io.BytesIO(data), len(data))
                record = {"partition_bytes": len(data), "partition_sha256": digest(data), "components": {}}
                for component in layout["components"]:
                    if component["name"] not in ("dtb", "recovery_dtbo"):
                        continue
                    start, size = component["offset"], component["bytes"]
                    payload = data[start:start + size]
                    if digest(payload) != component["sha256"]:
                        raise ValueError("component changed while inspecting")
                    record["components"][component["name"]] = {
                        "offset": start, "bytes": size, "sha256": digest(payload),
                        "inspection": inspect_dt_bundle(payload),
                    }
                result["images"][name] = record
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError("archive changed during inspection")
        stream.seek(0)
        if hashlib.file_digest(stream, "sha256").hexdigest() != EXPECTED_ARCHIVE_SHA:
            raise ValueError("archive changed before final readback")
        result["archive_stable_across_two_hash_reads"] = True
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--reference", required=True, type=Path)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    reference_bytes = args.reference.read_bytes()
    reference = json.loads(reference_bytes, object_pairs_hook=unique_pairs)
    result = inspect_backup(args.archive, reference)
    result["reference_sha256"] = digest(reference_bytes)
    result["source_sha256"] = digest(Path(__file__).read_bytes())
    result["dependency_sha256"] = {
        "native_dt.py": digest(Path(native_dt.__file__).read_bytes()),
        "inspect_boot_backup.py": digest(Path(inspect_boot_backup.__file__).read_bytes()),
    }
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as target:
            target.write(output)
            target.flush()
            os.fsync(target.fileno())
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
