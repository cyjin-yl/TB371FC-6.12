#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive an R5 validation recipe without changing the frozen v9 recipe.

Only an already independently staged R5 root can be configured. The old
production/maintenance archive checkers and generic VM result gates stay
unchanged; the guest root label is changed at exactly one reviewed location.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import stage_r5_fedora as s

HERE = Path(__file__).resolve().parent
PARENT = Path("scripts/research/input/system-integration")
V9 = PARENT / "profiles/persistent-result-v9"
LABEL = "tb371fc-r5-f45"
PINS = {
    "assemble_system.py": "9d698cf253edf526fa9cd81121f5e6d3e60789020fd2f5f5fab784113e8ab0c5",
    "boot_system_vm.py": "4d1f59691bb4faccdcdbd791ae2120a89e56f7712fd63270f0a2204662842736",
    "early_initramfs.py": "f3d4871fb4347356a9254634243863a37a62f424fad186e13a4f9ad783299ced",
    "guest_result_file.py": "8d0ecba854e0d8c6303938c0253d79a72e3a03e2c1190e2ced0e17556f1a23b1",
    "guest_transient_worker.py": "2efabfc34473ff37f703f71346fa7f61d4666867bea822bb9a6c17a110693b10",
    "guest_verify_system.py": "fc2dea25edc8ac4eb6a76ea77ecff799b8abf69e8cb47548bfefaef59eaaac16",
    "initrd-domain-proof.service": "1ac451e16abf1aeefa3191972370bed649060b1d21fba302a9fff047107d2631",
    "initrd-domain-proof.sh": "3b4b65784b3c8bd13fde728e780bcd101235986c5756ac1f24000d024cd50d95",
    "probe_fd_route_v2.py": "5ccc94fdc0bda5da5bf7cab46f6a195a86e51d6d85cddebcd31602daf3b19f5b",
    "read_vm_result.py": "e28f8a031c43e096bb0741a109ab03e8b1d725341ac3a71d1e5730cd10e2393d",
    "transient_protocol.py": "9504ad6c86730caa3e9f2dd571c50b57800e9aaeac2ff5322a6b201032f50cc5",
    "verify_runtime_policy_initramfs.py": "9e36bf88b93aa3dda05ddc3ff235ab743ff4c2c80fe8e6b0694175b69e9f497a",
}
SUPPLEMENT = {
    "verify_initramfs.py": (Path("scripts/research/rootfs/verify_initramfs.py"),
                           "263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a"),
    "verify_early_policy_initramfs.py": (PARENT / "verify_early_policy_initramfs.py",
                           "58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e"),
}
POLICY = "ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798"
OLD_POLICY = "928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430"
BOOTSTRAP = "0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("frozen derivation anchor changed: " + old)
    return text.replace(old, new, 1)


def derive_sources(repo, destination):
    """Read and validate every original before creating a new recipe."""
    originals = {}
    values = {}
    for name, (rel, digest) in ({n: (V9 / n, h) for n, h in PINS.items()} | SUPPLEMENT).items():
        path = repo / rel
        originals[name] = s.check(path, digest)
        values[name] = path.read_bytes()
    original_guest = values["guest_verify_system.py"].decode()
    values["guest_verify_system.py"] = replace_once(
        original_guest, "profile['root_label'] == 'tb371fc-r4f-f45'",
        "profile['root_label'] == '" + LABEL + "'").encode()
    assemble = replace_once(values["assemble_system.py"].decode(),
                            "tb371fc-research4-vm\\n", "tb371fc-research5-vm\\n")
    # Retain the exact configure and early_initramfs entry points. Replace
    # only the image implementation that timed out copying files in v9.
    start = assemble.index("\ndef image():\n")
    end = assemble.index("\n\nif __name__ == '__main__':", start)
    assemble = assemble[:start] + "\ndef image():\n    from system_common import build_image\n    build_image()\n" + assemble[end:]
    values["assemble_system.py"] = assemble.encode()
    values["system_common.py"] = (HERE / "r5_system_common.py").read_bytes()
    stage_source = HERE / "stage_r5_fedora.py"
    stage_identity = s.identity(stage_source)
    values["stage_r5_fedora.py"] = stage_source.read_bytes()
    for name, data in values.items():
        if name.endswith(".py"):
            compile(data, name, "exec")
    destination.mkdir()
    for name, data in values.items():
        target = destination / name
        if name == "stage_r5_fedora.py":
            # qualified_stage() compares the executed staging source's full
            # identity, including its mode. Git archive extraction and the
            # recipe creator may have different umasks.
            s.copy_exact(stage_source, target, stage_identity)
        else:
            with target.open("xb") as output:
                output.write(data)
            if name.endswith(".sh"):
                target.chmod(0o755)
    result = {"schema_version": 1, "originals": originals,
              "derived": {name: s.identity(destination / name) for name in sorted(values)},
              "changed_v9_files": ["assemble_system.py", "guest_verify_system.py"],
              "separate_r5_adapter": "system_common.py",
              "old_recipe_written": False, "vm_run": False}
    s.save(destination / "derivation.json", result)
    return result


