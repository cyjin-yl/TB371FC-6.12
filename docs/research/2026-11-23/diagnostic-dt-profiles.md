# Diagnostic DT profiles against the frozen 6.12.114 research build

## Result and scope

The historical touch and native-display DTS files need to be qualified against
the **actual selected driver sources**, rather than accepted because DTC can
compile them. The frozen `6.12.114-tb371fc-research1` tree contains the Novatek,
panel and dual-backlight drivers, but its DPU and DSI PHY OF tables do **not**
contain the two private compatibles selected by the native-display test. Neither
string has a generic fallback in that test DTS.

An isolated qualification of the existing
[`0002-tb371fc-phy-wideplane.patch`](../../../mainline-port/backports/linux-6.12/0002-tb371fc-phy-wideplane.patch)
**applied cleanly and compiled all five selected driver objects**. Both original
diagnostic DTs also compiled. The touch profile has no missing match within the
audited set; the original display profile has three available nodes without a
match in research1 (DPU and two PHYs), and those matches are present after the
patch. This is a rebuildable 6.12 source candidate, with the behavior limits
described below. Changing only the DT strings to generic compatibles would skip
those behaviors. The historical DTS files and the frozen research1 source/output
are preserved.

The new versioned display wrapper also **compiled and passed its binary-level
structure checks**: one real framebuffer node, a resolvable absolute
`stdout-path`, the original clock/domain specifiers, unchanged framebuffer
geometry and unchanged GPIO/supply specifiers. Its root compatible remains
`lenovo,tb371fc`, `qcom,sm8250`. The candidate is qualified for further integration
work; it has not been booted on the tablet.

**No physical device was booted, flashed, probed or modeset for this work.**
The qualification distinguishes source matching, configuration, DT compilation,
affected-object compilation and runtime hardware acceptance. It does not produce
a fully linked replacement kernel, establish successful probe, run binding
schema validation, or close the native-display/GPU acceptance gates.

## Exact baseline

The source composition is pinned to the `source_manifest` embedded in
[`kernel-build.json`](evidence/kernel-build.json). Its separate source-manifest
file has SHA-256
`1a8788a8e5700287870d9e9ca44ad2be8c69e6f28d927321edd89508c5501821`.
The frozen configuration has SHA-256
`1929caefadeb28cf84174c7fe7c100ab7251b3adcfdf547b2165c229b50f66da`.

The baseline is official Linux 6.12.114 plus the exported community handoff,
selected input/backlight/HID fixes, the board-source compatibility fix, and the
scoped early page-table fix. It copies the repository's 6.12 panel/backlight
sources and the base board DTS. It does **not** select the historical
`0002-tb371fc-phy-wideplane.patch`, `0003-tb371fc-v56-analog.patch`, or the old
panel probe-stage patch. In particular, the selected
`mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch` is an
entirely different file from the similarly numbered PHY patch.

The inherited base DTS already has the two fixes in
[`0016-dts-tb371fc-linux-6.12-compat.patch`](../../../mainline-port/backports/linux-6.12/0016-dts-tb371fc-linux-6.12-compat.patch):
the GPU ZAP child is extended by node name, and DSI1's shared PHY clock parents
use indices 0/1. Its prepared SHA-256 is
`288e8278b90770b16461073d32706c741abed79d6a45e4c33a3c1191c9b1e178`.
The [earlier base-DTB preflight](build-dtb.md) did not compile either diagnostic
variant; this is a separate qualification.

## Source-match matrix

The entries below are from the prepared source itself. `m` means the driver
must also be supplied and loaded on a running Linux system; this audit only
reads module metadata and never loads modules.

