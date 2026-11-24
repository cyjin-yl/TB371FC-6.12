#!/usr/bin/env python3
"""Compare complete fixed-libsepol CIL exports of the old and rebuilt policies.

Run with the fixed Fedora ARM Python and libsepol. Everything stays in ordinary
files and private process memory. This does not load or query kernel policy.
"""
import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import struct
import sys


OLD = (3835432, "928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430")
LIBRARY = (802880, "46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b")


def identity(data):
    return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def read_fixed(path, size, sha):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != size or size > 32 * 1024**2:
        raise ValueError("unexpected ordinary input file: " + str(path))
    data = path.read_bytes()
    after = path.lstat()
    fields = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_size, x.st_mtime_ns, x.st_ctime_ns)
    if fields(before) != fields(after) or hashlib.sha256(data).hexdigest() != sha:
        raise ValueError("input changed or hash differs: " + str(path))
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original", type=Path, required=True)
    ap.add_argument("--candidate", type=Path, required=True)
    ap.add_argument("--candidate-size", type=int, required=True)
    ap.add_argument("--candidate-sha256", required=True)
    ap.add_argument("--library", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    if platform.machine() != "aarch64" or c.sizeof(c.c_void_p) != 8:
        ap.error("fixed ARM64 userspace ABI required")
    if not re.fullmatch("[0-9a-f]{64}", args.candidate_sha256):
        ap.error("candidate SHA256 is required")
    if args.output.exists() or not str(args.output).startswith("/work/selinux-reload-map-20261123/"):
        ap.error("require a fresh output directory in the isolated experiment")
    data = {"original": read_fixed(args.original, *OLD),
            "candidate": read_fixed(args.candidate, args.candidate_size, args.candidate_sha256)}
    library = read_fixed(args.library, *LIBRARY)
    args.output.mkdir(mode=0o700)
    report = {"schema": 1, "scope": "complete offline binary-to-CIL comparison",
              "library": identity(library), "kernel_policy_loaded_or_queried": False,
              "physical_hardware_tested": False, "runtime_relabel_proven": False,
              "input_policy": {key: identity(value) for key, value in data.items()},
              "exports": {}, "conversions": {}, "completed": False,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    lib = c.CDLL(str(args.library))
    libc = c.CDLL("libc.so.6", use_errno=True)
    signatures = {
        "sepol_policydb_create": ([c.POINTER(c.c_void_p)], c.c_int),
        "sepol_policydb_free": ([c.c_void_p], None),
        "sepol_policydb_from_image": ([c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p], c.c_int),
        # Fixed 3.11 policydb.h defines struct sepol_policydb { struct policydb p; }.
        # Its first member has the same address; no private fields are read here.
        "sepol_kernel_policydb_to_cil": ([c.c_void_p, c.c_void_p], c.c_int),
        "sepol_policydb_set_vers": ([c.c_void_p, c.c_uint], c.c_int),
        "sepol_policydb_to_image": ([c.c_void_p, c.c_void_p, c.POINTER(c.c_void_p),
                                    c.POINTER(c.c_size_t)], c.c_int),
    }
    for name, (argv, result) in signatures.items():
        getattr(lib, name).argtypes = argv
        getattr(lib, name).restype = result
    libc.fopen.argtypes, libc.fopen.restype = [c.c_char_p, c.c_char_p], c.c_void_p
    libc.fclose.argtypes, libc.fclose.restype = [c.c_void_p], c.c_int
    libc.free.argtypes, libc.free.restype = [c.c_void_p], None

    def zero(value, label):
        if value != 0:
            raise RuntimeError(f"{label} returned {value}")

    def export(name, blob, version):
        if (struct.unpack_from("<II", blob) != (0xf97cff8c, 8) or
                blob[8:16] != b"SE Linux" or struct.unpack_from("<I", blob, 16)[0] != version):
            raise ValueError("unexpected policy image header")
        db, convert_db, serialized, stream = c.c_void_p(), c.c_void_p(), c.c_void_p(), None
        try:
            zero(lib.sepol_policydb_create(c.byref(db)), "create")
            buffer = c.create_string_buffer(blob, len(blob))
            zero(lib.sepol_policydb_from_image(None, buffer, len(blob), db), "from_image")
            path = args.output / f"{name}-v{version}.cil"
            stream = libc.fopen(str(path).encode(), b"wx")
            if not stream:
                raise OSError(c.get_errno(), "fopen export failed")
            zero(lib.sepol_kernel_policydb_to_cil(stream, db), "kernel_policydb_to_cil")
            ret = libc.fclose(stream)
            stream = None
            zero(ret, "fclose export")
            result = path.read_bytes()
            report["exports"][f"{name}-v{version}"] = {
                "path": str(path), **identity(result), "line_count": result.count(b"\n")}
            converted = None
            if version == 35:
                # The exporter may reorder internal tables. Convert a fresh
                # parse, matching the libselinux path without a prior export.
                zero(lib.sepol_policydb_create(c.byref(convert_db)), "create_conversion")
                zero(lib.sepol_policydb_from_image(None, buffer, len(blob), convert_db), "from_image_conversion")
                zero(lib.sepol_policydb_set_vers(convert_db, 33), "set_vers33")
                size = c.c_size_t()
                zero(lib.sepol_policydb_to_image(None, convert_db, c.byref(serialized), c.byref(size)), "to_image33")
                if not serialized or not 0 < size.value < 32 * 1024**2:
                    raise ValueError("invalid converted allocation")
                converted = c.string_at(serialized, size.value)
                target = args.output / f"{name}-converted-v33.policy"
                with target.open("xb") as f:
                    f.write(converted)
                report["conversions"][name] = {
                    "path": str(target), **identity(converted), "version": 33,
                    "fresh_parse_without_prior_cil_export": True,
                    "kernel_export_identity_asserted": False}
            return result, converted
        finally:
            if stream:
                libc.fclose(stream)
            if serialized:
                libc.free(serialized)
            if db:
                lib.sepol_policydb_free(db)
            if convert_db:
                lib.sepol_policydb_free(convert_db)

    try:
        exports = {}
        for name, blob in data.items():
            text35, converted = export(name, blob, 35)
            text33, _ = export(name, converted, 33)
            exports[name] = {35: text35, 33: text33}
        comparisons = {}
        pattern = re.compile(rb"^\(allow init_t semanage_store_t \(file \(([^\n()]*)\)\)\)$", re.M)
        for version in (35, 33):
            before, after = exports["original"][version], exports["candidate"][version]
            a, b = list(pattern.finditer(before)), list(pattern.finditer(after))
            if len(a) != 1 or len(b) != 1:
                raise ValueError("expected one merged init_t/semanage_store_t/file rule in each complete export")
            old_perms, new_perms = a[0].group(1).split(), b[0].group(1).split()
            only_map = (len(set(old_perms)) == len(old_perms) and len(set(new_perms)) == len(new_perms)
                        and b"map" not in old_perms and set(new_perms) == set(old_perms) | {b"map"})
            replaced = before[:a[0].start()] + b[0].group(0) + before[a[0].end():]
            same_everything_else = replaced == after
            comparisons[str(version)] = {
                "before_rule": a[0].group(0).decode(), "after_rule": b[0].group(0).decode(),
                "added_permissions": sorted(x.decode() for x in set(new_perms) - set(old_perms)),
                "removed_permissions": sorted(x.decode() for x in set(old_perms) - set(new_perms)),
                "only_map_added_in_rule": only_map,
                "complete_cil_identical_after_exact_rule_substitution": same_everything_else,
                "includes_other_av_booleans_types_permissive_mls_and_policycaps": True,
            }
        report["comparisons"] = comparisons
        old_blob, new_blob = data["original"], data["candidate"]
        changed = [i for i in range(min(len(old_blob), len(new_blob))) if old_blob[i] != new_blob[i]]
        report["binary_difference"] = {
            "same_length": len(old_blob) == len(new_blob), "changed_byte_count_in_overlap": len(changed),
            "first_changed_offsets": changed[:64], "trailing_length_delta": len(new_blob) - len(old_blob)}
        report["completed"] = all(x["only_map_added_in_rule"] and
                                  x["complete_cil_identical_after_exact_rule_substitution"]
                                  for x in comparisons.values())
        if read_fixed(args.library, *LIBRARY) != library:
            raise ValueError("library changed")
        if not report["completed"]:
            raise ValueError("policy change is broader than the intended map rule")
    except Exception as exc:
        report["completed"] = False
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    with (args.output / "result.json").open("x") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    sys.exit(main())
