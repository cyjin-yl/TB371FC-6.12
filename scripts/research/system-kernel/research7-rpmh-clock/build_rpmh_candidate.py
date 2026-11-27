#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a fresh R7 kernel/module/DTB candidate from the qualified R6 source.

Run inside the established build container under the owner's original heavy
job admission. This helper never boots, flashes, mounts or loads a module.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

RELEASE = "6.12.114-tb371fc-research7-rpmh-clock"
R6_RELEASE = "6.12.114-tb371fc-research6-tianma-off"
R5_SOURCE = "source-input/linux-6.12.114-input-integration"
PANEL = "drivers/gpu/drm/panel/panel-novatek-nt36523.c"
R5_PANEL_SHA = "dadab139e6ea0a0e8cf58da0020d9182fd7a604aebd58c54efb2e4182fdb6c33"
R6_PANEL_SHA = "9bc1c7fb376af05823bc933bbd730f0dcdc45807da383dc47e266509f75ed149"
R6_CONFIG_SHA = "5a8ec0c9e1c8eccb10fd12f25a05268b0d739f8bc77d9536a9e664f24bae0e72"
R7_CONFIG_SHA = "84747cefce945deaf0134e52c3b1a8a2bf771f3082853d6903be59ab6d5a92a4"
R6_BUILD_SHA = "f37fbe20624e7f49bdf09eeda28b536fe4da24f9379143efeac598da5a110cc7"
R6_SIGNATURE_SHA = "ab6e20a596985377ab112f6a258f861fdb28c307cb88342166fc54d29f1f5dfa"
R5_RECIPE_SHA = "053178a79838a69440a5e18f01f4fc9a9dc8a81c11347f1689c8e062d530439a"
SIGNATURE_VERIFIER_SHA = "8e7fb179b500bf13cfadd3843fdb3104a5740005f1cd394f2be8112732ee0082"
PANEL_TEST_SHA = "e8f174da818dacf1b9eb458db51572d15f65817bea10e787a0117e091aa96df2"
DTB = "qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb"
DTB_SHA = "af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730"
TOOLCHAIN = {"clang": "Debian clang version 19.1.7 (3+b1)",
             "ld.lld": "Debian LLD 19.1.7 (compatible with GNU linkers)", "pahole": "v1.30"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def identity(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "ordinary file required: " + str(path))
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            "input changed while hashing: " + str(path))
    return {"bytes": before.st_size, "sha256": digest}


def pinned(path, sha):
    result = identity(path)
    require(result["sha256"] == sha, "retained identity differs: " + str(path))
    return result