| Consumer | Diagnostic DT compatible | Frozen driver/config | Baseline source result |
| --- | --- | --- | --- |
| Touch controller on SE14 | `novatek,NVT-ts-spi` | `nt36523/nt36xxx.c`, `CONFIG_TOUCHSCREEN_NT36523_SPI=m` | Exact OF entry exists and is assigned to the SPI driver's `of_match_table` |
| SE14 SPI controller | `qcom,geni-spi` | `spi-geni-qcom.c`, `CONFIG_SPI_QCOM_GENI=y` | Exact OF entry exists |
| MDSS parent | `qcom,sm8250-mdss` | `msm_mdss.c`, `CONFIG_DRM_MSM_MDSS=y` | Exact OF entry exists |
| DPU | `lenovo,tb371fc-dpu` | `dpu_kms.c`, `CONFIG_DRM_MSM_DPU=y` | **Absent**; `qcom,sm8250-dpu` exists, but the test replaces it |
| Both DSI hosts | `qcom,mdss-dsi-ctrl` | `dsi/dsi.c`, `CONFIG_DRM_MSM_DSI=y` | Exact OF entry exists |
| Both DSI PHYs | `lenovo,tb371fc-dsi-phy-7nm` | `dsi/phy/dsi_phy.c`, `CONFIG_DRM_MSM_DSI_7NM_PHY=y` | **Absent**; `qcom,dsi-phy-7nm` exists, but both test nodes replace it |
| Tianma panel | `lenovo,tb371fc-tianma-nt36532` | `panel-novatek-nt36523.c`, `CONFIG_DRM_PANEL_NOVATEK_NT36523=m` | Exact first compatible exists, selecting `tb371fc_tianma_desc` |
| Both KTZ8866 halves | `lenovo,tb371fc-ktz8866` | `tb371fc-ktz8866.c`, `CONFIG_BACKLIGHT_TB371FC_KTZ8866=m` | Exact OF entry exists |
| Backlight I2C controllers | `qcom,geni-i2c` | `i2c-qcom-geni.c`, `CONFIG_I2C_QCOM_GENI=y` | Exact OF entry exists |

`CONFIG_DRM_MSM`, `CONFIG_QCOM_GPI_DMA` and `CONFIG_PINCTRL_SM8250` are enabled.
These are necessary pieces of the dependency chain, not proof that GENI firmware,
RPMh supplies, clocks, pin ownership or the panel have initialized.

The generic second panel string, `novatek,nt36523`, is not itself an entry in
this panel driver's table. That is not the missing-match problem here: the
specific Tianma first string already matches. Conversely, the DPU and PHY nodes
have only their private string, so a generic SM8250 entry elsewhere in the table
cannot match them.

## Touch diagnostic profile

The existing
[`sm8250-lenovo-tb371fc-touch-test.dts`](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc-touch-test.dts)
includes the base board, changes its model text, and enables `spi14` and its
Novatek child. It does not select a newer display-compatible contract. There is
no justified touch-DTS rewrite merely to label it “6.12”: the versioned profile
is the unchanged diagnostic file **plus the prepared 6.12 base** and its recorded
driver/configuration inputs.

The firmware-name properties still select
`lenovo/tb371fc/novatek_ts_fw_boe_6.bin` and
`lenovo/tb371fc/novatek_ts_tm_fw_6.bin`. Reset GPIO56, IRQ GPIO68, panel-ID GPIO82,
9.6 MHz SPI maximum and the existing pen properties are preserved. This check
does not change GPIO assignments, remove reserved pins, send SPI transactions,
or prove firmware upload/IRQ/power/suspend behavior. The actual input and pen
requirements remain in [input-and-pen.md](input-and-pen.md) and the
[whole-device acceptance runbook](acceptance.md).

## What the native prerequisite patch adds

The existing PHY/wide-plane patch changes six files and supplies both missing
match entries together with their data objects:

| Area | Added behavior | Boundary |
| --- | --- | --- |
| DPU OF match | `lenovo,tb371fc-dpu` selects `dpu_tb371fc_cfg` | Matches the historical native-display test's exact string |
| DPU catalog | Board-specific caps with `max_linewidth = 1880`; the catalog references the SM8250 resources | A source-fetch threshold is distinct from DSC/DSI output splitting |
| PHY OF match | `lenovo,tb371fc-dsi-phy-7nm` selects `dsi_phy_7nm_tb371fc_cfgs` | Both PHY nodes use this selector |
| PHY data | SM8250 addresses `0xae94400`/`0xae96400`, two PHYs, V4.1 quirk, existing regulator/clock operations, 600 MHz–5 GHz PLL bounds | Inherited source parameters, not measured operating points |
| PHY lane setup | Board-only clock-lane `CFG0=0x20`, other lanes remain zero | The owner's Android capture contains the corresponding byte in the 20-byte lane table; runtime PHY programming remains unmeasured |

