# Combined Fedora policy candidate for standard PID 1 reload and same-type context setup

## Result and scope

A **new, isolated policy candidate** was built from the original Fedora policy
and complete module store. It adds exactly the following two rules, containing
three permissions:

```cil
(allow init_t semanage_store_t (file (map)))
(allow init_t init_t (process (setcurrent dyntransition)))
```

The resulting version 35 policy is **3,835,432 bytes**, SHA-256
`e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269`.
The standard `semodule -n` build completed with exit **0** in **57.081 seconds**
including the job wrapper. The independent complete-policy comparison then
completed with exit **0** in **99.915 seconds**.

Both the full version 35 exports and the exports of freshly converted version
33 policies are byte-identical after substituting only the two reviewed allow
rules. No other access vector, type, boolean, permissive declaration, MLS
constraint or policy capability changes. In particular, **no new
`dyntransition` rule to another type is added**. The process rule names
`init_t` as both source and target; it does not claim that type enforcement
encodes only one particular runtime SID or MLS context.

The [machine-readable record](evidence/selinux-policy-map-self-candidate.json)
contains actual commands, tool identities, unchanged-source checks, raw build
results, comparison results and the complete manifest references. This is an
**offline construction and semantic-comparison result**. No VM was started,
no kernel policy was loaded or written, and no tablet boot or hardware test
was performed by this experiment.

The earlier [map-only candidate](selinux-policy-map-candidate.md), its `0dd46a…`
policy and its reports remain unchanged. The new candidate resides at:

```text
/work/selinux-reload-map-self-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35
```

## Why the extra same-type operations are needed

The [retained v6 boot](fedora-r4c-tmpfs-failed.md) demonstrated policy-file
mapping and API-label failures after the native helper had already executed
systemd into `init_t`. The first independent policy correction added only
read-only file mapping. A subsequent
[53-vector postreload audit](selinux-postreload-contract-query.md) established
a further concrete condition: that candidate still denied `init_t` to itself
both `process:setcurrent` and `process:dyntransition`.

Three matching source components explain why those two denials matter:

| Component | Exact behavior relevant to this candidate | Fixed source SHA-256 |
| --- | --- | --- |
| Fedora systemd 262.1 `src/core/selinux-setup.c` | After a successful standard policy load, calculate the init label and call `setcon_raw()`. A transition error produces a warning; the code still reports policy loaded and sets `loaded_policy = true`. | `868c39f4a81584803e38e82e5db02f510d0148594cf1c21923b522c19a3547e1` |
| Fedora-patched libselinux 3.11 `src/procattr.c` | A new process starts with `prev_current = UNSET`. `getcon_raw()` does not populate that setter cache. The first setter therefore writes the current attribute; only a successful setter write populates the cache. | `cbbc16d3879fbad25e5fbaf3a635272262d8aab8086c2fd0d572741b1b84464f` |
| Research4 Linux 6.12.114 `security/selinux/hooks.c` | The current-attribute operation checks `PROCESS__SETCURRENT`, then `PROCESS__DYNTRANSITION` between current and requested SIDs. Equal SIDs do not bypass those checks. | `6079b88f15ca1966b640753e35edc291139fe925fca37e5c54d0a2d6e36d8370` |

The library does have a same-value setter optimization. It cannot be inferred
from an earlier getter: the getter returns a copy of the context without
filling `prev_current`. The source chain and the actual offline AV denials are
preserved in the postreload audit. They establish a missing permission
contract, not an already-observed failure of this new candidate in a VM.

The new module therefore permits the standard operation for the same
`init_t` type. It does not change systemd or libselinux code, delay the
executable transition by forcing `kernel_t`, substitute a false loaded-policy
flag, ignore a transition warning, change file contexts, add permissive
domains or disable enforcement. The original management-domain and descriptor
requirements remain separate; this policy module grants no new access to
another process type or arbitrary policy-export interface.

## Fixed inputs and isolated build

The build used the immutable original policy/store in
`/work/fedora-input-system-v3/rootfs`. Its full source inventory contains
**1,766 entries: 1,329 files and 437 directories**. Before copying, the recipe
requires the canonical content/owner/mode inventory hash:

```text
c0070c6fb7f209ed7e391d4707a1058caedbaf1ad96c076a17624661e5558b50
```

This is derived from the independently retained original inventory, not from
the map-only candidate's store. Only `mtime_ns` and `ctime_ns` are excluded
from that portable content pin. The experiment separately compares its
original source before and after **including both timestamps**. Those full
source manifests are identical to each other and to the prior frozen source
manifest, SHA-256
`3ab1550b558272ac17ff8a89520238bac8d2b5c108958e4458210da52fb10534`.
No unchanged-atime claim is made.

