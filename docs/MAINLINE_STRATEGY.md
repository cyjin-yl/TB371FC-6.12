# TB371FC: make upstream Linux the long-term platform

Date: **2026-11-24, Asia/Shanghai**. Reviewed project snapshot:
`ec42c48405eb3966ca2539e53d96d02a5e725059` on
`research/reproducible-build-gpu-20261123`.

## Recommendation

Develop a reproducible, upstream-oriented Linux kernel and a normal AArch64
distribution as the primary long-term system for this tablet. Keep the
existing Android/chroot environment available while the native boot and
hardware work is qualified. Limit a reconstructed vendor kernel to a clearly
identified recovery/boot bridge or reference experiment when it is useful.
Do not make an unavailable exact vendor source release a prerequisite for
all mainline driver development.

This changes the direction of the work, not its completion status. The
[owner acceptance ledger](research/2026-11-23/acceptance.md) at the reviewed
snapshot still has **44 cases: 12 blocked, 32 not run, zero owner native-Linux
runs and zero hardware passes**. The existing R5 build, QEMU results and
upstream author's R226 hardware report retain their original evidence scopes.
This document adds no boot, deployment or driver test.

中文概要：长期主线应是“可复现的上游 Linux 适配＋正常 ARM64 发行版”。
多数 SoC 驱动可以复用；工作重点是本机启动、板级设备树、缺失外设协议、
固件合同和整机电源管理。当前没有本机主线 Linux 验收通过，不能把别人的
R226 或我们的 QEMU 构建当成这台平板已经可日用。

## Why this is a better architectural fit

The [fresh owner observation](evidence/2026-11-24-live-android-baseline.json)
identifies TB371FC / `spinel`, Android 14 ZUI 16.0.474 and
`4.19.157-perf+`. The decompressed live configuration still disables
`PID_NS`, `USER_NS`, `CGROUP_PIDS`, `FHANDLE`, `DEVTMPFS` and `KEXEC`.
Android owns v1 CPU, cpuset, block-I/O and memory hierarchies; the observed
cgroup2 root has an empty controller list. These are concrete kernel and
ownership constraints, rather than a missing userspace package.

