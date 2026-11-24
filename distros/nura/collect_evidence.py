#!/usr/bin/env python3
"""Read this experiment's named files and emit an evidence inventory as JSON.

This tool is read-only. The work root may be /work in the build container or
the same Docker volume's confirmed path when read from its owner host.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def metadata(path, work):
    return {
        "path_in_container": str(pathlib.Path("/work") / path.relative_to(work)),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def clean_tail(path, limit=2500):
    # Keep the original bytes/hash separately; only the displayed excerpt loses
    # terminal color and APK progress bars.
    text = path.read_text(errors="replace")
    text = re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|.)", "", text)
    text = re.sub(r"\d+% [█ ]+", "", text)
    return text[-limit:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=pathlib.Path, default=pathlib.Path("/work"))
    args = parser.parse_args()
    work = args.work_root
    project = work / "pmwork"
    if not (project / "boot/alpine/media.json").is_file():
        parser.error("The selected work root has no verified-media record")
    result = {
        "schema_version": 1,
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Generic ARM builder and qemu-aarch64 userspace experiment; no TB371FC hardware acceptance",
        "source": {
            "pmbootstrap": {
                "url": "https://gitlab.nura.eco/nura/pmbootstrap.git",
                "commit": "e0dfe2cda7f3a0b70cdcc96f3060100839322aa4",
                "version": "3.12.1",
            },
            "pmaports": {
                "url": "https://gitlab.nura.eco/nura/pmaports.git",
                "commit": "d7e3e81fd579f01d4742157257897e2b07fade5c",
                "device_recipe": "device/community/device-qemu-aarch64",
                "device_recipe_version": "16-r1",
            },
            "fixed_initial_media_does_not_freeze_later_apk_repositories": True,
        },
        "environment": {
            "device": "doesvm",
            "ct_id": 102,
            "container": "tb371fc-build-20261123",
            "container_architecture": "x86_64",
            "guest_architecture": "aarch64",
            "guest_role": "Native ARM build environment",
            "acceleration": "TCG, not KVM",
            "virtual_cpus": 2,
            "guest_memory_mib": 2048,
            "host_binfmt_registration_changed": False,
            "physical_devices_exposed": False,
            "network": "QEMU user networking; no guest port forwarding",
            "bootstrap_http_server": "Container loopback 127.0.0.1:18083; only verified public media",
            "guest_work_path": "/work/pmwork",
            "guest_work_backing_path_in_container": "/work/pmwork/guest-share/pmwork",
        },
        "completed_job_records": {},
        "serial_command_records": {},
        "recorded_files": {},
    }

    for path in sorted(work.glob("nura-*.json")):
        entry = json.loads(path.read_text())
        entry["metadata_file"] = metadata(path, work)
        log = path.with_suffix(".log")
        if log.is_file():
            entry["log"] = metadata(log, work)
            entry["log"]["excerpt_tail"] = clean_tail(log)
        result["completed_job_records"][path.stem] = entry

    for path in sorted(project.glob("guest-*.json")):
        entry = json.loads(path.read_text())
        entry["metadata_file"] = metadata(path, work)
        log = path.with_suffix(".serial.log")
        if log.is_file():
            entry["log"] = metadata(log, work)
            entry["log"]["excerpt_tail"] = clean_tail(log)
        result["serial_command_records"][path.stem] = entry

    for relative in [
        "boot/alpine/media.json", "boot/alpine/gpg-verify.log",
        "boot/alpine/bootstrap-apks.json", "vm-command-01.json",
        "vm-command-02.json", "vm-command-03.json", "vm-02-stop.json",
        "guest-bootstrap-01.sh", "serial-command-before-interrupt.py",
        "serial_command.py", "fetch_media.py", "export_rootfs.py",
        "guest-share/guest-bootstrap.sh", "guest-share/guest-bootstrap-02.sh",
        "guest-share/guest-install.sh", "guest-share/guest-install-01.sh",
        "guest-share/complete_package_cache.py", "guest-share/cache-completion-01.json",
        "guest-share/cache-completion-02.json", "cache-completion-01-stop.json",
        "guest-share/cache-completion-03.json", "complete_package_cache-01.py",
        "complete_package_cache-02.py", "export-rootfs-01.py",
        "guest-share/pmos.cfg",
        "guest-share/arm-builder-packages.txt",
        "guest-share/rootfs-export.json", "guest-share/target-packages.txt",
        "guest-share/target-package-cache.json", "guest-share/pmwork/apk.static",
        "stop_builder.py", "cleanup.json",
    ]:
        path = project / relative
        if not path.is_file():
            continue
        entry = metadata(path, work)
        if path.name in {"media.json", "rootfs-export.json", "cache-completion-01.json",
                          "cache-completion-02.json", "cache-completion-03.json",
                          "cache-completion-01-stop.json", "cleanup.json"}:
            entry["record"] = json.loads(path.read_text())
        elif path.name == "target-package-cache.json":
            manifest = json.loads(path.read_text())
            entry["summary"] = {key: value for key, value in manifest.items()
                                if key not in ("files", "target_packages")}
        elif path.name.startswith("vm-command-"):
            entry["command_record"] = json.loads(path.read_text())
        elif path.name in {"arm-builder-packages.txt", "target-packages.txt"}:
            entry["packages"] = path.read_text().splitlines()
            entry["line_count"] = len(entry["packages"])
        elif path.name == "pmos.cfg":
            entry["configuration"] = path.read_text()
        result["recorded_files"][relative] = entry

    media = json.loads((project / "boot/alpine/media.json").read_text())
    result["verified_bootstrap_medium"] = media
    transcripts = [p.read_text(errors="replace") for p in project.glob("guest-*.serial.log")]
    native_verified = any(re.search(r"(?m)^NURA_NATIVE_CHROOT_VERIFIED\r?$", t)
                          for t in transcripts)
    target_transaction_complete = any(re.search(r"(?m)^NURA_TARGET_INSTALL_COMPLETED\r?$", t)
                                      for t in transcripts)
    builder_booted = any(re.search(r"(?m)^Linux localhost .+ aarch64 Linux\r?$", t)
                         for t in transcripts)
    export_file = project / "guest-share/rootfs-export.json"
    exported = False
    if export_file.is_file():
        export = json.loads(export_file.read_text())
        exported = export.get("archive_exit_code") == 0
    status = "rootfs_exported" if exported else (
        "target_transaction_complete" if target_transaction_complete else (
            "native_chroot_verified" if native_verified else (
                "builder_booted" if builder_booted else "media_verified"
            )
        )
    )
    result["result"] = {
        "status": status,
        "alpine_builder_booted": builder_booted,
        "native_pmb_bootstrap_complete": native_verified,
        "target_package_transaction_complete": target_transaction_complete,
        "target_rootfs_exported": exported,
        "offline_cache_complete": export.get("offline_cache_complete") if exported else None,
        "independent_offline_rebuild_tested": False,
        "target_rootfs_booted": False,
        "tablet_linux_boot_tested_by_this_experiment": False,
        "hardware_gpu_tested_by_this_experiment": False,
        "rootfs_gzip_integrity_verified": (
            result["completed_job_records"].get("nura-archive-integrity-01", {}).get("exit_code") == 0
        ),
        "owned_vm_and_media_server_stopped": (
            result["recorded_files"].get("cleanup.json", {}).get("record", {}).get(
                "all_owned_processes_exited", False)
        ),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
