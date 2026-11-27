# R7 generic VM image qualification

`run_rpmh_generic_vm.py` runs the inherited generic ARM `virt` maintenance
label boot, followed by its enforcing production verification boot. It adds
an explicit chain of whole-image identities around the unchanged acceptance
program. The input must be the newly constructed, still unbooted R7 image.
No successful R7 VM run is asserted by this source or its tests.

## Execution

Use the established HDD build container `tb371fc-build-20261123`, with the
original host heavy-job admission already held and durable tmux evidence.
The wrapper runs in the foreground and does not acquire or replace that
admission. Construction and VM qualification are separate admitted jobs.
Both phases use `/usr/bin/qemu-system-aarch64`, `virt`, `cortex-a72`, two
virtual CPUs and 2048 MiB. There is no network, monitor, board DT, device
passthrough or host filesystem share.

```bash
MAKEFLAGS=-j2 python3 -B -O \
  "$R7_REPO/scripts/research/system-kernel/research7-rpmh-clock/run_rpmh_generic_vm.py" \
  --repo "$R7_REPO" \
  --work /work/fedora-r7-system-406f-01 \
  --construction-result-sha256 "$ACTUAL_R7_CONSTRUCTION_RESULT_SHA256"
```

Supply the SHA256 of the actual successful `r7-construction-result.json`.
The wrapper requires its exact constructor identity, R7 release, label,
production archive and 4 GiB ordinary image. All `vm-*` paths must be absent;
the fixed run names are `vm-label-01` and `vm-verify-01`. An unsuccessful or
previously booted image cannot silently restart this chain.

Use the same immutable recipe sources and their file modes as construction.
The wrapper recreates the exact 16-file R7 derivation from the pinned
constructor and original sources, then compares every actual recipe file,
its mode and the derivation receipt. It never edits the frozen acceptance
program. The system emulator and read-only result extractor are pinned to
the observed HDD container binaries:

| Binary | Bytes | SHA256 |
| --- | ---: | --- |
| `/usr/bin/qemu-system-aarch64` | 34,073,536 | `2e7fe3008a900980493a85e606036793fd162153edac0228477579988c53e1f5` |
| `/usr/sbin/debugfs` | 255,824 | `deb37b9515718738f369dfe0546a50a74fdd7d5837046adac272ef6a3381ccee` |

## Acceptance and ownership

The maintenance boot intentionally uses its maintenance initramfs and
`enforcing=0` to label the new image. The production boot uses the qualified
production initramfs with `enforcing=1`, `rdinit=/init.tmpfs`,
`rd.tb371fc.early-selinux=1`, `rd.tb371fc.tmpfs-root=1` and
`module.sig_enforce=1`. Existing readbacks and full guest gates remain
unchanged. A maintenance pass alone never qualifies a production image.

The inherited driver limits each VM to 900 seconds and 8 MiB of serial
output. The outer driver deadline is 1200 seconds, allowing its bounded
read-only persistent-result extraction after QEMU exits. Cancellation first
gives the driver 30 seconds to terminate QEMU and retain its evidence. A Linux
child subreaper then accounts for any orphan because the inherited driver
starts QEMU in a separate session. The wrapper reaps every owned descendant;
if an uninterruptible child remains, it keeps the foreground admission alive
and emits cleanup diagnostics until that child is gone. It does not release
ownership merely because a cleanup deadline elapsed.

After each exited driver, the wrapper checks the exact QEMU argv, pinned
inputs, recorded phase and scope. For verification it independently extracts
the private same-boot guest result from the closed image using the unchanged
read-only reader. The extracted bytes must equal the driver's retained guest
result. Both phases are then parsed again by the unchanged
`boot_system_vm.inspect_serial`. All acceptance results must match, including
the original enforcing/tmpfs/module-signature checks and zero production
warning counts. Readback does not mount, repair or replay the filesystem.

## Versioned receipt and image chain

The terminal receipt is `r7-generic-vm-result.json`, schema
`tb371fc-r7-generic-vm-v1`. A successful receipt has
`rootfs_phase="generic-vm-verified-v1"` and binds:

1. The caller-pinned construction receipt and its original full image hash.
2. The independently hashed image before and after the label boot.
3. The independently hashed image before and after production verification.
4. Both original phase results, command records and complete serial logs.
5. The retained guest result, independent reparse records, driver logs,
   wrapper, unchanged driver, recipe source inputs, profile and host tools.

Each phase begins only when its current full-image hash equals the preceding
stage's output. Post-boot hashes are taken after the owned driver, QEMU and
result-extraction children have been reaped. `final_rootfs` equals the final
verification output and is the image a subsequent R7 board-model contract
must name. The construction receipt and initial hash remain unchanged.

`passed`, `inputs_reverified` and `generic_virt_acceptance` become true only
after both phases and all final input checks pass. `board_model_verified`,
`physical_boot_verified` and `native_userspace_verified` remain false, and
`owner_native_linux_passes_added` remains zero. The generic VM result cannot
establish physical tablet readiness or a successful board-model handoff.

The tests cover real subprocess cancellation and separate-session orphan
cleanup, source regeneration, receipt identity negatives and phase command
policy. They do not start a VM or substitute for a retained runtime receipt.
