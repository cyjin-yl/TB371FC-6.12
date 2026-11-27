# R7 Fedora root and initramfs construction

`build_rpmh_rootfs.py` constructs a separate root, production initramfs,
maintenance initramfs and 4 GiB ordinary ext4 image for
`6.12.114-tb371fc-research7-rpmh-clock`. The root label is
`tb371fc-r7-f45`. It is a construction recipe; no completed R7 root, initramfs,
VM result or native boot is asserted by the source or its unit tests.

## Required inputs

Run only after the reviewed R7 kernel builder has completed with all of its
source, configuration, signing, module ABI and retention checks passing. Pass
the SHA256 of that actual `build-result.json`. The constructor requires the
reviewed builder identity, exact R7 config and native DTB identities, 84 module
paths matching R6, the same module bytes in the build/signature/ABI receipts,
the corresponding new public certificate, the exported symbol CRC table,
extracted kernel BTF and all three installed Kbuild metadata files.

The Fedora source is the same frozen baseline used to construct R5:
`/work/fedora-system-integration-v1/rootfs`. Its canonical tar stream must be
1,323,141,120 bytes with SHA256
`1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96`.
The source is rechecked after construction. The copied root retains its
69-file firmware inventory and journal ACLs. Existing baseline kernel files
and canonical runtime metadata are preserved under their original release
or the new root's `archive/research1` directory.

Use the established build container, its pinned PRoot and AArch64 QEMU user
emulator, and the original host heavy-job admission. Keep the operation in a
real tmux pane with its command log and terminal status. The work directory
must be a new `/work/fedora-r7-system-*` directory; `MAKEFLAGS` must be `-j2`.
The constructor's child processes have owned process groups, bounded phase
deadlines, latched cancellation and recorded command logs.

```bash
MAKEFLAGS=-j2 python3 -B -O \
  "$R7_REPO/scripts/research/system-kernel/research7-rpmh-clock/build_rpmh_rootfs.py" \
  --repo "$R7_REPO" \
  --kernel-work /work/r7-rpmh-clock-406f-01 \
  --build-result-sha256 "$R7_BUILD_RESULT_SHA256" \
  --work /work/fedora-r7-system-406f-01
```

## Versioned derivation

The pinned R5 materializer creates an unexecuted template in the new work
directory. A separate R7 recipe changes five template files: the release,
label and profile guards in the two guest programs; the R7 working-directory
adapter; the new hostname; and the initramfs producer's explicit supplier
module inclusion. The original R5 and v9 sources are never edited.

The three archive checkers, initrd process-domain proof payloads, result
reader/writer, transient protocol, file-descriptor probe and generic VM
driver remain byte-identical. Their existing checks for the fixed policy,
bootstrap, tmpfs handoff, AArch64 libraries and 69 firmware payloads still
apply. The copied VM driver is not executed by construction.

The initramfs explicitly includes `qcom-rpmh-regulator`, `qnoc-sm8250`,
`icc-rpmh`, `icc-bcm-voter` and `interconnect_qcom`. The actual target `depmod`
output determines their dependency closure. After packing, both archives
must contain that complete closure, only the new release's signed module
bytes, and a text dependency graph matching the corresponding qualified root
graph. Binary indexes are inventoried; the constructor does not claim to
interpret them or to have loaded any module.

## Outputs and limits

The terminal receipt is `r7-construction-result.json`. A successful receipt
binds the R7 build, profile, module tree, archive supplier checks, production
initramfs and new ext4 image. It explicitly leaves userspace, native boot and
runtime signature enforcement unverified. `mkfs.ext4`, read-only `e2fsck`
and `blkid` operate on a newly created ordinary image file; the recipe never
mounts an image, opens a tablet partition or boots QEMU system emulation.

Production handoff retains `rdinit=/init.tmpfs`,
`rd.tb371fc.early-selinux=1`, `rd.tb371fc.tmpfs-root=1`, `enforcing=1` and
`module.sig_enforce=1`. Runtime readback and the inherited guest acceptance
checks remain separate work. The existing R5 launcher must continue to
reject R7 substitutions; an R7 system launch requires its own reviewed input
contract.
