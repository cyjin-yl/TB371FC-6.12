# TB371FC input and pen: stock evidence and mainline work

Status: 2026-11-23. Scope: the Lenovo TB371FC running Android 14 and
`4.19.157-perf+`, inspected without rebooting or changing drivers. The source
baseline reviewed here is upstream project commit
`d157b92721fbeeab823f56a677b3593babf3afe6`.

**The keyboard has a standard I2C-HID transport with a known board-specific
wake/reset sequence. The screen digitizer exposes a separate Novatek pen
endpoint with pressure, tilt, hover and two buttons. Both have substantial
existing port code; neither an Android capability listing nor the earlier
4.19 desktop result proves those features work on a new mainline kernel.**

The passive capture is [android-stock.json](evidence/android-stock.json),
recorded at `2026-11-22T20:30:07.299342+00:00` (2026-11-23 04:30:07 in
Asia/Shanghai). Its `getevent -lp` entries are capability listings, not
recordings of keystrokes or pen motions.

This note separates this unit's stock observations, existing project source,
and acceptance work. It does not enable either controller or promote a kernel
build. Event numbers below identify this snapshot only and must be discovered
again after reconnecting an accessory or rebooting.

## Evidence boundaries

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Stock Android sysfs, device tree and input capabilities | Actual transport, bound drivers, advertised axes and board wiring | Linux 6.12/7.x operation, event quality, hotplug or suspend behavior |
| A HID report descriptor | Advertised collections, report IDs, fields and ranges | Successful transfers, correctly timed startup or working gestures |
| Existing `0002`/`0017` patches and device tree | An implemented porting path and specific remaining review points | The contents of a previously booted binary or a current hardware pass |
| Existing V56.2/V56.3 evidence | A working downstream/vendor-kernel reference | Acceptance of the 6.12/7.x kernel, even if the userspace looks identical |
| A bounded attended trace on the selected kernel | Observed behavior for the particular action and kernel captured | Features not exercised, or behavior after another power transition |

Raw identity fields, Bluetooth addresses, serial numbers, typed text and
unrelated application data are not part of the public evidence. Read-only
snapshot collection must use an allowlist and retain per-file hashes.

## Keyboard and touchpad

### This unit's stock interface

The attached cover is reported as **Lenovo Keyboard Pack for Spinel**, HID
vendor/product `17ef:6175`, bus `0018` (I2C). Its stock path is
`soc/a94000.i2c/i2c-5/5-0060`; the device-tree child is
`/soc/i2c@a94000/mouse@60`, compatible `hid-over-i2c`. The transport is bound
to `i2c_hid`, and the HID device to `hid-multitouch`. The compound device
registers three endpoints:

| Stock endpoint | Input name | Role |
|---|---|---|
| `event3` | Lenovo Keyboard Pack for Spinel Touchpad | Pointer/contact reports |
| `event4` | Lenovo Keyboard Pack for Spinel Keyboard | Keys and keyboard LEDs |
| `event5` | Lenovo Keyboard Pack for Spinel Consumer Control | Media/system controls |

The `mouse@60` node name does not mean this is only a mouse. The HID report
descriptor is the evidence for the compound input functions.

### Captured report descriptor

The saved descriptor is **604 bytes**, with SHA-256
`92b9e225936372a521e88f217d96d5a05200c6fdc91ab07532d6e9ca9b4cd9e0`.
The offline parser independently checked that size and hash and produced
[hid-summary.json](evidence/hid-summary.json) with no structural warnings.
Its three Application collections are Digitizers/Touch Pad, Generic
Desktop/Keyboard and Consumer/Consumer Control, matching the stock endpoints.

| Direction | Report ID | Bytes, including report ID | Descriptor function |
|---|---:|---:|---|
| Input | 3 | 29 | Touchpad contacts and pointer state |
| Input | 4 | 9 | Keyboard modifier/key reports |
| Input | 5 | 4 | Twenty Consumer Control bits plus padding |
| Output | 4 | 2 | Keyboard LED fields plus padding |
| Feature | 2 | 2 | Digitizer contact-count maximum and another digitizer field |
| Feature | 6 | 5 | Four bytes on vendor usage page `0xff00`, usage `0x00c5` |

