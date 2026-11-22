#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Record actual kernel artifacts and verify module release strings offline.

No module is loaded. This is an artifact check, not a tablet boot or complete
ABI validation. Hashes include the new build's signed module bytes.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def command(args):
    return subprocess.check_output(args, text=True, timeout=20).strip()


def read_module_order(path, build_order):
    if path.is_symlink() or not path.is_file():
        raise SystemExit("module order missing or symlinked: " + str(path))
    lines = path.read_text().splitlines()
    result = []
    for line in lines:
        entry = PurePosixPath(line)
        if (not line or str(entry) != line or entry.is_absolute() or ".." in entry.parts
                or "\\" in line or any(char.isspace() for char in line)):
            raise SystemExit("invalid module-order path: " + repr(line))
        if build_order:
            # Linux 6.12.114 Makefile.modinst transforms each build *.o entry
            # into kernel/*.ko in the installed modules.order.
            if not line.endswith(".o") or len(entry.name) <= 2:
                raise SystemExit("expected a build .o entry in modules.order: " + line)
            line = "kernel/" + line[:-2] + ".ko"
        elif not line.startswith("kernel/") or not line.endswith(".ko"):
            raise SystemExit("unexpected installed module-order path: " + line)
        result.append(line)
    if not result or len(result) != len(set(result)):
        raise SystemExit("empty or duplicate module-order entries: " + str(path))
    return result


