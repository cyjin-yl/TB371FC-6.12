# Combined candidate: independent postreload AV verification

## Outcome

The new combined policy candidate passed the **54-row offline permission
contract**: all 52 required permissions were allowed, while both expected
denial controls remained denied. In particular, it now allows `init_t` to
itself for `process:setcurrent` and `process:dyntransition`, the two permissions
that blocked the earlier map-only candidate's source-derived startup path.

This result qualifies the queried **candidate-policy permissions only**. It
does not prove that systemd reloaded the policy, that API filesystems were
relabeled, that the D-Bus descriptor route worked, or that any tablet hardware
ran Linux. Those remain separate actual-VM and physical-device checks.

The original failed candidate, its 53-row output and all earlier sources are
retained unchanged. See
[the earlier postreload report](selinux-postreload-contract-query.md) for its
kernel and libselinux source analysis, and
[the new complete evidence](evidence/selinux-postreload-combined-query.json)
for every query, return code, input identity and command in this run.

## Exact new artifacts

| Item | Bytes | SHA-256 |
|---|---:|---|
| Combined candidate version 35 | 3,835,432 | `e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269` |
| Its measured in-memory conversion to version 33 | 3,835,420 | `ce6ccbfda2105de32c6f865e883493a98ee4df848d298b703d55904cae3f9875` |
| Fixed Fedora AArch64 libsepol | 802,880 | `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |
| Independent query-v2 source | 13,480 | `3c23c6d1a4c8cd289a5a4b1bb09ec6351cbf4bae835369e818ce494f13ec3ad1` |
| Captured stdout JSON | 35,172 | `625942264342ae81c65a505a8330510763b09d77afd4ddad93fbb093e5f9c27b` |

The source policy was read from
`/work/selinux-reload-map-self-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35`.
This query used separately hash-checked copies in the new
`/work/selinux-postreload-contract-v2/inputs` directory. The public source is
[query_postreload_contract_v2.py](../../../scripts/research/selinux/query_postreload_contract_v2.py).

The `ce6ccb…` hash is an **offline libsepol serialization**. It must not be used
as an assumed identity for a future kernel's exported policy. It is also
distinct from the earlier stock conversion `aab7…`, map-only conversion
`bfe189…`, and previous VM's in-memory `9c79…` observation.

## What changed in this query's results

The first 53 row identities—source context, target context, class, permission
and group—exactly match the retained earlier matrix. Only these two allow
decisions changed within that subset:

| Source and target | Permission | Map-only candidate | Combined candidate |
|---|---|---|---|
| `init_t` → `init_t` | `process:setcurrent` | Deny | **Allow** |
| `init_t` → `init_t` | `process:dyntransition` | Deny | **Allow** |

All queried device-node source/target relabel permissions and filesystem
association checks remain allowed. The queried `/run` and journal-directory
relabel permissions remain allowed, as do journald's requested file and
directory operations on the intended `syslogd_var_run_t` label. The candidate
continues to allow `init_t` to read, open, inspect and map the ordinary
`semanage_store_t` policy file and to invoke `security:load_policy`.

Two controls are explicitly required to stay denied:

| Source | Target | Permission | Result |
|---|---|---|---|
| `syslogd_t` | `syslogd_tmpfs_t` | `file:map` | **Deny** |
| `init_t` | `security_t` | `security:read_policy` | **Deny** |

The first is retained from the original 53 rows. The second is a new row,
making 54 total. The script separately checks that the required rows allow
access and that **both** controls deny access; an unexpectedly granted control
would fail its candidate-contract result. Audit masks are recorded separately
from allow decisions, and no API error is treated as a denial.

This subset comparison does not claim to be a full policy semantic diff. The
separate policy-build work owns the full original/candidate comparison and
the restriction to the approved permission additions. This query independently
checks the resulting compiled candidate's specific permissions.

## Execution and next runtime boundary

The direct QEMU invocation completed in **3.800 seconds**, exit **0**, with
empty stderr. All 54 AV calls returned zero. The query used the same pinned
Fedora Python, loader, libc and libpython identities as the earlier independent
run. There was no PRoot, kernel policy load, policy-rule addition, SELinux
boolean change, mount, service execution or new VM in this task. The bounded
foreground process has ended.

A separate live probe has been prepared for the new VM profile. Its v2 source
retains the earlier 80-row FD/entry/export contract and appends the two required
same-domain context permissions, producing **82 rows**:

- [probe_fd_route.py](../../../scripts/research/input/system-integration/profiles/reload-and-fd-contract-v7/probe_fd_route.py),
  retained original: 14,866 bytes,
  `6a8b41ad24c1b83a99879f530d69710ea9e84ab4539f58ef22b6f8e2b508b9f9`.
- [probe_fd_route_v2.py](../../../scripts/research/input/system-integration/profiles/reload-and-fd-contract-v7/probe_fd_route_v2.py),
  independent successor: 15,438 bytes,
  `fee17f6826ad19a25fc431992affc43687699d85ae38c6fe4ab5bd2c14094a61`.

The live probe accepts actual caller-supplied version 33 policy bytes without
conversion. It explicitly treats the requested worker domain as a premise,
not as an observation. The parent protocol must observe the held worker's
real domain, PID identity, executable, argv, cgroup and three FD identities and
directions before releasing it. The host independently checks the complete
expected AV tuple set and the behavioral results. This report records the
source preparation, not a successful execution of that live contract.

The decisive follow-up remains the real Enforcing boot: standard policy-reload
and context-transition success, actual API/journal labels, the complete FD
route, a preserved ordinary-file copy of the loaded policy, and the unchanged
domain/command comparisons for the pids and BPF tests.
