# Linux 6.12.114 research2-display candidate

## Result and scope

Status: **complete Image/module/DT build, generic ARM64 VM boot and final
artifact inspection passed**. The frozen research1 manifest/configuration were
reproduced exactly before constructing the independent display candidate.
The final inspection was captured at `2026-11-22T23:21:27.185817+00:00`.
Physical tablet, native display and GPU acceptance remain untested.

This candidate has the explicit release
`6.12.114-tb371fc-research2-display`. It starts from the frozen research1 source
inputs, adds only the already-qualified historical PHY/wide-plane patch 0002,
and selects the corrected, versioned native-display diagnostic DT. It does not
reconstruct R226 or turn a source qualification into physical tablet acceptance.
Research1's recipes, source, artifacts and evidence remain separate.

| Executed job | Result | Elapsed time |
| --- | --- | ---: |
| Reproduce baseline and prepare independent display source | Exit 0; exact research1 manifest and qualified patched-source hashes | 36.96 s |
| Full Image, modules, selected DTB and module installation | Exit 0 | 1,268.92 s |
| Generic QEMU `virt` smoke job | Exit 0; expected release, `aarch64` and EL0 marker observed | 7.59 s |
| Final artifact inspection | Exit 0; 83 matching modules and exact qualified DTB | 1.44 s |

The [build evidence](evidence/research2-display-build.json) contains the source
combination, artifact hashes, complete module-set checks, selected module
aliases/firmware declarations, resolved prerequisites, native DT state and VM
result. The recorded build ran from `23:00:09 UTC` for approximately 21 minutes
9 seconds; the VM and final inspection followed automatically in the same
isolated candidate pipeline.

## Why this candidate exists

The [diagnostic profile audit](diagnostic-dt-profiles.md) demonstrated that the
historical display test compiles while its private DPU and two PHY compatible
strings have no match in research1. The repository's existing 6.12 0002 patch
applied cleanly and built the five related objects. The same audit found and
corrected a framebuffer-node ownership error in a new versioned wrapper, leaving
the historical DTS intact.

This build advances that qualified combination to a complete Image, its own
modules and its exact native diagnostic DTB. A complete build and a generic VM
boot can expose integration/link/ABI and early kernel-entry problems that an
individual object build cannot. Neither test exercises the physical DPU, DSI,
PHY, panel, GPU, touchscreen or power sequencing.

## Fixed source combination

| Input | Identity and role |
| --- | --- |
| Official Linux 6.12.114 archive | SHA-256 `7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3` |
| Frozen research1 preparation | Original manifest SHA-256 `1a8788a8e5700287870d9e9ca44ad2be8c69e6f28d927321edd89508c5501821`; reproduced in the new candidate's private work directory and retained verbatim as `source-manifest-research1.json` |
| Added driver patch | `mainline-port/backports/linux-6.12/0002-tb371fc-phy-wideplane.patch`, SHA-256 `839699e055d8959232f2912895cbd71f5fd85f3e07a1d3f033a1fd728e08ce56` |
| Historical display-test DTS | SHA-256 `cbb4a34fb144d01f2df5804049b6de1fc58cd3fdb0417cec04ee44b01a5b0cef`; included without modification |
| Corrected 6.12 wrapper | SHA-256 `8cac3ffe34d6eaf3ee43ea1c63b4395fd6a38325ccb5f289283da3e234bfe1f7` |
| Expected native DTB | SHA-256 `50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e`, matching the separately compiled/checked wrapper |

The prepared base DTS is inherited through the original research1 preparation,
including its already-qualified 6.12 label/clock-index compatibility correction.
The historical display-test and versioned wrapper are then copied into the same
QCOM DTS directory. Their include dependencies therefore resolve to the pinned
base and SoC files.

Only historical 0002 is appended. The separate 0003 analog-value experiment is
not part of this candidate. The original handoff's DSI/DSC/CTL behavior remains
the baseline described in [display.md](display.md); unrelated historical DSC
experiments are not stacked onto it.

