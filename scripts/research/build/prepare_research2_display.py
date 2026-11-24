#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Prepare the independent, source-pinned research2-display kernel candidate.

The frozen research1 recipe runs in this candidate's new private work directory.
Its exact original manifest is retained before adding only the qualified 0002
PHY/catalog patch and versioned display DT. No existing research1 tree is edited.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


RELEASE = "6.12.114-tb371fc-research2-display"
LOCALVERSION = "-tb371fc-research2-display"
SOURCE_DIR = "linux-6.12.114-research2-display"
BASE_MANIFEST_SHA256 = "1a8788a8e5700287870d9e9ca44ad2be8c69e6f28d927321edd89508c5501821"
BASE_CONFIG_SHA256 = "1929caefadeb28cf84174c7fe7c100ab7251b3adcfdf547b2165c229b50f66da"
ARCHIVE_SHA256 = "7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3"
QUALIFICATION = "docs/research/2026-11-23/evidence/diagnostic-dt-profiles.json"
QUALIFICATION_SHA256 = "5a277ba48186870748799b43b84e10c3fa719d6c6b178b1d14502a2a8091e5a9"
DTB_SHA256 = "50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e"
QCOM = "arch/arm64/boot/dts/qcom/"
DT_NAME = "sm8250-lenovo-tb371fc-display-test-6.12"
PATCH = "mainline-port/backports/linux-6.12/0002-tb371fc-phy-wideplane.patch"
ADDED_INPUTS = {
    PATCH: "839699e055d8959232f2912895cbd71f5fd85f3e07a1d3f033a1fd728e08ce56",
    "mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc-display-test.dts":
        "cbb4a34fb144d01f2df5804049b6de1fc58cd3fdb0417cec04ee44b01a5b0cef",
    "mainline-port/backports/linux-6.12/" + DT_NAME + ".dts":
        "8cac3ffe34d6eaf3ee43ea1c63b4395fd6a38325ccb5f289283da3e234bfe1f7",
}
FROZEN_HELPERS = {
    "scripts/research/build/prepare_kernel.py": "79794fb988ebfd204e1fc99ba35fdf301da6de5db554debdf689143700598f59",
    "scripts/research/build/inspect_kernel.py": "2cac7d0bfdf13d449349e6482c75ceda261ec7d67acd0c677490843f8591a875",
    "scripts/research/build/smoke_qemu.py": "e3bcf5a7fe442b3e0065e513d82e4774891de98b3b61a4331971a2ab112a5473",
    "scripts/research/build/qemu-init.c": "2932cb3b2cac25e7ba98041bba3df116623d169adc606bcd99974c29f5c5195f",
    "scripts/research/build/run_job.py": "94b3d3692adbbbbbcec8cf2d84718bf5eb6c0ef0278145add177c4c1e92d63fe",
}
RECIPES = (
    "scripts/research/build/prepare_research2_display.py",
    "scripts/research/build/build_research2_display.sh",
    "scripts/research/build/inspect_research2_display.py",
    "scripts/research/build/smoke_research2_display.py",
)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, **kwargs):
    print("+", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), check=True, **kwargs)


