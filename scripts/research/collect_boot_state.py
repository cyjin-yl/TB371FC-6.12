#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read only allowlisted Android boot state; never unlock, write or reboot.

Android properties can disagree with the bootloader-supplied command line.
Record both without reading identifiers, raw command lines or partition bytes.
Neither view replaces an attended check of the actual boot entry/restore path.
"""
import datetime
import json
from pathlib import Path
import shlex
import subprocess

PROPERTIES = (
    "ro.product.model", "ro.boot.flash.locked", "ro.boot.vbmeta.device_state",
    "ro.boot.verifiedbootstate", "ro.boot.veritymode", "ro.boot.slot_suffix",
    "ro.build.type", "ro.debuggable", "ro.oem_unlock_supported",
    "sys.oem_unlock_allowed",
)
BOOT_KEYS = {
    "androidboot.flash.locked", "androidboot.vbmeta.device_state",
    "androidboot.verifiedbootstate", "androidboot.veritymode", "androidboot.slot_suffix",
}


def collect():
    result = {"schema_version": 1,
              "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "passive Android boot metadata; no flash, unlock or physical boot test",
              "properties": {}, "kernel_boot_arguments": {}}
    for name in PROPERTIES:
        try:
            proc = subprocess.run(["/system/bin/getprop", name], capture_output=True,
                                  text=True, timeout=3, check=True)
            value = proc.stdout.strip()
            result["properties"][name] = value if len(value) <= 256 else {"unavailable": "oversize"}
        except (OSError, subprocess.SubprocessError) as error:
            result["properties"][name] = {"unavailable": type(error).__name__}
    for name in ("/proc/cmdline", "/proc/bootconfig"):
        try:
            with Path(name).open("rb") as stream:
                blob = stream.read(65537)
            if len(blob) > 65536:
                raise ValueError("oversize")
            tokens = shlex.split(blob.decode("utf-8", "strict").replace("\n", " "))
            selected = {}
            for index, token in enumerate(tokens):
                if "=" in token:
                    key, value = token.split("=", 1)
                    if key in BOOT_KEYS:
                        selected[key] = value
                elif (token in BOOT_KEYS and index + 2 < len(tokens)
                      and tokens[index + 1] == "="):
                    selected[token] = tokens[index + 2]
            result["kernel_boot_arguments"][name] = selected
        except (OSError, ValueError) as error:
            result["kernel_boot_arguments"][name] = {"unavailable": type(error).__name__}
    result["named_partition_presence"] = {
        f"{name}_{slot}": Path(f"/dev/block/by-name/{name}_{slot}").exists()
        for name in ("boot", "recovery", "vbmeta", "dtbo") for slot in ("a", "b")}
    disagreements = []
    for prop, key in (("ro.boot.vbmeta.device_state", "androidboot.vbmeta.device_state"),
                      ("ro.boot.verifiedbootstate", "androidboot.verifiedbootstate"),
                      ("ro.boot.slot_suffix", "androidboot.slot_suffix")):
        left = result["properties"].get(prop)
        right = result["kernel_boot_arguments"].get("/proc/cmdline", {}).get(key)
        if isinstance(left, str) and isinstance(right, str) and left != right:
            disagreements.append({"property": prop, "kernel_argument": key,
                                  "property_value": left, "kernel_value": right})
    result["disagreements"] = disagreements
    result["unlock_action_authorized_by_this_capture"] = False
    result["physical_mainline_boot_tested"] = False
    return result


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2, sort_keys=True))
