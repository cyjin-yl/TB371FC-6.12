# Shipping Android kernel: tracepoint helper and CNSS cache audit

The exact owner kernel **does contain the normal tracepoint dispatch for
legacy `BPF_FUNC_probe_read` (helper 4)**. This is now established from the
owner's original Image, including the program-type table, static relocations,
helper switch and implementation. The earlier `CONFIG_KPROBES=n` finding
therefore does not rule out normal tracepoint BPF.

The same Image establishes the CNSS global pointer and several cached scalar
offsets. It also exposes a material limit: the optional QMI response's validity
bits are **not retained by the audited cache writes**, and the BDF name is
built on the download function's stack. A cached `board_id`, particularly
`0xff`, cannot by itself prove a valid board-info TLV or the historical
filename requested. No program was loaded, no probe attached, and no live
kernel memory read. Dynamic work remains on hold.

The complete result is
[`evidence/cnss-shipping-static.json`](evidence/cnss-shipping-static.json).
The separate
[`android-tracepoint-capabilities.json`](evidence/android-tracepoint-capabilities.json)
records only metadata of the existing fork tracepoint interface on Android.
Neither file is an owner Linux hardware pass.

## Exact input and reproducibility

The ordinary private input is the uncompressed kernel member previously
retained from `recovery_a.img`, matching the owner `boot_a` kernel member in
the frozen [boot-header inspection](evidence/boot-header-inspection.json):

| Input | Identity |
| --- | --- |
| Owner release associated with the backup | `4.19.157-perf+` |
| Image size | 37,445,648 bytes |
| Image SHA-256 | `ef9e7b5cdb9ef3c66977a04d6b6e21cf83e83f2f45476390c861827d1bb1cf0f` |
| Decoded compressed symbols | 121,415 |
| Checked name-block markers | 475 |

Every marker and the exact compressed-name stream end were checked. All
selected symbol names, including `plat_env`, occur exactly once. The decoder
retains duplicate occurrences internally and rejects a duplicate selected
name; it does not silently choose the last one.

The Image has static pointer slots whose file contents can be zero before
relocation. Selected `R_AARCH64_RELATIVE` addends resolve those links. The
static ELF addend base is used only inside the inspection process and is not
published or treated as a live address/KASLR slide.

The version-specific helper
[`inspect_cnss_shipping.py`](../../../scripts/research/radio/inspect_cnss_shipping.py)
accepts only an ordinary file with the exact size and full hash above. It
performs no device, sysfs, memory-device, BPF, perf or module operation and has
no arbitrary-address or arbitrary-offset argument. Its fixed instruction
checks corroborate a manually reviewed control-flow interpretation; this is
not whole-program formal verification.

```sh
python3 -B /src/scripts/research/radio/inspect_cnss_shipping.py \
  --image /work/tfa9894-static-20261123/owner-Image
```

The actual run used the dedicated SSD container, a new
`/work/cnss-shipping-audit-20261123` prefix and tmux pane
`tb371fc-ssd:cnss-static:%33`. It exited **0 in 2.789 seconds**, starting at
`2026-11-23T03:52:08.333653+00:00`.

| Reproduction record | SHA-256 |
| --- | --- |
| Inspector source | `72972b0d83bf44e0ee46ac0141d7bf77057234095e1b369d9e09241f38b1d916` |
| Actual JSON output log, 17,965 bytes | `91194b21b511507b02de955645809d3284609112bab06ca3ce6aab9520f2974b` |
| Completed job record | `3fe703653e5e7b2619aafa4071cf17a1416c94aae5d5aebdc5846f74cc2b0f5e` |