The new source manifest records all baseline/additional input hashes, the frozen
helper identities, all four new recipe hashes, the resulting patched/copied
source hashes, and the selected release/DT target. Preparation also compares all
six 0002-modified files with the already-qualified source hashes. Build and
inspection recheck the prepared manifest and inputs.

The completed preparation began at `2026-11-22T22:59:32.171666+00:00`, took
36.96 seconds and exited zero. Its new source manifest has SHA-256
`845914d9cc1c876f10704f3334ee942b2c26deaa8045ce9c2ef82ef2920cde21`.
The actual private repository overlay contains 27 explicitly staged input,
recipe, helper and prerequisite-evidence files. Its input manifest has SHA-256
`d7d3869981e14f3bfed4dec4029842aa4a55e516b04594e94d3c3d941f529f27`.

## Configuration and artifact boundaries

The build repeats research1's merge and QCOM-only platform selection. Before
changing the release suffix, the resulting `.config` must reproduce SHA-256
`1929caefadeb28cf84174c7fe7c100ab7251b3adcfdf547b2165c229b50f66da`.
It then changes only `CONFIG_LOCALVERSION` to `-tb371fc-research2-display` and
runs `olddefconfig` again. Every other configuration line must remain equal.
Both checks have passed in the actual build. The resulting candidate `.config`
has SHA-256 `e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8`.

This preserves the compiled Novatek, panel, dual-backlight, HID wake, firmware
decompression, MSM and Venus prerequisites. Their presence still does not
establish driver probe, firmware authentication, display operation, input events
or hardware video decoding.

The selected **display** DT enables the native panel/DSI/PHY path while retaining
the base's disabled SPI14/touch nodes. The inspector explicitly records these
states. Touch-test has not silently been merged into this candidate, so this
artifact cannot be described as satisfying the owner's complete-device goal.

Image, DTB, `kernel.config`, `Module.symvers`, `System.map`, release, manifests and
all installed modules are published under the candidate's own work directory.
An exclusive build lock prevents concurrent writers. Completed artifacts are
published from a private staging directory; an existing completed artifact set
is not overwritten. `--resume` is limited to this profile's recorded source,
configuration and release state.

This job does not replace the kernel or module tree in the separately assembled
Fedora or postmarketOS/Nura userspaces. Any subsequent rootfs integration must
use this candidate's own `lib/modules/6.12.114-tb371fc-research2-display` tree
with its matching Image and symbol set, and must preserve the separate firmware
provenance and physical acceptance requirements.

The artifact checker reuses the existing strict module-inventory routine with
the new release. It requires the expected 83 modules, an exact match between
build `.o` order, installed `kernel/*.ko` order and files, correct ARM64 ELF
headers, and the new release in every module's vermagic. It records all module
hashes and selected OF aliases/firmware declarations without loading a module.
Equal vermagic is not treated as an independent proof of arbitrary ABI
compatibility; these modules are built together with this Image and symbol set.

The final native DTB must match the qualified binary hash and retain the root
compatibles `lenovo,tb371fc`, `qcom,sm8250`. The real framebuffer stdout path and
enabled native display nodes are checked again. The Image must also contain the
two newly linked private DPU/PHY compatible strings.

