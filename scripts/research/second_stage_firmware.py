#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""One explicit synthetic firmware handoff for a paused Linux model.

This is an additional gate after second_stage_layout's unchanged DT/PSCI and
payload checks. It neither generates nor writes guest firmware. The launcher
must copy all three complete regions from the paused QEMU address space.
No physical firmware, native boot, or userspace acceptance is inferred.
"""
from __future__ import annotations

from collections import Counter
import hashlib

from native_dt import _parse_tree


REFERENCE_PROFILE = "linux-reference-v1"
PROFILES = ("none", REFERENCE_PROFILE)
QEMU_REFERENCE_SOURCE = "6287cd9a41e5114de6cf3a4ac38b0fd85872ee06"
MACHINE_OPTIONS = (
    "rpmh-profile=reference", "rpmh-boot-configured=on",
    "aop-profile=reference-qdss-vote", "smem-profile=reference-empty",
)
GLOBAL_OPTION = "qcom-tcsr-mutex.boot-unlocked-reference=on"
SMEM_ROM = {"start": 0x80900000, "size": 0x200000,
            "memory": "ram", "name": "tb371fc.smem-reference-empty"}
# Source-derived expectations, not captured physical firmware. CommandDB is
# the independently generated public rpmh-reference.json image. SMEM is the
# v12 empty/global image from smem_build_reference; AOP is aop_reset's cold
# MAIL-v1 descriptor in otherwise zero SRAM. See the profile document.
REFERENCE_REGIONS = (
    {"name": "command-db", "start": 0x80860000, "size": 0x20000,
     "sha256": "416efcf69817cc7b0465a33724bace31e576040b3ec775e0a184a2d051f8c6f8"},
    {"name": "aop-msgram", "start": 0x0c300000, "size": 0x1000,
     "sha256": "7710db6e1ce6a491cfcc437385464af84fa2bcf272c65575171d88f7dd4fa2a4"},
    {"name": "smem", "start": 0x80900000, "size": 0x200000,
     "sha256": "ffb04af24ae4463ce841fee8f340ae0b1da5c7c72d102784a8689bc1cd904a3d"},
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def profile_arguments(name):
    """Return only the fixed named profile; never accept raw option strings."""
    require(type(name) is str and name in PROFILES, "unknown second-stage firmware profile")
    if name == "none":
        return "", []
    return "," + ",".join(MACHINE_OPTIONS), ["-global", GLOBAL_OPTION]


def check_reference_roms(entries, baseline_names):
    require(type(baseline_names) is tuple and len(baseline_names) == 4 and
            len(set(baseline_names)) == 4 and all(type(n) is str for n in baseline_names),
            "four unique baseline ROM names required")
    wanted = Counter((*baseline_names, SMEM_ROM["name"]))
    require(type(entries) is list and len(entries) == 5 and
            all(type(row) is dict and set(row) == {"start", "size", "memory", "name"}
                for row in entries) and
            Counter(row["name"] for row in entries) == wanted,
            "reference profile requires exactly the four baseline ROMs and one SMEM ROM")
    row = next(row for row in entries if row["name"] == SMEM_ROM["name"])
    require(type(row["start"]) is int and type(row["size"]) is int and row == SMEM_ROM,
            "reference SMEM ROM address, size, or memory kind differs")


def validate_reference_firmware(input_dtb, final_dtb, entries, baseline_names, captured):
    """Check measured full firmware bytes and only the declared SMEM delta.

    The ordinary layout validator must also succeed. This function deliberately
    grants no exception for any device node, property, PSCI child, other ROM,
    previous reservation, or kernel/initramfs/DTB byte or address check.
    """
    check_reference_roms(entries, baseline_names)
    require(type(captured) is dict and set(captured) == {r["name"] for r in REFERENCE_REGIONS},
            "all three complete reference firmware captures are required")
    measured = {}
    for region in REFERENCE_REGIONS:
        raw = captured[region["name"]]
        require(type(raw) is bytes and len(raw) == region["size"],
                "reference firmware capture length differs: " + region["name"])
        sha = hashlib.sha256(raw).hexdigest()
        require(sha == region["sha256"],
                "complete reference firmware bytes differ: " + region["name"])
        measured[region["name"]] = {"start": region["start"], "bytes": len(raw), "sha256": sha}
    _, before = _parse_tree(input_dtb)
    _, after = _parse_tree(final_dtb)
    original = Counter((r["start"], r["size"]) for r in before["memreserve"])
    final = Counter((r["start"], r["size"]) for r in after["memreserve"])
    pair = (SMEM_ROM["start"], SMEM_ROM["size"])
    expected = original.copy()
    added = pair not in original
    if added:
        expected[pair] = 1
    require(final == expected,
            "reference profile requires all original reservations and only one missing SMEM reservation")
    return {"schema": "tb371fc-linux-reference-firmware-v1", "profile": REFERENCE_PROFILE,
            "status": "paused_reference_bytes_verified", "synthetic_firmware": True,
            "expectation_source_commit": QEMU_REFERENCE_SOURCE,
            "measured_regions": measured, "complete_regions_verified": True,
            "memory_bytes_read": sum(r["size"] for r in REFERENCE_REGIONS),
            "smem_rom": dict(SMEM_ROM), "smem_memreserve_added": added,
            "physical_firmware_verified": False, "aop_firmware_executed": False,
            "remote_firmware_services_verified": False, "userspace_verified": False,
            "physical_boot_verified": False, "owner_native_linux_passes_added": 0}
