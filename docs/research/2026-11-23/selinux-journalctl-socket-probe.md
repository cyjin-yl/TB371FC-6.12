# Journalctl's socket-xattr probe: the remaining V8 AVC

## Finding and scope

The fixed Fedora 45 systemd 262.1 client has a source-supported reason to create
an otherwise unused Unix datagram socket during `journalctl --sync`: its Varlink
connection code probes whether socket inodes support user extended attributes.
The retained V8 policy denies `journalctl_t` permission to create that socket.
This matches the sole V8 AVC, including the anonymous socket class, the subject
and target domain, and the socket system-call arguments.

The smallest source-supported addition for this fixed Linux 6.12.114 candidate
is one permission:

```cil
(allow journalctl_t self (unix_dgram_socket (create)))
```

No attribute-access permission is needed by this probe on the fixed R4 kernel.
Its VFS rejects `user.*` attributes on a socket before either SELinux attribute
hook. The helper also does not bind, connect, or transmit through this temporary
socket. Those facts support preserving the existing denials for attributes,
data transfer, socket options, and `net_admin`.

This is a fixed-source diagnosis plus an effective-access query on **actually
retained V8 kernel-exported policy bytes**. It is not a captured runtime call
stack, a replacement VM result, or an owner-tablet Linux test. The existing V8
result remains a failed qualification because its controller correctly rejected
one raw AVC. All source identities, selected lines, and interpretation limits
are in the [investigation evidence](evidence/selinux-journalctl-socket-probe.json).

## What V8 actually recorded

At guest time `138.067420`, audit event `73` reported:

```text
avc: denied { create } for pid=345 comm="journalctl"
scontext=system_u:system_r:journalctl_t:s0
tcontext=system_u:system_r:journalctl_t:s0
tclass=unix_dgram_socket permissive=0
```

The associated AArch64 system call was `socket(1, 0x80002, 0)`, returning `-13`:
`AF_UNIX`, `SOCK_DGRAM | SOCK_CLOEXEC`, and `EACCES`. There was no pathname,
device, or inode field for this denied anonymous-socket creation. The recorded
command was `/usr/bin/journalctl --sync`.

This happened on the successful behavioral-test path, after the BPF test had
actually denied the worker's direct `/proc` open with `EPERM`. The sync command
then returned zero with empty standard output and standard error. A successful
command exit did not override the independent full-log AVC rejection.

The complete raw log has 1,395,418 bytes and SHA-256
`a88df1ce7489884a0c228a4a2a0320c4dc2c2f425b2a769b88c1f170823f3534`.
The three records belonging to audit event `73` are retained together in the
investigation JSON. See the unchanged
[V8 failed-run log](evidence/fedora-r4e-persistent-result-failed-verify.log) and
[controller result](evidence/fedora-r4e-persistent-result-failed-verify.json).

V8's clean QEMU exit, qualified persistent result, passing guest behavioral
gates, and zero detected audit-loss or suppression counters remain useful
observations. None makes the overall failed run pass. The raw log did not record
the client instruction pointer, stack, or complete environment; this report
does not invent those observations.

## Fixed source and the relevant call path

The source archive was extracted from the existing Fedora
`systemd-262.1-1.fc45.src.rpm`, 19,165,235 bytes, SHA-256
`de8e6ebb2fb7b7aa0e1297c0c27c3339d15c37b24b57ca16a762483580ea7168`.
Its embedded `systemd-262.1.tar.gz` has 19,088,198 bytes and SHA-256
`100fc873b848b9b0297d8a705e8e2ed326256c8483d9960ee1ffe264c8a5c3e3`.
The three packaging patches were inspected; they do not change the client,
socket-xattr probe, or xattr-wrapper files used below. Exact member identities
are recorded alongside the excerpts in the
[source evidence](evidence/selinux-journalctl-socket-probe.json).

