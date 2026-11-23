#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Install the frozen R5 runtime into a new, independently qualified Fedora root.

CT102 only. Never use the retained v9 root or partial image as an output.
This is a construction gate, not evidence of a firmware load or native boot.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys

BASE = Path("/work/fedora-system-integration-v1")
INPUTS = Path("/work/research5-services-kernel-inputs-v1")
RELEASE = "6.12.114-tb371fc-research5-services"
BASE_DIGEST = "1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96"
BASE_BYTES = 1323141120
PROOT = Path("/work/fedora-proot-src/src/proot")
QEMU = Path("/usr/bin/qemu-aarch64")
HOST_LIBS = "/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu"
PINS = {
    BASE / "fedora-system-integration.json": "66ac854b2bc938aed147afe0355b57fcbba856c874e9d82cec4cad663b1c87d9",
    BASE / "runtime.json": "10a373bfc3291aabe564c8f7af90265900763eadfe3167a7384cc4dcd596544b",
    BASE / "vm-verify-01/result.json": "223f73b253a48995dd238575e64aad055e11f311c658aa03534b49c570095675",
    PROOT: "313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f",
    QEMU: "73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943",
}
FW_PIN = "4feb4264605198fc56114fb8b8044ffcd51f662107270a857f59fdaf2e8bcf7c"
METADATA = {"modules.builtin", "modules.builtin.modinfo", "modules.order"}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def identity(path):
    if not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("ordinary file required: " + str(path))
    with path.open("rb") as f:
        digest = hashlib.file_digest(f, "sha256").hexdigest()
    return {"sha256": digest, "bytes": path.stat().st_size,
            "mode": stat.S_IMODE(path.stat().st_mode)}


def check(path, digest):
    result = identity(path)
    if result["sha256"] != digest:
        raise ValueError("digest mismatch: " + str(path))
    return result


def relative(name):
    if not isinstance(name, str) or not name or "\\" in name:
        raise ValueError("invalid relative path")
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or str(p) != name or p == PurePosixPath("."):
        raise ValueError("noncanonical path: " + name)
    return p


def save(path, record):
    with path.open("x") as f:
        json.dump(record, f, indent=2, sort_keys=True)
        f.write("\n")


def ordinary_dir(path):
    if not stat.S_ISDIR(path.lstat().st_mode):
        raise ValueError("ordinary directory required: " + str(path))


def under(root, name, mkdir=False):
    p = root
    parts = relative(name).parts
    for part in parts[:-1]:
        p = p / part
        if mkdir:
            p.mkdir(exist_ok=True)
        ordinary_dir(p)
    return p / parts[-1]


def copy_exact(src, dst, expected):
    if identity(src) != expected:
        raise ValueError("source identity mismatch: " + str(src))
    with src.open("rb") as inp, dst.open("xb") as out:
        shutil.copyfileobj(inp, out)
    dst.chmod(expected["mode"])
    if identity(dst) != expected or identity(src) != expected:
        raise ValueError("copied identity mismatch: " + str(dst))


def canonical(tree, log):
    ordinary_dir(tree)
    argv = ["timeout", "--signal=TERM", "--kill-after=10s", "1800s",
            "tar", "--sort=name", "--format=posix",
            "--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime",
            "--numeric-owner", "--acls", "--selinux", "--xattrs",
            "--xattrs-include=*", "-cf", "-", "-C", str(tree), "."]
    digest, size = hashlib.sha256(), 0
    with log.open("xb") as err:
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=err) as child:
            while data := child.stdout.read(1024 * 1024):
                digest.update(data)
                size += len(data)
            code = child.wait()
    record = {"argv": argv, "sha256": digest.hexdigest(), "bytes": size,
              "exit_code": code, "stderr_bytes": log.stat().st_size}
    if code or record["stderr_bytes"]:
        raise ValueError("canonical stream failed: " + str(log))
    return record


def require_baseline(record):
    if (record["sha256"], record["bytes"]) != (BASE_DIGEST, BASE_BYTES):
        raise ValueError("not the previously qualified Fedora baseline bytes/metadata")


def run(work, name, argv, env=None, timeout=600):
    record = {"argv": argv, "started_utc": now(), "timeout_seconds": timeout}
    try:
        with (work / (name + ".stdout")).open("xb") as out, \
             (work / (name + ".stderr")).open("xb") as err:
            result = subprocess.run(argv, stdout=out, stderr=err,
                                    env=env, timeout=timeout, check=False)
        record["exit_code"] = result.returncode
        if result.returncode:
            raise RuntimeError(name + " returned " + str(result.returncode))
    except BaseException as exc:
        record["error"] = str(exc)
        raise
    finally:
        record["finished_utc"] = now()
        save(work / (name + ".json"), record)
    return record


