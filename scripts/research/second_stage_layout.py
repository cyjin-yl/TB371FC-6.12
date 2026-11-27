#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check one paused TB371FC model handoff, without granting native readiness.

Inputs are exact bytes read by the launcher, actual ROM addresses, and the
RAM map independently calculated from its selected machine size.  This module
does not start QEMU, read files, or continue a CPU.  The launcher must verify
the complete loaded Image/initrd bytes before using a successful result.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import re
import struct

from boot_formats import parse_arm64_image, validate_memory_layout
from native_dt import _parse_tree, inspect_fdt

U64_LIMIT = 1 << 64
RAM_BASE = 0x80000000
RAM_HOLE_BASE = 0xBBB00000
RAM_HOLE_END = 0xC0000000
BOARD_COMPATIBLE = ["lenovo,tb371fc", "qcom,sm8250"]
FIRMWARE_HOLE = "/reserved-memory/firmware-hole@bbb00000"
MEMORY_PATH = "/memory@80000000"
CHOSEN_FIXUPS = {"bootargs", "linux,initrd-start", "linux,initrd-end"}
PSCI_PROPERTIES = {
    "compatible": b"arm,psci-1.0\0arm,psci-0.2\0arm,psci\0",
    "method": b"smc\0",
    "cpu_suspend": struct.pack(">I", 0xC4000001),
    "cpu_off": struct.pack(">I", 0x84000002),
    "cpu_on": struct.pack(">I", 0xC4000003),
    "migrate": struct.pack(">I", 0xC4000005),
}


class LayoutError(ValueError):
    """The observed handoff does not meet this bounded simulation profile."""


def require(condition, message):
    if not condition:
        raise LayoutError(message)


