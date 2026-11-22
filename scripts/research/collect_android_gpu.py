#!/usr/bin/env python3
"""Bounded Android GPU metadata; no commands, firmware export or GPU workloads."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import signal
import struct


def bounded(path, maximum=2 * 1024 * 1024):
    def expired(signum, frame):
        raise TimeoutError("bounded metadata read")
    old = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 0.75)
    try:
        with Path(path).open("rb") as stream:
            data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError("oversize")
        return data
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def elf_metadata(data):
    if data[:4] != b"\x7fELF":
        return None
    if len(data) < 64 or data[5] not in (1, 2):
        return {"unavailable": "invalid ELF header"}
    order = "<" if data[5] == 1 else ">"
    if data[4] == 1:
        offset, = struct.unpack_from(order + "I", data, 28)
        size, count = struct.unpack_from(order + "HH", data, 42)
        fmt = order + "IIIIIIII"
    elif data[4] == 2:
        offset, = struct.unpack_from(order + "Q", data, 32)
        size, count = struct.unpack_from(order + "HH", data, 54)
        fmt = order + "IIQQQQQQ"
    else:
        return {"unavailable": "unsupported ELF class"}
    if count > 64 or size < struct.calcsize(fmt) or offset + size * count > len(data):
        return {"unavailable": "invalid program header bounds"}
    segments = []
    for index in range(count):
        row = struct.unpack_from(fmt, data, offset + size * index)
        if data[4] == 1:
            kind, file_offset, _, _, file_size, mem_size, flags, _ = row
        else:
            kind, flags, file_offset, _, _, file_size, mem_size, _ = row
        segments.append({"index": index, "type": kind, "flags": flags,
                         "file_offset": file_offset, "file_size": file_size,
                         "memory_size": mem_size,
                         "bytes_present_in_this_file": file_offset + file_size <= len(data)})
    return {"class_bits": 32 if data[4] == 1 else 64, "program_headers": segments}


def capture():
    result = {"schema_version": 1, "capture_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "scope": "Android GPU identity, binding and firmware metadata; no hardware acceleration test",
              "attributes": {}, "bindings": {}, "firmware": [], "unavailable": {}}
    paths = ("/proc/sys/kernel/osrelease", "/sys/class/kgsl/kgsl-3d0/gpu_model",
             "/sys/class/kgsl/kgsl-3d0/gpu_available_frequencies",
             "/sys/class/kgsl/kgsl-3d0/devfreq/available_frequencies",
             "/sys/class/kgsl/kgsl-3d0/devfreq/governor")
    for path in paths:
        try:
            result["attributes"][path] = bounded(path, 4096).decode().strip()
        except (OSError, ValueError, UnicodeError) as exc:
            result["unavailable"][path] = type(exc).__name__
    for root in ("/sys/class/drm/card0", "/sys/class/drm/renderD128", "/sys/class/kgsl/kgsl-3d0"):
        result["bindings"][root] = {}
        for name in ("driver", "of_node"):
            path = Path(root) / "device" / name
            if path.is_symlink():
                result["bindings"][root][name] = str(path.resolve())
    names = ("a650_gmu.bin", "a650_sqe.fw", "a630_sqe.fw", "a650_zap.elf", "a650_zap.mdt",
             "a650_zap.b00", "a650_zap.b01", "a650_zap.b02")
    for directory in ("/vendor/firmware", "/vendor/firmware_mnt/image"):
        for name in names:
            path = Path(directory) / name
            if not path.is_file():
                continue
            try:
                data = bounded(path)
                item = {"path": str(path), "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                if name.endswith((".elf", ".mdt")):
                    item["elf"] = elf_metadata(data)
                result["firmware"].append(item)
            except (OSError, ValueError) as exc:
                result["unavailable"][str(path)] = type(exc).__name__
    return result


if __name__ == "__main__":
    print(json.dumps(capture(), indent=2, sort_keys=True))
