#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive a separate Nura/OpenRC R5 root; never boot or modify retained inputs."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile

import stage_r5_fedora as common

ARCHIVE = Path("/work/pmwork/artifacts/nura-qemu-aarch64-userspace-20261123.tar.gz")
ARCHIVE_PIN = ("eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46", 307393454)
INVENTORY = "docs/research/2026-11-23/evidence/nura-entry-inventory.json"
INVENTORY_PIN = "8e9f289acc6b7be0d40e6e89dec21125a8e9a3a2f16189adbab7e774e7ec991d"
FIRMWARE = Path("/work/stock-fw-stage-v1/canonical-elf")
MAX_MEMBERS = 200000
MAX_EXPANDED = 4 * 1024**3


def archive_name(value):
    if value in (".", "./"):
        return "."
    if value.startswith("./"):
        value = value[2:]
    value = value.removesuffix("/")
    if not value or value.startswith("/") or "\\" in value:
        raise ValueError("invalid archive name: " + repr(value))
    p = PurePosixPath(value)
    if str(p) != value or ".." in p.parts or value == ".":
        raise ValueError("noncanonical archive name: " + repr(value))
    return value


def validate_members(members):
    """Reject path aliases, special files and any write through a link parent."""
    seen = {}
    expanded = 0
    for member in members:
        name = archive_name(member.name)
        if name in seen or len(seen) >= MAX_MEMBERS:
            raise ValueError("duplicate member or member limit: " + name)
        if member.isdir():
            kind = "directory"
        elif member.isfile():
            kind = "file"
            expanded += member.size
            if member.size < 0 or expanded > MAX_EXPANDED:
                raise ValueError("archive expanded size limit")
        elif member.issym():
            kind = "symlink"
            if not member.linkname or "\x00" in member.linkname:
                raise ValueError("invalid symlink")
        elif member.islnk():
            kind = "hardlink"
            target = archive_name(member.linkname)
            if seen.get(target) not in ("file", "hardlink"):
                raise ValueError("hardlink must refer to a prior regular member: " + name)
        else:
            raise ValueError("special or unsupported archive member: " + name)
        if name == "." and kind != "directory":
            raise ValueError("archive root must be a directory")
        seen[name] = kind
    if seen.get(".") != "directory":
        raise ValueError("explicit root directory required")
    for name in seen:
        for parent in PurePosixPath(name).parents:
            if seen.get(str(parent)) != "directory":
                raise ValueError("missing/non-directory archive parent: " + name)
    return {"members": len(seen), "regular_bytes": expanded,
            "symlinks": sum(v == "symlink" for v in seen.values()),
            "hardlinks": sum(v == "hardlink" for v in seen.values())}


def extract_archive(work, archive, root):
    with tarfile.open(archive, "r|gz") as stream:
        layout = validate_members(stream)
    root.mkdir()
    common.run(work, "extract", ["tar", "--extract", "--gzip",
        "--file", str(archive), "--directory", str(root),
        "--numeric-owner", "--same-owner", "--same-permissions",
        "--acls", "--xattrs", "--xattrs-include=*", "--selinux",
        "--delay-directory-restore"], timeout=1800)
    return layout


def target(root, name):
    """Resolve guest symlinks without ever following a host absolute symlink."""
    pending = list(PurePosixPath(name).parts)
    done = []
    links = []
    for _ in range(256):
        if not pending:
            return root.joinpath(*done), links
        part = pending.pop(0)
        if part in ("", "/", "."):
            continue
        if part == "..":
            if not done:
                raise ValueError("target path escapes guest root")
            done.pop()
            continue
        path = root.joinpath(*done, part)
        if stat.S_ISLNK(path.lstat().st_mode):
            value = os.readlink(path)
            links.append({"path": "/".join(done + [part]), "target": value})
            if value.startswith("/"):
                done.clear()
            pending = list(PurePosixPath(value).parts) + pending
        else:
            done.append(part)
            if pending:
                common.ordinary_dir(path)
    raise ValueError("target resolution limit")


