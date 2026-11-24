# Owner Android RAM resource and CPU topology observation

The owner tablet was observed under its existing Android `4.19.157-perf+`
kernel at **2026-11-24 09:58:25 UTC**. This closes the previously missing
resource-tree and usable-memory baseline for part of **SYS-04**, and narrows
the DT's unresolved dynamic reservations to two aggregate geometry matches.
It does not establish their individual runtime ownership or a safe second-stage
load layout. **The native-Linux ledger remains 44 cases, 12 blocked, 32 not
run and zero passes.**

## Actual bounded execution

The collector ran from standard-library Python modules loaded in memory through
the existing root Python entry. It created no source file or bytecode cache on
the tablet. The observation completed between `09:58:25.727828` and
`09:58:25.739591` UTC, with process exit 0. These are collector timestamps, not
a throughput measurement or the complete RPC latency.

Only the fixed allowlist was read:

- `/proc/iomem` twice, at most 256 KiB per read;
- `/sys/firmware/fdt` twice, at most 16 MiB per read, retained only as size/hash;
- `/proc/meminfo`, at most 16 KiB, retaining seven memory/CMA/swap counters;
- CPU possible/present/online/offline lists and four topology fields for each
  reported CPU, bounded to 32 CPUs and 256 bytes per attribute;
- existence checks for three optional CMA/memblock interfaces, with no traversal
  or mounting of debugfs.

The complete collection had a 20-second process deadline. Unknown resource
labels and all raw FDT bytes were omitted from the published JSON. No workload,
physical-memory read, register access, module load, cgroup/SELinux change,
suspend, reset, boot-chain change or partition operation occurred.

The FDT was identical across both reads and equals the exact earlier
[native DT inspection](native-dt-selection.md): 973,052 bytes, SHA-256
`5114262a0dea5ef82b53db69b3d489ddbe57040e1a50b57365e87a28d2946207`.
The resource tree was also stable across both reads: 10,834 bytes,
347 resource entries, SHA-256
`3c288281658a748d92157c7fc849b6fe389c2a72fe18dece3ab6ad3b76e23b3c`.
The new code does not reinterpret the live FDT's previously recorded nonzero
padding as a format-compliant candidate.

## RAM geometry now has an exact accounting relationship

All intervals below are half-open. Linux `/proc/iomem` prints inclusive end
addresses; the parser explicitly converts them before calculating lengths.

| Observed or derived quantity | Bytes | Evidence meaning |
| --- | ---: | --- |
| RAM declared by the exact running FDT | 8,517,582,848 | Two declared banks; not allocator availability |
| Union of static enabled `no-map` reservations | 267,583,488 | Twenty declarations form six exclusion intervals |
| RAM left outside observed `System RAM`, after those static exclusions | 131,072 | One unnamed gap at `[0xffc00000, 0xffc20000)` |
| Actual `System RAM` resource union | 8,249,868,288 | Twelve printed resources, eight intervals after merging adjacency |
| `/proc/meminfo` `MemTotal` | 8,080,510,976 | Kernel-reported managed memory; separate from physical resource geometry |
| Resource-union bytes minus `MemTotal` | 169,357,312 | Not yet attributed to individual kernel overhead/reservation categories |

The first four quantities satisfy an exact relationship:

```text
8,517,582,848 - 267,583,488 - 131,072 = 8,249,868,288
```

No observed `System RAM` interval extends outside the two DT banks or overlaps
a static `no-map` declaration. This is a consistency result for this running
Android state, not permission to overwrite any of the ranges.

## The twelve dynamic requests are constrained, not individually resolved

The live DT has eleven enabled reusable dynamic requests with a combined
size of **364,904,448 bytes**. Two independent runtime observations have that
same aggregate size:

| Runtime observation | Actual value |
| --- | --- |
| `/proc/meminfo` `CmaTotal` | 356,352 KiB = 364,904,448 bytes |
| Unnamed `reserved` child within `System RAM` | `[0xea000000, 0xffc00000)` = 364,904,448 bytes |

This is a three-way aggregate match. It does not locate the eleven internal
boundaries or prove which individual request owns which pages. CMA ranges
remain part of managed System RAM; the `reserved` resource label is not a
measurement of current allocation or a statement that the region is available.
`CmaFree` was zero at this instant, while `MemAvailable` was 2,320,437,248 bytes;
neither counter establishes a fault or a stable capacity/performance result.

The remaining dynamic request, `/reserved-memory/mailbox_region`, asks for
128 KiB with 4 MiB alignment and a below-4-GiB allocation range. The single
unaccounted gap `[0xffc00000, 0xffc20000)` matches all three geometric
constraints. **Its ownership remains unverified**: equal size, alignment and
range do not establish that the mailbox allocation created this hole.

The three checked CMA/memblock interfaces were absent. The collector did not
mount debugfs, read arbitrary kernel memory or relax the shipping kernel's
configuration to obtain individual allocations. The machine-readable result
therefore keeps `individual_dynamic_allocations_resolved = 0`,
`complete_memory_ownership_verified = false`, and
`safe_load_addresses_selected = false`.

## CPU topology observation

CPU lists `possible`, `present` and `online` all contained **0–7**; `offline`
was empty. Each CPU's core ID, physical package ID and sibling lists are
retained in the bounded [observation](evidence/android-memory/observation.json).
This establishes eight advertised online CPUs under Android at the observation
time. No per-core execution, deterministic calculation, sustained workload,
suspend/resume or native-Linux CPU test was run.

## Implementation and reproducibility

- [android_memory.py](../../../scripts/research/android_memory.py) parses bounded
  resource trees, CPU lists and memory counters and performs interval accounting.
  Redacted `0-0` resources cannot become invented one-byte RAM ranges. Malformed,
  reversed, orphaned, overlapping sibling or out-of-parent entries are rejected.
- [collect_android_memory.py](../../../scripts/research/collect_android_memory.py)
  performs the fixed, read-only capture and retains source hashes.
- [correlate_android_memory.py](../../../scripts/research/correlate_android_memory.py)
  requires stable captures, the same kernel release and the exact inspected FDT
  size/hash before comparing geometry. It never emits safe load addresses.
- [test_android_memory.py](../../../scripts/research/test_android_memory.py)
  passed **15 tests under `python3 -O`**: inclusive ends, addresses over 4 GiB,
  resource hierarchy, privacy filtering, redaction, malformed bounds, CPU ranges,
  counter units, exact FDT binding and preservation of unresolved ownership.

The [CI workflow](../../../.github/workflows/android-memory-evidence.yml) runs
those regressions and reproduces the published correlation byte for byte:

```sh
python3 -O -m unittest discover -s scripts/research -p 'test_android_memory.py' -v
python3 -O scripts/research/correlate_android_memory.py \
  --live-dt docs/research/2026-11-24/evidence/native-dt/live-android.json \
  --memory-observation docs/research/2026-11-24/evidence/android-memory/observation.json
```

Evidence: [raw collector JSON](evidence/android-memory/observation.json),
[derived correlation](evidence/android-memory/correlation.json), and
[execution and source identities](evidence/android-memory/execution.json).
The unknown resource labels and original FDT are not included.

The next native-entry dependency is still individual reserved-memory ownership,
loader/firmware exclusions, a validated recovery channel, final layout and DMA
quiescence. This snapshot narrows the memory-accounting question without
claiming those entry prerequisites or any of the 44 hardware cases passed.
