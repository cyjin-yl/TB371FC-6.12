#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Observe Android RAM resource geometry and CPU topology without device writes.

Fixed procfs/sysfs allowlist only; no /dev/mem, arbitrary registers, logs,
debugfs mounts, input events, workload, module loading or power-state changes.
The complete invocation is bounded to 20 seconds and prints JSON to stdout.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import re
import signal

from android_memory import (MAX_CPUS, MAX_IOMEM, MAX_MEMINFO, parse_cpu_list,
                            parse_iomem, parse_meminfo, sha256)

MAX_FDT = 16 * 1024 * 1024
CPU_ROOT = "/sys/devices/system/cpu"


def read(path, limit):
    with open(path, "rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("allowlisted file exceeds bound")
    return data


def item(path, limit, parse):
    try:
        data = read(path, limit)
        return {"bytes": len(data), "sha256": sha256(data), "value": parse(data)}
    except (OSError, ValueError, UnicodeError) as error:
        return {"unavailable": type(error).__name__}


def integer(data):
    if not re.fullmatch(rb"-?[0-9]{1,10}\s*", data):
        raise ValueError("invalid scalar")
    return int(data)


def collect():
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fdt_first = read("/sys/firmware/fdt", MAX_FDT)
    iomem_first = read("/proc/iomem", MAX_IOMEM)
    memory = read("/proc/meminfo", MAX_MEMINFO)
    cpus = {name: item(f"{CPU_ROOT}/{name}", 256, parse_cpu_list)
            for name in ("possible", "present", "online", "offline")}
    topology = {}
    possible = cpus["possible"].get("value", [])
    for cpu in possible[:MAX_CPUS]:
        base = f"{CPU_ROOT}/cpu{cpu}/topology"
        topology[str(cpu)] = {name: item(f"{base}/{name}", 256, parse)
                              for name, parse in (("core_id", integer), ("physical_package_id", integer),
                                                  ("core_siblings_list", parse_cpu_list),
                                                  ("thread_siblings_list", parse_cpu_list))}
    iomem_second = read("/proc/iomem", MAX_IOMEM)
    fdt_second = read("/sys/firmware/fdt", MAX_FDT)
    result = {
        "schema": "tb371fc-android-memory-observation-v1",
        "capture_utc": started,
        "completed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evidence_class": "owner_android_read_only",
        "kernel_release": os.uname().release,
        "machine": os.uname().machine,
        "fdt": {"bytes": len(fdt_first), "sha256": sha256(fdt_first),
                "second_sha256": sha256(fdt_second), "stable_across_two_reads": fdt_first == fdt_second},
        "iomem": {"bytes": len(iomem_first), "sha256": sha256(iomem_first),
                  "second_sha256": sha256(iomem_second), "stable_across_two_reads": iomem_first == iomem_second,
                  "parsed": parse_iomem(iomem_first)},
        "meminfo": {"bytes": len(memory), "sha256": sha256(memory), "values_bytes": parse_meminfo(memory)},
        "cpu_lists": cpus, "cpu_topology": topology,
        "optional_interface_presence": {path: os.path.isdir(path) for path in (
            "/sys/kernel/mm/cma", "/sys/kernel/debug/cma", "/sys/kernel/debug/memblock")},
        "interface_presence_scope": "stat only; no debugfs traversal, reads or mounts",
        "raw_fdt_or_resource_labels_emitted": False,
        "device_state_writes_performed": False,
        "cpu_memory_workload_performed": False,
        "physical_mainline_linux_tested": False,
        "owner_native_linux_passes_added": 0,
    }
    return result


def timeout_handler(signum, frame):
    raise TimeoutError("20-second observation deadline")


if __name__ == "__main__":
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(20)
    try:
        result = collect()
        result["source_sha256"] = sha256(Path(__file__).read_bytes())
        result["parser_sha256"] = sha256(Path(__file__).with_name("android_memory.py").read_bytes())
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        signal.alarm(0)
