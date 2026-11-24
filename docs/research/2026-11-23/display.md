# TB371FC display: Android evidence to native DRM mapping

Date: 2026-11-23 (Asia/Shanghai). Source baseline:
`d157b92721fbeeab823f56a677b3593babf3afe6`.

## Result and evidence boundary

The present work is an **offline source audit against a passive capture from
the owner's running Android system**. The capture confirms the Tianma panel
configuration and all 86 vendor initialization payloads in the existing
6.12 panel source. It also exposes three concrete differences that need review:
DSC slices per packet, the power-down command state/delays, and panel-side
pen commands for different refresh rates. It does not establish that native
DPU/DSI scanout, a particular refresh rate, suspend, or recovery works on this
tablet. No display register,
backlight, global tracing configuration, SELinux policy, boot image, or
partition was changed by this investigation. The wider
[research record](README.md) includes bounded Android traces in private
tracefs instances, with their cleanup and unchanged global settings recorded
separately; this display comparison uses the passive DT/sysfs capture.

The evidence is [android-stock.json](evidence/android-stock.json), captured
at **2026-11-22 20:30:07 UTC / 2026-11-23 04:30:07 Asia/Shanghai**. It preserves
raw DT properties as base64 with individual byte lengths and SHA-256 hashes.
[display-summary.json](evidence/display-summary.json) records the decoded
display fields and command comparison; every decoded command property was
checked against its captured length and hash. No refresh-rate transition was
performed during this capture.

Three different evidence classes must remain separate:

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| This tablet's Android DT/sysfs snapshot | Tianma selection, two-link configuration, base timing, ON/OFF/pen table bytes, and advertised modes | Active refresh, runtime DSC PPS, actual regulator state, or mainline support |
| Existing source and historical port notes | Concrete board wiring, candidate command tables, and prior experiments exist | That every candidate was in the installed R226 image, or works on this tablet |
| R226 project report | The author's installed profile reached a desktop and working touch | Complete native display initialization, all four advertised modes, or suspend |

The November [installation status](../../INSTALL_CURRENT.md) and
[R226 record](../../../experimental/r226/README.md) take precedence over the
"current candidate" paragraph in [PANEL_PORT.md](../../PANEL_PORT.md), which
starts with an older 7.1.7/7.1.8 experiment. The exported
[6.12.114 diff](../../../experimental/community-handoff/reference/kernel-6.12.114/working-tree.patch)
is a working-tree snapshot, not a manifest proving the contents of R226.

## Current-device evidence

The boot selector is
`qcom,mdss_dsi_panel_spinel_tianma_nt36532_dsc_3k_video:`. It resolves to
`/soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_panel_spinel_tianma_nt36532_dsc_3k_video`.
There is **one captured base timing**, its
`qcom,mdss-dsi-display-timings/timing@0` child. A four-element DFPS list does
not mean four independent DT timing nodes exist.

| Captured item | Value | Interpretation |
| --- | --- | --- |
| DRM connector | `card0-DSI-1`: connected, enabled, DPMS On | Android connector state at capture |
| Advertised mode names | `2944x1840x120x375888vid`, `2944x1840x144x375888vid`, `2944x1840x60x375888vid`, `2944x1840x30x375888vid` | Mode names; neither an active-mode report nor an FPS measurement |
| Controller / PHY selection | `[0, 1]` / `[0, 1]`; panel count 2; broadcast and synchronized-command properties present | Configured dual-link topology, not measured synchronization |
| Base timing per link | 1472 x 1840 at nominal 120 Hz; HFP/HBP/HSW = 201/60/12, VFP/VBP/VSW = 26/182/2 | Matches the checked-in 120 Hz candidate's dimensions and porches |
| DT panel clockrate | 1,130,000,000 | Requested DT value; actual clock was not read |
| DSC | Version `0x11`, SCR 0, 8 bpc, 8 bpp, block prediction, 736 x 20 slice, **one slice per packet** | Concrete packetization reference; complete PPS remains missing |
| DFPS | `[120, 144, 60, 30]`; `dfps_immediate_porch_mode_vfp` | Declared strategy; runtime 144 Hz transition remains unresolved |
| Reset | TLMM GPIO69, raw GPIO flags 0; levels/waits `[1,10,0,10,1,10,0,10,1,10]` | Physical high/low/high/low/high, 10 ms each in the vendor table |
| ON / OFF tables | 800 bytes / 88 records, LP; 18 bytes / 2 records, HS | Decoded and compared below |
| Backlight snapshot | brightness 294, maximum 2047, `actual_brightness=0`, `bl_power=0` | The getter result alone does not establish that the panel is dark |

