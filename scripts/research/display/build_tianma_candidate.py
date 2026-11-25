#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the Tianma candidate in a new directory from retained, verified R5 sources."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import shutil
import subprocess
import time

RELEASE = "6.12.114-tb371fc-research6-tianma-off"
SOURCE_DIR = "source-input/linux-6.12.114-input-integration"
PANEL = "drivers/gpu/drm/panel/panel-novatek-nt36523.c"
PANEL_SHA = "dadab139e6ea0a0e8cf58da0020d9182fd7a604aebd58c54efb2e4182fdb6c33"
CONFIG_SHA = "a4980121abcc3e2bac47f7020e63c8c00949c53c289019c22b67808d84cd3afa"
PATCH = "mainline-port/backports/linux-6.12/0022-drm-panel-tb371fc-tianma-off-sequence.patch"
PATCH_SHA = "071a4fa269a539023bbbd41e0298418c351b64bdb2c3dc8ac8c3b82a061183ea"
DTB = "qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb"
DTB_SHA = "af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730"


def identity(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"bytes": path.stat().st_size, "sha256": digest}


def require(path, sha):
    actual = identity(path)
    if actual["sha256"] != sha:
        raise ValueError("retained input differs: " + str(path))
    return actual


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def build(repo, baseline, work):
    if not work.is_absolute() or work.parent != Path("/work") or not work.name.startswith("tianma-r6-build-"):
        raise ValueError("new /work/tianma-r6-build-* directory required")
    if os.environ.get("MAKEFLAGS") != "-j2":
        raise ValueError("run through the owner's agent-heavy two-job build environment")
    work.mkdir(mode=0o700)
    started = time.monotonic()
    record = {"started_utc": now(), "passed": False, "scope": "isolated ARM64 kernel/module/DTB construction",
              "kernel_release": RELEASE, "native_hardware_passes_added": 0,
              "old_objects_copied": False, "old_private_key_copied": False,
              "commands": [], "inputs": {}}

    def run(name, argv, timeout=7200):
        row = {"name": name, "argv": [str(x) for x in argv], "started_utc": now()}
        record["commands"].append(row)
        log_path = work / (name + ".log")
        try:
            with log_path.open("xb") as log:
                proc = subprocess.Popen(row["argv"], stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Stop this command's compiler children, not just make.
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                    raise
                row["exit_code"] = proc.returncode
                if proc.returncode:
                    raise RuntimeError(name + " failed; see " + str(work / (name + ".log")))
        except subprocess.TimeoutExpired:
            row["timed_out"] = True
            raise
        finally:
            row["finished_utc"] = now()
            if log_path.exists():
                row["log"] = identity(log_path)
        print(json.dumps({"step": name, "exit_code": row["exit_code"], "finished_utc": row["finished_utc"]}), flush=True)

    try:
        source = baseline / SOURCE_DIR
        config = baseline / "kernel-out/.config"
        # cp -a would otherwise retain an absolute/out-of-tree symlink and
        # allow patch or Kbuild to write back through it into a retained input.
        source_root = source.resolve()
        if source.is_symlink() or not source.is_dir() or not source_root.is_relative_to(baseline):
            raise ValueError("retained source must be a real directory inside the baseline")
        for path in source.rglob("*"):
            if path.is_symlink() and (os.path.isabs(os.readlink(path)) or
                                      not path.resolve().is_relative_to(source_root)):
                raise ValueError("source contains a non-relocatable symlink: " + str(path))
        for rel in (".config", "include/config/auto.conf", "include/generated/autoconf.h",
                    "certs/signing_key.pem", "certs/signing_key.x509", "vmlinux", "Module.symvers"):
            if (source / rel).exists() or (source / rel).is_symlink():
                raise ValueError("source contains a generated output or signing key: " + rel)
        record["inputs"]["panel"] = require(source / PANEL, PANEL_SHA)
        record["inputs"]["r5_config"] = require(config, CONFIG_SHA)
        record["inputs"]["candidate_patch"] = require(repo / PATCH, PATCH_SHA)
        record["inputs"]["r5_source_manifest"] = identity(baseline / "source-input/source-manifest.json")
        baseline_recipe = baseline / "recipe-v1/build_system.py"
        record["inputs"]["baseline_recipe"] = identity(baseline_recipe)
        namespace = runpy.run_path(str(baseline_recipe))
        namespace["verify_source"](baseline)
        record["baseline_source_verified"] = True
        record["baseline_source_verification_scope"] = "pinned assembled source files, baseline ABI inputs and input recipe manifests"
        target = work / "linux"
        out = work / "out"
        out.mkdir()
        run("copy-source", ["cp", "-a", "--reflink=auto", str(source), str(target)])
        require(target / PANEL, PANEL_SHA)
        run("apply-panel", ["patch", "--batch", "--fuzz=0", "-d", target, "-p1", "-i", repo / PATCH])
        record["patched_panel"] = identity(target / PANEL)
        run("actual-core-regression", ["python3", "-O", repo / "scripts/research/display/test_tianma_off.py",
            "--repo", repo, "--drm-panel-source", target / "drivers/gpu/drm/drm_panel.c"])
        shutil.copyfile(config, out / ".config")
        original = config.read_text()
        if 'CONFIG_MODULE_SIG_KEY="certs/signing_key.pem"' not in original.splitlines():
            raise ValueError("candidate requires a newly generated default Kbuild signing key")
        before = 'CONFIG_LOCALVERSION="-tb371fc-research5-services"'
        after = 'CONFIG_LOCALVERSION="-tb371fc-research6-tianma-off"'
        if original.count(before) != 1:
            raise ValueError("unexpected R5 localversion")
        expected = original.replace(before, after)
        (out / ".config").write_text(expected)
        argv = ["make", "-C", str(target), "O=" + str(out), "KCONFIG_CONFIG=.config", "ARCH=arm64", "LLVM=1",
                "CC=clang --sysroot=" + str(baseline / "target-sysroot")]
        run("olddefconfig", argv + ["olddefconfig"])
        if (out / ".config").read_text() != expected:
            raise ValueError("olddefconfig changed more than candidate localversion")
        record["candidate_config"] = identity(out / ".config")
        record["makeflags"] = os.environ["MAKEFLAGS"]
        record["toolchain"] = {tool: subprocess.check_output([tool, "--version"], text=True).splitlines()[0]
                               for tool in ("clang", "ld.lld", "pahole")}
        run("kernel-modules", argv + ["Image", "modules"])
        old_certificate = baseline / "kernel-out/certs/signing_key.x509"
        new_certificate = out / "certs/signing_key.x509"
        if identity(old_certificate) == identity(new_certificate):
            raise ValueError("candidate unexpectedly reused the R5 signing certificate")
        record["new_signing_certificate"] = identity(new_certificate)
        run("device-tree", argv + [DTB])
        if (out / "include/config/kernel.release").read_text().strip() != RELEASE:
            raise ValueError("unexpected built kernel release")
        if identity(out / ".config") != record["candidate_config"]:
            raise ValueError("Kbuild changed candidate configuration")
        require(out / "arch/arm64/boot/dts" / DTB, DTB_SHA)
        run("modules-install", argv + ["INSTALL_MOD_PATH=" + str(work / "modules"),
            "INSTALL_MOD_STRIP=1", "modules_install"])
        modules = sorted((work / "modules/lib/modules" / RELEASE / "kernel").rglob("*.ko"))
        if len(modules) != 84:
            raise ValueError("expected 84 installed R5-profile modules")
        for module in modules:
            with module.open("rb") as stream:
                elf = stream.read(20)
                stream.seek(-28, 2)
                tail = stream.read()
            if elf[:6] != b"\x7fELF\x02\x01" or elf[18:20] != b"\xb7\x00" or tail != b"~Module signature appended~\n":
                raise ValueError("not an AArch64 signed module: " + str(module))
        record["module_count"] = len(modules)
        record["module_signatures_appended"] = True
        record["runtime_signature_enforcement_verified"] = False
        record["modules"] = {str(p.relative_to(work)): identity(p) for p in modules}
        artifacts = work / "artifacts"
        artifacts.mkdir()
        outputs = {"Image": out / "arch/arm64/boot/Image", "board.dtb": out / "arch/arm64/boot/dts" / DTB,
                   "kernel.config": out / ".config", "kernel.release": out / "include/config/kernel.release",
                   "Module.symvers": out / "Module.symvers", "System.map": out / "System.map",
                   "signing-cert.der": out / "certs/signing_key.x509"}
        for name, path in outputs.items():
            shutil.copyfile(path, artifacts / name)
        record["artifacts"] = {name: identity(artifacts / name) for name in outputs}
        require(source / PANEL, PANEL_SHA)
        require(config, CONFIG_SHA)
        namespace["verify_source"](baseline)
        record["retained_r5_inputs_reverified"] = True
        record["passed"] = True
    except BaseException as exc:
        record["error"] = str(exc)
        raise
    finally:
        record["finished_utc"] = now()
        record["elapsed_seconds"] = time.monotonic() - started
        with (work / "build-result.json").open("x") as stream:
            json.dump(record, stream, indent=2, sort_keys=True)
            stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=Path("/work/research5-services"))
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    build(args.repo.resolve(), args.baseline.resolve(), args.work)
