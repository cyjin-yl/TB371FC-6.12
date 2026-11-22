# Firmware requests in the frozen research2-display kernel

## Scope and result

This is a **read-only source, final configuration and compiled-device-tree
contract** for `6.12.114-tb371fc-research2-display`. It identifies the filenames
that this kernel would request if the corresponding devices successfully
probed. It does not validate the contents or transfer of the separate stock
firmware archive, authenticate a blob, load a driver or establish hardware
operation. No kernel input, recipe, artifact or earlier evidence was changed.

The [machine-readable contract](evidence/firmware-kernel-contract.json) records
the final DT state, relevant resolved configuration, conditional request rules,
and SHA-256 identities and reviewed locations of 22 source files. Its fixed
kernel identities are:

| Input | SHA-256 |
| --- | --- |
| Source manifest | `845914d9cc1c876f10704f3334ee942b2c26deaa8045ce9c2ef82ef2920cde21` |
| Final configuration | `e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8` |
| Compiled display DTB | `50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e` |
| Image | `181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d` |

The [complete build record](research2-display-build.md) establishes which Image,
modules and DT were actually built. The audit read that candidate's source at
`/work/research2-display/linux-6.12.114-research2-display` and its final artifacts
in the isolated SSD builder. Temporary source copies used for analysis were
verified against hashes calculated at that source tree.

All names below are **relative to the kernel firmware search root**. They are
not Android source paths. The generic firmware loader searches its configured
firmware locations; the relevant source is `drivers/base/firmware_loader/main.c`.
`CONFIG_EXTRA_FIRMWARE=""` in this build. A copied file with a plausible name is
not proof that its format, signature, ABI or device-specific data is suitable.

## Actual enabled state and request mapping

“Available” in this table means OF availability, including available ancestors.
It does not mean that probe, power sequencing or firmware loading has succeeded.
`y` denotes built-in code and `m` denotes a built module.

| Function | Actual final DT/configuration | Request contract |
| --- | --- | --- |
| Adreno 650 SQE and GMU | GPU and GMU `okay`; `DRM_MSM=y` | Prefer `qcom/a650_sqe.fw` and `qcom/a650_gmu.bin` |
| A650 signed ZAP | Available GPU child; DT supplies a device-specific name | Exact `qcom/sm8250/lenovo/tb371fc/a650_zap.mbn` |
| ADSP | `remoteproc@17300000` `okay`; `QCOM_Q6V5_PAS=m` | Exact `qcom/sm8250/lenovo/tb371fc/adsp.mbn` |
| CDSP | `remoteproc@8300000` `okay`; same PAS module | Exact `qcom/sm8250/lenovo/tb371fc/cdsp.mbn` |
| SLPI | `remoteproc@5c00000` `okay`; same PAS module | Exact `qcom/sm8250/lenovo/tb371fc/slpi.mbn` |
| QCA6390 WLAN | **All three PCIe controller nodes are disabled**; `PCIE_QCOM=y`, `ATH11K=m`, `ATH11K_PCI=m`, `MHI_BUS=y` | Conditional directory `ath11k/QCA6390/hw2.0/`; API2 container or separate AMSS/M3; separately selected board data |
| QCA6390 Bluetooth | Bluetooth child and UART ancestors available; HCI UART/QCA modules, GENI UART and WCN power sequencer built | `qca/htbtfw%02x.tlv` and `qca/htnv%02x.bin`, with a runtime ROM-derived hexadecimal suffix |
| Novatek touch/pen controller | **Touch node and SPI14 parent disabled**; `TOUCHSCREEN_NT36523_SPI=m` | Selected `lenovo/tb371fc/novatek_ts_tm_fw_6.bin` or `lenovo/tb371fc/novatek_ts_fw_boe_6.bin` |
| Four TFA9894 amplifiers | **All four disabled; `SND_SOC_TFA989X` not set; that driver's OF table also lacks TFA9894** | No validated canonical request for the QS/YC containers in this kernel |
| Venus | **`video-codec@aa00000` disabled**; `VIDEO_QCOM_VENUS=m` | Default `qcom/vpu-1.0/venus.mbn`, with any required indexed split segments alongside it |

The raw DT paths, compatible strings, firmware properties and unavailable
ancestors are retained in the JSON. In particular, available decoder/encoder
children do not override their disabled Venus parent. Available PCIe endpoint
child nodes likewise do not override disabled PCIe controllers. The QCA PMU's
presence does not enable those controllers.

## A650 and remote processors

The A650 entry in `drivers/gpu/drm/msm/adreno/a6xx_catalog.c` selects
`a650_sqe.fw` and `a650_gmu.bin`. `adreno_request_fw()` in `adreno_gpu.c`
initially tries the `qcom/` location directly, the legacy unprefixed location,
and then the `qcom/` location through the normal firmware helper. Once it has
selected a location, `fwloc` controls subsequent catalog firmware requests.
Supplying both ordinary GPU files under `qcom/` follows the preferred contract.

