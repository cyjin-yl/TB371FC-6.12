#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile and exercise the actual patched ARM64 early allocator with host stubs.

Without arguments, apply patch 0023 to the exact retained R6 mmu.c fixture.
With --kernel-source, validate and extract the actual newly prepared source.
This checks allocator selection and failure behavior; it is not a guest boot.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

BASE_SHA = "b03413247434f6c2abd500036e2aca226f49156ebb726949c25f3a925ab1ca44"
PATCHED_SHA = "27cf3be8c966c1cfe84f5c3cb715aedd3c3d4a8f5ef522c5737212476dc8a0fb"
PATCH_SHA = "297c52bf389f50759d15422e8e51023e0e92d0548f6be6234c9622724a74a50a"
PATCH_REL = "mainline-port/backports/linux-6.12/0023-arm64-tb371fc-explicit-memblock-page-tables.patch"
FIXTURE_NAME = "linux-v6.12.114-tb371fc-mmu.c"
OPTIONS = argparse.Namespace(kernel_source=None, cc=None)

PREAMBLE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <errno.h>
#include <setjmp.h>
typedef uint8_t u8;
typedef uint64_t phys_addr_t;
#define PAGE_SIZE 4096U
#define __aligned(x) __attribute__((aligned(x)))
#define __init
#define __initdata
#define MEMBLOCK_ALLOC_NOLEAKTRACE UINT64_C(0xfffffffffffffffe)
#define early_param(name, fn) \
    static const char *registered_name = name; \
    static int (*registered_parser)(char *) = fn
