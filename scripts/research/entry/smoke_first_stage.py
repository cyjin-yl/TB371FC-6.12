#!/usr/bin/env python3
"""Boot the built entry Image + real rescue initramfs on generic QEMU virt.

No tablet DT, device firmware, networking, physical USB or kexec execution.
Reuse the reviewed bounded child controller without changing its source.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    kernels = ap.add_mutually_exclusive_group(required=True)
    kernels.add_argument("--kernel-manifest", type=Path)
    kernels.add_argument("--reference-research2", type=Path,
                         help="Check only the rescue userspace using the frozen research2 artifacts directory")
    ap.add_argument("--userspace-manifest", required=True, type=Path)
    ap.add_argument("--controller", type=Path, default=Path("/src/scripts/research/build/smoke_qemu.py"))
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--cpu", choices=["cortex-a76", "max"], default="cortex-a76",
                    help="Use a fixed Armv8.2 CPU model for this 4.19 kernel; max is a separate qualification")
    args = ap.parse_args()
    if not 15 <= args.timeout <= 300:
        ap.error("timeout must be 15..300 seconds")
    userspace_meta = args.userspace_manifest.resolve(strict=True)
    userspace = json.loads(userspace_meta.read_text())
    if userspace.get("completed") is not True:
        raise SystemExit("require a completed userspace build")
    downstream = args.kernel_manifest is not None
    if downstream:
        kernel_meta = args.kernel_manifest.resolve(strict=True)
        kernel = json.loads(kernel_meta.read_text())
        if kernel.get("schema") != "tb371fc-downstream-entry-build-v1" or kernel.get("build_completed") is not True:
            raise SystemExit("require the completed downstream entry build manifest")
        image = kernel_meta.parent / "artifacts/Image"
        expected_image = kernel["artifacts"]["Image"]["sha256"]
        release = kernel["release"]
    else:
        artifacts = args.reference_research2.resolve(strict=True)
        kernel_meta = artifacts / "source-manifest.json"
        image = artifacts / "Image"
        expected_image = "181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d"
        release = (artifacts / "kernel.release").read_text().strip()
        if (release != "6.12.114-tb371fc-research2-display"
                or sha(kernel_meta) != "845914d9cc1c876f10704f3334ee942b2c26deaa8045ce9c2ef82ef2920cde21"
                or sha(artifacts / "kernel.config") != "e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8"):
            raise SystemExit("reference research2 input differs from the frozen qualification")
    initrd = userspace_meta.parent / "artifacts/entry-initramfs.cpio.gz"
    if sha(image) != expected_image:
        raise SystemExit("Image checksum mismatch")
    if sha(initrd) != userspace["artifacts"][initrd.name]["sha256"]:
        raise SystemExit("initramfs checksum mismatch")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    helper = args.controller.resolve(strict=True)
    spec = importlib.util.spec_from_file_location("tb371fc_reviewed_qemu_controller", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command = ["qemu-system-aarch64", "-machine", "virt", "-accel", "tcg", "-cpu", args.cpu,
               "-smp", "2", "-m", "1024", "-nographic", "-monitor", "none", "-nic", "none",
               "-no-reboot", "-kernel", str(image), "-initrd", str(initrd),
               "-append", "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init loglevel=7 panic=1 tb371fc.entry_smoke=1"]
    record = {"schema": "tb371fc-new-entry-qemu-v1", "started_utc": datetime.now(timezone.utc).isoformat(),
              "scope": ("downstream entry Image and rescue initramfs on generic QEMU virt" if downstream else
                        "rescue userspace only on the frozen research2 reference kernel; NOT a downstream entry-kernel pass"),
              "downstream_entry_kernel_used": downstream,
              "command": command, "image_sha256": sha(image), "initramfs_sha256": sha(initrd),
              "kernel_manifest_sha256": sha(kernel_meta), "userspace_manifest_sha256": sha(userspace_meta),
              "script_sha256": sha(Path(__file__).resolve()),
              "controller_sha256": sha(helper), "expected_release": release,
              "qemu_version": subprocess.check_output(["qemu-system-aarch64", "--version"], text=True).splitlines()[0],
              "tablet_tested": False, "bootloader_acceptance_tested": False,
              "kexec_load_or_execute_tested": False, "recovery_return_tested": False,
              "tablet_usb_tested": False, "tablet_dt_used": False}
    print(json.dumps({"command": command, "expected_release": release, "scope": record["scope"]}), flush=True)
    with module.record_interrupts() as interrupts:
        serial, result = module.capture_child(command, release, args.timeout, interrupts)
        lines = {line.rstrip(b"\r") for line in serial.split(b"\n")[:-1]}
        record.update(result)
        record["entry_ready_observed"] = b"TB371FC_ENTRY_SMOKE_READY" in lines
        record["kexec_loaded_zero_observed"] = b"TB371FC_ENTRY_KEXEC_LOADED=0" in lines
        record["busybox_sha_observed"] = (userspace["artifacts"]["busybox"]["sha256"].encode()
                                           + b"  /bin/busybox") in lines
        record["kexec_sha_observed"] = (userspace["artifacts"]["kexec"]["sha256"].encode()
                                         + b"  /bin/kexec") in lines
        required = ["entry_ready_observed", "busybox_sha_observed", "kexec_sha_observed"]
        if downstream:
            required.append("kexec_loaded_zero_observed")
        record["kexec_loaded_zero_required"] = downstream
        if not all(record[k] for k in required):
            record["controller_result"] = "fail"
        if interrupts["signal"] is not None:
            record.update(controller_result="fail", stop_reason="interrupted", interrupted_signal=interrupts["signal"])
        (output / "serial.log").write_bytes(serial)
        record["serial_sha256"] = sha(output / "serial.log")
        record["ended_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        if interrupts["signal"] is not None and record["controller_result"] == "pass":
            record.update(controller_result="fail", stop_reason="interrupted", interrupted_signal=interrupts["signal"])
            (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    print(serial.decode("utf-8", "replace")[-9000:], flush=True)
    print(json.dumps(record, indent=2), flush=True)
    raise SystemExit(0 if record["controller_result"] == "pass" else 1)


if __name__ == "__main__":
    main()