Both captured PHY nodes have identical 20-byte lane configuration:
`00000a0a 00000a0a 00000a0a 00000a0a 20008a8a`.
The panel's 14-byte PHY timing property is
`00250a0a1b180a0a0a0204001f0f`. These are preserved reference bytes, not a
claim that they can be written unchanged into mainline PHY registers.

## Android-to-mainline mapping

The Android column now uses the captured DT/sysfs values. Native-Linux
entries refer to the source baseline; runtime equivalence is still untested.

| Android/vendor item | Existing native-Linux implementation | Exact comparison still required |
| --- | --- | --- |
| Selected `spinel_tianma_nt36532_dsc_3k_video` panel | `lenovo,tb371fc-tianma-nt36532`; `tb371fc_tianma_desc` and `tb371fc_nt36532_init_sequence(..., false)` | Selector resolved and ON/OFF hashes recorded; fitted revision and runtime transactions remain unknown |
| One 2944 x 1840 landscape scanout | One DRM connector/panel with two bonded DSI hosts | Android may expose a portrait logical coordinate system; keep rotation separate from link geometry |
| Two 1472 x 1840 DSI links, four lanes each | Both DSI endpoints; DSI0 master; `qcom,dual-dsi-mode` and `qcom,sync-dual-dsi`; DSI1 shares DSI0 byte/pixel PLL parents | Read both physical controllers' active timings and command synchronization state |
| DSC 1.1, 8 bpc, 8 bpp | Shared `drm_dsc_config`, full picture 2944 x 1840, slice 736 x 20, `.slice_count = 2` | In this implementation the count is per link: four slices across the whole picture. Verify every consumer uses the same convention |
| Vendor compressed transport: one slice per packet | `dsi_update_dsc_timing()` and DPU INTF width | Existing export groups both slices; see D1 |
| Vendor ON table: 86 vendor writes plus two standard commands | Explicit LP DCS long writes, dual PPS, Sleep Out, then Display On | Vendor payloads match; full PPS, runtime synchronization and OFF policy still need comparison |
| Reset GPIO69; physical 1/0/1/0/1 with 10 ms waits | Active-low descriptor; physical high/low/high/low/high, approximately 10 ms at each stage | Source sequence agrees after accounting for polarity; actual rail/host/reset order is unmeasured |
| DSI PHY v4.0 electrical settings | Board-specific `lenovo,tb371fc-dsi-phy-7nm` path and analog-value backport | Compare both hosts' lane configuration and PHY revision; preserve board scoping |
| KTZ8866A/B at I2C 0x11 on `i2c@994000` / `i2c@a8c000`; shared GPIO54/77/78 | `tb371fc-ktz8866.c`, one logical backlight, mirrored brightness/enable writes | DT nodes and enables are captured; transaction/brightness symmetry is untested |
| AVDD/LCDB, I/O/PHY rails and enable GPIOs | RPMh supply references; display-test pinctrl drives GPIO33/54/77/78 high | Establish dependency ordering, actual enabled state, and cold-start versus inherited-splash behavior |
| Dynamic FPS plus four `dispparam-pen-*-command` tables | Four advertised `drm_display_mode` entries | No matching TB371FC pen-refresh dispatch located; see D6; switching/blanking/suspend untested |

Relevant implementation sources:

- [6.12 panel driver](../../../mainline-port/backports/linux-6.12/panel-novatek-nt36523.c)
- [Base board DTS](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts)
- [Native display test DTS](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc-display-test.dts)
- [Dual KTZ8866 driver](../../../mainline-port/backports/linux-6.12/tb371fc-ktz8866.c)

