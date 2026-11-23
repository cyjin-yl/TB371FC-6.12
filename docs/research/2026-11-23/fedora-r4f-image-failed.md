# Fedora R4F: the first host image attempt timed out before any VM

The first R4F/V9 pipeline failed while copying the prepared root filesystem into
a new ext4 image. Its fixed `mkfs.ext4` subprocess deadline was 600 seconds. The
original exception, phase records, source manifest and partial image are
retained. **No VM ran in this attempt.** This result neither tests the new
SELinux permission at runtime nor changes the earlier R4E/V8 failure.

This report records the original attempt. A recovery must use a separate output
prefix and report its own source, timeout and results; it must not rewrite this
failure as a successful image build.

## Actual execution

The command ran inside the standard HDD builder `tb371fc-build-20261123`, under
the unique unit `tb371fc-r4f-full-01.service` (invocation
`67c43daba4bf43418f4b954fc102beaa`). Its work directory is
`/work/fedora-input-system-v9`; the materialized recipe is
`/work/fedora-input-system-recipe-r4-v7`.

| Phase | Exit | Elapsed seconds | Result |
| --- | ---: | ---: | --- |
| `stage-01` | 0 | 24.509 | R4 kernel, modules, firmware and profile staged |
| `configure-01` | 0 | 31.025 | Independent R4F root configured |
| `initramfs-01` | 0 | 477.185 | Both archives built and verified |
| `image-01` | 1 | 615.382 | `mkfs.ext4` exceeded its 600-second deadline |
| Label / production VM | — | — | Not started |
| Udev post-qualification / finalizer | — | — | Not started |

The pipeline ran from `2026-11-23T09:05:18.111872+00:00` to
`2026-11-23T09:24:26.788163+00:00`, exited 1 after 1,148.676 seconds, and recorded
no cancellation signal. The image log contains `subprocess.TimeoutExpired` for
the exact command below:

```text
/usr/sbin/mkfs.ext4 -F -L tb371fc-r4f-f45 \
  -E lazy_itable_init=0,lazy_journal_init=0 \
  -d /work/fedora-input-system-v9/rootfs \
  /work/fedora-input-system-v9/fedora45-research4f-persistent-result.ext4
```

The exception says `timed out after 600 seconds`. The total phase time includes
process cleanup and recording; it does not imply a different configured limit.
The last progress message was `Copying files into the device`. An independent
Nix store operation was also reading and writing this HDD. That concurrency is
relevant resource context, not proof that it was the exclusive cause of the
timeout. There was no kernel panic, guest SELinux result or device failure in
this attempt because no guest started.

## Inputs already qualified before the timeout

The original 20-file execution manifest is
`927fd0755f54f303adac25daa8342bfe4615d0d42ff9a07361d29226f7cdf947`.
The profile manifest is
`5fb332d61e8e5b9b1699021aba8a5b2658a2763c7897d656692e5a49ddc107e0`.
All 20 executed source files were reread and matched by the failure collector.
The earlier source and baseline records are retained in
[fedora-r4f-execution-source.json](evidence/fedora-r4f-execution-source.json)
and [fedora-r4f-baseline-preparation.json](evidence/fedora-r4f-baseline-preparation.json).

The successful archive records identify these ordinary files in the prepared
root's `boot` directory:

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| Production `initramfs-6.12.114-tb371fc-research4-system.img` | 32,532,312 | `8533dcc827613d332d4869167351d50acf4694c27b52dcc6cf144ef7268503f6` |
| Maintenance `initramfs-6.12.114-tb371fc-research4-system-maintenance.img` | 30,709,930 | `721af9be1c6c23b5b6dc1778c48c447eb197d1a7ec0a8d7f83a0e113815e33dd` |

Both records have `archive_verified=true`. The collector preserves their exact
metadata and validation results; it does not claim a new archive payload hash
calculation. A recovery must check the actual reused archive bytes again.

The active release remains `6.12.114-tb371fc-research4-system`, with the already
qualified R4 kernel and 84 modules. The new source policy is the independently
qualified seven-permission candidate, 3,835,468 bytes with SHA-256
`ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798`.
V4 early init is 72,528 bytes with SHA-256
`0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14`.
Those remain construction evidence. No actual loaded policy was exported from
this attempt. Its 82-query live contract, three-descriptor transfer, TasksMax,
BPF open-denial, journal sync and zero-AVC/loss gates were not run.

## What is retained

The primary immutable record is
[fedora-r4f-image-failed.json](evidence/fedora-r4f-image-failed.json),
321,928 bytes, SHA-256
`79390c4bf78de7f806cbc26109faf8df870fea3d7cce5b3ffb3db7e99b5806e9`.
It binds 25 original JSON/log members, including the full image traceback,
pipeline, four phase records and all selected preparation metadata. The
collector source is
[`freeze_r4f_image_failed_attempt.py`](../../../scripts/research/input/system-integration/freeze_r4f_image_failed_attempt.py).
Its executed SHA-256 is
`633b9e41dba98d7faafb9fd60c9d37cf27bb321b2f25bf1d4f186f99964a4f35`.

The private 26-member evidence packet is 39,892 bytes, SHA-256
`4711cef262c1c769efe23701646982d2fda6e881b28147a0d524932b942f48ce`.
It contains metadata and logs, not the image, firmware, policy binary or keys.
Every member was transferred and checked byte for byte locally. Original log
control characters have not been normalized.

The partial image remains at its original path. Its apparent size is 4 GiB;
this is not a complete-filesystem qualification. The collector only used
`lstat` on it: no payload hash, mount, journal replay, repair or boot occurred.
`image.before-boot.json` and all later VM/qualification/finalizer paths were
absent when collected. The original prepared root, successful archives and
failed image remain separate evidence inputs for an explicit recovery.

This is **host-build failure evidence**. Owner-tablet Linux boots and physical
hardware acceptance remain zero for this attempt.
