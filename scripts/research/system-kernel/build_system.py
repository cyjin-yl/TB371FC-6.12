#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Configure/build an isolated research3 kernel from reproduced input sources.

The preceding source preparation uses the pinned input helper in a new
<work>/source-input. No old output directory or private signing key is copied.
This helper never boots, flashes, mounts a block device or loads a module.
"""
from __future__ import annotations

import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import time

RELEASE = "6.12.114-tb371fc-research3-system"
SOURCE_MANIFEST_SHA = "5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0"
BASE_CONFIG_SHA = "e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8"
INPUT_HELPER_SHA = "0f3334412a7711d3a38d4bfdb0b0b5a35f5a5cb97c1d65868155d34e0c966059"
DTB_SHA = "af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730"
SOURCE_DIR = "source-input/linux-6.12.114-input-integration"
DTB_TARGET = "qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(path):
    return {"size": Path(path).stat().st_size, "sha256": digest(path)}


def config_values(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            result[line[2:-11]] = "n"
    return result


def write_new(path, value):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def verify_source(work):
    inputs = work / "source-input"
    helper = inputs / "input-recipe/scripts/research/input/prepare_input.py"
    if digest(helper) != INPUT_HELPER_SHA:
        raise RuntimeError("pinned input preparation helper changed")
    if digest(inputs / "source-manifest.json") != SOURCE_MANIFEST_SHA:
        raise RuntimeError("prepared research2 + 0018/0019 input manifest changed")
    if digest(inputs / "baseline-abi/kernel.config") != BASE_CONFIG_SHA:
        raise RuntimeError("baseline configuration changed")
    namespace = runpy.run_path(str(helper))
    return namespace["verify"](inputs)


def make_argv(work):
    return ["make", "-C", str(work / SOURCE_DIR), "O=" + str(work / "kernel-out"),
            "ARCH=arm64", "LLVM=1", "CC=clang --sysroot=" + str(work / "target-sysroot")]


def verify_config(work):
    before = config_values(work / "source-input/baseline-abi/kernel.config")
    after = config_values(work / "kernel-out/.config")
    fragment = config_values(work / "system.config")
    required = {**fragment, "CONFIG_BPF_EVENTS": "y", "CONFIG_DEBUG_INFO": "y",
                "CONFIG_DEBUG_INFO_BTF": "y", "CONFIG_DEBUG_INFO_BTF_MODULES": "y",
                "CONFIG_PERF_EVENTS": "y", "CONFIG_BPF_SYSCALL": "y", "CONFIG_BPF_JIT": "y",
                "CONFIG_SECURITY": "y", "CONFIG_SECURITYFS": "y", "CONFIG_MODVERSIONS": "y",
                "CONFIG_MODULE_SIG": "y", "CONFIG_MODULE_SIG_ALL": "y",
                "CONFIG_BPF_UNPRIV_DEFAULT_OFF": "y", "CONFIG_SECURITY_SELINUX": "y"}
    for key, expected in required.items():
        if after.get(key, "n") != expected:
            raise RuntimeError(f"required configuration not resolved: {key}={expected}, actual={after.get(key, 'n')}")
    protected = {key: value for key, value in before.items()
                 if key == "CONFIG_LSM" or key.startswith(("CONFIG_MODULE_SIG", "CONFIG_SECURITY_"))}
    for key, value in protected.items():
        if after.get(key, "n") != value:
            raise RuntimeError("existing security/signing option changed: " + key)
    if after.get("CONFIG_MODULE_COMPRESS_ALL", "n") != "n":
        raise RuntimeError("inspection expects the existing uncompressed module profile")
    changes = {key: {"before": before.get(key, "n"), "after": after.get(key, "n")}
               for key in sorted(set(before) | set(after))
               if before.get(key, "n") != after.get(key, "n")}
    return {"required": required, "preserved_security": protected, "changes": changes}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage", choices=("configure", "build"))
    p.add_argument("--work", type=Path, default=Path("/work/research3-system"))
    p.add_argument("--jobs", type=int, default=4)
    p.add_argument("--attempt", type=int, default=1)
    args = p.parse_args()
    if not 1 <= args.jobs <= 4 or args.attempt < 1:
        p.error("use 1..4 jobs and a positive, unique attempt number")
    work = args.work.resolve()
    if args.work.is_symlink() or not work.is_dir() or not str(work).startswith("/work/research3-system"):
        p.error("use an existing independent /work/research3-system prefix")
    os.umask(0o077)
    lock = (work / "build.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    record_path = work / f"{args.stage}-attempt-{args.attempt:02d}.json"
    if record_path.exists():
        raise SystemExit("retain previous attempt metadata; choose a new attempt number")
    record = {"schema_version": 1, "stage": args.stage, "kernel_release": RELEASE,
              "start_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "commands": [],
              "old_private_key_copied": False, "physical_hardware_tested": False,
              "recipe": {Path(__file__).name: identity(Path(__file__))}}
    env = dict(os.environ)
    env.update({"PATH": "/usr/lib/llvm-19/bin:" + env["PATH"],
                "KBUILD_BUILD_USER": "tb371fc-research", "KBUILD_BUILD_HOST": "isolated-builder",
                "KBUILD_BUILD_VERSION": "1", "KBUILD_BUILD_TIMESTAMP": "2026-11-23 00:00:00 +0000",
                "SOURCE_DATE_EPOCH": "1795392000", "LC_ALL": "C", "TZ": "UTC"})

    def command(argv, capture=False, cwd=None):
        argv = list(map(str, argv))
        print("COMMAND " + json.dumps(argv), flush=True)
        start = time.monotonic()
        proc = subprocess.run(argv, cwd=cwd, env=env, text=True,
                              stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.STDOUT if capture else None)
        item = {"argv": argv, "exit_code": proc.returncode, "elapsed_seconds": time.monotonic() - start}
        if capture:
            item["output"] = proc.stdout
            print(proc.stdout, end="", flush=True)
        record["commands"].append(item)
        if proc.returncode:
            raise subprocess.CalledProcessError(proc.returncode, argv)
        return proc.stdout

    start = time.monotonic()
    try:
        source_manifest = verify_source(work)
        record["input_source_manifest_sha256"] = SOURCE_MANIFEST_SHA
        output = work / "kernel-out"
        if args.stage == "configure":
            if output.exists() or (work / "configuration.json").exists():
                raise RuntimeError("configuration already exists; preserve it")
            output.mkdir()
            (work / "target-sysroot").mkdir()
            fragment = Path(__file__).with_name("system.config")
            shutil.copyfile(fragment, work / "system.config")
            record["recipe"]["system.config"] = identity(fragment)
            shutil.copyfile(work / "source-input/baseline-abi/kernel.config", output / "base.config")
            command(["bash", work / SOURCE_DIR / "scripts/kconfig/merge_config.sh", "-m", "-O", output,
                     output / "base.config", work / "system.config"], cwd=work / SOURCE_DIR)
            command(make_argv(work) + ["olddefconfig"])
            checked = verify_config(work)
            record.update(checked)
            record["config_sha256"] = digest(output / ".config")
            record["tool_versions"] = {name: command([name, "version" if name == "openssl" else "--version"], capture=True).splitlines()[0]
                                       for name in ("clang", "ld.lld", "pahole", "openssl")}
            write_new(work / "configuration.json", record)
            manifest = {"schema_version": 1, "profile": "research3-system", "kernel_release": RELEASE,
                        "source_dir": SOURCE_DIR, "dtb_target": DTB_TARGET, "expected_dtb_sha256": DTB_SHA,
                        "parent_input_manifest_sha256": SOURCE_MANIFEST_SHA,
                        "baseline_config_sha256": BASE_CONFIG_SHA, "system_config_sha256": digest(work / "system.config"),
                        "resolved_config_sha256": digest(output / ".config"),
                        "source_input": source_manifest, "configuration_changes": checked["changes"],
                        "old_objects_copied": False, "old_private_key_copied": False,
                        "physical_hardware_tested": False}
            write_new(work / "source-manifest.json", manifest)
        else:
            cfg = json.loads((work / "configuration.json").read_text())
            if digest(output / ".config") != cfg["config_sha256"]:
                raise RuntimeError("configuration differs from the reviewed configure stage")
            verify_config(work)
            if (work / "artifacts").exists() or (work / "artifacts.partial").exists():
                raise RuntimeError("preserve already staged artifacts")
            command(make_argv(work) + [f"-j{args.jobs}", "Image", "modules"])
            command(make_argv(work) + [f"-j{args.jobs}", DTB_TARGET])
            if (output / "include/config/kernel.release").read_text().strip() != RELEASE:
                raise RuntimeError("compiled release differs")
            if digest(output / ".config") != cfg["config_sha256"]:
                raise RuntimeError("Kbuild changed the reviewed configuration")
            dtb = output / "arch/arm64/boot/dts" / DTB_TARGET
            if digest(dtb) != DTB_SHA:
                raise RuntimeError("joint display/input DT differs from the frozen qualification")
            verify_source(work)
            # Kbuild installs an unsigned copy, strips it, then signs the final
            # bytes. Never strip a signed module after modules_install.
            command(make_argv(work) + ["INSTALL_MOD_PATH=" + str(work / "modules"),
                                     "INSTALL_MOD_STRIP=1", "modules_install"])
            artifacts = work / "artifacts.partial"
            artifacts.mkdir()
            copies = {"Image": output / "arch/arm64/boot/Image", "board.dtb": dtb,
                      "kernel.config": output / ".config", "Module.symvers": output / "Module.symvers",
                      "System.map": output / "System.map", "kernel.release": output / "include/config/kernel.release",
                      "signing-cert.der": output / "certs/signing_key.x509",
                      "configuration.json": work / "configuration.json", "source-manifest.json": work / "source-manifest.json",
                      "source-manifest-input.json": work / "source-input/source-manifest.json"}
            for name, source in copies.items():
                shutil.copyfile(source, artifacts / name)
                (artifacts / name).chmod(0o644)
            command(["llvm-objcopy", "--dump-section", ".BTF=" + str(artifacts / "kernel.btf"),
                     output / "vmlinux", "/dev/null"])
            (artifacts / "kernel.btf").chmod(0o644)
            (artifacts / "SHA256SUMS").write_text("".join(digest(path) + "  " + path.name + "\n"
                                                               for path in sorted(artifacts.iterdir()) if path.is_file()))
            record["artifacts"] = {path.name: identity(path) for path in artifacts.iterdir() if path.is_file()}
            artifacts.rename(work / "artifacts")
            record["new_build_key_generated_in_private_output"] = True
            record["modules_install_strip_then_sign"] = True
        record["passed"] = True
    except Exception as exc:
        record["passed"] = False
        record["failure"] = str(exc)
        raise
    finally:
        record["elapsed_seconds"] = time.monotonic() - start
        record["ended_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_new(record_path, record)
    print(json.dumps({"stage": args.stage, "passed": True, "record": str(record_path),
                      "record_sha256": digest(record_path), "kernel_release": RELEASE}))


if __name__ == "__main__":
    main()
