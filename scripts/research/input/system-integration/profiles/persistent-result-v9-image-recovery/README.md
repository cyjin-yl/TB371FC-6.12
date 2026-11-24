# Independent image recovery for the frozen R4F runtime

This is a host construction recovery for the first R4F/V9 attempt. The original
`/work/fedora-input-system-v9` pipeline failed in `mkfs.ext4 -d` after its fixed
600-second timeout, before any VM. Its original recipe, three successful
preparation phases, failed image and logs remain unchanged. See
[`fedora-r4f-image-failed.md`](../../../../../../docs/research/2026-11-23/fedora-r4f-image-failed.md).

Preparation and execution use separate new prefixes:

| Purpose | Path / identity |
| --- | --- |
| Native preparation recipe | `/work/fedora-r4f-recovery-preparation-v1` |
| Prepared root copy and all new results | `/work/fedora-input-system-v9-recovery-01` |
| Execution recipe | `/work/fedora-r4f-recovery-recipe-v1` |
| New ordinary image | `/work/fedora-input-system-v9-recovery-01/fedora45-research4f-recovery-01.ext4` |
| Original retained failure | SHA-256 `79390c4bf78de7f806cbc26109faf8df870fea3d7cce5b3ffb3db7e99b5806e9` |
| Original executed recipe | SHA-256 `927fd0755f54f303adac25daa8342bfe4615d0d42ff9a07361d29226f7cdf947` |

## Prepared-root qualification

`preparation/copy_prepared_root.py` uses the already prepared R4F root as its
read-only source. Native `cp -a --reflink=auto` preserves numeric ownership,
links, modes, ACLs and xattrs. Whether this filesystem actually uses a reflink
is left unknown. A successful copy alone is insufficient: canonical GNU tar
streams must match, the source's complete metadata inventory must remain
stable excluding read-atime changes, and both journal ACL values must match
byte for byte. The copied production and maintenance archive payloads and the
installed guest validation sources are checked against their original full
hashes.

The original metadata records are preserved in `prepared-predecessor-records`.
Only the two active archive records receive a new host path plus explicit
reuse provenance. Their payload, validator and validation result remain the
same. The initial R1 baseline-copy qualification is retained as lineage; a
separate fixed prepared-copy qualification is mandatory before any recovery
phase can execute. No PRoot command is run on the old prepared root.

The preparation wrapper owns only its new child session. Copy timeout is
1,800 seconds, each canonical stream timeout is 1,200 seconds, and the outer
preparation deadline is 4,800 seconds. Errors, warnings, mismatched streams,
source changes and partial outputs are retained as failures. No image, guest
or policy load is part of preparation.

## Execution boundary

The new pipeline starts at `image`, attempt **2**. It does not rerun `stage`,
`configure` or `initramfs`. It creates a fresh 4 GiB image with a **1,800-second
mkfs limit** and retains the existing filesystem check. The new pipeline's
outer deadline is 5,400 seconds. These host resource limits are independent of
the unchanged VM security and result gates.

The guest runtime profile, R4 Image and 84 modules, 69 firmware files, policy
`ff65a5f…`, V4 loader, two qualified initramfs payloads and all guest test code
are unchanged. The new common host helper fixes the actual prepared-copy
qualification hash and independently checks the original kernel bundle and
build report. Host boot verification and result extraction retain their
original bytes. Only the output prefix, prepared-copy guard, image timeout,
attempt selection, udev qualification output prefix and final provenance
change.

The label and production runs are `vm-label-02` and `vm-verify-02`. All existing
gates remain required: actual early process domains and labels, the real
system-bus/three-FD route and 82 exact AV tuples, task-limit behavior, matched
BPF baseline/open-EPERM behavior, successful journal sync, actual module
signature enforcement, zero visible AVC and audit-loss signals, the closed
ordinary result-file protocol, normal QEMU exit and complete udev handoff
qualification. No result from the original unstarted VM is carried forward.

The finalizer operates on the **new** prepared-root copy, including its
bounded PRoot RPM identity query. It never executes a guest program in the
original R1 or R4F root. The old partial image is never repaired or reused.

At the preparation-source freeze on 2026-11-23, the source packet was staged
and read back successfully; heavy copying and execution were waiting for the
other owned HDD store job to finish. That statement is a preparation-time
status, not a later VM result. Actual qualification and execution records must
be linked separately when produced. No tablet boot or physical hardware pass
can follow from this generic-VM recovery alone.
