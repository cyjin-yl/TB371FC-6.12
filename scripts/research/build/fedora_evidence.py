#!/usr/bin/env python3
"""Collect reproducible Fedora build evidence; never query a tablet or GPU.

Reads the prepared rootfs, retained RPMs and persistent build logs. Writes one
JSON manifest beneath the Fedora experiment work area. Full package payloads,
host secrets and Android firmware are not exported by this collector.
"""

import argparse
import configparser
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess


ARCHIVE = "Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar.xz"
EXPECTED_SHA256 = "bc6c3b3e132e3ed5eff398112d16fcdca13dc8abd63550f8aad40e882b9617b6"
EXPECTED_SIGNER = "4F50A6114CD5C6976A7F1179655A4B02F577861E"


def file_record(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            digest.update(block)
    return {"path": str(path), "size": size, "sha256": digest.hexdigest()}


def packages(path):
    text = path.read_text()
    # The first exploratory command overescaped the RPM query format. Keep its
    # original file unchanged and normalize the two literal delimiters here.
    if "\t" not in text and "\\t" in text:
        text = text.replace("\\t", "\t").replace("\\n", "\n")
    rows = []
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) != 3:
            raise ValueError(f"invalid package inventory row in {path}")
        rows.append(dict(zip(("name", "evr", "arch"), fields)))
    return sorted(rows, key=lambda row: (row["name"], row["arch"], row["evr"]))


