# Pre-policy tmpfs initramfs bootstrap: construction checkpoint

## Result and scope

The new pre-policy entry script and AArch64 cleanup waiter have been built
and qualified for the next, independent Fedora v6 system candidate. The
waiter compiled successfully against the fixed cross toolchain. Fedora's
actual ARM Bash parsed the entry script, and direct QEMU user emulation
confirmed that both entries reject execution outside PID 1 before doing
any mount or policy operation.

**This checkpoint does not claim a successful root relocation, new
production boot, or tablet boot.** Those operations belong to the separate
v6 system run. The original `e53cf…` SELinux `/init`, its source and its
earlier report remain unchanged. The complete build output, limited
execution records, source identities, policy-query summaries and proposed
runtime contract are in
[tmpfs-initramfs-bootstrap.json](evidence/tmpfs-initramfs-bootstrap.json).

The new sources are:

- [stage0.sh](../../../scripts/research/selinux/tmpfs-root/stage0.sh):
  the fixed `/init.tmpfs` entry.
- [wait_and_exec.c](../../../scripts/research/selinux/tmpfs-root/wait_and_exec.c):
  `/init.tmpfs-wait`, which checks the root migration and waits for cleanup.
- [build_stage1.py](../../../scripts/research/selinux/tmpfs-root/build_stage1.py):
  the isolated, input-pinned AArch64 build recipe.

All work used new project prefixes in CT102. It did not mount a target
root, load a policy, execute a new PID 1, run a system VM, use PRoot or
operate the physical tablet. The limited user emulation checks read the
retained Fedora v3 library root; they did not use the earlier R1 root
through PRoot.

## Why this follow-up is needed

The [retained v5 production failure](fedora-r4b-early-failed.md) established
a narrower result than the earlier archive and API checks could establish.
The native helper loaded the fixed Fedora policy with Enforcing enabled,
then failed while restoring the normal `var_t` label on `/var`.
The kernel denied `var_t` to `root_t` **filesystem associate**. PID 1 exited
before it executed systemd.

This permission compares the proposed inode label with the filesystem
superblock label. It is separate from the caller's relabel permissions.
Consequently, adding the already-qualified policy files or proving
`kernel_t` inode relabel permissions does not close that failure.

The [fixed-kernel and policy audit](selinux-rootfs-association.md) supplies
the source-level explanation. The Fedora base CIL gives the filesystem
type `rootfs` a `root_t` label through its `genfscon` rule. Ordinary `tmpfs`
and `ramfs` use the policy's `tmpfs_t` filesystem label. Linux 6.12 selects
this behavior using the actual filesystem-type name; changing the initial
rootfs wrapper's backing allocation does not rename it to ordinary tmpfs.
The same audit excludes a pre-policy `fscontext=` remount and a
post-initialization remount as ways to change this existing superblock SID.

The independently executed 44-query result used the fixed policy
`928dd639…`, converted to version 33 in libsepol process memory.
For `var_t`, `init_exec_t`, `udev_exec_t`, `bin_t`, `lib_t`, `etc_t`
and `usr_t`, `filesystem associate` was denied to `root_t` and allowed
to `tmpfs_t` and `fs_t`. `root_t` itself could associate with all three.
The actual v5 denial independently corroborates the `var_t`/`root_t`
case. The converted policy bytes are not asserted to equal a running
kernel's exported policy.

A second, 18-query check found the examined `kernel_t` to `root_t`
directory and inode cleanup permissions allowed. The implementation
nevertheless requires cleanup to finish before the first policy load.
It does not use those allows to treat an asynchronous cleanup race as
verified.

The chosen candidate therefore creates a new ordinary tmpfs superblock
before policy loading, copies the fixed initramfs payload onto it, uses
Fedora's standard `switch_root`, completes and checks old-root cleanup,
and then executes the original native helper. It makes no policy change
and does not skip the failed restorecon operation.

## Exact stage0 contract

`stage0.sh` is installed as `/init.tmpfs`, and the production kernel must
select it through exactly one `rdinit=/init.tmpfs` argument. The script
also requires exactly one each of:

```text
selinux=1
enforcing=1
rd.tb371fc.early-selinux=1
rd.tb371fc.tmpfs-root=1
```

It requires PID 1, effective UID 0, no positional arguments, an ordinary
`/etc/initrd-release` file, an initial SELinux context of `kernel`, and
one actual root mount whose filesystem type is `rootfs`. A bounded
command-line read and exact-token counts reject ambiguous opt-ins.

Before creating any new mountpoint, it requires the archive's complete
top level to be exactly these 18 paths:

```text
bin dev etc init init.systemd init.tmpfs init.tmpfs-wait lib lib64
proc root run sbin sys sysroot tmp usr var
```

Unknown paths, including hidden top-level entries, cause failure. The
archive checker pins the payload itself; this runtime layout check
prevents the copy operation from silently expanding to an unexpected
top-level input.