#define pr_info_once(msg) do { \
    static bool emitted; \
    if (!emitted) { emitted = true; log_count++; log_message = msg; } \
} while (0)
static void *initial_boot_params = (void *)(uintptr_t)1;
static bool compatible = true;
static bool fail_allocation;
static unsigned int memblock_calls, compatibility_calls, root_calls, log_count;
static const char *log_message;
static jmp_buf panic_target;
static bool expect_panic;
static char panic_message[256];
static int of_get_flat_dt_root(void)
{
    assert(initial_boot_params);
    root_calls++;
    return 42;
}
static bool of_flat_dt_is_compatible(int root, const char *name)
{
    assert(root == 42 && strcmp(name, "lenovo,tb371fc") == 0);
    compatibility_calls++;
    return compatible;
}
static phys_addr_t memblock_phys_alloc_range(phys_addr_t size,
        phys_addr_t alignment, phys_addr_t start, phys_addr_t end)
{
    assert(size == PAGE_SIZE && alignment == PAGE_SIZE && start == 0);
    assert(end == MEMBLOCK_ALLOC_NOLEAKTRACE);
    memblock_calls++;
    return fail_allocation ? 0 : UINT64_C(0x300000000) + memblock_calls * PAGE_SIZE;
}
static phys_addr_t __pa_symbol(void *ptr)
{
    return (phys_addr_t)(uintptr_t)ptr;
}
static __attribute__((noreturn)) void panic(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(panic_message, sizeof(panic_message), fmt, ap);
    va_end(ap);
    if (!expect_panic) {
        fprintf(stderr, "unexpected panic: %s", panic_message);
        abort();
    }
    longjmp(panic_target, 1);
}
'''

HARNESS = r'''
static void check_pool_page(unsigned int i)
{
    phys_addr_t p = early_pgtable_alloc(12);
    assert(p == __pa_symbol(tb371fc_early_pgtable_pool) + i * PAGE_SIZE);
    assert((p % PAGE_SIZE) == 0);
    assert(memblock_calls == 0);
}
static void check_memblock_pages(unsigned int count)
{
    unsigned int i;
    for (i = 0; i < count; ++i)
        assert(early_pgtable_alloc(12) == UINT64_C(0x300000000) + (i + 1) * PAGE_SIZE);
    assert(memblock_calls == count);
    assert(tb371fc_early_pgtable_pool_used == 0);
}
int main(int argc, char **argv)
{
    unsigned int i;
    assert(argc >= 2);
    assert(strcmp(registered_name, "tb371fc.early_pgtable") == 0);
    assert(registered_parser == parse_tb371fc_early_pgtable);
    assert(!tb371fc_early_pgtable_memblock);
    assert(TB371FC_EARLY_PGTABLE_POOL_PAGES == 256);

    if (!strcmp(argv[1], "default-board")) {
        for (i = 0; i < 256; ++i)
            check_pool_page(i);
        assert(tb371fc_early_pgtable_pool_used == 256);
        assert(log_count == 0);
        expect_panic = true;
        if (!setjmp(panic_target)) {
            early_pgtable_alloc(12);
            abort();
        }
        assert(strcmp(panic_message,
               "TB371FC embedded early page-table pool exhausted\n") == 0);
        assert(tb371fc_early_pgtable_pool_used == 256 && memblock_calls == 0);
    } else if (!strcmp(argv[1], "non-board")) {
        compatible = false;
        check_memblock_pages(5000);
        assert(compatibility_calls == 5000 && log_count == 0);
    } else if (!strcmp(argv[1], "no-fdt")) {
        initial_boot_params = NULL;
        check_memblock_pages(5000);
        assert(root_calls == 0 && compatibility_calls == 0 && log_count == 0);
    } else if (!strcmp(argv[1], "explicit-memblock")) {
        assert(registered_parser("memblock") == 0);
        assert(tb371fc_early_pgtable_memblock);
        check_memblock_pages(5000);
        assert(log_count == 1);
        assert(strcmp(log_message,
               "TB371FC early page tables: explicit memblock allocator\n") == 0);
    } else if (!strcmp(argv[1], "invalid")) {
        assert(argc == 3);
        assert(registered_parser(argv[2]) == -EINVAL);
        assert(!tb371fc_early_pgtable_memblock);
        check_pool_page(0);
        assert(log_count == 0);
    } else if (!strcmp(argv[1], "missing")) {
        assert(registered_parser(NULL) == -EINVAL);
        assert(!tb371fc_early_pgtable_memblock);
        check_pool_page(0);
        assert(log_count == 0);
    } else if (!strcmp(argv[1], "allocation-failure")) {
        assert(argc == 3);
        if (!strcmp(argv[2], "explicit"))
            assert(registered_parser("memblock") == 0);
        else if (!strcmp(argv[2], "non-board"))
            compatible = false;
        else {
            assert(!strcmp(argv[2], "no-fdt"));
            initial_boot_params = NULL;
        }
        fail_allocation = true;
        expect_panic = true;
        if (!setjmp(panic_target)) {
            early_pgtable_alloc(12);
            abort();
        }
        assert(strcmp(panic_message, "Failed to allocate page table page\n") == 0);
        assert(memblock_calls == 1 && tb371fc_early_pgtable_pool_used == 0);
    } else if (!strcmp(argv[1], "duplicate-parser-semantics")) {
        /* The launcher, not Linux's early-option parser, rejects duplicates. */
        assert(registered_parser("memblock") == 0);
        assert(registered_parser("invalid") == -EINVAL);
        assert(tb371fc_early_pgtable_memblock);
    } else {
        abort();
    }
    puts("allocator case passed");
    return 0;
}
'''


def pin(path, expected):
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError(f"source identity differs: {path}: {actual}")
    return raw


def prepared_source(directory):
    here = Path(__file__).resolve().parent
    if OPTIONS.kernel_source:
        return pin(OPTIONS.kernel_source / "arch/arm64/mm/mmu.c", PATCHED_SHA)
    repo = here.parents[3]
    fixture = here / "fixtures" / FIXTURE_NAME
    patch = repo / PATCH_REL
    raw = pin(fixture, BASE_SHA)
    pin(patch, PATCH_SHA)
    target = directory / "arch/arm64/mm/mmu.c"
    target.parent.mkdir(parents=True)
    target.write_bytes(raw)
    subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-d", str(directory),
                    "-i", str(patch)], check=True, capture_output=True, timeout=30)
    return pin(target, PATCHED_SHA)


class EarlyPageTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="tb371fc-pgtable-")
        cls.addClassCleanup(cls.temp.cleanup)
        directory = Path(cls.temp.name)
        raw = prepared_source(directory)
        source = raw.decode("utf-8")
        start = "#define TB371FC_EARLY_PGTABLE_POOL_PAGES 256"
        end = "\nbool pgattr_change_is_safe("
        if source.count(start) != 1 or source.count(end) != 1:
            raise ValueError("allocator extraction boundaries differ")
        body = source[source.index(start):source.index(end)]
        program = directory / "allocator.c"
        program.write_text(PREAMBLE + body + HARNESS)
        cls.binary = directory / "allocator"
        compiler = OPTIONS.cc or shutil.which("clang") or shutil.which("cc")
        if not compiler:
            raise RuntimeError("a host C compiler is required")
        subprocess.run([compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", str(program), "-o", str(cls.binary)],
                       check=True, capture_output=True, timeout=90)

    def case(self, *args):
        result = subprocess.run([str(self.binary), *args], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout, "allocator case passed\n")

    def test_native_default_retains_bounded_pool_and_exhaustion(self):
        self.case("default-board")

    def test_non_tb371fc_uses_memblock(self):
        self.case("non-board")

    def test_no_fdt_uses_memblock_without_dereference(self):
        self.case("no-fdt")

    def test_exact_opt_in_can_request_5000_table_pages(self):
        self.case("explicit-memblock")

    def test_missing_option_value_keeps_pool(self):
        self.case("missing")

    def test_unknown_and_case_changed_values_keep_pool(self):
        for value in ("", "MEMBLOCK", "pool", "auto", "memblock=1", "memblock ", "1"):
            with self.subTest(value=value):
                self.case("invalid", value)

    def test_allocator_failure_panics_in_all_memblock_paths(self):
        for mode in ("explicit", "non-board", "no-fdt"):
            with self.subTest(mode=mode):
                self.case("allocation-failure", mode)

    def test_duplicate_semantics_require_launcher_rejection(self):
        self.case("duplicate-parser-semantics")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-source", type=Path,
                        help="test the exact patched Linux source instead of applying the fixture patch")
    parser.add_argument("--cc", help="host C compiler")
    OPTIONS, remaining = parser.parse_known_args()
    unittest.main(argv=[__file__, *remaining])
