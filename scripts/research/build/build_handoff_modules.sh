#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Compile the exported R241 diagnostic modules for this new kernel ABI.
# This does not install, load, or activate a charger/Type-C driver.
set -euo pipefail
project=${TB371FC_REPO:-/src}
work=${TB371FC_BUILD_WORK:-/work}
module_work="$work/r241-research1"
kernel_output="$work/kernel-out"

test "$(cat "$kernel_output/include/config/kernel.release")" = '6.12.114-tb371fc-research1'
test -s "$kernel_output/Module.symvers"
test ! -e "$module_work"
(
    cd "$project/experimental/community-handoff"
    sha256sum --check SOURCE_SHA256SUMS
)
mkdir -p "$module_work"
cp -a "$project/experimental/community-handoff/reference/r241/." "$module_work/"
make -C "$kernel_output" ARCH=arm64 LLVM=1 M="$module_work" W=1 -j2 modules
python3 - "$module_work" "$kernel_output" <<'PY'
import hashlib, json, subprocess, sys
from pathlib import Path
module_work, kernel_output = map(Path, sys.argv[1:])
release = (kernel_output / 'include/config/kernel.release').read_text().strip()
rows = []
for name in ('tcpm.ko', 'r233_pmic_tcpm.ko'):
    path = module_work / name
    data = path.read_bytes()
    assert data[:6] == b'\x7fELF\x02\x01' and int.from_bytes(data[18:20], 'little') == 183
    magic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(path)], text=True).strip()
    assert magic.split()[0] == release
    rows.append({'name': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'vermagic': magic})
result = {'kernel_release': release,
          'kernel_module_symvers_sha256': hashlib.sha256((kernel_output/'Module.symvers').read_bytes()).hexdigest(),
          'modules': rows, 'installed': False, 'loaded': False, 'hardware_tested': False,
          'scope': 'R241 diagnostic source compilation against the new research ABI only'}
(module_work / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
PY
