# TB371FC driver roadmap: reuse upstream code, close board gaps

Date: **2026-11-24, Asia/Shanghai**. Project evidence baseline:
`ec42c48405eb3966ca2539e53d96d02a5e725059`.

This roadmap implements the direction in [MAINLINE_STRATEGY](MAINLINE_STRATEGY.md).
It does not label every driver missing and does not award new hardware passes.
Use the existing [44-case owner ledger](research/2026-11-23/acceptance.md) for
results. The classifications below describe engineering work, not readiness
to flash or a percentage of completed hardware.

## Evidence to use first

| Evidence | Identity and permitted conclusion |
| --- | --- |
| [Current owner Android baseline](evidence/2026-11-24-live-android-baseline.json) | TB371FC / spinel / ZUI16.0.474 / 4.19.157-perf+; current config, registered input interfaces and driver bindings. No physical Linux or functional input test |
| [Owner research captures](research/2026-11-23/README.md) | Exact panel selection, GPU numeric ID, HID descriptor, peripheral inventories, firmware records and bounded source/binary interpretations |
| [Pinned upstream inventory](evidence/2026-11-24-upstream-source-audit.json) | `torvalds/linux@b6a9fa34ce4187cb69d3c588a4bbffc31ce5db8f`; selected upstream source/match tables. No promise that every path is present in an older stable kernel |
| [R5 construction](research/2026-11-23/research5-services-kernel.md) | Actual Image, joint DT and 84 signed ARM64 modules, with offline signature/CRC checks. No owner native-Linux run |
| [R226 and handoff](../experimental/community-handoff/README.md) | An independent author's bounded hardware results and later failed/unrun experiments. Different unit/card/stack; not transferable owner acceptance |

The vendor DT model string is generic `kona QRD`; product properties identify
this unit as TB371FC. A DT declaration alone is weaker than an observed driver
binding, and neither proves all physical functions work. Keep those distinctions
when the vendor tree contains generic reference-board nodes.

## Platform, graphics and input

| Area / owner evidence | Existing implementation to reuse | Board-specific work and acceptance |
| --- | --- | --- |
| **Boot, CPU, memory, clocks, interconnect, interrupt and IOMMU.** Owner kernel is ARM64 SM8250; shipping kexec is disabled | Upstream `arch/arm64/boot/dts/qcom/sm8250.dtsi`, Qualcomm clocks/pinctrl/RPMh/interconnect, ARM GIC and SMMU infrastructure; the reproduced R5 source and initramfs experiments | Resolve actual loader entry and recovery; preserve correct reservations, DMA ownership, DT and early CPU state. Audit each inherited early-MMU/capability workaround before rebasing. **SYS-01, SYS-04** |
| **GPU Adreno 650.** Owner numeric chip ID is `0x06050002`; `Adreno650v3` is the vendor display name | MSM A6xx kernel catalogue and Mesa Freedreno/Turnip. That exact chip ID already exists upstream; no invented `650.3` compatible is needed | GMU/ZAP/SQE firmware, OPPs, standard Adreno SMMU, real API submission/readback, isolation, recovery and thermal behavior. R5 retains the intended SMMU references. Render-node existence or software Mesa execution is insufficient. **GPU-01–05, THERM-01** |
| **Internal panel and backlight.** Owner selected Tianma NT36532 dual-DSI; stock declares 30/60/120/144 Hz. Two KTZ8866 driver bindings were observed | Upstream SM8250 DPU/DSI, NT36523 panel-family infrastructure; the repository's exact TB371FC panel/dual-backlight implementation, board DTS and display review | Full-frame cold scanout, matching DSC/PPS and packetization, CTL ownership, both links, panel/PHY power sequence, symmetric brightness and actual transitions through every verified mode. 144 Hz is a declared mode, not measured refresh. simpledrm handoff does not complete native DSI. **DISP-01–03** |
| **Touch and native pen.** `NVTCapacitiveTouchScreen` and `NVTCapacitivePen`, SPI bus `001c`; owner capability capture records ten contacts, pressure 0–4095, tilt ±60, hover and two stylus buttons | Existing out-of-tree Novatek SPI/pen code plus compiled 0018/0019 corrections. Upstream `novatek-nvt-ts.c` instead matches I2C NT11205/NT36672A, so a same-vendor filename is not a drop-in driver | Keep the successful error/resource fixes; audit firmware bounds and WDT/ESD paths; implement/review panel-before-touch sequencing and shared mode/pen commands. Test real geometry, physical dimensions, rotations, pen latency and palm rejection. **TOUCH-01, PEN-01–02** |
| **Keyboard and touchpad.** I2C `0018`, HID `17ef:6175`, Lenovo Keyboard Pack for Spinel; 604-byte descriptor already captured | Generic `i2c-hid-of`, HID and `hid-multitouch`; existing wake-GPIO patch and joint input DT | Validate reset/wake/IRQ semantics, actual physical layout, LEDs, gestures, cold attachment, hotplug and wake/resume. Do not import the unrelated `17ef:6127` cover's report protocol. **KEY-01, PAD-01** |
| **Bluetooth pen auxiliary functions.** Current endpoints identify Lenovo Precision Pen 3 on Bluetooth `0005`, `17ef:612b` | Bluetooth/HID userspace and kernel paths once the controller works | Resolve actual auxiliary reports and controls. Keep this transport separate from NVT screen inking and magnetic charging; a Bluetooth endpoint proves neither. **PEN-04** |
| **Magnetic pen charging.** Existing owner records contain the CTN730-related board path, with no charging acceptance | Retained CTN730/stock protocol clues and existing power/input frameworks | Confirm device identity and power/IRQ/firmware contracts, define attachment/charge-state behavior and protection, then implement or adapt the exact driver. No exact upstream CTN730 implementation was established by this review. **PEN-03** |

