# Reproducible build routes: handoff kernel, Nura/postmarketOS, Fedora and NixOS

Research date: 2026-11-23, Asia/Shanghai. Repository source baseline:
`d157b92721fbeeab823f56a677b3593babf3afe6`.

The immediately useful deliverables are a newly built ARM64 kernel/module
baseline and separately identified ARM64 userspace trees. A distribution's
generic image does not supply this tablet's recovery/kexec entry conditions,
DT, external drivers, signed firmware, display initialization or charger
ownership. This note records source verification and actual container experiments,
with each result limited to the source/configuration and execution environment
that was tested. No new physical-tablet boot or device acceptance is claimed.

## Observed build results and working choice

| Route | Actually demonstrated in this workspace | Remaining entry/integration boundary |
| --- | --- | --- |
| Shared kernel | Both Linux 6.12.114 research1 and research2-display Image/DT/module sets compiled and reached ARM64 userspace on generic QEMU; each has 83 matching modules | Base research1 DT disables panel/touch; research2 enables its native display path but still disables touch; no tablet entry or hardware pass |
| Fedora 45 ARM64 | Signed OCI source verified; 160 packages installed with normal RPM scriptlets; dependency/database/selected-file checks passed; actual EGL pixel readback, Weston/Wayland clients and software Vulkan presentation passed under QEMU user execution | Hardware DRM and A650 unavailable in the builder; this is an assembled graphical userspace, not a fully booted tablet system |
| NixOS 26.05 ARM64 | Configuration and system derivation evaluated; ARM64 hello executed; selected 386-path userspace closure realized; ARM64 Freedreno/Turnip files present | Full system closure and external kernel/DT/initramfs/firmware integration remain incomplete |
| Nura / postmarketOS | Native ARM64 pmbootstrap installed 382 target packages, generated qemu-profile boot files and exported a 307,393,454-byte rootfs archive; selected ARM64 tools and graphics-library ELF checks passed | The exported target rootfs has not booted; 371/382 package archives retained, so offline cache is incomplete; no tested TB371FC device package |

The exact experiment reports are [kernel-build.md](kernel-build.md),
[research2-display-build.md](research2-display-build.md),
[fedora-build.md](fedora-build.md), [nura-build.md](nura-build.md) and
the [NixOS README](../../../distros/nixos/README.md). They retain failures as
well as successful retries. The kernel work is a new Debian/LLVM 19 research
recipe; the older Ubuntu/LLVM 18 reconstruction discussion below describes
the handoff boundary rather than the environment actually used here.

Based on these observed results, **Fedora is the leading first desktop-userspace
candidate**: its real ARM64 package transactions and graphical software path
have the broadest execution evidence in this experiment. This is an engineering
choice for the next integration test, not a claim of better tablet battery life
or accelerated performance. Nura remains useful for packaging and maintaining
the device port; NixOS remains useful for declaring a fixed userspace once the
common kernel/boot/firmware contract is reliable. None of the three can repair
native DSI, GPU address-space switching, charger ownership or suspend merely
by selecting a different root filesystem.

The common [entry-source audit](entry-source-audit.md) identifies nine absent
vendor patches and private intermediate recovery/ramdisk dependencies in the
historical first-stage chain. The owner's current Android kernel has no kexec
support. [Verified current-partition backups](boot-readiness.md) now exist on
both devices; a usable owner-specific first stage and tested recovery transport
still need to be supplied and qualified for every distro route.

## Fixed sources and intended outputs

