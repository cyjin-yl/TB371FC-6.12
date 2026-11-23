# Canonical stock-firmware trees for the frozen research2 kernel

This follow-up turns the previously verified 118-file private capture into
actual `lib/firmware` trees for image assembly. It also records a bounded
read-only search for Android WLAN board selection and Bluetooth ROM metadata.
The [machine-readable evidence](evidence/stock-firmware-staging.json) contains
both full output manifests, per-file source/destination hashes, command/exit
records, shared-parser identities, validation results and the radio observations.

## Actual staging result

Both invocations of
[`stage_stock_firmware.py`](../../../scripts/research/stage_stock_firmware.py)
returned 0 in the original CT102 `tb371fc-build-20261123` container. Every output
file was independently re-read and checked. All five selected canonical `.mbn`
images were parsed again under their **destination** names, verifying that their
indexed sibling paths still close after the metadata suffix/directory mapping.

| Output in that container | Firmware files | Firmware payload bytes | Manifest SHA256 |
| --- | ---: | ---: | --- |
| `/work/stock-fw-stage-v1/canonical-elf` | 69 | 35,332,142 | `4feb4264605198fc56114fb8b8044ffcd51f662107270a857f59fdaf2e8bcf7c` |
| `/work/stock-fw-stage-v1/canonical-mdt` | 70 | 35,326,714 | `adf7c9a901e7bc1c65e004fb139e3ebc76b324167193f8d10bbd997c28ce2bfd` |

Each prefix contains `lib/firmware`, `stock-firmware-manifest.json` and
`SHA256SUMS`. The first uses the complete A650 ZAP ELF; the second uses its MDT
and required `b02` payload. All other chosen inputs and destination paths are
the same. The complete ELF is larger because its embedded layout includes
padding that the separate MDT/payload representation does not retain.

The prefixes are mode `0700`; internal directories use `0755` and files use
`0644`, allowing ordinary later rootfs/initramfs assembly while keeping the
staging prefix private. `SHA256SUMS` covers all firmware files and the manifest.
The checksum-list hashes are:

- ELF tree: `fa7466ec479bb474a3f82cd03629d9de5cf251ef66379260ac5fa965730c66c5`.
- MDT tree: `a1ae5be4deeab0d2781feeda456bae666985ae0d5f7c72b12b60e1d4a5150a6c`.

These are installable **file trees**, with explicit unresolved component gates.
No firmware was installed into the running tablet or host firmware search
directory, authenticated, or loaded. The manifests retain
`all_hardware_firmware_contracts_satisfied=false`. A later consumer must retain
that distinction when incorporating the files into its own image.

## Fixed inputs and unchanged contract

The stager pins the existing private archive and the two frozen public evidence
documents. It has no command-line replacement hash, force mode or fallback to
an unverified package. A different Android capture or kernel request contract
requires a deliberate reviewed change.

| Input | SHA256 |
| --- | --- |
| 15,747,897-byte source archive | `fc331d84ed585457b4183b08f799a49d9839d3114bf5ec2f281a725b87fe5f92` |
| Manifest inside that archive | `d1bf375a24a065489013567d03746900967bf8eb00455f0067b79d8350dd5ca9` |
| [Verified 118-file capture/transfer evidence](evidence/stock-firmware-bundle.json) | `94661a62898cd1cc7ef75bf90d713371b0bc5bb7372215c13dc7d5d34ce27c2b` |
| [Frozen firmware request contract](evidence/firmware-kernel-contract.json) | `26ab16aa3e71f2317e736aa0877572616fb13c64f29ff5ea3381278bc931644a` |
| Shared MDT parser, `stock_firmware_bundle.py` | `9ca9ccbdc628ff1a1b365ef4b5deb092ed8405acd1bcb79c8c0454f700bd18f1` |
| This stager | `428f09ad0d73e881cc4095f9c79d025fdbab08078df48e9e786ea4db467c82a2` |

The request contract is still `6.12.114-tb371fc-research2-display`, with Image
SHA256 `181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d`
and DTB SHA256
`50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e`.
This work did not change that kernel, DT, prior evidence JSON or any firmware
payload bytes. The [contract report](firmware-kernel-contract.md) remains the
authority for driver configuration, effective DT availability and request rules.