The final ZAP child has an explicit `firmware-name`. `zap_shader_load_mdt()`
therefore requests that exact device-specific path directly and bypasses the
catalog-location fallback. The catalog's legacy `a650_zap.mdt` string does not
override the DT path. A structurally validated full signed ELF or a validated
split MDT can use the requested `.mbn` name without changing its bytes, but the
applicable segment and metadata rules below must still be satisfied. Existing
GPU staging/validation details are documented in [firmware.md](firmware.md).

`qcom_q6v5_pas.c` reads `firmware-name` before allocating each remote processor.
The final DT overrides the generic `adsp.mdt`, `cdsp.mdt` and `slpi.mdt` defaults
with the three Lenovo `.mbn` paths above. The corresponding SM8250 match entries
exist. All three resource descriptions set `auto_boot=true`; this matters only
after the module has loaded and probe dependencies have succeeded. Remoteproc
then requests its chosen firmware and passes it through the MDT/PAS loading
path. No generic unqualified-name fallback was established for a missing
DT-selected file.

DSP authentication and boot remain separate from usable audio, sensors or
compute services. This audit does not validate the services carried by the
stock DSP firmware or the associated userspace support.

## Venus and the common MDT rules

The exact answer for this build is **`qcom/vpu-1.0/venus.mbn`**.
`drivers/media/platform/qcom/venus/core.c` assigns that string to `sm8250_res`
and maps `qcom,sm8250-venus` to that resource. `venus_boot()` in `firmware.c`
first looks for a DT `firmware-name`, then falls back to the resource string.
The final DT has no Venus firmware-name override. `venus_load_fw()` requests
the selected path and invokes `qcom_mdt_load()` or `qcom_mdt_load_no_init()`
according to the secure-loading path. It also checks the reserved-memory size.
These are source contracts; the disabled node has not requested or loaded any
Venus firmware during this investigation.

The frozen `drivers/soc/qcom/mdt_loader.c` has SHA-256
`135cca918b03f795d31cd12831aa84cab03a21ee39cda8665d09218d2cca5567`.
It interprets an ELF32 header/program-header layout. A suffix rename does not
convert or join the file's contents. The rules are:

1. **Segment names retain the original ELF program-header index.** The loader
   replaces the final three characters of the requested main filename with
   `b%02d`, using a decimal index. For example,
   `qcom/vpu-1.0/venus.mbn` with payload index 3 requests
   `qcom/vpu-1.0/venus.b03`. A renamed `adsp.mdt` requested as Lenovo's
   `adsp.mbn` still uses `adsp.bNN` in that same Lenovo directory. Do not
   renumber a sparse set of segments or put them in a different directory.
2. **Split detection considers every nonempty program header.** A nonzero
   `p_filesz` entry whose start or end lies beyond the main file makes the image
   split, including hash or other non-`PT_LOAD` entries. Zero-file-size BSS
   entries do not make it split.
3. **Payload selection is narrower than split detection.** The loader copies
   only `PT_LOAD`, non-hash entries with nonzero `p_memsz`. In split mode each
   selected entry with nonzero `p_filesz` is requested from its `bNN` file,
   even if that particular payload would fit inside the main file. BSS is
   zero-filled. A split payload must match `p_filesz`; `p_filesz` cannot exceed
   `p_memsz`, and the destination must fit the reserved region.
4. **Hash metadata has its own branch.** The first program header must be
   non-`PT_LOAD`, with a subsequent QCOM hash entry. If the first header's
   `p_filesz` plus the hash entry's `p_filesz` equals the main file size, the hash
   is read from the packed bytes immediately after the first-header bytes.
   Otherwise an entirely in-file hash is read at its declared offset; otherwise
   the loader requests that hash entry's indexed `bNN` file.

Consequently, preserving all original stock files is useful provenance, but
their count is not the runtime-required segment count. A complete image can
need no external payload files; a split image can omit indexes that represent
metadata or empty segments. The archive's own ELF/size inspection must establish
which case applies to each captured image. This source audit does not establish
that any captured Venus firmware's HFI ABI or secure signature is accepted by
the device.

## QCA6390 WLAN

The actual QCA6390 hardware entry uses `QCA6390/hw2.0`; the shared path builder
prepends `ath11k/`. This frozen 6.12 source has the newer firmware API selection:

- `fw.c` first requests `firmware-2.bin`. It checks the `QCOM-ATH11K-FW` magic
  and parses information elements for AMSS and M3. **Raw stock AMSS is not that
  container and must not simply be renamed to it.**
- Failure to obtain/parse that container selects API1. When no embedded AMSS
  or M3 is available, the code uses `amss.bin` through MHI and `m3.bin` through
  QMI. One MHI comment calls the older image `mhi.bin`; the operative
  `ATH11K_AMSS_FILE` macro in `hw.h` is **`amss.bin`**.
