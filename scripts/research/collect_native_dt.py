#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read the running Android DT and allowlisted DT-selection observations.

No raw FDT, command line, bootconfig, serial, MAC or ramdisk content is emitted.
This is an Android observation, never a physical mainline-Linux acceptance run.
Run with access to /sys/firmware/fdt; the tool does not change permissions.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

from native_dt import inspect_fdt

MAX_FDT = 16 * 1024 * 1024
BOOT_KEYS = ("androidboot.dtb_idx", "androidboot.dtbo_idx", "androidboot.slot_suffix")
PROPERTIES = ("ro.product.model", "ro.product.device", "ro.boot.slot_suffix",
              "ro.boot.dtb_idx", "ro.boot.dtbo_idx")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def bounded_read(path, limit):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("input exceeds its fixed limit")
    return data


def selection_value(key, value):
    """Retain validated numbers/slots only, even on malformed input."""
    if key.endswith("slot_suffix"):
        return {"slot_suffix": value} if value in ("_a", "_b") else {"valid": False}
    pattern = r"[0-9]{1,10}" if key.endswith("dtb_idx") else r"[0-9]{1,10}(?:,[0-9]{1,10}){0,63}"
    if not re.fullmatch(pattern, value):
        return {"valid": False}
    indices = [int(item) for item in value.split(",")]
    if any(item > 0xffffffff for item in indices):
        return {"valid": False}
    return {"indices": indices, "valid": True}


def command_line_observations(data):
    values = {key: [] for key in BOOT_KEYS}
    for token in shlex.split(data.decode("utf-8", "strict")):
        key, sep, value = token.partition("=")
        if sep and key in values:
            values[key].append(selection_value(key, value))
    return values


def bootconfig_observations(data):
    """Read only flat, fully-qualified keys; never guess nested XBC syntax."""
    values = {key: [] for key in BOOT_KEYS}
    for line in data.decode("utf-8", "strict").splitlines():
        match = re.fullmatch(r'\s*(androidboot\.(?:dtb_idx|dtbo_idx|slot_suffix))\s*=\s*(.*?)\s*;?\s*', line)
        if not match:
            continue
        raw = match.group(2).rstrip(";").strip()
        if len(raw) >= 2 and raw[0] == raw[-1] == '"':
            raw = raw[1:-1]
        values[match.group(1)].append(selection_value(match.group(1), raw))
    return values


def collect():
    result = {
        "schema": "tb371fc-android-native-dt-observation-v1",
        "captured_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evidence_class": "owner_android_read_only",
        "kernel_release": os.uname().release,
        "scope": "running Android FDT forensic metadata and allowlisted reported DT indices",
        "fdt_parse_mode": "explicit live forensic inspection; nonzero alignment padding retained as nonconformant",
        "bootloader_selection_replayed": False,
        "bootloader_acceptance_tested": False,
        "physical_mainline_linux_tested": False,
        "owner_native_linux_passes_added": 0,
        "properties": {}, "boot_arguments": {},
    }
    for name in PROPERTIES:
        try:
            proc = subprocess.run(["/system/bin/getprop", name], check=True,
                                  capture_output=True, text=True, timeout=3)
            value = proc.stdout.strip()
            if name.startswith("ro.product."):
                result["properties"][name] = value if re.fullmatch(r"[A-Za-z0-9._ -]{1,80}", value) else {"unavailable": "empty_or_invalid"}
            elif not value:
                result["properties"][name] = {"present": False}
            else:
                result["properties"][name] = selection_value(name, value)
        except (OSError, subprocess.SubprocessError):
            result["properties"][name] = {"unavailable": "read_failed"}
    for name, decoder in (("/proc/cmdline", command_line_observations),
                          ("/proc/bootconfig", bootconfig_observations)):
        try:
            data = bounded_read(name, 65536)
            result["boot_arguments"][name] = {
                "bytes": len(data), "sha256": digest(data),
                "observations": decoder(data),
                "unparsed_nested_xbc_not_inferred": name.endswith("bootconfig"),
            }
        except (OSError, ValueError):
            result["boot_arguments"][name] = {"unavailable": "read_or_parse_failed"}
    first = bounded_read("/sys/firmware/fdt", MAX_FDT)
    # The owner's live FDT has a confirmed nonzero property-padding byte.
    # Keep that defect visible while reading bounded metadata; artifact bundle
    # parsers retain their strict default and no bootability gate is relaxed.
    inspected = inspect_fdt(first, allow_nonzero_padding=True)
    second = bounded_read("/sys/firmware/fdt", MAX_FDT)
    if first != second:
        raise ValueError("running FDT changed during observation")
    result["running_fdt"] = {
        "bytes": len(first), "sha256": digest(first),
        "stable_across_two_reads": True, "inspection": inspected,
    }
    result["source_sha256"] = digest(Path(__file__).read_bytes()) if "__file__" in globals() and Path(__file__).is_file() else None
    return result


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, sort_keys=True))
