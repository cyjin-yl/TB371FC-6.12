# Owner WLAN cached version and the remaining board-data selector

A previously unexamined, bounded sysfs read has obtained actual cached WLAN
firmware and BDF descriptor fields from this owner's Android system. It still
does **not** establish the CNSS QMI board ID or which `bdwlan.*` file was
selected. The [new evidence](evidence/android-radio-version.json) records the
exact discovery, both reads, allowlisted fields, source references and capture
programs. This supplements the [canonical staging report](stock-firmware-staging.md)
and the [earlier retained-buffer observation](evidence/android-radio-boot-selection.json).

## Actual observation

The final capture was taken at `2026-11-23T03:00:01.500875+00:00` while the
owner remained on `4.19.157-perf+`. Names-only discovery followed the actual
`wifi/wlan/fw/1` hierarchy beneath `/sys/kernel`; it did not guess a numeric
psoc ID. Only the final `version` attribute's value was read. The nearby
`driver_version` name was observed but its value was not read.

| Field | Observed value |
| --- | --- |
| Exact attribute | `/sys/kernel/wifi/wlan/fw/1/version` |
| Value length / SHA256 | 123 bytes / `d154227c68f046413ffbd2a9f5e7f27abc1a7fee8fc37065922568b3454867e5` |
| Cached firmware version | `1.0.1.0.1596.0` |
| BDF version | `0x8` |
| Reference design ID | `0x0` |
| Customer ID | `0x0` |
| Project ID | `0x0` |
| Board-data revision | `0x1` |
| QMI board ID / selected stock filename | Not observed |

Every operation had a one-second deadline; file values were capped at 4 KiB.
The first read's strict whole-line parser did not match the shipping output.
That failure is retained. A second parser extracted only the five explicitly
named numeric BDF fields and dotted numeric firmware version. Both 123-byte
reads had the same hash; their recorded read durations were about 0.25 ms
and 0.49 ms. These durations describe acquisition only, not radio performance.
Unmatched text, including any unmatched hardware-name field, was omitted.

No power/beacon attribute, raw log, register/MMIO interface, traffic counter,
MAC address, SSID or user network configuration was read. The collector made
no radio restart, configuration write, log clear, firmware request or explicit
QMI call. These action flags describe the collector and the reviewed public
getter; the shipping driver was not instrumented or proved byte-equivalent.

## Source contract and its limits

The source was already pinned and acquired for the independent first-stage
experiment: [`tem423/android_kernel_lenovo_tb371fc` at
`9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1`](https://github.com/tem423/android_kernel_lenovo_tb371fc/tree/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1).
It is a public 4.19.325 source clue, not an exact source identification of
this owner's shipping 4.19.157 binary.

| Source file | Relevant behavior | SHA256 |
| --- | --- | --- |
| `drivers/staging/qcacld-3.0/core/hdd/src/wlan_hdd_sysfs.c` | `__show_fw_version()` formats cached `hdd_context` version and `hw_bd_info` fields. `show_fw_version()` adds context/synchronization guards. The default root is `wifi`; `MULTI_IF_NAME` can change it. | `16d6cfc6cd250eb6b5aa989b1dcc2e71024265239c1758002115c382830ea995` |
| `drivers/net/wireless/cnss2/qmi.c` | `cnss_wlfw_tgt_cap_send_sync()` caches QMI board information; `cnss_get_bdf_file_name()` selects the name; `cnss_wlfw_bdf_dnld_send_sync()` requests it. | `3facb40945088a385ef2281d7eed529da5fd975c042278d3ea506a98b70ef64b` |
| `drivers/net/wireless/cnss2/pci.c` | `cnss_get_soc_info()` copies cached board information to kernel callers. `cnss_pci_add_fw_prefix_name()` conditionally adds the QCA6390 directory. | `4ca227532ffa5df9381f1816381947e9df71a1baa53bf4b75cd02005d2dcfd60` |
| `drivers/net/wireless/cnss2/debug.c` | The inspected `control_params` read exposes `bdf_type`, without the selected filename or cached board ID. CNSS debugfs creation depends on the debug configuration. | `61674fbf5bab8ba5e2e16ab1e1fbcb5d68ac10c34ff1bfce38484a1630f65b32` |

The inspected sysfs show path formats cached fields; it does not issue a
QMI transaction or read device registers. Its five BDF descriptors are not
`cnss_plat_data.board_info.board_id`. The latter is populated from a valid
QMI target-capability response, with `0xff` used as a fallback when that
response lacks valid board information. It is not the PCI subsystem ID.

For the non-GF ELF branch, `0xff` chooses `bdwlan.elf`, smaller IDs choose
`bdwlan.e%02x`, and larger IDs use `bdwlan%02x.e%02x` from the high/low bytes.
The GF chip-mask branch can choose `bdwlang` names, the BIN branch uses other
suffixes, and an independently selected prefix can add `qca6390/`. Knowing
that a candidate file exists therefore does not identify the active branch.
The observed version/customer/project/revision fields also do not prove a
unique match among the 28 privately retained board-data candidates.

The same source sends target-capability and chosen-filename diagnostics to
CNSS logging, but no additional log source was opened in this task. Finding
format strings in a saved kernel/module binary could corroborate that a
branch was compiled; it cannot recover the runtime response value from that
disk file. The earlier 2,269-byte retained kernel buffer had no selection
tokens, which is a bounded negative result, not proof of a missing load.

## Effect on the firmware and acceptance records

This closes one metadata-discovery gap: the existing Android cached version
interface was present and supplied five BDF descriptors. No more general
claim that passive evidence had been exhausted, or that a reboot was
necessarily required to obtain any additional information, is justified.

The active QMI board ID and selected stock filename remain unresolved. A
future exact cached-board-ID interface or a separately controlled observation
of the actual capability/filename selection could provide the missing evidence.
No such action was performed here. The five descriptor fields must not be
renamed to `board_id`, and none of the captured `bdwlan.*` files is promoted
to `board-2.bin` or `board.bin` by this result. Mainline ath11k's board-key and
API contracts remain the ones recorded in the
[frozen firmware request audit](firmware-kernel-contract.md).

The new JSON embeds both capture programs and their SHA256 hashes, with the
failed initial parser and successful named-field extraction preserved. They
use standard-library Python, fixed metadata discovery, bounded reads and no
user-supplied commands. No raw version line or firmware payload is published.
This is `device_android` baseline evidence, with source interpretation kept
explicit; Linux radio operation and every owner hardware pass remain untested.
