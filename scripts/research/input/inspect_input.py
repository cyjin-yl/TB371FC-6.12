#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the actual module/object/DT artifacts; never label device success."""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil
import struct
import subprocess

import prepare_input as profile


def command(argv):
    return subprocess.check_output(list(map(str, argv)), text=True, timeout=30).strip()


def identity(path):
    return {"sha256": profile.digest(path), "size": path.stat().st_size}


def dt_nodes(path):
    """Read generated flattened properties for a full baseline/candidate diff."""
    data = path.read_bytes()
    if len(data) < 40 or len(data) > 4 * 1024 * 1024:
        raise ValueError("unexpected DTB length")
    magic, total, off_struct, off_strings, _, version, _, _, n_strings, n_struct = struct.unpack(">10I", data[:40])
    if magic != 0xD00DFEED or total != len(data) or version < 17:
        raise ValueError("unexpected DTB header")
    if off_struct + n_struct > len(data) or off_strings + n_strings > len(data):
        raise ValueError("DTB block outside file")
    strings = data[off_strings:off_strings + n_strings]
    body = data[off_struct:off_struct + n_struct]
    stack, nodes, pos = [], {}, 0
    while pos + 4 <= len(body):
        tag, = struct.unpack_from(">I", body, pos); pos += 4
        if tag == 1:
            end = body.index(b"\0", pos)
            stack.append(body[pos:end].decode("ascii")); pos = (end + 4) & ~3
            name = "/" + "/".join(stack[1:])
            if name in nodes:
                raise ValueError("duplicate DT node")
            nodes[name] = {}
        elif tag == 2:
            if not stack:
                raise ValueError("unbalanced DT node")
            stack.pop()
        elif tag == 3:
            size, nameoff = struct.unpack_from(">II", body, pos); pos += 8
            if not stack or pos + size > len(body) or nameoff >= len(strings):
                raise ValueError("DT property outside bounds")
            nameend = strings.index(b"\0", nameoff)
            prop = strings[nameoff:nameend].decode("ascii")
            node = "/" + "/".join(stack[1:])
            if prop in nodes[node]:
                raise ValueError("duplicate DT property")
            nodes[node][prop] = body[pos:pos + size]; pos = (pos + size + 3) & ~3
        elif tag == 4:
            continue
        elif tag == 9:
            if stack:
                raise ValueError("unclosed DT node")
            return nodes
        else:
            raise ValueError("unknown FDT token")
    raise ValueError("DT END token absent")


def text(value):
    return value.rstrip(b"\0").decode("ascii").split("\0")


