#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect one SHA-pinned owner Image as an ordinary offline file.

This is a version-specific evidence extractor, not a BPF program, a live
memory reader or a general disassembler. It decodes compressed symbol names,
selected static RELATIVE relocations and a few reviewed AArch64 instructions.
The interpretation applies only to the complete input hash below. No live
address, relocation base, raw Image, complete symbol map or network identifier
is emitted. The manual control-flow review is identified separately.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

IMAGE_SHA = "ef9e7b5cdb9ef3c66977a04d6b6e21cf83e83f2f45476390c861827d1bb1cf0f"
IMAGE_SIZE = 37445648
LAYOUT = {
    "offsets": 25312000, "relative_base_field": 25797888,
    "count": 25798144, "names": 25798400, "names_end": 27436274,
    "markers": 27436288, "token_table": 27440128, "token_index": 27441152,
}
FUNCTIONS = (
    "tp_prog_func_proto", "tracing_func_proto", "bpf_probe_read",
    "probe_kernel_read", "cnss_get_plat_priv", "cnss_bus_dev_to_plat_priv",
    "cnss_get_soc_info", "cnss_wlfw_tgt_cap_send_sync",
    "cnss_wlfw_bdf_dnld_send_sync", "cnss_bus_add_fw_prefix_name",
    "cnss_pci_add_fw_prefix_name", "cnss_probe", "cnss_remove",
    "cnss_driver_event_work", "cnss_wlfw_server_exit",
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fixed_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode), "ordinary offline file required")
        require(info.st_size == IMAGE_SIZE, "wrong owner Image size")
        data = stream.read(IMAGE_SIZE + 1)
    require(len(data) == IMAGE_SIZE and sha(data) == IMAGE_SHA,
            "complete owner Image identity mismatch")
    return data


def cstring(data, offset, limit=256):
    require(0 <= offset < len(data), "string outside offline Image")
    end = data.index(b"\0", offset, min(len(data), offset + limit))
    return data[offset:end].decode("ascii")


