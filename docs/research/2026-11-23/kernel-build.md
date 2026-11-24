# Linux 6.12.114 research build: actual compilation and generic ARM boot

Date: 2026-11-23, Asia/Shanghai. This is a new source combination named
`6.12.114-tb371fc-research1`, built in a dedicated Docker container inside
doesvm CT102. It is not a reconstruction of the author's R226 binary, an
installable recovery image, or a physical TB371FC hardware-validation result.

**The final Image, modules and native board DTB compiled successfully. The
same final Image then booted on a generic QEMU ARM64 `virt` machine and ran
a freestanding ARM64 `/init`.** The first VM attempt exposed an actual early
page-table failure; both that failure and the successful retest are retained.

The compiled base board DT deliberately leaves the native internal panel and
Novatek touch node disabled. A source/ABI baseline with disabled devices does
not satisfy the owner's [whole-device acceptance contract](acceptance.md).

## Source assembly and fixes

[prepare_kernel.py](../../../scripts/research/build/prepare_kernel.py) starts
from the official Linux 6.12.114 archive, SHA-256
`7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3`.
It applies an explicit ordered list and copies three explicit source files.
It never treats all historical experiments as a stackable patch series.

| Input or change | Purpose and evidence boundary |
| --- | --- |
| Exported 6.12.114 working-tree patch | Supplies the handoff's 19 modified files; it does not supply every external driver or DT source |
| Novatek input patch `0002`, backlight integration `0006`, explicit 6.12 panel/backlight/board sources | Completes the missing source and Kbuild inputs for this new build |
| Backport `0013` | Preserves negative GPIO-to-IRQ errors, including probe deferral |
| Backport `0014` | Unwinds failed dual-backlight probe list/pointer ownership |
| Backport `0015` | Releases the OF node reference in the headless MSM lookup without changing address-space policy |
| Backport `0016` | Fixes actual 6.12 DT compilation failures: the missing GPU ZAP label and unavailable DSI clock macros |
| Historical I2C-HID patch `0017` | Adds the wake GPIO sequencing required by the board DT; this was absent from the exported working-tree patch |
| Backport `0017-arm64-scope-tb371fc-early-page-table-pool.patch` | Contains the inherited static allocator workaround to a flattened root compatible of `lenovo,tb371fc`; restores upstream allocation for other machines |

The two files numbered `0017` are in different directories and serve different
subsystems. Both paths are explicit in the preparation recipe and source
manifest. The historical HID patch, like `0006`, has inaccurate hunk counts;
the recipe uses `git apply --recount --check` before applying each named patch.
The new backport patches also pass ordinary `git apply --check`.

The source manifest records every input hash and the resulting panel,
backlight, touch, MSM, I2C-HID, binding, MMU and board-DTS hashes. The build
script verifies the manifest against the current explicit recipe before
compiling. `--resume` also requires the original base/config fragments and
expected kernel release, so an unrelated output tree is not silently reused.

## Configuration and module boundary

The historical exported configuration is merged with
[research.config](../../../scripts/research/build/research.config), followed
by `olddefconfig`. Unrelated ARM64 platform families are disabled; QCOM stays
enabled. The resolved full configuration is retained with the artifacts.

The research fragment enables firmware XZ/Zstd loading and the missing
V4L2 mem-to-mem parent of `VIDEO_QCOM_VENUS`. It includes the Novatek touch,
panel and dual-backlight modules, MSM, I2C-HID, namespaces and the limited
PL011/virtio transports used for VM preflight. Historical framebuffer/reset
checkpoint options are disabled. Enabling Venus in Kconfig establishes a
build prerequisite, not working video decoding or the correct Venus firmware.

Image, DTB, resolved config, `Module.symvers`, installed modules and
`kernel.release` belong to this build. Old R226 `.ko` files must not be mixed
with it. [inspect_kernel.py](../../../scripts/research/build/inspect_kernel.py)
checks the ARM64 Image header, native DT root compatible, required resolved
Kconfig values, every installed module's ELF architecture and release string,
and hashes the actual signed module bytes. It does not load a module or claim
that equal vermagic alone establishes full ABI compatibility.

The public [kernel build evidence](evidence/kernel-build.json) contains exact
artifact hashes, selected module details, source manifest and job/log hashes.
The final inspector found **83 expected and 83 installed modules**, with the
build `modules.order`, installed order and actual module-file set all matching.
There are no missing modules or undeclared extra module directories. Fifteen
relevant driver modules are listed separately in the JSON. The complete
[module checksum index](evidence/kernel-modules.SHA256SUMS) and
[builder package list](evidence/builder-packages.tsv) are published as metadata
and retained beside the build artifacts on doesvm.

The exported R241 TCPM/PMIC diagnostic modules were also rebuilt separately
against this `Module.symvers`; see [the R241 result](r241-build.md). They are
not installed into the 83-module baseline and were not loaded or used to
control charging.

## A failure that compilation did not catch

The first complete build took 2038.69 seconds and exited zero. A second,
incremental build integrated the omitted keyboard wake patch and also exited
zero. The resulting Image's SHA-256 was
`57cf7f0255b7bf7788341036fac6a3807070540f04f2a96e71aed72e06117ff2`.

On QEMU `virt`, CPU `max`, 2 vCPUs and 1 GiB RAM, it reached the early console
and then panicked with:

```text
TB371FC embedded early page-table pool exhausted
```

