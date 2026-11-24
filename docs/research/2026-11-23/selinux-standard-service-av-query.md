# Independent AV qualification of the standard-services policy

## Result and boundary

One actual AArch64 userspace query process qualified the fixed new candidate:
**86 recorded rows, 80 ALLOW, 6 DENY, no required permission denied**. The query
reuses the entire frozen 54-row post-reload contract and 32-row Varlink contract
with explicit group prefixes. It performed one private policy conversion and
one libsepol services-database parse. It did not load a kernel policy, start a
VM, change booleans, run PRoot, mount a disk, execute a service, or access Android.

The three previously missing standard-service permissions are now allowed for
the supplied valid contexts. The target socket's diagnostic getattr remains
denied. The original post-reload and Varlink denial controls remain denied.

Evidence: [complete result and execution record](evidence/selinux-standard-service-av-query.json),
[frozen query source](../../../scripts/research/selinux/standard-services/query_standard_services_contract.py),
[policy construction and full CIL comparison](selinux-standard-service-policy.md),
[prior Varlink diagnosis](selinux-varlink-cleanup.md), and
[prior combined post-reload query](selinux-postreload-combined-query.md).

This is an offline candidate qualification. It does not establish successful
standard services, policy loading, descriptor transfer, BPF enforcement, or
native Linux operation on the TB371FC. Those remain separate same-boot tests.

## Fixed input identities

| Input | Size | SHA-256 |
|---|---:|---|
| New candidate policy35 | 3,835,456 | 727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502 |
| Independently expected and actually produced fresh33 | 3,835,444 | 9b39b5a59771bf3f7ac1119979ac09ca7c579fd5504b57f2970008b6ee200afe |
| AArch64 libsepol | 802,880 | 46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b |
| QEMU userspace interpreter | 16,661,520 | 73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943 |
| Fedora Python resolved executable | 68,968 | a12cb0a1160abfbc59d3336fb3713562977fd862b9a3eafc2553c89b887a8d15 |
| New combined query source | 19,145 | 70c409c787ff613741814e34c71ff802799fc46ccf679c6b70f7406afea61461 |

The actual candidate was copied into a fresh private prefix from
/work/selinux-standard-services-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35.
The library was copied from the previously qualified ordinary query input.
Their complete hashes are checked before the query, inside the query where
applicable, and after completion. The original candidate source file also
retains its original hash.

The actual Python command uses the previously qualified
/work/fedora-input-system-v3/rootfs/usr/bin/python3 symlink. It resolves to
python3.15; this result was recorded instead of assuming the executable
version. The direct QEMU -L closure is the existing v3 Fedora tree. Python
runs with -I -B. There is no PRoot bind-target creation and no execution in the
frozen R1 rootfs.

## Source preservation and ABI

The new source retains the typed public API and lifecycle from frozen
query_postreload_contract_v2.py, SHA
3c23c6d1a4c8cd289a5a4b1bb09ec6351cbf4bae835369e818ce494f13ec3ad1.
Its post-reload matrix is preserved with a group prefix. The second matrix is
extracted without changing its context/class/permission entries from frozen
query_varlink_cleanup_contract.py, SHA
99541034b31a6f91d068104b7155a3cab821ba2a50517c422b8bbda3e0e0b7d8.

The source requires the fixed 35 input, AArch64 ELF library and ABI, 20-byte
AV-decision structure, and exact converted33 identity. It uses libsepol's
process-private policy database and sepol_context_to_sid() to validate the
full user/role/type/MLS context strings. Nonzero API returns are errors, not
permission denials. Allowed bits and audit-denial masks are recorded separately.
No libselinux function or kernel policy interface is called.

Five actual tuples occur in both historical matrices. Two more are repeated
inside the original post-reload matrix because tmpfs_t is both a relabel source
and a target. All original rows are intentionally retained: 86 rows represent
**79 unique AV tuples**. The 73 required-allow rows represent 68 unique required
tuples. Counting preserved rows does not imply 86 distinct permissions or
independent runs.

