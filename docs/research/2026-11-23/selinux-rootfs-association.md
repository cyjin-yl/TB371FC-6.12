# SELinux rootfs association failure and the standard tmpfs handoff

## Result and evidence boundary

The retained v5 production boot reached its first SELinux policy load in
Enforcing mode. It then failed while assigning the normal `var_t` label to
`/var`: that inode label was not allowed to associate with the initial
`rootfs` superblock's `root_t` label. The fixed Linux 6.12.114 source and the
fixed Fedora policy explain this failure together.

Neither a pre-policy `fscontext=` remount nor a post-policy remount can reset
that superblock label in this kernel. An independent, ordinary `tmpfs`
superblock has the policy's normal `tmpfs_t` filesystem label and the compiled
security-xattr implementation needed for the next candidate. Moving a
qualified copy of the initramfs onto that filesystem is a supported source
route. **This audit does not report a successful relocation or a passed new
production boot.**

The complete file identities, source excerpts, already-executed offline
policy query, and package-to-installed-ELF comparison are in
[selinux-rootfs-association.json](evidence/selinux-rootfs-association.json).
This work read existing artifacts natively and downloaded source/package files
into a separate analysis directory. It ran no PRoot, target mount,
`switch_root`, new VM, policy load or enforcement change. The original
[bootstrap](early-initramfs-selinux.md), checker and kernel remain frozen.

## The actual failure followed a valid archive check

The production archive was 32,466,768 bytes, SHA-256:

```text
9f2a664305c968f4fc3efecd4ef5298a1723cae9030d896a2bc35f2f94bb6668
```

Its existing archive-verification result is
`/work/fedora-input-system-v5/initramfs-archive-verification.json`,
109,842 bytes, SHA-256
`8500f905f34f5074289f15bc1ad86843cd2c137963008614023c814ba6c121dd`.
It records a pass by the fixed `58a5…` checker. This is a byte/layout result,
not a policy or boot success.

The actual production serial log is
`/work/fedora-input-system-v5/vm-verify-01/serial.log`, 19,359 bytes,
SHA-256
`4bcf21659de6f20fe700626897f26deafa3ed125fd394d14d65ca3f206005a75`.
It records, in order:

1. Policy loaded with `enforcing=1` and PID 1 in `kernel_t`.
2. An `associate` denial for the proposed `var_t` inode label against
   `root_t`, class `filesystem`, on device `rootfs`.
3. The bootstrap's `restore-initramfs-contexts` failure with errno 13.
4. PID 1 exit and the resulting kernel panic.

The denial's source context is the **proposed inode label**, not the caller's
process label. Treating it as an ordinary missing `kernel_t` relabel
permission would miss the last check in `selinux_inode_setxattr()`.

## How the initial filesystem acquired root_t

The frozen kernel source is
`/work/research4-system/source-input/linux-6.12.114-input-integration`.
The evidence records complete SHA-256 identities for each inspected source.

In `security/selinux/hooks.c`, `selinux_inode_setxattr()` first checks the
caller's relabel-from and relabel-to permissions and the label transition.
It then checks:

```c
avc_has_perm(newsid, sbsec->sid,
             SECCLASS_FILESYSTEM, FILESYSTEM__ASSOCIATE, &ad)
```

Here `newsid` is the proposed `var_t` label; `sbsec->sid` is the filesystem
superblock label.

In `security/selinux/ss/services.c`, `security_fs_use()` selects behavior
using `sb->s_type->name`. It first looks for a policy `fsuse` entry. If none
matches, it uses the filesystem's `genfscon` rule for `/`.

The fixed Fedora base CIL contains:

| Filesystem type | Fixed rule | Filesystem label |
| --- | --- | --- |
| `rootfs` | `genfscon rootfs "/"` | `root_t` |
| `ramfs` | `fsuse trans ramfs` | `tmpfs_t` |
| `tmpfs` | `fsuse trans tmpfs` | `tmpfs_t` |

The compressed CIL SHA-256 is
`1d1e418d8147cfbf61b089003549c95b92c939818b85710f98a45221473f7667`;
its decoded SHA-256 is
`bb28ac9c5b5b4673315386ac869fef7a6dbe8b3ac790608eb2030d50a240c966`.
The two `fsuse` entries and the `genfscon` entry were read directly from
the ordinary fixed source file; no policy was changed.

The observed command line supplies both `root=LABEL=…` and
`rootfstype=ext4`. In `init/do_mounts.c`, these values leave
`is_tmpfs` false, so the initial `rootfs` wrapper uses the ramfs initializer.
Its filesystem-type name remains `rootfs`. Even selecting a tmpfs backend
for that wrapper would not turn its type name into `tmpfs`; changing the
kernel's `rootfstype=` argument is therefore not a solution to this SID
selection.

