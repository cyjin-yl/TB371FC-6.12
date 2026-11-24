#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Clone the qualified Nix registration root and stage the frozen R5 runtime.

No activation, image creation, native boot, or change to the registered source.
Native Nix verifies the clone before target ARM kmod generates its own indexes.
All work and logs belong to a new CT102 /work/nixos-r5-stage-* directory.
"""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import sys

import stage_r5_fedora as common

RECOVERY = Path("/work/nixos-ssd-recovery-20261124-v1")
RESULT_SHA = "44d633777bf13b21964e3714ffc37d85daa7a356dc895564ef6dd7cc34e0397e"
DB_SHA = "9965e527bf77eb5a97db2487a38c88fe52f0d9102d9a9e269a145f2cb377e461"
RECIPE_SHA = "fa3ebb5e3822f289e6636ffaddfaa5cfefe492eb11dc25872cda5d72da8b152d"
TOOL = Path("/work/nixos-native-tool-20261123-v1/tool")
TOOL_REPORT_SHA = "afaa0995663626f443a9bc5507f1873ea3043a8ec44b4576e8316798e436101b"
NIX_SHA = "1795adb32a21c0aeef19e19530e96b933b603465a99dc6cf3ceed5b96948de58"
TOP = "/nix/store/j1g4ih1ajpffx2vhp5z0iyns13h59c4a-nixos-system-tb371fc-research-26.05.20261121.94c3211"
KMOD = "/nix/store/rry33ccw1nkhhgf49p1jzifji6ypayi4-kmod-31"
ENTRY = {
    "init": "d7440ba41d2fb1abdbe1a9a2a1267cde841deb9dd4bd088a59586b12a719becd",
    "activate": "8e8c85675ceca709cd0445f5211a556cb3d0edf52d94e63cd1ea1bdf989f2ea9",
}
DB = "nix/var/nix/db/db.sqlite"
FW_MANIFEST = "usr/share/tb371fc/stock-firmware-manifest.json"

def require(condition, message):
    if not condition:
        raise ValueError(message)

def read_json(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, "duplicate JSON key: " + key)
            out[key] = value
        return out
    return json.loads(path.read_text(), object_pairs_hook=unique)

def qualify_receipt(report):
    for key in ("complete", "cache_assembled", "root_registered", "require_sigs"):
        require(report.get(key) is True, "missing registration gate: " + key)
    for key in ("activation_executed", "vm_started", "physical_hardware_tested",
                "source_store_modified", "old_cache_modified", "global_configuration_written"):
        require(report.get(key) is False, "unexpected registration scope: " + key)
    for key, want in (("path_count", 894), ("nar_bytes", 3751712072),
                      ("destination_content_signature_verify_exit_code", 0),
                      ("recovered_official_records", 1), ("newly_signed_local_records", 3)):
        require(type(report.get(key)) is int and report[key] == want,
                "wrong registration value: " + key)
    for key, want in (("independent_db_sha256", DB_SHA), ("recipe_sha256", RECIPE_SHA),
                      ("native_tool_report_sha256", TOOL_REPORT_SHA), ("entry_hashes", ENTRY)):
        require(report.get(key) == want, "wrong registration identity: " + key)
    keys = report["inputs"]
    result = [keys[name] for name in ("old_project_public_key", "official_public_key",
                                      "new_project_public_key")]
    require(all(isinstance(k, str) and re.fullmatch(r"[A-Za-z0-9._-]+:[A-Za-z0-9+/]{43}=", k)
                for k in result), "malformed public keys")
    require(len({k.split(":")[0] for k in result}) == 3, "ambiguous public keys")
    require(result[1] == "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY=",
            "wrong official key")
    return " ".join(result)

def validate_source(root):
    common.ordinary_dir(root)
    common.check(common.under(root, DB), DB_SHA)
    for name, digest in ENTRY.items():
        common.check(common.under(root, TOP.lstrip("/") + "/" + name), digest)

def same_tree(a, b):
    require(a["sha256"] == b["sha256"] and a["bytes"] == b["bytes"],
            "clone/source canonical tree differs")

def copy_runtime(root, kernel_root, fw_root, contract):
    modules = common.selected_modules(contract)
    # A fresh registered root has no external module or firmware installation.
    # Reject unexpected aliases rather than following an absolute guest link.
    for name in ("lib", "boot", "usr"):
        path = root / name
        if path.exists() or path.is_symlink():
            common.ordinary_dir(path)
        else:
            path.mkdir()
    dest = common.under(root, "lib/modules/" + common.RELEASE, mkdir=True)
    dest.mkdir()
    for name, expected in sorted(modules.items()):
        src = common.under(kernel_root, "modules/lib/modules/" + common.RELEASE + "/" + name)
        common.copy_exact(src, common.under(dest, name, mkdir=True), expected)
    fw = common.firmware_inventory(fw_root)
    for name, expected in sorted(fw.items()):
        common.copy_exact(common.under(fw_root, "usr/" + name),
                          common.under(root, name, mkdir=True), expected)
    source_manifest = common.under(fw_root, FW_MANIFEST)
    common.copy_exact(source_manifest, common.under(root, FW_MANIFEST, mkdir=True),
                      common.check(source_manifest, common.FW_PIN))
    # Keep a conventional /lib/firmware tree for the external kernel, without
    # editing the generated Nix system closure or pretending it contains R5.
    artifacts = {row["path"]: {k: row[k] for k in ("sha256", "bytes", "mode")}
                 for row in contract["kernel_files"] if row["path"].startswith("artifacts/")}
    for name in ("Image", "board.dtb", "kernel.config", "System.map",
                 "signing-cert.der", "kernel.btf", "modules.SHA256SUMS",
                 "research5-services-build.json", "source-manifest.json"):
        rel = "artifacts/" + name
        common.copy_exact(common.under(kernel_root, rel),
                          common.under(root, "boot/r5/" + name, mkdir=True), artifacts[rel])
    return modules, fw

def stage(repo, work, kernel_root, fw_root):
    require(os.geteuid() == 0 and os.uname().machine == "x86_64", "native isolated builder required")
    require(work.parent == Path("/work") and re.fullmatch(r"nixos-r5-stage-[A-Za-z0-9_-]+", work.name),
            "new dedicated /work/nixos-r5-stage-* required")
    common.ordinary_dir(work.parent)
    require(not work.exists() and not work.is_symlink(), "new output required")
    source = RECOVERY / "rootfs"
    for p in (RECOVERY, source, kernel_root, fw_root):
        common.ordinary_dir(p)
        require(not work.resolve().is_relative_to(p.resolve()), "output aliases input")
    os.umask(0o077)
    # Coordinate the immutable registration input; never restart its recovery.
    with (Path("/work") / "nixos-ssd-recovery-lane.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
        work.mkdir(mode=0o700)
        root = work / "rootfs"
        report = {"schema_version": 1, "complete": False, "source_registration_verified": False,
                  "clone_verified": False, "target_depmod_verified": False,
                  "kernel_release": common.RELEASE, "activation_executed": False,
                  "image_created": False, "vm_started": False, "physical_hardware_tested": False,
                  "owner_native_linux_passes_added": 0, "native_boot_readiness": "blocked"}
        try:
            report["recipe"] = common.identity(Path(__file__))
            report["registration"] = common.check(RECOVERY / "result.json", RESULT_SHA)
            keys = qualify_receipt(read_json(RECOVERY / "result.json"))
            validate_source(source)
            report["source_registration_verified"] = True
            candidate = repo / "docs/research/2026-11-23/boot-candidate-r5.json"
            qualifier = repo / "scripts/research/qualify_boot_bundle.py"
            report["candidate"] = common.identity(candidate)
            contract = read_json(candidate)
            common.run(work, "kernel-gate", [sys.executable, str(qualifier), "--repo", str(repo),
                       "--kernel-root", str(kernel_root), "--gate", "kernel", "--output",
                       str(work / "kernel-gate.json")])
            report["source_before"] = common.canonical(source, work / "source-before.stderr")
            common.run(work, "clone", ["cp", "-a", "--reflink=auto", "--", str(source), str(root)],
                       timeout=1800)
            report["clone_before"] = common.canonical(root, work / "clone-before.stderr")
            same_tree(report["source_before"], report["clone_before"])
            validate_source(root)
            require(not os.path.samefile(source / DB, root / DB), "database shared with source")
            # Fresh content/signature verification on the independent clone only.
            common.check(TOOL / "bin/nix", NIX_SHA)
            common.check(TOOL.parent / "result.json", TOOL_REPORT_SHA)
            for name in ("config", "xdg", "home"):
                (work / name).mkdir()
            env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C",
                   "NIX_CONFIG": "", "NIX_CONF_DIR": str(work / "config"),
                   "NIX_USER_CONF_FILES": "", "NIX_PAGER": "cat",
                   "XDG_CACHE_HOME": str(work / "xdg"), "HOME": str(work / "home")}
            native = [str(TOOL / "lib/ld-linux-x86-64.so.2"), "--inhibit-cache",
                      "--library-path", str(TOOL / "lib"), str(TOOL / "bin/nix")]
            common.run(work, "nix-version", native + ["--version"], env=env)
            require((work / "nix-version.stdout").read_text().strip() == "nix (Nix) 2.26.3",
                    "unexpected Nix version")
            common.run(work, "verify-clone", native + ["--extra-experimental-features", "nix-command",
                       "--store", "local?root=" + str(root), "--option", "require-sigs", "true",
                       "--option", "trusted-public-keys", keys, "--option", "substituters", "",
                       "--option", "build-users-group", "", "store", "verify", "--recursive",
                       "--sigs-needed", "1", TOP], env=env, timeout=1800)
            report["clone_verified"] = True
            modules, fw = copy_runtime(root, kernel_root, fw_root, contract)
            report["module_count"] = len(modules) - len(common.METADATA)
            report["firmware_count"] = len(fw)
            # Use the actual Nix closure's target kmod, not host depmod or the
            # Fedora-generated indexes. The original R5 signature policy stays.
            guest = KMOD + "/bin/kmod"
            executable = common.under(root, guest.lstrip("/"))
            report["target_kmod"] = common.identity(executable)
            with executable.open("rb") as f:
                header = f.read(20)
            require(header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\xb7\x00",
                    "expected AArch64 kmod")
            common.check(common.PROOT, common.PINS[common.PROOT])
            common.check(common.QEMU, common.PINS[common.QEMU])
            wrapper = [str(common.PROOT), "-0", "-r", str(root), "-q", str(common.QEMU),
                       "-w", "/"]
            guest_env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C",
                         "LD_LIBRARY_PATH": common.HOST_LIBS, "SYSTEMD_OFFLINE": "1"}
            common.run(work, "target-depmod-version", wrapper + [guest, "depmod", "--version"],
                       env=guest_env)
            common.run(work, "target-depmod", wrapper + [guest, "depmod", "-a", common.RELEASE],
                       env=guest_env)
            require(common.identity(executable) == report["target_kmod"], "kmod changed")
            common.run(work, "root-module-gate", [sys.executable, str(qualifier), "--repo", str(repo),
                       "--rootfs-root", str(root), "--gate", "evidence", "--output",
                       str(work / "root-module-gate.json")])
            gate = read_json(work / "root-module-gate.json")["root_module_tree"]
            require(gate["passed"] is True and gate["input_snapshot_stable"] is True,
                    "root module gate failed")
            report["root_module_gate"] = common.identity(work / "root-module-gate.json")
            report["target_depmod_verified"] = True
            for name, expected in fw.items():
                require(common.identity(common.under(root, name)) == expected, "firmware changed")
            for name, digest in ENTRY.items():
                common.check(common.under(root, TOP.lstrip("/") + "/" + name), digest)
            validate_source(source)
            report["source_after"] = common.canonical(source, work / "source-after.stderr")
            same_tree(report["source_before"], report["source_after"])
            report["complete"] = True
        except BaseException as exc:
            report["error"] = str(exc)
            raise
        finally:
            report["finished_utc"] = common.now()
            common.save(work / "stage-result.json", report)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "work", "kernel-root", "firmware-root"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args()
    stage(a.repo.resolve(strict=True), a.work, a.kernel_root, a.firmware_root)

if __name__ == "__main__":
    main()
