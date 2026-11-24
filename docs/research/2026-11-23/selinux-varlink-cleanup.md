# v7: Varlink cleanup and journal synchronization permission gaps

## Result and scope

The fixed systemd source and two independent effective-permission queries
identify **three required permissions missing from the current policy** for
the two reviewed paths:

| Subject → target type | Class / permission | Evidence |
|---|---|---|
| `init_t` → `systemd_varlink_registry_t` | `lnk_file unlink` | Actual v7 AVC 4 during udev socket cleanup; denied by both queried policies |
| `journalctl_t` → `syslogd_var_run_t` | `sock_file write` | Actual v7 AVC 68 during failure-diagnostic `journalctl --sync`; denied by both queried policies |
| `journalctl_t` → `syslogd_t` | `unix_stream_socket connectto` | Necessary next access check identified from the Unix-stream connection path and effective AV results; **not an observed AVC in this run** |

The source candidate was queried after a private version-33 conversion. The
second query used the **actual, separately preserved v7 kernel-exported
version-33 bytes without conversion**. Both completed 32 API queries with
the same 25 allow and seven deny decisions in this subset. Three denials are
the required gaps above, one is a diagnostic target-socket metadata check,
and three are deliberately retained denial controls.

This is a completed source/permission diagnosis. No policy repair, label
change, new VM, tablet access or hardware acceptance was performed by this
work. The [v7 integration failure](fedora-r4d-reload-fd-failed.md) remains a
separate, unchanged result. In particular, the later journal diagnostic
denial does not explain the independent PL061 assertion that stopped that
integration before its BPF behavior test.

The [complete evidence](evidence/selinux-varlink-cleanup.json) includes both
query outputs, every return code and permission mask, exact execution
metadata, fixed source identities and excerpts, original policy-context
rules, the preserved export record, and the two actual console AVCs.

## What the original v7 log actually records

The inspected raw console is 1,115,806 bytes with SHA-256
`cfe215d2a33dc01f8ffdf7ab5bc2d7dd2f7fafec309d06c82eb3db48bb5658aa`.
It matches the published
[retained raw log](evidence/fedora-r4d-reload-fd-failed-verify.log).

AVC 4 appears at raw-console time **36.352137**, between the udev Varlink
socket's successful deactivation message and its transition from listening
to dead. PID 1 is `init_t`; the denied operation is unlinking the
`systemd_varlink_registry_t` symbolic link named `io.systemd.Udev`.
The actual `dev` field is **`tmpfs`**, not `devtmpfs`.

AVC 68 appears at raw-console time **126.049789**. The process is
`journalctl`, domain `journalctl_t`, and the denied operation is writing the
`syslogd_var_run_t` socket inode named `io.systemd.journal`. The same audit
event also appears inside the diagnostic journal output; that repeated
presentation is not counted as another AVC. This command was part of
failure diagnostics, after the ordinary FD route and PIDs behavior work.

There is **no `connectto` AVC** in this captured run. Its denial is the
source-and-policy prediction of a subsequent gate after the pathname-socket
write permission is repaired. No unexecuted event has been added to the log.

## Udev registration and cleanup are standard socket-unit operations

