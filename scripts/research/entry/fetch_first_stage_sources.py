#!/usr/bin/env python3
"""Fetch immutable public inputs for the new TB371FC downstream entry study.

This does not reproduce V56/R201 and never contacts or writes a tablet. The
first acquisition records archive hashes; subsequent runs can require that
manifest with --lock. Unfinished downloads/extractions are retained for review.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile
import time
import urllib.request


INPUTS = {
    "kernel": {
        "commit": "9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1",
        "tree": "0dab36615babaf7b31c211589639a738f8196cf6",
        "url": "https://codeload.github.com/tem423/android_kernel_lenovo_tb371fc/tar.gz/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1",
        "strip_root": True,
    },
    "snapdragon-clang": {
        "commit": "a16fec82a8deaf8f742ea54f8de98c021af200d4",
        "tree": "34b56bd2317201f6517e9942f0f52917c83b4ac3",
        "url": "https://codeload.github.com/sticpaper/Snapdragon-LLVM-ARM-Compiler-10.0.7-for-Android-NDK/tar.gz/a16fec82a8deaf8f742ea54f8de98c021af200d4",
        "strip_root": True,
        "provenance": "Public third-party import of Qualcomm binaries; not a Qualcomm signature verification.",
    },
    "gcc-aarch64": {
        "commit": "606f80986096476912e04e5c2913685a8f2c3b65",
        "tree": "9959a53ab082bef137916638c48c9871c5d82cfd",
        "url": "https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/+archive/606f80986096476912e04e5c2913685a8f2c3b65.tar.gz",
        "strip_root": False,
        "resolved_tag": "android-11.0.0_r1",
    },
    "gcc-arm": {
        "commit": "b0c6a654327ca8796bed1e61dffcf523d04dceaa",
        "tree": "91c70ff36200356813e0992c39b8b0d47d85aa0b",
        "url": "https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/arm/arm-linux-androideabi-4.9/+archive/b0c6a654327ca8796bed1e61dffcf523d04dceaa.tar.gz",
        "strip_root": False,
        "resolved_tag": "android-11.0.0_r1",
    },
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def safe_unpack(archive: Path, destination: Path, strip_root: bool) -> int:
    """Extract only within a fresh directory, honoring safe relative links."""
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        top = None
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe archive member: {member.name!r}")
            if member.isdev() or member.isfifo():
                raise ValueError("device/FIFO member in source archive")
            if strip_root:
                if not path.parts:
                    continue
                if top is None:
                    top = path.parts[0]
                if path.parts[0] != top:
                    raise ValueError("archive has multiple root directories")
                member.name = str(PurePosixPath(*path.parts[1:]))
                # Hard link names in tar are archive-root relative.
                if member.islnk():
                    link = PurePosixPath(member.linkname)
                    if not link.parts or link.parts[0] != top:
                        raise ValueError("hard link escapes archive root")
                    member.linkname = str(PurePosixPath(*link.parts[1:]))
        selected = [m for m in members if m.name not in {"", "."}]
        tf.extractall(destination, members=selected, filter="data")
    return len(selected)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=Path("/work/first-stage-research"))
    ap.add_argument("--lock", type=Path, help="Require previously captured archive SHA-256 values")
    args = ap.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    cache = work / "downloads"
    cache.mkdir(exist_ok=True)
    lock = json.loads(args.lock.read_text())["inputs"] if args.lock else {}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = work / "sources-acquired.json"
    if target.exists():
        raise SystemExit("sources-acquired.json already exists; do not overwrite a completed acquisition")

    def acquire(item):
        name, spec = item
        archive = cache / (name + "-" + spec["commit"] + ".tar.gz")
        if not archive.exists():
            part = archive.with_name(archive.name + ".partial-" + stamp)
            if part.exists():
                raise RuntimeError("partial download already exists")
            print(f"FETCH {name} {spec['url']}", flush=True)
            req = urllib.request.Request(spec["url"], headers={"User-Agent": "TB371FC-reproducible-entry-study"})
            with urllib.request.urlopen(req, timeout=60) as response, part.open("xb") as out:
                while data := response.read(1024 * 1024):
                    out.write(data)
            part.rename(archive)
        sha = digest(archive)
        if args.lock:
            expected = lock[name]
            if (expected["commit"] != spec["commit"] or expected["url"] != spec["url"]
                    or expected["archive_sha256"] != sha or expected["archive_bytes"] != archive.stat().st_size):
                raise RuntimeError(f"locked source mismatch: {name}")
        destination = work / "public-sources" / name
        count = safe_unpack(archive, destination, spec["strip_root"])
        result = dict(spec, archive=str(archive), archive_bytes=archive.stat().st_size,
                      archive_sha256=sha, extracted=str(destination), members=count)
        print(f"READY {name} {archive.stat().st_size} {sha}", flush=True)
        return name, result

    start = time.monotonic()
    # Two large independent downloads, bounded disk/network pressure.
    with ThreadPoolExecutor(max_workers=2) as ex:
        results = dict(ex.map(acquire, INPUTS.items()))
    record = {"schema": "tb371fc-public-first-stage-sources-v1",
              "captured_utc": datetime.now(timezone.utc).isoformat(),
              "elapsed_seconds": time.monotonic() - start,
              "locked_archives_verified": bool(args.lock), "inputs": results,
              "physical_device_accessed": False,
              "historical_first_stage_reproduction": False}
    target.write_text(json.dumps(record, indent=2) + "\n")
    print(f"MANIFEST {target} {digest(target)}", flush=True)


if __name__ == "__main__":
    main()
