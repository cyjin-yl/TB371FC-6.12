# Socket-xattr probe policy candidate: one additional permission

## Qualified offline result

A new policy candidate was built from the fixed original Fedora policy store
and qualified offline. Relative to the previously reviewed six-permission
candidate, it adds exactly:

```cil
(allow journalctl_t self (unix_dgram_socket (create)))
```

The complete version-35 and fresh version-33 CIL comparisons passed. In both
versions, removing this one new rule makes the entire export byte-identical to
the previous candidate. The subsequent 19 effective-access queries also passed:
the existing six permissions plus this new permission are allowed, while all
twelve retained or diagnostic negative controls remain denied.

This is a **host build and offline policy qualification**, not a replacement VM
pass. No kernel policy was loaded, no enforcement mode or boolean was changed,
and no owner-tablet action occurred. The original V8 remains failed. Its sole
AVC and the fixed source reason for the permission are documented separately in
[the socket-probe investigation](selinux-journalctl-socket-probe.md).
The complete qualification metadata is in
[the evidence JSON](evidence/selinux-socket-probe-policy.json).

## Artifact identities

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| New candidate `policy.35` | 3,835,468 | `ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798` |
| New candidate, fresh userspace serialization to version 33 | 3,835,456 | `fe71750b659e71969145d89d08153196f21b46e6d66c6f28e09f8b11e739e53e` |
| Previous six-permission `policy.35`, comparison baseline | 3,835,456 | `727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502` |
| Previous candidate, independently fresh serialization to version 33 | 3,835,444 | `9b39b5a59771bf3f7ac1119979ac09ca7c579fd5504b57f2970008b6ee200afe` |

The new version-35 file is mode `0644` at:

```text
/work/selinux-socket-probe-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35
```

The new version-33 file is at:

```text
/work/selinux-socket-probe-20261123/compare-01/candidate-converted-v33.policy
```

Both are ordinary files in the existing HDD build container. The fresh
version-33 identity is an offline serialization identity. It is **not** V8's
actual exported `9d7aa2b3…` policy and is not a predicted identity for a future
kernel export. A later VM must record and retain its own actual exported bytes.

## Build isolation and exact inputs

The new [build recipe](../../../scripts/research/selinux/socket-probe/build_policy.py)
is a narrow derivation of the frozen standard-service recipe. It accepts exactly
the following six CIL rules, comprising seven permissions relative to stock:

```cil
(allow init_t semanage_store_t (file (map)))
(allow init_t init_t (process (setcurrent dyntransition)))
(allow init_t systemd_varlink_registry_t (lnk_file (unlink)))
(allow journalctl_t syslogd_var_run_t (sock_file (write)))
(allow journalctl_t syslogd_t (unix_stream_socket (connectto)))
(allow journalctl_t self (unix_dgram_socket (create)))
```

The module is preserved as
[tb371fc_socket_probe.cil](../../../scripts/research/selinux/socket-probe/tb371fc_socket_probe.cil),
344 bytes, SHA-256
`72a3dc94296a5b99b6c6b2cd6fc376f88129c73c211035065e6109f44eaf3cde`.
The old six-permission module and its executed records were not edited.

The build copied the original `etc/selinux` and
`var/lib/selinux/targeted` subtrees from the qualified v3 root into a new private
candidate prefix. It started from the stock `policy.35` with SHA-256
`928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430`,
not from an accumulated edited store. The complete source-content inventory
matched the previously fixed
`c0070c6fb7f209ed7e391d4707a1058caedbaf1ad96c076a17624661e5558b50`.

The fixed ARM64 `semodule`, `setfiles`, `sefcontext_compile`, libsemanage,
libselinux, and libsepol files and their recursive ELF dependency closure were
copied into the independent tool root. Explicit QEMU user emulation ran
`semodule -n` against the new store; the helper wrapper rejects every
`load_policy` invocation. There was no PRoot, host `binfmt` registration,
filesystem relabel, or VM in this experiment.

Before/after inventories proved that the two source policy/store subtrees kept
their content, modes, ownership, symlink targets, mtime, and ctime. The
inventory does not make an atime promise. The independent candidate store
changed only the policy payloads and the expected semodule transaction/module
metadata. Original-byte build metadata, helper invocations, input pins, and
the changed-path inventory are in the
[build result](evidence/selinux-socket-probe-policy-build.json).

## Complete semantic comparison

The [comparison recipe](../../../scripts/research/selinux/socket-probe/compare_policy.py)
uses the fixed Fedora ARM64 libsepol 3.11. It accepts the previous candidate only
at its exact `727cd98e…` identity and the newly recorded candidate identity.
For each policy it exports the full version-35 policy to CIL, then parses a
fresh independent copy, serializes it to version 33, and exports that complete
policy to CIL as well. The conversion does not reuse a policy database that the
exporter may already have reordered.

