# TB371FC device-tree preflight against Linux 6.12.114

## Result and limits

The base `qcom/sm8250-lenovo-tb371fc.dtb` target **compiled successfully** with
Clang 19.1.7 after applying
[`0016-dts-tb371fc-linux-6.12-compat.patch`](../../../mainline-port/backports/linux-6.12/0016-dts-tb371fc-linux-6.12-compat.patch).
The unmodified board DTS failed on two references that are incompatible with the
prepared Linux 6.12.114 tree. The patch corrects those references without removing
hardware nodes, changing GPIO assignments, changing the firmware filename, or
enabling the experimental DSI paths.

This is a compiler check, not a boot or hardware test. It does not establish GPU
initialization, native DSI scanout, panel timing correctness, firmware
authentication, touchscreen operation, or working power management. Only the base
DTB target was built; the stage0, display-test, touch-test and camera variants were
not separately compiled in this preflight. `dtbs_check` was not run, so the result
is not a binding/schema-validation claim. See [the display audit](display.md) and
[the GPU audit](gpu-acceleration.md) for the remaining hardware questions.

## Isolated build setup

The runs took place on **2026-11-22 UTC**, inside the `tb371fc-build-20261123`
Docker container in doesvm CT102. The date in this research directory is its
existing project label. The container's `/src` repository mount was read-only.

The first run used the already prepared source tree
`/work/linux-6.12.114-research1`, including the handoff changes, selected 6.12
backports, custom panel/backlight drivers and installed TB371FC board DTS. It
copied `/work/kernel-out/.config` into the dedicated output directory
`/work/dtb-preflight` and ran:

```sh
make -C /work/linux-6.12.114-research1 \
    O=/work/dtb-preflight ARCH=arm64 LLVM=1 olddefconfig
make -C /work/linux-6.12.114-research1 \
    O=/work/dtb-preflight ARCH=arm64 LLVM=1 -j2 \
    qcom/sm8250-lenovo-tb371fc.dtb
```

For the corrected run, `/work/dtb-preflight-source` provided a private source
overlay. Its directory path to the board DTS and its top-level Makefile were
private, with other source entries symlinked to the prepared source tree. Only
the private board DTS was patched. The corrected run reused this preflight's own
output directory, never the concurrently running main kernel output directory:

```sh
git -C /work/dtb-preflight-source apply --check \
    /work/dtb-preflight-compat.patch
git -C /work/dtb-preflight-source apply \
    /work/dtb-preflight-compat.patch
make -C /work/dtb-preflight-source \
    O=/work/dtb-preflight ARCH=arm64 LLVM=1 olddefconfig
make -C /work/dtb-preflight-source \
    O=/work/dtb-preflight ARCH=arm64 LLVM=1 -j2 V=1 \
    qcom/sm8250-lenovo-tb371fc.dtb
```

These patch commands describe the completed run; the private overlay is already
patched. The source hashes below verify that the original prepared board DTS
remained unchanged. No operation in this preflight edited the main build's source
or `/work/kernel-out`.

The jobs ran in separate windows of tmux session `tb371fc`, through
[`scripts/research/build/run_job.py`](../../../scripts/research/build/run_job.py),
which records persistent logs, start times, exit codes and elapsed time.

## Reproduced failures and minimal fixes

| Original compiler failure | Cause in Linux 6.12.114 | Change in 0016 |
| --- | --- | --- |
| `502.1-16 Label or path gpu_zap_shader not found` | `sm8250.dtsi` has an unlabelled `zap-shader` child of `gpu`, with its inherited `memory-region = <&gpu_mem>`. The board tried to extend a label that does not exist in this base tree. | Merge the board's firmware override into `&gpu { gpu_zap_shader: zap-shader { ... }; };`. The child node name is unchanged, so its inherited memory region is retained. The added label also preserves the name referenced by the existing stage0 source. |
| `728.43-44 syntax error` | `DSI_BYTE_PLL_CLK` and `DSI_PIXEL_PLL_CLK` are private C driver defines, not exported DT binding macros in this source tree. They survive preprocessing as invalid tokens inside a DT cell list. | Use `0` and `1` respectively for the existing `&mdss_dsi0_phy` clock references, matching this kernel's provider and upstream SM8250 usage. |

The relevant primary source is the exact Linux v6.12.114 implementation:

- [`sm8250.dtsi`](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/arch/arm64/boot/dts/qcom/sm8250.dtsi?h=v6.12.114)
  defines the GPU's existing `zap-shader` child and uses DSI PHY clock indices.