def module_inventory(work, release):
    """Qualify this build's complete, uncompressed in-tree module inventory."""
    module_dir = work / "modules/lib/modules" / release
    kernel_dir = module_dir / "kernel"
    if module_dir.is_symlink() or kernel_dir.is_symlink() or not kernel_dir.is_dir():
        raise SystemExit("missing or symlinked installed kernel module subtree")
    # A normal modules_install creates the build symlink. This recipe builds
    # no external modules; updates/, extra/, weak-updates/ or another directory
    # would be undeclared inputs even if their release strings happen to match.
    for path in module_dir.iterdir():
        if path.name == "build" and path.is_symlink():
            continue
        if path.is_symlink():
            raise SystemExit("undeclared module-tree symlink: " + str(path))
        if path.is_dir() and path.name != "kernel":
            raise SystemExit("undeclared module directory: " + str(path))
        if path.is_file() and ".ko" in path.name:
            raise SystemExit("module outside the declared kernel subtree: " + str(path))
    source_order = work / "kernel-out/modules.order"
    installed_order = module_dir / "modules.order"
    expected = read_module_order(source_order, build_order=True)
    installed = read_module_order(installed_order, build_order=False)
    if installed != expected:
        raise SystemExit("installed modules.order differs from this build's modules.order")
    modules = []
    for parent, directories, names in os.walk(kernel_dir, followlinks=False):
        parent = Path(parent)
        for name in directories:
            if (parent / name).is_symlink():
                raise SystemExit("symlinked kernel module directory: " + str(parent / name))
        for name in names:
            path = parent / name
            if path.is_symlink() or not path.is_file() or not name.endswith(".ko"):
                raise SystemExit("unexpected file in uncompressed module tree: " + str(path))
            modules.append(path)
    modules.sort()
    actual = {path.relative_to(module_dir).as_posix() for path in modules}
    if actual != set(expected):
        raise SystemExit("module inventory mismatch: " + json.dumps({
            "missing": sorted(set(expected) - actual), "unexpected": sorted(actual - set(expected))}))
    return modules, {
        "scope": "all declared uncompressed in-tree modules; no external module directory admitted",
        "build_order_path": "kernel-out/modules.order", "build_order_sha256": digest(source_order),
        "installed_order_path": installed_order.relative_to(work).as_posix(),
        "installed_order_sha256": digest(installed_order),
        "build_order_entry_format": ".o mapped to kernel/*.ko by Linux 6.12.114 modules_install",
        "expected_count": len(expected), "installed_count": len(modules),
        "installed_order_matches_build": True, "installed_module_set_matches_build": True,
        "missing_modules": [], "unexpected_modules": [], "undeclared_module_directories": [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("/work"))
    args = parser.parse_args()
    work = args.work.resolve()
    artifacts = work / "artifacts"
    destination = artifacts / "kernel-build.json"
    if destination.exists() or destination.is_symlink():
        raise SystemExit("evidence already exists; retain it before collecting a new build")
    release = (artifacts / "kernel.release").read_text().strip()
    if release != "6.12.114-tb371fc-research1":
        raise SystemExit("unexpected kernel release")
    with (artifacts / "Image").open("rb") as stream:
        header = stream.read(64)
    if header[56:60] != b"ARM\x64":
        raise SystemExit("not an ARM64 Linux Image")
    compatible = command(["fdtget", "-t", "s", str(artifacts / "board.dtb"), "/", "compatible"]).split()
    if "lenovo,tb371fc" not in compatible:
        raise SystemExit("native board DTB lacks the compatible used by the early allocator guard")
    config = {}
    for line in (artifacts / "kernel.config").read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            name, value = line.split("=", 1)
            config[name] = value
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            config[line[2:-11]] = "n"
    required = {"CONFIG_DRM_MSM": "y", "CONFIG_TOUCHSCREEN_NT36523_SPI": "m",
                "CONFIG_BACKLIGHT_TB371FC_KTZ8866": "m", "CONFIG_DRM_PANEL_NOVATEK_NT36523": "m",
                "CONFIG_VIDEO_QCOM_VENUS": "m", "CONFIG_FW_LOADER_COMPRESS_XZ": "y",
                "CONFIG_FW_LOADER_COMPRESS_ZSTD": "y", "CONFIG_I2C_HID_OF": "y"}
    for name, expected in required.items():
        if config.get(name) != expected:
            raise SystemExit(f"resolved configuration mismatch: {name}")
    for name in ("CONFIG_TB371FC_EARLY_FB_MARKER", "CONFIG_TB371FC_LATE_FB_MARKER",
                 "CONFIG_TB371FC_POST_MMU_RESET_CHECKPOINT"):
        if config.get(name, "n") != "n":
            raise SystemExit("diagnostic checkpoint unexpectedly enabled: " + name)
    module_root = work / "modules"
    if config.get("CONFIG_MODULE_COMPRESS_ALL", "n") == "y":
        raise SystemExit("this inspection profile expects uncompressed .ko modules")
    modules, inventory = module_inventory(work, release)
    module_dir = module_root / "lib/modules" / release
    checksums = []
    selected = []
    for path in modules:
        if path.is_symlink():
            raise SystemExit("unexpected symlink module: " + str(path))
        relative = str(path.relative_to(module_root))
        checksum = digest(path)
        checksums.append(f"{checksum}  {relative}\n")
        vermagic = command(["modinfo", "-F", "vermagic", str(path)])
        if not vermagic.split() or vermagic.split()[0] != release:
            raise SystemExit("module release mismatch: " + relative)
        with path.open("rb") as stream:
            elf = stream.read(20)
        if elf[:6] != b"\x7fELF\x02\x01" or int.from_bytes(elf[18:20], "little") != 183:
            raise SystemExit("module is not ARM64 ELF: " + relative)
        driver_relative = path.relative_to(module_dir).as_posix()
        if any(part in driver_relative for part in ("nt36523/", "tb371fc", "panel-novatek", "/venus/", "ath11k", "sm8250", "qcom-rpmh")):
            selected.append({"path": relative, "size": path.stat().st_size,
                             "sha256": checksum, "vermagic": vermagic,
                             "firmware_names": command(["modinfo", "-F", "firmware", str(path)]).splitlines()})
    index = artifacts / "modules.SHA256SUMS"
    index.write_text("".join(checksums))
    packages = command(["dpkg-query", "-W", "-f=${binary:Package}\t${Version}\n"])
    package_manifest = artifacts / "builder-packages.tsv"
    package_manifest.write_text(packages + "\n")
    jobs = {}
    for name in ("kernel-prepare-v2", "kernel-build", "kernel-finalize", "kernel-pool-scope", "kernel-qemu", "kernel-qemu-fixed"):
        record = work / (name + ".json")
        log = work / (name + ".log")
        if record.exists():
            jobs[name] = {"result": json.loads(record.read_text()),
                          "result_sha256": digest(record), "log_sha256": digest(log)}
    files = {name: {"size": (artifacts / name).stat().st_size, "sha256": digest(artifacts / name)}
             for name in ("Image", "board.dtb", "kernel.config", "Module.symvers", "kernel.release",
                          "source-manifest.json", "modules.SHA256SUMS", "builder-packages.tsv")}
    result = {"schema_version": 1, "capture_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "kernel_release": release, "files": files, "native_dtb_root_compatible": compatible,
              "dtb_model": command(["fdtget", "-t", "s", str(artifacts / "board.dtb"), "/", "model"]),
              "module_count": len(modules), "all_module_vermagic_matches": True,
              "module_inventory": inventory,
              "all_modules_elf_aarch64": True, "selected_modules": selected,
              "resolved_config": {name: value for name, value in config.items()
                                  if name in required or any(name.startswith(prefix) for prefix in
                                      ("CONFIG_TB371FC_", "CONFIG_MODULE_SIG", "CONFIG_ARM64_VA_BITS", "CONFIG_ARM64_PA_BITS"))},
              "compiler": command(["clang", "--version"]).splitlines(),
              "linker": command(["ld.lld", "--version"]),
              "source_manifest": json.loads((artifacts / "source-manifest.json").read_text()),
              "jobs": jobs,
              "scope": "offline source/artifact checks and separately recorded generic VM test; no physical tablet acceptance",
              "bit_for_bit_reproducibility_proven": False,
              "reproducibility_limit": "APT packages are recorded, not snapshot-pinned; a fresh build generates a private module signing key",
              "physical_hardware_tested": False}
    with destination.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"kernel_release": release, "module_count": len(modules),
                      "all_module_vermagic_matches": True, "evidence_sha256": digest(destination),
                      "physical_hardware_tested": False}))


if __name__ == "__main__":
    main()