The first policy load calls `selinux_complete_init()`, which iterates the
existing superblocks and initializes their labels. The original rootfs is
already initialized when the bootstrap subsequently calls restorecon.

### The fixed policy query supports a different superblock

The independently executed 44-query result is
`/work/early-selinux-rootfs-20261123/query-01/result.json`, SHA-256
`4b97090641defd1f24860f79096bec77c1561ed5f865380df09c701543956cb7`.
This audit read that result and its complete input identities.

For `var_t`, `init_exec_t`, `udev_exec_t`, `bin_t`, `lib_t`, `etc_t`
and `usr_t`, the query denies `filesystem associate` to `root_t` and
allows it to `tmpfs_t` and `fs_t`. `root_t` itself can associate with all
three. The query also permits `kernel_t` to mount the ordinary tmpfs
filesystem.

These are queries against the fixed policy converted to version 33 in
libsepol memory, SHA-256 `aab7…`. They are not asserted to be byte-identical
to a running kernel's exported policy. The actual v5 AVC independently
corroborates the `var_t` to `root_t` case. The new tmpfs route still needs
its own complete runtime verification.

## Why remount and label-option substitutions do not solve it

The pre-policy remount path was checked separately from the ordinary
new-superblock path:

```text
do_remount
  → parse_monolithic_mount_data
  → vfs_parse_fs_param
  → selinux_fs_context_parse_param
  → selinux_add_opt
```

`selinux_add_opt()` explicitly returns `-EINVAL` when SELinux has not
loaded its first policy. It does so before allocating or retaining the
requested mount options. Consequently, `MS_REMOUNT` with `fscontext=`
does not save a pending filesystem SID. The early return in
`selinux_sb_remount()` for an uninitialized superblock cannot help: option
parsing has already rejected the request.

After policy initialization, `bad_option()` rejects a new security-option
flag or a changed SID on an existing initialized superblock.
`selinux_sb_remount()` checks compatibility; it does not assign a new
superblock SID.

The related options have different meanings:

| Option or operation | Relevant behavior |
| --- | --- |
| `fscontext=` | Specifies a filesystem superblock label on a qualifying new mount; cannot reset this initialized rootfs by remount. |
| `rootcontext=` | Specifies the root inode label, not the filesystem label used by the failed association check. |
| `context=` | Selects one mount-point label for its files; the kernel disables ordinary per-inode relabeling for that behavior. |
| Bind-mounting the original rootfs | Reuses the same superblock; it does not create the required differently labelled filesystem. |
| A new ordinary tmpfs mount without SELinux label overrides | Uses the fixed policy's `fsuse trans tmpfs` behavior. |

This is a source-level exclusion of those alternatives. No speculative
remount was executed.

## The existing kernel supports ordinary tmpfs security xattrs

The actual research4 configuration, 222,379 bytes, SHA-256
`0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275`,
has all of the following enabled:

```text
CONFIG_SHMEM=y
CONFIG_TMPFS=y
CONFIG_TMPFS_POSIX_ACL=y
CONFIG_TMPFS_XATTR=y
CONFIG_SECURITYFS=y
CONFIG_SECURITY_SELINUX=y
```

In the fixed `mm/shmem.c`,
SHA-256 `1ff75b0c8ecb8daddd8cf3725ce0019449a83e09a1642455d4f3ea7c2c354fb3`,
the configured security-xattr handler provides both get and set operations
for `security.*`. The setter uses `simple_xattr_set()`; tmpfs creation
assigns the handler table to `sb->s_xattr`. The corresponding inode
operations expose xattr support. SELinux's `SECURITY_FS_USE_TRANS` behavior
is also classified as a relabel-capable filesystem.

Thus the proposed move does not require enabling a missing tmpfs-xattr
configuration option. This establishes the compiled implementation; the new
candidate must still exercise restorecon and read back the actual labels.

## Qualifying Fedora's existing switch_root

The actual installed tool is:

| Item | Identity |
| --- | --- |
| Canonical source file | `/work/fedora-system-integration-v1/rootfs/usr/bin/switch_root` |
| Size / mode | 69,104 bytes / `0755` |
| SHA-256 | `6b6c1803111f117b76b553a664cec1a074827d025618446319d7871f9c127f75` |
| ELF | AArch64, ELF64 little-endian PIE |
| Interpreter | `/lib/ld-linux-aarch64.so.1` |
| `DT_NEEDED` | `libc.so.6`, `ld-linux-aarch64.so.1` |
| Build ID | `7b93d667f58681e03e92d29fdec2aab2d492bd18` |

The `/usr/sbin` directory is a symlink to `bin`, so its tool spelling
reaches the same file. It is not a second independent payload.

