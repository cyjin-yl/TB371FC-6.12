#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Boot a research Image on generic QEMU virt and verify ARM64 PID 1 execution.

This does not use the TB371FC DTB, a physical device, firmware or networking.
The only init is a freestanding static ELF that prints uname and a marker.
After that marker the controller terminates only the QEMU child it created.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import gzip
import hashlib
import json
import os
from pathlib import Path
import selectors
import shlex
import signal
import subprocess
import time


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(entries):
    data = bytearray()
    for index, (name, mode, payload, major, minor) in enumerate(entries, 1):
        name = name.encode() + b"\0"
        fields = [index, mode, 0, 0, 1, 1795392000, len(payload),
                  0, 0, major, minor, len(name), 0]
        data.extend(b"070701" + b"".join(f"{value:08x}".encode() for value in fields))
        data.extend(name)
        data.extend(b"\0" * (-len(data) % 4))
        data.extend(payload)
        data.extend(b"\0" * (-len(data) % 4))
    data.extend(b"\0" * (-len(data) % 512))
    return bytes(data)


def observed_lines(serial, release):
    """Match complete console lines, including the final newline, exactly."""
    lines = {line.removesuffix(b"\r") for line in bytes(serial).split(b"\n")[:-1]}
    return {
        "release": ("TB371FC_QEMU_RELEASE=" + release).encode() in lines,
        "machine": b"TB371FC_QEMU_MACHINE=aarch64" in lines,
        "el0_marker": b"TB371FC_QEMU_EL0_READY" in lines,
        "guest_error": b"TB371FC_QEMU_EL0_ERROR" in lines,
    }


@contextmanager
def record_interrupts():
    """Latch cancellation without raising inside Popen's ownership handoff.

    Keep this active until the result/log have been written. Repeated signals
    cannot interrupt child cleanup. The child inherits neither a blocked
    signal mask nor a Python exception handler across exec.
    """
    state = {"signal": None}
    previous = {}

    def handler(signum, _frame):
        if state["signal"] is None:
            state["signal"] = signum

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, handler)
        yield state
    finally:
        for signum, old_handler in previous.items():
            signal.signal(signum, old_handler)


