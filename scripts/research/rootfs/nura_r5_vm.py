#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare and boot an independent Nura R5 direct-root generic ARM64 VM.

The source stage and prepared image remain unchanged. Each run receives its
own ordinary-file disk. This does not build or qualify a tablet root loader.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import time

import stage_r5_fedora as common
import stage_r5_nura as nura
from r5_system_common import create_ext4

HERE = Path(__file__).resolve().parent
LABEL = "tb371fc-nura-r5"
PROFILE = "usr/share/tb371fc/nura-r5-vm.json"
GUEST = "usr/libexec/tb371fc-nura-r5-vm.py"
SERVICE = "etc/init.d/tb371fc-nura-r5-vm"
RESULT = "var/lib/tb371fc/nura-r5-vm-result.json"
SCOPE = {"root_loader_built": False, "physical_hardware_tested": False,
         "owner_native_linux_passes_added": 0, "board_dtb_used": False,
         "network": False, "scope": "generic ARM64 direct-root core boot only"}
SERVICE_TEXT = '''#!/sbin/openrc-run
description="Observe the isolated Nura R5 virtual machine"
command="/usr/bin/python3"
command_args="/usr/libexec/tb371fc-nura-r5-vm.py"
command_background="yes"
pidfile="/run/tb371fc-nura-r5-vm.pid"
output_log="/dev/console"
error_log="/dev/console"
depend() {
    after "*"
}
'''


def require(condition, message):
    if not condition:
        raise ValueError(message)


def owned_directory(path, prefix):
    require(path.parent == Path("/work") and
            re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", path.name),
            "dedicated /work/" + prefix + "* required")
    common.ordinary_dir(path.parent)
    common.ordinary_dir(path)


def checked(path, expected):
    require(common.identity(path) == expected, "identity differs: " + str(path))


def qualify_stage(repo, stage):
    owned_directory(stage, "nura-r5-stage-")
    root = stage / "rootfs"
    common.ordinary_dir(root)
    receipt_path = stage / "nura-r5-stage.json"
    receipt_identity = common.identity(receipt_path)
    record = json.loads(receipt_path.read_text())
    require(record.get("complete") is True and record.get("kernel_release") == common.RELEASE
            and record.get("owner_native_linux_passes_added") == 0,
            "successful unchanged R5 Nura stage required")
    for key, path in (("source", Path(nura.__file__)), ("common_source", Path(common.__file__)),
                      ("candidate", repo / "docs/research/2026-11-23/boot-candidate-r5.json"),
                      ("qualifier", repo / "scripts/research/qualify_boot_bundle.py")):
        checked(path, record[key])
    inventory_file = repo / nura.INVENTORY
    common.check(inventory_file, nura.INVENTORY_PIN)
    require((record["archive"]["sha256"], record["archive"]["bytes"]) == nura.ARCHIVE_PIN,
            "stage is not derived from the retained Nura archive")
    checked(stage / "source.tar.gz", record["archive"])
    inventory = json.loads(inventory_file.read_text())
    nura.verify_inventory(root, inventory, staged=True)
    contract = json.loads((repo / "docs/research/2026-11-23/boot-candidate-r5.json").read_text())
    selected = common.selected_modules(contract)
    require(all(record["module_tree"].get(name) == value for name, value in selected.items()),
            "stage module identities differ from the frozen candidate")
    require({name for name in record["module_tree"] if name.endswith(".ko")} ==
            {name for name in selected if name.endswith(".ko")}, "stage module set differs")
    checked(stage / "root-module-report.json", record["root_module_report"])
    report = json.loads((stage / "root-module-report.json").read_text())["root_module_tree"]
    require(report["passed"] and report["input_snapshot_stable"], "stage module gate failed")
    files = {}
    for name, expected in record["module_tree"].items():
        path = "usr/lib/modules/" + common.RELEASE + "/" + common.relative(name).as_posix()
        checked(common.under(root, path), expected)
        files[path] = expected
    for name, expected in record["firmware"].items():
        path = "usr/" + common.relative(name).as_posix()
        wanted = {key: expected[key] for key in ("bytes", "mode", "sha256")}
        checked(common.under(root, path), wanted)
        files[path] = wanted
    require(len(record["firmware"]) == 69, "69 staged firmware files required")
    for name, expected in record["kernel_payload"].items():
        checked(common.under(stage / "r5-kernel", name), expected)
    for entry in contract["kernel_files"]:
        if entry["path"].startswith("artifacts/"):
            require(record["kernel_payload"].get(entry["path"]) ==
                    {key: entry[key] for key in ("bytes", "mode", "sha256")},
                    "stage kernel artifact differs from the frozen candidate")
    require(record["firmware_manifest"]["sha256"] == common.FW_PIN, "firmware manifest differs")
    for name, expected in record["depmod_receipts"].items():
        checked(common.under(stage, name), expected)
    checked(receipt_path, receipt_identity)
    return record, receipt_identity, inventory, files


