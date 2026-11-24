# Standard-service policy candidate: six exact permissions, complete offline comparison

## Result and boundary

A fresh copy of the original Fedora policy/module store was rebuilt with
**five CIL rules adding six reviewed permissions**. The standard no-load
build and complete original/candidate CIL comparisons both exited 0.
After reversing only those five exact rule changes, the complete candidate
CIL equals the original byte for byte for both policy version 35 and an
independently parsed version-33 conversion. Original context files and
SELinux configuration remain unchanged.

The actual new policy is **3,835,456 bytes**, SHA-256
`727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502`.
It is retained in the HDD container `tb371fc-build-20261123`, CT102:

```text
/work/selinux-standard-services-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35
```

This is a source/build result. No kernel policy was loaded, no VM was started,
no enforcement setting or runtime label was changed, and no tablet operation
was performed by this experiment. **Owner Linux runs and hardware passes remain
zero.** The [v7 failure](fedora-r4d-reload-fd-failed.md), its raw logs, and the
older map-only and combined candidates retain their original outcomes.
The [machine record](evidence/selinux-standard-service-policy.json) contains
the exact commands, tool identities, full comparison decisions, inventory
checks and transfer identities.

## Why these permissions are present

The earlier [combined candidate](selinux-policy-map-self-candidate.md) added
the three PID 1 operations needed for standard policy mapping and same-type
context setup. V7 subsequently observed successful standard reload/context
setup and correct early API/journal labels. It also exposed two further
standard-service denials. The [matched-source Varlink audit](selinux-varlink-cleanup.md)
checked both the offline candidate and the actual preserved version-33
kernel export. Those two 32-query results establish the relevant permission
subset; their agreement is not a claim that the complete policies are equal.

| Source → target | Object class | Added permission(s) | Evidence motivating this candidate |
| --- | --- | --- | --- |
| `init_t` → `semanage_store_t` | `file` | `map` | Correctly labelled policy file; standard libselinux maps it during reload |
| `init_t` → `init_t` | `process` | `setcurrent`, `dyntransition` | Standard first `setcon_raw` write and matching kernel checks, even for the same type |
| `init_t` → `systemd_varlink_registry_t` | `lnk_file` | `unlink` | Actual v7 AVC while the standard udev socket unit removes its configured link |
| `journalctl_t` → `syslogd_var_run_t` | `sock_file` | `write` | Actual v7 AVC during failure-diagnostic `journalctl --sync` |
| `journalctl_t` → `syslogd_t` | `unix_stream_socket` | `connectto` | Exact next Unix-stream connection check, denied in both queried policies; not an AVC reached by v7 |

The complete new module is:

```cil
(allow init_t semanage_store_t (file (map)))
(allow init_t init_t (process (setcurrent dyntransition)))
(allow init_t systemd_varlink_registry_t (lnk_file (unlink)))
(allow journalctl_t syslogd_var_run_t (sock_file (write)))
(allow journalctl_t syslogd_t (unix_stream_socket (connectto)))
```

No target `sock_file getattr` permission is added. The fixed short-path
journal client calls `connect()` directly; its `fstat()` and `getsockopt()`
operate on the newly created client socket, whose relevant rights already
allow. The [source audit](selinux-varlink-cleanup.md) also confirms the
original journal and registry labels. Relabelling them to another type would
not be justified by those standard paths.

The process rule targets only `init_t` itself. It adds no transition to a
different domain. No boolean, permissive declaration, original context,
`init_t read_policy`, systemd code or libselinux code is changed. The later
PL061 directory assertion and interleaved console frames are separate
fixture issues; a policy change does not fix either of them.

## Fresh original-store construction

The source is the retained original policy/store under
`/work/fedora-input-system-v3/rootfs`, with policy.35 SHA-256
`928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430`.
The build does not use the already modified `e1a63…` or `0dd46a…` candidate
as its source. It copies `etc/selinux` and `var/lib/selinux/targeted` into
its own fresh directory and first requires the complete content/owner/mode
inventory to match the original hard pin:

```text
c0070c6fb7f209ed7e391d4707a1058caedbaf1ad96c076a17624661e5558b50
```

The recorded original inventory has **1,766 entries**, including **1,329
regular files**. Original before/after inventories match exactly, including
mtime and ctime. This is a check of these policy/store trees, not a claim
about atime or every unrelated inode in the rootfs. The initial candidate
matches their content, ownership and modes; copied directory timestamps are
recorded separately.