The script mounts `/proc` with `nosuid,nodev,noexec` and `/dev` as devtmpfs
with `mode=0755,nosuid,strictatime`. Descriptor 3 keeps the old root
directory open across exec. The script does not pre-mount `/sys`, `/run`
or selinuxfs. The unchanged native helper supplies its existing API
mounts later, and systemd creates and labels `/run` after policy loading.

The new root is an ordinary tmpfs at `/tb371fc-initroot`, with source name
`tb371fc-initroot` and options `mode=0755,size=192M`. It has no SELinux
label override and no `nosuid`, `noexec` or `nodev` restriction. Those
restrictions are inappropriate for this executable root and could
prevent the required policy transition on exec. Its actual mount record
must identify tmpfs and a device number different from the old root.

The retained v5 production tree contained 82,856,600 ordinary-file bytes
at inspection time. The 192 MiB limit provides a bounded target for this
fixed candidate; the file-size sum is not a peak-memory measurement or a
claim that the physical tablet can satisfy this allocation under every
workload.

One `cp -a -x` invocation copies these 14 static top-level inputs:

```text
bin etc init init.systemd init.tmpfs init.tmpfs-wait lib lib64
root sbin sysroot tmp usr var
```

A single invocation preserves hardlinks shared across top-level inputs.
The API roots are excluded entirely, and empty destination mountpoints
are created for them. Supplying an API mountpoint as its own `cp -x`
source would still traverse that source mount, so `-x` alone would not
make such a copy safe or finite.

After checking the copied native entries, stage0 emits:

```text
TB371FC_TMPFS_STAGE0_V1 COPY_COMPLETE old_dev=M:m new_dev=M:m policy_load_attempted=0
```

It then execs the fixed standard tool:

```text
/usr/bin/switch_root /tb371fc-initroot /init.tmpfs-wait
```

Every failure stops this PID 1 route with a phase/reason diagnostic.
There is no fallback to a different root or policy mode.

## Why the standard tool needs a separate waiter

The [matching Fedora util-linux audit](selinux-rootfs-association.md)
compared the installed tool with the corresponding official
`util-linux-core-2.42.4-1.fc45.aarch64` RPM and inspected the matching
source RPM. The installed payload is 69,104 bytes, mode `0755`, SHA-256:

```text
6b6c1803111f117b76b553a664cec1a074827d025618446319d7871f9c127f75
```

Its source moves the API mounts, moves/chroots to the new root, then
forks a child to remove the old RAMFS/TMPFS directory tree. The parent
does not wait; it immediately execs the requested new init.
Some deletion failures produce warnings while the child can still
exit zero. The tool also does not reconnect the inherited console
descriptors.

The new native stage1 closes those specific verification gaps without
implementing another tree copier or root-switch algorithm. It requires:

1. PID 1, root, no arguments, and the pre-policy `kernel` context.
2. A non-CLOEXEC directory descriptor 3 referring to a RAMFS/TMPFS old
   root, and a different current root whose magic is TMPFS.
3. A writable new root without `nosuid`, `noexec` or `nodev`.
4. A real `/dev/console` character device, major 5/minor 1, opened without
   following a symlink and duplicated onto standard input/output/error.
5. The default SIGCHLD disposition with no `SA_NOCLDWAIT`.
6. Exactly one cleanup child reaped with exit status zero, followed by
   `ECHILD`, within a 30-second monotonic deadline.
7. An old-root directory scan rewound to offset zero and completed
   without errors, with no entries other than `.` and `..`.
8. Closure of both the scan descriptor and saved old-root descriptor
   before executing the original `/init`.

`ECHILD` without first reaping the one expected child is a failure.
A second child, a signalled child, timeout, a nonzero status or any
remaining old-root entry also fails. The explicit directory scan is
needed because a zero cleanup exit status alone does not prove all
named entries were removed.

The final marker is:

```text
TB371FC_TMPFS_STAGE1_V1 CLEANUP_COMPLETE old_dev=M:m new_dev=M:m cleanup_children=1 old_root_empty=1 policy_load_attempted=0
```

The waiter checks the original native `/init`'s ordinary-file shape,
size, owner and mode. The independent archive checker verifies its
complete SHA-256 identity. The waiter then execs that unchanged helper.

This establishes the intended ordering and a named-directory cleanup
criterion. Even when demonstrated at runtime, it would not by itself
measure how many physical pages were freed or prove that no unrelated
unlinked reference exists elsewhere.

## Actual build and limited execution

The build ran in `tb371fc-build-ssd-20261123` at
`2026-11-23T05:12:39.776999Z`, under:

```text
/work/early-selinux-rootfs-20261123/build-01
```

It exited zero in 2.319 seconds with no compiler diagnostics.
The recipe checked the compiler executable's SHA-256 and the actual
package versions before compiling:

| Component | Fixed identity |
| --- | --- |
| GCC | `aarch64-linux-gnu-gcc`, Debian `14.2.0-19` |
| Cross compiler package | `gcc-14-aarch64-linux-gnu 14.2.0-19cross1` |
| Cross binutils | `binutils-aarch64-linux-gnu 2.44-3` |
| Cross libc development files | `libc6-dev-arm64-cross 2.41-11cross1` |
| Compiler SHA-256 | `fb743ca27a77466c91da66047eec879a615993feaabd860aaf3750e7b222b131` |