| Step | Fixed source | Consequence |
| --- | --- | --- |
| Select sync action | `src/journal/journalctl.c`, `ACTION_SYNC` branch | Calls `action_sync()` after normal client initialization. |
| Connect to journald | `src/journal/journalctl-varlink.c`, `varlink_connect_journal()` and `action_sync()` | Uses `/run/systemd/journal/io.systemd.journal`, then calls `io.systemd.Journal.Synchronize`. |
| Establish the transport | `src/libsystemd/sd-json/json-stream.c`, lines 181–220 | Creates and connects a Unix **stream** socket. This is distinct from the denied temporary datagram socket. |
| Mark a connected client | `src/libsystemd/sd-varlink/sd-varlink.c`, lines 189–209 | After a successful connection, calls `mark_varlink_socket(..., "client")` and deliberately ignores its result. |
| Check the feature | The same file, lines 162–187 | Calls `socket_xattr_supported()` before attempting `user.varlink`. A false result returns `EOPNOTSUPP` without marking the connected socket. |
| Probe an expendable socket | `src/basic/socket-util.c`, lines 1900–1922 | Creates `AF_UNIX, SOCK_DGRAM | SOCK_CLOEXEC`, tries `user.testxxx`, caches unsupported on `EPERM` or a supported “not supported” error, then closes the temporary fd. |

This source path explains how sync can succeed while an optional probe produces
an AVC: the connected Varlink client ignores the marking error and continues
with the sync request. The retained log proves the denied syscall and final
command result; the source identifies the matching probe on the successful
connection path. These two evidence scopes are kept separate.

## Why `getattr` and `setattr` remain denied

The xattr wrapper deserves a complete check because it performs a read before
the attempted write. `xsetxattr()` calls `xsetxattr_full(..., SIZE_MAX, 0)`.
With zero xattr flags, `xsetxattr_full()` first tries to read the current value so
it can avoid an unnecessary write. The probe supplies a normal fd, a null path,
and `AT_EMPTY_PATH`.

`normalize_and_maybe_pin_inode()` therefore uses `fd_is_opath()`; the fixed
`fd-util.c` implementation at lines 903–913 only calls `fcntl(F_GETFL)` and
checks `O_PATH`. It does not call `fstat`. Because this socket fd is not an
`O_PATH` descriptor, the wrapper directly uses `fgetxattr()` and `fsetxattr()`.
The newer `setxattrat()` branch requires a nonempty path and is not taken here.

The fixed R4 source is
`/work/research4-system/source-input/linux-6.12.114-input-integration`.
Its `fs/xattr.c` has 37,463 bytes and SHA-256
`9056f9f49ec11d5afa10c500269f0c159dea5a68f285dc05eb597b6c7316f858`.
Its `net/socket.c` assigns `S_IFSOCK` to the anonymous socket inode in
`sock_alloc()`. The relevant VFS ordering is:

| Operation in this probe | Fixed R4 check order | Result before the SELinux hook |
| --- | --- | --- |
| Read `user.testxxx` | `vfs_getxattr()` calls `xattr_permission(..., MAY_READ)` before `security_inode_getxattr()` | `ENODATA`: a socket is neither a regular file nor a directory. |
| Write `user.testxxx` | `__vfs_setxattr_locked()` calls `xattr_permission(..., MAY_WRITE)` before `security_inode_setxattr()` | `EPERM` for the same socket-inode restriction. |

The `user.*` restriction is at `fs/xattr.c` lines 146–148. It also precedes the
final `inode_permission()` call. The failed pre-read does not skip the write;
the write then returns the `EPERM` that `socket_xattr_supported()` recognizes
as an unsupported feature. Consequently there is no SELinux xattr access to
authorize on this temporary socket in this fixed kernel path. The full wrapper
and VFS excerpts are retained in the
[investigation evidence](evidence/selinux-journalctl-socket-probe.json).

This conclusion is specific to the frozen 6.12.114 R4 source. The systemd probe
itself anticipates newer Linux socket-xattr support. A future kernel that
changes that VFS behavior needs a fresh access-contract review.

## Exact effective-policy query

