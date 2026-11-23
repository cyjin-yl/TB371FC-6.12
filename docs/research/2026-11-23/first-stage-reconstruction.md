# A new public-source downstream first stage

Date: 2026-11-23 UTC. Evidence classes: source audit, completed cross-build,
failed downstream generic-VM attempts, successful reference-kernel userspace
VM, and private Android v2 format verification. **No owner Linux boot pass.**

This study continues [the dependency audit](entry-source-audit.md) by actually
acquiring, patching and building a new first-stage kernel and a clean rescue
initramfs. It does not reproduce the missing V56.6/R201 chain. The selected
kernel is public **4.19.325**, distinct from both the owner's running
**4.19.157-perf+** and the historical V56.6 configuration.

The full kernel and static userspace builds completed successfully. The new
4.19 Image did **not** reach PID 1 on generic QEMU: a fixed Cortex-A76 run
reached a Qualcomm secure-call exception during early architecture setup.
The exact same rescue initramfs separately reached PID 1 using the frozen
6.12 research2 reference kernel. That is a userspace result, not a pass for
the new downstream kernel. No tablet boot, USB, kexec handoff or restore was
performed. A private unsigned v2 container now combines these new payloads
with the owner’s exact recovery-A header/DT inputs and passes independent
format checks. It remains an unbooted, format-only candidate.

The [complete evidence JSON](evidence/first-stage-reconstruction.json) contains
the source/tool/build manifests, all attempt results and log hashes, raw
generic-VM serial bytes encoded as base64, configuration differences, final
recipe hashes and the sanitized private-container verification manifest.

## Actual build outputs