The Debian root reports forky/sid, but its **actually installed systemd is
257.7-1**. A distribution codename must not be substituted for that installed
version. The package database observation does not show systemd running as
PID 1. Ordinary chroot cannot create the PID namespace omitted from the
host kernel or transfer ownership of Android's cgroup hierarchies. The
[systemd container interface](https://systemd.io/CONTAINER_INTERFACE/) and
[delegation contract](https://systemd.io/CGROUP_DELEGATION/) require a coherent
container/host arrangement. Starting another manager or creating a marker
directory does not establish one.

An independently booted Linux system can instead make its own init process
PID 1, mount the chosen cgroup hierarchy and own device/service lifecycles.
That is the useful role for systemd in the Fedora/NixOS routes. It does not
implement a panel, charger, pen or GPU driver. The current chroot already
executes native ARM64 code; the improvement sought is full platform ownership
and maintainability, not elimination of an assumed CPU emulator.

The exact shipping kernel source remains a separate provenance/compliance
question, tracked in [SOURCE_PROVENANCE](SOURCE_PROVENANCE.md). A community
4.19 tree or a source tree for another Lenovo tablet is useful only with its
own origin and limitations. It is not a corresponding-source match merely
because it compiles or contains `tb371fc` in a repository name.

## Three meanings that must stay separate

| Claim | Meaning in this project | Current evidence |
| --- | --- | --- |
| Mainline-based kernel | A public upstream release plus explicit, reviewable TB371FC patches | The 6.12.114 research family is actually built; R5 has 84 qualified signed modules |
| Board supported upstream | The required board DT, bindings and drivers have been accepted into their upstream projects | Not established; the inspected upstream QCOM DTS directory has no `tb371fc` filename |
| Native distribution on this tablet | The exact kernel, firmware, initramfs and rootfs boot here and satisfy owner hardware acceptance | Not yet demonstrated |

The [upstream source inventory](evidence/2026-11-24-upstream-source-audit.json)
pins `torvalds/linux` to
`b6a9fa34ce4187cb69d3c588a4bbffc31ce5db8f`. It finds existing SM8250 SoC
support, A650/MSM, QCA6390 ath11k/Bluetooth, UFS, SDHCI, QMP USB/DP PHY,
CAMSS, Venus, MM8013, remoteproc and sound infrastructure. Thus the project
does **not** need to reimplement every driver. The
[driver roadmap](DRIVER_ROADMAP.md) separates reusable code, board integration,
missing functionality and unconfirmed hardware identities.

This upstream inventory is a bounded source review, not an assurance that
each inspected implementation exists unchanged in 6.12.114 or that it works
on this board. A donor such as upstream `sm8250-xiaomi-pipa.dts` is a comparison
source; its GPIOs, panel, memory map, calibration and firmware cannot replace
the TB371FC contract.

## Kernel lanes and release policy

Keep the existing research inputs immutable so failures remain reproducible.
Use a new branch/build prefix for each source or configuration change.

| Lane | Purpose | Next concrete output |
| --- | --- | --- |
| Reproduction: pinned 6.12.114 research5 | Preserve the already built Image, joint display/input DT, signing and module evidence | One coherent, manifested kernel/initramfs/rootfs candidate; complete its outstanding system checks |
| Maintained 6.12.y integration | Move the minimal verified patch stack forward without changing all hardware interfaces at once | Audit 6.12.114 → the selected maintained patch release, retain semantic/config differences and regressions |
| Upstream development | Remove obsolete workarounds and submit separable board/binding/driver fixes | Compare every local patch with a pinned current upstream tree; test clean replacements before dropping a patch |

On this review date [kernel.org](https://www.kernel.org/) lists 6.12.119 and
6.18.65 as longterm, 7.3.6 as stable, and 7.4-rc4 as mainline. These are
dated source candidates, not successful TB371FC builds. The repository name
does not require staying on 6.12 forever. A move to 6.18 or the current stable
series should follow an explicit patch/driver comparison and a controlled
baseline test, rather than replacing a reproducible reference with an
unqualified release-candidate kernel.

For each patch, record upstream status, source origin/license, dependency,
hardware reason and removal condition. Separate board DTS/bindings from
generic framework fixes and temporary diagnostics. Existing broad handoff
changes such as early capability handling or display/clock retention need
their own scope and explanation. A directory of historical patches is not a
single release manifest; the handoff itself says its working-tree snapshot
does not prove every change was in the installed R226 Image.

## Distribution choice

**Use the existing Fedora ARM64 work as the first desktop integration lane.**
It has the strongest complete-system execution evidence already in this
project. Use Nura/postmarketOS packaging as a parallel upstreamable device-port
lane, and preserve NixOS as a declarative system integration lane. Keep the
author's Arch Linux ARM setup as a hardware/reference baseline. This choice
does not predict battery life or graphics performance before measurement.

| Route | Existing project result at the pinned snapshot | Intended role and remaining work |
| --- | --- | --- |
| Fedora 45 AArch64 | Frozen research1 reached systemd multi-user with SELinux Enforcing in generic ARM64 QEMU; later v8 exercised FD transfer, TasksMax and BPF behavior but failed its complete gate on one AVC; first v9 image creation timed out before a VM | First normal desktop candidate. Finish the separately recorded system integration, then use the same hardware contract on the tablet |
| Nura / postmarketOS | 382-package rootfs export and BusyBox/OpenRC entry inventory; R5 compiled prerequisites for its original services | Device packaging, firmware maps and an upstream port. No TB371FC device-package or target PID 1 pass follows from the qemu-profile export |
| NixOS 26.05 AArch64 | Full 894-path system closure built; first registered-root preparation timed out during signed-cache copy | Declarative reproducibility and updates once the common boot artifacts are qualified. Still needs a registered root, activation, initrd and actual PID 1 boot |
| Arch Linux ARM | Upstream author reports installed R226 on that author's tablet | Compare known hardware behavior and recipes. It is not an owner-tablet pass or a clean-checkout installer |

The precise results and retained failures are in the
[research overview](research/2026-11-23/README.md),
[distro report](research/2026-11-23/distro-builds.md) and
[R5 report](research/2026-11-23/research5-services-kernel.md).
The [official Nura documentation](https://docs.nura.eco/) now receives the
old postmarketOS documentation URL; keep names and pinned package sources
explicit when reproducing old commands.

[Fedora's ARM installation documentation](https://fedoraproject.org/wiki/Architectures/ARM/Installation)
describes normal installation on firmware/platforms meeting its boot
requirements. It does not establish that the TB371FC ABL supplies UEFI or
that a generic ISO boots here. Similarly, the
[official NixOS ARM documentation](https://wiki.nixos.org/wiki/NixOS_on_ARM)
describes generic AArch64 builds whose usefulness depends on kernel and
platform-firmware support. A rootfs change cannot resolve a missing display
sequence, WLAN board-data selector or charger owner.

Nura's retained original entry uses BusyBox PID 1 and OpenRC. Switching that
lane to systemd just to make all experiments look alike would change the
experiment. Test each distribution's normal service path and compare the
same hardware outcomes.

## Remove the vendor-kernel boot dependency deliberately

The preferred end state is **ABL/platform firmware → reviewed Linux entry →
our initramfs → the selected distribution's native PID 1**. It need not keep
an Android 4.19 process alive after entry. Qualcomm secure firmware and device
firmware may still be necessary; a mainline kernel does not imply that those
components have been replaced or can be distributed without their licenses.

| Entry route | What is known | Required proof before selecting it |
| --- | --- | --- |
| Direct Android-format mainline Image/DT/initrd | AOSP v2 can package these components; current owner backups use v2. Historical author attempts did not establish a working direct mainline entry | Actual ABL command support and lock state; runtime placement/EL/MMU/cache/DMA state; a reachable recovery path; physical entry into the correct kernel |
| U-Boot/UEFI/EDK2 handoff | A possible way to provide a cleaner standard boot interface | An exact TB371FC port and its memory, DT, storage and display contracts. A donor or an ARM64 build is not this proof |
| Public-source 4.19.325 bridge | Already compiled with a clean HOLD-oriented rescue initramfs; downstream generic-QEMU boot stopped before PID 1 | Physical bridge boot, rescue transport and clean kexec handoff. This is neither the absent exact shipping source nor the historical R201 image |
| Existing shipping Android kernel | Stable current environment and valuable hardware reference; `CONFIG_KEXEC=n` | It cannot acquire kexec/PID namespaces by installing a command or rootfs package |

The detailed [entry audit](research/2026-11-23/entry-source-audit.md),
[reconstruction](research/2026-11-23/first-stage-reconstruction.md) and
[boot readiness](research/2026-11-23/boot-readiness.md) retain the exact
evidence. They already record owner-property/cmdline lock-state disagreement,
verified current partition copies and an unverified recovery transport.
The [ARM64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html)
and [Android image format](https://source.android.com/docs/core/architecture/bootloader/boot-image-header)
are contracts to implement, not evidence that this bootloader accepts a
particular candidate. Do not treat the author's `fastboot boot` limitation
or slot-B procedure as a fresh measurement of this unit.

The next physical gate is a verified, reachable entry/recovery transport and
one fully identified, attended boot experiment. The checked current Android
slot, owned microSD layout and current partition backups remain the authority;
the author's card-specific SD150 preset and installation commands cannot be
applied blindly. This strategy document itself runs no boot command.

## Work sequence and acceptance

1. **Close source/artifact and entry contracts.** Reuse R5 and the preserved
   system experiments, complete the exact initrd/rootfs bundle, and qualify
   entry/recovery. Keep direct mainline entry as a first-class work item so a
   reconstructed 4.19 bridge does not become a permanent dependency by accident.
2. **Establish board fundamentals.** Console, memory, clocks, regulators,
   interrupts, storage, USB recovery and safe power ownership precede a desktop
   claim. Capture one source/config/DT/firmware/modules/userspace manifest.
3. **Complete the interactive stack.** Treat A650 rendering, native dual-DSI
   scanout, display modes, touch, pen and keyboard as separate tests, then
   qualify them together. Keep the intended GPU address-space isolation.
4. **Complete peripherals and energy behavior.** Resolve radio firmware
   selection, all audio routes, charging/PD/charge-pump policy, cameras,
   sensors, accessories and sleep. A working battery icon or black screen is
   insufficient evidence of charging policy or suspend.
5. **Publish maintainable support.** Package the exact board port, shrink the
   patch delta through upstream review, and run the existing whole-device
   functional/performance/latency/energy/stability contract. Add newly confirmed
   hardware functions to the inventory and acceptance scope before declaring
   the tablet complete.

One result must identify whether it is source analysis, a host build, generic
QEMU execution, an Android observation, or native Linux on this owner tablet.
Build/test counts from the first four classes never increase the last class's
pass count. The existing acceptance ledger remains the single authority for
the owner's “all hardware in its best working state” goal.

## Cross-repository division of work

| Repository | Owned output | Shared input/output contract |
| --- | --- | --- |
| [TB371FC-6.12](https://github.com/cyjin-yl/TB371FC-6.12/tree/docs/mainline-strategy-20261124) | Linux DT, bindings, drivers, distro packaging and physical acceptance | Canonical owner inventory, source provenance, firmware hashes/protocol observations and tested hardware vectors |
| [qemu-tb371fc](https://github.com/cyjin-yl/qemu-tb371fc/blob/docs/mainline-hardware-contract-20261124/tb371fc/docs/cross-project-hardware-contract.md) | Explicit board/device models and deterministic boot/protocol regression | Consume measured contracts; record model simplifications. Passing emulated IO is not physical fidelity or a Linux driver pass |
| [UniXNU-tb371fc](https://github.com/cyjin-yl/UniXNU-tb371fc/blob/docs/mainline-hardware-contract-20261124/docs/CROSS_PROJECT_HARDWARE.md) | Route-A architecture/ABI qualification and XNU-specific platform/driver work | Reuse hardware facts and tests, while implementing XNU/IOKit interfaces separately |

Linux drivers are not directly loadable macOS kernel extensions. The macOS 27
track must separately establish its exact source/binary provenance, ISA/ABI,
boot, firmware and driver requirements; a Linux or QEMU result supplies only
the portions actually measured. Keep firmware bytes, device identifiers,
keys and user content out of public documentation. Preserve the licenses and
provenance of any code used across projects.