| Component | Version/revision verified here | Purpose |
| --- | --- | --- |
| Existing kernel handoff | Linux 6.12.114 plus the exported 19-file diff | Reconstruct and compile the historical diagnostic source baseline |
| Official stable kernel tag | `v6.12.114`, commit `85d82e0d7c2dfd3e75d34f35b7ebbf41f45c9c4e` | Public base for that diff |
| Nura pmaports | `d7e3e81fd579f01d4742157257897e2b07fade5c`, `main` at inspection | Device recipes and a maintained SM8250 tablet donor |
| pmbootstrap | `3.12.1`, commit `e0dfe2cda7f3a0b70cdcc96f3060100839322aa4` | ARM64 APK building/rootfs assembly tooling |
| Nura Xiaomi Pad 6 donor | `device-xiaomi-pipa 11-r0`, `linux-xiaomi-pipa 7.2.4-r0` | Compare newer DSI/DSC/Novatek/charger work; not a TB371FC image |
| Fedora | 45, release compose `45-1.4`, aarch64 | Fixed initial userspace/OCI source |
| Fedora graphics packages | Mesa `26.2.7-1.fc45`, aarch64 | Available Freedreno/Turnip userspace, subject to a working kernel/firmware |
| NixOS/nixpkgs | 26.05, `94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd` | Declarative ARM64 userspace and cross-build probes |

Commit and package pins do not freeze every later repository dependency.
Retain downloaded source/package checksums, lock files, package manifests and
toolchain versions. A successful compilation, a successful ARM program under
QEMU, and a successful tablet hardware test are different results.

## 1. What the 6.12.114 handoff actually contains

All **17 entries** in
[SOURCE_SHA256SUMS](../../../experimental/community-handoff/SOURCE_SHA256SUMS)
passed verification from the handoff directory:

```sh
cd experimental/community-handoff
sha256sum -c SOURCE_SHA256SUMS
```

The [handoff](../../../experimental/community-handoff/README.md) contains the
19-file working-tree patch, final exported `.config`, PS5169 source and matched
R241 TCPM/PMIC module sources. The patch adds **no new files**. In particular,
it does not add board DT sources, the Novatek input source, panel driver,
dual-backlight driver or their build-system integration.

The exported `BASE_COMMIT` is `cbd34a5b44674ba9c3f617da74c38a197741832d`,
identified by the handoff as the author's local base. The public stable
`v6.12.114` annotated tag object is
`94632db1ce2426a1018af806db3bd3d6f1d04e46`, resolving to commit
`85d82e0d7c2dfd3e75d34f35b7ebbf41f45c9c4e`. Do not require another contributor
to fetch the local base object as if it were the public tag.