- [`dsi_phy.h`](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/drivers/gpu/drm/msm/dsi/phy/dsi_phy.h?h=v6.12.114)
  defines `DSI_BYTE_PLL_CLK` as `0` and `DSI_PIXEL_PLL_CLK` as `1` for the driver.
- [`dsi_phy_7nm.c`](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/drivers/gpu/drm/msm/dsi/phy/dsi_phy_7nm.c?h=v6.12.114)
  installs the byte and pixel clocks at those two provider indices.
- [`sm8250-xiaomi-elish-common.dtsi`](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/arch/arm64/boot/dts/qcom/sm8250-xiaomi-elish-common.dtsi?h=v6.12.114)
  already uses `<&mdss_dsi0_phy 0>, <&mdss_dsi0_phy 1>` for the second DSI host.
  This is evidence for the SoC clock binding, not a claim that another tablet's
  panel configuration applies to TB371FC.

The patch must be applied **after** the repository's
[`sm8250-lenovo-tb371fc.dts`](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts)
has been installed into `arch/arm64/boot/dts/qcom/` in the prepared kernel source.
It is a compatibility patch for that source composition, not a patch that applies
directly to an otherwise untouched upstream tree lacking the TB371FC board file.

## Recorded execution

All log and JSON paths in this table are inside the build container.

| Job | UTC start | Exit | Elapsed | Evidence |
| --- | --- | --- | --- | --- |
| First kernel-target build | `2026-11-22T21:20:49.082085+00:00` | `2` | 275.66 s | `/work/dtb-preflight.log`, `/work/dtb-preflight.json` |
| Independent direct preprocessing/DTC reproduction | `2026-11-22T21:25:40.405993+00:00` | `1` | 0.79 s | `/work/dtb-preflight-direct.log`, `/work/dtb-preflight-direct.json` |
| Corrected kernel-target build | `2026-11-22T21:29:34.297319+00:00` | `0` | 76.80 s | `/work/dtb-preflight-compat.log`, `/work/dtb-preflight-compat.json` |

The first `olddefconfig` completed without changing the configuration. The two
failed runs reproduced the same missing-label and syntax diagnostics. The
corrected run emitted no compiler warning/error diagnostics in its log under
the kernel target's default warning settings. The target itself disables several
DTC warning classes; this is not evidence that every possible warning or schema
check is clean.

Tool versions recorded in the container:

- `Debian clang version 19.1.7 (3+b1)`.
- Kernel-built device-tree compiler: `DTC 1.7.0-gbcd02b52`.

## Output and semantic spot checks

The output is
`/work/dtb-preflight/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dtb`,
**126,236 bytes**. A read-only parse of this compiled binary confirmed:

| Compiled node/property | Observed value |
| --- | --- |
| `/soc@0/gpu@3d00000/zap-shader/firmware-name` | `qcom/sm8250/lenovo/tb371fc/a650_zap.mbn` |
| The same node's `memory-region` | Phandle `0x7d`, resolving to `/reserved-memory/memory@8681a000` |
| `/soc@0/display-subsystem@ae00000/dsi@ae96000/assigned-clock-parents` | Cells `0xda 0x0 0xda 0x1`; `0xda` resolves to `/soc@0/display-subsystem@ae00000/phy@ae94400` |
| The same second DSI host's `status` | `disabled`, as in the input board DTS |

Phandle numbers are specific to this output and must not be hardcoded into
source. These checks establish that the intended inherited memory reference,
firmware filename, provider selection and output indices survived compilation;
they do not establish that firmware can be authenticated or that DSI can run.

| Artifact | SHA-256 |
| --- | --- |
| Original prepared board DTS, unchanged after the corrected build | `80b9dbbe56e2ea892d553c756308ec516b9eb45a9dec2d19dc7edf91db1abe97` |
| Private patched board DTS | `288e8278b90770b16461073d32706c741abed79d6a45e4c33a3c1191c9b1e178` |
| 0016 patch | `1dfc5caa09ae5f7bb6b93198331abde812e878e5b9f82c13467bdade1e74a105` |
| Preflight `.config`, before and after `olddefconfig` | `1929caefadeb28cf84174c7fe7c100ab7251b3adcfdf547b2165c229b50f66da` |
| Compiled base DTB | `129bbee33b0c71be120d1d724be6267d0e4f99c07ec9ed951a823ab9241998dc` |

The private overlay's source provenance and the before/after source check are
also recorded in `/work/dtb-preflight-compat-source.json`. Nothing from this
preflight was booted or flashed to the tablet.
