# R4C / v6: tmpfs migration works; complete system verification still fails

**Result: the production VM failed its unchanged verification gates.** This
candidate successfully migrated the initramfs to an ordinary tmpfs, reaped the
old-root cleanup process, loaded the original policy with Enforcing active,
and executed systemd. An independent same-boot probe observed PID 1 in
`init_t` and udevd in `udev_t`. Those are new runtime results. They do not make
the complete system acceptable: the full log contains SELinux denials, and
the real system-bus `--wait --pipe` control failed before the TasksMax and BPF
behavior probes could execute.

The immutable machine record is
[evidence/fedora-r4c-tmpfs-failed.json](evidence/fedora-r4c-tmpfs-failed.json),
84,480 bytes, SHA-256
`8575cb6378d8df7636b6155af38715c773c70e938c168c62416d2cd5eb8b2e2a`.
This is a generic ARM64 VM result, with no network, host filesystem share,
physical-device passthrough or Lenovo board DT passed to QEMU. It adds **zero
owner-tablet Linux boots and zero hardware acceptance passes**.

## Independent candidate and reproducible source

The work directory is `/work/fedora-input-system-v6` in the standard HDD
Docker builder `tb371fc-build-20261123` on CT102. The active release remains
`6.12.114-tb371fc-research4-system`. The frozen R4 Image, matching 84-module
set, 69 owner firmware files and joint display/input DT are staged without
changing the R4 kernel build or any previous system candidate.

The executed 16-file recipe is
`/work/fedora-input-system-recipe-r4-v4`; its manifest is 2,136 bytes with
SHA-256 `ae47f2919847fc311e5f6fba5b2f89c8da1d66615207fcb699e308bf725e7fa7`.
The repository contains its full profile under
`scripts/research/input/system-integration/profiles/tmpfs-early-selinux-v6`,
including the materializer and exact parent/supplemental source identities.
The profile-source manifest SHA-256 is
`e2a3a926296f624f562f76186f13dc4dd319fbd6e49dc73050cfb677bb7a1951`.
The [execution source map](evidence/fedora-r4c-execution-source.json) records
the correspondence between all actual files and the public source paths.

The new HDD copy independently passed the native quiescent-copy check. Its
canonical source and destination streams were both 1,323,141,120 bytes with
SHA-256 `1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96`.
The prior [copy-race failure](selinux-query-copy-followup.md) remains failed;
no source timestamp was reset. No PRoot command was run against the original
R1 source tree by this profile. Target commands use this separate candidate.

## Actual phases and retained artifacts

| Phase | Actual result | Controller duration |
|---|---:|---:|
| Checked runtime staging | Exit 0 | 3.51 s |
| Independent system configuration | Exit 0 | 5.02 s |
| Maintenance and production archive creation/checks | Exit 0 | 242.11 s |
| New ordinary ext4 image creation | Exit 0 | 50.06 s |
| Maintenance labeling VM | Exit 0 | 163.07 s |
| Production Enforcing VM | **Exit 1** | 138.54 s |
| Separate full-log udev qualification | **Exit 1** | Original VM failure retained |
| Successful-system finalizer | Not run | Prerequisite failed |

The maintenance QEMU lifetime was 162.27 seconds and ended with a clean
poweroff. Its separate archive uses the original systemd entry and explicit
`enforcing=0` only for labeling the new ext4 image. It does not use the
production tmpfs bootstrap. The production QEMU lifetime was 137.17 seconds.
The controller observed the guest's failure marker, retained the diagnostics,
and terminated/reaped its own QEMU child. QEMU's exit code was 0; the
controller correctly returned 1. A clean production poweroff is not claimed.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Kernel Image | See frozen R4 build | `8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb` |
| Maintenance initramfs | 30,709,650 | `02a825056b4cee63e4aa85734d66872bb03e5e6e1b5638ee9418c0e2e1795db5` |
| Production initramfs | 32,484,273 | `cf89e286c60b5d9faa2798b746a7f6664e166919e1b0f7bb6ef2d6df01a99616` |
| Exact system profile | Recorded in machine report | `828f106e45b497503b3d1205afaf61d20be4bf0c63cf5c0ea21f12fcc86dd544` |
| Failed ext4 image after owned QEMU exited | 4,294,967,296 | `0dfcc822c8bf27c8f3c5f68aac3d0a73b0018ea16ca4e9745f9a54189f96e57a` |

The retained image is
`/work/fedora-input-system-v6/fedora45-research4c-tmpfs-early-selinux.ext4`.
It was neither repaired nor reclassified as a successful candidate while
freezing this report. Earlier R3, first-R4, copy-race and v5 failures remain
separate, with their original recipes and logs.

