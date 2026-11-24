# Fixed stock-firmware capture and private transfer

Experiment date: 2026-11-23, Asia/Shanghai. This report records actual reads from
the owner's running Android installation and an independently verified copy on
doesvm. The [public evidence](evidence/stock-firmware-bundle.json) contains all
118 original file paths, byte sizes, SHA256 values, parsed MDT program headers,
required segment relationships and explicit result boundaries. Proprietary
payload bytes remain only in the owner's private capture/archive directories.

## Observed result

**All 118 explicitly selected files were captured and transferred successfully.**
Their total uncompressed payload is **38,546,828 bytes**. Every source was a
nonempty regular file, opened read-only without following symlinks. A second
independent source read matched each first-read hash. The receiver checked the
exact archive member set, each member's length and hash, the source manifest,
gzip integrity, and a separate re-read of the stored archive. Capture and the
complete SSH pipeline both returned 0.

| Artifact | Identity |
| --- | --- |
| Private compressed archive | `stock-firmware.tar.gz`, **15,747,897 bytes** |
| Archive SHA256, source and receiver | `fc331d84ed585457b4183b08f799a49d9839d3114bf5ec2f281a725b87fe5f92` |
| Source manifest SHA256 | `d1bf375a24a065489013567d03746900967bf8eb00455f0067b79d8350dd5ca9` |
| Collector/receiver script SHA256 | `9ca9ccbdc628ff1a1b365ef4b5deb092ed8405acd1bcb79c8c0454f700bd18f1` |
| Exact frozen kernel contract JSON | `26ab16aa3e71f2317e736aa0877572616fb13c64f29ff5ea3381278bc931644a` |

The source archive remains in
`/data/local/tmp/tb371fc-stock-firmware-20261123` on the tablet. The independently
verified copy is in
`/tank/shared/projects/tb371fc-linux/private/stock-firmware-20261123` on doesvm.
The receiver directory is mode `0700`; its archive is `0600`. The directory
also holds the source manifest, receiver receipt and a private exact-command
record. The public evidence identifies those records by hash without publishing
the private SSH endpoint. No archive member was extracted into the host system
or installed under a live firmware search directory.

All required file/length dependencies in the six inspected ELF/MDT variants
were present. This is a **structural completeness** result. Qualcomm signature
authentication, PAS handoff, memory reservations, firmware ABI, remoteproc
services and hardware operation remain untested. The result deliberately keeps
`all_hardware_firmware_contracts_satisfied=false`,
`vendor_signature_authentication_performed=false`, `firmware_loaded=false`,
`video_decode_tested=false` and `tablet_linux_tested=false`.

## Exact capture scope

The [collector and receiver](../../../scripts/research/stock_firmware_bundle.py)
share a fixed allowlist. Neither searches a firmware directory for arbitrary
matches. The only source roots are `/vendor/firmware`,
`/vendor/firmware_mnt/image` and `/vendor/bt_firmware/image`. The operation reads
no Android user configuration, network credentials or unrelated device data.
Its only Android writes create a new private project capture and script.

| Group | Exact selected family | Files | Payload bytes |
| --- | --- | ---: | ---: |
| ADSP | `adsp.mdt`, `adsp.b00`–`adsp.b18` | 20 | 15,502,768 |
| CDSP | `cdsp.mdt`, `b00`–`b06`, `b08`, `b09`, `b11` | 11 | 6,079,158 |
| SLPI | `slpi.mdt`, `slpi.b00`–`slpi.b20` | 22 | 7,261,168 |
| Venus video codec | `venus.mdt`, `b00`–`b10`, `b19` | 13 | 946,108 |
| QCA6390 executable/regulatory candidates | `qca6390/amss20.bin`, `m3.bin`, `regdb.bin` | 3 | 4,670,960 |
| QCA6390 board-data candidate pool | `bdwlan.e01`–`bdwlan.e1a`, `bdwlan.e25`, `bdwlan.elf` | 28 | 1,620,412 |
| QCA6390 Bluetooth | `htbtfw10.tlv`, `htbtfw20.tlv`, `htnv10.bin`, `htnv20.bin` | 4 | 345,144 |
| Adreno 650 | GMU, SQE, complete ZAP ELF, ZAP MDT and `b00`–`b02` | 7 | 102,540 |
| Novatek | Eight BOE/Tianma firmware/manufacturing variants, original filenames | 8 | 1,966,080 |
| TFA9894 containers | `tfa98xx_QS.cnt`, `tfa98xx_YC.cnt` | 2 | 52,490 |
| **Total** | **Fixed source set** | **118** | **38,546,828** |

The source manifest retains the full path of every entry, including all eight
Novatek variant names. The seven A650 files match the previously captured
[Android GPU evidence](evidence/android-gpu.json) byte-for-byte. Both TFA
containers match the previously pinned hashes in
[`package-stock-firmware.sh`](../../../scripts/package-stock-firmware.sh).
These comparisons establish byte identity with existing project observations;
they do not establish vendor signature trust.

## MDT findings: sparse indices are intentional

The structural parser follows the exact split/metadata rules documented in the
[frozen research2 kernel contract](firmware-kernel-contract.md), whose source
manifest, configuration, DT and Image hashes are retained separately. It checks
ELF32 header bounds, original program-header indices, hash metadata location,
loadable file/memory sizes and the precise lengths of required split files.
The archive retains original names even when a future Linux firmware tree
would use a different directory or `.mbn` metadata suffix.