The input was the real policy exported during V8, subsequently retained from
the closed image with read-only `debugfs`. No new VM, filesystem replay, or
kernel-policy load was used to obtain it. Its ordinary-file identity is:

| Input | Size | SHA-256 |
| --- | ---: | --- |
| V8 `loaded-policy.33` | 3,835,444 | `9d7aa2b3d3c64e8c24dbff83e8850036b8e15cec63aaa1521bbea555f42b2342` |
| Fixed Fedora ARM64 `libsepol.so.2` | 802,880 | `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |

The [query source](../../../scripts/research/selinux/socket-probe/query_journalctl_socket_probe.py)
has SHA-256
`fb51735ec147fee035c0fe091d6f3172fdef0b5c1290d0fab072457c444837ec`.
It accepts only those fixed version-33 bytes, does not convert their version,
and uses libsepol's userspace services API in private process memory. The
qualified AArch64 ABI uses a 20-byte access-decision structure. Invalid context,
class, permission, or API returns fail the query; they are never converted into
a normal access denial.

The single execution began at `2026-11-23T08:26:29.494404+00:00`, ended at
`08:26:38.465724+00:00`, and exited zero after 8.971320 seconds. It completed 19
unique permission queries: **6 ALLOW and 13 DENY**. Zero means this diagnostic
query completed, not that the policy had been repaired. The exact
[stdout JSON](evidence/selinux-journalctl-socket-probe-query.json) and
[execution record](evidence/selinux-journalctl-socket-probe-execution.json)
are preserved as separate original-byte files.

| Query group | Effective result | Interpretation |
| --- | --- | --- |
| `journalctl_t` → itself, `unix_dgram_socket:create` | DENY | Matches the actual V8 denial; the one new candidate permission. |
| Same socket, `getattr` and `setattr` | Both DENY | Preserved diagnostic controls; the fixed VFS returns before these LSM checks. |
| Same socket, `connect`, `bind`, `read`, `write`, `getopt`, `setopt` | All six DENY | The temporary feature probe needs none of these operations. |
| `journalctl_t` → itself, `capability:net_admin` | DENY | No capability is required for the reviewed probe. |
| Earlier six reviewed standard-service permissions | All six ALLOW | Map, same-domain `setcurrent`/`dyntransition`, registry unlink, journald socket write, and stream `connectto` remain effective. |
| Retained security controls | All three DENY | PID1 policy export, the old journal temporary-file map, and broker-to-`unconfined_service_t` FIFO write remain restricted. |

The broker control uses its observed full MLS range,
`system_u:system_r:system_dbusd_t:s0-s0:c0.c1023`. The JSON retains `auditdeny`
separately from `allowed`; a silent-denial mask does not prove that a particular
unobserved call was attempted.

## Alternative paths and evidence limits

The investigation also inspected ordinary logging and final status-notification
paths. A pipe on stderr alone does not prove that the journal logging backend
is selected. The inspected path uses `JOURNAL_STREAM` identity checks.
`main_finalize()` can call `sd_notifyf()`, but the notification implementation
checks `NOTIFY_SOCKET` before creating its socket. The frozen validation unit
was a oneshot without an explicit notification setup; V8 did not capture the
child's complete environment. These remain inspected conditional paths, not
invented runtime callers.

The proposed fix does not change the environment, suppress messages, ignore the
AVC, or grant datagram transmission permissions. The source-supported feature
probe and effective policy are sufficient to prepare the single-permission
candidate; a later independent VM must still demonstrate a clean complete log.

Shared-relay timeouts and rate limiting, the initially truncated source packet,
and an absent assumed `main-func.c` extraction path were retained as collection
failures. Complete member identities were subsequently checked against the
fixed SRPM. The original query was not repeated after its bridge timeout:
existing exit metadata and stdout established that the one execution completed.

The new policy build and candidate qualification are recorded independently in
[the socket-probe policy report](selinux-socket-probe-policy.md). Neither report
changes the frozen V8 failure or any owner-tablet acceptance case.