def capture_child(command, release, timeout, interrupts, output_limit=4 * 1024 * 1024):
    """Run one owned child, retain bounded output, and always attempt to reap it."""
    process = None
    selector = None
    serial = bytearray()
    reason = "timeout"
    error = None
    output_lost = False
    cleanup = {"terminate_sent": False, "kill_sent": False, "child_reaped": False, "errors": []}
    started = time.monotonic()

    def append(chunk):
        nonlocal output_lost
        remaining = max(0, output_limit - len(serial))
        serial.extend(chunk[:remaining])
        if len(chunk) > remaining:
            output_lost = True

    try:
        # Cancellation is a flag, so a signal between creation and assignment
        # cannot throw away the returned Popen object and orphan the child.
        if interrupts["signal"] is not None:
            reason = "interrupted_before_spawn"
        else:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() - started < timeout:
                if interrupts["signal"] is not None:
                    reason = "interrupted"
                    break
                for key, _ in selector.select(0.25):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if chunk:
                        append(chunk)
                    else:
                        selector.unregister(key.fileobj)
                if output_lost:
                    reason = "serial_output_limit"
                    break
                lines = observed_lines(serial, release)
                if lines["el0_marker"]:
                    reason = "observed_el0_marker"
                    break
                if lines["guest_error"]:
                    reason = "guest_uname_failed"
                    break
                if process.poll() is not None:
                    reason = "qemu_exited_before_marker"
                    break
    except Exception as exc:
        reason = "controller_exception"
        error = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        # The selector and its registration may themselves have failed. Child
        # ownership and cleanup do not depend on either being initialized.
        if process is not None:
            if process.poll() is None:
                try:
                    process.send_signal(signal.SIGTERM)
                    cleanup["terminate_sent"] = True
                except ProcessLookupError:
                    pass
                except OSError as exc:
                    cleanup["errors"].append(type(exc).__name__ + ": " + str(exc))
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    cleanup["kill_sent"] = True
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    cleanup["errors"].append(type(exc).__name__ + ": " + str(exc))
            cleanup["child_reaped"] = process.poll() is not None
            # Reap first, then drain only currently available pipe bytes. This
            # cannot turn a 4 MiB cap into an unbounded communicate() allocation,
            # or wait for EOF from an unexpected inherited pipe writer.
            if process.stdout is not None:
                try:
                    os.set_blocking(process.stdout.fileno(), False)
                    while True:
                        try:
                            chunk = os.read(process.stdout.fileno(), 65536)
                        except BlockingIOError:
                            break
                        if not chunk:
                            break
                        append(chunk)
                        if output_lost:
                            break
                except OSError as exc:
                    cleanup["errors"].append(type(exc).__name__ + ": " + str(exc))
                finally:
                    process.stdout.close()
        if selector is not None:
            selector.close()

    lines = observed_lines(serial, release)
    if interrupts["signal"] is not None:
        reason = "interrupted" if process is not None else "interrupted_before_spawn"
    elif output_lost:
        reason = "serial_output_limit"
    elif reason == "qemu_exited_before_marker" and lines["el0_marker"]:
        reason = "observed_el0_marker"
    success = (reason == "observed_el0_marker" and all(lines[name] for name in ("release", "machine", "el0_marker"))
               and not lines["guest_error"] and cleanup["child_reaped"] and not cleanup["errors"])
    result = {"controller_result": "pass" if success else "fail", "stop_reason": reason,
              "qemu_returncode": process.returncode if process is not None else None,
              "elapsed_seconds": time.monotonic() - started, "interrupted_signal": interrupts["signal"],
              "serial_output_truncated": output_lost, "observed_lines": lines, "cleanup": cleanup}
    if error:
        result["controller_error"] = error
    return bytes(serial), result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=Path("/work/artifacts/Image"))
    parser.add_argument("--release", type=Path, default=Path("/work/artifacts/kernel.release"))
    parser.add_argument("--output", type=Path, default=Path("/work/qemu-kernel-smoke"))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if not 10 <= args.timeout <= 300:
        parser.error("timeout must be 10..300 seconds")
    image = args.image.resolve(strict=True)
    release = args.release.read_text().strip()
    if release != "6.12.114-tb371fc-research1":
        parser.error("this probe expects the explicit research1 ABI")
    if args.output.exists() or args.output.is_symlink():
        parser.error("output already exists; retain it and choose another directory")
    args.output.mkdir(parents=True)
    output = args.output.resolve()
    source = Path(__file__).with_name("qemu-init.c").resolve()
    elf = output / "init.elf"
    compiler = ["clang", "--target=aarch64-linux-gnu", "-fuse-ld=lld", "-Oz",
                "-ffreestanding", "-fno-stack-protector", "-nostdlib", "-static",
                "-Wl,-e,_start", "-Wl,--build-id=none", "-o", str(elf), str(source)]
    print("+", shlex.join(compiler), flush=True)
    subprocess.run(compiler, check=True)
    blob = elf.read_bytes()
    if blob[:6] != b"\x7fELF\x02\x01" or int.from_bytes(blob[18:20], "little") != 183:
        raise SystemExit("probe is not a little-endian ELF64 AArch64 executable")
    initrd = output / "initramfs.cpio.gz"
    entries = [("dev", 0o040755, b"", 0, 0),
               ("dev/console", 0o020600, b"", 5, 1),
               ("init", 0o100755, blob, 0, 0),
               ("TRAILER!!!", 0, b"", 0, 0)]
    initrd.write_bytes(gzip.compress(archive(entries), mtime=0))
    command = ["qemu-system-aarch64", "-machine", "virt", "-accel", "tcg",
               "-cpu", "max", "-smp", "2", "-m", "1024", "-nographic",
               "-monitor", "none", "-nic", "none", "-no-reboot",
               "-kernel", str(image), "-initrd", str(initrd),
               "-append", "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init loglevel=7 panic=1"]
    print("+", shlex.join(command), flush=True)
    record = {"scope": "generic QEMU virt only; no tablet DT or hardware acceptance",
              "command": command, "compiler_command": compiler,
              "image_sha256": sha(image), "init_source_sha256": sha(source),
              "init_elf_sha256": sha(elf), "initramfs_sha256": sha(initrd),
              "expected_release": release, "timeout_seconds": args.timeout}
    with record_interrupts() as interrupts:
        serial, observation = capture_child(command, release, args.timeout, interrupts)
        log = output / "serial.log"
        log.write_bytes(serial)
        record.update(observation)
        # A cancellation during artifact writing still prevents a pass.
        if interrupts["signal"] is not None:
            record.update(controller_result="fail", stop_reason="interrupted",
                          interrupted_signal=interrupts["signal"])
        record.update(serial_sha256=sha(log), physical_hardware_tested=False)
        result_path = output / "result.json"
        result_path.write_text(json.dumps(record, indent=2) + "\n")
        if interrupts["signal"] is not None and record["controller_result"] == "pass":
            record.update(controller_result="fail", stop_reason="interrupted",
                          interrupted_signal=interrupts["signal"])
            result_path.write_text(json.dumps(record, indent=2) + "\n")
    text = serial.decode("utf-8", "replace")
    print(text[-6000:], flush=True)
    print(json.dumps(record, indent=2), flush=True)
    raise SystemExit(0 if record["controller_result"] == "pass" else 1)


if __name__ == "__main__":
    main()
