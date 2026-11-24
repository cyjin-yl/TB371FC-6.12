# Display and input integration: real driver fixes and a compiled joint profile

Date: 2026-11-23. Evidence: [input-integration.json](evidence/input-integration.json).

Follow-up: [patch 0020](novatek-firmware-bounds.md) now addresses specific
firmware-parser range checks left open by this report. It has a separate R5
module build, 16 owner-matched stock-file comparisons and 18 range/decode
checks. The historical research2 results and physical acceptance below remain
unchanged.

**The two new input patches, Novatek module, three HID objects and joint display/input DT have been built successfully against the frozen research2 ABI.** Eighteen groups of fault-injection checks execute functions extracted from the actual patched C source. This is a source and host-build result. No module was loaded, no tablet was booted or written, and no physical input test passed in this task.

The final independent build is `/work/input-integration-v3` in the standard Docker container `tb371fc-build-ssd-20261123` on doesvm/CT102. Frozen research1/research2 source, Image and installed modules were not modified. The module in this report is **unsigned**; signing and any integrated kernel/module/DT bundle must have a separate manifest.

## Changes that are supported by the code

Apply these patches, in order, after the complete frozen research2 source recipe:

1. [`0018-input-nt36523-use-declared-physical-dimensions.patch`](../../../mainline-port/backports/linux-6.12/0018-input-nt36523-use-declared-physical-dimensions.patch).
2. [`0019-input-nt36523-fail-closed-and-release-resources.patch`](../../../mainline-port/backports/linux-6.12/0019-input-nt36523-fail-closed-and-release-resources.patch).

The baseline already includes historical input patch 0002 and the earlier 0013 negative GPIO-to-IRQ error fix. These new files do not rewrite those historical patches.

### Physical units

