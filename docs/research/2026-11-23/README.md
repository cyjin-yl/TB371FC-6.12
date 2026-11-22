# Independent TB371FC evidence and research builds, 2026-11-23

This contribution adds a second owner's hardware evidence and offline analysis
to the project at base commit `d157b92721fbeeab823f56a677b3593babf3afe6`.
The reference system is Lenovo TB371FC, Android 14, kernel
`4.19.157-perf+`. Capture timestamps are UTC; this directory uses the owner's
Asia/Shanghai date. See the [Chinese overview](README.zh-CN.md).

**These results answer several board-specific questions without claiming a new
mainline boot, a power saving, working suspend, or a completed driver port.**
The R226 installation/reproducibility limitations in
[INSTALL_CURRENT.md](../../INSTALL_CURRENT.md) still apply.

## Build follow-up and completion standard

The new `6.12.114-tb371fc-research1` Image, matching modules and native board
DTB have now compiled in an isolated CT102 container. A generic ARM64 VM boot
first exposed an inherited early page-table pool panic; after a board-scoped
fix, the same final Image reached ARM64 userspace. This is a host/VM result,
not a new physical-tablet pass. The base DT still disables native display
and touch, so it is not a completed all-device profile.

The independent `6.12.114-tb371fc-research2-display` candidate has also completed
its full build, matching 83-module inventory and generic ARM64 VM boot. Its
versioned DT enables the native display path with corrected driver matching
and framebuffer ownership, while touch remains disabled. Physical display,
rendering, input and whole-device acceptance remain open.

- [Actual kernel build, failure/fix and VM retest](kernel-build.md).
- [Native 6.12 DT/driver qualification and framebuffer fix](diagnostic-dt-profiles.md),
  [independent display candidate](research2-display-build.md) and [SSD builder](ssd-builder.md).
- [GPU acceleration audit and runtime evidence requirements](gpu-acceleration.md).
- [Actual private GPU firmware staging, public manifests and tests](firmware.md).
- [Distro build comparison](distro-builds.md), [Fedora experiment](fedora-build.md)
  and [Nura experiment](nura-build.md); [NixOS configuration](../../../distros/nixos/README.md).
- [Whole-device acceptance runbook](acceptance.md) and [machine-readable ledger](acceptance.json).
- [Actual entry prerequisites and verified off-device backups](boot-readiness.md),
  plus [matched R241 diagnostic module compilation](r241-build.md).
- [First-stage source, toolchain and private-intermediate dependency audit](entry-source-audit.md).
- [Frozen kernel firmware requests, effective device states and loader rules](firmware-kernel-contract.md).
- [Verified private transfer and structure of 118 selected stock firmware files](stock-firmware-bundle.md).
- [Owner-specific camera, audio and sensor inventory](android-peripheral-inventory.md).

The owner's definition of completion requires every fitted device to operate
at its best demonstrated state, with measured stock comparisons where
appropriate. Enumeration, a successful build, software rendering, disabled
hardware or an unmeasured power claim do not satisfy that requirement.
The measured completion target is Android parity or better for matched
throughput, latency and energy, with intact features, thermal policy, isolation
and recovery. Measurement uncertainty is frozen before Linux comparisons;
inconclusive evidence cannot be converted into a pass by relaxing the target.

## Findings

| Question | Evidence obtained | Consequence |
| --- | --- | --- |
| Which panel is fitted/selected? | The current Android selector chooses the Tianma NT36532 path; its DT and four advertised DRM modes are attached | Compare this exact path before changing native display initialization |
| How does Android group DSC slices? | The selected live DT specifies `slice-per-pkt = 1` | Review the later 6.12 export's two-slice packet change; it is not yet proven to cause the historical half-screen corruption |
| Are the Tianma ON payloads still missing? | All 86 vendor payloads match the checked-in 6.12 source; the captured table contains 88 records including Sleep Out and Display On | Further work should prioritize transport, topology, transitions and power sequencing, rather than guessing a new vendor table |
| Does shutdown match Android? | Android declares HS OFF commands with 15 ms and 60 ms waits; the current native path differs | Reconcile command state and waits before relying on blank/unblank or suspend |
| Does the panel have pen-related mode commands? | The saved 144 Hz pen table differs at `B3` from the 30/60/120 Hz tables | Treat display-mode and pen acceptance as a joint test; register semantics remain unproven |
| Is the keyboard protocol unknown? | A 604-byte I2C-HID descriptor identifies touchpad, keyboard and consumer collections | Reuse HID infrastructure; validate board wake/reset, IRQ and attach lifecycle |
| Can another Lenovo cover's status parser be reused? | This cover is `17ef:6175` and has no Input report ID 6; the inspected donor side channel targets `17ef:6127` | Do not copy that parser based only on the manufacturer |
| Is a pen-charging implementation available to study? | CTN730 is bound on the actual device and GPL downstream source exists | Study its lifecycle and mainline binding separately from Novatek inking and Bluetooth controls |
| Is this Android capture using USB PD? | Runtime fields say HVDCP 3 and `pd_active = 0`, despite two generic PD labels | Class labels are insufficient to validate a PD contract |
| What does a short power trace establish? | An isolated low-volume trace retained 196 CPU-frequency, 12 GPU-frequency and 18 GPU-state events with no reported buffer loss | It provides a bounded Android baseline, not residence time, battery efficiency, FPS or a sleep test |
| Can the historical motion-sensor identity be reused? | This owner's SensorService reports TDK-Invensense `icm4x6xx` acceleration/gyroscope entries, differing from the historical Bosch BMI3x0 row | Confirm driver and orientation choices from this owner's evidence; declared rates are not measured performance |
| Are camera and amplifier variants now established? | Two cameras enumerate and four `tfa98xx` I2C clients have drivers bound | Camera silicon names, exact amplifier silicon/container variants and actual capture/playback remain unconfirmed |

