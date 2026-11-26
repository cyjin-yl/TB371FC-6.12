#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Gate an identified Linux second stage in a paused TB371FC QEMU process.

This is a simulated handoff diagnostic. The gate reads the actual QEMU ROM map,
the entire loaded Image and initrd, and the final memory-resident FDT before
issuing `cont`. A layout pass is never a userspace or physical-device pass.
The supplied root image is opened with QEMU's transient snapshot mode.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time

from boot_formats import parse_arm64_image
from native_dt import _parse_tree


MIB = 1 << 20
RAM_BASE = 0x80000000
RAM_END = 0x280000000
BOARD_RAM = [{"start": RAM_BASE, "size": 0x3bb00000},
             {"start": 0xc0000000, "size": 0x1c0000000}]
MAX_DTB = 2 * MIB
MAX_LOG_SCAN = 32 * MIB
QMP_LINE_LIMIT = MIB
QMP_TOTAL_LIMIT = 8 * MIB
ROM_LINE = re.compile(
    r'addr=(?:0x)?([0-9a-fA-F]+) size=0x([0-9a-fA-F]+) '
    r'mem=(ram|rom) name="([^\r\n]*)"')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def record_interrupts():
    """Latch cancellation across Popen assignment and owned-child cleanup."""
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


def identity(raw):
    return {"bytes": len(raw), "sha256": digest(raw)}


def read_ordinary(path, maximum):
    """Read one bounded, non-symlink ordinary file, including empty log files."""
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum,
                "not a bounded ordinary file: " + str(path))
        data = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    require(len(data) == before.st_size and
            all(getattr(before, key) == getattr(after, key) for key in keys),
            "file changed during read: " + str(path))
    return data


def source_identities():
    root = Path(__file__).resolve().parent
    names = ("launch_second_stage.py", "second_stage_layout.py",
             "second_stage_inputs.py", "boot_formats.py", "native_dt.py",
             "qualify_boot_bundle.py", "derive_boot_candidate.py")
    return {name: identity(read_ordinary(root / name, MIB))
            for name in names if (root / name).exists()}


def parse_roms(text):
    require(isinstance(text, str), "QEMU info roms did not return text")
    result = []
    for line in text.splitlines():
        line = line.strip()
        match = ROM_LINE.fullmatch(line)
        if match:
            start, size = int(match[1], 16), int(match[2], 16)
            require(size > 0 and 0 <= start < start + size <= 1 << 64,
                    "invalid QEMU ROM range")
            result.append({"start": start, "size": size,
                           "memory": match[3], "name": match[4]})
        elif line.startswith("addr="):
            raise ValueError("unrecognized physical ROM entry")
    require(result, "no physical ROM entries in actual QEMU")
    return result


def only_rom(entries, name):
    rows = [row for row in entries if row["name"] == name]
    require(len(rows) == 1, "expected exactly one actual ROM entry for " + name)
    return rows[0]


class QMP:
    """Small bounded QMP client; records unsolicited events without losing IDs."""
    def __init__(self, sock):
        self.sock = sock
        self.pending = bytearray()
        self.messages = []
        self.number = 0
        self.received = 0
        self.closed = False

    def receive(self, timeout):
        deadline = time.monotonic() + max(0, timeout)
        while True:
            if b"\n" in self.pending:
                line, _, rest = self.pending.partition(b"\n")
                self.pending = bytearray(rest)
                require(len(line) <= QMP_LINE_LIMIT, "QMP message exceeded bound")
                if not line.strip():
                    continue
                message = json.loads(line)
                require(isinstance(message, dict), "QMP message is not an object")
                self.messages.append(message)
                return message
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self.sock.settimeout(remaining)
            try:
                data = self.sock.recv(65536)
            except socket.timeout:
                return None
            if not data:
                self.closed = True
                raise EOFError("QMP connection closed")
            self.received += len(data)
            require(self.received <= QMP_TOTAL_LIMIT, "QMP transcript exceeded bound")
            self.pending.extend(data)
            require(b"\n" in self.pending or len(self.pending) <= QMP_LINE_LIMIT,
                    "unterminated QMP message exceeded bound")

    def command(self, name, arguments=None, timeout=15):
        self.number += 1
        request_id = "stage2-" + str(self.number)
        payload = {"execute": name, "id": request_id}
        if arguments is not None:
            payload["arguments"] = arguments
        self.sock.settimeout(timeout)
        self.sock.sendall((json.dumps(payload) + "\n").encode())
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = self.receive(deadline - time.monotonic())
            if message is None:
                break
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise ValueError("QMP " + name + " failed: " + str(message["error"]))
            require("return" in message, "QMP response lacks return/error")
            return message["return"]
        raise TimeoutError("QMP " + name + " timed out")

    def close(self):
        self.sock.close()