The previous driver divided pen coordinates by donor dimensions **148 × 237 mm**. Those constants are not a measurement of this tablet's active digitizer. Patch 0018 uses the paired standard `touchscreen-x-mm` / `touchscreen-y-mm` properties, rejects incomplete, unreadable or zero dimensions, and derives integer counts per millimetre from each axis's coordinate span. The same rule applies to touch and pen axes. The exact baseline [Linux 6.12.114 common touchscreen binding](https://github.com/gregkh/linux/blob/v6.12.114/Documentation/devicetree/bindings/input/touchscreen/touchscreen.yaml) defines the two physical-dimension properties and their mutual dependency.

The joint board profile does **not** invent those dimensions. Resolution remains zero/unknown when they are absent, matching the kind of metadata reported by this owner's Android input snapshot. The panel's 274 × 171 mm mechanical metadata is not substituted for a measured digitizer area or orientation. Pen coordinate range, pressure, tilt, hover and buttons are unchanged by this patch. Android enumerated maximum coordinates 18400 × 29440, pressure 0–4095, tilt ±60, distance 0–1 and two stylus buttons; those are capabilities, not measurements of actual strokes. See [input-and-pen.md](input-and-pen.md) and the hashed owner references in the new JSON.

### Probe, power management and IRQ handling

Patch 0019 fixes the following specific software failures:

| Previous behavior | Changed behavior |
|---|---|
| A requested IRQ could run before completion/work/firmware initialization. | `IRQF_NO_AUTOEN` leaves it disabled until successful initialization. |
| IRQ zero bypassed registration but could reach later IRQ operations; negative errors were already fixed by 0013. | Both zero and negative mappings fail, preserving negative errno. |
| MT slot allocation errors were ignored. | Probe unwinds the unregistered input device on failure. |
| Probe continued after a failed firmware load. | Firmware, reset-state and pen-command failures unwind the probe. |
| Resume returned zero after failed firmware load, reset handshake or pen setup. | It returns the actual failure, leaves the controller logically unavailable and the IRQ disabled, and permits a later explicit retry. |
| `enable_irq_wake()` errors were discarded and successful wake references had no matching disarm. | A separate ownership flag changes only after successful enable/disable, with matching resume/removal handling. |
| Deep-sleep transfer failure was discarded. | Suspend reports the error and restores its prior active software state; it does not claim that a failed transfer proved a hardware power state. |

The existing deep-sleep command is unchanged. Its event-buffer page is explicitly selected instead of relying on a preceding pen command to leave the correct page selected. No gesture-entry command, electrical polarity, reset delay or display command was invented.

All callers were reviewed. `nvt_pm_suspend()` changes `dev_pm_suspend` and reinitializes its completion only after successful controller suspend. `nvt_pm_resume()` clears that **transport wait flag** and completes the IRQ thread's wait before synchronously disabling the IRQ and running controller resume; it returns the resume errno. Delaying the completion until firmware success would obstruct an IRQ thread that holds the controller mutex. `bTouchIsAwake` and IRQ enablement represent controller readiness separately. The two legacy void work callbacks now log their failure results.

This distinguishes a completed SPI transport PM phase from a working touchscreen. It does not establish the physical display-reset/DSI-before-touch order.

### Resource ownership

Each firmware-update exit now releases the firmware object, partition map and transfer buffer. Invalid retries use the same release path. Probe balances its wake hold on success and late failure. Removal frees the SPI receive/transmit buffers as well as the controller structure.

Removal and shutdown drain the event workqueue before disabling the IRQ and cancelling/destroying the self-requeueing ESD work. In the compiled two-file Novatek port, the event queue has only `INIT_WORK` setup: there is no `queue_work` producer, registered external notifier or exported symbol path that schedules its suspend/resume work. The ordering is nevertheless explicit so drained event work cannot re-enable the IRQ or requeue ESD work after those resources have been removed. The fault-injection test is not a concurrent kernel workqueue stress test.

## The exact joint DT profile

The new source is [`sm8250-lenovo-tb371fc-display-input-test-6.12.dts`](../../../mainline-port/backports/linux-6.12/sm8250-lenovo-tb371fc-display-input-test-6.12.dts). It includes the qualified research2 6.12 display wrapper, which already requires its recorded native DPU/PHY source prerequisites. It then enables the inherited SPI14 touchscreen description and makes the existing I2C13 keyboard's status explicit.

The inspector parses both compiled DTBs and compares every node and every property's raw bytes. The complete difference is exactly:

| Compiled node | Property change |
|---|---|
| `/` | Model text identifies the display and input integration. |
| `/soc@0/geniqup@8c0000/spi@880000` | `status`: disabled → okay. |
| The above node's `touchscreen@0` | `status`: disabled → okay. |
| `/soc@0/geniqup@ac0000/i2c@a94000/keyboard-cover@60` | Explicit `status = "okay"`; absent status was already available. |

All remaining node names and property bytes match the frozen display DT. This includes the native display graph, panel/backlight wiring, disabled unrelated devices, TLMM reserved ranges, SPI pinmux and firmware names. It is a precise composition of existing board descriptions, not proof that pin requests or hardware probe will succeed.

The touch node retains reset GPIO56 active-low, IRQ GPIO68 active-high, panel-ID GPIO82, super-resolution 10 and both owner-project BOE/Tianma firmware paths. The keyboard retains address `0x60`, descriptor register 1, GPIO110 level-low interrupt, reset GPIO114 active-low and wake GPIO108 active-high. Numbers in the JSON's GPIO arrays also include the **new DT's own** phandle; an Android phandle is never copied into it.

## Keyboard source audit

No new vendor-specific `17ef:6175` HID protocol was introduced. The actual owner descriptor is 604 bytes and enumerates keyboard, touchpad and consumer-control functions under Android's `i2c_hid` + `hid-multitouch` binding. The prepared 6.12 source retains the generic HID/multitouch path and historical optional wake-GPIO patch 0017. The I2C-HID OF, I2C-HID core and hid-multitouch objects were actually compiled as AArch64 objects.

An additional pinned public source clue is [`tem423/android_kernel_lenovo_tb371fc` at `9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1`](https://github.com/tem423/android_kernel_lenovo_tb371fc/blob/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1/drivers/hid/i2c-hid/i2c-hid-core.c). Its `i2c_hid_init_irq()` selects `IRQF_TRIGGER_LOW` when the supplied IRQ has no trigger type. This explains a possible interpretation of the owner's raw `<110 0>` tuple; the tuple alone still does not prove a trigger, and this public source is not a verified match to the shipping binary. That file's SHA-256 is recorded in the JSON.

The public file drives `mcu_resume_gpio` high/low in runtime callbacks, but the reviewed file initializes the global to zero; the inspected HID, keyboard and miscellaneous source directories did not supply an assignment from the owner's GPIO108 property. This bounded search is not a claim that no other public file or revision can implement it. The owner's 100 ms post-power delay and the port's 120 ms post-reset delay apply at different points and are not treated as interchangeable. Existing `17ef:6127` report-ID-6 cover logic is not applied to this `17ef:6175` device.

## Actual build and regression results

The final preparation reproduced the frozen research2 source manifest exactly before applying the two new patches. It exited zero in **39.437 s**. Build, regression and artifact inspection exited zero in **44.483 s**, using one build job with Debian Clang/LLD **19.1.7**. All versions and the preceding failed attempts are retained in [the evidence JSON](evidence/input-integration.json).

| Artifact | Size | SHA-256 |
|---|---:|---|
| `nt36523_ts.ko` | 90,984 B | `cecbd4709f2e6cbb488586ca24f06de6ffe4f7a27fd15bba5ab4649aa29d3972` |
| Joint `board.dtb` | 126,877 B | `af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730` |
| Final source manifest | 7,108 B | `5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0` |

The generated `.config` is byte-identical to the frozen research2 config (`e024e6d2…`). The complete baseline `Module.symvers` is unchanged (`8e71a956…`). The new module's **63 imported symbol CRCs** match that symbol table, and its vermagic is `6.12.114-tb371fc-research2-display SMP preempt mod_unload modversions aarch64`. These are offline compatibility checks; no insertion, signature acceptance or device binding occurred.

The regression extracts eight actual C function bodies into a host C harness. Its 18 reported groups cover absent/incomplete/zero/error/declared geometry, wake ownership and error paths, firmware/reset/pen failures during resume, successful resume and retry, failed sleep/wake suspend, successful sleep/wake transitions, and firmware resource release on success plus four failure exits. These are injected kernel-API outcomes, not simulated pen traces or software rendering substitutes for hardware tests.

Two failed attempts remain visible. The first stopped at strict configuration comparison because newly installed target libc made `CC_CAN_LINK` and `CC_CAN_LINK_STATIC` become true. The recipe now passes an explicit **empty target sysroot** to the target Clang, preserving the original freestanding build boundary while host tools use the host libc. The exact baseline config then matched; no package was removed or falsified. The second stopped because relative `M=` was resolved below the separate `O=` output tree. The final recipe uses the standard absolute external-module source path in its own new source tree. Neither failure is reported as a build pass.

## Reproduce without touching the frozen trees

The new tools are under [`scripts/research/input/`](../../../scripts/research/input/). They accept a new work directory and retain existing work instead of overwriting it. In the prepared SSD builder, use a fresh name:

```sh
python3 /path/to/repo/scripts/research/input/prepare_input.py \
  --repo /path/to/repo \
  --baseline-repo /work/research2-repo \
  --baseline-work /work/research2-display \
  --work /work/input-integration-next \
  --cache /work/downloads/linux-6.12.114.tar.xz

TB371FC_INPUT_WORK=/work/input-integration-next \
  bash /work/input-integration-next/input-recipe/scripts/research/input/build_input.sh
```

The archive is the official Linux 6.12.114 tarball with SHA-256 `7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3`. The baseline recipe checks its pinned source and helper inputs; the new recipe retains that manifest before applying its own patches. The output contains the replacement module, joint DT, HID objects, exact config/symbol table and source-derived regression record. It does not contain a rebuilt Image or a complete new installed module tree. Build-directory paths enter manifests, so a different fresh path intentionally changes their bytes; source/config/artifact identities remain individually recorded.

## Remaining boundaries for real integration

The module and DT can now be composed with their explicitly matching kernel baseline, subject to that kernel's signing/trust policy and a separately recorded complete bundle. This report is not an installation instruction.

The physical gates remain open: cold-start pin ownership and firmware selection, HID reset/attachment/system wake, actual touch contacts and pen pressure/tilt/hover/buttons, palm rejection, suspend/resume and power consumption. The port still lacks a display panel-follower implementation that establishes the required display-before-touch restart order. Existing 30/60/120-versus-144 Hz pen/display command differences remain a joint hardware acceptance item. CTN730 magnetic pen charging and its notifier integration are not implemented here. Bluetooth pen enumeration cannot substitute for digitizer or charging tests.

The bounded changes also do not certify the inherited firmware metadata parser or WDT/ESD recovery transaction policy. In particular, those recovery callers and malformed-file bounds need separate review before claiming complete recovery robustness. All physical Linux cases stay pending; the host fault-injection count must not enter the device-pass count.