| Input or result | Bytes | SHA-256 |
| --- | ---: | --- |
| Original version 35 policy | 3,835,432 | `928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430` |
| New two-line source module | 104 | `f0bf27105894ec4ce8b027d4c68ccc395467ff947721b1f82574b0dbd9895a38` |
| New build recipe | 14,599 | `79d8caa49030b517dd9f14cce11f93adf3c4b9a59a44051aaedadaf64c99d5f6` |
| New complete-policy comparator | 11,129 | `344d29b039ec0bb1f53d086a0251f0be04963b8cd2234962885818f8cd8e4a18` |
| Fixed AArch64 libsepol | 802,880 | `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |
| Fixed explicit QEMU-user executable | 16,661,520 | `73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943` |
| New combined version 35 policy | 3,835,432 | `e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269` |

The [build recipe](../../../scripts/research/selinux/reload-map-self/build_policy.py)
creates a fresh candidate and an independent 18-file tool/runtime closure.
It uses the same fixed Fedora ARM `semodule`, `setfiles`,
`sefcontext_compile` and libraries qualified in the
[original source/toolchain audit](selinux-policy-map-candidate.md). It runs
through explicit QEMU-user, without PRoot or binfmt changes. The new namespace
is `/work/selinux-reload-map-self-20261123`; no old build directory is reused
or modified.

The effective semodule invocation uses the new alternate root, the original
store layout and priority 400:

```text
semodule -p <fresh-candidate> -S /var/lib/selinux -s targeted \
  -g <fixed-tool-path-build-config> -n -v -X 400 \
  -i <tb371fc_init_reload_contract.cil>