The captured lane-property bytes are
`00000a0a 00000a0a 00000a0a 00000a0a 20008a8a` on both PHYs, with SHA-256
`a82ceff043fd7b4593d69167457c67f73f4b5843577d6faa6e3a9b782e6d70db`;
see [android-stock.json](evidence/android-stock.json) and [display.md](display.md).
This is a grounded comparison of the particular clock-lane byte, not an assertion
that the entire downstream lane table has been translated correctly.

### The actual 6.12 wide-plane behavior

The historical display-test comment describes Linux 7.1's `dpu_plane_split()`
and two SSPPs. That description must not be applied to this 6.12 source. Its
`dpu_plane_atomic_check()` instead sets:

```c
pipe->multirect_index = DPU_SSPP_RECT_0;
pipe->multirect_mode = DPU_SSPP_MULTIRECT_PARALLEL;
r_pipe->sspp = pipe->sspp;
r_pipe->multirect_index = DPU_SSPP_RECT_1;
r_pipe->multirect_mode = DPU_SSPP_MULTIRECT_PARALLEL;
```

Both rectangles therefore use **the same hardware SSPP**. The source splits
source/destination rectangles at their midpoint. Its width-triggered branch
rejects UBWC when source width exceeds the limit, rejects width greater than
twice the limit, and rejects scaling, YUV, or a pipe without the required smart
DMA feature. A 2944-pixel unscaled linear RGB buffer meets the simple width
inequalities `1880 < 2944 <= 2 * 1880`, producing two 1472-pixel rectangles.
Those inequalities are not a proof that atomic check, bandwidth allocation or
scanout will succeed.

The handoff already changes generic SM8250's `max_linewidth` to
`DEFAULT_DPU_OUTPUT_LINE_WIDTH`, whose actual definition in this tree is **2560**.
The board patch adds a separate 1880 cap; it must not be described as reverting
the generic handoff change or adding 7.1's allocation implementation. Desktop
GBM/KWin format and modifier negotiation remains a separate acceptance item:
passing a linear-buffer diagnostic does not establish a working full desktop
path with the modifiers it normally selects.

The completed initializer comparison verified that 0002 leaves the existing
generic SM8250 caps and catalog unchanged. The new board caps differ only in
`max_linewidth`, and its resource table differs only in the caps pointer.
This confirms the patch does not duplicate or overwrite the handoff's generic
catalog edit. The assertions and input hashes are in
[native-dt-612.json](evidence/native-dt-612.json).

The old `verify-r137-native-prereqs.py` is not a qualification gate for this new
combination. It assumes the earlier generic cap is 4096 and also demands analog
overrides from a second patch. Altering that assertion just to obtain its
historical PASS text would erase the distinction between source combinations.

### Related patches are separate experiments

[`0003-tb371fc-v56-analog.patch`](../../../mainline-port/backports/linux-6.12/0003-tb371fc-v56-analog.patch)
adds board-gated DPHY analog overrides. The historical R137 build script applied
both 0002 and 0003. The qualification here tests 0003's application context but
does **not** add it to the one-patch candidate or claim those analog values were
measured on the owner's tablet.

Likewise, old DSC patches 0010/0011/0012 are not an automatic patch series to
append to the handoff. The handoff already changes CTL allocation/assignment,
DSC ownership/flushes and packetization. Its exact implementation must be
compared before choosing further changes; see the competing CTL and packetization
contracts in [display.md](display.md). A compatible-match fix alone does not
settle those contracts.

## Versioned 6.12 display wrapper

There is also a concrete DT structure defect independent of the driver-match
problem. The base board declares the label `framebuffer0` on the node
`/chosen/framebuffer@9c000000`. The historical display test instead adds a new
node named `/chosen/framebuffer0` and puts its clock and power-domain references
there. A label and a node name are different: this does not extend the original
simple framebuffer. The added node has no `compatible` or `reg`. DTC can compile
that structure without making the intended simple-framebuffer driver consume
those references.

The new
[`sm8250-lenovo-tb371fc-display-test-6.12.dts`](../../../mainline-port/backports/linux-6.12/sm8250-lenovo-tb371fc-display-test-6.12.dts)
includes the unchanged historical display test and makes three explicit changes:

- Remove only its unbound `/chosen/framebuffer0` node.
- Place the same 13 clock specifiers and the same MDSS power-domain specifier
  on `&framebuffer0`, the existing simple-framebuffer node.