def identity(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def integer(value, label, *, positive=False):
    require(type(value) is int and (0 < value if positive else 0 <= value)
            and value < U64_LIMIT, label + " must be a bounded unsigned integer")
    return value


def ranges(value, label, *, nonempty=False, disjoint=True):
    require(type(value) is list and (value or not nonempty),
            label + " must be an explicit range list")
    require(len(value) <= 4096, label + " exceeds the range budget")
    result = []
    for row in value:
        require(type(row) is dict and set(row) == {"start", "size"},
                label + " entries must contain only start and size")
        start = integer(row["start"], label + " start")
        size = integer(row["size"], label + " size", positive=True)
        require(start + size <= U64_LIMIT, label + " range overflows 64 bits")
        result.append({"start": start, "size": size})
    result.sort(key=lambda row: (row["start"], row["size"]))
    if disjoint:
        for left, right in zip(result, result[1:]):
            require(left["start"] + left["size"] <= right["start"],
                    label + " ranges overlap")
    return result


def union_ranges(rows):
    spans = sorted((row["start"], row["start"] + row["size"]) for row in rows)
    result = []
    for start, end in spans:
        if result and start <= result[-1][1]:
            result[-1][1] = max(end, result[-1][1])
        else:
            result.append([start, end])
    return [{"start": start, "size": end - start} for start, end in result]


def model_ram(ram):
    """Require the board's clipped physical map, rather than arbitrary RAM."""
    require(len(ram) in (1, 2) and ram[0]["start"] == RAM_BASE,
            "model RAM must start at the TB371FC physical base")
    low_end = ram[0]["start"] + ram[0]["size"]
    require(low_end <= RAM_HOLE_BASE, "model RAM includes the firmware hole")
    if len(ram) == 2:
        require(low_end == RAM_HOLE_BASE and ram[1]["start"] == RAM_HOLE_END,
                "model RAM banks must preserve the TB371FC firmware hole")


def parse_config(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 2 * 1024 * 1024,
            "kernel configuration must be bounded bytes")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise LayoutError("kernel configuration is not ASCII") from exc
    values = {}
    for line in lines:
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            key, value = line[2:-len(" is not set")], "n"
        else:
            continue
        # Kconfig symbol names are case-sensitive and may contain lowercase
        # letters: the frozen R5 configuration includes FONT_TER16x32.
        require(re.fullmatch(r"CONFIG_[A-Za-z0-9_]+", key) is not None,
                "invalid kernel configuration key: " + repr(key))
        require(key not in values, "duplicate kernel configuration key: " + key)
        values[key] = value
    return values


def command_line(raw, requested, config_raw):
    require(type(raw) is bytes and raw.endswith(b"\0") and b"\0" not in raw[:-1],
            "final /chosen/bootargs must be one terminated string")
    try:
        actual = raw[:-1].decode("ascii")
    except UnicodeDecodeError as exc:
        raise LayoutError("final bootargs are not ASCII") from exc
    require(type(requested) is str and actual == requested,
            "final bootargs differ from the requested machine command line")
    require(0 < len(actual) <= 4095 and all(32 <= ord(c) <= 126 for c in actual)
            and not any(c in actual for c in "\"'\\"),
            "bootargs fall outside the unquoted printable-ASCII profile")
    tokens = actual.split()
    boundary = tokens.index("--") if "--" in tokens else len(tokens)
    enforcement = [(i, token) for i, token in enumerate(tokens)
                   if token.partition("=")[0].replace("-", "_") == "module.sig_enforce"]
    require(len(enforcement) == 1 and enforcement[0][0] < boundary
            and enforcement[0][1].partition("=")[2] == "1",
            "require exactly one module.sig_enforce=1 before --")
    config = parse_config(config_raw)
    require(config.get("CONFIG_CMDLINE_FROM_BOOTLOADER") == "y"
            and config.get("CONFIG_CMDLINE_FORCE", "n") == "n"
            and config.get("CONFIG_CMDLINE_EXTEND", "n") == "n",
            "unsupported kernel command-line mode; bootloader must take precedence")
    fallback = config.get("CONFIG_CMDLINE")
    require(type(fallback) is str and len(fallback) >= 2
            and fallback.startswith('"') and fallback.endswith('"'),
            "kernel built-in command-line fallback is not explicit")
    require(config.get("CONFIG_MODULES") == "y"
            and config.get("CONFIG_MODULE_SIG") == "y",
            "kernel does not enable signed loadable modules")
    require(config.get("CONFIG_MODULE_SIG_FORCE", "n") in ("y", "n"),
            "invalid module signature force configuration")
    return {"final_bootargs": actual,
            "required_argument": "module.sig_enforce=1",
            "kernel_cmdline_mode": "from_bootloader",
            "built_in_fallback": fallback,
            "fallback_overridden": True,
            "module_signature_force_configured": config.get("CONFIG_MODULE_SIG_FORCE") == "y",
            "module_enforcement_runtime_verified": False}


def memory_paths(nodes):
    return {path for path, props in nodes.items()
            if path.count("/") == 1 and (path == "/memory" or path.startswith("/memory@")
                                         or props.get("device_type") == b"memory\0")}


def property_delta(path, before, after):
    changed = []
    for name in sorted(set(before) | set(after)):
        if before.get(name) != after.get(name) or (name in before) != (name in after):
            changed.append({"path": path, "property": name,
                            "before": identity(before[name]) if name in before else None,
                            "after": identity(after[name]) if name in after else None})
    return changed


def check_dtb_delta(before_nodes, after_nodes, before_meta, after_meta, ram):
    """Permit only the fixups in this board model and ARM boot helper."""
    old_memory, new_memory = memory_paths(before_nodes), memory_paths(after_nodes)
    require(new_memory == {MEMORY_PATH}, "final FDT must expose one canonical memory node")
    for path in old_memory | new_memory:
        for nodes in (before_nodes, after_nodes):
            if path in nodes:
                require(set(nodes[path]) <= {"device_type", "reg"},
                        "memory replacement would discard unsupported properties")
                require(not any(p.startswith(path + "/") for p in nodes),
                        "memory replacement has unsupported child nodes")
    require(after_nodes[MEMORY_PATH].get("device_type") == b"memory\0",
            "final memory node lacks device_type=memory")

    expected_hole = None
    if len(ram) == 2:
        expected_hole = {"reg": struct.pack(">QQ", RAM_HOLE_BASE, RAM_HOLE_END - RAM_HOLE_BASE),
                         "no-map": b""}
    elif FIRMWARE_HOLE in after_nodes:
        # With a partially clipped physical aperture, the usable RAM alone
        # cannot establish how much of the hole was backed. Do not guess it.
        raise LayoutError("partially clipped firmware hole requires a fuller model contract")
    if expected_hole is not None:
        require(after_nodes.get(FIRMWARE_HOLE) == expected_hole,
                "final firmware-hole reservation differs from the board geometry")
    if FIRMWARE_HOLE in before_nodes:
        require(before_nodes[FIRMWARE_HOLE] == after_nodes.get(FIRMWARE_HOLE),
                "pre-existing firmware-hole properties changed")

    final_psci = after_nodes.get("/psci", {})
    require(all(final_psci.get(name) == raw for name, raw in PSCI_PROPERTIES.items()),
            "final PSCI node differs from the explicit AArch64 SMC model")
    original_psci = before_nodes.get("/psci", {})
    original_extra = {name: raw for name, raw in original_psci.items()
                      if name not in PSCI_PROPERTIES}
    final_extra = {name: raw for name, raw in final_psci.items()
                   if name not in PSCI_PROPERTIES}
    require(original_extra == final_extra,
            "PSCI fixup added, removed or changed an unrelated property")
    original_children = {path: props for path, props in before_nodes.items()
                         if path.startswith("/psci/")}
    final_children = {path: props for path, props in after_nodes.items()
                      if path.startswith("/psci/")}
    require(original_children == final_children,
            "PSCI fixup added, removed or changed a descendant")

    allowed_paths = old_memory | new_memory | {"/chosen", "/psci", FIRMWARE_HOLE}
    if "/reserved-memory" not in before_nodes and expected_hole is not None:
        require(after_nodes.get("/reserved-memory") == {
            "#address-cells": struct.pack(">I", 2),
            "#size-cells": struct.pack(">I", 2), "ranges": b""},
            "new reserved-memory parent differs from the explicit board fixup")
        allowed_paths.add("/reserved-memory")
    require((set(before_nodes) - allowed_paths) == (set(after_nodes) - allowed_paths),
            "unexpected FDT node addition or removal")
    changes = []
    for path in sorted(set(before_nodes) | set(after_nodes)):
        before, after = before_nodes.get(path, {}), after_nodes.get(path, {})
        delta = property_delta(path, before, after)
        if path == "/chosen":
            require(all(row["property"] in CHOSEN_FIXUPS for row in delta),
                    "unexpected /chosen property change")
        elif path not in allowed_paths:
            require(not delta, "unexpected FDT property change at " + path)
        changes.extend(delta)
    for name in ("version", "last_compatible_version", "boot_cpuid_phys"):
        require(before_meta[name] == after_meta[name], "unexpected FDT header change: " + name)
    original = Counter((row["start"], row["size"]) for row in before_meta["memreserve"])
    final = Counter((row["start"], row["size"]) for row in after_meta["memreserve"])
    require(all(final[pair] >= count for pair, count in original.items()),
            "QEMU removed an original FDT memory reservation")
    additions = final - original
    # The SMEM model's fixed range is added by tb371fc_fixup_memory only when
    # reference-empty is selected. Every addition remains in the exclusion map.
    require(all(pair == (0x80900000, 0x200000) and count == 1 and pair not in original
                for pair, count in additions.items()),
            "unexpected FDT memory-reservation addition")
    return {"property_changes": changes,
            "memreserve_additions": [{"start": pair[0], "size": pair[1]}
                                     for pair in sorted(additions)],
            "psci_preservation": {
                "unrelated_properties": sorted(original_extra),
                "descendant_count": len(original_children),
                "descendant_paths": sorted(original_children),
                "descendant_properties_unchanged": True,
            },
            "input_memory_nodes": sorted(old_memory),
            "final_memory_nodes": sorted(new_memory)}


def static_and_unresolved(meta, source):
    record = meta["reserved_memory"]
    if record["present"] and record.get("enabled"):
        require(record.get("physical_address_interpretation_qualified"),
                source + " reserved-memory address translation is unqualified")
    allowed_issues = {"reserved-memory-allocation-unresolved", "overlapping-reservation-declarations"}
    if source == "input":
        allowed_issues |= {"memory-node-type-or-reg-unresolved", "no-positive-enabled-memory-reg"}
    unexpected = set(meta["memory_map_issues"]) - allowed_issues
    require(not unexpected, source + " FDT memory map is invalid: " + ", ".join(sorted(unexpected)))
    unresolved = []
    for row in record["nodes"]:
        if row["enabled"] and (not row["reg"] or row["zero_size_placeholder"]):
            unresolved.append({"source": source, "path": row["path"],
                               "allocation": row["allocation"], "size": row["size"],
                               "alignment": row["alignment"], "alloc_ranges": row["alloc_ranges"]})
    return meta["described_static_exclusion_union"], unresolved


def validate_observed_layout(image: bytes, input_dtb: bytes, final_dtb: bytes,
                             initrd: bytes, kernel_config: bytes, observed: dict) -> dict:
    """Return a simulation-only handoff report, or raise ValueError.

    ``observed`` requires kernel_address, initramfs_address, dtb_address, ram,
    loader_reserved, and bootargs. The launcher obtains actual ROM addresses,
    includes every other resident loader ROM as a reservation, and calculates
    ram independently from -m rather than trusting the FDT being inspected.
    """
    require(type(observed) is dict and set(observed) == {
        "kernel_address", "initramfs_address", "dtb_address", "ram", "loader_reserved", "bootargs"},
        "observed handoff fields differ from this exact profile")
    for name in ("kernel_address", "initramfs_address", "dtb_address"):
        integer(observed[name], name)
    require(type(initrd) is bytes and 0 < len(initrd) <= 512 * 1024 * 1024,
            "initrd must be nonempty bounded bytes")
    header = parse_arm64_image(image)
    require(header["endianness"] == "little", "selected board profile requires a little-endian Image")
    require(header["page_size"] == 4096, "selected board profile requires a 4 KiB Image")
    ram = ranges(observed["ram"], "model RAM", nonempty=True)
    model_ram(ram)
    loader = ranges(observed["loader_reserved"], "loader reservations", disjoint=False)
    before_nodes, before_meta = _parse_tree(input_dtb)
    after_nodes, after_meta = _parse_tree(final_dtb)
    before, after = inspect_fdt(input_dtb), inspect_fdt(final_dtb)
    for name, meta in (("input", before), ("final", after)):
        require(meta["compatible"] == BOARD_COMPATIBLE,
                name + " FDT root compatible is not the exact TB371FC profile")
        require(meta["root_cells"] == {"address": 2, "size": 2,
                                       "address_explicit": True, "size_explicit": True},
                name + " FDT root address/size cells must both be explicitly two")
    before_reserved, before_unresolved = static_and_unresolved(before, "input")
    after_reserved, after_unresolved = static_and_unresolved(after, "final")
    actual_ram = ranges([row for node in after["memory"] if node["enabled"]
                         for row in node["reg"]], "final FDT RAM", nonempty=True)
    require(actual_ram == ram, "final FDT RAM differs from independently selected model RAM")
    chosen = after["chosen_numeric"]
    require(not ({"linux,usable-memory-range", "linux,elfcorehdr"} & set(chosen)),
            "crash-kernel memory restrictions are outside the selected handoff profile")
    require(chosen.get("linux,initrd-start") == observed["initramfs_address"]
            and chosen.get("linux,initrd-end") == observed["initramfs_address"] + len(initrd),
            "final /chosen initrd interval differs from loaded initrd")
    command = command_line(after_nodes.get("/chosen", {}).get("bootargs"),
                           observed["bootargs"], kernel_config)
    delta = check_dtb_delta(before_nodes, after_nodes, before_meta, after_meta, ram)
    exclusions = union_ranges(before_reserved + after_reserved + loader)
    plan = {key: observed[key] for key in ("kernel_address", "initramfs_address", "dtb_address")}
    plan.update(ram=ram, reserved=exclusions)
    arithmetic = validate_memory_layout(header, len(final_dtb), len(initrd), plan)
    unresolved = before_unresolved + after_unresolved
    blockers = ["physical RAM ownership is unverified", "firmware and loader lifetime are unverified",
                "DMA quiescence is unverified", "native entry and recovery are unverified",
                "board-model simulation is not owner-native hardware acceptance"]
    if unresolved:
        blockers.append("individual dynamic or zero-size FDT allocations remain unresolved")
    return {"schema_version": 1, "kind": "tb371fc-paused-second-stage-layout",
            "status": "simulated_layout_valid", "scope": "paused model layout; no guest execution verdict",
            "image": identity(image), "input_dtb": identity(input_dtb), "final_dtb": identity(final_dtb),
            "initrd": identity(initrd), "kernel_config": identity(kernel_config),
            "arm64_header": header, "model_ram": ram, "reserved_union": exclusions,
            "loader_reserved": loader, "layout": arithmetic, "command_line": command,
            "dtb_fixups": delta, "unresolved_reservations": unresolved,
            "actual_payload_bytes_verified_by_this_function": False,
            "physical_boot_verified": False, "native_boot_attempted": False,
            "native_boot_readiness": {"status": "blocked", "requirements": blockers},
            "owner_native_linux_passes_added": 0}