def selected_modules(contract):
    if contract["kernel"]["release"] != RELEASE or contract["kernel"]["module_count"] != 84:
        raise ValueError("not frozen R5 release")
    prefix = "modules/lib/modules/" + RELEASE + "/"
    selected = {}
    for entry in contract["kernel_files"]:
        name = entry["path"]
        relative(name)
        if not name.startswith(prefix):
            continue
        rel = name[len(prefix):]
        relative(rel)
        if rel in selected:
            raise ValueError("duplicate module destination")
        if rel not in METADATA and not (rel.startswith("kernel/") and rel.endswith(".ko")):
            raise ValueError("unexpected module input: " + rel)
        selected[rel] = {k: entry[k] for k in ("sha256", "bytes", "mode")}
    if set(selected).intersection(METADATA) != METADATA or len(selected) != 87:
        raise ValueError("expected 84 modules and three Kbuild files")
    return selected


def firmware_inventory(root):
    manifest = under(root, "usr/share/tb371fc/stock-firmware-manifest.json")
    check(manifest, FW_PIN)
    data = json.loads(manifest.read_text())
    found = {}
    for item in data["files"]:
        path = relative(item["destination"]).as_posix()
        if not path.startswith("lib/firmware/") or path in found:
            raise ValueError("invalid firmware manifest destination")
        file = under(root, "usr/" + path)
        result = check(file, item["sha256"])
        if result["bytes"] != item["size_bytes"]:
            raise ValueError("firmware length mismatch")
        found[path] = result
    directory = root / "usr/lib/firmware"
    ordinary_dir(directory)
    actual = set()
    for path in directory.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISREG(mode):
            actual.add("lib/firmware/" + path.relative_to(directory).as_posix())
        elif not stat.S_ISDIR(mode):
            raise ValueError("unexpected firmware tree node: " + str(path))
    if len(found) != 69 or data["firmware_file_count"] != 69 or actual != set(found):
        raise ValueError("canonical firmware tree differs from the retained manifest")
    return found


