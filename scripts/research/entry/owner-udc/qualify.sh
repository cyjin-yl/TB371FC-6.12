#!/bin/sh
# Independent, host-only owner-UDC revision; historical inputs stay unchanged.
set -eu
repo=${TB371FC_ENTRY_REPO:-/src}
name=${1:-userspace-r2-owner-udc}
work=/work/first-stage-research
output=$work/$name

# The repacker refuses existing destinations and validates the pinned parent
# binaries, owner observation and narrow init change before publishing bytes.
python3 -B "$repo/scripts/research/entry/owner-udc/repack.py" \
    --repo "$repo" --work "$work" --output "$output"

# This is the frozen mainline reference Image, not a downstream-kernel test.
# entry_smoke prevents gadget creation and does not load/execute kexec.
python3 -B "$repo/scripts/research/entry/smoke_first_stage.py" \
    --reference-research2 /work/research2-display/artifacts \
    --userspace-manifest "$output/build.json" \
    --controller "$repo/scripts/research/build/smoke_qemu.py" \
    --output "$output/qemu-reference" --cpu cortex-a76 --timeout 180

# The unchanged 4.19 entry-r1 Image is packaged with the new userspace. The
# old packer's entry-r1 basename refers to that unchanged kernel release;
# this fresh directory and manifest distinguish the owner-UDC revision.
python3 -B "$repo/scripts/research/entry/package_owner_v2.py" \
    --repo "$repo" \
    --owner-recovery-a "$work/private-input/recovery_a.img" \
    --kernel-manifest "$work/entry-r1-attempt4/build.json" \
    --userspace-manifest "$output/build.json" \
    --userspace-vm "$output/qemu-reference/result.json" \
    --output "$output/private-owner-v2"