Detailed source/evidence links:
[GPU identity](research/2026-11-23/gpu-chipid.md),
[graphics audit](research/2026-11-23/gpu-acceleration.md),
[display](research/2026-11-23/display.md),
[input/pen](research/2026-11-23/input-and-pen.md), and
[already built input fixes](research/2026-11-23/input-integration.md).

The panel and input review has already identified concrete integration work;
starting another wholesale touchscreen or GPU implementation would discard that
progress. Conversely, a successful compile of those drivers does not resolve
the full-panel, pen or suspend contracts.

## Connectivity, storage and audio

| Area / owner evidence | Existing implementation to reuse | Board-specific work and acceptance |
| --- | --- | --- |
| **Wi-Fi QCA6390.** Owner PCI `17cb:1101`, subsystem `17cb:0108`; vendor CNSS binding and cached FW `1.0.1.0.1596.0` | Upstream `ath11k/pci.c` has QCA6390 hw2.0; Qualcomm PCIe/MHI/QMI and existing stock-firmware staging | Resolve the actual board-data selector and the mainline loader's board key/API. Cached BDF version/customer/project fields are not `board_id`; do not rename an arbitrary `bdwlan.*` into `board-2.bin`. Test association, throughput, latency, reconnect, power save and coexistence. **WIFI-01–02** |
| **Bluetooth QCA6390.** Stock family and UART path already mapped; current pen endpoints are separately enumerated | `hci_qca.c`/`btqca.c` contain QCA6390 support and `qcom,qca6390-bt`; reuse the declared transport | Match controller ROM and firmware suffix, rails, enable/wake and serial flow control. Test BLE/HID/audio, reconnect and Wi-Fi coexistence. A copied firmware set is not accepted firmware. **BT-01** |
| **USB data and docking.** Owner has a known primary DWC3 controller; current transport/recovery evidence is still limited | DWC3, SM8250 QMP USB3/DP PHY and generic USB classes; existing R226/R209 board PHY/PS5169 work as a scoped reference | Both connector orientations, gadget/host roles, replug, hubs and integrity. Author R226 is peripheral/fixed orientation and only ~3–6 MB/s NCM; SuperSpeed link state is not application throughput. Keep the actual PS5169 separate from older NB7VPQ904M assumptions. **USB-01–02** |
| **DP Alt Mode and Type-C analog audio.** FSA4480 is actually bound; existing DP/redriver descriptions are source clues | MSM DP, QMP combo PHY and upstream FSA4480 mux support | Exact Type-C/mux/redriver topology, orientation and ownership; establish actual PD/alt-mode exchanges before claiming external output. The inspected upstream mux directory has no PS5169-named driver; PS8830/NB7 are not interchangeable identities. **DISP-04, AUDIO-03** |
| **UFS and microSD.** `ufshcd-qcom` is bound on Android; owner card has its own three-partition layout | Qualcomm UFS and SDHCI; board redriver/timing work and the preserved conservative profiles | Begin with matched board/clock/voltage settings and read-only diagnostics. Do not apply the author's card-identity-specific 150 MHz transition to another card. Check owned-file integrity and recovery before throughput; keep raw partition writes outside performance tests. **STOR-01–02** |
| **Speakers.** Four actual `tfa98xx` I2C bindings at `0x34–0x37`; shared cached request slot says `tfa98xx_QS.cnt` | Upstream SM8250 ASoC/DSP infrastructure plus the already built separate TFA98xx/TFA9894 prototype | Resolve exact silicon/acoustic variant, four independent container choices, TDM slots, DSP routing and full persistent-write/calibration behavior. The prototype is unsigned, unexecuted, has 35 retained warnings and is not in R5's signed runtime. The upstream `tfa989x.c` table matches 9890/9895/9897, not 9894. **AUDIO-01** |
| **Microphones and sound routing.** Owner exposes a kona sound card; WCD938x/SoundWire appear in DT and sound infrastructure | Existing upstream SM8250 machine, codec/SoundWire/Q6 paths and PipeWire/ALSA userspace | Confirm actual codec binding, physical microphone count and routing; then test every microphone, duplex/echo behavior and route changes. Generic WSA881x DT declarations do not override the four bound TFA amplifier observations. **AUDIO-02–03** |
| **FM receiver.** Earlier owner capture bound `rtc6226` and exposed `radio0` | V4L2 radio and audio frameworks, plus exact stock RTC6226 protocol evidence when available | No RTC6226-named driver appears in the inspected upstream radio directory. Determine tuning/control/audio/antenna behavior and implement the specific missing path; test reception and coexistence. Do not silently omit the fitted receiver from completion. **FM-01** |

