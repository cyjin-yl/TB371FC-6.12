#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute the actual WDT-history C function with injected operation failures.

Reconstructs the public Novatek sources from the repository patches, verifies
the unchanged R5 core identity, and applies only the new history patch to a
second private copy. The harness extracts both the function and its WDT caller
block verbatim. It uses no firmware bytes, device access, or installed modules.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


DRIVER = Path("drivers/input/touchscreen/nt36523")
BASE_SHA = "c1bc7a07d67ec332a6154ca9403df7ee971e31efa0798c2cc8a611ed9c5035a0"
BASE_PATCHES = (
    "0013-input-nt36523-preserve-gpio-irq-errors.patch",
    "0018-input-nt36523-use-declared-physical-dimensions.patch",
    "0019-input-nt36523-fail-closed-and-release-resources.patch",
    "0020-input-nt36523-validate-firmware-ranges.patch",
)
NEW_PATCH = "0021-input-nt36523-handle-wdt-history-failures.patch"
CASES = (
    "success", "no-history", "page-error", "read-error", "alloc-error",
    "restore-error", "page-and-restore-error", "read-and-restore-error",
    "alloc-and-restore-error", "no-history-and-restore-error",
    "all-ff", "all-zero",
)

PREAMBLE = r'''
/* Extracted Novatek/Xiaomi C retains its GPL-2.0-or-later license. */
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <errno.h>
#define FW_HISTORY_SIZE 128
#define DUMMY_BYTES 1
#define GFP_KERNEL 0
struct memory_map { uint32_t FW_HISTORY_ADDR, EVENT_BUF_ADDR; } memory_map;
struct controller { struct memory_map *mmap; void *client; const char *fw_name; } controller;
static struct controller *ts = &controller;
static int page_error, read_error, restore_error, alloc_error, payload_kind;
static unsigned pages, restores, reads, allocs, frees, dumps, reloads;
static char history_text[513], order[32];
static size_t order_len;
static void require(int condition, const char *message) {
    if (!condition) { fprintf(stderr, "%s\n", message); exit(1); }
}
static void op(char c) {
    require(order_len + 1 < sizeof(order), "operation trace overflow");
    order[order_len++] = c; order[order_len] = '\0';
}
static int nvt_set_page(uint32_t address) {
    if (address == memory_map.EVENT_BUF_ADDR) {
        restores++; op('E'); return restore_error;
    }
    require(address == memory_map.FW_HISTORY_ADDR, "wrong history page");
    pages++; op('P'); return page_error;
}
static int CTP_SPI_READ(void *client, uint8_t *buffer, size_t length) {
    require(client == ts->client, "wrong SPI client");
    require(length == FW_HISTORY_SIZE + 1, "wrong history read length");
    require(buffer[0] == (memory_map.FW_HISTORY_ADDR & 0xff), "wrong history offset");
    reads++; op('R');
    for (size_t i = 0; i < FW_HISTORY_SIZE; i++)
        buffer[i + 1] = payload_kind == 1 ? 0xff : payload_kind == 2 ? 0 : (uint8_t)(i ^ 0xa5);
    return read_error;
}
static void *test_alloc(size_t length, int flags) {
    (void)flags;
    require(length == FW_HISTORY_SIZE * 4, "unexpected dump allocation size");
    allocs++; op('A');
    return alloc_error ? NULL : calloc(1, length);
}
static void test_free(void *p) {
    if (p) { frees++; op('F'); }
    free(p);
}
static void test_log(const char *format, ...) {
    va_list args;
    require(!strcmp(format, "%s"), "unexpected successful dump format");
    va_start(args, format);
    const char *text = va_arg(args, const char *);
    require(text != NULL, "null dump printed");
    size_t length = strlen(text);
    require(length < sizeof(history_text), "dump text too long");
    memcpy(history_text, text, length + 1);
    va_end(args);
    dumps++; op('D');
}
#define NVT_ERR(...) ((void)0)
#define NVT_LOG(...) test_log(__VA_ARGS__)
#define kzalloc test_alloc
#define kfree test_free
static int nvt_update_firmware(const char *name) {
    require(name == ts->fw_name, "firmware recovery selection changed");
    reloads++; op('U'); return 0;
}
static int nvt_wdt_fw_recovery(uint8_t *data) { (void)data; return 1; }
'''

