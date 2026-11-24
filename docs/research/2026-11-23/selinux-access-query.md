# Offline SELinux access-vector queries for the Fedora broker investigation

## Result and scope

The fixed Fedora policy denies `system_dbusd_t` the five queried `fifo_file`
permissions on `unconfined_service_t` pipes, while allowing `fd/use` for that
same target type. The five FIFO denials also have their `auditdeny` bits clear.
This is a concrete candidate for a failure involving the reported validator
pipes without a corresponding AVC message. It does **not** establish which
operation caused the broker connection reset.

The corresponding queries for `init_t` and `initrc_t` pipes allow all five FIFO
permissions and `fd/use`. `kernel_t:fd use` and the three queried
`null_device_t:chr_file` permissions also allow access. The service-entry
follow-up allows all 12 queried permissions for an explicit `initrc_t` entry,
including `init_t` self `process/setexec`.

These are computations in **libsepol's private userspace policy database** in
the dedicated build container. No kernel policy was loaded or changed, no
policy image was written, no root filesystem was modified by the probes, and
no physical tablet operation was performed. Successful query execution means
that an access vector was computed; it does not mean every requested
permission was allowed. The complete return codes, masks, contexts, commands,
source pins and retained attempt identities are in
[the evidence JSON](evidence/selinux-access-query.json).

## Fixed inputs and the loaded-policy boundary

The probe uses the original Fedora ARM64 Python and libsepol through the
already qualified PRoot 5.5/QEMU environment. The work prefix is
`/work/selinux-access-query-v1` in `tb371fc-build-20261123`; the frozen source
root filesystem is `/work/fedora-system-integration-v1/rootfs`.