Compilation used PIE, stack protection, `_FORTIFY_SOURCE=3`,
`-Wall -Wextra -Werror`, RELRO and immediate binding. The actual ELF
inspection found AArch64 ELF64 little-endian PIE, a non-executable GNU
stack, GNU RELRO and BIND_NOW. Its interpreter is
`/lib/ld-linux-aarch64.so.1`; its only `DT_NEEDED` entries are
`libc.so.6` and `ld-linux-aarch64.so.1`. It requires GLIBC symbol versions
2.17, 2.33 and 2.34 and has no RPATH/RUNPATH.

| Item | Bytes | SHA-256 |
| --- | ---: | --- |
| Stage0 source / `/init.tmpfs` | 6,039 | `15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d` |
| Waiter source | 7,529 | `32fbddd979e02c310ed28e3571d32a32f9733c8a07bed772aa9c64baf4483b33` |
| Build recipe | 8,093 | `5c6985c93942a7987acb5fa3e0822567c3c76348c5a34d280f370dcf3f62e294` |
| Actual `/init.tmpfs-wait` ELF | 71,872 | `cc30c123b32259b1097eeb2f34cc13528d510cfc2521aac170bae23c4880a63a` |
| Original, unchanged native `/init` | 72,048 | `e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d` |

The five source/build files listed in the JSON were streamed into the
same new project prefix in the HDD container, and the receiver
independently reread their lengths, modes and SHA-256 values. This was a
verified transfer of one build. A repeated byte-identical rebuild of
this new waiter has not been demonstrated.

At `2026-11-23T05:13:24.513509Z`, direct QEMU user emulation using the
retained Fedora v3 dynamic-loader/library root performed three checks:

| Check | Observed result | Meaning |
| --- | --- | --- |
| Actual ARM Bash `-n stage0.sh` | Exit 0 | Target shell accepts the script syntax. |
| Stage0 invoked outside PID 1 | Exit 1, expected entry diagnostic | It rejects before its mount path. |
| Waiter ELF invoked outside PID 1 | Exit 1, expected entry diagnostic | It links/runs and rejects before root or cleanup actions. |

These checks do not exercise copy, mount, switch_root, wait/reap,
restorecon or systemd. They are useful limited checks, not substitutes
for the production VM.

The build record SHA-256 is
`1383a22b3c8acfd3b6c3dd4de8256ca043a97b32347c60632654e9e3bc78de20`.
The limited-execution record SHA-256 is
`7bfcf82b3fa0d37b0073ca8c4e2414ebf859774fb89805d9baaa7d524932ad2c`.
Both complete record bodies are retained in the public evidence JSON.

## Reproduction and independent integration gates

The recipe accepts an explicit source checkout and a **fresh**
`/work` output directory. In the qualified cross-build container,
after the fixed public revision has been synchronized to `/src`, a
separate reproduction would use:

```sh
python3 /src/scripts/research/selinux/tmpfs-root/build_stage1.py \
  --repo /src \
  --work /work/early-selinux-rootfs-20261123/rebuild-01
```

The recipe refuses an existing output prefix, a changed source, a
changed compiler binary or a changed toolchain package version.
It does not execute the result, edit a rootfs or mount a filesystem.
This pins the small helper's construction; it does not claim that the
whole kernel or system image is reproducible.

The separate
[archive checker](../../../scripts/research/input/system-integration/verify_tmpfs_policy_initramfs.py)
was frozen at SHA-256
`92f02fd33fcc5f7aaea6d1d0e06c04589af024b09e8f678f772798909c2ebb07`.
It pins the two new stages, the standard switch_root payload and the
unchanged e53 native helper, and retains the earlier archive, library,
policy and firmware checks. Its existence is not recorded here as a
successful new archive execution.

The v6 runtime qualification must independently observe the new tmpfs
root and the actual process domains. Its required order is:

```text
COPY_COMPLETE
CLEANUP_COMPLETE
unchanged helper: POLICY_LOADED enforcing=1
unchanged helper: EXEC_SYSTEMD
same-boot initrd PID1 and udevd domain proof
```

Stage0 and stage1 must agree on old and new device numbers; those
numbers must differ. The new device must also match the actual root
entry from initrd PID 1's mountinfo, with source `tb371fc-initroot`
and the required mount flags. The proof must read PID 1 in `init_t`
and udevd in `udev_t` during that same initrd boot.

The unchanged helper mounts its API filesystems again after the first
root switch. The actual mount state, domains, absence of AVC denials
and later udev event handoff must therefore be checked in the VM.
Successful static source review does not resolve those runtime facts.
The system-bus descriptor route, actual broker context and exported
policy access, pids enforcement, BPF LSM denial/control, signed modules,
runtime hashes and clean system completion remain separate gates.

The physical TB371FC entry/recovery transport and every owner-Linux
hardware acceptance case remain outside this host-only checkpoint.