## Required changes and controls

| Effective query | New candidate | Classification |
|---|---|---|
| init_t to systemd_varlink_registry_t, lnk_file unlink | ALLOW | Required registry cleanup |
| journalctl_t to syslogd_var_run_t, sock_file write | ALLOW | Required connection through the correctly labelled endpoint |
| journalctl_t to syslogd_t, unix_stream_socket connectto | ALLOW | Required next connection check |
| init_t to semanage_store_t, file map | ALLOW | Prior standard policy-reload requirement |
| init_t to init_t, process setcurrent | ALLOW | Prior standard same-domain setcon requirement |
| init_t to init_t, process dyntransition | ALLOW | Prior standard same-domain setcon requirement |
| journalctl_t to syslogd_var_run_t, sock_file getattr | DENY | Diagnostic-only permission deliberately not added |
| init_t to security_t, security read_policy | DENY | Retained manager export restriction |
| syslogd_t to syslogd_tmpfs_t, file map | DENY | Retained old-label restriction |
| system_dbusd_t to unconfined_service_t, fifo_file write | DENY | Retained former service-domain restriction |

The exact full contexts are present in every JSON row. The broker control
uses system_u:system_r:system_dbusd_t:s0-s0:c0.c1023; the process contexts in
the other rows use the fixed system role and s0 range. Object contexts use
object_r. Validating these supplied contexts is not an observation of a live
process, socket, directory, or descriptor.

The rest of the post-reload matrix verifies device and /run relabel source
and target permissions, filesystem association, journal access, policy-file
read/open/getattr/map, and policy load. The full Varlink matrix retains registry
directory lifecycle/traversal, symlink creation/read/getattr, client socket
operations, journal parent traversal, diagnostics, and controls. All required
rows pass. The six DENY rows are two control tuples repeated across the two
matrices, the third unique control, and the target getattr diagnostic;
none is a required permission denial.

## Actual execution

The single query completed on 2026-11-23 at 07:32:52 UTC:

- Process exit: 0.
- Elapsed wall time: 6.065733732 seconds.
- Standard error: empty.
- Standard output: 63,262 bytes, SHA-256
  274ed15ffc4191d427c7236a65a3e011a02a52cd163b06d1c00ce6f1e62bcbd7.
- Execution metadata SHA-256:
  01d7a1a68144d8d1f1cae9c201718b387d0524edbc41564369bd8e63353f4d4c.
- Every named contract gate is true, including all three new permissions,
  both post-reload controls, all three Varlink controls, and the target
  socket getattr denial.

The retained ordinary files are under
/work/selinux-standard-services-av-20261123/query-01/.
The JSON embeds the complete query result, raw-output identities, actual
command, execution metadata, input manifest, and source construction records.

One earlier metadata-only read guessed a nonexistent python3.14 path and
exited 1. It created no query and ran no ARM program. The actual command uses
the pre-existing qualified python3 path after recording its real target.
This preparation error is preserved and is separate from the successful
single AV execution.

The local shared execution environment was unavailable during this work.
Construction, qualification, and report retention therefore used only the
already authorized build container and a new isolated prefix. No remote
public repository file was changed. This report/source bundle is prepared
for the parent's later normal synchronization.

## Remaining runtime gates

The converted33 identity is the expected fresh serialization of this
candidate, not a kernel-export identity. Full CIL comparison is separate
evidence; this query additionally checks these concrete effective decisions
and context validity. Neither proves the eventual runtime boolean state,
service domains, file labels, FD opener/inode identities, or every policy
permission outside this matrix.

A subsequent VM must independently record the actual exported loaded policy,
perform its same-boot AV and context checks, exercise all required services
and descriptor routes, and enforce the existing zero-AVC, audit-loss,
process-limit, BPF, signature, and artifact gates. This offline qualification
does not turn previous failed v7 results or unexecuted tablet tests into passes.