def materialize(repo, work):
    if work.parent != Path("/work") or not work.name.startswith("fedora-r5-system-"):
        raise ValueError("dedicated R5 directory required")
    s.ordinary_dir(work)
    root = work / "rootfs"
    s.ordinary_dir(root)
    stage_path = work / "r5-runtime-stage.json"
    stage = json.loads(stage_path.read_text())
    if (stage.get("complete") is not True or stage.get("kernel_release") != s.RELEASE
            or stage.get("stage_source") != s.identity(HERE / "stage_r5_fedora.py")):
        raise ValueError("stage receipt must identify this executed source")
    report = work / "root-module-report.json"
    if s.identity(report) != stage["root_module_report"]:
        raise ValueError("root-module report identity mismatch")
    candidate = repo / "docs/research/2026-11-23/boot-candidate-r5.json"
    if s.identity(candidate) != stage["candidate"]:
        raise ValueError("candidate differs from staging input")
    contract = json.loads(candidate.read_text())
    sys.path.insert(0, str(repo / "scripts/research"))
    from boot_rootfs import inspect_root_module_tree
    reread = inspect_root_module_tree(root, contract)
    if not reread["passed"]:
        raise ValueError("staged root changed before recipe construction")
    modules = s.selected_modules(contract)
    for n, identity in stage["module_tree"].items():
        if s.identity(s.under(root, "usr/lib/modules/" + s.RELEASE + "/" + n)) != identity:
            raise ValueError("staged module/index identity differs: " + n)
    firmware = s.firmware_inventory(root)
    if firmware != stage["firmware_inventory"]:
        raise ValueError("staged firmware identity differs")
    acls = {}
    for name, expected in stage["journal_acls"].items():
        raw = os.getxattr(root / "var/log/journal", name, follow_symlinks=False)
        import hashlib
        observed = hashlib.sha256(raw).hexdigest()
        if observed != expected:
            raise ValueError("journal ACL changed")
        acls[name] = {"sha256": observed, "size": len(raw), "byte_identical": True}
    if set(acls) != {"system.posix_acl_access", "system.posix_acl_default"}:
        raise ValueError("both journal ACLs required")
    runtime_files = {"usr/lib/modules/" + s.RELEASE + "/" + n: v["sha256"]
                     for n, v in stage["module_tree"].items()}
    runtime_files.update({"usr/" + n: v["sha256"] for n, v in firmware.items()})
    runtime_files["usr/share/tb371fc/stock-firmware-manifest.json"] = s.FW_PIN
    metadata = "usr/share/tb371fc/" + s.RELEASE + "/"
    mappings = {"Image": "boot/Image-" + s.RELEASE,
                "board.dtb": "boot/dtb-" + s.RELEASE + "/qcom/sm8250-lenovo-tb371fc.dtb",
                "kernel.config": "boot/config-" + s.RELEASE,
                "System.map": "boot/System.map-" + s.RELEASE}
    for name in ("research5-services-build.json", "source-manifest.json", "signing-cert.der",
                 "modules.SHA256SUMS", "kernel.btf"):
        mappings[name] = metadata + name
    artifacts = {e["path"]: {k: e[k] for k in ("bytes", "sha256", "mode")}
                 for e in contract["kernel_files"] if e["path"].startswith("artifacts/")}
    for n, target in mappings.items():
        expected = artifacts["artifacts/" + n]
        if s.identity(s.under(root, target)) != expected:
            raise ValueError("staged artifact identity differs: " + target)
        runtime_files[target] = expected["sha256"]
    autofs = [n for n in modules if n.endswith("/autofs4.ko")]
    if len(autofs) != 1:
        raise ValueError("exact signed autofs module required")
    for tool in (s.PROOT, s.QEMU):
        s.check(tool, s.PINS[tool])
    recipe = work / "recipe"
    derived = derive_sources(repo, recipe)
    env = dict(os.environ, LD_LIBRARY_PATH=s.HOST_LIBS, SYSTEMD_OFFLINE="1")
    wrapper = [str(s.PROOT), "-0", "-r", str(root), "-q", str(s.QEMU),
               "-b", "/proc", "-b", "/dev/null", "-b", "/dev/zero",
               "-b", "/dev/random", "-b", "/dev/urandom", "-w", "/"]
    signature = {}
    for field in ("signer", "sig_key", "sig_hashalgo"):
        name = "target-modinfo-" + field
        s.run(work, name, wrapper + ["/usr/sbin/modinfo", "-F", field,
              "/usr/lib/modules/" + s.RELEASE + "/" + autofs[0]], env)
        signature[field] = (work / (name + ".stdout")).read_text().strip()
        if not signature[field]:
            raise ValueError("signed module metadata absent: " + field)
    # Keep old canonical metadata intact in the independently copied root.
    old = root / "usr/share/tb371fc"
    archive = old / "archive/research1"
    archive.mkdir(parents=True)
    moved = []
    for name in ("kernel-build.json", "kernel-source-manifest.json", "modules.SHA256SUMS", "runtime.json"):
        src, dst = old / name, archive / name
        ident = s.identity(src)
        src.rename(dst)
        moved.append({"from": str(src.relative_to(root)), "to": str(dst.relative_to(root)), **ident})
    runtime = {"schema_version": 1, "kernel_release": s.RELEASE,
               "module_count": 84, "firmware_file_count": 69, "runtime_files": runtime_files,
               "old_runtime_metadata_preserved": moved,
               "physical_tablet_tested": False, "firmware_selection_verified": False}
    s.save(work / "runtime.json", runtime)
    s.copy_exact(work / "runtime.json", old / "runtime.json", s.identity(work / "runtime.json"))
    btf = artifacts["artifacts/kernel.btf"]
    profile = {
        "schema_version": 1, "profile": "research5-services-fedora45-derived-v9",
        "kernel_release": s.RELEASE, "root_label": LABEL, "module_count": 84,
        "firmware_file_count": 69, "runtime_manifest_sha256": s.identity(work / "runtime.json")["sha256"],
        "kernel_image_sha256": artifacts["artifacts/Image"]["sha256"],
        "board_dtb_sha256": artifacts["artifacts/board.dtb"]["sha256"],
        "kernel_btf_sha256": btf["sha256"], "kernel_btf_size": btf["bytes"],
        "public_signing_certificate_sha256": artifacts["artifacts/signing-cert.der"]["sha256"],
        "autofs_module_signature": signature, "validation_tasks_max": 128,
        "validation_selinux_context": "system_u:system_r:sysadm_t:s0",
        "transient_selinux_context": "system_u:system_r:sysadm_t:s0",
        "transient_worker_sha256": derived["derived"]["guest_transient_worker.py"]["sha256"],
        "guest_result_writer_sha256": derived["derived"]["guest_result_file.py"]["sha256"],
        "host_result_reader_sha256": derived["derived"]["read_vm_result.py"]["sha256"],
        "audit_printk_opt_in_required": True, "audit_printk_interval_required": 0,
        "source_policy_sha256": POLICY, "original_source_policy_sha256": OLD_POLICY,
        "actual_exported_kernel_policy_sha256_predetermined": False,
        "early_bootstrap_sha256": BOOTSTRAP, "early_bootstrap_build_policy_sha256": POLICY,
        "early_bootstrap_embeds_policy_hash": False, "early_bootstrap_expected_policy_size": 3835468,
        "early_selinux_required": True, "initramfs_root_type_required": "tmpfs",
        "kernel_rdinit_required": "/init.tmpfs", "journal_acl_check": acls,
        "staging_receipt_sha256": s.identity(stage_path)["sha256"],
        "configured_module_sig_force": False, "vm_module_signature_enforcement_required": True,
        "module_enforcement_scope": "unique module.sig_enforce=1 and actual sysfs readback",
        "scope": "generic ARM64 VM; packaged Lenovo DT is not used by QEMU",
    }
    s.save(work / "system-profile.json", profile)
    s.copy_exact(work / "system-profile.json", old / "system-profile.json",
                 s.identity(work / "system-profile.json"))
    s.save(work / "r5-recipe-materialized.json", {
        "profile_sha256": s.identity(work / "system-profile.json")["sha256"],
        "derivation_sha256": s.identity(recipe / "derivation.json")["sha256"],
        "owner_native_linux_passes_added": 0, "root_loader_built": False,
        "next": ["recipe/assemble_system.py configure", "recipe/assemble_system.py initrd",
                 "recipe/assemble_system.py image", "recipe/boot_system_vm.py label --run vm-label-01",
                 "recipe/boot_system_vm.py verify --run vm-verify-01"]})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    materialize(args.repo.resolve(strict=True), args.work)


if __name__ == "__main__":
    main()
