#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the research2-display Image on generic QEMU virt, never the tablet DT.

Reuses the frozen controller's bounded capture, exact marker parsing and child
cleanup. The original research1 command-line defaults and evidence are untouched.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import shlex
import subprocess

import prepare_research2_display as profile
import smoke_qemu as controller


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--work", type=Path, default=Path("/work/research2-display"))
    parser.add_argument("--output", type=Path, help="new output directory; default WORK/qemu-smoke")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 300:
        parser.error("timeout must be 10..300 seconds")
    repo, work = args.repo.resolve(), args.work.resolve()
    profile.verify_work(repo, work)
    if profile.digest(Path(controller.__file__)) != profile.FROZEN_HELPERS["scripts/research/build/smoke_qemu.py"]:
        raise SystemExit("imported QEMU controller differs from the frozen helper")
    artifacts = work / "artifacts"
    image = artifacts / "Image"
    release = (artifacts / "kernel.release").read_text().strip()
    if release != profile.RELEASE:
        raise SystemExit("unexpected candidate release")
    output = args.output.resolve() if args.output else work / "qemu-smoke"
    if output.exists() or output.is_symlink():
        raise SystemExit("retain previous VM evidence; choose a new output directory")
    output.mkdir(parents=True)
    source = repo / "scripts/research/build/qemu-init.c"
    elf = output / "init.elf"
    compiler = ["clang", "--target=aarch64-linux-gnu", "-fuse-ld=lld", "-Oz",
                "-ffreestanding", "-fno-stack-protector", "-nostdlib", "-static",
                "-Wl,-e,_start", "-Wl,--build-id=none", "-o", str(elf), str(source)]
    print("+", shlex.join(compiler), flush=True)
    subprocess.run(compiler, check=True)
    blob = elf.read_bytes()
    if blob[:6] != b"\x7fELF\x02\x01" or int.from_bytes(blob[18:20], "little") != 183:
        raise SystemExit("probe is not little-endian ELF64 AArch64")
    entries = [("dev", 0o040755, b"", 0, 0), ("dev/console", 0o020600, b"", 5, 1),
               ("init", 0o100755, blob, 0, 0), ("TRAILER!!!", 0, b"", 0, 0)]
    initrd = output / "initramfs.cpio.gz"
    initrd.write_bytes(gzip.compress(controller.archive(entries), mtime=0))
    command = ["qemu-system-aarch64", "-machine", "virt", "-accel", "tcg", "-cpu", "max",
               "-smp", "2", "-m", "1024", "-nographic", "-monitor", "none", "-nic", "none",
               "-no-reboot", "-kernel", str(image), "-initrd", str(initrd),
               "-append", "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init loglevel=7 panic=1"]
    print("+", shlex.join(command), flush=True)
    record = {"schema_version": 1, "profile": "research2-display",
              "scope": "generic QEMU virt using its machine DT; native TB371FC display DT is not passed",
              "command": command, "compiler_command": compiler, "expected_release": release,
              "image_sha256": profile.digest(image), "init_source_sha256": profile.digest(source),
              "init_elf_sha256": profile.digest(elf), "initramfs_sha256": profile.digest(initrd),
              "controller_sha256": profile.digest(Path(controller.__file__)),
              "profile_launcher_sha256": profile.digest(Path(__file__)),
              "source_manifest_sha256": profile.digest(artifacts / "source-manifest.json"),
              "timeout_seconds": args.timeout, "native_display_tested": False,
              "physical_hardware_tested": False}
    with controller.record_interrupts() as interrupts:
        serial, observation = controller.capture_child(command, release, args.timeout, interrupts)
        log = output / "serial.log"
        log.write_bytes(serial)
        record.update(observation)
        if interrupts["signal"] is not None:
            record.update(controller_result="fail", stop_reason="interrupted", interrupted_signal=interrupts["signal"])
        record["serial_sha256"] = profile.digest(log)
        result = output / "result.json"
        result.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        if interrupts["signal"] is not None and record["controller_result"] == "pass":
            record.update(controller_result="fail", stop_reason="interrupted", interrupted_signal=interrupts["signal"])
            result.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(serial.decode("utf-8", "replace")[-6000:], flush=True)
    print(json.dumps(record, indent=2), flush=True)
    return 0 if record["controller_result"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