## Archive qualification and the new runtime result

The production archive passed the fixed tmpfs-policy checker
`92f02fd33fcc5f7aaea6d1d0e06c04589af024b09e8f678f772798909c2ebb07`.
It imports the fixed prior early-policy parser and verifies the immutable R1
baseline with the original checker. It checks the exact stage0 script,
stage1 ELF, standard Fedora `switch_root`, original native `/init`, saved
systemd link, command dependencies, complete top-level copy contract and
hardlink boundaries. The actual archive contains the fixed 34 policy/config/
context files, all 69 firmware payloads, 139 ARM64 non-firmware ELF files and
the independently derived 39-library cache map. The target ARM `ldconfig`
listing is compared with the fixed payloads; a self-reported cache hash alone
is not sufficient. PRoot's original dracut/ldconfig warning is retained;
the later external ARM ldconfig and repacked-archive checks are explicit.

The [full archive record](evidence/fedora-r4c-tmpfs-initramfs-validation.json)
is 122,983 bytes, SHA-256
`26d8f3cb59761e6c8f33b4611c2c283dfe5dba1bfd87c37b2ff7cf940bb621d0`.
The [proof payload record](evidence/fedora-r4c-tmpfs-initrd-proof-payloads.json)
also verifies the exact script, service and activation link.

Unlike the [v5 failure](fedora-r4b-early-failed.md), this actual production log
contains the following ordered milestones:

```text
TB371FC_TMPFS_STAGE0_V1 COPY_COMPLETE old_dev=0:2 new_dev=0:20 policy_load_attempted=0
TB371FC_TMPFS_STAGE1_V1 CLEANUP_COMPLETE old_dev=0:2 new_dev=0:20 cleanup_children=1 old_root_empty=1 policy_load_attempted=0
TB371FC_EARLY_SELINUX_V1 POLICY_LOADED enforcing=1 context=system_u:system_r:kernel_t:s0
TB371FC_EARLY_SELINUX_V1 EXEC_SYSTEMD enforcing=1 flags=0x828c
```

The original native `/init` is still the 72,048-byte `e53cf407…` artifact.
It reads back `init_exec_t` on the systemd executable and `udev_exec_t` on
the actual udevadm target before execution. The subsequent independent
same-boot probe records:

| Runtime observation | Actual value |
|---|---|
| PID 1 process context | `system_u:system_r:init_t:s0` |
| udevd process context | `system_u:system_r:udev_t:s0-s0:c0.c1023` |
| `/proc/1/mountinfo` root filesystem/source | `tmpfs` / `tb371fc-initroot` |
| Actual root device | `0:20`, matching both migration markers |
| Root mount options | `rw,relatime` |
| Root superblock options | `rw,seclabel,size=196608k,mode=755` |
| Explicit production entry | Unique `rdinit=/init.tmpfs` and tmpfs/early-policy opt-ins |

The new mount is distinct from the old `0:2` root, and the observed root has
no `nosuid` or `noexec` flag. These results qualify this particular migration
and process-domain sequence, not all labels on separately mounted API
filesystems. The independent [bootstrap source/build report](tmpfs-initramfs-bootstrap.md)
remains a separate, narrower record.

The original controller's `tmpfs_migration_proof.passed` remains **false**:
that aggregate gate also compares with the final guest result, which this
failed run never produced. The raw markers and independent initrd record
above are retained partial observations; the original aggregate result is
not rewritten into a pass.

## Actual SELinux failures

The unchanged host gate reports 83 denial records. A separate full-log scan
finds 83 distinct visible audit identifiers; repeated log presentation is not
counted as a new kernel event. This is an observed-log count, not a claim that
the log inventories every possible audit event: the raw log explicitly
reports suppressed audit callbacks. Representative failures are:

| Point | Actual denial |
|---|---|
| Early systemd, about 10.01 s | `init_t` mapping `policy.35`, labeled `semanage_store_t`, denied `file map` |
| Initrd generators and services | `/dev/null` on devtmpfs still labeled `device_t`; several service domains denied read/write/getattr |
| Initrd journald | `syslogd_t` denied access to `kmsg` labeled `device_t` |
| Initrd journal file | `syslogd_t` mapping a file labeled `syslogd_tmpfs_t`, denied `file map` |
| Actual FD-bearing system-bus call, about 132.12 s | PID 1 in `init_t` denied `fifo_file write` to the observed stdout pipe labeled `initrc_t` |

The native root-tree relabel uses `XDEV` and does not itself traverse a
separately mounted devtmpfs. Correct root process domains therefore cannot
be substituted for correct `/dev` labels. The systemd policy reload and API
filesystem-label initialization chain needs its own source-supported repair.
This report does not claim that an isolated `/dev` relabel would fix the
policy-file or journal-map failures. No policy allowance, suppressed denial,
permissive production boot or ignored error was introduced.

