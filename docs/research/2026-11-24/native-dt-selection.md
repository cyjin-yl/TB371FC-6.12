# Owner DT selection observations and native-entry memory inputs

Date: **2026-11-24, Asia/Shanghai**. This work reads the owner's existing boot
backups and running Android FDT. It adds no owner-native Linux run or hardware
pass: the ledger remains **44 cases, 12 blocked, 32 not run, zero passes**.

The first-stage reconstruction already exists. The missing input addressed here
was its relationship to the actual DTB bundle, DTBO table, reported selections
and runtime memory declarations. A whole-component hash alone did not show
which trees the container held or what a new loader still needed to supply.

## Actual owner observations

At **02:23:24 UTC**, the running `4.19.157-perf+` Android kernel supplied a
973,052-byte FDT with 4,276 nodes. Two reads matched exactly. The corresponding
Android properties and allowlisted command-line fields independently reported:

| Field | Property | Command line |
| --- | --- | --- |
| Slot | `_a` | `_a` |
| DTB index | `0` | `0` |
| DTBO indices | `[2]` | `[2]` |

The capture omits raw command lines, identifiers, arbitrary DT properties and
firmware bytes. The live FDT SHA-256 is
`5114262a0dea5ef82b53db69b3d489ddbe57040e1a50b57365e87a28d2946207`.
These are reported Android observations. They do not demonstrate a future
bootloader accepting another kernel or replay its exact selection algorithm.

## The backed-up container is now resolved into its component trees

The compressed backup was copied into a new private CT102 work directory and
verified against its existing exact archive identity. The inspector then checked
the original member set, each inspected partition's complete bytes and hash,
and the archive again after processing. Original backup permissions and bytes
were unchanged.

All four boot/recovery DTB components contain **four concatenated FDTs**:

| Index | Description | `boot_a` bytes | Other three bytes |
| --- | --- | ---: | ---: |
| 0 | kona v2.1 base | 538,388 | 538,620 |
| 1 | kona v2 base | 538,616 | 538,616 |
| 2 | kona v1 base | 531,698 | 531,698 |
| 3 | Small tree without a board model or root IDs | 173 | 173 |

The A-slot base at reported index 0 has SHA-256
`9ded79854f0db23503b3592417c1e5cd61d98d84cab8dc5e213d3a9b868c7019`.
Its SoC ID `[356, 131073]` matches the live tree; its board ID `[0, 0]`
and generic model do not equal the final live board identity.

Both recovery-DTBO components and the table portion of both DTBO partitions
contain the same **14-entry AOSP v0 table**, 4,299,963 bytes, SHA-256
`279910628e61cad149ccdb16ae0aa0a3a2f46441e21132ac3a1323e565219679`.
Partition tails are recorded separately as opaque bytes; their presence does
not validate AVB signatures or rollback compatibility.

Reported DTBO index 2 is the 502,232-byte kona QRD tree, SHA-256
`696cbe86a0ce5683edbad9bb330e909dcc44f33aa8e242933afd19d9177cdfc1`.
Its board ID `[11, 0]`, model and compatible list match the corresponding live
metadata. No missing SoC ID is invented for this overlay. The correlation tool
keeps base identity and overlay identity separate.

## Independent libfdt checks establish what offline composition supplies

The separate [libfdt verifier](../../../scripts/research/verify_native_dt_libfdt.py)
does not import either project DT parser. It independently verifies the frozen
archive and two partition hashes, extracts base 0 and overlay 2, and uses the
container's existing `fdtget` and `fdtoverlay` from **DTC 1.7.2**.

The final actual run completed at **02:35:27 UTC**, exit 0:

- **136 tool commands** retained with executable identities, arguments, exit
  codes and private stdout/stderr hashes.
- **63 same-input field comparisons** matched the project inspector: root
  identities, cell counts, memory declarations and eight selected reserve nodes.
- `fdtoverlay` successfully composed base 0 plus overlay 2 offline.
- The composed result still differed from live Android in **compatible, model,
  Qualcomm root IDs and `/memory/reg`**. These differences remain in the report.

In particular, ordinary offline overlay application leaves the base root's
generic identity and zero-sized RAM placeholder. It does not recreate all
runtime modifications made somewhere in the actual boot chain. The next native
entry must supply and verify its own exact final tree, root identity, RAM and
reservation contract. Successful offline composition cannot substitute for it.

The earlier successful libfdt run is retained under its original source hash.
An independent review then tightened the public JSON comparison to distinguish
boolean/float values from integer indices; the final exact source was executed
again. No earlier receipt was relabeled as the new code.

## Memory declarations are inputs, not a free-memory map

The backed-up base has `/memory/reg = <0 0 0 0>`. The live Android tree has:

| Start | End, exclusive | Declared bytes |
| --- | --- | ---: |
| `0x80000000` | `0xbbb00000` | 1,001,390,080 |
| `0xc0000000` | `0x280000000` | 7,516,192,768 |

