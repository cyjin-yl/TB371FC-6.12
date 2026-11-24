# TB371FC GPU acceleration: source audit and acceptance contract

Date: 2026-11-23 (Asia/Shanghai). Repository source baseline:
`d157b92721fbeeab823f56a677b3593babf3afe6`.

## Result and evidence boundary

Adreno 650 has a mainline MSM/Freedreno/Turnip implementation to build on.
This repository also contains a historical working-desktop claim and concrete
GPU bring-up code. The remaining work is to reproduce one complete kernel,
DT, firmware and userspace combination, remove or account for its workarounds,
and test rendering and presentation independently. Installing a different
root filesystem does not complete those steps.

This report is an offline source/configuration audit, supplemented by the
owner's Android reference in [android-gpu.json](evidence/android-gpu.json).
No new mainline GPU draw, desktop, native DSI, video-decoding or suspend test
is claimed. An x86 build container or emulated AArch64 rootfs can validate
packages and build recipes; it cannot validate this tablet's A650 without the
actual device and an appropriate kernel/device interface.

The follow-up now has a successful [full research kernel build and generic VM
boot](kernel-build.md), plus [actual GPU firmware staging](firmware.md) in both
complete-ELF and split-MDT forms. The final resolved configuration enables
firmware decompression and Venus's parent menu. Patch 0015 compiled as part of
that Image. These close build/packaging prerequisites only; the no-mainline-draw
boundary above still applies. Fedora's software EGL/Wayland/Vulkan checks are
documented separately in [fedora-build.md](fedora-build.md).

The independently built [research2-display candidate](research2-display-build.md)
also passes its full build, matching module-set inspection and generic ARM64
VM boot. Its enabled native display DT still needs physical qualification.
The [frozen firmware request contract](firmware-kernel-contract.md) confirms
the final A650 filenames and enabled GPU/GMU nodes, while Venus remains
disabled despite its module being built. Neither candidate supplies a new
owner-tablet render, video-codec or GPU address-space-isolation result.

The current project reference remains [R226](../../../experimental/r226/README.md).
Its installed result explicitly confirms desktop, touch, SD and USB behavior;
it is not a fresh per-API GPU test log. The root [README](../../../README.en.md)
reports Freedreno/KWin acceleration. Older [V56 records](../../WORKING_BASELINE_V56.md)
describe a different **KGSL Turnip/Zink** stack, with software KWin. Neither
should be silently substituted for the other.

### Findings that affect the next build

| Finding | Concrete evidence | Required action |
| --- | --- | --- |
| Android exposes both KGSL and a DRM render node | Current reference identifies `kgsl-3d` and DRM driver `msm_drm` | Never accept `renderD128` existence as mainline MSM proof |
| R185 bypasses per-process GPU page-table switching | `qcom,adreno-smmu` is removed from the GPU SMMU compatible list | Treat global address space as an explicit workaround; recover the original fault evidence before calling the issue fixed |
| The headless patch leaks an OF-node reference | `msm_use_mmu()` uses `of_find_node_with_property()` directly as a Boolean | Patch 0015 now balances the reference; existing lookup policy is preserved, hardware validation remains pending |
| Handoff firmware decompression is disabled | `CONFIG_FW_LOADER_COMPRESS` is explicitly not set | Match the target kernel to the distribution's actual uncompressed/XZ/Zstd firmware packaging |
| The handoff disables the Venus parent menu | `CONFIG_V4L_MEM2MEM_DRIVERS` is explicitly not set | Build and validate the video-codec path separately if hardware decoding is required |
| KWin activation is based on path existence | `tb371fc-gpu-env.sh` tests two fixed by-path names, then prints "enabled" | Verify actual driver/context and compositor information; retain a deliberate fallback |
| Historical KGSL overrides can contaminate a native session | Old launcher forces Zink, a private ICD, `TU_DEBUG=noconform`, and software WSI | Use a coherent distro Mesa/GLVND stack for native MSM; inspect effective environment |

Sources and exact limits for each finding follow below. These are source
findings, not newly observed native failures.

## Four independent graphics paths

