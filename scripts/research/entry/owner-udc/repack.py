#!/usr/bin/env python3
"""Repack the frozen rescue binaries with a fixed owner-UDC selector.

All execution is host QEMU-user or source-derived predicate tests. No real
sysfs UDC tree, USB device, role control, partition or signing key is opened.
The actual init retains its literal /sys path and has no test override.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

BASE_MANIFEST = "4851e02c7016d6f1288f46e78290cbccecd472951cff116c2059c67a4655bbc9"
BASE_INIT = "ae33ff124ffdca598642a1753e9b5e50de02e8c95b9645c539aae5d5978c9a25"
USB_CAPTURE = "1cb624874a33a5698fab497b0a76a1870817a8299b1f7f264eecb7b2d9f7b445"
HELPERS = {
    "build_first_stage_userspace.py": "c7eb63b41738ba830fefe007a02ba81b627ea520d2386ca26dab953bb69bbb56",
    "package_owner_v2.py": "911ff4530a78173f28af167b02b2843703c5ee0180d6c7c65a00d372fd73c270",
}
BINARIES = {
    "busybox": "f4480b232a952cf1960c96db6b8b9f2d5cef09336321ffc6b13f1f02f3e1d60e",
    "kexec": "70ecd56d8acc1857eaa286ebf7b30796f34d3477d21192e55c13f2797734da60",
    "entry-return-bootloader": "d5b989c22c190eb7edcf20d64707b7961fc8b9dd70fc5bb98a2484c3f14869eb",
}
BEGIN = "# OWNER_UDC_SELECTOR_BEGIN\n"
END = "# OWNER_UDC_SELECTOR_END\n\n"
OLD_SELECTION = '    set -- /sys/class/udc/*\n    if [ "$#" = 1 ] && [ -e "$1" ]; then\n        udc=${1##*/}\n'
NEW_SELECTION = "    if udc=$(select_owner_udc); then\n"
OLD_MESSAGE = "require exactly one enumerated UDC"
NEW_MESSAGE = "require observed a600000.dwc3 with readable UDC metadata"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def regular(path, expected=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("expected a regular input: " + str(path))
    value = sha(path)
    if expected is not None and value != expected:
        raise ValueError("input hash differs: " + str(path))
    return value


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_static_elf(data):
    if data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
        raise ValueError("not the expected AArch64 ELF")
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    if size != 56 or not count or offset + size * count > len(data):
        raise ValueError("unexpected ELF program header table")
    if any(struct.unpack_from("<I", data, offset + i * size)[0] == 3 for i in range(count)):
        raise ValueError("unexpected PT_INTERP in static binary")


def selector_tests(function, busybox):
    """Exercise the original function, mocking only the shell test primitive.

    No runtime path/argument is substituted into the production init. Each
    fixture represents directory/file/readability facts, not a driver probe.
    """
    target = "/sys/class/udc/a600000.dwc3"
    queries = [("-d", target), ("-f", target + "/state"), ("-r", target + "/state"),
               ("-f", target + "/maximum_speed"), ("-r", target + "/maximum_speed")]
    fixtures = [
        ("both_observed_controllers", ["a600000.dwc3", "a800000.dwc3"], [True] * 5, True),
        ("observed_target_only", ["a600000.dwc3"], [True] * 5, True),
        ("secondary_only_no_fallback", ["a800000.dwc3"], [False] * 5, False),
        ("no_controller", [], [False] * 5, False),
        ("unknown_controller_only", ["unobserved.dwc3"], [False] * 5, False),
        ("target_not_directory", ["a600000.dwc3", "a800000.dwc3"], [False, True, True, True, True], False),
        ("state_missing_or_nonregular", ["a600000.dwc3", "a800000.dwc3"], [True, False, True, True, True], False),
        ("state_unreadable", ["a600000.dwc3", "a800000.dwc3"], [True, True, False, True, True], False),
        ("maximum_speed_missing_or_nonregular", ["a600000.dwc3", "a800000.dwc3"], [True, True, True, False, True], False),
        ("maximum_speed_unreadable", ["a600000.dwc3", "a800000.dwc3"], [True, True, True, True, False], False),
    ]
    results = []
    for name, devices, values, success in fixtures:
        predicate = 'test() {\n    echo "CHECK=$1:$2" >&2\n    case "$1:$2" in\n'
        for (operation, path), exists in zip(queries, values):
            predicate += "        '" + operation + ":" + path + "') return " + str(0 if exists else 1) + ";;\n"
        predicate += '        *) echo UNEXPECTED_SELECTOR_QUERY >&2; exit 97;;\n    esac\n}\n'
        body = predicate + function + '\nif selected=$(select_owner_udc); then\n    echo "SELECTED=$selected"\nelse\n    echo HOLD\nfi\n'
        result = subprocess.run(["qemu-aarch64", str(busybox), "sh", "-c", body],
                                capture_output=True, text=True, timeout=10)
        expected = "SELECTED=a600000.dwc3" if success else "HOLD"
        observed = result.stdout.strip()
        calls = result.stderr.splitlines()
        allowed = {"CHECK=" + operation + ":" + path for operation, path in queries}
        if result.returncode or observed != expected or not calls or any(line not in allowed for line in calls):
            raise RuntimeError("selector fixture failed: " + name)
        results.append({"name": name, "fixture_controller_names": devices,
                        "target_metadata_predicates": dict(zip([op + ":" + p for op, p in queries], values)),
                        "exit_code": result.returncode, "observed": observed,
                        "queries": calls, "no_secondary_or_unknown_controller_queried": True, "passed": True})
    return {"scope": "source-derived selector logic under ARM BusyBox with mocked file predicates; no hardware access",
            "function_sha256": hashlib.sha256(function.encode()).hexdigest(),
            "production_function_used_without_path_substitution": True,
            "production_init_test_override_added": False, "fixtures": results, "passed": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--work", type=Path, default=Path("/work/first-stage-research"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, work, output = args.repo.resolve(), args.work.resolve(), args.output.resolve()
    if (str(work) != "/work/first-stage-research" or output.parent != work
            or not re.fullmatch(r"userspace-r2-owner-udc(?:-[0-9]{2})?", output.name)):
        parser.error("use a fresh userspace-r2-owner-udc[-NN] prefix under the isolated work directory")
    os.umask(0o077)
    output.mkdir(mode=0o700, exist_ok=False)
    start = time.monotonic()
    record = {"schema": "tb371fc-clean-entry-userspace-v1", "profile": "owner-udc-r2",
              "started_utc": datetime.now(timezone.utc).isoformat(), "default_action": "hold",
              "completed": False, "new_binary_compilation_performed": False,
              "physical_device_tested": False, "physical_usb_tested": False,
              "role_or_pd_configuration_changed": False, "kexec_load_or_execute_tested": False,
              "artifacts": {}, "commands": []}
    try:
        baseline = work / "userspace-r1-attempt7"
        baseline_meta = baseline / "build.json"
        regular(baseline_meta, BASE_MANIFEST)
        source = json.loads(baseline_meta.read_text())
        if source.get("completed") is not True or source.get("default_action") != "hold":
            raise ValueError("frozen userspace baseline incomplete")
        entry = repo / "scripts/research/entry"
        for name, expected in HELPERS.items():
            regular(entry / name, expected)
        regular(entry / "ramdisk-init", BASE_INIT)
        evidence = repo / "docs/research/2026-11-23/evidence/android-usb-transport.json"
        regular(evidence, USB_CAPTURE)
        owner = json.loads(evidence.read_text())["capture"]
        if ({item["sysfs_name"] for item in owner["udc"]} != {"a600000.dwc3", "a800000.dwc3"}
                or next(item for item in owner["gadget_identifiers"] if item["path"] == "/config/usb_gadget/g1")["attributes"]["UDC"]["value"] != "a600000.dwc3"):
            raise ValueError("owner selector observation differs")
        record["owner_usb_capture_sha256"] = USB_CAPTURE
        record["baseline_userspace_manifest_sha256"] = BASE_MANIFEST
        record["reused_helpers"] = HELPERS
        recipe = Path(__file__).resolve().parent
        new_init = (recipe / "ramdisk-init").read_text()
        if new_init.count(BEGIN) != 1 or new_init.count(END) != 1:
            raise ValueError("selector markers differ")
        begin, end = new_init.index(BEGIN), new_init.index(END) + len(END)
        function = new_init[begin + len(BEGIN):new_init.index(END)]
        reverted = (new_init[:begin] + new_init[end:]).replace(NEW_SELECTION, OLD_SELECTION, 1).replace(NEW_MESSAGE, OLD_MESSAGE, 1)
        old_init = (entry / "ramdisk-init").read_text()
        if reverted != old_init or new_init.count(NEW_SELECTION) != 1:
            raise ValueError("changes outside the isolated UDC selector")
        record["init_diff"] = "".join(difflib.unified_diff(old_init.splitlines(True), new_init.splitlines(True),
                                                         fromfile="frozen/ramdisk-init", tofile="owner-udc/ramdisk-init"))
        record["recipe_hashes"] = {"ramdisk-init": sha(recipe / "ramdisk-init"), "repack.py": sha(Path(__file__))}
        artifacts = output / "artifacts"
        artifacts.mkdir()
        for name, expected in BINARIES.items():
            binary = baseline / "artifacts" / name
            regular(binary, expected)
            data = binary.read_bytes()
            check_static_elf(data)
            target = artifacts / name
            with target.open("xb") as stream:
                stream.write(data)
            target.chmod(0o755)
            record["artifacts"][name] = {"bytes": len(data), "sha256": sha(target), "elf_machine": 183, "pt_interp": False}
        init_copy = artifacts / "ramdisk-init"
        init_copy.write_text(new_init)
        init_copy.chmod(0o755)
        for argv in (["qemu-aarch64", artifacts / "busybox", "sh", "-n", init_copy],
                     ["qemu-aarch64", artifacts / "kexec", "--version"],
                     ["qemu-aarch64", artifacts / "entry-return-bootloader", "--version"]):
            result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=15)
            record["commands"].append({"argv": list(map(str, argv)), "exit_code": result.returncode,
                                       "stdout": result.stdout, "stderr": result.stderr})
            if result.returncode:
                raise RuntimeError("reused userspace/syntax check failed")
        record["selector_tests"] = selector_tests(function, artifacts / "busybox")
        writer = load(entry / "build_first_stage_userspace.py", "owner_udc_frozen_newc_writer")
        reader = load(entry / "package_owner_v2.py", "owner_udc_frozen_newc_reader")
        original_archive = baseline / "artifacts/entry-initramfs.cpio.gz"
        regular(original_archive, source["artifacts"][original_archive.name]["sha256"])
        original = reader.cpio_entries(original_archive.read_bytes())
        if hashlib.sha256(original["init"]["data"]).hexdigest() != BASE_INIT:
            raise ValueError("original archive init differs")
        entries = []
        for item in source["cpio_entries"]:
            name = item["path"]
            data = new_init.encode() if name == "init" else original[name]["data"]
            mode = int(item["mode"], 8)
            if original[name]["mode"] != mode:
                raise ValueError("frozen archive mode differs")
            entries.append((name, mode, data, *item["rdev"]))
        packed = gzip.compress(writer.newc(entries), compresslevel=9, mtime=0)
        decoded = reader.cpio_entries(packed)
        changed = [name for name in original if decoded.get(name) != original[name]]
        if set(original) != set(decoded) or changed != ["init"]:
            raise ValueError("archive changed outside init")
        archive = artifacts / "entry-initramfs.cpio.gz"
        with archive.open("xb") as stream:
            stream.write(packed)
        record["artifacts"][archive.name] = {"bytes": len(packed), "sha256": sha(archive)}
        record["cpio_entries"] = [{"path": n, "mode": oct(m), "bytes": len(data), "rdev": [major, minor]}
                                  for n, m, data, major, minor in entries]
        record["archive_changed_entries"] = changed
        record["all_other_archive_entries_identical"] = True
        for name, expected in BINARIES.items():
            regular(baseline / "artifacts" / name, expected)
        regular(baseline_meta, BASE_MANIFEST)
        regular(entry / "ramdisk-init", BASE_INIT)
        record["frozen_inputs_rechecked_unchanged"] = True
        record["completed"] = True
    except Exception as error:
        record["failure"] = str(error)
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - start
        record["ended_utc"] = datetime.now(timezone.utc).isoformat()
        with (output / "build.json").open("x") as stream:
            stream.write(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"completed": True, "manifest": str(output / "build.json"),
                      "manifest_sha256": sha(output / "build.json"),
                      "archive": record["artifacts"]["entry-initramfs.cpio.gz"],
                      "selector_cases": len(record["selector_tests"]["fixtures"])}))


if __name__ == "__main__":
    main()
