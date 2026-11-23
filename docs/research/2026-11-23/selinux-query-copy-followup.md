# PRoot query execution and source-copy metadata follow-up

This is an additive qualification of the
[offline SELinux access-vector report](selinux-access-query.md). Its original
Markdown and JSON remain byte-for-byte frozen at SHA256 `37421389…` and
`3b0235ad…`. **The query scripts' read-only behavior and the policy/library
hash checks do not prove that the complete PRoot execution left the source
root directory tree unchanged.** The independent evidence for this follow-up
is [selinux-query-copy-followup.json](evidence/selinux-query-copy-followup.json).

## What changed in the interpretation

The query Python scripts do not write a policy, call a kernel policy loader,
or modify their fixed library input. Their before/after policy and library
hash checks remain valid. The original `rootfs_written_by_probe=false` flags
must be read as a statement about those scripts, rather than a guarantee
covering PRoot's own mount-binding setup and cleanup.

The actual PRoot 5.5.0 source can create placeholder directories or nodes in
the guest root tree when initializing a binding whose guest destination does
not exist. It registers cleanup that removes those placeholders when PRoot
exits. Creation and removal can change parent-directory modification times
even when the directory is absent after the command completes. The native
follow-up found this mechanism in the exact source used by the qualified
PRoot binary, SHA256
`313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f`.

| Source at commit `25dc6a3134891f98a79f57ce1c2c1b23ff15cad1` | Relevant operation | Source SHA256 |
|---|---|---|
| [`binding.c`](https://github.com/proot-me/proot/blob/25dc6a3134891f98a79f57ce1c2c1b23ff15cad1/src/path/binding.c) | Enables glue creation while canonicalizing a binding destination | `12747c22372e97867d90d40e58241422de294eaee500121293754004d35360d0` |
| [`canon.c`](https://github.com/proot-me/proot/blob/25dc6a3134891f98a79f57ce1c2c1b23ff15cad1/src/path/canon.c) | Calls the glue builder for a missing component during binding initialization | `935aef55e5b4f3141980cbc1a67741bb6f40988c84949770e97e2622e9734d00` |
| [`glue.c`](https://github.com/proot-me/proot/blob/25dc6a3134891f98a79f57ce1c2c1b23ff15cad1/src/path/glue.c) | Creates guest placeholders and removes them through a termination destructor | `750aacd7eb224f3f18c3f4cb93e773cf2f8b054572591dbd69a527715a481598` |

The `PROOT_DONT_POLLUTE_ROOTFS` switch bypasses this guest-placeholder creation
branch. The native follow-up observed that variable unset in the current
container environment. The original wrapper recorded only its explicit
environment overrides, so this is not a complete capture of every inherited
variable at each historical invocation. The switch also does not make an
arbitrary guest program or root filesystem read-only. No new PRoot invocation
was made to reproduce the effect on the frozen source tree.

## Timing and the retained failed copy

The v4 baseline-copy attempt ran from `04:00:35.524376` to
`04:01:32.960453` UTC on 2026-11-23. The file-copy command returned zero, but
its subsequent canonical source tar returned one and the qualification
record correctly remains `complete=false`. The integration task reported
`tar: .: file changed as we read it`.

The separate ARM64 `matchpathcon` lookup completed during that window; its
result file has an mtime of `04:01:19.982145` UTC. A later native-only
observation found `/analysis` absent in the frozen root. The root and `dev`
directory mtimes were both `04:02:28.350890246`, approximately one millisecond
before the final service-entry query's stdout record was written at
`04:02:28.351890301`. These observations and the source mechanism are
consistent with PRoot placeholder cleanup affecting directory metadata.
There was no syscall trace of the historical tar failure, so its exact
causal operation is not claimed as proven.

The old failed copy, its record and its original timestamps were retained.
The source timestamps were not reset, and no historical tar hash was
reconstructed or relabeled as a successful result. The exact record
identities and native observations are preserved in
[the follow-up JSON](evidence/selinux-query-copy-followup.json).

## Quiescent copy qualification

After all query PRoot jobs had ended, the integration task made a new v5 copy
from `04:17:34.589246` to `04:18:44.427405` UTC. Both canonical source and
destination streams returned zero and matched:

| Measurement | Result |
|---|---|
| Canonical tar size, each stream | 1,323,141,120 bytes |
| Canonical tar SHA256, both streams | `1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96` |
| v5 copy qualification | `complete=true` |
| Journal access/default ACL comparisons | Byte-identical |

A native read-only comparison of the retained v4 copy and the quiescent v5
copy found exactly three differences: the `mtime_ns` fields of `.`, `dev`,
and `etc`. It found no payload, mode, owner, group, xattr, device-number or
symlink differences, and the hardlink groups matched. Both complete
comparison manifests are retained, each 7,708,567 bytes. This comparison
covers those two snapshots; it does not reconstruct every intermediate
state of the source tree.

| Retained record | SHA256 |
|---|---|
| `/work/fedora-input-system-v4/baseline-copy.json` | `d66345fa5eb8fab0526f3823c99e4af8030acd390d8cf919bec3888924b7f4c0` |
| `/work/fedora-input-system-v5/baseline-copy.json` | `c385dc8b5cab3a068ba18d4cb385f31beb401f8e51e83d8adfd9e2008955d75f` |
| `/work/fedora-r4-baseline-comparison-v1/comparison.json` | `4fbba68f55e17ad2e170cc7c769829a516f3642f018776644c8bd7f5f8d530b5` |

All three records were read natively and checked against these supplied
hashes before incorporation into this supplement. The failed v4 qualification
remains failed; the later v5 copy has its own successful qualification.

## Subsequent scope

Further PRoot invocations against the frozen R1 source root have stopped.
This follow-up read source files and metadata through native Python only.
The new initramfs verifier likewise reads archive bytes and ordinary source
files natively; it does not start PRoot, load policy, execute an image, or
rewrite source metadata.

The access-vector results remain the fixed-policy computations described in
the original report, including the boundary between the converted policy and
the separately exported live policy. This supplement corrects the scope of
the source-tree immutability claim. It adds no physical-tablet or hardware
success claim.
