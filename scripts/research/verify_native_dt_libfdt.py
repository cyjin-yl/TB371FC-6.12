#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Independently read frozen owner DT inputs using existing libfdt tools.

No project DT parser is imported. A small Android-v2/AOSP-table envelope reader
extracts only boot_a DTB index 0 and dtbo_a entry 2 from the hash-pinned backup.
fdtget supplies every DT property value. An optional fdtoverlay invocation is
an offline composition experiment, never an ABL replay or bootability test.
Private DT bytes and raw tool logs remain in a fresh 0700 work directory.

Primary tool/format sources:
https://github.com/dgibson/dtc/blob/main/fdtget.c
https://github.com/dgibson/dtc/blob/main/fdtoverlay.c
https://android.googlesource.com/platform/system/libufdt/+/refs/heads/main/utils/src/dt_table.h
https://source.android.com/docs/core/architecture/bootloader/boot-image-header
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tarfile


ARCHIVE_BYTES = 93319878
ARCHIVE_SHA = "6fb0d1964bef82d0b1bcb91282da48a6223910f5987ab1c8466d5746e7ead8e2"
PARTITIONS = {
    "boot_a": (100663296, "78ba0f4f75bec85a80155a9e9ea8fa19546bbd88598a7923a16b069404899a9a"),
    "dtbo_a": (25165824, "d82c51b5b85c8a9c7d8a163d4fc24e61f7abbd93f5728a7235dcfb809e3b8b17"),
}
BUNDLE_SHA = "7827766497a13ce96161ab3e38b2db4f7238dba3a056793299e911334a1732a4"
TABLE_SHA = "279910628e61cad149ccdb16ae0aa0a3a2f46441e21132ac3a1323e565219679"
IDS = ("qcom,msm-id", "qcom,board-id", "qcom,pmic-id", "qcom,pmic-id-size")
RESERVED = (
    "hyp_region@80000000", "xbl_aop_region@80700000", "removed_region@80b00000",
    "cont_splash_region@9c000000", "disp_rdump_region@9c000000",
    "dfps_data_region@9e300000", "boot_log_region@0", "linux,cma",
)


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique_pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def exact_json(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def read_json(path):
    raw = path.read_bytes()
    need(len(raw) <= 8 * 1024 * 1024, "public reference exceeds limit")
    return json.loads(raw, object_pairs_hook=unique_pairs), sha(raw)


def private_write(path, data):
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def envelope(boot, dtbo):
    """Read only reviewed container offsets; DT structure belongs to libfdt."""
    need(len(boot) == PARTITIONS["boot_a"][0] and boot[:8] == b"ANDROID!", "wrong boot_a envelope")
    fields = struct.unpack_from("<10I", boot, 8)
    kernel, unused, ramdisk, unused, second, unused, unused, page, version, unused = fields
    recovery_size, recovery_offset, header_size, dtb_size, unused = struct.unpack_from("<IQIIQ", boot, 1632)
    need(page == 4096 and version == 2 and header_size == 1660 and second == 0
         and recovery_size == 0, "unreviewed boot_a version-2 profile")
    rounded = lambda size: (size + page - 1) // page * page
    offset = page + rounded(kernel) + rounded(ramdisk) + rounded(second) + rounded(recovery_size)
    need(offset + dtb_size <= len(boot) and dtb_size == 1608875, "invalid boot_a DTB extent")
    bundle = boot[offset:offset + dtb_size]
    need(sha(bundle) == BUNDLE_SHA, "boot_a DTB bundle differs")
    entries, cursor = [], 0
    while cursor < len(bundle):
        need(len(entries) < 8 and cursor + 40 <= len(bundle), "invalid concatenated header")
        magic, size = struct.unpack_from(">II", bundle, cursor)
        need(magic == 0xD00DFEED and 40 <= size <= 2 * 1024 * 1024
             and cursor + size <= len(bundle), "invalid concatenated FDT extent")
        entries.append({"index": len(entries), "offset": cursor, "bytes": size,
                        "sha256": sha(bundle[cursor:cursor + size])})
        cursor += size
    need([item["bytes"] for item in entries] == [538388, 538616, 531698, 173],
         "frozen boot_a concatenation differs")

    header = struct.unpack_from(">8I", dtbo)
    need(header == (0xD7B7AB1E, 4299963, 32, 32, 14, 32, 4096, 0),
         "unreviewed dtbo_a table profile")
    need(sha(dtbo[:header[1]]) == TABLE_SHA, "frozen DT table differs")
    table_entries = []
    for index in range(14):
        size, begin, ident, revision, *custom = struct.unpack_from(">8I", dtbo, 32 + 32 * index)
        need(size >= 40 and begin >= 32 + 32 * 14 and begin + size <= header[1],
             "invalid DT table entry extent")
        table_entries.append({"index": index, "offset": begin, "bytes": size,
                              "id": ident, "rev": revision, "custom": custom,
                              "sha256": sha(dtbo[begin:begin + size])})
    selected = table_entries[2]
    overlay = dtbo[selected["offset"]:selected["offset"] + selected["bytes"]]
    need(struct.unpack_from(">II", overlay) == (0xD00DFEED, len(overlay)),
         "selected overlay is not one exact FDT")
    return bundle[:entries[0]["bytes"]], overlay, {
        "boot_a_dtb_component_offset": offset, "bundle_sha256": BUNDLE_SHA,
        "bundle_entries": entries, "table_sha256": TABLE_SHA,
        "table_entries": table_entries, "dtb_index": 0, "dtbo_index": 2,
        "slot": "_a", "selection_scope": "fixed profile matching reported Android observations; no loader execution",
    }


def extract_inputs(archive_path):
    fd = os.open(archive_path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        need(stat.S_ISREG(before.st_mode) and before.st_size == ARCHIVE_BYTES, "require exact regular backup archive")
        need(hashlib.file_digest(stream, "sha256").hexdigest() == ARCHIVE_SHA, "archive hash mismatch")
        stream.seek(0)
        payloads = {}
        with tarfile.open(fileobj=stream, mode="r:gz") as archive:
            members = archive.getmembers()
            for name, (size, expected_sha) in PARTITIONS.items():
                matches = [item for item in members if item.name == name + ".img"]
                need(len(matches) == 1 and matches[0].isfile() and matches[0].size == size,
                     "partition archive member mismatch")
                with archive.extractfile(matches[0]) as source:
                    data = source.read(size + 1)
                need(len(data) == size and sha(data) == expected_sha, "partition identity mismatch")
                payloads[name] = data
        after = os.fstat(stream.fileno())
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        need(identity(before) == identity(after), "archive changed during extraction")
        stream.seek(0)
        need(hashlib.file_digest(stream, "sha256").hexdigest() == ARCHIVE_SHA, "archive final hash mismatch")
    return envelope(payloads["boot_a"], payloads["dtbo_a"])


def decode_strings(raw):
    if raw is None:
        return None
    need(raw and raw.endswith(b"\0"), "allowlisted property is not a terminated string")
    values = raw[:-1].split(b"\0")
    need(all(value and all(32 <= item < 127 for item in value) for value in values),
         "allowlisted property is not printable ASCII")
    return [value.decode("ascii") for value in values]


def decode_cells(raw):
    if raw is None:
        return None
    need(len(raw) % 4 == 0, "allowlisted numeric property has incomplete u32 cells")
    return list(struct.unpack(">" + "I" * (len(raw) // 4), raw))


def ranges(raw, ac, sc):
    values = decode_cells(raw)
    if values is None:
        return []
    need(ac in (1, 2) and sc in (1, 2) and len(values) > 0 and len(values) % (ac + sc) == 0,
         "independent memory tuple width differs")
    result = []
    for cursor in range(0, len(values), ac + sc):
        start = int.from_bytes(raw[cursor * 4:(cursor + ac) * 4], "big")
        size = int.from_bytes(raw[(cursor + ac) * 4:(cursor + ac + sc) * 4], "big")
        need(start + size <= 1 << 64, "independent memory range overflows")
        result.append({"start": start, "size": size})
    return result


class Commands:
    def __init__(self, work, record):
        self.work, self.record = work, record

    def run(self, argv):
        number = len(self.record["commands"])
        result = subprocess.run([str(item) for item in argv], capture_output=True, timeout=20)
        need(len(result.stdout) <= 262144 and len(result.stderr) <= 262144, "tool output exceeded fixed limit")
        private_write(self.work / "private" / ("command-%03d.stdout" % number), result.stdout)
        private_write(self.work / "private" / ("command-%03d.stderr" % number), result.stderr)
        self.record["commands"].append({"argv": [str(item) for item in argv], "exit_code": result.returncode,
                                        "stdout_sha256": sha(result.stdout), "stderr_sha256": sha(result.stderr)})
        return result

    def tool(self, supplied):
        resolved = shutil.which(supplied)
        need(resolved is not None, "required libfdt tool is unavailable")
        path = Path(resolved).resolve(strict=True)
        version = self.run([path, "-V"])
        need(version.returncode == 0, "libfdt tool version query failed")
        text = (version.stdout + version.stderr).decode("ascii", "strict").strip()
        need(len(text) <= 256 and all(32 <= ord(c) < 127 or c == "\n" for c in text), "invalid tool version text")
        self.record["tools"][path.name] = {"path": str(path), "bytes": path.stat().st_size,
                                          "sha256": sha(path.read_bytes()), "version": text}
        return path

    def query(self, tool, tree, node, prop=None, children=False):
        argv = [tool, "-l", tree, node] if children else [tool, "-t", "bx", tree, node, prop]
        result = self.run(argv)
        if result.returncode:
            need(result.returncode == 1 and b"FDT_ERR_NOTFOUND" in result.stderr, "libfdt query failed beyond an absent property")
            return None
        text = result.stdout.decode("ascii", "strict").strip()
        if children:
            names = text.splitlines() if text else []
            need(len(names) <= 1024 and len(names) == len(set(names))
                 and all(re.fullmatch(r"[A-Za-z0-9,._+@-]{1,255}", name) for name in names), "invalid libfdt child list")
            return names
        fields = text.split()
        need(len(fields) <= 16384 and all(re.fullmatch(r"[0-9a-fA-F]{1,2}", field) for field in fields),
             "invalid libfdt byte output")
        return bytes(int(field, 16) for field in fields)


def inspect_properties(commands, tool, path):
    before = path.read_bytes()
    q = lambda node, prop: commands.query(tool, path, node, prop)
    one = lambda raw, default: default if raw is None else int.from_bytes(raw, "big") if len(raw) == 4 else None
    acraw, scraw = q("/", "#address-cells"), q("/", "#size-cells")
    ac, sc = one(acraw, 2), one(scraw, 1)
    need(ac in (1, 2) and sc in (1, 2), "unsupported root memory cell profile")
    model = decode_strings(q("/", "model"))
    need(model is None or len(model) == 1, "root model is not one string")
    result = {"bytes": len(before), "sha256": sha(before),
              "compatible": decode_strings(q("/", "compatible")) or [],
              "model": model[0] if model else None, "qcom_ids": {},
              "root_cells": {"address": ac, "size": sc}, "memory": [], "reserved_memory": []}
    for prop in IDS:
        value = decode_cells(q("/", prop))
        if value is not None:
            result["qcom_ids"][prop] = value
    children = commands.query(tool, path, "/", children=True)
    need(children is not None, "libfdt root is missing")
    for child in children:
        if child == "memory" or child.startswith("memory@"):
            node = "/" + child
            result["memory"].append({"path": node, "reg": ranges(q(node, "reg"), ac, sc)})
    if "reserved-memory" in children:
        rac, rsc = one(q("/reserved-memory", "#address-cells"), 2), one(q("/reserved-memory", "#size-cells"), 1)
        need(rac in (1, 2) and rsc in (1, 2), "unsupported reserved-memory cell profile")
        result["reserved_memory_cells"] = {"address": rac, "size": rsc,
                                           "empty_ranges": q("/reserved-memory", "ranges") == b""}
        reserved_children = commands.query(tool, path, "/reserved-memory", children=True)
        for child in RESERVED:
            if child not in reserved_children:
                continue
            node = "/reserved-memory/" + child
            item = {"path": node, "reg": ranges(q(node, "reg"), rac, rsc)}
            for prop in ("size", "alignment"):
                value = q(node, prop)
                need(value is None or len(value) == rsc * 4, "reserved scalar width mismatch")
                item[prop] = int.from_bytes(value, "big") if value is not None else None
            item["alloc_ranges"] = ranges(q(node, "alloc-ranges"), rac, rsc)
            for prop in ("no-map", "reusable"):
                value = q(node, prop)
                need(value is None or value == b"", "reserved boolean is not empty")
                item[prop.replace("-", "_")] = value is not None
            result["reserved_memory"].append(item)
    need(path.read_bytes() == before, "private DT input changed during libfdt observation")
    return result


def compare(reference, observed, *, require_same_input=True):
    checks = []
    def check(name, left, right):
        equal = exact_json(left, right)
        checks.append({"field": name, "equal": equal, "reference": left, "libfdt": right})
    if require_same_input:
        need(reference.get("sha256") == observed["sha256"], "comparison inputs have different DT hashes")
    for field in ("compatible", "model", "qcom_ids"):
        check(field, reference[field], observed[field])
    for field in ("address", "size"):
        check("root_cells." + field, reference["root_cells"][field], observed["root_cells"][field])
    for kind, reference_items in (("memory", reference["memory"]),
                                  ("reserved_memory", reference["reserved_memory"]["nodes"])):
        indexed = {item["path"]: item for item in reference_items}
        selected_paths = sorted(indexed) if kind == "memory" else sorted(
            name for name in indexed if name.removeprefix("/reserved-memory/") in RESERVED)
        check(kind + ".selected-paths", selected_paths, sorted(item["path"] for item in observed[kind]))
        for item in observed[kind]:
            if require_same_input:
                need(item["path"] in indexed, "independent libfdt node absent from comparison report")
            for field in item:
                if field != "path":
                    check(item["path"] + ":" + field, indexed.get(item["path"], {}).get(field), item[field])
    return checks


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--fdtget", default="fdtget")
    ap.add_argument("--fdtoverlay", help="optional existing fdtoverlay executable; omitted means do not compose")
    ap.add_argument("--inspection-report", type=Path, help="optional public native_dt backup output for same-byte cross-check")
    ap.add_argument("--live-report", type=Path, help="optional public live Android observation for separately scoped comparison")
    args = ap.parse_args()
    os.umask(0o077)
    work = args.work.resolve()
    work.mkdir(mode=0o700, exist_ok=False)
    (work / "private").mkdir(mode=0o700)
    record = {"schema": "tb371fc-libfdt-independent-dt-check-v1", "started_utc": datetime.now(timezone.utc).isoformat(),
              "source_sha256": sha(Path(__file__).read_bytes()), "archive_sha256": ARCHIVE_SHA,
              "project_dt_parser_imported": False, "tools": {}, "commands": [], "passed": False,
              "pass_scope": "selected libfdt property reads and any explicitly requested cross-check/composition only",
              "parser_crosscheck_performed": False, "independent_property_readback_passed": False,
              "bootloader_selection_replayed": False, "bootloader_acceptance_tested": False,
              "native_memory_layout_qualified": False, "physical_mainline_linux_tested": False,
              "owner_native_linux_passes_added": 0, "overlay_composition": {"attempted": False}}
    try:
        base, overlay, record["container_metadata"] = extract_inputs(args.archive)
        base_path, overlay_path = work / "private/base-index0.dtb", work / "private/overlay-index2.dtbo"
        private_write(base_path, base)
        private_write(overlay_path, overlay)
        commands = Commands(work, record)
        getter = commands.tool(args.fdtget)
        record["base"] = inspect_properties(commands, getter, base_path)
        record["overlay"] = inspect_properties(commands, getter, overlay_path)
        if args.inspection_report:
            report, digest = read_json(args.inspection_report)
            need(report.get("archive_sha256") == ARCHIVE_SHA, "comparison report has wrong archive identity")
            refs = {"base": report["images"]["boot_a"]["components"]["dtb"]["inspection"]["entries"][0]["dt"],
                    "overlay": report["dtbo_partitions"]["dtbo_a"]["inspection"]["entries"][2]["dt"]}
            record["inspection_report_sha256"] = digest
            record["same_input_parser_comparisons"] = {name: compare(refs[name], record[name]) for name in refs}
            record["parser_crosscheck_performed"] = True
            need(all(item["equal"] for rows in record["same_input_parser_comparisons"].values() for item in rows),
                 "independent libfdt properties disagree with project inspection")
        record["independent_property_readback_passed"] = True
        if args.fdtoverlay:
            merger = commands.tool(args.fdtoverlay)
            merged = work / "private/offline-composed.dtb"
            result = commands.run([merger, "-i", base_path, "-o", merged, overlay_path])
            record["overlay_composition"] = {"attempted": True, "exit_code": result.returncode,
                                              "scope": "libfdt offline base0 plus overlay2 only; no ABL fixups or runtime handoff"}
            need(result.returncode == 0, "requested offline overlay composition failed")
            need(merged.is_file() and merged.stat().st_size <= 4 * 1024 * 1024, "invalid offline merged output")
            record["offline_composed"] = inspect_properties(commands, getter, merged)
        if args.live_report:
            live, digest = read_json(args.live_report)
            need(live.get("schema") == "tb371fc-android-native-dt-observation-v1", "wrong live-observation schema")
            obs = live["boot_arguments"]["/proc/cmdline"]["observations"]
            expected = {"dtb_idx": {"indices": [0], "valid": True}, "dtbo_idx": {"indices": [2], "valid": True},
                        "slot_suffix": {"slot_suffix": "_a"}}
            need(all(exact_json(obs["androidboot." + key], [value])
                     and exact_json(live["properties"]["ro.boot." + key], value)
                     for key, value in expected.items()), "reported Android selection is ambiguous or differs from this profile")
            record["live_report_sha256"] = digest
            record["reported_selection_observations_consistent"] = True
            if "offline_composed" in record:
                record["offline_to_live_comparison"] = compare(live["running_fdt"]["inspection"], record["offline_composed"], require_same_input=False)
                record["offline_to_live_scope"] = "selected public fields only; differences retained, not a whole-DT match or bootloader replay"
        record["passed"] = True
    except Exception as exc:
        record["error_type"] = type(exc).__name__
        # Errors contain only our fixed messages, public paths or allowlisted field names.
        record["error"] = str(exc)
    finally:
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        private_write(work / "result.json", (json.dumps(record, indent=2, sort_keys=True) + "\n").encode())
        print(json.dumps({"result": str(work / "result.json"), "passed": record["passed"],
                          "owner_native_linux_passes_added": 0}, sort_keys=True))
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
