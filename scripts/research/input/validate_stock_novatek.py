#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare the actual old/new driver functions on owner-matched stock files.

This offline program extracts C functions verbatim. SPI operations are replaced
with a private file sink; no device is opened or firmware loaded. The patched
functions run with ASan and UBSan. Only the eight fixed files authenticated by
the live Android capture are read from the private archive. Firmware bytes stay
in the private output directory and must not be committed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile


NAMES = (
    "novatek_ts_fw_boe.bin", "novatek_ts_fw_boe_6.bin",
    "novatek_ts_mp_boe.bin", "novatek_ts_mp_boe_6.bin",
    "novatek_ts_tm_fw.bin", "novatek_ts_tm_fw_6.bin",
    "novatek_ts_tm_mp.bin", "novatek_ts_tm_mp_6.bin",
)

PREAMBLE = r'''
/* Extracted Novatek/Xiaomi driver functions retain their GPL-2.0-or-later license. */
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <inttypes.h>
typedef uint8_t u8;
#define U32_MAX UINT32_MAX
#define GFP_KERNEL 0
#define NVT_TRANSFER_LEN (63 * 1024)
#define DIV_ROUND_UP(n, d) (((n) + (d) - 1) / (d))
#define NVT_LOG(...) ((void)0)
#define NVT_ERR(...) ((void)0)
#define kzalloc(n, flags) calloc(1, (n))
#define kcalloc(n, size, flags) calloc((n), (size))
struct nvt_ts_bin_map {
    char name[12]; uint32_t BIN_addr, SRAM_addr, size, crc;
};
static struct nvt_ts_bin_map *bin_map;
static uint32_t partition;
static uint8_t ilm_dlm_num = 2, cascade_2nd_header_info;
static uint8_t *fwbuf;
struct driver_context { uint8_t hw_crc; void *client; } context;
static struct driver_context *ts = &context;
static uint64_t copied_bytes, writes, payload_hash = UINT64_C(14695981039346656037);
static FILE *copy_sink;
static int nvt_set_page(uint32_t address) { (void)address; return 0; }
static int CTP_SPI_WRITE(void *client, uint8_t *bytes, size_t length) {
    (void)client;
    if (length < 1 || length > NVT_TRANSFER_LEN + 1) return -EINVAL;
    if (fwrite(bytes + 1, 1, length - 1, copy_sink) != length - 1) return -EIO;
    writes++;
    copied_bytes += length - 1;
    for (size_t i = 1; i < length; i++) {
        payload_hash ^= bytes[i]; payload_hash *= UINT64_C(1099511628211);
    }
    return 0;
}
'''

MAIN = r'''
#ifdef NVT_VALIDATE_RANGES
static int range_checks(void) {
    unsigned checks = 0;
#define REQUIRE(expr) do { checks++; if (!(expr)) return 1; } while (0)
    REQUIRE(nvt_fw_range_valid(0, 0, 0));
    REQUIRE(!nvt_fw_range_valid(0, 0, 1));
    REQUIRE(nvt_fw_range_valid(16, 16, 0));
    REQUIRE(!nvt_fw_range_valid(16, 17, 0));
    REQUIRE(nvt_fw_range_valid(16, 12, 4));
    REQUIRE(!nvt_fw_range_valid(16, 12, 5));
    REQUIRE(!nvt_fw_range_valid(16, SIZE_MAX, 1));
    REQUIRE(!nvt_fw_range_valid(16, 1, SIZE_MAX));
    REQUIRE(nvt_fw_partition_valid(16, 0, 0));
    REQUIRE(nvt_fw_partition_valid(16, U32_MAX, 0));
    REQUIRE(nvt_fw_partition_valid(16, 14, 1));
    REQUIRE(!nvt_fw_partition_valid(16, 15, 1));
    REQUIRE(!nvt_fw_partition_valid(16, 16, 1));
    REQUIRE(!nvt_fw_partition_valid(16, U32_MAX, 1));
    REQUIRE(!nvt_fw_partition_valid(16, 1, U32_MAX));
    REQUIRE(nvt_fw_partition_valid(16, 0, 15));
    REQUIRE(!nvt_fw_partition_valid(16, 0, 16));
    const uint8_t high_bit[4] = {0, 0, 0, 0x80};
    REQUIRE(byte_to_word(high_bit) == UINT32_C(0x80000000));
    printf("{\"range_predicates_passed\":%u}\n", checks);
    return 0;
#undef REQUIRE
}
#endif
int main(int argc, char **argv) {
#ifdef NVT_VALIDATE_RANGES
    if (argc == 2 && !strcmp(argv[1], "--ranges")) return range_checks();
#endif
    if (argc != 4) return 2;
    FILE *f = fopen(argv[1], "rb");
    if (!f || fseek(f, 0, SEEK_END)) return 2;
    long n = ftell(f);
    if (n <= 0 || n > 1024 * 1024 || fseek(f, 0, SEEK_SET)) return 2;
    uint8_t *data = malloc((size_t)n);
    if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) return 2;
    fclose(f);
    ts->hw_crc = (uint8_t)atoi(argv[2]);
    int ret = nvt_bin_header_parser(data, (size_t)n);
    if (ret) {
        fprintf(stderr, "stock firmware rejected: %d\n", ret);
        free(bin_map); free(data); return 1;
    }
    fwbuf = calloc(NVT_TRANSFER_LEN + 2, 1);
    if (!fwbuf) return 2;
    copy_sink = fopen(argv[3], "wb");
    if (!copy_sink) return 2;
    ret = nvt_write_firmware(data, (size_t)n);
    if (fclose(copy_sink)) ret = -EIO;
    if (ret) {
        fprintf(stderr, "offline copy failed: %d\n", ret);
        free(fwbuf); free(bin_map); free(data); return 1;
    }
    printf("{\"partition_count\":%u,\"active_partitions\":[", partition);
    bool first = true;
    for (uint32_t i = 0; i < partition; i++) {
        if (!bin_map[i].size) continue;
        printf("%s{\"name\":\"%s\",\"file_offset\":%u,\"sram_offset\":%u,"
               "\"encoded_size\":%u,\"checksum\":%u}", first ? "" : ",",
               bin_map[i].name, bin_map[i].BIN_addr, bin_map[i].SRAM_addr,
               bin_map[i].size, bin_map[i].crc);
        first = false;
    }
    printf("],\"copy_calls\":%" PRIu64 ",\"copied_bytes\":%" PRIu64
           ",\"payload_fnv1a64\":\"%016" PRIx64 "\"}\n", writes, copied_bytes, payload_hash);
    free(fwbuf); free(bin_map); free(data);
    return 0;
}
'''