| Path | What must be demonstrated | What it does not establish |
| --- | --- | --- |
| A650 rendering | MSM render device, correct firmware/GMU/SMMU, a real FD650/Adreno 650 context, correct draw/readback | Display modes, scanout, compositor selection or video decoding |
| GPU rendering with inherited framebuffer presentation | KWin/application uses A650, then transfers the result through the simpledrm output path | Native DPU/DSI initialization or a higher panel refresh |
| Native DPU/dual-DSI presentation | Correct full frame on both halves, DSC/PPS, resource allocation, synchronization, blanking and transitions | A650 acceleration; a CPU-rendered image can also be scanned out |
| Venus decoding | Video-codec probe/firmware, V4L2 formats, a successful decode session and application use | GL/Vulkan rendering or native display correctness |

Linux 6.12 [simpledrm](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/tiny/simpledrm.c)
uses `drm_gem_fb_begin_cpu_access()`, `drm_fb_blit()` and
`drm_gem_fb_end_cpu_access()` in its plane update. Its driver features do not
include a render node. Consequently, GPU composition can coexist with a CPU
copy into the inherited framebuffer. This can improve shader/compositing work
while leaving a presentation cost. It is not a zero-copy or native-DSI result.
The exact KWin allocation/import path still needs its own evidence.