The live tree describes **35 reserved-memory nodes: 23 static and 12 dynamic**.
Their allowlisted metadata matches the selected base tree's declarations. The
static ranges form seven union intervals totaling 305,332,224 bytes. The
continuous-splash and display-dump declarations overlap by 8 MiB at
`0x9c000000`; this is recorded rather than silently discarded.

Dynamic allocations, secure-firmware ownership, loader buffers, active DMA and
runtime reuse remain separate. The seven static intervals cannot establish a
complete exclusion map, and subtracting them from RAM cannot prove a safe kernel
load address. The Android initrd addresses are observed metadata for this boot,
not automatically chosen addresses for the new R5 loader.

The later [bounded Android memory observation](android-memory-topology.md)
binds this exact FDT to a stable live resource tree. It accounts for all declared
RAM except a 128-KiB unnamed gap after static `no-map` exclusions, and finds an
exact aggregate match between eleven reusable dynamic requests, `CmaTotal` and
one reserved resource range. Individual dynamic allocation boundaries/owners,
safe load addresses and DMA quiescence remain unverified.

## Keep strict artifacts separate from live forensic interpretation

The first live read failed strict FDT parsing. A more precise second diagnostic
localized nonzero property-alignment padding. The final bounded capture records
two issues: offsets **821109** and **821537**, each a three-byte padding region
containing one nonzero byte. It emits only these numeric counts/offsets.

The explicit live-only forensic option returns `format_compliant=false`.
All structure, extent, token, duplicate-property and memory-type checks remain
enabled. Concatenated artifact and DT-table readers retain their strict default;
no padding bytes are edited, normalized or promoted to accepted new artifacts.
The strict failures and the intervening disconnected read are preserved.

## Tools, tests and reproducibility

The new tools are standard-library Python except for the explicitly independent
libfdt command-line check:

- [native_dt.py](../../../scripts/research/native_dt.py): bounded FDT, exact
  concatenations, AOSP table v0/v1, bounded compression and memory metadata.
- [inspect_native_dt_backup.py](../../../scripts/research/inspect_native_dt_backup.py):
  exact frozen owner backup and per-partition verification.
- [collect_native_dt.py](../../../scripts/research/collect_native_dt.py): bounded
  Android observation with explicit live-forensic mode and no device writes.
- [correlate_native_dt.py](../../../scripts/research/correlate_native_dt.py):
  type-sensitive, duplicate-aware slot/index correlation and memory differences.

**51 regressions pass under `python3 -O`**, including malformed extents,
compression budgets, ambiguous/duplicate/invalid indices, overlapping ranges,
private-field omission and strict-versus-forensic padding behavior. The exact
public correlation record is reproducible byte for byte. These tests exercise
parsing and provenance; they are not additional Android or Linux hardware runs.

```sh
python3 scripts/research/inspect_native_dt_backup.py \
  --archive "$PRIVATE_BACKUP/current-boot.tar.gz" \
  --reference docs/research/2026-11-23/evidence/boot-backup-off-device.json \
  --output "$NEW_PUBLIC_REPORT"

python3 scripts/research/correlate_native_dt.py \
  --backup docs/research/2026-11-24/evidence/native-dt/backup-final.json \
  --live docs/research/2026-11-24/evidence/native-dt/live-android.json \
  --output "$NEW_CORRELATION_REPORT"
```

The metadata correlation result is `reported_indices_consistent`; its actual
ABL replay, per-byte runtime selection, native load-layout and physical-boot
fields all remain false.

## Evidence and next implementation boundary

- [Final backup metadata](evidence/native-dt/backup-final.json)
- [Live Android metadata](evidence/native-dt/live-android.json)
- [Reported-index correlation](evidence/native-dt/correlation.json)
- [Independent libfdt result](evidence/native-dt/libfdt-final.json)
- [Exact execution command and source](evidence/native-dt/libfdt-final-execution.json)
- [All retained file identities and attempt scopes](evidence/native-dt/index.json)

Private original/merged DTs and raw tool outputs remain in new CT102 directories
`/work/native-dt-inspection-20261124-0217` and
`/work/native-dt-libfdt-20261124-01` / `-02`. They are not published.

Linux, QEMU and UniXNU can now consume the same exact selection observations and
memory declarations. Each consumer must explicitly implement its missing loader
changes and record a separate runtime test. The mainline second-stage tree must
retain its intended `lenovo,tb371fc` compatibility; this downstream first-stage
QRD tree does not replace it. Native boot/recovery, DMA quiescence, safe load
addresses and the 44 hardware cases remain unqualified.

Primary references:
[AOSP DTB images](https://source.android.com/docs/core/architecture/bootloader/dtb-images),
[AOSP DTB/DTBO tables](https://source.android.com/docs/core/architecture/dto/partitions),
[DTSpec flattened format](https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html),
and [Linux 6.12 ARM64 boot protocol](https://www.kernel.org/doc/html/v6.12/arch/arm64/booting.html).
