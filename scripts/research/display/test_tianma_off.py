#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Apply the candidate patch to a copy; run the actual disable C code with mocked DSI transport."""
import argparse
import hashlib
import pathlib
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKPORT = pathlib.Path("mainline-port/backports/linux-6.12")
SOURCE = "panel-novatek-nt36523.c"
PATCH = "0022-drm-panel-tb371fc-tianma-off-sequence.patch"
PREFIX = r'''
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#define DSI_NUM_MIN 1
#define MIPI_DSI_MODE_LPM 0x800ul
struct mipi_dsi_device { unsigned long mode_flags; int id; };
struct mipi_dsi_multi_context { struct mipi_dsi_device *dsi; int accum_err; };
struct panel_desc { bool is_dual_dsi; };
static const struct panel_desc tb371fc_tianma_desc = { true };
static const struct panel_desc tb371fc_boe_desc = { true };
static const struct panel_desc other_desc = { false };
struct drm_panel { int unused; };
struct panel_info { struct drm_panel panel; const struct panel_desc *desc; struct mipi_dsi_device *dsi[2]; };
static struct panel_info *to_panel_info(struct drm_panel *p) { return (struct panel_info *)p; }
static int trace[6], count, transfer_count, faults[4], errors;
static unsigned long flags[4];
static void check(bool ok, const char *what) {
    if (!ok) { fprintf(stderr, "FAIL: %s\n", what); errors++; }
}
static void transfer(struct mipi_dsi_multi_context *ctx, int sleep) {
    if (count >= 6 || transfer_count >= 4) abort();
    trace[count++] = 10 * sleep + ctx->dsi->id;
    flags[transfer_count] = ctx->dsi->mode_flags;
    ctx->accum_err = faults[transfer_count++];
}
static void mipi_dsi_dcs_set_display_off_multi(struct mipi_dsi_multi_context *ctx) { transfer(ctx, 0); }
static void mipi_dsi_dcs_enter_sleep_mode_multi(struct mipi_dsi_multi_context *ctx) { transfer(ctx, 1); }
static void msleep(int ms) { if (count >= 6) abort(); trace[count++] = 100 + ms; }
'''
SUFFIX = r'''
static void reset(void) {
    count = transfer_count = 0;
    for (int i = 0; i < 4; i++) faults[i] = flags[i] = 0;
}
static void test_tianma(int mask) {
    struct mipi_dsi_device a = { MIPI_DSI_MODE_LPM | 0x04, 0 }, b = { 0x20, 1 };
    struct panel_info p = { {0}, &tb371fc_tianma_desc, {&a, &b} };
    const int want[] = {0, 1, 115, 10, 11, 160};
    int expected = 0;
    reset();
    for (int i = 0; i < 4; i++) {
        if (mask & (1 << i)) {
            faults[i] = -EIO - i;
            if (!expected) expected = faults[i];
        }
    }
    check(nt36523_disable(&p.panel) == expected, "first transfer error");
    check(count == 6 && transfer_count == 4, "both halves and both delays");
    for (int i = 0; i < 6; i++) check(trace[i] == want[i], "OFF/Sleep ordering");
    for (int i = 0; i < 4; i++) check(flags[i] == (i % 2 ? 0x20ul : 0x04ul), "HS and other flags preserved");
    check(a.mode_flags == (MIPI_DSI_MODE_LPM | 0x04) && b.mode_flags == 0x20, "flags restored");
}
static void test_other(const struct panel_desc *desc) {
    struct mipi_dsi_device a = { MIPI_DSI_MODE_LPM | 4, 0 }, b = { MIPI_DSI_MODE_LPM | 32, 1 };
    struct panel_info p = { {0}, desc, {&a, &b} };
    reset();
    faults[0] = -EIO;
    check(nt36523_disable(&p.panel) == 0, "unrelated legacy error behavior");
    if (desc->is_dual_dsi) {
        check(count == 5 && transfer_count == 4 && trace[0] == 0 && trace[1] == 1 && trace[2] == 10 && trace[3] == 11 && trace[4] == 170, "BOE legacy ordering");
    } else {
        check(count == 3 && transfer_count == 2 && trace[0] == 0 && trace[1] == 10 && trace[2] == 170, "single link legacy ordering");
    }
    for (int i = 0; i < transfer_count; i++) check(flags[i] & MIPI_DSI_MODE_LPM, "unrelated LP policy");
}
int main(void) {
    for (int mask = 0; mask < 16; mask++) test_tianma(mask);
    test_other(&tb371fc_boe_desc);
    test_other(&other_desc);
    if (errors) { fprintf(stderr, "%d failed predicates\n", errors); return 1; }
    puts("PASS: 16 Tianma transfer-fault combinations + BOE and single-link legacy cases");
    return 0;
}
'''

def run(repo, original=False):
    source = repo / BACKPORT / SOURCE
    patch = repo / BACKPORT / PATCH
    data = source.read_bytes()
    print("source sha256:", hashlib.sha256(data).hexdigest(), flush=True)
    print("patch sha256:", hashlib.sha256(patch.read_bytes()).hexdigest(), flush=True)
    with tempfile.TemporaryDirectory(prefix="tb371fc-tianma-off-") as directory:
        root = pathlib.Path(directory)
        target = root / "drivers/gpu/drm/panel" / SOURCE
        target.parent.mkdir(parents=True)
        target.write_bytes(data)
        if not original:
            subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch.resolve())], cwd=root, check=True)
        text = target.read_text()
        start = text.index("static int nt36523_disable(" if original else "/* The owner Tianma OFF table")
        end = text.index("static int nt36523_unprepare(", start)
        code = root / "harness.c"
        code.write_text(PREFIX + text[start:end] + SUFFIX)
        executable = root / "harness"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all", str(code), "-o", str(executable)], check=True)
        result = subprocess.run([str(executable)])
        if original:
            if result.returncode != 1:
                raise SystemExit("original source did not reproduce expected behavioral failure")
            print("Original behavior rejected by the new gate (expected).")
        elif result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    parser.add_argument("--original", action="store_true")
    args = parser.parse_args()
    run(args.repo.resolve(), args.original)