Detailed sources:
[firmware loader contract](research/2026-11-23/firmware-kernel-contract.md),
[radio board selector](research/2026-11-23/radio-board-selection.md),
[owner USB/entry readiness](research/2026-11-23/boot-readiness.md),
[current peripheral inventory](research/2026-11-23/android-peripheral-inventory.md),
[TFA cached metadata](research/2026-11-23/tfa9894-cached-metadata.md), and
[TFA prototype](research/2026-11-23/tfa-module-prototype.md).

The shared QS slot is registered before asynchronous firmware-load completion.
It is useful request-selection evidence, not proof of all four amplifiers'
successful load, calibration or physical supplier. Preserve both its positive
observation and those limits when preparing an audio candidate.

## Power, cameras, sensors and newly observed functions

| Area / owner evidence | Existing implementation to reuse | Board-specific work and acceptance |
| --- | --- | --- |
| **Fuel gauge.** Current I2C device `mm8013c06` is bound to `mm8013` at `0x55` | Upstream MM8013 power-supply driver and the existing board integration | Confirm binding differences, units, signs, counter semantics and trends against controlled stock measurements. Gauge telemetry does not implement a charger. **PWR-01** |
| **Charging, Type-C/PD and charge pump.** PM8150B/SMB5 configuration; current `smb1396` child is bound under the name `qcom,smb1398-charger` | Upstream PM8150B TCPM/Type-C support, power-supply framework and retained R227–R241 observations | Establish the exact charger/charge-pump variant and registers, input policy, thermal/JEITA/watchdog behavior and one owner for each control path. Inspected `qcom_smbx.c` matches PMI8998/PM660; it does not prove PM8150B/SMB5 or SMB1396 support. Existing polling helpers are reference code, not a complete charger. **PWR-02–03** |
| **Suspend, runtime power and thermal.** Owner Android advertises idle/sleep states and has bounded CPU/GPU power traces | RPMh, cpuidle/cpufreq/devfreq, thermal, remoteproc and per-device runtime/system PM | Measure actual sleep residency, wake sources and rail/device restoration. Test with display/pen/keyboard/radios attached, and match Android conditions. A blank screen or successful suspend callback does not prove whole-system low power. **PM-01–02, THERM-01** |
| **Cameras.** This owner's passive inventory confirms rear/front roles and limited metadata; silicon/module variants remain unresolved | Upstream SM8250 CAMSS/CCI, V4L2 and libcamera; repository S5K4H7 prototype only if the exact fitted module is confirmed | Determine exact sensors, actuator, flash, EEPROM/calibration, clocks, rails and CSI topology. Earlier author's S5K4H7/HI1339 names and generic `cam-sensor` nodes are not sufficient. Validate streaming and image quality, not merely sensor-ID/driver probe. **CAM-01–02** |
| **Video codec.** Android exposes vendor `msm_vidc` interfaces | Existing upstream `qcom,sm8250-venus` implementation and recorded firmware staging | Match firmware/secure-memory/power dependencies, enable the intended DT and test native decode/encode formats through actual applications. GPU-rendered 1080p playback is not hardware decode. **VIDEO-01–02** |
| **Motion, magnetic, ambient/RGB and Hall.** Owner HAL names `icm4x6xx`, QMC630x, TCS3408 and BU52053NVX; current PMIC ADC IIO entries are separate | Existing IIO/input frameworks, relevant ICM-family candidate drivers and Qualcomm DSP/remoteproc infrastructure | Verify exact part revisions and whether access is direct or through the sensor DSP; determine calibration, orientation, timestamp and wake semantics. The author's BMI3x0 inventory must not replace this unit's `icm4x6xx` evidence. A family driver on another bus cannot bypass unimplemented SSC transport. **SENS-01–02, SWITCH-01** |
| **Fingerprint and haptics: new platform leads.** Current Android capture shows `soc:goodix_fp` bound to `goodix_fp` and an input named `qti-haptics` | Existing input/haptic and platform frameworks; exact-device code/protocol must be identified | Registration alone does not establish physical sensor revision, secure-world transport or usable functions. Extend **SYS-02** inventory and add dedicated acceptance cases when the fitted functions are confirmed; do not collect biometric templates or assume these are already covered by the older 44 cases |