The official [DRM user API](https://docs.kernel.org/6.12/gpu/drm-uapi.html)
separates render nodes from modesetting/master ownership. It also documents
that PRIME import/export capability flags always report support from Linux
6.6 onward; those bits cannot replace a real format/modifier, import and
fence test. The panel-specific remaining issues are in [display.md](display.md).

## Current Android reference

The coordinated passive observation identifies **Adreno650v3**, a
`msm-adreno-tz` KGSL governor and available frequencies of
683/642/602/537/452/410 MHz. These are Android's reported identity and list,
not a validated mainline OPP table or a request to force the highest rate.
The device has `/dev/dri/renderD128`, but its DRM driver is `msm_drm`; the
GPU's own platform driver is `kgsl-3d`, with OF node
`/soc/qcom,kgsl-3d0@3d00000`. This is the vendor Android stack.

The stock files are under `/vendor/firmware`, and both ZAP forms exist:

| Stock file | Size | Role / handling |
| --- | ---: | --- |
| `a650_gmu.bin` | 41,548 bytes | GMU firmware; compare the captured hash with the packaged mainline copy |
| `a650_sqe.fw` | 31,632 bytes | GPU command-processor firmware |
| `a650_zap.elf` | 13,964 bytes | Complete ELF form; do not confuse its length/hash with split metadata |
| `a650_zap.mdt` | 6,860 bytes | Split-package metadata |
| `a650_zap.b00` / `.b01` / `.b02` | 148 / 6,712 / 1,676 bytes | Sibling split files; validate which ELF segments the loader actually requires |

The evidence JSON records hashes; firmware bytes are not published here.
The presence of both `.elf` and `.mdt` means the existing packaging script's
`.mdt` input is available. There is no basis to claim it is missing merely
because a complete `.elf` was also found.

## Kernel, device tree and firmware contract

### A650 support and API versions

The official [Mesa Freedreno documentation](https://docs.mesa3d.org/drivers/freedreno.html)
describes Freedreno GL/GLES and Turnip Vulkan for the Adreno 6xx family. Its
overview currently lists GLES 3.2 / desktop GL 4.5 and Vulkan 1.3. The
[Mesa 26.3.1 release notes](https://docs.mesa3d.org/relnotes/26.3.1.html), dated
2026-11-18, discuss Mesa-wide GL 4.6 / Vulkan 1.4 but explicitly say the
reported version depends on the driver and context. Thus a release-wide
number is not an A650 acceptance result or a ceiling inferred from an older
overview page. Record the actual driver, context type, GL version and Vulkan
physical-device API version in the selected distro build.

Do not use `MESA_GL_VERSION_OVERRIDE`, `MESA_GLES_VERSION_OVERRIDE` or
`TU_DEBUG=noconform` to satisfy an API requirement. Context creation,
advertised features, conformance and application correctness are different
claims. GMEM versus sysmem rendering is also a GPU tiling choice, not a
simpledrm versus native-DSI choice.

Linux 6.12's [A6xx catalogue](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/msm/adreno/a6xx_catalog.c)
has an A650 entry for chip ID `0x06050002`, requests `a650_sqe.fw` and
`a650_gmu.bin`, and carries a default ZAP name. The board can override ZAP
through DT. The checked-in
[TB371FC DTS](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts)
enables `&gpu` and `&gmu` and requests
`qcom/sm8250/lenovo/tb371fc/a650_zap.mbn`.

The SoC [sm8250.dtsi](https://github.com/torvalds/linux/blob/v6.12/arch/arm64/boot/dts/qcom/sm8250.dtsi)
provides the GMU, SMMU, OPP, clock, power-domain and speed-bin relationships.
Do not replace those with a maximum Android frequency or copy an unrelated
board's OPP ceiling. The [stage0 DTS](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc-stage0.dts)
deliberately disables GPU/GMU/ZAP: that diagnostic profile cannot be used as
evidence that an otherwise complete GPU port fails.

### Resolved kernel configuration, not just a fragment

The table below was read from the exported
[6.12.114 config](../../../experimental/community-handoff/reference/kernel-6.12.114/config).
It is not a manifest proving which config will be used by a future build.
The short `configs/*39bit.config` and `tb371fc-arch.config` files are fragments;
absence from a fragment is not the same as a disabled resolved Kconfig option.

| Layer | Handoff value | Check in the new build |
| --- | --- | --- |
| MSM render / scheduler / fences | `DRM_MSM=y`, `DRM_SCHED=y`, `SYNC_FILE=y`, `DMA_SHARED_BUFFER=y` | Preserve required selections from the target kernel's [MSM Kconfig](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/msm/Kconfig) |
| Clock/fuse support | `SM_GPUCC_8250=y`, `NVMEM_QCOM_QFPROM=y` | Also resolve COMMON_CLK_QCOM/GCC and the actual speed-bin dependency |
| GPU MMU | `ARM_SMMU=y`, `ARM_SMMU_QCOM=y` | Inspect the compiled GPU-SMMU compatible list, not config alone |
| Power/firmware | `QCOM_SCM`, `QCOM_MDT_LOADER`, `QCOM_AOSS_QMP`, `QCOM_LLCC`, `QCOM_RPMH`, `QCOM_RPMHPD`, `PM_OPP`, `PM_DEVFREQ` are `y` | Package dependencies and firmware at the stage that actually probes the GPU |
| Interconnect | `INTERCONNECT_QCOM_SM8250=m`, `INTERCONNECT_QCOM_RPMH=m` | Include matching modules/depmod metadata in the early root if consumers need them there; handle deferred probe |
| Governors/thermal | simple-ondemand and devfreq thermal enabled; performance governor disabled | Keep thermal policy and normal DVFS; forcing performance is not a repair |
| Firmware compression | `FW_LOADER_COMPRESS=n` | Provide uncompressed files, or enable the matching XZ/Zstd loader options and verify the final initrd/rootfs |
| Scanout | simpledrm plus MSM DPU/DSI/7nm PHY enabled | DT and runtime ownership determine which path is active |
| Video codec | `V4L_MEM2MEM_DRIVERS=n`; `VIDEO_QCOM_VENUS` absent | A separate feature gap, not a GL/Vulkan failure |

The firmware decompression mismatch is conditional on the selected rootfs
actually supplying only compressed files. It is not an assertion that either
container currently has such files. Check the image contents and resolved
config together rather than assuming a distribution's package policy.

### Firmware packaging gaps

[package-stock-firmware.sh](../../../scripts/package-stock-firmware.sh) places
SQE and GMU under `qcom/` and copies stock ZAP `.mdt` metadata to the board's
`.mbn` lookup name, retaining `.bXX` siblings. This extension change alone
is not an error: the official
[MDT loader](https://github.com/torvalds/linux/blob/v6.12/drivers/soc/qcom/mdt_loader.c)
uses ELF metadata and derives sibling names by replacing the final extension.
The loader supports split and complete-image forms.

There is a concrete packaging-check omission: unlike the preceding DSP loop,
the ZAP loop does not fail when no split segments are copied. A robust fix is
to inspect the ELF program headers, identify valid loadable segments, and
require the appropriate sibling sizes **when the image is split**. Requiring
at least one `.bXX` file unconditionally would reject a legitimate complete
image. The new acceptance helper reports split packaging and missing segments;
it does not authenticate Qualcomm signatures or load firmware.

Pin hashes of Image, resolved config, DTB, modules and firmware package. If
probe occurs before the real root is available, the same needed firmware and
module dependencies must be in the initrd. An existing file on the later
rootfs is not proof that an early request succeeded. The historical
[6.12 port notes](../../LINUX_6_12_PORT.md) mention a provisional generic ZAP;
prefer the captured stock provenance and document the chosen set explicitly.

## Concrete code and integration fixes to prepare

### GPU-01 — Contain and investigate the global-address-space workaround

[build-r185-global-pgtable.sh](../../../scripts/build-r185-global-pgtable.sh)
states that R183 encountered CP translation faults on userspace IBs. It removes
`qcom,adreno-smmu` so MSM cannot create its normal per-process page tables.
[build-r185-gpu-dt.sh](../../../scripts/build-r185-gpu-dt.sh) carries the same
change into the desktop DT. A separate
[R183 candidate](../../../scripts/build-r183-noncoherent.sh) removes
`dma-coherent` for a cache-maintenance experiment.

These are distinct experiments. Do not stack them without recording the
exact DT and fault behavior, and do not describe globally shared GPU address
space as restored per-process isolation. The public handoff does not supply a
new reproduction of the original IB fault on the owner's tablet.

The next kernel change should target a demonstrated cause: compare the
working/global and intended/per-process paths on the same kernel and Mesa,
retain the offending IOVA/context/fault class, and review the Adreno SMMU
implementation, TTBR switching and coherency setup. A board-scoped temporary
workaround must remain explicit. Acceptance needs multiple independent GPU
clients, buffer lifetime/fence tests and clean fault recovery, not merely a
single successful EGL initialization. Do not change `dma-coherent` or disable
IOMMU protection simply to obtain a benchmark result.

### GPU-02 — Reference leak fixed; broader headless policy remains unchanged

[Patch 0003](../../../mainline-port/patches/0003-drm-msm-adreno-tb371fc-headless-gpu.patch)
and the exported
[working-tree diff](../../../experimental/community-handoff/reference/kernel-6.12.114/working-tree.patch)
extend the legacy headless Adreno path with `tb371fc,headless-gpu` and a
synthetic `msm` platform device. The comment says "render node only", but a
headless DRM driver may still expose a primary card node; its absence of a
display pipeline is the relevant distinction.

`msm_use_mmu()` calls `of_find_node_with_property()` inside a Boolean
expression and never releases the returned node. The official
[OF implementation](https://github.com/torvalds/linux/blob/v6.12/drivers/of/base.c)
documents that this returns an incremented reference.
[Patch 0015](../../../mainline-port/backports/linux-6.12/0015-drm-msm-balance-headless-node-reference.patch)
now moves that single Boolean lookup into a helper, records whether the node
exists and releases the reference before returning. It deliberately preserves
the original OR short-circuit order, whole-tree search and `!of_node`
predicate. It does not alter headless registration, IOMMU selection or the
global-page-table workaround.

The patch was checked and applied offline to the official Linux v6.12.114
`msm_drv.c` **after** the handoff working-tree patch's changes to that file.
Both `git apply --check` and application succeeded. The subsequent full
research Image build also compiled this source successfully; see
[kernel-build.md](kernel-build.md). Neither result exercises this code on the
physical tablet. Apply it after the handoff patch in the selected build recipe.
Any later change that scopes the lookup to a particular enabled GPU/IOMMU
is a separate behavior change requiring its own rationale and validation.

Review synthetic-device registration failure/unregistration as part of the
same lifecycle change; the inherited
[6.12 helper](https://github.com/torvalds/linux/blob/v6.12/drivers/gpu/drm/msm/adreno/adreno_device.c)
discards the registration return value. Do not broaden that legacy pattern
into a general unbind/reprobe guarantee. For a different kernel version,
first check its existing headless support and DT bindings instead of applying
this old patch blindly. Registration/lifecycle and address-space policy
questions remain separate from the reference-balance fix. The read-only
acceptance helper does not apply kernel patches.

### GPU-03 — Make KWin activation an observed choice

The base [Plasma service](../../../scripts/r149-config/r149-plasma.service)
forces QPainter/software rendering. The
[R185 environment script](../../../scripts/r184-config/tb371fc-gpu-env.sh)
overrides it when fixed `platform-msm-card` / `platform-msm-render` paths exist,
selects MSM before the inherited framebuffer, and sets
`KWIN_DRM_FORCE_GL_FINISH_PRESENT=1`.

For Fedora or postmarketOS, prepare a distro-appropriate session configuration
that identifies devices from driver binding and their actual by-path links.
Do not hard-code `card0`, `renderD128` or the historical framebuffer address as
universal identities. A DRM node can exist while firmware initialization,
userspace access or real rendering fails; the existing "Adreno compositing
enabled" message is optimistic, not acceptance evidence.

After session start, collect KWin's `supportInformation`, its effective
graphics environment and the corresponding DRM mapping. Confirm FD650/Adreno
650 rather than QPainter/llvmpipe. Confirm that normal Qt applications have
not inherited `QT_QUICK_BACKEND=software`. A correct application renderer
does not by itself prove that KWin uses the same device.

The forced GL-finish setting is a historical synchronization workaround.
Carry it only with a matching KWin version/source and an explained need;
record correctness and presentation behavior before removing it. Changing a
KWin render-loop refresh override cannot change the panel's physical mode.
No compositor or session restart is performed by the acceptance helper.

### GPU-04 — Keep one coherent Mesa/GBM/EGL stack

Use Mesa's native MSM Freedreno/Turnip backends for the mainline kernel;
ensure the installed build includes Freedreno Gallium, the Freedreno Vulkan
driver, GBM/EGL and the intended Wayland platform. Verify the actual package
contents in each distro image. Do not transplant the old Arch launcher or
private `/opt` library paths into a different libc/package environment.

[tb371fc-run-gpu](../../../scripts/tb371fc-run-gpu) is explicitly a historical
KGSL launcher. It selects a private Turnip ICD, patched Zink libraries,
`TU_DEBUG=noconform` and `MESA_VK_WSI_DEBUG=sw`. These variables are evidence of
that alternate path, not prerequisites for the native driver. Scope any
legacy experiment to that command/session rather than export it globally.

Mesa's official [EGL documentation](https://docs.mesa3d.org/egl.html) explains
that initialization can fall back to software and that the internal
library/driver ABI is not stable. Therefore `eglinfo` exit 0, a Vulkan ICD
manifest, or a visible desktop is insufficient. Record the actual renderer
and loaded driver; keep Mesa, its Gallium/Vulkan drivers, GBM and GLVND
components from a coherent build. A software Vulkan device may coexist with
Turnip; do not fail the hardware device merely because lavapipe is also listed.

### GPU-05 — Give Venus its own build and application gate

The [Venus Kconfig](https://github.com/torvalds/linux/blob/v6.12/drivers/media/platform/qcom/venus/Kconfig)
depends on `V4L_MEM2MEM_DRIVERS`, `VIDEO_DEV`, `QCOM_SMEM` and the IOMMU path,
and selects its buffer/MDT dependencies. The handoff's disabled parent gate
explains why a Venus driver is not present in that config.
The [SM8250 Venus entry](https://github.com/torvalds/linux/blob/v6.12/drivers/media/platform/qcom/venus/core.c)
uses HFI 6xx / IRIS2 and the firmware lookup
`qcom/vpu-1.0/venus.mbn`. Match the actual DT and firmware package; enabling a
Kconfig symbol alone cannot supply its clocks, power domains or firmware.

Prepare a separate, bounded decode test only after device probe and V4L2
format enumeration. Require an application to report and use the expected
hardware decoder and produce correct frames. Browser WebGL, low CPU use,
smooth playback and GPU rasterization are not decoder identity tests. This
report does not promise a codec/profile/resolution or a working browser path.

## Executable acceptance workflow

The helper is [gpu_acceptance.py](../../../scripts/research/gpu_acceptance.py).
It only writes JSON to stdout. Normal exit 0 means the evidence collection
completed, **not** that the GPU passed all acceptance criteria.

### 1. Build-container or extracted-rootfs inspection

Run from the repository root, substituting an actual prepared rootfs and
resolved target config:

```sh
python3 -B scripts/research/gpu_acceptance.py \
  --root /path/to/prepared-rootfs \
  --kernel-config /path/to/resolved-target.config > gpu-image-audit.json
```

This checks firmware packaging, Vulkan ICD manifests and any available
snapshot DT/sysfs. Missing live nodes are expected in an ordinary image.
The tool refuses `--probe` with an extracted root, preventing the build
host's renderer from being mixed into target evidence. A successful package
installation or x86 llvmpipe result in CT102 is an image/build result only.

### 2. Passive snapshot on the actual booted Linux target

```sh
python3 -B scripts/research/gpu_acceptance.py > gpu-passive.json
```

Run as the intended desktop user to observe its current access. The default
does not open DRM devices or execute a program. It reads a narrow allowlist of
sysfs/DT/config/firmware and the graphics-related environment of KWin processes
when permissions allow. It does not read framebuffer pixels, arbitrary
debugfs/MMIO, full process environments or private application input.
Missing/denied attributes remain recorded as unavailable, not success.

### 3. Explicit information queries

```sh
python3 -B scripts/research/gpu_acceptance.py \
  --probe egl --probe vulkan --probe kwin \
  --require-a650-enumeration > gpu-enumeration.json
```

The only executable choices are fixed system paths for `eglinfo -B`,
`vulkaninfo --summary` and KWin's read-only `supportInformation` DBus method.
No arbitrary user command or shell is accepted. Queries have bounded time
and output, can create temporary driver contexts, and disable Mesa's shader
disk cache in the child process. They do not request a modeset, restart KWin,
change governors or force performance. Existing graphics overrides are
preserved and reported rather than silently hidden.

The optional exit-status gate requires an accessible character-device MSM
render node and a successful live query naming A650. Any observed KGSL or
vendor `msm_drm` backend prevents this **mainline enumeration** gate from
passing. Its classification is still a candidate identity check, not proof
of drawing, driver conformance, isolation or display correctness.

Existing logs can instead be parsed with `--egl-report`, `--vulkan-report`
and `--kwin-report`. Their origin, exit status and completeness are not
assumed, so supplied logs cannot satisfy the live-query gate. Vulkan UUIDs
and unrelated KWin support text are not copied into the parsed result.

### 4. Rendering and presentation acceptance, separately attended

These active tests are deliberately outside the passive helper:

1. **Offscreen correctness:** after enumeration, run the existing
   [EGL clear/readback smoke test](../../../scripts/r183-egl-smoke.py) on the
   known native target. It requires FD650 and exact RGB readbacks. Treat its
   success as a small draw/readback result; it is GLES2-only, not a GL/Vulkan
   feature-suite result. Inspect new GPU/GMU/IOMMU faults around the run.
2. **GL and Vulkan application correctness:** select a bounded, known scene
   for each API; record renderer, package versions, output correctness and
   errors. Avoid version overrides. Add multi-client allocation/lifetime
   coverage because of the documented address-space workaround.
3. **Wayland/compositor presentation:** inspect KWin support information,
   then exercise ordinary window movement, resizing and redraw. Capture
   import/modifier/fence/pageflip errors. Check both halves visually and
   identify which card owns the connector. If simpledrm is active, record
   that result explicitly; do not rename it native DSI.
4. **Native display:** use the mode/PPS/DSC acceptance items in
   [display.md](display.md). Refresh switching, both panel halves and pen
   behavior are separate from shader throughput. A vblank counter or KWin
   render-loop setting alone is not a measured presentation rate.
5. **Power and recovery:** after stable rendering, perform an attended
   idle/resume and then system suspend/resume test with input/display/network
   checks. Read devfreq/governor and fault history without forcing the
   highest frequency. Use [power-management.md](power-management.md) for the
   broader suspend evidence boundaries.
6. **Decode:** follow the separate Venus path above with known media and a
   decoder-identity check; do not infer hardware decoding from the GL tests.

Each result should identify kernel/config/DT/firmware/Mesa/KWin versions,
test input and duration, renderer/device selection, observed errors and the
scope actually exercised. No performance, battery-life, high-refresh or
video-codec claim is made by this audit.
