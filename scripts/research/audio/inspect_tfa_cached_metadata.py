#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Inspect the fixed owner TFA module and kernel as ordinary private files.

This is a version-specific, offline evidence reader. It never opens sysfs,
kernel memory or a device, executes a module, or emits firmware/kernel bytes.
The control-flow interpretation refers to manually reviewed AArch64 code in
the two SHA-pinned inputs; this is not a general disassembler or a proof for
other versions. Only relative file/text offsets and selected metadata leave
the process. Static pointer relocation bases are not emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct

IMAGE_SHA = "ef9e7b5cdb9ef3c66977a04d6b6e21cf83e83f2f45476390c861827d1bb1cf0f"
MODULE_SHA = "94ec336cab4e1aa338e93ac7a8a9f4671b6c3dbfc7109b0530f2318910a89f37"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fixed_file(path, size, expected):
    require(path.is_file() and not path.is_symlink(), "ordinary input file required")
    require(path.stat().st_size == size, "input size differs from the audited version")
    data = path.read_bytes()
    require(digest(data) == expected, "input SHA differs from the audited version")
    return data


def cstring(data, offset, limit=512):
    require(0 <= offset < len(data), "string offset outside input")
    end = data.index(b"\0", offset, min(len(data), offset + limit))
    return data[offset:end].decode("ascii")


class Module:
    def __init__(self, data):
        self.data = data
        h = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
        require(h[0][:6] == b"\x7fELF\x02\x01" and h[1:3] == (1, 183), "AArch64 ET_REL required")
        require(h[11] == 64 and h[12] == 32, "unexpected pinned section layout")
        self.sections = [struct.unpack_from("<IIQQQQIIQQ", data, h[6] + i * 64) for i in range(h[12])]
        names = self.raw(h[13])
        self.names = [cstring(names, s[0]) for s in self.sections]
        si = next(i for i, s in enumerate(self.sections) if s[1] == 2)
        section = self.sections[si]
        strings = self.raw(section[6])
        self.symbols = []
        for offset in range(0, section[5], 24):
            name, info, _, shndx, value, size = struct.unpack_from("<IBBHQQ", self.raw(si), offset)
            self.symbols.append({"name": cstring(strings, name), "type": info & 15,
                                 "section": shndx, "offset": value, "size": size})
        self.by_name = {s["name"]: s for s in self.symbols if s["name"]}
        self.relocations = {}
        for i, section in enumerate(self.sections):
            if section[1] != 4:
                continue
            require(section[9] == 24, "unexpected RELA entry size")
            for at in range(0, section[5], 24):
                offset, info, addend = struct.unpack_from("<QQq", self.raw(i), at)
                symbol = self.symbols[info >> 32]
                key = (section[7], offset)
                require(key not in self.relocations, "duplicate module relocation")
                self.relocations[key] = {"type": info & 0xFFFFFFFF, "symbol": symbol, "addend": addend}

    def raw(self, index):
        s = self.sections[index]
        require(s[4] + s[5] <= len(self.data) or s[1] == 8, "section outside module")
        return self.data[s[4]:s[4] + s[5]]

    def local_pointer(self, section, offset):
        r = self.relocations[(section, offset)]
        require(r["type"] == 257 and r["symbol"]["section"] != 0, "local ABS64 pointer required")
        return r["symbol"]["section"], r["symbol"]["offset"] + r["addend"]

    def function(self, name):
        s = self.by_name[name]
        b = self.raw(s["section"])[s["offset"]:s["offset"] + s["size"]]
        calls = [{"relative_text_offset": off, "symbol": r["symbol"]["name"]}
                 for (sec, off), r in self.relocations.items()
                 if sec == s["section"] and s["offset"] <= off < s["offset"] + s["size"]
                 and r["type"] == 283 and r["symbol"]["name"]]
        return {"relative_text_offset": s["offset"], "size": len(b), "sha256": digest(b), "direct_relocated_calls": calls}

    def parameters(self):
        result = []
        for name in ("fw_name_first", "fw_name_second"):
            s = self.by_name["__param_" + name]
            require(s["size"] == 40, "unexpected parameter record size")
            ops = self.relocations[(s["section"], s["offset"] + 16)]
            require(ops["type"] == 257 and ops["symbol"]["section"] == 0
                    and ops["symbol"]["name"] == "param_ops_charp" and ops["addend"] == 0,
                    "parameter is not bound to the audited generic getter")
            section, pointer = self.local_pointer(s["section"], s["offset"] + 32)
            const_section, const_pointer = self.local_pointer(section, pointer)
            mode = struct.unpack_from("<H", self.raw(s["section"]), s["offset"] + 24)[0]
            result.append({"name": name, "permission_octal": oct(mode), "ops": "param_ops_charp",
                           "parameter_record_offset": s["offset"], "data_pointer_offset": pointer,
                           "compiled_default": cstring(self.raw(const_section), const_pointer)})
        require([r["compiled_default"] for r in result] == ["tfa98xx_YC.cnt", "tfa98xx_QS.cnt"], "unexpected firmware candidates")
        return result


