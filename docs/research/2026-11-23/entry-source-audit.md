# First-stage recovery: source and dependency audit

Date: 2026-11-23, Asia/Shanghai. Evidence class: **source clue**. Audited project
HEAD: `d157b92721fbeeab823f56a677b3593babf3afe6`, with the current research
evidence alongside it. This audit reads scripts, existing device evidence and
public repository metadata; it
does not build, package, load or boot a first stage.

**The owner backups provide a verified recovery layout and owner-specific
inputs, but the current checkout does not contain a complete reproducible
R226 first-stage build.** R226's selector consumes an already built R201
recovery. The underlying 4.19 build refers to missing patches, an unpinned
local source tree/configuration and private intermediate ramdisks. Replacing
the old payload hashes with research2 hashes would leave these gaps intact.

The [audit metadata](evidence/entry-source-audit.json) records the inspected
file hashes, missing paths and unresolved pins. Missing means absent from this
worktree and its recorded Git HEAD; it does not assert that no copy exists
anywhere on the Internet or in the author's private workspace.

## What the existing owner material establishes

[Boot readiness](boot-readiness.md) records eight verified local and off-device
current-partition copies, plus a bounded inspection of the four boot/recovery
images. They use header v2, 4096-byte pages and gzip ramdisks. The recovery
images contain both a DTB component and a recovery-DTBO component. These bytes
can supply the selected slot's wrapper/layout reference and board-description
inputs to a new, separately identified build. They are not source for a
newly configured kernel or proof of a working restore.

The running Android kernel is `4.19.157-perf+`, with `CONFIG_KEXEC=n`,
`CONFIG_MODULE_SIG_FORCE=y`, `CONFIG_MODVERSIONS=y` and
`CONFIG_USB_CONFIGFS_ACM=n`. A new ramdisk or a kexec executable cannot add the
missing kernel syscall. Historical `.ko` files cannot be assumed loadable.
The configuration of each backed-up recovery kernel has not been separately
extracted by this audit; equal release strings do not establish equal config.
In particular, A/B kernel component hashes differ despite equal releases.

An exact slot detail matters: the stock-input hash hardcoded in
[build-diagnostic-recovery.sh](../../../scripts/build-diagnostic-recovery.sh),
`94649360140db672e861729927011984e9714459b4e19c9aab02b7ab79466668`,
matches this owner's **recovery_a** copy. The current recovery_b hash is
`2c62c4c7c85ed751f3ca2273191fdddb6a20c62504f0ccb5a45456c08c6f5a72`.
The historical filename ending in `recovery_b.bin` cannot select the owner's
slot, or prove which slot is appropriate for a future entry experiment.

## The published dependency chain

| Stage | Public recipe/content | Required input still outside this checkout |
| --- | --- | --- |
| R226 recovery v3 | [Selector packager](../../../experimental/r226/scripts/package-r226-autoboot-recovery.py) | R201 recovery image with SHA-256 `800307febff4f2e8387e1a73d9759e03375db1333c6e67537062ea22f0093f68`, its unpacked components and the pinned R226 v2 payload files |
| Earlier R191 selector | [R191 packager](../../../scripts/package-r191-autoboot-recovery.py) and [autoboot helper](../../../scripts/r191-recovery/tb371fc-autoboot-612) | R121 recovery with SHA-256 `976b4820c956f011da6b21ef20884c9d344914afcfb1b7836021ca5c69f047e6` |
| R121 / R120 | [R121](../../../scripts/package-linux-6.12-r121-panic-gate.py) and [R120](../../../scripts/package-linux-6.12-r120-handoff.py) repackagers | R120 image; before that, independently pinned R118 and R101 recovery images |
| V56.6 first-stage kernel | [Watchdog wrapper](../../../scripts/build-v56-6-watchdog-kexec-kernel.sh), then [V56.1 common builder](../../../scripts/build-v56-1-community-kernel.sh) | V56.5 source/output trees; earlier community source, base config, WLAN donor sources and the absent vendor patch directory |
| V56.x ramdisk/package | [Common packager](../../../scripts/build-v56-1-community-simplefb-qca6390-kde.sh) | V55 recovery/ramdisk, an exact static kexec binary, board blobs, binaries and helper source files |
| V55 ramdisk | [V55 packager](../../../scripts/build-v55-community-simplefb-arch-loopback-ssh.sh) | V23 ramdisk, V49 kernel, V50 modified DTB bundle and V47 AVDD-modified recovery DTBO |

R226 changes selection and hash guards in the inherited ramdisk. Its code
explicitly preserves the R201 kernel, DTB, recovery DTBO and command line.
It selects R226 only with `ENABLE` and three exact payload hashes; otherwise
it selects the preserved R201 directory. No R201 recovery construction recipe
or its full input manifest was found in this checkout. The R191/R121 chain
shows earlier dependencies, but does not prove that R201 is byte-identical to
R191 or reconstruct the missing R201 build.

The R226 packager also tests its generated selector against private v2 files.
Those checks are useful for that exact historical set, but cannot authenticate
a new research2 Image, DT or root-loading initramfs. Neither the generic QEMU
probe initramfs nor a qemu-profile distro boot directory fulfils that contract.

