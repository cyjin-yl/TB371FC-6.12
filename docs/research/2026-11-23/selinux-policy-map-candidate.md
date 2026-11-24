# Fedora policy candidate: permit PID 1's standard read-only policy mapping

## Result and scope

A new, isolated Fedora SELinux policy was actually rebuilt with the standard
Fedora ARM64 `semodule` and libraries. The added module contains exactly one
rule:

```cil
(allow init_t semanage_store_t (file (map)))
```

The resulting version 35 policy is **3,835,432 bytes**, SHA256
`0dd46af3240a02d1c7399c46facf30cce2a71a471fb70c0d0f5e58e571e53c74`.
It differs from the fixed original binary in **one byte**. Complete CIL exports
of both binaries contain 356,733 lines each. Substituting the single changed
permission rule makes those complete exports byte-identical. The same check
passes after independently converting fresh policy databases to version 33.
This verifies the change against the original binary as well as against the
input module store. [Machine-readable evidence](evidence/selinux-policy-map-candidate.json)
contains the actual commands, statuses, hashes, full rule comparison, and source
identities.

This is an **offline build and policy-comparison result**. No policy was loaded
into a kernel, no VM was started by this experiment, and no tablet action took
place. Standard systemd reload, API-filesystem relabeling, full Fedora boot, and
owner hardware acceptance remain separate runtime gates. Owner Linux runs and
hardware passes remain **zero**.

The candidate file is retained in CT102's HDD container
`tb371fc-build-20261123` at:

```text
/work/selinux-reload-map-20261123/build-02/candidate/etc/selinux/targeted/policy/policy.35
```

The separately built
[V2 early loader](early-selinux-reload-loader.md) preserves the prior loader's
control flow. Its construction result does not establish a successful policy
reload or boot.

## Why this permission is needed

The retained [R4c / v6 production attempt](fedora-r4c-tmpfs-failed.md) reached
the intended early sequence: a distinct ordinary tmpfs root, completed old-root
cleanup, initial policy load with Enforcing enabled, root relabeling, and
execution of systemd in `init_t`. It then recorded an actual denial when PID 1
attempted to map `/etc/selinux/targeted/policy/policy.35`, whose label was
`semanage_store_t`. The raw event is retained in the
[original serial log](evidence/fedora-r4c-tmpfs-failed-verify.log).

That policy-file label is correct for this Fedora policy. The fixed
`file_contexts`, and the original `selinuxutil` CIL module, both assign
`semanage_store_t` to the binary-policy directory and its contents. The local
file-context and substitution overrides are empty. The original `init` CIL
module grants `init_t` the policy-file read/open/getattr permissions and the
`security:load_policy` permission, but lacks the file `map` permission. The
[separate AV audit](selinux-runtime-contract-query.md) confirms that distinction
for the fixed offline policy. Its converted policy is explicitly distinguished
from the unretained policy bytes exported inside the older VM.

The matched Fedora libselinux 3.11 code uses a read-only, private `mmap` to read
the policy image before `security_load_policy`. If this mapping fails, that
path returns failure; it does not retry the read through a different interface.
The missing permission therefore blocks a standard operation that the existing
read and load permissions already intend to permit.

### Why an already-loaded policy did not cause systemd to relabel `/dev` and `/run`

The exact Fedora systemd 262.1 source explains the observed sequence:

1. `mac_selinux_setup()` detects that SELinux is already initialized, but still
   calls `selinux_init_load_policy()`.
2. A successful call sets the calculated init context and sets the caller's
   `loaded_policy` flag to true.
3. If the load fails while an enforcing policy is already active, systemd
   continues using that policy and leaves `loaded_policy` false.
4. Later, `mount_setup(loaded_policy, ...)` uses that flag to enable its standard
   API-mount labeling and recursive relabeling of `/dev`, `/dev/shm`, and `/run`.

