# Owner TB371FC: whole-device Linux acceptance plan

Research folder date: 2026-11-23, Asia/Shanghai. Evidence timestamps retain UTC.
Plan revision: 7. Machine-readable ledger: [acceptance.json](acceptance.json).

**Current outcome: not accepted. There are 44 planned cases, 12 explicitly
blocked and 32 not run; no native-Linux run or hardware pass on this owner
tablet has been recorded.** A case marked `not_run` can still depend on a
blocked prerequisite. That status does not claim it is immediately executable.

This is an attended runbook and evidence contract. It does not execute its
command templates, deploy an image, or grant additional device permissions.
The source review, Android observations, successful host compilation and generic
QEMU execution remain useful evidence within their own limits.

## What “best working state” means here

Acceptance requires every feature actually fitted to this tablet and every
confirmed stock mode needed by the owner to work together in one reproducible
Linux stack. That includes native full-panel output, all verified refresh
rates, ten-contact touch, pen pressure/tilt/hover/buttons and charging, keyboard
and touchpad, Wi-Fi/Bluetooth and the fitted FM receiver, storage, audio, cameras, sensors, charging, sleep and
graphics/video hardware paths. CPU execution, usable memory and data integrity
are also checked.

Performance is compared with controlled measurements on this same tablet's
Android reference, with matched workloads, conditions and uncertainty.
Throughput must reach stock parity; latency and energy must be no worse than
the reference. Measurement uncertainty is specified separately from that goal. “Best”
does not mean a claim of an unlimited or universal optimum. It means meeting
predeclared functional, quality, responsiveness, energy, stability and recovery
targets in named daily-use, high-refresh/pen, media and connected-sleep profiles.
Unmeasured combinations remain outside the claim.

No unresolved functional or isolation regression can be hidden by changing
the test configuration. Software rendering/decoding, a single working panel
half, lower refresh caps, permanently disabled touch/radios/sensors, a global
GPU address space, or slower fallback charging can be useful diagnostics.
They cannot satisfy a case requiring the corresponding full feature. Missing
Linux support never proves a feature is physically absent.

## Evidence levels and current position

| Evidence class | What it can establish | What it cannot establish |
| --- | --- | --- |
| `source_clue` | Driver behavior, DT wiring, donor comparison, offline descriptor/command interpretation, historical project reports | Operation on this owner's tablet |
| `host_build` | A specified build, package/staging check, mock test or generic QEMU result | Tablet boot, signed firmware acceptance, physical GPU rendering or peripheral behavior |
| `device_android` | A bounded observation on the owner tablet's Android reference | Native Linux operation; a passive capability list also does not establish a completed Android action |
| `device_linux` | A measured action on this same tablet using a named immutable Linux stack | Untested hardware combinations, configurations or modes |

The existing Android capture identifies the selected Tianma panel and
2944 × 1840 modes, Novatek touch/pen capabilities, the 17ef:6175 I2C-HID keyboard
cover, a four-contact touchpad, CTN730, QCA6390, SMB5 and MM8013. It contains no
live strokes, attended key/gesture sequence, controlled charge/sleep trial or
performance benchmark. The 8.012-second CPU/GPU trace is bounded Android activity,
not an energy, residency or frame-rate result. The later
boot-capability capture confirms an MMC card with three partition nodes;
its filesystem, negotiated speed and integrity/performance remain unmeasured.

The [current-owner peripheral inventory](android-peripheral-inventory.md)
adds static CameraService/SensorService identities and actual driver bindings.
SensorService advertises TDK-Invensense `icm4x6xx` acceleration/gyroscope
descriptors at 1–400 Hz, rather than the historical BMI3x0 lead; QST `qmc630x`
is advertised at 1–100 Hz. These are family/rate declarations, not chip-ID or
sample measurements. The ams `tcs3408` light/RGB and ROHM `bu52053nvx` Hall
descriptors are also present. The separate unbound `OCH8801-0` DT/I2C candidate
remains unresolved and is not substituted for the Hall service identity.

CameraService ID 0 is BACK with a 3264 × 2448 pixel array and 90° orientation;
ID 1 is FRONT with a 4240 × 3152 pixel array and 270° orientation. Pixel arrays
and AE rate declarations are not output-stream matrices or measured frame
rates. Exact camera silicon remains unconfirmed. Android also exposes one
`kona-qrd-snd-card`, 32 PCM interfaces and four bound `tfa98xx` clients at
0x34–0x37; that does not identify the exact TFA/codec/acoustic variants or prove
speaker/microphone operation. The bound `rtc6226` client and `radio0` interface
add a separate required **FM-01** case. Antenna, reception, routes and Android
functional baseline remain untested; no online radio stream can substitute.
This new evidence expands the plan by one case rather than omitting the tuner.

Research1's base DTB retains disabled DSI1 and touch. The independent
[research2-display build](research2-display-build.md) now has its own complete
Image, exact 83-module set and native diagnostic DTB. Both DSI/PHY links and
the Tianma panel are enabled in that DT, with qualified driver matches; SPI14
and touch remain disabled. The same research2 Image reached the exact release,
`aarch64` and EL0 markers in a generic ARM64 VM. These are actual host build and
VM results; no panel scanout, input event, board handoff or owner Linux boot
has been demonstrated. Device-tree availability is not a driver-probe result.

The [frozen firmware request audit](firmware-kernel-contract.md) makes further
configuration gaps explicit. GPU/GMU, ADSP/CDSP/SLPI and Bluetooth paths are
available in the research2 DT. All three PCIe controllers, SPI14/touch, four
TFA amplifiers and Venus are disabled. The generic TFA989X driver is unset and
does not match TFA9894, so copying acoustic containers cannot complete the
amplifier route. Conditional WLAN board selection, Bluetooth ROM suffixes,
Novatek panel-ID selection and secure firmware acceptance still need runtime
evidence. These static findings do not establish a successful probe or load.

Actual owner-matched GPU firmware staging succeeded in both full-ELF and
packed-MDT forms. This establishes byte provenance and packaging, not
authentication or execution by the GPU. The later
[fixed stock-firmware transfer](stock-firmware-bundle.md) independently verified
118 original files totalling 38,546,828 bytes and all loader-required segment
lengths in six ELF/MDT variants. Its private archive retains original names;
it is not an installed canonical firmware tree. File completeness does not
establish firmware ABI, signatures, services, WLAN board selection or the
Bluetooth ROM-dependent choice. No device was enabled or loaded by that copy.

