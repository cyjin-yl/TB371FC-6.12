# TFA9894: an isolated driver prototype now compiles for research4

The repository's existing downstream TFA98xx patch has now been compiled as
an **independent AArch64 external-module prototype** against the fixed
`6.12.114-tb371fc-research4-system` configuration and symbol versions. The
successful module contains the `nxp,tfa9894` match, has BTF, and all **75 imported
symbol CRCs** match the qualified R4 kernel.

This establishes a concrete source/build route for the amplifier driver that
is absent from the current runtime. The prototype is **unsigned, uninstalled
and unexecuted**. The 84 signed R4 modules, its DT and all firmware staging
remain unchanged. It does not add an audio hardware pass.

## Exact build result

The original builder report is retained byte-for-byte as
[tfa-module-prototype.json](evidence/tfa-module-prototype.json), SHA-256
`29fb3ac7b8952a30cf3bd5c70a27d1e6462b4d61edbfad3302ea6bdee3e9bec0`.
The separate [attempt history](evidence/tfa-module-prototype-history.json)
preserves the first failure, corrected derivation, successful inspector and
all warning categories.

| Check | Actual result |
| --- | --- |
| Location | doesvm CT102, existing isolated SSD Docker builder |
| Compiler identity | UID/GID 1000, no supplementary groups |
| Source/output/sysroot | New independent copies under `/work/tfa-module-prototype-v2` |
| Target kernel | `6.12.114-tb371fc-research4-system` |
| Final kernel configuration | Unchanged SHA-256 `0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275` |
| Prototype compile | Exit 0, 6.006 seconds |
| Module inspection | Exit 0, 0.471 seconds |
| ELF | 64-bit little-endian AArch64, machine 183 |
| Module size | 1,759,864 bytes |
| Module SHA-256 | `1b42be5150332798a12925aa5c3bdfdec5bb07bb764d07c11fa317c8a7c99dba` |
| Imported symbol versions | 75 checked; all match the fixed R4 `Module.symvers` |
| Device match | Actual module aliases include `nxp,tfa9894` |
| BTF | Present in the actual module |
| Signature | Absent; this is not an admitted member of the signed runtime |
| Physical device, firmware or calibration action | None |

The original R4 Image, configuration, `Module.symvers` and installed-module
inventory hashes were checked before and after the work. No original kernel
source or output permissions were changed. The independent copies were owned
by the unprivileged compiler; no private signing key or output `certs`
directory was copied. The module remains at:

```text
/work/tfa-module-prototype-v2/module/snd-soc-tfa98xx.ko
```

## Source and the limited adaptations

The source comes from the already present
[0003 downstream TFA patch](../../../mainline-port/patches/0003-wip-ASoC-codecs-add-support-for-TFA98xx-based-on-dow.patch),
identified in its header as `121d75c9b5d8bbdcd320290529d6e1347a23e28b`.
The exact patch is 1,725,238 bytes, SHA-256
`9d5ca9bf17c37601f17f0ea5271fe81b3f68fb2187a438a4244a76aba74745b7`.
The new recipe extracts only its 35 `tfa98xx-downstream` source files and
records every original and resulting file hash.

The adaptation follows the repository's historical R161 build reference:

1. Replace the single `snd_soc_component_to_dapm()` use with the 6.12
   `snd_soc_component_get_dapm()` API.
2. Apply the existing, pinned
   [MTP guard source transformation](../../../scripts/r160-sound/tfa98xx-mtp-guard.py),
   SHA-256 `57b07505a43b1f28d74b76737faa9846bb4f2463b8b97a398f003992f105484c`.
3. Compile the four existing implementation files through a dedicated
   external-module Kbuild.

The guard inserts rejection paths in `tfa98xx_key2()` for unlocking,
`tfa98xx_set_mtp()` and `tfa_dev_mtp_set()`. This experiment does **not** prove
complete prevention of persistent amplifier writes. The raw-register,
container, calibration and manual-MTP paths still need a coherent review
before any hardware load candidate is prepared. No guard behavior was tested
against an amplifier here.

The original [prototype recipe](../../../scripts/research/audio/tfa_module_prototype.py)
is kept unchanged after its first attempt. The
[v2 derivation](../../../scripts/research/audio/derive_tfa_prototype_v2.py)
checks that recipe's exact hash and makes only named build-environment changes.
Its resulting recipe has SHA-256
`ce5f8a1619086492336d612262a857354e101ca9ad6cf460e4a5ed0b15a9c9b5`.
It makes no additional driver-source change.

## The first failed attempt remains failed

The first preparation completed, but compilation exited 2 in 5.043 seconds.
Its reduced development-output copy omitted `arch/arm64/include/generated`,
so the compiler could not find `asm/types.h`. The inherited `/work/tmp` was
also not writable by UID 1000, and GNU make reported that it could not create
its jobserver FIFO. Neither diagnostic was a demonstrated TFA API defect.

The new v2 prefix copies the generated architecture headers and supplies a
separate temporary directory owned by that compiler. Its preparation took
19.441 seconds; the subsequent build and inspection passed. The failed v1
tree, source, command, logs and exit record remain intact. No retry overwrote
the original failure or modified the qualified kernel.

## Compiler warnings remain visible

The successful [complete build log](evidence/tfa-module-prototype-build.log)
has SHA-256
`6e789acaa413d31c4ca92126ddee6c5b8475ef0de461a6d9524158f5c8561f82`.
It contains **35 compiler warnings**:

| Category | Count |
| --- | ---: |
| Missing previous function prototypes | 23 |
| Conversions between the driver's two error-enumeration types | 10 |
| Unused function | 1 |
| Unused variable | 1 |

The existing kernel configuration has `CONFIG_WERROR` unset. The new Kbuild
adds no blanket warning suppression. A successful link does not resolve those
API-quality and error-semantics questions, and this result is not described as
a warning-free or deployment-ready driver.

## Firmware selection and integration still have separate requirements

The compiled source has one global `fw_name` parameter, defaulting to
`tfa98xx.cnt`; its asynchronous request uses that parameter. The actual module
metadata exposes the parameter and TFA9894 aliases. It does not advertise a
fixed `MODULE_FIRMWARE` entry or implement the shipping Android QS/YC selection
mechanism merely by compiling successfully.

The independent [shipping-binary and cached-selection audit](tfa9894-cached-metadata.md)
observed `tfa98xx_QS.cnt` in the owner's shared registration slot. That is useful
selection evidence, but does not prove all four amplifiers' independent
choices, successful DSP processing, calibration or speaker identity. This
prototype was given neither container, and no modprobe configuration was
created to force an assignment.

The current [kernel firmware contract](firmware-kernel-contract.md) remains
accurate for the named frozen kernel profile: its generic `tfa989x` driver does
not supply this TFA9894 container path, and the amplifier nodes are disabled.
The new artifact supplies an additional driver-source/build route; it does
not retroactively change that profile. Native integration still requires the
exact machine/DAI/TDM routes, board resources, coherent amplifier/container
selection, controlled firmware/DSP initialization and measured sound quality,
power behavior and recovery on the owner tablet.

All findings remain `host_build` or source evidence in the
[whole-device acceptance ledger](acceptance.json). The owner tablet was not
accessed by this compile experiment.