MAIN = r'''
static void configure(const char *name) {
    memory_map.FW_HISTORY_ADDR = 0x240c0;
    memory_map.EVENT_BUF_ADDR = 0x20000;
    controller.mmap = &memory_map; controller.client = &controller;
    controller.fw_name = "fixture-only-never-loaded.bin";
    if (strstr(name, "no-history")) memory_map.FW_HISTORY_ADDR = 0;
    if (strstr(name, "page-")) page_error = -ETIMEDOUT;
    if (strstr(name, "read-")) read_error = -EIO;
    if (strstr(name, "alloc-")) alloc_error = 1;
    if (strstr(name, "restore-error")) restore_error = -EREMOTEIO;
    if (!strcmp(name, "all-ff")) payload_kind = 1;
    if (!strcmp(name, "all-zero")) payload_kind = 2;
}
static void validate_dump(void) {
    char expected[513]; size_t n = 0;
    for (unsigned i = 0; i < FW_HISTORY_SIZE; i++) {
        uint8_t v = payload_kind == 1 ? 0xff : payload_kind == 2 ? 0 : (uint8_t)(i ^ 0xa5);
        int written = snprintf(expected + n, sizeof(expected) - n, "%02X ", v);
        require(written == 3, "fixture formatting failed"); n += (size_t)written;
        if ((i + 1) % 16 == 0) expected[n++] = '\n';
    }
    expected[n] = '\0';
    require(n == 392 && strlen(history_text) == 392, "history text length changed");
    require(!memcmp(history_text, expected, n + 1), "history payload/format changed");
}
int main(int argc, char **argv) {
    require(argc == 3, "mode and case required");
    configure(argv[2]);
    int expected = !memory_map.FW_HISTORY_ADDR ? -EOPNOTSUPP :
                   page_error ? page_error : read_error ? read_error :
                   alloc_error ? -ENOMEM : restore_error;
    bool direct = !strcmp(argv[1], "direct");
    int actual = direct ? (int)nvt_dump_fw_history() : actual_wdt_call();
    if (direct) require(actual == expected, "wrong diagnostic errno");
    require(restores == 1, "event-page restoration must be attempted exactly once");
    require(pages == (memory_map.FW_HISTORY_ADDR != 0), "unexpected history-page call");
    bool can_read = memory_map.FW_HISTORY_ADDR && !page_error;
    bool can_alloc = can_read && !read_error;
    bool can_dump = can_alloc && !alloc_error;
    require(reads == (unsigned)can_read, "read continued after page failure");
    require(allocs == (unsigned)can_alloc, "allocation continued after transfer failure");
    require(dumps == (unsigned)can_dump, "invalid history data printed");
    require(frees == (unsigned)can_dump, "successful allocation not freed exactly once");
    if (can_dump) validate_dump();
    require(reloads == (direct ? 0u : 1u), "diagnostic failure prevented WDT reload");
    require(order[order_len - 1] == (direct ? 'E' : 'U'), "wrong final operation");
    if (!direct) require(order_len > 1 && order[order_len - 2] == 'E', "reload before page restoration");
    printf("{\"mode\":\"%s\",\"case\":\"%s\",\"return\":%d,\"dump_bytes\":%zu,\"operations\":\"%s\"}\n",
           argv[1], argv[2], actual, strlen(history_text), order);
    return 0;
}
'''


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def block(text: str, start: int) -> str:
    """Select a brace-balanced block; these frozen bodies contain no brace literals."""
    first = text.index("{", start)
    depth, position = 1, first + 1
    while depth and position < len(text):
        depth += (text[position] == "{") - (text[position] == "}")
        position += 1
    if depth:
        raise ValueError("unterminated source block")
    return text[start:position]


def harness(text: str) -> str:
    match = re.search(r"^static (?:u?int32_t|int) nvt_dump_fw_history\(void\)\s*\{", text, re.M)
    if not match:
        raise ValueError("history function not found")
    function = block(text, match.start())
    start = text.index("if (nvt_wdt_fw_recovery(point_data)) {")
    caller = block(text, start)
    wrapper = ("\nstatic int actual_wdt_call(void) {\n"
               "int32_t ret = 0; uint8_t point_data[8] = {0}; point_data[1] = 0xFD;\n" +
               caller + "\nXFER_ERROR: return ret;\n}\n")
    return PREAMBLE + function + wrapper + MAIN


