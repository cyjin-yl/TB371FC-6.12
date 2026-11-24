# V3 early SELinux loader with an explicit generic-VM audit observation path

## Actual construction result

The new AArch64 loader compiled successfully in the existing SSD build
container: **exit 0 in 1.562511 seconds**. The executable is **72,528 bytes**,
SHA-256
`84cc4868317fd1799ab1ff8f8ba5ae8bf85445dda5d65c3f11e1637aadb599c3`.
Its HDD copy has the same complete hash, length and `0755` mode. A direct
QEMU-user invocation subsequently exited 1 at the non-PID1 entry guard,
before the audit observation path, mounts or policy loading.

These are construction and entry-refusal results. This report records no
successful PID 1 execution, policy load, VM boot, audit-sysctl update or owner
tablet test. The separate complete-system experiment must establish those
runtime results. The previously frozen V1 and V2 sources, executables and
reports remain unchanged.

The exact native records are retained as ordinary JSON files:

| Record | Bytes | SHA-256 |
| --- | ---: | --- |
| [Build and ELF inspection](evidence/early-selinux-standard-services-build.json) | 13,533 | `0e24edc68d3aacb612c209fc677fce714089ed210f79585b1e85e10dd5701017` |
| [Build invocation](evidence/early-selinux-standard-services-invocation.json) | 996 | `f1378fc04dde8c06175ddaf31a5d700e86be915ca5c68b1f2bd223c62bad97d7` |
| [Input transfer](evidence/early-selinux-standard-services-input-transfer.json) | 843 | `db0798c026d708b23b37e71d48c9640e4042dc9b70bc37d84e225d414a862901` |
| [HDD transfer](evidence/early-selinux-standard-services-hdd-transfer.json) | 944 | `fc1d123b1b98b0883593f15241980a2ee4aa7a6021b5bb8ac5f6a83f62603544` |
| [Actual non-PID1 refusal](evidence/early-selinux-standard-services-negative.json) | 2,057 | `42c003de493b6929ad94ad23e1caf94a9ebe3d7438f226faec3fbd4b9c02fed0` |

## Reason for the new version

The retained [R4D run](fedora-r4d-reload-fd-failed.md) reached standard systemd
policy reload, actual descriptor transfer and the pids limit test. It also
exposed missing standard-service permissions, visible AVCs, a shared printk
suppression message, and serial interleaving that prevented the host from
parsing the entire result. V3 addresses the early observation prerequisite;
it does not reinterpret any of those failed gates as passed.

The [independently built service-policy candidate](selinux-standard-service-policy.md)
has a new length of 3,835,456 bytes. The loader's fixed length condition is
updated accordingly. Its runtime C still does not hash that policy: the
archive checker and complete-system profile must separately bind the full
`727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502`
source-policy identity, and the running kernel's exported policy requires its
own observation and checks.

The [audit source investigation](audit-observability.md) identifies a shared
`printk_ratelimit()` check in the fixed kernel's audit printing path. With
that implementation, an interval of zero bypasses this particular limiter.
A suppression count does not identify how many AVCs were omitted, and the
caller named when a shared counter is printed need not identify every
message that contributed to it. This motivates an explicit observation
setting in the controlled generic VM, before the first policy load.

## Fixed inputs and derivation

The [V3 recipe](../../../scripts/research/selinux/standard-services/build_early_init_v3.py)
hash-checks the original C and build recipe, checks every derivation anchor,
and incorporates the separately pinned
[audit guard](../../../scripts/research/selinux/standard-services/audit_printk_guard.inc).
The original recipe is used for its fixed extraction and inspection helpers;
its original source-specific build is not rerun or edited.

| Input or output | Bytes | SHA-256 |
| --- | ---: | --- |
| Original V1 C | 12,548 | `6006a0fade3e9e8cc9201b5549cab3339961931feadb842c0f3d5863dc383726` |
| V3 build recipe | 13,002 | `21e912fa4a2b79b771b70e7b6a46187bde2f746425e549e7e4151d0ce3caf268` |
| Audit guard include | 7,393 | `f715d823ac20181b916afac5c4db9ae9af8226454508e2dff9bb9b8f35e035cc` |
| Derived V3 C | 20,011 | `58fe1187109bc0feaedec249274815490ac69aa2e892cb3534c32a2f793cf4b8` |
| Candidate source policy, version 35 | 3,835,456 | `727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502` |
| Compiled V3 ELF | 72,528 | `84cc4868317fd1799ab1ff8f8ba5ae8bf85445dda5d65c3f11e1637aadb599c3` |

The complete source-change list is in the native build record. It changes
the V1 marker to V3, the policy length from 3,835,432 to 3,835,456, adds
`limits.h`, inserts the guard functions before `load_api()`, and calls the
guard after checked API/SELinux filesystem mounting and before `load_api()`.
The original root/PID1/no-arguments entry check runs earlier. The retained
`--check-api` mode is a separate original branch; it does not execute this
guard or load a policy, and it was not invoked in the V3 qualification.

## Runtime observation contract

Normal boot execution must meet all of the following conditions before the
guard attempts its single fixed sysctl update:

