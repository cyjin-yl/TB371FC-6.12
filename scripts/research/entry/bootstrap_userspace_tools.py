#!/usr/bin/env python3
"""Install pinned cross-build tools in the dedicated builder, without binfmt.

No host/CT package changes: invoke only inside tb371fc-build-ssd-20261123.
The apt simulation must contain no upgrades/removals. Keep downloaded .debs
and record their SHA-256 values for the independently built entry userspace.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PINS = {
    "binutils-aarch64-linux-gnu": "2.44-3",
    "cpp-14-aarch64-linux-gnu": "14.2.0-19cross1",
    "cpp-aarch64-linux-gnu": "4:14.2.0-1",
    "gcc-14-aarch64-linux-gnu": "14.2.0-19cross1",
    "gcc-14-aarch64-linux-gnu-base": "14.2.0-19cross1",
    "gcc-14-cross-base": "14.2.0-19cross1",
    "gcc-aarch64-linux-gnu": "4:14.2.0-1",
    "libasan8-arm64-cross": "14.2.0-19cross1",
    "libatomic1-arm64-cross": "14.2.0-19cross1",
    "libc6-arm64-cross": "2.41-11cross1",
    "libc6-dev-arm64-cross": "2.41-11cross1",
    "libgcc-14-dev-arm64-cross": "14.2.0-19cross1",
    "libgcc-s1-arm64-cross": "14.2.0-19cross1",
    "libgomp1-arm64-cross": "14.2.0-19cross1",
    "libhwasan0-arm64-cross": "14.2.0-19cross1",
    "libitm1-arm64-cross": "14.2.0-19cross1",
    "liblsan0-arm64-cross": "14.2.0-19cross1",
    "libstdc++6-arm64-cross": "14.2.0-19cross1",
    "libtsan2-arm64-cross": "14.2.0-19cross1",
    "libubsan1-arm64-cross": "14.2.0-19cross1",
    "linux-libc-dev-arm64-cross": "6.12.38-1cross1",
    "qemu-user": "1:10.0.13+ds-0+deb13u1",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=Path("/work/first-stage-research"))
    args = ap.parse_args()
    work = args.work.resolve()
    if not Path("/.dockerenv").exists():
        raise SystemExit("run only inside the dedicated Docker builder")
    manifest = work / "userspace-toolchain.json"
    if manifest.exists():
        raise SystemExit("existing manifest; refuse to overwrite")
    cache = work / "userspace-debs"
    (cache / "partial").mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive", LC_ALL="C")
    args_apt = ["--no-install-recommends", "--no-remove", "-o", f"Dir::Cache::archives={cache}",
                "-o", "APT::Keep-Downloaded-Packages=true", "install"]
    packages = [f"{k}={v}" for k, v in PINS.items()]
    simulation = subprocess.check_output(["apt-get", "-s", *args_apt, *packages], env=env, text=True)
    print(simulation, flush=True)
    if not re.search(r"\b0 upgraded, \d+ newly installed, 0 to remove", simulation):
        raise SystemExit("simulation would change existing package versions; stop")
    if "qemu-user-binfmt" in "\n".join(line for line in simulation.splitlines() if line.startswith("Inst ")):
        raise SystemExit("binfmt integration must not be installed")
    subprocess.run(["apt-get", "-y", *args_apt, *packages], env=env, check=True)
    actual = {}
    for name, expected in PINS.items():
        version = subprocess.check_output(["dpkg-query", "-W", "-f=${Version}", name], text=True)
        if version != expected:
            raise SystemExit(f"installed package version mismatch: {name}")
        actual[name] = version
    record = {"schema": "tb371fc-entry-userspace-toolchain-v1",
              "captured_utc": datetime.now(timezone.utc).isoformat(),
              "packages": actual, "simulation": simulation,
              "debs": {p.name: {"bytes": p.stat().st_size,
                                "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in sorted(cache.glob("*.deb"))},
              "binfmt_integration_requested": False,
              "host_or_ct_packages_modified": False}
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    print("TOOLCHAIN_READY", manifest, flush=True)


if __name__ == "__main__":
    main()