def kernel_metadata(data):
    require(data[56:60] == b"ARM\x64", "ARM64 Image header required")
    layout = {"offsets": 25312000, "relative_base": 25797888, "count": 25798144,
              "names": 25798400, "names_end": 27436274, "markers": 27436288,
              "token_table": 27440128, "token_index": 27441152}
    n = struct.unpack_from("<Q", data, layout["count"])[0]
    require(n == 121415, "unexpected pinned symbol count")
    offsets = struct.unpack_from("<" + "I" * n, data, layout["offsets"])
    indexes = struct.unpack_from("<256H", data, layout["token_index"])
    tokens = [cstring(data, layout["token_table"] + x, 128) for x in indexes]
    require(all(tokens), "empty token in pinned dictionary")
    marker_count = (n + 255) // 256
    markers = struct.unpack_from("<" + "Q" * marker_count, data, layout["markers"])
    pos = layout["names"]
    symbols = {}
    for i in range(n):
        if i % 256 == 0:
            require(pos - layout["names"] == markers[i // 256], "kallsyms marker mismatch")
        length = data[pos]; pos += 1
        require(length > 0 and pos + length <= layout["markers"], "compressed symbol outside table")
        name = "".join(tokens[x] for x in data[pos:pos + length]); pos += length
        require(len(name) >= 2, "empty decoded symbol")
        symbols[name[1:]] = {"type": name[0], "offset": offsets[i], "index": i}
    require(pos == layout["names_end"] and not any(data[pos:layout["markers"]]), "compressed names end mismatch")
    require(symbols["_text"]["offset"] == 0 and symbols["_stext"]["offset"] == 2048, "unexpected text anchor")

    # The file contains unrelocated pointer slots. Recover only the static
    # relocation addend base, never a live address, from a corroborated pair.
    anchor = 32173880
    target, info, addend = struct.unpack_from("<QQQ", data, anchor)
    base = target - (symbols["param_ops_charp"]["offset"] + 16)
    require(info == 1027 and addend - base == symbols["param_get_charp"]["offset"], "generic getter relocation anchor mismatch")
    relocs = {}
    pos = 0
    while True:
        pos = data.find(struct.pack("<Q", 1027), pos)
        if pos < 0:
            break
        if pos >= 8 and pos + 16 <= len(data):
            off = struct.unpack_from("<Q", data, pos - 8)[0] - base
            dest = struct.unpack_from("<Q", data, pos + 8)[0] - base
            if 0 <= off < len(data) and 0 <= dest < 64 * 1024 * 1024:
                require(off not in relocs or relocs[off]["target"] == dest, "ambiguous relative relocation")
                relocs[off] = {"record_offset": pos - 8, "target": dest}
        pos += 8

    def pointer(offset):
        if offset in relocs:
            return relocs[offset]["target"]
        require(struct.unpack_from("<Q", data, offset)[0] == 0, "unclassified nonzero pointer")
        return None

    def link(offset):
        target = pointer(offset)
        return {"field_relative_text_offset": offset, "relocation_record_offset": relocs.get(offset, {}).get("record_offset"),
                "target_relative_text_offset": target, "target_symbols": [k for k, v in symbols.items() if v["offset"] == target]}

    attribute = symbols["hw_info_tfa98xx"]["offset"]
    require(struct.unpack_from("<I", data, attribute)[0] == 131, "wrong hardware info id")
    require(cstring(data, pointer(attribute + 8)) == "tfa98xx", "wrong attribute name")
    attrs = symbols["huaqin_attrs"]["offset"]
    table = [pointer(attrs + 8 * i) for i in range(27)]
    require(table[-1] is None and table[25] == attribute + 8 and table.count(attribute + 8) == 1, "attribute pointer table mismatch")
    require(pointer(symbols["huaqin_sysfs_ops"]["offset"]) == symbols["huaqin_show"]["offset"], "show function mismatch")
    require(pointer(symbols["huaqin_ktype"]["offset"] + 8) == symbols["huaqin_sysfs_ops"]["offset"], "ktype ops mismatch")
    require(pointer(symbols["huaqin_ktype"]["offset"] + 16) == attrs, "ktype attributes mismatch")
    require(cstring(data, 0x1ADA402) == "%s\n", "format constant mismatch")
    require([cstring(data, p) for p in (0x1AD7E9C, 0x1A2EF8D, 0x1AD7D45)] == ["huaqin", "interface", "hw_info"], "init naming constants mismatch")
    ranges = {}
    for name, end in [("param_get_charp", "param_free_charp"), ("hq_register_hw_info", "huaqin_show"),
                      ("huaqin_show", "huaqin_store"), ("hq_harware_init", "hq_misc_sys_init")]:
        start, stop = symbols[name]["offset"], symbols[end]["offset"]
        ranges[name] = {"relative_text_offset": start, "size": stop - start, "sha256": digest(data[start:stop])}
    fields = [symbols["param_ops_charp"]["offset"] + 16, symbols["huaqin_sysfs_ops"]["offset"],
              symbols["huaqin_ktype"]["offset"] + 8, symbols["huaqin_ktype"]["offset"] + 16, attrs + 25 * 8]
    return {"layout": layout, "symbol_count": n, "marker_count": marker_count,
            "all_name_markers_consistent": True, "mapped_relative_relocations": len(relocs),
            "static_pointer_base_published": False, "live_kernel_memory_read": False,
            "selected_pointer_links": [link(p) for p in fields], "audited_function_ranges": ranges,
            "attribute": {"object_relative_text_offset": attribute, "id": 131, "name": "tfa98xx",
                          "permission_octal": oct(struct.unpack_from("<H", data, attribute + 16)[0]),
                          "array_index": 25, "path": "/sys/class/huaqin/interface/hw_info/tfa98xx"},
            "reviewed_control_flow": {
                "id_131_read": "huaqin_show: ordinary registered-name path; cached pointer then sprintf('%s\\n'); unregistered/null cases copy constant messages",
                "normal_read_offsets": [0x7FF8C0, 0x7FF8C4, 0x7FF8CC, 0x7FF8D4, 0x7FF944, 0x7FF94C, 0x7FF954, 0x7FFAE0, 0x7FFAE4],
                "normal_read_call": "sprintf", "normal_read_call_relative_text_offset": 0x1305F28,
                "special_id_branches_not_read": [0x20, 0x80, 0xF0, 0xF1],
                "registered_flag_field": 24, "cached_name_field": 32,
                "registration": "shared id slot stores pointer and registered=1; while registered, another registration returns -4 without replacing the pointer",
                "per_amplifier_identity_available": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--module", type=Path, required=True)
    args = parser.parse_args()
    image = fixed_file(args.image, 37445648, IMAGE_SHA)
    blob = fixed_file(args.module, 267094, MODULE_SHA)
    module = Module(blob)
    functions = {n: module.function(n) for n in ("tfa98xx_probe", "tfa98xx_i2c_probe", "tfa98xx_rw_read")}
    calls = functions["tfa98xx_probe"]["direct_relocated_calls"]
    require({"relative_text_offset": 0x14B8C, "symbol": "hq_register_hw_info"} in calls, "registration site mismatch")
    require({"relative_text_offset": 0x14BBC, "symbol": "request_firmware_nowait"} in calls, "request site mismatch")
    result = {"schema_version": 1, "evidence_class": "offline_owner_binary_inspection", "passed": True,
              "inputs": {"image": {"size": len(image), "sha256": IMAGE_SHA},
                         "module": {"size": len(blob), "sha256": MODULE_SHA}},
              "kernel": kernel_metadata(image), "module_parameters": module.parameters(),
              "module_function_ranges": functions,
              "reviewed_module_selection": {"cached_flag_structure_offset": 0x3C0,
                  "chosen_name_structure_offset": 0x328, "zero_flag_candidate": "fw_name_first",
                  "nonzero_flag_candidate": "fw_name_second", "hq_id": 131,
                  "registration_precedes_async_firmware_request": True,
                  "registration_return_value_checked_by_probe": False,
                  "rw_attribute_reads_i2c": True, "rw_attribute_read_by_this_tool": False},
              "limits": ["The cached registration name is not firmware load, DSP, calibration or playback success.",
                         "One shared registration slot cannot establish each of four amplifiers' selection.",
                         "The kernel path proof applies only to these fixed owner bytes and id 131; other attributes may have side effects.",
                         "The separate bounded Android capture owns the observed value; this tool performs no live read."],
              "module_executed_or_loaded": False, "device_accessed": False}
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
