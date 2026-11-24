#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail
project=${TB371FC_REPO:-/src}
work=${TB371FC_RESEARCH2_WORK:-/work/research2-display}
jobs=${TB371FC_BUILD_JOBS:-4}
project=$(realpath -e "$project")
work=$(realpath -e "$work")
source_tree="$work/linux-6.12.114-research2-display"
output="$work/kernel-out"
release='6.12.114-tb371fc-research2-display'
resume=false
case "${1:-}" in
    '') ;;
    --resume) resume=true ;;
    *) printf 'Usage: %s [--resume]\n' "$0" >&2; exit 2 ;;
esac
(( $# <= 1 )) || { printf 'Only --resume is accepted.\n' >&2; exit 2; }
[[ "$jobs" =~ ^[1-4]$ ]] || { printf 'Use 1..4 build jobs in this profile.\n' >&2; exit 2; }
test -f "$work/source-manifest-research1.json"
python3 "$project/scripts/research/build/prepare_research2_display.py" --repo "$project" --work "$work" --verify
exec 9>"$work/build.lock"
flock -n 9 || { printf 'Another candidate build owns this work directory.\n' >&2; exit 2; }
test ! -e "$work/artifacts"
test ! -e "$work/artifacts.partial"
export KBUILD_BUILD_USER=tb371fc-research
export KBUILD_BUILD_HOST=isolated-builder
export KBUILD_BUILD_VERSION=1
export KBUILD_BUILD_TIMESTAMP='2026-11-23 00:00:00 +0000'
export SOURCE_DATE_EPOCH=1795392000

if "$resume"; then
    test -f "$output/build-state.json"
    python3 - "$project" "$work" <<'PY'
import json, sys
from pathlib import Path
project, work = map(Path, sys.argv[1:])
sys.path.insert(0, str(project / 'scripts/research/build'))
import prepare_research2_display as profile
state = json.loads((work / 'kernel-out/build-state.json').read_text())
if state['kernel_release'] != profile.RELEASE:
    raise SystemExit('resume release mismatch')
for name, expected in state['inputs'].items():
    if profile.digest(work / name) != expected:
        raise SystemExit('resume input changed: ' + name)
PY
else
    test ! -e "$output"
    mkdir -p "$output"
    cp "$project/experimental/community-handoff/reference/kernel-6.12.114/config" "$output/base.config"
    cp "$project/scripts/research/build/research.config" "$output/research1.config"
fi

cd "$source_tree"
if ! "$resume"; then
    scripts/kconfig/merge_config.sh -m -O "$output" "$output/base.config" "$output/research1.config"
    make O="$output" ARCH=arm64 LLVM=1 olddefconfig
    python3 - "$source_tree/arch/arm64/Kconfig.platforms" "$output/.config" <<'PY'
import re, subprocess, sys
from pathlib import Path
for name in re.findall(r'^config (ARCH_[A-Z0-9_]+)$', Path(sys.argv[1]).read_text(), re.M):
    if name != 'ARCH_QCOM':
        subprocess.run(['scripts/config', '--file', sys.argv[2], '--disable', name], check=True)
PY
    make O="$output" ARCH=arm64 LLVM=1 olddefconfig
    python3 - "$project" "$work" <<'PY'
import sys
from pathlib import Path
project, work = map(Path, sys.argv[1:])
sys.path.insert(0, str(project / 'scripts/research/build'))
import prepare_research2_display as profile
if profile.digest(work / 'kernel-out/.config') != profile.BASE_CONFIG_SHA256:
    raise SystemExit('resolved baseline differs from the frozen research1 configuration')
PY
    cp "$output/.config" "$output/resolved-research1.config"
    scripts/config --file "$output/.config" --set-str LOCALVERSION '-tb371fc-research2-display'
    make O="$output" ARCH=arm64 LLVM=1 olddefconfig
    python3 - "$project" "$work" <<'PY'
import json, sys
from pathlib import Path
project, work = map(Path, sys.argv[1:])
sys.path.insert(0, str(project / 'scripts/research/build'))
import prepare_research2_display as profile
before = (work / 'kernel-out/resolved-research1.config').read_text().splitlines()
after = (work / 'kernel-out/.config').read_text().splitlines()
key = 'CONFIG_LOCALVERSION='
if [line for line in before if not line.startswith(key)] != [line for line in after if not line.startswith(key)]:
    raise SystemExit('configuration changed beyond the explicit release suffix')
if [line for line in after if line.startswith(key)] != [key + '"' + profile.LOCALVERSION + '"']:
    raise SystemExit('candidate localversion mismatch')
paths = ['source-manifest.json', 'source-manifest-research1.json', 'kernel-out/.config',
         'kernel-out/base.config', 'kernel-out/research1.config', 'kernel-out/resolved-research1.config']
state = {'schema_version': 1, 'kernel_release': profile.RELEASE,
         'only_config_change': {'CONFIG_LOCALVERSION': profile.LOCALVERSION},
         'inputs': {name: profile.digest(work / name) for name in paths}}
(work / 'kernel-out/build-state.json').write_text(json.dumps(state, indent=2, sort_keys=True) + '\n')
PY
fi

make O="$output" ARCH=arm64 LLVM=1 -j"$jobs" Image modules
make O="$output" ARCH=arm64 LLVM=1 -j"$jobs" qcom/sm8250-lenovo-tb371fc-display-test-6.12.dtb
test "$(cat "$output/include/config/kernel.release")" = "$release"
python3 - "$project" "$work" <<'PY'
import sys
from pathlib import Path
project, work = map(Path, sys.argv[1:])
sys.path.insert(0, str(project / 'scripts/research/build'))
import prepare_research2_display as profile
dtb = work / 'kernel-out' / profile.QCOM / (profile.DT_NAME + '.dtb')
if profile.digest(dtb) != profile.DTB_SHA256:
    raise SystemExit('compiled display DTB differs from the qualified wrapper binary')
profile.verify_work(project, work)
PY
make O="$output" ARCH=arm64 LLVM=1 INSTALL_MOD_PATH="$work/modules" INSTALL_MOD_STRIP=1 modules_install
mkdir "$work/artifacts.partial"
cp "$output/arch/arm64/boot/Image" "$work/artifacts.partial/Image"
cp "$output/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc-display-test-6.12.dtb" "$work/artifacts.partial/board.dtb"
cp "$output/.config" "$work/artifacts.partial/kernel.config"
cp "$output/Module.symvers" "$work/artifacts.partial/Module.symvers"
cp "$output/System.map" "$work/artifacts.partial/System.map"
cp "$output/include/config/kernel.release" "$work/artifacts.partial/kernel.release"
cp "$output/build-state.json" "$work/artifacts.partial/build-state.json"
cp "$work/source-manifest.json" "$work/source-manifest-research1.json" "$work/artifacts.partial/"
cd "$work/artifacts.partial"
sha256sum Image board.dtb kernel.config Module.symvers System.map kernel.release build-state.json \
    source-manifest.json source-manifest-research1.json > SHA256SUMS
cd "$work"
mv artifacts.partial artifacts
printf 'Built independent research2-display Image/modules/DT; physical hardware acceptance remains pending.\n'