These lengths exclude the I2C-HID transport's length/header framing. No
Feature GET/SET request was sent. The existence of a Feature report says
nothing about its current values or safe write semantics.

There is **no Input report ID 6** in this descriptor. In particular, Feature
ID 6 is not evidence for the older `17ef:6127` cover's input-status protocol.
Consumer usages include `0x038e` and `0x0390`..`0x039b`; the Android capability
listing maps several to radar/sonar-related Linux key names. Those names
do not establish the physical key labels or intended actions. Compare the
exact Android keylayout and deliberately exercised keys before choosing
desktop shortcuts or a HID quirk.

The touchpad advertises four multitouch slots (`ABS_MT_SLOT` 0..3), X
0..2998, Y 0..1771, axis resolution 31, and pointer/buttonpad properties.
This is an observed Android input configuration; no gesture quality or
simultaneous-contact test was performed.

### Existing port implementation

The [board DTS](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts),
[migration notes](../../MAINLINE_V56_MIGRATION.md),
[R153 DT preparation](../../../scripts/prepare-r153-keyboard-dt.sh) and
[patch 0017](../../../mainline-port/patches/0017-hid-i2c-add-optional-wake-gpio.patch)
describe this contract:

| Parameter | Existing port value | Interpretation |
|---|---|---|
| Controller | QUPv3 SE13, I2C `a94000`, 1 MHz | Board transport; Linux adapter number is not stable |
| Address | `0x60` | Keyboard MCU's I2C address |
| HID descriptor register | `0x1` | Separate from the I2C address |
| SDA / SCL | GPIO36 / GPIO37 | QUP13 pinmux |
| IRQ | GPIO110, level low | `IRQ_TYPE_LEVEL_LOW` (DT interrupt type 8) |
| Reset | GPIO114, active low | Logical deassertion drives the physical line high |
| Wake | GPIO108, active high | An output to keep the controller awake, not an IRQ wake source |
| Settle time | 120 ms after reset deassertion | A board startup delay, not measured input latency |

The captured stock DT resolves phandle 101 to `/soc/pinctrl@f000000` and
confirms address `0x60`, descriptor register `0x1`, `mcu_resume_gpio` GPIO108
and `mcu_rst_gpio` GPIO114. It records **`interrupts = <110 0>`** and
**`post-power-on-delay-ms = <100>`**. The zero interrupt-type cell does not
prove a level-low IRQ: the shipping driver may set the trigger explicitly.
The existing port's level-low IRQ and 120 ms post-reset delay are therefore
inherited port decisions, not byte-for-byte confirmations from this capture.
The two delays also apply to different points in the sequence.

Both stock legacy MCU GPIO properties contain flag zero. Those raw flags
cannot be copied directly into the descriptor-based reset binding to infer
physical reset polarity; inspect how the stock code drives the pins. Do not
transfer adapter numbers or phandle values between the stock and mainline
trees. The snapshot also shows `power/wakeup=enabled` on the Android I2C
keyboard device; this is a policy flag, not a successful system-wake test.

Patch 0017 extends `i2c-hid-of` with an optional `wake-gpios` descriptor. Its
power-up order is supply enable and any power-on delay, **wake assertion,
reset deassertion**, then the post-reset delay. Power-down asserts reset,
deasserts wake and disables supplies. Its rationale records that this cover
does not answer at `0x60` without the wake/reset sequence. That is a concrete
board requirement, not a reason to implement a new HID protocol.

The parent controller's interconnect properties and TLMM reserved ranges were
changed by the historical R153 experiment to fit that experiment's missing
providers. Those edits are not a universal recipe: the production target
kernel must be checked for the actual interconnect providers and pin owners.

### Reusable mainline HID support