A selected Nix ARM64 package closure
and QEMU hello have run; that is not a complete tablet rootfs. Fedora's ARM64
package assembly and actual emulated software graphics checks are also host
results. [Nura's native ARM builder](nura-build.md) installed 382 target packages
and exported a 307,393,454-byte generic rootfs archive, followed by a successful
gzip integrity check and cleanup of its owned VM/media server. That target
rootfs has not booted. Its cache retains 371 of the 382 installed package
versions, so offline reconstruction remains incomplete. The generic target's
7.3.5 kernel/modules are separate from both 6.12 research candidates. Each
candidate's build and userspace results remain separate from whole-device
acceptance.

Boot-state evidence needs explicit interpretation: Android properties report
locked/green while the captured kernel arguments report unlocked/orange.
Neither representation alone establishes the intended bootloader state or
safe boot entry. A recovery/boot contract must be demonstrated without guessing
that an unlock or data wipe is required. The final DTB root compatibility also
matters: the scoped early-page-table workaround selects `lenovo,tb371fc`; the
historical recovery overlay keeps generic Kona compatibility and therefore
takes the other allocator branch. A generic-QEMU success does not validate the
Lenovo branch or provide the tablet's initramfs.

The [boot-readiness review](boot-readiness.md) now has verified preparation
material: eight current boot/recovery/vbmeta/dtbo A/B partition copies total
461,504,512 bytes. Their local source/copy/source-recheck hashes agree, and the
93,319,878-byte off-device archive has independently checked image hashes.
This closes the missing off-device-copy item. It does not demonstrate restore,
inactive-slot boot, AVB/rollback validity or Linux entry, and it is not a backup
of Android userdata, super or persist. Equal `4.19.157-perf+` release strings
mask different A/B kernel bytes, so entry artifacts must be matched by exact
slot and hash.

The same owner's running kernel has `CONFIG_KEXEC=n`, enforced module
signatures and version checks, and `CONFIG_USB_CONFIGFS_ACM=n`. NCM and
FunctionFS are configured, but their presence is not a demonstrated rescue
transport. Installing a kexec executable or reusing a historical module cannot
supply those missing or incompatible kernel contracts. The exact first-stage,
usable console/recovery route and root-loading initramfs are still open. The
three-partition card must retain its actual layout; the author's historical
two-partition recipe is not an applicable layout assumption.

The [first-stage source audit](entry-source-audit.md) also finds an unresolved
build dependency: R226's selector repackages a private R201 recovery, while
the checked `d157b927` checkout lacks nine referenced vendor patches and the
resolved V56.6 source/configuration and ramdisk inputs. No alternative complete
recipe was found in the three enumerated public branches, two distinct heads,
empty tag list and queried path histories. This is a bounded source finding,
not a claim about every old or private source. The public tem423 `9d8abeb`
4.19.325 candidate is accurately identified, but is not V56.6's unknown
4.19.157 source; its inspected defconfig disables KEXEC, ACM and DEVTMPFS.
The owner's backups can supply matched layout/board inputs, but cannot supply
the missing source or turn a new payload hash into a working first stage.

A [separate standard Docker builder](ssd-builder.md) is also ready with an SSD
work bind, the same 4 CPU / 8 GiB limits, LLVM 19 and a checked AArch64 compiler
probe. Its old HDD predecessor and the ongoing userspace work were retained.
This is build infrastructure evidence; later kernel candidates keep separate
source, output and validation records.

## Measurement protocol and proposed thresholds

Record Android baselines before judging Linux. Use the same physical battery,
pen/nib, cover, chargers/cables, dock, card, LAN endpoint and test fixtures.
Keep identifiers private and use stable local aliases in published results.
Freeze application/workload versions and fixture hashes. Match actual active
resolution/refresh, measured luminance and audio level, radio conditions,
charging protocol, starting SOC and temperature, background services and
normal power/thermal policy. Record instrument uncertainty and every failed
trial; do not select only favorable runs.

An initial controlled environment of 23 ± 2 °C, 40–70% SOC and a five-minute
warmup is proposed where appropriate. These are experiment controls, not
manufacturer safety limits. Charging tests need their own fixed comparable
SOC window; brightness numbers from two different drivers are not equal
luminance. Alternate Android/Linux trial order where practical and retain at
least three paired trials. Add repetitions if that is insufficient to resolve
the chosen threshold; inconclusive data stays pending.

| Comparison profile | Proposed target to adopt before Linux testing | Required qualification |
| --- | --- | --- |
| Throughput | Linux median at least the matched Android median: ratio **≥ 1.0** | Comparable CPU/app/compiler and hardware paths; freeze effective precision and the uncertainty/confidence decision rule after the controlled Android baseline and before Linux trials |
| Tail latency | Linux p95 no greater than Android p95: ratio **≤ 1.0** | Same method and sampling; freeze timing uncertainty and precision, with an equivalent absolute parity bound when the denominator is below instrument resolution |
| Energy | Linux energy no greater than Android for the same work/interval: ratio **≤ 1.0** | Calibrated battery energy measurement and frozen uncertainty; USB input watts, unvalidated `charge_counter`, or short SOC-only samples cannot substitute |
| Quality | No regression beyond the adopted metric's combined measurement uncertainty | Freeze actual metrics and tolerances per case: spatial error/jitter, luminance/color, audio noise/distortion, camera quality, sensor bias, and so on |
| Active refresh | Measured cadence within 1% of the owner-verified target | Active DRM/link settings plus independent cadence observation; mode names or generic tracepoint counts alone are insufficient |

The throughput, latency and energy completion target is **stock parity at
ratio 1.0**. There is no default allowance for lower throughput or higher
latency/energy. The measurement methods and other engineering thresholds remain
proposals, not achieved results, product guarantees or universal standards;
every profile starts as `proposed` until its method is qualified. After the
controlled Android baseline, freeze effective precision, the uncertainty and
decision method, the exact metric and timestamp before its Linux trial.
Uncertainty cannot be converted into an arbitrary performance discount. If it
prevents a defensible parity conclusion, record the result as inconclusive.
No target may be loosened after observing a failed Linux result.
A selected desktop-GL feature without an Android equivalent needs
an explicit Linux correctness/conformance target; compare performance only for
a genuinely common workload/API. Unavailable or invalid readings remain unknown,
never numeric zero or an implicit pass.

## Execution order and release gate

1. **Assemble and identify the stack.** Finish one Image/DTB/initramfs/config/
   Module.symvers/modules/firmware/rootfs manifest, resolve entry/recovery and
   record effective enabled devices and diagnostic workarounds. Generic VM
   boot is a host gate; it is not SYS-01.
2. **Establish the owner baseline and minimum native session.** Confirm the
   remaining hardware inventory under Android, then complete boot/recovery,
   CPU/memory, native panel, input, gauge and storage checks under Linux.
3. **Complete independent hardware functions.** Validate Wi-Fi, Bluetooth, FM, USB, audio,
   camera, sensors, CTN730 and charging ownership. Keep absent/unimplemented
   modes visible rather than deleting their cases.
4. **Validate integration and power.** Exercise all refresh/pen modes, GL and
   Vulkan render/readback, compositor presentation, isolation/recovery,
   hardware video, runtime power, suspend and thermal performance. Dependencies
   in the JSON define the actual order; later post-resume checks revisit early
   device gates without creating a dependency cycle.
5. **Run one final configuration.** Recheck gates affected by a stack change,
   then complete the 24-hour mixed-use case. Every applicable required case
   must pass on the same final stack. A changed Image/DT/config/module/firmware/
   rootfs identity starts a new stack ID and invalidates dependent old passes
   until reviewed and retested.

The planned repetition counts and durations are a bounded acceptance campaign,
not a statistical guarantee of failure-free lifetime operation. A regression
stops the affected gate and remains in the result ledger. Hardware-protection
paths use reviewed driver tests and normal operating observations; this plan
does not call for forced overheating, overcharging, raw register guesses or
destructive storage tests.

## Recording a run and validating the ledger

Use [acceptance.json](acceptance.json) as the result ledger. Preserve the
baseline evidence and append new records; do not relabel the existing Android
or host records as Linux results. Each evidence item has a path, SHA256, class,
claims and limits. A controlled Android baseline additionally uses
`controlled_measurement: true` and must actually contain its method/results.

Register each immutable stack in `stack_manifests` with `id`, `evidence_id`
pointing to its reviewed manifest, and SHA256 values for all eight keys listed
in `stack_component_keys`. Tree artifacts use the hash of a complete file
manifest, not a directory name. Linux evidence includes `device_id`, `stack_id`
and `run_id`. A run records start/finish with timezones, profile, repetitions,
conditions-evidence ID and reviewer. Evidence from a VM has class `host_build`
even if it prints a Linux uname.

For each criterion, record `criterion_id`, `met`, `actual`, `unit` and its
Linux `evidence_ids`. Use Boolean `actual: true` for the fixed functional
assertions, with the measurements/observations in their linked evidence; an
unknown or a failed assertion cannot be encoded as true. Every comparison
profile used by the case also needs a `comparison_results` entry containing
the exact metric, adopted target/unit, threshold-freeze timestamp, paired
trial count, Android baseline IDs, Linux evidence IDs, measured actual,
uncertainty and `met`. Store samples and confidence calculations in the
referenced evidence, not just a claimed ratio. Freeze the reusable profile
and case-specific threshold before the Linux start time.

Set `pass` only after all dependencies, criteria, comparisons and repetitions
are satisfied with no open issue or degrading workaround. The same evidence
can support several clearly stated criteria, but its claims must support each
one. `not_applicable` is limited to cases marked `confirm_on_owner_android`:
add `result.absence` with reviewer, reason and controlled owner-Android
absence evidence. A missing Linux driver or unavailable accessory needed by
the owner's use is not absence. Update the decision's unique run and pass
counts from the ledger.

From the repository root:

```sh
# Offline only: structure, references, hashes and evidence/gate rules.
python3 scripts/research/validate_acceptance.py --check-files

# A valid unfinished plan exits 2; it must not be interpreted as acceptance.
python3 scripts/research/validate_acceptance.py --check-files --require-accepted
```

The first command's exit 0 means the ledger is internally consistent. Its
output must still say `hardware_accepted: false` while gates remain pending.
Exit 1 denotes a malformed or inconsistent ledger; exit 2 with
`--require-accepted` means valid but incomplete. The validator does not execute
the command catalog, authenticate a measurement, judge arbitrary narrative
evidence or replace review of the recorded criteria and calculations. Hashes
detect changes, not truth. Source reports edited later need review and updated
fingerprints; immutable acquisition JSON should not be silently rewritten.

### Command templates and privacy

Only run a template after mapping its live target and satisfying its case's
conditions. `${TB_ACCEPT_EVENT}` is a current Linux event node selected by
identity, never a copied Android event number. `${TB_ACCEPT_SERVER}` is the
chosen private LAN test endpoint. The command catalog's effects are explicit.
`evtest` is limited to an attended synthetic test sequence; do not collect
unrelated typing. Audio/camera fixtures must be test material. Publish sanitized
metrics and driver counters, not personal photos, voices, SSIDs, MACs, serials,
credentials or raw GPU firmware.

Do not read arbitrary sysfs/debugfs trees: the downstream CTN730 `cn_test`
getter initiates hardware activity. No raw block-device write, guessed
regulator transaction or competing charge-policy helper is part of this plan.
Existing session permissions continue to govern any actual device operation.

## Current preflight snapshot

### PF-OWNER-PERIPHERALS — `passive_owner_inventory_recorded`

The owner capture at 2026-11-22T23:47:37.939173Z enumerates two HAL 3.5 cameras, 49 logical SensorService entries, one ALSA card/32 PCM interfaces and four actually bound tfa98xx I2C clients. SensorService advertises icm4x6xx rather than historical BMI3x0, plus qmc630x, tcs3408 and bu52053nvx; reported rate limits are not samples. FSA4480 and RTC6226/radio0 are bound, so FM-01 is now a required separate gate. The scan retained 69 compatible-bearing DT declarations within its bounds; OCH8801-0 remains an unbound candidate. Exact camera/amp/codec/acoustic variants, microphones, streams, sensor transports and dynamic baseline quality remain open. No camera, audio, sensor or tuner stream was started and no Linux test was performed.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX.

### PF-KERNEL — `host_build_and_generic_vm_pass`

Full Image/modules and scoped-pool rebuild exited 0. Initial generic QEMU virt boot exhausted the historical early page-table pool; patch 0017 rebuild and the same virt/max/2CPU/1GiB QEMU now reach ARM64 /init and EL0_READY. New Image SHA256 5b7dbf8ac810ef4b488d394f6b976d876e52372621428f751f02f8deac5667f5; all 83 expected installed modules exactly match the build/installed module orders and actual file set, with matching release strings and ARM64 ELF headers. The lenovo,tb371fc branch and real tablet boot remain untested; the generic QEMU initramfs is not a tablet rootfs. Module signing keys and unsnapshotted APT dependencies mean bit-for-bit independent reproduction is not established.

Evidence: KERNEL-HOST, KERNEL-ARTIFACTS, QEMU-INITIAL, QEMU-FIXED, STATIC-FIXES, DISTRO-SOURCE.

### PF-KERNEL-R2 — `host_build_and_generic_vm_pass`

Independent 6.12.114-tb371fc-research2-display preparation reproduced the frozen research1 source/config, then added only historical 0002 and the qualified display wrapper. Full build exited 0 in 1268.915 seconds. Image SHA256 181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d and DTB SHA256 50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e have their own config, Module.symvers and 83 exactly matched modules. The same Image reached exact generic-QEMU release/machine/EL0 markers in 7.079 seconds; original serial and package/module manifests are retained. The native DT enables display but keeps SPI14/touch disabled. No physical display/input/GPU/Lenovo handoff or owner boot has been tested.

Evidence: R2-BUILD, R2-ARTIFACTS, R2-QEMU, R2-QEMU-SERIAL, R2-MODULES, R2-PACKAGES, SSD-BUILDER.

### PF-DTB — `base_and_display_profile_compiled`

Research1 base DT compiled with native panel/DSI1 and touch disabled. Independent research2 now builds the qualified diagnostic display DT with both DSI/PHY links and Tianma panel available, correct private driver matches, lenovo,tb371fc root and real framebuffer stdout path. Its SPI14/touch nodes are still disabled. OF availability is not a driver-probe or display result; a complete combined input/display profile, binding/runtime validation and owner boot remain separate.

Evidence: DTB-HOST, KERNEL-HOST, R2-BUILD, R2-ARTIFACTS.

### PF-GPU-FIRMWARE — `staging_verified`

Actual full-ELF3-file and MDT4-file packages match captured hashes; authentication/load remains untested.

Evidence: GPU-STAGE-ELF, GPU-STAGE-MDT.

### PF-FIRMWARE-CONTRACT — `static_request_map_reviewed`

The frozen research2 Image/config/DT/source contract maps GPU/GMU/ZAP, three DSPs, QCA6390 WLAN/BT, Novatek and Venus firmware requests. GPU/GMU, ADSP/CDSP/SLPI and Bluetooth OF paths are available, without observed probe or load. All three PCIe controllers, SPI14/touch, four TFA amps and the Venus parent are disabled. TFA989X is unset and its generic OF table lacks TFA9894, so QS/YC containers have no established request in this kernel. WLAN board keys/API compatibility, BT ROM suffix, Novatek logical panel-ID selection and all secure authentication/runtime services remain open. This maps future requests; it does not validate the separate stock archive or supply a complete enabled board profile.

Evidence: FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, R2-ARTIFACTS.

### PF-STOCK-FIRMWARE — `private_capture_copy_and_structure_verified`

The fixed owner capture and private SSH transfer completed with exit 0. The receiver independently verified 118 original files totalling 38546828 bytes, all manifest lengths/hashes, gzip integrity and a separate archive re-read. The 15747897-byte archive SHA256 is fc331d84ed585457b4183b08f799a49d9839d3114bf5ec2f281a725b87fe5f92. Complete A650 ELF plus A650/ADSP/CDSP/SLPI/Venus MDT variants have all loader-required segments with correct lengths; sparse BSS indices and packed metadata are preserved correctly. This provides identified private materials, not a canonical full firmware installation or all-device firmware compatibility. Vendor authentication, load, WLAN board selection, BT ROM matching, hardware decode and Linux hardware operation remain untested.

Evidence: STOCK-FIRMWARE-REPORT, STOCK-FIRMWARE-RECEIPT, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA.

### PF-USERSPACE — `host_userspace_evidence_only`

Nix selected closure/evaluation/QEMU hello exists. Fedora ARM64 userspace has 309 packages after adding 160 with normal scriptlets; dependency/loading checks and actual emulated software EGL/Wayland/Vulkan checks passed. Turnip found no physical GPU. These do not provide owner tablet boot, native rendering, full tablet initramfs or hardware acceptance. Nura generic ARM builder checkpoint: alpine_builder_booted=true, native_pmb_bootstrap_complete=true, target_rootfs_exported=true, rootfs_gzip_integrity_verified=true, owned_vm_and_media_server_stopped=true, offline_cache_complete=false, target_rootfs_booted=false, tablet_linux_boot_tested_by_this_experiment=false. The completed generic target has 382 installed packages and 371 retained APKs. Its 307393454-byte archive has SHA256 eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46. Its qemu-profile 7.3.5 kernel/modules are not the TB371FC 6.12 stack; independent offline reconstruction and tablet root-loader integration remain open.

Evidence: NIX-HOST, FEDORA-HOST, FEDORA-ARTIFACTS, NURA-HOST, NURA-ARTIFACTS, DISTRO-SOURCE.

### PF-BOOT-BACKUPS — `verified_preparation_only`

Eight current A/B boot/recovery/vbmeta/dtbo partitions total 461504512 bytes. All local source/copy/source-recheck hashes agree; the actually received 93319878-byte off-device archive and all eight embedded images independently match the manifest. This closes the missing off-device-copy preparation item. The copies are not certified pristine factory images, do not cover userdata/super/persist, do not prove B boots and are not a demonstrated restore. Header inspection requires exact slot/hash pairing despite equal kernel release strings.

Evidence: ANDROID-BOOT-BACKUP, BOOT-BACKUP-OFFDEVICE, BOOT-HEADER-HOST, BOOT-READINESS.

### PF-BOOT-RECOVERY — `unresolved_stock_entry`

The running owner 4.19 kernel has CONFIG_KEXEC=n; module signature enforcement and MODVERSIONS are enabled; ACM is not configured, while NCM/FunctionFS are. There is no demonstrated stock-to-kexec entry or historical rescue-console equivalence. Android properties still conflict with boot arguments about locked/green versus unlocked/orange. The actual bootloader/transport, matched first-stage, final native DT, root-loading initramfs and recovery procedure remain to be established. Current mmcblk0 has three partitions, so a historical two-partition/card-specific install recipe cannot be applied by assumption. Existing session authorizations continue to govern any actual entry experiment; this ledger adds no deployment permission or confirmation step.

Evidence: ANDROID-BOOT, ANDROID-BOOT-CAPABILITIES, BOOT-READINESS.

### PF-FIRST-STAGE-SOURCE — `missing_inputs_in_audited_refs`

R226 selector changes an already-built R201 ramdisk; it does not build the 4.19 bridge. The checked d157 checkout lacks nine referenced V56.6 vendor patches plus exact source/config/donor and private ramdisk inputs. Live enumeration found no alternative complete recipe in the three public branches (two distinct heads), empty tag list and queried vendor-kernel path histories. This is not an assertion about every old/renamed/private source. Public tem423 commit 9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1 exists as a 4.19.325 candidate, but its defconfig disables KEXEC/ACM/DEVTMPFS and it is not the unknown V56.6 4.19.157 source. The historical packer stock hash matches owner recovery_a, not recovery_b. No new first-stage image was built.

Evidence: ENTRY-SOURCE, ENTRY-METADATA, ANDROID-BOOT-CAPABILITIES, BOOT-HEADER-HOST.

### PF-BUILDER — `ssd_work_builder_ready`

A separate standard Docker builder completed bootstrap with exit 0 in 617.685 seconds. Its /work is SSD, /src is read-only, CPU/RAM limits remain 4/8 GiB, LLVM 19.1.7 produced a real AArch64 object, and the official archive/reference manifest copies match expected hashes. The old build/Nura container remains intact. This is infrastructure readiness, with no kernel or tablet pass implied.

Evidence: SSD-BUILDER.

## Test index

| ID | Subsystem and case | Current status | Minimum repetition/duration |
| --- | --- | --- | --- |
| [SYS-01](#sys-01) | Boot identity, reproducible stack and recovery | `blocked` | 20; case sequence |
| [SYS-02](#sys-02) | Owner hardware and feature inventory | `not_run` | 1; case sequence |
| [SYS-04](#sys-04) | CPU topology, usable memory and computation integrity | `not_run` | 3; 10 min per trial |
| [DISP-01](#disp-01) | Cold native full-panel scanout and geometry | `not_run` | 10; case sequence |
| [DISP-02](#disp-02) | All stock refresh modes and transitions | `not_run` | 3; 120 s per steady trial; 5 trials per directed transition |
| [DISP-03](#disp-03) | Backlight range, symmetry and blanking | `not_run` | 20; case sequence |
| [DISP-04](#disp-04) | USB-C external display and docking | `not_run` | 20; case sequence |
| [TOUCH-01](#touch-01) | Ten-contact touch, geometry and rotations | `not_run` | 3; case sequence |
| [PEN-01](#pen-01) | Native inking, pressure, tilt, hover and geometry | `not_run` | 3; case sequence |
| [PEN-02](#pen-02) | Palm rejection and display/pen interaction | `not_run` | 3; 10 min per supported refresh |
| [PEN-03](#pen-03) | Magnetic attachment and actual pen charging | `blocked` | 3; at least 30 min per charge condition |
| [PEN-04](#pen-04) | Bluetooth pen auxiliary functions | `not_run` | 10; case sequence |
| [KEY-01](#key-01) | Cover keyboard, physical layout and lifecycle | `not_run` | 20; case sequence |
| [PAD-01](#pad-01) | Cover touchpad and multi-finger gestures | `not_run` | 3; case sequence |
| [SWITCH-01](#switch-01) | Power/volume keys, cover Hall and wake policy | `not_run` | 20; case sequence |
| [WIFI-01](#wifi-01) | Wi-Fi association, throughput, latency and reliability | `not_run` | 3; 30 s per throughput trial plus 60 min stability |
| [WIFI-02](#wifi-02) | Confirmed hotspot/P2P services and Wi-Fi/BT coexistence | `not_run` | 3; 30 min coexistence |
| [BT-01](#bt-01) | Bluetooth controller, BLE/HID and audio profiles | `not_run` | 3; 30 min audio/profile stability |
| [USB-01](#usb-01) | USB-C device role, link speed and data integrity | `not_run` | 20; case sequence |
| [USB-02](#usb-02) | USB host, hub and role switching | `not_run` | 20; case sequence |
| [AUDIO-01](#audio-01) | All internal speakers and amplifier calibration | `blocked` | 3; 30 min sustained playback |
| [AUDIO-02](#audio-02) | Internal microphones, capture and duplex audio | `blocked` | 3; 10 min duplex |
| [AUDIO-03](#audio-03) | USB-C analog/digital and headset route changes | `not_run` | 20; case sequence |
| [FM-01](#fm-01) | RTC6226 tuning, reception, audio and recovery | `blocked` | 3; 30 min per required route; 20 lifecycle cycles |
| [CAM-01](#cam-01) | Rear camera still/video and application pipeline | `blocked` | 3; 30 stills plus 10 min per required stream |
| [CAM-02](#cam-02) | Front camera still/video and application pipeline | `blocked` | 3; 30 stills plus 10 min per required stream |
| [SENS-01](#sens-01) | Accelerometer, gyroscope, magnetometer and orientation | `blocked` | 3; case sequence |
| [SENS-02](#sens-02) | Ambient/RGB sensing and automatic brightness | `not_run` | 20; case sequence |
| [STOR-01](#stor-01) | UFS filesystem integrity, throughput and recovery | `not_run` | 3; case sequence |
| [STOR-02](#stor-02) | microSD compatibility, integrity and safe reinsert | `not_run` | 3; case sequence |
| [PWR-01](#pwr-01) | Fuel-gauge units, sign, trends and desktop reporting | `not_run` | 3; case sequence |
| [PWR-02](#pwr-02) | Sustained charging and actual negotiated protocols | `blocked` | 3; 45 min steady trial;20 replug cycles |
| [PWR-03](#pwr-03) | Charge limits, thermal controls and watchdog ownership | `blocked` | 3; case sequence |
| [PM-01](#pm-01) | Screen-on/off idle and runtime power management | `not_run` | 3; 30 min per condition |
| [PM-02](#pm-02) | Real suspend entry, wake and complete device restoration | `not_run` | 20; 20 cycles plus3x8h sleep |
| [THERM-01](#therm-01) | Sustained CPU/GPU performance and thermal regulation | `not_run` | 3; 20 min sustained plus idle cooldown |
| [GPU-01](#gpu-01) | Actual native MSM device, firmware and API inventory | `not_run` | 1; case sequence |
| [GPU-02](#gpu-02) | OpenGL/GLES hardware draw and readback correctness | `not_run` | 3; 30 min stability |
| [GPU-03](#gpu-03) | Vulkan submissions, synchronization and readback | `not_run` | 3; 30 min stability |
| [GPU-04](#gpu-04) | Wayland/KWin hardware composition and native presentation | `not_run` | 3; case sequence |
| [GPU-05](#gpu-05) | Per-process GPU address-space isolation and bounded recovery | `blocked` | 3; case sequence |
| [VIDEO-01](#video-01) | Native hardware decode and application use | `blocked` | 3; 10 min per required stream |
| [VIDEO-02](#video-02) | Hardware encode where stock exposes it | `not_run` | 3; 10 min per mode |
| [SYS-03](#sys-03) | Complete daily-use combination and soak | `not_run` | 1; 24 h mixed-use soak |

## Detailed attended procedures

All criteria below are pending. Repetition counts include the case-specific
cycles described in each procedure; three paired performance trials are an
additional comparison requirement where a profile is used. A future result
must name which conditions and modes each trial covered.

### SYS-01

**Boot identity, reproducible stack and recovery** — `blocked`.

**Known baseline:** Owner stock is TB371FC Android 14 / 4.19.157-perf+. Property lock/verified-boot values conflict with captured boot arguments. The running kernel lacks kexec and ACM, and enforces module signatures/version checks. Eight current boot-related partitions have checked local/off-device copies, but no restore or stock-to-mainline entry has been demonstrated; the inspected historical first-stage source chain has missing inputs. Research1 and independent research2-display Image/module/DT builds and generic ARM64 /init boots succeeded; the original research1 VM pool panic is retained. Research2 enables the native display profile in its compiled DT but keeps SPI14/touch disabled. All are host results, with no owner Linux boot.

Evidence: ANDROID-STOCK, ANDROID-BOOT, ANDROID-BOOT-CAPABILITIES, ANDROID-BOOT-BACKUP, BOOT-BACKUP-OFFDEVICE, BOOT-HEADER-HOST, BOOT-READINESS, ENTRY-SOURCE, ENTRY-METADATA, KERNEL-HOST, KERNEL-ARTIFACTS, QEMU-INITIAL, QEMU-FIXED, R2-BUILD, R2-ARTIFACTS, R2-QEMU, DTB-HOST, GPU-STAGE-ELF, GPU-STAGE-MDT, DISTRO-SOURCE. Dependencies: preflight assembly and recovery.

**Current blocker:** A complete matched tablet boot payload/root-loading initramfs and owner entry/recovery route remain unverified, despite verified off-device current backups. The measured stock kernel has CONFIG_KEXEC=n, enforced module signatures/versioning and no configured ACM function; the historical first-stage entry cannot be assumed to apply. The property/command-line lock-state disagreement remains unresolved at the actual bootloader.

**Before running:** One named kernel/DTB/initramfs/module/firmware/rootfs stack; owner boot-entry and recovery method resolved first.

**Android work still required:** Confirm the actual owner bootloader entry state, available transport, ordinary Android cold/warm boot and recovery behavior; do not resolve conflicting lock fields by assumption. Retain the verified current-partition backup and exact slot identities. Establish a matched first-stage/loader and usable recovery console: installing a kexec executable cannot supply CONFIG_KEXEC=n, and historical modules/ACM behavior cannot bypass current signature, ABI or USB-function constraints.

**Linux procedure:**

1. Record hashes of all eight stack components and exact native driver/workaround configuration; verify loaded release/build identity against the boot manifest. Record the final flat root compatible: the board-specific early pool guard requires lenovo,tb371fc; a legacy recovery overlay retaining only qcom,kona identifiers takes a different allocator path.
2. Perform 10 controlled cold boots and 10 warm reboots, retaining success/time/error counters and confirming normal shutdown.
3. Demonstrate the documented recovery route returns to the known baseline with its data intact; re-enter the identical test stack.

**Required result:**

- `SYS-01.C01`: All 20 boots reach the intended Linux session without hidden watchdog-reset checkpoints or manual driver rescue.
- `SYS-01.C02`: Loaded modules have the same build ABI/Module.symvers/signing policy; no historical .ko reuse by filename.
- `SYS-01.C03`: Recovery and shutdown succeed; no stock-data or boot-policy corruption.

Minimum repetitions: 20. Comparison profiles: fixed functional criteria only.

### SYS-02

**Owner hardware and feature inventory** — `not_run`.

**Known baseline:** Owner captures now cover selected display/input/radio/power nodes plus two CameraService devices, sensor-family declarations, one ALSA card/32 PCM entries, four bound tfa98xx clients, FSA4480 and RTC6226/radio0. These are passive identities/capabilities, not frames, samples, audio or FM reception. Camera silicon, acoustic/codec variants, microphones, full stream matrices and remaining board/accessory functions are unresolved. OCH8801-0 at 3-0018 has no driver symlink and remains a candidate; it is not proven absent or interchangeable with the advertised ROHM Hall sensor.

Evidence: ANDROID-STOCK, ANDROID-GPU, ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-01.

**Before running:** Same tablet and owned accessories; enumerate before executing device-specific electrical paths.

**Android work still required:** Resolve exact fitted camera and amp/codec/acoustic variants, microphone count/routes, sensor transports/axes and remaining Hall/button candidates without treating generic DT names as chip IDs. Complete UFS/microSD, DP, USB, FM/antenna and other radio/accessory capability inventory with attended checks. Record any physically absent feature explicitly. An absent Linux driver never proves a feature is absent from the tablet.

**Linux procedure:**

1. Build an owner inventory matching each Android-present feature to a Linux driver, userspace route and test ID.
2. Record every additional Android-present feature as a new required case; freeze camera modes, video codecs, radio features and application/API requirements before Linux acceptance.

**Required result:**

- `SYS-02.C01`: Every Android-present hardware feature is covered by a case; no disabled device is deleted from scope.
- `SYS-02.C02`: All identity uncertainty is resolved before loading board-specific firmware/calibration or camera/amp configuration.

Minimum repetitions: 1. Comparison profiles: fixed functional criteria only.

### SYS-04

**CPU topology, usable memory and computation integrity** — `not_run`.

**Known baseline:** Android exposes three CPU frequency policies for CPUs 0-3, 4-6 and 7. The passive capture did not measure available RAM, sustained calculation correctness or cross-core behavior.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: SYS-01, SYS-02, PWR-01.

**Before running:** Normal DVFS/thermal policy; ordinary userspace allocations bounded to at most 25 percent of current MemAvailable; no reserved-memory, raw /dev/mem or forced CPU/voltage writes.

**Android work still required:** Record all eight CPUs, possible/online topology and usable memory/reservations on Android; run the same bounded deterministic CPU/memory workload and retain checksums.

**Linux procedure:**

1. Account for fitted RAM against available/reserved regions and the selected DT; check every expected CPU can execute work under normal scheduler policy.
2. Run a reviewed deterministic multiworker CPU/memory integrity workload three times for ten minutes within the stated allocation bound, checking expected results.
3. Repeat its short correctness subset after suspend and the final soak; distinguish legitimate reservations from lost memory or offlined cores.

**Required result:**

- `SYS-04.C01`: All eight expected CPUs and the accounted usable memory are available under normal policy; no unexplained capacity loss or offline core.
- `SYS-04.C02`: All deterministic results match with no memory error, corruption, OOM, reset or silent protection bypass.

Minimum repetitions: 3. Duration: 10 min per trial. Comparison profiles: paired-throughput.

### DISP-01

**Cold native full-panel scanout and geometry** — `not_run`.

**Known baseline:** Android selects Tianma, 2944x1840 dual-DSI/DSC; one slice per packet in captured DT. Research1 base DT retains disabled DSI1. The separately built research2 display DT enables both DSI/PHY links and the Tianma panel with qualified driver matches, but no native scanout or panel action was tested.

Evidence: ANDROID-STOCK, DISPLAY-DECODE, DISPLAY-SOURCE, DTB-HOST, R2-BUILD, R2-ARTIFACTS. Dependencies: SYS-01.

**Before running:** Native MSM DPU plus both DSI links; cold init without retained splash; initially fixed 60 Hz and matched luminance.

**Android work still required:** Observe the same full-screen color bars, single-pixel grids, text, gradients and frame counters under Android; record orientation and seam.

**Linux procedure:**

1. Start from cold power state and present test patterns across both halves at 2944x1840.
2. Retain the active mode, per-link DSI timings/clocks and effective DSC/PPS settings from the selected driver diagnostics; distinguish requested DT defaults from applied state and avoid arbitrary raw-register reads.
3. Check edges, seam, gradients, clipping, color/channel order and frame continuity; log DPU/DSI/DSC faults.
4. Repeat after a userspace compositor restart and after the later suspend gate.

**Required result:**

- `DISP-01.C01`: All pixels across both halves are correctly addressed, with no corruption, tearing seam, crop or persistent boot splash.
- `DISP-01.C02`: Native DPU/dual-DSI owns scanout; inherited simpledrm, 640x400 diagnostics or software-only presentation do not satisfy this case.

Minimum repetitions: 10. Comparison profiles: paired-quality.

### DISP-02

**All stock refresh modes and transitions** — `not_run`.

**Known baseline:** Android advertises 30/60/120/144 Hz; actual active rates and 144 Hz transition mechanism were not measured.

Evidence: ANDROID-STOCK, DISPLAY-DECODE, DISPLAY-SOURCE. Dependencies: DISP-01.

**Before running:** Test every owner-verified advertised mode, not just default; same light rendering pattern and measurement method.

**Android work still required:** Measure active cadence at 30/60/120/144 Hz and document which transitions Android actually supports; retain any unsupported-mode evidence instead of assuming advertising means success.

**Linux procedure:**

1. For each supported rate measure three 120-second steady runs using active timings and independent cadence observation.
2. Attach the actual per-link DSI/DSC/PPS and active clock/mode evidence for each rate, with unavailable values left unknown; correlate pen tests with the confirmed B3 table difference without assigning unproven register semantics.
3. Exercise all 12 directed transitions among four rates five times, including the 120-to-144 and 144-to-120 paths.
4. Run a light animated pattern and then pen activity; log each requested/active mode and presentation discontinuity.

**Required result:**

- `DISP-02.C01`: Every confirmed stock mode works at full geometry; silently capping at 60/120 Hz is incomplete.
- `DISP-02.C02`: All planned transitions recover to their requested active mode without stale halves, reset, unexplained fallback or pen loss.

Minimum repetitions: 3. Duration: 120 s per steady trial; 5 trials per directed transition. Comparison profiles: active-refresh, paired-latency.

### DISP-03

**Backlight range, symmetry and blanking** — `not_run`.

**Known baseline:** Android reports requested brightness 294/2047 and actual_brightness 0; that getter alone is not measured darkness. Two KTZ8866 controllers are captured.

Evidence: ANDROID-STOCK, DISPLAY-SOURCE, STATIC-FIXES. Dependencies: DISP-01.

**Before running:** Use measured luminance/reference patterns, identical ambient light and confirmed amp/panel supplies; do not equate raw brightness numbers across drivers.

**Android work still required:** Measure minimum usable and maximum normal luminance, five intermediate levels, left/right uniformity and blank/unblank on Android.

**Linux procedure:**

1. Sweep the supported brightness range including zero and the minimum usable step; compare both halves and flicker.
2. Perform 20 blank/unblank cycles and restoration after compositor/session restart.
3. Record requested and measured brightness independently; inspect I2C error handling without treating mock tests as runtime proof.

**Required result:**

- `DISP-03.C01`: One logical control drives both halves consistently; zero truly blanks and the previous level restores without a stuck half.
- `DISP-03.C02`: Usable luminance range, monotonicity and uniformity meet the frozen Android quality comparison.

Minimum repetitions: 20. Comparison profiles: paired-quality.

### DISP-04

**USB-C external display and docking** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** DP Alt Mode and redriver wiring are historical source clues; the owner capture confirms PS5169 binding, not DP output.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX, DISPLAY-SOURCE. Dependencies: SYS-02, USB-02, DISP-01.

**Before running:** Owned known-good dock/cable/display; both USB-C orientations; test shared USB, charging and audio paths.

**Android work still required:** Confirm owner Android external-display support and exact modes/refresh/audio/USB coexistence with this dock.

**Linux procedure:**

1. Connect/disconnect 20 times, test mirror and extended desktop where supported, and run 30 minutes at each baseline mode.
2. Verify picture, link retraining, display audio, USB transfers and charging coexistence; repeat after suspend.

**Required result:**

- `DISP-04.C01`: All confirmed stock external-display modes remain usable with correct output and no internal-panel corruption.
- `DISP-04.C02`: Dock attach/role changes recover without manual service reload; unsupported Linux DP is not treated as absent hardware.

Minimum repetitions: 20. Comparison profiles: paired-quality.

### TOUCH-01

**Ten-contact touch, geometry and rotations** — `not_run`.

**Known baseline:** Android NVTCapacitiveTouchScreen is registered with ten contacts, 18400x29440 ranges, touch-major 255 and finger pressure maximum 1; no live strokes were captured. Research2 builds the Novatek module but keeps SPI14 and touchscreen disabled. Its conditional Tianma/BOE firmware names are known; the mainline panel-ID GPIO and actual firmware loading have not been observed.

Evidence: ANDROID-STOCK, INPUT-SOURCE, R2-ARTIFACTS, R2-MODULES, FIRMWARE-CONTRACT, STOCK-FIRMWARE-RECEIPT. Dependencies: DISP-01.

**Before running:** Fresh event-node mapping; all four logical orientations and all validated panel rates; test synthetic motions only.

**Android work still required:** Measure edge coverage, grid accuracy/jitter, ten-finger tracking and touch-to-photon timing under Android.

**Linux procedure:**

1. Trace a 5x5 grid and edges, slow diagonals and circles; hold ten contacts and cross/move them without changing IDs.
2. Repeat in all rotations and after 20 blank/unblank and detach/resume interactions.
3. Record dropped/stuck contacts and spatial/timing error against the matched baseline.

**Required result:**

- `TOUCH-01.C01`: Ten independent contacts work with correct orientation, edge coverage and release; no ghost or stuck touch.
- `TOUCH-01.C02`: Coordinate scaling is consistent with 18400x29440 reports; finger pressure is not misrepresented as the pen pressure sensor.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

Command templates: `input-list`, `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### PEN-01

**Native inking, pressure, tilt, hover and geometry** — `not_run`.

**Known baseline:** Novatek pen advertises 18400x29440, pressure 0..4095, tilt +/-60, distance 0..1 and two barrel buttons. Android physical resolution is zero; donor 148x237 mm conflicts with panel metadata.

Evidence: ANDROID-STOCK, INPUT-SOURCE, STATIC-FIXES. Dependencies: TOUCH-01.

**Before running:** Use the same pen/nib and a pressure-aware app; confirm active physical area and axis mapping before changing counts/mm.

**Android work still required:** Measure grid and edge accuracy, pressure ramps, tilt response, hover and stroke latency; identify exact button semantics.

**Linux procedure:**

1. Draw repeated slow/fast diagonals, 5x5 targets and ten normal-force pressure ramps; do not force the pen to reach an advertised maximum.
2. Test controlled tilts, hover entry/exit and both buttons, then repeat at each refresh and orientation.
3. Verify input metadata and application-visible behavior separately, with calibrated physical dimensions.

**Required result:**

- `PEN-01.C01`: Position, pressure, tilt, hover and both buttons function through the Novatek SPI path and the chosen application.
- `PEN-01.C02`: No stuck tool/contact, broken scale or edge offset; BT pen enumeration does not satisfy inking.
- `PEN-01.C03`: Physical resolution metadata is supported by measured active area and orientation, rather than unverified donor defaults.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

Command templates: `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### PEN-02

**Palm rejection and display/pen interaction** — `not_run`.

**Known baseline:** Android pen-related panel commands differ at B3 for 144 Hz. Their runtime meaning/dispatch is unmeasured; native counterpart is not established.

Evidence: DISPLAY-DECODE, DISPLAY-SOURCE, INPUT-SOURCE. Dependencies: PEN-01, DISP-02.

**Before running:** Pen hover/contact with palm resting, touch enabled; supported rates/orientations; blank/unblank and GPU workload scenarios.

**Android work still required:** Record Android palm/touch behavior during pen hover and contact, and behavior when entering/leaving 144 Hz.

**Linux procedure:**

1. Write for ten minutes at each supported rate with palm rests, lifting/re-entering hover and pressing the buttons.
2. Switch display modes during pen activity, then blank/unblank and resume; compare false touches and lost strokes.
3. Record any pen-specific panel command implementation and measured effect without inferring semantics from B3 alone.

**Required result:**

- `PEN-02.C01`: No unintended palm strokes or permanent touch suppression; drawing remains continuous across validated transitions.
- `PEN-02.C02`: Touch disabled globally, 144 Hz removed, or pen features disabled is incomplete rather than a fix.

Minimum repetitions: 3. Duration: 10 min per supported refresh. Comparison profiles: paired-quality, paired-latency.

### PEN-03

**Magnetic attachment and actual pen charging** — `blocked`.

**Known baseline:** CTN730 is bound at /soc/i2c@984000/ctn730@28, GPIO84/160/111; distinct from PS5169 at another 0x28. No charging cycle was measured and no complete mainline CTN730 port is established.

Evidence: ANDROID-STOCK, INPUT-SOURCE, HISTORICAL-MATRIX. Dependencies: SYS-02, PWR-01.

**Current blocker:** Reviewed CTN730 Linux driver/binding and actual charging baseline are not yet available.

**Before running:** Known pen starting charge below full; same tablet SOC/charger state, dock position and temperature; independent pen charge telemetry or run-time method.

**Android work still required:** Measure Android dock detection, charge trend over at least 30 minutes, undock recovery and screen-off charging; validate what the pen battery report means.

**Linux procedure:**

1. Repeat 20 attach/detach events and check controller/pen state without reading the downstream cn_test attribute.
2. Measure a 30-minute charge session and a screen-off session, then verify the pen remains usable and charging stops/changes appropriately when removed.
3. Compare energy/charge progress and temperatures with the Android reference; test reattachment after suspend.

**Required result:**

- `PEN-03.C01`: Dock sensing and measurable pen energy/charge increase are both demonstrated; BT pairing, an input node or an attached flag alone cannot pass.
- `PEN-03.C02`: Charging ownership, shutdown and temperature behavior are correct; no CTN730/PS5169 address confusion or forced charging-test getter.

Minimum repetitions: 3. Duration: at least 30 min per charge condition. Comparison profiles: paired-quality.

### PEN-04

**Bluetooth pen auxiliary functions** — `not_run`.

**Known baseline:** Lenovo Precision Pen 3 Mouse and Consumer Control expose Bluetooth VID:PID 17ef:612b; this is separate from SPI inking and CTN730 charging.

Evidence: ANDROID-STOCK, INPUT-SOURCE. Dependencies: BT-01.

**Before running:** Same pen and recorded Android auxiliary-button/battery features; no pairing/address identifiers in published logs.

**Android work still required:** Identify which advertised BT reports have a real owner-visible Android action or telemetry.

**Linux procedure:**

1. Pair/reconnect ten times; exercise every confirmed auxiliary action and test reconnect after pen/tablet sleep.
2. Verify that inking and charging do not falsely depend on a desktop BT button mapping.

**Required result:**

- `PEN-04.C01`: All confirmed pen BT functions operate and reconnect; unsupported unobserved functions remain explicitly unknown.
- `PEN-04.C02`: Passing this test never changes PEN-01 or PEN-03 to pass.

Minimum repetitions: 10. Comparison profiles: fixed functional criteria only.

### KEY-01

**Cover keyboard, physical layout and lifecycle** — `not_run`.

**Known baseline:** Lenovo Keyboard Pack for Spinel 17ef:6175, I2C-HID at a94000/0x60; reset114/wake108/IRQ110. Descriptor has keyboard/touchpad/consumer collections and no Input ID6.

Evidence: ANDROID-STOCK, HID-DECODE, INPUT-SOURCE. Dependencies: SYS-01.

**Before running:** Correct cover; synthetic typing in a dedicated test view; cold-attached and hot-attached cases.

**Android work still required:** Map every physical key/Fn/consumer key and LED actually present; record repeat, modifiers and stock hotplug/wake behavior.

**Linux procedure:**

1. Exercise all keys, modifiers/chords, repeats and consumer functions; aggregate expected/received counts.
2. Perform 20 detach/reattach cycles and ten cold-attached boots; test wake and key-release recovery after suspension.
3. Check for stuck keys/IRQ storms and verify the actual wake/reset/IRQ sequence; do not borrow the 17ef:6127 status parser.

**Required result:**

- `KEY-01.C01`: Every physical key and confirmed consumer function maps correctly with zero lost, duplicated or stuck events in the prescribed sequence.
- `KEY-01.C02`: Cold attach, hotplug and wake work without manual rebind or persistent active IRQ storms.

Minimum repetitions: 20. Comparison profiles: paired-latency.

Command templates: `input-list`, `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### PAD-01

**Cover touchpad and multi-finger gestures** — `not_run`.

**Known baseline:** Owner Android touchpad has four slots (0..3), X0..2998/Y0..1771, resolution31, POINTER/BUTTONPAD; HID report ID3 is 29 bytes including ID.

Evidence: ANDROID-STOCK, HID-DECODE, INPUT-SOURCE. Dependencies: KEY-01.

**Before running:** Same pointer settings recorded on both systems; platform gesture mapping documented separately from raw contact delivery.

**Android work still required:** Record pointer, click/drag, scroll, multi-finger capability, palm rejection and gesture actions actually available on Android.

**Linux procedure:**

1. Test slow/fast motion, edge reaches, clicks, drag-and-drop, two-finger scroll and supported three/four-finger contacts/gestures.
2. Type while resting near the pad to test palm rejection; repeat after 20 cover cycles and suspend.
3. Compare motion/scroll latency and jitter; verify no coordinate-range or contact-count clipping.

**Required result:**

- `PAD-01.C01`: All confirmed raw contacts, button/drag/scroll functions work; gesture bindings are documented and usable in the desktop.
- `PAD-01.C02`: No stuck button, accidental palm click or loss after reattach; an external mouse is not a substitute.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

Command templates: `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### SWITCH-01

**Power/volume keys, cover Hall and wake policy** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** Owner SensorService advertises ROHM bu52053nvx Hall wakeup/non-wakeup descriptors, without lid/cover/pen actions. A distinct OCH8801-0 I2C/DT candidate at 3-0018 has no driver symlink; its physical role or absence is not established. Complete physical button mapping and actual wake behavior remain unmeasured.

Evidence: ANDROID-STOCK, ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, KEY-01.

**Before running:** Use actual owner-present buttons and cover states; distinguish wake, display blank and system suspend.

**Android work still required:** Map physical buttons, Hall/lid states, long-press behavior and which inputs Android permits to wake the tablet.

**Linux procedure:**

1. Exercise each switch 20 times, including lid/cover close/open and permitted wake sources.
2. Repeat with pen docked, keyboard attached and charging; confirm no phantom transitions or unintended reboot.

**Required result:**

- `SWITCH-01.C01`: All owner-present buttons/switches work with the intended policy and restore the complete input/display session.
- `SWITCH-01.C02`: A missing Linux Hall/button device cannot be recorded as absent hardware.

Minimum repetitions: 20. Comparison profiles: fixed functional criteria only.

### WIFI-01

**Wi-Fi association, throughput, latency and reliability** — `not_run`.

**Known baseline:** PCI 17cb:1101 is bound to Android cnss_pci; QCA6390 is confirmed. No association/throughput trial is in the capture. Research2 builds ath11k/MHI but disables all three PCIe controllers. Its conditional firmware path is ath11k/QCA6390/hw2.0/; board selection and firmware ABI remain unverified.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX, POWER-SOURCE, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT. Dependencies: SYS-01.

**Before running:** Same AP/server/channel/width/regulatory domain, tablet placement, power state and test data; cover 2.4 and 5 GHz and supported 802.11ax. Do not assume 6 GHz.

**Android work still required:** Measure three paired sessions per band/location, bidirectional LAN throughput and latency, 20 reconnects and sleep reconnection.

**Linux procedure:**

1. Associate using private test credentials; measure 30-second traffic in each direction, repeated at least three times.
2. Run 60-minute mixed traffic and 20 reconnect/roam/replug-equivalent cycles appropriate to the AP setup.
3. Check the final enabled PCIe path, actual ath11k firmware API and runtime board selection before interpreting association results. Raw AMSS is not a firmware-2.bin container, and the stock bdwlan pool cannot justify an arbitrary board-2.bin/board.bin choice.
4. Check PCIe/runtime-PM recovery and filtered error deltas.

**Required result:**

- `WIFI-01.C01`: All confirmed bands/security modes associate without firmware crashes or manual service reload.
- `WIFI-01.C02`: Packet loss/corruption and reconnect failures are zero in the controlled local test; performance meets matched baselines.

Minimum repetitions: 3. Duration: 30 s per throughput trial plus 60 min stability. Comparison profiles: paired-throughput, paired-latency, paired-energy.

Command templates: `wifi-tx`, `wifi-rx` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### WIFI-02

**Confirmed hotspot/P2P services and Wi-Fi/BT coexistence** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** Historical stock interfaces include P2P/Wi-Fi Aware, but owner support/use is not tested. Shared QCA6390 radio coexistence needs its own trial.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX. Dependencies: WIFI-01, BT-01.

**Before running:** Only owner-confirmed services and supported test peers; both radios active under the same baseline workload.

**Android work still required:** Confirm hotspot/P2P/service modes actually exposed on the owner Android system, then measure simultaneous Wi-Fi transfer and BT audio/input.

**Linux procedure:**

1. Exercise each confirmed service with a known peer and repeat reconnects.
2. Run 30 minutes of Wi-Fi load with BT audio and keyboard/pen auxiliary events; measure dropouts, transfer performance and energy.

**Required result:**

- `WIFI-02.C01`: Every confirmed radio service is usable and recovers; no hidden radio disable is used to pass coexistence.
- `WIFI-02.C02`: No audible/event loss or radio firmware crash, and the frozen simultaneous-workload comparison is met.

Minimum repetitions: 3. Duration: 30 min coexistence. Comparison profiles: paired-throughput, paired-latency, paired-energy.

### BT-01

**Bluetooth controller, BLE/HID and audio profiles** — `not_run`.

**Known baseline:** BT pen input 17ef:612b is present on Android. Research2 has available Bluetooth/UART ancestors and compiled QCA/power-sequencing drivers, but no physical probe. Its qca/htbtfw%02x.tlv and qca/htnv%02x.bin suffix is chosen from runtime ROM information; the suffix and all owner Linux HCI/profile behavior remain untested.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX, FIRMWARE-CONTRACT, STOCK-FIRMWARE-RECEIPT. Dependencies: SYS-01.

**Before running:** Owned test BLE/HID and audio peers; record supported profiles and codec/microphone route.

**Android work still required:** Confirm Android profile support, connect times, range and 30-minute audio/input behavior on the same peers.

**Linux procedure:**

1. Verify btqca/HCI firmware and controller, pair/reconnect 20 times, and test BLE/HID input.
2. Run stereo playback and any confirmed headset microphone profile for 30 minutes; inspect dropouts and latency.
3. Repeat after suspend, airplane/radio toggles through supported userspace and controller recovery.

**Required result:**

- `BT-01.C01`: All confirmed profiles work with actual traffic/audio and no controller reset loop.
- `BT-01.C02`: No external USB Bluetooth adapter or pen inking is substituted for the internal BT controller.

Minimum repetitions: 3. Duration: 30 min audio/profile stability. Comparison profiles: paired-quality, paired-latency.

### USB-01

**USB-C device role, link speed and data integrity** — `not_run`.

**Known baseline:** Owner Type-C snapshot reports sink/device; PS5169 is bound. The running Android configuration enables NCM/FunctionFS but not ACM; configuration alone does not identify active functions. Generic USB_PD labels do not prove data speed or a PD contract.

Evidence: ANDROID-STOCK, ANDROID-BOOT-CAPABILITIES, POWER-SOURCE, HISTORICAL-MATRIX. Dependencies: SYS-01, PWR-01.

**Before running:** Known data cable and same host port, both plug orientations; distinct charging-only and data-capable accessories.

**Android work still required:** Record actual owner Android device-role functions and negotiated USB speeds, then transfer the same test data.

**Linux procedure:**

1. Enumerate intended Linux USB data functions and negotiated speed; transfer and verify a test file of at least 1 GiB.
2. Repeat 20 attach/detach events and sleep recovery in both orientations while monitoring charging role.
3. Measure protocol-matched throughput; retain USB controller/redriver errors and any renegotiation.

**Required result:**

- `USB-01.C01`: Confirmed device-role data functions and stock-equivalent physical link speed work with correct hashes.
- `USB-01.C02`: No role confusion, reset loop or loss of charging; USB2-only operation cannot satisfy verified Android SuperSpeed capability.

Minimum repetitions: 20. Comparison profiles: paired-throughput.

Command templates: `usb-tree` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### USB-02

**USB host, hub and role switching** — `not_run`.

**Known baseline:** Dual-role support is advertised in owner Android Type-C class; host/dock functionality is not measured in the capture.

Evidence: ANDROID-STOCK, POWER-SOURCE, HISTORICAL-MATRIX. Dependencies: USB-01.

**Before running:** Known hub, keyboard and storage peripheral; both connector orientations; one charger/Type-C policy owner.

**Android work still required:** Verify Android host mode, simultaneous hub devices, external power and supported role changes with the exact accessories.

**Linux procedure:**

1. Attach USB keyboard/storage/hub; perform known-file transfers and input checks.
2. Cycle host/device and powered/unpowered hub states 20 times, verifying VBUS/data roles and orderly detach.
3. Repeat with DP/audio and after suspend, using only supported role interfaces.

**Required result:**

- `USB-02.C01`: All confirmed host functions and peripherals operate with data integrity and correct power/data roles.
- `USB-02.C02`: No conflicting TCPM/legacy charger writers, phantom power source state or permanent rebind requirement.

Minimum repetitions: 20. Comparison profiles: paired-throughput.

Command templates: `usb-tree` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### AUDIO-01

**All internal speakers and amplifier calibration** — `blocked`.

**Known baseline:** Owner Android registers kona-qrd-snd-card and 32 PCM interfaces, with tfa98xx drivers actually bound at I2C addresses 0x34..0x37. These prove neither exact TFA9894 silicon/revision nor QS/YC selection, calibration or four working speakers. Research2 disables all four amplifier nodes, leaves SND_SOC_TFA989X unset, and that generic driver lacks a TFA9894 match/QS-YC request. Available ADSP/PAS configuration is not a working audio service.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX, DISTRO-SOURCE, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT. Dependencies: SYS-02.

**Current blocker:** Exact amplifier silicon/acoustic calibration, TDM routing and controlled speaker baseline remain unresolved; the research2 amplifier path is disabled and lacks compatible DSP/driver integration.

**Before running:** Exact board/amp calibration and TDM routing confirmed before playback; same measured reference sound level, not raw mixer percentage.

**Android work still required:** Confirm every physical speaker, channel assignment, normal volume range and reference tone/speech response under Android.

**Linux procedure:**

1. Verify native ALSA/ASoC path, correct calibration choice and all four output channels with attended reference audio.
2. Test stereo balance, volume/mute, 30-minute playback, routing and resume; inspect underruns and amp errors.
3. Compare noise/distortion and level using the same measurement position and normal reference output.

**Required result:**

- `AUDIO-01.C01`: Every fitted internal speaker functions with correct routing and calibration, without distortion, clipping, reset or thermal-protection bypass.
- `AUDIO-01.C02`: USB/BT audio, partial speaker count or an ALSA card list cannot substitute for internal-speaker completion.

Minimum repetitions: 3. Duration: 30 min sustained playback. Comparison profiles: paired-quality, paired-energy.

Command templates: `audio-playback-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### AUDIO-02

**Internal microphones, capture and duplex audio** — `blocked`.

**Known baseline:** Owner ALSA exposes capture-capable PCM names within 32 registered interfaces. The DT declares Bolero/WCD938x and SoundWire candidates, but exact codec revision/binding and physical microphone count, placement, routing and capture quality were not established. No audio stream was opened.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-01.

**Current blocker:** Owner microphone inventory and Linux capture path remain unresolved.

**Before running:** Known nonpersonal speech/tone source, fixed position/level; identify all owner-present microphone channels.

**Android work still required:** Record Android microphone count/routes, noise level, gain, recording modes and duplex/echo behavior.

**Linux procedure:**

1. Capture a fixed test sequence on every fitted input; compare channel orientation, sample timing, clipping and noise.
2. Run simultaneous speaker playback and capture for ten minutes; test mute/privacy controls and resume.
3. Exercise the intended desktop communication/capture application and retain sanitized metrics.

**Required result:**

- `AUDIO-02.C01`: Every confirmed internal microphone is usable with correct timing and routing; no silent channel or persistent feedback.
- `AUDIO-02.C02`: Duplex and applicable echo-control behavior meet the frozen reference; external headset input is not a substitute.

Minimum repetitions: 3. Duration: 10 min duplex. Comparison profiles: paired-quality, paired-latency.

Command templates: `audio-capture-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### AUDIO-03

**USB-C analog/digital and headset route changes** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** Owner 8-0042 fsa4480-i2c is actually bound to fsa4480-driver. ALSA includes USB/hostless route names, but analog/digital accessory routing was not exercised. Bound RTC6226/radio0 has separate FM-01 acceptance; its audio route must coexist with these paths.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: AUDIO-01, AUDIO-02, USB-02, BT-01.

**Before running:** Only owner-confirmed analog/digital adapters and headset controls; exact accessories on both systems.

**Android work still required:** Confirm which USB-C analog/digital routes, headset microphone/buttons and jack/adapter changes Android supports.

**Linux procedure:**

1. Play and capture through each confirmed route; test volume, microphone, headset buttons and automatic return to speakers.
2. Exercise 20 hotplug/routing changes and repeat with charge/dock coexistence. After FM-01 establishes the tuner route, revisit applicable headset/speaker switching and FM coexistence without substituting streaming radio.

**Required result:**

- `AUDIO-03.C01`: Each confirmed route and control works without wrong-channel audio, silent capture or stuck default device.
- `AUDIO-03.C02`: Working one external route does not hide incomplete internal speaker/microphone tests.

Minimum repetitions: 20. Comparison profiles: paired-quality.

### FM-01

**RTC6226 tuning, reception, audio and recovery** — `blocked`.

**Known baseline:** Owner Android I2C client 6-0064 is bound to rtc6226, and radio0 is named rtc6226-fmtuner. This establishes registration/binding, not a received station, actual frequency band, antenna path, stereo/RDS capability, quality, power use or Linux support. No tuner command or audio stream was opened.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-01, PWR-01.

**Current blocker:** Usable owner FM reception, antenna/accessory and audio-route baseline have not been established; native Linux tuning, reception, power and recovery are untested.

**Before running:** Identify the actual receive-only tuner/antenna and audio path from the owner Android baseline before Linux tuning; use the same antenna/headset, position, frequencies, audio level and stable RF conditions. Validate AUDIO-03 routes if an external accessory is required. Record locally supported band/channel spacing and only owner-confirmed features such as seek, stereo or RDS; keep device identity separate from package/app presence.

**Android work still required:** Confirm the owner can receive FM using its fitted tuner and establish the required antenna/accessory and internal/headset audio routes. Record supported band, tuning steps, stable reference stations and any confirmed seek/stereo/RDS behavior. Measure reception stability, channel separation/audio noise, tuning/recovery latency and calibrated energy under matched RF/audio conditions; repeat enough paired intervals to distinguish broadcast variation from a platform regression.

**Linux procedure:**

1. Verify the native Linux driver and bound physical radio device, then use the supported tuner API to tune the same reference frequencies and exercise every confirmed tune/seek/control mode.
2. Receive and route audio for 30 minutes per required route; compare dropouts, mono/stereo behavior, quality and matched energy. Verify RDS or other metadata only where the Android baseline establishes that feature.
3. Repeat 20 open/close, station-change and applicable antenna/headset attach cycles; verify correct speaker/headset routing and that closing the session releases power.
4. After the platform suspend test, verify wake/reopen/reception and route restoration. Exercise applicable simultaneous Wi-Fi, Bluetooth, charging and display workloads and compare reception, audio and energy with the same Android scenario.

**Required result:**

- `FM-01.C01`: The fitted receiver actually receives the required reference signals and exposes all owner-confirmed tuning/control features through the intended application, with correct audio routing.
- `FM-01.C02`: Reception/audio quality, latency and energy meet the frozen matched Android comparison; no persistent dropout, stuck route, tuner reset loop or post-close high-power state.
- `FM-01.C03`: The receiver and selected audio route recover after lifecycle and suspend tests. An online radio stream, external tuner or missing mainline driver cannot satisfy this case or justify marking the fitted receiver absent.

Minimum repetitions: 3. Duration: 30 min per required route; 20 lifecycle cycles. Comparison profiles: paired-quality, paired-latency, paired-energy.

### CAM-01

**Rear camera still/video and application pipeline** — `blocked`.

**Known baseline:** Owner CameraService ID 0, BACK, HAL 3.5; pixelArraySize 3264x2448, orientation 90 degrees; raw activeArraySize [0,0,3264,2448]; advertised AE FPS pairs [15,15], [12,30], [30,30]. These static tags are not a complete output-stream matrix or measured frame rate. No frames were captured. Generic qcom,cam-sensor/cam-sensor-driver entries do not identify silicon; historical S5K4H7 remains an unconfirmed source lead for this owner.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-02.

**Current blocker:** Owner rear static role/array metadata is available, but silicon identity, full stream matrix, controlled image/video baseline and native Linux capture remain unresolved.

**Before running:** Confirm fitted module and exact power/clock/reset/calibration first; controlled test chart/light, same supported streams and app processing policy.

**Android work still required:** Resolve the owner rear camera silicon/module and full supported output format/resolution/frame-rate matrix, focus behavior if present, and exposure/white-balance ranges. Verify the advertised orientation dynamically; do not turn pixel-array size into an assumed streaming mode. Capture matched test charts and timed video with a known audio marker; freeze the actual stream matrix before Linux trials.

**Linux procedure:**

1. Use native CAMSS/CCI plus the verified sensor/libcamera path to take 30 stills and ten-minute video per required mode.
2. Compare image orientation, geometry, color/exposure, frame count/timestamps, applicable focus and AV synchronization.
3. Repeat open/close, app handoff and post-suspend recovery; inspect CSI/ISP errors and dropped frames.

**Required result:**

- `CAM-01.C01`: The fitted rear camera delivers real frames in every owner-confirmed required stream mode with correct controls.
- `CAM-01.C02`: No black/corrupt frames, persistent CSI errors or unexplained frame loss; a webcam or other camera cannot substitute.

Minimum repetitions: 3. Duration: 30 stills plus 10 min per required stream. Comparison profiles: paired-quality, paired-latency.

Command templates: `camera-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### CAM-02

**Front camera still/video and application pipeline** — `blocked`.

**Known baseline:** Owner CameraService ID 1, FRONT, HAL 3.5; pixelArraySize 4240x3152, orientation 270 degrees; raw activeArraySize [16,16,4208,3120]; advertised AE FPS pairs [15,15], [10,30], [30,30]. These static tags are not a complete output-stream matrix or measured frame rate. No frames were captured. Generic qcom,cam-sensor/cam-sensor-driver entries do not identify silicon; historical HI1339 remains an unconfirmed source lead for this owner.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-02.

**Current blocker:** Owner front static role/array metadata is available, but silicon identity, full stream matrix, controlled image/video baseline and native Linux capture remain unresolved.

**Before running:** Confirm fitted module and exact power/clock/reset/calibration first; controlled test chart/light, same supported streams and app processing policy.

**Android work still required:** Resolve the owner front camera silicon/module and full supported output format/resolution/frame-rate matrix, focus behavior if present, and exposure/white-balance ranges. Verify the advertised orientation dynamically; do not turn pixel-array size into an assumed streaming mode. Capture matched test charts and timed video with a known audio marker; freeze the actual stream matrix before Linux trials.

**Linux procedure:**

1. Use native CAMSS/CCI plus the verified sensor/libcamera path to take 30 stills and ten-minute video per required mode.
2. Compare image orientation, geometry, color/exposure, frame count/timestamps, applicable focus and AV synchronization.
3. Repeat open/close, app handoff and post-suspend recovery; inspect CSI/ISP errors and dropped frames.

**Required result:**

- `CAM-02.C01`: The fitted front camera delivers real frames in every owner-confirmed required stream mode with correct controls.
- `CAM-02.C02`: No black/corrupt frames, persistent CSI errors or unexplained frame loss; a webcam or other camera cannot substitute.

Minimum repetitions: 3. Duration: 30 stills plus 10 min per required stream. Comparison profiles: paired-quality, paired-latency.

Command templates: `camera-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### SENS-01

**Accelerometer, gyroscope, magnetometer and orientation** — `blocked`.

**Known baseline:** Owner SensorService advertises TDK-Invensense icm4x6xx accelerometer/gyroscope at 1..400 Hz and QST qmc630x magnetometer at 1..100 Hz, with wakeup/non-wakeup and calibrated/uncalibrated variants. These are HAL family/rate declarations, not measured samples or exact chip IDs. No BMI3x0 descriptor is present. The three captured IIO devices are PMIC ADCs. Research2 DSP OF availability/PAS firmware paths do not establish sensor transport, authentication or delivered data.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX, FIRMWARE-CONTRACT, STOCK-FIRMWARE-RECEIPT. Dependencies: SYS-02.

**Current blocker:** Owner service-level families are recorded; exact transport/axes, measured sample-rate/quality baseline, DSP services and the native Linux sensor path remain unresolved.

**Before running:** Confirm fitted parts/firmware and orientation matrices; fixed physical orientation/motion test, recorded sample rates.

**Android work still required:** Resolve exact parts/transports and axes using the current icm4x6xx/qmc630x leads; do not import historical BMI3x0 orientation or firmware assumptions. Measure actual units, timestamps, rates/loss, six-face gravity response, gyro zero/rate response, heading and confirmed fusion/gesture behavior.

**Linux procedure:**

1. Verify native sensor/remoteproc/IIO paths and timestamped data; repeat six faces, calibrated rotations and stationary intervals.
2. Test desktop orientation changes and lock, then sensor recovery/power-down after inactivity and suspend.
3. Compare units, bias/noise, timing, axes and orientation latency with the matched Android baseline.

**Required result:**

- `SENS-01.C01`: Every fitted motion/magnetic sensor supplies correctly scaled, oriented and timestamped data without missing samples at required rates.
- `SENS-01.C02`: Auto-rotation/fusion is usable; software fixed rotation or a powered-off sensor cannot count as completion.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

### SENS-02

**Ambient/RGB sensing and automatic brightness** — `not_run`.

**Known baseline:** Owner SensorService advertises ams AG tcs3408 ambient-light and RGB wakeup/non-wakeup descriptors. Their retained delay fields are zero; no periodic rate is established. Illumination/color response, calibration and automatic-brightness behavior were not measured.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, DISP-03.

**Before running:** Fixed low/mid/high illumination and color reference; distinguish actual sensor data from desktop policy.

**Android work still required:** Confirm owner ALS/RGB capabilities, dynamic response, calibration and automatic-brightness behavior.

**Linux procedure:**

1. Measure monotonic response and timestamps under each reference light; cover/uncover and change light repeatedly.
2. Verify native sensor data feeds usable automatic brightness, with sensible transitions and suspend recovery.

**Required result:**

- `SENS-02.C01`: Every owner-present ALS/RGB channel works and automatic brightness responds without oscillation or a stuck level.
- `SENS-02.C02`: Manual fixed brightness is a useful diagnostic but does not satisfy the confirmed automatic feature.

Minimum repetitions: 20. Comparison profiles: paired-quality, paired-latency.

### STOR-01

**UFS filesystem integrity, throughput and recovery** — `not_run`.

**Known baseline:** UFS is present in the historical board inventory; this collection did not measure owner storage throughput or filesystem behavior.

Evidence: HISTORICAL-MATRIX, DISTRO-SOURCE. Dependencies: SYS-01, SYS-02.

**Before running:** Only an allocated test file under an explicitly selected Linux data filesystem; never raw block-device or Android-partition writes. Record encryption/filesystem/free space/cache policy.

**Android work still required:** Measure the same file workload on an owner-authorized Android test directory with comparable cache/crypto conditions.

**Linux procedure:**

1. Copy, fsync and read/verify at least a 512 MiB generated fixture for three trials; retain file hashes and timings.
2. Check the fixture after controlled reboot and suspend, and exercise concurrent app/storage traffic.
3. Inspect UFS error/correctness counters and performance under the same validated power policy.

**Required result:**

- `STOR-01.C01`: Every verified file remains intact across controlled reboot/suspend and no UFS recovery/error loop occurs.
- `STOR-01.C02`: The intended storage path and filesystem remain usable; redirecting data to another device cannot hide a UFS gap.

Minimum repetitions: 3. Comparison profiles: paired-throughput, paired-energy.

### STOR-02

**microSD compatibility, integrity and safe reinsert** — `not_run`.

**Known baseline:** Owner Android exposes mmcblk0 with three partitions. No card identity, filesystem, negotiated speed or integrity trial was captured. Historical R226 card guards and SD150 experiments do not establish this card or universal high-speed support.

Evidence: ANDROID-BOOT-CAPABILITIES, HISTORICAL-MATRIX, DISTRO-SOURCE. Dependencies: STOR-01, SYS-02.

**Before running:** Owner-confirmed card and supported bus modes; use a removable test card that is not the active root filesystem for insertion tests. Preserve the actual three-partition layout and select an ordinary test file; do not assume the historical two-partition installation layout or remove card-specific guards to claim support.

**Android work still required:** Record owner card capacity, negotiated standard mode and same-file Android integrity/throughput; keep CID/serial private.

**Linux procedure:**

1. Run three filesystem file/verify trials and post-reboot checks on the selected card.
2. Perform 20 orderly unmount/reinsert events for a non-root test card, or document reboot-only testing when it is the root medium.
3. Verify recovery after suspend and concurrent Wi-Fi/USB use without command/CRC errors.

**Required result:**

- `STOR-02.C01`: The tested card works at its confirmed supported mode with zero data corruption and reliable detection.
- `STOR-02.C02`: A single guarded card result is not generalized to all cards; untested card/mode combinations remain explicit.

Minimum repetitions: 3. Comparison profiles: paired-throughput.

### PWR-01

**Fuel-gauge units, sign, trends and desktop reporting** — `not_run`.

**Known baseline:** MM8013C06 at I2C0x55 is confirmed. Android shows 28%, 34.1 C, 3.789 V, +426000 uA while Charging; charge_counter=90 is not calibrated.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: SYS-01.

**Before running:** Same battery; unplugged and charging samples over time; distinguish net battery current from USB input current.

**Android work still required:** Validate sign/units and stored-charge trends under discharge/charge; compare with an appropriate independent reference and determine which counters are trustworthy.

**Linux procedure:**

1. Identify the actual Linux gauge supply and supported attributes; compare voltage/temp/SOC and sign with charge/discharge trends.
2. Verify desktop reporting and low-battery behavior using normal operating ranges, including rest/reboot/resume.
3. Record unavailable/invalid counters as unknown; establish measurement uncertainty before any energy claim.

**Required result:**

- `PWR-01.C01`: Telemetry is coherent in units/sign/trends and reports missing data correctly instead of zero.
- `PWR-01.C02`: A battery icon, equal design/full capacity or a single reading is not accepted as health, efficiency or charge-policy proof.

Minimum repetitions: 3. Comparison profiles: paired-quality.

### PWR-02

**Sustained charging and actual negotiated protocols** — `blocked`.

**Known baseline:** Owner sample has real_type USB_HVDCP_3, pd_active=0 and input-voltage reading about7.137 V despite generic PD labels. Sustained rates and PD capability remain unmeasured.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: PWR-01, USB-01.

**Current blocker:** Complete single-owner charger/protocol implementation and controlled owner rate baseline remain open.

**Before running:** One Type-C/charger policy owner; same known charger/cable, starting SOC window and temperature; independent input/protocol evidence where available.

**Android work still required:** Measure owner stock-charger HVDCP behavior, sustained net charge trend and rate; separately test an appropriate PD source to establish actual PD capability.

**Linux procedure:**

1. Measure at least 45 minutes of steady charging, tracking actual protocol/contract, input voltage/current, net battery trend and temperature.
2. Perform 20 replug cycles in both orientations, changing between confirmed chargers and repeating screen-off and sleep conditions.
3. Verify policy ownership and watchdog continuity, including after driver/application recovery; record protocol downgrades.

**Required result:**

- `PWR-02.C01`: All confirmed owner charging modes negotiate and sustain charging with no resets, repeated manual recovery or unexplained stop.
- `PWR-02.C02`: Generic PD class labels, online=1, a slow fixed5V fallback or inherited charging alone cannot satisfy confirmed fast-charge capability.
- `PWR-02.C03`: Net stored charge rises consistently and rate/temperature meet the matched baseline without bypassing policy limits.

Minimum repetitions: 3. Duration: 45 min steady trial;20 replug cycles. Comparison profiles: paired-throughput, paired-quality.

### PWR-03

**Charge limits, thermal controls and watchdog ownership** — `blocked`.

**Known baseline:** Android SMB5 DT has JEITA enabled,16 thermal entries and16-second watchdog bark. Historical R189/R231/R235/TCPM helpers have mutually constrained ownership.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: PWR-02.

**Current blocker:** Reviewed complete policy/ownership and protection-test evidence are not available.

**Before running:** Reviewed driver policy and normal operating thermal conditions; no competing raw-register helper and TCPM owner.

**Android work still required:** Record owner charge-hold/hysteresis features and normal temperature/current-limit behavior; preserve original policy limits.

**Linux procedure:**

1. Verify the selected Linux driver owns Type-C/charging and supported charge-limit requests; exercise normal limit/hysteresis transitions.
2. Validate boundary/invalid-input handling in a driver-level controlled test and confirm normal runtime telemetry/protection behavior.
3. Check watchdog servicing and shutdown/unplug behavior; do not deliberately overheat/overcharge hardware or suppress protection to complete a test.

**Required result:**

- `PWR-03.C01`: Charge-limit, JEITA/thermal and watchdog policy retain correct ownership and fail safely on invalid/missing data.
- `PWR-03.C02`: No blanket protection disable, forced high current, fake battery bypass or simultaneous legacy/TCPM writes.
- `PWR-03.C03`: Any untested protection path is documented and blocks a blanket best-state claim.

Minimum repetitions: 3. Comparison profiles: fixed functional criteria only.

### PM-01

**Screen-on/off idle and runtime power management** — `not_run`.

**Known baseline:** Android exposes WFI/rail-pc;8-second trace shows dynamic CPU/GPU states but no residency or energy result. Several runtime-PM getters report unsupported.

Evidence: ANDROID-STOCK, ANDROID-TRACE, POWER-SOURCE. Dependencies: PWR-01, DISP-03, WIFI-01, BT-01, KEY-01.

**Before running:** Matched measured luminance/refresh/radio and cover states; same SOC window and ambient; calibrated energy measurement.

**Android work still required:** Collect three30-minute screen-on idle and three30-minute screen-off idle baselines with identical radio/wake policy and before/after counters.

**Linux procedure:**

1. Measure the paired Linux conditions with CPU/GPU/radio/display runtime-state counter deltas and calibrated energy.
2. Verify that idle devices can sleep and still respond to their intended wake source; check interrupt/wakelock activity without collecting app names.
3. Separate normal runtime power management from full-system suspend; document unavailable residency metrics.

**Required result:**

- `PM-01.C01`: Idle energy meets the frozen comparison with all intended features enabled; no forced airplane mode or disabled input used as an equivalent test.
- `PM-01.C02`: State transitions and wake behavior work; unsupported getters or missing trace events are not converted to zero power/residency.

Minimum repetitions: 3. Duration: 30 min per condition. Comparison profiles: paired-energy.

### PM-02

**Real suspend entry, wake and complete device restoration** — `not_run`.

**Known baseline:** Android advertises freeze/mem and selects deep, but cumulative4146 successes/1941 failures are historical counters; no controlled cycle was captured.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: SYS-01, DISP-01, TOUCH-01, KEY-01, WIFI-01, BT-01, PWR-01.

**Before running:** Verified recovery/wake path, matched radio wake policy; battery/charger and cover-attached/detached matrix; actual suspend-state evidence.

**Android work still required:** Measure20 controlled Android cycles, wake sources and resume timing, plus3 overnight intervals with matched conditions and counter deltas.

**Linux procedure:**

1. Perform20 Linux suspend/resume cycles distributed across battery/charger and keyboard states; verify actual platform entry from counter/trace/residency evidence.
2. After each wake check display, touch, pen, keyboard/pad, radios, audio, storage and gauge; run GPU render/readback again when that gate is ready.
3. Run three8-hour sleep intervals and compare calibrated energy, spurious wakes and recovery.

**Required result:**

- `PM-02.C01`: Every planned cycle resumes to the full usable session with no new failed-suspend counter delta, stuck driver or reset.
- `PM-02.C02`: Panel blanking, an idle userspace process, disabled peripherals or s2idle substituted for confirmed deep-sleep behavior cannot be labeled equivalent.
- `PM-02.C03`: Sleep energy and resume timing meet the frozen owner comparison.

Minimum repetitions: 20. Duration: 20 cycles plus3x8h sleep. Comparison profiles: paired-energy, paired-latency.

Command templates: `sleep-mode`, `suspend-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### THERM-01

**Sustained CPU/GPU performance and thermal regulation** — `not_run`.

**Known baseline:** Android cpufreq policies were constrained during the snapshot and changed later. GPU advertises up to683MHz in this capture; neither field is a universal hardware ceiling.

Evidence: ANDROID-STOCK, ANDROID-GPU, ANDROID-TRACE, POWER-SOURCE. Dependencies: GPU-02, GPU-03, PWR-01, PM-01.

**Before running:** Matched workload/data/build, starting temperature, measured luminance, SOC/charger and ambient; retain normal DVFS/thermal/voltage policy.

**Android work still required:** Measure three20-minute common CPU/GPU workloads on Android, including last10-minute throughput, temperature envelope and idle recovery.

**Linux procedure:**

1. Run the same comparable workloads on Linux and record rolling throughput, tail latency, thermal zones and throttling decisions.
2. Return to idle and confirm frequency/power/temperature recovery; repeat with a normal combined display/network workload.
3. Identify any limitation owner; never infer a new OPP or voltage from a snapshot maximum or another board.

**Required result:**

- `THERM-01.C01`: Sustained rather than burst performance meets the frozen matched comparison, without thermal/voltage protection bypass.
- `THERM-01.C02`: No emergency shutdown, watchdog reset, unbounded temperature rise or persistent post-load high-power state; normal safe throttling is interpreted with Android comparison.

Minimum repetitions: 3. Duration: 20 min sustained plus idle cooldown. Comparison profiles: paired-throughput, paired-latency, paired-energy, paired-quality.

### GPU-01

**Actual native MSM device, firmware and API inventory** — `not_run`.

**Known baseline:** Android has KGSL and msm_drm render nodes. Host ELF/MDT GPU packages now exist. Research2 GPU/GMU/ZAP nodes are available and its three requests match the staged paths, but physical driver probe, firmware authentication and Linux GPU initialization have not been exercised.

Evidence: ANDROID-GPU, GPU-STAGE-ELF, GPU-STAGE-MDT, GPU-SOURCE, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT. Dependencies: SYS-01.

**Before running:** Actual Linux tablet, coherent distro Mesa/GLVND/GBM/ICD stack, no KGSL launch overrides, no software renderer.

**Android work still required:** Record owner Android actual GL/GLES/Vulkan capabilities and application requirements separately from mode or device-node names.

**Linux procedure:**

1. Collect passive GPU evidence, then fixed EGL/Vulkan/KWin queries on the actual device.
2. Verify driver/physical-device identity, render permissions, loaded firmware/provenance, GMU/SMMU initialization and resolved config.
3. Freeze required API versions/features for the chosen apps using this Mesa driver build; do not copy release-wide version maxima.

**Required result:**

- `GPU-01.C01`: A650/FD650 is genuinely available through native MSM/Freedreno/Turnip with the expected firmware and no initialization faults.
- `GPU-01.C02`: No llvmpipe/lavapipe, old KGSL/msm_drm, forced version strings or TU_DEBUG=noconform is used to satisfy a requirement.
- `GPU-01.C03`: Enumeration alone is reported only as this gate, not as rendering, presentation, isolation or video success.

Minimum repetitions: 1. Comparison profiles: fixed functional criteria only.

Command templates: `gpu-passive`, `gpu-enumeration` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### GPU-02

**OpenGL/GLES hardware draw and readback correctness** — `not_run`.

**Known baseline:** No owner GL/GLES rendering result exists; driver/API enumeration is not a draw test.

Evidence: ANDROID-GPU, GPU-SOURCE. Dependencies: GPU-01.

**Before running:** Pinned GLES/desktop-GL context requirements and a coherent native Mesa driver; deterministic common test scenes and reference images.

**Android work still required:** Run comparable supported GLES scenes and record rendered-reference/feature behavior under Android; desktop-GL-only requirements use an explicit separate reference suite.

**Linux procedure:**

1. Create every required context, draw known color/depth/texture/blend/FBO scenes and compare GPU readbacks with reference tolerances.
2. Repeat with multiple windows/contexts and30-minute rendering, then after compositor restart and suspend.
3. Record actual renderer/context/API version and errors for each run, not only a version query.

**Required result:**

- `GPU-02.C01`: All required GL/GLES feature tests produce correct readbacks on A650 with no graphics corruption or unexplained reset.
- `GPU-02.C02`: Software GL, API-version spoofing or a benchmark showing only frame counters cannot pass.

Minimum repetitions: 3. Duration: 30 min stability. Comparison profiles: paired-throughput, paired-energy.

### GPU-03

**Vulkan submissions, synchronization and readback** — `not_run`.

**Known baseline:** No owner Vulkan submission or correctness result exists; Turnip package/ICD presence is host evidence only.

Evidence: ANDROID-GPU, GPU-SOURCE, NIX-HOST. Dependencies: GPU-01.

**Before running:** Actual Adreno650 Vulkan physical device, fixed API/features, deterministic workload and validated native ICD.

**Android work still required:** Run common supported Vulkan draw/compute/copy/synchronization scenes under Android using the same test revision where possible.

**Linux procedure:**

1. Exercise command submission, images/buffers, barriers/fences, compute if required, and host readback against known references.
2. Repeat multi-context/window presentation and30-minute steady workload, then resume and application restart.
3. Record device-lost events, validation findings, output errors and actual physical-device API/features.

**Required result:**

- `GPU-03.C01`: Required Vulkan workloads submit and complete with correct results on the hardware device.
- `GPU-03.C02`: Lavapipe/software WSI, noconform overrides or an ICD JSON file alone cannot satisfy Vulkan operation.

Minimum repetitions: 3. Duration: 30 min stability. Comparison profiles: paired-throughput, paired-energy.

### GPU-04

**Wayland/KWin hardware composition and native presentation** — `not_run`.

**Known baseline:** Historical launchers infer GPU enablement from paths and may force Zink/private ICD/software WSI. Simpledrm CPU-copy presentation is distinct from native DPU/DSI.

Evidence: GPU-SOURCE, DISPLAY-SOURCE. Dependencies: GPU-02, GPU-03, DISP-01, DISP-02.

**Before running:** Single coherent userspace graphics stack; actual compositor GPU FD/renderer and scanout path observed.

**Android work still required:** Record a matched owner interactive workload: scrolling, window/app transitions and video/pen interaction at selected rates.

**Linux procedure:**

1. Observe KWin renderer and open GPU device, then test GBM/dma-buf import, window movement, scaling and mixed GL/Vulkan apps.
2. Freeze the actually supported dma-buf formats/modifiers and implicit/explicit synchronization combinations for this stack, then exercise each required combination under load and after recovery; do not infer support from package versions.
3. Measure frame pacing and input latency on native DPU output; separately label any inherited-framebuffer copy diagnostic.
4. Run session restart, display transitions and pen interaction with no stale launcher overrides.

**Required result:**

- `GPU-04.C01`: KWin and test applications actually use A650, with correct native full-panel presentation and pacing.
- `GPU-04.C02`: Path existence, software composition or simpledrm copies are not promoted to complete native display/GPU integration.

Minimum repetitions: 3. Comparison profiles: paired-latency, paired-energy.

Command templates: `gpu-enumeration` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### GPU-05

**Per-process GPU address-space isolation and bounded recovery** — `blocked`.

**Known baseline:** R185/global-page-table workaround removes qcom,adreno-smmu. Source compatibility and host tests do not restore process isolation.

Evidence: GPU-SOURCE, DISTRO-SOURCE. Dependencies: GPU-02, GPU-03.

**Current blocker:** Per-process GPU SMMU restoration and a reviewed bounded isolation/fault test are still unresolved.

**Before running:** Per-process SMMU capability restored and observed at runtime; disposable attended graphics session with known recovery path and reviewed upstream self-test.

**Android work still required:** Record Android context/fault behavior where a comparable supported test exists; no private-process memory is used.

**Linux procedure:**

1. Verify compiled DT/kernel and runtime context records show separate process address spaces, not merely two successful apps in one global domain.
2. Use two owned test processes with separate test buffers; run the reviewed isolation case and a bounded context termination/timeout recovery case.
3. Confirm the unaffected process continues correctly, no cross-process data is exposed/corrupted, the device recovers and subsequent GL/Vulkan tests pass.

**Required result:**

- `GPU-05.C01`: Per-process isolation is actually active; retaining the global address-space workaround is an explicit unresolved degradation.
- `GPU-05.C02`: The selected fault stays contained, recovery is bounded and usable rendering returns without a tablet reboot or unrelated data damage.
- `GPU-05.C03`: A passing multiclient stress test alone is not evidence of memory isolation.

Minimum repetitions: 3. Comparison profiles: fixed functional criteria only.

### VIDEO-01

**Native hardware decode and application use** — `blocked`.

**Known baseline:** Owner video32/video33 are bound to Android msm_vidc_v4l2, which is not mainline Venus evidence. Research2 enables the required Kconfig parent and Venus module, but its compiled video-codec parent node remains disabled. The exact conditional request is qcom/vpu-1.0/venus.mbn with required indexed siblings. Owner codec/stream matrix, firmware HFI ABI/authentication and hardware decoding remain unverified.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, GPU-SOURCE, DISTRO-SOURCE, KERNEL-HOST, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT. Dependencies: SYS-02, GPU-04, AUDIO-01.

**Current blocker:** Owner codec matrix and enabled/native Venus hardware result are missing.

**Before running:** Confirmed codec/bit-depth/resolution/frame-rate matrix; known clips with hashes and the same display/audio conditions.

**Android work still required:** Record owner Android hardware decoder identity and supported stream matrix, then play representative H264/HEVC and any other confirmed codec modes.

**Linux procedure:**

1. Enable and verify the actual Venus driver/firmware/queues, then decode representative clips for ten minutes per required mode.
2. Prove the application uses hardware decoding rather than silently falling back, and verify frame correctness, drops and AV synchronization.
3. Repeat seek, pause/resume, app restart and post-suspend playback; compare CPU time/energy with the hardware Android baseline.

**Required result:**

- `VIDEO-01.C01`: Each confirmed required codec/mode uses real hardware decoding with correct frames and synchronized audio.
- `VIDEO-01.C02`: Software decoding, codec-package presence, working OpenGL or a V4L2 node alone cannot count as hardware video support.

Minimum repetitions: 3. Duration: 10 min per required stream. Comparison profiles: paired-quality, paired-energy.

### VIDEO-02

**Hardware encode where stock exposes it** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** No owner encode capability or native Linux encoding result was captured. The research2 Venus parent remains disabled; available encoder/decoder child nodes do not make that parent operational.

Evidence: HISTORICAL-MATRIX, GPU-SOURCE, FIRMWARE-CONTRACT. Dependencies: SYS-02, CAM-01, CAM-02.

**Before running:** Only owner-confirmed hardware encode modes; known raw/video source and explicit application encoder selection.

**Android work still required:** Identify Android hardware encoders and required camera/screen recording modes, formats and rates.

**Linux procedure:**

1. Encode a known source through the native hardware path and decode/check the produced bitstream and timestamps.
2. Test ten-minute capture/encode, pause/restart and concurrent audio; record actual encoder driver and application route.

**Required result:**

- `VIDEO-02.C01`: Every confirmed required hardware encoding mode produces correct, playable output at its specified rate.
- `VIDEO-02.C02`: CPU encoding is recorded as a fallback and cannot satisfy a confirmed hardware-encode feature.

Minimum repetitions: 3. Duration: 10 min per mode. Comparison profiles: paired-throughput, paired-quality, paired-energy.

### SYS-03

**Complete daily-use combination and soak** — `not_run`.

**Known baseline:** No owner Linux session has completed any functional gate in this ledger.

Evidence: ANDROID-STOCK, GPU-SOURCE, POWER-SOURCE. Dependencies: SYS-04, DISP-04, PEN-02, PEN-03, PEN-04, PAD-01, SWITCH-01, WIFI-02, USB-02, AUDIO-03, FM-01, CAM-01, CAM-02, SENS-01, SENS-02, STOR-02, PWR-03, PM-02, THERM-01, GPU-04, GPU-05, VIDEO-01, VIDEO-02.

**Before running:** One immutable final stack and each named usage profile; all applicable features enabled with normal policy.

**Android work still required:** Run a fixed owner Android daily-use script to establish responsiveness, charge/sleep behavior and accessory interactions.

**Linux procedure:**

1. Run a 24-hour mixed-use soak covering pen notes, keyboard/pad, browser/GL/Vulkan, local video, cameras, WiFi/BT, FM reception using its confirmed route, charging and sleep.
2. Exercise the specified dock/cover/pen attach events and resume while preserving the same final configuration.
3. Re-run integrity checks and every critical device smoke after the soak; resolve all regressions before closing the ledger.

**Required result:**

- `SYS-03.C01`: No crash, reset, filesystem corruption, stuck input/radio/audio/camera, persistent high-power state or manual rescue during the planned workload.
- `SYS-03.C02`: Every applicable individual gate remains passed on this same stack; no per-test configuration disables another required feature.
- `SYS-03.C03`: All open functional, isolation, thermal and recovery issues are closed; diagnostic/software fallbacks remain incomplete.

Minimum repetitions: 1. Duration: 24 h mixed-use soak. Comparison profiles: paired-latency, paired-energy.

## Evidence register

Hashes are stored in the JSON so revisions and derived claims can be checked.
The following links are repository-relative.

| ID | Class | Evidence | Limits |
| --- | --- | --- | --- |
| `ANDROID-STOCK` | `device_android` | [android-stock.json](evidence/android-stock.json) | Sequential observations; no input motions, charge cycle, controlled suspend, benchmark or Linux test. |
| `ANDROID-GPU` | `device_android` | [android-gpu.json](evidence/android-gpu.json) | No measured GL/Vulkan application, isolation, recovery or mainline rendering. |
| `ANDROID-PERIPHERALS` | `device_android` | [android-peripheral-inventory.json](evidence/android-peripheral-inventory.json) | No frames, audio streams, sensor events, tuner reception or Linux operation. Service names/rate declarations are not chip-ID reads or measured performance. Camera silicon, exact TFA/codec/acoustic variants, physical microphone inventory and full stream matrices remain unresolved; the unbound OCH8801-0 declaration is only a candidate. |
| `PERIPHERAL-REVIEW` | `source_clue` | [android-peripheral-inventory.md](android-peripheral-inventory.md) | A bounded interpretation of passive evidence, not a complete physical inventory, silicon verification, successful functional baseline or Linux hardware test. Interface counts do not equal physical device/channel counts. |
| `ANDROID-TRACE` | `device_android` | [android-trace-summary.json](evidence/android-trace-summary.json) | Uncontrolled workload; no energy/residency/FPS/suspend baseline. |
| `ANDROID-BOOT` | `device_android` | [android-boot-state.json](evidence/android-boot-state.json) | No bootloader entry, unlock, flash, data-clear or physical mainline boot was performed; contradictory fields do not establish a safe deployment method. |
| `ANDROID-BOOT-CAPABILITIES` | `device_android` | [android-boot-capabilities.json](evidence/android-boot-capabilities.json) | Passive configuration/interface evidence only; no module or kexec call, no working rescue transport, no card filesystem assessment and no Linux boot. |
| `ANDROID-BOOT-BACKUP` | `device_android` | [android-boot-backup-local.json](evidence/android-boot-backup-local.json) | Current bytes, not certified factory images; excludes userdata/super/persist, does not prove inactive B boots or any restore. The local copy alone resides on userdata. |
| `BOOT-BACKUP-OFFDEVICE` | `host_build` | [boot-backup-off-device.json](evidence/boot-backup-off-device.json) | A verified off-device backup closes a preparation item, not a working restore, AVB/rollback check or physical Linux boot. Private image bytes are not published. |
| `BOOT-HEADER-HOST` | `host_build` | [boot-header-inspection.json](evidence/boot-header-inspection.json) | Numeric layout and content identity only; no AVB signature, rollback compatibility, new-image bootability or restore has been verified. |
| `BOOT-READINESS` | `source_clue` | [boot-readiness.md](boot-readiness.md) | A reviewed entry/recovery analysis, not demonstrated stock-to-kexec handoff or a Linux hardware result. |
| `ENTRY-SOURCE` | `source_clue` | [entry-source-audit.md](entry-source-audit.md) | Read-only dependency audit. No complete first stage was built or booted. Absence is bounded to the inspected checkout and enumerated upstream refs/path queries, not all historical or private sources. |
| `ENTRY-METADATA` | `source_clue` | [entry-source-audit.json](evidence/entry-source-audit.json) | That public candidate is not the unknown V56.6 4.19.157 source/config. No compile, image packaging, module load, kexec, reboot, flash or restore occurred in this audit. |
| `DISPLAY-DECODE` | `source_clue` | [display-summary.json](evidence/display-summary.json) | Derived evidence, not runtime packet capture or native display test. |
| `HID-DECODE` | `source_clue` | [hid-summary.json](evidence/hid-summary.json) | Descriptor support is not successful event delivery or hotplug. |
| `DISPLAY-SOURCE` | `source_clue` | [display.md](display.md) | No owner Linux hardware pass can be inferred from this report. |
| `INPUT-SOURCE` | `source_clue` | [input-and-pen.md](input-and-pen.md) | No owner Linux hardware pass can be inferred from this report. |
| `POWER-SOURCE` | `source_clue` | [power-management.md](power-management.md) | No owner Linux hardware pass can be inferred from this report. |
| `GPU-SOURCE` | `source_clue` | [gpu-acceleration.md](gpu-acceleration.md) | No owner Linux hardware pass can be inferred from this report. |
| `DISTRO-SOURCE` | `source_clue` | [distro-builds.md](distro-builds.md) | No owner Linux hardware pass can be inferred from this report. |
| `STATIC-FIXES` | `source_clue` | [static-driver-fixes.md](static-driver-fixes.md) | No owner Linux hardware pass can be inferred from this report. |
| `FIRMWARE-POLICY` | `source_clue` | [firmware.md](firmware.md) | No owner Linux hardware pass can be inferred from this report. |
| `FIRMWARE-CONTRACT` | `source_clue` | [firmware-kernel-contract.md](firmware-kernel-contract.md) | Static availability/configuration only, not driver probe, blob transfer/content validation, secure authentication, DSP services or hardware operation. TFA989X is not configured and its OF table does not match TFA9894. |
| `FIRMWARE-CONTRACT-METADATA` | `source_clue` | [firmware-kernel-contract.json](evidence/firmware-kernel-contract.json) | No kernel source changes or device actions. Firmware ABI, runtime Bluetooth suffix, WLAN board selection and Novatek panel-ID GPIO value remain untested; canonical request names do not establish valid contents. |
| `STOCK-FIRMWARE-REPORT` | `source_clue` | [stock-firmware-bundle.md](stock-firmware-bundle.md) | Private payloads remain outside the repository. Structural completeness and byte provenance do not establish signatures, reserved-memory/ABI fit, remoteproc services or hardware operation; no canonical full firmware tree was generated. |
| `STOCK-FIRMWARE-RECEIPT` | `host_build` | [stock-firmware-bundle.json](evidence/stock-firmware-bundle.json) | The JSON also retains the Android source capture/re-read metadata, but this evidence ID covers the off-device verification only. No vendor authentication, load, hardware video or tablet Linux test occurred. WLAN board identity and Bluetooth runtime ROM matching remain false; available file counts do not close those contracts. |
| `HISTORICAL-MATRIX` | `source_clue` | [HARDWARE_MATRIX.md](../../HARDWARE_MATRIX.md) | Historical rows belong to other named author/build observations. Use the separate owner capture for current static identities; no row establishes this owner's Linux hardware operation. |
| `DTB-HOST` | `host_build` | [build-dtb.md](build-dtb.md) | Only base DTB; DSI1 remains disabled; no dtbs_check, variant build, boot or hardware test. |
| `GPU-STAGE-ELF` | `host_build` | [gpu-staging-elf.json](evidence/gpu-staging-elf.json) | Host artifact/provenance check only; no Qualcomm authentication or GPU initialization. |
| `GPU-STAGE-MDT` | `host_build` | [gpu-staging-mdt.json](evidence/gpu-staging-mdt.json) | Host artifact/provenance check only; no Qualcomm authentication or GPU initialization. |
| `NIX-HOST` | `host_build` | [nixos-build.json](evidence/nixos-build.json) | No complete NixOS rootfs/system assembly or tablet boot; QEMU is not physical GPU evidence. |
| `KERNEL-HOST` | `host_build` | [kernel-build.md](kernel-build.md) | Host compilation and generic virt boot only; no owner tablet boot, native display/touch test, complete tablet initramfs or bit-for-bit rebuild claim. |
| `KERNEL-ARTIFACTS` | `host_build` | [kernel-build.json](evidence/kernel-build.json) | Offline artifact inspection; release strings alone do not prove complete ABI compatibility, device loading or physical operation. |
| `QEMU-INITIAL` | `host_build` | [kernel-qemu-initial.json](evidence/kernel-qemu-initial.json) | A failed generic VM test, not evidence that the owner tablet reproduced the historical kexec problem; panic details are in the retained log/report. |
| `QEMU-FIXED` | `host_build` | [kernel-qemu-fixed.json](evidence/kernel-qemu-fixed.json) | Generic virt uses no tablet DT, physical GPU, board firmware or tablet rootfs; no Lenovo allocator-branch or hardware acceptance. |
| `R2-BUILD` | `host_build` | [research2-display-build.md](research2-display-build.md) | Display diagnostic candidate only: SPI14 and touchscreen remain disabled. No owner boot, display, GPU, input or handoff result; no arbitrary ABI or bit-for-bit reproduction claim. |
| `R2-ARTIFACTS` | `host_build` | [research2-display-build.json](evidence/research2-display-build.json) | Device-tree availability and compatible strings are static artifact facts, not bound/operating drivers. The native diagnostic DT was not used in QEMU and touch remains disabled. |
| `R2-QEMU` | `host_build` | [research2-display-qemu.json](evidence/research2-display-qemu.json) | Generic machine DT and probe init only: no physical tablet DT, firmware, network/disk passthrough, native display or board early-allocator/handoff validation. |
| `R2-QEMU-SERIAL` | `host_build` | [research2-display-qemu.log](evidence/research2-display-qemu.log) | A short generic ARM boot log; no physical hardware operation, long-duration stability or recovery result. |
| `R2-MODULES` | `host_build` | [research2-display-modules.SHA256SUMS](evidence/research2-display-modules.SHA256SUMS) | File-byte inventory only; no module load or permission to mix this set with another kernel/rootfs build. |
| `R2-PACKAGES` | `host_build` | [research2-display-builder-packages.tsv](evidence/research2-display-builder-packages.tsv) | Host tool inventory, not an immutable APT snapshot or tablet userspace/hardware result. |
| `FEDORA-HOST` | `host_build` | [fedora-build.md](fedora-build.md) | QEMU userspace software graphics only; Turnip found no physical GPU. No tablet boot, complete tablet initramfs, native DSI, hardware rendering or isolation result. |
| `FEDORA-ARTIFACTS` | `host_build` | [fedora-build.json](evidence/fedora-build.json) | Physical GPU/display/board hardware were not exposed. Turnip-only enumeration exited 1 without a GPU; software results cannot pass any owner hardware case. |
| `NURA-HOST` | `host_build` | [nura-build.md](nura-build.md) | The exported qemu-aarch64 rootfs itself has not booted and is not a TB371FC image. Only 371 of 382 package archives are retained, so the offline cache is incomplete and independent offline/byte-identical reproduction is unproved. No owner Linux hardware result. |
| `NURA-ARTIFACTS` | `host_build` | [nura-build.json](evidence/nura-build.json) | offline_cache_complete, independent_offline_rebuild_tested, target_rootfs_booted and tablet/GPU hardware-test flags remain false. Its generic 7.3.5 target kernel/modules are separate from the Alpine builder kernel and both 6.12 research candidates. |
| `SSD-BUILDER` | `host_build` | [ssd-builder.json](evidence/ssd-builder.json) | Infrastructure preparation only; no kernel was built by this bootstrap. Tool binaries remain on the normal HDD-backed Docker layer, APT is not snapshot-pinned and no speedup or tablet function was measured. |