## Missing 4.19 source/configuration inputs

The V56.1 common builder clones a local branch named `tb371fc-desktop-linux`
from `/root/tb371fc-desktop-working-kernel`. It copies that tree's
`scripts/Kbuild.include`, imports three WLAN source directories from a second
local tree, and seeds the output from `/root/tb371fc-desktop-working-out-v49/.config`
or a later V56 output. The recipe records the source HEAD only when it runs;
it does not pin that HEAD in this checkout. The inherited Kbuild modification,
complete resolved 4.19 configuration and donor revisions are not supplied.

The complete `vendor-kernel/` directory is absent. These nine inputs are
referenced by the V56.6 chain and are missing:

```text
0001-cnss2-add-no-ssr-diagnostic-mode.patch
0002-cnss2-add-single-qmi-client-diagnostic-mode.patch
0015-arm64-avoid-legacy-cpu-soft-restart-kexec-name-clash.patch
0022-community-import-qcacld-build-glue.patch
0023-community-backport-qcacld-netlink-time-helpers.patch
0024-community-drm-track-userspace-test-only.patch
0025-msm-drm-preserve-kms-state-during-kexec.patch
0026-cpu-hotplug-ignore-suspend-wakeup-during-kexec.patch
0027-msm-watchdog-local-kexec-shutdown.patch
```

The builder looks for markers such as `cpu_soft_restart_kexec`, a KMS-state
preservation message and a kexec CPU-hotplug exception. A marker and patch
filename describe the intended change; they cannot establish the missing
patch's exact contents, compatibility or completeness.

[The older bridge record](../../MAINLINE_STATUS.md) identifies
`tem423/android_kernel_lenovo_tb371fc` commit
`9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1` and
`vendor/tb371fc_defconfig` for a **4.19.325** bridge.
[build-v29-kexec-bridge.sh](../../../scripts/build-v29-kexec-bridge.sh) also
names that commit, but consumes an older local config and missing vendor
patches. A public GitHub API read confirmed that commit and tree
`0dab36615babaf7b31c211589639a738f8196cf6`, its Makefile version 4.19.325,
and its actual `arch/arm64/configs/vendor/tb371fc_defconfig` bytes. The config
SHA-256 is `87185808d2a9a4cf2e8b7c917b6f60fb1c85d064a7903cf7bfeff35c6f69d2f0`;
it disables **KEXEC, ACM and DEVTMPFS** while enabling NCM and module signing.
This is an accurately identified candidate for further source review, not
the missing V56.6 **4.19.157** source/config or a ready first stage. Its full
tree was not checked out or built in this audit.

### Public branches and path history checked

Unauthenticated, read-only GitHub API queries at `2026-11-22T23:12Z` returned
the following complete branch/tag inventory for
`oproskyrin/TB371FC-6.12`, without pagination:

| Public ref | Commit |
| --- | --- |
| Default `main` | `d157b92721fbeeab823f56a677b3593babf3afe6` |
| `codex/community-handoff-r241-20261105` | `d157b92721fbeeab823f56a677b3593babf3afe6` |
| `codex/r226-sd150-usb3` | `153824c8e613b1b1677d991bb4e07562a4718b60` |
| Tags | None returned |

The API commit-history query for path `vendor-kernel` returned no entries on
either distinct reachable branch head. The R226 branch's complete recursive
tree had 1349 entries and `truncated=false`; the same vendor patch directory,
diagnostics source directory, R201 recovery recipe and resolved 4.19 config
were absent. Thus no alternative source-complete first-stage version was found
in the enumerated public refs and those path-history queries. This does not
rule out unreferenced commits, renamed paths, another repository or private
material. The selected API response fields are retained in the audit metadata.

## Tools, ABI and a clean ramdisk

The first-stage recipe explicitly uses **Snapdragon Clang 10.0.7**, with
`CC=clang`, `CLANG_TRIPLE=aarch64-linux-gnu-` and
`CROSS_COMPILE=aarch64-linux-android-`. The historical bridge notes identify
Android 11 GCC 4.9 cross tools. Archive/source checksums for those toolchains
are not pinned here. R226's second-stage LLVM 18 and the new research builds'
LLVM 19 are different build environments; changing the compiler is a new
qualification, not reproduction of the old bridge.

