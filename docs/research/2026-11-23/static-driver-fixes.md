# Static driver fixes for the Linux 6.12 build

Two independent follow-up patches correct error handling in the existing
Novatek input driver and the dual KTZ8866 backlight driver. They require no
new assumption about this tablet's wiring, firmware, register values or
display geometry. The physical-size inconsistency remains an explicit open
item. These changes do not constitute a boot, touch, pen or backlight test
on the owner's tablet.

| Patch | Correction | Source required first |
|---|---|---|
| [0013: Novatek IRQ errors](../../../mainline-port/backports/linux-6.12/0013-input-nt36523-preserve-gpio-irq-errors.patch) | Preserve a negative `gpiod_to_irq()` result, including `-EPROBE_DEFER`, and unwind the registered input devices without requesting or freeing that invalid IRQ | Historical input patch `0002` |
| [0014: backlight probe cleanup](../../../mainline-port/backports/linux-6.12/0014-backlight-tb371fc-unwind-failed-probe.patch) | Remove the failed controller from the global list, clear its client data, and clear the shared backlight pointer only if this client owns it | Copy the unmodified 6.12 backport `tb371fc-ktz8866.c` into the kernel source |

Neither historical patch nor the original tracked C source was rewritten.
Consumers must explicitly apply the new patches after installing the source.

## Reproducible source boundary

The new build uses the official **Linux 6.12.114** release archive:

- URL: <https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.114.tar.xz>
- SHA-256: `7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3`
- Build environment selected by the parent task: Debian trixie, LLVM 19 or
  its GCC 14 AArch64 toolchain. This is a new build; it does not establish
  compatibility with old project modules built by LLVM 18.

The complete driver inputs are present in this repository:

- [Historical patch 0002](../../../mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch)
  supplies the top-level touchscreen Kconfig/Makefile additions and the
  `nt36523` subdirectory's Kconfig, Makefile, `nt36xxx.c`, `nt36xxx.h`,
  `nt36xxx_fw_update.c` and `nt36xxx_mem_map.h`.
- [Historical patch 0006](../../../mainline-port/patches/0006-backlight-add-tb371fc-dual-ktz8866.patch)
  supplies the backlight Kconfig/Makefile additions.
- [The 6.12 backlight source](../../../mainline-port/backports/linux-6.12/tb371fc-ktz8866.c)
  is a complete driver, not an excerpt. Its default brightness is 128;
  the separate `mainline-port/drivers` variant uses 1200, and the historical
  R170 variant has additional bootloader-level/sink handling. The fix does
  not select a new brightness or sink policy.

The unmodified `0002` and `0006` patches both pass
`git apply --recount --check` against their affected upstream Kconfig and
Makefile files from the exact stable `v6.12.114` tag. The six new Novatek
files also apply. `--recount` is necessary for the historical patches:
`0006` otherwise reports a corrupt hunk count. The new `0013` and `0014`
patches have correct hunk counts and need no recount option.

The following upstream files were downloaded and inspected for this audit:

- [Touchscreen Kconfig](https://github.com/gregkh/linux/blob/v6.12.114/drivers/input/touchscreen/Kconfig)
  and [Makefile](https://github.com/gregkh/linux/blob/v6.12.114/drivers/input/touchscreen/Makefile).
- [Backlight Kconfig](https://github.com/gregkh/linux/blob/v6.12.114/drivers/video/backlight/Kconfig)
  and [Makefile](https://github.com/gregkh/linux/blob/v6.12.114/drivers/video/backlight/Makefile).
- [`struct spi_device`](https://github.com/gregkh/linux/blob/v6.12.114/include/linux/spi/spi.h),
  whose `irq` member is signed `int`.
- [`gpiod_to_irq()`](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpio/gpiolib.c),
  which returns negative errors, explicitly supports `-EPROBE_DEFER`, and
  converts a GPIO chip's zero/`NO_IRQ` result to `-ENXIO`.
- [Backlight registration and devres release](https://github.com/gregkh/linux/blob/v6.12.114/drivers/video/backlight/backlight.c),
  which confirm that the managed registration owns unregistration.

These source and patch checks establish applicability and the API contract.
The subsequent [full research kernel build](kernel-build.md) passed that
separate compilation gate. These checks still do not establish
that the firmware loader or the input report parser works on this hardware.

### Input hashes

| File | SHA-256 |
|---|---|
| Historical `0002` patch | `7ce384059a725714cfc82ebf77bcac17f4d327c060947a202abd142a7dbede14` |
| Historical `0006` patch | `cf1c2d9f4ab9790efc5817d885c4fa325f766a03747f9e8fea1535bc2b46302b` |
| New `0013` patch | `7915efcbed2eb6e230524529b33a90588380788769ed8d15f9422c7cc35a11a6` |
| New `0014` patch | `2e3e6fabe529d0d971639f3551a27cdafdd10735db726be3b9f8eb30ea46aa6a` |
| `nt36xxx.c` immediately after `0002`, before `0013` | `cc1d093890be4583f70fc043d9a8e1bb0e0cc0b9b236d4f428e80c72a3d5171f` |
| `nt36xxx.c` after `0013` | `bcc8e60eb6c10d97b84680224d1118462e5d121daa62d6b8732ec8938a09e0a2` |
| Backport `tb371fc-ktz8866.c` before `0014` | `411274490ba052ce942a08db0fa900d2fc342c69be7364423b934fd7d162f127` |
| Backport `tb371fc-ktz8866.c` after `0014` | `5e52309b0c1d6b836273efd1161bf862683dbf6b8b58b3095d04a360f9faab59` |

## Why these changes are necessary

### Novatek: preserve an IRQ mapping failure

The original probe assigns `gpiod_to_irq(ts->irq_gpio)` to `client->irq`
and tests only `if (client->irq)`. Negative errors pass that test. The
following `request_threaded_irq()` takes an unsigned IRQ number, so a
mapping failure can become a request for an invalid IRQ and return a
different error. In particular, the driver can lose a genuine
`-EPROBE_DEFER` result.

Patch `0013` adds an explicit negative check immediately after the mapping
call. `dev_err_probe()` records the mapping error and returns the same
errno. The existing `err_int_request_failed` label unregisters the pen
input device, if present, then the touch device, and releases the driver's
other allocated state. This label is after `free_irq()` in the unwind
chain, so the failed mapping cannot free an IRQ that was never requested.

The successful lookup/request path and its trigger flags remain intact.
The fix does not resolve the separate hardware questions about reset
polarity, interrupt trigger, firmware choice or suspend/resume. See the
[input and pen evidence report](input-and-pen.md) for those boundaries.

### Backlight: unwind every failure after insertion

The driver inserts its devm-allocated controller in a global list before
registering the shared backlight and before writing the initial brightness.
The original registration-failure branch unlinks it, but an I2C/regmap
write failure returns from probe without unlinking. Failed probe releases
managed resources without calling this driver's `remove()` callback. A
later update or another controller's probe can therefore follow a freed
list node. If this failed probe created the shared backlight, the global
backlight pointer would also refer to a managed object about to be released.

Patch `0014` uses one cleanup block under the existing mutex for all errors
after insertion. Moving registration failure into that block avoids a
double `list_del()`. The block clears the shared pointer only when its
parent is this client, so a failing secondary cannot discard the backlight
owned by a successfully bound primary. The failed client's driver data is
also cleared. Managed unregistration remains responsible for releasing a
registered backlight; the fix adds no second unregister operation.

| Failure point | Failed controller | Previously bound peer | Shared pointer |
|---|---|---|---|
| Shared backlight registration fails | Unlinked once; client data cleared | Retained | Already reset to null by the registration-error branch |
| Newly registered primary's own initial write fails | Unlinked; client data cleared | Retained, if any | Cleared because this client owns it |
| Primary probe fails while initializing an earlier secondary | Only the failed primary probe's controller is unlinked | Earlier secondary remains bound | Cleared because this primary created it |
| New secondary's initial write fails | Unlinked; client data cleared | Existing primary remains bound | Existing primary's pointer is retained |

The patch restores software lifetime invariants. A regmap error can still
occur after some hardware writes succeeded; this change does not invent a
hardware rollback sequence or claim that the two halves are synchronized
after a failed probe.

## Physical size remains unresolved

The Novatek defaults are 148 by 237 mm. With this board's configured pen
ranges, the current calculation reports 124 counts/mm on both axes:
`18400 / 148` and `29440 / 237`, using integer division. The TB371FC panel
source instead advertises 274 by 171 mm in landscape. Using the candidate
portrait orientation, 171 by 274 mm, would produce 107 counts/mm on both
axes. The owner's Android pen endpoint reports resolution zero, which
provides no measured physical-size calibration.

This is a real metadata inconsistency, but the candidate replacement is
not yet a verified active digitizer area. The panel's advertised dimensions
also do not establish the input controller's axis transformation. No patch
changes these constants or the absolute coordinate ranges.

Closing this item requires confirming the digitizer's usable physical area
and X/Y orientation, then making the dimensions board-specific rather than
changing a shared donor driver's defaults for every compatible controller.
A later acceptance check should verify reported counts/mm and coordinate
mapping together. See [input-and-pen.md](input-and-pen.md) and the
[display evidence](display.md) for the original observations.

## Exact application sequence

Run this only in a fresh build source tree. The separately audited 6.12
handoff patch can be applied first if it does not already install these
drivers. The commands deliberately use an explicit list; the repository's
generic `build-kernel.sh` defaults to the historical 7.1 branch and does not
automatically apply the 6.12 backports.

```sh
TB_FIX_PROJECT=/work/TB371FC-6.12
TB_FIX_KERNEL=/work/linux-6.12.114
TB_FIX_BACKPORTS="$TB_FIX_PROJECT/mainline-port/backports/linux-6.12"

git -C "$TB_FIX_KERNEL" apply --recount --check \
  "$TB_FIX_PROJECT/mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch"
git -C "$TB_FIX_KERNEL" apply --recount \
  "$TB_FIX_PROJECT/mainline-port/patches/0002-input-touchscreen-add-nt36523-spi-pen.patch"

git -C "$TB_FIX_KERNEL" apply --recount --check \
  "$TB_FIX_PROJECT/mainline-port/patches/0006-backlight-add-tb371fc-dual-ktz8866.patch"
git -C "$TB_FIX_KERNEL" apply --recount \
  "$TB_FIX_PROJECT/mainline-port/patches/0006-backlight-add-tb371fc-dual-ktz8866.patch"

install -m 0644 "$TB_FIX_BACKPORTS/tb371fc-ktz8866.c" \
  "$TB_FIX_KERNEL/drivers/video/backlight/tb371fc-ktz8866.c"

git -C "$TB_FIX_KERNEL" apply --check \
  "$TB_FIX_BACKPORTS/0013-input-nt36523-preserve-gpio-irq-errors.patch" \
  "$TB_FIX_BACKPORTS/0014-backlight-tb371fc-unwind-failed-probe.patch"
git -C "$TB_FIX_KERNEL" apply \
  "$TB_FIX_BACKPORTS/0013-input-nt36523-preserve-gpio-irq-errors.patch" \
  "$TB_FIX_BACKPORTS/0014-backlight-tb371fc-unwind-failed-probe.patch"

sha256sum \
  "$TB_FIX_KERNEL/drivers/input/touchscreen/nt36523/nt36xxx.c" \
  "$TB_FIX_KERNEL/drivers/video/backlight/tb371fc-ktz8866.c"
```

The last two hashes must match the two **after** entries above. If a build
intentionally stages the R170 or `mainline-port/drivers` backlight variant,
the `0014` hunks also pass application checks there, but that variant has a
different whole-file hash and policy. Record its identity explicitly. Do
not apply the fix twice or silently substitute another source variant.

## Build acceptance

For an isolated LLVM 19 compile check, use a new output directory. The
complete build task may instead retain its audited board configuration;
the driver symbols below still need to be enabled.

```sh
TB_FIX_OUT=/work/out-static-driver-fixes-6.12.114
make -C "$TB_FIX_KERNEL" O="$TB_FIX_OUT" ARCH=arm64 LLVM=-19 defconfig
"$TB_FIX_KERNEL/scripts/config" --file "$TB_FIX_OUT/.config" \
  --enable MODULES --enable OF --enable GPIOLIB --enable SPI \
  --enable INPUT --enable INPUT_TOUCHSCREEN --enable I2C \
  --enable BACKLIGHT_CLASS_DEVICE \
  --module TOUCHSCREEN_NT36523_SPI --module BACKLIGHT_TB371FC_KTZ8866
make -C "$TB_FIX_KERNEL" O="$TB_FIX_OUT" ARCH=arm64 LLVM=-19 olddefconfig

make -C "$TB_FIX_KERNEL" O="$TB_FIX_OUT" ARCH=arm64 LLVM=-19 \
  -j"$(nproc)" \
  drivers/input/touchscreen/nt36523/nt36xxx.o \
  drivers/input/touchscreen/nt36523/nt36xxx_fw_update.o \
  drivers/video/backlight/tb371fc-ktz8866.o
```

`REGMAP_I2C` is selected by the added backlight Kconfig entry. Confirm the
requested symbols survived `olddefconfig`. A successful object build checks
the compiler and kernel-header interfaces; it is not a module link check.
For the complete build gate, use the same configuration, source and
toolchain to build `Image modules`, retain the build log and resolved
`.config`, and inspect the resulting `nt36523_ts.ko` and
`tb371fc-ktz8866.ko` with `file`, `modinfo` and `sha256sum`. Assign the new
build its own release identity; do not combine it with historical R226 or
R170 module output.

No firmware blob is needed to compile the Novatek C sources. Runtime
firmware loading and input registration remain hardware tests; no module
was loaded on a tablet as part of this static fix task.

## Verification performed for these patches

- Both historical wiring patches passed `git apply --recount --check`
  against the relevant official `v6.12.114` files. Both new fixes applied
  and produced the exact source hashes recorded above.
- Patch `0014` also passed an independent application check against the
  tracked mainline source and the historical R170 source, each staged at
  the kernel target path.
- An offline C fault harness compiled the actual backlight function bodies
  with mocked list, registration, regmap and devres services. The fixed
  source passed 15 scenarios: each of the three initial register writes
  failing, registration failure, either controller probing first, failure
  while initializing an earlier peer, preservation of an existing primary,
  and successful probe/update/remove in both orders. AddressSanitizer and
  UndefinedBehaviorSanitizer reported no errors. LeakSanitizer was disabled
  because this executor runs under ptrace, so this is not a leak-sanitizer
  claim. The original source failed the first initial-write-failure case
  because the list/shared-pointer cleanup invariant did not hold.
- That harness is a temporary host-side control-flow check, not a kernel
  fault-injection or concurrency test. The build task records the separate
  full-kernel build result. This report does not claim a completed hardware
  test or extend the project's existing touch/pen/display acceptance.