def write_new(root, name, value, mode=0o644):
    path = common.under(root, name, mkdir=True)
    with path.open("x") as stream:
        stream.write(value)
    path.chmod(mode)
    return common.identity(path)


def prepare(repo, stage, work, size_bytes):
    require(os.geteuid() == 0, "root is required to preserve the copied root's metadata")
    require(work.parent == Path("/work") and
            re.fullmatch(r"nura-r5-vm-[A-Za-z0-9][A-Za-z0-9._-]{0,80}", work.name),
            "new dedicated /work/nura-r5-vm-* required")
    common.ordinary_dir(work.parent)
    work.mkdir(mode=0o700)
    record = {"schema_version": 1, **SCOPE, "started_utc": common.now(),
              "complete": False, "target_booted": False, "source_stage": str(stage)}
    try:
        record["host_source"] = common.identity(Path(__file__))
        record["guest_source"] = common.identity(HERE / "nura_r5_guest.py")
        staged, receipt, inventory, files = qualify_stage(repo, stage)
        record["source_receipt"] = receipt
        record["source_tree"] = common.canonical(stage / "rootfs", work / "source-before.stderr")
        root = work / "rootfs"
        common.run(work, "copy-root", ["cp", "-a", "--reflink=auto", "--",
                   str(stage / "rootfs"), str(root)], timeout=1800)
        copied = common.canonical(root, work / "copy-tree.stderr")
        require((copied["sha256"], copied["bytes"]) ==
                (record["source_tree"]["sha256"], record["source_tree"]["bytes"]),
                "copied root differs in bytes or archive metadata")
        nura.verify_inventory(root, inventory, staged=True)
        original = {}
        for entry in inventory["files"]:
            if "unavailable" not in entry:
                path, _ = nura.target(root, entry["path"])
                original[entry["path"]] = common.identity(path)
        services = {name.rsplit("/", 1)[-1]: [item["name"] for item in data["entries"]]
                    for name, data in inventory["directories"].items()
                    if name.startswith("etc/runlevels/")}
        for names in services.values():
            for name in names:
                path, _ = nura.target(root, "etc/init.d/" + name)
                original["etc/init.d/" + name] = common.identity(path)
        common.under(root, RESULT, mkdir=True)
        require(not (root / RESULT).exists(), "guest result already present before first boot")
        guest_source = HERE / "nura_r5_guest.py"
        common.copy_exact(guest_source, common.under(root, GUEST, mkdir=True),
                          common.identity(guest_source))
        service_identity = write_new(root, SERVICE, SERVICE_TEXT, 0o755)
        link = common.under(root, "etc/runlevels/default/tb371fc-nura-r5-vm")
        link.symlink_to("/" + SERVICE)
        (work / "kernel").mkdir()
        kernel = stage / "r5-kernel/artifacts/Image"
        kernel_identity = staged["kernel_payload"]["artifacts/Image"]
        common.copy_exact(kernel, work / "kernel/Image", kernel_identity)
        config = (stage / "r5-kernel/artifacts/kernel.config").read_text().splitlines()
        require('CONFIG_INITRAMFS_SOURCE=""' in config, "direct-root forbids an embedded initramfs")
        for symbol in ("VIRTIO_MMIO", "VIRTIO_BLK", "EXT4_FS", "DEVTMPFS", "DEVTMPFS_MOUNT"):
            require("CONFIG_" + symbol + "=y" in config, "direct-root needs built-in " + symbol)
        profile = {"schema_version": 1, **SCOPE, "nonce": secrets.token_hex(16),
                   "kernel_release": common.RELEASE, "kernel_image": kernel_identity,
                   "root_label": LABEL, "source_stage_receipt": receipt,
                   "runtime_files": files, "original_files": original,
                   "original_services": services,
                   "added_files": {GUEST: common.identity(guest_source), SERVICE: service_identity}}
        record["profile"] = write_new(root, PROFILE, json.dumps(profile, indent=2, sort_keys=True) + "\n")
        common.copy_exact(root / PROFILE, work / "profile.json", record["profile"])
        record["image"] = create_ext4(root, work / "prepared.ext4", LABEL, size_bytes=size_bytes)
        record["kernel"] = kernel_identity
        after = common.canonical(stage / "rootfs", work / "source-after.stderr")
        require((after["sha256"], after["bytes"]) ==
                (record["source_tree"]["sha256"], record["source_tree"]["bytes"]),
                "source stage root changed while preparing independent candidate")
        checked(stage / "nura-r5-stage.json", receipt)
        record["source_tree_unchanged"] = True
        checked(Path(__file__), record["host_source"])
        checked(guest_source, record["guest_source"])
        record["complete"] = True
    except BaseException as error:
        record["error"] = str(error)
        raise
    finally:
        record["finished_utc"] = common.now()
        common.save(work / "prepare.json", record)