| Input or derived object | Bytes | SHA256 |
|---|---:|---|
| On-disk `policy.35` | 3,835,432 | `928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430` |
| Executed ARM64 `libsepol.so.2` | 802,880 | `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |
| In-memory version 33 serialization used for these queries | 3,835,420 | `aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe` |
| Earlier research1 VM's exported loaded version 33 policy | 3,835,420 | `9c79cb12810a781d6cb91f9b7dff160a1d768c534b784743b4256015799f22a8` |

The conversion reuses the exact input checks and header parser from
[`verify_selinux_compatibility.py`](../../../scripts/research/verify_selinux_compatibility.py),
whose SHA256 is
`6c3c9d4e75c9da1d30c977ae7d99be4dcb57ebb0bb68d247e9ec12a3d870bf6d`.
The policy and library are hash checked before and after each query phase.
Version 35 is changed to version 33 only in the temporary libsepol conversion
database; the serialized bytes are checked against the previously qualified
conversion result. See [the compatibility report](selinux-compatibility.md)
and [the earlier runtime record](evidence/fedora-system-integration.json).

**The offline serialization and the exported loaded policy are not byte
identical.** Equal length and version do not change this. This experiment does
not establish their semantic equivalence or determine the reason for the
different hashes. It queries the boolean values serialized in the fixed
on-disk input and does not substitute live boolean state. A query on the exact
loaded bytes, followed by an Enforcing runtime test, belongs to the separate
full-system integration proof. The integration task has been given the
qualified public API and both identities for that follow-up.

## Query implementation and public ABI

The API review used SELinuxProject release `3.11`, commit
`2233a23a4d4f1bf29054037babec13f30d038e65`. All eight reviewed source files have
content hashes in the evidence. The source establishes the API contract;
the independent hash above identifies the actual Fedora library executed.
No equivalence between an unmodified upstream build and the Fedora binary is
assumed.

The public types are 32-bit security IDs and access vectors, a 16-bit security
class, and a 20-byte access-decision structure containing five 32-bit fields:
`allowed`, `decided`, `auditallow`, `auditdeny`, and `seqno`. Class numbers and
permission bits are looked up from the actual policy, rather than hardcoded.
Context strings are converted to process-local SIDs; these numbers are not
live kernel SIDs. The declarations are in
[`flask_types.h`](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/include/sepol/policydb/flask_types.h)
and
[`services.h`](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/include/sepol/policydb/services.h).

The actual Fedora library exports `sepol_set_policydb_from_file`. Its
implementation initializes libsepol's own `mypolicydb` and SID table and
reads the supplied `FILE *`; it is not a kernel SELinux loader. The probe
supplies a read-only `fmemopen` stream over the converted bytes, closes that
stream after the database read, and later frees the conversion database and
buffer. The library's separate service database stays within this process.
This behavior is defined in
[`sepol.h`](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/include/sepol/sepol.h)
and the `sepol_set_policydb_from_file` implementation in
[`services.c`](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/src/services.c).

Neither AV probe imports libselinux or calls a kernel SELinux interface.
`sepol_load_policy` and `sepol_transition_sid` are not exported by this actual
Fedora `.so`, even though implementations or declarations exist upstream.
No private symbol offsets or guessed internal structure layouts were used.
The separate `matchpathcon` invocation described below uses libselinux only
for a file-context lookup.

Each permission is submitted separately to `sepol_compute_av_reason`. The
decision is read from the requested bit of `allowed`. `auditdeny` is recorded
separately: a clear audit bit is not evidence that access was denied. For
example, this same run allows `system_dbusd_t` to use an `init_t` file
descriptor while its corresponding `auditdeny` bit is clear. The source's
AV calculation and constraint handling are also in the pinned `services.c`.

## Broker, descriptor and pipe results

Both source contexts were computed independently:

- `system_u:system_r:system_dbusd_t:s0`
- `system_u:system_r:system_dbusd_t:s0-s0:c0.c1023`

Their results are identical for this bounded query set. The table shows all
22 permission checks per source context, for 44 total queries. Each API call
returned zero. There are ten permission denials across the two source
contexts, all in the `unconfined_service_t` FIFO group.

| Target context | Class and permissions | Decision for both source ranges | Requested `auditdeny` bits |
|---|---|---|---|
| `system_u:system_r:unconfined_service_t:s0` | `fd/use` | Allow | Set |
| Same target | `fifo_file/read,write,append,getattr,ioctl` | Deny each; reason is type enforcement | Clear for all five |
| `system_u:system_r:init_t:s0` | `fd/use` | Allow | Clear |
| Same target | `fifo_file/read,write,append,getattr,ioctl` | Allow each | Set for all five |
| `system_u:system_r:initrc_t:s0` | `fd/use` and the same five FIFO permissions | Allow each | Set for all six |
| `system_u:system_r:kernel_t:s0` | `fd/use` | Allow | Set |
| `system_u:object_r:null_device_t:s0` | `chr_file/read,write,ioctl` | Allow each | Set for all three |

The runtime integration task reported that its validator, `systemd-run`,
and the stdout/stderr pipe inodes used
`system_u:system_r:unconfined_service_t:s0`. It reported the broker launcher
in `system_dbusd_t` with the full category range. Those observations guided
this query set; this offline task did not capture the live broker child or
its file-descriptor receive operation. The evidence records that handoff
separately from the directly executed queries.

An inherited file descriptor has an opener security ID, while its inode has
an object label. The reported `/dev/null` inode label does not identify the
descriptor's opener ID. `kernel_t:fd use` was therefore queried as a separate
candidate and was allowed. Neither this result nor the character-device
result supplies the missing actual opener ID. See the per-query records and
the `runtime_context_handoff` section in
[the evidence](evidence/selinux-access-query.json).

## Existing service-entry permissions

The first follow-up queried 11 permissions. A retained second follow-up adds
the requested `setexec` permission and reruns that bounded set. The final
12 queries all return zero and allow the requested access:

| Source → target | Class | Queried permissions | Result |
|---|---|---|---|
| `init_t` → `init_t` | `process` | `setexec` | Allow |
| `init_t` → `initrc_t` | `process` | `transition` | Allow |
| `initrc_t` → `bin_t` | `file` | `entrypoint`, `execute`, `read`, `open`, `getattr` | Allow all five |
| `initrc_t` → `shell_exec_t` | `file` | Same five permissions | Allow all five |

Process contexts here are `system_u:system_r:TYPE:s0`; file contexts are
`system_u:object_r:TYPE:s0`. Each service-entry attempt first reconstructs the
same private library database using the original query engine. Its complete
44-query result is serialized and required to reproduce the original
`f556fbb6…` result hash before the entry queries run.

These results support testing the existing `initrc_t` entry with an explicit
execution context and the original Python command. They are not an
exhaustive proof of the systemd execution path, domain transition, subsequent
commands, broker operation, or confinement behavior. The separate runtime
candidate must require the actual expected process context and rerun its
Enforcing behavior checks. No policy module, file label, boolean, or service
unit was changed by this task.

The file-context lookup also distinguishes symlinks from their executable
targets. The qualified ARM64 `matchpathcon` returned these policy defaults:

| Path | Default context from the fixed file-context files | Source-tree identity |
|---|---|---|
| `/usr/bin/sh` | `system_u:object_r:bin_t:s0` | Symlink to `bash` |
| `/usr/bin/bash` | `system_u:object_r:shell_exec_t:s0` | Regular executable |
| `/usr/bin/python3` | `system_u:object_r:bin_t:s0` | Symlink to `python3.15` |
| `/usr/bin/python3.15` | `system_u:object_r:bin_t:s0` | Regular executable |

All four frozen source-tree paths returned `ENODATA` for `security.selinux`;
the defaults above are **not** observed xattrs from the live VM. The lookup
command, actual `matchpathcon` and libselinux hashes, and every consulted
file-context input hash are retained in the evidence.

A limited read of the installed `init`, `dbus`, and `unconfined` CIL modules
found an explicit `init_t` + `shell_exec_t` → `initrc_t` rule and an optional
`init_t` + `bin_t` → `unconfined_service_t` rule in `init/cil`. It did not prove
the complete compiled automatic-transition relation or resolve all module
attributes and optional blocks. The requested separate `domain/cil` does not
exist in this installation. Broader CIL investigation was stopped when the
integration task selected a direct explicit execution context, avoiding the
proposed extra shell execution. No absence of a rule is inferred from the
limited search.

## Execution records and reproduction

All three recorded query jobs exited successfully; their stderr files are
empty. Each ARM64 invocation has a 45-second bound. The original attempts
remain in the new work prefix, and no background query or transfer remains.

| Attempt | Start UTC, 2026-11-23 | Elapsed seconds | Queries in the phase | Stdout SHA256 |
|---|---|---:|---:|---|
| `query-01` | 03:56:24.128106 | 8.947 | 44 | `f556fbb650713298b380e7d05e7677b49c683abc6d6dd42af4d1d61b92f096a3` |
| `service-entry-01` | 04:00:27.830096 | 4.268 | 11 | `6902c2b5abffa486e6671ded42cd563656525bd166c7b58958101a1c179bd32b` |
| `service-entry-02` | 04:02:23.982787 | 4.376 | 12 | `f68c9a632875ac2f2f96d95f5b8321673e9dda3b8dd5d215ace3b779a53e0d2a` |

The public helpers are
[`query_policy_access.py`](../../../scripts/research/selinux/query_policy_access.py)
and
[`query_service_entry.py`](../../../scripts/research/selinux/query_service_entry.py).
The former is 12,847 bytes with SHA256
`43f81b1334aeac1691529a699a6b8dad923ada9b5f16e38b2c45643ead9736d3`.
The final entry helper is 6,928 bytes with SHA256
`5397f6a590c64fe8ab1c3b087dec8791c79c3d6362840dac5ea17e18c7fe4021`.
For immutable attempt retention, that final helper is named
`query_service_entry_v2.py` in the remote work directory; the first version
remains beside it under its original name and hash.

The query engine requires the exact qualified compatibility helper at
`/analysis/verify_selinux_compatibility.py`. In the actual runs, `/analysis`
was a PRoot bind of the new work prefix. Python was invoked with `-B -I`;
`SYSTEMD_OFFLINE=1` was set. The evidence records the complete PRoot argument
arrays, host-library environment override, runtime executable hashes, and
`run_job.py` commands. No new packages, binfmt registrations, or host/container
configuration changes were needed.

Two bounded preparation failures are retained rather than hidden: a source
manifest append used the wrong container type before its `files` array was
updated correctly, and a first CIL lookup stopped on the absent `domain`
module. Both failed before the relevant query and neither changed the frozen
root filesystem or policy. They are separate from all three successful AV
executions.
