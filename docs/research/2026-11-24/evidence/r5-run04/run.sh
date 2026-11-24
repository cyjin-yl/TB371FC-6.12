#!/bin/bash
set -uo pipefail
job=/work/r5-fedora-job-6b24e66-run04
src=/work/r5-fedora-source-6b24e66-run04
work=/work/fedora-r5-system-v4
sha=6b24e66087e80c6847f0a759e1f6e9a2b9bd4f0d
finish(){ printf '%s\n' "$?" > "$job/exit-code"; date -u +%FT%TZ > "$job/finished-utc"; }
trap finish EXIT
set -e
exec 9>>/work/r5-fedora-lane.lock
flock -n 9
date -u +%FT%TZ > "$job/started-utc"
test ! -e "$work"
export TMPDIR="$job"
run(){ local phase="$1"; shift; date -u +%FT%TZ > "$job/$phase.started"; local rc=0; "$@" > "$job/$phase.stdout" 2> "$job/$phase.stderr" || rc=$?; printf '%s\n' "$rc" > "$job/$phase.exit"; date -u +%FT%TZ > "$job/$phase.finished"; return "$rc"; }
mkdir "$src"
run download curl -fL --retry 1 --max-time 180 -o "$job/source.tar.gz" "https://codeload.github.com/cyjin-yl/TB371FC-6.12/tar.gz/$sha"
run extract tar -xzf "$job/source.tar.gz" --strip-components=1 -C "$src"
printf '%s\n' "$sha" > "$src/source-commit.txt"
sha256sum "$job/source.tar.gz" > "$job/source.sha256"
python3 - "$src" <<'PY'
from pathlib import Path
import subprocess, sys, json
root=Path(sys.argv[1])/"scripts/research/rootfs"
expected={"materialize_r5_fedora_recipe.py":"51d3a5f0c6f362e58a64dd90c64984b987903b4b","test_r5_fedora_recipe.py":"41e4105a302d9264a43ee3fc3beac727fd3c5cc4","r5_system_common.py":"bf67270747f19d5e097e0d796c0f1de93551b47a"}
actual={name:subprocess.check_output(["git","hash-object",str(root/name)],text=True).strip() for name in expected}
if actual != expected: raise SystemExit("published source blob identity mismatch")
(root.parents[2]/"verified-source-blobs.json").write_text(json.dumps(actual,indent=2)+"\n")
PY
run regression env PYTHONPATH="$src/scripts/research/rootfs" python3 -m unittest test_r5_fedora_recipe -v
run stage python3 "$src/scripts/research/rootfs/stage_r5_fedora.py" --repo "$src" --work "$work"
run materialize python3 "$src/scripts/research/rootfs/materialize_r5_fedora_recipe.py" --repo "$src" --work "$work"
run configure python3 "$work/recipe/assemble_system.py" configure
run initrd python3 "$work/recipe/assemble_system.py" initrd
run image python3 "$work/recipe/assemble_system.py" image
flock -u 9
run label python3 "$src/scripts/research/rootfs/run_r5_vm_phase.py" --work "$work" label
run verify python3 "$src/scripts/research/rootfs/run_r5_vm_phase.py" --work "$work" verify