Detailed evidence, source references and untested questions:

- [Display and native-DRM mapping](display.md)
- [Keyboard, touch and pen](input-and-pen.md)
- [Power, charging and suspend](power-management.md)
- [Applied static driver fixes](static-driver-fixes.md)

The documents also record static source-review findings, including the pen
physical-size inconsistency, negative IRQ error handling, and dual-backlight
probe cleanup. The latter two have follow-up fixes and successful compilation;
they have not been exercised on this owner's physical tablet under mainline
and are not presented as observed device failures.

## Evidence files

| File | Contents and limits |
| --- | --- |
| [android-stock.json](evidence/android-stock.json) | Reviewed running hardware DT properties with bytes/hash/BE32 interpretations, hardware bindings, descriptor, capability listings, sysfs state and trace capabilities; values were read sequentially |
| [display-summary.json](evidence/display-summary.json) | Offline command/timing comparison derived from that capture |
| [hid-summary.json](evidence/hid-summary.json) | Offline descriptor structure, report lengths, ranges and source hash |
| [power-summary.json](evidence/power-summary.json) | Selected stock values, both trace references, hashes and interpretation limits |
| [android-trace-summary.json](evidence/android-trace-summary.json) | 8.012-second low-volume trace summary; no reported per-CPU loss, zero unparsed lines |
| [android-trace-idle-partial.json](evidence/android-trace-idle-partial.json) | Earlier idle-inclusive trace; buffer overruns explicitly recorded, counts are lower bounds |
| [android-gpu.json](evidence/android-gpu.json) | Stock GPU identity, driver bindings, firmware hashes and ELF layout; no firmware bytes |
| [android-boot-state.json](evidence/android-boot-state.json) | Conflicting Android property and kernel command-line lock states; no raw command line or identifiers |
| [android-boot-capabilities.json](evidence/android-boot-capabilities.json) | Actual `CONFIG_KEXEC=n`, forced module signatures, USB gadget prerequisites and MMC node names; no attempted entry |
| [Local boot-copy manifest](evidence/android-boot-backup-local.json) / [off-device receipt](evidence/boot-backup-off-device.json) | Eight current partitions copied and independently re-hashed on doesvm; no partition bytes published and no restore claimed |
| [boot-header-inspection.json](evidence/boot-header-inspection.json) | Numeric v2 layout, exact kernel/ramdisk/DT component hashes and observed slot differences |
| [GPU ELF staging](evidence/gpu-staging-elf.json) / [MDT staging](evidence/gpu-staging-mdt.json) | Actual package manifests, verified against this owner's captured firmware hashes |
| [kernel-build.json](evidence/kernel-build.json) | Actual source, Image/DT/config/module artifacts and build results |
| [research2-display-build.json](evidence/research2-display-build.json) | Independently built display candidate, exact native DT, configuration and 83-module checks |
| [research2-display-qemu.json](evidence/research2-display-qemu.json) | Successful generic virt boot of that candidate; no native display DT was passed to the VM |
| [entry-source-audit.json](evidence/entry-source-audit.json) | Actual source/file/API evidence for the unresolved first-stage build chain |
| [firmware-kernel-contract.json](evidence/firmware-kernel-contract.json) | Exact research2 source/config/DT request rules; disabled consumers and unselected board/ROM variants remain explicit |
| [stock-firmware-bundle.json](evidence/stock-firmware-bundle.json) | 118 privately archived vendor files, source/receiver hashes and six ELF/MDT file-set checks; no firmware bytes or load/authentication claim |
| [android-peripheral-inventory.json](evidence/android-peripheral-inventory.json) | Filtered owner Android camera/sensor/audio identities and declarations; no capture, playback or native Linux test |
| [Initial VM failure](evidence/kernel-qemu-initial.json) / [fixed VM result](evidence/kernel-qemu-fixed.json) | Retained generic ARM64 early-boot failure and successful EL0 retest |
| [nixos-build.json](evidence/nixos-build.json) | Actual evaluation, ARM64 cache/closure execution and explicit missing-artifact gate |
| [SHA256SUMS](evidence/SHA256SUMS) | Integrity of the published evidence files, not a boot-image manifest |

