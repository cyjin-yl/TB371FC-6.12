#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
project=${TB371FC_REPO:-/src}
work=${TB371FC_BUILD_WORK:-/work}
jobs=${TB371FC_BUILD_JOBS:-4}
source_tree="$work/linux-6.12.114-research1"
output="$work/kernel-out"
resume=false
case "${1:-}" in
    '') ;;
    --resume) resume=true ;;
    *) printf 'Usage: %s [--resume]\n' "$0" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { printf 'Only --resume is accepted.\n' >&2; exit 2; }
export KBUILD_BUILD_USER=tb371fc-research
export KBUILD_BUILD_HOST=isolated-builder
export KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP='2026-11-23 00:00:00 +0000'
export SOURCE_DATE_EPOCH=1795392000

test -f "$work/source-manifest.json"
python3 - "$project" "$work" <<'PY'
import hashlib, json, runpy, sys
from pathlib import Path
project, work = map(Path, sys.argv[1:])
recipe = runpy.run_path(str(project / 'scripts/research/build/prepare_kernel.py'))
manifest = json.loads((work / 'source-manifest.json').read_text())
expected = set(recipe['PATCHES']) | set(recipe['COPIES']) | {
    'experimental/community-handoff/reference/kernel-6.12.114/config',
    'scripts/research/build/research.config'}
if set(manifest['inputs']) != expected or manifest['base_sha256'] != recipe['ARCHIVE_SHA256']:
    raise SystemExit('source manifest does not match the current explicit recipe')
for kind, base in [('inputs', project), ('assembled_files', work / 'linux-6.12.114-research1')]:
    for name, expected_hash in manifest[kind].items():
        actual = hashlib.sha256((base / name).read_bytes()).hexdigest()
        if actual != expected_hash:
            raise SystemExit(f'{kind} hash mismatch: {name}')
PY
if "$resume"; then
    test -f "$output/.config"
    cmp "$project/experimental/community-handoff/reference/kernel-6.12.114/config" "$output/base.config"
    cmp "$project/scripts/research/build/research.config" "$output/research.config"
    test "$(cat "$output/include/config/kernel.release")" = '6.12.114-tb371fc-research1'
else
    test ! -e "$output"
    mkdir -p "$output"
    cp "$project/experimental/community-handoff/reference/kernel-6.12.114/config" "$output/base.config"
    cp "$project/scripts/research/build/research.config" "$output/research.config"
fi
cd "$source_tree"
if ! "$resume"; then
scripts/kconfig/merge_config.sh -m -O "$output" "$output/base.config" "$output/research.config"
make O="$output" ARCH=arm64 LLVM=1 olddefconfig
# Reduce unrelated platform compilation; record the final full configuration.
python3 - "$source_tree/arch/arm64/Kconfig.platforms" "$output/.config" <<'PY'
import re, subprocess, sys
from pathlib import Path
for name in re.findall(r'^config (ARCH_[A-Z0-9_]+)$', Path(sys.argv[1]).read_text(), re.M):
    if name != 'ARCH_QCOM':
        subprocess.run(['scripts/config', '--file', sys.argv[2], '--disable', name], check=True)
PY
make O="$output" ARCH=arm64 LLVM=1 olddefconfig
fi
make O="$output" ARCH=arm64 LLVM=1 -j"$jobs" Image modules
make O="$output" ARCH=arm64 LLVM=1 -j"$jobs" qcom/sm8250-lenovo-tb371fc.dtb
make O="$output" ARCH=arm64 LLVM=1 INSTALL_MOD_PATH="$work/modules" INSTALL_MOD_STRIP=1 modules_install
mkdir -p "$work/artifacts"
cp "$output/arch/arm64/boot/Image" "$work/artifacts/Image"
cp "$output/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dtb" "$work/artifacts/board.dtb"
cp "$output/.config" "$work/artifacts/kernel.config"
cp "$output/Module.symvers" "$work/artifacts/Module.symvers"
cp "$output/include/config/kernel.release" "$work/artifacts/kernel.release"
cp "$work/source-manifest.json" "$work/artifacts/source-manifest.json"
cd "$work/artifacts"
sha256sum Image board.dtb kernel.config Module.symvers kernel.release source-manifest.json > SHA256SUMS
printf 'Built a new research kernel and matched modules; hardware acceptance remains pending.\n'