| Inspected main file | Program headers | Required external payload indices | Zero-file-size loadable indices | Result |
| --- | ---: | --- | --- | --- |
| `a650_zap.elf` | 3 | None: complete image | None | Complete embedded image structure |
| `a650_zap.mdt` | 3 | 2 | None | `a650_zap.b02` length matches |
| `adsp.mdt` | 20 | 2–18 | 19 | All 17 payloads match |
| `cdsp.mdt` | 13 | 2–6, 8, 9, 11 | 7, 10, 12 | All eight payloads match |
| `slpi.mdt` | 22 | 2–20 | 21 | All 19 payloads match |
| `venus.mdt` | 20 | 2–10, 19 | 12, 14, 16, 18 | All ten payloads match |

All five `.mdt` files carry their hash metadata packed immediately after the
metadata header. Their captured `b00` and `b01` files are therefore preserved
source evidence, not additional files required by this particular loader path.
The full A650 ELF carries its hash inside the image and needs no external
segment files.

For CDSP, the absent `b07`, `b10` and `b12` correspond to zero `p_filesz` entries.
For Venus, **every index from 11 through 18 has zero `p_filesz`**. The even
indices in that range have memory to zero-fill; the odd indices also have zero
`p_memsz` and are excluded from the loader's valid payload set. Neither family
has a missing required firmware file on that basis. The ADSP index 19 and SLPI
index 21 likewise contain no file bytes. Renumbering the retained segments
would break the loader's index-based names.

The parser's bounded checks also exercised three failure-relevant cases with
synthetic ELF fixtures: a packed hash does not require a separate hash file,
a zero-file-size segment needs no payload file, and absent or incorrectly sized
required payloads produce an incomplete result. An unlisted source path is
rejected before opening it. Those fixture checks concern the parser; the actual
118-file results come from the captured bytes and receiver receipt.

## Canonical request paths and remaining gaps

The independent source audit establishes what the frozen
`6.12.114-tb371fc-research2-display` candidate would request if a device probed.
It does not make every captured file a valid or currently enabled runtime
input. **This transfer generated no canonical firmware tree and loaded no
firmware.**

| Function | Source-grounded mapping or unresolved selection | Remaining boundary |
| --- | --- | --- |
| Adreno SQE/GMU/ZAP | Prefer `qcom/a650_sqe.fw`, `qcom/a650_gmu.bin`; DT selects `qcom/sm8250/lenovo/tb371fc/a650_zap.mbn` | Files and ZAP structure are available; secure loading, GPU probe, OpenGL and Vulkan remain physical tests |
| ADSP/CDSP/SLPI | DT selects `qcom/sm8250/lenovo/tb371fc/{adsp,cdsp,slpi}.mbn`; preserve original indexed siblings in the same directory | Required file sets close structurally; PAS authentication, reserved-memory compatibility and services remain untested |
| QCA6390 WLAN | API1 candidates map `amss20.bin` to `ath11k/QCA6390/hw2.0/amss.bin` and retain `m3.bin`; API2 `firmware-2.bin` has its own container format | All PCIe controllers remain disabled in this candidate. No mainline board database or correct runtime board entry was selected; firmware protocol compatibility is untested |
| WLAN board data / regdb | Preserve all 28 `bdwlan.*` originals as candidates. The QCA6390 table has `supports_regdb=false` | No arbitrary blob was renamed to `board-2.bin`, `board.bin` or `firmware-2.bin`; captured `regdb.bin` is not proof of a required QCA6390 request |
| Bluetooth | `qca/htbtfw%02x.tlv` and `qca/htnv%02x.bin`, suffix selected from runtime ROM version | Both 10/20 pairs are captured; the actual mainline ROM-derived selection and HCI operation remain unverified |
| Novatek touch/pen | Final DT names the Tianma/BOE `_fw_6.bin` variants under `lenovo/tb371fc/` | Controller and SPI14 remain disabled. GPIO panel selection, firmware startup and pen/touch events require physical validation; manufacturing payload presence proves no runtime use |
| TFA9894 | Keep original QS/YC container names and hashes | All four nodes disabled; `SND_SOC_TFA989X` unset, and that generic driver does not supply a TFA9894 container-loading contract |
| Venus video codec | Exact default request is `qcom/vpu-1.0/venus.mbn`; its indexed siblings stay beside it | Stock MDT structure closes, but the Venus parent remains disabled and reserved-memory/HFI/secure-boot compatibility was not tested. Hardware video decode remains separate from GL/Vulkan |

The Venus default was checked against this exact candidate's
`drivers/media/platform/qcom/venus/core.c` and `firmware.c`, not inferred from a
similarly named firmware file. The mainline loader can request an MDT container
using an `.mbn` suffix; changing the filename does not join its split payloads
or establish ABI/signature compatibility. The private archive therefore keeps
`venus.mdt` and its original `venus.bNN` names intact.

## Execution, privacy and completion

The collector ran as root only to read the three explicit vendor roots and
create its new project capture. It did not read `/data` user configuration or
change a loader, driver, power, charging or thermal control. The transport used
the owner's already verified Dropbear connection, with batch mode and strict
host-key checking retained. No new credential or host-trust entry was created.
The precise commands and tool exit output are stored in the private
`transfer-command.json`; its SHA256 is
`b48dcc5df382f52ef95e20e10e1bfdbc25e7be0b51945fa3bcc647b8516d736b`.

The SSH pipeline completed normally. Scoped process checks on both devices
found no remaining owned sender or receiver process; this task left no
background transfer job. The earlier Nura builder VM and media server had
already been stopped after its independently verified rootfs export. All
private captures and completed evidence are retained. No source firmware was
modified, firmware installed, upstream message sent, or physical Linux
acceptance gate advanced by this operation.
