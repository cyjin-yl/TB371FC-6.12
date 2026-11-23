# Early SELinux initialization: source audit and native bootstrap

## Result and scope

A dedicated ARM64 `/init` bootstrap has been built and handed to the independent
Fedora system experiment. It uses the original Fedora SELinux policy and the
standard `libselinux` APIs to load policy and relabel the initramfs **within one
process**, then executes the original systemd. A second build through the new
recipe produced the same 72,048-byte ELF, SHA-256:

```text
e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d
```

This report freezes the source investigation, two builds, an ARM userspace
library check, and a negative entry-point check. **It does not report a successful
PID 1 boot, a passed production initramfs, or a tablet hardware result.** The
complete system experiment must independently exercise the bootstrap and all its
existing runtime gates. Those results belong in its own report.

The complete observations, package identities, patch results, commands, flags,
access-vector query and library hashes are in
[early-initramfs-selinux.json](evidence/early-initramfs-selinux.json).
The implementation is
[early_init.c](../../../scripts/research/selinux/early_init.c), with the fixed
[build_early_init.py recipe](../../../scripts/research/selinux/build_early_init.py).
Neither the frozen kernels nor the earlier system images were modified.

## The observed failure was a queued-event handoff

The retained first research4 verification log contains one early Enforcing
denial at kernel time `40.627770`: PID 1 in `init_t` could not perform `getattr`
on a `kernel_t` `netlink_kobject_uevent_socket`. Immediately afterward, systemd
reported that it could not retain the deserialized `event-serialization` file
descriptor for `systemd-udevd.service`.

The raw serial log is 889,309 bytes, SHA-256
`f99f7fca24dab4d97ac12ab76a3c531544f76e06e6f61b61f6911bc33a4cb114`,
retained at
`/work/fedora-input-system-v3/vm-verify-01/serial.log` in the original builder.
The journal later records the same event at a different receipt timestamp;
that is not a second independent denial.

The matched systemd source makes the consequence specific:

1. When initrd udevd exits, `manager_serialize_events()` creates a new
   `NETLINK_KOBJECT_UEVENT` socket and writes its still-queued events into it.
   It sends the named descriptor to PID 1 only after at least one event has
   been stored.
2. After switching root, PID 1 calls `service_add_fd_store()` while restoring
   service state. This function performs `fstat()` before accepting the
   descriptor. An error consumes and closes that descriptor.
3. The new udevd receives the queued-event socket by its distinct name and
   restores events from it. The ordinary kernel listening socket follows a
   different branch.

Consequently, a later listening or running `systemd-udevd-kernel.socket` does not
establish that the saved queued events were recovered. The denial is also
separate from the later D-Bus/SCM_RIGHTS reset under investigation in the system
experiment. Fixing this startup path does not by itself resolve that bus test.