The [owner power report](research/2026-11-23/power-management.md) recorded
`real_type=USB_HVDCP_3` with **`pd_active=0`**, despite abstract `USB_PD`
labels. Preserve that difference. A working fixed 5 V sink, a USB PD contract,
HVDCP fast charging and a switched charge pump are different capabilities.
Changing a displayed type string or repeatedly servicing a watchdog is not
equivalent to reproducing the stock charging stack.

R231 and TCPM must not concurrently own charging/Type-C registers. Integrate
policy through normal kernel subsystems, with explicit ownership of limits,
reconnect and fault handling. Keep stock protections while measuring the
actual negotiated protocol and battery/input behavior; disabling protections
or forcing a requested rate cannot satisfy the existing acceptance target.

## How to turn this matrix into focused changes

### 1. Preserve existing work and identify the smallest missing contract

Before coding, name the exact source/config/DT/firmware version and the
observed gap. Choose among:

- **Board integration:** DT graph, regulators, pinctrl, clocks, firmware path
  or calibration mapping for an already supported controller.
- **Driver correction or extension:** a specific callback, match entry,
  protocol feature or failure path missing from an existing implementation.
- **New device implementation:** only where an exact protocol/device still
  lacks a usable implementation, such as an unresolved charging or accessory
  path. Reuse the relevant standard kernel subsystem.
- **Evidence gap:** identify the part, transport or real failure before
  inventing a driver requirement.

Do not classify a device as unsupported merely because its node is disabled
in a diagnostic DT. Do not classify it as supported merely because a module
or matching family exists. Keep disabled nodes, firmware presence and runtime
results in separate fields.

### 2. Keep one reviewable unit per dependency

For a board description, submit its binding and DTS with verified electrical
properties. For a framework fix, explain why it belongs in that framework
and test other affected paths. For a new driver, document protocol, firmware,
power/IRQ lifecycle, error handling, recovery and concurrency. Keep temporary
instrumentation separable from the proposed production path.

The [pinned upstream inventory](evidence/2026-11-24-upstream-source-audit.json)
is a starting point for that review. Its filename/match-table negative results
are deliberately bounded; inspect relevant mailing-list series and newer
source revisions before starting a replacement implementation. Preserve
third-party copyright/license information and follow
[SOURCE_PROVENANCE](SOURCE_PROVENANCE.md) for donor source status.

### 3. Validate one physical stack, then combinations

Use the existing ledger's source/config/DT/Image/module/firmware/userspace
manifest and its Android comparison profiles. First prove the specific driver
behavior on the owner's tablet, then repeat across cold start, runtime idle,
hotplug, screen mode changes and system sleep. Finish with the daily-use,
high-refresh/pen, media and connected-sleep combination tests.

Numeric goals already belong to the ledger; do not replace them with generic
claims such as “smooth”, “USB3” or “GPU enabled”. Record errors and unmeasured
combinations. A firmware-file hash or an enumerated input endpoint is useful
identity evidence but cannot close a functional, quality or energy case.

## Share hardware evidence without conflating operating systems

The canonical owner observations and tested protocol vectors should be linked
from [QEMU's hardware contract](https://github.com/cyjin-yl/qemu-tb371fc/blob/docs/mainline-hardware-contract-20261124/tb371fc/docs/cross-project-hardware-contract.md)
and [UniXNU's hardware contract](https://github.com/cyjin-yl/UniXNU-tb371fc/blob/docs/mainline-hardware-contract-20261124/docs/CROSS_PROJECT_HARDWARE.md).
Keep each consumer's limitations explicit. QEMU implements a model; Linux
implements its own kernel/device APIs; XNU needs its own platform and IOKit
integration. Shared register facts, firmware protocols, HID descriptions and
test expectations reduce duplicated reverse engineering. They do not make
Linux modules directly usable in macOS 27 or prove that a model matches all
physical timing, power and security behavior.
