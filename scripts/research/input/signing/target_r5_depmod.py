#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run Fedora's ARM64 kmod on a separate signed Novatek module candidate.

Both the Fedora tool root and module tree are copied into a new work directory.
The retained Fedora root, frozen R5 kernel, and signed-stage result are inputs
only. The target commands are depmod, modinfo and modprobe --show-depends;
neither a kernel module nor the copied operating system is started.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path

import stage_r5_novatek as stage

common = stage.common
signing = stage.signing
qualification = stage.qualification
boot_rootfs = stage.boot_rootfs
RELEASE = stage.RELEASE
MODULE = stage.MODULE
KMOD_SHA = "bbcc9efbb7f828e68eb8a9e6d81b0019e765e5f113d2c26262d9dcee4b42c6bf"
require = stage.require


def derived_contract(original, receipt):
    """Accept one signed-stage replacement, retaining every other R5 identity."""
    require(receipt.get("complete") is True and
            receipt.get("frozen_inputs_verified_after") is True and
            receipt.get("module_loaded") is False and
            receipt.get("module_count") == 84 and
            receipt.get("unchanged_modules") == 83 and
            receipt.get("kernel_release") == RELEASE and
            receipt.get("public_certificate_sha256") == stage.CERT_SHA and
            receipt.get("original_cms", {}).get("signature_verified") is True and
            receipt.get("replacement_cms", {}).get("signature_verified") is True,
            "completed R5 signed-stage receipt required")
    selected = common.selected_modules(original)
    require(selected[MODULE]["sha256"] == stage.BASE_MODULE_SHA,
            "wrong frozen Novatek baseline")
    require(receipt.get("unsigned", {}).get("sha256") == stage.UNSIGNED_SHA and
            receipt.get("unsigned", {}).get("bytes") == stage.UNSIGNED_SIZE,
            "receipt does not bind the accepted 0020+0021 build")
    replacement = receipt["replacement"]
    require(set(replacement) == {"sha256", "bytes", "mode"} and
            replacement["sha256"] != stage.BASE_MODULE_SHA and
            replacement["mode"] == selected[MODULE]["mode"],
            "replacement must be a distinct module with the frozen mode")
    result = copy.deepcopy(original)
    result["candidate_id"] = "tb371fc-r5-novatek-0020-0021-target-depmod"
    path = "modules/lib/modules/" + RELEASE + "/" + MODULE
    matches = [entry for entry in result["kernel_files"] if entry["path"] == path]
    require(len(matches) == 1, "one replacement entry required")
    matches[0].update(replacement)
    # Validate replacement sizes/digests as well as the exact module count.
    boot_rootfs._expected(result)
    return result


def target_kmod(root):
    """Resolve Fedora's two documented aliases without following host links."""
    common.ordinary_dir(root)
    common.ordinary_dir(root / "usr")
    sbin = root / "usr/sbin"
    if sbin.is_symlink():
        require(os.readlink(sbin) in ("bin", "/usr/bin"),
                "unexpected Fedora sbin alias")
        sbin = root / "usr/bin"
    common.ordinary_dir(sbin)
    for name in ("depmod", "modinfo", "modprobe"):
        alias = sbin / name
        require(alias.is_symlink() and os.readlink(alias) == "kmod",
                "unexpected target kmod command alias: " + name)
    binary = sbin / "kmod"
    identity = common.check(binary, KMOD_SHA)
    with binary.open("rb") as stream:
        header = stream.read(20)
    require(header[:6] == b"\x7fELF\x02\x01" and header[18:20] == b"\xb7\x00",
            "target kmod must be AArch64 ELF64")
    return identity


