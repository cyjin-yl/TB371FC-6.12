#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Qualify the 6.12 framebuffer wrapper after the isolated driver/DT audit.

Uses only that audit's private source/output. The research1 tree/output and
historical DTS files remain inputs. No hardware access or driver loading occurs.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import re
import shutil
import struct
import time

import qualify_dt_profiles as core


WRAPPER = "mainline-port/backports/linux-6.12/sm8250-lenovo-tb371fc-display-test-6.12.dts"
WRAPPER_SHA256 = "8cac3ffe34d6eaf3ee43ea1c63b4395fd6a38325ccb5f289283da3e234bfe1f7"
PATCH_SHA256 = "839699e055d8959232f2912895cbd71f5fd85f3e07a1d3f033a1fd728e08ce56"


def cells(raw):
    if len(raw) % 4:
        raise ValueError("non-cell property")
    return list(struct.unpack(">" + "I" * (len(raw) // 4), raw))


def references(nodes, raw, cell_property=None):
    phandles = {cells(props["phandle"])[0]: path for path, props in nodes.items() if "phandle" in props}
    values, result, offset = cells(raw), [], 0
    while offset < len(values):
        if values[offset] == 0:
            result.append({"provider": None, "args": []})
            offset += 1
            continue
        provider = phandles[values[offset]]
        count = cells(nodes[provider][cell_property])[0] if cell_property else 0
        if offset + 1 + count > len(values):
            raise ValueError("short provider specifier")
        result.append({"provider": provider, "args": values[offset + 1:offset + 1 + count]})
        offset += 1 + count
    return result


def gpio_supplies(nodes):
    result = {}
    for path, props in nodes.items():
        for name, raw in props.items():
            if name == "gpios" or name.endswith("-gpios"):
                result[path + ":" + name] = references(nodes, raw, "#gpio-cells")
            elif name.endswith("-supply"):
                result[path + ":" + name] = references(nodes, raw)
    return result


def block(text, name):
    match = re.search(r"\b" + re.escape(name) + r"\s*=\s*\{(.*?)\n\};", text, re.S)
    if not match:
        raise ValueError("source initializer missing: " + name)
    return match.group(1)


def fields(text):
    return dict(re.findall(r"\.(\w+)\s*=\s*([^\n]+),", text))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--qualification", type=Path, default=Path("/work/dtb-profile-qualification-v2"))
    parser.add_argument("--output", type=Path, default=Path("/work/dtb-native-612-qualification"))
    parser.add_argument("--wrapper", type=Path, help="explicit staging copy; content hash is pinned")
    parser.add_argument("--wait-seconds", type=int, default=0,
                        help="bounded wait for an already-running prerequisite job")
    args = parser.parse_args()
    if not 0 <= args.wait_seconds <= 1800:
        parser.error("wait must be between 0 and 1800 seconds")
    repo, qualification, output = args.repo.resolve(), args.qualification.resolve(), args.output.resolve()
    manifest_path = qualification / "diagnostic-dt-profiles.json"
    deadline = time.monotonic() + args.wait_seconds
    while True:
        try:
            previous = json.loads(manifest_path.read_text())
            break
        except (FileNotFoundError, json.JSONDecodeError):
            if time.monotonic() >= deadline:
                raise SystemExit("completed prerequisite manifest is unavailable")
            time.sleep(min(5, max(0, deadline - time.monotonic())))
    if (previous.get("qualification_command_exit") != 0 or
            previous.get("native_candidate_status") != "affected_objects_compiled_hardware_untested"):
        raise SystemExit("require completed isolated driver/DT qualification")
    if core.digest(Path(core.__file__)) != previous["qualifier_script_sha256"]:
        raise SystemExit("imported qualifier differs from the recorded run")
    source, out = qualification / "source", qualification / "out"
    original = Path(previous["source"])
    for protected in (repo, source, out, original, original.parent / "kernel-out", original.parent / "artifacts"):
        if output.is_relative_to(protected) or protected.is_relative_to(output):
            raise SystemExit("new output overlaps an input")
    if output.exists() or output.is_symlink():
        raise SystemExit("retain existing output; choose a new --output")
    for name, expected in previous["candidate_source_files"].items():
        if core.digest(source / name) != expected:
            raise SystemExit("candidate driver source changed: " + name)
    if (core.digest(repo / core.PATCH) != PATCH_SHA256 or
            previous["native_patch"]["sha256"] != PATCH_SHA256):
        raise SystemExit("native prerequisite patch differs")
    wrapper = args.wrapper.resolve() if args.wrapper else repo / WRAPPER
    if core.digest(wrapper) != WRAPPER_SHA256 or core.digest(out / ".config") != core.FROZEN_CONFIG:
        raise SystemExit("wrapper/config differs from this qualification profile")
    qcom = source / core.QCOM
    for parent in (source, source / "arch", source / "arch/arm64", source / "arch/arm64/boot", source / "arch/arm64/boot/dts", qcom):
        if parent.is_symlink():
            raise SystemExit("refuse to write through source-directory symlink")
    makefile = qcom / "Makefile"
    if makefile.is_symlink():
        raise SystemExit("QCOM Makefile must be private")
    filename = Path(WRAPPER).name
    target = qcom / filename
    if target.exists() or target.is_symlink():
        raise SystemExit("wrapper target already exists; retain earlier evidence")
    historical = previous["profiles"]["display-test"]
    old_dtb = qualification / historical["dtb"]
    if core.digest(old_dtb) != historical["sha256"]:
        raise SystemExit("historical comparison DTB changed")
    old_nodes = core.read_fdt(old_dtb)
    real, orphan = "/chosen/framebuffer@9c000000", "/chosen/framebuffer0"
    if (orphan not in old_nodes or "compatible" in old_nodes[orphan] or "reg" in old_nodes[orphan]
            or core.strings(old_nodes[real].get("compatible", b"")) != ["simple-framebuffer"]):
        raise SystemExit("historical framebuffer structure differs from the audited defect")
    output.mkdir(parents=True)
    result = {"schema_version": 1, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "profile": "Linux 6.12.114 research1 plus historical 0002; versioned display-DT wrapper",
              "prior_qualification": str(manifest_path), "prior_qualification_sha256": core.digest(manifest_path),
              "qualifier_script_sha256": core.digest(Path(__file__)),
              "wrapper": {"path": WRAPPER, **core.identity(wrapper)},
              "native_patch": {"path": core.PATCH, **core.identity(repo / core.PATCH)},
              "historical_dts_sha256": historical["source_sha256"],
              "historical_dtb_sha256": historical["sha256"],
              "frozen_source_manifest_sha256": core.FROZEN_MANIFEST,
              "frozen_config_sha256": core.FROZEN_CONFIG,
              "physical_hardware_tested": False, "drivers_loaded": False,
              "replacement_kernel_linked": False, "schema_validation_run": False,
              "private_makefile_before_sha256": core.digest(makefile)}
    status = 0
    try:
        shutil.copyfile(wrapper, target)
        with makefile.open("a") as stream:
            stream.write(f"\ndtb-$(CONFIG_ARCH_QCOM) += {Path(filename).stem}.dtb\n")
        result["compile"] = core.run(["make", "-C", source, "O=" + str(out), "ARCH=arm64", "LLVM=1", "-j2", "V=1",
                                      "qcom/" + Path(filename).stem + ".dtb"], output, "wrapper-dtb")
        dtb = out / core.QCOM / (Path(filename).stem + ".dtb")
        nodes = core.read_fdt(dtb)
        compatible = core.strings(nodes["/"]["compatible"])
        stdout = core.strings(nodes["/chosen"]["stdout-path"])[0]
        simple = [name for name, props in nodes.items()
                  if "simple-framebuffer" in core.strings(props.get("compatible", b""))]
        assert compatible == ["lenovo,tb371fc", "qcom,sm8250"]
        assert orphan not in nodes and simple == [real] and stdout == real
        assert all(nodes[real][key] == old_nodes[real][key] for key in ("reg", "width", "height", "stride", "format"))
        clocks = references(nodes, nodes[real]["clocks"], "#clock-cells")
        domains = references(nodes, nodes[real]["power-domains"], "#power-domain-cells")
        assert clocks == references(old_nodes, old_nodes[orphan]["clocks"], "#clock-cells")
        assert domains == references(old_nodes, old_nodes[orphan]["power-domains"], "#power-domain-cells")
        assert gpio_supplies(nodes) == gpio_supplies(old_nodes)
        checks = core.binding_checks(nodes, core.tables(source), previous["resolved_config"])
        missing = [item for item in checks if item["effectively_available"] and not item["static_of_match_available"]]
        assert not missing, "missing relevant compatible/config match"
        result.update({"dtb": {"path": str(dtb), **core.identity(dtb)}, "root_compatible": compatible,
                       "stdout_path": stdout, "simple_framebuffer_nodes": simple, "orphan_node_absent": True,
                       "framebuffer_reg_cells": cells(nodes[real]["reg"]),
                       "clock_references": clocks, "power_domain_references": domains,
                       "clock_domain_specifiers_preserved": True, "framebuffer_geometry_preserved": True,
                       "gpio_supply_specifiers_preserved": True, "binding_checks": checks})
        catalog = "drivers/gpu/drm/msm/disp/dpu1/catalog/dpu_6_0_sm8250.h"
        baseline, candidate = (original / catalog).read_text(), (source / catalog).read_text()
        assert block(baseline, "sm8250_dpu_caps") == block(candidate, "sm8250_dpu_caps")
        assert block(baseline, "dpu_sm8250_cfg") == block(candidate, "dpu_sm8250_cfg")
        expected_caps = fields(block(candidate, "sm8250_dpu_caps"))
        expected_caps["max_linewidth"] = "1880"
        assert expected_caps == fields(block(candidate, "tb371fc_dpu_caps"))
        expected_cfg = fields(block(candidate, "dpu_sm8250_cfg"))
        expected_cfg["caps"] = "&tb371fc_dpu_caps"
        assert expected_cfg == fields(block(candidate, "dpu_tb371fc_cfg"))
        result["catalog_contract"] = {"generic_caps_and_resources_unchanged": True,
                                      "board_caps_only_linewidth_differs": True,
                                      "board_resources_only_caps_pointer_differs": True,
                                      "generic_linewidth_expression": "DEFAULT_DPU_OUTPUT_LINE_WIDTH",
                                      "generic_linewidth_constant": 2560, "board_linewidth": 1880}
        definition = (source / "drivers/gpu/drm/msm/disp/dpu1/dpu_hw_catalog.c").read_text()
        assert re.search(r"#define\s+DEFAULT_DPU_OUTPUT_LINE_WIDTH\s+2560\b", definition)
    except Exception as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        status = 1
    finally:
        result["candidate_driver_sources_unchanged"] = all(core.digest(source / name) == expected
            for name, expected in previous["candidate_source_files"].items())
        result["frozen_source_unchanged"] = all(core.digest(original / name) == expected
            for name, expected in previous["source_before"].items())
        result["frozen_artifacts_unchanged"] = all(core.identity(original.parent / "artifacts" / name) == expected
            for name, expected in previous["primary_artifacts_before"].items())
        if not all(result[key] for key in ("candidate_driver_sources_unchanged", "frozen_source_unchanged", "frozen_artifacts_unchanged")):
            status = 1
        result["private_makefile_after_sha256"] = core.digest(makefile)
        result["completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        result["qualification_command_exit"] = status
        destination = output / "native-dt-612.json"
        destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps({"manifest": str(destination), "sha256": core.digest(destination), "exit_code": status}), flush=True)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
