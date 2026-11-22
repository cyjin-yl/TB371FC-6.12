#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Qualify research2-display artifacts and its completed generic VM smoke run.

Reuses the frozen complete module-inventory check with the new explicit release.
No module is loaded, and a generic virt boot never becomes native-display proof.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import subprocess

import inspect_kernel as module_check
import prepare_research2_display as profile
import smoke_qemu as controller


def command(args):
    return subprocess.check_output(list(map(str, args)), text=True, timeout=30).strip()


def identity(path):
    return {"sha256": profile.digest(path), "size": path.stat().st_size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--work", type=Path, default=Path("/work/research2-display"))
    args = parser.parse_args()
    repo, work = args.repo.resolve(), args.work.resolve()
    manifest = profile.verify_work(repo, work)
    for imported, relative in ((module_check, "scripts/research/build/inspect_kernel.py"),
                               (controller, "scripts/research/build/smoke_qemu.py")):
        if profile.digest(Path(imported.__file__)) != profile.FROZEN_HELPERS[relative]:
            raise SystemExit("imported frozen helper differs: " + relative)
    artifacts = work / "artifacts"
    destination = artifacts / "research2-display-build.json"
    if destination.exists() or destination.is_symlink():
        raise SystemExit("retain existing candidate evidence; do not overwrite a qualification")
    if (artifacts / "kernel.release").read_text().strip() != profile.RELEASE:
        raise SystemExit("artifact release mismatch")
    if profile.digest(artifacts / "source-manifest.json") != profile.digest(work / "source-manifest.json"):
        raise SystemExit("artifact/source manifest mismatch")
    if profile.digest(artifacts / "source-manifest-research1.json") != profile.BASE_MANIFEST_SHA256:
        raise SystemExit("preserved baseline manifest mismatch")
    image = (artifacts / "Image").read_bytes()
    if image[56:60] != b"ARM\x64":
        raise SystemExit("not an ARM64 Image")
    for compatible in (b"lenovo,tb371fc-dpu\0", b"lenovo,tb371fc-dsi-phy-7nm\0"):
        if compatible not in image:
            raise SystemExit("linked Image lacks a native prerequisite compatible string")
    dtb = artifacts / "board.dtb"
    if profile.digest(dtb) != profile.DTB_SHA256:
        raise SystemExit("candidate DT differs from the qualified versioned wrapper")
    compatibles = command(["fdtget", "-t", "s", dtb, "/", "compatible"]).split()
    framebuffer = "/chosen/framebuffer@9c000000"
    if compatibles != ["lenovo,tb371fc", "qcom,sm8250"]:
        raise SystemExit("incorrect native DT root compatible")
    if command(["fdtget", "-t", "s", dtb, "/chosen", "stdout-path"]) != framebuffer:
        raise SystemExit("incorrect framebuffer stdout path")
    if "framebuffer0" in command(["fdtget", "-l", dtb, "/chosen"]).splitlines():
        raise SystemExit("orphan framebuffer node remains")
    mdss = "/soc@0/display-subsystem@ae00000"
    native_nodes = {"mdss": mdss, "dpu": mdss + "/display-controller@ae01000", "phy0": mdss + "/phy@ae94400",
                    "phy1": mdss + "/phy@ae96400", "dsi0": mdss + "/dsi@ae94000",
                    "dsi1": mdss + "/dsi@ae96000", "panel": mdss + "/dsi@ae94000/panel@0"}
    dt_summary = {"model": command(["fdtget", "-t", "s", dtb, "/", "model"]),
                  "root_compatible": compatibles, "stdout_path": framebuffer, "nodes": {}}
    for name, node in native_nodes.items():
        properties = set(command(["fdtget", "-p", dtb, node]).splitlines())
        # OF treats an absent status property as available.
        status = command(["fdtget", "-t", "s", dtb, node, "status"]) if "status" in properties else "okay"
        if status not in ("okay", "ok"):
            raise SystemExit("native diagnostic node not enabled: " + name)
        dt_summary["nodes"][name] = {"path": node, "status": status, "status_property_present": "status" in properties,
                                    "compatible": command(["fdtget", "-t", "s", dtb, node, "compatible"]).split()}
    # The selected display-only wrapper deliberately does not merge touch-test.
    # Record the actual compiled nodes; driver availability is not touch enablement.
    spi14 = "/soc@0/geniqup@8c0000/spi@880000"
    dt_summary["input_nodes"] = {}
    for name, node in (("spi14", spi14), ("touchscreen", spi14 + "/touchscreen@0")):
        status = command(["fdtget", "-t", "s", dtb, node, "status"])
        if status != "disabled":
            raise SystemExit("display-only candidate unexpectedly changed the touch profile")
        dt_summary["input_nodes"][name] = {"path": node, "status": status,
            "compatible": command(["fdtget", "-t", "s", dtb, node, "compatible"]).split()}
    before = (work / "kernel-out/resolved-research1.config").read_text().splitlines()
    after = (artifacts / "kernel.config").read_text().splitlines()
    if profile.digest(work / "kernel-out/resolved-research1.config") != profile.BASE_CONFIG_SHA256:
        raise SystemExit("baseline resolved configuration changed")
    if [l for l in before if not l.startswith("CONFIG_LOCALVERSION=")] != [l for l in after if not l.startswith("CONFIG_LOCALVERSION=")]:
        raise SystemExit("configuration changed beyond release suffix")
    config = dict(line.split("=", 1) for line in after if line.startswith("CONFIG_") and "=" in line)
    required = {"CONFIG_LOCALVERSION": '"' + profile.LOCALVERSION + '"', "CONFIG_DRM_MSM": "y",
                "CONFIG_DRM_MSM_DPU": "y", "CONFIG_DRM_MSM_DSI": "y", "CONFIG_DRM_MSM_DSI_7NM_PHY": "y",
                "CONFIG_TOUCHSCREEN_NT36523_SPI": "m", "CONFIG_DRM_PANEL_NOVATEK_NT36523": "m",
                "CONFIG_BACKLIGHT_TB371FC_KTZ8866": "m", "CONFIG_I2C_HID_OF": "y",
                "CONFIG_VIDEO_QCOM_VENUS": "m", "CONFIG_FW_LOADER_COMPRESS_XZ": "y", "CONFIG_FW_LOADER_COMPRESS_ZSTD": "y"}
    if any(config.get(name) != value for name, value in required.items()):
        raise SystemExit("resolved candidate Kconfig prerequisite differs")
    if config.get("CONFIG_MODULE_COMPRESS_ALL", "n") == "y":
        raise SystemExit("this qualification expects uncompressed modules")
    modules, inventory = module_check.module_inventory(work, profile.RELEASE)
    if len(modules) != 83:
        raise SystemExit("unexpected module count for the unchanged research1 configuration")
    selected, checksums = [], []
    module_root = work / "modules"
    for path in modules:
        relative = path.relative_to(module_root).as_posix()
        data = path.read_bytes()
        if data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
            raise SystemExit("module is not AArch64 ELF: " + relative)
        vermagic = command(["modinfo", "-F", "vermagic", path])
        if not vermagic.split() or vermagic.split()[0] != profile.RELEASE:
            raise SystemExit("module release mismatch: " + relative)
        checksums.append(profile.digest(path) + "  " + relative + "\n")
        if any(part in relative for part in ("nt36523/", "tb371fc-ktz", "panel-novatek", "/venus/", "ath11k", "sm8250", "qcom-rpmh")):
            selected.append({"path": relative, **identity(path), "vermagic": vermagic,
                             "aliases": command(["modinfo", "-F", "alias", path]).splitlines(),
                             "firmware_names": command(["modinfo", "-F", "firmware", path]).splitlines()})
    qemu_file, serial_file = work / "qemu-smoke/result.json", work / "qemu-smoke/serial.log"
    qemu = json.loads(qemu_file.read_text())
    expected_image = profile.digest(artifacts / "Image")
    observed = controller.observed_lines(serial_file.read_bytes(), profile.RELEASE)
    if (qemu.get("controller_result") != "pass" or qemu.get("expected_release") != profile.RELEASE
            or qemu.get("image_sha256") != expected_image or qemu.get("serial_sha256") != profile.digest(serial_file)
            or qemu.get("source_manifest_sha256") != profile.digest(artifacts / "source-manifest.json")
            or not all(observed[name] for name in ("release", "machine", "el0_marker")) or observed["guest_error"]
            or not qemu.get("cleanup", {}).get("child_reaped") or qemu.get("physical_hardware_tested") is not False):
        raise SystemExit("generic VM qualification does not match this candidate")
    (artifacts / "modules.SHA256SUMS").write_text("".join(checksums))
    packages = command(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"])
    (artifacts / "builder-packages.tsv").write_text(packages + "\n")
    jobs = {}
    for name in ("research2-display-prepare", "research2-display-build", "research2-display-qemu"):
        record, log = work.parent / (name + ".json"), work.parent / (name + ".log")
        if record.exists():
            jobs[name] = {"result": json.loads(record.read_text()), "result_sha256": profile.digest(record),
                          "log_sha256": profile.digest(log)}
    names = ("Image", "board.dtb", "kernel.config", "Module.symvers", "System.map", "kernel.release", "build-state.json",
             "source-manifest.json", "source-manifest-research1.json", "modules.SHA256SUMS", "builder-packages.tsv")
    files = {name: identity(artifacts / name) for name in names}
    result = {"schema_version": 1, "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "profile": "research2-display", "kernel_release": profile.RELEASE, "files": files,
              "native_dtb": dt_summary, "native_compatible_strings_in_image": True,
              "only_config_change": {"CONFIG_LOCALVERSION": profile.LOCALVERSION}, "resolved_config": required,
              "source_manifest": manifest, "baseline_source_manifest": json.loads((work / "source-manifest-research1.json").read_text()),
              "module_inventory": inventory, "module_count": len(modules), "selected_modules": selected,
              "all_modules_elf_aarch64": True, "all_module_vermagic_matches": True,
              "qemu": {"result_sha256": profile.digest(qemu_file), "serial_sha256": profile.digest(serial_file), "result": qemu},
              "jobs": jobs, "compiler": command(["clang", "--version"]).splitlines(), "linker": command(["ld.lld", "--version"]),
              "scope": "complete Image/modules/native diagnostic DT build plus generic virt boot; no native hardware validation",
              "physical_hardware_tested": False, "native_display_tested": False,
              "bit_for_bit_independent_reproducibility_proven": False,
              "reproducibility_limit": "APT is recorded rather than snapshot-pinned; a fresh private module-signing key affects output bytes"}
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    index = {**files, destination.name: identity(destination)}
    (artifacts / "qualified-artifacts.SHA256SUMS").write_text("".join(
        value["sha256"] + "  " + name + "\n" for name, value in sorted(index.items())))
    print(json.dumps({"kernel_release": profile.RELEASE, "module_count": len(modules),
                      "evidence_sha256": profile.digest(destination), "physical_hardware_tested": False}))


if __name__ == "__main__":
    main()