def verify_work(repo, work):
    manifest = json.loads((work / "source-manifest.json").read_text())
    base_file = work / "source-manifest-research1.json"
    if digest(base_file) != BASE_MANIFEST_SHA256:
        raise SystemExit("preserved research1 manifest differs")
    baseline = json.loads(base_file.read_text())
    if manifest.get("kernel_release") != RELEASE or manifest.get("source_dir") != SOURCE_DIR:
        raise SystemExit("unexpected candidate profile/release")
    if manifest.get("added_patches") != [PATCH] or manifest.get("dtb_target") != "qcom/" + DT_NAME + ".dtb":
        raise SystemExit("candidate patch/DT selection differs")
    if (manifest.get("base_sha256") != ARCHIVE_SHA256 or manifest.get("expected_dtb_sha256") != DTB_SHA256
            or manifest.get("baseline_resolved_config_sha256") != BASE_CONFIG_SHA256
            or manifest.get("configuration_change") != {"CONFIG_LOCALVERSION": LOCALVERSION}):
        raise SystemExit("candidate archive/configuration/DT identity differs")
    expected_inputs = dict(baseline["inputs"])
    expected_inputs.update(ADDED_INPUTS)
    if manifest["inputs"] != expected_inputs:
        raise SystemExit("candidate input manifest differs from the explicit source combination")
    if manifest["frozen_helpers"] != FROZEN_HELPERS or set(manifest["recipes"]) != set(RECIPES):
        raise SystemExit("candidate helper/recipe identity differs")
    for mapping in (manifest["inputs"], manifest["frozen_helpers"], manifest["recipes"]):
        for name, expected in mapping.items():
            if digest(repo / name) != expected:
                raise SystemExit("repository input changed: " + name)
    for name, expected in manifest["assembled_files"].items():
        if digest(work / SOURCE_DIR / name) != expected:
            raise SystemExit("prepared source changed: " + name)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/src"))
    parser.add_argument("--work", type=Path, default=Path("/work/research2-display"))
    parser.add_argument("--cache", type=Path, default=Path("/work/downloads/linux-6.12.114.tar.xz"))
    parser.add_argument("--verify", action="store_true", help="read-only verification of an existing prepared candidate")
    args = parser.parse_args()
    repo, work = args.repo.resolve(), args.work.resolve()
    if args.verify:
        manifest = verify_work(repo, work)
        print(json.dumps({"kernel_release": manifest["kernel_release"], "source_verified": True}))
        return
    if work.exists() or work.is_symlink():
        raise SystemExit("candidate work directory exists; retain it and choose a new --work")
    if work.is_relative_to(repo) or repo.is_relative_to(work):
        raise SystemExit("work overlaps the read-only repository")
    for name, expected in {**ADDED_INPUTS, **FROZEN_HELPERS, QUALIFICATION: QUALIFICATION_SHA256}.items():
        if digest(repo / name) != expected:
            raise SystemExit("pinned input differs: " + name)
    qualification = json.loads((repo / QUALIFICATION).read_text())
    if qualification["qualification_command_exit"] != 0:
        raise SystemExit("prerequisite source qualification did not pass")
    recipe_hashes = {name: digest(repo / name) for name in RECIPES}
    work.mkdir(parents=True)
    cache = args.cache.resolve()
    if cache.is_file():
        if digest(cache) != ARCHIVE_SHA256:
            raise SystemExit("kernel archive cache SHA-256 mismatch")
        downloads = work / "downloads"
        downloads.mkdir()
        target = downloads / "linux-6.12.114.tar.xz"
        try:
            os.link(cache, target)
        except OSError:
            shutil.copyfile(cache, target)
    run([sys.executable, repo / "scripts/research/build/prepare_kernel.py", "--repo", repo, "--work", work])
    base_file = work / "source-manifest.json"
    if digest(base_file) != BASE_MANIFEST_SHA256:
        raise SystemExit("fresh research1 preparation did not reproduce the frozen input/source manifest")
    baseline = json.loads(base_file.read_text())
    base_file.rename(work / "source-manifest-research1.json")
    source = work / SOURCE_DIR
    (work / "linux-6.12.114-research1").rename(source)
    run(["git", "apply", "--recount", "--check", repo / PATCH], cwd=source)
    run(["git", "apply", "--recount", repo / PATCH], cwd=source)
    for name in ADDED_INPUTS:
        if name.endswith(".dts"):
            target = source / QCOM / Path(name).name
            if target.exists():
                raise SystemExit("diagnostic DT target unexpectedly exists")
            shutil.copyfile(repo / name, target)
    with (source / QCOM / "Makefile").open("a") as stream:
        stream.write(f"\ndtb-$(CONFIG_ARCH_QCOM) += {DT_NAME}.dtb\n")
    for name, expected in qualification["candidate_source_files"].items():
        if digest(source / name) != expected:
            raise SystemExit("source differs from qualified native prerequisite: " + name)
    paths = set(baseline["assembled_files"]) | {QCOM + "Makefile"}
    inputs = {**baseline["inputs"], **ADDED_INPUTS}
    for name in inputs:
        if name.endswith(".patch"):
            paths.update(re.findall(r"^\+\+\+ b/(.+)$", (repo / name).read_text(), re.M))
    paths.update(QCOM + Path(name).name for name in ADDED_INPUTS if name.endswith(".dts"))
    manifest = {
        "schema_version": 1, "kernel_release": RELEASE, "source_dir": SOURCE_DIR,
        "profile": "research2-display; complete-build candidate; physical hardware untested",
        "base_url": baseline["base_url"], "base_sha256": ARCHIVE_SHA256,
        "baseline_manifest": {"path": "source-manifest-research1.json", "sha256": BASE_MANIFEST_SHA256},
        "baseline_resolved_config_sha256": BASE_CONFIG_SHA256,
        "configuration_change": {"CONFIG_LOCALVERSION": LOCALVERSION},
        "added_patches": [PATCH], "dtb_target": "qcom/" + DT_NAME + ".dtb",
        "expected_dtb_sha256": DTB_SHA256,
        "inputs": inputs, "frozen_helpers": FROZEN_HELPERS, "recipes": recipe_hashes,
        "assembled_files": {name: digest(source / name) for name in sorted(paths)},
        "prerequisite_qualification": {"path": QUALIFICATION, "sha256": QUALIFICATION_SHA256},
        "physical_hardware_tested": False,
    }
    (work / "source-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    verify_work(repo, work)
    print(json.dumps({"source": str(source), "kernel_release": RELEASE,
                      "manifest_sha256": digest(work / "source-manifest.json")}))


if __name__ == "__main__":
    main()