All of those final checks passed. The delivered candidate identities are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Image` | 29,849,608 | `181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d` |
| `board.dtb` | 126,861 | `50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e` |
| `kernel.config` | 216,625 | `e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8` |
| `Module.symvers` | 807,568 | `8e71a956b3c79112228f92cd234a13a39aa7a3193a5d1222d1dab5123043d9d0` |
| `System.map` | 4,425,244 | `ab405c0d8b879e13b401e4b5cf86fe03e57c9843a7ed77c14e92e7a806ae9128` |

The compiled native profile has the following actual OF state. “Available” here
is a device-tree property, not an observed driver probe or operating device.

| Node | Compiled compatible(s) | Actual OF availability |
| --- | --- | --- |
| MDSS | `qcom,sm8250-mdss` | `status = "okay"` |
| DPU | `lenovo,tb371fc-dpu` | Available; no `status` property |
| Both DSI controllers | `qcom,sm8250-dsi-ctrl`, `qcom,mdss-dsi-ctrl` | Both `okay` |
| Both DSI PHYs | `lenovo,tb371fc-dsi-phy-7nm` | Both `okay` |
| Tianma panel | `lenovo,tb371fc-tianma-nt36532`, `novatek,nt36523` | `okay` |
| SPI14 | `qcom,geni-spi` | `disabled` |
| Touchscreen | `novatek,NVT-ts-spi` | `disabled` |

The root compatible order is exactly `lenovo,tb371fc`, `qcom,sm8250`, and
`stdout-path` resolves to `/chosen/framebuffer@9c000000`. The orphan
`/chosen/framebuffer0` node is absent. The final binary hash also ties this DTB
to the earlier full framebuffer clock/domain/GPIO/supply qualification.

All 83 installed module paths and their order match the complete build list,
with no missing, extra or undeclared external module tree. Every installed
module is ELF64 little-endian AArch64 and has the candidate release in vermagic.
The [complete module checksum list](evidence/research2-display-modules.SHA256SUMS)
records the actual stripped/signed installed files. The panel, backlight, touch
and Venus modules being present does not change their untested hardware status.

## Generic VM check

The new launcher imports the frozen controller's exact-line parsing, bounded
serial capture, cancellation and child cleanup functions. It preserves the old
research1 launcher's defaults and evidence. A fresh, freestanding ARM64 `/init`
must print the candidate's actual `uname` release, machine and readiness marker.

The VM uses QEMU `virt`, TCG, two CPUs and 1 GiB RAM. It passes no physical tablet
DTB, proprietary firmware, network interface, physical disk or passthrough device.
Its machine DT therefore takes the generic memblock branch of the scoped early
allocator fix. This cannot test the TB371FC-specific early pool or vendor-kexec
handoff. The Image hash, expected release, serial bytes, helper/launcher hashes
and cleanup result are retained and checked against the same final artifacts.

The actual [VM result](evidence/research2-display-qemu.json) records `pass`, with
all three exact release/machine/EL0 observations true and no guest error marker.
QEMU ran for 7.08 seconds within the smoke job, exited zero, and its child was
reaped without a forced kill. Serial output was not truncated. The
[original serial bytes](evidence/research2-display-qemu.log) have SHA-256
`00f50dfd515fed0df41474024ba55cc47e422e2a3a13064abb11bcd1d07d753c`.
The controller stopped after observing the userspace marker; this is not a
long-duration stability or suspend test. The tablet's native hardware drivers
were not exercised by this generic VM test.

## Reproduction

The new scripts are:

- [prepare_research2_display.py](../../../scripts/research/build/prepare_research2_display.py)
- [build_research2_display.sh](../../../scripts/research/build/build_research2_display.sh)
- [smoke_research2_display.py](../../../scripts/research/build/smoke_research2_display.py)
- [inspect_research2_display.py](../../../scripts/research/build/inspect_research2_display.py)

In a fresh isolated builder with the verified archive cached under
`/work/downloads/linux-6.12.114.tar.xz` and the complete current source mounted
read-only at `/src`:

```sh
export PATH=/usr/lib/llvm-19/bin:$PATH
export PYTHONDONTWRITEBYTECODE=1

python3 /src/scripts/research/build/run_job.py \
  --name research2-display-prepare -- \
  python3 /src/scripts/research/build/prepare_research2_display.py

python3 /src/scripts/research/build/run_job.py \
  --name research2-display-build -- \
  bash /src/scripts/research/build/build_research2_display.sh

python3 /src/scripts/research/build/run_job.py \
  --name research2-display-qemu -- \
  python3 /src/scripts/research/build/smoke_research2_display.py