The earlier public tem423
[`4.19.325` source](https://github.com/tem423/android_kernel_lenovo_tb371fc/tree/9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1)
remains a comparison clue. Its expanded BPF helper enums and implementation
are not substituted for the owner's `4.19.157` binary layout.

## Normal tracepoint support, separately from kprobes

The owner metadata-only capture at
`2026-11-23T03:36:41.643157+00:00` found the regular, mode-`0444` file:

```text
/sys/kernel/tracing/events/sched/sched_process_fork/id
```

The numeric ID was not read, the event was not enabled, and no child process
was created to trigger it. This finding complements the earlier
[six-flag audit](radio-probe-capabilities.md): `BPF_SYSCALL`, `BPF_EVENTS`,
`BPF_JIT` and `PERF_EVENTS` are compiled, while `KPROBES` is disabled and the
kprobe event-source interface is absent. A normal tracepoint is a different
attachment mechanism.

All code offsets below are relative to this Image's `_text`, not live
addresses.

| Verified link | Actual shipping evidence |
| --- | --- |
| Program type 5 → tracepoint verifier operations | `bpf_verifier_ops[5]` has a static RELATIVE relocation to `tracepoint_verifier_ops`; relocation record at file offset 32,200,880 |
| Verifier operations → helper lookup | Its first pointer relocates to `tp_prog_func_proto`, relative offset `0x1617d8` |
| Helper 4 → common lookup | Helper 4 misses the tracepoint-specific 25/67/27 cases and follows the call at `0x16181c` to `tracing_func_proto` |
| Common lookup → exact prototype | Table byte at `0x16dd2e8 + (4 - 1)` is `0x10`; destination `0x162cdc` returns `bpf_probe_read_proto` |
| Prototype → implementation | Prototype at `0x16dd4a0` relocates to `bpf_probe_read`, relative offset `0x160b50` |
| Read and failure behavior | Implementation calls `probe_kernel_read`; on a negative result it calls `memset` to clear the destination before returning the error |

The 40-byte prototype has `gpl_only=1`, `pkt_access=0`, return-type value 0,
and argument-type values `6, 8, 10, 0, 0`. These match the historical
[`v4.19` argument enum](https://github.com/torvalds/linux/blob/v4.19/include/linux/bpf.h):
uninitialized destination memory, constant size or zero, and an initialized
source argument. That public header was separately fetched and hashed
(`9f3d2582c427725a02387926cd239fff5e038cd5fb24cc4c8e1ec3b2aded1e77`);
the table and implementation linkage come from the actual owner bytes.

This proves compiled dispatch availability. It does not prove that a proposed
program passes the owner verifier, that its loading or perf attachment is
permitted, or that JIT execution is active at runtime.

## CNSS pointer and field mapping

`cnss_get_plat_priv` directly loads `plat_env`. The slot is at relative
`_text + 0x24624f8`, beyond the Image's file-backed byte range, in BSS. The
offline file therefore cannot supply its live value.

The audited `cnss_probe` publishes its managed allocation into that slot.
An error path and `cnss_remove` clear it. The getter itself provides no
reference acquisition or synchronization for an unrelated tracepoint reader.
Knowing the offset does not supply a verified live address or a lifetime pin.

The existing `cnss_get_soc_info` follows its device's private-data pointer
(`device + 0xb8`) and then the PCI-private backpointer (`private + 8`) before
copying the platform cache. Its null-pointer checks are not QMI-validity checks.
The getter's loads and target-capability writer's stores independently agree
on the following fields:

| Platform-cache displacement | Width | Interpretation in the reviewed functions |
| --- | --- | --- |
| `0x6b0` | 32 bits | Chip ID; filename logic tests bit 4 |
| `0x6b4` | 32 bits | Chip family |
| `0x6b8` | 32 bits | Cached board ID, including the `0xff` fallback |
| `0x6bc` | 32 bits | SoC ID |
| `0x6c0` | 32 bits | Firmware version |

These are Android CNSS offsets for this one Image. They are not ath11k
structure offsets, generic SM8250 constants or evidence that these values
were read on the running tablet.

## The validity flags are transient

In `cnss_wlfw_tgt_cap_send_sync`, after a successful QMI result:

1. The temporary response byte at `+0x4` controls whether the chip ID and
   family are copied to the platform cache.
2. The response byte at `+0x10` controls the board ID. If true, the response
   word at `+0x14` is copied to cache `+0x6b8`; if false, `0xff` is stored
   instead.
3. The temporary request and response are freed before return. The audited
   path copies the scalar values, not those two validity bytes.

No persistent equivalent of either optional-field validity bit was proved.
A cached `0xff` can therefore represent the explicit missing-board-info
fallback; it must not automatically be labeled a valid QMI board identifier.
An unchanged chip field likewise does not prove a newly received valid TLV.

The event worker sets `driver_state` bit 1 **before** calling the capability
exchange, and can then leave through its error path. That state bit is not a
successful-capability or optional-TLV-validity flag. A later ready state is
also a different concept; this audit does not replace the absent validity
record with an unrelated state bit.

## What selects the filename in this shipping binary

The download function receives the BDF type. The reviewed event worker first
requests type 4, then reads the configured type at platform offset `0x1364`
for the subsequent request. For the BIN/ELF branches, the static format
patterns are:

| Cached board ID | Chip-ID bit 4 | BIN type 0 basename pattern | ELF type 1 basename pattern |
| --- | --- | --- | --- |
| `0xff` | Clear | `bdwlan.bin` | `bdwlan.elf` |
| `0xff` | Set | `bdwlang.bin` | `bdwlang.elf` |
| `0x00`–`0xfe` | Clear | `bdwlan.b%02x` | `bdwlan.e%02x` |
| `0x00`–`0xfe` | Set | `bdwlang.b%02x` | `bdwlang.e%02x` |
| Greater than `0xff` | Either | `bdwlan%02x.b%02x` | `bdwlan%02x.e%02x` |

The last row uses `(board_id >> 8) & 0xff` and `board_id & 0xff`; it does not
encode an unrestricted 32-bit ID. These are reviewed format rules, not an
observed filename or a choice among the retained owner candidate files.

`cnss_bus_add_fw_prefix_name` delegates to the PCI implementation. A cached
boolean at platform offset `0x12e2` controls prefixing. When enabled, PCI
device ID `0x1101` uses `qca6390/%s`, and `0x1103` uses `qca6490/%s`; the
other branch uses `%s`. The shipping `snprintf`/`scnprintf` calls use a
20-byte bound, so the format table must not be treated as an unbounded path
constructor.

The basename is in the download function's stack frame at `sp + 0x30`; the
prefixed request name is at `sp + 0x1c`. The latter is passed directly to
`request_firmware` and to the diagnostic log. Firmware is later released.
The reviewed path does not preserve a selected filename in the audited
platform cache.

Even a future successful snapshot of all current selection inputs would
therefore be an inference about the deterministic selection logic. It would
not be a direct record of the past request, successful QMI download, firmware
acceptance, or radio operation. No `board-2.bin` was manufactured, and the
private 28-file BDF candidate pool and canonical firmware staging remain
unchanged.

## Held design, with no dynamic implementation

A future narrowly scoped tracepoint experiment would need a separately
reviewed live-address and lifetime/synchronization contract for the exact
shipping image. It would attach only to the collector's own TID, with
inheritance disabled, and trigger only an owned short-lived child. An
additional PID/TID check, fixed scalar allowlist, one bounded result map,
finite deadline, and unconditional FD closure/child reaping would limit its
scope. It would publish status and allowed scalars, not pointers, arbitrary
memory, strings, process names, MAC addresses or network names.

That design is not implemented by the offline helper. No BPF map/program or
perf event was created, no event was enabled, no probe or module was attached,
and no trace instance, sysctl, policy or radio setting was changed. In
particular, no QMI transaction or radio restart was used to regenerate the
missing selection history.

The current gate remains incomplete: helper dispatch and fixed field offsets
are verified, while a live lifetime contract, actual load/attachment behavior,
original optional-field validity and historical request identity are not.
This finding narrows the remaining evidence problem without claiming a
wireless or owner Linux pass.