The official
[util-linux source RPM](https://kojipkgs.fedoraproject.org/packages/util-linux/2.42.4/1.fc45/src/util-linux-2.42.4-1.fc45.src.rpm)
is 10,793,227 bytes, SHA-256
`a42fac96ae0930c3074fb3cfb1cb4a58d50f9abbeeb398c10fbd8b99110d5587`.
Its upstream source archive SHA-256 is
`fbd62a100ab7bb8746ba0661255c3c48185b1e9021507c624da01fbc696330ec`.
The two Fedora patches change login handling and a MOTD path; neither changes
the switch_root algorithm.

The matching official
[AArch64 util-linux-core RPM](https://kojipkgs.fedoraproject.org/packages/util-linux/2.42.4/1.fc45/aarch64/util-linux-core-2.42.4-1.fc45.aarch64.rpm)
is 565,839 bytes, SHA-256
`c19e86d0ae0e035646a28a3a8a9ae14b094505ca56e33f470bbc4e5a0c9c24d9`.
Its selected `usr/bin/switch_root` payload is **byte-identical** to the actual
fixed rootfs file. Its RPM metadata identifies the exact source RPM above.
This inspection did not install either RPM or perform a new RPM signature
verification.

The complete recursive ELF dependency set is already in the qualified v5
initramfs:

| Ordinary dependency file | Bytes | SHA-256 |
| --- | ---: | --- |
| `usr/lib64/libc.so.6` | 2,303,728 | `620f6221d0cb0a7bc7d0674bcb0682a0b42f7fb593f596f3bf646f02b10cb798` |
| `usr/lib/ld-linux-aarch64.so.1` | 928,784 | `8821728d15728a7046deef6d4183fb343716901e0e8119fff53d6b51e2605547` |

The first metadata-inspection attempt assumed the loader was under
`usr/lib64` and stopped. The actual directory layout was then read, and
the corrected ordinary `usr/lib` loader was qualified. That failed
assumption and the corrected result are both retained. No target executable
or mount operation was run by either inspection.

### Actual move and cleanup semantics

The audited `sys-utils/switch_root.c` is 6,244 bytes, SHA-256
`e87b0456e4b72bcaf853c29e27e257d84523284cc82639fd5db58b0dfa08dcfe`.
It implements the same mount-move/chroot approach described by the fixed
kernel's `Documentation/filesystems/ramfs-rootfs-initramfs.rst`. The
original rootfs cannot be unmounted or passed through the ordinary
`pivot_root` route.

The tool attempts to move `/dev`, `/proc`, `/sys` and `/run` into the
new root, changes into the new root, moves that mount over `/`, calls
`chroot(".")`, and changes to `/`. API-mount movement errors can be
warnings followed by detach or forced-unmount attempts. The existing native
bootstrap and runtime guards must therefore verify the actual API
filesystems; tool execution alone is not their proof. The tool does not reopen
the console descriptors.

After changing roots, it forks one cleanup child. The child accepts only
RAMFS or TMPFS for the old root and removes its named contents without
crossing a different `st_dev`. Symlink entries are unlinked rather than
followed. **The parent does not wait for this child**; it immediately executes
the requested init.

Some cleanup failures only generate warnings. The child takes a normal
success exit even when the recursive removal returned failure, although a
standard-stream flush failure can independently change its exit status.
Therefore neither parent success nor child status zero proves complete
cleanup.

### FD 3 and the required ordering proof

The fixed tool contains no SIGCHLD-disposition change, no
`SA_NOCLDWAIT`, and no close-all or closefrom call. It closes the old-root
descriptor that it opened itself. A pre-existing, non-close-on-exec FD 3
therefore remains available to the next init. The used
`close_stdout_atexit()` helper flushes and duplicates/closes standard-stream
descriptors; it does not sweep inherited FD 3.

A separate next-stage guard can establish the needed boundary before
executing the unchanged native bootstrap:

1. Confirm it is the guarded PID 1 and that policy has not yet been loaded.
2. Verify the inherited old-root descriptor is a directory on RAMFS/TMPFS,
   while the new root is ordinary tmpfs with a different device identity.
3. Require a usable SIGCHLD disposition, wait for the actual cleanup child,
   and reap it before policy loading.
4. Enumerate the old-root directory to EOF without error and reject every
   name other than `.` and `..`.
5. Close the inherited old-root descriptor, then execute the fixed
   Enforcing bootstrap.

The source result supports this design but does not execute or validate the
future guard. An empty old-root directory proves its named tree is empty;
it is not an exact measurement of freed physical pages and does not by itself
exclude other open references to unlinked objects.

The next independent archive must retain the original kernel, native
`/init`, policy, firmware, label readbacks, actual initrd process domains,
system-bus/FIFO tests and complete log failure gates. Its static qualification
and complete production boot remain separate results.

