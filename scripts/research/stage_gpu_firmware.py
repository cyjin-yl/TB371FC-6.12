#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage only captured TB371FC GPU firmware from an already extracted directory.

Offline, standard-library-only, Linux/POSIX tool. It never extracts images,
accesses a phone, loads firmware, authenticates signatures, or installs files
into a running system. All inputs must match the pinned Android capture.
Unknown files are never enumerated or copied. Existing outputs are refused.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys


FIRMWARE_LIMIT = 32 * 1024 * 1024
EVIDENCE_LIMIT = 1024 * 1024
TRUSTED_CAPTURE_SHA256 = "67492d703071ebe5fa6abbdbc344103ecc427a88b85bc1ce55b7b54e0cdcae61"
DEFAULT_EVIDENCE = (Path(__file__).absolute().parents[2] /
                    "docs/research/2026-11-23/evidence/android-gpu.json")
CAPTURE_REFERENCE = "docs/research/2026-11-23/evidence/android-gpu.json"
KERNEL_VERSION = "6.12.114"
ZAP_DESTINATION = "qcom/sm8250/lenovo/tb371fc/a650_zap.mbn"
BASE_FILES = {"a650_gmu.bin": "qcom/a650_gmu.bin",
              "a650_sqe.fw": "qcom/a650_sqe.fw"}
INPUT_NAME = re.compile(r"a650_(?:gmu\.bin|sqe\.fw|zap\.(?:elf|mdt|b[0-9]{2}))")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
PT_LOAD = 1
QCOM_MDT_TYPE_MASK = 7 << 24
QCOM_MDT_TYPE_HASH = 2 << 24


class FirmwareError(ValueError):
    """An input, provenance, layout or output-boundary check failed."""


def safe_absolute(path: Path | str) -> Path:
    raw = os.fspath(path)
    if not raw or any(ord(char) < 32 or ord(char) == 127 for char in raw):
        raise FirmwareError("empty/control-character path is not allowed")
    candidate = Path(raw)
    if ".." in candidate.parts:
        raise FirmwareError("parent traversal '..' is not allowed")
    result = Path(os.path.abspath(candidate))
    if len(result.parts) > 1 and result.parts[1] in {"dev", "proc", "sys", "vendor", "odm", "system"}:
        raise FirmwareError("live device/system paths are not extracted firmware inputs")
    return result