The trace passed through `early_pgtable_alloc`, memory mapping and
`paging_init`. The handoff had replaced the normal memblock allocator with
a fixed 256-page pool for every machine. This pool originated as a workaround
for the author's vendor-kernel kexec handoff. The observed VM failure is not
evidence that this owner's tablet has reproduced the original DMA/handoff
problem.

The new backport uses the **flattened** DT root, because `setup_arch()` has
validated it before paging setup but has not yet unflattened the live OF tree.
For `lenovo,tb371fc`, the existing pool and its explicit exhaustion panic are
preserved. For other roots or no flattened tree, it restores the upstream
`memblock_phys_alloc_range()` call and allocation-failure check. The change
does not enlarge the pool, disable `rodata_full`, remove KPTI, or hide a failed
memory-protection check.

There is an important entry-contract limit: the separate historical
`sm8250-lenovo-tb371fc-recovery-overlay.dts` has a Qualcomm-only root compatible,
not `lenovo,tb371fc`. If an entry path passes that root unchanged to this
kernel, it selects the memblock branch even on the physical tablet. This
build's **native board DTB** includes `lenovo,tb371fc`, and that is checked in
the artifact inspector. A future boot manifest must pin the final DT actually
passed to kexec; a model name or the first-stage recovery DT is insufficient.
The original board-specific pool and kexec/DMA issue remain open acceptance
items. Do not broaden the guard to all `qcom,kona` boards.

## Successful generic VM retest

After rebuilding with that fix, the Image SHA-256 is:

```text
5b7dbf8ac810ef4b488d394f6b976d876e52372621428f751f02f8deac5667f5
```

The board DTB remains 126,236 bytes, SHA-256
`129bbee33b0c71be120d1d724be6267d0e4f99c07ec9ed951a823ab9241998dc`.
The repaired build exited zero in 158.49 seconds. The same VM configuration
then reached `/init` and printed:

```text
TB371FC_QEMU_RELEASE=6.12.114-tb371fc-research1
TB371FC_QEMU_MACHINE=aarch64
TB371FC_QEMU_EL0_READY
```

The VM test observed its marker in 5.17 seconds and exited successfully.
[smoke_qemu.py](../../../scripts/research/build/smoke_qemu.py) then ends only
its own QEMU child. It uses no tablet DTB, proprietary firmware, network,
physical disk or passthrough device. The small
[probe init](../../../scripts/research/build/qemu-init.c) calls `uname` and
writes to the console. It is not a Fedora/NixOS/Nura rootfs initramfs and must
not be installed as the tablet's root loader.

Retained results:

- [Initial failed VM result](evidence/kernel-qemu-initial.json).
- [Successful fixed VM result](evidence/kernel-qemu-fixed.json).
- [Initial serial output](evidence/kernel-qemu-initial.log) and
  [successful serial output](evidence/kernel-qemu-fixed.log), preserving the
  original bytes covered by the result hashes.
- [Independent DT build investigation](build-dtb.md).
- [Input/backlight source and fault-injection review](static-driver-fixes.md).

## Build environment and reproducibility limits

The actual container is `tb371fc-build-20261123`, inside CT102. It has 4 CPUs,
8 GiB RAM, an 8 GiB memory-plus-swap limit and a 2048 PID limit. It has no
physical-device passthrough or Docker socket. `/src` is the project mounted
read-only; `/work` is its dedicated persistent volume. Ordinary build jobs
run in visible `tb371fc` tmux windows and retain their stdout and exit metadata.

The [Containerfile](../../../scripts/research/build/Containerfile) fixes the
Debian trixie-slim base digest. The actual compiler/linker are Debian LLVM
19.1.7, whereas the historical author's configuration referred to LLVM 18.
The exact installed builder packages are recorded in `builder-packages.tsv`.
The current recipe does **not** pin APT to an immutable package snapshot.

Build user, host, version and timestamp are fixed. Nevertheless, a fresh
build generates a private module-signing key under the inherited configuration.
The certificate and signatures affect output bytes. The private key remains
in the private build workspace and is not published. This is an executable,
source-pinned rebuild recipe with identified outputs; **bit-for-bit independent
reproduction has not been established**. Do not disable signing merely to
claim deterministic output.

The initial HDD volume was I/O constrained. A whole-toolchain snapshot/SSD
staging experiment was started; its long-running snapshot client was later
stopped (service exit 143), retaining the original container and work volume.
All results above were obtained in that original container and are not
attributed to an SSD migration. Any later SSD qualification is a separate
environment/result record.

## Reproduce in a fresh isolated work volume

Use the current branch and a fresh container/volume name. Build the image from
the narrow build-script directory, so private project data is not a Docker
build context. Inside the dedicated container, the sequence is:

```sh
python3 /src/scripts/research/build/prepare_kernel.py
bash /src/scripts/research/build/build_kernel.sh
python3 /src/scripts/research/build/smoke_qemu.py
python3 /src/scripts/research/build/inspect_kernel.py
```

Preparation refuses an existing source directory and the normal build refuses
an existing output directory. For an explicitly reviewed incremental change,
retain the old artifacts and manifest, update the source/manifest together,
then use `build_kernel.sh --resume`. Use a new VM output directory for every
retest. The persistent job wrapper records each command separately; a failed
earlier result is not overwritten with a later success.

Actual outputs are `/work/artifacts` and `/work/modules` inside the builder.
They contain no complete tablet recovery/boot image or distro entry contract.
No new mainline image was flashed or booted on the owner's tablet in this work.
