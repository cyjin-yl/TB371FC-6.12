# Offline staging of the owner's TB371FC GPU firmware

[stage_gpu_firmware.py](../../../scripts/research/stage_gpu_firmware.py)
closes the GPU packaging gap identified in
[gpu-acceleration.md](gpu-acceleration.md): it checks which ZAP files the
kernel actually needs instead of copying whichever `bXX` files happen to
be present. It accepts an already extracted vendor firmware directory and
creates a new local staging prefix containing only GPU firmware, a provenance
manifest and checksums. It does not read a phone or image, mount a filesystem,
access block devices, use the network, upload files, install firmware or load
a driver.

After the owner explicitly authorized transfer, the three stock GMU, SQE
and complete ZAP ELF files were transferred to the private build workspace.
Their sizes and SHA-256 values matched the recorded Android capture.
Both complete-ELF and split-MDT packages have now been produced and checked
on CT102. Only the tools, tests and metadata manifests are checked in;
the proprietary firmware bytes remain private. Packaging does not establish
Secure World authentication or a working GPU on a mainline boot.

The later [firmware-to-kernel contract](firmware-kernel-contract.md) checks
the exact source, final configuration and compiled DT of research2-display.
It confirms this GPU mapping and separately records the DSP, WLAN, Bluetooth,
Novatek, amplifier and Venus request rules. Its available GPU/GMU nodes are
not proof of probe success. All PCIe controllers, touch, four amplifiers and
Venus remain disabled in that display candidate; supplying their firmware
cannot make it a complete all-device profile.

The separate [stock firmware archive](stock-firmware-bundle.md) now preserves
118 explicitly selected vendor files (38,546,828 bytes) on doesvm, including
GPU, ADSP/CDSP/SLPI, WLAN/board candidates, Bluetooth, Novatek, amplifier
containers and Venus. Source rereads and receiver checks agree for every file.
All six inspected ELF/MDT layouts have the required indexed payload files and
sizes. This closes the private transfer and structural-file-set gaps for that
fixed capture; board selection, canonical installation, ABI compatibility,
authentication and hardware loading are separate unresolved work. This broader
archive does not change the GPU-only behavior of `stage_gpu_firmware.py`.

## Actual packaging result

Both invocations of the tool returned exit status zero. The complete-ELF
package contains three firmware files; the split-MDT package contains four.
The MDT and its `b02` payload were reconstructed from the transferred complete
ELF, then independently checked against the sizes and SHA-256 values of the
original Android MDT and `b02` recorded in the capture. The reconstructed
bytes were accepted only after those comparisons succeeded.

| Private build output | Published metadata | Manifest SHA-256 |
| --- | --- | --- |
| `/work/gpu-stage-elf` | [gpu-staging-elf.json](evidence/gpu-staging-elf.json) | `3e58e725784b27bd8658bbcf6317e647358a2a039dc5875d9297c43146dd89da` |
| `/work/gpu-stage-mdt` | [gpu-staging-mdt.json](evidence/gpu-staging-mdt.json) | `d32cac1ccacbd8986c33a1cc34d3e34f921abdf0272d7b412997fd2bfb63265c` |

The reconstruction used `elf[0:148] + elf[4096:10808]` for the MDT and
`elf[12288:13964]` for `b02`; these offsets are specific to this captured
file. The reusable staging tool takes already extracted inputs and does
not assume those offsets for other firmware. Neither package has yet been
loaded by this owner's tablet under the new research kernel.

## The selected kernel's requested names

Linux 6.12's [A6xx catalogue](https://github.com/gregkh/linux/blob/v6.12.114/drivers/gpu/drm/msm/adreno/a6xx_catalog.c)
names `a650_gmu.bin` and `a650_sqe.fw` for A650. The checked-in
[TB371FC device tree](../../../mainline-port/arch/arm64/boot/dts/qcom/sm8250-lenovo-tb371fc.dts)
selects the board-specific ZAP name. The output mapping is fixed to that
contract:

| Input from the selected extracted directory | Relative to the new staging prefix | Condition |
|---|---|---|
| `a650_gmu.bin` | `lib/firmware/qcom/a650_gmu.bin` | Always required |
| `a650_sqe.fw` | `lib/firmware/qcom/a650_sqe.fw` | Always required |
| `a650_zap.elf` | `lib/firmware/qcom/sm8250/lenovo/tb371fc/a650_zap.mbn` | Explicit `--zap-format elf`; complete image required |
| `a650_zap.mdt` | Same board-specific `a650_zap.mbn` path | Explicit `--zap-format mdt`; required sibling files are validated |
| A required `a650_zap.bNN` | `lib/firmware/qcom/sm8250/lenovo/tb371fc/a650_zap.bNN` | Only when the ELF/MDT loader rules require this exact index |

