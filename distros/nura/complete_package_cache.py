#!/usr/bin/env python3
"""Retain exact APKs omitted from the install cache, inside the ARM build VM.

The observed automatic cache omitted zero-payload metapackage archives. This
downloads missing installed versions with native apk fetch; it does not
install or upgrade target packages.
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import platform
import shlex
import subprocess


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=pathlib.Path,
                        default=pathlib.Path("/work/cache-completion-01.json"))
    args = parser.parse_args()
    if platform.machine() != "aarch64":
        parser.error("Run this helper only inside the disposable ARM build VM")
    if args.record.exists():
        parser.error("Retain the previous record and select a new attempt path")
    for path, commit in [
        ("/work/pmbootstrap", "e0dfe2cda7f3a0b70cdcc96f3060100839322aa4"),
        ("/work/pmaports", "d7e3e81fd579f01d4742157257897e2b07fade5c"),
    ]:
        if subprocess.check_output(["git", "-C", path, "rev-parse", "HEAD"], text=True).strip() != commit:
            raise SystemExit("Pinned source revision changed: " + path)
    os.environ["PMB_CHANNELS_CFG"] = "/work/pmaports/channels.cfg"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    inventory = pathlib.Path("/work/target-packages.txt")
    versions = inventory.read_text().splitlines()
    cache = pathlib.Path("/work/pmwork/cache_apk_aarch64")

    def scan_cache():
        # The work share is 9p. Stat each file once per snapshot, not once for
        # every target package: the latter performs O(n^2) remote metadata I/O.
        return [p for p in cache.iterdir() if p.name.endswith(".apk")
                and not p.is_symlink() and p.is_file()]

    cached_paths = scan_cache()

    def matches(package_version):
        return [p for p in cached_paths if
                (p.name == package_version + ".apk" or p.name.startswith(package_version + "."))]

    missing = []
    for version in versions:
        files = matches(version)
        if len(files) > 1:
            raise SystemExit("Ambiguous cached APK version: " + version)
        if not files:
            missing.append(version)
    specifications = []
    for version in missing:
        name, upstream_version, release = version.rsplit("-", 2)
        specifications.append(name + "=" + upstream_version + "-" + release)
    base = ["python3", "/work/pmbootstrap/pmbootstrap.py", "--as-root",
            "--config", "/work/pmos.cfg", "--timeout", "180", "--details-to-stdout"]
    # Use the same target chroot and physical cache as the successful install.
    # Try one small metapackage first. Only a successful probe permits the
    # remaining downloads; no trust/checksum validation is disabled.
    probe = next((spec for spec in specifications if spec.startswith("postmarketos-ui-console=")),
                 specifications[0] if specifications else None)
    fetch = ["apk", "--arch", "aarch64", "--cache-dir", "/var/cache/apk",
             "fetch", "--output", "/var/cache/apk"]
    shell_command = "set -eu; "
    if probe:
        shell_command += shlex.join([*fetch, probe])
        shell_command += "; printf '%s\\n' NURA_CACHE_SINGLE_PROBE_OK"
        remaining = [spec for spec in specifications if spec != probe]
        if remaining:
            shell_command += "; " + shlex.join([*fetch, *remaining])
    command = [*base, "chroot", "--rootfs", "--output", "stdout", "--",
               "/bin/sh", "-c", shell_command]
    record = {
        "start_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "inventory_sha256": sha256(inventory),
        "target_package_count": len(versions),
        "missing_before": missing,
        "single_package_probe": probe,
        "cache_directory_in_chroot": "/var/cache/apk",
        "cache_directory_in_guest": str(cache),
        "fetch_command": command if missing else None,
        "scope": "Retain exact installed APK versions; no target package transaction",
    }
    print(json.dumps(record, indent=2), flush=True)
    if missing:
        try:
            subprocess.run(command, check=True)
        finally:
            subprocess.run([*base, "shutdown"], check=True)
    if record["inventory_sha256"] != sha256(inventory):
        raise SystemExit("Installed package inventory changed during cache completion")
    cached_paths = scan_cache()
    for version in versions:
        if len(matches(version)) != 1:
            raise SystemExit("Expected one retained APK after fetch: " + version)
    record["all_target_packages_cached"] = True
    record["fetched_files"] = [{"package_version": version, "filename": matches(version)[0].name,
                                "sha256": sha256(matches(version)[0]),
                                "size_bytes": matches(version)[0].stat().st_size}
                               for version in missing]
    args.record.write_text(json.dumps(record, indent=2) + "\n")
    subprocess.run(["sync"], check=True)
    print(json.dumps(record, indent=2), flush=True)


if __name__ == "__main__":
    main()