The recipe copies a fixed ARM64 tool/library closure and runs the matching
Fedora `semodule` through explicit QEMU user emulation. It uses the standard
alternate-root/store options, module priority 400 and **`-n` no-load mode**.
Controlled wrappers route the transaction's external `setfiles` and
`sefcontext_compile` calls to the same fixed ARM tool closure. The
`load_policy` wrapper rejects every invocation. No PRoot, host binfmt
registration, package installation or live-policy operation is part of
this build.

The observed transaction invoked:

- `setfiles -q -c` to validate the generated policy against file contexts;
- `sefcontext_compile -r` for `file_contexts`;
- `sefcontext_compile -r` for `file_contexts.homedirs`.

All three calls met their fixed allowlisted arguments. No load-policy call
occurred. The build retains this warning in the exact
[267-byte transaction log](evidence/selinux-standard-service-policy-build.log):

```text
Error obtaining file context handle: No such file or directory
```

The earlier [matched tool/source analysis](selinux-policy-map-candidate.md)
records this optional default context-handle path. The warning is not hidden
or promoted to a host-labeling success. The explicit validation/compilation
calls, standard transaction and subsequent full policy comparison all
completed successfully, and the original context payloads are unchanged.

The independent persistent job ran in tmux `tb371fc-policy-services`.
Its exact job command is embedded in the JSON. The build wrapper took
**58.467 seconds**, with the recorded
transaction/validation interval **57.050 seconds**.
The raw build result deliberately retains
`built_pending_delta_and_runtime_qualification`; the later comparison
closes only its offline-delta requirement.

## What the complete policy comparison proves

The comparator uses the fixed ARM64 `libsepol.so.2`, 802,880 bytes, SHA-256
`46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b`.
It parses each complete original/new version-35 binary and exports CIL.
It separately creates a **fresh parse without prior CIL export** for the
version-33 conversion, then parses and exports that converted binary. The
fresh parse avoids confusing mutations in a previously exported in-memory
policy object with a new serialization.

For each version, the checker requires exactly the five approved
source/target/class tuples. Existing tuples may only gain their listed
permissions; an absent tuple may gain a line with exactly its approved
permission. There may be no removed or duplicate permission. It then
replaces the changed lines with the exact old lines, or removes the whole
new line where the old tuple was absent, and compares the **entire resulting
CIL byte stream** with the original.

Both versions pass. The exporter spells the same-type process target as
`self`. Three existing tuples gain the approved permissions; the two journal
connection tuples are new. All other exported AV rules, declarations,
booleans, types, permissive entries, MLS/constraint statements and policy
capabilities remain byte-identical after that exact reversal. The result is
more than an assertion that the input module looks small.

| Full CIL export | Bytes | Lines | SHA-256 |
| --- | ---: | ---: | --- |
| candidate-v33 | 26816215 | 356735 | `74839737f1c0dd679cbe3d288bdb8e1342816f71dcd18d9114565ef8cc2b8501` |
| candidate-v35 | 26816215 | 356735 | `74839737f1c0dd679cbe3d288bdb8e1342816f71dcd18d9114565ef8cc2b8501` |
| original-v33 | 26816056 | 356733 | `92eac75fb11b66a737394832355483b462827647000717bac539f5b92bc3979a` |
| original-v35 | 26816056 | 356733 | `92eac75fb11b66a737394832355483b462827647000717bac539f5b92bc3979a` |

The independent comparison job exited 0 in
**184.626 seconds**. Its rule-by-rule
before/after strings and all success flags are included in the machine
record. The complete CIL files remain under
`/work/selinux-standard-services-20261123/compare-01` for replay.

### Binary identities are distinct from runtime identities

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Original policy35 | 3,835,432 | `928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430` |
| New policy35 | 3,835,456 | `727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502` |
| Original fresh policy33 | 3,835,420 | `aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe` |
| New fresh policy33 | 3,835,444 | `9b39b5a59771bf3f7ac1119979ac09ca7c579fd5504b57f2970008b6ee200afe` |

The new binary grows by **24 bytes**. A positional comparison finds
1,518,106 differing bytes in the overlapping region because serialized
records and subsequent offsets move. This is not a claim that only six
bytes change. The complete CIL comparison establishes the exact rule delta.

The new offline version-33 hash is not a prediction of the next kernel's
exported bytes. V7's actual preserved export has its own `0fe3c0e1…` identity.
A future boot must retain and query its own actual export and must independently
observe all relevant labels, service effects and absence of denials.

## Inventory changes and retained evidence

