#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile and audit TB371FC diagnostic DTs in a private 6.12.114 overlay.

This is deliberately pinned to the frozen research1 inputs. It never loads a
driver, operates a tablet, edits that source tree, or reuses its output directory
for writing. A native-candidate check adds only the repository's historical 0002
PHY/wide-plane patch. Successful OF matching and object compilation do not imply
successful probe, native scanout, or a linkable/bootable replacement kernel.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time


FROZEN_MANIFEST = "1a8788a8e5700287870d9e9ca44ad2be8c69e6f28d927321edd89508c5501821"
FROZEN_CONFIG = "1929caefadeb28cf84174c7fe7c100ab7251b3adcfdf547b2165c229b50f66da"
QCOM = "arch/arm64/boot/dts/qcom/"
BOARD = "sm8250-lenovo-tb371fc"
PATCH = "mainline-port/backports/linux-6.12/0002-tb371fc-phy-wideplane.patch"
ANALOG_PATCH = "mainline-port/backports/linux-6.12/0003-tb371fc-v56-analog.patch"
PATCH_FILES = (
    "drivers/gpu/drm/msm/dsi/phy/dsi_phy.h",
    "drivers/gpu/drm/msm/dsi/phy/dsi_phy.c",
    "drivers/gpu/drm/msm/dsi/phy/dsi_phy_7nm.c",
    "drivers/gpu/drm/msm/disp/dpu1/dpu_hw_catalog.h",
    "drivers/gpu/drm/msm/disp/dpu1/dpu_kms.c",
    "drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_6_0_sm8250.h",
)
OBJECTS = (
    "drivers/gpu/drm/msm/dsi/phy/dsi_phy.o",
    "drivers/gpu/drm/msm/dsi/phy/dsi_phy_7nm.o",
    "drivers/gpu/drm/msm/disp/dpu1/dpu_kms.o",
    "drivers/gpu/drm/msm/disp/dpu1/dpu_hw_catalog.o",
    "drivers/gpu/drm/msm/disp/dpu1/dpu_plane.o",
)
# The selectors below are explicitly scoped; this is not a general DT validator.
DRIVERS = {
    "mdss": ("drivers/gpu/drm/msm/msm_mdss.c", "CONFIG_DRM_MSM_MDSS",
             ("qcom,sm8250-mdss",)),
    "dpu": ("drivers/gpu/drm/msm/disp/dpu1/dpu_kms.c", "CONFIG_DRM_MSM_DPU",
            ("qcom,sm8250-dpu", "lenovo,tb371fc-dpu")),
    "dsi_host": ("drivers/gpu/drm/msm/dsi/dsi.c", "CONFIG_DRM_MSM_DSI",
                 ("qcom,mdss-dsi-ctrl",)),
    "dsi_phy": ("drivers/gpu/drm/msm/dsi/phy/dsi_phy.c", "CONFIG_DRM_MSM_DSI_7NM_PHY",
                ("qcom,dsi-phy-7nm", "lenovo,tb371fc-dsi-phy-7nm")),
    "panel": ("drivers/gpu/drm/panel/panel-novatek-nt36523.c", "CONFIG_DRM_PANEL_NOVATEK_NT36523",
              ("lenovo,tb371fc-tianma-nt36532", "lenovo,tb371fc-boe-nt36532")),
    "backlight": ("drivers/video/backlight/tb371fc-ktz8866.c", "CONFIG_BACKLIGHT_TB371FC_KTZ8866",
                  ("lenovo,tb371fc-ktz8866",)),
    "spi": ("drivers/spi/spi-geni-qcom.c", "CONFIG_SPI_QCOM_GENI", ("qcom,geni-spi",)),
    "i2c": ("drivers/i2c/busses/i2c-qcom-geni.c", "CONFIG_I2C_QCOM_GENI", ("qcom,geni-i2c",)),
    "touch": ("drivers/input/touchscreen/nt36523/nt36xxx.c", "CONFIG_TOUCHSCREEN_NT36523_SPI",
              ("novatek,NVT-ts-spi",)),
}
MODULES = {
    "touch": "drivers/input/touchscreen/nt36523/nt36523_ts.ko",
    "panel": "drivers/gpu/drm/panel/panel-novatek-nt36523.ko",
    "backlight": "drivers/video/backlight/tb371fc-ktz8866.ko",
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(path):
    return {"sha256": digest(path), "size": Path(path).stat().st_size}


def run(command, output, name, cwd=None, check=True):
    command = [str(arg) for arg in command]
    print("+", " ".join(command), flush=True)
    started = time.monotonic()
    log = output / (name + ".log")
    with log.open("x") as stream:
        result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
    record = {"command": command, "cwd": str(cwd) if cwd else None,
              "exit_code": result.returncode, "elapsed_seconds": time.monotonic() - started,
              "log": log.name, "log_sha256": digest(log)}
    print(json.dumps(record), flush=True)
    if check and result.returncode:
        print(log.read_text()[-12000:], flush=True)
        raise RuntimeError(f"{name} failed: {result.returncode}")
    return record


def overlay(source, destination, private):
    """Copy every writable leaf; symlink only entries this task never edits."""
    def copy_branch(relative):
        (destination / relative).mkdir()
        for child in (source / relative).iterdir():
            name = (relative / child.name).as_posix()
            target = destination / name
            if name in private:
                shutil.copyfile(child, target)
            elif any(entry.startswith(name + "/") for entry in private):
                if not child.is_dir():
                    raise RuntimeError("non-directory source prefix: " + name)
                copy_branch(Path(name))
            else:
                target.symlink_to(child.resolve(), target_is_directory=child.is_dir())
    copy_branch(Path("."))


def read_fdt(path):
    """Read the standard structure/string blocks, with bounds checks."""
    data = path.read_bytes()
    if len(data) < 40:
        raise ValueError("short FDT")
    magic, total, off, strings, _, version, _, _, slen, size = struct.unpack_from(">10I", data)
    if magic != 0xD00DFEED or version < 17 or total > len(data):
        raise ValueError("unexpected FDT header")
    if off + size > total or strings + slen > total:
        raise ValueError("FDT block outside file")
    limit, string_limit = off + size, strings + slen
    nodes, stack = {}, []
    while off + 4 <= limit:
        token = struct.unpack_from(">I", data, off)[0]
        off += 4
        if token == 1:
            end = data.index(b"\0", off, limit)
            name = data[off:end].decode("ascii")
            off = (end + 4) & ~3
            node = (stack[-1].rstrip("/") + "/" + name) if stack else "/"
            if node in nodes:
                raise ValueError("duplicate FDT node")
            nodes[node] = {}
            stack.append(node)
        elif token == 2:
            if not stack:
                raise ValueError("unbalanced FDT node")
            stack.pop()
        elif token == 3:
            if off + 8 > limit or not stack:
                raise ValueError("bad FDT property")
            length, nameoff = struct.unpack_from(">2I", data, off)
            off += 8
            if off + length > limit or nameoff >= slen:
                raise ValueError("FDT property outside block")
            end = data.index(b"\0", strings + nameoff, string_limit)
            name = data[strings + nameoff:end].decode("ascii")
            nodes[stack[-1]][name] = data[off:off + length]
            off = (off + length + 3) & ~3
        elif token == 4:
            continue
        elif token == 9:
            if stack:
                raise ValueError("unclosed FDT node")
            return nodes
        else:
            raise ValueError("unexpected FDT token")
    raise ValueError("missing FDT end")


def strings(raw):
    return raw.rstrip(b"\0").decode("ascii").split("\0") if raw else []


def tables(source):
    result = {}
    for name, (relative, config, selectors) in DRIVERS.items():
        data = (source / relative).read_text()
        blocks = list(re.finditer(r"(?:static\s+)?(?:const\s+)?struct\s+of_device_id\s+(\w+)\s*\[\s*\]\s*=\s*\{(.*?)\n\};", data, re.S))
        if not blocks:
            raise RuntimeError("no OF table found in " + relative)
        result[name] = {
            "source": relative, "source_sha256": digest(source / relative), "config": config,
            "scope_selectors": selectors,
            "tables": [{"name": block.group(1),
                        "line": data[:block.start()].count("\n") + 1,
                        "entries": re.findall(r'\.compatible\s*=\s*"([^"]+)"', block.group(2)),
                        "driver_references_table": bool(re.search(
                            r"\.of_match_table\s*=\s*(?:of_match_ptr\s*\(\s*)?" + re.escape(block.group(1)) + r"\b", data))}
                       for block in blocks],
        }
    return result


def binding_checks(nodes, matches, config):
    checks = []
    for path, props in nodes.items():
        compatible = strings(props.get("compatible", b""))
        relevant = [name for name, item in matches.items()
                    if set(item["scope_selectors"]).intersection(compatible)]
        if not relevant:
            continue
        ancestors = ["/"] + ["/" + "/".join(path.strip("/").split("/")[:n])
                               for n in range(1, len(path.strip("/").split("/")) + 1)]
        unavailable = [p for p in ancestors if nodes[p].get("status", b"okay\0") not in (b"okay\0", b"ok\0")]
        for name in relevant:
            item = matches[name]
            registered = {entry for table in item["tables"] if table["driver_references_table"]
                          for entry in table["entries"]}
            found = [entry for entry in compatible if entry in registered]
            enabled_config = config.get(item["config"], "n")
            checks.append({"node": path, "driver": name, "compatible": compatible,
                           "status": strings(props.get("status", b"okay\0"))[0],
                           "unavailable_ancestors": unavailable, "effectively_available": not unavailable,
                           "config": item["config"], "config_value": enabled_config,
                           "matched_compatible": found,
                           "static_of_match_available": bool(found) and enabled_config in ("y", "m"),
                           "runtime_probe_tested": False})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--work", type=Path, default=Path("/work"))
    parser.add_argument("--output", type=Path, default=Path("/work/dtb-profile-qualification"))
    args = parser.parse_args()
    repo, work, output = args.repo.resolve(), args.work.resolve(), args.output.resolve()
    source, kernel_out, artifacts = work / "linux-6.12.114-research1", work / "kernel-out", work / "artifacts"
    for protected in (repo, source, kernel_out, artifacts):
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise SystemExit("output overlaps a protected input: " + str(protected))
    if output.exists() or output.is_symlink():
        raise SystemExit("retain existing output; select a new --output directory")
    manifest_file = artifacts / "source-manifest.json"
    if digest(manifest_file) != FROZEN_MANIFEST or digest(kernel_out / ".config") != FROZEN_CONFIG:
        raise SystemExit("this script is pinned to the recorded research1 source/config")
    frozen = json.loads(manifest_file.read_text())
    for relative, expected in frozen["assembled_files"].items():
        if digest(source / relative) != expected:
            raise SystemExit("prepared input changed: " + relative)
    patch = repo / PATCH
    changed = re.findall(r"^\+\+\+ b/(.+)$", patch.read_text(), re.M)
    if set(changed) != set(PATCH_FILES) or len(changed) != len(PATCH_FILES):
        raise SystemExit("unexpected patch target set")
    protected_files = set(frozen["assembled_files"]) | set(PATCH_FILES) | {
        "drivers/gpu/drm/msm/disp/dpu1/dpu_plane.c", "drivers/gpu/drm/msm/dsi/dsi_host.c",
        "drivers/gpu/drm/msm/disp/dpu1/dpu_rm.c", "drivers/gpu/drm/msm/disp/dpu1/dpu_encoder.c",
        "drivers/gpu/drm/msm/disp/dpu1/dpu_encoder_phys_vid.c", "drivers/gpu/drm/msm/disp/dpu1/dpu_hw_catalog.c",
    } | {item[0] for item in DRIVERS.values()}
    before = {relative: digest(source / relative) for relative in sorted(protected_files)}
    primary_before = {name: identity(artifacts / name) for name in ("Image", "board.dtb", "kernel.config", "source-manifest.json")}
    output.mkdir(parents=True)
    record = {"schema_version": 1, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "isolated diagnostic DT and affected-object compile; static OF match audit only",
              "qualifier_script_sha256": digest(Path(__file__)),
              "source": str(source), "frozen_manifest_sha256": FROZEN_MANIFEST,
              "frozen_config_sha256": FROZEN_CONFIG, "source_manifest": frozen,
              "physical_hardware_tested": False, "drivers_loaded": False,
              "schema_validation_run": False, "replacement_kernel_linked": False,
              "source_before": before, "primary_artifacts_before": primary_before,
              "native_patch": {"path": PATCH, **identity(patch)}, "jobs": {}, "profiles": {}}
    config = dict(re.findall(r"^(CONFIG_\w+)=(.*)$", (kernel_out / ".config").read_text(), re.M))
    record["resolved_config"] = {item[1]: config.get(item[1], "n") for item in DRIVERS.values()}
    record["resolved_config"].update({name: config.get(name, "n") for name in
                                      ("CONFIG_QCOM_GPI_DMA", "CONFIG_PINCTRL_SM8250", "CONFIG_DRM_MSM", "CONFIG_OF")})
    result_code = 0
    try:
        baseline_tables = tables(source)
        record["baseline_tables"] = baseline_tables
        private = set(PATCH_FILES) | {"Makefile", QCOM + "Makefile", QCOM + BOARD + ".dts"}
        candidate = output / "source"
        overlay(source, candidate, private)
        for kind in ("touch-test", "display-test"):
            name = BOARD + "-" + kind + ".dts"
            original = repo / "mainline-port" / QCOM / name
            target = candidate / QCOM / name
            if target.exists() or target.is_symlink():
                raise RuntimeError("diagnostic profile already exists in baseline: " + name)
            shutil.copyfile(original, target)
            record["profiles"][kind] = {"source": original.relative_to(repo).as_posix(),
                                        "source_sha256": digest(original), "source_modified": False}
        with (candidate / QCOM / "Makefile").open("a") as stream:
            for kind in ("touch-test", "display-test"):
                stream.write(f"\ndtb-$(CONFIG_ARCH_QCOM) += {BOARD}-{kind}.dtb\n")
        out = output / "out"
        out.mkdir()
        shutil.copyfile(kernel_out / ".config", out / ".config")
        make = ["make", "-C", candidate, "O=" + str(out), "ARCH=arm64", "LLVM=1", "-j2"]
        record["jobs"]["config"] = run(make + ["olddefconfig"], output, "config")
        record["isolated_config_sha256"] = digest(out / ".config")
        if record["isolated_config_sha256"] != FROZEN_CONFIG:
            raise RuntimeError("isolated olddefconfig changed the frozen configuration")
        record["jobs"]["dtbs"] = run(make + ["V=1"] +
            ["qcom/" + BOARD + "-" + kind + ".dtb" for kind in ("touch-test", "display-test")], output, "dtbs")
        for kind, profile in record["profiles"].items():
            dtb = out / QCOM / (BOARD + "-" + kind + ".dtb")
            nodes = read_fdt(dtb)
            profile.update({"dtb": dtb.relative_to(output).as_posix(), **identity(dtb),
                            "dtc_compiled": True, "model": strings(nodes["/"]["model"])[0],
                            "baseline_binding_checks": binding_checks(nodes, baseline_tables, config)})
        check = run(["git", "apply", "--recount", "--check", patch], output, "native-patch-check", candidate, False)
        record["jobs"]["native_patch_check"] = check
        if check["exit_code"]:
            record["native_candidate_status"] = "blocked_patch_context"
            result_code = 1
        else:
            record["jobs"]["native_patch_apply"] = run(["git", "apply", "--recount", patch], output, "native-patch-apply", candidate)
            record["candidate_source_files"] = {name: digest(candidate / name) for name in PATCH_FILES}
            candidate_tables = tables(candidate)
            record["candidate_tables"] = candidate_tables
            for kind, profile in record["profiles"].items():
                profile["candidate_binding_checks"] = binding_checks(read_fdt(output / profile["dtb"]), candidate_tables, config)
            # Report applicability of the separate historical analog patch;
            # do not silently add it to this one-patch candidate.
            record["analog_patch_not_applied"] = {"path": ANALOG_PATCH, **identity(repo / ANALOG_PATCH)}
            record["jobs"]["analog_patch_check_only"] = run(["git", "apply", "--recount", "--check", repo / ANALOG_PATCH],
                output, "analog-patch-check-only", candidate, False)
            record["jobs"]["objects"] = run(make + ["V=1", *OBJECTS], output, "objects")
            record["objects"] = {}
            for name in OBJECTS:
                path = out / name
                header = path.read_bytes()[:20]
                if header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != 183:
                    raise RuntimeError("object is not AArch64 ELF: " + name)
                record["objects"][name] = {**identity(path), "elf_aarch64": True}
            record["native_candidate_status"] = "affected_objects_compiled_hardware_untested"
        release = "6.12.114-tb371fc-research1"
        record["existing_module_aliases"] = {}
        for name, relative in MODULES.items():
            module = work / "modules/lib/modules" / release / "kernel" / relative
            aliases = subprocess.check_output(["modinfo", "-F", "alias", str(module)], text=True, timeout=20).splitlines()
            record["existing_module_aliases"][name] = {"path": str(module), **identity(module), "aliases": aliases}
        record["compiler"] = subprocess.check_output(["clang", "--version"], text=True, timeout=20).splitlines()
    except Exception as exc:
        record["error"] = type(exc).__name__ + ": " + str(exc)
        result_code = 1
    finally:
        record["source_after"] = {name: digest(source / name) for name in sorted(protected_files)}
        record["primary_artifacts_after"] = {name: identity(artifacts / name) for name in primary_before}
        record["protected_source_unchanged"] = record["source_after"] == before
        record["primary_artifacts_unchanged"] = record["primary_artifacts_after"] == primary_before
        record["primary_output_config_unchanged"] = digest(kernel_out / ".config") == FROZEN_CONFIG
        if not all(record[key] for key in ("protected_source_unchanged", "primary_artifacts_unchanged", "primary_output_config_unchanged")):
            result_code = 1
        record["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record["qualification_command_exit"] = result_code
        destination = output / "diagnostic-dt-profiles.json"
        destination.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"manifest": str(destination), "sha256": digest(destination),
                          "exit_code": result_code, "physical_hardware_tested": False}), flush=True)
    return result_code


if __name__ == "__main__":
    raise SystemExit(main())