The kernel job exited **0** after **1164.8 seconds** (three compile jobs).
The resulting release is `4.19.325-cip134-st18-tb371fc-entry-r1`.
The final userspace job also exited **0**. All three executables are
little-endian ELF64 AArch64 (`e_machine=183`) without a `PT_INTERP` segment.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Image` | 46,315,536 | `f8effadc219ff50b87f07563bb56255982e3ce94589adeae0f3feff68655882c` |
| `kernel.config` | 171,885 | `fff120f633f85e635fc1e8de3465be4b536f41f5345a419eaf69e10e9d3cba48` |
| `System.map` | 5,023,873 | `d05986d3001a6427a6afabe3271e6d9c4db40d5be33cad5fc65babf90c8204e2` |
| `busybox` | 1,253,520 | `f4480b232a952cf1960c96db6b8b9f2d5cef09336321ffc6b13f1f02f3e1d60e` |
| `kexec` | 1,003,472 | `70ecd56d8acc1857eaa286ebf7b30796f34d3477d21192e55c13f2797734da60` |
| `entry-return-bootloader` | 708,680 | `d5b989c22c190eb7edcf20d64707b7961fc8b9dd70fc5bb98a2484c3f14869eb` |
| `entry-initramfs.cpio.gz` | 1,351,464 | `68533fcb02e35b04c805dc433eb438e8b2e03d0a19e6904d1eadc05f5c6b2ab5` |

The uncompressed Image header reports `text_offset=0x80000`, effective
`image_size=56,471,552` bytes and flags `0xa`. Its in-memory extent is therefore
larger than its 46,315,536-byte file; future payload placement must use the
effective size. This Image-only target does not construct a TB371FC DTB or
recovery-DTBO. The separate format packager below reuses the owner board bytes
and header; it adds no AVB wrapper. The final log contains a
nonfatal `find` diagnostic for the absent output DTS directory; it is not a
DT build or validation result.

The completed kernel artifacts are in
`/work/first-stage-research/entry-r1-attempt4/artifacts`; userspace artifacts
are in `/work/first-stage-research/userspace-r1-attempt7/artifacts`. The exact
recipe snapshots are `recipe-v4` and `userspace-recipe-v7` under the same work
directory. Earlier failed and intermediate runs are retained.

## Actual VM observations, kept separate

| Attempt | Actual inputs and result | What it establishes |
| --- | --- | --- |
| `qemu-entry-r1-v1` | New 4.19 Image + new rescue initramfs; QEMU 10.0.13 `virt`, TCG, `max`, 2 CPUs, 1 GiB. Timed out after 180.17 s with no guest serial output. | **Fail**, no PID 1 observation. |
| `qemu-entry-r1-v2` | Identical Image/initramfs; only the virtual CPU was changed to `cortex-a76`. The kernel printed its real release, then failed in `setup_arch -> init_random_pool -> scm_call2 -> is_scm_armv8`; early exception handling subsequently recursed through minidump/panic. Controller timed out after 180.24 s and reaped the process. | **Fail**, concrete Qualcomm secure-world dependency in early startup. No downstream userspace or kexec runtime pass. |
| `qemu-entry-userspace-reference-v1` | Frozen 6.12 research2 Image SHA-256 `181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d` + the unchanged new rescue initramfs. Exact PID 1/release/machine markers, BusyBox and kexec hashes, helper `--version` and `kexec_loaded=0` observed; 2.99 s. | **Pass for the clean rescue userspace on that reference kernel only.** The downstream Image was not used in this run. |

The first timeout is consistent with a specific source incompatibility:
[this 4.19 `head.S`](https://github.com/tem423/android_kernel_lenovo_tb371fc/blob/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1/arch/arm64/kernel/head.S)
requires the 4 KiB granule field to equal zero and otherwise parks before the
normal console. [QEMU 10.0.13's `max` properties](https://github.com/qemu/qemu/blob/v10.0.13/target/arm/tcg/cpu64.c)
enable LPA2 by default, and
[its finalizer](https://github.com/qemu/qemu/blob/v10.0.13/target/arm/cpu64.c)
sets the field to one. The exact guest PC/registers were not captured in the
first run, so that cause remains a source-based explanation rather than a
sampled instruction-pointer result.

The Cortex-A76 run supplies a direct stack trace and early console. The
[pinned `setup.c`](https://github.com/tem423/android_kernel_lenovo_tb371fc/blob/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1/arch/arm64/kernel/setup.c)
calls `init_random_pool()` during architecture setup. The
[Qualcomm implementation](https://github.com/tem423/android_kernel_lenovo_tb371fc/blob/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1/drivers/soc/qcom/early_random.c)
requests secure-world PRNG bytes through
[`scm_call2`](https://github.com/tem423/android_kernel_lenovo_tb371fc/blob/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1/drivers/soc/qcom/scm.c).
Generic `virt` does not provide the tablet's Qualcomm secure firmware. This
candidate retains that platform behavior. Its downstream boot result remains
failed in the VM and untested on the tablet; no entropy/SCM bypass was added
for a favorable test result.

The reference-kernel invocation uses an explicit `--reference-research2`
option that validates the frozen Image, config, release and source-manifest
hashes. Its result sets `downstream_entry_kernel_used=false`. It reuses the
reviewed bounded VM controller and does not pass a tablet DT, device firmware,
network interface, physical USB controller or storage device to QEMU.

## Private owner-v2 format candidate

[package_owner_v2.py](../../../scripts/research/entry/package_owner_v2.py)
actually assembled this new private file and completed independent verification
with exit **0** in **3.52 s**:

```text
/work/first-stage-research/private-owner-v2-r1/entry-r1-owner-recovery-a-unsigned-v2.img
53,583,872 bytes
SHA-256 46a4f7c862b3a57ac95c5c11d5e746433d5f78239e1a9900eb77790013256f0e
```

The directory is mode `0700` and the image is `0600`. The source was the
owner's exact 104,857,600-byte `recovery_a` backup, SHA-256
`94649360140db672e861729927011984e9714459b4e19c9aab02b7ab79466668`.
The coordinator verified the original archive and streamed only this regular
member into a new private input file; the inaccessible original backup ACLs
were not changed. Using recovery A as a byte source does **not** select or
modify a boot slot.

The complete original 4096-byte header page is preserved except for kernel
size, ramdisk size, recovery-DTBO file offset and the legacy image-ID checksum.
Exactly 27 header bytes changed within those fields. Stored load-address
fields, product/command-line bytes, OS-version field and all other header
bytes remain identical. The 15 stored command-line tokens contain no detected
`skip_initramfs` or conflicting `init`/`rdinit` override. Only their hash and
conflict result are public; bootloader-appended arguments remain unobserved.
The new ramdisk's actual CPIO entries, init mode/source hash and static binary
hashes were rechecked before packaging.

| Component | File offset | Bytes | SHA-256 |
| --- | ---: | ---: | --- |
| New kernel | 4,096 | 46,315,536 | `f8effadc219ff50b87f07563bb56255982e3ce94589adeae0f3feff68655882c` |
| New hold initramfs | 46,321,664 | 1,351,464 | `68533fcb02e35b04c805dc433eb438e8b2e03d0a19e6904d1eadc05f5c6b2ab5` |
| Original recovery-DTBO | 47,673,344 | 4,299,963 | `279910628e61cad149ccdb16ae0aa0a3a2f46441e21132ac3a1323e565219679` |
| Original complete DTB bundle | 51,974,144 | 1,609,107 | `cb0f50f13fd70b5dcd0b12d330ae09d070ae4d6f20f4873b1a9815883726ee0e` |

The existing bounded numeric inspector reparsed the result. Separately, the
fixed AOSP `unpack_bootimg.py` at commit
`8d0922bfb932ee532226728b1bf2fe54a2055f5a` extracted all four components; every
size and SHA-256 matched its source. The same revision's `mkbootimg.py`
`update_sha()` function recomputed the legacy image ID from those independently
extracted files and matched the new header. Tool source hashes are pinned in
the recipe and captured manifest. The unpacker's raw output, which includes
owner header strings, remains in the private directory and is not part of
public evidence.

The file ends after its page-aligned DTB. It has **no AVB footer, no copied
source partition trailer, and no padding to the recovery partition size**.
The SHA-1 ID is an Android-header checksum, not a signature. The preserved OS
field is opaque owner metadata, not a claim about this new kernel's security
patch level. File-format verification does not establish runtime address
placement, ABL overlay selection, driver/firmware compatibility, authentication,
rollback acceptance, USB control or recovery. No boot/flash command was issued.

To reproduce this offline step after independently staging the exact private
backup and completing the userspace reference VM, choose a new output path:

```sh
python3 "$recipe/package_owner_v2.py" --repo /src --owner-recovery-a /work/first-stage-research/private-input/recovery_a.img --kernel-manifest "$work/entry-r1/build.json" --userspace-manifest "$work/userspace-r1/build.json" --userspace-vm "$work/qemu-userspace-reference/result.json" --output "$work/private-owner-v2"
```

The current sanitized format manifest is
`/work/first-stage-research/private-owner-v2-r1/format-manifest.json`, SHA-256
`13ebb66b54fa6c85f030ff926750d8671b12e585b8d0d1418f8402e2b12df967`.
It is embedded in the evidence JSON; the actual private image and owner data
are not added to Git.

## Scope and source closure

The new kernel and userspace recipes do not consume R201, R121, R55, a private
ramdisk, the old static kexec binary, a locally modified WLAN donor tree, or
any recovered historical patch. Every new source patch is included under
[scripts/research/entry](../../../scripts/research/entry/). This closes the
**code and rescue userspace** dependency chain. It does not make the first
stage independent of its board description or proprietary device firmware.

For this candidate the downstream board-DT/DTBO contract remains an explicit
separate input. The private format candidate preserves the owner backup bytes
without claiming their runtime selection or complete driver compatibility.
The upstream 6.12 board DT cannot be substituted for a vendor 4.19 DT: their
bindings, reserved memory and driver expectations differ.

The recipe ran in CT102's existing SSD Docker builder,
`tb371fc-build-ssd-20261123`, in `/work/first-stage-research`. The frozen
research1/research2 sources, outputs and recipes were not changed. Kernel
compilation used three jobs; the short userspace builds used one. No host or
CT package was installed and no binfmt interpreter was registered. Twenty-two
pinned Debian cross-build packages were installed in this Docker builder,
with no package upgrades or removals, and their downloaded `.deb` hashes were
retained in a separate toolchain manifest. This did change the builder's
available target linker/sysroot probes; the input-driver agent was informed
and kept its frozen 6.12 config invariant using an explicit empty sysroot.

## Fixed inputs

[sources.lock.json](../../../scripts/research/entry/sources.lock.json) records
the archive URLs, sizes and SHA-256 values. The kernel builder verifies these
archives again before using them.

| Component | Fixed identity | Provenance and qualification |
| --- | --- | --- |
| Downstream kernel | [`tem423/android_kernel_lenovo_tb371fc@9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1`](https://github.com/tem423/android_kernel_lenovo_tb371fc/tree/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1) | Public community source, tree `0dab36615babaf7b31c211589639a738f8196cf6`; not owner-kernel binary equivalence |
| Kernel C compiler | [`sticpaper/Snapdragon-LLVM-ARM-Compiler-10.0.7-for-Android-NDK@a16fec82a8deaf8f742ea54f8de98c021af200d4`](https://github.com/sticpaper/Snapdragon-LLVM-ARM-Compiler-10.0.7-for-Android-NDK/tree/a16fec82a8deaf8f742ea54f8de98c021af200d4) | Actual `clang --version` reports 10.0.7; this is a third-party import of compiler binaries, not a Qualcomm signature verification |
| AArch64 binutils | [AOSP `606f80986096476912e04e5c2913685a8f2c3b65`](https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/aarch64/aarch64-linux-android-4.9/+/606f80986096476912e04e5c2913685a8f2c3b65/) | Android 11 tag resolved to a fixed commit; despite the repository's `gcc-4.9` name, this revision has binutils and no GCC C executable |
| ARM binutils | [AOSP `b0c6a654327ca8796bed1e61dffcf523d04dceaa`](https://android.googlesource.com/platform/prebuilts/gcc/linux-x86/arm/arm-linux-androideabi-4.9/+/b0c6a654327ca8796bed1e61dffcf523d04dceaa/) | Fixed companion revision; kernel target C compilation uses Clang |
| Legacy compiler runtime | [Debian `libtinfo5_6.4-4_amd64.deb`](https://deb.debian.org/debian/pool/main/n/ncurses/libtinfo5_6.4-4_amd64.deb) | SHA-256 `dd347f794e651039e7b4c391f86c674fed7f415b3dca6b0937beb0d470f09c1a`; extracted into each isolated build, exposed only through that build's `LD_LIBRARY_PATH` |
| BusyBox | [1.37.0 source](https://busybox.net/downloads/busybox-1.37.0.tar.bz2) | SHA-256 `3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4` |
| kexec-tools | [2.0.32 stable source](https://www.kernel.org/pub/linux/utils/kernel/kexec/kexec-tools-2.0.32.tar.xz) | SHA-256 `8f81422a5fd2362cf6cb001b511e535565ed0f32c2f4451fb5eb68fed6710a5d`; different from the historical, unpinned `2.0.32.git` binary |
| Static userspace compiler/libc | Debian GCC `14.2.0-19cross1`, arm64 glibc `2.41-11cross1`, binutils `2.44-3` | Exact 22-package set and retained `.deb` hashes in `userspace-toolchain.json`; explicit QEMU user emulation, no host binfmt |

Public HTTPS acquisition plus fixed hashes is recorded separately from
signature authentication. The kernel and compiler Git revisions and acquired
archive hashes are pinned. BusyBox and kexec archive hashes were compared
with their upstream checksum lists; the kexec checksum-list signature was not
verified in this investigation. The compiler import's origin is not elevated
to an official signed toolchain distribution.

## New source changes

These patches were reconstructed against the selected public commit. They
are not claimed to recover the contents of the missing historic patches.

| Patch | Concrete problem and change | Limit |
| --- | --- | --- |
| [0001](../../../scripts/research/entry/0001-arm64-name-kexec-restart-wrapper.patch) | Vendor `proc.S` exports a two-argument `cpu_soft_restart`; the ARM64 kexec inline wrapper has a different four-argument C ABI. Rename only the kexec wrapper/call, retaining the existing five-register `__cpu_soft_restart` helper. | The compiled `machine_kexec.o` references `__cpu_soft_restart`, not the legacy `cpu_soft_restart`; runtime CPU/EL/cache handoff is untested. |
| [0002](../../../scripts/research/entry/0002-cpu-kexec-is-not-a-suspend-attempt.patch) | Normal `kernel_kexec()` sets `kexec_in_progress` before teardown. Do not abort its secondary-CPU teardown merely because a suspend wakeup is pending. | Real CPU-down failures still propagate. The context-preserving `KEXEC_JUMP` path and ordinary suspend behavior are unchanged. |
| [0003](../../../scripts/research/entry/0003-qcom-stop-local-watchdog-on-normal-kexec.patch) | The public Qualcomm watchdog has no shutdown callback and its worker rearms the pet timer. Teach both waits to observe thread stop, stop the worker while secondary CPUs remain online, then call the existing local disable helper and drain accounting work during normal kexec. | No secure-watchdog policy change, SCM workaround, DMA guarantee, or verified tablet transition. It does not reproduce the missing KMS-preservation patch. |
| [0004](../../../scripts/research/entry/0004-bpf-provide-non-jit-blinding-stub.patch) | The actual build exposed an unconditional verifier call to `bpf_jit_blinding_enabled()` with no non-JIT definition. Add the false-valued non-JIT stub alongside the existing non-JIT helpers. | No verifier bypass or warning suppression. This configuration has no BPF JIT. |

The early attempts are retained, including missing compiler runtime, an
incorrect assumption about a GCC executable in the AOSP binutils repository,
and the real non-JIT BPF compile error. The final recipe incorporates those
specific corrections. It does not silence compiler errors or remove the WLAN
source to obtain an Image.

## Resolved configuration is the authority

The initial public `vendor/tb371fc_defconfig` has SHA-256
`87185808d2a9a4cf2e8b7c917b6f60fb1c85d064a7903cf7bfeff35c6f69d2f0`.
The [entry fragment](../../../scripts/research/entry/first-stage.config) adds
classic KEXEC, devtmpfs, ACM and PL011 console support; it sets a new local
release and disables loadable modules. NCM and the vendor DWC3-MSM path remain
built in. The clean rescue image therefore has no external module signing or
symbol-version dependency. Removing MODULES also removes features that depend
on it, including this tree's BPF JIT. This is a first-stage configuration, not
a proposed desktop distribution configuration.

`olddefconfig` also exposes stale entries already present in the published
base. An exact search of every `Kconfig*` in the selected public source found
no definitions for `BACKLIGHT_KTZ8866A`, `BACKLIGHT_KTZ8866B`,
`MM8013C06_BATTERY`, `SND_SOC_TFA98XX` or `SPINEL_CHARGER`. Those base `=y`
lines do not become functional drivers in the resolved configuration.
`NFC_CTN730` is likewise absent; the actual `drivers/misc/ctn730/Kconfig`
symbol is `NFC_NXP_CTN730`, which resolves to `y`.

No `*.dts*` below the public tree's `arch/arm64/boot/dts` contains `spinel`,
`tb371fc` or `nt36532` (case-insensitive search). This is a bounded source-tree
finding, not a claim that no compatible board description exists anywhere.
The historical author used stock DTB/DTBO bytes with this public kernel.
The owner-specific DT/DTBO input and each required driver/firmware relationship
still need explicit matching before a physical launch.

## Clean ramdisk contract

[The init](../../../scripts/research/entry/ramdisk-init) is built from source
and placed in a deterministic `newc`/gzip archive with static AArch64 BusyBox,
kexec and [a small return helper](../../../scripts/research/entry/return_bootloader.c).
It mounts only virtual filesystems. It has no inherited SSH keys, password,
network daemon, Android partition mount, rootfs selector or payload auto-boot.
Its default action is to hold for a local rescue console. No proprietary
firmware is included. Built-in platform drivers can probe before PID 1, so
firmware absence, probe behavior and secure-world dependencies still require
board-specific qualification before a physical launch.

Outside VM-smoke mode, it attempts an ACM function only when exactly one UDC
is enumerated. A successful write to `UDC` would be reported only as a local
bind: host enumeration, bidirectional shell access and disconnect/reconnect
remain separate hardware observations. The helper's `--version` path is
executed during qualification; its explicitly requested restart path is not.
A compiled `reboot(RESTART2, "bootloader")` call does not prove a recoverable
bootloader or working host transport.

The kexec executable is statically linked without zlib/lzma/zstd. Its intended
kernel input is an uncompressed ARM64 Image. An initramfs can be passed as
opaque bytes for the receiving kernel to unpack. A future controlled load
must explicitly choose the classic `kexec_load` path and provide the new
second-stage DT and command line; it must not silently reuse the downstream
DT/cmdline or assume `kexec_file_load` consumes the provided DT. Neither load
nor execute was invoked in this investigation.

## Can Android v2 bypass the first stage?

**As a container format, yes; as a demonstrated temporary entry method on this
owner's device, not yet.** The [AOSP header specification](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
and [pinned mkbootimg implementation](https://android.googlesource.com/platform/system/tools/mkbootimg/+/8d0922bfb932ee532226728b1bf2fe54a2055f5a/mkbootimg.py)
allow a v2 image with separate kernel, ramdisk, recovery-DTBO and DTB components.
That construction does not require R201/R55 or any downstream Linux process.
It does require the bootloader to accept and actually enter the payload while
satisfying the [ARM64 boot protocol](https://docs.kernel.org/6.12/arch/arm64/booting.html):
correct Image placement and effective memory size, valid DT/initrd placement,
entry registers/EL, cache/MMU state and quiescent DMA.

The owner backup inspection reports 4096-byte pages, header size 1660 and
stored v2 address fields `kernel=0x8000`, `ramdisk=0x1000000`, `tags=0x100`,
`dtb=0x1f00000`. They cannot be accepted as a literal nonoverlapping runtime
map: the stored stock kernel alone is larger than the nominal 16 MiB ramdisk
offset. Actual bootloader placement/override policy has not been observed.
Changing a packager's base/offset fields is not evidence that this policy has
been discovered. An AVB footer with `algorithm NONE` is likewise not OEM
signature, rollback-index or bootloader-unlock acceptance.

The [historical direct-entry record](../../MAINLINE_STATUS.md) reports failed
mainline launches after separate overlay, header-offset and entry-branch
experiments, while a small bare-metal payload and stock/public-downstream
controls did run. The [U-Boot notes](../../U_BOOT_PORT.md) report that that
author's ABL rejected `fastboot boot` as unknown. These are useful historical
results, **not fresh observations of the owner's current ABL or transport**.
The owner's contradictory Android lock-state indicators remain unresolved by
this source study. The public [fastboot protocol](https://android.googlesource.com/platform/system/core/+/master/fastboot/README.md)
does not establish which commands this ABL implements.

Research2-display also retains TB371FC vendor-handoff-specific early memory
and capability handling. Its generic-QEMU result is not a cold-entry
qualification. A source-complete v2 packager alone would therefore not close
these entry and recovery gates. The new downstream route is the concrete
build pursued here, while direct entry remains a separate, unresolved route.

## Reproduce the code and userspace build

Run the following inside an isolated Docker builder with the recorded Debian
build dependencies. Use a **new work directory**; the acquisition and build
scripts refuse to replace their existing output directories/manifests. The
captured run uses numbered attempt directories so its earlier failures remain
available.

```sh
recipe=/src/scripts/research/entry
work=/work/first-stage-reproduce
python3 "$recipe/fetch_first_stage_sources.py" --work "$work" --lock "$recipe/sources.lock.json"
python3 "$recipe/bootstrap_userspace_tools.py" --work "$work"
python3 "$recipe/build_first_stage_kernel.py" --work "$work" --recipe "$recipe" --jobs 3 --name entry-r1
python3 "$recipe/build_first_stage_userspace.py" --work "$work" --recipe "$recipe" --jobs 1 --name userspace-r1
python3 "$recipe/smoke_first_stage.py" --kernel-manifest "$work/entry-r1/build.json" --userspace-manifest "$work/userspace-r1/build.json" --output "$work/qemu-entry-r1" --cpu cortex-a76
```

The last command reproduces the downstream VM attempt; with the recorded
generic machine its Qualcomm SCM failure is expected, and a nonzero result
must be retained. The separate rescue-userspace qualification uses:

```sh
python3 "$recipe/smoke_first_stage.py" --reference-research2 /work/research2-display/artifacts --userspace-manifest "$work/userspace-r1/build.json" --output "$work/qemu-userspace-reference" --cpu max
```

The two package/source acquisitions and all commands are recorded. Source,
patch, config, tool and artifact hashes make this a reviewable rebuild recipe.
No second independent byte-identical full-kernel rebuild has been performed;
that stronger reproducibility claim is not made.

## Physical gates still open

A successful code build or generic VM does not close any owner hardware case.
The next physical entry needs a verified external control/recovery route;
matched owner DT/DTBO and bootloader selection behavior; understood placement
of the effective kernel image, DT and initrd; the required firmware and its
loader paths; reliable USB rescue access; and an independently observed return
to the original Android state. A subsequent kexec additionally needs stopped
secondary CPUs, local and secure watchdog behavior, DMA/device teardown,
correct second-stage memory/DT/command line and retained control on failure.
This candidate has not established those conditions.
