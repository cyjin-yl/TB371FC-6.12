# Board-model attempt 04: first executed kernel and early page-table failure

Date: **2026-11-27, Asia/Shanghai**. Exact execution timestamps below are UTC.

The retained R5 board-model experiment passed the paused load gate, issued
QMP `cont`, and produced the real Linux early console. The first runtime
failure is a kernel panic in the TB371FC embedded page-table allocator:

```text
Kernel panic - not syncing: TB371FC embedded early page-table pool exhausted
```

This is an observed boot failure after successful input and load validation.
It is not a userspace, full boot, UFS, or physical-tablet acceptance result.

## Exact experiment and retained evidence

The [complete serial log](evidence/attempt04/serial.log) retains all 1,406
original bytes, including CRLF endings. The
[public observation summary](evidence/attempt04/observation.json) records
selected values from the full retained result, identifies that original
result by SHA-256, and distinguishes this run from the separately qualified
newer QEMU artifact.

| Item | Observed identity or result |
| --- | --- |
| Linux launch sources | `aa7795fc8d35518df297239cfe270f0962fc3c97` |
| Kernel release | `6.12.114-tb371fc-research5-services` |
| QEMU source actually executed | `d46f660a464e850b94ed483a5f823a11196dfd49` |
| QEMU binary SHA-256 | `e97b5500bf534c51ac9e7e91bdd1df403dea44b822438a21311f731b9b43efcc` |
| Launcher start / completion | `2026-11-27T10:35:37.156361+00:00` / `2026-11-27T10:36:24.429559+00:00` |
| Bounded observation | 45 seconds, then paused diagnostics and owned cleanup |
| Paused layout gate / `cont` | Passed / issued |
| Complete loaded Image and initramfs | Rehashed and matched their frozen inputs |
| Input stability after observation | Passed; root disk used `snapshot=on` |
| Controller errors | None |
| Kernel runtime verdict | Fatal panic detected; launcher exit 3 |
| Cleanup | QMP quit requested, QEMU returned 0, child reaped, no cleanup errors |
| Full retained result | 83,796 bytes; SHA-256 `89a6b602d520efba2bec73a2c049a6e94e5155a777d929af0b7b94bf5929646b` |
| Complete serial log | 1,406 bytes; SHA-256 `201c0a6836bec013d9c99484ebb5812a5c2a04a9ffbafabc15a1ebc4bfa52d29` |

The original result's `status=simulated_layout_verified` describes the load
gate. Its `exit_code=3` and `runtime_observation.fatal_detected=true` preserve
the later kernel failure. Both `userspace_verified` and
`boot_completed_verified` remain false. A normal QEMU exit records successful
host cleanup; it does not turn the panic into a boot pass.

## Failure location and interpretation

The early console reaches the Linux banner, machine model, and enabled
`qcom_geni0` boot console before panicking in `early_pgtable_alloc`. The
retained call chain then names `create_kpti_ng_temp_pgd`, `__map_memblock`,
`map_mem`, `paging_init`, `setup_arch`, and `start_kernel`.

In the retained kernel source, `create_kpti_ng_temp_pgd` is an alias of
`__create_pgd_mapping_locked`. That symbol in the backtrace does not establish
a separate KPTI failure or an extra temporary page-table allocation. The
failing allocation occurs while building the linear memory mapping.
The inspected retained `arch/arm64/mm/mmu.c` is 44,729 bytes with SHA-256
`b03413247434f6c2abd500036e2aca226f49156ebb726949c25f3a925ab1ca44`.

The board-specific allocator contains only 256 embedded pages. With the
candidate's 4 KiB granule this is 1 MiB of page-table storage. When
`can_set_direct_map()` is true, `map_mem()` disables block and contiguous
mappings and needs a PTE page for each mapped 2 MiB span, plus the upper-level
tables. The model's high RAM bank alone spans 7 GiB, from `0xc0000000` to
`0x280000000`; a page-level mapping of that bank needs 3,584 leaf-table pages.
The complete model RAM and lower-bank reservations are retained in the
observation summary. This arithmetic explains why the small embedded pool
cannot cover the simulated memory map under page-level mapping. It is not a
measurement of the exact number of successful allocations before the panic.

The diagnostic UFS link remained down and the root disk had no I/O. The
kernel had not reached UFS initialization, so these observations do not
identify a UFS-model or root-filesystem failure. Reference RPMh/AOP/SMEM
firmware is also later than this early mapping failure.

## Follow-up scope

The follow-up in PR #22 introduces the explicit early option
`tb371fc.early_pgtable=memblock` for the simulated R7 entry. The
native-compatible default retains the embedded pool and its existing handoff
behavior. The R7 second-stage input contract must require one exact option
and reject duplicates or conflicting values. The generic `virt` control
remains outside the TB371FC compatibility branch.

The observed failure justifies testing a memblock-backed allocation mode
against the model's already validated RAM layout. It does not demonstrate
that memblock allocation is safe during a physical tablet's vendor-kernel
handoff. A rebuilt kernel and a new retained guest run must establish whether
the model gets beyond `paging_init`; source checks alone do not establish
that result.

## Separately completed QEMU artifact qualification

The newer QEMU artifact completed host-side acquisition and qualification
before attempt 04 finished. It was **not** the binary used for attempt 04.
Its qualifier covered the 116 required CI gates and 17 producer cases, and
its acquisition worker exited 0 with its child reaped and process group gone.
The qualification job did not run a guest.

| Item | Qualified identity |
| --- | --- |
| QEMU source | `6287cd9a41e5114de6cf3a4ac38b0fd85872ee06` |
| CI run | [45920669404](https://github.com/cyjin-yl/qemu-tb371fc/actions/runs/45920669404) |
| CI artifact | `15165425834` |
| QEMU binary | 64,083,920 bytes; SHA-256 `c087daf03d581ddc542dad1414080e7db44a8a1c16486ecd0a26cc9292a1e560` |
| Qualification receipt | 1,636,059 bytes; SHA-256 `ac35d17e57bf29b1c564ac5c9b5cb2283ba6267add4567ecb4aa61824145897e` |
| Acquisition completion | `2026-11-27T10:32:38.281515+00:00` |

The newer artifact and the explicit reference-firmware profile provide the
next board-model input. Their qualification does not certify a Linux boot.
No tablet reboot, flash, partition change, or native pass is recorded by
these experiments. The native ledger remains **44 total: 12 blocked, 32 not
run, 0 native passes**.
