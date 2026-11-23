#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bind the two R5 generic-VM phases to one actual ext4 image.

Run only after PR #4 has materialized and assembled a fresh R5 work tree.
The unchanged derived v9 runner remains the authority for guest results.
A failed or interrupted attempt is retained; never silently rerun it.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys

LABEL = "tb371fc-r5-f45"
RELEASE = "6.12.114-tb371fc-research5-services"
IMAGE = "fedora45-research5-services.ext4"
ROLES = {
    "label": ("maintenance-initramfs.json", "maintenance-label-only"),
    "verify": ("initramfs.json", "production-tmpfs-early-selinux"),
}


def identity(path: Path) -> dict:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
        raise ValueError(f"independent ordinary file required: {path}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_nlink")
    if any(getattr(before, k) != getattr(after, k) for k in keys):
        raise ValueError(f"file changed during measurement: {path}")
    return {"sha256": digest, "bytes": after.st_size}


def read_json(path: Path) -> dict:
    identity(path)
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def save(path: Path, data: dict) -> None:
    with path.open("x") as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write("\n")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def boot_inputs(work: Path, phase: str) -> dict:
    root = work / "rootfs"
    recipe = work / "recipe"
    profile = root / "usr/share/tb371fc/system-profile.json"
    profile_id = identity(profile)
    require(profile_id == identity(work / "system-profile.json"), "profile copies differ")
    data = read_json(profile)
    require(data["kernel_release"] == RELEASE and data["root_label"] == LABEL,
            "not the frozen R5 profile")
    manifest = read_json(work / "image.before-boot.json")
    image = work / IMAGE
    require(manifest["path"] == str(image) and manifest["label"] == LABEL
            and manifest["filesystem"] == "ext4"
            and manifest["physical_block_device_used"] is False
            and manifest["profile_sha256"] == profile_id["sha256"],
            "image receipt does not identify this R5 profile")
    runner = recipe / "boot_system_vm.py"
    derived = read_json(recipe / "derivation.json")["derived"]["boot_system_vm.py"]
    runner_id = identity(runner)
    require(runner_id == {k: derived[k] for k in ("sha256", "bytes")},
            "derived VM runner differs from recipe receipt")
    kernel = identity(root / "boot" / ("Image-" + RELEASE))
    require(kernel["sha256"] == data["kernel_image_sha256"], "kernel differs from profile")
    archives = {}
    for stage, (name, role) in ROLES.items():
        entry = read_json(work / name)
        suffix = "-maintenance" if stage == "label" else ""
        path = root / "boot" / ("initramfs-" + RELEASE + suffix + ".img")
        actual = identity(path)
        require(entry["path"] == str(path) and entry["role"] == role
                and entry["archive_verified"] is True and entry["kernel_release"] == RELEASE
                and entry["size_bytes"] == actual["bytes"]
                and entry["sha256"] == actual["sha256"]
                and manifest["archives"][role] == actual["sha256"], "archive receipt mismatch")
        archives[stage] = actual["sha256"]
    require(archives["label"] != archives["verify"], "phase archives must be distinct")
    actual_image = identity(image)
    require(actual_image["bytes"] == manifest["size_bytes"], "image size changed")
    return {"profile_sha256": profile_id["sha256"], "kernel_image_sha256": kernel["sha256"],
            "initramfs_sha256": archives[phase], "archives": archives,
            "runner": runner_id, "image_manifest": identity(work / "image.before-boot.json"),
            "image": actual_image, "original_image": {"sha256": manifest["sha256"],
                                                       "bytes": manifest["size_bytes"]}}


def result_matches(result: dict, inputs: dict, phase: str) -> bool:
    return (result.get("passed") is True and result.get("phase") == phase
            and result.get("qemu_exit_code") == 0
            and result.get("termination_reason") is None
            and all(result.get(k) == inputs[k] for k in
                    ("profile_sha256", "kernel_image_sha256", "initramfs_sha256")))


def prepare(work: Path, phase: str) -> dict:
    inputs = boot_inputs(work, phase)
    # Old or failed attempts cannot qualify a new image. Exactly one pair.
    vm_dirs = {p.name for p in work.glob("vm-*")}
    lineage_dirs = {p.name for p in work.glob("lineage-*")}
    if phase == "label":
        require(not vm_dirs and not lineage_dirs, "existing boot attempt; preserve it")
        require(inputs["image"] == inputs["original_image"], "image differs from fresh build")
    else:
        require(vm_dirs == {"vm-label-01"} and lineage_dirs == {"lineage-label"},
                "verify requires exactly one completed guarded label attempt")
        label_path = work / "vm-label-01/result.json"
        label = read_json(work / "lineage-label/after.json")
        prior = label["before"]
        require(label["passed"] is True and label["runner_exit_code"] == 0
                and prior["image"] == inputs["original_image"]
                and label["image_after"] == inputs["image"]
                and label["result"] == identity(label_path),
                "label receipt does not identify current image")
        for key in ("profile_sha256", "kernel_image_sha256", "runner", "archives",
                    "image_manifest", "original_image"):
            require(prior[key] == inputs[key], f"label/verify input changed: {key}")
        require(prior["initramfs_sha256"] == inputs["archives"]["label"]
                and result_matches(read_json(label_path), prior, "label"),
                "underlying label gate did not pass")
    return inputs


def run_phase(work: Path, phase: str) -> int:
    before = prepare(work, phase)
    lineage = work / ("lineage-" + phase)
    lineage.mkdir(mode=0o700)
    save(lineage / "before.json", before)
    run = "vm-" + phase + "-01"
    command = [sys.executable, str(work / "recipe/boot_system_vm.py"), phase, "--run", run]
    save(lineage / "command.json", {"argv": command})
    record = {"before": before, "phase": phase, "passed": False,
              "physical_hardware_tested": False}
    try:
        child = subprocess.run(command, check=False)
        record["runner_exit_code"] = child.returncode
        record["image_after"] = identity(work / IMAGE)
        result_path = work / run / "result.json"
        record["result"] = identity(result_path)
        after = boot_inputs(work, phase)
        require(all(before[k] == after[k] for k in before if k != "image"),
                "boot inputs changed during phase")
        record["passed"] = (child.returncode == 0
                            and result_matches(read_json(result_path), before, phase))
    except BaseException as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        save(lineage / "after.json", record)
    return 0 if record["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("phase", choices=tuple(ROLES))
    args = parser.parse_args()
    work = args.work
    require(work.parent == Path("/work") and work.name.startswith("fedora-r5-system-")
            and work.is_dir() and not work.is_symlink() and work.resolve() == work,
            "independent CT102 R5 work directory required")
    # Coordinate with the existing staging/assembly lane. Never delete its lock.
    with Path("/work/r5-fedora-lane.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return run_phase(work, args.phase)


if __name__ == "__main__":
    raise SystemExit(main())