The new stager directly reuses `stock_firmware_bundle.inspect_mdt()` for ELF
selection and split dependencies. It reuses the GPU stager's strict bounded
regular-file I/O, path validation and exclusive prefix publisher. It introduces
no second MDT algorithm. The source archive is read as a bounded stream of
regular members; no `tar.extractall()` or member-directed filesystem extraction
is used. The exact archive, manifest and every source member must match before
the output prefix is created.

## Exact mapping and explicit variant choices

All destination paths below are relative to the staging prefix. Only
loader-required MDT sibling segments are installed. The public manifest lists
every exact filename and excludes the other captured inputs explicitly.

| Component | Canonical destination | Installed files | Selection / remaining condition |
| --- | --- | ---: | --- |
| A650 | `lib/firmware/qcom/a650_{gmu.bin,sqe.fw}` and Lenovo `a650_zap.mbn` | 3 ELF / 4 MDT | Explicit `--zap-format`; GPU loading and rendering remain untested |
| ADSP | `lib/firmware/qcom/sm8250/lenovo/tb371fc/adsp.mbn` plus `b02`–`b18` | 18 | Matches the DT override and original program-header indices |
| CDSP | Same Lenovo directory, `cdsp.mbn`, `b02`–`b06`, `b08`, `b09`, `b11` | 9 | Empty indices are not manufactured or renumbered |
| SLPI | Same Lenovo directory, `slpi.mbn` plus `b02`–`b20` | 20 | File dependencies close; remoteproc services remain untested |
| Venus | `lib/firmware/qcom/vpu-1.0/venus.mbn`, `venus.b02`–`venus.b10`, `venus.b19` | 11 | Exact frozen default request; node remains disabled and HFI/memory/authentication untested |
| Novatek | `lib/firmware/lenovo/tb371fc/novatek_ts_tm_fw_6.bin` and `novatek_ts_fw_boe_6.bin` | 2 | Explicit `--novatek-variants dt-both-6`; preserves both actual DT alternatives |
| Bluetooth | `lib/firmware/qca/htbtfw10.tlv`, `htbtfw20.tlv`, `htnv10.bin`, `htnv20.bin` | 4 | Both original ROM candidate pairs retained; no active ROM claim |
| WLAN API1 executables | `lib/firmware/ath11k/QCA6390/hw2.0/amss.bin` and `m3.bin` | 2 | Stock `amss20.bin` maps to the reviewed API1 AMSS name; board data still missing from the deployment contract |
| WLAN board candidates / regulatory file | No staged destination | 0 | No arbitrary `board-2.bin` or `board.bin` choice; QCA6390's frozen table does not require separate `regdb.bin` |
| TFA9894 QS/YC containers | No staged destination | 0 | No validated matching driver/container request contract |

The original 28 `bdwlan.*` candidates, all TFA containers, unused Novatek
manufacturing/other revision variants, unused ZAP representation and redundant
MDT metadata segments remain intact in the original private archive. The stager
does not rename raw AMSS to the different `firmware-2.bin` container format.
It does not create a generic Novatek alias or change the DT's GPIO selection.

The current display DT still disables all PCIe controllers, Novatek/SPI14,
Venus and the four amplifiers. Packaging their known inputs does not enable
those consumers. DSP authentication, reserved-memory fit and service ABI also
remain separate from the verified filename/length dependencies.

## Actual Android radio-selection observations

The radio investigation used fixed metadata paths, directory-name discovery
and explicitly named non-identifying SoC properties. It did not read full
kernel/application logs, MAC addresses, network credentials or user network
configuration, and did not restart either radio or send a firmware-download
command. Reads of the selected PCI/static metadata were bounded to 750 ms.