def stage(repo, work):
    ordinary_dir(work.parent)
    if work.parent != Path("/work") or not work.name.startswith("fedora-r5-system-"):
        raise ValueError("new dedicated /work/fedora-r5-system-* required")
    work.mkdir(mode=0o700)
    root = work / "rootfs"
    record = {"schema_version": 1, "started_utc": now(), "complete": False,
              "kernel_release": RELEASE, "owner_native_linux_passes_added": 0,
              "root_loader_built": False, "firmware_selection_verified": False,
              "runtime_signature_enforcement_verified": False}
    try:
        record["pinned_inputs"] = {str(p): check(p, h) for p, h in PINS.items()}
        vm = json.loads((BASE / "vm-verify-01/result.json").read_text())
        if not (vm["passed"] and vm["guest_gates_match"] and
                vm["guest_result"]["selinux"] == "Enforcing"):
            raise ValueError("historical baseline VM gate absent")
        candidate = repo / "docs/research/2026-11-23/boot-candidate-r5.json"
        qualifier = repo / "scripts/research/qualify_boot_bundle.py"
        record["candidate"] = identity(candidate)
        record["qualifier"] = identity(qualifier)
        record["stage_source"] = identity(Path(__file__))
        contract = json.loads(candidate.read_text())
        modules = selected_modules(contract)
        run(work, "kernel-gate", [sys.executable, str(qualifier), "--repo", str(repo),
            "--kernel-root", str(INPUTS), "--gate", "kernel",
            "--output", str(work / "kernel-gate-report.json")])
        record["source_tree"] = canonical(BASE / "rootfs", work / "source-tree.stderr")
        require_baseline(record["source_tree"])
        run(work, "copy", ["cp", "-a", "--reflink=auto", "--",
                           str(BASE / "rootfs"), str(root)], timeout=1800)
        record["destination_tree"] = canonical(root, work / "destination-tree.stderr")
        require_baseline(record["destination_tree"])
        record["journal_acls"] = {}
        for key in ("system.posix_acl_access", "system.posix_acl_default"):
            a = os.getxattr(BASE / "rootfs/var/log/journal", key, follow_symlinks=False)
            b = os.getxattr(root / "var/log/journal", key, follow_symlinks=False)
            if a != b:
                raise ValueError("journal ACL copy mismatch")
            record["journal_acls"][key] = hashlib.sha256(a).hexdigest()
        record["firmware_inventory"] = firmware_inventory(root)
        # Preserve the old release and metadata. Install into new names only.
        lib = root / "lib"
        if not lib.is_symlink() or os.readlink(lib) != "usr/lib":
            raise ValueError("expected Fedora merged-usr alias")
        dest = under(root, "usr/lib/modules/" + RELEASE)
        dest.mkdir()
        source = INPUTS / "modules/lib/modules" / RELEASE
        for name, expected in sorted(modules.items()):
            copy_exact(under(source, name), under(dest, name, mkdir=True), expected)
        artifacts = {x["path"]: {k: x[k] for k in ("sha256", "bytes", "mode")}
                     for x in contract["kernel_files"] if x["path"].startswith("artifacts/")}
        mappings = {"Image": "boot/Image-" + RELEASE,
                    "board.dtb": "boot/dtb-" + RELEASE + "/qcom/sm8250-lenovo-tb371fc.dtb",
                    "kernel.config": "boot/config-" + RELEASE,
                    "System.map": "boot/System.map-" + RELEASE}
        metadata = "usr/share/tb371fc/" + RELEASE + "/"
        for name in ("research5-services-build.json", "source-manifest.json",
                     "signing-cert.der", "modules.SHA256SUMS", "kernel.btf"):
            mappings[name] = metadata + name
        for name, target in mappings.items():
            key = "artifacts/" + name
            copy_exact(under(INPUTS, key), under(root, target, mkdir=True), artifacts[key])
        kmod = under(root, "usr/sbin/kmod")
        depmod = under(root, "usr/sbin/depmod")
        if not depmod.is_symlink() or os.readlink(depmod) != "kmod":
            raise ValueError("unexpected target depmod alias")
        record["target_kmod"] = identity(kmod)
        with kmod.open("rb") as f:
            header = f.read(20)
        if header[:6] != b"\x7fELF\x02\x01" or header[18:20] != b"\xb7\x00":
            raise ValueError("target kmod must be little-endian AArch64 ELF64")
        env = dict(os.environ, LD_LIBRARY_PATH=HOST_LIBS, SYSTEMD_OFFLINE="1")
        wrapper = [str(PROOT), "-0", "-r", str(root), "-q", str(QEMU),
                   "-b", "/proc", "-b", "/dev/null", "-b", "/dev/zero",
                   "-b", "/dev/random", "-b", "/dev/urandom", "-w", "/"]
        run(work, "target-depmod-version", wrapper + ["/usr/sbin/depmod", "--version"], env)
        run(work, "target-depmod", wrapper + ["/usr/sbin/depmod", "-a", RELEASE], env)
        if identity(kmod) != record["target_kmod"]:
            raise ValueError("target kmod changed during execution")
        # This is a second check of changed root state, not a repeat of the
        # earlier historical kernel-only acceptance.
        run(work, "root-module-gate", [sys.executable, str(qualifier), "--repo", str(repo),
            "--rootfs-root", str(root), "--gate", "evidence",
            "--output", str(work / "root-module-report.json")])
        # The evidence gate itself does not require the optional root to pass.
        sys.path.insert(0, str(repo / "scripts/research"))
        import boot_rootfs
        report = json.loads((work / "root-module-report.json").read_text())
        record["root_module_report"] = identity(work / "root-module-report.json")
        record["module_tree"] = {p.relative_to(dest).as_posix(): identity(p)
                                 for p in sorted(dest.rglob("*")) if p.is_file()}
        for name, expected in modules.items():
            if record["module_tree"].get(name) != expected:
                raise ValueError("depmod changed a frozen module or Kbuild input")
        for name in boot_rootfs.REQUIRED_INDEXES:
            if name not in record["module_tree"]:
                raise ValueError("missing target depmod index: " + name)
        boot_rootfs._dependency_graph((dest / "modules.dep").read_bytes(),
                                     {n: v for n, v in modules.items() if n.endswith(".ko")})
        record["depmod_receipts"] = {name: identity(work / name) for name in (
            "target-depmod.json", "target-depmod.stdout", "target-depmod.stderr",
            "target-depmod-version.json", "target-depmod-version.stdout",
            "target-depmod-version.stderr")}
        record["complete"] = True
    except BaseException as exc:
        record["error"] = str(exc)
        raise
    finally:
        record["finished_utc"] = now()
        save(work / "r5-runtime-stage.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    stage(args.repo.resolve(strict=True), args.work)


if __name__ == "__main__":
    main()