def open_qmp(path, process, timeout=15):
    deadline = time.monotonic() + timeout
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        while True:
            require(process.poll() is None, "QEMU exited before QMP connected")
            try:
                sock.settimeout(max(.05, deadline - time.monotonic()))
                sock.connect(str(path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("QMP socket did not become available")
                time.sleep(.05)
        qmp = QMP(sock)
        greeting = qmp.receive(max(.05, deadline - time.monotonic()))
        require(isinstance(greeting, dict) and "QMP" in greeting,
                "QMP greeting absent")
        qmp.command("qmp_capabilities")
        return qmp
    except BaseException:
        sock.close()
        raise


def make_command(inputs, out, qmp_path):
    paths = {name: str(path) for name, path in inputs["paths"].items()}
    root = paths["rootfs"]
    require(not any(c in root for c in (",", "\n", "\r", "\0")),
            "rootfs path cannot contain QEMU option delimiters")
    base = inputs["kernel_load_base"]
    require(type(base) is int and RAM_BASE <= base < RAM_END and
            base % (2 * MIB) == 0, "invalid explicit kernel load base")
    return [paths["qemu"], "-M", "tb371fc,kernel-load-base=" + hex(base),
            "-accel", "tcg,thread=multi", "-m", "8G", "-smp", "8",
            "-display", "none", "-monitor", "none", "-nic", "none",
            "-serial", "file:" + str(out / "serial.log"), "-no-reboot",
            "-S", "-qmp", "unix:" + str(qmp_path) + ",server=on,wait=off",
            "-kernel", paths["kernel"], "-initrd", paths["initrd"],
            "-dtb", paths["dtb"], "-append", inputs["bootargs"],
            "-drive", "file=" + root + ",if=none,format=raw,id=stage2-root,snapshot=on",
            "-device", "ufs-lu,bus=ufs0,drive=stage2-root,lun=0"]


def final_bootargs(raw):
    nodes, _ = _parse_tree(raw)
    value = nodes.get("/chosen", {}).get("bootargs")
    require(isinstance(value, bytes) and value.endswith(b"\0") and
            b"\0" not in value[:-1], "final FDT bootargs must be one terminated string")
    return value[:-1].decode("ascii", "strict")


def guest_copy(qmp, row, destination, maximum):
    require(0 < row["size"] <= maximum, "guest payload exceeds bounded copy size")
    qmp.command("pmemsave", {"val": row["start"], "size": row["size"],
                            "filename": str(destination)})
    data = read_ordinary(destination, maximum)
    require(len(data) == row["size"], "QMP memory copy has wrong length")
    return data


def check_paused_layout(inputs, out, qmp, validator):
    status = qmp.command("query-status")
    require(status.get("running") is False, "QEMU must remain paused during layout validation")
    cpus = qmp.command("query-cpus-fast")
    require(isinstance(cpus, list) and len(cpus) == 8, "expected eight simulated CPUs")
    text = qmp.command("human-monitor-command", {"command-line": "info roms"})
    (out / "roms.txt").write_text(text, encoding="utf-8")
    entries = parse_roms(text)
    kernel = only_rom(entries, str(inputs["paths"]["kernel"]))
    initrd = only_rom(entries, str(inputs["paths"]["initrd"]))
    dtb = only_rom(entries, "dtb")
    stub = only_rom(entries, "bootloader")
    raw = inputs["raw"]
    require(kernel["size"] == len(raw["kernel"]), "actual kernel ROM length differs from pinned Image")
    require(initrd["size"] == len(raw["initrd"]), "actual initrd ROM length differs from pinned archive")
    require(0 < dtb["size"] <= MAX_DTB, "final DTB exceeds ARM64 bound")
    base = inputs["kernel_load_base"]
    require(stub["start"] == base and stub["size"] <= 4096,
            "actual boot stub differs from explicit loader base")
    header = parse_arm64_image(raw["kernel"])
    offset = header["text_offset"] + (2 * MIB if header["text_offset"] < 4096 else 0)
    expected_kernel = base + offset
    remaining_ram = RAM_END - base
    expected_initrd = max(base + min(remaining_ram // 2, 128 * MIB),
                          expected_kernel + header["image_size"])
    expected_initrd = (expected_initrd + 4095) & ~4095
    expected_dtb = (expected_initrd + len(raw["initrd"]) + 2 * MIB - 1) & ~(2 * MIB - 1)
    require(kernel["start"] == expected_kernel, "actual Image entry differs from QEMU load contract")
    require(initrd["start"] == expected_initrd, "actual initrd address differs from QEMU load contract")
    require(dtb["start"] == expected_dtb, "actual DTB address differs from QEMU load contract")
    loaded_kernel = guest_copy(qmp, kernel, out / "loaded-kernel.bin", len(raw["kernel"]))
    require(identity(loaded_kernel) == identity(raw["kernel"]),
            "complete loaded Image differs from pinned bytes")
    loaded_initrd = guest_copy(qmp, initrd, out / "loaded-initrd.bin", len(raw["initrd"]))
    require(identity(loaded_initrd) == identity(raw["initrd"]),
            "complete loaded initrd differs from pinned bytes")
    final_dtb = guest_copy(qmp, dtb, out / "final.dtb", MAX_DTB)
    args = final_bootargs(final_dtb)
    require(args == inputs["bootargs"], "final FDT bootargs differ from exact launcher arguments")
    # The requested board aperture is independent of the FDT being checked.
    # Other loaded ROM blobs, including the startup stub, remain exclusions.
    payload_ids = {id(kernel), id(initrd), id(dtb)}
    reserved = [{"start": row["start"], "size": row["size"]}
                for row in entries if id(row) not in payload_ids]
    observed = {"kernel_address": kernel["start"],
                "initramfs_address": initrd["start"], "dtb_address": dtb["start"],
                "ram": [dict(row) for row in BOARD_RAM],
                "loader_reserved": reserved, "bootargs": args}
    layout = validator(raw["kernel"], raw["dtb"], final_dtb,
                       raw["initrd"], raw["config"], observed)
    require(layout.get("status") == "simulated_layout_valid",
            "validator did not establish a simulated layout")
    return {"paused_status": status, "cpu_count": len(cpus),
            "rom_entries": entries, "observed": observed, "header": header,
            "complete_loaded_payloads_verified": True,
            "memory_bytes_read": len(loaded_kernel) + len(loaded_initrd) + len(final_dtb),
            "loaded_kernel": identity(loaded_kernel), "loaded_initrd": identity(loaded_initrd),
            "input_dtb": identity(raw["dtb"]), "final_dtb": identity(final_dtb),
            "validation": layout}


def log_observations(out):
    """Preserve fatal early messages; no banner or exit is a userspace verdict."""
    patterns = {
        "kernel_banner": re.compile(r"^(?:\[[^\]]*\]\s*)?Linux version \d+\.", re.M),
        "panic": re.compile(r"Kernel panic - not syncing|---\[ end Kernel panic"),
        "fatal_exception": re.compile(r"Unable to handle kernel|Internal error:|Oops:"),
        "call_trace": re.compile(r"Call trace:|Call Trace:"),
    }
    observations, fatal = {}, []
    for name in ("serial.log", "qemu-stderr.log", "qemu-stdout.log"):
        path = out / name
        if not path.exists():
            observations[name] = {"present": False}
            continue
        length = path.stat().st_size
        if length > MAX_LOG_SCAN:
            # Keep the complete original file; a bounded scan never certifies
            # its unobserved suffix. The launch stops on this resource bound.
            with path.open("rb") as stream:
                data = stream.read(MAX_LOG_SCAN)
            complete = False
        else:
            data = read_ordinary(path, MAX_LOG_SCAN)
            complete = True
        text = data.decode("utf-8", "replace")
        matches = {key: len(pattern.findall(text)) for key, pattern in patterns.items()}
        observations[name] = {"present": True, "bytes": length,
                              "scanned_bytes": len(data), "scan_complete": complete,
                              "scanned_sha256": digest(data), "matches": matches}
        for line in text.splitlines():
            if any(patterns[key].search(line) for key in ("panic", "fatal_exception", "call_trace")):
                fatal.append({"file": name, "line": line[:2000]})
                if len(fatal) >= 100:
                    break
    return {"logs": observations, "fatal_lines": fatal,
            "fatal_detected": bool(fatal), "userspace_verified": False,
            "boot_completed_verified": False}


def cleanup_child(process, qmp):
    cleanup = {"quit_requested": False, "terminate_sent": False,
               "kill_sent": False, "child_reaped": process is None, "errors": []}
    if process is not None:
        if qmp is not None and process.poll() is None:
            cleanup["quit_requested"] = True
            try:
                qmp.command("quit", timeout=3)
            except (OSError, ValueError, EOFError, TimeoutError):
                # QEMU can close immediately after handling quit.
                pass
        try:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()
                cleanup["terminate_sent"] = True
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    cleanup["kill_sent"] = True
                    process.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired) as error:
            cleanup["errors"].append(str(error))
        cleanup["child_reaped"] = process.poll() is not None
        cleanup["qemu_returncode"] = process.returncode
    if qmp is not None:
        try:
            qmp.close()
        except OSError as error:
            cleanup["errors"].append(str(error))
    return cleanup


def run_prepared(inputs, out, run_seconds=0, *, process_factory=subprocess.Popen,
                 qmp_factory=open_qmp, unchanged=None, validator=None):
    with record_interrupts() as interrupts:
        return _run_prepared(inputs, out, run_seconds, process_factory=process_factory,
                             qmp_factory=qmp_factory, unchanged=unchanged,
                             validator=validator, interrupts=interrupts)


def _run_prepared(inputs, out, run_seconds=0, *, process_factory=subprocess.Popen,
                  qmp_factory=open_qmp, unchanged=None, validator=None, interrupts):
    require(type(run_seconds) is int and 0 <= run_seconds <= 120,
            "run-seconds must be an integer in 0..120")
    out = Path(out)
    # Exclusive creation is deliberate and remains active under python -O.
    out.mkdir(mode=0o700, parents=False, exist_ok=False)
    out = out.resolve(strict=True)
    if unchanged is None:
        from second_stage_inputs import verify_unchanged
        unchanged = verify_unchanged
    if validator is None:
        from second_stage_layout import validate_observed_layout
        validator = validate_observed_layout
    sources = source_identities()
    record = {"schema": "tb371fc-second-stage-qmp-run-v1", "started_utc": utc_now(),
              "status": "failed", "layout_gate_passed": False, "cont_issued": False,
              "run_seconds": run_seconds, "source_identities": sources,
              "inputs": inputs.get("identities", {}), "release": inputs["release"],
              "kernel_bundle_qualification": inputs.get("kernel_bundle_qualification"),
              "evidence_bindings": inputs.get("evidence_bindings"),
              "scope": "Paused simulated load gate and optional bounded board-model observation; no physical entry or userspace acceptance",
              "native_boot_readiness": "blocked", "physical_boot_verified": False,
              "owner_native_linux_passes_added": 0, "rootfs_snapshot_mode": True}
    process = qmp = None
    errors = []
    try:
        with tempfile.TemporaryDirectory(prefix="tb-stage2-", dir="/tmp") as runtime:
            command = make_command(inputs, out, Path(runtime) / "qmp.sock")
            record["command"] = command
            (out / "command.json").write_text(json.dumps(command, indent=2) + "\n")
            unchanged(inputs)
            with (out / "qemu-stdout.log").open("xb") as stdout, (out / "qemu-stderr.log").open("xb") as stderr:
                try:
                    require(interrupts["signal"] is None, "interrupted before QEMU spawn")
                    process = process_factory(command, stdin=subprocess.DEVNULL,
                                              stdout=stdout, stderr=stderr,
                                              start_new_session=True)
                    qmp = qmp_factory(Path(runtime) / "qmp.sock", process, 15)
                    record["qemu_version"] = qmp.command("query-version")
                    record["layout"] = check_paused_layout(inputs, out, qmp, validator)
                    unchanged(inputs)
                    require(source_identities() == sources, "validation source changed before cont")
                    status = qmp.command("query-status")
                    require(status.get("running") is False, "QEMU resumed before gate completed")
                    require(interrupts["signal"] is None, "interrupted before layout gate completed")
                    record["layout_gate_passed"] = True
                    record["stop_reason"] = "paused_layout_only"
                    if run_seconds:
                        # This is the sole continuation point, after every gate.
                        record["cont_issued"] = True
                        qmp.command("cont")
                        deadline = time.monotonic() + run_seconds
                        record["stop_reason"] = "observation_deadline"
                        while process.poll() is None:
                            if interrupts["signal"] is not None:
                                record["stop_reason"] = "interrupted"
                                break
                            remaining = deadline - time.monotonic()
                            if remaining <= 0:
                                break
                            try:
                                qmp.receive(min(.2, remaining))
                            except EOFError:
                                process.wait(timeout=3)
                                break
                            if any((out / name).exists() and (out / name).stat().st_size > MAX_LOG_SCAN
                                   for name in ("serial.log", "qemu-stderr.log", "qemu-stdout.log")):
                                record["stop_reason"] = "log_scan_bound_exceeded"
                                errors.append("guest output exceeded bounded observation scan")
                                break
                        if process.poll() is not None:
                            record["stop_reason"] = "qemu_exited_during_observation"
                            if process.returncode != 0:
                                errors.append("QEMU exited nonzero during observation")
                    record["status"] = "simulated_layout_verified"
                finally:
                    record["cleanup"] = cleanup_child(process, qmp)
                    if qmp is not None:
                        record["qmp_messages"] = qmp.messages
                    process = qmp = None
    except (Exception, KeyboardInterrupt) as error:
        errors.append(type(error).__name__ + ": " + str(error))
    finally:
        # This also handles failures before the inner ownership scope existed.
        if process is not None or qmp is not None:
            record["cleanup"] = cleanup_child(process, qmp)
            if qmp is not None:
                record["qmp_messages"] = qmp.messages
        try:
            unchanged(inputs)
            require(source_identities() == sources, "validation source changed during observation")
            record["inputs_unchanged_after"] = True
        except Exception as error:
            errors.append("post-run stability: " + str(error))
            record["inputs_unchanged_after"] = False
        try:
            record["runtime_observation"] = log_observations(out)
        except Exception as error:
            errors.append("log observation: " + str(error))
        cleanup = record.get("cleanup", {})
        if cleanup and (not cleanup.get("child_reaped") or cleanup.get("errors")):
            errors.append("owned QEMU cleanup incomplete")
        if record["layout_gate_passed"] and cleanup.get("qemu_returncode") != 0:
            # A successful paused gate does not erase a later QEMU failure.
            # Forced cleanup remains explicit and also cannot certify normal
            # controller completion; the validated layout record is retained.
            errors.append("QEMU did not exit normally after the verified layout")
        record["interrupted_signal"] = interrupts["signal"]
        if interrupts["signal"] is not None:
            errors.append("execution interrupted")
        record["controller_errors"] = errors
        if errors:
            record["status"] = "failed"
        record["completed_utc"] = utc_now()
        record["userspace_verified"] = False
        record["boot_completed_verified"] = False
        fatal = record.get("runtime_observation", {}).get("fatal_detected", False)
        record["exit_code"] = 1 if errors or not record["layout_gate_passed"] else 3 if fatal else 0
        record["exit_scope"] = "0 verifies the simulated layout and controller only; 3 preserves an observed kernel failure; neither is a boot pass"
        (out / "result.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--run-seconds", type=int, default=0)
    args = parser.parse_args(argv)
    if not 0 <= args.run_seconds <= 120:
        parser.error("--run-seconds must be 0..120")
    try:
        from second_stage_inputs import verify_inputs
        inputs = verify_inputs(args.manifest)
        result = run_prepared(inputs, args.out, args.run_seconds)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "preflight_failed", "error": str(error),
                          "physical_boot_verified": False}), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "layout_gate_passed": result["layout_gate_passed"],
                      "cont_issued": result["cont_issued"], "exit_code": result["exit_code"],
                      "result": str(args.out / "result.json"),
                      "controller_errors": result["controller_errors"],
                      "userspace_verified": False, "physical_boot_verified": False}))
    return result["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
