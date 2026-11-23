#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a separate Novatek candidate against the frozen research5 output.

Copies only the module sources, checks/applies patch 0020 in that copy and
uses normal external-module Kbuild. Never installs or loads the result, and
does not sign it or alter the existing signed research5 module set.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


SOURCE = Path("source-input/linux-6.12.114-input-integration")
DRIVER = Path("drivers/input/touchscreen/nt36523")
EXPECTED = {
    str(SOURCE / DRIVER / "nt36xxx_fw_update.c"): "8720c0a2fa1cc4311bb100d2d493e3bf697fb20e6d402589e102bfa1b6f33f77",
    "kernel-out/.config": "a4980121abcc3e2bac47f7020e63c8c00949c53c289019c22b67808d84cd3afa",
    "kernel-out/Module.symvers": "bd99bf91ba0644a9f2d52de1cf5e390118569371644bc80484b88b0e555e8545",
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--patch", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    base, patch, work = (p.resolve() for p in (args.baseline, args.patch, args.work))
    if work == base or work.is_relative_to(base) or base.is_relative_to(work):
        raise SystemExit("work must be separate from baseline")
    before = {rel: digest(base / rel) for rel in EXPECTED}
    if before != EXPECTED:
        raise SystemExit("frozen research5 inputs differ")
    work.mkdir(parents=True, mode=0o700, exist_ok=False)
    source = work / "source"
    target = source / DRIVER
    target.parent.mkdir(parents=True)
    shutil.copytree(base / SOURCE / DRIVER, target)
    shutil.copyfile(patch, work / "0020.patch")
    subprocess.run(["git", "apply", "--check", str(work / "0020.patch")], cwd=source, check=True)
    subprocess.run(["git", "apply", str(work / "0020.patch")], cwd=source, check=True)
    command = ["make", "-C", str(base / "kernel-out"), "M=" + str(target),
               "ARCH=arm64", "LLVM=1", "LLVM_IAS=1", "CROSS_COMPILE=aarch64-linux-gnu-",
               "-j" + str(max(1, min(args.jobs, 4))), "modules"]
    start = datetime.now(timezone.utc).isoformat()
    with (work / "build.log").open("w") as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=600)
    after = {rel: digest(base / rel) for rel in EXPECTED}
    record = {"schema_version": 1, "started_at_utc": start,
              "finished_at_utc": datetime.now(timezone.utc).isoformat(),
              "evidence_class": "host_build", "command": command,
              "build_exit_code": result.returncode, "patch_sha256": digest(work / "0020.patch"),
              "baseline_hashes": before, "baseline_hashes_after": after,
              "baseline_unchanged": before == after, "module_installed": False,
              "module_loaded": False, "module_signed": False, "device_linux_tested": False}
    module = target / "nt36523_ts.ko"
    if result.returncode == 0:
        record["module"] = {"path": str(module), "size": module.stat().st_size,
                            "sha256": digest(module),
                            "vermagic": subprocess.check_output(["modinfo", "-F", "vermagic", str(module)], text=True).strip(),
                            "signer": subprocess.check_output(["modinfo", "-F", "signer", str(module)], text=True).strip()}
        record["elf_header"] = subprocess.check_output(["readelf", "-h", str(module)], text=True)
        if not record["module"]["vermagic"].startswith("6.12.114-tb371fc-research5-services "):
            raise RuntimeError("module release mismatch")
        if "AArch64" not in record["elf_header"]:
            raise RuntimeError("module architecture mismatch")
    (work / "result.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True))
    if result.returncode or before != after:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
