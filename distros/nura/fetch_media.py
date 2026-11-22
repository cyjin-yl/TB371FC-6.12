#!/usr/bin/env python3
"""Fetch and verify a fixed Alpine ARM VM bootstrap medium.

This creates ordinary files only. It does not format, mount, attach or boot a
disk and does not change binfmt registration. The VM is a build environment,
not a TB371FC hardware model.
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import struct
import subprocess
import urllib.request

VERSION = "3.24.4"
FILENAME = f"alpine-virt-{VERSION}-aarch64.iso"
BASE_URL = "https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/"
ISO_SHA256 = "cf88d8ba67389d20d9ed307366b52e487c15d7d3ee3233b62b95f709daa1d430"
SIGNER = "0482D84022F52DF1C4E7CD43293ACD0907D9495A"
KEY_URL = "https://alpinelinux.org/keys/ncopa.asc"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url, destination):
    if destination.exists():
        return
    partial = destination.with_name(destination.name + ".partial")
    with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as output:
        while block := response.read(1024 * 1024):
            output.write(block)
    partial.replace(destination)


def iso_directory(stream, extent, size, block_size):
    """Read ISO9660 records, including short Rock Ridge NM names."""
    stream.seek(extent * block_size)
    data = stream.read(size)
    offset = 0
    entries = {}
    while offset < len(data):
        length = data[offset]
        if length == 0:
            offset = (offset // block_size + 1) * block_size
            continue
        record = data[offset : offset + length]
        if len(record) != length or length < 34:
            raise ValueError("Malformed ISO directory record")
        name_length = record[32]
        name = record[33 : 33 + name_length]
        system_use = (33 + name_length + 1) & ~1
        rr_name = b""
        while system_use + 4 <= length:
            entry_size = record[system_use + 2]
            if entry_size < 4 or system_use + entry_size > length:
                break
            if record[system_use : system_use + 2] == b"NM" and entry_size >= 5:
                flags = record[system_use + 4]
                if not flags & 6:
                    rr_name += record[system_use + 5 : system_use + entry_size]
            system_use += entry_size
        if rr_name:
            name = rr_name
        if name not in (b"\0", b"\1"):
            name = name.decode("utf-8").split(";", 1)[0].rstrip(".")
            entries[name.lower()] = {
                "name": name,
                "extent": struct.unpack_from("<I", record, 2)[0],
                "size": struct.unpack_from("<I", record, 10)[0],
                "directory": bool(record[25] & 2),
            }
        offset += length
    return entries


def extract_boot_files(iso, destination):
    result = {}
    with iso.open("rb") as source:
        source.seek(16 * 2048)
        descriptor = source.read(2048)
        if descriptor[:7] != b"\x01CD001\x01":
            raise ValueError("Expected a primary ISO9660 volume descriptor")
        block_size = struct.unpack_from("<H", descriptor, 128)[0]
        if block_size != 2048:
            raise ValueError("Unexpected ISO logical block size")
        root = descriptor[156:190]
        root_entries = iso_directory(
            source,
            struct.unpack_from("<I", root, 2)[0],
            struct.unpack_from("<I", root, 10)[0],
            block_size,
        )
        boot = root_entries["boot"]
        if not boot["directory"]:
            raise ValueError("ISO boot entry is not a directory")
        entries = iso_directory(source, boot["extent"], boot["size"], block_size)
        for filename in ("vmlinuz-virt", "initramfs-virt", "modloop-virt"):
            entry = entries[filename]
            if entry["directory"] or entry["extent"] * block_size + entry["size"] > iso.stat().st_size:
                raise ValueError("Invalid boot file extent")
            source.seek(entry["extent"] * block_size)
            data = source.read(entry["size"])
            if len(data) != entry["size"]:
                raise ValueError("Truncated boot file")
            output = destination / filename
            output.write_bytes(data)
            result[filename] = {"size_bytes": len(data), "sha256": sha256(output)}
    return result


def extract_arm64_image(destination):
    # Linux's EFI zboot header declares the compressed payload's offset, size
    # and compression name. See drivers/firmware/efi/libstub/zboot-header.S:
    # https://github.com/torvalds/linux/blob/v6.12/drivers/firmware/efi/libstub/zboot-header.S
    data = (destination / "vmlinuz-virt").read_bytes()
    if data[:8] != b"MZ\0\0zimg" or data[24:29] != b"gzip\0":
        raise ValueError("Expected the verified release's gzip EFI zboot image")
    offset, size = struct.unpack_from("<II", data, 8)
    if offset < 64 or size < 20 or offset + size > len(data):
        raise ValueError("Invalid EFI zboot payload range")
    image = gzip.decompress(data[offset : offset + size])
    if image[56:60] != b"ARM\x64":
        raise ValueError("Decompressed payload lacks the ARM64 Image magic")
    output = destination / "Image"
    output.write_bytes(image)
    return {
        "method": "Declared EFI zboot gzip payload, then ARM64 Image magic check",
        "payload_offset": offset,
        "payload_size": size,
        "size_bytes": len(image),
        "sha256": sha256(output),
    }


def extract_bootstrap_repository(iso, destination):
    """Extract only the signed ISO's aarch64 APK repository for local netboot."""
    result = {}
    output = destination / "apks" / "aarch64"
    output.mkdir(parents=True, exist_ok=True)
    with iso.open("rb") as source:
        source.seek(16 * 2048 + 156)
        root = source.read(34)
        entries = iso_directory(source, struct.unpack_from("<I", root, 2)[0],
                                struct.unpack_from("<I", root, 10)[0], 2048)
        for component in ("apks", "aarch64"):
            entry = entries[component]
            if not entry["directory"]:
                raise ValueError("Expected a directory in the ISO APK repository")
            entries = iso_directory(source, entry["extent"], entry["size"], 2048)
        for entry in entries.values():
            name = entry["name"]
            if entry["directory"] or pathlib.PurePosixPath(name).name != name:
                raise ValueError("Unexpected APK repository entry")
            source.seek(entry["extent"] * 2048)
            data = source.read(entry["size"])
            if len(data) != entry["size"]:
                raise ValueError("Truncated APK repository file")
            path = output / name
            path.write_bytes(data)
            result[name] = {"size_bytes": len(data), "sha256": sha256(path)}
    if "APKINDEX.tar.gz" not in result:
        raise ValueError("The fixed ISO APK repository has no signed APKINDEX")
    (destination / "bootstrap-apks.json").write_text(json.dumps(result, indent=2) + "\n")
    return {
        "relative_path": "apks/aarch64",
        "file_count": len(result),
        "manifest_sha256": sha256(destination / "bootstrap-apks.json"),
        "source": "Files extracted from the verified fixed-version ISO",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = {
        FILENAME: BASE_URL + FILENAME,
        FILENAME + ".sha256": BASE_URL + FILENAME + ".sha256",
        FILENAME + ".asc": BASE_URL + FILENAME + ".asc",
        "ncopa.asc": KEY_URL,
    }
    for name, url in sources.items():
        print("Fetching", url, flush=True)
        download(url, args.output / name)
    iso = args.output / FILENAME
    actual = sha256(iso)
    listed = (args.output / (FILENAME + ".sha256")).read_text().split()[0]
    if actual != ISO_SHA256 or listed != ISO_SHA256:
        raise SystemExit("ISO checksum does not match the fixed official release")

    keyring = args.output / "gnupg"
    keyring.mkdir(mode=0o700, exist_ok=True)
    keyring.chmod(0o700)
    gpg = ["gpg", "--batch", "--homedir", str(keyring)]
    subprocess.run(gpg + ["--import", str(args.output / "ncopa.asc")], check=True)
    fingerprint = subprocess.check_output(gpg + ["--with-colons", "--fingerprint"], text=True)
    if f"fpr:::::::::{SIGNER}:" not in fingerprint:
        raise SystemExit("Official signing-key fingerprint mismatch")
    verification = subprocess.run(
        gpg + ["--status-fd", "1", "--verify", str(args.output / (FILENAME + ".asc")), str(iso)],
        capture_output=True, text=True,
    )
    (args.output / "gpg-verify.log").write_text(verification.stdout + verification.stderr)
    print(verification.stdout + verification.stderr, end="", flush=True)
    if verification.returncode or f"[GNUPG:] VALIDSIG {SIGNER} " not in verification.stdout:
        raise SystemExit("ISO signature was not validated against the fixed signing key")
    extracted = extract_boot_files(iso, args.output)
    image = extract_arm64_image(args.output)
    bootstrap_repository = extract_bootstrap_repository(iso, args.output)
    record = {
        "alpine_version": VERSION,
        "architecture": "aarch64",
        "role": "Generic ARM virtual-machine bootstrap medium; not a TB371FC image",
        "sources": {name: {"url": url, "sha256": sha256(args.output / name)} for name, url in sources.items()},
        "verified_signer_fingerprint": SIGNER,
        "signature_verification_exit_code": verification.returncode,
        "extracted_boot_files": extracted,
        "arm64_image": image,
        "bootstrap_repository": bootstrap_repository,
    }
    (args.output / "media.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