Changing the `.elf` or `.mdt` extension to the DT-requested `.mbn` name does
not rewrite its bytes. These are alternative inputs for one requested
firmware file, so the format must be selected explicitly. There is no
fallback from an incomplete selected input to another file.

The tool does not stage Bluetooth, WLAN, DSP, Venus, touchscreen or audio
firmware. It does not recursively enumerate the source tree. Unrelated
files, including private keys, unknown `bXX` files and the separately
captured `a630_sqe.fw`, are not read or copied.

## Provenance is tied to this recorded device capture

Every file actually copied must match the size and SHA-256 recorded in
[android-gpu.json](evidence/android-gpu.json). The tool also pins the exact
bytes of that evidence file:

```text
67492d703071ebe5fa6abbdbc344103ecc427a88b85bc1ce55b7b54e0cdcae61
```

The capture time is `2026-11-22T21:06:57.696003+00:00`. Its attribution to
the owner's Lenovo TB371FC comes from this research session. Merely naming
a different device's ZAP file `a650_zap.elf` or placing it under a Lenovo
directory will fail the byte comparison. Supplying another evidence JSON
also fails unless its bytes match the same pinned capture; `--evidence`
only supports using a copy at another local path. There is no force,
unverified-input or replacement-hash command-line option.

| Captured input | Bytes | SHA-256 |
|---|---:|---|
| `a650_gmu.bin` | 41,548 | `df79fa8482fcc7587bb239b9c9e2b24bce4729893b990fe3f82b30da8175b01c` |
| `a650_sqe.fw` | 31,632 | `b4c27420fd6a5c6b511b254cc0fad8cdd40eea38ceb3418f895a1084f4460487` |
| `a650_zap.elf` | 13,964 | `9fa3242134d6070c4facba48bb5c5ef2206d92995035aec7daff01198e853299` |
| `a650_zap.mdt` | 6,860 | `61269235aed0949659580859c8694eaf5a9744aaa0ffa6ef1f5125ab3bf8083a` |
| `a650_zap.b02` | 1,676 | `a415e5452fa8f597670a6e51010e97bfabca7d20fbce8044caed64d9d5873113` |

The evidence file is the authoritative hash list. The staging tool does
not infer a device model from an ELF header, authenticate Qualcomm's
signature, prove which physical device originally supplied identical
bytes, or claim that Secure World will accept them. Its narrower guarantee
is a byte-for-byte match with this recorded capture plus structural
completeness for the selected loader. A new ZUI firmware version requires
a separately attributed capture and a reviewed update to the trust pin.

## ELF and MDT completeness checks