- Board data is separate. The driver requests `board-2.bin`, verifies its
  `QCA-ATH11K-BOARD` container magic and selects entries by runtime board keys,
  trying its full/fallback/chip-ID key forms. It then permits a raw `board.bin`
  fallback if those API2 attempts fail. Renaming an arbitrary `bdwlan.*` blob
  to either destination does not establish the appropriate board identity.
- The QCA6390 table sets `supports_regdb=false`. The conditional separate
  regulatory database fetch seen for other ath11k hardware is not a required
  QCA6390 file request in this exact table.

The 28 stock `bdwlan.*` files can therefore remain an identifiable candidate
pool in the archive. This audit supplies no basis for generating a board-2
container, picking a specific raw board fallback or enabling the disabled PCIe
path. Firmware protocol compatibility with this kernel is also untested.

## QCA6390 Bluetooth

`hci_qca.c` matches `qcom,qca6390-bt` and obtains a runtime SoC/ROM version.
`btqca.c` derives a ROM byte and uses the QCA6390 switch branches to request
`qca/htbtfw%02x.tlv` and `qca/htnv%02x.bin`. This audit does not establish the
actual hexadecimal suffix by communicating with the controller.

The final Bluetooth DT has no `firmware-name` override. If a later DT supplied
one, that argument changes the **NVM** selection: a name with an extension gets
`qca/` prepended; a stem goes through board-ID naming. It does not replace the
QCA6390 rampatch branch. Keep captured filenames and runtime version evidence
distinct; file presence alone does not prove which branch will be selected.
Relevant HCI UART, QCA helper, GENI UART and WCN power-sequencing drivers are
compiled, but their physical probe and operation have not been exercised.

## Novatek and TFA

The Novatek driver first accepts a fixed `firmware-name`. Without one, when the
panel-ID GPIO and both named variants are present, it uses the **logical GPIO
value 1 for Tianma and 0 for BOE**. The selected names are the two final DT
properties listed above. Only if no name is selected does it fall back to
`novatek/nt36523.bin`. `nt36xxx_fw_update.c` passes the chosen string to
`request_firmware()`; its old `/etc/firmware` comment does not override the
generic loader's filesystem search. Boot/resume/recovery use this chosen
controller firmware. This audit establishes no separate pen or manufacturing
test firmware request. Android's panel selection is not a substitute for an
observed mainline panel-ID GPIO value.

The display candidate keeps both Novatek and SPI14 disabled. It does not load
that controller's firmware merely because its module or blobs are present.

All four `nxp,tfa9894` nodes are disabled, and `CONFIG_SND_SOC_TFA989X` is not
set. The inspected generic `tfa989x.c` matches TFA9890/9895/9897, bypasses their
DSP, and has no firmware-request call. It supplies **no TFA9894 QS/YC container
request contract**. Retain those stock containers with their original names and
variant provenance; naming or copying them cannot supply the missing amplifier
driver/DSP integration.

## Source references and boundaries

The contract JSON contains every audited source file's full SHA-256 and line
locations. The principal references within the frozen assembled source are:

| Contract | Source and relevant locations |
| --- | --- |
| A650 catalog and search/DT override | `drivers/gpu/drm/msm/adreno/a6xx_catalog.c`, A650 entry; `adreno_gpu.c`, `zap_shader_load_mdt()`, `adreno_request_fw()`, `adreno_load_fw()` |
| DSP selection and remoteproc requests | `drivers/remoteproc/qcom_q6v5_pas.c`, probe and SM8250 match/resource tables; `remoteproc_core.c`, boot/autoboot firmware requests |
| Venus default and load | `drivers/media/platform/qcom/venus/core.c`, `sm8250_res` and OF match; `firmware.c`, `venus_boot()` and `venus_load_fw()` |
| Split and metadata rules | `drivers/soc/qcom/mdt_loader.c`, `mdt_load_split_segment()`, `qcom_mdt_read_metadata()`, `qcom_mdt_bins_are_split()`, `__qcom_mdt_load()` |
| WLAN paths and format selection | `drivers/net/wireless/ath/ath11k/{core.c,core.h,hw.h,fw.c,fw.h,mhi.c,qmi.c}`; `drivers/bus/mhi/host/boot.c` |
| Bluetooth dynamic names | `drivers/bluetooth/{hci_qca.c,btqca.c}` |
| Novatek selection and request | `drivers/input/touchscreen/nt36523/{nt36xxx.c,nt36xxx.h,nt36xxx_fw_update.c}` |
| TFA match and DSP bypass | `sound/soc/codecs/tfa989x.c` |

The separate firmware archive must record original paths, sizes, hashes and
actual MDT segment relationships. This report deliberately makes no assertion
that all files in that archive are requested by this DT, that a canonical blob
tree has been installed, or that authentication and hardware acceptance have
passed. All physical acceptance gates in [acceptance.md](acceptance.md) remain
separate.
