# Explicit memblock page tables for the isolated TB371FC simulator

## Observed failure

The retained R5 second-stage attempt 04 passed the final device-tree, Image,
initramfs and layout checks and issued QEMU `cont`. Its first kernel failure
was:

```text
[    0.000000] Kernel panic - not syncing: TB371FC embedded early page-table pool exhausted
```

The call chain reached `early_pgtable_alloc`, `create_kpti_ng_temp_pgd`,
`__map_memblock`, `map_mem`, `paging_init` and `setup_arch`. The kernel never
reached userspace in this observation. The launcher and its QEMU process were
reaped and their ownership was resolved. Exit code 3 describes the completed
simulator observation; it is not a successful Linux boot.

Evidence retained on the build host:

| Item | SHA-256 |
|---|---|
| `attempt-04/result.json`, 83,796 bytes | `89a6b602d520efba2bec73a2c049a6e94e5155a777d929af0b7b94bf5929646b` |
| Attempt 04 serial output, 1,406 bytes | `201c0a6836bec013d9c99484ebb5812a5c2a04a9ffbafabc15a1ebc4bfa52d29` |
| Retained R6 `arch/arm64/mm/mmu.c`, 44,729 bytes | `b03413247434f6c2abd500036e2aca226f49156ebb726949c25f3a925ab1ca44` |

The result is under
`/tank/shared/projects/tb371fc-linux/.git/continuation-406f-stage2/attempt-04`.
The exact allocator source is under
`/tank/hot/tb371fc-build-20261123/tianma-r6-build-ec332-01/linux`.
The R6 source qualification permits only the panel repair relative to the
retained R5 source; this allocator is inherited unchanged.

## Why it exhausts the pool

The inherited board workaround reserves 256 page-table pages inside the
kernel image. With the retained 4 KiB configuration this is a 1 MiB pool.
Patch 0017 already limits that workaround to the flattened root compatible
`lenovo,tb371fc`; generic QEMU `virt` uses the normal memblock allocator.

The board simulator intentionally preserves the native compatible. It thus
selects the embedded pool even though its bootstrap does not inherit a
running vendor kernel or vendor DMA state.

The retained configuration enables `CONFIG_RODATA_FULL_DEFAULT_ENABLED`.
`can_set_direct_map()` therefore causes `map_mem()` to set both
`NO_BLOCK_MAPPINGS` and `NO_CONT_MAPPINGS`. At 4 KiB granularity, one PTE-table
page maps 2 MiB. The observed model RAM includes the contiguous 7 GiB high
bank `[0xc0000000, 0x280000000)`, while the retained reserved regions are
below that bank. The high bank alone needs 3,584 PTE-table pages, before
counting the lower bank or intermediate tables. The pool's 256-page limit
cannot cover this mapping.

`create_kpti_ng_temp_pgd` in the stack is an alias of
`__create_pgd_mapping_locked` in this source. The symbol name does not show
that a separate KPTI mapping or a KPTI defect caused the panic.

## Change and scope

Patch 0023 adds the explicit early option:

```text
tb371fc.early_pgtable=memblock
```

With that exact value the kernel uses the same
`memblock_phys_alloc_range(PAGE_SIZE, PAGE_SIZE, 0,
MEMBLOCK_ALLOC_NOLEAKTRACE)` path that already serves non-TB371FC machines.
An allocation failure still panics. The memblock allocator keeps the
existing memory-bank and reserved-memory accounting; the patch does not
add RAM or map carveouts.

The option is parsed before `paging_init`: the retained `setup_arch`
initializes the flattened device tree and calls `parse_early_param()` first.
On the explicit path it logs once:

```text
TB371FC early page tables: explicit memblock allocator
```

The option selects an allocator; it does not detect QEMU hardware. Only the
reviewed R7 simulator input profile should emit it. That profile must require
one exact option and reject duplicates, conflicting values and option-name
aliases before issuing `cont`. Linux's early-option parser alone does not
provide that contract: a malformed second token reports an error but does
not undo a previously accepted token.

Without the option, TB371FC retains the existing 256-page pool and its
exhaustion check. The pool remains permanent BSS because live page tables
outlive initialization. The selection flag can be `__initdata` because its
only consumer, the allocator, is `__init`. Non-TB371FC and no-FDT boots keep
their previous memblock behavior. Generic VM boot arguments are unchanged.

This resolves a simulator bootstrap mismatch without enlarging a static
pool based on an arbitrary RAM limit or disabling page-granular read-only
protection. It does not establish that the native vendor-kernel handoff is
safe. No physical boot, reboot, flash or partition action follows from this
change. SELinux, signed-module enforcement, read-only protections and
reserved-memory validation remain required.

## Reproducible validation

The test fixture is the complete retained `mmu.c`, pinned to the hash above.
The default test applies the exact patch with `patch --batch --fuzz=0`, then
requires the complete patched source hash:

```text
27cf3be8c966c1cfe84f5c3cb715aedd3c3d4a8f5ef522c5737212476dc8a0fb
```

It extracts the actual C allocator and option parser from that source and
compiles them with host stubs. It does not reimplement the allocator in
Python. `--kernel-source` performs the same check directly against the
newly prepared kernel tree during construction.

```sh
python3 -B scripts/research/system-kernel/research7-rpmh-clock/test_early_pgtable.py -v
python3 -B scripts/research/system-kernel/research7-rpmh-clock/test_early_pgtable.py \
  --kernel-source /work/FRESH-CANDIDATE/linux -v
```

Eight tests exercise 16 compiled-C cases: native default selection and its
257th-allocation panic; non-board and no-FDT behavior; 5,000 explicit
memblock allocations with no embedded-pool consumption; missing and seven
invalid values; allocation failure on all three memblock paths; and the
duplicate-parser behavior that the launcher must reject. Both fixture and
actual-source modes passed locally, including invocation with Python `-O`.
The C assertions remain active because the harness is compiled without
`NDEBUG`.

These checks validate source identity, selection and failure handling.
A fresh complete kernel/module build, generic VM verification and a new
board-simulator observation are still required to prove runtime progress.
They add no native hardware passes.
