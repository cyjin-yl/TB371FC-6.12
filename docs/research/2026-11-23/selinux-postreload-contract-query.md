# Postreload label and same-domain context contracts

## Result

The independently built **map-only** policy candidate permits the queried
standard device-node and `/run` relabel operations, and permits journald's
queried file operations on the intended `syslogd_var_run_t` label. It still
denies **`init_t` to itself, `process:setcurrent` and `process:dyntransition`**.
Those two denials matter to the first normal `setcon_raw()` call after the
already-labeled systemd executable starts.

This is a source and **offline candidate-policy** finding. No new VM was
started, no live policy was loaded, and no new panic or successful reboot is
claimed. The query process exited zero because it completed all 53 AV calls;
the candidate's required permission contract is explicitly **incomplete**.

Complete return codes, raw decisions, commands and source excerpts are in
[selinux-postreload-contract-query.json](evidence/selinux-postreload-contract-query.json).
The earlier management-domain investigation remains separately frozen in
[selinux-runtime-contract-query.md](selinux-runtime-contract-query.md).

## Exact input and execution

| Item | Bytes | SHA-256 |
|---|---:|---|
| New candidate version 35 policy | 3,835,432 | `0dd46af3240a02d1c7399c46facf30cce2a71a471fb70c0d0f5e58e571e53c74` |
| Its actual in-memory libsepol conversion to version 33 | 3,835,420 | `bfe189488e5b99bd9bdb6571ec5023100be68771a80ebaf2e42e6c51527d83ba` |
| Fixed Fedora AArch64 `libsepol.so.2` | 802,880 | `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |
| New query source | 12,816 | `c2e9f490f44202130271fec12626573d7608be39ca7d04c9ee1bc7d60acbe8aa` |
| Captured stdout JSON | 35,034 | `e4ef29089de87797ccb7eb71a40e33287bcd6c5111da1f16e5a1889424e0f4fe` |

The candidate source was read from
`/work/selinux-reload-map-20261123/build-02/candidate/etc/selinux/targeted/policy/policy.35`.
The query used hash-checked private copies in
`/work/selinux-postreload-contract-v1/inputs`, direct QEMU with the qualified
Fedora v3 Python/runtime prefix, and `-I -B`. It completed in **5.912 seconds**,
exit **0**, with empty stderr. Every individual AV API returned zero.

The new `bfe189…` conversion is neither the earlier stock-policy conversion
`aab7…` nor the earlier VM's `9c79…` in-memory export. No equivalence between
those identities is assumed. The source, actual conversion identity and all
runtime dependencies are recorded in the JSON. Public executable source is
[query_postreload_contract.py](../../../scripts/research/selinux/query_postreload_contract.py).

## Queried labeling contract

The companion file-context audit identified these intended targets:

| Path or pattern | Intended type |
|---|---|
| `/dev/null` | `null_device_t` |
| `/dev/kmsg` | `kmsg_device_t` |
| `/dev/shm` directory | `tmpfs_t` |
| `/run` directory | `var_run_t` |
| `/run/log(/.*)?`, including the journal subtree | `syslogd_var_run_t` |

The query checked permission relationships for these labels. It did not
observe that any particular runtime path already had, or subsequently acquired,
one of them. In particular, the `syslogd_tmpfs_t` source cases cover a possible
preexisting object; they are not proof of its existence in a future boot.

| Relationship | Queried permissions | Offline result |
|---|---|---|
| `init_t` → `device_t:chr_file` | `getattr`, `relabelfrom` | Allow |
| `init_t` → `null_device_t` / `kmsg_device_t:chr_file` | `getattr`, `relabelto` | Allow |
| Null/kmsg object types → `device_t:filesystem` | `associate` | Allow |
| `init_t` → `tmpfs_t` / `syslogd_tmpfs_t:dir` | `getattr`, `search`, `relabelfrom` | Allow |
| `init_t` → those same source types as `file` | `getattr`, `relabelfrom` | Allow |
| `init_t` → `var_run_t` / `syslogd_var_run_t` / `tmpfs_t:dir` | `getattr`, `search`, `relabelto` | Allow |
| Those target object types → `tmpfs_t:filesystem` | `associate` | Allow |
| `init_t` → `syslogd_var_run_t:file` | `getattr`, `relabelto` | Allow |
| `syslogd_t` → `syslogd_var_run_t:file` | `create`, `open`, `read`, `write`, `append`, `getattr`, `map` | Allow |
| `syslogd_t` → `syslogd_var_run_t:dir` | `search`, `add_name`, `write`, `open`, `read`, `getattr` | Allow |
| `init_t` → `semanage_store_t:file` | `read`, `open`, `getattr`, `map` | Allow in this candidate |
| `init_t` → `security_t:security` | `load_policy` | Allow |
| `syslogd_t` → old `syslogd_tmpfs_t:file` | `map` | **Deny; diagnostic control** |

The old journal-label denial was retained as a diagnostic. It was not changed
into an allow and was not hidden by the successful results for the intended
label. A future boot still needs actual label readbacks and working journal
operations; a static permission table cannot prove that relabeling ran.

## The remaining same-domain `setcon` issue

Two additional AV rows both deny access, with the type-enforcement reason bit
and successful API return codes:

| Source and target | Class | Permission | Result |
|---|---|---|---|
| `system_u:system_r:init_t:s0` → itself | `process` | `setcurrent` | **Deny** |
| The same source and target | `process` | `dyntransition` | **Deny** |

The fixed Linux 6.12.114 source does not bypass these checks merely because the
requested SID equals the current SID. `selinux_lsm_setattr()` first checks
`PROCESS__SETCURRENT` for the current-attribute operation. Its current-context
branch later checks `PROCESS__DYNTRANSITION` between the current and requested
SIDs. The evidence includes those exact source excerpts from the research4
`security/selinux/hooks.c`, SHA-256
`6079b88f15ca1966b640753e35edc291139fe925fca37e5c54d0a2d6e36d8370`.

The matching Fedora libselinux implementation also requires care. Its
`procattr.c` has a same-value setter cache, but `prev_current` starts as
`UNSET` after exec. `getcon_raw()` can read the current context without filling
that setter cache. The first `setcon_raw()` therefore opens the current
attribute for writing and writes it; only a successful write fills the cache.
An earlier read of `init_t` does not make that first setter call a harmless
userspace no-op.

That source is the qualified Fedora-patched libselinux 3.11
`/work/early-selinux-bootstrap-20261123/patched-libselinux/libselinux-3.11/src/procattr.c`,
7,558 bytes, SHA-256
`cbbc16d3879fbad25e5fbaf3a635272262d8aab8086c2fd0d572741b1b84464f`.
Its cache initialization, getter, setter and successful-write paths are
included in the evidence. The companion systemd audit owns the precise
boot-time call sequence; this report establishes the candidate AV and the
kernel/libselinux checks reached by the first such call.

The concrete conclusion is that **the map-only candidate cannot yet be treated
as a complete postreload contract**. This task did not add the two permissions,
change systemd, change the bootstrap, or execute that path in a VM. A subsequent
independent correction must preserve this candidate and its result, establish
its own source/policy identity, and be verified through the real Enforcing
boot. No source or result from the earlier frozen investigations was edited.

The direct QEMU query has ended. It left no mount, PRoot session, background
query process or new VM running.
