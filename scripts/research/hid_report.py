#!/usr/bin/env python3
"""Summarize a saved HID report descriptor without opening an input device.

This is an offline descriptor parser, not an event recorder. It prints no raw
descriptor bytes, strings, serial numbers, Bluetooth addresses or file paths.
String/designator items and opaque long-item payloads are deliberately omitted.
The JSON describes advertised reports, not proven device behavior.
"""

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path


MAX_DESCRIPTOR_BYTES = 65536
MAX_REPORT_BITS = 1048576
PAGE_NAMES = {
    0x01: "Generic Desktop", 0x07: "Keyboard/Keypad", 0x08: "LEDs",
    0x09: "Button", 0x0C: "Consumer", 0x0D: "Digitizers",
}
USAGE_NAMES = {
    (0x01, 0x01): "Pointer", (0x01, 0x02): "Mouse",
    (0x01, 0x06): "Keyboard", (0x01, 0x30): "X", (0x01, 0x31): "Y",
    (0x01, 0x38): "Wheel", (0x0C, 0x01): "Consumer Control",
    (0x0D, 0x01): "Digitizer", (0x0D, 0x02): "Pen",
    (0x0D, 0x04): "Touch Screen", (0x0D, 0x05): "Touch Pad",
    (0x0D, 0x20): "Stylus", (0x0D, 0x22): "Finger",
    (0x0D, 0x30): "Tip Pressure", (0x0D, 0x32): "In Range",
    (0x0D, 0x3D): "X Tilt", (0x0D, 0x3E): "Y Tilt",
    (0x0D, 0x42): "Tip Switch", (0x0D, 0x44): "Barrel Switch",
    (0x0D, 0x47): "Confidence", (0x0D, 0x51): "Contact Identifier",
    (0x0D, 0x54): "Contact Count", (0x0D, 0x55): "Contact Count Maximum",
    (0x0D, 0x56): "Scan Time",
}


class DescriptorError(ValueError):
    """Malformed or unsupported-size descriptor."""


def describe_usage(usage):
    page, code = usage >> 16, usage & 0xFFFF
    result = {"page": f"0x{page:04x}", "usage": f"0x{code:04x}"}
    if page in PAGE_NAMES:
        result["page_name"] = PAGE_NAMES[page]
    if (page, code) in USAGE_NAMES:
        result["name"] = USAGE_NAMES[(page, code)]
    return result