def verify_inventory(root, inventory, staged=False):
    matched = {}
    for expected in inventory["files"]:
        name = expected["path"]
        if "unavailable" in expected:
            if name != "sbin/openrc-init":
                raise ValueError("unrecognized unavailable inventory entry")
            try:
                target(root, name)
            except FileNotFoundError:
                matched[name] = "absent"
                continue
            raise ValueError("originally absent init now exists")
        path, links = target(root, name)
        actual = common.identity(path)
        if (actual["sha256"], actual["bytes"], actual["mode"]) != (
                expected["sha256"], expected["size"], int(expected["mode"], 8)):
            raise ValueError("entry identity differs: " + name)
        info = path.lstat()
        if (info.st_uid, info.st_gid) != (expected["uid"], expected["gid"]):
            raise ValueError("entry owner differs: " + name)
        if str(path.relative_to(root)) != expected["resolved_path"] or links != expected["links"]:
            raise ValueError("entry resolution differs: " + name)
        matched[name] = actual
    for name, expected in inventory["directories"].items():
        path, links = target(root, name)
        common.ordinary_dir(path)
        if str(path.relative_to(root)) != expected["resolved_path"] or links != expected["links"]:
            raise ValueError("directory resolution differs: " + name)
        entries = []
        for child in sorted(path.iterdir()):
            mode = child.lstat().st_mode
            kind = ("symlink" if stat.S_ISLNK(mode) else
                    "directory" if stat.S_ISDIR(mode) else
                    "file" if stat.S_ISREG(mode) else "other")
            item = {"name": child.name, "kind": kind}
            if kind == "symlink":
                item["target"] = os.readlink(child)
            entries.append(item)
        # New release files are additive. Preserve exact old names and links.
        if staged and name == "lib/modules":
            entries = [x for x in entries if x["name"] != common.RELEASE]
        if entries != expected["entries"]:
            raise ValueError("original directory inventory differs: " + name)
    return matched


def stage_firmware(root, source):
    manifest = common.under(source, "stock-firmware-manifest.json")
    common.check(manifest, common.FW_PIN)
    data = json.loads(manifest.read_text())
    files = {}
    if data["firmware_file_count"] != 69 or len(data["files"]) != 69:
        raise ValueError("unexpected firmware count")
    for entry in data["files"]:
        name = common.relative(entry["destination"]).as_posix()
        if not name.startswith("lib/firmware/") or name in files:
            raise ValueError("invalid firmware destination")
        src = common.under(source, name)
        expected = common.check(src, entry["sha256"])
        if expected["bytes"] != entry["size_bytes"]:
            raise ValueError("firmware length mismatch")
        dst = common.under(root, "usr/" + name, mkdir=True)
        if dst.exists() or dst.is_symlink():
            existing = common.identity(dst)
            if existing["sha256"] != expected["sha256"] or existing["bytes"] != expected["bytes"]:
                raise ValueError("refusing to overwrite distribution firmware: " + name)
            files[name] = {"status": "existing-identical", **existing}
        else:
            common.copy_exact(src, dst, expected)
            files[name] = {"status": "added", **expected}
    return files