- Set `stdout-path = &framebuffer0`, which DTC resolves to the node's absolute
  path, rather than depending on a string being interpreted as an alias.

The wrapper also labels its model as a Linux 6.12 diagnostic and documents the
0002 driver prerequisite and same-SSPP multirect boundary. It preserves all
panel/touch/backlight GPIOs, supplies and mode definitions. Removing a node with
no hardware binding is not claimed as disabling or fixing any physical device.
Moving the references to their intended consumer is a structural correction;
safe splash takeover and clock/power ownership still require hardware evidence.

The separate
[`qualify_native_dt_612.py`](../../../scripts/research/build/qualify_native_dt_612.py)
requires the first qualification's successful object-build manifest. It pins the
wrapper and PHY patch hashes, reuses only that job's private source/output, and
compiles the new wrapper target. Its binary-level checks require exactly one
simple-framebuffer node, the expected `reg` and geometry, an absolute resolvable
`stdout-path`, absence of the orphan node, and preserved clock/domain providers
and arguments. It also compares all GPIO/supply specifiers after resolving
phandles, so a harmless phandle renumbering is not mistaken for changed wiring.
The final root-compatible list must remain `lenovo,tb371fc`, `qcom,sm8250`.

## Reproduction and evidence

The reproducible checker is
[`qualify_dt_profiles.py`](../../../scripts/research/build/qualify_dt_profiles.py).
It refuses an existing output directory, verifies the frozen manifest/config and
assembled source hashes, creates private copies of every file it changes, and
links untouched source entries read-only by convention. Kbuild receives an
independent `O=` directory. The checked original source files and frozen artifacts are
hashed before and after the run; no module-loading or device operation is part
of the script.

Inside the existing builder container:

```sh
python3 /src/scripts/research/build/run_job.py \
  --name dt-profile-qualification-reproduce -- \
  python3 /src/scripts/research/build/qualify_dt_profiles.py \
  --output /work/dtb-profile-qualification-reproduce

python3 /src/scripts/research/build/run_job.py \
  --name dt-native-612-qualification-reproduce -- \
  python3 /src/scripts/research/build/qualify_native_dt_612.py \
  --qualification /work/dtb-profile-qualification-reproduce \
  --output /work/dtb-native-612-qualification-reproduce
```

The qualification compiles both unmodified diagnostic DTs against the copied,
already-corrected base. It extracts the compiled node status/compatible values,
checks relevant driver table/configuration combinations, and reads the three
existing module aliases without loading them. It then uses `git apply --recount
--check` followed by `git apply --recount` **only in the isolated source** and
compiles `dsi_phy.o`, `dsi_phy_7nm.o`, `dpu_kms.o`, `dpu_hw_catalog.o` and
`dpu_plane.o`. The objects must be AArch64 ELF. Patch/API or compile errors are
recorded as failures, not suppressed.

The OF-table reader is deliberately scoped to the named drivers and known
configuration guards. It is not a C preprocessor, general dependency resolver or
DT schema checker. The resulting manifest records exact source hashes, table
names/entries, active ancestry, configuration and missing matches so that the
static conclusion can be reviewed without confusing it with runtime probe.

### Recorded execution

The runs used the existing `tb371fc-build-20261123` container in doesvm CT102 on
2026-11-22 UTC. The repository mount remained read-only. Main qualification:
`/work/dtb-profile-qualification-v2`, tmux window `@48`, persistent job
`/work/dt-profile-qualification-v2.{log,json}`. Its UTC start was
`2026-11-22T22:24:32.769121+00:00`; total elapsed time was **383.26 s**, exit **0**.
The longer configuration phase was an independent Kconfig-tool build/read, not a
hardware test. The resolved configuration was byte-identical to the frozen one.

| Step | Exit | Elapsed | Observed result |
| --- | ---: | ---: | --- |
| Private `olddefconfig` | 0 | 299.82 s | No `.config` change |
| Original touch/display DT targets | 0 | 35.82 s | Both DTBs produced |
| 0002 `git apply --recount --check` | 0 | 0.83 s | No application diagnostic |
| 0002 apply, private source only | 0 | 0.005 s | Six owned source files patched |
| 0003 context check only | 0 | 0.003 s | Applies after 0002; not applied |
| Five affected/related objects | 0 | 41.56 s | All identified as AArch64 ELF |

