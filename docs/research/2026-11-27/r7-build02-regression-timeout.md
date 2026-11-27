# R7 build 02: actual-source regression exceeded its enclosing deadline

## Observed result

The second R7 construction used published source
`0712f053a4518a3a3512d053763d584283fb3d4b` and the unchanged original admission
wrapper. It obtained a slot at 2026-11-27 11:43:58 UTC (19:43:58 Asia/Shanghai).
The container worker started at 11:44:42 UTC. All three exact toolchain probes,
the complete retained-source comparison, the fresh source copy and the pinned
MMU patch succeeded. The patched candidate's only additional source delta was
`arch/arm64/mm/mmu.c`.

The next command, `actual-early-pgtable-regression`, began at
11:47:52.041667 UTC and hit its 120-second enclosing deadline at
11:49:52.735770 UTC. Its complete log was zero bytes. The owned command was
terminated and reaped with exit code -15. No subsequent core regression,
Kconfig, kernel compilation or module construction ran.

The worker, host and driver retained failure receipts at 11:50:01,
11:50:04 and 11:50:05 UTC respectively. Worker cleanup completed with no
surviving descendants; the host verified the worker was absent and container
ownership was resolved. The three successor observers stopped on the failed
predecessor. This attempt did not execute a guest or add a native pass.

| Exact retained evidence | Bytes | SHA-256 |
| --- | ---: | --- |
| `build-result.json` | 6204 | `14e372086eca20aef1fd766f3debe225f4a018d600c5008523b56a96178889d2` |
| Outer `execution.log` | 21426 | `023be7364cf17d600dc9bc9f31c36e79888a71560cd27cc851ddb2675e8a7ee5` |
| `actual-early-pgtable-regression.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| Actual patched-source inventory | 17407164 | `95ad54b6a39a61d113931159ee63fc445e9bee946b3443243497c80f91310622` |

The immutable work directory is
`/tank/hot/tb371fc-build-20261123/r7-rpmh-clock-406f-02`.
The host controls are under
`/tank/shared/projects/tb371fc-linux/.git/continuation-406f-stage2/r7-control-406f-02`.
A compact source-backed summary is in
[`evidence/r7-build02/observation.json`](evidence/r7-build02/observation.json).

## What the empty log establishes

The old harness performs source verification and host C compilation in
`setUpClass`, before unittest emits its test-result markers. Compilation uses
captured output and a 90-second inner timeout. Its 16 actual C invocations each
permit 10 seconds. Their permitted budgets already total 250 seconds before
Python startup, source preparation and cleanup, while the enclosing builder
allowed only 120 seconds.

The same attempt's successful `clang --version` command took 51.395 seconds.
Slow process/tool startup is therefore observed in this environment. However,
the blank regression log does not identify its exact stalled step and does
not demonstrate a failed C assertion or a compiler diagnostic. The original
timeout remains a failed attempt; no allocator pass is inferred from it.

## Reviewed correction

The harness now emits flushed structured start/completion records for source
validation, compilation and each C case, including elapsed time and bounded
stderr on errors. Compilation permits 300 seconds and each of the same 16
cases permits 30 seconds, totaling 780 seconds for those subprocess calls.
The builder's separate 1200-second enclosing deadline leaves 420 seconds for
startup and preparation. The fixture-only patch call remains bounded at 30
seconds and is not invoked by the actual-source build path.

The C preamble, extracted allocator/parser, harness assertions, MMU source
identities, eight test methods and sixteen cases are retained. This is a
runtime-budget and diagnostic correction, not a change to the kernel patch
or its pass conditions. The builder retains its owned-process cleanup; the
host still holds admission until container ownership is resolved. The original
five-slot wrapper, `MAKEFLAGS=-j2`, 10800-second builder limit and 11000-second
host limit are unchanged.

A reviewed new source revision and fresh build/control/output namespace are
required for the next attempt. Build 02 and its source/output/receipts remain
preserved. Rootfs construction, generic VM verification and board-QEMU
observation still require actual successful predecessor receipts. Neither this
report nor local harness validation establishes an R7 kernel or boot pass.
