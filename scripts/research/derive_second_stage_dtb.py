#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive an offline R5 second-stage RAM declaration, not a boot-ready DTB."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from boot_formats import parse_fdt, _ranges as checked_ranges
from native_dt import inspect_fdt, _parse_tree

R5_SHA = "af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730"
OBS_SHA = "e071f91b43a063ff6f96cb401269469e20703ab695e64dd37a1d5b86113ba745"
LIVE_SHA = "5114262a0dea5ef82b53db69b3d489ddbe57040e1a50b57365e87a28d2946207"
BOARD = ["lenovo,tb371fc", "qcom,sm8250"]
MEMORY = "/memory@80000000"
RAM = [{"start": 0x80000000, "size": 0x3bb00000},
       {"start": 0xc0000000, "size": 0x1c0000000}]
RAM_BYTES = b"".join(struct.pack(">QQ", r["start"], r["size"]) for r in RAM)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_fixed(path, expected):
    require(path.is_file() and not path.is_symlink(), "expected regular input file")
    with path.open("rb") as stream:
        data = stream.read(2 * 1024 * 1024 + 1)
    require(len(data) <= 2 * 1024 * 1024 and sha(data) == expected,
            "frozen input identity mismatch")
    return data


def observation(raw):
    require(sha(raw) == OBS_SHA, "wrong owner observation identity")
    live = json.loads(raw)["running_fdt"]
    tree = live["inspection"]
    require(live["stable_across_two_reads"] is True and live["sha256"] == LIVE_SHA
            and tree["sha256"] == LIVE_SHA and tree["format_compliant"] is False,
            "wrong live FDT identity or forensic scope")
    require(len(tree["memory"]) == 1, "ambiguous owner RAM declaration")
    mem = tree["memory"][0]
    require(mem["enabled"] is True and mem["device_type_is_memory"] is True
            and mem["reg"] == RAM, "unexpected owner RAM declaration")
    checked_ranges(mem["reg"], "observed RAM", nonempty=True)
    nodes = tree["reserved_memory"]["nodes"]
    require(len(nodes) == 35 and sum(n["allocation"] == "dynamic" for n in nodes) == 12,
            "wrong reserve inventory")
    return tree


def reserve_comparison(main, owner):
    # Path and geometry matches do not establish semantic equivalence.
    left = main["reserved_memory"]["nodes"]
    right = owner["reserved_memory"]["nodes"]
    def rows(source, other):
        return [{"declaration": node,
                 "same_path": [n["path"] for n in other if n["path"] == node["path"]],
                 "identical_nonempty_reg": [n["path"] for n in other
                     if node["reg"] and all(r["size"] > 0 for r in node["reg"])
                     and n["reg"] == node["reg"]],
                 "intersecting_reg": [n["path"] for n in other if any(
                     a["size"] > 0 and b["size"] > 0
                     and max(a["start"], b["start"]) <
                     min(a["start"] + a["size"], b["start"] + b["size"])
                     for a in node["reg"] for b in n["reg"])]}
                for node in source]
    return {"mainline": rows(left, right), "android": rows(right, left),
            "semantic_equivalence_verified": False}


def check_delta(before, after):
    a, ah = _parse_tree(before)
    b, bh = _parse_tree(after)
    require(a.keys() == b.keys(), "node inventory changed")
    changes = []
    for path in a:
        require(a[path].keys() == b[path].keys(), "property inventory changed")
        for prop in a[path]:
            if a[path][prop] != b[path][prop]:
                changes.append((path, prop))
    require(changes == [(MEMORY, "reg")], "unexpected semantic changes")
    for field in ("version", "last_compatible_version", "boot_cpuid_phys", "memreserve"):
        require(ah[field] == bh[field], "FDT header or reservation changes")
    require(a[MEMORY]["reg"] == struct.pack(">4I", 0, 0x80000000, 0, 0),
            "unexpected source placeholder")
    require(b[MEMORY]["reg"] == RAM_BYTES, "incorrect final RAM cells")
    return [{"path": MEMORY, "property": "reg", "before_hex": a[MEMORY]["reg"].hex(),
             "after_hex": b[MEMORY]["reg"].hex()}]