Only `etc/selinux/targeted/policy/policy.35` changes among the runtime
`etc/selinux` payloads. **All 32 original context files and the original
config remain unchanged.** The standard module-store transaction separately
updates its commit number, module directory/CIL/language marker, checksum,
linked policy and kernel-policy cache. These expected build-store changes
are listed in full; they are not silently copied wholesale into a runtime
candidate. The final candidate inventory has **1,771 entries**.

| Retained public record | Bytes | SHA-256 |
| --- | ---: | --- |
| build-01/source-before.json | 504226 | `3ab1550b558272ac17ff8a89520238bac8d2b5c108958e4458210da52fb10534` |
| build-01/candidate-before.json | 504226 | `c0e7adf30d018ce99bbcfafd1042106aa6100262bc085795e97a163363e32855` |
| build-01/candidate-after.json | 505523 | `a5d64afb687c801c9c93593df629be4d6a9f8a5c24fbee280e97f6bdf55d94e4` |
| build-01/semodule.log | 267 | `fe393b55f846d35bb83e145bccd1029bba4e5742dfd8ebb569418262b61766d8` |

The remote bundle retains 14 exact text records, including raw build and
comparison results, job commands, recipes and before/after inventories.
Its XZ file is 87,824 bytes with SHA-256
`97ff121a5757a3b9030a21b24c0b0e8aacfdeb81bfb4157cc4046fc9f16721d5`.
The expanded 2,313,924 bytes have SHA-256
`df510bb4652ffc2e8a513d98e31f79782211564a152aea8d40f4686665305de8`.
Every entry's byte length/hash was independently checked on transfer. The
public machine record embeds the small raw results and references the full
published inventories; no vendor firmware or private kernel symbols are
included.

## Reproduction and next runtime gate

| Exact source | Bytes | SHA-256 |
| --- | ---: | --- |
| [build_policy.py](../../../scripts/research/selinux/standard-services/build_policy.py) | 14787 | `c1d3125b2ad211bb10db36ec6c72aceb21e46af49537753c7ed24a3c7d74c637` |
| [compare_policy.py](../../../scripts/research/selinux/standard-services/compare_policy.py) | 11919 | `5cd9b4e3a57b3a856ef9ecf22e295ef566933aa42f6c7354ddf953c46159bfab` |
| [tb371fc_standard_services.cil](../../../scripts/research/selinux/standard-services/tb371fc_standard_services.cil) | 289 | `791afa8483adb1ccbdfe559bf0b574e9aff9fd4490407d6bf2f258d94fffde2a` |

The executed private recipe copies had mode 0600 and were invoked with an
explicit interpreter. Published Python files use mode 0755; their bytes and
hashes are exactly the executed copies. The CIL file is mode 0644 publicly.
The commands below use fresh child directories, so the original build and
comparison outputs are retained:

```sh
python3 /src/scripts/research/selinux/standard-services/build_policy.py \
  --source-root /work/fedora-input-system-v3/rootfs \
  --work /work/selinux-standard-services-20261123/build-02 \
  --module /src/scripts/research/selinux/standard-services/tb371fc_standard_services.cil

/usr/bin/qemu-aarch64 \
  -L /work/fedora-input-system-v3/rootfs \
  -E PYTHONHOME=/work/fedora-input-system-v3/rootfs/usr \
  /work/fedora-input-system-v3/rootfs/usr/bin/python3 -B \
  /src/scripts/research/selinux/standard-services/compare_policy.py \
  --original /work/fedora-input-system-v3/rootfs/etc/selinux/targeted/policy/policy.35 \
  --candidate /work/selinux-standard-services-20261123/build-02/candidate/etc/selinux/targeted/policy/policy.35 \
  --candidate-size 3835456 \
  --candidate-sha256 727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502 \
  --library /work/fedora-input-system-v3/rootfs/usr/lib64/libsepol.so.2 \
  --output /work/selinux-standard-services-20261123/compare-02
```

The fixed tool hashes and original complete store inventory are required;
a different distro revision cannot silently substitute for them. These
recipes establish a method and one measured construction, not unrestricted
cross-toolchain reproducibility.

The previous V2 helper was bound to a 3,835,432-byte policy and its size guard
cannot accept this 3,835,456-byte candidate. A separate loader/profile must
bind the new length and **full policy hash**, preserve original contexts and
firmware/ELF closure, and retain successful/failed outcomes independently.
No new loader, archive or runtime binding is claimed by this policy report.
The subsequent Enforcing VM must still verify standard reload, actual labels,
all descriptor receivers, exact pids/BPF behavior, PL061's actual binding,
strict serial result delivery and zero AVCs. Even a complete generic-VM pass
would leave the physical tablet's entry, recovery and hardware tests open.
