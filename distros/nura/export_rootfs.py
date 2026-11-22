#!/usr/bin/env python3
"""Export the completed qemu-aarch64 experiment's tree, with provenance.

Run inside the build container after guest-install.sh exits successfully.
This creates ordinary archive/manifest files only; it never mounts or formats
a filesystem and never operates on a physical block device.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import platform
import struct
import subprocess
import sys


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path):
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-record", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--record", type=pathlib.Path,
                        default=pathlib.Path("/work/pmwork/guest-share/rootfs-export.json"))
    parser.add_argument("--cache-manifest", type=pathlib.Path,
                        default=pathlib.Path("/work/pmwork/guest-share/target-package-cache.json"))
    parser.add_argument("--require-complete-cache", action="store_true",
                        help="Also require a unique cached APK for every installed package")
    args = parser.parse_args()
    share = pathlib.Path("/work/pmwork/guest-share")
    work = share / "pmwork"
    rootfs = work / "chroot_rootfs_qemu-aarch64"
    report = args.record
    cache_manifest = args.cache_manifest
    partial = args.output.with_name(args.output.name + ".partial")
    if any(path.exists() for path in (args.output, partial, report, cache_manifest)):
        parser.error("Export output/record already exists; retain it and choose a new explicit attempt")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    install = json.loads(args.install_record.read_text())
    if install.get("guest_exit_code") != 0:
        parser.error("The recorded guest install/verification did not complete successfully")
    if not rootfs.is_dir() or rootfs.is_symlink():
        parser.error("Expected the experiment's ordinary qemu-aarch64 rootfs directory")
    inventory = share / "target-packages.txt"
    if not inventory.is_file() or not inventory.read_text().strip():
        parser.error("Missing target package inventory from guest verification")

    # Inspect only this synthetic target tree. Do not print password hash data.
    shadow = (rootfs / "etc/shadow").resolve(strict=True)
    shadow.relative_to(rootfs.resolve())
    locked = {}
    for line in shadow.read_text().splitlines():
        fields = line.split(":")
        if fields[0] in ("root", "research"):
            locked[fields[0]] = fields[1].startswith(("!", "*"))
    if locked != {"root": True, "research": True}:
        raise SystemExit("Synthetic target passwords have not both been locked")

    turnip = (rootfs / "usr/lib/libvulkan_freedreno.so").resolve(strict=True)
    turnip.relative_to(rootfs.resolve())
    with turnip.open("rb") as stream:
        header = stream.read(64)
    if header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 183:
        raise SystemExit("Expected an ELF64 little-endian AArch64 Turnip library")
    msm_entry = rootfs / "usr/lib/dri/msm_dri.so"
    msm_loader = msm_entry.resolve(strict=True)
    msm_loader.relative_to(rootfs.resolve())
    with msm_loader.open("rb") as stream:
        header = stream.read(64)
    if header[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", header, 18)[0] != 183:
        raise SystemExit("Expected an AArch64 ELF DRI loader at the msm entry")

    boot_files = {}
    for relative in ("boot/initramfs", "boot/EFI/BOOT/BOOTAA64.EFI",
                     "boot/loader/entries/pmos.conf"):
        path = (rootfs / relative).resolve(strict=True)
        path.relative_to(rootfs.resolve())
        boot_files[relative] = file_record(path)
    for path in sorted((rootfs / "boot").glob("vmlinuz*")):
        if path.is_file():
            resolved = path.resolve(strict=True)
            resolved.relative_to(rootfs.resolve())
            boot_files[str(path.relative_to(rootfs))] = file_record(resolved)

    cached = []
    for directory in sorted(work.glob("cache_apk*")):
        if not directory.is_dir() or directory.is_symlink():
            continue
        for path in sorted(directory.rglob("*")):
            if path.is_file() and not path.is_symlink():
                cached.append(file_record(path))
    if not cached:
        raise SystemExit("No retained APK cache files; record package inputs before exporting")
    target_packages = inventory.read_text().splitlines()
    cached_apks = [item for item in cached if item["path"].endswith(".apk")]
    package_inputs = []
    missing_packages = []
    ambiguous_packages = []
    for package_version in target_packages:
        matches = [item for item in cached_apks
                   if pathlib.Path(item["path"]).name == package_version + ".apk" or
                   pathlib.Path(item["path"]).name.startswith(package_version + ".")]
        if len(matches) == 1:
            package_inputs.append({"package_version": package_version, **matches[0]})
        elif not matches:
            missing_packages.append(package_version)
        else:
            ambiguous_packages.append({"package_version": package_version, "candidates": matches})
    cache_complete = not missing_packages and not ambiguous_packages
    if args.require_complete_cache and not cache_complete:
        raise SystemExit("APK cache is incomplete or ambiguous; the requested complete-cache gate failed")
    installed_db = rootfs / "lib/apk/db/installed"
    missing_metadata = []
    for entry in installed_db.read_text().split("\n\n"):
        fields = {line[0]: line[2:] for line in entry.splitlines()
                  if len(line) >= 2 and line[1] == ":" and line[0] in "PVACIS"}
        version = fields.get("P", "") + "-" + fields.get("V", "")
        if version in missing_packages:
            missing_metadata.append({
                "package_version": version,
                "package": fields.get("P"), "version": fields.get("V"),
                "architecture": fields.get("A"),
                "installed_control_checksum": fields.get("C"),
                "recorded_archive_size_bytes": int(fields.get("S", "0")),
                "installed_payload_size_bytes": int(fields.get("I", "0")),
            })

    # A diagnostic pmb chroot invocation adds its private build repository.
    # Restore the actual public repository list before exporting a standalone
    # tree, recording the exact normalization instead of shipping that path.
    repositories = rootfs / "etc/apk/repositories"
    before = repositories.read_bytes()
    private_repository = "/mnt/pmbootstrap/packages/edge"
    public_repositories = [line for line in before.decode().splitlines()
                           if line and line != private_repository]
    expected = [
        "https://mirror.postmarketos.org/postmarketos/main",
        "https://dl-cdn.alpinelinux.org/edge/main",
        "https://dl-cdn.alpinelinux.org/edge/community",
        "https://dl-cdn.alpinelinux.org/edge/testing",
    ]
    if public_repositories != expected:
        raise SystemExit("Unexpected target APK repository list; inspect it before exporting")
    after = ("\n".join(public_repositories) + "\n").encode()
    if before != after:
        repositories.write_bytes(after)
    repository_configuration = {
        "path": str(repositories),
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "removed_build_repository": private_repository if before != after else None,
        "public_repositories": public_repositories,
    }
    cache_manifest.write_text(json.dumps({
        "scope": "Retained download cache for this native ARM pmbootstrap work directory",
        "files": cached,
        "file_count": len(cached),
        "apk_file_count": len(cached_apks),
        "target_package_count": len(target_packages),
        "cached_target_package_count": len(package_inputs),
        "all_target_packages_cached": cache_complete,
        "offline_cache_complete": cache_complete,
        "missing_target_packages": missing_packages,
        "missing_target_package_metadata": missing_metadata,
        "ambiguous_target_packages": ambiguous_packages,
        "target_packages": package_inputs,
        "total_size_bytes": sum(item["size_bytes"] for item in cached),
    }, indent=2) + "\n")

    command = [
        "tar", "--sort=name", "--numeric-owner", "--acls", "--xattrs",
        "--format=posix", "--pax-option=delete=atime,delete=ctime",
        "--one-file-system", "--use-compress-program=gzip -n -1",
        "-C", str(rootfs), "-cf", str(partial), ".",
    ]
    print(json.dumps({"archive_command": command}), flush=True)
    subprocess.run(command, check=True)
    partial.replace(args.output)
    result = {
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Generic qemu-aarch64 userspace tree, not a TB371FC boot/install image",
        "export_environment": {
            "architecture": platform.machine(),
            "python": sys.version,
            "tools": {name: subprocess.check_output([name, "--version"], text=True).splitlines()[0]
                      for name in ("tar", "gzip", "qemu-system-aarch64")},
        },
        "source_rootfs": str(rootfs),
        "successful_guest_install_record": file_record(args.install_record),
        "artifact": file_record(args.output),
        "archive_command": command,
        "archive_exit_code": 0,
        "synthetic_accounts_locked": locked,
        "repository_configuration": repository_configuration,
        "target_package_inventory": file_record(inventory),
        "target_package_count": len(target_packages),
        "all_target_packages_cached": cache_complete,
        "offline_cache_complete": cache_complete,
        "cached_target_package_count": len(package_inputs),
        "missing_target_packages": missing_packages,
        "require_complete_cache_requested": args.require_complete_cache,
        "independent_offline_rebuild_tested": False,
        "retained_cache_manifest": file_record(cache_manifest),
        "bootstrap_apk_static": file_record(work / "apk.static"),
        "turnip_library": {**file_record(turnip), "elf_machine": 183, "elf_class": 64},
        "msm_dri_loader": {
            "entry_path": str(msm_entry),
            "link_target": str(msm_entry.readlink()) if msm_entry.is_symlink() else None,
            **file_record(msm_loader),
            "elf_machine": 183,
            "elf_class": 64,
            "scope": "DRI loader entry present; hardware driver initialization was not tested",
        },
        "target_boot_files": boot_files,
        "target_kernel_packages": [name for name in target_packages
                                   if name.startswith("linux-postmarketos-")],
        "target_module_directories": sorted(path.name for path in
                                            (rootfs / "usr/lib/modules").iterdir()
                                            if path.is_dir()),
        "gpu_acceleration_tested": False,
        "target_rootfs_booted": False,
        "tablet_boot_tested": False,
        "bit_for_bit_rebuild_demonstrated": False,
    }
    report.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