```

The fixed source establishes `-n` as no-load behavior. Native wrappers admit
only the fixed context-validation/compiler invocations; a `load_policy`
wrapper rejects every invocation and was never called. The actual external
calls were one successful `setfiles -q -c` context-file validation and two
successful `sefcontext_compile -r` calls. They did not traverse the source or
host filesystem to relabel it.

The build configuration changes only executable paths needed to dispatch the
fixed ARM tools. It does not alter policy compiler options, booleans,
dontaudit behavior or runtime `/etc/selinux/config`. The exact source module
is [tb371fc_init_reload_contract.cil](../../../scripts/research/selinux/reload-map-self/tb371fc_init_reload_contract.cil).

## Full payload and semantic comparison

The new candidate copy initially matches all original source content,
ownership and modes. After compilation, the only changed payload under
`etc/selinux` is `targeted/policy/policy.35`. **All 32 original context files
and the original config remain byte-identical.** The module store records the
normal transaction/checksum updates, the two new module payloads, linked
policy outputs and new module/disabled directories. These expected store
changes are retained in the full manifest; they are not automatically copied
into a runtime root by this experiment.

The comparator parses each original and candidate binary into a private
libsepol database and exports its entire CIL. It independently reparses each
version 35 input before converting to version 33, so export-side ordering
cannot contaminate that conversion. It then fully exports the version 33
results and repeats the same strict comparison.

| Complete export | Bytes | Lines | SHA-256 |
| --- | ---: | ---: | --- |
| Original version 35 | 26,816,056 | 356,733 | `92eac75fb11b66a737394832355483b462827647000717bac539f5b92bc3979a` |
| New combined version 35 | 26,816,085 | 356,733 | `3b03fe615a38c9c06845340aa14b31065061a8415ac9de449c58f357d4c6f7c3` |
| Original fresh version 33 | 26,816,056 | 356,733 | Same complete CIL hash as original version 35 |
| New combined fresh version 33 | 26,816,085 | 356,733 | Same complete CIL hash as new version 35 |

For each policy version the comparator requires exactly these merged-rule
changes:

```diff
-(allow init_t semanage_store_t (file (ioctl read lock open)))
+(allow init_t semanage_store_t (file (ioctl read lock map open)))
-(allow init_t self (process (fork getsched getcap setcap setexec setfscreate setkeycreate setsockcreate)))
+(allow init_t self (process (fork getsched getcap setcap setexec setfscreate dyntransition setcurrent setkeycreate setsockcreate)))
```

The binary-to-CIL exporter renders the same-type target as `self`. The source
module explicitly names `init_t` twice. After replacing just these two full
lines, the entire original and candidate CIL files compare byte-for-byte
identical. This checks the rest of the policy, including constraints and
attribute-derived rules; it is more than a search for the desired new allow.
The original `getattr` grant can come through unchanged attribute rules and
need not appear in the direct merged file rule above.

The version 35 binaries have the same length and differ at three byte offsets:
`667305`, `667306` and `1026692`. The semantic claim follows from the complete
CIL comparison, not from the small number of changed binary bytes.

Fresh in-memory version 33 serialization produced:

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| Original policy | 3,835,420 | `aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe` |
| New combined policy | 3,835,420 | `ce6ccbfda2105de32c6f865e883493a98ee4df848d298b703d55904cae3f9875` |

These are offline conversion identities, **not predetermined hashes of policy
bytes exported by a running kernel**. A later same-boot AV query must use the
actual exported bytes and retain them independently. The old unpersisted
`9c79…` identity is not substituted with either of these files.

## Retained warning and limits of the construction

The actual [build log](evidence/selinux-policy-map-self-build.log) retains:

```text
Error obtaining file context handle: No such file or directory
```

As established by the matching libsemanage source in the earlier audit, the
optional default file-context handle uses the emulated tool root, which does
not contain a runtime SELinux labeling setup. That warning does not silently
make the transaction or the explicit context-file validation fail. All three
fixed external validations completed, semodule returned zero, and the full
output-policy comparison passed. The warning is preserved; this result makes
no claim that the build performed runtime filesystem labeling.

The raw semodule result was correctly written before the comparison, with
status `built_pending_delta_and_runtime_qualification`. That immutable
record is not rewritten. The later comparison closes its **offline delta**
condition only; runtime remains untested.

The already constructed [V2 native loader](early-selinux-reload-loader.md) is
72,048 bytes with SHA-256
`cc042c9fc4e92c75803215649c99bd87badd301bb05aa16820b43aaeb8fb50bc`.
Its original build input was the map-only `0dd46a…` policy. The new policy has
the same length, so that loader's native shape/size condition is compatible,
and no new loader compilation was performed here. That is not an implicit
hash binding: the **new** archive and runtime profile must explicitly require
`e1a63e…`, while retaining the old loader-construction record unchanged.
The waiter's own size check also cannot distinguish these same-length policies.

A successful systemd policy-load message alone is insufficient: its source
can print that message after a failed calculated-label transition. The next
independent VM must preserve the transition/actual-domain, API/journal-label,
zero-AVC, actual-policy-byte, descriptor, pids/BPF and clean-shutdown gates.
This construction has not exercised any of those success branches. All owner
Linux hardware runs and passes remain zero.

## Reproduction and retained files

All commands must use a new output directory. The scripts deliberately refuse
to overwrite an existing build or comparison. The actual jobs ran in the
visible `tb371fc-policy-self` tmux session through the existing job recorder;
both completed and left their logs and exit metadata.

```bash
python3 scripts/research/selinux/reload-map-self/build_policy.py \
  --source-root /work/fedora-input-system-v3/rootfs \
  --work /work/selinux-reload-map-self-20261123/build-01 \
  --module scripts/research/selinux/reload-map-self/tb371fc_init_reload_contract.cil
```

The [comparison recipe](../../../scripts/research/selinux/reload-map-self/compare_policy.py)
is invoked through the hash-pinned ARM Python/runtime and explicit QEMU, with
`-B`, the fixed original policy, candidate size/full hash, libsepol identity and
a fresh output directory. The complete actual command, rather than a shortened
placeholder, is retained in the JSON.

| Public record | Bytes | SHA-256 |
| --- | ---: | --- |
| [Original full source manifest](evidence/selinux-policy-map-self-source-manifest.json) | 504,226 | `3ab1550b558272ac17ff8a89520238bac8d2b5c108958e4458210da52fb10534` |
| [Candidate before build](evidence/selinux-policy-map-self-before-manifest.json) | 504,226 | `169603559d388fe1af51789fef4be2000f385b149ec43b3fdf3243f74a7279ac` |
| [Candidate after build](evidence/selinux-policy-map-self-candidate-manifest.json) | 505,532 | `4be3108af468604a4ac1dcb3d6757ef9719296e3d255cceb6c0335219384ac8c` |
| [Exact semodule output](evidence/selinux-policy-map-self-build.log) | 268 | `316572b45bbb0bb7eff6dce3d77916e21da4236fc7ec3999d1146806c2147da8` |

The full CIL exports and binary policy files stay in the isolated work prefix.
Their paths, sizes and hashes are recorded, and the public scripts reproduce
the comparison. A fixed transfer of the 15 metadata/log/manifest records was
verified after local ingestion. No earlier report, policy, helper, image,
recipe or physical-device state was modified by this experiment.