def reconstruct(repo: Path, before: Path, after: Path) -> dict:
    first = repo / "mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch"
    before.mkdir()
    files = []
    for chunk in first.read_text().split("diff --git ")[1:]:
        header, *lines = chunk.splitlines()
        relative = Path(header.split(" b/", 1)[1])
        if not relative.is_relative_to(DRIVER):
            continue
        if "--- /dev/null" not in lines or ".." in relative.parts:
            raise ValueError("unexpected original driver patch")
        payload = "\n".join(s[1:] for s in lines if s.startswith("+") and not s.startswith("+++")) + "\n"
        target = before / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload)
        files.append(str(relative))
    if len(files) != 6:
        raise ValueError("original driver file set changed")
    backports = repo / "mainline-port/backports/linux-6.12"
    sources = [first]
    for name in BASE_PATCHES:
        patch = backports / name
        subprocess.run(["git", "apply", "--check", str(patch)], cwd=before, check=True)
        subprocess.run(["git", "apply", str(patch)], cwd=before, check=True)
        sources.append(patch)
    original = before / DRIVER / "nt36xxx.c"
    if sha(original) != BASE_SHA:
        raise ValueError("reconstructed R5 core differs from frozen input")
    shutil.copytree(before, after)
    patch = backports / NEW_PATCH
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=after, check=True)
    subprocess.run(["git", "apply", str(patch)], cwd=after, check=True)
    sources.append(patch)
    return {"patches": [{"path": str(p.relative_to(repo)), "sha256": sha(p)} for p in sources],
            "baseline_nt36xxx_sha256": sha(original),
            "patched_nt36xxx_sha256": sha(after / DRIVER / "nt36xxx.c")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    repo, work = args.repo.resolve(), args.work.resolve()
    if work == repo or repo.is_relative_to(work):
        raise SystemExit("work must not contain the repository")
    work.mkdir(mode=0o700, parents=True, exist_ok=False)
    before, after = work / "baseline", work / "patched"
    record = {"schema_version": 1, "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "evidence_class": "host_actual_c_fault_injection", "physical_hardware_tested": False,
              "firmware_loaded": False, "module_loaded": False, "passed": False,
              "runner_sha256": sha(Path(__file__)), "runs": []}
    try:
        record.update(reconstruct(repo, before, after))
        compiler = shutil.which(args.cc)
        if not compiler:
            raise ValueError("compiler not found")
        record["compiler"] = subprocess.check_output([compiler, "--version"], text=True)
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=1:halt_on_error=1", UBSAN_OPTIONS="halt_on_error=1")
        for name, source in (("baseline", before), ("patched", after)):
            c = work / (name + ".c")
            c.write_text(harness((source / DRIVER / "nt36xxx.c").read_text()))
            binary = work / name / "history-harness"
            command = [compiler, "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                       "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                       "-no-pie", str(c), "-o", str(binary)]
            compile_result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            (work / (name + "-compile.log")).write_text(compile_result.stdout + compile_result.stderr)
            record[name + "_compile"] = {"command": command, "exit_code": compile_result.returncode,
                                        "source_sha256": sha(c)}
            if compile_result.returncode:
                raise RuntimeError(name + " harness compilation failed")
            cases = [(mode, case) for mode in ("direct", "wdt") for case in CASES] if name == "patched" else [
                ("direct", "success"), ("direct", "page-error"), ("direct", "read-error"), ("direct", "alloc-error")]
            for mode, case in cases:
                result = subprocess.run([str(binary), mode, case], capture_output=True, text=True, timeout=15, env=env)
                stem = name + "-" + mode + "-" + case
                (work / (stem + ".stdout")).write_text(result.stdout)
                (work / (stem + ".stderr")).write_text(result.stderr)
                expected_failure = name == "baseline" and case != "success"
                entry = {"source": name, "mode": mode, "case": case, "exit_code": result.returncode,
                         "expected_failure": expected_failure, "stdout": result.stdout,
                         "stderr_sha256": sha(work / (stem + ".stderr"))}
                record["runs"].append(entry)
                if expected_failure:
                    marker = "null pointer" if case == "alloc-error" else "wrong diagnostic errno"
                    if result.returncode == 0 or marker not in result.stderr:
                        raise RuntimeError("baseline defect not reproduced: " + case)
                elif result.returncode:
                    raise RuntimeError("regression failed: " + stem)
        record["patched_checks_passed"] = 2 * len(CASES)
        record["baseline_defects_reproduced"] = 3
        record["passed"] = True
    except Exception as exc:
        record["error"] = str(exc)
    finally:
        record["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (work / "result.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        print(json.dumps(record, sort_keys=True))
    if not record["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
