# Retained R5 second-stage DTB candidate and source

The earlier CT102 run produced a separate **offline RAM-declaration candidate**
from the frozen R5 mainline DTB. This publication recovers its exact source,
receipt, successful tests, and first failed test attempt from
`/work/r5-stage2-dtb-auto01`. It does not regenerate that candidate or repeat
the historical test execution. The new PR workflow checks source/evidence
identity and runs synthetic fixtures separately.

The candidate remains blocked for physical use. It neither chooses load
addresses nor establishes the ownership of memory used by firmware, a loader,
or active DMA. No native Linux hardware pass is added.

## Exact retained inputs and result

The complete metadata and all file identities are in
[`evidence/r5-second-stage-dtb/index.json`](evidence/r5-second-stage-dtb/index.json).
The original receipt is retained without alteration as
[`receipt.json`](evidence/r5-second-stage-dtb/receipt.json).

| Item | Bytes | SHA-256 |
| --- | ---: | --- |
| Frozen R5 `board.dtb` | 126,877 | `af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730` |
| Candidate reported by the original receipt | 126,893 | `7092d992582a2f49b65e8eb1a4209fede3b41ccbbacb3abc28d29b649b33423c` |
| Original candidate receipt | 49,765 | `5d1f6141efbd89f5197cc91c429c0aaba1a3a39fe992f5579884023726ed8d14` |
| Original derivation source | 8,488 | `b397f68b753e04d386e6deedeec63685477559fbc55c499cbf70eb9535cafec0` |
| Final original test source | 4,838 | `ff11e1bde4ab0a06e2a776e48c4158872fc3c17c066f9b263c9a3ce3094d8460` |

The retained receipt identifies `fdtput` as DTC 1.7.2, executable SHA-256
`bf17d680f6b098ad92f9f2a509ca1827eb60c5ba5106fa0e26488023595c4f01`.
The DTB binaries were not fetched or published in this publication step;
their identities above are taken from the original receipt. A separate raw
generation-command exit receipt was not present in the recovered file set.
The historical test exit files are present and preserved.

The already published owner metadata remains exactly
[`native-dt/live-android.json`](evidence/native-dt/live-android.json), SHA-256
`e071f91b43a063ff6f96cb401269469e20703ab695e64dd37a1d5b86113ba745`.
It describes the stable two-read Android FDT snapshot with SHA-256
`5114262a0dea5ef82b53db69b3d489ddbe57040e1a50b57365e87a28d2946207`.
That original Android FDT required forensic padding handling and retains
`format_compliant=false`; the new candidate is still parsed strictly.
See [the native-DT investigation](native-dt-selection.md) for that distinction.

## What the derivation permits

[`derive_second_stage_dtb.py`](../../../scripts/research/derive_second_stage_dtb.py)
accepts only the pinned R5 DTB and pinned owner observation. It copies the DTB
to a temporary file, uses `fdtput` to replace `/memory@80000000/reg`, and reads
the result through both existing strict parsers. It compares every node and
property before and after, preserves the board compatible strings
`lenovo,tb371fc` and `qcom,sm8250`, and requires unchanged header reservation
metadata and reserved-memory declarations. The output directory must be new.

The sole permitted semantic property change replaces the zero-size RAM
placeholder with these observed declarations:

| Start, inclusive | End, exclusive | Bytes |
| --- | --- | ---: |
| `0x80000000` | `0xbbb00000` | 1,001,390,080 |
| `0xc0000000` | `0x280000000` | 7,516,192,768 |

These are declarations from the existing Android boot, not approved free
space for a subsequent kernel or boot loader. The empty
`mainline_memory_map_issues` list in the receipt describes only that parser's
local structural checks; it does not override the explicit runtime and
physical-boot blocking flags.

The report compares all **19 mainline reserved-memory declarations** with
the **35 Android declarations** in both directions. Nineteen pairs have
identical nonempty `reg` geometry. This is not proof of equivalent purpose,
ownership, lifetime, or permitted access. Twelve Android dynamic requests
have no resolved allocation in this observation. Four other declarations
have no identical mainline geometry: `res_xbl_uefi_log_region`,
`disp_rdump_region`, `dfps_data_region`, and the zero-size
`boot_log_region` placeholder. This count does not imply four additional
positive-size physical allocations.

The later [Android RAM accounting](android-memory-topology.md) adds an
aggregate CMA-size match and a bounded resource-tree observation. It still
resolves zero individual dynamic allocations and does not select load
addresses. This retained candidate continues to use its original pinned
observation and does not silently absorb newer evidence.

## Retained test history and current CI

The original final [`tests.log`](evidence/r5-second-stage-dtb/tests.log) records
10 tests passing; [`tests.exit`](evidence/r5-second-stage-dtb/tests.exit)
contains `0`. The first attempt remains recorded in
[`tests-attempt01.log`](evidence/r5-second-stage-dtb/tests-attempt01.log), its
exit file (`1`), and its exact test source. Its added-property fixture used
`"test"`, whose NUL-terminated length was five bytes. That mutation exposed
nonzero property padding, which the strict parser rejected before the
expected property-inventory check.

The final fixture uses `"abc"`, whose NUL-terminated length is four bytes,
and removes an unused import. The production parser and derivation source
were not weakened. Both the initial failure and final successful test
source are bound by the index's size and SHA-256 entries.

The publication workflow runs the same synthetic contract tests on a new
CI runner. It does not have the private R5 binary and cannot recreate or
claim a new real candidate build. A passing publication workflow establishes
the checkout's synthetic behavior and retained-file identities only.

## Remaining physical-entry conditions

The original receipt continues to block physical use until individual
dynamic reservations and mainline/owner differences are explained, firmware
and loader exclusions are established, a checked physical load layout is
selected, DMA is quiescent, and entry plus recovery are verified. This
publication does not flash, reboot, call `kexec`, change the frozen R5
artifacts, or modify the first-stage Android recovery DT.