## Real system-bus progress and the exact stopping gate

The root-side validator actually ran as `initrc_t`. The real broker child
was found by process/parent identity and observed as `system_dbusd_t`; the
broker child had 22 open descriptors and an actual 16,384-descriptor limit.
The validator read the active exported policy: version 33, 3,835,420 bytes,
SHA-256 `9c79cb12810a781d6cb91f9b7dff160a1d768c534b784743b4256015799f22a8`.
All 15 user-space AV computations returned successfully. They allowed the
actual `initrc_t` FD/FIFO access and retained the existing
`unconfined_service_t` FIFO restriction. This uses the actual exported bytes,
not an assumed equivalence to an offline conversion of policy version 35.

The actual runtime-hash checkpoint matched 84 modules and 69 firmware files.
Both the broker `GetId` and the systemd manager `Version` round-trip succeeded
over the system bus. While the `--wait --pipe` child was held, the creator and
the two actual FIFO inode labels were all `initrc_t`; the inherited stdin
inode was observed as `null_device_t` at this later root-side point.

The unrestricted `/usr/bin/true` control nevertheless returned exit 1:

```text
error-name=org.freedesktop.DBus.Error.InconsistentMessage
error-message=Failed to set unit properties: Bad message
```

The real manager received `StartTransientUnit` and sent that error reply.
The preceding raw lines identify a further real permission boundary:

```text
avc: denied { write } ... pid=1 comm="systemd" path="pipe:[7512]"
scontext=system_u:system_r:init_t:s0
tcontext=system_u:system_r:initrc_t:s0 tclass=fifo_file permissive=0
Received a bus message with MSG_CTRUNC set with 1 fds received vs. 3 declared.
```

The denied inode `7512` is the same stdout pipe held and recorded by the
validator. This places the observed rejection at the manager's receiving
end, followed by truncated ancillary FD delivery and the property error.
It differs from the earlier broker peer reset. The successful broker-side
AV computations do not cover PID 1's FIFO permission and cannot establish
that the entire FD forwarding path is allowed. This is a failed FD-bearing
operation, despite the successful ordinary broker/manager round-trips.
The system bus was not replaced by the manager's private socket. Diagnostics
and a sync completed before the failure marker was emitted.

Because this baseline failed, **neither the TasksMax/EAGAIN probe nor the
controlled BPF filesystem denial ran**. No successful final guest record,
successful-system marker or completed module-enforcement behavior test is
claimed. The R4 compile-time and offline module-signature evidence remain
valid at their original scope; they do not fill these runtime gaps.

## Udev handoff boundary and raw evidence

The separate [full-log qualifier](evidence/fedora-r4c-tmpfs-udev-qualification.json)
matched the closed raw log to its controller identity. It found no matching
storage, push, receive, insertion or lost-FD error prefix, but it also found
no positive serialized/restored count pair and no root-side accepted
serialization-FD line. Absence of count lines does not prove the queue was
empty. The qualifier returned **exit 1** because the original complete VM
result failed; its conditional no-error observation is not a full-system pass
or an independent inventory of every original queued event.

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| [Maintenance raw log](evidence/fedora-r4c-tmpfs-failed-label.log) | 1,086,822 | `4c468f1872e15bbd394f96700fa54567bbba2da14c603dbf3133109e367e71c7` |
| [Production raw log](evidence/fedora-r4c-tmpfs-failed-verify.log) | 1,313,223 | `e7e5f620a6a7cfe2bb989ddd4ae881b2a988a598d8296a8b2b2af26c3f5ca0b2` |
| [Original production controller result](evidence/fedora-r4c-tmpfs-failed-verify.json) | 37,927 | `0e7cd2f14a30f860529810062b4ce240adfc6a5a10dbd67b45cc3d62015447de` |
| [Read-only udev qualification](evidence/fedora-r4c-tmpfs-udev-qualification.json) | 2,132 | `247f4162361cd001ae77ef24a122d165563eb947c4f638f285884562347db39a` |

Raw CR/LF bytes are preserved. The independent failure-freeze source is
`scripts/research/input/system-integration/freeze_tmpfs_failed_attempt.py`
(5,859 bytes, SHA-256
`54a17feee9d11ef1b654acce0268e8c0bbac6b6a1955f3dbf8f1791004720ed8`).
It records a completed failed run and hashes the closed image; it neither
repairs filesystems nor rewrites the original controller result. A later
candidate must execute the full original gates again. Physical panel, touch,
pen/charging, keyboard, radios, audio, camera, power and Android-parity
acceptance remain separate and unpassed.