Thus, continuing with the old policy does not imply that the standard relabel
branch ran. In v6, the early loader's root traversal deliberately used XDEV and
did not relabel the separate devtmpfs. The later `device_t` labels and journal
errors are consistent with the skipped standard branch. This candidate permits
the normal reload to take place; it does not force `loaded_policy` true, ignore
a failed load, change the policy-file label, or add a permissive domain.

The original native helper, previous policy, and previous failure evidence are
unchanged. The CIL addition is a deliberate policy change in a new candidate,
not a claim that the old policy already worked.

## Fixed sources and tools

All source archives are first-party Fedora Koji source RPMs. The full source
file and patch hashes are in the JSON evidence. The fixed runtime tools are
copied from the already retained Fedora root, whose package identities are in
the [package inventory](evidence/fedora-system-packages.tsv).

| Component | Fixed package/source | Role in this investigation |
|---|---|---|
| SELinux policy | `selinux-policy` and `selinux-policy-targeted` 45.24-1.fc45 | Original binary, complete CIL store, configuration and context files |
| [systemd source RPM](https://kojipkgs.fedoraproject.org/packages/systemd/262.1/1.fc45/src/systemd-262.1-1.fc45.src.rpm) | 262.1-1.fc45 | Reload flag, context transition and API relabel ordering |
| [libselinux source RPM](https://kojipkgs.fedoraproject.org/packages/libselinux/3.11/5.fc45/src/libselinux-3.11-5.fc45.src.rpm) | 3.11-5.fc45 | Actual policy-image mapping and relabel handle behavior |
| [policycoreutils source RPM](https://kojipkgs.fedoraproject.org/packages/policycoreutils/3.11/2.fc45/src/policycoreutils-3.11-2.fc45.src.rpm) | 3.11-2.fc45 | `semodule` no-reload and alternate-root semantics |
| [libsemanage source RPM](https://kojipkgs.fedoraproject.org/packages/libsemanage/3.11/4.fc45/src/libsemanage-3.11-4.fc45.src.rpm) | 3.11-4.fc45 | Complete store linking, external validators and final-file installation |
| [libsepol source RPM](https://kojipkgs.fedoraproject.org/packages/libsepol/3.11/2.fc45/src/libsepol-3.11-2.fc45.src.rpm) | 3.11-2.fc45 | Complete binary parsing, CIL export and version conversion |

The systemd source RPM is SHA256
`de8e6ebb2fb7b7aa0e1297c0c27c3339d15c37b24b57ca16a762483580ea7168`.
Its extracted files were checked against the RPM payload digests. Its three
applicable Fedora patches were applied to the independent source copy. They
modify UID classification, userdb directory labeling, and the machined resolver
workaround; they do not modify the reload, mount-setup or property-formatting
code examined here. The conditional pre-Fedora-40 patch does not apply to this
Fedora 45 source.

The new policycoreutils and libsemanage source RPMs are respectively:

```text
3c14350d0f664618be03e4e8e6f4b34229de85c3903860b57237c5496604f7c7
9730615282b161afbfd956180f27cad79ca75c3ed5e4232495bd5f6305acf685
```

The libsepol source RPM is
`d73db18582210563148c797198183ca9dec00a98f02956297f75cda253f2ad77`.
Its spec has no Fedora patches. The comparison uses the installed ARM64
`libsepol.so.2`, 802,880 bytes, SHA256
`46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b`.
The public export prototype and the containing `sepol_policydb` layout were
checked in this exact source; the script does not guess structure offsets or
read arbitrary memory.

## Offline build procedure and actual execution

The recipe is
[`build_policy.py`](../../../scripts/research/selinux/reload-map/build_policy.py),
with the separate
[`tb371fc_init_policy_map.cil`](../../../scripts/research/selinux/reload-map/tb371fc_init_policy_map.cil)
module. Its only policy statement is checked before execution. The script
requires fixed original policy, configuration, tool and library hashes and a
fresh child of `/work/selinux-reload-map-20261123`.

The build has these properties:

- The original `/etc/selinux` tree and the complete 1,290-file module store are
  copied to a new candidate root. No hardlink is used to make these copies.
- The matching ARM tools and their recursive ELF dependency closure are copied
  into a separate tool root. Explicit, hash-pinned QEMU user emulation runs them;
  PRoot and host binfmt registration are not used.
- `semodule -p <candidate> -S /var/lib/selinux -s targeted -n` directs both the
  store and final policy files to the candidate. In this fixed source, `-n`
  calls `semanage_set_reload(..., 0)` before commit. No `-R` is present.
- The original compiler configuration is retained except for routing fixed
  external helper paths through explicit QEMU wrappers. `setfiles` keeps its
  binary-policy/context validation arguments and `sefcontext_compile` keeps
  its original `-r` argument. A `load_policy` wrapper rejects every invocation;
  it was never invoked.
- No compiler option changes policy booleans, removes dontaudit rules, or
  introduces a permissive domain. All pre-existing CIL modules remain inputs.
- Native before/after inventories cover content, mode, ownership, mtime and
  ctime of the source policy trees. Those source inventories are identical.
  This does not claim that filesystem access times remain unchanged.

A replay using the retained fixed source root and current recipe can use a new
output directory:

```sh
python3 scripts/research/selinux/reload-map/build_policy.py \
  --source-root /work/fedora-input-system-v3/rootfs \
  --work /work/selinux-reload-map-20261123/replay-01 \
  --module scripts/research/selinux/reload-map/tb371fc_init_policy_map.cil
```

This requires the recorded Fedora root and fixed QEMU tool to exist in the
container. The recipe deliberately rejects a different source or reused output
directory. It is not a command to install policy on the tablet or the host.

### Retained first failure and successful build

`build-01` failed while copying the tool closure, before running `semodule`.
The copied root's `/etc/nsswitch.conf` is an absolute guest symlink to
`/etc/authselect/nsswitch.conf`. The first recipe incorrectly resolved it against
the build host. The corrected recipe resolves both relative and absolute guest
symlinks within the supplied root, with an escape/loop bound. The old recipe and
failed job are retained in the evidence and
[`history/build_policy-v1.py`](../../../scripts/research/selinux/reload-map/history/build_policy-v1.py).
No source-tree change occurred in that attempt.

`build-02` started at **2026-11-23 05:48:14 UTC**, completed with **exit 0**, and
took **57.423 seconds** in its job wrapper. The real external calls were one
successful `setfiles` validation and two successful file-context compilation
calls. The final module transaction was number 4.

The [258-byte build log](evidence/selinux-policy-map-build.log) retains a warning
about obtaining a default file-context handle. This isolated tool root does not
include a default SELinux label database. The fixed libsemanage code tries to
restore its optional module-store labeling handle after the transaction, and
libselinux reports the absent handle. The compiler, binary-policy validation
and context compilation all completed; that optional handle does not change
the commit result. The warning has not been hidden or replaced with a success
message. No claim is made that the build directory's SELinux xattrs qualify it
as a runtime root.

## Complete before/after checks

The original policy binary is 3,835,432 bytes, SHA256
`928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430`.
The candidate has the same length. Offset **1,026,692** changes from `0x00` to
`0x04`; every other byte is unchanged. The comparison then independently
parses the complete binaries with the fixed libsepol library instead of
interpreting that byte by hand.

The canonical rule changes from:

```cil
(allow init_t semanage_store_t (file (ioctl read lock open)))
```

to:

```cil
(allow init_t semanage_store_t (file (ioctl read lock map open)))
```

The complete old export is 26,816,056 bytes; the new export is 26,816,060 bytes.
Both contain 356,733 lines. Replacing that one complete rule in the old export
makes the entire output exactly equal to the new export. This includes all
other access-vector rules, booleans, type and attribute declarations,
permissive-type declarations, MLS data, contexts and policy capabilities.
Permissions such as `getattr` may also be supplied through unchanged attribute
rules; their absence from this particular optimized direct rule is not an
assertion that they are denied.

[`compare_policy.py`](../../../scripts/research/selinux/reload-map/compare_policy.py)
checks both policy versions. Its successful `compare-02` job took **68.423
seconds**. Each version-33 conversion uses a **fresh parse** of the original
ordinary input file, before any CIL export on that database:

| Offline image | Bytes | SHA256 |
|---|---:|---|
| Original v35 converted to v33 | 3,835,420 | `aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe` |
| Candidate v35 converted to v33 | 3,835,420 | `bfe189488e5b99bd9bdb6571ec5023100be68771a80ebaf2e42e6c51527d83ba` |

These are userspace conversion identities. They are **not predicted or observed
kernel-export hashes**. The v6 VM's previously observed `9c79…` export was not
saved as a file and is not an input to this comparison.

The earlier `compare-01` is retained. It exported CIL before converting the same
private database, which changed the subsequent serialized ordering and yielded
different conversion hashes. Its complete v35 comparison remains valid, but
those conversion hashes are not used to model the normal loader.
[`history/compare_policy-v1.py`](../../../scripts/research/selinux/reload-map/history/compare_policy-v1.py)
preserves that exact code. The fresh-parse correction reproduces the previously
established original `aab7…` conversion and again proves the sole permission
change.

Complete inventories are provided, including directories and metadata:

| Inventory | Items | Evidence |
|---|---:|---|
| Original source, before and after; identical bytes | 1,766 | [source manifest](evidence/selinux-policy-map-source-manifest.json) |
| Candidate copy immediately before compilation | 1,766 | [candidate before manifest](evidence/selinux-policy-map-candidate-before-manifest.json) |
| Candidate after compilation | 1,771 | [candidate manifest](evidence/selinux-policy-map-candidate-manifest.json) |

All **32 context files** and the SELinux configuration remain identical. Within
the candidate's `/etc/selinux`, the only changed regular file is `policy.35`.
The complete store also records the new priority-400 CIL module, normal commit
and module checksums, the generated disabled-module directory, and the linked
and kernel-policy copies. These normal store changes are enumerated in the
JSON. No pre-existing module content changed.

The new runtime candidate should install the explicitly qualified policy
binary while retaining the original context files. The whole generated store
is build evidence and is not automatically a replacement for runtime files.
Full generated CIL exports remain at their recorded `/work` paths; the recipe
can regenerate them. They are not copied into Git as four large redundant
generated files.

## Runtime contract that remains to be tested

A successful reload enters a branch that v6 did not execute. The fixed source
sets the calculated init context **before** `mount_setup()`. With the early
loader already in `init_t`, the subsequent relabel work must be allowed to
`init_t`; it cannot rely on the initial `kernel_t` domain.

Even setting the same current context is not permission-free. The frozen Linux
6.12.114 `selinux_lsm_setattr()` checks self `process:setcurrent`, then
`process:dyntransition` for the requested current context, with no equal-SID
shortcut. These permissions and the API-relabel permissions must be checked
against the candidate and the actual next exported policy. No extra allow rule
is added by this build to pre-empt that check.

The fixed file-context database supplies these expected labels:

| Actual path/type to inspect | Standard type |
|---|---|
| `/dev/null`, character device | `null_device_t` |
| `/dev/kmsg`, character device | `kmsg_device_t` |
| `/run`, directory | `var_run_t` |
| `/dev/shm`, directory | `tmpfs_t` |
| `/run/log`, directory | `syslogd_var_run_t` |
| `/run/log/journal` and its journal files | `syslogd_var_run_t` |

The `/run/log` socket rule is a different object-type rule and must not be used
as the expected label for the directory. The v6 journal denial named
`syslogd_tmpfs_t`; this is not the expected path label above.

The next production VM must retain its existing Enforcing, domain, actual
policy-export, module, firmware, pids and BPF gates, and additionally verify
successful standard reload and the actual API labels. The mount code does not
propagate every individual `label_fix` failure as a fatal startup error, so a
generic relabel log line alone cannot replace zero-AVC and actual-label checks.
The known D-Bus descriptor path also remains a separate contract involving both
the broker and PID 1 as recipients; adding the policy-file mapping permission
does not grant FIFO permissions to a test service.

No result in this report changes a physical tablet acceptance status.