def function(text, name):
    match = re.search(r"^static [^;{}]*\b" + re.escape(name) + r"\s*\([^;{}]*\)\s*\{", text, re.M)
    if not match:
        raise ValueError("missing function: " + name)
    start = match.start()
    depth = 1
    pos = match.end()
    while depth:
        if pos >= len(text):
            raise ValueError("unterminated function")
        depth += (text[pos] == "{") - (text[pos] == "}")
        pos += 1
    return text[start:pos]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compile_harness(source, out, label, cc, sanitized):
    text = source.read_text()
    names = ["CheckSum", "byte_to_word"]
    if sanitized:
        names += ["nvt_fw_range_valid", "nvt_fw_partition_valid"]
    names += ["nvt_bin_header_parser", "nvt_write_sram", "nvt_write_firmware"]
    c = out / (label + ".c")
    c.write_text(PREAMBLE + "\n\n".join(function(text, name) for name in names) + MAIN)
    binary = out / label
    command = [cc, "-std=c11", "-g", "-O1", "-Wall", "-Wextra",
               "-Wno-unused-but-set-variable", "-Wno-unused-variable"]
    if sanitized:
        command += ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-DNVT_VALIDATE_RANGES=1"]
    command += [str(c), "-o", str(binary)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=60)
    (out / (label + "-compile.log")).write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError("compiler failed: " + result.stderr)
    return binary, {"driver_source_sha256": digest(source), "extracted_harness_sha256": digest(c),
                    "binary_sha256": digest(binary), "sanitizers": ["address", "undefined"] if sanitized else []}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--patched", type=Path, required=True)
    ap.add_argument("--archive", type=Path, required=True)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--cc", default="cc")
    args = ap.parse_args()
    args.out.mkdir(mode=0o700, parents=True, exist_ok=False)
    capture = json.loads(args.capture.read_text())
    expected = {Path(x["path"]).name: x for x in capture["firmware"]}
    if set(expected) != set(NAMES) or capture["model"] != "TB371FC":
        raise SystemExit("capture identity mismatch")
    files = []
    with tarfile.open(args.archive, "r:gz") as archive:
        for name in NAMES:
            member = archive.getmember("vendor/firmware/" + name)
            if not member.isfile() or member.size != expected[name]["size"] or member.size > 1024 * 1024:
                raise SystemExit("archive member identity mismatch")
            blob = archive.extractfile(member).read()
            if hashlib.sha256(blob).hexdigest() != expected[name]["sha256"]:
                raise SystemExit("live/archive firmware hash mismatch")
            path = args.out / name
            path.write_bytes(blob)
            files.append(path)
    baseline, old = compile_harness(args.baseline, args.out, "baseline", args.cc, False)
    patched, new = compile_harness(args.patched, args.out, "patched", args.cc, True)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1",
               UBSAN_OPTIONS="halt_on_error=1:print_stacktrace=1")
    predicates = subprocess.run([str(patched), "--ranges"], text=True, capture_output=True,
                                env=env, timeout=20, check=True)
    if predicates.stderr:
        raise RuntimeError("range predicate diagnostic: " + predicates.stderr)
    range_result = json.loads(predicates.stdout)
    checks = []
    for file in files:
        for mode in (0, 1):
            results = []
            payloads = []
            for binary in (baseline, patched):
                sink = args.out / (file.stem + "-" + str(mode) + "-" + binary.name + ".copied")
                r = subprocess.run([str(binary), str(file), str(mode), str(sink)], text=True,
                                   capture_output=True, env=env, timeout=20)
                log = args.out / (file.stem + "-" + str(mode) + "-" + binary.name + ".log")
                log.write_text(r.stdout + r.stderr)
                if r.returncode or r.stderr:
                    raise RuntimeError("stock execution failed: " + str(log))
                results.append(json.loads(r.stdout))
                payloads.append(sink.read_bytes())
            if results[0] != results[1] or payloads[0] != payloads[1]:
                raise RuntimeError("active partition/copy behavior changed: " + file.name)
            checks.append({"firmware": file.name, "sha256": digest(file),
                           "crc_mode": "hardware" if mode else "software",
                           "matches_baseline": True, "copied_payloads_equal": True,
                           "copied_payload_sha256": hashlib.sha256(payloads[1]).hexdigest(),
                           "result": results[1]})
    record = {"schema_version": 1, "evidence_class": "host_execution",
              "live_capture_sha256": digest(args.capture),
              "archive_sha256": digest(args.archive), "baseline": old, "patched": new,
              "compiler": subprocess.check_output([args.cc, "--version"], text=True).splitlines()[0],
              "range_checks": range_result,
              "cases": checks, "passed": len(checks), "firmware_written_or_loaded": False,
              "device_linux_tested": False}
    (args.out / "result.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"passed": len(checks), "result": str(args.out / "result.json")}))


if __name__ == "__main__":
    main()