def derive(board, raw_obs, output_dir):
    require(sha(board) == R5_SHA, "wrong frozen R5 DTB identity")
    owner = observation(raw_obs)
    original = inspect_fdt(board)
    require(parse_fdt(board)["compatible"] == BOARD, "wrong second-stage board")
    require(original["root_cells"] == {"address": 2, "size": 2,
            "address_explicit": True, "size_explicit": True}, "unexpected root cells")
    require(len(original["memory"]) == 1 and original["memory"][0]["path"] == MEMORY
            and original["memory"][0]["enabled"] is True
            and original["memory"][0]["device_type_is_memory"] is True,
            "unexpected memory node")
    tool = shutil.which("fdtput")
    require(tool is not None, "fdtput (libfdt) is required")
    with tempfile.TemporaryDirectory() as tmp:
        candidate = Path(tmp) / "board.dtb"
        candidate.write_bytes(board)
        cells = [f"{cell:x}" for cell in struct.unpack(">8I", RAM_BYTES)]
        subprocess.run([tool, "-t", "x", str(candidate), MEMORY, "reg", *cells],
                       check=True, timeout=30, capture_output=True)
        after = candidate.read_bytes()
    final = inspect_fdt(after)
    require(parse_fdt(after)["compatible"] == BOARD, "wrong final identity")
    delta = check_delta(board, after)
    require(final["memory"][0]["reg"] == RAM, "RAM readback mismatch")
    require(final["reserved_memory"] == original["reserved_memory"],
            "reserved-memory declarations changed")
    report = {
        "schema": "tb371fc-r5-second-stage-dtb-offline-candidate-v1",
        "status": "offline_candidate_only",
        "source": {"sha256": sha(board), "bytes": len(board)},
        "candidate": {"sha256": sha(after), "bytes": len(after), "compatible": BOARD},
        "owner_observation": {"sha256": sha(raw_obs), "live_fdt_sha256": LIVE_SHA,
                              "format_compliant": False, "ram": RAM},
        "fdtput": {"version": subprocess.check_output([tool, "--version"], timeout=10,
                     text=True).strip(), "sha256": sha(Path(tool).read_bytes())},
        "semantic_property_changes": delta,
        "mainline_memory_before": original["memory"],
        "mainline_memory_after": final["memory"],
        "reserved_memory_comparison": reserve_comparison(final, owner),
        "mainline_memreserve": final["memreserve"], "android_memreserve": owner["memreserve"],
        "mainline_memory_map_issues": final["memory_map_issues"],
        "android_memory_map_issues": owner["memory_map_issues"],
        "android_unresolved_dynamic": [n for n in owner["reserved_memory"]["nodes"]
                                        if n["allocation"] == "dynamic"],
        "blocking": ["owner_dynamic_reservations_unresolved",
                     "mainline_owner_reservation_differences_unresolved",
                     "firmware_and_loader_exclusions_unverified",
                     "physical_load_layout_unselected", "dma_quiescence_unverified",
                     "entry_and_recovery_unverified"],
        "runtime_memory_map_verified": False, "physical_boot_verified": False,
        "owner_native_linux_passes_added": 0,
    }
    # Refuse existing output directories, including symlinks. No input rewrite.
    output_dir.mkdir(mode=0o700)
    (output_dir / "board.dtb").write_bytes(after)
    (output_dir / "receipt.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r5-dtb", type=Path, required=True)
    parser.add_argument("--owner-observation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error("output directory must not exist")
    try:
        result = derive(read_fixed(args.r5_dtb, R5_SHA),
                        read_fixed(args.owner_observation, OBS_SHA), args.output_dir)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"offline candidate rejected: {error}\n")
    print(json.dumps({"status": result["status"], "candidate": result["candidate"]}))


if __name__ == "__main__":
    main()