| Observed source | Actual result | What it establishes |
| --- | --- | --- |
| PCI endpoint `0000:01:00.0` | Vendor/device `17cb:1101`, subsystem `17cb:0108`, revision `01` | PCI identity only; subsystem `0108` is not assumed to be the QMI firmware board ID |
| CNSS and PCI endpoint DT property names | No board-ID, BDF-selection or firmware-name property in the two inspected nodes | Those DT nodes did not supply a selected stock BDF |
| Fixed CNSS debug/parameter locations | `/sys/kernel/debug/cnss`, `/sys/kernel/debug/cnss_pci` and `/sys/module/cnss2/parameters` absent | No metadata was obtained from these paths; this is not a claim about every possible interface |
| PCI endpoint and `wlan0` attribute names | No firmware/board version attribute among the inspected direct entries | No additional board selector from those entries; address/statistics/control files were not read |
| `/vendor/etc/wifi/qca6390/WCNSS_qcom_cfg.ini` | 8,775 bytes, SHA256 `ceebfa9bd1226ec748ecf28c5ed5543cb184fd8a55dd34ac1611300903598b17`; no matching board/BDF/SoC/ROM selector keys | The fixed vendor driver configuration did not answer the selection question; all other contents were omitted |
| `vendor.qcom.bluetooth.soc` and `persist.vendor.qcom.bluetooth.soc` | Both `hastings` | Bluetooth SoC family property, not ROM revision |
| Explicit Bluetooth ROM/product/patch/version properties | Empty values | Neither a `10` nor `20` runtime filename branch was established |
| `/sys/class/bluetooth` | Empty | No HCI metadata was obtained there; it does not prove that Android Bluetooth is absent or unusable |
| Two fixed vendor Bluetooth configuration candidates | Absent | No static ROM selector obtained from those files |

Consequently `wlan_qmi_board_id_observed=false`,
`wlan_bdf_branch_observed=false` and `bluetooth_runtime_rom_observed=false`.
This is a bounded negative result for the checked sources. A later controlled
observation of actual QMI board metadata or Bluetooth ROM response can close
those questions; filename presence, PCI subsystem identity and the family
property cannot substitute for that evidence. Both Bluetooth pairs stay in the
tree, while WLAN board data remains deliberately unresolved.

## Execution and validation

The first read of the original host-private archive through `/src/private`
failed with `PermissionError: [Errno 13]` because of the unprivileged-container
UID mapping. The original archive's private directory and file permissions
were preserved. Its owner opened it read-only on doesvm and streamed it into a
new exclusive `0600` file in `/work/stock-fw-stage-v1`; the container checked its
exact 15,747,897-byte size and pinned SHA256 before accepting the copy.
All subsequent staging and validation ran inside that container.

| Recorded job | Exit | Result |
| --- | ---: | --- |
| `input-copy` | 0 | Verified private container input copy; original unchanged |
| `stage-elf` | 0 | 69-file canonical tree; 71 independent file checks including metadata |
| `stage-mdt` | 0 | 70-file canonical tree; 72 independent file checks including metadata |
| `stage-boundaries` | 0 | Seven expected rejection cases and two independent GNU checksum checks passed |

[`test_stock_firmware.py`](../../../scripts/research/test_stock_firmware.py)
uses new private altered-input fixtures and verifies rejection of a changed
archive, changed capture evidence, changed kernel contract, source-file symlink,
existing output prefix, parent traversal and output-parent symlink. It confirms
that rejected operations created no package and that the original source and
completed output manifests remained unchanged. `sha256sum --check --quiet`
independently passed for both completed prefixes after those checks.
Expected rejection exits are retained as boundary-test results, not hidden
build failures or hardware tests.

All four synchronous jobs have ended. No background radio, transfer or staging
process was launched by this step. The private work directory retains the
verified input, both output trees, altered test fixtures, logs and command/exit
records. Public Git content contains scripts and metadata only.

## Reuse in later image assembly

For a new explicit staging attempt, select a fresh output prefix:

```sh
python3 -B /src/scripts/research/stage_stock_firmware.py \
  --archive /work/stock-fw-stage-v1/source-stock-firmware.tar.gz \
  --output /work/stock-fw-stage-v1/canonical-elf-NEW \
  --zap-format elf --novatek-variants dt-both-6
```

Use `--zap-format mdt` only when deliberately choosing the split ZAP form.
Existing prefixes are refused. The helper does not execute an installation
command. A rootfs/initramfs builder can consume the chosen prefix's
`lib/firmware` directory, retain its exact manifest, and check each recorded
destination after copying. That later image's own evidence must record its
kernel/DT/module identities and whether early consumers actually receive the
files. Generic QEMU and filesystem-copy results remain separate from physical
firmware authentication, device operation and whole-tablet acceptance.
