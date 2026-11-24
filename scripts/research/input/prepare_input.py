#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Reproduce research2 in a new tree, then apply the explicit input changes.

Only a new --work is accepted. The frozen baseline repository/tree and its
artifacts remain read-only. This recipe prepares a module/DT integration, not
a new complete Image or a device-install command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

BASE_MANIFEST_SHA256 = "845914d9cc1c876f10704f3334ee942b2c26deaa8045ce9c2ef82ef2920cde21"
BASE_CONFIG_SHA256 = "e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8"
BASE_SYMVERS_SHA256 = "8e71a956b3c79112228f92cd234a13a39aa7a3193a5d1222d1dab5123043d9d0"
BASE_DTB_SHA256 = "50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e"
RELEASE = "6.12.114-tb371fc-research2-display"
SOURCE_DIR = "linux-6.12.114-input-integration"
QCOM = "arch/arm64/boot/dts/qcom/"
DT_NAME = "sm8250-lenovo-tb371fc-display-input-test-6.12"
PREFIX = "mainline-port/backports/linux-6.12/"
PATCHES = (
    PREFIX + "0018-input-nt36523-use-declared-physical-dimensions.patch",
    PREFIX + "0019-input-nt36523-fail-closed-and-release-resources.patch",
)
INPUTS = PATCHES + (PREFIX + DT_NAME + ".dts",)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(argv, **kwargs):
    print("+", " ".join(map(str, argv)), flush=True)
    subprocess.run(list(map(str, argv)), check=True, **kwargs)


def verify(work):
    manifest = json.loads((work / "source-manifest.json").read_text())
    if manifest["source_dir"] != SOURCE_DIR or manifest["kernel_release"] != RELEASE:
        raise SystemExit("input candidate identity mismatch")
    if manifest["patch_order"] != list(PATCHES):
        raise SystemExit("input patch selection mismatch")
    if digest(work / "source-manifest-research2.json") != BASE_MANIFEST_SHA256:
        raise SystemExit("preserved research2 manifest mismatch")
    for rel, expected in manifest["assembled_files"].items():
        if digest(work / SOURCE_DIR / rel) != expected:
            raise SystemExit("input candidate source changed: " + rel)
    for rel, expected in manifest["baseline_abi_inputs"].items():
        if digest(work / rel) != expected:
            raise SystemExit("baseline ABI input changed: " + rel)
    for rel, expected in manifest["input_copies"].items():
        if digest(work / "input-recipe" / rel) != expected:
            raise SystemExit("input recipe changed: " + rel)
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, required=True, help="repository/overlay containing the new input files")
    p.add_argument("--baseline-repo", type=Path, default=Path("/work/research2-repo"))
    p.add_argument("--baseline-work", type=Path, default=Path("/work/research2-display"))
    p.add_argument("--work", type=Path, default=Path("/work/input-integration-v3"))
    p.add_argument("--cache", type=Path, default=Path("/work/downloads/linux-6.12.114.tar.xz"))
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    repo, base_repo, base_work, work = (x.resolve() for x in
                                      (args.repo, args.baseline_repo, args.baseline_work, args.work))
    if args.verify:
        print(json.dumps({"verified": True, "profile": verify(work)["profile"]}))
        return
    if args.work.is_symlink() or work.exists():
        raise SystemExit("retain existing work; use a fresh --work directory")
    for other in (repo, base_repo, base_work):
        if work.is_relative_to(other) or other.is_relative_to(work):
            raise SystemExit("candidate work overlaps a source/baseline directory")
    baseline_paths = {
        "source-manifest.json": BASE_MANIFEST_SHA256,
        "artifacts/kernel.config": BASE_CONFIG_SHA256,
        "artifacts/Module.symvers": BASE_SYMVERS_SHA256,
        "artifacts/board.dtb": BASE_DTB_SHA256,
    }
    for rel, expected in baseline_paths.items():
        if digest(base_work / rel) != expected:
            raise SystemExit("frozen research2 input mismatch: " + rel)
    run([sys.executable, base_repo / "scripts/research/build/prepare_research2_display.py",
         "--repo", base_repo, "--work", work, "--cache", args.cache])
    if digest(work / "source-manifest.json") != BASE_MANIFEST_SHA256:
        raise SystemExit("fresh research2 source manifest did not reproduce")
    (work / "source-manifest.json").rename(work / "source-manifest-research2.json")
    baseline = json.loads((work / "source-manifest-research2.json").read_text())
    source = work / SOURCE_DIR
    (work / baseline["source_dir"]).rename(source)
    paths = set(baseline["assembled_files"])
    import re
    for rel in PATCHES:
        run(["git", "apply", "--check", repo / rel], cwd=source)
        run(["git", "apply", repo / rel], cwd=source)
        paths.update(re.findall(r"^\+\+\+ b/(.+)$", (repo / rel).read_text(), re.M))
    dts_rel = QCOM + DT_NAME + ".dts"
    if (source / dts_rel).exists():
        raise SystemExit("input DT target already exists")
    shutil.copyfile(repo / PREFIX / (DT_NAME + ".dts"), source / dts_rel)
    with (source / QCOM / "Makefile").open("a") as stream:
        stream.write(f"\ndtb-$(CONFIG_ARCH_QCOM) += {DT_NAME}.dtb\n")
    paths.update((dts_rel, QCOM + "Makefile"))
    abi = work / "baseline-abi"
    abi.mkdir()
    shutil.copyfile(base_work / "artifacts/kernel.config", abi / "kernel.config")
    shutil.copyfile(base_work / "artifacts/Module.symvers", abi / "Module.symvers")
    shutil.copyfile(base_work / "artifacts/board.dtb", abi / "display.dtb")
    recipe_files = list(INPUTS) + [str(x.relative_to(repo)) for x in
                                   sorted((repo / "scripts/research/input").glob("*")) if x.is_file()]
    copies = {}
    for rel in recipe_files:
        dst = work / "input-recipe" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, dst)
        copies[rel] = digest(dst)
    manifest = {
        "schema_version": 1,
        "profile": "input-integration-v3; module/DT-only against frozen research2 ABI",
        "source_dir": SOURCE_DIR, "kernel_release": RELEASE,
        "base_manifest_sha256": BASE_MANIFEST_SHA256,
        "patch_order": list(PATCHES), "dtb_target": "qcom/" + DT_NAME + ".dtb",
        "baseline_abi_inputs": {"baseline-abi/kernel.config": BASE_CONFIG_SHA256,
                                "baseline-abi/Module.symvers": BASE_SYMVERS_SHA256,
                                "baseline-abi/display.dtb": BASE_DTB_SHA256},
        "input_copies": copies,
        "assembled_files": {rel: digest(source / rel) for rel in sorted(paths)},
        "image_built": False, "module_loaded": False, "device_linux_tested": False,
    }
    (work / "source-manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    verify(work)
    print(json.dumps({"source": str(source), "source_manifest_sha256": digest(work / "source-manifest.json")}))


if __name__ == "__main__":
    main()
