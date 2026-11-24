#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect bounded DTB bundles and memory metadata without selecting or editing a DT.

This separate reader deliberately leaves the frozen R5/owner-v2 inspectors
unchanged. Inputs are bytes; it never opens a device, applies an overlay, or
executes a loader. Public output omits bootargs, serials, MACs, seeds and arbitrary
property values. Only root compatible/model, allowlisted numeric Qualcomm IDs,
memory/reserved-memory paths and numeric chosen properties are returned.

Profile: FDT v17/last-compatible 16, <=2 MiB per FDT; exact concatenated FDTs;
AOSP DT tables v0/v1 with 32-byte headers/entries, bounded zlib/gzip decoding.
Exact shared payload spans are allowed because AOSP mkdtboimg deduplicates them;
partial overlaps and overlap with metadata are rejected. Physical reservation
overlaps are reported, rather than silently deleted or mistaken for free RAM.

References (read 2026-11-24):
https://source.android.com/docs/core/architecture/bootloader/dtb-images
https://source.android.com/docs/core/architecture/dto/partitions
https://android.googlesource.com/platform/system/libufdt/+/refs/heads/main/utils/src/dt_table.h
https://android.googlesource.com/platform/system/libufdt/+/refs/heads/main/utils/src/mkdtboimg.py
https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html
https://devicetree-specification.readthedocs.io/en/stable/devicetree-basics.html
https://github.com/devicetree-org/devicetree-specification/blob/main/source/chapter3-devicenodes.rst
https://github.com/devicetree-org/dt-schema/blob/main/dtschema/schemas/reserved-memory/reserved-memory.yaml
https://docs.kernel.org/6.12/arch/arm64/booting.html
"""
from __future__ import annotations

import hashlib
import re
import struct
import zlib


SCHEMA = "tb371fc-native-dt-metadata-v1"
FDT_MAGIC = 0xD00DFEED
DT_TABLE_MAGIC = 0xD7B7AB1E
MAX_FDT_BYTES = 2 * 1024 * 1024
MAX_BUNDLE_BYTES = 32 * 1024 * 1024
MAX_DECODED_TABLE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 1024
MAX_NODES = 32768
MAX_DEPTH = 256
MAX_PATH_BYTES = 8 * 1024 * 1024
MAX_REG_TUPLES = 4096
MAX_FORMAT_ISSUES = 4096
U64_LIMIT = 1 << 64
_NODE_NAME = re.compile(r"[A-Za-z0-9,._+@-]{1,255}\Z")
_PROPERTY_NAME = re.compile(r"[A-Za-z0-9,._+?#-]{1,255}\Z")


class DTError(ValueError):
    """Input falls outside the explicitly supported bounded format profile."""


def _need(ok, message):
    if not ok:
        raise DTError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _bytes(data, maximum, minimum, label):
    _need(type(data) is bytes, label + " input must be bytes")
    _need(minimum <= len(data) <= maximum, label + " length outside bounded profile")


def _strings(raw, label):
    _need(raw and raw.endswith(b"\0"), label + " must be a terminated stringlist")
    parts = raw[:-1].split(b"\0")
    _need(all(parts), label + " contains an empty string")
    _need(all(all(32 <= c <= 126 for c in part) for part in parts),
          label + " contains non-printable/non-ASCII bytes")
    return [part.decode("ascii") for part in parts]


def _string(raw, label):
    parts = _strings(raw, label)
    _need(len(parts) == 1, label + " must be a single string")
    return parts[0]


def _cstring(data, offset, end, label):
    _need(0 <= offset < end <= len(data), label + " starts outside its block")
    stop = data.find(b"\0", offset, end)
    _need(stop >= 0, label + " has no terminator in its block")
    try:
        value = data[offset:stop].decode("ascii")
    except UnicodeDecodeError as exc:
        raise DTError(label + " is not ASCII") from exc
    return value, stop + 1


def _disjoint(spans, label):
    ordered = sorted(spans)
    for left, right in zip(ordered, ordered[1:]):
        _need(left[1] <= right[0], label + " ranges overlap")


def _parse_tree(data, *, allow_nonzero_padding=False):
    _bytes(data, MAX_FDT_BYTES, 40, "FDT")
    _need(type(allow_nonzero_padding) is bool, "allow_nonzero_padding must be bool")
    format_issues = []

    def inspect_padding(start, end, label):
        count = sum(c != 0 for c in data[start:end])
        if not count:
            return
        _need(allow_nonzero_padding,
              "nonzero FDT " + label + " padding at offset " + str(start)
              + " length " + str(end - start) + " nonzero_count " + str(count))
        _need(len(format_issues) < MAX_FORMAT_ISSUES, "FDT padding diagnostic budget exceeded")
        format_issues.append({"offset": start, "length": end - start, "nonzero_count": count})

    (magic, total, struct_offset, strings_offset, reserve_offset, version,
     last_version, boot_cpu, strings_size, struct_size) = struct.unpack_from(">10I", data)
    _need(magic == FDT_MAGIC, "invalid FDT magic")
    _need(total == len(data), "FDT totalsize differs from exact supplied extent")
    _need(version == 17 and last_version == 16, "only FDT version pair 17/16 is supported")
    _need(struct_offset >= 40 and struct_offset % 4 == 0 and struct_size >= 16
          and struct_size % 4 == 0 and struct_offset + struct_size <= total,
          "invalid FDT structure bounds/alignment")
    _need(strings_offset >= 40 and strings_offset + strings_size <= total,
          "invalid FDT strings bounds")
    _need(not strings_size or data[strings_offset + strings_size - 1] == 0,
          "FDT strings block lacks final NUL")
    _need(reserve_offset >= 40 and reserve_offset % 8 == 0
          and reserve_offset + 16 <= total, "invalid FDT reservation offset")
    memreserve, pos = [], reserve_offset
    while True:
        _need(pos + 16 <= total, "unterminated FDT reservation block")
        start, size = struct.unpack_from(">QQ", data, pos)
        pos += 16
        if start == size == 0:
            break
        _need(size > 0 and start + size <= U64_LIMIT,
              "zero-size or overflowing FDT reservation")
        _need(len(memreserve) < MAX_REG_TUPLES, "too many FDT reservations")
        memreserve.append({"start": start, "size": size})
    sections = [(0, 40), (reserve_offset, pos),
                (struct_offset, struct_offset + struct_size)]
    if strings_size:
        sections.append((strings_offset, strings_offset + strings_size))
    _disjoint(sections, "FDT file section")

    nodes, stack = {}, []
    pos, end = struct_offset, struct_offset + struct_size
    root_closed = False
    path_bytes, maximum_depth = 0, 0
    finished = False
    while pos < end:
        _need(pos + 4 <= end, "truncated FDT token")
        tag, = struct.unpack_from(">I", data, pos)
        pos += 4
        if tag == 1:
            name, after = _cstring(data, pos, end, "FDT node name")
            aligned = (after + 3) & ~3
            _need(aligned <= end, "FDT node-name alignment exceeds structure")
            inspect_padding(after, aligned, "node-name")
            pos = aligned
            if not stack:
                _need(not nodes and not root_closed and name == "", "invalid or repeated FDT root")
                path = "/"
            else:
                _need(_NODE_NAME.fullmatch(name) is not None and name not in {".", ".."},
                      "invalid FDT node name")
                stack[-1]["children_started"] = True
                path = stack[-1]["path"].rstrip("/") + "/" + name
            _need(path not in nodes, "duplicate FDT node path")
            path_bytes += len(path)
            _need(path_bytes <= MAX_PATH_BYTES and len(nodes) < MAX_NODES,
                  "FDT node/path budget exceeded")
            node = {"path": path, "properties": {}, "children_started": False}
            nodes[path] = node["properties"]
            stack.append(node)
            maximum_depth = max(maximum_depth, len(stack))
            _need(maximum_depth <= MAX_DEPTH, "FDT nesting exceeds bounded profile")
        elif tag == 2:
            _need(bool(stack), "unbalanced FDT END_NODE")
            stack.pop()
            if not stack:
                root_closed = True
        elif tag == 3:
            _need(bool(stack) and not stack[-1]["children_started"],
                  "FDT property outside node or after its children")
            _need(pos + 8 <= end, "truncated FDT property header")
            size, name_offset = struct.unpack_from(">II", data, pos)
            pos += 8
            _need(name_offset < strings_size, "FDT property name outside strings block")
            name, unused = _cstring(data, strings_offset + name_offset,
                                   strings_offset + strings_size, "FDT property name")
            _need(_PROPERTY_NAME.fullmatch(name) is not None, "invalid FDT property name")
            props = stack[-1]["properties"]
            _need(name not in props, "duplicate FDT property")
            aligned = (pos + size + 3) & ~3
            _need(aligned <= end,
                  "FDT property extent exceeds structure: offset " + str(pos)
                  + " size " + str(size) + " structure_end " + str(end))
            inspect_padding(pos + size, aligned, "property")
            props[name] = data[pos:pos + size]
            pos = aligned
        elif tag == 4:
            continue
        elif tag == 9:
            _need(root_closed and not stack and pos == end,
                  "FDT END before root closure or before structure end")
            finished = True
            break
        else:
            raise DTError("unknown FDT structure token")
    _need(finished and "/" in nodes, "FDT END/root missing")
    return nodes, {"totalsize": total, "version": version,
                   "last_compatible_version": last_version,
                   "boot_cpuid_phys": boot_cpu, "node_count": len(nodes),
                   "maximum_depth": maximum_depth, "memreserve": memreserve,
                   "format_compliant": not format_issues,
                   "format_compliance_scope": "bounded binary FDT profile; not complete binding validation",
                   "diagnostic_nonzero_padding_allowed": allow_nonzero_padding,
                   "format_issues": format_issues}


def _u32(raw, label):
    _need(len(raw) == 4, label + " must be one u32")
    return struct.unpack(">I", raw)[0]


def _cells(props, name, default):
    value = _u32(props[name], name) if name in props else default
    _need(value in (1, 2), name + " outside 32/64-bit memory profile")
    return value


def _number(raw, count, label):
    _need(count in (1, 2) and len(raw) == count * 4, label + " has wrong cell width")
    return int.from_bytes(raw, "big")


def _ranges(raw, address_cells, size_cells, label):
    width = 4 * (address_cells + size_cells)
    _need(len(raw) > 0 and len(raw) % width == 0, label + " has incomplete address/size tuples")
    _need(len(raw) // width <= MAX_REG_TUPLES, label + " exceeds tuple budget")
    result = []
    for offset in range(0, len(raw), width):
        start = _number(raw[offset:offset + address_cells * 4], address_cells, label)
        size = _number(raw[offset + address_cells * 4:offset + width], size_cells, label)
        _need(start + size <= U64_LIMIT, label + " address range overflows 64 bits")
        result.append({"start": start, "size": size})
    return result


def _status(props):
    value = _string(props["status"], "memory status") if "status" in props else "okay"
    _need(value in {"okay", "ok", "disabled", "reserved", "fail"}
          or value.startswith("fail-"), "unrecognized memory-node status")
    return value, value in {"okay", "ok"}


def _flag(props, name):
    if name not in props:
        return False
    _need(props[name] == b"", "reserved-memory " + name + " must be an empty boolean")
    return True


def _overlaps(named_ranges):
    spans = sorted((r["start"], r["start"] + r["size"], name)
                   for name, r in named_ranges if r["size"])
    result = []
    for index, (start, end, name) in enumerate(spans):
        for other_start, other_end, other_name in spans[index + 1:]:
            if other_start >= end:
                break
            _need(len(result) < MAX_REG_TUPLES, "physical overlap-report budget exceeded")
            result.append({"left": name, "right": other_name,
                           "start": other_start, "size": min(end, other_end) - other_start})
    return result


def _union(named_ranges):
    spans = sorted((r["start"], r["start"] + r["size"])
                   for unused, r in named_ranges if r["size"])
    result = []
    for start, end in spans:
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return [{"start": start, "size": end - start} for start, end in result]


def inspect_fdt(data: bytes, *, allow_nonzero_padding: bool = False) -> dict:
    """Return allowlisted metadata from one exact DTB, including overlay DTBs.

    A structurally valid pre-overlay DT can contain placeholder zero-sized RAM
    or unresolved dynamic reservations. These are retained explicitly. The
    result does not assert that any supplied tree was selected by ABL, that
    overlays were applied, or that its RAM is safe for a new kernel to use.

    allow_nonzero_padding is an explicit forensic option for the measured live
    Android FDT. Nonzero alignment padding is retained as numeric-only issues
    and sets format_compliant=False. No bytes are changed, no other parser
    condition is relaxed, and bundle/table callers never enable this option.
    """
    nodes, result = _parse_tree(data, allow_nonzero_padding=allow_nonzero_padding)
    root = nodes["/"]
    ac, sc = _cells(root, "#address-cells", 2), _cells(root, "#size-cells", 1)
    result.update(schema=SCHEMA, bytes=len(data), sha256=_sha(data),
                  compatible=_strings(root["compatible"], "root compatible")
                  if "compatible" in root else [],
                  model=_string(root["model"], "root model") if "model" in root else None,
                  root_cells={"address": ac, "size": sc,
                              "address_explicit": "#address-cells" in root,
                              "size_explicit": "#size-cells" in root},
                  qcom_ids={}, memory=[], reserved_memory={"present": False, "nodes": []},
                  chosen_numeric={}, runtime_selection_verified=False,
                  runtime_memory_map_verified=False, physical_boot_tested=False,
                  owner_native_linux_passes_added=0)
    for name in ("qcom,msm-id", "qcom,board-id", "qcom,pmic-id", "qcom,pmic-id-size"):
        if name in root:
            raw = root[name]
            _need(0 < len(raw) <= 4096 and len(raw) % 4 == 0,
                  "root Qualcomm ID has invalid u32-array length")
            result["qcom_ids"][name] = list(struct.unpack(">" + "I" * (len(raw) // 4), raw))
    ram_ranges, reservation_ranges = [], []
    issues = []
    for path, props in nodes.items():
        if path.count("/") != 1 or path == "/":
            continue
        name = path[1:]
        dtype = _string(props["device_type"], "memory device_type") if (
            "device_type" in props and (name == "memory" or name.startswith("memory@")
                                       or props["device_type"] == b"memory\0")) else None
        if dtype != "memory" and name != "memory" and not name.startswith("memory@"):
            continue
        status, enabled = _status(props)
        ranges = _ranges(props["reg"], ac, sc, "memory reg") if "reg" in props else []
        item = {"path": path, "device_type_is_memory": dtype == "memory",
                "status": status, "enabled": enabled, "reg": ranges,
                "reg_present": "reg" in props,
                "zero_size_placeholder": any(r["size"] == 0 for r in ranges),
                "address_cells": ac, "size_cells": sc}
        result["memory"].append(item)
        if enabled:
            if dtype != "memory" or not ranges or item["zero_size_placeholder"]:
                issues.append("memory-node-type-or-reg-unresolved")
            if dtype == "memory":
                ram_ranges.extend((path, r) for r in ranges)

    reserved = nodes.get("/reserved-memory")
    if reserved is not None:
        rac, rsc = _cells(reserved, "#address-cells", 2), _cells(reserved, "#size-cells", 1)
        parent_status, parent_enabled = _status(reserved)
        identity = reserved.get("ranges") == b""
        physical_qualified = (identity and (rac, rsc) == (ac, sc)
                              and "#address-cells" in reserved and "#size-cells" in reserved)
        record = result["reserved_memory"]
        record.update(present=True, address_cells=rac, size_cells=rsc,
                      address_cells_explicit="#address-cells" in reserved,
                      size_cells_explicit="#size-cells" in reserved,
                      cell_counts_match_root=(rac, rsc) == (ac, sc),
                      ranges_present="ranges" in reserved,
                      identity_address_translation=identity,
                      physical_address_interpretation_qualified=physical_qualified,
                      status=parent_status, enabled=parent_enabled)
        if not physical_qualified:
            issues.append("reserved-memory-address-translation-unqualified")
        for path, props in nodes.items():
            if not path.startswith("/reserved-memory/") or path.count("/") != 2:
                continue
            status, enabled = _status(props)
            no_map, reusable = _flag(props, "no-map"), _flag(props, "reusable")
            _need(not (no_map and reusable), "reserved-memory no-map and reusable conflict")
            ranges = _ranges(props["reg"], rac, rsc, "reserved-memory reg") if "reg" in props else []
            requested = _number(props["size"], rsc, "reserved-memory size") if "size" in props else None
            alignment = _number(props["alignment"], rsc, "reserved-memory alignment") if "alignment" in props else None
            alloc_ranges = _ranges(props["alloc-ranges"], rac, rsc, "reserved-memory alloc-ranges") if "alloc-ranges" in props else []
            item = {"path": path, "status": status, "enabled": parent_enabled and enabled,
                    "no_map": no_map, "reusable": reusable, "reg": ranges,
                    "reg_present": "reg" in props, "size": requested, "alignment": alignment,
                    "alloc_ranges": alloc_ranges,
                    "allocation": "static" if "reg" in props else "dynamic" if requested is not None else "unspecified",
                    "reg_takes_precedence_over_size": "reg" in props and "size" in props,
                    "zero_size_placeholder": any(r["size"] == 0 for r in ranges)}
            record["nodes"].append(item)
            if item["enabled"]:
                if not ranges or item["zero_size_placeholder"]:
                    issues.append("reserved-memory-allocation-unresolved")
                if physical_qualified:
                    reservation_ranges.extend((path, r) for r in ranges)

    chosen = nodes.get("/chosen", {})
    result["chosen_present"] = "/chosen" in nodes
    result["chosen_bootargs_omitted"] = "bootargs" in chosen
    for name in ("linux,initrd-start", "linux,initrd-end"):
        if name in chosen:
            raw = chosen[name]
            _need(len(raw) in (4, 8), "chosen initrd address must be u32/u64")
            result["chosen_numeric"][name] = int.from_bytes(raw, "big")
    for name in ("linux,usable-memory-range", "linux,elfcorehdr"):
        if name in chosen:
            result["chosen_numeric"][name] = _ranges(chosen[name], ac, sc, "chosen memory range")
    initrd = result["chosen_numeric"]
    if "linux,initrd-start" in initrd or "linux,initrd-end" in initrd:
        if not ("linux,initrd-start" in initrd and "linux,initrd-end" in initrd
                and initrd["linux,initrd-start"] < initrd["linux,initrd-end"]):
            issues.append("chosen-initrd-pair-invalid-or-incomplete")

    result["overlay_fragments"] = sum(path.count("/") == 1 and path.startswith("/fragment@")
                                      for path in nodes)
    result["external_fixups_present"] = "/__fixups__" in nodes
    result["overlay_application_performed"] = False
    if result["overlay_fragments"]:
        issues.append("overlay-not-applied")
    if not any(r["size"] for unused, r in ram_ranges):
        issues.append("no-positive-enabled-memory-reg")
    memreserve = [("memreserve[" + str(i) + "]", r) for i, r in enumerate(result["memreserve"])]
    result["memory_overlaps"] = _overlaps(ram_ranges)
    result["reservation_overlaps"] = _overlaps(reservation_ranges + memreserve)
    if result["memory_overlaps"]:
        issues.append("overlapping-memory-regions")
    if result["reservation_overlaps"]:
        issues.append("overlapping-reservation-declarations")
    result["described_static_exclusion_union"] = _union(reservation_ranges + memreserve)
    result["memory_map_issues"] = sorted(set(issues))
    result["exclusion_scope"] = "supplied FDT header and enabled identity-mapped /reserved-memory static reg only; not complete firmware/loader exclusions"
    return result


def _entry(data, index, offset, size):
    return {"index": index, "offset": offset, "bytes": size,
            "sha256": _sha(data), "dt": inspect_fdt(data)}


def _decompress(payload, compression):
    if compression == 0:
        _need(len(payload) <= MAX_FDT_BYTES, "uncompressed table entry exceeds FDT budget")
        return payload
    _need(compression in (1, 2), "unknown DT table compression flag")
    decoder = zlib.decompressobj(15 if compression == 1 else 31)
    try:
        decoded = decoder.decompress(payload, MAX_FDT_BYTES + 1)
    except zlib.error as exc:
        raise DTError("invalid compressed DT table entry") from exc
    _need(len(decoded) <= MAX_FDT_BYTES and decoder.eof
          and not decoder.unconsumed_tail and not decoder.unused_data,
          "compressed DT entry exceeds budget, is incomplete, or has trailing data")
    return decoded


def inspect_dt_table(data: bytes, *, allow_partition_tail: bool = False) -> dict:
    """Inspect an exact AOSP table, or explicitly report an opaque partition tail.

    With allow_partition_tail=True, only header.total_size is parsed as the
    table. Remaining bytes are hashed/length-recorded, never interpreted as AVB
    or authenticated padding. Entry id/rev/custom are descriptions, not proof
    that an entry was selected; no choice is performed here.
    """
    _bytes(data, MAX_BUNDLE_BYTES, 32, "DT table")
    _need(type(allow_partition_tail) is bool, "allow_partition_tail must be bool")
    (magic, total, header_size, entry_size, count, entries_offset,
     page_size, version) = struct.unpack_from(">8I", data)
    _need(magic == DT_TABLE_MAGIC, "invalid DT table magic")
    _need(version in (0, 1), "unsupported DT table version")
    _need(header_size == entry_size == 32, "unreviewed DT table header/entry sizes")
    _need(32 <= total <= len(data) and (allow_partition_tail or total == len(data)),
          "DT table total_size differs from supplied extent")
    _need(1 <= count <= MAX_ENTRIES, "DT table entry count outside bounded profile")
    _need(entries_offset >= header_size and entries_offset % 4 == 0
          and entries_offset + count * entry_size <= total, "DT table metadata out of bounds")
    _need(page_size >= 512 and page_size <= 65536 and page_size & (page_size - 1) == 0,
          "unreviewed DT table page size")
    metadata_end = entries_offset + count * entry_size
    descriptors = []
    for index in range(count):
        fields = struct.unpack_from(">8I", data, entries_offset + index * entry_size)
        size, offset, ident, revision = fields[:4]
        _need(size > 0 and offset >= metadata_end and offset + size <= total,
              "DT table entry overlaps metadata or exceeds table")
        flags = fields[4] if version else 0
        _need(flags & ~0xF == 0, "unreviewed DT table reserved flag bits")
        compression = flags & 0xF
        _need(compression in (0, 1, 2), "unknown DT table compression flag")
        descriptors.append({"index": index, "offset": offset, "bytes": size,
                            "id": ident, "rev": revision,
                            "custom": list(fields[5:] if version else fields[4:]),
                            "flags": flags, "compression": compression})
    # Shared complete spans are a documented mkdtboimg optimization. A shared
    # span with different encodings is ambiguous and is rejected independently.
    spans, encodings = set(), {}
    for item in descriptors:
        span = item["offset"], item["offset"] + item["bytes"]
        _need(span not in encodings or encodings[span] == item["compression"],
              "shared DT payload has inconsistent compression flags")
        encodings[span] = item["compression"]
        spans.add(span)
    _disjoint(spans, "DT table payload")
    decoded_cache, decoded_bytes = {}, 0
    entries = []
    for item in descriptors:
        offset, size = item["offset"], item["bytes"]
        key = offset, size, item["compression"]
        if key not in decoded_cache:
            payload = data[offset:offset + size]
            decoded = _decompress(payload, item["compression"])
            decoded_bytes += len(decoded)
            _need(decoded_bytes <= MAX_DECODED_TABLE_BYTES,
                  "decoded DT table aggregate budget exceeded")
            decoded_cache[key] = (_sha(payload), inspect_fdt(decoded))
        payload_sha, dt = decoded_cache[key]
        entries.append(dict(item, sha256=payload_sha, dt=dt))
    tail = data[total:]
    return {"schema": SCHEMA, "kind": "android-dt-table", "bytes": len(data),
            "sha256": _sha(data), "table_bytes": total, "table_sha256": _sha(data[:total]),
            "version": version, "header_size": header_size, "entry_size": entry_size,
            "entries_offset": entries_offset, "page_size": page_size,
            "entry_count": count, "unique_payload_count": len(spans), "entries": entries,
            "partition_tail": {"bytes": len(tail), "sha256": _sha(tail),
                               "interpreted": False, "avb_verified": False},
            "runtime_selection_verified": False, "overlay_application_performed": False,
            "physical_boot_tested": False, "owner_native_linux_passes_added": 0}


def inspect_dt_bundle(data: bytes) -> dict:
    """Inspect an exact concatenation of complete FDTs or an exact AOSP table."""
    _bytes(data, MAX_BUNDLE_BYTES, 8, "DT bundle")
    magic, = struct.unpack_from(">I", data)
    if magic == DT_TABLE_MAGIC:
        return inspect_dt_table(data)
    _need(magic == FDT_MAGIC, "unrecognized DT bundle magic")
    pos, entries = 0, []
    while pos < len(data):
        _need(len(entries) < MAX_ENTRIES and pos + 40 <= len(data),
              "too many DTBs or truncated concatenated FDT header")
        magic, size = struct.unpack_from(">II", data, pos)
        _need(magic == FDT_MAGIC and 40 <= size <= MAX_FDT_BYTES and pos + size <= len(data),
              "invalid concatenated FDT extent/magic")
        entries.append(_entry(data[pos:pos + size], len(entries), pos, size))
        pos += size
    return {"schema": SCHEMA, "kind": "concatenated-fdt", "bytes": len(data),
            "sha256": _sha(data), "entry_count": len(entries), "entries": entries,
            "runtime_selection_verified": False, "overlay_application_performed": False,
            "physical_boot_tested": False, "owner_native_linux_passes_added": 0}
