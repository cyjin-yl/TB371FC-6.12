#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Correlate public owner DT metadata; never replay ABL or apply an overlay.

Exit 0 means that available, valid reported slot/index observations consistently
name entries in the inspected backup. Exit 2 retains unresolved/invalid/conflicting
reports. Neither result establishes per-byte runtime DT selection, free RAM, a
usable native boot layout, recovery, or an owner-native Linux hardware pass.
The original live/nonconformant format observations remain visible.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


SCHEMA = "tb371fc-native-dt-correlation-v1"
MAX_JSON = 16 * 1024 * 1024
U64_LIMIT = 1 << 64
SHA = re.compile(r"[0-9a-f]{64}\Z")
PATH = re.compile(r"/(?:memory(?:@[A-Za-z0-9,._+-]+)?|reserved-memory/[A-Za-z0-9,._+@-]+)\Z")


class CorrelationError(ValueError):
    pass


def need(value, message):
    if not value:
        raise CorrelationError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def decode(data):
    need(type(data) is bytes and 0 < len(data) <= MAX_JSON, "JSON input must be bounded bytes")
    def bad_constant(unused):
        raise CorrelationError("nonfinite JSON number")
    try:
        result = json.loads(data, object_pairs_hook=unique_pairs, parse_constant=bad_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise CorrelationError("invalid UTF-8 JSON document") from exc
    need(type(result) is dict, "document root must be an object")
    return result


def integer(value, label, *, positive=False, limit=U64_LIMIT):
    need(type(value) is int and (0 < value if positive else 0 <= value) and value < limit,
         label + " must be a bounded integer, not bool/float")
    return value


def boolean(value, label):
    need(type(value) is bool, label + " must be bool")
    return value


def sha(value):
    need(type(value) is str and SHA.fullmatch(value) is not None, "invalid SHA-256 identity")
    return value


def strings(value, label):
    need(type(value) is list and len(value) <= 1024, label + " must be a bounded list")
    need(all(type(x) is str and 0 < len(x) <= 4096 and all(32 <= ord(c) < 127 for c in x)
             for x in value), label + " contains an invalid public string")
    return value


def ranges(value):
    need(type(value) is list and len(value) <= 4096, "invalid memory range list")
    result = []
    for item in value:
        need(type(item) is dict and set(item) == {"start", "size"}, "invalid memory range shape")
        start, size = integer(item["start"], "range start"), integer(item["size"], "range size")
        need(start + size <= U64_LIMIT, "memory range overflows")
        result.append({"start": start, "size": size})
    return result


def merge_ranges(items):
    merged = []
    for start, end in sorted((r["start"], r["start"] + r["size"]) for r in items if r["size"]):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [{"start": start, "size": end - start} for start, end in merged]


def subtract(left, right):
    output = []
    for item in merge_ranges(left):
        cursor, end = item["start"], item["start"] + item["size"]
        for other in merge_ranges(right):
            start2, end2 = other["start"], other["start"] + other["size"]
            if end2 <= cursor:
                continue
            if start2 >= end:
                break
            if start2 > cursor:
                output.append({"start": cursor, "size": start2 - cursor})
            cursor = max(cursor, end2)
            if cursor >= end:
                break
        if cursor < end:
            output.append({"start": cursor, "size": end - cursor})
    return output


def public_identity(dt):
    need(type(dt) is dict and dt.get("schema") == "tb371fc-native-dt-metadata-v1", "unrecognized FDT metadata schema")
    sha(dt.get("sha256"))
    size = integer(dt.get("bytes"), "FDT bytes", positive=True)
    need(type(dt.get("totalsize")) is int and dt["totalsize"] == size, "FDT extent identity mismatch")
    need(dt.get("runtime_selection_verified") is False and dt.get("physical_boot_tested") is False
         and type(dt.get("owner_native_linux_passes_added")) is int
         and dt["owner_native_linux_passes_added"] == 0, "unsupported FDT proof scope")
    compliant = boolean(dt.get("format_compliant"), "format_compliant")
    diagnostic = boolean(dt.get("diagnostic_nonzero_padding_allowed"), "diagnostic mode")
    issues = dt.get("format_issues")
    need(type(issues) is list and len(issues) <= 4096, "invalid format issue list")
    for issue in issues:
        need(type(issue) is dict and set(issue) == {"offset", "length", "nonzero_count"},
             "format diagnostic must contain numeric metadata only")
        offset = integer(issue["offset"], "padding offset")
        length = integer(issue["length"], "padding length", positive=True, limit=4)
        count = integer(issue["nonzero_count"], "padding count", positive=True, limit=4)
        need(count <= length and offset + length <= size, "padding diagnostic outside FDT")
    need(compliant == (not issues) and (not issues or diagnostic), "inconsistent format diagnostic state")
    need(dt.get("format_compliance_scope") == "bounded binary FDT profile; not complete binding validation", "unrecognized format compliance scope")
    ids = dt.get("qcom_ids")
    need(type(ids) is dict and set(ids) <= {"qcom,msm-id", "qcom,board-id", "qcom,pmic-id", "qcom,pmic-id-size"}, "invalid root ID allowlist")
    for value in ids.values():
        need(type(value) is list and 0 < len(value) <= 1024, "invalid root ID array")
        for number in value:
            integer(number, "root ID", limit=1 << 32)
    model = dt.get("model")
    if model is not None:
        strings([model], "root model")
    return {"bytes": size, "sha256": dt["sha256"], "compatible": strings(dt.get("compatible"), "compatible"),
            "model": model, "qcom_ids": ids}


def memory_summary(dt):
    public_identity(dt)
    memory = dt.get("memory")
    need(type(memory) is list and len(memory) <= 4096, "invalid memory-node list")
    seen, banks, placeholders = set(), [], []
    for item in memory:
        need(type(item) is dict and type(item.get("path")) is str
             and PATH.fullmatch(item["path"]) is not None and not item["path"].startswith("/reserved-memory/"), "invalid memory path")
        need(item["path"] not in seen, "duplicate memory node")
        seen.add(item["path"])
        active = boolean(item.get("enabled"), "memory enabled")
        recognized = boolean(item.get("device_type_is_memory"), "memory device type")
        declared = ranges(item.get("reg"))
        if active and recognized:
            banks.extend(r for r in declared if r["size"])
            placeholders.extend({"path": item["path"], **r} for r in declared if not r["size"])
    reserved = dt.get("reserved_memory")
    need(type(reserved) is dict and type(reserved.get("nodes")) is list and len(reserved["nodes"]) <= 4096, "invalid reserved-memory list")
    present = boolean(reserved.get("present"), "reserved-memory present")
    qualified = False
    if present:
        qualified = boolean(reserved.get("physical_address_interpretation_qualified"), "reserved-memory physical interpretation")
    else:
        need(not reserved["nodes"], "absent reserved-memory has nodes")
    static = ranges(dt.get("memreserve"))
    nodes, dynamic = {}, []
    for item in reserved["nodes"]:
        need(type(item) is dict and type(item.get("path")) is str
             and PATH.fullmatch(item["path"]) is not None and item["path"].startswith("/reserved-memory/"), "invalid reservation path")
        path = item["path"]
        need(path not in nodes, "duplicate reservation node")
        enabled = boolean(item.get("enabled"), "reservation enabled")
        allocation = item.get("allocation")
        need(allocation in ("static", "dynamic", "unspecified"), "unknown reservation allocation")
        record = {"path": path, "enabled": enabled, "allocation": allocation,
                  "reg": ranges(item.get("reg")), "alloc_ranges": ranges(item.get("alloc_ranges")),
                  "no_map": boolean(item.get("no_map"), "no_map"),
                  "reusable": boolean(item.get("reusable"), "reusable")}
        for field in ("size", "alignment"):
            record[field] = None if item.get(field) is None else integer(item[field], "reservation " + field)
        need(not (record["no_map"] and record["reusable"]), "conflicting reservation flags")
        nodes[path] = record
        if enabled and allocation == "dynamic":
            dynamic.append(record)
        if enabled and qualified:
            static.extend(record["reg"])
    static_union = merge_ranges(static)
    need(static_union == ranges(dt.get("described_static_exclusion_union")), "derived static exclusion union differs from declarations")
    overlap_input = dt.get("reservation_overlaps")
    need(type(overlap_input) is list and len(overlap_input) <= 4096, "invalid reservation overlap list")
    overlaps = []
    for item in overlap_input:
        need(type(item) is dict and set(item) == {"left", "right", "start", "size"}, "invalid reservation overlap")
        for side in ("left", "right"):
            need(type(item[side]) is str and (PATH.fullmatch(item[side]) is not None
                 or re.fullmatch(r"memreserve\[[0-9]{1,4}\]", item[side]) is not None), "invalid overlap path")
        span = ranges([{k: item[k] for k in ("start", "size")}])[0]
        overlaps.append({"left": item["left"], "right": item["right"], **span})
    need(len(overlaps) <= 4096, "too many reservation overlaps")
    return {"banks": banks, "bank_union": merge_ranges(banks),
            "bank_bytes_sum": sum(r["size"] for r in banks), "zero_size_placeholders": placeholders,
            "static_exclusion_union": static_union, "reservation_nodes": nodes,
            "dynamic_reservations": dynamic, "reservation_overlaps": overlaps,
            "issues": strings(dt.get("memory_map_issues"), "memory-map issues")}


def validate_container(container):
    need(type(container) is dict and container.get("schema") == "tb371fc-native-dt-metadata-v1", "invalid DT container metadata")
    kind = container.get("kind")
    need(kind in ("concatenated-fdt", "android-dt-table"), "unsupported DT container kind")
    size = integer(container.get("bytes"), "container bytes", positive=True)
    sha(container.get("sha256"))
    entries = container.get("entries")
    need(type(entries) is list and 0 < len(entries) <= 1024, "invalid DT entries")
    count = integer(container.get("entry_count"), "entry_count", positive=True)
    need(count == len(entries), "entry_count mismatch")
    extent = size
    if kind == "android-dt-table":
        extent = integer(container.get("table_bytes"), "table bytes", positive=True)
        sha(container.get("table_sha256"))
        need(extent <= size, "table exceeds container")
    cursor = 0
    for expected_index, entry in enumerate(entries):
        need(type(entry) is dict, "invalid entry object")
        need(integer(entry.get("index"), "entry index") == expected_index, "entry indices must be unique and in exact order")
        offset = integer(entry.get("offset"), "entry offset")
        length = integer(entry.get("bytes"), "entry bytes", positive=True)
        need(offset + length <= extent, "entry exceeds its container")
        sha(entry.get("sha256"))
        identity = public_identity(entry.get("dt"))
        need(entry["dt"].get("format_compliant") is True
             and entry["dt"].get("diagnostic_nonzero_padding_allowed") is False
             and entry["dt"].get("format_issues") == [], "backup artifact was not strictly parsed")
        if kind == "concatenated-fdt":
            need(offset == cursor, "concatenated FDT offset gap or overlap")
            cursor += length
        compression = 0 if kind == "concatenated-fdt" else integer(entry.get("compression"), "compression", limit=3)
        if compression == 0:
            need(length == identity["bytes"] and entry["sha256"] == identity["sha256"], "uncompressed entry identity mismatch")
        memory_summary(entry["dt"])
    if kind == "concatenated-fdt":
        need(cursor == size, "concatenated FDT extent mismatch")
    return container


def validate_inputs(backup, live):
    need(backup.get("schema") == "tb371fc-owner-backup-dt-inspection-v1", "unrecognized backup schema")
    need(live.get("schema") == "tb371fc-android-native-dt-observation-v1", "unrecognized live schema")
    need(backup.get("archive_stable_across_two_hash_reads") is True, "backup archive stability absent")
    need(backup.get("bootloader_selection_verified") is False and backup.get("overlays_applied") is False
         and live.get("bootloader_selection_replayed") is False and live.get("physical_mainline_linux_tested") is False,
         "unsupported input proof scope")
    for record in (backup, live):
        need(type(record.get("owner_native_linux_passes_added")) is int
             and record["owner_native_linux_passes_added"] == 0, "input adds unsupported native passes")
        sha(record.get("source_sha256"))
    sha(backup.get("archive_sha256"))
    integer(backup.get("archive_bytes"), "archive bytes", positive=True)
    sha(live.get("parser_sha256"))
    need(type(backup.get("dependency_sha256")) is dict
         and backup["dependency_sha256"].get("native_dt.py") == live["parser_sha256"], "input parser identities differ")
    images = backup.get("images")
    need(type(images) is dict and set(images) == {"boot_a", "boot_b", "recovery_a", "recovery_b"}, "backup image set differs")
    for name, image in images.items():
        sha(image.get("partition_sha256"))
        length = integer(image.get("partition_bytes"), "partition bytes", positive=True)
        components = image.get("components")
        expected = {"dtb", "recovery_dtbo"} if name.startswith("recovery") else {"dtb"}
        need(type(components) is dict and set(components) == expected, "backup DT component set differs")
        for component in components.values():
            need(type(component) is dict, "invalid component object")
            offset = integer(component.get("offset"), "component offset")
            size = integer(component.get("bytes"), "component bytes", positive=True)
            need(offset + size <= length, "component exceeds partition")
            c = validate_container(component.get("inspection"))
            need(component.get("sha256") == c["sha256"] and size == c["bytes"], "component wrapper identity mismatch")
    partitions = backup.get("dtbo_partitions")
    need(type(partitions) is dict and set(partitions) == {"dtbo_a", "dtbo_b"}, "backup DTBO partition set differs")
    for partition in partitions.values():
        need(type(partition) is dict, "invalid partition object")
        container = validate_container(partition.get("inspection"))
        need(container["kind"] == "android-dt-table", "DTBO partition is not a DT table")
        need(partition.get("partition_sha256") == container["sha256"]
             and type(partition.get("partition_bytes")) is int
             and partition["partition_bytes"] == container["bytes"], "partition wrapper identity mismatch")
    running = live.get("running_fdt")
    need(type(running) is dict and running.get("stable_across_two_reads") is True, "live FDT stability absent")
    identity = public_identity(running.get("inspection"))
    need(running.get("sha256") == identity["sha256"] and type(running.get("bytes")) is int
         and running["bytes"] == identity["bytes"], "live FDT wrapper identity mismatch")
    memory_summary(running["inspection"])


def observation(value, slot=False):
    if type(value) is not dict:
        return "invalid", None
    if set(value) == {"present"} and value["present"] is False:
        return "missing", None
    if set(value) == {"unavailable"}:
        return "unavailable", None
    if slot:
        if set(value) == {"slot_suffix"} and value["slot_suffix"] in ("_a", "_b"):
            return "valid", value["slot_suffix"]
        return "invalid", None
    if set(value) != {"valid", "indices"} or value["valid"] is not True:
        return "invalid", None
    numbers = value["indices"]
    if (type(numbers) is not list or not 1 <= len(numbers) <= 64
            or any(type(i) is not int or not 0 <= i < 1 << 32 for i in numbers)
            or len(set(numbers)) != len(numbers)):
        return "invalid", None
    return "valid", numbers


def resolve_report(live, suffix):
    slot = suffix == "slot_suffix"
    prop, arg = "ro.boot." + suffix, "androidboot." + suffix
    need(type(live.get("properties")) is dict and type(live.get("boot_arguments")) is dict,
         "invalid boot-observation maps")
    collected, issues = [], []
    def record(source, raw):
        state, value = observation(raw, slot=slot)
        if state == "valid" and suffix == "dtb_idx" and len(value) != 1:
            state, value = "invalid", None
        item = {"source": source, "state": state}
        if value is not None:
            item["value"] = value
        collected.append(item)
        if state == "invalid":
            issues.append("invalid-reported-value:" + source)
    record(prop, live["properties"].get(prop, {"present": False}))
    for source in ("/proc/cmdline", "/proc/bootconfig"):
        document = live["boot_arguments"].get(source, {"unavailable": "absent"})
        need(type(document) is dict, "invalid boot argument source")
        if "unavailable" in document:
            need(set(document) == {"unavailable"}, "unavailable source also contains observations")
            collected.append({"source": source, "state": "unavailable"})
            continue
        observed = document.get("observations")
        need(type(observed) is dict, "boot argument observations missing")
        values = observed.get(arg, [])
        need(type(values) is list and len(values) <= 1024, "invalid reported observation list")
        if not values:
            collected.append({"source": source, "state": "missing"})
        if len(values) > 1:
            issues.append("duplicate-reported-key:" + source)
        for index, raw in enumerate(values):
            record(source + "[" + str(index) + "]", raw)
    values = [item["value"] for item in collected if item["state"] == "valid"]
    if not values:
        issues.append("no-valid-reported-value")
    elif any(value != values[0] for value in values[1:]):
        issues.append("conflicting-reported-values")
    # The first value is used only after every observation was inspected and
    # absence of invalid, repeated or conflicting reports was established.
    return {"state": "consistent" if not issues else "unresolved", "value": values[0] if not issues else None,
            "observations": collected, "issues": issues,
            "scope": "available allowlisted reports only; not loader replay"}


def compare_memory(candidate, live):
    first, second = memory_summary(candidate), memory_summary(live)
    changed = []
    first_nodes, second_nodes = first["reservation_nodes"], second["reservation_nodes"]
    for path in sorted(first_nodes.keys() & second_nodes.keys()):
        if first_nodes[path] != second_nodes[path]:
            changed.append({"path": path, "candidate": first_nodes[path], "live": second_nodes[path]})
    return {"candidate": first, "live": second,
            "live_bank_ranges_not_in_candidate": subtract(second["bank_union"], first["bank_union"]),
            "candidate_bank_ranges_not_in_live": subtract(first["bank_union"], second["bank_union"]),
            "live_static_exclusions_not_in_candidate": subtract(second["static_exclusion_union"], first["static_exclusion_union"]),
            "candidate_static_exclusions_not_in_live": subtract(first["static_exclusion_union"], second["static_exclusion_union"]),
            "reservation_nodes_only_in_candidate": sorted(first_nodes.keys() - second_nodes.keys()),
            "reservation_nodes_only_in_live": sorted(second_nodes.keys() - first_nodes.keys()),
            "changed_reservation_nodes": changed,
            "scope": "set arithmetic on separately recorded declarations; no overlay application, free-memory claim or allocation permission"}


def correlate_entry(entry, running):
    identity, live = public_identity(entry["dt"]), public_identity(running)
    comparisons = {}
    for name in sorted(identity["qcom_ids"].keys() | live["qcom_ids"].keys()):
        candidate_value, live_value = identity["qcom_ids"].get(name), live["qcom_ids"].get(name)
        state = "absent_in_candidate" if candidate_value is None else "absent_in_live" if live_value is None else "equal" if candidate_value == live_value else "different"
        comparisons[name] = {"state": state, "candidate": candidate_value, "live": live_value}
    return {"index": entry["index"], "offset": entry["offset"], "bytes": entry["bytes"],
            "sha256": entry["sha256"], "identity": identity, "root_id_comparison": comparisons,
            "compatible_list_equal": identity["compatible"] == live["compatible"],
            "model_equal": identity["model"] == live["model"],
            "unmodified_blob_sha_equals_live": identity["sha256"] == live["sha256"],
            "memory_comparison": compare_memory(entry["dt"], running),
            "runtime_selection_verified": False}


def correlate(backup_bytes: bytes, live_bytes: bytes) -> dict:
    backup, live = decode(backup_bytes), decode(live_bytes)
    validate_inputs(backup, live)
    reports = {name: resolve_report(live, name) for name in ("slot_suffix", "dtb_idx", "dtbo_idx")}
    running = live["running_fdt"]["inspection"]
    result = {"schema": SCHEMA,
              "inputs": {"backup": {"bytes": len(backup_bytes), "sha256": digest(backup_bytes),
                                     "archive_sha256": backup["archive_sha256"], "source_sha256": backup["source_sha256"]},
                         "live": {"bytes": len(live_bytes), "sha256": digest(live_bytes),
                                  "fdt_sha256": live["running_fdt"]["sha256"], "source_sha256": live["source_sha256"]}},
              "parser_sha256": live["parser_sha256"], "reported_selection": reports,
              "live_identity": public_identity(running), "live_memory": memory_summary(running),
              "live_format": {key: running[key] for key in ("format_compliant", "diagnostic_nonzero_padding_allowed", "format_issues", "format_compliance_scope")},
              "base_dt_by_reported_index": None, "overlays_by_reported_indices": None,
              "issues": [], "runtime_abl_replayed": False, "overlay_application_performed": False,
              "per_byte_runtime_selection_verified": False, "native_load_layout_verified": False,
              "physical_mainline_linux_tested": False, "owner_native_linux_passes_added": 0,
              "source_sha256": digest(Path(__file__).read_bytes())}
    for name, report in reports.items():
        result["issues"].extend(name + ":" + reason for reason in report["issues"])
    slot = reports["slot_suffix"]["value"]
    if slot is not None:
        base_name, overlay_name = "boot" + slot, "dtbo" + slot
        base = backup["images"][base_name]["components"]["dtb"]["inspection"]
        overlay = backup["dtbo_partitions"][overlay_name]["inspection"]
        dtb_indices, dtbo_indices = reports["dtb_idx"]["value"], reports["dtbo_idx"]["value"]
        if dtb_indices is not None:
            index = dtb_indices[0]
            if index >= len(base["entries"]):
                result["issues"].append("reported-dtb-index-out-of-range")
            else:
                result["base_dt_by_reported_index"] = {"partition": base_name,
                    "partition_sha256": backup["images"][base_name]["partition_sha256"],
                    "bundle_sha256": base["sha256"], **correlate_entry(base["entries"][index], running)}
        if dtbo_indices is not None:
            if any(index >= len(overlay["entries"]) for index in dtbo_indices):
                result["issues"].append("reported-dtbo-index-out-of-range")
            else:
                result["overlays_by_reported_indices"] = {"partition": overlay_name,
                    "partition_sha256": backup["dtbo_partitions"][overlay_name]["partition_sha256"],
                    "table_sha256": overlay["table_sha256"],
                    "entries": [correlate_entry(overlay["entries"][index], running) for index in dtbo_indices]}
    result["correlation_status"] = "reported_indices_consistent" if not result["issues"] else "unresolved"
    result["interpretation"] = "reported indices locate backup entries; root IDs and memory differences are metadata comparisons, not proof of ABL's byte-for-byte selection or final native layout"
    return result


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        before = os.fstat(source.fileno())
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= MAX_JSON, "require a bounded regular JSON file")
        data = source.read(MAX_JSON + 1)
        after = os.fstat(source.fileno())
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
         == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
         and len(data) == before.st_size, "input changed during read")
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backup", type=Path, required=True)
    ap.add_argument("--live", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        result = correlate(read_regular(args.backup), read_regular(args.live))
        raw = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            with args.output.open("x", encoding="utf-8") as target:
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
        else:
            print(raw, end="")
        return 0 if result["correlation_status"] == "reported_indices_consistent" else 2
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("DT metadata correlation failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