def cells(value):
    if len(value) % 4:
        raise ValueError("non-cell property")
    return list(struct.unpack(">" + "I" * (len(value) // 4), value))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=Path("/work/input-integration-v3"))
    args = p.parse_args()
    work = args.work.resolve()
    manifest = profile.verify(work)
    output = work / "kernel-out"
    artifacts = work / "artifacts"
    if artifacts.exists() or artifacts.is_symlink():
        raise SystemExit("retain previous artifact inspection; do not overwrite")
    sysroot = work / "target-sysroot"
    if sysroot.is_symlink() or not sysroot.is_dir() or any(sysroot.iterdir()):
        raise SystemExit("the explicitly empty target sysroot changed")
    if profile.digest(output / ".config") != profile.BASE_CONFIG_SHA256:
        raise SystemExit("module build config differs from research2")
    if profile.digest(output / "Module.symvers") != profile.BASE_SYMVERS_SHA256:
        raise SystemExit("baseline symbol versions changed")
    if (output / "include/config/kernel.release").read_text().strip() != profile.RELEASE:
        raise SystemExit("prepared kernel release mismatch")
    # With O= and an absolute M=, kbuild places external-module products in M.
    # This is the new private source tree, never a frozen research2 directory.
    module = work / profile.SOURCE_DIR / "drivers/input/touchscreen/nt36523/nt36523_ts.ko"
    objects = [output / rel for rel in (
        "drivers/hid/i2c-hid/i2c-hid-of.o", "drivers/hid/i2c-hid/i2c-hid-core.o",
        "drivers/hid/hid-multitouch.o")]
    for path in [module, *objects]:
        data = path.read_bytes()
        if data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
            raise SystemExit("not AArch64 ELF: " + str(path))
    vermagic = command(["modinfo", "-F", "vermagic", module])
    if vermagic.split()[0] != profile.RELEASE:
        raise SystemExit("input module release mismatch")
    aliases = command(["modinfo", "-F", "alias", module]).splitlines()
    if "of:N*T*Cnovatek,NVT-ts-spi" not in aliases:
        raise SystemExit("touchscreen OF alias absent")
    reference = {parts[1]: int(parts[0], 16) for line in
                 (work / "baseline-abi/Module.symvers").read_text().splitlines()
                 if len(parts := line.split()) >= 2}
    imports = {}
    for line in command(["modprobe", "--show-modversions", module]).splitlines():
        crc, name = line.split()
        if reference.get(name) != int(crc, 16):
            raise SystemExit("module symbol CRC mismatch: " + name)
        imports[name] = crc
    if not imports or "module_layout" not in imports:
        raise SystemExit("module version imports not verified")
    dtb = output / profile.QCOM / (profile.DT_NAME + ".dtb")
    nodes = dt_nodes(dtb)
    baseline = dt_nodes(work / "baseline-abi/display.dtb")
    spi = "/soc@0/geniqup@8c0000/spi@880000"
    touch = spi + "/touchscreen@0"
    keyboards = [name for name in nodes if name.endswith("/i2c@a94000/keyboard-cover@60")]
    if len(keyboards) != 1:
        raise SystemExit("expected exactly one I2C13 keyboard")
    keyboard = keyboards[0]
    actual_changes = {(node, prop) for node in nodes.keys() | baseline.keys()
                      for prop in nodes.get(node, {}).keys() | baseline.get(node, {}).keys()
                      if nodes.get(node, {}).get(prop) != baseline.get(node, {}).get(prop)}
    expected_changes = {("/", "model"), (spi, "status"), (touch, "status"), (keyboard, "status")}
    if actual_changes != expected_changes or nodes.keys() != baseline.keys():
        raise SystemExit("DT changes exceed the explicit input profile: " + repr(actual_changes))
    for node in (spi, touch, keyboard, keyboard.rsplit("/", 1)[0]):
        if text(nodes[node].get("status", b"okay\0")) != ["okay"]:
            raise SystemExit("input node is not enabled: " + node)
    if text(nodes[touch]["compatible"]) != ["novatek,NVT-ts-spi"]:
        raise SystemExit("touch compatible mismatch")
    if text(nodes[keyboard]["compatible"]) != ["hid-over-i2c"]:
        raise SystemExit("keyboard compatible mismatch")
    if "touchscreen-x-mm" in nodes[touch] or "touchscreen-y-mm" in nodes[touch]:
        raise SystemExit("unmeasured physical dimension was introduced")
    regression = json.loads((work / "regression/result.json").read_text())
    if regression.get("compile_exit") != 0 or regression.get("run_exit") != 0:
        raise SystemExit("source-derived API fault-injection failed")
    artifacts.mkdir()
    selections = {"nt36523_ts.ko": module, "board.dtb": dtb,
                  "kernel.config": output / ".config", "Module.symvers": output / "Module.symvers",
                  "source-manifest.json": work / "source-manifest.json",
                  "regression.json": work / "regression/result.json"}
    selections.update({p.name: p for p in objects})
    for name, path in selections.items():
        shutil.copyfile(path, artifacts / name)
    result = {
        "schema_version": 1, "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "profile": manifest["profile"], "evidence_class": "host_build",
        "kernel_release": profile.RELEASE, "config_unchanged": True,
        "module": {"vermagic": vermagic, "aliases": aliases,
                   "signer": command(["modinfo", "-F", "signer", module]),
                   "imported_symbol_crc_count": len(imports), "all_imported_crcs_match_baseline": True},
        "joint_dtb": {"model": text(nodes["/"]["model"])[0],
                      "root_compatible": text(nodes["/"]["compatible"]),
                      "changes": [{"path": n, "property": p,
                                   "before": text(baseline[n][p]) if p in baseline[n] else None,
                                   "after": text(nodes[n][p])} for n, p in sorted(actual_changes)],
                      "touch": {"path": touch, "irq_gpio": cells(nodes[touch]["irq-gpios"]),
                                "reset_gpio": cells(nodes[touch]["reset-gpios"]),
                                "panel_id_gpio": cells(nodes[touch]["panel-id-gpios"]),
                                "super_resolution": cells(nodes[touch]["novatek,super-resolution"]),
                                "physical_dimensions_mm": None,
                                "boe_firmware": text(nodes[touch]["novatek,boe-firmware-name"]),
                                "tianma_firmware": text(nodes[touch]["novatek,tianma-firmware-name"])},
                      "keyboard": {"path": keyboard, "interrupts": cells(nodes[keyboard]["interrupts"]),
                                   "reset_gpio": cells(nodes[keyboard]["reset-gpios"]),
                                   "wake_gpio": cells(nodes[keyboard]["wake-gpios"]),
                                   "descriptor_address": cells(nodes[keyboard]["hid-descr-addr"])}},
        "regression": regression,
        "files": {name: identity(artifacts / name) for name in selections},
        "compiler": command(["clang", "--version"]).splitlines()[0],
        "target_cc_sysroot": {"path": str(sysroot), "empty": True,
                              "purpose": "isolate freestanding Kconfig probes from ambient target userspace libc"},
        "build_jobs": 1, "new_image_built": False, "module_loaded": False,
        "hardware_probe_tested": False, "device_linux_tested": False,
        "limits": ["Module/object/DT build only; no new complete Image or modules-install tree.",
                   "No physical probe, touch/pen samples, charging, wake, resume, or display timing test.",
                   "CTN730 and display-before-touch lifecycle coordination remain separate work."]
    }
    (artifacts / "input-integration-build.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"artifact_inspection": "pass", "module_imports_checked": len(imports),
                      "regression_cases": len(regression["cases"]), "device_linux_tested": False}))


if __name__ == "__main__":
    main()