The collector excludes serial numbers, MAC addresses, credentials, network
profiles, raw input streams, unrelated process names and firmware binaries.
Two Novatek manufacturing-test threshold matrices were additionally removed
from the publication copy; the JSON records that transformation. The private
transport capture is not a public distribution of Android partitions or firmware.
The snapshot's collector hash identifies the acquisition revision before that
additional omission was implemented in the reusable collector. The reusable
collector was subsequently tightened to an explicit DT property allowlist;
unknown properties retain names only, with no values or hashes. Failed, empty
or oversized command output is recorded as unavailable rather than accepted
or silently truncated. These changes do not rewrite the saved acquisition.

The initial acquisition attempted `/sys/power/wakeup_count`, whose read blocked
in `pm_get_wakeup_count`; no successful capture is attributed to that attempt.
The final collector omits this suspend synchronization interface and bounds
individual reads. An initial trace exceeded a 2 MiB text cap and was discarded;
its private instance was removed. The saved idle-inclusive trace used a larger
read bound but had overruns, so a separate low-volume capture was collected.
The failed and partial attempts are not silently promoted to complete samples.

## Reproduce the observations

The Python helpers require only the standard library. Use the tablet's existing
root access and Python; no installation, SELinux change or driver rebinding is
performed by the helpers. Keep captures private until reviewing their contents.

```sh
# In an already authorized Android root shell, with Python available:
python3 collect_android_hardware.py > android-stock.json

# Uses a new tracefs instance, never the global trace buffer.
# Defaults to an 8-second low-volume profile, then removes its own instance.
python3 capture_android_trace.py --seconds 8 > android-trace-summary.json

# Optional, high-volume idle events; check per-CPU loss counters before use.
python3 capture_android_trace.py --seconds 8 --cpu-idle > android-trace-idle.json
```

The scripts are [collect_android_hardware.py](../../../scripts/research/collect_android_hardware.py)
and [capture_android_trace.py](../../../scripts/research/capture_android_trace.py).
Root access does not make every read-only-looking sysfs file passive: the
downstream CTN730 `cn_test` getter initiates a test. This is why the collector
does not recursively read arbitrary device attributes, debugfs or register
interfaces. It never records keystrokes or pen motions.

Both saved trace runs report that the global tracer settings were unchanged
and their private instance was removed. A normal exception or handled signal
also runs cleanup. Power loss or SIGKILL cannot run Python cleanup; after an
interrupted process, inspect only the instance created by that invocation.

The reusable trace helper now samples power attributes only before and after
the active trace interval, so slow sysfs reads do not extend that interval.
It preserves cleanup evidence in JSON even after capture failure and exits
nonzero when capture or verification fails. The saved acquisitions predate
this revision and contain four sequential power samples; their actual elapsed
intervals and original evidence have been retained. Scheduling delays remain
possible, so use `observed_seconds` rather than assuming the requested duration.

Offline analysis on a development host:

```sh
python3 scripts/research/display_decode.py commands \
  --capture docs/research/2026-11-23/evidence/android-stock.json \
  --node /soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_panel_spinel_tianma_nt36532_dsc_3k_video/qcom,mdss-dsi-display-timings/timing@0 \
  --property qcom,mdss-dsi-on-command

# The HID tool accepts a saved binary/hex/base64 descriptor, never /dev/input.
python3 scripts/research/hid_report.py --help

python3 scripts/research/test_research_tools.py
```

No captured mode name or enabled tracepoint demonstrates an active refresh
rate. No capability listing demonstrates actual pen pressure or palm rejection.
The short traces did not exercise a controlled screen-off or suspend cycle.

## Next changes and their acceptance

1. Use the newly identified 6.12 kernel/DT/module baseline for the next controlled
   checks, after assembling an actual entry/initramfs/firmware contract and a
   verified recovery path. Historical transforms are not a stackable patch queue.
2. Reconcile one-slice packetization, dual-DSI/DSC/CTL allocation and source
   fetch splitting. Require a real frame on both halves before mode transitions.
3. Review the now-confirmed OFF/pen-mode differences and explicit resource
   ownership, then test blank/unblank and display/pen transitions together.
4. Verify keyboard cold attach, detach/reattach and IRQ behavior on that kernel;
   verify pen motion, pressure, tilt and hover with an attended test.
5. Port charging with a single owner for Type-C/charger policy, preserve thermal
   and watchdog behavior, and validate the actual negotiated protocol.
6. Establish repeated suspend/resume with before/after counters, wake reason,
   input restoration and a measured battery-energy delta under fixed conditions.

These are follow-up hardware/driver tasks, not completed results of this data
collection. No image was flashed and no new mainline kernel was booted on this
owner's physical tablet in this round; the generic VM result is recorded above.
