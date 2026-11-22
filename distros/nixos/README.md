# NixOS userspace build for TB371FC research

This flake pins the official **NixOS 26.05** channel revision
`94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd` and targets `aarch64-linux`.
The generated [flake.lock](flake.lock) also fixes its NAR hash to
`sha256-IEuDsf80ubivfpidbRsIm30HVo7PZIdZt1stRsbaY4Y=`.
It assembles a NixOS userspace configuration, Mesa, Vulkan tools, a minimal
Wayland stack, NetworkManager, Bluetooth tools and input diagnostics. It does
not provide a TB371FC kernel or a bootable Android/recovery image.

The official [26.05 channel revision](https://channels.nixos.org/nixos-26.05/git-revision)
resolved to that commit on 2026-11-23 (Asia/Shanghai), corresponding to
[`nixos-26.05.14979.94c3211b0ee8`](https://releases.nixos.org/nixos/26.05/nixos-26.05.14979.94c3211b0ee8/).
The [release announcement](https://nixos.org/blog/announcements/2026/nixos-2605/)
and [ARM documentation](https://wiki.nixos.org/wiki/NixOS_on_ARM) describe
generic AArch64 support and the official binary cache. They do not certify this
tablet. The complete `nixos-hardware` tree at
[`33475966110df258f52d05ec4d4cd6394637cbb9`](https://github.com/NixOS/nixos-hardware/tree/33475966110df258f52d05ec4d4cd6394637cbb9)
contained no `tb371fc`, `pipa`, `sm8250` or `nabu` path in this review.

## What can be checked immediately

Run inside the dedicated build container. `path:` is intentional while these
files are new/untracked; a Git-backed flake normally excludes untracked files.
Adjust the checkout path, then use:

```sh
TB_NIX_FLAKE="path:$PWD/distros/nixos"
nix --extra-experimental-features 'nix-command flakes' \
  eval --json "$TB_NIX_FLAKE#lib.tb371fc"
nix --extra-experimental-features 'nix-command flakes' \
  eval --raw "$TB_NIX_FLAKE#nixosConfigurations.tb371fc.config.system.build.toplevel.drvPath"
nix --extra-experimental-features 'nix-command flakes' \
  eval --raw "$TB_NIX_FLAKE#packages.x86_64-linux.vanilla-kernel-cross.drvPath"
```

No ARM binary needs to run for those evaluations. On an x86_64 builder, the
following attempts realization of ARM package outputs from the official cache
and creates a closure inventory with a native x86_64 builder:

```sh
nix --extra-experimental-features 'nix-command flakes' \
  build --no-link --print-out-paths \
  "$TB_NIX_FLAKE#packages.x86_64-linux.hello-aarch64"
nix --extra-experimental-features 'nix-command flakes' \
  build --no-link --print-out-paths \
  "$TB_NIX_FLAKE#packages.x86_64-linux.aarch64-userspace-closure"
```

The closure output contains `store-paths` and a registration file. It is a
package-availability result, not a root filesystem image, ARM execution test,
GPU test or tablet boot. `mesa-aarch64` is also exposed as an individual output.
Inspect its DRI and Vulkan ICD files after realization; a CPU renderer remains
possible until the tablet's MSM render node and exact firmware work.

For the full NixOS userspace closure, build
`nixosConfigurations.tb371fc.config.system.build.toplevel` on a native AArch64
builder or a deliberately configured foreign-architecture builder. The custom
system derivations are not expected to be present in the public binary cache.
The generated stage-2 `init` must later be entered by the reviewed external
initramfs after mounting the root filesystem and making the Nix store available.
This configuration disables Nix-generated kernel/initrd and deliberately rejects
boot-loader installation. `nixos-rebuild switch` is not a deployment procedure
for this tablet or the build host.

## Container permissions and build architecture

Evaluation and cache substitution require a writable Nix store and network
access. They do not require tablet USB, DRM, UFS, microSD, loop devices or an
ARM emulator. A pure cross-kernel build runs an x86_64 compiler that emits
ARM64 code; the `vanilla-kernel-cross` output is only a toolchain probe and
contains none of the TB371FC handoff changes.

Nix local builds normally use namespaces and a sandbox. An unprivileged LXC
container may deny the additional namespace/mount operations. Record the actual
error before changing any setting. Prefer a working sandbox, a native remote
builder, or an already approved container configuration. If the dedicated
disposable build container cannot provide the required isolation, a deliberate
per-invocation `--option sandbox false` is a possible build-only fallback; it
removes Nix build isolation and must be recorded with the result. The flake does
not set it and does not change the host or CT102 daemon configuration.

Running foreign ARM commands on x86_64 needs an AArch64 builder or explicitly
configured QEMU/binfmt. The flake does not register a global binfmt handler or
pretend that setting the target architecture provides CPU emulation. For
rootless/portable Nix setups, confirm how the Nix store and sandbox are
implemented before assuming that chroot/FUSE/user-namespace requirements are
available in nested LXC.

## External boot contract and explicit gate

The nullable `tb371fc.artifacts` options are declared in
[hardware-configuration.nix](hardware-configuration.nix). Supply real local
paths through an additional NixOS module when a coherent build exists:

| Option | Required artifact |
| --- | --- |
| `kernelImage` | Uncompressed ARM64 `Image` from the chosen TB371FC source/config |
| `deviceTreeBlob` | Exact matching board/panel DTB |
| `initramfs` | Audited first-stage/root-mount/init handoff for this NixOS system |
| `kernelConfig` | Final build `.config` |
| `moduleSymvers` | `Module.symvers` from the full kernel build |
| `moduleRoot` | Staging prefix with `lib/modules/<kernelRelease>` |
| `firmwareRoot` | Staging prefix with `lib/firmware`, preserving source/licenses |
| `kernelRelease` | Exact release string shared by Image and modules |

The paths are deliberately unset. No fake checksum, generic DTB, renamed donor
firmware or historical binary is substituted. A path supplied to Nix may be
copied to its store; keep private firmware stores and outputs private and do
not publish proprietary images through a binary cache.

```sh
# Expected to fail clearly until the real artifacts are supplied:
nix --extra-experimental-features 'nix-command flakes' \
  build --no-link "$TB_NIX_FLAKE#packages.x86_64-linux.artifact-gate"
```

With supplied paths, this gate checks the ARM64 Image/DT magic, nonempty
inputs, module directory and vermagic release, and records file hashes. It
does not prove symbol-CRC compatibility, DT suitability, firmware acceptance,
initramfs contents, external kexec entry state or actual hardware behavior.
Artifact references are not automatically installed into this userspace
profile. Wiring the matching module and firmware trees into the root/initrd,
then validating that handoff, remains an explicit integration change.

## Observed container results, 2026-11-23

The complete record is
[nixos-build.json](../../docs/research/2026-11-23/evidence/nixos-build.json).
These commands ran in the existing Debian 13, x86_64 build container
`tb371fc-build-20261123` inside CT102, using **Nix 2.26.3**. The Nix store used
`https://cache.nixos.org/` with `require-sigs = true`; the record retains the
stored cache signatures and NAR hashes for `hello` and Mesa. The missing
`nixbld` group and four dedicated build users were created inside that container.

| Check | Actual result | What it establishes |
| --- | --- | --- |
| NixOS `system.build.toplevel.drvPath` | Exit 0; a custom `aarch64-linux` system derivation was produced | The configuration evaluates; the full system was not built |
| `hello-aarch64` | Exit 0; `hello 2.12.3` and dependencies substituted from the official cache | The fixed ARM package output is available |
| Explicit `qemu-aarch64` execution | Exit 0; output `Hello, world!`; ELF64 little-endian, `e_machine = 183` | The cached program and its dynamic userspace dependencies execute under QEMU |
| Selected ARM userspace closure | Exit 0 on the recorded retry; 386 unique store paths, all present | The selected Mesa/Wayland/input/network package dependencies are realized |
| Mesa `26.1.8` | ARM64 Freedreno DRI library and Turnip Vulkan library/ICD present | The required graphics userspace is packaged; GPU execution was not tested |
| External artifact gate | Expected exit 1, listing all eight missing inputs | An incomplete boot artifact set is rejected |

The first closure attempt explicitly used `sandbox = true` and
`sandbox-fallback = false`. It failed with **“this system does not support the
kernel namespaces that are required for sandboxing”**. Only the subsequent
closure build and missing-artifact gate used per-command
`--option sandbox false`; both commands and the original error are retained.
The default was checked afterward and remained `sandbox = true`. No host/CT
Nix setting or binfmt registration was changed.

The successful closure output is:

```text
/nix/store/gb1qmx1p3a8rl5z6qnflzr0yhgf9w78s-closure-info
```

Its 386 selected dependency paths have a total NAR size of **2,217,061,896
bytes**. This is a serialized store size, not a compressed download size or
a rootfs image size. `store-paths` has SHA-256
`04e8b016f843f739a9455c8d752a3f97683e2cd859c63f716309a49aff5a7848`.
The manifest and registration file were copied to `/work`, and
`/work/nix-aarch64-userspace-result` retains the output as an indirect GC root.
The package bytes themselves remain in the build container's Nix store.

Mesa's output is
`/nix/store/cdxbk3aq70mqjf70wfq61ns705mwhgsp-mesa-26.1.8`. Inspection found
`share/vulkan/icd.d/freedreno_icd.aarch64.json`,
`lib/libvulkan_freedreno.so`, and `lib/dri/msm_dri.so`; both shared libraries
have AArch64 ELF machine ID 183. The evidence records their exact hashes and
the ICD's library path. No render-node, compositor, Vulkan-device or tablet
hardware test was performed.

The actual ABI probe used QEMU user mode **10.0.13** directly:

```sh
qemu-aarch64 \
  /nix/store/67xf635fy5p8pryn15rwfc5iz63gk0kx-hello-2.12.3/bin/hello
```

The full custom NixOS system output does not exist yet. Its derivation names
an `aarch64-linux` builder, so this native x86_64 container still needs an
explicitly configured AArch64 build route for those new derivations. Running
one cached ARM program through QEMU does not supply that route automatically.
No rootfs image was assembled, and no kernel, firmware, boot or tablet hardware
acceptance is implied by these package results.