def check_load_plan(text, dependency_text, selected):
    """Check a real target modprobe dry run against its depmod text graph."""
    graph = {}
    for line in dependency_text.splitlines():
        if line:
            name, values = line.split(":", 1)
            require(name not in graph, "duplicate dependency row")
            graph[name] = values.split()
    require(MODULE in graph, "Novatek dependency row missing")
    expected = set(graph[MODULE]) | {MODULE}
    require(expected <= set(selected), "foreign module in dependency row")
    prefix = "/candidate/lib/modules/" + RELEASE + "/"
    paths = []
    for line in text.splitlines():
        fields = line.split()
        require(len(fields) == 2 and fields[0] == "insmod" and
                fields[1].startswith(prefix),
                "unexpected command or path in target dry run")
        relative = fields[1][len(prefix):]
        common.relative(relative)
        paths.append(relative)
    require(paths and paths[-1] == MODULE and len(paths) == len(set(paths)) and
            set(paths) == expected,
            "target binary indexes resolve a different dependency closure")
    return {"modules": paths, "module_count": len(paths),
            "module_loaded": False, "binary_index_lookup_executed": True}


def run(repo, signed_stage, work):
    require(work.parent == Path("/work") and work.name.startswith("r5-novatek-depmod-"),
            "choose a new dedicated /work/r5-novatek-depmod-* directory")
    runtime = common.BASE / "rootfs"
    for path in (repo, signed_stage, runtime, work):
        require(not path.is_symlink(), "symlinked input/output root")
    qualification.validate_output_destination(work, (repo, signed_stage, common.BASE))
    require(not work.exists(), "retain prior attempt; choose a new output directory")
    candidate_path = repo / "docs/research/2026-11-23/boot-candidate-r5.json"
    original = qualification.read_candidate(candidate_path)
    receipt_path = signing.plain_file(signed_stage, "r5-novatek-stage.json")
    receipt_identity = common.identity(receipt_path)
    signed_receipt = json.loads(receipt_path.read_text())
    contract = derived_contract(original, signed_receipt)
    selected = common.selected_modules(contract)
    before = boot_rootfs.inspect_root_module_tree(signed_stage / "rootfs", contract)
    require(before["passed"], "signed-stage module tree differs from its receipt")
    tool_identity = target_kmod(runtime)
    inputs = {str(path): common.check(path, digest)
              for path, digest in common.PINS.items()}
    work.mkdir(mode=0o700)
    report = {"schema_version": 1, "started_utc": common.now(), "complete": False,
              "scope": "offline Fedora ARM64 depmod and binary-index dry run",
              "kernel_release": RELEASE, "module_loaded": False,
              "physical_hardware_tested": False, "owner_native_linux_passes_added": 0,
              "native_boot_readiness": "blocked", "target_depmod_verified": False,
              "signed_stage_receipt": receipt_identity, "pinned_tools": inputs,
              "target_kmod": tool_identity, "recipe": common.identity(Path(__file__))}
    try:
        common.save(work / "signed-input-gate.json", before)
        common.save(work / "derived-candidate.json", contract)
        # Only the module/Kbuild inputs are copied. All indexes must be newly
        # generated by the target depmod, never inherited from host depmod.
        root = work / "rootfs"
        destination = root / "lib/modules" / RELEASE
        destination.mkdir(parents=True)
        source = signed_stage / "rootfs/lib/modules" / RELEASE
        for name, expected in sorted(selected.items()):
            common.copy_exact(common.under(source, name),
                              common.under(destination, name, mkdir=True), expected)
        verify = work / "verification"
        verify.mkdir()
        certificate = signing.plain_file(signed_stage, "verification/cert.pem")
        cert_before = common.identity(certificate)
        signing.run(["openssl", "x509", "-in", certificate, "-outform", "DER",
                     "-out", verify / "cert.der"])
        common.check(verify / "cert.der", stage.CERT_SHA)
        payload, report["replacement_cms"] = stage.cms(
            verify, "replacement", (destination / MODULE).read_bytes(), certificate)
        btf, debug_count = stage.elf_btf(payload)
        require(btf == signed_receipt["btf"] and debug_count == 0,
                "replacement BTF/debug sections differ from signing receipt")
        # The copied tool root prevents target commands from writing into the
        # retained Fedora runtime, including on an unexpected error path.
        report["runtime_source"] = common.canonical(runtime, work / "runtime-source.stderr")
        common.require_baseline(report["runtime_source"])
        tool_root = work / "tool-root"
        common.run(work, "copy-runtime", ["cp", "-a", "--reflink=auto", "--",
                   str(runtime), str(tool_root)], timeout=1800)
        report["runtime_copy"] = common.canonical(tool_root, work / "runtime-copy.stderr")
        common.require_baseline(report["runtime_copy"])
        require(target_kmod(tool_root) == tool_identity, "copied target kmod changed")
        (tool_root / "candidate").mkdir()
        env = dict(os.environ, LD_LIBRARY_PATH=common.HOST_LIBS, SYSTEMD_OFFLINE="1")
        wrapper = [str(common.PROOT), "-0", "-r", str(tool_root), "-q", str(common.QEMU),
                   "-b", str(root) + ":/candidate", "-b", "/proc", "-b", "/dev/null",
                   "-b", "/dev/zero", "-b", "/dev/random", "-b", "/dev/urandom", "-w", "/"]
        commands = {
            "target-depmod-version": ["/usr/sbin/depmod", "--version"],
            "target-depmod": ["/usr/sbin/depmod", "-a", "-b", "/candidate", RELEASE],
        }
        module_path = "/candidate/lib/modules/" + RELEASE + "/" + MODULE
        for field in ("signer", "sig_key", "sig_hashalgo", "vermagic"):
            commands["target-modinfo-" + field] = ["/usr/sbin/modinfo", "-F", field, module_path]
        commands["target-modversions"] = ["/usr/sbin/modprobe", "--show-modversions", module_path]
        commands["target-load-plan"] = ["/usr/sbin/modprobe", "--show-depends", "-C", "/dev/null",
                                        "-d", "/candidate", "-S", RELEASE, "nt36523_ts"]
        for name, argv in commands.items():
            common.run(work, name, wrapper + argv, env, timeout=120)
            require((work / (name + ".stderr")).stat().st_size == 0,
                    "target command emitted diagnostics: " + name)
        actual_info = {field: (work / ("target-modinfo-" + field + ".stdout")).read_text().strip()
                       for field in ("signer", "sig_key", "sig_hashalgo", "vermagic")}
        require(actual_info == signed_receipt["signer"], "target signing metadata differs")
        versions = stage.parse_versions((work / "target-modversions.stdout").read_text())
        require(versions == signed_receipt["imported_crcs"], "target imported CRCs differ")
        inspected = boot_rootfs.inspect_root_module_tree(root, contract)
        common.save(work / "target-root-module-gate.json", inspected)
        require(inspected["passed"], "target-produced indexes/module tree failed inspection")
        report["load_plan"] = check_load_plan((work / "target-load-plan.stdout").read_text(),
                                               (destination / "modules.dep").read_text(), selected)
        report["module_tree"] = {path.relative_to(destination).as_posix(): common.identity(path)
                                  for path in sorted(destination.rglob("*")) if path.is_file()}
        require(all(report["module_tree"].get(name) == expected
                    for name, expected in selected.items()), "target commands changed a module")
        after = boot_rootfs.inspect_root_module_tree(signed_stage / "rootfs", contract)
        require(after["passed"] and before == after, "signed input tree changed")
        require(common.identity(receipt_path) == receipt_identity and
                common.identity(certificate) == cert_before, "signed-stage evidence changed")
        require(target_kmod(runtime) == tool_identity and target_kmod(tool_root) == tool_identity,
                "target runtime kmod changed")
        report["runtime_source_after"] = common.canonical(runtime, work / "runtime-source-after.stderr")
        common.require_baseline(report["runtime_source_after"])
        report["command_receipts"] = {
            name + suffix: common.identity(work / (name + suffix))
            for name in commands for suffix in (".json", ".stdout", ".stderr")}
        report.update(complete=True, target_depmod_verified=True, inputs_unchanged=True,
                      module_count=84, unchanged_modules=83, target_module_info=actual_info,
                      target_imported_crcs=versions, target_depmod_exit_code=0)
    except BaseException as exc:
        report["failure"] = str(exc)
        raise
    finally:
        report["finished_utc"] = common.now()
        common.save(work / "r5-novatek-target-depmod.json", report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repo", "signed-stage", "work"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.repo, args.signed_stage, args.work)


if __name__ == "__main__":
    main()
