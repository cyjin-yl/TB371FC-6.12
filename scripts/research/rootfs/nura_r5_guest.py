#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Observe the real BusyBox/OpenRC startup inside the dedicated direct-root VM."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import time

PROFILE = Path("/usr/share/tb371fc/nura-r5-vm.json")
RESULT = Path("/var/lib/tb371fc/nura-r5-vm-result.json")
SCOPE = {"root_loader_built": False, "physical_hardware_tested": False,
         "owner_native_linux_passes_added": 0, "board_dtb_used": False,
         "network": False, "scope": "generic ARM64 direct-root core boot only"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(argv, timeout=15):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=timeout, check=False)
        return {"argv": argv, "exit_code": result.returncode,
                "stdout": result.stdout[:65536], "stderr": result.stderr[:65536]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"argv": argv, "error": str(error), "exit_code": None}


def verify_files(files):
    errors = []
    for name, expected in files.items():
        try:
            path = Path("/" + name)
            info = path.stat()
            if (not stat.S_ISREG(info.st_mode) or info.st_size != expected["bytes"] or
                    stat.S_IMODE(info.st_mode) != expected["mode"] or digest(path) != expected["sha256"]):
                errors.append(name)
        except OSError:
            errors.append(name)
    return {"files": len(files), "mismatches": errors, "passed": not errors}


def crashed_services(result):
    """OpenRC exits 1 when no crashed service exists and 0 when it lists one."""
    names = result.get("stdout", "").split()
    valid_names = all(re.fullmatch(r"[A-Za-z0-9_.@+-]+", name) for name in names)
    valid = (not result.get("stderr") and valid_names and
             ((result["exit_code"] == 1 and not names) or
              (result["exit_code"] == 0 and bool(names))))
    return valid, set(names)


def observe(profile, cmdline):
    data = {"schema_version": 1, **SCOPE, "nonce": profile["nonce"],
            "run": cmdline["tb371fc.nura-run"], "profile_sha256": digest(PROFILE),
            "kernel_release": platform.release(), "gates": {}}
    gates = data["gates"]
    data["pid1"] = os.readlink("/proc/1/exe")
    gates["pid1"] = data["pid1"] == "/usr/bin/busybox"
    gates["kernel_release"] = data["kernel_release"] == profile["kernel_release"]
    mount = next(line.split(" - ", 1) for line in Path("/proc/self/mountinfo").read_text().splitlines()
                 if line.split()[4] == "/")
    data["root_type"], data["root_source"] = mount[1].split()[:2]
    gates["root_type"] = data["root_type"] == "ext4"
    gates["root_device"] = os.stat("/").st_dev == os.stat("/dev/vda").st_rdev
    blkid = command([shutil.which("blkid") or "/sbin/blkid", "-s", "LABEL", "-o", "value", "/dev/vda"])
    data["blkid"] = blkid
    data["root_label"] = blkid.get("stdout", "").strip()
    gates["root_label"] = blkid["exit_code"] == 0 and data["root_label"] == profile["root_label"]
    sig = Path("/sys/module/module/parameters/sig_enforce").read_text().strip()
    data["signature_enforced"] = sig in ("1", "Y", "y")
    gates["signature_enforced"] = data["signature_enforced"]
    for key in ("original_files", "runtime_files", "added_files"):
        data[key] = verify_files(profile[key])
        gates[key] = data[key]["passed"]
    # The verifier is backgrounded by OpenRC. Wait for the original startup
    # transactions to settle, without stopping or removing any original service.
    for _ in range(60):
        starting = list(Path("/run/openrc/starting").glob("*"))
        if not starting:
            break
        time.sleep(1)
    data["openrc_status"] = command(["/sbin/rc-status", "--all", "--nocolor"])
    data["openrc_crashed"] = command(["/sbin/rc-status", "--crashed", "--nocolor"])
    crash_query_valid, crashed = crashed_services(data["openrc_crashed"])
    gates["service_status_complete"] = (data["openrc_status"]["exit_code"] == 0 and
                                         crash_query_valid)
    runlevel = command(["/sbin/rc-status", "--runlevel"])
    data["openrc_runlevel_command"] = runlevel
    data["openrc_runlevel"] = runlevel.get("stdout", "").strip()
    gates["openrc_default"] = runlevel["exit_code"] == 0 and data["openrc_runlevel"] == "default"
    services = {name for values in profile["original_services"].values() for name in values}
    states = ("started", "starting", "stopping", "stopped", "failed", "crashed", "inactive")
    data["original_service_states"] = {
        name: [state for state in states if (Path("/run/openrc") / state / name).is_symlink()
               or (Path("/run/openrc") / state / name).exists()] for name in sorted(services)}
    for name in crashed & services:
        if "crashed" not in data["original_service_states"][name]:
            data["original_service_states"][name].append("crashed")
    for name in ("udev", "dbus"):
        gates[name] = data["original_service_states"].get(name) == ["started"]
    data["default_runlevel_all_services_started"] = gates["service_status_complete"] and all(
        data["original_service_states"][name] == ["started"]
        for name in profile["original_services"]["default"])
    data["dbus_roundtrip"] = command(["/usr/bin/dbus-send", "--system", "--print-reply",
        "--dest=org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"])
    gates["dbus_roundtrip"] = (data["dbus_roundtrip"]["exit_code"] == 0 and
                               "org.freedesktop.DBus" in data["dbus_roundtrip"].get("stdout", ""))
    data["module_probe"] = command(["/sbin/modprobe", "autofs4"])
    gates["signed_module_loaded"] = (data["module_probe"]["exit_code"] == 0 and
                                     Path("/sys/module/autofs4").is_dir())
    data["security"] = {"fedora_selinux_equivalence_claimed": False}
    for key, filename in (("selinux_enforce", "/sys/fs/selinux/enforce"),
                          ("pid1_lsm_context", "/proc/1/attr/current")):
        try:
            data["security"][key] = Path(filename).read_text().strip()
        except OSError as error:
            data["security"][key] = {"unavailable": str(error)}
    data["core_boot_passed"] = all(gates.values())
    return data


def main():
    profile = json.loads(PROFILE.read_text())
    cmdline = dict(word.split("=", 1) for word in Path("/proc/cmdline").read_text().split() if "=" in word)
    compatible = Path("/proc/device-tree/compatible").read_bytes().split(b"\0")
    if (cmdline.get("tb371fc.nura-vm") != profile["nonce"] or
            "tb371fc.nura-run" not in cmdline or b"linux,dummy-virt" not in compatible):
        raise SystemExit("refusing verifier outside its explicitly selected generic VM")
    data = {"schema_version": 1, **SCOPE, "nonce": profile["nonce"],
            "run": cmdline["tb371fc.nura-run"], "profile_sha256": digest(PROFILE),
            "core_boot_passed": False}
    try:
        data = observe(profile, cmdline)
    except BaseException as error:
        data["error"] = str(error)
    raw = (json.dumps(data, indent=2, sort_keys=True) + "\n").encode()
    with RESULT.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.sync()
    print("TB371FC_NURA_R5_RESULT " + profile["nonce"] + " " + hashlib.sha256(raw).hexdigest(), flush=True)
    print("TB371FC_NURA_R5_CORE " + ("PASS" if data["core_boot_passed"] else "FAIL"), flush=True)
    # BusyBox init receives a normal shutdown request and invokes the original
    # OpenRC shutdown sequence. No force flag or emulated power-register write.
    command(["/sbin/poweroff"], timeout=15)


if __name__ == "__main__":
    main()