def command(args, env=None):
    result = subprocess.run(args, text=True, capture_output=True, timeout=30, env=env)
    return {"command": args, "exit_code": result.returncode,
            "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("/work"))
    parser.add_argument("--smoke-result", type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    root = work / "fedora-bundle/rootfs"
    smoke_path = args.smoke_result or work / "fedora-smoke-primary/result.json"
    if not smoke_path.resolve().is_relative_to(work):
        parser.error("smoke result must be within the experiment work directory")

    downloads = work / "downloads"
    archive = downloads / ARCHIVE
    checksum = downloads / "Fedora-Container-45-1.4-aarch64-CHECKSUM"
    keyring = downloads / "fedora.gpg"
    archive_record = file_record(archive)
    if archive_record["sha256"] != EXPECTED_SHA256:
        raise ValueError("Fedora OCI archive hash differs from the fixed seed")
    match = re.search(r"^SHA256 \(" + re.escape(ARCHIVE) + r"\) = ([a-f0-9]{64})$",
                      checksum.read_text(), re.MULTILINE)
    if not match or match.group(1) != EXPECTED_SHA256:
        raise ValueError("signed CHECKSUM does not name the fixed archive hash")
    gpg_home = work / "fedora-gpgv-home"
    gpg_home.mkdir(mode=0o700, exist_ok=True)
    signature = command(["gpgv", "--homedir", str(gpg_home), "--status-fd", "1",
                         "--keyring", str(keyring), str(checksum)])
    if signature["exit_code"] or f"VALIDSIG {EXPECTED_SIGNER} " not in signature["stdout"]:
        raise ValueError("Fedora 45 signature verification did not match the pinned signer")

    jobs = {}
    for path in sorted(work.glob("fedora-*.json")):
        value = json.loads(path.read_text())
        if not isinstance(value, dict) or not {"command", "exit_code", "start_utc"} <= value.keys():
            continue
        log = path.with_suffix(".log")
        jobs[path.stem] = value | {"status_file": file_record(path),
                                   "log_file": file_record(log) if log.exists() else None}

    before = packages(work / "fedora-base-packages.tsv")
    after = packages(work / "fedora-final-packages.tsv")
    before_keys = {(p["name"], p["arch"]): p["evr"] for p in before}
    additions = [p for p in after if (p["name"], p["arch"]) not in before_keys]
    replacements = [p for p in after if (p["name"], p["arch"]) in before_keys
                    and p["evr"] != before_keys[(p["name"], p["arch"])]]

    completion_lines = []
    for path in sorted((root / "var/log").glob("dnf5.log*")):
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            if "RPM callback stop " in line and "scriptlet" in line:
                code = re.search(r"return code (-?\d+)\b", line)
                if code:
                    completion_lines.append({"return_code": int(code.group(1)), "line": line})

    repositories = []
    for path in sorted((root / "etc/yum.repos.d").glob("*.repo")):
        config = configparser.ConfigParser(interpolation=None)
        config.read(path)
        for name in ("fedora", "updates"):
            if name in config:
                repositories.append({"id": name, "source_file": "/" + str(path.relative_to(root)),
                                     **{key: config[name].get(key) for key in (
                                         "gpgcheck", "repo_gpgcheck", "gpgkey", "metalink", "baseurl")}})

    binaries = []
    for relative in (
        "usr/bin/weston", "usr/bin/eglinfo", "usr/bin/vulkaninfo", "usr/bin/vkcube",
        "usr/lib64/libEGL_mesa.so.0", "usr/lib64/libgbm.so.1",
        "usr/lib64/libvulkan_freedreno.so", "usr/lib64/libvulkan_lvp.so",
        "usr/lib64/libgallium-26.2.7.so", "usr/lib64/dri/msm_dri.so",
    ):
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"guest library path escapes rootfs: {relative}")
        record = file_record(path)
        record["guest_path"] = "/" + relative
        with path.open("rb") as stream:
            header = stream.read(64)
        if header[:4] != b"\x7fELF" or header[4:6] != b"\x02\x01":
            raise ValueError(f"expected little-endian ELF64: {relative}")
        record["elf_machine"] = struct.unpack_from("<H", header, 18)[0]
        if record["elf_machine"] != 183:
            raise ValueError(f"expected AArch64 ELF: {relative}")
        binaries.append(record)

    scripts = []
    for name in ("fedora-userspace.sh", "fedora_guest_egl.py", "fedora_smoke.py", "fedora_evidence.py"):
        scripts.append(file_record(work / name))
    native_environment = os.environ.copy()
    native_environment["LD_LIBRARY_PATH"] = str(work / "fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu")
    proot = work / "fedora-proot-src/src/proot"
    smoke = json.loads(smoke_path.read_text())
    result = {
        "schema_version": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "evidence_class": "host_build_and_emulated_userspace",
        "environment": {"device": "doesvm", "ct": 102,
                        "container": "tb371fc-build-20261123", "rootfs": str(root)},
        "seed": {**archive_record, "url": "https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Container/aarch64/images/" + ARCHIVE,
                 "checksum_file": file_record(checksum), "checksum_matches_archive": True,
                 "signer_fingerprint": EXPECTED_SIGNER, "signature_verification": signature,
                 "keyring_file": file_record(keyring), "keyring_url": "https://fedoraproject.org/fedora.gpg"},
        "execution_compatibility": {
            "direct_qemu_nested_exec": {"status": "failed", "child_exit_code": 126,
                                       "reason": "Exec format error", "job": "fedora-preflight"},
            "debian_proot_5_1": {"status": "incompatible_for_dnf", "statx_missing_file": True,
                                  "test_exists": 0, "test_regular_file": 0, "test_readable": 1,
                                  "job": "fedora-proot-fs-probe"},
            "fixed_proot": {"revision": command(["git", "-C", str(work / "fedora-proot-src"), "rev-parse", "HEAD"])["stdout"],
                            "uthash_revision": command(["git", "-C", str(work / "fedora-proot-src/lib/uthash"), "rev-parse", "HEAD"])["stdout"],
                            "binary": file_record(proot),
                            "version": command([str(proot), "--version"], env=native_environment)},
            "qemu": {"binary": file_record(Path("/usr/bin/qemu-aarch64-static")),
                     "version": command(["/usr/bin/qemu-aarch64-static", "--version"])},
            "host_binfmt_changed": False, "system_vm_started_for_fedora": False,
            "container_root_packages_installed": False,
        },
        "assembly": {
            "install_job": "fedora-install", "check_job": "fedora-check",
            "scriptlets_disabled": False, "dnf_tsflags": "nodocs",
            "systemd_offline": True, "weak_dependencies": False,
            "repositories": repositories,
            "observed_scriptlet_completions": completion_lines,
            "nonzero_observed_scriptlet_completions": [x for x in completion_lines if x["return_code"]],
            "base_package_count": len(before), "final_package_count": len(after),
            "new_package_count": len(additions), "replaced_packages": replacements,
            "installed_packages": after, "new_packages": additions,
            "retained_rpms": [file_record(p) for p in sorted((root / "var/cache/libdnf5").rglob("*.rpm"))],
            "verified_aarch64_elf_files": binaries,
        },
        "emulated_graphics": smoke,
        "selected_diagnostics": {
            name: (smoke_path.parent / (name + ".log")).read_text(errors="replace")
            for name in ("egl_readback", "lavapipe_vulkaninfo", "turnip_without_device", "weston")
        },
        "native_tool_debs": [file_record(p) for p in sorted((work / "fedora-host-tools/packages").glob("*.deb"))],
        "reproduction_scripts": scripts, "jobs": jobs,
        "hardware_claims": {
            "tablet_booted_or_flashed": False, "bootable_tablet_image_produced": False,
            "adreno_acceleration_passed": False, "native_dpu_dsi_passed": False,
            "gpu_process_isolation_passed": False, "hardware_video_passed": False,
            "systemd_pid1_tested": False, "physical_input_or_wifi_tested": False,
            "android_gpu_binaries_used": False,
        },
    }
    destination = work / "fedora-build.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"evidence": file_record(destination),
                      "installed_packages": len(after), "new_packages": len(additions),
                      "retained_rpms": len(result["assembly"]["retained_rpms"]),
                      "software_smoke_passed": smoke["software_smoke_passed"]}, indent=2))


if __name__ == "__main__":
    main()