python3 /src/scripts/research/build/run_job.py \
  --name research2-display-inspect -- \
  python3 /src/scripts/research/build/inspect_research2_display.py
```

The default private candidate work directory is `/work/research2-display`.
When using a private repository overlay, pass its absolute path through
`--repo` for Python commands and `TB371FC_REPO` for the build script; the
actual input and recipe hashes are still verified and recorded.

## Build environment and remaining acceptance

The actual execution environment is `tb371fc-build-ssd-20261123` in doesvm CT102,
with a dedicated SSD work mount, four CPU and 8 GiB memory limits, and LLVM 19.
The independently recorded [SSD builder qualification](ssd-builder.md) documents
Python 3.13.5, LLVM/LLD 19.1.7, make 4.4.1, system DTC 1.7.2, kmod 34.2 and QEMU
10.0.13, as well as a real AArch64 cross-compilation probe. Kernel DT compilation
uses the kernel-built DTC, not a substitution of the system compiler. The
builder's raw `/work/builder-ready.json` hash is
`106b252282329ccf03871236fe921371744b794abc6adf2ebc48b20e38665781`.

The original checkout mount `/src` is read-only. New and frozen inputs are
staged in `/work/research2-repo`, with untouched entries linked to `/src`. All
candidate preparation/build products stay under `/work/research2-display`.
The visible pipeline runs in container tmux session `tb371fc-ssd`, window `@1`,
with separate persistent `research2-display-{prepare,build,qemu,inspect}` jobs.
The pipeline preserves the LLVM 19 path and disables Python bytecode-cache writes
to its input overlay. The original HDD container and its Nura VM are separate.

The final builder [package inventory](evidence/research2-display-builder-packages.tsv)
has SHA-256 `8ac64da0ebd395e10811716dc4682371323166f29acafd1d4ed40e1b0939cee4`,
identical to the inventory captured when the SSD builder was qualified. The
five archived evidence files were transferred as raw bytes with size/SHA-256
verification; the serial log's original line endings are retained.

| Archived evidence | SHA-256 |
| --- | --- |
| [Build and artifact inspection](evidence/research2-display-build.json) | `64324d3d72a6c4dbec3d36fec7a1930628e5c584ff8789eb06d7131935e439c3` |
| [VM controller result](evidence/research2-display-qemu.json) | `b765158f46617d1bacda5dda81d6faa636f9270fc03baba866bf4b368f92331a` |
| [Raw VM serial log](evidence/research2-display-qemu.log) | `00f50dfd515fed0df41474024ba55cc47e422e2a3a13064abb11bcd1d07d753c` |
| [All module checksums](evidence/research2-display-modules.SHA256SUMS) | `18fc3d022405bb7a1f69424a41cc7af5d7608beb6a2d3e5a0b6f9c51a2ef4dbc` |
| [Builder package inventory](evidence/research2-display-builder-packages.tsv) | `8ac64da0ebd395e10811716dc4682371323166f29acafd1d4ed40e1b0939cee4` |

The complete build products remain in the SSD container at
`/work/research2-display/artifacts`, with the matching module tree under
`/work/research2-display/modules/lib/modules/6.12.114-tb371fc-research2-display`.
The complete job logs and exit records are `/work/research2-display-{prepare,build,qemu,inspect}.{log,json}`.

Build identity/timestamp are fixed, but a fresh inherited module-signing key
still affects output bytes. Private signing keys remain in the private build
workspace. APT package versions are recorded rather than obtained from an
immutable snapshot. This is a source-pinned, executable reconstruction recipe;
independent bit-for-bit reproduction is not claimed.

The [whole-device acceptance contract](acceptance.md) remains authoritative.
Native full-width scanout, both panel halves, 30/60/120/144 Hz transitions,
source-fetch format/modifier limitations, GPU rendering/presentation, input,
blanking/suspend/recovery and power behavior each require their own evidence.
No file in this build record authorizes or records a tablet boot or flash.