def stage(repo, work, archive):
    if os.geteuid() != 0:
        raise ValueError("root needed to preserve archive numeric owners and metadata")
    if work.parent != Path("/work") or not work.name.startswith("nura-r5-stage-"):
        raise ValueError("new dedicated /work/nura-r5-stage-* required")
    common.ordinary_dir(work.parent)
    work.mkdir(mode=0o700)
    record = {"schema_version": 1, "started_utc": common.now(), "complete": False,
              "scope": "isolated rootfs construction only", "kernel_release": common.RELEASE,
              "image_built": False, "root_loader_built": False, "target_booted": False,
              "runtime_signature_enforcement_verified": False,
              "owner_native_linux_passes_added": 0}
    root = work / "rootfs"
    try:
        record["source"] = common.identity(Path(__file__))
        candidate = repo / "docs/research/2026-11-23/boot-candidate-r5.json"
        qualifier = repo / "scripts/research/qualify_boot_bundle.py"
        record["candidate"] = common.identity(candidate)
        record["qualifier"] = common.identity(qualifier)
        record["common_source"] = common.identity(Path(common.__file__))
        record["firmware_manifest"] = common.check(
            FIRMWARE / "stock-firmware-manifest.json", common.FW_PIN)
        contract = json.loads(candidate.read_text())
        modules = common.selected_modules(contract)
        common.run(work, "kernel-gate", [sys.executable, str(qualifier), "--repo", str(repo),
            "--kernel-root", str(common.INPUTS), "--gate", "kernel",
            "--output", str(work / "kernel-gate-report.json")])
        record["inventory"] = common.check(repo / INVENTORY, INVENTORY_PIN)
        inventory = json.loads((repo / INVENTORY).read_text())
        record["archive"] = common.identity(archive)
        if (record["archive"]["sha256"], record["archive"]["bytes"]) != ARCHIVE_PIN:
            raise ValueError("not the retained Nura export")
        private_archive = work / "source.tar.gz"
        common.copy_exact(archive, private_archive, record["archive"])
        record["archive_layout"] = extract_archive(work, private_archive, root)
        if common.identity(private_archive) != record["archive"]:
            raise ValueError("private archive changed")
        record["original_entries"] = verify_inventory(root, inventory)
        if not (root / "lib").is_symlink() or os.readlink(root / "lib") != "usr/lib":
            raise ValueError("unexpected Nura lib alias")
        module_root = common.under(root, "usr/lib/modules/" + common.RELEASE)
        module_root.mkdir()
        source_root = common.INPUTS / "modules/lib/modules" / common.RELEASE
        for name, expected in sorted(modules.items()):
            common.copy_exact(common.under(source_root, name),
                              common.under(module_root, name, mkdir=True), expected)
        record["installed_module_and_kbuild_files"] = len(modules)
        record["firmware"] = stage_firmware(root, FIRMWARE)
        # Keep the original /boot entries untouched. New kernel payload is a
        # sibling of the root, not an assertion that the generic loader uses it.
        payload = work / "r5-kernel"
        payload.mkdir()
        record["kernel_payload"] = {}
        for entry in contract["kernel_files"]:
            name = entry["path"]
            if name.startswith("artifacts/"):
                expected = {k: entry[k] for k in ("sha256", "bytes", "mode")}
                dest = common.under(payload, name, mkdir=True)
                common.copy_exact(common.under(common.INPUTS, name), dest, expected)
                record["kernel_payload"][name] = expected
        kmod, _ = target(root, "sbin/depmod")
        if str(kmod.relative_to(root)) != "usr/bin/kmod":
            raise ValueError("target depmod does not resolve to Nura kmod")
        record["target_kmod"] = common.identity(kmod)
        if record["target_kmod"]["sha256"] != "e2de3c1a1eefb1afe1f2458a03541bf388bfdcf4aa83d762d0f5fa2cdec41319":
            raise ValueError("target kmod differs from original inventory")
        with kmod.open("rb") as f:
            header = f.read(20)
        if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\xb7\x00":
            raise ValueError("target kmod must be AArch64 ELF64")
        record["target_executor"] = {str(tool): common.check(tool, common.PINS[tool])
                                     for tool in (common.PROOT, common.QEMU)}
        env = dict(os.environ, LD_LIBRARY_PATH=common.HOST_LIBS)
        wrapper = [str(common.PROOT), "-0", "-r", str(root), "-q", str(common.QEMU),
                   "-b", "/proc", "-b", "/dev/null", "-w", "/"]
        common.run(work, "target-depmod-version", wrapper + ["/sbin/depmod", "--version"], env)
        common.run(work, "target-depmod", wrapper + ["/sbin/depmod", "-a", common.RELEASE], env)
        if common.identity(kmod) != record["target_kmod"]:
            raise ValueError("target kmod changed during execution")
        common.run(work, "root-module-gate", [sys.executable, str(qualifier), "--repo", str(repo),
            "--rootfs-root", str(root), "--gate", "evidence",
            "--output", str(work / "root-module-report.json")])
        report = json.loads((work / "root-module-report.json").read_text())
        tree = report["root_module_tree"]
        if not tree["passed"] or not tree["input_snapshot_stable"]:
            raise ValueError("root module qualification did not pass")
        record["root_module_report"] = common.identity(work / "root-module-report.json")
        record["module_tree"] = {p.relative_to(module_root).as_posix(): common.identity(p)
                                 for p in sorted(module_root.rglob("*")) if p.is_file()}
        for name, expected in modules.items():
            if record["module_tree"].get(name) != expected:
                raise ValueError("depmod changed a frozen module or Kbuild input")
        for item in tree["indexes"]:
            expected = {k: item[k] for k in ("sha256", "bytes", "mode")}
            if record["module_tree"].get(item["path"]) != expected:
                raise ValueError("depmod index changed after inspection")
        record["depmod_receipts"] = {name: common.identity(work / name) for name in (
            "target-depmod.json", "target-depmod.stdout", "target-depmod.stderr",
            "target-depmod-version.json", "target-depmod-version.stdout",
            "target-depmod-version.stderr")}
        for name, expected in record["firmware"].items():
            current = common.identity(common.under(root, "usr/" + name))
            if any(current[k] != expected[k] for k in ("bytes", "sha256", "mode")):
                raise ValueError("staged firmware changed: " + name)
        record["original_entries_after"] = verify_inventory(root, inventory, staged=True)
        if common.identity(archive) != record["archive"]:
            raise ValueError("retained source archive changed")
        record["complete"] = True
    except BaseException as exc:
        record["error"] = str(exc)
        raise
    finally:
        record["finished_utc"] = common.now()
        common.save(work / "nura-r5-stage.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    stage(args.repo.resolve(), args.work, args.archive)


if __name__ == "__main__":
    main()
