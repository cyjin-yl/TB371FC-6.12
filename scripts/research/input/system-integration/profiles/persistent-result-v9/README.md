# R4F: native journal socket capability probe and full system verification

This is the independent V9 execution contract. At this source preparation point,
the native baseline copy is qualified and the new loader has been built. The
policy's final effective-access qualification and the actual pipeline result
remain separate prerequisites/evidence. No V9 VM result is asserted here.

The unchanged R4 kernel, 84 signed modules and 69 staged firmware files are used
in `/work/fedora-input-system-v9`. The recipe materializes only into the new
`/work/fedora-input-system-recipe-r4-v7` directory. The dedicated ext4 label is
`tb371fc-r4f-f45`, and the profile is
`research4-display-input-fedora45-v9-persistent-result`.

## Actual starting material

The native source and destination canonical streams each contain 1,323,141,120
bytes and have SHA-256
`1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96`.
Both retained journal ACL attributes match. The independent copy qualification
record is pinned to
`aea118880abaff3eee5c7aafc311f614d6c4f897308e6216e93e36c9ae964143`.
The baseline job already exited 0; it is not rerun by the system pipeline.

The actual executed baseline source, records and complete source identity are
retained separately in the R4F baseline preparation evidence. Old Fedora trees,
earlier images, executed recipes and failed results remain unchanged.

## Narrow policy and loader inputs

The source policy is the ordinary 3,835,468-byte `policy.35` from
`/work/selinux-socket-probe-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35`,
SHA-256 `ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798`.
Its independently constructed policy delta preserves the six previous explicit
permissions and adds only `journalctl_t` self `unix_dgram_socket create` for the
standard socket capability probe. Complete 35/fresh-33 policy comparisons and
effective AV decisions qualify the candidate independently. The fresh userspace
serialization is not asserted to equal the later kernel-exported policy bytes.

The new V4 native bootstrap is the actual 72,528-byte executable at
`/work/early-selinux-socket-probe-20261123/build-01/early-init`, SHA-256
`0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14`.
Its marker is `TB371FC_EARLY_SELINUX_V4`. The source changes from V3 are the
marker and the expected source-policy length; all early loading, relabeling and
explicit generic-VM-only audit observation guards remain in place.

The existing V2 waiter is retained byte for byte: 71,872 bytes, SHA-256
`7e593ef9b2c40834b97ad35b1bc21fcd54b00e34dce72381832f88329e28b3ec`,
marker `TB371FC_TMPFS_STAGE1_V2`. Its size/ELF-shape target check remains valid
because the actual V4 bootstrap is also 72,528 bytes. Its original build target
was V3. The independent V9 archive verifier binds the new V4 executable's full
hash; the waiter alone does not establish that identity. Stage0 is unchanged.

The original R1 policy, contexts, library payloads and archive remain pinned as
inputs. The candidate changes only the one source-policy file inside the copied
root. It does not change file contexts, SELinux booleans, the global default
domain, the kernel, or the signed module set.

## Complete gates preserved from V8

The materializer consumes exactly 18 profile files plus the two unchanged,
byte-pinned supplemental archive verifiers. It rejects an existing output,
changed sources and incomplete manifests. It records the immediate V8 source
manifest `f705c87a1c5efe082ae134febc139e8ce437818951c83a9709bd475d17fc60d2`
as provenance. `candidate-derivation.patch` contains the exact differences.

The maintenance archive performs offline-filesystem labeling in its own VM
phase. The production archive must then demonstrate tmpfs migration and old-root
cleanup, V4 policy loading, standard systemd policy reload and domain transition,
same-boot initrd process domains, and actual device/run/journal labels.

The production management service and all four controlled transient workers use
the existing `sysadm_t` domain. Each route retains exactly 82 live effective AV
queries against the actual exported kernel policy, checked independently as a
unique tuple set by the host. READY/GO still requires the actual worker PID,
start time, executable, arguments, cgroup, unit properties and all three pipe
directions/inodes/contexts to match while the worker is held.

The real system-bus path, held noop worker, TasksMax=3 behavior, two child
processes plus the third EAGAIN failure and pids-event growth remain required.
The BPF comparison keeps the same worker/domain/arguments. The unrestricted
case must read the actual release; the restricted case must fail specifically
at `open` with EPERM and zero data, with the actual systemd LSM attachment
evidence also present. Ordinary PL061 binding, module enforcement, autofs,
taint, BTF, all runtime hashes and absence of failed units remain required.

A successful-path `journalctl --sync` must complete before the result is sealed.
The guest writes one exclusive 0600 ordinary result file, fsyncs it and its
directory, reads it back and emits a short same-boot receipt. After QEMU has
exited and been reaped, the host uses read-only debugfs to extract the fixed
member and verifies metadata, length, hash, profile and boot ID. Transport
qualification alone never passes the system.

The full raw log must have zero visible AVCs, no audit loss/backlog errors and
no positive callback-suppression notices, including conservative notices from
other callers of the shared printk limiter. The explicitly opted-in generic VM
sets only the printk rate interval to zero before policy load and reads it back;
the burst value and audit queue semantics are unchanged. There is no audit or
Enforcing bypass.

## Results and failure retention

V8 remains overall failed. Its successful guest behavior and result transport
do not erase the sole visible AVC, and its stopped post-qualification/finalize
steps are not backfilled. V9 has a new unit, namespace, image and all output
paths. A failed required stage stops the pipeline and preserves the original
source, argv, stage/controller result, full raw bytes and any independently
qualified guest result. Any supplementary inspection produces a new record.

Read-only extraction after a forced VM termination may fail to see the latest
committed inode without journal replay. That remains a failed extraction, not
permission to mount or repair the failed image or to rescore the original run.
The full failure-retention procedure is in `failure-retention-plan.md`.

All of this is a generic ARM64 VM integration experiment. It does not use the
Lenovo DT as the QEMU machine, pass through owner hardware or establish any
owner-tablet Linux boot, GPU/input function, or whole-device acceptance.
