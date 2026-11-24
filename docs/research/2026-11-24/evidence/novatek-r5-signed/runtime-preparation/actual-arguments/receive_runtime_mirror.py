#!/usr/bin/env python3
"""Receive the exact canonical Fedora runtime on SSD, then preserve its metadata.

Preparation only: the original target gate must still qualify the extracted
root. No program from the received root is executed. Failed work is retained.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import select
import shutil
import signal
import stat
import subprocess
import sys
import time

EXPECTED_BYTES = 1323141120
EXPECTED_SHA256 = "1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96"
MIN_FREE_BYTES = 6 * 1024 ** 3
DEFAULT_WORK = Path("/work/r5-novatek-runtime-mirror-c1296-01")
CHUNK_BYTES = 1024 * 1024


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def atomic_json(path, value):
    temporary = path.with_name("." + path.name + "." + str(os.getpid()) + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def file_identity(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(CHUNK_BYTES):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def interrupted(number, unused_frame):
    raise InterruptedError("received signal " + str(number))


def receive(work, receive_timeout, extract_timeout):
    require(work.parent == Path("/work") and
            work.name.startswith("r5-novatek-runtime-mirror-c1296-"),
            "new /work/r5-novatek-runtime-mirror-c1296-* directory required")
    require(not work.exists() and not work.is_symlink(), "retain existing work; choose a new directory")
    require(stat.S_ISDIR(work.parent.lstat().st_mode), "ordinary /work parent required")
    require(os.geteuid() == 0, "root is required to preserve numeric ownership")
    require(1 <= receive_timeout <= 7200 and 1 <= extract_timeout <= 3600,
            "timeout outside the bounded preparation budget")
    free = shutil.disk_usage(work.parent).free
    require(free >= MIN_FREE_BYTES, "at least 6 GiB free is required before receiving")
    tar = shutil.which("tar")
    require(tar is not None, "GNU tar is required")
    version = subprocess.run([tar, "--version"], capture_output=True, text=True,
                             check=True, timeout=10).stdout.strip()
    require("GNU tar" in version, "GNU tar metadata options are required")
    work.mkdir(mode=0o700)
    report = {"schema": "tb371fc-fedora-runtime-mirror-preparation-v1",
              "started_utc": utc(), "complete": False, "phase": "receive",
              "work_directory": str(work), "expected_bytes": EXPECTED_BYTES,
              "expected_sha256": EXPECTED_SHA256, "minimum_free_bytes": MIN_FREE_BYTES,
              "free_bytes_before": free, "receive_timeout_seconds": receive_timeout,
              "extract_timeout_seconds": extract_timeout, "tar_version": version,
              "receiver_source": file_identity(Path(__file__)),
              "archive_identity_verified": False, "extracted_tree_canonical_verified": False,
              "target_gate_executed": False, "program_from_rootfs_executed": False,
              "physical_hardware_tested": False, "module_loaded": False,
              "received_bytes": 0, "saved_bytes": 0}
    receipt = work / "receipt.json"
    atomic_json(receipt, report)
    digest = hashlib.sha256()
    started = time.monotonic()
    deadline = started + receive_timeout
    previous_progress = 0.0
    archive = work / "runtime.canonical.tar"
    fd = sys.stdin.fileno()
    previous_blocking = os.get_blocking(fd)
    os.set_blocking(fd, False)

    def progress(force=False):
        nonlocal previous_progress
        current = time.monotonic()
        if force or current - previous_progress >= 5:
            atomic_json(work / "progress.json", {
                "utc": utc(), "phase": report["phase"], "complete": report["complete"],
                "elapsed_seconds": current - started,
                "received_bytes": report["received_bytes"], "saved_bytes": report["saved_bytes"],
                "expected_bytes": EXPECTED_BYTES, "sha256_so_far": digest.hexdigest()})
            previous_progress = current

    try:
        with archive.open("xb", buffering=CHUNK_BYTES) as output:
            archive.chmod(0o600)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("canonical input did not finish within receive deadline")
                progress()
                ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
                if not ready:
                    continue
                try:
                    # Read at most one byte beyond the hard bound, and never
                    # save that excess byte or proceed to extraction.
                    block = os.read(fd, min(CHUNK_BYTES, EXPECTED_BYTES - report["saved_bytes"] + 1))
                except BlockingIOError:
                    continue
                if not block:
                    break
                report["received_bytes"] += len(block)
                if report["received_bytes"] > EXPECTED_BYTES:
                    raise ValueError("canonical input exceeds the exact byte bound")
                output.write(block)
                digest.update(block)
                report["saved_bytes"] += len(block)
            output.flush()
            os.fsync(output.fileno())
        report["receive_finished_utc"] = utc()
        report["archive"] = {"path": archive.name, "bytes": report["saved_bytes"],
                             "sha256": digest.hexdigest()}
        require(report["saved_bytes"] == EXPECTED_BYTES and
                archive.stat().st_size == EXPECTED_BYTES and digest.hexdigest() == EXPECTED_SHA256,
                "canonical archive byte count or SHA-256 differs from the frozen runtime")
        report["archive_identity_verified"] = True
        report["phase"] = "extract"
        report["free_bytes_before_extract"] = shutil.disk_usage(work).free
        atomic_json(receipt, report)
        progress(force=True)
        root = work / "rootfs"
        root.mkdir(mode=0o700)
        command = [tar, "--extract", "--file", str(archive), "--directory", str(root),
                   "--numeric-owner", "--same-owner", "--same-permissions",
                   "--acls", "--selinux", "--xattrs", "--xattrs-include=*",
                   "--delay-directory-restore"]
        report["extract"] = {"argv": command, "started_utc": utc(),
                             "timeout_seconds": extract_timeout}
        atomic_json(receipt, report)
        try:
            with (work / "extract.stdout").open("xb") as out, \
                 (work / "extract.stderr").open("xb") as err:
                result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=out,
                                        stderr=err, timeout=extract_timeout, check=False)
            report["extract"]["exit_code"] = result.returncode
            require(result.returncode == 0, "metadata-preserving extraction failed")
            require((work / "extract.stderr").stat().st_size == 0,
                    "extraction emitted diagnostics; inspect before qualifying the mirror")
        finally:
            report["extract"]["finished_utc"] = utc()
            for name in ("extract.stdout", "extract.stderr"):
                if (work / name).is_file():
                    report["extract"][name] = file_identity(work / name)
        report.update(complete=True, phase="verified_archive_extracted",
                      rootfs=str(root), free_bytes_after=shutil.disk_usage(work).free)
    except BaseException as exc:
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        os.set_blocking(fd, previous_blocking)
        report["finished_utc"] = utc()
        report["elapsed_seconds"] = time.monotonic() - started
        if archive.exists():
            report["archive_file_bytes_at_finish"] = archive.stat().st_size
        atomic_json(receipt, report)
        progress(force=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=DEFAULT_WORK)
    parser.add_argument("--receive-timeout", type=int, default=3600)
    parser.add_argument("--extract-timeout", type=int, default=1800)
    args = parser.parse_args()
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, interrupted)
    result = receive(args.work, args.receive_timeout, args.extract_timeout)
    print(json.dumps({"complete": result["complete"], "archive": result["archive"],
                      "rootfs": result["rootfs"], "target_gate_executed": False}))


if __name__ == "__main__":
    main()