The reviewed Linux upstream
[I2C-HID OF transport](https://github.com/torvalds/linux/blob/master/drivers/hid/i2c-hid/i2c-hid-of.c)
already handles the HID descriptor register, supplies and reset sequencing.
Its reviewed version lacks the project's optional wake GPIO extension.
[hid-multitouch](https://github.com/torvalds/linux/blob/master/drivers/hid/hid-multitouch.c)
has generic matches for both ordinary and Windows 8-style multitouch HID
groups, including any vendor/product ID. No `17ef:6175`-specific quirk was
found in the reviewed `hid-multitouch.c`, `hid-ids.h` or I2C-HID core table.
The absence of a dedicated entry therefore does not by itself indicate a
missing driver. The descriptor and runtime reports must establish whether a
new quirk is required.

Upstreaming still needs binding review, a device-specific compatible if
requested by maintainers, documented wake/reset timings and demonstrated
behavior for devices that omit the optional GPIO. Patch 0017's wake line
does not by itself add system wake-on-key support, attachment detection or a
hotplug state machine.

The pinned downstream `i2c-hid-core.c` also contains a report-ID `0x06`
cover-status path, but it explicitly matches **17ef:6127**, not this unit's **17ef:6175**. Its attachment handling, battery/pairing messages and
`kb,output-gpio` logic are comparison material only. Do not apply that
protocol or its side effects to Spinel without exact-device evidence.

### Keyboard acceptance work

1. Start with the cover attached and prove an actual `hid-multitouch` bind,
   expected report descriptor hash and three usable input functions.
2. Test modifiers, key rollover, media keys, LED output, pointer buttons,
   two-finger scrolling and gestures with a short deliberate test sequence.
3. Detach while a key or contact is active; verify releases, no stuck input
   and no interrupt storm. Reattach and verify enumeration and events.
4. Test a boot without the cover, then attach it after userspace starts.
5. Once platform suspend is independently working, test cover-attached and
   cover-detached suspend/resume. Record whether keyboard wake is supported
   separately from whether input resumes after another wake source.

The current source and earlier vendor-kernel success make these reasonable
tests; they are not recorded as passes in this investigation.

## Touchscreen and inking

### This unit's stock interface

The Novatek controller is the SPI child `/soc/spi@880000/novatek@0`. Upstream
SM8250 labels this controller `spi14` (QUP wrapper 2, SE0), matching the
project's `&spi14` node. Its DT
contains `novatek,pen-support` and `novatek,stylus-resol-double`. The kernel
registers `NVTCapacitiveTouchScreen` (`event8` in this snapshot) and a distinct
`NVTCapacitivePen` (`event9`). The pen advertises:

| Capability | Stock advertised range / keys |
|---|---|
| Position | `ABS_X` 0..18400; `ABS_Y` 0..29440 |
| Pressure | `ABS_PRESSURE` 0..4095 |
| Tilt | `ABS_TILT_X` and `ABS_TILT_Y`, -60..60 |
| Hover | `ABS_DISTANCE` 0..1 |
| Tool/contact/buttons | `BTN_TOOL_PEN`, `BTN_TOUCH`, `BTN_STYLUS`, `BTN_STYLUS2` |

These ranges prove the Android input ABI and are useful acceptance targets.
The stock pen X/Y resolution metadata is zero; it is not a physical-area
measurement. The separate touchscreen advertises ten slots, touch-major
0..255 and `ABS_MT_PRESSURE` 0..1. The latter is a binary advertised range,
not the pen's 0..4095 pressure range.

The snapshot does not establish observed pressure samples, calibrated tilt,
low latency, palm rejection or pen identity.

### Existing patch 0002

[Patch 0002](../../../mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch)
and [the touch-port notes](../../TOUCH_PORT.md) contain the Novatek SPI port.
The exact TB371FC adaptations include the NT36532 memory maps and chip ID,
firmware transfer changes, board-selected BOE/Tianma firmware, 108-byte touch
reports and a 10x coordinate scale. The DTS explicitly sets
`novatek,super-resolution = <10>`; copying only `stylus-resol-double` would
produce the wrong range with this implementation.

The current parser uses byte 66 as the pen format ID. Format `0x01` reads
X/Y, pressure, tilt, hover distance and two button bits from the remaining
pen fields, then reports a separate pen input frame. Format `0xff` releases
the pen state. The battery byte is parsed but its publication remains a TODO;
format `0xf0` is reserved for a pen ID report and is not exposed. These are
source-level observations, not verified raw-SPI traces from this unit.

For the reviewed code, super-resolution takes precedence over the
`stylus-resol-double` branch when advertising pen X/Y limits. That agrees
with this unit's 18400x29440 ABI when base geometry is 1840x2944. Pen tilt is
stored in signed 8-bit variables and reported separately from pressure and
contact state.

The normal board DTS keeps SPI14 and its touchscreen child disabled; the
separate `sm8250-lenovo-tb371fc-touch-test.dts` is the diagnostic enablement.
Do not change the normal tree solely because a snapshot matches the expected
hardware. Reset polarity, firmware choice and the actual target-kernel
interrupt path still need a controlled runtime test.

### Specific review gaps

| Gap found in current source | Consequence / next evidence |
|---|---|
| Pen physical-size defaults are 148x237 mm | `input_abs_set_res()` uses these defaults, whereas patch 0001 and the TB371FC panel backport specify 274x171 mm in landscape. This is an internal source inconsistency. Confirm the active area and portrait/landscape axis mapping before using 171x274 mm for pen resolution; preserve the absolute coordinate range. |
| Touch IRQ trigger is assigned from the driver's `INT_TRIGGER_TYPE` constant | The snapshot confirms IRQ GPIO68 and reset GPIO56; the legacy IRQ property carries raw flags `0x2001`, whereas reset carries zero. These are vendor properties. Compare driver handling and configured IRQ type before translating them to standard GPIO/interrupt bindings. |
| Touchscreen pressure ABI differs from the snapshot | Patch 0002 advertises `TOUCH_FORCE_NUM=1000`; this Android kernel advertises finger pressure 0..1. The pen pressure range agrees. Check firmware-report semantics and desired userspace ABI rather than treating touch pressure and pen pressure as the same field. |
| `gpiod_to_irq()` is checked with `if (client->irq)` | A negative error is nonzero. A future driver change should reject errors explicitly before requesting the IRQ and preserve probe-defer behavior. This is a static review finding, not an observed device failure. |
| `pen_is_charge` is initialized false; no CTN730 integration is shown | Dock charging state and any charge-time input suppression are not implemented just because the parser tests this flag. |
| Pen battery parsing is not connected to a published interface | A parsed battery byte does not provide desktop battery reporting. Its units and semantics need evidence. |
| The pinned downstream Novatek source enables a 65-byte point checksum and Spinel `NVT_DPR_SWITCH` handling, absent from patch 0002 | Its header sets `POINT_DATA_CHECKSUM=1`, `POINT_DATA_CHECKSUM_LEN=65`, `NVT_DPR_SWITCH=1`, but `CHECK_PEN_DATA_CHECKSUM=0`. Compare this with the shipping build and observed packets before porting validation/mode handling. Do not claim the downstream pen checksum is enabled. |
| No attended mainline pen trace is attached here | Pressure, hover, tilt, both buttons, edge accuracy, rotation and palm rejection remain acceptance work. |

This change deliberately records these review findings rather than changing
the kernel patch without a target build or the required runtime evidence.

## Pen and display-mode coupling

The selected Tianma node in the sanitized Android capture contains four
`qcom,mdss-dsi-dispparam-pen-<rate>hz-command` tables. See the
[display investigation](display.md) and its
[decoded evidence](evidence/display-summary.json) for command framing and the
separate native-display blockers.

| Pen-related table name | Ordered DCS payloads in the captured DT |
|---|---|
| `pen-30hz`, `pen-60hz`, `pen-120hz` | `ff 10`, `fb 01`, `b3 40` |
| `pen-144hz` | `ff 10`, `fb 01`, `b3 00` |

Each table is marked `dsi_lp_mode`. The display source audit found no
corresponding `b3` write in the reviewed TB371FC native initialization
sequence. This is evidence of a **missing comparison/transition contract**:
pen behavior and display-rate handling should not be accepted independently.
The property names and byte difference do not establish register semantics,
prove Android executed a table during this snapshot, or guarantee successful
144 Hz inking. They are not instructions to issue these writes on the live
Android device.

After native display startup is independently stable, acceptance should
exercise hover, tip contact, pressure, tilt, both buttons and palm contact
at each proven display mode. Record the actual DRM mode alongside the input
event timestamps; do not infer physical display refresh or pen sample rate
from a mode name. Test mode transitions with the pen hovering and in contact,
then lift it and verify all contact/tool/button releases. Include blank/unblank
and subsequent firmware reinitialization because the existing R226 path
already couples panel startup to a Novatek refresh. Only extend this matrix
to 144 Hz once that display mode and the intended pen-table behavior have
been demonstrated. This investigation performed none of these active tests.

## Three distinct pen paths

The connected Bluetooth accessory advertises **Lenovo Precision Pen 3** and
HID `17ef:612b`, with Mouse and Consumer Control collections. Older project
documents use the accessory name AP500U. Keep both names as recorded evidence;
do not infer that every accessory sold under either name is electrically or
firmware-identical.

| Function | Evidence and implementation boundary |
|---|---|
| Screen coordinates, pressure, tilt and hover | Arrive through the Novatek SPI digitizer and `NVTCapacitivePen`. Bluetooth pairing is not an inking acceptance test. |
| Bluetooth mouse/consumer actions | Separate Bluetooth HID reports. Enumerated functions need their own deliberate button tests and mappings. |
| Magnetic attachment, charging and charging telemetry | Separate NXP CTN730 controller path. Neither working Bluetooth nor valid inking proves charging. |

The vendor-derived overlay described in the existing project places
`nxp,ctn730` at I2C address `0x28`, with reset GPIO84, enable GPIO160 and IRQ
GPIO111. The documented board moves QCA6390's PCIe wake to GPIO81 to free
GPIO84. This unit's snapshot confirms the exact DT child
`/soc/i2c@984000/ctn730@28`, bound at `0-0028` to driver `ctn730`, and those
three GPIO numbers. Its interrupt tuple is `<111 0>`; that tuple alone does
not establish the runtime trigger type. This proves enumeration and binding,
not an observed charging cycle. No usable upstream CTN730 driver has been identified in
this investigation, and the current normal DTS does not implement charging.
However, the pinned community downstream tree contains
[`drivers/misc/ctn730/`](https://github.com/tb371fc-desktop/linux-android-msm-lenovo-p12/tree/7709a49f1a5db75b68ea8b35f6d46e0d945c572d/drivers/misc/ctn730),
including `CTN730_i2c.c`, `ctn730.c` and headers. Its Makefile selects
`CTN730_i2c.o` only when `CONFIG_NXP_VERSION=y`; otherwise it selects
`ctn730.o` plus `crc32.o`. These are alternative implementations, not two
drivers to bind simultaneously. This is a concrete source
starting point; it is not proof that the code matches this unit's shipping
binary or is ready for a modern kernel.
GPIO84 is not a spare pin to experiment with.

The reviewed `ctn730.c` publishes cached `charge_state`, `level`, `attached`
and `status` getters and an attachment notifier chain. Those are useful
reference interfaces for a port. Its `mac` attribute exposes an identifier;
its apparently read-only `cn_test` getter calls an active controller test.
Do not bulk-read every sysfs attribute. Only the four cached getters above
are candidates for a passive capture after verifying the running driver
matches this interface. The code also depends on legacy GPIO and a vendor
DRM-panel notifier, so copying the directory into a new kernel is not a
complete port.

Porting work should first identify the exact vendor driver and userspace
interface, then document packet framing, power/reset timings, interrupt
acknowledgement, charging limits and completion/fault states. A register dump
or write to an unidentified bus is not a substitute for that provenance.

## Source provenance

The [touch-port document](../../TOUCH_PORT.md) credits cleaned Novatek SPI
work from SM8150-mainline, including commits
`7514687cf6dbf1ab6beac2d8f4c01aff48cf41a0`,
`25aa7c55b4f7f1e8745271705e5cbe1a933abaa3` and
`f16d6f0a1f8d19d9017485b81914e46cd130c17c`. It attributes TB371FC packet
layout, geometry, memory maps and firmware selection to the community
[Lenovo-derived source tree](https://github.com/tb371fc-desktop/linux-android-msm-lenovo-p12).
This attribution must not be rewritten as a verified complete OEM source
release. As checked on 2026-11-23, that repository defaults to
`tb371fc-desktop-linux-6.12` at
`be75653d3ca56f010b5f419edd6c4ea51ccdc2a8`, while its `tb371fc` branch points to
`7709a49f1a5db75b68ea8b35f6d46e0d945c572d` and `tb371fc-desktop-linux` points to
`bf6d1ec43ec1ae2781351cb5179ff73793e441a3`. A link to its default branch is
therefore not a pinned downstream reference. Pin the donor commit and paths
when importing or comparing code. On the pinned `tb371fc` commit,
[Novatek source](https://github.com/tb371fc-desktop/linux-android-msm-lenovo-p12/tree/7709a49f1a5db75b68ea8b35f6d46e0d945c572d/drivers/input/touchscreen/nt36xxx)
and the CTN730 source cited above are present; their directory spelling differs
from `NT36XXX_SPI` in the default 6.12 branch.

The existing [migration document](../../MAINLINE_V56_MIGRATION.md) records
the downstream keyboard runtime result and the later GPIO/IRQ port. The
[hardware matrix](../../HARDWARE_MATRIX.md) and touch notes distinguish
compile-only work from earlier vendor-kernel hardware results, although
their kernel/version narratives are historical. Keep new evidence scoped to
the actual `uname`, build identity, DTB and patch hashes tested.

## Offline descriptor inspection

[`scripts/research/hid_report.py`](../../../scripts/research/hid_report.py)
parses a saved descriptor using only the Python standard library:

```sh
python3 scripts/research/hid_report.py keyboard-report-descriptor.bin
python3 scripts/research/hid_report.py keyboard-report-descriptor.base64 --format base64
```

It emits a descriptor checksum, application collections, per-report bit
lengths and field usage/range metadata. It never opens an event device or
replays reports. Raw bytes, string indices, opaque long-item payloads, file
paths, Bluetooth addresses and serial values are omitted from the output.
Unsupported delimiter semantics produce a warning; malformed/truncated items
are rejected. A successful parse establishes descriptor structure only.

## Minimal additional read-only evidence

1. The `17ef:6175` descriptor, hash and allowlisted bindings are captured.
   Keep this baseline for comparison with a future target kernel; omit
   `uniq` and device identifiers from further captures.
2. The keyboard, Novatek and CTN730 properties and GPIO-controller phandles
   are captured. A targeted read of the configured IRQ type and the exact
   keyboard keylayout can resolve the remaining trigger/mapping questions.
3. Seven target-only `getevent -lp` capability listings are captured. No
   ordinary user-input stream was recorded; preserve that distinction.
4. CTN730 enumeration and binding are captured. Only a verified cached-state
   getter should be added to passive telemetry; do not issue I2C reads/writes,
   reset the controller, read its active-test attribute or toggle charging.
5. If an attended trace is needed, use a bounded duration and an agreed test
   action. Tag every trace with the actual kernel and test context. Keep raw
   typed events private; publish only purpose-specific sanitized results.

No bootloader operation, module rebinding, pinmux change, firmware upload or
charging-control change is required to collect these items.
