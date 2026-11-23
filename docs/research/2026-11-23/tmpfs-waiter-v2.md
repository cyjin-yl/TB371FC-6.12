# Cleanup waiter V2 for the measured V3 early loader

## Actual result and scope

The independent cleanup waiter V2 **compiled successfully and passed ARM64
ELF inspection plus the original-baseline non-PID1 rejection check**. Its
71,872-byte ELF has been copied from the SSD builder to the HDD Fedora
builder with independent length/hash/mode readback.

This experiment did not run PID 1, mount a filesystem, clean an old root,
load a policy, edit a rootfs or start a VM. It adds **zero owner Linux boots
and zero physical hardware passes**. The complete
[machine record](evidence/tmpfs-waiter-v2.json) retains the actual build,
transfer, negative invocation, tool/ELF identities and exact source delta.
The original [V1 bootstrap](tmpfs-initramfs-bootstrap.md), source and ELF
cc30c123 remain unchanged.

## Why a new waiter is required

The actual separately built V3 early loader is **72,528 bytes**, SHA-256
84cc4868317fd1799ab1ff8f8ba5ae8bf85445dda5d65c3f11e1637aadb599c3.
The original waiter requires its next fixed /init to be **72,048 bytes**.
That old size check would reject the measured V3 before it could run.

The new recipe receives the actual V3 path, byte length and complete hash
explicitly, verifies the ordinary root-owned 0755 AArch64 PIE ELF, and
derives a separate C file. Only these source substitutions are allowed:

1. The marker becomes TB371FC_TMPFS_STAGE1_V2.
2. HELPER_SIZE becomes 72528.
3. The header comment names V3 and states that runtime checks here cover
   shape/length, while the independent archive pins both complete ELF hashes.

Reversing those three substitutions reproduces every original C byte. All
PID 1/root/argc, FD 3, memory-root/distinct-root, mount-flags, initial
security-state, console, SIGCHLD/waitability, one-cleanup-child, 30-second
deadline, old-root rewind/emptiness, saved-FD close and target-shape checks
remain unchanged. The existing failure string unchanged-native-entry-shape
also remains; it does not claim V3 equals the old e53 ELF.

## Fixed inputs and actual outputs

| Item | Bytes | SHA-256 |
| --- | ---: | --- |
| Original waiter C | 7,529 | 32fbddd979e02c310ed28e3571d32a32f9733c8a07bed772aa9c64baf4483b33 |
| Original build helper | 8,093 | 5c6985c93942a7987acb5fa3e0822567c3c76348c5a34d280f370dcf3f62e294 |
| Unchanged stage0 | 6,039 | 15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d |
| New independent recipe | 10,860 | aeba1f16a6b20667067806a57b30712ead5879728de2f9e3c33ed00820cd9dd8 |
| Actual derived V2 C | 7,669 | 59f83f1654d7d4d12f82ba577d3f2c760bcade4d261d9db6aa959dd1f5473143 |
| Actual V2 waiter ELF | 71,872 | 7e593ef9b2c40834b97ad35b1bc21fcd54b00e34dce72381832f88329e28b3ec |
| Required V3 next /init | 72,528 | 84cc4868317fd1799ab1ff8f8ba5ae8bf85445dda5d65c3f11e1637aadb599c3 |

The waiter's own size stays 71,872 bytes, as in V1; its hash and marker change.
Its target /init length is a different property.

The [new recipe](../../../scripts/research/selinux/tmpfs-root-v2/build_stage1.py)
imports only the hash-pinned old tool/ELF helpers, without calling the old
build entry point or changing its constants. The
[derived C](../../../scripts/research/selinux/tmpfs-root-v2/wait_and_exec.c)
is the exact file compiled.

## Actual build and transfer

The SSD container is tb371fc-build-ssd-20261123, source checkout /src,
new workspace /work/tmpfs-waiter-v2-20261123/build-01, and persistent tmux
session tb371fc-waiter-v2. All frozen source and actual V3 identities were
checked before launch and after construction. The fixed GCC 14.2 cross
compiler, binutils 2.44 and 2.41 cross libc development package identities,
command and environment are in the machine record.

Compilation exited 0 in **0.497650 seconds**. Compiler
stdout and stderr are empty. The artifact is ELF64 little-endian AArch64
ET_DYN, with interpreter /lib/ld-linux-aarch64.so.1, only libc.so.6 plus
ld-linux-aarch64.so.1 dependencies, and no RPATH/RUNPATH. Complete readelf
headers, dynamic entries and symbol-version requirements are retained.

Ten fixed regular files were streamed between the CT102 Docker containers.
The receiver wrote only a fresh project prefix and independently checked
every length/hash/mode/readback. The 170,464-byte transfer SHA-256 is
58c8736d1db73a2116df760ce07a38df7da8dfd30f45aed18262c51e6493043b.

The waiter is now at this path in both the SSD container and the HDD
tb371fc-build-20261123 container:

    /work/tmpfs-waiter-v2-20261123/build-01/init.tmpfs-wait

## Limited same-baseline execution

The HDD check used the original Fedora v3 root and fixed QEMU user emulator:

    /usr/bin/qemu-aarch64 -L /work/fedora-input-system-v3/rootfs /work/tmpfs-waiter-v2-20261123/build-01/init.tmpfs-wait

It returned **exit 1**, empty stdout, and exactly:

    TB371FC_TMPFS_STAGE1_V2 FAILED phase=entry reason=pid1-root-with-no-arguments-required errno=0

This is the expected rejection; the enclosing qualification job exited 0.
The actual child invocation took **0.046788 seconds**.
QEMU's SHA-256 is
73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943.
The actual loader/libc identities and exact stdout/stderr are retained. The
[executed qualifier](../../../scripts/research/selinux/tmpfs-root-v2/qualify_non_pid1.py)
is preserved byte for byte.

The qualifier's raw started_utc field was generated during result assembly
after the short child invocation; the enclosing job start_utc is the launch
timestamp. The measured monotonic duration is separate. No raw field was
retrospectively rewritten.

This check reaches only the first PID 1 refusal. It does not demonstrate
cleanup, descriptor continuity, target-shape acceptance or V3 execution.
Stage0 was not rerun because its bytes did not change.

## Remaining archive and runtime gates

The consumer must pin **both complete ELF hashes**, install the new waiter
at /init.tmpfs-wait, retain unchanged stage0 and require the V2 cleanup
marker in sequence. The native waiter **does not hash /init**. Fixed byte
length and metadata checks must not be described as content authentication.

A new VM still must observe the actual roots, one reaped cleaner, empty old
root, V3's guarded early path, required process/API labels, complete result
file and serial qualification, and every prior system gate. This report
does not provide that new PID 1 or VM result.

A 14-record evidence bundle is retained in the workspace. Its XZ size is
12,544 bytes, SHA-256
95baeb9d92898a97ec99d38f1abc7c1f478a0f57f462fdb622e3e9ccb32e067a.
The expanded 66,768 bytes have SHA-256
9f2df5d18fc5041cd099e3d0b3742ce92b3511e03c3a5598bebb2a9e505a939e.
All entry hashes were verified. Cloud-workspace unavailability affected
only the initial local report-save attempt; the completed builds, transfer
and original remote evidence were retained.
