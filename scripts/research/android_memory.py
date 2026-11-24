#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded parsers and interval accounting for passive Android RAM evidence.

Resource-tree geometry is not a free-memory map or a loading-address approval.
Unknown /proc/iomem labels are never emitted.
"""
from __future__ import annotations

import hashlib
import re

MAX_IOMEM = 256 * 1024
MAX_MEMINFO = 16 * 1024
MAX_RESOURCES = 4096
MAX_CPUS = 32
U64_END = 1 << 64
MEMINFO_KEYS = frozenset(("MemTotal", "MemAvailable", "MemFree", "CmaTotal",
                          "CmaFree", "SwapTotal", "SwapFree"))
RESOURCE_LABELS = frozenset(("System RAM", "reserved", "Kernel code",
                             "Kernel data", "Kernel bss", "Crash kernel"))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def parse_cpu_list(data):
    text = data.decode("ascii", "strict").strip()
    if not text:
        return []
    if len(data) > 256:
        raise ValueError("CPU list exceeds bound")
    cpus = set()
    for item in text.split(","):
        match = re.fullmatch(r"([0-9]{1,2})(?:-([0-9]{1,2}))?", item)
        if not match:
            raise ValueError("invalid CPU list")
        first = int(match[1])
        last = int(match[2] or match[1])
        if not 0 <= first <= last < MAX_CPUS:
            raise ValueError("CPU number exceeds capture bound")
        chunk = set(range(first, last + 1))
        if chunk & cpus:
            raise ValueError("duplicate CPU number")
        cpus |= chunk
    return sorted(cpus)


def parse_meminfo(data):
    if len(data) > MAX_MEMINFO:
        raise ValueError("meminfo exceeds bound")
    result = {}
    for line in data.decode("ascii", "strict").splitlines():
        key = line.partition(":")[0]
        if key not in MEMINFO_KEYS:
            continue
        match = re.fullmatch(r"([A-Za-z]+):\s+([0-9]{1,16}) kB\s*", line)
        if not match or key in result:
            raise ValueError("invalid or duplicate allowlisted meminfo field")
        value = int(match[2]) * 1024
        if value >= U64_END:
            raise ValueError("meminfo byte count out of range")
        result[key] = value
    if "MemTotal" not in result:
        raise ValueError("missing MemTotal")
    return result


def parse_iomem(data):
    if len(data) > MAX_IOMEM:
        raise ValueError("iomem exceeds bound")
    records, stack = [], []
    for line in data.decode("ascii", "strict").splitlines():
        match = re.fullmatch(r"( *)([0-9a-fA-F]{1,16})-([0-9a-fA-F]{1,16}) : ([^\x00-\x1f]{1,512})", line)
        if not match or len(records) >= MAX_RESOURCES:
            raise ValueError("invalid or excessive iomem resource entries")
        indent = len(match[1])
        start, last = int(match[2], 16), int(match[3], 16)
        if start > last or indent > 128:
            raise ValueError("reversed range or excessive resource depth")
        while stack and records[stack[-1]]["indent"] >= indent:
            stack.pop()
        if indent and not stack:
            raise ValueError("orphan indented resource")
        parent = stack[-1] if stack else None
        label = match[4]
        records.append({"start": start, "end": last + 1, "indent": indent,
                        "parent": parent, "kind": label if label in RESOURCE_LABELS else "other",
                        "zero_zero": start == last == 0})
        stack.append(len(records) - 1)
    if not records:
        raise ValueError("empty iomem resource tree")
    # Linux may redact every address to 0-0. Do not turn such output into
    # one-byte ranges or fabricate a memory map from repeated zero addresses.
    if any(row["zero_zero"] for row in records):
        return {"address_visibility": "redacted_or_ambiguous_zero_resource",
                "resource_count": len(records), "system_ram": [],
                "ram_children": [], "geometry_qualified": False}
    siblings = {}
    for index, row in enumerate(records):
        parent = row["parent"]
        if parent is not None:
            owner = records[parent]
            if not owner["start"] <= row["start"] < row["end"] <= owner["end"]:
                raise ValueError("resource outside its parent")
        group = siblings.setdefault(parent, [])
        if group and records[group[-1]]["end"] > row["start"]:
            raise ValueError("overlapping or unsorted sibling resources")
        group.append(index)
    ram = [index for index, row in enumerate(records) if row["kind"] == "System RAM"]
    if not ram:
        raise ValueError("no System RAM resources")
    ram_set = set(ram)
    descendants = []
    for index, row in enumerate(records):
        ancestor = row["parent"]
        while ancestor is not None and ancestor not in ram_set:
            ancestor = records[ancestor]["parent"]
        if ancestor is not None:
            descendants.append({"start": row["start"], "end": row["end"],
                                "kind": row["kind"], "resource_index": index,
                                "ram_resource_index": ancestor})
    return {"address_visibility": "nonzero_resource_addresses",
            "resource_count": len(records), "geometry_qualified": True,
            "system_ram": [{"start": records[i]["start"], "end": records[i]["end"],
                            "resource_index": i} for i in ram],
            "ram_children": descendants}


def interval(start, end):
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= U64_END:
        raise ValueError("invalid half-open physical interval")
    return start, end


def union(ranges):
    merged = []
    for start, end in sorted(interval(*pair) for pair in ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract(left, right):
    pending = union(left)
    for cut_start, cut_end in union(right):
        next_pending = []
        for start, end in pending:
            if end <= cut_start or start >= cut_end:
                next_pending.append((start, end))
            else:
                if start < cut_start:
                    next_pending.append((start, cut_start))
                if end > cut_end:
                    next_pending.append((cut_end, end))
        pending = next_pending
    return pending


def public_ranges(ranges):
    return [{"start": start, "end": end, "size": end - start} for start, end in union(ranges)]


def byte_total(ranges):
    return sum(end - start for start, end in union(ranges))


def compare(live, observation):
    if live.get("schema") != "tb371fc-android-native-dt-observation-v1":
        raise ValueError("unsupported live DT evidence schema")
    if observation.get("schema") != "tb371fc-android-memory-observation-v1":
        raise ValueError("unsupported memory evidence schema")
    fdt = observation["fdt"]
    original = live["running_fdt"]
    if fdt.get("stable_across_two_reads") is not True or original.get("stable_across_two_reads") is not True:
        raise ValueError("FDT was not stable")
    if fdt["sha256"] != original["sha256"] or fdt["bytes"] != original["bytes"]:
        raise ValueError("memory observation is not bound to this exact FDT")
    if observation["kernel_release"] != live["kernel_release"]:
        raise ValueError("kernel release mismatch")
    capture = observation["iomem"]
    if capture.get("stable_across_two_reads") is not True:
        raise ValueError("resource tree changed during observation")
    resources = capture["parsed"]
    if resources.get("geometry_qualified") is not True:
        raise ValueError("resource address visibility is not qualified")
    dt = original["inspection"]
    reservation = dt["reserved_memory"]
    if reservation.get("physical_address_interpretation_qualified") is not True:
        raise ValueError("DT reserved memory translation is not qualified")
    declared = []
    for memory in dt["memory"]:
        if memory["enabled"]:
            declared += [(row["start"], row["start"] + row["size"]) for row in memory["reg"]]
    actual = [(row["start"], row["end"]) for row in resources["system_ram"]]
    nodes = [node for node in reservation["nodes"] if node["enabled"]]
    static_no_map = [(r["start"], r["start"] + r["size"])
                     for node in nodes if node["allocation"] == "static" and node["no_map"]
                     for r in node["reg"]]
    unexplained = subtract(subtract(declared, static_no_map), actual)
    reusable = [node for node in nodes if node["allocation"] == "dynamic" and node["reusable"]]
    dynamic_no_map = [node for node in nodes if node["allocation"] == "dynamic" and node["no_map"]]
    for node in reusable + dynamic_no_map:
        if type(node["size"]) is not int or not 0 < node["size"] < U64_END:
            raise ValueError("invalid dynamic reservation size")
    reusable_bytes = sum(node["size"] for node in reusable)
    meminfo = observation["meminfo"]["values_bytes"]
    reserved = [(row["start"], row["end"]) for row in resources["ram_children"] if row["kind"] == "reserved"]
    candidate_matches = []
    for node in dynamic_no_map:
        alignment = node.get("alignment")
        if alignment is not None and (type(alignment) is not int or alignment <= 0):
            raise ValueError("invalid dynamic alignment")
        allocations = [(r["start"], r["start"] + r["size"]) for r in node["alloc_ranges"]]
        matches = [(a, b) for a, b in unexplained
                   if b - a == node["size"] and (alignment is None or a % alignment == 0)
                   and (not allocations or not subtract([(a, b)], allocations))]
        candidate_matches.append({"path": node["path"], "matching_gap_geometry": public_ranges(matches),
                                  "runtime_ownership_verified": False})
    return {
        "schema": "tb371fc-android-memory-correlation-v1",
        "evidence_class": "owner_android_read_only",
        "capture_utc": observation["capture_utc"],
        "kernel_release": observation["kernel_release"],
        "fdt_sha256": fdt["sha256"],
        "dt_declared_ram": public_ranges(declared),
        "dt_declared_ram_bytes": byte_total(declared),
        "iomem_system_ram": public_ranges(actual),
        "iomem_system_ram_bytes": byte_total(actual),
        "static_no_map_union": public_ranges(static_no_map),
        "static_no_map_union_bytes": byte_total(static_no_map),
        "system_ram_outside_dt": public_ranges(subtract(actual, declared)),
        "static_no_map_intersection_with_system_ram": public_ranges(subtract(static_no_map, subtract(static_no_map, actual))),
        "ram_gaps_after_static_no_map": public_ranges(unexplained),
        "dynamic_reusable_request_count": len(reusable),
        "dynamic_reusable_requested_bytes": reusable_bytes,
        "meminfo_cma_total_bytes": meminfo.get("CmaTotal"),
        "cma_total_equals_dynamic_reusable_request_sum": meminfo.get("CmaTotal") == reusable_bytes,
        "reserved_children_equal_to_cma_request_sum": public_ranges([(a, b) for a, b in reserved if b - a == reusable_bytes]),
        "dynamic_no_map_gap_candidates": candidate_matches,
        "meminfo_total_bytes": meminfo["MemTotal"],
        "system_ram_minus_memtotal_bytes": byte_total(actual) - meminfo["MemTotal"],
        "individual_dynamic_allocations_resolved": 0,
        "complete_memory_ownership_verified": False,
        "safe_load_addresses_selected": False,
        "dma_quiescence_tested": False,
        "physical_mainline_linux_tested": False,
        "owner_native_linux_passes_added": 0,
        "limitations": [
            "Equal aggregate sizes and matching gaps do not identify individual allocations or owners.",
            "CMA pages remain managed System RAM; reserved labels are resource-tree observations, not live allocation states.",
            "MemTotal differs from physical resource geometry; the difference has not been assigned to individual kernel overheads.",
            "No unoccupied or safely reusable physical range is inferred from this Android snapshot.",
        ],
    }