The separate tem423 `workflows` branch was observed at
`f6562e36de1601442314a5675fa3ad8619b80149`. Its public `test.yml` blob
`6003d0e1a9a90e0122b1771e8549a66ac94a4f89` names the
[Snapdragon 10.0.7 compiler repository](https://github.com/sticpaper/Snapdragon-LLVM-ARM-Compiler-10.0.7-for-Android-NDK),
but selects compiler branch `main`, build action `tem423/kernel_build_action@main`
and kernel branch `测试`. It is a tool/source lead with mutable dependencies,
not an immutable recipe for commit `9d8abeb…` or V56.6.

The packager requires a static AArch64 kexec binary with SHA-256
`6c3c706315389d30638cc5fbb5482c069d8f411b6bb0ae298a8b25db319ae77d`.
Historical notes call it `kexec-tools 2.0.32.git`, but supply no exact source
revision/configure recipe for that binary. A clean replacement needs a chosen,
pinned source and toolchain, validated ARM64 Image/DT/initrd loading through
the intended legacy `kexec_load` path, and a new manifest. The filename or
version text cannot substitute for that build evidence.

A new clean ramdisk should be assembled from individually identified sources
and packages: static BusyBox with the required applets, an explicit PID 1,
the root/payload loader, kexec tools, selected recovery transport and the
necessary drivers/firmware. Fresh private authentication material belongs to
the owner. The old V55 ramdisk is not a credential-free source recipe, and
the current scripts additionally refer to absent `diagnostics/framebuffer-pattern.c`
and `diagnostics/reboot-bootloader-userspace.c`. A referenced
`bin/tb371fc-development-init-runtime` is also absent; a related public runtime
exists under `rootfs/development-overlay/usr/local/sbin/`, whose equivalence
to the former private file is not established.

If the new bridge uses modules, build and sign them with that bridge's exact
resolved config, symbol CRCs, `Module.symvers` and trusted certificate. Generate
and keep the corresponding private key locally. A historical `.ko` signed
for another build is not repaired by changing its release string. Its ABI is
also separate from every 6.12 module in research1/research2.

## DT, handoff and recovery transport contracts

The first-stage downstream DT bundle and recovery DTBO describe the vendor
kernel's bindings. Historical V49/V50 scripts modify framebuffer reservations,
clock references and AVDD behavior; they do not simply reuse an unmodified
stock DT. A clean recipe must expose each transformation against the owner's
selected blob and verify all bundle entries/overlay matches. Do not put the
upstream 6.12 board DT into a 4.19 wrapper merely because both describe TB371FC.

The second-stage DT is a separate input. Its final root compatible must select
the intended `lenovo,tb371fc` early allocator branch. Its memory reservations,
Image effective size, initramfs placement and DMA ownership must match the
handoff; a generic QEMU boot checks none of the vendor handoff behavior.

The public [r38 execute helper](../../../initramfs/execute-linux-6.12-r38)
requires the first stage's watchdog control, syncs storage and attempts to
unbind CNSS before `kexec -e`. Its CNSS unbind is best-effort and continues on
failure. That historical behavior is not proof that this owner's old DMA,
remote processors, USB or display engines are quiescent. The missing watchdog,
CPU-hotplug and DRM shutdown patches must be recovered/reimplemented and
reviewed with the selected source, followed by physical handoff validation.

[setup-usb-acm-v56](../../../initramfs/setup-usb-acm-v56) creates a configfs
`acm.GS0` function and binds an actual UDC. The first-stage kernel therefore
needs its gadget/configfs/ACM and board USB/PHY dependencies built in or
available as matching initramfs modules. The current stock `ACM=n` cannot
fulfil this script. NCM is a possible separately implemented transport, but
its stock Kconfig setting alone proves neither link configuration nor an
authenticated recovery session.

The historical authenticated SSH console also depends on an Arch loop-root
and serial bridge. [boot-arch-development-rootfs](../../../initramfs/boot-arch-development-rootfs)
assumes exFAT `mmcblk0p1` and a 6–64 GiB ext4 image file with project markers;
it mounts these read/write. This is not a generic rescue shell guaranteed to
survive missing SD contents. A new first stage needs a usable console before
root/payload failure, cancellation/hold behavior and a tested return route.
The owner's actual three-partition card must be mapped explicitly, without
applying the author's two-partition or card-specific layout.

## What a reproducible owner first stage still needs

1. **A closed source recipe:** a selected public 4.19 commit, every local
   patch/donor revision, the complete config and immutable tool inputs. Missing
   patches can be recovered or newly implemented, but new code must be reviewed
   as a new bridge rather than claimed as the author's recovered build.
2. **An independently assembled ramdisk and DT transformation recipe:** no
   dependence on R201/V55 private binaries; explicit transport, loader, module,
   firmware and credential boundaries; paths and hashes belonging to the new
   build. A small bridge is an entry component, not whole-device acceptance.
3. **An owner-specific image manifest:** selected stock slot/hash, v2 layout,
   exact kernel/ramdisk/DT/recovery-DTBO hashes, config/toolchain/ABI identity,
   final second-stage payload and an actual root-loading initramfs. Preserve
   effective ARM64 image memory size separately from stored byte length.
4. **Offline qualification followed by actual entry/recovery evidence:**
   compile and inspect the new outputs, then independently unpack and compare
   all components and header limits. The existing packager adds an AVB hash
   footer with `algorithm NONE`; its `verify_image` check does not establish
   OEM signing, bootloader acceptance or rollback-index compatibility. The
   actual bootloader/transport and recovery behavior remain unresolved by
   the contradictory Android lock-state observations.

These are technical dependencies and validation boundaries. This source audit
does not add an approval step or change the existing session authorization.
No first-stage artifact is declared ready, and no owner Linux or restore pass
is recorded.
