#!/usr/bin/env python3
"""Decode captured display bytes offline; no device commands or file writes.

Commands are Qualcomm DT command records with a seven-byte header:
type, last, virtual-channel, message-flags, wait-ms, payload-length (big endian).
The Android reference parser ORs byte 3 into msg.flags; it is retained whole:
https://github.com/smith-dog/kernel-tb371fc/blob/c3df39c507c11eebb124224bd34e3ab701b6d1f3/techpack/display/msm/dsi/dsi_panel.c
PPS offsets follow Linux v6.12 include/drm/display/drm_dsc.h:
https://github.com/torvalds/linux/blob/v6.12/include/drm/display/drm_dsc.h

Examples:
  display_decode.py commands --file qcom,mdss-dsi-on-command
  display_decode.py commands --hex '05 01 00 00 78 00 01 11'
  display_decode.py pps --file android-pps.bin --compare-file linux-pps.bin

The decoder does not infer command-page semantics, infer the active mode,
validate panel safety, generate a new PPS, or claim a hardware test passed.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys


def commands(data: bytes) -> dict:
    records = []
    offset = 0
    while offset < len(data):
        if len(data) - offset < 7:
            raise ValueError(f"truncated command header at byte {offset}")
        dtype, last, vc, flags, wait_ms = data[offset : offset + 5]
        payload_length = int.from_bytes(data[offset + 5 : offset + 7], "big")
        end = offset + 7 + payload_length
        if end > len(data):
            raise ValueError(
                f"command at byte {offset} declares {payload_length} payload "
                f"bytes, only {len(data) - offset - 7} remain"
            )
        records.append(
            {
                "offset": offset,
                "packet_type": f"0x{dtype:02x}",
                "last_command_raw": last,
                "virtual_channel": vc,
                "message_flags_raw": flags,
                "wait_ms": wait_ms,
                "payload_length": payload_length,
                "payload_hex": data[offset + 7 : end].hex(),
            }
        )
        offset = end
    return {"command_count": len(records), "commands": records}


def pps(data: bytes) -> dict:
    if len(data) != 128:
        raise ValueError(f"DSC PPS must contain exactly 128 bytes, got {len(data)}")

    def u16(offset: int) -> int:
        return int.from_bytes(data[offset : offset + 2], "big")

    ranges = []
    for index in range(15):
        word = u16(58 + index * 2)
        offset = word & 0x3F
        ranges.append(
            {
                "min_qp": word >> 11,
                "max_qp": (word >> 6) & 0x1F,
                "bpg_offset": offset - 64 if offset & 0x20 else offset,
            }
        )

    bpp_u6_4 = ((data[4] & 3) << 8) | data[5]
    return {
        "dsc_version_major": data[0] >> 4,
        "dsc_version_minor": data[0] & 0x0F,
        "pps_identifier": data[1],
        "bits_per_component_encoded": data[3] >> 4,
        "line_buf_depth_encoded": data[3] & 0x0F,
        "block_prediction": bool(data[4] & 0x20),
        "convert_rgb": bool(data[4] & 0x10),
        "simple_422": bool(data[4] & 0x08),
        "vbr_enable": bool(data[4] & 0x04),
        "bits_per_pixel_u6_4": bpp_u6_4,
        "bits_per_pixel": bpp_u6_4 / 16,
        "pic_height": u16(6),
        "pic_width": u16(8),
        "slice_height": u16(10),
        "slice_width": u16(12),
        "chunk_size": u16(14),
        "initial_xmit_delay": ((data[16] & 3) << 8) | data[17],
        "initial_dec_delay": u16(18),
        "initial_scale_value": data[21] & 0x3F,
        "scale_increment_interval": u16(22),
        "scale_decrement_interval": ((data[24] & 0x0F) << 8) | data[25],
        "first_line_bpg_offset": data[27] & 0x1F,
        "nfl_bpg_offset": u16(28),
        "slice_bpg_offset": u16(30),
        "initial_offset": u16(32),
        "final_offset": u16(34),
        "flatness_min_qp": data[36] & 0x1F,
        "flatness_max_qp": data[37] & 0x1F,
        "rc_model_size": u16(38),
        "rc_edge_factor": data[40] & 0x0F,
        "rc_quant_incr_limit0": data[41] & 0x1F,
        "rc_quant_incr_limit1": data[42] & 0x1F,
        "rc_tgt_offset_high": data[43] >> 4,
        "rc_tgt_offset_low": data[43] & 0x0F,
        "rc_buf_thresholds_encoded": list(data[44:58]),
        "rc_range_parameters": ranges,
        "native_422": bool(data[88] & 1),
        "native_420": bool(data[88] & 2),
        "second_line_bpg_offset": data[89] & 0x1F,
        "nsl_bpg_offset": u16(90),
        "second_line_offset_adj": u16(92),
        "raw_hex": data.hex(),
    }


def read_input(path: Path, encoding: str) -> bytes:
    if encoding == "hex":
        return bytes.fromhex(path.read_text(encoding="ascii"))
    return path.read_bytes()


def read_capture(path: Path, node: str, prop: str) -> bytes:
    capture = json.loads(path.read_text(encoding="utf-8"))
    value = capture["device_tree"]["nodes"][node][prop]
    data = base64.b64decode(value["base64"], validate=True)
    if len(data) != value["size"]:
        raise ValueError("captured property length does not match its metadata")
    if hashlib.sha256(data).hexdigest() != value["sha256"]:
        raise ValueError("captured property SHA-256 does not match its metadata")
    return data


def byte_comparison(left: bytes, right: bytes) -> dict:
    mismatches = []
    for offset in range(max(len(left), len(right))):
        a = left[offset] if offset < len(left) else None
        b = right[offset] if offset < len(right) else None
        if a != b:
            mismatches.append({"offset": offset, "left": a, "right": b})
    return {"byte_identical": left == right, "mismatches": mismatches}


def compare_tianma_init(records: list[dict], path: Path) -> dict:
    """Compare the known TB371FC source layout; this is not a general C parser."""
    if (len(records) < 2 or
            records[-2]["packet_type"] != "0x05" or
            records[-2]["payload_hex"] not in ("11", "1100") or
            records[-1]["packet_type"] != "0x05" or
            records[-1]["payload_hex"] not in ("29", "2900")):
        raise ValueError("expected the Tianma ON table's sleep-out/display-on tail")
    source = path.read_text(encoding="utf-8")
    start = source.index("static int tb371fc_nt36532_init_sequence")
    end = source.index("static int tb371fc_boe_init_sequence", start)
    body = source[start:end]
    marker = "if (boe) {"
    if body.count(marker) != 1:
        raise ValueError("expected exactly one BOE-only block in panel source")
    branch = body.index(marker)
    cursor = body.index("{", branch) + 1
    depth = 1
    while depth:
        if cursor >= len(body):
            raise ValueError("unterminated BOE-only source block")
        depth += (body[cursor] == "{") - (body[cursor] == "}")
        cursor += 1
    body = body[:branch] + body[cursor:]
    values = re.findall(
        r"tb371fc_dsi_dual_dcs_long_write_seq_multi"
        r"\(&dsi_ctx, dsi0, dsi1, ([^;]+)\);", body)
    if not values:
        raise ValueError("no expected Tianma vendor-write calls in panel source")
    payloads = [bytes(int(v.strip(), 16) for v in value.split(",")).hex()
                for value in values]
    # Preserve order and count. Extra, missing or changed vendor writes are
    # reported; they are never silently discarded to obtain a match.
    actual = records[:-2]
    mismatches = []
    for index in range(max(len(payloads), len(actual))):
        expected = payloads[index] if index < len(payloads) else None
        observed = actual[index]["payload_hex"] if index < len(actual) else None
        if expected != observed:
            mismatches.append({"index": index, "source_payload": expected,
                               "captured_payload": observed})
    return {
        "source_path": str(path),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "scope": "ordered vendor payload comparison; not runtime/on-wire proof",
        "source_vendor_count": len(payloads),
        "captured_vendor_count": len(actual),
        "vendor_payloads_match": not mismatches,
        "payload_mismatches": mismatches,
        "captured_vendor_header_variants": [list(row) for row in sorted({
            (r["packet_type"], r["last_command_raw"], r["virtual_channel"],
             r["message_flags_raw"], r["wait_ms"]) for r in actual})],
        "captured_final_two_records": records[-2:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("commands", "pps"))
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--file", type=Path, help="captured file, opened read-only")
    inputs.add_argument("--hex", help="space-separated hex bytes, not a log dump")
    inputs.add_argument("--capture", type=Path,
                        help="JSON from collect_android_hardware.py")
    parser.add_argument("--node", help="exact DT path in --capture")
    parser.add_argument("--property", help="exact property in --capture")
    parser.add_argument("--encoding", choices=("raw", "hex"), default="raw")
    parser.add_argument("--compare-file", type=Path,
                        help="second capture; uses the same --encoding")
    parser.add_argument("--tianma-init-source", type=Path,
                        help="compare ON vendor payloads with the known TB371FC C source")
    args = parser.parse_args()
    if args.capture is not None and (not args.node or not args.property):
        parser.error("--capture requires both --node and --property")
    if args.capture is None and (args.node or args.property):
        parser.error("--node/--property require --capture")
    if args.tianma_init_source is not None and args.kind != "commands":
        parser.error("--tianma-init-source requires kind=commands and an ON table")
    try:
        if args.capture is not None:
            data = read_capture(args.capture, args.node, args.property)
        elif args.hex is not None:
            data = bytes.fromhex(args.hex)
        else:
            data = read_input(args.file, args.encoding)
        decoder = commands if args.kind == "commands" else pps
        result = {
            "kind": args.kind,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "decoded": decoder(data),
        }
        if args.tianma_init_source is not None:
            result["tianma_init_comparison"] = compare_tianma_init(
                result["decoded"]["commands"], args.tianma_init_source)
        if args.compare_file is not None:
            other = read_input(args.compare_file, args.encoding)
            comparison = byte_comparison(data, other)
            comparison.update({
                "other_size_bytes": len(other),
                "other_sha256": hashlib.sha256(other).hexdigest(),
                "other_decoded": decoder(other),
            })
            result["comparison"] = comparison
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as error:
        print(f"display_decode: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