The audited package is the retained official
[`systemd-262.1-1.fc45.src.rpm`](https://kojipkgs.fedoraproject.org/packages/systemd/262.1/1.fc45/src/systemd-262.1-1.fc45.src.rpm),
19,165,235 bytes, SHA-256
`de8e6ebb2fb7b7aa0e1297c0c27c3339d15c37b24b57ca16a762483580ea7168`.
Its embedded `systemd-262.1.tar.gz` is 19,088,198 bytes with SHA-256
`100fc873b848b9b0297d8a705e8e2ed326256c8483d9960ee1ffe264c8a5c3e3`.
The spec and three included patches were also inspected. Their targets are
UID classification, core userdb setup and machined; none changes the socket
or journal client source used here. The old `26494.patch` spec entry is
conditional on Fedora below 40 and RHEL below 10.

`units/systemd-udevd-varlink.socket` specifies:

```ini
ListenStream=/run/udev/io.systemd.Udev
Symlinks=/run/varlink/registry/io.systemd.Udev /run/udev/control
RemoveOnStop=yes
```

In `src/core/socket.c`, `socket_symlink()` creates these links through the
idempotent symlink helper. If an existing conflicting object is encountered
with `RemoveOnStop` enabled, it also attempts unlink before retrying creation.
During normal socket close, lines 1014–1016 explicitly iterate the configured
links and call `unlink()` when `remove_on_stop` is set. That return value is
discarded, explaining why an AVC can coexist with a successful unit-stop
message. A successful stop message is not evidence that the link was removed.

The original context file assigns `/run/varlink/registry` directories and
their symbolic-link children to `systemd_varlink_registry_t`. The observed
label is consistent with those rules. The original `init` policy module
directly grants creation and attribute inspection of these links, while
effective AV queries also confirm that directory `search`, `write`,
`add_name`, and `remove_name` already pass. Link `create`, `getattr`, and
`read` pass as well. **Only the reviewed link's `unlink` permission is missing
from this lifecycle.** A missing direct CIL statement was not treated as an
effective denial without querying attribute-derived access.

## Journal synchronization uses the correctly labeled Varlink socket

`src/journal/journalctl-varlink.c` establishes the complete direct route:

- `action_sync()` calls `varlink_connect_journal()`.
- With no namespace argument, the address is exactly
  `/run/systemd/journal/io.systemd.journal`.
- The client calls `sd_varlink_connect_address()` and then
  `io.systemd.Journal.Synchronize`.

The original fixed `file_contexts` rule for `/run/systemd/journal(/.*)?`
assigns `syslogd_var_run_t`. Its specific `syslog` and `dev-log` socket
exceptions do not name this Varlink endpoint. Thus the observed label is
consistent with the original package; relabeling it as `devlog_t` would not
be a correction justified by this source.

The Unix-stream route requires access to the pathname socket inode and to
the receiving journald socket domain. Both
`journalctl_t → syslogd_var_run_t:sock_file write` and
`journalctl_t → syslogd_t:unix_stream_socket connectto` are denied in the
candidate and captured-runtime queries. Traversal of the queried parent-directory
types and the client's own socket creation, connection, read and write permissions pass.

### Why target `sock_file getattr` is excluded

The query deliberately includes this additional diagnostic permission, and
it is denied. The source establishes that this fixed `--sync` route does not
need it:

`json_stream_connect_address()` in `src/libsystemd/sd-json/json-stream.c`
creates an ordinary Unix stream socket, formats the address and calls
`connect()` directly. The fixed address fits in `sockaddr_un`; the long-path
`O_PATH` fallback is not selected. It does not `stat` the target pathname.

`json_stream_attach_fds()` subsequently uses `fstat()` and `getsockopt()` on
the **new client socket FD**, not the server's filesystem inode. The query's
`journalctl_t` self `unix_stream_socket getattr/getopt` rows both allow those
operations. They were initially collected in the diagnostic group; this
later source reading establishes their role without changing the recorded
query output. The target `syslogd_var_run_t:sock_file getattr` denial remains
outside the proposed repair.

## Exact queried policies and execution

| Run | Input and treatment | Actual completion |
|---|---|---|
| `query-01` | Fixed combined candidate.35 `e1a63e7e…`, converted privately to `ce6ccbfda…` version 33 | Exit 0, 5.127 seconds, 32 queries |
| `query-02` | Actually preserved v7 export.33 `0fe3c0e1…`, queried directly with no version conversion | Exit 0, 2.180 seconds, 32 queries |

Full identities:

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Combined candidate policy.35 | 3,835,432 | `e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269` |
| Candidate's private version-33 serialization | 3,835,420 | `ce6ccbfda2105de32c6f865e883493a98ee4df848d298b703d55904cae3f9875` |
| Actual preserved v7 export.33 | 3,835,420 | `0fe3c0e16007f42cb15f05e5ec35fe4b20c5d876a7d1219a558fc3593a3a0e29` |
| Fixed Fedora ARM64 libsepol | 802,880 | `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |
| Candidate-query stdout | 29,266 | `145354766a3d82fb3eb8253564bfa5f3def066cf6bafff44c2b613b810b24247` |
| Captured-policy-query stdout | 29,147 | `992067affbc578c601fe050bfb9aad35794e002d129e292113acd2db6e8667a6` |

The actual v7 export is a mode-0600, root-owned ordinary file retained by the
integration runner after its VM stopped. Its
[same-boot identity record](evidence/fedora-r4d-loaded-policy-export.json)
is retained. This audit copied and hashed that file into its own prefix; it
did not open or modify the VM disk image. This new file does not retroactively
supply the previously missing ordinary-file copy of the earlier `9c79…`
in-memory observation.

The [query source](../../../scripts/research/selinux/query_varlink_cleanup_contract.py)
has SHA-256 `99541034b31a6f91d068104b7155a3cab821ba2a50517c422b8bbda3e0e0b7d8`.
It derives the qualified public libsepol ABI/lifecycle from the unchanged
[previous query](../../../scripts/research/selinux/query_postreload_contract_v2.py).
It accepts only the two fixed input identities, checks its actual ARM64
library, and uses process-private policy/SID data. Both runs used explicit
QEMU plus ARM Python with `-I -B`, with no PRoot or R1-rootfs execution.
Their stderr files are empty. Exit zero means the API queries completed;
the three missing permissions remain failures of the reviewed contract.

The two byte-distinct policies have the same decisions for these **32
specific rows**. That observation is not a complete-policy equivalence proof.
The controls still deny PID 1's `security:read_policy`, old
`syslogd_tmpfs_t:file map`, and the broker's write access to an
`unconfined_service_t` FIFO. Previously added PID 1 mapping and same-domain
context-setting permissions remain allowed.

## Minimal candidate delta and remaining work

The source-supported next candidate delta is:

```cil
(allow init_t systemd_varlink_registry_t (lnk_file (unlink)))
(allow journalctl_t syslogd_var_run_t (sock_file (write)))
(allow journalctl_t syslogd_t (unix_stream_socket (connectto)))
```

These are type-based permissions. They are not restricted to one filename
or to the `Synchronize` method. No broad `manage` macro, directory deletion
permission, target-socket `getattr`, label substitution, boolean change or
permissive domain is justified by these findings.

A separate candidate must preserve the original policy and v7 image,
compare its complete semantic delta, and repeat the actual integration
gates. This audit applies none of the proposed rules and does not predict
that fixing these two paths also fixes the PL061 observation or demonstrates
BPF behavior.

## Source and attempt preservation

The source indexes and query records are under the independent
`/work/selinux-varlink-cleanup-query-v1` prefix. The
[first source reader](../../../scripts/research/selinux/inspect_varlink_cleanup_source.py)
and [second reader](../../../scripts/research/selinux/inspect_varlink_cleanup_source_v2.py)
are both retained. The second adds the package's actual `src/journal/`
subtree; it does not rewrite the first capture. Two additional low-level
connection sources were read from the same hash-checked archive and retained
with their exact identities and excerpts.

The initial unavailable-`rg` invocation, an unmatched CPIO member name
without its observed `./` prefix, and one relay timeout are recorded as
access/collection failures. The unmatched extraction failed its archive
digest guard and was not accepted as source evidence. The subsequent source
captures and both AV queries have explicit successful completion records.
All owned jobs have ended; no new background task or device operation is
required to interpret these results.
