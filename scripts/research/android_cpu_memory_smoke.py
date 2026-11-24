#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Short, single-process Android SYS-04 correctness smoke; not a benchmark."""
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time

SIZE = 2 * 1024 * 1024
EXPECTED = "91d3beb88a9b2f778a6c44a1c53b63d3c79931845a9aef84b3fb414610bd1938"
REVERSED = "5d0930c72a53828aec014fbecdaf87dfc6f71723521bc2a723a515bfc52353c5"

def deadline(*_):
    raise TimeoutError("12-second smoke deadline")

def read_conditions():
    # Only three allowlisted read-only values; never read user files.
    p = subprocess.run(["su", "-c", "grep '^MemAvailable:' /proc/meminfo; cat /sys/class/power_supply/battery/temp; cat /sys/class/power_supply/battery/capacity"],
                       capture_output=True, text=True, timeout=3, check=True)
    match = re.fullmatch(r"MemAvailable:\s+(\d+) kB\s*\n(-?\d+)\s*\n(\d+)\s*", p.stdout)
    if not match:
        raise ValueError("unexpected preflight values")
    return {"available_bytes": int(match[1])*1024, "battery_temp_deci_c": int(match[2]), "battery_percent": int(match[3])}

def run():
    if os.geteuid() == 0:
        raise ValueError("workload must be unprivileged")
    before = read_conditions()
    if before["available_bytes"] < 128*1024*1024 or not 0 <= before["battery_temp_deci_c"] < 380 or before["battery_percent"] < 20:
        raise ValueError("resource/temperature preflight refused")
    allowed = sorted(os.sched_getaffinity(0))
    if not allowed or len(allowed) > 8 or any(c not in range(8) for c in allowed):
        raise ValueError("unexpected process affinity")
    started = time.monotonic()
    fixture = bytes(range(256)) * (SIZE//256)
    rows = []
    try:
        for cpu in allowed:
            os.sched_setaffinity(0, {cpu})
            if os.sched_getaffinity(0) != {cpu}:
                raise ValueError("affinity readback mismatch")
            for trial in range(3):
                copy = bytearray(fixture)
                first = hashlib.sha256(copy).hexdigest()
                copy.reverse()
                second = hashlib.sha256(copy).hexdigest()
                if first != EXPECTED or second != REVERSED:
                    raise ValueError("deterministic checksum mismatch")
                rows.append({"cpu": cpu, "trial": trial+1, "original_sha256": first, "reversed_sha256": second})
                del copy
    finally:
        os.sched_setaffinity(0, set(allowed))
    if os.sched_getaffinity(0) != set(allowed):
        raise ValueError("affinity restoration failed")
    after = read_conditions()
    return {"schema":"tb371fc-android-cpu-memory-smoke-v1","kernel_release":os.uname().release,
            "python":sys.version.split()[0],"conditions_before":before,"conditions_after":after,
            "allowed_cpus":allowed,"unavailable_cpus":sorted(set(range(8))-set(allowed)),
            "trials":rows,"fixture_bytes":SIZE,"live_fixture_and_copy_bytes":2*SIZE,
            "elapsed_seconds":round(time.monotonic()-started,6),"affinity_restored":True,
            "all_requested_checks_passed":True,"native_linux_passes_added":0,
            "scope":"short sequential Android userspace checksum smoke; not sustained, parallel, thermal or throughput qualification"}

if __name__ == "__main__":
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(12)
    try:
        print(json.dumps(run(),sort_keys=True))
    finally:
        signal.alarm(0)
