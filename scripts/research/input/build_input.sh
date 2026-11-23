#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
work=${TB371FC_INPUT_WORK:-/work/input-integration-v3}
work=$(realpath -e "$work")
recipe="$work/input-recipe/scripts/research/input"
source_tree="$work/linux-6.12.114-input-integration"
output="$work/kernel-out"
# Research2 had no target userspace sysroot. Do not let later cross-libc
# installations silently change Kconfig's CC_CAN_LINK capability results.
# Kernel target objects are freestanding; host tools still use the host libc.
target_cc="clang --sysroot=$work/target-sysroot"
export PATH="/usr/lib/llvm-19/bin:$PATH"
export KBUILD_BUILD_USER=tb371fc-research
export KBUILD_BUILD_HOST=isolated-builder
export KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP='2026-11-23 00:00:00 +0000'
export SOURCE_DATE_EPOCH=1795392000
exec 9>"$work/build.lock"
flock -n 9 || { printf 'Another input build owns this work.\n' >&2; exit 2; }
test ! -e "$output"
test ! -e "$work/artifacts"
python3 "$recipe/prepare_input.py" --repo "$work/input-recipe" --work "$work" --verify
mkdir "$output"
mkdir "$work/target-sysroot"
cp "$work/baseline-abi/kernel.config" "$output/.config"
make -C "$source_tree" O="$output" ARCH=arm64 LLVM=1 CC="$target_cc" -j1 olddefconfig modules_prepare
cmp "$work/baseline-abi/kernel.config" "$output/.config"
cp "$work/baseline-abi/Module.symvers" "$output/Module.symvers"
make -C "$source_tree" O="$output" ARCH=arm64 LLVM=1 CC="$target_cc" -j1 \
    M="$source_tree/drivers/input/touchscreen/nt36523" modules
make -C "$source_tree" O="$output" ARCH=arm64 LLVM=1 CC="$target_cc" -j1 \
    drivers/hid/i2c-hid/i2c-hid-of.o drivers/hid/i2c-hid/i2c-hid-core.o \
    drivers/hid/hid-multitouch.o \
    qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb
python3 "$recipe/regress_input.py" --source "$source_tree" --output "$work/regression" --cc clang
python3 "$recipe/inspect_input.py" --work "$work"
printf 'Input module, HID objects, joint DT and source-derived regression completed; device tests remain pending.\n'
