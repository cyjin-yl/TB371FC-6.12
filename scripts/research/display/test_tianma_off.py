#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile actual panel OFF and Linux 6.12.114 panel-core lifecycle functions.

DSI transport, power callbacks, backlight operations and waits are host mocks.
The four DRM panel-core functions are extracted from a byte-pinned upstream
fixture; their state handling is neither reimplemented nor mocked.
"""
import argparse
import hashlib
import pathlib
import subprocess
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKPORT = pathlib.Path("mainline-port/backports/linux-6.12")
SOURCE = "panel-novatek-nt36523.c"
PATCH = "0022-drm-panel-tb371fc-tianma-off-sequence.patch"
FIXTURES = pathlib.Path("scripts/research/display/fixtures")
CORE = "linux-v6.12.114-drm_panel.c"
CORE_SHA256 = "b6deca77d92c2395952114154dd1674e9ee812064318d9a1b15ccb7113588d5a"
OLD_PATCH = "tianma-off-pr18-0acacec1.patch"
OLD_PATCH_SHA256 = "13debad44edec82adf21f864e1512302da1612642f0024bf293c3417987e5913"
SOURCE_SHA256 = "dadab139e6ea0a0e8cf58da0020d9182fd7a604aebd58c54efb2e4182fdb6c33"
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

struct device { int unused; };
struct drm_panel;
struct drm_panel_funcs {
    int (*prepare)(struct drm_panel *);
    int (*unprepare)(struct drm_panel *);
    int (*enable)(struct drm_panel *);
    int (*disable)(struct drm_panel *);
};
struct drm_panel_follower;
struct drm_panel_follower_funcs {
    int (*panel_prepared)(struct drm_panel_follower *);
    int (*panel_unpreparing)(struct drm_panel_follower *);
};
struct drm_panel_follower {
    const struct drm_panel_follower_funcs *funcs;
    struct drm_panel_follower *next;
};
struct list_head { struct drm_panel_follower *first; };
struct backlight_device { bool enabled; int enables, disables; };
struct drm_panel {
    struct device *dev;
    const struct drm_panel_funcs *funcs;
    struct backlight_device *backlight;
    bool prepared, enabled;
    int follower_lock;
    struct list_head followers;
};
struct panel_info {
    struct drm_panel panel;
    const struct panel_desc *desc;
    struct mipi_dsi_device *dsi[2];
};
static struct panel_info *to_panel_info(struct drm_panel *p) { return (struct panel_info *)p; }
static int trace[6], count, transfer_count, faults[4], errors;
static unsigned long flags[4];
static int reported_error, reports, prepares, unprepares;
static bool power_on;
static void check(bool ok, const char *what) {
    if (!ok) { fprintf(stderr, "FAIL: %s\n", what); errors++; }
}
static void transfer(struct mipi_dsi_multi_context *ctx, int sleep) {
    if (ctx->accum_err) return;
    if (count >= 6 || transfer_count >= 4) abort();
    trace[count++] = 10 * sleep + ctx->dsi->id;
    flags[transfer_count] = ctx->dsi->mode_flags;
    ctx->accum_err = faults[transfer_count++];
}
static void mipi_dsi_dcs_set_display_off_multi(struct mipi_dsi_multi_context *ctx) { transfer(ctx, 0); }
static void mipi_dsi_dcs_enter_sleep_mode_multi(struct mipi_dsi_multi_context *ctx) { transfer(ctx, 1); }
static void msleep(int ms) { if (count >= 6) abort(); trace[count++] = 100 + ms; }

/* External side effects are mocked; the core's branches below are unmodified. */
static inline void record_error(struct device *dev, int error) {
    (void)dev;
    reports++;
    reported_error = error;
}
#define dev_err(dev, format, error) record_error(dev, error)
static void log_message(struct device *dev, const char *format, ...) {
    (void)dev; (void)format;
}
#define dev_warn log_message
#define dev_info log_message
#define DRM_DEV_INFO log_message
static void mutex_lock(int *lock) { check(*lock == 0, "core lock acquired once"); ++*lock; }
static void mutex_unlock(int *lock) { check(*lock == 1, "core lock released once"); --*lock; }
#define list_for_each_entry(pos, head, member) \
    for (pos = (head)->first; pos; pos = pos->next)
static int backlight_enable(struct backlight_device *bl) {
    if (bl) { bl->enabled = true; bl->enables++; }
    return 0;
}
static int backlight_disable(struct backlight_device *bl) {
    if (bl) { bl->enabled = false; bl->disables++; }
    return 0;
}
'''
SUFFIX = r'''
static void reset(void) {
    count = transfer_count = reports = reported_error = prepares = unprepares = 0;
    for (int i = 0; i < 6; i++) trace[i] = -1;
    for (int i = 0; i < 4; i++) faults[i] = flags[i] = 0;
}
static int set_faults(int mask) {
    int expected = 0;
    for (int i = 0; i < 4; i++) {
        if (mask & (1 << i)) {
            faults[i] = -EIO - i;
            if (!expected) expected = faults[i];
        }
    }
    return expected;
}
static void check_tianma_trace(struct mipi_dsi_device *a, struct mipi_dsi_device *b) {
    const int want[] = {0, 1, 115, 10, 11, 160};
    check(count == 6 && transfer_count == 4, "both device calls and both delays");
    for (int i = 0; i < 6; i++) check(trace[i] == want[i], "OFF/Sleep ordering");
    for (int i = 0; i < 4; i++) check(flags[i] == (i % 2 ? 0x20ul : 0x04ul), "HS and other flags preserved");
    check(a->mode_flags == (MIPI_DSI_MODE_LPM | 0x04) && b->mode_flags == 0x20, "flags restored");
}
static void test_tianma(int mask) {
    struct mipi_dsi_device a = { MIPI_DSI_MODE_LPM | 0x04, 0 }, b = { 0x20, 1 };
    struct panel_info p = { .desc = &tb371fc_tianma_desc, .dsi = {&a, &b} };
    reset();
    int expected = set_faults(mask);
#ifdef ORIGINAL_SOURCE
    check(nt36523_disable(&p.panel) == expected, "first transfer error");
#else
    check(tb371fc_tianma_disable(&p) == expected, "first transfer error");
#endif
    check_tianma_trace(&a, &b);
}
static int prepare_panel(struct drm_panel *panel) {
    (void)panel;
    prepares++;
    power_on = true;
    return 0;
}
static int unprepare_panel(struct drm_panel *panel) {
    (void)panel;
    unprepares++;
    power_on = false;
    return 0;
}
static void test_lifecycle(int mask) {
    static const struct drm_panel_funcs funcs = {
        .prepare = prepare_panel, .unprepare = unprepare_panel,
        .disable = nt36523_disable,
    };
    struct mipi_dsi_device a = { MIPI_DSI_MODE_LPM | 0x04, 0 }, b = { 0x20, 1 };
    struct backlight_device backlight = { .enabled = true };
    struct panel_info p = {
        .panel = { .funcs = &funcs, .backlight = &backlight,
                   .prepared = true, .enabled = true },
        .desc = &tb371fc_tianma_desc, .dsi = {&a, &b},
    };
    reset();
    int expected = set_faults(mask);
    power_on = true;

    /* The real panel bridge ignores disable's result and still unprepares. */
    int ret = drm_panel_disable(&p.panel);
    check(ret == 0, "disable completes despite a transport error");
    check(!p.panel.enabled, "panel enabled cleared");
    check(p.panel.prepared && power_on, "disable preserves preparation");
    check(!backlight.enabled && backlight.disables == 1, "backlight disabled");
#ifndef ORIGINAL_SOURCE
    check(reports == !!mask && reported_error == expected, "callback reports the first error");
#else
    (void)expected;
#endif
    check_tianma_trace(&a, &b);

    check(drm_panel_unprepare(&p.panel) == 0, "unprepare completes");
    check(!p.panel.prepared && !power_on && unprepares == 1, "panel powered off");
    check(drm_panel_prepare(&p.panel) == 0, "prepare completes");
    check(p.panel.prepared && power_on && prepares == 1, "panel powered on");
    check(drm_panel_enable(&p.panel) == 0, "enable completes");
    check(p.panel.enabled, "panel enabled after a full power cycle");
    check(backlight.enabled && backlight.enables == 1, "backlight restored after a full power cycle");
    check(p.panel.follower_lock == 0, "core lifecycle leaves lock released");
}
static void test_other(const struct panel_desc *desc) {
    struct mipi_dsi_device a = { MIPI_DSI_MODE_LPM | 4, 0 }, b = { MIPI_DSI_MODE_LPM | 32, 1 };
    struct panel_info p = { .desc = desc, .dsi = {&a, &b} };
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
    for (int mask = 0; mask < 16; mask++) test_lifecycle(mask);
    test_other(&tb371fc_boe_desc);
    test_other(&other_desc);
    if (errors) { fprintf(stderr, "%d failed predicates\n", errors); return 1; }
    puts("PASS: 16 Tianma transfer masks + 16 actual DRM core lifecycle cases + 2 legacy cases");
    return 0;
}
'''


def pinned_bytes(path, expected):
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise SystemExit(f"pinned source differs: {path}: {actual}")
    return data


def core_functions(text):
    """Extract complete, unchanged function definitions, excluding export macros."""
    functions = []
    for name in ("drm_panel_prepare", "drm_panel_unprepare",
                 "drm_panel_enable", "drm_panel_disable"):
        start = text.index(f"int {name}(")
        end = text.index(f"\nEXPORT_SYMBOL({name});", start)
        functions.append(text[start:end] + "\n")
    return "\n".join(functions)


def run(repo, original=False, pre_fix=False, drm_panel_source=None):
    source = repo / BACKPORT / SOURCE
    patch = repo / (FIXTURES / OLD_PATCH if pre_fix else BACKPORT / PATCH)
    data = pinned_bytes(source, SOURCE_SHA256)
    core_path = drm_panel_source or repo / FIXTURES / CORE
    core = pinned_bytes(core_path, CORE_SHA256).decode()
    if pre_fix:
        pinned_bytes(patch, OLD_PATCH_SHA256)
    print("source sha256:", hashlib.sha256(data).hexdigest(), flush=True)
    print("patch sha256:", hashlib.sha256(patch.read_bytes()).hexdigest(), flush=True)
    print("Linux 6.12.114 panel core sha256:", CORE_SHA256, flush=True)
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
        mode = "#define ORIGINAL_SOURCE\n" if original else ""
        code.write_text(mode + PREFIX + text[start:end] +
                        core_functions(core) + SUFFIX)
        executable = root / "harness"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=undefined", "-fno-sanitize-recover=all", str(code), "-o", str(executable)], check=True)
        result = subprocess.run([str(executable)], text=True, capture_output=True)
        print(result.stdout, end="")
        print(result.stderr, end="")
        if original or pre_fix:
            if result.returncode != 1:
                raise SystemExit("negative control did not reproduce its behavioral failure")
            if pre_fix:
                for diagnostic in ("FAIL: panel enabled cleared",
                                   "FAIL: backlight restored after a full power cycle"):
                    if diagnostic not in result.stderr:
                        raise SystemExit("pre-fix control missed the lifecycle counterexample")
            print("Pre-fix lifecycle failure reproduced (expected)." if pre_fix
                  else "Original behavior rejected by the new gate (expected).")
        elif result.returncode:
            raise SystemExit(result.returncode)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    parser.add_argument("--drm-panel-source", type=pathlib.Path,
                        help="verify the same pinned core from an actual kernel source tree")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--original", action="store_true")
    mode.add_argument("--pre-fix", action="store_true")
    args = parser.parse_args()
    run(args.repo.resolve(), args.original, args.pre_fix, args.drm_panel_source)