def guest_acceptance(guest, profile, profile_sha, run_name):
    expected = {"schema_version": 1, "nonce": profile["nonce"], "run": run_name,
                "profile_sha256": profile_sha, "kernel_release": common.RELEASE,
                "pid1": "/usr/bin/busybox", "root_type": "ext4",
                "root_label": LABEL, "signature_enforced": True,
                "openrc_runlevel": "default", **SCOPE}
    require(all(guest.get(k) == v for k, v in expected.items()), "guest identity or scope mismatch")
    wanted = {"root_device", "original_files", "runtime_files", "added_files",
              "signature_enforced", "openrc_default", "udev", "dbus", "dbus_roundtrip",
              "signed_module_loaded", "pid1", "kernel_release", "root_label", "root_type"}
    gates = guest.get("gates", {})
    wanted.add("service_status_complete")
    require(set(gates) == wanted and all(value is True for value in gates.values())
            and guest.get("core_boot_passed") is True,
            "one or more direct-root core gates failed")
    expected_services = {name for values in profile["original_services"].values() for name in values}
    require(set(guest.get("original_service_states", {})) == expected_services,
            "original service status coverage differs")
    states = guest["original_service_states"]
    require(all(states.get(name) == ["started"] for name in ("udev", "dbus")),
            "critical service state contradicts its gate")
    all_default = all(states[name] == ["started"] for name in profile["original_services"]["default"])
    require(guest.get("default_runlevel_all_services_started") is all_default,
            "default runlevel summary contradicts original service states")
    for name in ("original_files", "runtime_files", "added_files"):
        require(guest.get(name) == {"files": len(profile[name]), "mismatches": [], "passed": True},
                "guest file verification contradicts its gate: " + name)
    return True


def stop_child(child, grace=10):
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=grace)
    else:
        child.wait()