For each version, the comparison requires one unique new merged allow rule,
with exactly `create`, no removed permissions, and no extra permission on that
tuple. Replacing that line with its original absent form must restore **all**
exported bytes. This covers other access rules, types and attributes,
constraints, booleans, permissive declarations, MLS content, and policy
capabilities, rather than examining only a convenient subset of allow rules.

| Complete CIL export | Bytes | Lines | SHA-256 |
| --- | ---: | ---: | --- |
| Previous candidate, both 35 and fresh 33 | 26,816,215 | 356,735 | `74839737f1c0dd679cbe3d288bdb8e1342816f71dcd18d9114565ef8cc2b8501` |
| New candidate, both 35 and fresh 33 | 26,816,270 | 356,736 | `6d81bc7ebf3cab9bfe047436c8a4591877e894effad33ea5e81d99cc5549d53e` |

The extra 55 CIL bytes are exactly the single new rule and its newline. The
comparison passed for both versions. In particular, the old six permissions
remain unchanged, no cross-type process transition was added, and no socket
attribute, send/receive, option, or capability rule was added. The full result
and artifact identities are retained in the
[comparison JSON](evidence/selinux-socket-probe-policy-compare.json).

## Effective-access qualification

The complete CIL check was followed by one independently executed access-query
job. Its [candidate query source](../../../scripts/research/selinux/socket-probe/query_candidate.py)
derives from the diagnostic query on actual V8 bytes, preserves the same 19
context/class/permission tuples, and accepts the candidate's exact size and
SHA-256 as mandatory arguments. It parses the fresh version-33 bytes into
private libsepol memory, without a kernel-policy operation or another version
conversion.

The [native recording wrapper](../../../scripts/research/selinux/socket-probe/run_candidate_query.py)
pins that fresh policy, the query source, fixed libsepol, QEMU, and the qualified
ARM Python. It makes new private ordinary-file copies, retains exact stdout,
stderr, command and exit metadata, and rechecks the source inputs afterward.
Context or API errors cause failure and are never reported as a normal DENY.

The result was **7 ALLOW and 12 DENY**:

| Contract | Result |
| --- | --- |
| New `journalctl_t` self `unix_dgram_socket:create` | ALLOW |
| Previous policy-map permission | ALLOW |
| Previous same-domain `setcurrent` and `dyntransition` | Both ALLOW |
| Previous registry symlink unlink | ALLOW |
| Previous journald pathname socket write and peer stream `connectto` | Both ALLOW |
| Self datagram `getattr`, `setattr`, `connect`, `bind`, `read`, `write`, `getopt`, `setopt` | All eight DENY |
| Self `capability:net_admin` | DENY |
| `init_t` policy export | DENY |
| `syslogd_t` mapping its previous temporary-file type | DENY |
| Full-range broker writing an `unconfined_service_t` FIFO | DENY |

All fixed contexts were accepted by the policy, including the broker's observed
`s0-s0:c0.c1023` range. `all_candidate_contracts_satisfied` is true, the inputs
were unchanged, and stderr is empty. The candidate query has a stricter exit
contract than the original diagnosis: zero requires both completed queries and
all seven required ALLOW/twelve expected DENY results.

The query began at `2026-11-23T08:58:52.567814+00:00` and ended at
`08:58:57.889633+00:00`, exiting zero after 5.321820 seconds. Its exact
[14,320-byte stdout](evidence/selinux-socket-probe-policy-query.json) has SHA-256
`35e2473b2bbd6526d8b6d823997fcf46fca11d2c8c4ea6b04443d8a1c0b0faa0`.
The separate [execution record](evidence/selinux-socket-probe-policy-query-execution.json)
preserves all input and tool identities.

## Execution and handoff

| Actual persistent job | Exit | Elapsed seconds |
| --- | ---: | ---: |
| `tb371fc-socket-policy-build-01` | 0 | 247.818535 |
| `tb371fc-socket-policy-compare-01` | 0 | 82.594404 |
| `tb371fc-socket-policy-query-01`, including its recording wrapper | 0 | 5.380779 |

The visible tmux session was `tb371fc-socket-probe`, with separate build,
comparison, and query windows. All three jobs have final exit records; there is
no continuing build or query from this work. Job-log sizes and SHA-256 values,
full commands, and source-manifest identities are retained in the
[qualification evidence](evidence/selinux-socket-probe-policy.json).

One combined relay call timed out after 20.9 seconds while installing the new
query and launching comparison. The installation or launch was not repeated.
A later read of the existing fixed source, job records, and results established
that the comparison had completed successfully. Early empty logs were also
retained; a bounded inspection of this job's own pane and processes showed
source-copy/tool preparation progressing. Those transport observations were
not recast as failed policy executions.

The new candidate identity was handed to the independent
[V4 early-loader work](early-selinux-socket-probe-loader.md). A following
complete-system VM still has to prove standard reload, its actual exported
policy, descriptor routing, PID limits, BPF behavior, journal sync, and zero
raw AVC/loss. This offline success does not relax any of those gates or count
as owner/native Linux hardware validation.