The validator follows the relevant rules in Linux `v6.12.114`
[`drivers/soc/qcom/mdt_loader.c`](https://github.com/gregkh/linux/blob/v6.12.114/drivers/soc/qcom/mdt_loader.c).
The existing `gpu_acceptance.inspect_zap()` reports best-effort observations;
its interface does not reject an incomplete package. This tool uses a
separate strict validator and leaves that collector unchanged.

It requires a bounded little-endian ELF32 version-1 header, a complete
program-header table, the Qualcomm metadata header and a hash segment. A
payload segment is considered loadable only when `p_type == PT_LOAD`,
`p_memsz != 0`, and its Qualcomm type bits are not `HASH`. For those
segments, `p_filesz` must not exceed `p_memsz`, the read limit or the ELF32
file-extent boundary.

If any nonempty program header's file extent is outside the selected ZAP
file, the kernel uses split packaging. This initial test includes hash and
non-loadable headers; it skips zero-file-size headers. In that mode,
**every valid payload segment with
nonzero `p_filesz` requires its own exact `bNN` file**, including a valid
segment whose extent happens to fit inside the metadata. A zero-file-size
segment is filled as BSS and needs no empty sibling file. The tool rejects
a missing or wrong-length required sibling before creating any output.

Metadata has its own hash-placement rule. If the metadata-header size plus
the hash size equals the selected file's length, the hash follows the
header in the packed metadata. Otherwise, the loader uses the hash's
program-header offset if that extent is inside the file, or requests the
hash index's `bNN` file if it is external. The tool handles this external
hash case too; excluding hash segments from payload loading does not mean
external hash bytes can always be omitted.

### What the owner's captured layout requires

The capture records three program headers:

| Index | Kind | File bytes | Interpretation for the captured package |
|---:|---|---:|---|
| 0 | Non-loadable metadata header | 148 | Already at the beginning of the selected ZAP file; `b00` is not needed |
| 1 | Qualcomm hash metadata | 6,712 | Inside the complete ELF; packed immediately after the 148-byte header in the MDT |
| 2 | Non-hash `PT_LOAD`, nonzero memory size | 1,676 | At offset 12,288 in the ELF; supplied by `b02` for the MDT |

For the **13,964-byte ELF**, the payload ends at exactly
`12,288 + 1,676 = 13,964`, so this complete input needs no `bXX` files. The
package contains three firmware files: GMU, SQE and the renamed ZAP ELF.

For the **6,860-byte MDT**, `148 + 6,712 = 6,860`: the hash is already
packed into the metadata, while the loadable payload is external. The
package contains four firmware files: GMU, SQE, the renamed MDT and
`a650_zap.b02`. The captured presence of `b00` and `b01` is not a reason to
copy them. These requirements are computed from the supplied, hash-checked
bytes during staging; the metadata observations alone are not substituted
for the firmware input.

## Usage

Run from the repository with Python 3.10 or newer on Linux. The source must
already contain the selected files as ordinary extracted files. The
output's parent must exist, and the output prefix itself must not exist.

To stage the complete ELF form:

```sh
python3 scripts/research/stage_gpu_firmware.py \
  --source /work/extracted-TB371FC/vendor/firmware \
  --output /work/gpu-firmware-tb371fc-elf \
  --zap-format elf
```

To stage and validate the split MDT form instead:

```sh
python3 scripts/research/stage_gpu_firmware.py \
  --source /work/extracted-TB371FC/vendor/firmware \
  --output /work/gpu-firmware-tb371fc-mdt \
  --zap-format mdt
```

The tool refuses an existing destination, including an empty directory or
a dangling symlink. It also refuses `..`, overlapping source/output trees,
symlinks in path components or selected files, special files such as FIFOs
and block devices, and live `/vendor`, `/odm`, `/system`, `/dev`, `/proc` or
`/sys` paths. It uses held directory descriptors and `O_NOFOLLOW` rather
than resolving a symlink and opening its target later. Inputs are bounded
at 32 MiB each and are read only after verifying a regular file; an inode,
size or timestamp change during the read causes failure.

Validation finishes before the staging prefix is created. Output files
are created exclusively under the newly created prefix, without inheriting
input executable permissions or traversing source links. Firmware is
written first, then the manifest, then the checksums. A successful command
returns a small JSON status and exit status zero. An error returns nonzero;
the tool never treats a partially read or skipped required input as valid.

The prefix contains two review files in addition to `lib/firmware/`:

- `gpu-firmware-manifest.json` records source filenames, captured paths,
  destination mappings, byte counts, SHA-256 hashes, capture provenance,
  selected input and the parsed loader requirements. It explicitly says
  signature authentication was not performed.
- `SHA256SUMS` covers every staged firmware file and the manifest. Verify
  it from inside the chosen staging prefix with `sha256sum --check SHA256SUMS`.

The manifest excludes absolute extraction/output paths and new wall-clock
timestamps. Repeated staging of the same capture, inputs and selection
therefore produces identical manifest and checksum bytes in different
fresh output directories. Neither the staging prefix nor its proprietary
firmware files should be added to this source repository by this task.

## Offline regression coverage

Run:

```sh
python3 scripts/research/test_gpu_firmware.py -v
```

The 31 tests use generated ELF32 fixtures and synthetic payloads. They
mock the evidence trust pin in the test process only; no production bypass
or vendor binary is supplied. Coverage includes:

- Complete ELF success without any split files; unrelated keys, A630
  firmware and unknown segment files are excluded.
- Packed MDT success with only `b02`; external-hash MDT requiring `b01`;
  hash-marked `PT_LOAD` and zero-memory-size segments excluded from payload
  loading; BSS needing no sibling file.
- A missing required segment, an ELF-inconsistent length even when that
  length/hash is in the synthetic capture, and different same-size bytes.
- The rule that one external nonempty header makes all nonempty valid
  payloads use split files, including when only a hash/non-loadable extent
  is outside the file. A zero-file-size BSS header alone does not trigger
  split mode. There is no automatic ELF/MDT fallback.
- Invalid program-header bounds, an oversized file-to-memory segment,
  and an image with no valid non-hash loadable payload.
- A renamed foreign ZAP, tampered capture JSON, source/evidence symlinks,
  symlinked source and output parents, parent traversal, a FIFO, overlapping
  trees, existing output and a dangling output symlink.
- Identical manifests/checksums in two new prefixes, plus verification of
  the produced checksums.

These tests passed in the local executor. The real pinned evidence JSON
also passed its SHA check and yielded precisely the seven captured A650
candidate names; which of those are copied is determined by the selected
format and the loader rules above. Actual firmware-byte staging, Qualcomm
authentication and Adreno rendering are separate checks and remain outside
this offline tool validation.