| Artifact | Size | SHA-256 |
| --- | ---: | --- |
| Original touch diagnostic DTB | 126,248 bytes | `540401ca6f4f867471b8104d855ea4addd706b0d291e7bb530fb7e57f52129e5` |
| Original display diagnostic DTB | 126,857 bytes | `c72dc90cb4597501d8ea19c69442cef739d159264b5b8fa18dc05bd383f465be` |
| 0002 prerequisite patch | 4,783 bytes | `839699e055d8959232f2912895cbd71f5fd85f3e07a1d3f033a1fd728e08ce56` |
| Main qualification manifest | 144,938 bytes | `5a277ba48186870748799b43b84e10c3fa719d6c6b178b1d14502a2a8091e5a9` |
| Corrected 6.12 wrapper source | 1,587 bytes | `8cac3ffe34d6eaf3ee43ea1c63b4395fd6a38325ccb5f289283da3e234bfe1f7` |
| Corrected 6.12 wrapper DTB | 126,861 bytes | `50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e` |
| Wrapper qualification manifest | 29,334 bytes | `cce4698ba1d97be9de6308bdb7ee1b1ec51a262fe0fef4a99921f43a4a8d961e` |

The wrapper's final job started at `2026-11-22T22:34:08.411658+00:00`, took
**3.88 s** overall and exited **0**. Its own DTC build took 3.57 s. It reused the
private output tree and did not rerun the full kernel or replace the five-object
result above. The job records are
`/work/dt-native-612-qualification-v2.{log,json}`, and its detailed output is
`/work/dtb-native-612-qualification-v2/native-dt-612.json`.

The final DTB is at
`/work/dtb-profile-qualification-v2/out/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc-display-test-6.12.dtb`.
Its only simple framebuffer is `/chosen/framebuffer@9c000000`; `stdout-path`
resolves to that same path. All 13 clock references and the MDSS domain reference
resolve to the same providers/arguments previously attached to the orphan node.
The preserved GPIO/supply checks and unchanged primary-artifact/source hashes
are recorded in the wrapper manifest.

The complete evidence is retained in
[diagnostic-dt-profiles.json](evidence/diagnostic-dt-profiles.json),
[native-dt-612.json](evidence/native-dt-612.json), and
[diagnostic-dt-execution.json](evidence/diagnostic-dt-execution.json).
The execution summary preserves every job's exit, elapsed time and log hash,
including the two early failures below. Its diagnostic scan distinguishes
Kbuild's printed shell commands containing `echo warning/error` text from actual
emitted diagnostics. The builds used the kernel's default DTC warning exclusions;
they are not a `dtbs_check` result.

Two early tool-development failures are retained. The first table parser
incorrectly required `const struct of_device_id` and exited before creating a
source overlay; Novatek legitimately uses a mutable table. The parser was fixed.
The first wrapper compile rejected a property written after `/delete-node/`;
only that statement order was corrected. Neither failure was a hardware result,
and neither changed the frozen research1 inputs or artifacts.

## Acceptance still required

Before promoting a candidate to a new complete kernel/rootfs combination,
retain explicit manifests and link/build its whole kernel and modules together.
Before calling the native-display profile functional on the tablet, require:

1. Successful binding and dependency resolution for both PHYs/hosts, DPU, panel
   and backlight halves, with inspectable ownership and error logs.
2. Full native 2944 × 1840 scanout on both halves, including both cold-start and
   inherited-splash takeover, without using simpledrm output as the success test.
3. Recorded source rectangles, SSPP/multirect allocation, format/modifier/pitch,
   DPU/DSC/CTL/INTF assignment, and both DSI links' PPS/packet timing.
4. Separate OpenGL and Vulkan rendering/presentation checks with the real target
   DRM devices and compositor. A linear diagnostic pattern or source-match audit
   cannot stand in for that result.
5. Correct 30/60/120/144 Hz modes and transitions, panel/pen interaction,
   brightness symmetry, blanking, suspend/resume and recovery, as specified in
   [acceptance.md](acceptance.md). Thresholds remain proposed until Android
   baselines and Linux measurements are obtained.

The missing private OF entries are a concrete integration defect with a
rebuildable source candidate. The remaining native-display requirements stay
open until their own evidence exists.