A public Android-side reference was additionally inspected at
[`smith-dog/kernel-tb371fc` commit `c3df39c507c11eebb124224bd34e3ab701b6d1f3`](https://github.com/smith-dog/kernel-tb371fc/blob/c3df39c507c11eebb124224bd34e3ab701b6d1f3/techpack/display/msm/dsi/dsi_panel.c).
Its `dsi_panel_parse_dsc_params()` reads the DT slice-per-packet value, and
`dsi_dsc_pclk_param_calc()` derives `bytes_per_pkt` and `pkt_per_line` from it.
Its `dsi_panel_create_cmd_packets()` copies header byte 3 into the full
`msg.flags` field and byte 4 into the delay; the offline decoder therefore
retains the raw flags rather than assuming that byte means only ACK. This is
a source reference, **not a demonstrated source match for the running Android
kernel**; build identity and binary matching are separate evidence.

## Timing and DSC invariants

The source declares the following timing model. Pixel clocks are calculated
from its integer totals; they are not measured clocks and are not performance
claims.

| Advertised refresh | Full horizontal total | Vertical front porch | Vertical total | Full uncompressed mode clock |
| ---: | ---: | ---: | ---: | ---: |
| 120 Hz | 3490 | 26 | 2050 | 858,540,000 Hz |
| 144 Hz | 3490 | 26 | 2050 | 1,030,248,000 Hz |
| 60 Hz | 3490 | 2076 | 4100 | 858,540,000 Hz |
| 30 Hz | 3490 | 6176 | 8200 | 858,540,000 Hz |

The horizontal model is twice `(1472 + 201 + 12 + 60)`. Vertical sync and
back porch are 2 and 182 lines. Thus this source makes 30/60/120 share a nominal
pixel clock and change vertical blanking; its 144 Hz entry requires a different
clock. The captured Android DT instead declares VFP-based dynamic FPS from
one 120 Hz timing. At the stated base clock, scaling 2050 lines by 120/144
would leave fewer lines than the active height plus fixed sync/back porch.
Consequently, the 144 Hz path cannot be reconstructed from that simple formula
alone. Actual Android mode construction and clock changes must be inspected;
do not invent a negative porch or assume that advertised 144 Hz was exercised.

At 8 bpp, each 736-pixel DSC slice has a nominal 736-byte chunk. One link
contains 1472 compressed bytes per line. The DSI RGB888 transport needs
`ceil(1472 / 3) = 491` pixel-clock units; truncation gives 490. The existing
[round-up patch](../../../mainline-port/backports/linux-6.12/0011-dpu-dsc-intf-width-round-up.patch)
addresses this concrete DPU/DSI disagreement. It should be retained or replaced
by an equivalent upstream fix in a selected baseline, not confused with the
separate slices-per-packet question.

Using the repository's compression/blanking model gives approximately
1,127,664,000 bit/s per lane for 30/60/120 and 1,353,196,800 bit/s for 144.
These are **derived candidates**. The 120 Hz candidate is about 0.207% below
the captured `panel-clockrate` value of 1,130,000,000. That arithmetic proximity
does not prove clock equivalence. Actual clock summaries and PHY programming
were not captured.

The PPS comparison must cover all 128 bytes, including initial transmit/decode
delay, rate-control thresholds/ranges, offsets and scale intervals. Matching
resolution, bpp and slice dimensions alone is insufficient. The panel driver
already refuses preparation when several computed DSC fields are zero; that
guard proves population, not agreement with Android.

## Concrete source gaps

### D1 — Exported packetization disagrees with this tablet's Android DT

The captured `timing@0/qcom,mdss-dsc-slice-per-pkt` is exactly **1**,
consistent with `PANEL_PORT.md`. In contrast, the 6.12.114 working-tree diff
changes:

- `bytes_per_pkt` from one chunk to `slice_chunk_size * slice_per_intf`;
- `pkt_per_line` from `slice_per_intf` to `1`;
- command-mode word count from one chunk plus one to all link chunks plus one.

For the stated two-slice link this changes transport grouping, even though
the total compressed bytes per line remain 1472. The export retains a nearby
comment claiming only `slice_per_pkt = 1` support. This is an actionable
source/documentation inconsistency, **not proof that the change caused the
author's right-half corruption**.

Remaining evidence: both DSI controllers' compression/packet registers if
already exposed by a
known read-only debug interface, and the corresponding Android parser and
programming function. Select one packetization contract and document its
hardware result. Do not import this global DSI change into an upstream patch
without parameterization and a justification for affected devices.

### D2 — The repository contains competing CTL ownership models

The historical [0010 topology patch](../../../mainline-port/backports/linux-6.12/0010-dpu-dsc-keep-bonded-intf-count.patch)
reserves two interfaces/CTLs. The [0012 ownership patch](../../../mainline-port/backports/linux-6.12/0012-dpu-dsc-per-ctl-ownership.patch)
assigns and flushes one DSC through each physical encoder's CTL. Later
[R146](../../../scripts/apply-r146-single-ctl.py) uses one ACTIVE_CFG CTL for
both interfaces and adds `CTL_INTF_MASTER`. The exported 6.12.114 tree contains
yet another combined implementation with shared-CTL assignment, per-physical
DSC selection, and altered slave-interface flushing.

These files describe different experiments. They are not a patch series that
can safely be stacked. Reconstruct the chosen tree, then inventory actual
LM/SSPP/pingpong/DSC/CTL/INTF allocation and flush ownership. Compare the
Android configuration at an equivalent mode. A missing slave flush, incorrect
master selection, or resource assignment is a hypothesis until that
comparison is recorded.

### D3 — Full-width source fetch and DSC topology are separate problems

The 7.1-specific [linewidth quirk](../../../mainline-port/patches/0016-drm-msm-dpu-add-tb371fc-linewidth-quirk.patch)
sets a board catalog limit of 1880 pixels to trigger upstream plane splitting.
The latest exported 6.12.114 diff instead changes generic SM8250
`max_linewidth` from 4096 to `DEFAULT_DPU_OUTPUT_LINE_WIDTH`.

Neither form by itself establishes the resulting source-pipe allocation.
Document the chosen catalog, compiled constant, actual two-half source
rectangles, pitch, format, and mixer placement. Preserve the distinction
between source fetch splitting and DSC/DSI output splitting. The blanket
SM8250 catalog edit also needs scoping or a hardware-wide rationale before
upstreaming.

### D4 — ON payloads match; OFF state and delays differ

The checked-in 6.12 Tianma path contains 86 explicit vendor long writes plus
the two standard sleep-out/display-on commands. That agrees with the
historical 88-command count. It adds generated DSC PPS between the vendor
writes and sleep-out, and waits 120 ms then 100 ms.

The current-device ON property has SHA-256
`eb0cca9406be39a7c1934257211d0b194c8fe4f6aeca2119bce5a1b65e41d7dc`.
All **86 vendor payloads match the Tianma source in order**, without dropping
or normalizing a vendor command. Their captured headers are uniformly type
`0x39`, last=1, VC=0, raw flags=0, wait=0. The final records are type `0x05`,
payload `11 00` with 120 ms wait, and `29 00` with 100 ms wait. The source uses
the corresponding no-parameter Sleep Out and Display On helpers; the stock
table's zero padding explains the byte-length difference from a one-byte
representation. This does not establish the final wire transactions.

This removes an absent/different vendor initialization payload as a current
source mismatch. It does **not** verify the dynamically generated PPS, host
preparation, command broadcast, or the physical frame. The original
`diagnostics/v24-live-panel-dt/...` files are no longer needed to reproduce
this particular comparison.

The OFF property has SHA-256
`2c9fd13b1258217b536c969db415c4becaa18f21c3a1b10e5dd6977b5c856374`.
It is explicitly **`dsi_hs_mode`** and consists of type `0x05` Display Off
(`28 00`), **wait 15 ms**, then Enter Sleep (`10 00`), **wait 60 ms**.
The native `nt36523_disable()` sends Display Off to both hosts, immediately
sends Enter Sleep to both, and waits 70 ms at the end. The TB371FC descriptor
retains `MIPI_DSI_MODE_LPM`; this function does not switch it to HS. Thus the
source neither expresses the staged 15/60 ms waits nor the captured OFF
transport policy. This is a concrete lifecycle difference to resolve in a
board-specific change, not proof of the cause of any observed failure.

### D5 — Cold power sequencing is not modeled completely

The panel driver's ordinary prepare path enables `vddio`, resets, and sends
the table. The display-test DT separately drives several enable GPIOs high;
the backlight driver controls brightness and LED enable. Historical notes
also identify an independently disabled `display_panel_avdd` rail. This
division needs a supply/GPIO ownership and ordering audit.

The current capture resolves `qcom,panel-supply-entries` to
`/soc/dsi_panel_pwr_supply_lab_ibb`, but that provider subtree was not included.
Both PHY consumers resolve `vdda-0p9` to PM8150 L5 and request 880,000 uV,
46,000 uA enable load. Both controller consumers resolve `vdda-1p2` to PM8150
L9 and request 1,200,000 uV, 26,700 uA enable load; their `refgen` provider is
`/soc/refgen-regulator@88e7000`. These are DT consumer requirements, not
measured voltages or regulator enable counts. Both KTZ8866 nodes specify
shared HWEN/ENP/ENN GPIO54/77/78. Resolve the missing panel supply entries and
GPIO33 ownership before proposing a complete cold power sequence.

The [R180 keep-splash transform](../../../scripts/r180-panel-keep-splash.py)
skips reset, initialization, disable and unprepare. A visible result with that
option does not verify a cold native sequence, blank/unblank, or suspend.
Read regulator and clock state first, then identify how the working Android
driver acquires each resource. Do not infer required voltage from the name of
a regulator or from a DT limit alone.

The dual-backlight source also has a concrete cleanup gap: after adding a
device to the global list, a failure in the later initial brightness writes
returns from probe without removing that list entry. Device-managed storage
is then released while the shared list can still reference it. Primary probe
failure can also leave the global backlight pointer referring to released
device-managed state. Fix and review this path before treating repeated
probe/unbind as a safe recovery mechanism. This audit has not executed that
failure on hardware.

### D6 — Mode declarations are not transition coverage

The four declared modes establish proposed timings. They do not validate
30/60/120/144 transitions, panel-side switching commands, clock parent changes,
TE/ESD policy, restored brightness, or touch firmware behavior after panel
reinitialization. R226 explicitly needs a post-panel Novatek refresh for
touch; display and touch sequencing therefore must be tested together.

The current Android timing node also contains four explicit pen-related
command tables. Each is LP, three type `0x39` commands, VC=0, flags=0,
wait=0, with last-command flags 0/0/1:

| Table suffix | Ordered payloads | SHA-256 |
| --- | --- | --- |
| `pen-30hz`, `pen-60hz`, `pen-120hz` | `ff10`, `fb01`, `b340` | `f090a9a0a6d0d0dde20e84b60b767589fc420474c9528032d93fee1cccc9b28a` |
| `pen-144hz` | `ff10`, `fb01`, `b300` | `30f023a6e7b52ab12834cc823184a8863d4deef96bff68ac02a8487be3706c56` |

No corresponding write or per-refresh dispatch was located in the TB371FC
path of the checked-in native panel driver. The property names and payload
difference give a concrete display/pen integration lead. A passive DT capture
does not reveal when Android sends these tables, whether pen presence gates
them, or what the undocumented `B3` value controls. Establish the Android
dispatch condition before wiring them to every DRM mode change.

First establish one full native frame on both halves at a mode whose Android
reference was captured. Only then test a reversible transition and return to
the baseline. High refresh and power saving are later acceptance items; no
frame-rate, latency, battery-life, or thermal target is claimed here.

## Remaining read-only evidence requests

The collector must discover a path before reading an optional attribute. Save
missing/denied results as evidence; do not change SELinux or bind/unbind a
driver to make a capture succeed.

The current capture already covers the selector, connector attributes,
backlight attributes, panel/timing command properties and both controller/PHY
nodes. Do not repeat them merely to expand the evidence set. Remaining useful
reads are:

1. The resolved `/soc/dsi_panel_pwr_supply_lab_ibb` subtree and relevant
   regulator provider properties; any existing pinctrl entry owning GPIO33.
2. An existing active-mode/state interface, distinct from `connector/modes`.
   No mode switch is needed to read the currently active state.
3. Discover debugfs DRM/MDSS/DSI filenames. Read only established state and
   summary interfaces; do not read arbitrary command, register-selector,
   trace-pipe or MMIO nodes. Filter `clk_summary`/`regulator_summary` to the
   resolved display resources while retaining provider context.
4. Filter existing kernel logs for MDSS/SDE/DSI/DSC/panel/KTZ8866/LCDB/AVDD
   messages and associated errors. Exclude device/network identifiers.
5. Inventory display-related names in tracefs `available_events` and
   `available_filter_functions`, plus current tracer and enable state.
   Listing available functions does not start a trace. A future bounded
   display-specific trace needs an explicit selection and cleanup plan.
6. An existing captured/runtime PPS, if a documented read-only interface
   exposes it. Do not inject a DSI read command or arbitrary MMIO access to
   manufacture a PPS capture.

Do not run [collect-android-permissive-display.sh](../../../scripts/collect-android-permissive-display.sh)
for this request: it changes SELinux/policy and recursively reads broad sysfs
trees. Its behavior exceeds this read-only evidence task.

## Offline decoder

[display_decode.py](../../../scripts/research/display_decode.py) accepts copied
binary properties or explicit hexadecimal input. It prints JSON to stdout;
it does not send device commands, invoke another program, change a capture,
or construct a replacement PPS.

```sh
python3 scripts/research/display_decode.py commands --file captured-on-command.bin
python3 scripts/research/display_decode.py pps --file android-pps.bin --compare-file linux-pps.bin
```

The current-device vendor-payload comparison is reproducible from the
repository root (the long node path is intentional):

```sh
python3 -B scripts/research/display_decode.py commands \
  --capture docs/research/2026-11-23/evidence/android-stock.json \
  --node /soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_panel_spinel_tianma_nt36532_dsc_3k_video/qcom,mdss-dsi-display-timings/timing@0 \
  --property qcom,mdss-dsi-on-command \
  --tianma-init-source mainline-port/backports/linux-6.12/panel-novatek-nt36523.c
```

The source comparator is deliberately limited to this known C initializer
layout. It excludes the explicit BOE-only branch, preserves vendor payload
count/order, and requires the expected ON-table tail. It does not claim to be
a general C parser or to prove transport semantics from C text.

For the JSON produced by `collect_android_hardware.py`, use `--capture
hardware.json --node /the/exact/captured/node --property
qcom,mdss-dsi-on-command` in place of `--file`. The decoder verifies the
property's captured byte length and SHA-256 before parsing it. The exact node
must be selected from the capture; the tool does not guess the active panel.

The command decoder preserves the Qualcomm packet header, delay, payload and
offset and rejects truncated records. The PPS decoder requires exactly 128
bytes, reports the geometry and rate-control fields, and retains all raw bytes
for comparison. PPS field offsets follow the upstream
[Linux v6.12 DRM definition](https://github.com/torvalds/linux/blob/v6.12/include/drm/display/drm_dsc.h).
No opcode is labelled as sleep/display state without considering vendor page
context; no panel state is inferred by this decoder.

Offline validation covered a three-command synthetic stream, both truncated
header and truncated payload failures, PPS geometry/8-bpp offsets, a negative
six-bit rate-control offset, and byte-length mismatch reporting. The captured
800-byte ON and 18-byte OFF properties and all four pen command tables also
decoded successfully after hash/length checks. The ON comparison returns 86
matching vendor payloads; passing the OFF table as ON is rejected. These are
offline evidence/parser checks, not a native display hardware test.

## Reviewable completion criteria

- [x] Attach sanitized current-device evidence with collection method, timestamp
  and hashes; distinguish absent properties from parser failures.
- [x] Resolve the Tianma node, base timing and advertised mode list.
- [x] Decode the 88-command ON candidate and document OFF/pen differences.
- [ ] Compare the complete runtime DSC PPS with the selected native baseline.
- [ ] Resolve active mode/clock state and the Android 144 Hz/pen dispatch path.
- [ ] Choose one reproducible kernel/DT/module baseline; record whether it uses
  one or two CTLs, packet grouping, and splash preservation.
- [ ] Produce a source change only for an explained mismatch. Require compiled
  artifacts and a separate device result before marking any runtime item done.

No hardware experiment or native-Linux success is recorded by this document.