def write_new(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def expected_config(raw):
    require(hashlib.sha256(raw).hexdigest() == R6_CONFIG_SHA, "complete R6 config differs")
    old = b'CONFIG_LOCALVERSION="-tb371fc-research6-tianma-off"'
    new = b'CONFIG_LOCALVERSION="-tb371fc-research7-rpmh-clock"'
    disabled = b"# CONFIG_QCOM_CLK_RPMH is not set"
    require(raw.count(old) == raw.count(disabled) == 1, "ambiguous R6 configuration")
    result = raw.replace(old, new).replace(disabled, b"CONFIG_QCOM_CLK_RPMH=y")
    require(len(result) == 223386 and hashlib.sha256(result).hexdigest() == R7_CONFIG_SHA,
            "R7 config expectation differs")
    return result


def source_inventory(root):
    require(root.is_absolute() and root.is_dir() and not root.is_symlink()
            and root.resolve(strict=True) == root, "ordinary canonical source root required")
    for rel in (".config", "include/config/auto.conf", "include/generated/autoconf.h",
                "certs/signing_key.pem", "certs/signing_key.x509", "vmlinux", "Module.symvers"):
        require(not os.path.lexists(root / rel), "generated source output or key: " + rel)
    result = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            path = Path(directory) / name
            rel = str(path.relative_to(root))
            st = path.lstat()
            if stat.S_ISLNK(st.st_mode):
                target = os.readlink(path)
                require(not os.path.isabs(target) and path.resolve().is_relative_to(root),
                        "nonrelocatable source symlink: " + rel)
                result[rel] = {"type": "symlink", "target": target}
            elif stat.S_ISREG(st.st_mode):
                result[rel] = {"type": "file", "executable": bool(st.st_mode & 0o111), **identity(path)}
            else:
                require(stat.S_ISDIR(st.st_mode), "special source entry: " + rel)
                result[rel] = {"type": "directory"}
    require(result and len(result) < 200000, "unexpected source inventory size")
    return result


def compare_sources(r5, r6):
    require(r5.keys() == r6.keys(), "R6 source inventory differs from retained R5")
    differences = [name for name in r5 if r5[name] != r6[name]]
    require(differences == [PANEL], "R6 source delta exceeds the qualified panel repair: " + repr(differences[:20]))
    require(r5[PANEL]["sha256"] == R5_PANEL_SHA and r6[PANEL]["sha256"] == R6_PANEL_SHA,
            "panel repair identity differs")


def installed_module_order(raw):
    lines = raw.decode("ascii").splitlines()
    require(lines and len(lines) == len(set(lines)) and all(line.endswith(".o")
            and not line.startswith("/") and ".." not in Path(line).parts for line in lines),
            "unexpected Kbuild modules.order")
    return ("\n".join("kernel/" + line[:-2] + ".ko" for line in lines) + "\n").encode("ascii")


def baseline_receipts(baseline):
    pinned(baseline / "build-result.json", R6_BUILD_SHA)
    pinned(baseline / "module-signatures.json", R6_SIGNATURE_SHA)
    build = json.loads((baseline / "build-result.json").read_text())
    sig = json.loads((baseline / "module-signatures.json").read_text())
    require(build["passed"] is True and sig["passed"] is True and build["kernel_release"] == R6_RELEASE
            and build["module_count"] == sig["module_count"] == 84, "R6 baseline did not qualify")
    modules = build["modules"]
    recorded = {"modules/" + row["path"]: {"bytes": row["bytes"], "sha256": row["sha256"]}
                for row in sig["modules"]}
    require(modules == recorded and all(row["passed"] is True for row in sig["modules"]),
            "R6 signature/build module identities differ")
    observed_paths = sorted(str(p.relative_to(baseline)) for p in (baseline / "modules").rglob("*.ko"))
    require(observed_paths == sorted(modules), "R6 module paths differ from build receipt")
    for name, expected in {**modules, **{"artifacts/" + k: v for k, v in build["artifacts"].items()}}.items():
        require(identity(baseline / name) == expected, "R6 retained payload differs: " + name)
    prefix = "modules/lib/modules/" + R6_RELEASE + "/"
    require(all(name.startswith(prefix) for name in modules), "R6 module release path differs")
    return build, sorted(name[len(prefix):] for name in modules)


def build(repo, r5, baseline, work):
    require(work.is_absolute() and work.parent == Path("/work") and work.name.startswith("r7-rpmh-clock-")
            and not os.path.lexists(work), "fresh /work/r7-rpmh-clock-* required")
    require(os.environ.get("MAKEFLAGS") == "-j2", "use the admitted two-job build environment")
    for path in (repo, r5, baseline):
        require(path.is_dir() and not path.is_symlink() and path.resolve(strict=True) == path,
                "canonical existing input directory required: " + str(path))
    os.umask(0o077)
    sys.dont_write_bytecode = True
    work.mkdir(mode=0o700)
    started = time.monotonic()
    record = {"schema_version": 1, "started_utc": now(), "passed": False,
              "scope": "fresh R7 ARM64 construction and offline module qualification",
              "kernel_release": RELEASE, "native_hardware_passes_added": 0,
              "old_objects_copied": False, "old_private_key_copied": False,
              "runtime_signature_enforcement_verified": False, "commands": [], "inputs": {}}
    env = dict(os.environ)
    env.update(PATH="/usr/lib/llvm-19/bin:" + env["PATH"], LC_ALL="C", TZ="UTC", PYTHONDONTWRITEBYTECODE="1")
    env.pop("KCONFIG_CONFIG", None)
    cancellation_signal = None
    def interrupted(signum, frame):
        nonlocal cancellation_signal
        if cancellation_signal is None:
            cancellation_signal = signum
        # Latch only: asynchronously raising inside Popen could lose ownership
        # of a newly created process before its handle is assigned.
    def check_cancelled():
        if cancellation_signal is not None:
            raise InterruptedError("candidate build interrupted by signal " + str(cancellation_signal))
    handlers = {sig: signal.signal(sig, interrupted) for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}

    def run(name, argv, timeout=7200, extra_env=None):
        check_cancelled()
        row = {"name": name, "argv": [str(x) for x in argv], "started_utc": now()}
        record["commands"].append(row)
        path = work / (name + ".log")
        print(json.dumps({"phase_started": name, "argv": row["argv"], "started_utc": row["started_utc"]}), flush=True)
        try:
            with path.open("xb") as log:
                proc = subprocess.Popen(row["argv"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        env={**env, **(extra_env or {})}, start_new_session=True)
                row["pid"] = proc.pid
                try:
                    check_cancelled()
                    deadline = time.monotonic() + timeout
                    with selectors.DefaultSelector() as poller:
                        poller.register(proc.stdout, selectors.EVENT_READ)
                        while poller.get_map():
                            check_cancelled()
                            if time.monotonic() >= deadline:
                                raise subprocess.TimeoutExpired(row["argv"], timeout)
                            for key, unused in poller.select(0.5):
                                chunk = os.read(key.fd, 65536)
                                if not chunk:
                                    poller.unregister(key.fileobj)
                                    continue
                                log.write(chunk)
                                log.flush()
                                sys.stdout.buffer.write(chunk)
                                sys.stdout.buffer.flush()
                    while True:
                        check_cancelled()
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(row["argv"], timeout)
                        try:
                            proc.wait(timeout=min(0.5, deadline - time.monotonic()))
                            break
                        except subprocess.TimeoutExpired:
                            pass
                    check_cancelled()
                except BaseException:
                    # Only our command's process group is stopped. The caller
                    # must retain host admission until this child is reaped.
                    try:
                        os.killpg(proc.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    if proc.poll() is None:
                        try:
                            proc.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            pass
                    # make may exit while a compiler still holds its stdout.
                    # Terminate any surviving member of this owned group too.
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    raise
                finally:
                    proc.stdout.close()
                row["exit_code"] = proc.returncode
                require(proc.returncode == 0, name + " failed; inspect " + str(path))
        finally:
            row["finished_utc"] = now()
            if path.exists():
                row["log"] = identity(path)
            print(json.dumps(row), flush=True)

    try:
        record["recipe"] = identity(Path(__file__))
        recipe_inputs = {Path(__file__): record["recipe"],
                         Path(__file__).with_name("verify_module_abi.py"): identity(Path(__file__).with_name("verify_module_abi.py")),
                         Path(__file__).with_name("system.config"): identity(Path(__file__).with_name("system.config"))}
        tools = {name: subprocess.check_output([name, "--version"], env=env, text=True, timeout=10).splitlines()[0]
                 for name in TOOLCHAIN}
        require(tools == TOOLCHAIN, "qualified R6 toolchain differs: " + repr(tools))
        record["toolchain"] = tools
        record["makeflags"] = env["MAKEFLAGS"]
        signature_verifier = repo / "scripts/research/display/verify_module_signatures.py"
        panel_test = repo / "scripts/research/display/test_tianma_off.py"
        record["inputs"]["signature_verifier"] = pinned(signature_verifier, SIGNATURE_VERIFIER_SHA)
        record["inputs"]["panel_test"] = pinned(panel_test, PANEL_TEST_SHA)
        recipe_inputs.update({signature_verifier: record["inputs"]["signature_verifier"],
                              panel_test: record["inputs"]["panel_test"]})
        record["inputs"]["r5_recipe"] = pinned(r5 / "recipe-v1/build_system.py", R5_RECIPE_SHA)
        namespace = runpy.run_path(str(r5 / "recipe-v1/build_system.py"))
        namespace["verify_source"](r5)
        retained, expected_modules = baseline_receipts(baseline)
        recipe_inputs[r5 / "kernel-out/certs/signing_key.x509"] = identity(r5 / "kernel-out/certs/signing_key.x509")
        record["inputs"]["r6_build"] = pinned(baseline / "build-result.json", R6_BUILD_SHA)
        record["inputs"]["r6_signatures"] = pinned(baseline / "module-signatures.json", R6_SIGNATURE_SHA)
        record["inputs"]["r6_config"] = pinned(baseline / "artifacts/kernel.config", R6_CONFIG_SHA)
        expected = expected_config((baseline / "artifacts/kernel.config").read_bytes())
        r5_inventory = source_inventory(r5 / R5_SOURCE)
        r6_inventory = source_inventory(baseline / "linux")
        compare_sources(r5_inventory, r6_inventory)
        check_cancelled()
        write_new(work / "source-inventory.json", r6_inventory)
        record["source_inventory"] = identity(work / "source-inventory.json")
        record["retained_source_delta"] = [PANEL]
        out = work / "out"
        target = work / "linux"
        out.mkdir()
        run("copy-source", ["cp", "-a", "--reflink=auto", baseline / "linux", target])
        require(source_inventory(target) == r6_inventory, "copied R6 source differs")
        check_cancelled()
        run("actual-core-regression", ["python3", "-B", "-O", panel_test, "--repo", repo,
                                       "--drm-panel-source", target / "drivers/gpu/drm/drm_panel.c"])
        fragment = Path(__file__).with_name("system.config")
        record["inputs"]["fragment"] = identity(fragment)
        shutil.copyfile(baseline / "artifacts/kernel.config", out / "base.config")
        run("merge-config", ["bash", target / "scripts/kconfig/merge_config.sh", "-m", "-O", out,
                             out / "base.config", fragment], extra_env={"KCONFIG_CONFIG": str(out / ".config")})
        argv = ["make", "-C", str(target), "O=" + str(out), "KCONFIG_CONFIG=.config", "ARCH=arm64", "LLVM=1",
                "CC=clang --sysroot=" + str(r5 / "target-sysroot")]
        run("olddefconfig", argv + ["olddefconfig"])
        require((out / ".config").read_bytes() == expected, "olddefconfig exceeds exact two-symbol delta")
        record["candidate_config"] = identity(out / ".config")
        write_new(work / "configuration.json", {"passed": True, "config": record["candidate_config"],
                  "expected_release": RELEASE, "exact_changes": ["CONFIG_LOCALVERSION", "CONFIG_QCOM_CLK_RPMH"]})
        run("kernel-modules", argv + ["Image", "modules"])
        new_certificate = out / "certs/signing_key.x509"
        cert = identity(new_certificate)
        require(cert not in (identity(r5 / "kernel-out/certs/signing_key.x509"),
                             identity(baseline / "artifacts/signing-cert.der")), "old signing certificate reused")
        require(new_certificate.read_bytes() in (out / "arch/arm64/boot/Image").read_bytes(),
                "new public certificate absent from Image")
        record["new_signing_certificate"] = cert
        run("device-tree", argv + [DTB])
        require((out / "include/config/kernel.release").read_text() == RELEASE + "\n", "built release differs")
        require((out / ".config").read_bytes() == expected, "Kbuild changed candidate config")
        pinned(out / "arch/arm64/boot/dts" / DTB, DTB_SHA)
        run("modules-install", argv + ["INSTALL_MOD_PATH=" + str(work / "modules"),
                                       "INSTALL_MOD_STRIP=1", "modules_install"])
        installed_release = work / "modules/lib/modules" / RELEASE
        record["module_metadata"] = {}
        for name in ("modules.builtin", "modules.builtin.modinfo", "modules.order"):
            generated = (out / name).read_bytes()
            expected_metadata = installed_module_order(generated) if name == "modules.order" else generated
            require((installed_release / name).read_bytes() == expected_metadata,
                    "installed module metadata differs from Kbuild: " + name)
            record["module_metadata"][name] = {"built": identity(out / name),
                "installed": identity(installed_release / name),
                "relationship": "Kbuild kernel-prefix and .o-to-.ko transform" if name == "modules.order" else "byte-identical"}
        require(sorted((installed_release / "modules.order").read_text().splitlines()) == expected_modules,
                "installed module order differs from the exact 84-module set")
        run("module-signatures", ["python3", "-B", signature_verifier, "--modules", work / "modules",
                                  "--certificate", new_certificate, "--expected-count", "84",
                                  "--output", work / "module-signatures.json"])
        write_new(work / "expected-module-paths.json", expected_modules)
        abi_verifier = Path(__file__).with_name("verify_module_abi.py")
        record["inputs"]["abi_verifier"] = identity(abi_verifier)
        run("module-abi", ["python3", "-B", abi_verifier, "--modules", work / "modules/lib/modules" / RELEASE,
                           "--release", RELEASE, "--symvers", out / "Module.symvers",
                           "--expected-paths", work / "expected-module-paths.json", "--output", work / "module-abi.json"])
        modules = sorted((work / "modules/lib/modules" / RELEASE).rglob("*.ko"))
        require([str(p.relative_to(work / "modules/lib/modules" / RELEASE)) for p in modules] == expected_modules,
                "module set changed during qualification")
        record["module_count"] = len(modules)
        record["modules"] = {str(p.relative_to(work)): identity(p) for p in modules}
        record["offline_signature_result"] = identity(work / "module-signatures.json")
        record["offline_abi_result"] = identity(work / "module-abi.json")
        artifacts = work / "artifacts"
        artifacts.mkdir()
        record["vmlinux"] = identity(out / "vmlinux")
        run("extract-kernel-btf", ["llvm-objcopy", "--dump-section", ".BTF=" + str(artifacts / "kernel.btf"),
                                   out / "vmlinux", "/dev/null"], timeout=120)
        require(identity(out / "vmlinux") == record["vmlinux"] and (artifacts / "kernel.btf").stat().st_size > 24,
                "vmlinux changed or kernel BTF extraction is empty")
        outputs = {"Image": out / "arch/arm64/boot/Image", "board.dtb": out / "arch/arm64/boot/dts" / DTB,
                   "kernel.config": out / ".config", "kernel.release": out / "include/config/kernel.release",
                   "Module.symvers": out / "Module.symvers", "System.map": out / "System.map",
                   "signing-cert.der": new_certificate,
                   **{name: installed_release / name for name in record["module_metadata"]}}
        for name, path in outputs.items():
            shutil.copyfile(path, artifacts / name)
        record["artifacts"] = {name: identity(artifacts / name) for name in [*outputs, "kernel.btf"]}
        require(source_inventory(target) == r6_inventory, "Kbuild changed copied source")
        require(source_inventory(baseline / "linux") == r6_inventory, "retained R6 source changed")
        require(source_inventory(r5 / R5_SOURCE) == r5_inventory, "retained R5 source changed")
        baseline_receipts(baseline)
        namespace["verify_source"](r5)
        require(all(identity(path) == expected for path, expected in recipe_inputs.items()),
                "executed recipe input changed")
        check_cancelled()
        record.update(retained_inputs_reverified=True, offline_modules_qualified=True, passed=True)
    except BaseException as error:
        record["error"] = repr(error)
        raise
    finally:
        record["finished_utc"] = now()
        record["elapsed_seconds"] = time.monotonic() - started
        write_new(work / "build-result.json", record)
        for sig, old in handlers.items():
            signal.signal(sig, old)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True)
    p.add_argument("--r5", type=Path, default=Path("/work/research5-services"))
    p.add_argument("--baseline", type=Path, default=Path("/work/tianma-r6-build-ec332-01"))
    p.add_argument("--work", type=Path, required=True)
    args = p.parse_args()
    build(args.repo, args.r5, args.baseline, args.work)