def symbols(data):
    require(data[56:60] == b"ARM\x64", "ARM64 Image header absent")
    count = struct.unpack_from("<Q", data, LAYOUT["count"])[0]
    require(count == 121415, "pinned kallsyms count changed")
    offsets = struct.unpack_from("<" + "I" * count, data, LAYOUT["offsets"])
    indexes = struct.unpack_from("<256H", data, LAYOUT["token_index"])
    tokens = [cstring(data, LAYOUT["token_table"] + i, 128) for i in indexes]
    require(all(tokens), "empty pinned kallsyms token")
    marker_count = (count + 255) // 256
    markers = struct.unpack_from("<" + "Q" * marker_count, data, LAYOUT["markers"])
    found = defaultdict(list)
    pos = LAYOUT["names"]
    for i in range(count):
        if i % 256 == 0:
            require(pos - LAYOUT["names"] == markers[i // 256],
                    "kallsyms block marker mismatch")
        size = data[pos]
        pos += 1
        require(size and pos + size <= LAYOUT["markers"], "bad compressed name")
        name = "".join(tokens[t] for t in data[pos:pos + size])
        pos += size
        require(len(name) > 1, "empty kallsyms name")
        found[name[1:]].append({"type": name[0], "offset": offsets[i]})
    require(pos == LAYOUT["names_end"] and not any(data[pos:LAYOUT["markers"]]),
            "kallsyms stream end mismatch")
    return found, sorted(set(offsets)), count, marker_count


def inspect(data):
    syms, boundaries, count, marker_count = symbols(data)

    def sym(name):
        require(len(syms[name]) == 1, "selected symbol missing or duplicated: " + name)
        return syms[name][0]["offset"]

    require(sym("_text") == 0, "text anchor mismatch")

    def word(offset):
        require(0 <= offset <= len(data) - 4 and offset % 4 == 0,
                "instruction outside pinned Image")
        return struct.unpack_from("<I", data, offset)[0]

    def signed(value, bits):
        return value - (1 << bits) if value & (1 << (bits - 1)) else value

    def call(offset, name):
        value = word(offset)
        require(value & 0xFC000000 == 0x94000000, "expected BL instruction")
        target = offset + (signed(value & 0x3FFFFFF, 26) << 2)
        require(target == sym(name), "reviewed direct call target changed")
        return {"instruction_relative_offset": offset, "target_symbol": name,
                "target_relative_offset": target}

    def page(offset, register):
        value = word(offset)
        require(value & 0x9F000000 == 0x90000000 and value & 31 == register,
                "expected ADRP instruction")
        immediate = ((value >> 5) & 0x7FFFF) * 4 + ((value >> 29) & 3)
        return (offset & ~4095) + (signed(immediate, 21) << 12)

    def addition(offset, destination, source):
        value = word(offset)
        require(value & 0xFF800000 == 0x91000000 and value & 31 == destination
                and (value >> 5) & 31 == source, "expected ADD immediate")
        return ((value >> 10) & 4095) << (12 if value & (1 << 22) else 0)

    def memory(offset, operation, width, base, register, displacement):
        encodings = {
            ("load", 1): 0x39400000, ("store", 1): 0x39000000,
            ("load", 4): 0xB9400000, ("store", 4): 0xB9000000,
            ("load", 8): 0xF9400000, ("store", 8): 0xF9000000,
        }
        value = word(offset)
        require(value & 0xFFC00000 == encodings[(operation, width)]
                and value & 31 == register and (value >> 5) & 31 == base
                and ((value >> 10) & 4095) * width == displacement,
                "reviewed load/store instruction changed")
        return {"instruction_relative_offset": offset, "operation": operation,
                "width_bytes": width, "base_register": base,
                "value_register": register, "structure_displacement": displacement}

    # The base below is only the static ELF relocation addend base. It is
    # neither a runtime address nor a source of a KASLR slide and is not emitted.
    target, info, addend = struct.unpack_from("<QQQ", data, 32173880)
    base = target - (sym("param_ops_charp") + 16)
    require(info == 1027 and addend - base == sym("param_get_charp"),
            "independent static relocation anchor mismatch")
    selected = {
        sym("bpf_verifier_ops") + 5 * 8: ("bpf_verifier_ops[5]", "tracepoint_verifier_ops"),
        sym("tracepoint_verifier_ops"): ("tracepoint_verifier_ops.get_func_proto", "tp_prog_func_proto"),
        sym("bpf_probe_read_proto"): ("bpf_probe_read_proto.func", "bpf_probe_read"),
    }
    links = {}
    pos = 0
    while True:
        pos = data.find(struct.pack("<Q", 1027), pos)
        if pos < 0:
            break
        if pos >= 8 and pos + 16 <= len(data):
            field = struct.unpack_from("<Q", data, pos - 8)[0] - base
            if field in selected:
                label, name = selected[field]
                destination = struct.unpack_from("<Q", data, pos + 8)[0] - base
                require(destination == sym(name) and field not in links,
                        "selected static relocation ambiguous or changed")
                links[field] = {
                    "field": label, "field_relative_offset": field,
                    "record_file_offset": pos - 8, "relocation_type": 1027,
                    "target_symbol": name, "target_relative_offset": destination,
                }
        pos += 8
    require(set(links) == set(selected), "selected relocation missing")

    # Helper 4 misses tp's 25/67/27 special cases and follows its default.
    calls = [call(0x16181C, "tracing_func_proto"),
             call(0x160B70, "probe_kernel_read"),
             call(0x160B9C, "memset")]
    table = page(0x162C7C, 9) + addition(0x162C84, 9, 9)
    require(table == 0x16DD2E8 and data[table + 4 - 1] == 16,
            "helper 4 switch table changed")
    branch = 0x162C9C + data[table + 3] * 4
    require(branch == 0x162CDC, "helper 4 switch destination changed")
    prototype = page(branch, 0) + addition(branch + 4, 0, 0)
    require(prototype == sym("bpf_probe_read_proto"), "helper 4 prototype changed")
    gpl, packet = struct.unpack_from("<BB", data, prototype + 8)
    types = struct.unpack_from("<6I", data, prototype + 12)
    require((gpl, packet, types) == (1, 0, (0, 6, 8, 10, 0, 0)),
            "pinned legacy helper prototype changed")

    global_pointer = page(0x925CD8, 8) + 0x4F8
    require(global_pointer == sym("plat_env"), "global CNSS cache pointer mismatch")
    global_load = memory(0x925CDC, "load", 8, 8, 0, 0x4F8)
    global_load["global_relative_text_offset"] = global_pointer
    require(page(0x9288B0, 23) + 0x4F8 == global_pointer
            and page(0x9293F8, 8) + 0x4F8 == global_pointer,
            "CNSS publication/removal global changed")
    publication = memory(0x928A1C, "store", 8, 23, 19, 0x4F8)
    removal = memory(0x929408, "store", 8, 8, 31, 0x4F8)
    device_chain = [memory(0x930D44, "load", 8, 0, 8, 0xB8),
                    memory(0x930D4C, "load", 8, 8, 20, 8)]

    fields = []
    for name, offset, getter, writer in (
        ("chip_id", 0x6B0, 0x930D74, 0x939C28),
        ("chip_family", 0x6B4, 0x930D7C, 0x939C2C),
        ("board_id_cache", 0x6B8, 0x930D84, 0x939C90),
        ("soc_id", 0x6BC, 0x930D8C, 0x939CC0),
        ("firmware_version", 0x6C0, 0x930D98, 0x939CE0),
    ):
        fields.append({"name": name, "width_bytes": 4, "structure_offset": offset,
                       "getter": memory(getter, "load", 4, 20, 8, offset),
                       "writer": memory(writer, "store", 4, 21,
                                        9 if name == "chip_family" else 8, offset)})
    valid_loads = [
        memory(0x939C1C, "load", 1, 20, 8, 4),
        memory(0x939C30, "load", 1, 20, 8, 0x10),
        memory(0x939C88, "load", 4, 20, 8, 0x14),
    ]
    calls += [call(0x939C0C, "kfree"), call(0x939AC4, "kfree"),
              call(0x93A248, "cnss_bus_add_fw_prefix_name"),
              call(0x93A25C, "request_firmware"),
              call(0x93A3BC, "release_firmware"),
              call(0x929BE0, "cnss_wlfw_tgt_cap_send_sync"),
              call(0x929C00, "cnss_wlfw_bdf_dnld_send_sync")]
    bdf_inputs = [
        memory(0x93A144, "load", 4, 22, 3, 0x6B8),
        memory(0x93A150, "load", 1, 22, 8, 0x6B0),
        memory(0x929BF8, "load", 4, 19, 1, 0x1364),
    ]
    constants = {
        0x1AFB13D: "bdwlang.elf", 0x1AFB149: "bdwlan.elf",
        0x1AFB154: "bdwlang.e%02x", 0x1AFB162: "bdwlan.e%02x",
        0x1AFB16F: "bdwlan%02x.e%02x",
        0x1AFB180: "bdwlang.bin", 0x1AFB18C: "bdwlan.bin",
        0x1AFB197: "bdwlang.b%02x", 0x1AFB1A5: "bdwlan.b%02x",
        0x1AFB1B2: "bdwlan%02x.b%02x",
        0x1B01C55: "%s", 0x1AF6E05: "qca6390/%s", 0x1AF6E10: "qca6490/%s",
    }
    for offset, value in constants.items():
        require(cstring(data, offset, 96) == value, "BDF format constant changed")

    ranges = {}
    for name in FUNCTIONS:
        start = sym(name)
        stop = boundaries[bisect_right(boundaries, start)]
        require(0 <= start < stop <= len(data), "reviewed function outside Image")
        ranges[name] = {"relative_text_offset": start, "size_to_next_symbol": stop - start,
                        "sha256": sha(data[start:stop])}
    selected_names = sorted(set(FUNCTIONS) | {
        "plat_env", "tracepoint_verifier_ops", "bpf_verifier_ops", "bpf_probe_read_proto",
    })
    return {
        "schema": "tb371fc-shipping-cnss-static-inspection-v1",
        "evidence_class": "source_clue",
        "source_kind": "matching_owner_kernel_binary",
        "analyzed_utc": datetime.now(timezone.utc).isoformat(),
        "input": {"size": len(data), "sha256": IMAGE_SHA},
        "mechanical_checks_passed": True,
        "symbol_decoding": {"layout": LAYOUT, "count": count,
                            "marker_count": marker_count, "all_markers_checked": True,
                            "selected_name_occurrences": {n: len(syms[n]) for n in selected_names},
                            "complete_symbol_map_published": False},
        "selected_static_relocations": list(links.values()),
        "audited_functions": ranges,
        "direct_calls": calls,
        "helper_dispatch": {
            "program_type": 5, "program_type_name": "BPF_PROG_TYPE_TRACEPOINT",
            "helper_id": 4, "helper_name": "BPF_FUNC_probe_read",
            "jump_table_relative_offset": table, "helper_table_byte": 16,
            "switch_destination_relative_offset": branch,
            "prototype_relative_offset": prototype,
            "gpl_only": True, "pkt_access": False,
            "return_type_numeric": types[0], "argument_types_numeric": list(types[1:]),
            "compiled_helper_dispatch_supported": True,
            "actual_program_load_or_attachment_tested": False,
        },
        "cnss_pointer": {
            "symbol": "plat_env", "relative_text_offset": global_pointer,
            "symbol_in_file_backed_bytes": global_pointer < len(data),
            "storage": "BSS pointer slot, not a file-backed cache value",
            "getter_load": global_load, "probe_publication": publication,
            "remove_clear": removal, "get_soc_info_device_pointer_chain": device_chain,
            "live_pointer_or_static_link_base_published": False,
            "runtime_address_or_KASLR_slide_derived": False,
            "lifetime_pin_or_synchronized_live_snapshot_proven": False,
        },
        "cache_fields": fields,
        "response_validity": {
            "reviewed_loads": valid_loads,
            "chip_info_valid_response_offset": 4,
            "board_info_valid_response_offset": 16,
            "board_id_response_offset": 20,
            "board_invalid_response_cache_value": 255,
            "chip_validity_copied_to_cache_in_audited_function": False,
            "board_validity_copied_to_cache_in_audited_function": False,
            "temporary_response_freed_before_return": True,
            "persistent_equivalent_validity_flag_proven": False,
        },
        "bdf_selection": {
            "reviewed_input_loads": bdf_inputs,
            "bdf_type_control_offset": 0x1364,
            "use_firmware_prefix_boolean_offset": 0x12E2,
            "pci_private_pointer_offset": 8, "pci_device_id_offset": 0x18,
            "basename_stack_offset": 0x30, "prefixed_name_stack_offset": 0x1C,
            "static_format_constants": [{"relative_text_offset": p, "value": v}
                                        for p, v in constants.items()],
            "persistent_selected_filename_established": False,
            "runtime_board_id_observed": False, "runtime_requested_filename": None,
        },
        "manual_control_flow_review": [
            "Helper 4 follows tp_prog_func_proto's default to tracing_func_proto and its reviewed switch entry returns bpf_probe_read_proto; the implementation calls probe_kernel_read and clears the destination on a negative result.",
            "cnss_get_plat_priv directly returns the global pointer. cnss_probe publishes a managed allocation; error/removal paths clear the global. These instructions do not provide a lifetime pin to an unrelated tracepoint reader.",
            "The successful target-capability reply conditionally copies chip fields; board_info_valid selects response board_id versus 0xff. The response flags are not copied into the audited cached fields, and the temporary response is freed.",
            "The event worker sets driver_state bit 1 before calling target-capability exchange. That bit cannot prove exchange success or either optional TLV's validity.",
            "BIN type 0 and ELF type 1 select formats from the cached board ID and chip ID bit 4. Board 0xff selects generic names; IDs up to 0xfe use one suffix; larger IDs use masked upper/lower bytes and the two-part format.",
            "The optional prefix checks a cached byte and the PCI device ID: 0x1101 uses qca6390, 0x1103 qca6490, otherwise no prefix. These current inputs do not establish the past request or successful firmware processing.",
            "The reviewed download function builds names in its stack frame, passes the prefixed name to request_firmware, and later releases firmware; it does not preserve that name in the audited platform cache.",
        ],
        "decision": {
            "dynamic_probe_implemented": False,
            "dynamic_probe_prerequisites_fully_closed": False,
            "hold_reasons": [
                "No verified current address/lifetime/synchronization contract was established by this offline audit.",
                "Original optional QMI response-validity bits are not preserved in the audited cache writes.",
                "A cached selection input is not an observed historical request filename or firmware success.",
                "BPF verifier, permission and perf attachment behavior have not been exercised on the owner.",
            ],
        },
        "actions": {
            "device_accessed": False, "live_kernel_memory_read": False,
            "bpf_program_or_map_created": False, "perf_event_open_called": False,
            "probe_attached": False, "tracepoint_enabled": False,
            "module_loaded": False, "radio_or_qmi_action": False,
        },
        "limits": [
            "Mechanical identity, table and instruction checks corroborate the fixed manual review; this is not whole-program formal verification.",
            "Offsets are relative to this exact Image's _text or to the stated private structure, never live addresses. The BSS pointer slot lies beyond the Image's file-backed bytes.",
            "No private firmware, complete kernel image, raw relocation base, full symbol map or network identifier is published.",
            "No owner Linux hardware acceptance result follows from this offline Android-binary inspection.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(fixed_file(args.image))
    result["inspector_sha256"] = sha(Path(__file__).read_bytes())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
