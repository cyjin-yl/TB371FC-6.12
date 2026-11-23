#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bounded offline readers for this project's raw Image / v17 DTB profile.

These functions inspect bytes and a proposed memory map only. They do not
establish loader execution, AVB acceptance, CPU state, DMA quiescence, recovery,
module loading or physical boot success. No files or devices are accessed.

The Image rules follow Linux 6.12 Documentation/arch/arm64/booting.rst. The DTB
reader deliberately supports format version 17 / last-compatible version 16;
it is not a compatibility promise for every flattened-devicetree version.
"""
from __future__ import annotations

import re
import struct


U64_LIMIT = 1 << 64
MIB = 1 << 20
GIB = 1 << 30
MAX_DTB_BYTES = 2 * MIB
MAX_DEPTH = 256
MAX_NAME_BYTES = 255
MAX_TOTAL_PATH_BYTES = 8 * MIB


class FormatError(ValueError):
    """Input falls outside the documented, bounded offline profile."""


def _require(condition, message):
    if not condition:
        raise FormatError(message)


def _integer(value, name, *, positive=False):
    _require(type(value) is int and (0 < value if positive else 0 <= value)
             and value < U64_LIMIT, name + " must be a bounded unsigned integer")
    return value


def parse_arm64_image(data: bytes) -> dict:
    """Read a non-legacy, uncompressed ARM64 Image header without executing it.

    Stored length and effective memory size remain separate. A zero image_size
    belongs to an older, unbounded-size protocol and is unsupported here. The
    optional PE offset is reported but EFI/PE validity is not established.
    """
    _require(isinstance(data, bytes), "Image input must be bytes")
    _require(len(data) >= 64, "truncated ARM64 Image header")
    _require(data[56:60] == b"ARM\x64", "not an uncompressed ARM64 Image")
    text_offset, image_size, flags, res2, res3, res4 = struct.unpack_from("<6Q", data, 8)
    _require(image_size != 0, "legacy zero-size Image is outside this profile")
    _require(image_size >= len(data), "effective Image size is smaller than stored bytes")
    _require(flags & ~0xF == 0, "unsupported reserved ARM64 Image flags")
    _require(res2 == res3 == res4 == 0, "nonzero reserved ARM64 Image fields")
    page_encoding = (flags >> 1) & 3
    return {
        "stored_bytes": len(data),
        "text_offset": text_offset,
        "image_size": image_size,
        "flags": flags,
        "endianness": "big" if flags & 1 else "little",
        "page_size": (None, 4096, 16384, 65536)[page_encoding],
        "placement_anywhere_in_48bit_range": bool(flags & 8),
        "pe_header_offset": struct.unpack_from("<I", data, 60)[0],
        "efi_entry_verified": False,
    }


def _cstring(data, start, limit, label):
    _require(0 <= start < limit <= len(data), label + " offset outside its block")
    end = data.find(b"\0", start, limit)
    _require(end != -1, label + " has no NUL terminator in its block")
    try:
        value = data[start:end].decode("ascii")
    except UnicodeDecodeError as error:
        raise FormatError(label + " is not ASCII") from error
    return value, end + 1


def _stringlist(raw, label):
    _require(raw and raw[-1:] == b"\0", label + " must be a terminated stringlist")
    pieces = raw[:-1].split(b"\0")
    _require(all(pieces), label + " has an empty string")
    try:
        result = [part.decode("ascii") for part in pieces]
    except UnicodeDecodeError as error:
        raise FormatError(label + " is not ASCII") from error
    _require(all(all(32 <= ord(char) < 127 for char in part) for part in result),
             label + " has control characters")
    return result


def _disjoint(spans, label):
    ordered = sorted(spans, key=lambda item: (item[0], item[1]))
    for before, after in zip(ordered, ordered[1:]):
        _require(before[1] <= after[0], label + " overlap: " + before[2] + " / " + after[2])


def parse_fdt(data: bytes) -> dict:
    """Parse a single v17 DTB and return properties from its actual root node.

    This validates structure, not board correctness. Callers must compare the
    returned root compatible list with their independently selected board.
    `reservations` refers to the DTB memory-reservation block; it does not
    silently stand for the board's complete /reserved-memory or firmware map.
    """
    _require(isinstance(data, bytes), "DTB input must be bytes")
    _require(40 <= len(data) <= MAX_DTB_BYTES, "DTB length outside the ARM64 profile")
    (magic, total, off_struct, off_strings, off_reserve, version,
     last_version, boot_cpu, size_strings, size_struct) = struct.unpack_from(">10I", data)
    _require(magic == 0xD00DFEED, "invalid DTB magic")
    _require(total == len(data), "DTB totalsize differs from its file length")
    _require(version == 17 and last_version == 16,
             "unsupported DTB version pair; this profile requires 17 / 16")
    _require(off_struct >= 40 and off_struct % 4 == 0 and size_struct >= 16
             and size_struct % 4 == 0 and off_struct + size_struct <= total,
             "invalid DTB structure-block bounds or alignment")
    _require(off_strings >= 40 and off_strings + size_strings <= total,
             "invalid DTB strings-block bounds")
    _require(off_reserve >= 40 and off_reserve % 8 == 0 and off_reserve + 16 <= total,
             "invalid DTB reservation-block bounds or alignment")
    _require(size_strings == 0 or data[off_strings + size_strings - 1] == 0,
             "DTB strings block is not NUL terminated")

    # The reservation extent is determined by its required all-zero terminator.
    reservations, reservation_spans = [], []
    pos = off_reserve
    while True:
        _require(pos + 16 <= total, "unterminated DTB memory-reservation block")
        start, size = struct.unpack_from(">QQ", data, pos)
        pos += 16
        if start == size == 0:
            break
        _require(size > 0 and start + size <= U64_LIMIT,
                 "empty or overflowing DTB memory reservation")
        reservations.append({"start": start, "size": size})
        reservation_spans.append((start, start + size, "reservation " + str(len(reservations))))
    _disjoint(reservation_spans, "DTB physical reservations")
    block_spans = [(0, 40, "header"), (off_reserve, pos, "reservations"),
                   (off_struct, off_struct + size_struct, "structure")]
    if size_strings:
        block_spans.append((off_strings, off_strings + size_strings, "strings"))
    _disjoint(block_spans, "DTB blocks")

    structure_end = off_struct + size_struct
    strings_end = off_strings + size_strings
    pos, stack, paths = off_struct, [], set()
    root_properties = None
    root_seen, root_closed, finished = False, False, False
    maximum_depth, total_path_bytes = 0, 0
    while pos < structure_end:
        _require(pos + 4 <= structure_end, "truncated DTB structure token")
        tag, = struct.unpack_from(">I", data, pos)
        pos += 4
        if tag == 1:  # FDT_BEGIN_NODE
            name, name_end = _cstring(data, pos, structure_end, "DTB node name")
            aligned_end = (name_end + 3) & ~3
            _require(aligned_end <= structure_end and not any(data[name_end:aligned_end]),
                     "invalid DTB node-name alignment padding")
            pos = aligned_end
            if not stack:
                _require(not root_seen and not root_closed and name == "",
                         "DTB must have one unnamed root")
                root_seen = True
                path = "/"
            else:
                _require(name not in ("", ".", "..") and len(name) <= MAX_NAME_BYTES
                         and re.fullmatch(r"[A-Za-z0-9,._+@-]+", name) is not None,
                         "invalid DTB child node name")
                stack[-1]["children_started"] = True
                path = stack[-1]["path"].rstrip("/") + "/" + name
            _require(path not in paths, "duplicate DTB node path")
            total_path_bytes += len(path)
            _require(total_path_bytes <= MAX_TOTAL_PATH_BYTES,
                     "DTB paths exceed this bounded profile")
            paths.add(path)
            stack.append({"path": path, "properties": {}, "children_started": False})
            maximum_depth = max(maximum_depth, len(stack))
            _require(maximum_depth <= MAX_DEPTH, "DTB nesting exceeds this profile")
        elif tag == 2:  # FDT_END_NODE
            _require(stack, "unbalanced DTB END_NODE")
            frame = stack.pop()
            if not stack:
                root_properties = frame["properties"]
                root_closed = True
        elif tag == 3:  # FDT_PROP
            _require(stack and not stack[-1]["children_started"],
                     "DTB property outside a node or after a child")
            _require(pos + 8 <= structure_end, "truncated DTB property header")
            length, name_offset = struct.unpack_from(">II", data, pos)
            pos += 8
            _require(name_offset < size_strings, "DTB property-name offset outside strings")
            name, unused = _cstring(data, off_strings + name_offset, strings_end,
                                    "DTB property name")
            _require(len(name) <= MAX_NAME_BYTES
                     and re.fullmatch(r"[A-Za-z0-9,._+?#-]+", name) is not None,
                     "invalid DTB property name")
            frame = stack[-1]
            _require(name not in frame["properties"], "duplicate DTB property")
            aligned_end = (pos + length + 3) & ~3
            _require(aligned_end <= structure_end and not any(data[pos + length:aligned_end]),
                     "DTB property payload or padding outside structure")
            raw = data[pos:pos + length]
            frame["properties"][name] = raw
            if name == "compatible":
                _stringlist(raw, frame["path"] + " compatible")
            pos = aligned_end
        elif tag == 4:  # FDT_NOP
            continue
        elif tag == 9:  # FDT_END
            _require(root_seen and root_closed and not stack,
                     "DTB END before the root closes")
            _require(pos == structure_end, "DTB END is not the final structure token")
            finished = True
            break
        else:
            raise FormatError("unknown DTB structure token")
    _require(finished and root_properties is not None, "DTB END token absent")
    _require("compatible" in root_properties, "DTB root compatible is absent")
    compatible = _stringlist(root_properties["compatible"], "root compatible")
    model = None
    if "model" in root_properties:
        model_parts = _stringlist(root_properties["model"], "root model")
        _require(len(model_parts) == 1, "DTB root model is not one string")
        model = model_parts[0]
    return {
        "totalsize": total,
        "version": version,
        "last_compatible_version": last_version,
        "boot_cpuid_phys": boot_cpu,
        "compatible": compatible,
        "model": model,
        "reservations": reservations,
        "reservation_scope": "DTB memory-reservation block only",
        "node_count": len(paths),
        "maximum_depth": maximum_depth,
        "root_property_names": sorted(root_properties),
    }


def require_root_compatible(tree: dict, expected: str) -> None:
    """Reject a well-formed tree for a different selected board."""
    _require(isinstance(expected, str) and expected and "\0" not in expected,
             "expected compatible must be one nonempty string")
    _require(isinstance(tree, dict) and isinstance(tree.get("compatible"), list)
             and expected in tree["compatible"], "selected board root compatible is absent")


def _ranges(value, name, *, nonempty=False):
    _require(isinstance(value, list) and (value or not nonempty),
             name + " must be an explicit range list")
    spans = []
    for index, entry in enumerate(value):
        _require(isinstance(entry, dict) and "start" in entry and "size" in entry,
                 name + " range must contain start and size")
        start = _integer(entry["start"], name + " start")
        size = _integer(entry["size"], name + " size", positive=True)
        _require(start + size <= U64_LIMIT, name + " range overflows 64 bits")
        spans.append((start, start + size, name + " " + str(index)))
    _disjoint(spans, name)
    return sorted(spans)


def _covered(start, end, ram):
    # Adjacent banks jointly cover an interval; a one-byte hole does not.
    cursor = start
    for low, high, unused in ram:
        if high <= cursor:
            continue
        if low > cursor:
            return False
        cursor = high
        if cursor >= end:
            return True
    return False


def validate_memory_layout(header: dict, dtb_size: int, initramfs_size: int,
                           layout: dict) -> dict:
    """Validate explicit planned addresses against the supplied memory map.

    `layout` must supply integer kernel_address/dtb_address/initramfs_address,
    plus ram and reserved lists of {start, size}. The caller must obtain the
    complete map from the selected board/loader, including DTB reservations,
    /reserved-memory and firmware exclusions; an empty list is a declaration,
    not evidence that the board has no reservations.

    A successful result proves only arithmetic against that supplied map.
    Mapping attributes, CPU/cache state and actual loader placement remain
    unverified. In particular this routine never reports physical boot-ready.
    """
    _require(isinstance(header, dict) and isinstance(layout, dict),
             "header and layout must be objects")
    for field in ("text_offset", "image_size", "flags", "stored_bytes"):
        _require(field in header, "missing Image header field: " + field)
    image_size = _integer(header["image_size"], "image_size", positive=True)
    stored = _integer(header["stored_bytes"], "stored_bytes", positive=True)
    offset = _integer(header["text_offset"], "text_offset")
    flags = _integer(header["flags"], "flags")
    _require(image_size >= stored >= 64 and flags & ~0xF == 0,
             "invalid effective Image extent or flags")
    dtb_size = _integer(dtb_size, "dtb_size", positive=True)
    initramfs_size = _integer(initramfs_size, "initramfs_size", positive=True)
    _require(dtb_size <= MAX_DTB_BYTES, "DTB exceeds ARM64 boot size limit")
    addresses = {}
    for field in ("kernel_address", "dtb_address", "initramfs_address"):
        _require(field in layout, "missing planned address: " + field)
        addresses[field] = _integer(layout[field], field)
    _require("ram" in layout and "reserved" in layout, "RAM and reserved maps must be explicit")
    ram = _ranges(layout["ram"], "RAM", nonempty=True)
    reserved = _ranges(layout["reserved"], "reserved")
    kernel = addresses["kernel_address"]
    dtb = addresses["dtb_address"]
    initramfs = addresses["initramfs_address"]
    _require(kernel >= offset and (kernel - offset) % (2 * MIB) == 0,
             "Image address minus text_offset is not a 2 MiB aligned base")
    _require(dtb % 8 == 0, "DTB address is not 8-byte aligned")
    payloads = [(kernel, kernel + image_size, "kernel-effective"),
                (dtb, dtb + dtb_size, "dtb"),
                (initramfs, initramfs + initramfs_size, "initramfs")]
    for start, end, label in payloads:
        _require(end <= U64_LIMIT, label + " physical range overflows 64 bits")
        _require(_covered(start, end, ram), label + " is not fully covered by supplied RAM")
        for low, high, unused in reserved:
            _require(end <= low or high <= start, label + " overlaps supplied reserved memory")
    _disjoint(payloads, "planned payloads")
    _require(not (flags & 8) or kernel + image_size <= 1 << 48,
             "Image exceeds the header's 48-bit placement range")
    window_base = min(kernel, initramfs) // GIB * GIB
    window_end = max(kernel + image_size, initramfs + initramfs_size)
    window_size = (window_end - window_base + GIB - 1) // GIB * GIB
    _require(window_size <= 32 * GIB,
             "Image and initramfs exceed a common 1 GiB aligned 32 GiB window")
    unverified = ["supplied_ram_and_reservation_map_matches_board",
                  "dtb_2m_mapping_attributes", "actual_loader_placement",
                  "cpu_cache_and_mmu_entry_state", "dma_quiescence"]
    if not flags & 8:
        unverified.append("base_as_close_as_possible_to_dram_start")
    return {
        "status": "planned_layout_valid",
        "scope": "offline arithmetic against the supplied memory map",
        "kernel_stored_bytes": stored,
        "kernel_effective_bytes": image_size,
        "image_base": kernel - offset,
        "payloads": [{"name": label, "start": start, "size": end - start}
                     for start, end, label in payloads],
        "kernel_initramfs_window": {"start": window_base, "size": window_size},
        "unverified": unverified,
        "physical_boot_verified": False,
    }
