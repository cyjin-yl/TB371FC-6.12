#!/usr/bin/env python3
"""Rebuild a new downstream entry Image from public, SHA-locked inputs only.

Run inside the isolated CT102 build container. Never boots, flashes, opens a
block device, mounts owner storage, or overwrites research1/research2 outputs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
import urllib.request

from fetch_first_stage_sources import INPUTS, digest, safe_unpack

PATCHES = [
    "0001-arm64-name-kexec-restart-wrapper.patch",
    "0002-cpu-kexec-is-not-a-suspend-attempt.patch",
    "0003-qcom-stop-local-watchdog-on-normal-kexec.patch",
    "0004-bpf-provide-non-jit-blinding-stub.patch",
]
DEFCONFIG_SHA = "87185808d2a9a4cf2e8b7c917b6f60fb1c85d064a7903cf7bfeff35c6f69d2f0"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=Path("/work/first-stage-research"))
    ap.add_argument("--recipe", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--name", default="entry-r1")
    args = ap.parse_args()
    if not 1 <= args.jobs <= 4 or not re.fullmatch(r"entry-r[1-9][0-9]*(?:-attempt[1-9][0-9]*)?", args.name):
        ap.error("use 1..4 jobs and an explicit entry-rN[-attemptN] name")
    work, recipe = args.work.resolve(), args.recipe.resolve()
    run = work / args.name
    run.mkdir(exist_ok=False)
    record = {"schema": "tb371fc-downstream-entry-build-v1", "name": args.name,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "physical_device_tested": False, "historical_first_stage_reproduction": False,
              "commands": [], "inputs": {}, "patches": [], "artifacts": {}}
    env = dict(os.environ)
    start = time.monotonic()

    def command(argv, capture=False, check=True, cwd=None):
        print("COMMAND " + json.dumps([str(a) for a in argv]), flush=True)
        before = time.monotonic()
        p = subprocess.run([str(a) for a in argv], cwd=cwd, env=env,
                           stdout=subprocess.PIPE if capture else None,
                           stderr=subprocess.STDOUT if capture else None, text=True)
        item = {"argv": [str(a) for a in argv], "exit_code": p.returncode,
                "elapsed_seconds": time.monotonic() - before}
        if capture:
            item["output"] = p.stdout
            print(p.stdout, end="", flush=True)
        record["commands"].append(item)
        if check and p.returncode:
            raise subprocess.CalledProcessError(p.returncode, argv)
        return p

    try:
        lockfile = recipe / "sources.lock.json"
        lock = json.loads(lockfile.read_text())["inputs"]
        record["source_lock_sha256"] = digest(lockfile)
        for name, spec in INPUTS.items():
            archive = work / "downloads" / (name + "-" + spec["commit"] + ".tar.gz")
            if archive.stat().st_size != lock[name]["archive_bytes"] or digest(archive) != lock[name]["archive_sha256"]:
                raise RuntimeError(f"source archive mismatch: {name}")
            record["inputs"][name] = dict(lock[name], tree=spec["tree"])

        # Re-extract the verified kernel archive rather than trusting a mutable
        # previously unpacked source directory. Toolchain roots are separate.
        source = run / "linux"
        output = run / "out"
        safe_unpack(work / "downloads" / ("kernel-" + INPUTS["kernel"]["commit"] + ".tar.gz"), source, True)
        output.mkdir()
        clang = work / "public-sources/snapdragon-clang"
        gcc64 = work / "public-sources/gcc-aarch64"
        gcc32 = work / "public-sources/gcc-arm"
        env["PATH"] = ":".join(str(p / "bin") for p in [clang, gcc64, gcc32]) + ":/usr/bin:/bin"
        env.update({"KBUILD_BUILD_USER": "tb371fc", "KBUILD_BUILD_HOST": "entry-builder",
                    "KBUILD_BUILD_VERSION": "1", "KBUILD_BUILD_TIMESTAMP": "Sun Aug  9 03:17:56 UTC 2026",
                    "SOURCE_DATE_EPOCH": "1786245476", "TZ": "UTC", "LC_ALL": "C"})
        # The 2020 compiler requires ABI 5; never fake it with a libtinfo6
        # symlink or replace the builder's system libraries.
        runtime_sha = "dd347f794e651039e7b4c391f86c674fed7f415b3dca6b0937beb0d470f09c1a"
        runtime_url = "https://deb.debian.org/debian/pool/main/n/ncurses/libtinfo5_6.4-4_amd64.deb"
        runtime_deb = work / "downloads/libtinfo5_6.4-4_amd64.deb"
        if not runtime_deb.exists():
            with urllib.request.urlopen(runtime_url, timeout=30) as response:
                raw = response.read(1024 * 1024)
            if len(raw) != 328276 or hashlib.sha256(raw).hexdigest() != runtime_sha:
                raise RuntimeError("legacy compiler runtime download mismatch")
            with runtime_deb.open("xb") as f:
                f.write(raw)
        if digest(runtime_deb) != runtime_sha:
            raise RuntimeError("legacy compiler runtime archive mismatch")
        runtime = run / "compiler-runtime"
        command(["dpkg-deb", "--extract", runtime_deb, runtime])
        libraries = list(runtime.rglob("libtinfo.so.5"))
        if len(libraries) != 1:
            raise RuntimeError("unexpected legacy terminfo runtime layout")
        env["LD_LIBRARY_PATH"] = str(libraries[0].parent)
        record["legacy_runtime"] = {"url": runtime_url, "sha256": runtime_sha,
                                    "extracted_to": str(runtime),
                                    "system_libraries_modified": False}
        # These Android-11 revisions retain GNU binutils in repositories named
        # gcc-4.9, but no GCC C compiler. Target C compilation uses Clang.
        bins = [clang / "bin/clang", gcc64 / "bin/aarch64-linux-android-as",
                gcc64 / "bin/aarch64-linux-android-ld", gcc32 / "bin/arm-linux-androideabi-as"]
        record["tools"] = []
        for binary in bins:
            result = command([binary, "--version"], capture=True)
            record["tools"].append({"path": str(binary), "sha256": digest(binary),
                                    "version": result.stdout.splitlines()[0]})
        record["host_packages"] = command(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Architecture}\n"], capture=True).stdout

        base = source / "arch/arm64/configs/vendor/tb371fc_defconfig"
        if digest(base) != DEFCONFIG_SHA:
            raise RuntimeError("published defconfig hash mismatch")
        record["base_defconfig_sha256"] = digest(base)
        for name in PATCHES:
            patch = recipe / name
            command(["git", "apply", "--check", patch], cwd=source)
            command(["git", "apply", patch], cwd=source)
            record["patches"].append({"name": name, "sha256": digest(patch)})
        fragment = recipe / "first-stage.config"
        record["fragment_sha256"] = digest(fragment)
        command(["bash", source / "scripts/kconfig/merge_config.sh", "-m", "-O", output, base, fragment], cwd=source)
        make = ["make", "-C", source, f"O={output}", "ARCH=arm64", "CC=clang",
                "HOSTCC=gcc", "HOSTCXX=g++", "CLANG_TRIPLE=aarch64-linux-gnu-",
                "CROSS_COMPILE=aarch64-linux-android-", "CROSS_COMPILE_ARM32=arm-linux-androideabi-", "LOCALVERSION="]
        command(make + ["olddefconfig"])
        config = (output / ".config").read_text()
        for key in ["KEXEC", "KEXEC_CORE", "DEVTMPFS", "DEVTMPFS_MOUNT", "USB_CONFIGFS_ACM", "USB_F_ACM", "USB_CONFIGFS_NCM", "USB_DWC3_MSM", "IKCONFIG_PROC", "SERIAL_AMBA_PL011_CONSOLE"]:
            if f"CONFIG_{key}=y\n" not in config:
                raise RuntimeError(f"required builtin configuration missing: {key}")
        if "# CONFIG_MODULES is not set\n" not in config:
            raise RuntimeError("unexpected external module dependency")
        shutil.copyfile(output / ".config", run / "resolved.config")
        # The config and source hashes are available even if a compiler fails.
        record["resolved_config_sha256"] = digest(output / ".config")
        record["source_changes"] = {rel: digest(source / rel) for rel in [
            "arch/arm64/kernel/cpu-reset.h", "arch/arm64/kernel/machine_kexec.c",
            "kernel/cpu.c", "drivers/soc/qcom/watchdog_v2.c", "include/linux/filter.h"]}
        (run / "prepared.json").write_text(json.dumps(record, indent=2) + "\n")
        command(make + [f"-j{args.jobs}", "Image"])
        image = output / "arch/arm64/boot/Image"
        raw = image.read_bytes()[:64]
        if len(raw) != 64 or raw[56:60] != b"ARM\x64":
            raise RuntimeError("result is not an uncompressed ARM64 Image")
        text_offset, effective, flags = struct.unpack_from("<QQQ", raw, 8)
        if effective < image.stat().st_size:
            raise RuntimeError("ARM64 effective memory region is smaller than Image")
        record["arm64_header"] = {"text_offset": text_offset, "image_size": effective, "flags": flags,
                                   "stored_bytes": image.stat().st_size}
        record["release"] = (output / "include/config/kernel.release").read_text().strip()
        artifacts = run / "artifacts"
        artifacts.mkdir()
        for filename, origin in {"Image": image, "kernel.config": output / ".config", "System.map": output / "System.map"}.items():
            shutil.copyfile(origin, artifacts / filename)
            record["artifacts"][filename] = {"bytes": origin.stat().st_size, "sha256": digest(origin)}
        record["build_completed"] = True
    except Exception as exc:
        record["build_completed"] = False
        record["failure"] = str(exc)
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - start
        record["ended_utc"] = datetime.now(timezone.utc).isoformat()
        record["recipe_files"] = {p.name: digest(p) for p in recipe.iterdir() if p.is_file()}
        (run / "build.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
