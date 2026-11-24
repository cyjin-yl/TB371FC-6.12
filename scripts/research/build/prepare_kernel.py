#!/usr/bin/env python3
"""Assemble an explicit 6.12.114 research tree; never operate a tablet.

This is a new source combination, not a reconstruction claim for R226. The
handoff delta and added sources are independently recorded in source-manifest.
No historical patch glob, generated Windows path, or existing output is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

VERSION = "6.12.114"
ARCHIVE_SHA256 = "7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3"
URL = f"https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-{VERSION}.tar.xz"
PATCHES = (
    "experimental/community-handoff/reference/kernel-6.12.114/working-tree.patch",
    "mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch",
    "mainline-port/patches/0006-backlight-add-tb371fc-dual-ktz8866.patch",
    "mainline-port/backports/linux-6.12/0013-input-nt36523-preserve-gpio-irq-errors.patch",
    "mainline-port/backports/linux-6.12/0014-backlight-tb371fc-unwind-failed-probe.patch",
    "mainline-port/backports/linux-6.12/0015-drm-msm-balance-headless-node-reference.patch",
    "mainline-port/backports/linux-6.12/0016-dts-tb371fc-linux-6.12-compat.patch",
    "mainline-port/patches/0017-hid-i2c-add-optional-wake-gpio.patch",
    "mainline-port/backports/linux-6.12/0017-arm64-scope-tb371fc-early-page-table-pool.patch",
)
COPIES = {
    "mainline-port/backports/linux-6.12/tb371fc-ktz8866.c": "drivers/video/backlight/tb371fc-ktz8866.c",
    "mainline-port/backports/linux-6.12/panel-novatek-nt36523.c": "drivers/gpu/drm/panel/panel-novatek-nt36523.c",
    "mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts": "arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, **kwargs):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--work", type=Path, default=Path("/work"))
    args = parser.parse_args()
    repo, work = args.repo.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    destination = work / "linux-6.12.114-research1"
    if destination.exists():
        raise SystemExit("source already exists; retain it and use a new --work directory")
    inputs = list(PATCHES) + list(COPIES) + [
        "experimental/community-handoff/reference/kernel-6.12.114/config",
        "scripts/research/build/research.config",
    ]
    manifest = {"schema_version": 1, "base_url": URL, "base_sha256": ARCHIVE_SHA256,
                "profile": "6.12.114-research1; compile qualification, hardware untested",
                "inputs": {name: digest(repo / name) for name in inputs}}
    downloads = work / "downloads"
    downloads.mkdir(exist_ok=True)
    archive = downloads / f"linux-{VERSION}.tar.xz"
    if not archive.exists():
        # Keep a partial download separate; never trust a truncated file as the source.
        partial = archive.with_suffix(".xz.partial")
        run(["curl", "--fail", "--location", "--retry", "3", "--connect-timeout", "20",
             "--max-time", "1800", "--output", partial, URL])
        if digest(partial) != ARCHIVE_SHA256:
            raise SystemExit("kernel archive SHA-256 mismatch; partial file retained")
        partial.rename(archive)
    if digest(archive) != ARCHIVE_SHA256:
        raise SystemExit("cached kernel archive SHA-256 mismatch")
    unpacked = work / f"linux-{VERSION}"
    if unpacked.exists():
        raise SystemExit("unpack destination exists; use a new work directory")
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            if not (member.name.startswith(f"linux-{VERSION}/") or
                    (member.name == f"linux-{VERSION}" and member.isdir())):
                raise SystemExit("unexpected archive member")
        stream.extractall(work, filter="data")
    unpacked.rename(destination)
    for source, target in COPIES.items():
        shutil.copyfile(repo / source, destination / target)
    for patch in PATCHES:
        run(["git", "apply", "--recount", "--check", repo / patch], cwd=destination)
        run(["git", "apply", "--recount", repo / patch], cwd=destination)
    dts_makefile = destination / "arch/arm64/boot/dts/qcom/Makefile"
    with dts_makefile.open("a") as stream:
        stream.write("\ndtb-$(CONFIG_ARCH_QCOM) += sm8250-lenovo-tb371fc.dtb\n")
    manifest["assembled_files"] = {
        target: digest(destination / target) for target in COPIES.values()
    }
    manifest["assembled_files"]["drivers/input/touchscreen/nt36523/nt36xxx.c"] = digest(
        destination / "drivers/input/touchscreen/nt36523/nt36xxx.c")
    for name in ("arch/arm64/mm/mmu.c", "drivers/gpu/drm/msm/msm_drv.c", "drivers/hid/i2c-hid/i2c-hid-of.c",
                 "Documentation/devicetree/bindings/input/hid-over-i2c.yaml"):
        manifest["assembled_files"][name] = digest(destination / name)
    (work / "source-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(destination)


if __name__ == "__main__":
    main()
