#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read fixed stock firmware identities; never load firmware or read input events.

Run with the existing Android root shell and Termux Python. Only file sizes,
hashes, selected DT properties, model and driver binding are emitted. Firmware
payloads, input reports and per-unit identifiers are not included.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import struct
import subprocess


FIRMWARE_NAMES = (
    "novatek_ts_fw_boe.bin", "novatek_ts_fw_boe_6.bin",
    "novatek_ts_mp_boe.bin", "novatek_ts_mp_boe_6.bin",
    "novatek_ts_tm_fw.bin", "novatek_ts_tm_fw_6.bin",
    "novatek_ts_tm_mp.bin", "novatek_ts_tm_mp_6.bin",
)


def main():
    files = []
    for name in FIRMWARE_NAMES:
        path = Path("/vendor/firmware") / name
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise SystemExit("firmware exceeds fixed capture bound")
        files.append({"path": str(path), "size": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()})

    device = Path("/sys/bus/spi/devices/spi0.0")
    properties = {}
    for name in ("compatible", "status", "reg", "spi-max-frequency",
                 "novatek,pen-support", "novatek,stylus-resol-double",
                 "novatek,irq-gpio", "novatek,reset-gpio", "panel"):
        path = device / "of_node" / name
        if not path.exists():
            properties[name] = {"present": False}
            continue
        with path.open("rb") as stream:
            raw = stream.read(4097)
        if len(raw) > 4096:
            raise SystemExit("DT property exceeds capture bound")
        if name in ("compatible", "status"):
            properties[name] = {"strings": raw.rstrip(b"\0").decode().split("\0")}
        elif not raw:
            properties[name] = {"present": True}
        elif len(raw) % 4 == 0:
            properties[name] = {"cells_be32": list(struct.unpack(">" + "I" * (len(raw) // 4), raw))}
        else:
            properties[name] = {"byte_count": len(raw), "hex": raw.hex()}

    result = {
        "schema_version": 1,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "device_android",
        "collector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model": subprocess.check_output(
            ["/system/bin/getprop", "ro.product.model"], text=True, timeout=3).strip(),
        "kernel_release": platform.release(),
        "firmware": files,
        "touchscreen": {"path": str(device), "driver": str((device / "driver").resolve()),
                        "modalias": (device / "modalias").read_text().strip(),
                        "of_node": str((device / "of_node").resolve()),
                        "properties": properties},
        "firmware_written_or_loaded": False,
        "input_events_read": False,
        "device_linux_tested": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