The diff's applicability was checked without modifying a kernel tree: all
19 original files were retrieved from the stable maintainer's
[`v6.12.114` tree](https://github.com/gregkh/linux/tree/v6.12.114). Every Git
blob SHA-1 matched the diff's old-object prefix. Applying **49 hunks in memory**
matched each context/deleted line exactly, and every resulting file matched
the diff's new-object SHA-1 prefix. This establishes that the textual delta
matches that vanilla base; it is not a compile or boot result.

The official [kernel.org checksum list](https://cdn.kernel.org/pub/linux/kernel/v6.x/sha256sums.asc)
lists this source archive:

```text
https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.114.tar.xz
SHA256: 7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3
```

### A minimal compile experiment

Use a dedicated Ubuntu 24.04 build container. The historical configuration
records Ubuntu clang **18.1.3**. Installing the distribution's current LLVM 18
packages preserves the compiler major but does not recreate the original
package build exactly; record `clang-18 --version` and installed package
versions. A plain compile needs no tablet, GPU, block device, loop device,
privileged container or ARM CPU emulation. An x86_64 compiler can emit ARM64
code using [LLVM's supported cross-build mode](https://docs.kernel.org/kbuild/llvm.html).

Container package preparation:

```sh
apt-get update
apt-get install --no-install-recommends \
  build-essential clang-18 lld-18 llvm-18 bc bison flex \
  libssl-dev libelf-dev dwarves cpio rsync kmod device-tree-compiler \
  python3 patchutils xz-utils zstd curl ca-certificates git
```

Example source/build commands, after mounting the project at `/work/project`:

```sh
TB_PROJECT=/work/project
TB_BUILD=/work/tb371fc-build
TB_SOURCE="$TB_BUILD/linux-6.12.114"
TB_OUT="$TB_BUILD/kernel-out"
mkdir -p "$TB_BUILD" "$TB_OUT"
cd "$TB_BUILD"
curl --fail --location --output linux-6.12.114.tar.xz \
  https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.114.tar.xz
printf '%s  %s\n' \
  7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3 \
  linux-6.12.114.tar.xz | sha256sum -c -
tar -xf linux-6.12.114.tar.xz
git -C "$TB_SOURCE" apply --check \
  "$TB_PROJECT/experimental/community-handoff/reference/kernel-6.12.114/working-tree.patch"
git -C "$TB_SOURCE" apply \
  "$TB_PROJECT/experimental/community-handoff/reference/kernel-6.12.114/working-tree.patch"
cp "$TB_PROJECT/experimental/community-handoff/reference/kernel-6.12.114/config" \
  "$TB_OUT/.config"
cp "$TB_OUT/.config" "$TB_OUT/config.before-olddefconfig"
"$TB_SOURCE/scripts/config" --file "$TB_OUT/.config" \
  --set-str LOCALVERSION '-tb371fc-research-20261123' --disable LOCALVERSION_AUTO
make -C "$TB_SOURCE" O="$TB_OUT" ARCH=arm64 LLVM=-18 olddefconfig
make -C "$TB_SOURCE" O="$TB_OUT" ARCH=arm64 LLVM=-18 -j4 Image modules
```

Keep the configuration delta. The new release name prevents accidental
association with the old `6.12.114-tb371fc-r199+` module collection. The exported
configuration enables early/late framebuffer markers and a post-MMU reset
checkpoint; this is a diagnostic source experiment, not a proposed production
boot profile. The configuration also enables module versioning and module
signing. Retain the actual build's symbol CRCs and signing policy rather than
reusing old `.ko` files by filename or release string.

Only after a complete build has produced `Module.symvers` should the matched
R241 source be built in a new work directory. Linux explicitly documents that
[`modules_prepare` does not generate `Module.symvers`](https://docs.kernel.org/kbuild/modules.html)
for a `CONFIG_MODVERSIONS=y` build.

```sh
TB_R241="$TB_BUILD/r241-modules"
mkdir -p "$TB_R241"
cp "$TB_PROJECT/experimental/community-handoff/reference/r241/"* "$TB_R241/"
test -s "$TB_OUT/Module.symvers"
make -C "$TB_SOURCE" O="$TB_OUT" ARCH=arm64 LLVM=-18 \
  M="$TB_R241" W=1 modules
```

### What still separates that build from R226

| Missing assembly contract | Existing material to use | Remaining work |
| --- | --- | --- |
| Exact board DTB | [board DTS](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts), test DTS variants and historical transforms | Select one topology/provider/splash/SD/USB profile; the patch itself contains no board DTS |
| Panel/backlight modules | [6.12 backports](../../../mainline-port/backports/linux-6.12/), [R180 builder](../../../scripts/build-r180-native-kernel.sh) | Reconcile separate driver copies, `keep_splash`, bridge/PHY prerequisites and symbol dependencies |
| Novatek input module | [patch 0002](../../../mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch), [R148 build adapter](../../../scripts/build-r148-touch-module.sh) | Extract/build the exact driver against the new ABI, then review changes separately |
| USB3 and SD150 helpers | [R226 sources](../../../experimental/r226/README.md), R209 reference, R224/R225 sources | Rebuild helpers and select board DT; do not remove the tested-card guard to claim generic SD150 support |
| Initramfs and rootfs services | R226 packaging script and service templates | Replace hard-coded author paths and reconstruct the intended first-stage/root handoff without private provisioned archives |
| Firmware and boot entry | [firmware record](../../FIRMWARE.md), existing recovery/kexec notes | Preserve exact board-specific paths, provenance, ownership and first-stage entry conditions |

The [R226 package script](../../../experimental/r226/scripts/package-r226-combined.sh)
expects pre-existing R224 kernel/initrd, R207 board DT, R209 modules and R225
touch-PM module. Its initrd transformation expects an already populated
`bin/boot-arch-r129-base`. These are concrete missing inputs for a clean
checkout, even though much of their source history is present. The handoff
snapshot includes later diagnostics and does not prove which changes were in
R226's installed Image. A new build should have its own manifest and acceptance
record, not claim binary equivalence to R226.

## 2. Nura / postmarketOS

The project [announced its rename to Nura on 2026-09-27](https://nura.eco/blog/2026/09/27/nura-rename/).
Its official [source-code page](https://nura.eco/source-code/) now links:

```text
https://gitlab.nura.eco/nura/pmaports.git
https://gitlab.nura.eco/nura/pmbootstrap.git
```

The old domains redirect, and some documentation still uses postmarketOS names.
The GitLab web UI returned an Anubis challenge in this review, while public raw
files and repository API requests succeeded. This is an access observation,
not a reason to change authentication or bypass controls.

An official package-index search for `*tb371fc*` returned no matching packages.
At the pinned pmaports revision, `device-lenovo-tb371fc` was absent from
`device/main`, `community`, `testing`, `archived` and `downstream`. This supports
planning a new local device package; it is not a claim that no private or
unmerged port exists anywhere.

The official [Xiaomi Pad 6 package](https://pkgs.nura.eco/package/main/postmarketos/aarch64/device-xiaomi-pipa)
is `11-r0`, with CSOT/Tianma kernel-selection subpackages. Its
[`linux-xiaomi-pipa` package](https://pkgs.nura.eco/package/main/postmarketos/aarch64/linux-xiaomi-pipa)
is `7.2.4-r0`. The pinned
[kernel APKBUILD](https://gitlab.nura.eco/nura/pmaports/-/blob/d7e3e81fd579f01d4742157257897e2b07fade5c/device/testing/linux-xiaomi-pipa/APKBUILD)
uses the kernel.org 7.2.4 source archive, LLVM and `pmb:cross-native`. Its patch
list includes DSI0 command synchronization, DSC slices per packet, NT36532
panels, Novatek input and a PM8150B float-voltage correction. These are specific
donor comparisons for the gaps in this project. Xiaomi's panel tables,
Nuvolta charging, firmware, keyboard protocol and DT are not Lenovo's hardware
contract.

The pinned pmbootstrap [project metadata](https://gitlab.nura.eco/nura/pmbootstrap/-/blob/e0dfe2cda7f3a0b70cdcc96f3060100839322aa4/pyproject.toml)
requires Python 3.10 or newer; its source reports version 3.12.1. Install Python,
OpenSSL and Git in the build container, then pin both source checkouts. Do not
run `pmbootstrap pull` midway through a reproducibility experiment.

```sh
git clone https://gitlab.nura.eco/nura/pmbootstrap.git pmbootstrap
git -C pmbootstrap checkout --detach e0dfe2cda7f3a0b70cdcc96f3060100839322aa4
git clone https://gitlab.nura.eco/nura/pmaports.git pmaports
git -C pmaports checkout --detach d7e3e81fd579f01d4742157257897e2b07fade5c
python3 pmbootstrap/pmbootstrap.py --version
python3 pmbootstrap/pmbootstrap.py -p "$PWD/pmaports" -w "$PWD/pmwork" init
```

For an initial donor/toolchain experiment, selecting `xiaomi-pipa` configures
the known package dependency graph. Build its kernel without deploying it:

```sh
python3 pmbootstrap/pmbootstrap.py -p "$PWD/pmaports" -w "$PWD/pmwork" \
  checksum --verify linux-xiaomi-pipa
python3 pmbootstrap/pmbootstrap.py -p "$PWD/pmaports" -w "$PWD/pmwork" \
  build --arch=aarch64 linux-xiaomi-pipa
```

That output must remain labelled Xiaomi donor. The real TB371FC route needs
local `linux-lenovo-tb371fc` and `device-lenovo-tb371fc` packages using the chosen
kernel/DT/module inputs, exact firmware dependencies and an explicit external
boot handoff. Once those exist and evaluate correctly, `pmbootstrap install`
and `pmbootstrap export` can create local artifacts. The official
[usage documentation](https://docs.nura.eco/pmbootstrap/main/usage.html)
distinguishes local export from flashing. No flasher action is part of this
build plan.

pmbootstrap uses chroots and bind mounts. Kernel `pmb:cross-native` compilation
uses native tools; it is documented separately from QEMU-based foreign
userspace builds in the [cross-compilation guide](https://docs.nura.eco/pmbootstrap/main/cross_compiling.html).
An unprivileged LXC container must actually permit the required mount/chroot
operations; installing Docker or passing a CPU architecture flag does not
create those capabilities. Use the authorized build container's observed
permissions. Image creation may additionally require loop devices; package
compilation and an exported tree should be attempted first. Do not expose
physical tablet disks or USB merely to compile a package.

## 3. Fedora 45 ARM64 userspace

The official [download page](https://fedoraproject.org/workstation/download/)
identifies Fedora 45, released 2026-11-03. The
[miscellaneous downloads](https://fedoraproject.org/misc/) provide both generic
AArch64 disk images and a smaller OCI base. For a fixed initial filesystem,
the latter avoids needing a UEFI boot or an ARM CPU just to extract packages:

```text
https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Container/aarch64/images/Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar.xz
SHA256: bc6c3b3e132e3ed5eff398112d16fcdca13dc8abd63550f8aad40e882b9617b6
Size: 68,993,700 bytes
```

The signed
[aarch64 compose CHECKSUM](https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Container/aarch64/images/Fedora-Container-45-1.4-aarch64-CHECKSUM)
was read here. The large archive was not downloaded by this source review,
and signature verification is not claimed. The builder should verify the
CHECKSUM with Fedora's published keys, then check the archive. The official
container registry is `quay.io/fedora/fedora`; pin an inspected manifest digest
if using the registry instead of the fixed compose archive.

After verification, `skopeo` and `umoci` can unpack the OCI filesystem without
executing ARM programs:

```sh
xz --decompress --keep Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar.xz
skopeo copy \
  oci-archive:Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar \
  oci:fedora45-oci:base
umoci unpack --rootless --image fedora45-oci:base fedora45-bundle
```

This is an inspection/staging tree. Rootless unpacking affects ownership and
some metadata handling; a final rootfs export must preserve the intended UIDs,
permissions and xattrs. The [umoci workflow](https://umo.ci/quick-start/) is an
OCI operation, not an installation of a tablet bootloader.

### Graphics and firmware availability

The Fedora package index reports Mesa `26.2.7-1.fc45`. To avoid inferring ARM64
contents from its x86_64 presentation, this review read the RPM headers of the
two **aarch64** packages from the official updates repository using HTTP Range:

| Official aarch64 package | Relevant header file entries |
| --- | --- |
| `mesa-vulkan-drivers-26.2.7-1.fc45.aarch64.rpm` | `libvulkan_freedreno.so`, `freedreno_icd.aarch64.json` |
| `mesa-dri-drivers-26.2.7-1.fc45.aarch64.rpm` | `msm_dri.so`, plus other DRI drivers |

The package URLs are under
[`updates/45/Everything/aarch64/Packages/m/`](https://dl.fedoraproject.org/pub/fedora/linux/updates/45/Everything/aarch64/Packages/m/).
Header inspection establishes advertised package contents; it is not a full
RPM download/signature check or a GPU test. [Mesa's own documentation](https://docs.mesa3d.org/drivers/freedreno.html)
identifies Turnip as the Adreno Vulkan driver. The normal Fedora packages are
the first userspace candidate; a custom Mesa build is not initially required.

Include `mesa-dri-drivers`, `mesa-vulkan-drivers`, `mesa-libEGL`, `mesa-libgbm`,
`vulkan-loader`, `vulkan-tools` and `libdrm` in the target package inventory.
Fedora separately packages [qcom-firmware](https://packages.fedoraproject.org/pkgs/linux-firmware/qcom-firmware/)
for Qualcomm SoC components and [atheros-firmware](https://packages.fedoraproject.org/pkgs/linux-firmware/atheros-firmware/)
for Wi-Fi/Bluetooth. Those package names do not prove that every Lenovo-specific
signed GPU/remoteproc image, QCA6390 board mapping or Novatek firmware lookup is
satisfied. Check exact requested filenames and provenance against the chosen
kernel/DT before accepting hardware support.

On a Fedora 45 build environment, first query the **aarch64** repository and
save the resolved NEVRAs and RPM checksums. A later installroot transaction can
use an existing ARM64 execution environment:

```sh
dnf5 --forcearch=aarch64 --releasever=45 repoquery \
  mesa-dri-drivers mesa-vulkan-drivers mesa-libEGL mesa-libgbm \
  vulkan-loader vulkan-tools libdrm qcom-firmware atheros-firmware
```

[`dnf5 --installroot`](https://dnf5.readthedocs.io/en/latest/misc/installroot.7.html)
requires explicit repository/release handling for an empty root; the current
interface uses `--use-host-config` when choosing the build environment's repo
configuration. `--forcearch=aarch64` selects target packages but does **not**
emulate ARM scriptlets. Full configuration needs native AArch64 execution or
deliberately configured QEMU/binfmt. Skipping all scriptlets is not equivalent
to a configured Fedora installation. A valid generic rootfs still needs the
project's kernel, modules, firmware and external first-stage integration.

## 4. NixOS 26.05

The official [NixOS download page](https://nixos.org/download/) and
[26.05 announcement](https://nixos.org/blog/announcements/2026/nixos-2605/)
identify 26.05 as the current stable series in this review. The channel's
`git-revision` resolved to `94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd`, also the
observed `nixos-26.05` branch head. The fixed release directory is
[`nixos-26.05.14979.94c3211b0ee8`](https://releases.nixos.org/nixos/26.05/nixos-26.05.14979.94c3211b0ee8/).
Official AArch64 images and cached packages exist. The
[ARM support documentation](https://wiki.nixos.org/wiki/NixOS_on_ARM) makes
board support dependent on the kernel and platform firmware.

The complete `NixOS/nixos-hardware` tree at
`33475966110df258f52d05ec4d4cd6394637cbb9` had no `tb371fc`, `pipa`, `sm8250`
or `nabu` path. A separate Mobile NixOS project exists, but no merged
TB371FC-specific support was established by this review. Generic AArch64
support and an unverified third-party port are not substitutes for that evidence.

An initial configuration is provided in
[`distros/nixos`](../../../distros/nixos/README.md). It fixes nixpkgs to the
revision above, selects ARM64 Mesa/Wayland/network/input packages, and exposes:

- `nixosConfigurations.tb371fc`: NixOS stage-2 userspace, with external boot
  integration deliberately incomplete;
- `hello-aarch64` and `mesa-aarch64`: independently realizable ARM package
  outputs;
- `aarch64-userspace-closure`: package closure inventory built by a native
  x86_64 or AArch64 helper, depending on the selected attribute;
- `vanilla-kernel-cross`: a cross-toolchain/kernel probe, without TB371FC changes;
- `artifact-gate`: explicit failure until real kernel/DT/initramfs/config/
  Module.symvers/module/firmware inputs are supplied.

The first checks require neither ARM execution nor a tablet:

```sh
TB_NIX_FLAKE="path:$PWD/distros/nixos"
nix --extra-experimental-features 'nix-command flakes' \
  eval --json "$TB_NIX_FLAKE#lib.tb371fc"
nix --extra-experimental-features 'nix-command flakes' \
  eval --raw "$TB_NIX_FLAKE#nixosConfigurations.tb371fc.config.system.build.toplevel.drvPath"
nix --extra-experimental-features 'nix-command flakes' \
  build --no-link --print-out-paths \
  "$TB_NIX_FLAKE#packages.x86_64-linux.hello-aarch64"
```

Evaluation proves configuration consistency only. Cache substitution proves
availability of the selected package output. A full custom NixOS system closure
contains new derivations; build those on a native AArch64 builder or a properly
configured foreign builder, or deliberately cross-compile after assessing each
package. A complete ARM desktop cross-build is a different and larger task
than cross-compiling a kernel with native tools.

Nix normally isolates builds with its [sandbox settings](https://nix.dev/manual/nix/stable/command-ref/conf-file#conf-sandbox).
Nested unprivileged LXC may deny required namespace or mount operations. Start
with the existing setting and record the actual failure. A disposable build
container can explicitly opt into a per-command `--option sandbox false` if
needed and authorized, recording the weaker isolation; this is not a default
in the flake and must not become an unexplained host-wide change. Portable or
rootless Nix still has store/user-namespace/FUSE requirements to inspect; it
does not automatically resolve nested-container restrictions.

The final route is a fixed custom TB371FC kernel/DT/module/firmware build plus
a realized NixOS root tree and reviewed initramfs entry into its stage-2 `init`.
The provided module disables Nix-generated kernel/initrd and rejects bootloader
installation so its current output cannot be mistaken for that final route.

### Recorded Nix container verification

The actual results are in [nixos-build.json](evidence/nixos-build.json) and the
[Nix README](../../../distros/nixos/README.md#observed-container-results-2026-11-23).
They were obtained in the existing Debian 13 x86_64 build container in CT102
using Nix **2.26.3**, with the generated [flake.lock](../../../distros/nixos/flake.lock)
retained. The lock's source NAR hash is
`sha256-IEuDsf80ubivfpidbRsIm30HVo7PZIdZt1stRsbaY4Y=`.

| Experiment | Result |
| --- | --- |
| NixOS configuration evaluation | Exit 0; the custom system derivation targets `aarch64-linux` |
| ARM64 `hello 2.12.3` | Substituted from the official cache, then executed through explicit `qemu-aarch64 10.0.13`; exit 0 and `Hello, world!` |
| Selected ARM64 userspace closure | Successfully realized; 386 unique dependency paths present, total NAR size 2,217,061,896 bytes |
| ARM64 Mesa `26.1.8` | Freedreno `msm_dri.so`, Turnip `libvulkan_freedreno.so` and `freedreno_icd.aarch64.json` present; both shared libraries are AArch64 ELF |
| Missing-artifact gate | Expected exit 1, explicitly listing the eight missing boot artifact inputs |

The closure initially failed because the container could not provide Nix's
required sandbox namespaces. The first attempt's error was preserved. The
successful retry and the gate check explicitly used `--option sandbox false`
for those commands only; the container's Nix default remained `sandbox = true`.
The missing `nixbld` group and four build users were created only inside the
build container. No host/CT Nix configuration or binfmt registration changed.

The successful closure inventory is
`/nix/store/gb1qmx1p3a8rl5z6qnflzr0yhgf9w78s-closure-info`; its manifest and
registration metadata are retained under `/work`, together with an indirect
GC root for the realized store output. The official cache was used with
`require-sigs = true`. The evidence retains command/exit records, log hashes,
source hashes, the first sandbox failure, selected cache signatures/NAR hashes,
and graphics/ELF inspection details.

The full NixOS system/rootfs was **not** built. Its custom derivations need an
AArch64 builder or a deliberately configured foreign build route. The result
above is the selected package dependency closure plus an ARM userspace ABI
probe; there was no GPU execution, tablet boot or hardware acceptance test.

## Build acceptance records and remaining hardware work

Each experiment must record the container image/digest, architecture,
compiler/Nix/pmbootstrap version, source revision, final config/lock file,
commands, exit status and artifact hashes. Preserve the first concrete failure
instead of suppressing it to produce a nominally successful archive.

Accept a kernel compile only with the expected ARM64 Image and matching module
metadata. Accept a rootfs build only after target-architecture packages and
required configuration scripts are accounted for. Keep a separate acceptance
item for kernel/DT/firmware integration, controlled tablet boot, rendering,
input, Wi-Fi, charging and suspend. None of those hardware items is completed
by this source/build-route document.
