#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only vermagic, imported CRC and retained BTF checks for ARM64 modules.

This complements verify_module_signatures.py; it does not load a module,
establish kernel trust or replace the separate detached-signature check.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import struct


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def snapshot(path):
    st = path.lstat()
    require(stat.S_ISREG(st.st_mode), "ordinary file required: " + str(path))
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read(path, limit=256 * 1024**2):
    before = snapshot(path)
    require(before[3] <= limit, "file exceeds bound: " + str(path))
    data = path.read_bytes()
    require(snapshot(path) == before and len(data) == before[3], "input changed: " + str(path))
    return data, before


def c_string(table, offset):
    require(0 <= offset < len(table), "string offset outside table")
    end = table.find(b"\0", offset)
    require(end >= offset, "unterminated ELF string")
    return table[offset:end].decode("ascii")


def sections(data):
    require(len(data) >= 64, "truncated ELF header")
    h = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    require(h[0][:7] == b"\x7fELF\x02\x01\x01" and h[1:4] == (1, 183, 1),
            "little-endian AArch64 ET_REL required")
    require(h[8] == 64 and h[10] == 0 and h[11] == 64 and 0 < h[12] < 65535
            and 0 < h[13] < h[12] and 64 <= h[6] <= len(data) - h[12] * 64,
            "invalid ELF section table")
    table = [struct.unpack_from("<IIQQQQIIQQ", data, h[6] + i * 64) for i in range(h[12])]
    for s in table:
        require(s[1] == 8 or (s[4] <= len(data) and s[5] <= len(data) - s[4]),
                "section exceeds file")
    names = table[h[13]]
    require(names[1] == 3, "invalid section-name string table")
    strings = data[names[4]:names[4] + names[5]]
    result = {}
    for i, s in enumerate(table):
        name = c_string(strings, s[0])
        require(name not in result, "duplicate section name: " + name)
        result[name] = {"index": i, "header": s, "data": data[s[4]:s[4] + s[5]] if s[1] != 8 else b""}
    return result, table


def symvers(raw):
    result = {}
    for line in raw.decode("ascii").splitlines():
        cols = line.split("\t")
        require(len(cols) in (4, 5) and re.fullmatch(r"0x[0-9a-fA-F]{8}", cols[0])
                and cols[1] and cols[2], "invalid Module.symvers entry")
        require(cols[1] not in result, "duplicate Module.symvers symbol: " + cols[1])
        result[cols[1]] = int(cols[0], 16)
    require(result, "empty Module.symvers")
    return result


def module_abi(data, release, exported):
    section, table = sections(data)
    for name in (".modinfo", "__versions", ".symtab", ".BTF"):
        require(name in section, "missing required section: " + name)
    require(not any(x.startswith((".debug_", ".zdebug_")) for x in section),
            "DWARF debug sections were not stripped")
    info = section[".modinfo"]["data"].split(b"\0")
    vermagic = [x[len(b"vermagic="):].decode("ascii") for x in info if x.startswith(b"vermagic=")]
    require(vermagic == [release + " SMP preempt mod_unload modversions aarch64"],
            "module vermagic differs from the exact release/profile")
    version_bytes = section["__versions"]["data"]
    require(version_bytes and len(version_bytes) % 64 == 0, "invalid ARM64 __versions size")
    versions = {}
    for offset in range(0, len(version_bytes), 64):
        crc, name_bytes = struct.unpack_from("<Q56s", version_bytes, offset)
        require(b"\0" in name_bytes, "unterminated module version symbol")
        name, padding = name_bytes.split(b"\0", 1)
        require(name and not any(padding) and crc <= 0xffffffff, "invalid module version record")
        symbol = name.decode("ascii")
        require(symbol not in versions, "duplicate imported version: " + symbol)
        require(exported.get(symbol) == crc, "imported CRC differs or symbol absent: " + symbol)
        versions[symbol] = crc
    require("module_layout" in versions, "missing module_layout version")
    syms = section[".symtab"]
    sh = syms["header"]
    require(sh[1] == 2 and sh[9] == 24 and sh[5] % 24 == 0 and 0 < sh[6] < len(table),
            "invalid ELF symbol table")
    strings_header = table[sh[6]]
    require(strings_header[1] == 3, "invalid symbol string table")
    strings = data[strings_header[4]:strings_header[4] + strings_header[5]]
    required_imports, weak_imports = set(), set()
    for offset in range(0, len(syms["data"]), 24):
        name, info, other, index, value, size = struct.unpack_from("<IBBHQQ", syms["data"], offset)
        if index == 0 and name:
            symbol = c_string(strings, name)
            if info >> 4 == 1:
                required_imports.add(symbol)
            elif info >> 4 == 2:
                weak_imports.add(symbol)
    require(required_imports <= versions.keys(),
            "undefined strong symbol lacks CRC: " + ",".join(sorted(required_imports - versions.keys())))
    require((weak_imports & exported.keys()) <= versions.keys(), "exported weak import lacks CRC")
    btf = section[".BTF"]["data"]
    require(len(btf) >= 24, "truncated BTF header")
    magic, version, flags, header_len, type_off, type_len, str_off, str_len = struct.unpack_from("<HBBIIIII", btf)
    require((magic, version, flags, header_len) == (0xeb9f, 1, 0, 24)
            and type_len > 0 and str_len > 0
            and header_len + type_off + type_len <= len(btf)
            and header_len + str_off + str_len <= len(btf)
            and (type_off + type_len <= str_off or str_off + str_len <= type_off),
            "invalid bounded BTF data")
    return {"vermagic": vermagic[0], "versioned_import_count": len(versions),
            "strong_import_count": len(required_imports), "weak_import_count": len(weak_imports),
            "imported_symbol_crcs_match": True, "btf": identity(btf), "debug_info_stripped": True}


def verify(modules, release, symvers_path, expected_paths):
    require(modules.is_dir() and not modules.is_symlink(), "ordinary module root required")
    before = {}
    raw, before[symvers_path] = read(symvers_path, 16 * 1024**2)
    exported = symvers(raw)
    paths = sorted(modules.rglob("*.ko"))
    observed = [str(p.relative_to(modules)) for p in paths]
    require(observed == sorted(expected_paths), "module relative path set differs from R6")
    require(len(observed) == 84, "expected exactly 84 rebuilt modules")
    result = {"schema_version": 1, "passed": False,
              "scope": "offline module ABI, retained BTF and bounded BTF header/section checks",
              "btf_semantic_type_validation": False,
              "kernel_release": release, "module_symvers": identity(raw), "modules": [],
              "runtime_module_loading_verified": False, "runtime_signature_enforcement_verified": False}
    for path in paths:
        raw, before[path] = read(path)
        row = {"path": str(path.relative_to(modules)), **identity(raw), **module_abi(raw, release, exported)}
        result["modules"].append(row)
    require(all(snapshot(path) == snap for path, snap in before.items()), "ABI input changed during verification")
    require(sorted(modules.rglob("*.ko")) == paths, "module inventory changed during verification")
    result.update(passed=True, module_count=len(paths), input_snapshot_stable=True)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--modules", type=Path, required=True)
    p.add_argument("--release", required=True)
    p.add_argument("--symvers", type=Path, required=True)
    p.add_argument("--expected-paths", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = verify(args.modules, args.release, args.symvers, json.loads(args.expected_paths.read_text()))
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