1. The process is root and PID 1, with the original no-arguments entry guard
   already satisfied.
2. `/proc/cmdline`, read from the checked proc filesystem, contains exactly
   one `rd.tb371fc.audit-printk-unlimited=1` token. Another value, a bare key,
   a duplicate key or an embedded NUL fails the guard.
3. The actual sysfs device-tree compatible property contains exactly one
   complete `linux,dummy-virt` entry in a valid NUL-terminated list. A command
   line assertion alone cannot satisfy the machine check.
4. The fixed interval and burst nodes are ordinary root-owned proc files,
   opened without following a final symlink. Reads have byte and call bounds;
   integer parsing rejects malformed or out-of-range values.

The guard then writes exactly the two ASCII bytes `0\n` to
`/proc/sys/kernel/printk_ratelimit`. Interrupted writes have a bounded retry
count; a short write fails instead of continuing at a nonzero offset.
Fresh opens must read back interval zero and the unchanged burst value.
The code does not set the burst to zero, alter audit admission/rate/backlog,
disable SELinux, or change an enforcing flag.

Only after successful readback and checked marker output does the normal
loader proceed toward its first policy API call. The marker has this form;
the bracketed values below are placeholders, not an observed V3 VM result:

```text
TB371FC_EARLY_SELINUX_V3 AUDIT_PRINTK_UNLIMITED scope=generic-vm opt_in=1 compatible=linux,dummy-virt before=<observed> after=0 burst_before=<observed> burst_after=<same> policy_load_attempted=0
```

The complete-system verifier must require one correctly ordered marker,
between successful old-root cleanup and policy loading, and independently
recheck interval/burst in the running guest. It must also inspect the full
raw serial output for AVCs and actual audit-loss/suppression indicators.
Disabling this one shared printk interval does not prove that audit queues,
other rate limiters, journaling or serial transport cannot lose information.

The explicit machine guard scopes this executable to the generic VM
experiment. Its successful compilation does not make this initramfs an
owner-tablet boot image; the owner entry and recovery profile has separate
requirements.

## Actual build and native transfer

Compilation ran in `tb371fc-build-ssd-20261123` under:

```text
/work/early-selinux-standard-services-20261123/build-01
```

The outer invocation started at 15:23:07 and finished at 15:23:11 on
2026-11-23, Asia/Shanghai. It passed the checked source-policy path, full
SHA-256 and length explicitly. The candidate was transferred from the
independent HDD policy-build tree through a native container bridge; no
PRoot setup or policy load was involved.

The fixed cross-compiler is GCC 14.2, actual compiler SHA-256
`fb743ca27a77466c91da66047eec879a615993feaabd860aaf3750e7b222b131`.
The recipe reuses the pinned Fedora libselinux header RPM and verifies all
seven extracted headers. It retains PIE, stack protection, fortification,
RELRO/NOW, `-Werror`, fixed locale and deterministic epoch options. Compiler
stdout/stderr were empty. This record contains one compilation; fixed
inputs alone are not evidence of an independent identical rebuild.

The inspected executable is little-endian AArch64, machine 183, `ET_DYN`,
with `/lib/ld-linux-aarch64.so.1` as interpreter. Its only `DT_NEEDED` entries
are `libc.so.6` and `ld-linux-aarch64.so.1`, with no RPATH/RUNPATH. Required
versions are `GLIBC_2.17`, `GLIBC_2.33` and `GLIBC_2.34`. Runtime libselinux
and other archive-library identities remain separate archive gates.

The ELF, derived C, original build JSON and both recipe sources were copied
to the same prefix in `tb371fc-build-20261123`. Every destination length,
hash and mode matched its transfer record. No original frozen rootfs or
source recipe was modified by that transfer.

## Actual entry-refusal check and integration requirement

At 15:26:33 Asia/Shanghai, the HDD container executed:

```text
/usr/bin/qemu-aarch64-static \
  -L /work/fedora-input-system-v6/rootfs \
  /work/early-selinux-standard-services-20261123/build-01/early-init
```

The child exited 1 in **0.211217 seconds**, produced no stdout, and emitted
exactly:

```text
TB371FC_EARLY_SELINUX_V3 FAILED phase=entry reason=pid1-with-no-arguments-required errno=0
```

The frozen source order and exact marker identify the refused entry branch.
The sampled reference-root, `dev` and `etc` inode/mtime/ctime values were
unchanged; container interval and burst readings remained `5` and `10`.
These are limited corroborating observations, not a complete syscall trace
or evidence that the new guard has executed as PID 1.

The old cleanup waiter expects a 72,048-byte next `/init`, so it cannot be
reused with this 72,528-byte V3 loader. The separately compiled
[waiter V2](tmpfs-waiter-v2.md) supplies the new length contract while
retaining its child-cleanup and old-root checks. The archive/profile must
pin the complete identities of both executables: neither the waiter nor
the loader's policy-length check is a content-hash substitute.

The [whole-device acceptance ledger](acceptance.json) gains no GPU,
display, input, radio, audio, charging or power-management pass from this
construction work. Those results require actual owner-hardware evidence.