def parse_descriptor(data):
    if not data or len(data) > MAX_DESCRIPTOR_BYTES:
        raise DescriptorError("descriptor must contain 1..65536 bytes")
    state = dict(usage_page=0, logical_min=0, logical_max=0, physical_min=0,
                 physical_max=0, unit=0, unit_exponent=0, report_size=0,
                 report_count=0, report_id=0)
    stack, collections, applications, fields, warnings = [], [], [], [], []
    offsets = {}
    local = {}
    index = 0
    while index < len(data):
        start = index
        prefix = data[index]
        index += 1
        if prefix == 0xFE:
            if index + 2 > len(data):
                raise DescriptorError(f"truncated long item at byte {start}")
            length = data[index]
            index += 2
            if index + length > len(data):
                raise DescriptorError(f"truncated long payload at byte {start}")
            index += length
            warnings.append(f"opaque long item omitted at byte {start}")
            continue
        length = (0, 1, 2, 4)[prefix & 3]
        item_type, tag = (prefix >> 2) & 3, prefix >> 4
        if index + length > len(data):
            raise DescriptorError(f"truncated short item at byte {start}")
        raw = data[index:index + length]
        index += length
        unsigned = int.from_bytes(raw, "little")
        signed = int.from_bytes(raw, "little", signed=True)
        if item_type == 1:  # Global items survive each Main item.
            if tag == 0:
                state["usage_page"] = unsigned
            elif tag == 1:
                state["logical_min"] = signed
            elif tag == 2:
                state["logical_max"] = signed if state["logical_min"] < 0 else unsigned
            elif tag == 3:
                state["physical_min"] = signed
            elif tag == 4:
                state["physical_max"] = signed if state["physical_min"] < 0 else unsigned
            elif tag == 5:
                nibble = unsigned & 15
                state["unit_exponent"] = nibble - 16 if nibble & 8 else nibble
            elif tag == 6:
                state["unit"] = unsigned
            elif tag == 7:
                state["report_size"] = unsigned
            elif tag == 8:
                if not 1 <= unsigned <= 255:
                    raise DescriptorError(f"invalid report ID at byte {start}")
                state["report_id"] = unsigned
            elif tag == 9:
                state["report_count"] = unsigned
            elif tag == 10:
                stack.append(state.copy())
            elif tag == 11:
                if not stack:
                    raise DescriptorError(f"global stack underflow at byte {start}")
                state = stack.pop()
            continue
        if item_type == 2:  # Local usage metadata; no string/designator output.
            if tag in (0, 1, 2):
                usage = unsigned if length == 4 else (state["usage_page"] << 16) | unsigned
                if tag == 0:
                    local.setdefault("usages", []).append(usage)
                else:
                    local["usage_min" if tag == 1 else "usage_max"] = usage
            elif tag == 10:
                warnings.append(f"usage delimiter not expanded at byte {start}")
            continue
        if item_type != 0:
            warnings.append(f"reserved item omitted at byte {start}")
            continue
        if tag == 10:  # Collection
            usage = (local.get("usages") or [local.get("usage_min", 0)])[0]
            collection = {"type": unsigned, "usage": describe_usage(usage)}
            collections.append(collection)
            if unsigned == 1:
                applications.append(collection["usage"])
        elif tag == 12:  # End Collection
            if not collections:
                raise DescriptorError(f"collection stack underflow at byte {start}")
            collections.pop()
        elif tag in (8, 9, 11):
            kind = {8: "input", 9: "output", 11: "feature"}[tag]
            key = kind, state["report_id"]
            size, count = state["report_size"], state["report_count"]
            bits = size * count
            offset = offsets.get(key, 0)
            if size > MAX_REPORT_BITS or count > MAX_REPORT_BITS or offset + bits > MAX_REPORT_BITS:
                raise DescriptorError(f"report exceeds size limit at byte {start}")
            field = {
                "kind": kind, "report_id": key[1], "offset_bits_payload": offset,
                "size_bits": size, "count": count, "constant": bool(unsigned & 1),
                "variable": bool(unsigned & 2), "relative": bool(unsigned & 4),
                "flags": f"0x{unsigned:x}",
                "logical_range": [state["logical_min"], state["logical_max"]],
                "physical_range": [state["physical_min"], state["physical_max"]],
                "unit": f"0x{state['unit']:x}", "unit_exponent": state["unit_exponent"],
                "collections": list(collections),
                "usages": [describe_usage(u) for u in local.get("usages", [])],
            }
            for name in ("usage_min", "usage_max"):
                if name in local:
                    field[name] = describe_usage(local[name])
            fields.append(field)
            offsets[key] = offset + bits
        else:
            warnings.append(f"unknown Main item omitted at byte {start}")
        local = {}  # All Main items consume the Local state.
    if stack:
        warnings.append("unclosed global Push state")
    if collections:
        warnings.append("unclosed Collection")
    if any(report_id == 0 for _, report_id in offsets) and any(report_id != 0 for _, report_id in offsets):
        warnings.append("descriptor mixes unnumbered and numbered reports")
    reports = [
        {"kind": kind, "report_id": report_id, "payload_bits": bits,
         "report_bytes_with_id": (bits + 7) // 8 + bool(report_id)}
        for (kind, report_id), bits in sorted(offsets.items())
    ]
    return {
        "schema": "tb371fc-hid-report-descriptor-v1",
        "descriptor_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        "interpretation": "Advertised descriptor capabilities only; no events or runtime validation.",
        "privacy": "No raw bytes, string values, device paths, serial numbers or network addresses are emitted.",
        "applications": applications, "reports": reports, "fields": fields,
        "warnings": warnings,
    }


def read_descriptor(path, encoding):
    # Bound the encoded file before decoding; never auto-detect arbitrary input.
    with path.open("rb") as stream:
        raw = stream.read(MAX_DESCRIPTOR_BYTES * 6 + 1)
    if len(raw) > MAX_DESCRIPTOR_BYTES * 6:
        raise DescriptorError("encoded input exceeds size limit")
    if encoding == "binary":
        return raw
    try:
        text = raw.decode("ascii")
        if encoding == "hex":
            if not re.fullmatch(r"[0-9a-fA-F\s]*", text):
                raise DescriptorError("hex input must contain only hex digits and whitespace")
            return bytes.fromhex(text)
        return base64.b64decode("".join(text.split()), validate=True)
    except (UnicodeDecodeError, ValueError) as exc:
        raise DescriptorError("invalid encoded descriptor") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("descriptor", type=Path, help="saved descriptor file (never /dev/input)")
    parser.add_argument("--format", choices=("binary", "hex", "base64"), default="binary")
    parser.add_argument("--expect-sha256", help="optional checksum of decoded descriptor bytes")
    args = parser.parse_args()
    try:
        if not args.descriptor.is_file():
            raise DescriptorError("input must be a regular saved file")
        data = read_descriptor(args.descriptor, args.format)
        if args.expect_sha256 and hashlib.sha256(data).hexdigest() != args.expect_sha256.lower():
            raise DescriptorError("descriptor checksum mismatch")
        result = parse_descriptor(data)
    except OSError:
        print("error: cannot read saved descriptor", file=sys.stderr)
        return 2
    except DescriptorError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