These statements use the actual Fedora
[systemd-262.1-1.fc45 source RPM](https://kojipkgs.fedoraproject.org/packages/systemd/262.1/1.fc45/src/systemd-262.1-1.fc45.src.rpm),
not an older systemd version. Its SHA-256 is
`de8e6ebb2fb7b7aa0e1297c0c27c3339d15c37b24b57ca16a762483580ea7168`.
The six relevant source files were identical to
[upstream v262.1](https://github.com/systemd/systemd/tree/v262.1).
The three applicable Fedora patches affect UID classification, varlink and
machined; they do not modify these audited functions. An older generator patch
is excluded by the source RPM's Fedora-version conditional.

## What the old initramfs omitted

The retained initramfs is:

```text
/work/fedora-input-system-v3/retained-dracut-trees/dracut.dfGeBwW/initramfs
```

It contains the original systemd and `libselinux.so.1`, but lacks
`/etc/selinux/config`, the targeted policy, the contexts directory, and
`libsepol.so.2`. Its `selinux` dracut module installs a late `pre-pivot` hook.
The selected module set lacks `dracut-systemd` and the corresponding
`dracut-pre-pivot.service`. The serial log shows the first policy load only
after switching to the real root.

The version-matched `mac_selinux_setup()` explicitly skips loading policy in an
initrd without its SELinux directory. Its later init-label calculation uses the
executable's **actual file context**. Merely placing `file_contexts` beside an
executable does not assign that label.

The fixed Fedora policy gives the rootfs a default `root_t` label. Its normal
process transitions require `init_exec_t` for systemd and `udev_exec_t` for
udevd. The project's `newc` archive does not carry the original SELinux xattrs.
Furthermore, the real `systemd-udevd` executable is a symlink to
`/usr/bin/udevadm`; checking only the symlink would miss the actual executable.

The standard systemd `relabel-extra` mechanism was considered. It runs before
manager startup, but a drop-in merely packed underneath `/run` would be hidden
when systemd mounts `/run`. It would also require further handling of PID 1's
initial context. The selected bootstrap uses the ordinary load, relabel and
executable-transition sequence directly.

## Why two external commands were rejected before testing

An initial proposal used a shell to run `load_policy -i`, then external
`restorecon`. A narrow offline policy query found a real problem with that
sequence.

The fixed original policy was converted to version 33 **only in libsepol
process memory**, as in the earlier
[SELinux compatibility investigation](selinux-compatibility.md). Eleven fixed
access-vector queries were run through explicit ARM QEMU userspace emulation.
They used the retained research4 root's pinned Python and libsepol; no PRoot,
kernel policy load, live boolean substitution or rootfs mutation was involved.

| Fixed policy query | Result | Consequence |
|---|---|---|
| `kernel_t` → `root_t`, file `read`, `open`, `map`, `getattr`, `execute` | Allowed | These permissions alone do not establish that a new process can execute without a transition. |
| `kernel_t` → `root_t`, file `execute_no_trans` | Denied by type enforcement; denial audit bit set | Executing still-unlabelled `restorecon` after policy loading is not a valid continuation. |
| `kernel_t` → `root_t`, file relabel permissions | Allowed | The existing bootstrap process can use the standard relabel operation. |
| `kernel_t` → `init_exec_t` / `udev_exec_t`, file `relabelto` | Allowed | The required executable labels have a policy-supported relabel path. |
| `init_t` → `udev_t`, uevent netlink socket `getattr` | Allowed | A correctly labelled udev-owned queued-event socket has the relevant access-vector permission. |

The converted in-memory policy hash is
`aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe`.
It is **not** asserted to equal a policy exported by a running kernel.
These eleven queries are not a complete syscall or boot proof. The evidence
JSON preserves the exact one-off query source, interpreter arguments, input
hashes and results so that this particular finding can be replayed.

This is why the implementation stays in one native process until the executables
have been relabelled. It does not add an allow rule or relax enforcement.

## The fixed native bootstrap contract

The program is an ordinary dynamically linked AArch64 PIE. Its default path
requires PID 1 with no extra arguments, the explicit kernel command-line tokens
`enforcing=1` and `rd.tb371fc.early-selinux=1`, and the unchanged targeted,
Enforcing configuration. Conflicting enforcement or SELinux-disable arguments
cause failure.

It performs the following bounded sequence:

1. Mount the standard API filesystems and verify their filesystem types.
   `/proc` and `/sys` use `nosuid,nodev,noexec`; `/dev` uses devtmpfs with
   `mode=0755,nosuid,strictatime`; selinuxfs uses `nosuid,noexec`.
   As in libselinux, selinuxfs deliberately does not use `nodev`.
2. Open the fixed Fedora `libselinux.so.1` and resolve a fixed set of standard
   API symbols. Require the initial `kernel` context and Enforcing state.
3. Obtain the standard file-context handle. Require its specifications for
   systemd and `/usr/bin/udevadm` to have the expected executable types.
4. Call `selinux_init_load_policy()`, the same API used by `load_policy -i`.
   Require success, Enforcing still equal to 1, and the bootstrap still in
   `kernel_t`.
5. Call `selinux_restorecon()` on `/` without executing another program.
   Force the complete specified context, recurse, and remain on the initramfs
   filesystem. Abort on a traversal error and skip label-digest caching.
6. Read back the actual executable labels. Require systemd `init_exec_t`,
   `/usr/bin/udevadm` `udev_exec_t`, and Enforcing still equal to 1.
7. Execute the original `/usr/lib/systemd/systemd`. The existing policy
   supplies the process transition. There is no manual `setcon`.

The restorecon flags are `0x828c`:

| Flag | Value | Purpose |
|---|---:|---|
| `SELINUX_RESTORECON_SET_SPECFILE_CTX` | `0x4` | Apply the full specified context. |
| `SELINUX_RESTORECON_RECURSE` | `0x8` | Traverse the initramfs tree. |
| `SELINUX_RESTORECON_XDEV` | `0x80` | Do not descend into another filesystem. |
| `SELINUX_RESTORECON_ABORT_ON_ERROR` | `0x200` | Stop on a traversal error. |
| `SELINUX_RESTORECON_SKIP_DIGEST` | `0x8000` | Do not skip or cache work using directory label digests. |

No no-change, ignored-error, ignored-mount or ignored-missing-file mode is
enabled. Failures emit a fixed phase/reason marker and exit with failure; the
program does not print a boot-success marker or continue with another command.

The frozen 6.12 source explicitly includes `rootfs` among the special genfs
filesystems eligible for SELinux inode relabelling. This closes the source-level
question of whether an initramfs can acquire runtime labels, but the actual
relabel operation still requires the new VM test.

### Matching the installed libselinux, including Fedora patches

The implementation compiles against headers extracted from the actual
[libselinux-devel-3.11-5.fc45 ARM64 RPM](https://kojipkgs.fedoraproject.org/packages/libselinux/3.11/5.fc45/aarch64/libselinux-devel-3.11-5.fc45.aarch64.rpm),
SHA-256
`60383ef415eee73f0f2cad12e81010f6a6c2bf810dfed7b3c61f585ea772e6da`.
The package was extracted as data; it was not installed into a rootfs or host.

The corresponding
[libselinux source RPM](https://kojipkgs.fedoraproject.org/packages/libselinux/3.11/5.fc45/src/libselinux-3.11-5.fc45.src.rpm)
is 408,679 bytes, SHA-256
`7a1e9a263681aa698203601e1738bc5312c6f4b0812ec012a0b87b3f0088f4fd`.
Its four Fedora patches were actually applied in a new analysis directory with
the spec's strip level. All applied successfully. The resulting `restorecon.h`
and `label.h` exactly match the development package headers. The small header
difference from the unpatched release was part of Fedora's SHA-2 change.

The patched `selinux_restorecon_default_handle()` requests a digest but does
**not** enable `SELABEL_OPT_VALIDATE`. `selabel_lookup_raw()` does not request
context translation. Thus the two pre-load raw file-context lookups do not
require validation against an already loaded kernel policy. This finding was
checked in the actual patched source, not inferred from the API-only test.

The patched restorecon source has SHA-256
`f90098e435b4c270bc1e11a9a5aabfef67beafdc4cf680b09ad706b5caaed6a0`;
its label dispatcher has SHA-256
`1b1394617ba13252c5cfad0850c1dffe0fd5ddaab412f5ed0057d70f9506ea43`.
The standard load-policy implementation retains SHA-256
`8c8402d292d74e6bfc887415953802af589183de580b4022186e450cb441bbf1`.

One earlier package-identity query used PRoot only against the retained
research4-v3 root, with `/proc` and `/dev/null` binds. It did not use the frozen
research1 source tree. There was no whole-tree metadata comparison around that
query, so it is not evidence that the entire research4-v3 directory tree was
untouched. The access-vector and native helper checks reported below used
direct QEMU instead. The separate
[PRoot copy follow-up](selinux-query-copy-followup.md) explains why a query's
read-only intent must not be extended to PRoot bind-placeholder metadata.

## Library closure and archive qualification

The helper's ELF interpreter is `/lib/ld-linux-aarch64.so.1`; its direct
`DT_NEEDED` entries are `libc.so.6` and `ld-linux-aarch64.so.1`.
The highest requested GLIBC version is 2.34. It has no RPATH or RUNPATH override.
The native compiler uses the existing Debian cross-toolchain; the runtime test
uses the fixed Fedora ARM64 libraries. Those are separate, recorded inputs.

Two dynamic edges must be included explicitly:

```text
/init → /usr/lib64/libselinux.so.1
libselinux.so.1 → libsepol.so.2
```

The second is required for the normal policy-version adaptation. Relying only
on `DT_NEEDED` would miss both edges.

| Runtime payload | Bytes | SHA-256 prefix |
|---|---:|---|
| `libselinux.so.1` | 270,480 | `c9edfec980b8` |
| `libsepol.so.2` | 802,880 | `46dbfe1a0888` |
| `libpcre2-8.so.0.15.0` | 662,552 | `7f08df34d1ea` |
| `libgcc_s-16-20260819.so.1` | 137,000 | `ac02fe32df90` |
| `libc.so.6` | 2,303,728 | `620f6221d0cb` |
| `ld-linux-aarch64.so.1` | 928,784 | `8821728d1572` |

The evidence JSON gives complete hashes, SONAME symlinks and recursive
dependencies. The API implementation does not require external `load_policy`,
`restorecon`/`setfiles`, `libaudit`, or `semanage.conf`. It requires the complete
unchanged targeted contexts directory, the unchanged config, the original
`policy.35`, and the runtime closure above.

The separate
[early-policy archive checker](../../../scripts/research/input/system-integration/verify_early_policy_initramfs.py)
preserves the frozen old verifier and old archive as mandatory inputs. It
derives the new library/cache mapping from those sources and the explicit
dynamic edges, checks the saved original systemd symlink and old userspace ELF
payloads, requires the complete policy/context set, and verifies the same 69
firmware payloads. Its initial native parsing preflight is useful static
evidence, not a production archive or PID 1 pass.

## Actual build and limited execution

Both builds ran in the isolated SSD container, in new directories underneath
`/work/early-selinux-bootstrap-20261123`. They used GCC 14.2.0, binutils 2.44,
and the installed ARM64 cross libc development package. No package installation
or frozen kernel/source modification was needed.

| Check | Observed result | Scope |
|---|---|---|
| First compilation | Exit 0; 1.459 seconds; no diagnostics | ARM64 ELF construction |
| Public recipe, fresh output directory | Exit 0; 0.217 seconds | Same compiler/container and fixed inputs |
| Compare the two ELFs | Identical size and SHA-256 | This bootstrap only |
| Explicit ARM QEMU `--check-api` | Exit 0, all fixed symbols found, flags `0x828c` | No policy load or mounts |
| Explicit ARM QEMU, no arguments, non-PID 1 | Exit 1 with the expected entry guard | No bootstrap side effects |
| Full production PID 1/system VM | Pending in the independent integration work | Required before a runtime claim |
| Owner tablet | Not attempted | Zero owner Linux passes |

The ARM userspace checks used direct `qemu-aarch64 -L` against the retained
research4-v3 Fedora root. They did not use PRoot. The `--check-api` mode is
unavailable to PID 1 and cannot be used as an alternate boot-success path.

Source SHA-256:
`6006a0fade3e9e8cc9201b5549cab3339961931feadb842c0f3d5863dc383726`.
Recipe SHA-256:
`5ed18306782a44b20c6bf022976c6dc029b0829ec5a72352575ae35440fb493d`.
The exact ELF is retained in both builders at:

```text
/work/early-selinux-bootstrap-20261123/build-01/early-init
```

The public recipe's matching copy is in the SSD builder at
`/work/early-selinux-bootstrap-20261123/rebuild-01/early-init`.

To repeat the isolated build, use a new output directory in the same qualified
container after the repository inputs have been synchronized:

```sh
python3 /src/scripts/research/selinux/build_early_init.py \
  --repo /src \
  --work /work/early-selinux-bootstrap-reproduce-01 \
  --cache /work/early-selinux-bootstrap-20261123
```

This command builds and inspects a regular file. It does not start the bootstrap
or alter an installed system.

## Required runtime checks

The next independent candidate must retain the original Enforcing policy and
all prior kernel, module, firmware, bus, pids and BPF guards. In addition:

- Qualify the actual production archive, including the native `/init`, complete
  policy/contexts, both dynamic-library edges and target loader cache.
- Observe successful policy loading and the two actual executable-label markers
  from the helper. Confirm enforcement stays enabled.
- In the initramfs, read actual PID 1 and udevd process contexts after execution,
  bind that evidence to the boot ID, and verify it again after switching root.
  File-label lookup alone is not process-domain evidence.
- Preserve the complete zero-AVC gate. Reject a lost `event-serialization`
  descriptor. If the old udevd recorded a nonempty serialized queue, require
  evidence that the new udevd received and restored it; an empty queue does not
  require inventing a positive event count.
- Re-run the real system-bus and descriptor-passing path, followed by the actual
  pids and BPF filesystem-denial tests. This startup fix does not exempt them.

These are generic system-VM checks. Physical tablet entry, a proven USB/recovery
control path, native display/input/GPU, radio selection, power management and
performance remain separate owner-device gates.