def boot(work, qemu, qemu_sha, run_name, timeout):
    owned_directory(work, "nura-r5-vm-")
    require(re.fullmatch(r"run-[0-9]{2}", run_name), "run must be run-NN")
    require(30 <= timeout <= 1800, "VM timeout must be 30..1800 seconds")
    output = work / run_name
    output.mkdir(mode=0o700)
    record = {"schema_version": 1, **SCOPE, "started_utc": common.now(), "passed": False,
              "target_booted": False, "timeout_seconds": timeout, "run": run_name}
    child = None
    cancelled = []
    handlers = {sig: signal.signal(sig, lambda signum, frame: cancelled.append(signum))
                for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        prepared = json.loads((work / "prepare.json").read_text())
        require(prepared.get("complete") is True and prepared.get("source_tree_unchanged") is True,
                "complete independent preparation required")
        checked(Path(__file__), prepared["host_source"])
        checked(work / "profile.json", prepared["profile"])
        checked(work / "kernel/Image", prepared["kernel"])
        profile = json.loads((work / "profile.json").read_text())
        record["profile_sha256"] = prepared["profile"]["sha256"]
        record["qemu"] = common.check(qemu, qemu_sha)
        require(os.access(qemu, os.X_OK), "QEMU must be executable")
        image = work / "prepared.ext4"
        image_identity = common.identity(image)
        require(image_identity["sha256"] == prepared["image"]["sha256"] and
                image_identity["bytes"] == prepared["image"]["size_bytes"], "prepared image changed")
        common.run(output, "copy-image", ["cp", "--preserve=mode", "--reflink=auto", "--sparse=always", "--",
                   str(image), str(output / "rootfs.ext4")], timeout=1800)
        checked(output / "rootfs.ext4", image_identity)
        common.run(output, "qemu-version", [str(qemu), "--version"])
        require(not cancelled, "cancelled before VM launch")
        cmdline = ("console=ttyAMA0 root=/dev/vda rootfstype=ext4 rootwait rw init=/sbin/init "
                   "module.sig_enforce=1 tb371fc.nura-vm=" + profile["nonce"] +
                   " tb371fc.nura-run=" + run_name)
        argv = [str(qemu), "-machine", "virt", "-cpu", "cortex-a72", "-smp", "2", "-m", "2048",
                "-display", "none", "-monitor", "none", "-serial", "stdio", "-nic", "none",
                "-no-reboot", "-kernel", str(work / "kernel/Image"), "-append", cmdline,
                "-drive", "if=none,id=rootfs,format=raw,file=" + str(output / "rootfs.ext4"),
                "-device", "virtio-blk-device,drive=rootfs"]
        common.save(output / "command.json", argv)
        start = time.monotonic()
        with (output / "serial.log").open("xb") as log:
            child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            record["qemu_pid"] = child.pid
            while child.poll() is None:
                if cancelled or time.monotonic() - start > timeout or log.tell() > 8 * 1024**2:
                    record["termination_reason"] = ("cancelled" if cancelled else
                        "timeout" if time.monotonic() - start > timeout else "serial log limit")
                    break
                time.sleep(0.25)
            stop_child(child)
        record["elapsed_seconds"] = time.monotonic() - start
        record["qemu_exit_code"] = child.returncode
        record["serial"] = common.identity(output / "serial.log")
        serial = (output / "serial.log").read_text(errors="replace")
        record["kernel_panic_seen"] = "Kernel panic - not syncing" in serial
        common.run(output, "filesystem", ["/usr/sbin/e2fsck", "-fn", str(output / "rootfs.ext4")], timeout=600)
        common.run(output, "read-guest-result", ["/usr/sbin/debugfs", "-R",
                   "dump /" + RESULT + " " + str(output / "guest-result.json"),
                   str(output / "rootfs.ext4")], timeout=60)
        actual = common.identity(output / "guest-result.json")
        require(actual["bytes"] <= 1024**2, "oversized guest result")
        guest = json.loads((output / "guest-result.json").read_text())
        record["guest_result"] = guest
        record["guest_result_identity"] = actual
        marker = "TB371FC_NURA_R5_RESULT " + profile["nonce"] + " " + actual["sha256"]
        require(marker in serial, "persisted result lacks its matching serial receipt")
        record["target_booted"] = guest.get("pid1") == "/usr/bin/busybox"
        guest_acceptance(guest, profile, record["profile_sha256"], run_name)
        require(child.returncode == 0 and not record.get("termination_reason")
                and not record["kernel_panic_seen"], "VM did not close normally")
        checked(image, image_identity)
        checked(qemu, record["qemu"])
        checked(work / "kernel/Image", prepared["kernel"])
        record["default_runlevel_all_services_started"] = guest["default_runlevel_all_services_started"]
        record["passed"] = True
    except BaseException as error:
        record["error"] = str(error)
    finally:
        if child is not None:
            stop_child(child)
            record["qemu_exit_code"] = child.returncode
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
        record["finished_utc"] = common.now()
        common.save(output / "result.json", record)
    print(json.dumps(record, indent=2, sort_keys=True), flush=True)
    return 0 if record["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="phase", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--repo", type=Path, required=True)
    prep.add_argument("--stage", type=Path, required=True)
    prep.add_argument("--work", type=Path, required=True)
    prep.add_argument("--size-gib", type=int, choices=(2, 3, 4), default=2)
    run = sub.add_parser("run")
    run.add_argument("--work", type=Path, required=True)
    run.add_argument("--qemu", type=Path, default=Path("/usr/bin/qemu-system-aarch64"))
    run.add_argument("--qemu-sha256", required=True)
    run.add_argument("--run", required=True)
    run.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.repo.resolve(strict=True), args.stage, args.work, args.size_gib * 1024**3)
        return 0
    return boot(args.work, args.qemu.resolve(strict=True), args.qemu_sha256, args.run, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