@contextmanager
def open_directory(path: Path | str):
    """Open each component with O_NOFOLLOW; no resolve-then-open symlink gap."""
    absolute = safe_absolute(path)
    descriptor = os.open("/", DIR_FLAGS)
    try:
        for name in absolute.parts[1:]:
            next_descriptor = os.open(name, DIR_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        yield descriptor
    finally:
        os.close(descriptor)


def read_regular(directory: int, name: str, limit: int) -> bytes:
    if Path(name).name != name or name in ("", ".", ".."):
        raise FirmwareError("input must be a single fixed filename")
    try:
        before = os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError as error:
        raise FirmwareError(f"required input missing: {name}") from error
    if not stat.S_ISREG(before.st_mode):
        raise FirmwareError(f"input is not a regular file (symlinks refused): {name}")
    if not 0 < before.st_size <= limit:
        raise FirmwareError(f"input size is empty or exceeds the limit: {name}")
    descriptor = os.open(name, READ_FLAGS, dir_fd=directory)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise FirmwareError(f"input changed while opening: {name}")
        chunks, size = [], 0
        while size <= limit:
            chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        after = os.fstat(descriptor)
        if size > limit or size != before.st_size or (
                after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (
                before.st_size, before.st_mtime_ns, before.st_ctime_ns):
            raise FirmwareError(f"input changed or exceeded its bound while reading: {name}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def load_capture(path: Path | str) -> tuple[dict, dict[str, dict]]:
    absolute = safe_absolute(path)
    with open_directory(absolute.parent) as directory:
        data = read_regular(directory, absolute.name, EVIDENCE_LIMIT)
    if hashlib.sha256(data).hexdigest() != TRUSTED_CAPTURE_SHA256:
        raise FirmwareError("evidence does not match the pinned TB371FC Android capture")
    try:
        capture = json.loads(data)
    except (ValueError, UnicodeError) as error:
        raise FirmwareError("invalid capture JSON") from error
    if capture.get("schema_version") != 1 or not isinstance(capture.get("firmware"), list):
        raise FirmwareError("unsupported capture schema")
    expected = {}
    for row in capture["firmware"]:
        path = row.get("path", "")
        name = path.removeprefix("/vendor/firmware/")
        if path != "/vendor/firmware/" + name or not INPUT_NAME.fullmatch(name):
            continue
        if (name in expected or type(row.get("size")) is not int or
                not 0 < row["size"] <= FIRMWARE_LIMIT or
                not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", ""))):
            raise FirmwareError("invalid or duplicate expected firmware record")
        expected[name] = {"size": row["size"], "sha256": row["sha256"], "capture_path": path}
    return capture, expected


def inspect_zap(data: bytes) -> dict:
    """Strict ELF32/MDT structural gate matching the v6.12.114 loader rules.

    This is intentionally separate from gpu_acceptance.inspect_zap(), whose
    public API collects best-effort diagnostics instead of rejecting a package.
    No signature, certificate or executable-payload authentication is performed.
    """
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x01\x01":
        raise FirmwareError("ZAP must have a little-endian ELF32 version-1 header")
    version, = struct.unpack_from("<I", data, 20)
    phoff, = struct.unpack_from("<I", data, 28)
    ehsize, phsize, phnum = struct.unpack_from("<HHH", data, 40)
    table_end = phoff + phsize * phnum
    if (version != 1 or ehsize != 52 or phsize != 32 or not 2 <= phnum <= 100 or
            phoff < ehsize or table_end > len(data)):
        raise FirmwareError("invalid or unsupported ZAP program-header table")
    headers = []
    for index in range(phnum):
        kind, offset, _, _, filesz, memsz, flags, _ = struct.unpack_from("<8I", data, phoff + 32 * index)
        headers.append({"index": index, "type": kind, "file_offset": offset,
                        "file_size": filesz, "memory_size": memsz, "flags": flags})
    first = headers[0]
    if first["type"] == PT_LOAD or not table_end <= first["file_size"] <= len(data):
        raise FirmwareError("invalid Qualcomm metadata header segment")
    hashes = [row for row in headers[1:]
              if row["flags"] & QCOM_MDT_TYPE_MASK == QCOM_MDT_TYPE_HASH]
    if not hashes or not 0 < hashes[0]["file_size"] <= FIRMWARE_LIMIT:
        raise FirmwareError("Qualcomm metadata hash segment is missing or invalid")
    hash_segment = hashes[0]
    required = {}
    if first["file_size"] + hash_segment["file_size"] == len(data):
        hash_source = "packed immediately after metadata header"
    elif hash_segment["file_offset"] + hash_segment["file_size"] <= len(data):
        hash_source = "embedded at hash program-header offset"
    else:
        hash_source = f"a650_zap.b{hash_segment['index']:02d}"
        required[hash_source] = {"segment_index": hash_segment["index"],
                                 "size": hash_segment["file_size"], "reason": "metadata hash"}
    valid = [row for row in headers if row["type"] == PT_LOAD and row["memory_size"] and
             row["flags"] & QCOM_MDT_TYPE_MASK != QCOM_MDT_TYPE_HASH]
    if not valid:
        raise FirmwareError("ZAP has no non-hash loadable segment")
    for row in valid:
        if row["file_size"] > row["memory_size"] or row["file_size"] > FIRMWARE_LIMIT:
            raise FirmwareError("loadable ZAP segment has invalid file/memory size")
        if row["file_offset"] + row["file_size"] > 0xffffffff:
            raise FirmwareError("loadable ZAP segment file extent overflows ELF32")
    # qcom_mdt_bins_are_split() checks ALL nonempty program headers, including
    # hash/non-loadable ones. Only the subsequent payload requests use valid.
    split = any(row["file_offset"] + row["file_size"] > len(data)
                for row in headers if row["file_size"])
    if split:
        # The loader uses split files for ALL valid nonempty segments once any
        # nonempty header lies outside the file. Zero-file-size/BSS needs no file.
        for row in valid:
            if row["file_size"]:
                name = f"a650_zap.b{row['index']:02d}"
                required[name] = {"segment_index": row["index"], "size": row["file_size"],
                                  "reason": "loadable payload"}
    return {"format": "ELF32 little endian", "program_header_count": phnum,
            "split_payload_required": split, "metadata_header_bytes": first["file_size"],
            "metadata_hash_bytes": hash_segment["file_size"], "metadata_hash_source": hash_source,
            "loadable_segments": valid, "required_split_files": required,
            "signature_authentication": "not performed"}


def plan_firmware(source: Path | str, zap_format: str, evidence: Path | str = DEFAULT_EVIDENCE) -> tuple[dict, dict[str, bytes]]:
    if zap_format not in ("elf", "mdt"):
        raise FirmwareError("choose exactly one ZAP input format: elf or mdt")
    capture, expected = load_capture(evidence)
    files, records = {}, []
    with open_directory(source) as directory:
        def add(name: str, destination: str, role: str, expected_size: int | None = None) -> bytes:
            if not INPUT_NAME.fullmatch(name) or name not in expected:
                raise FirmwareError(f"firmware is absent from the pinned capture: {name}")
            data = read_regular(directory, name, FIRMWARE_LIMIT)
            if expected_size is not None and len(data) != expected_size:
                raise FirmwareError(f"split segment length does not match ELF: {name}")
            digest = hashlib.sha256(data).hexdigest()
            if len(data) != expected[name]["size"] or digest != expected[name]["sha256"]:
                raise FirmwareError(f"firmware does not match the TB371FC capture: {name}")
            relative = "lib/firmware/" + destination
            files[relative] = data
            records.append({"source_filename": name, "capture_path": expected[name]["capture_path"],
                            "destination": relative, "size": len(data), "sha256": digest, "role": role})
            return data

        for name, destination in BASE_FILES.items():
            add(name, destination, "GMU" if name.endswith(".bin") else "SQE")
        zap = add("a650_zap." + zap_format, ZAP_DESTINATION, "ZAP ELF/MDT")
        layout = inspect_zap(zap)
        if zap_format == "elf" and (layout["split_payload_required"] or layout["required_split_files"]):
            raise FirmwareError("selected .elf is not a complete image; no automatic MDT fallback")
        for name, required in sorted(layout["required_split_files"].items()):
            add(name, str(Path(ZAP_DESTINATION).parent / name), required["reason"], required["size"])

    manifest = {"schema_version": 1, "tool": "stage_gpu_firmware.py", "device": "Lenovo TB371FC",
                "scope": "GPU firmware staging only; no signature authentication or hardware test",
                "provenance": {"basis": "byte-for-byte match with this owner's recorded Android capture",
                               "evidence_reference": CAPTURE_REFERENCE,
                               "evidence_sha256": TRUSTED_CAPTURE_SHA256,
                               "capture_utc": capture.get("capture_utc")},
                "kernel_contract": {"version": KERNEL_VERSION,
                                    "gmu": BASE_FILES["a650_gmu.bin"], "sqe": BASE_FILES["a650_sqe.fw"],
                                    "zap": ZAP_DESTINATION,
                                    "loader": "drivers/soc/qcom/mdt_loader.c",
                                    "board_dts": "mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts"},
                "selected_zap_input": "a650_zap." + zap_format, "zap_layout": layout,
                "files": sorted(records, key=lambda row: row["destination"])}
    return manifest, files


def publish_new(parent: int, name: str, files: dict[str, bytes]) -> None:
    """Exclusive new directory; every child is created via held directory FDs."""
    os.mkdir(name, 0o700, dir_fd=parent)  # Refuses files, directories and dangling symlinks.
    root = os.open(name, DIR_FLAGS, dir_fd=parent)
    root_identity = os.fstat(root)
    directories = {(): root}
    created_files, created_directories = [], []
    try:
        # Publish the manifest after firmware, then the checksum list. A killed
        # process cannot leave an early manifest describing unwritten payloads.
        order = sorted(files, key=lambda value: (value == "SHA256SUMS",
                                                value == "gpu-firmware-manifest.json", value))
        for relative in order:
            data = files[relative]
            components = Path(relative).parts
            if Path(relative).is_absolute() or ".." in components or not components:
                raise FirmwareError("unsafe internal output mapping")
            current = ()
            for part in components[:-1]:
                following = current + (part,)
                if following not in directories:
                    os.mkdir(part, 0o755, dir_fd=directories[current])
                    child = os.open(part, DIR_FLAGS, dir_fd=directories[current])
                    directories[following] = child
                    created_directories.append((directories[current], part))
                current = following
            descriptor = os.open(components[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                 0o644, dir_fd=directories[current])
            created_files.append((directories[current], components[-1]))
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
    except BaseException:
        # Remove only entries created here; never recurse through a foreign tree.
        for directory, filename in reversed(created_files):
            os.unlink(filename, dir_fd=directory)
        for directory, dirname in reversed(created_directories):
            os.rmdir(dirname, dir_fd=directory)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) == (root_identity.st_dev, root_identity.st_ino):
            os.rmdir(name, dir_fd=parent)
        raise
    finally:
        for descriptor in reversed(list(directories.values())):
            os.close(descriptor)


def stage_firmware(source: Path | str, output: Path | str, zap_format: str,
                   evidence: Path | str = DEFAULT_EVIDENCE) -> dict:
    source, output = safe_absolute(source), safe_absolute(output)
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise FirmwareError("source and staging prefix must not overlap")
    with open_directory(output.parent) as parent:
        try:
            os.stat(output.name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FirmwareError("staging prefix already exists; overwriting is forbidden")
        manifest, files = plan_firmware(source, zap_format, evidence)
        manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
        files["gpu-firmware-manifest.json"] = manifest_bytes
        files["SHA256SUMS"] = "".join(hashlib.sha256(data).hexdigest() + "  " + name + "\n"
                                       for name, data in sorted(files.items())).encode()
        publish_new(parent, output.name, files)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="already extracted vendor firmware directory")
    parser.add_argument("--output", type=Path, required=True, help="new staging prefix; parent must exist")
    parser.add_argument("--zap-format", choices=("elf", "mdt"), required=True,
                        help="explicit input; never falls back from an incomplete package")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE,
                        help="copy of the pinned Android GPU JSON; other evidence hashes are refused")
    args = parser.parse_args()
    try:
        manifest = stage_firmware(args.source, args.output, args.zap_format, args.evidence)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"status": "staged", "firmware_files": len(manifest["files"]),
                      "selected_zap_input": manifest["selected_zap_input"],
                      "signature_authentication": "not performed"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
