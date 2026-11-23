# SELinux reload and management-service contracts after the v6 failure

## Result and scope

Two bounded, offline queries completed successfully against the fixed Fedora
policy and AArch64 libsepol. Query 01 evaluated 147 access vectors. Query 02
retained those 147 results exactly and evaluated 41 additional worker, stdin and
policy-export permissions. The existing `sysadm_t` domain satisfies the queried
management-service contract for **both the D-Bus broker and PID 1**, and for a
worker explicitly placed in the same domain. The coordinator selected it for a
new, separate validation profile. No service was started or relabeled by this
task, and this is not a successful VM or tablet acceptance result.

The policy-file results also isolate a concrete permission gap: `init_t` can
`read`, `open` and `getattr` a `semanage_store_t` file, and has `security:load_policy`,
but cannot `map` that file. This agrees with the actual v6 denial. It does not
establish that every later step of policy reload will succeed after that gap is
addressed.

All raw decisions, return codes, commands, source identities and role/type
declarations are in
[selinux-runtime-contract-query.json](evidence/selinux-runtime-contract-query.json).
The unchanged earlier runtime failure is recorded in
[fedora-r4c-tmpfs-failed.md](fedora-r4c-tmpfs-failed.md) and its
[serial log](evidence/fedora-r4c-tmpfs-failed-verify.log).

## Three policy identities must remain separate

| Object | Bytes | SHA-256 | Used by these queries? |
|---|---:|---|---|
| Frozen Fedora on-disk `policy.35` | 3,835,432 | `928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430` | Yes, as the source input |
| libsepol conversion of that file to version 33, in private process memory | 3,835,420 | `aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe` | Yes, the actual queried policy |
| Earlier VM's `/sys/fs/selinux/policy` bytes observed in guest memory | 3,835,420 | `9c79cb12810a781d6cb91f9b7dff160a1d768c534b784743b4256015799f22a8` | No retained ordinary-file copy was available |

The v6 guest really read its loaded policy, hashed those bytes, and passed them
directly to its 15-query userspace probe. It did **not** save those bytes to a
normal file. The earlier research1 record likewise did not provide a retained
original for this task. A nonexistent export was not substituted with the
offline conversion, and no new VM was started merely to obtain it.

Accordingly, all new matrices below are **offline candidate results on `aab7…`**.
The existing v6 AVCs and its 15 live-policy query results are separate runtime
observations. Matching results for an overlapping subset do not establish
semantic equivalence of the two policy hashes. A subsequent candidate policy
with an added permission will have another identity and requires its own
qualification and actual loaded-policy checks.

The fixed queried library is Fedora AArch64 `libsepol.so.2`, 802,880 bytes,
SHA-256 `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b`.
Both policy and library were copied, hash checked, into the new private
`/work/selinux-runtime-contract-v1/inputs` directory before execution.

## Runtime observations that motivated the queries

At boot time **10.011635 seconds**, v6 audit event **3** denied PID 1
`init_t` the `map` permission on
`/etc/selinux/targeted/policy/policy.35`, labeled `semanage_store_t`, with
`permissive=0`. The next serial message says loading the new policy failed and
the old policy is retained. This is an actual denial, independent of the
offline calculation.

At **132.115713 seconds**, audit event **226** denied PID 1 `init_t` a
`fifo_file:write` on `pipe:[7512]`, whose inode label was
`system_u:system_r:initrc_t:s0`. The next line reports `MSG_CTRUNC`, with one
descriptor received where three were declared. The actual broker child was
`system_u:system_r:system_dbusd_t:s0-s0:c0.c1023`.

The earlier live probe showed that this broker could receive descriptors and
FIFO access from `initrc_t`. It did not query the **manager's separate receive
step**, or a later worker's access. Thus the broker result did not establish the
complete descriptor transfer. These observations remain failures in the frozen
v6 report; no earlier gate or result was edited.

## Policy-file read and reload matrix

| Source | Target | Class | Permission | Offline result |
|---|---|---|---|---|
| `init_t` | `semanage_store_t` | `file` | `read` | Allow |
| `init_t` | `semanage_store_t` | `file` | `open` | Allow |
| `init_t` | `semanage_store_t` | `file` | `getattr` | Allow |
| `init_t` | `semanage_store_t` | `file` | `map` | **Deny** |
| `init_t` | `security_t` | `security` | `load_policy` | Allow |
| `init_t` | `security_t` | `security` | `read_policy` | **Deny; separate diagnostic** |

The first five rows identify `map` as the missing permission in this particular
read-and-reload contract. The denial reason returned by libsepol is the type
enforcement bit, with a successful API return; it is not a parsing error.

`security:read_policy` is a different operation. The fixed Linux 6.12.114
`selinuxfs.c` checks it when opening and reading the **kernel policy export**.
It is not the permission for reading the ordinary `policy.35` file, nor the
permission that permits a reload. PID 1 is not assigned this export permission
by selecting a different management-service domain. Query 02 instead checks
that the management service can perform the export.

No allow rule was added by this task. The separate policy/source work must
retain the source file's intended label and qualify any narrowly derived
policy as a new artifact. Other v6 denials, including the journal-file mapping
case, are outside this query's proposed correction and remain separate work.

## Both broker and manager need a descriptor contract

Here `B` is the actual broker context
`system_u:system_r:system_dbusd_t:s0-s0:c0.c1023`, and `I` is
`system_u:system_r:init_t:s0`. Each target is
`system_u:system_r:<type>:s0`. **A** means allowed; **D** means denied.
The five rightmost columns are `fifo_file` permissions.

| Receiver | Creator / FIFO type | `fd:use` | `read` | `write` | `append` | `getattr` | `ioctl` |
|---|---|---|---|---|---|---|---|
| B | `initrc_t` | A | A | A | A | A | A |
| I | `initrc_t` | A | D | D | D | D | D |
| B | `unconfined_service_t` | A | D | D | D | D | D |
| I | `unconfined_service_t` | A | D | A | A | A | A |
| B | `unconfined_t` | A | A | A | A | A | A |
| I | `unconfined_t` | A | A | A | A | A | A |
| B | `sysadm_t` | A | A | A | A | A | A |
| I | `sysadm_t` | A | A | A | A | A | A |

This table does not equate a descriptor's opener SID with an inode's label.
In the fixed kernel, `selinux_file_alloc_security()` saves the current SID in
the file security object. `selinux_file_receive()` checks that opener through
`fd:use`, then checks the inode's label with the access implied by the actual
file mode. `FMODE_READ` requires `read`; writable descriptors require `write`
or `append` according to their flags. This explains why inspecting a retained
read end is insufficient to qualify a forwarded write end.

The source locations are `security/selinux/hooks.c` 1740–1805, 2021–2040,
3681–3689 and 4204–4208, in the pinned research4 source. Its SHA-256 is
`6079b88f15ca1966b640753e35edc291139fe925fca37e5c54d0a2d6e36d8370`.
The evidence records the complete source path and identity.

## A legal explicit management-service entry

The installed policy source was read without executing it. A scan of the 426
module CIL files in the frozen priority-100 store found these declarations:

| Module | Relevant declaration |
|---|---|
| `base` | `userrole system_u system_r` |
| `sysadm` | `type sysadm_t`; `roletype system_r sysadm_t` |
| `unconfineduser` | `type unconfined_t`; `roletype system_r unconfined_t` |
| `init` | `type initrc_t`; `roletype system_r initrc_t` |
| `unconfined` | `type unconfined_service_t`; `roletype system_r unconfined_service_t` |

There was no `systemd_run_t` declaration in that scanned store. The distinct
`systemd_run_generator_t` type is not evidence of a `systemd-run` client domain.
Compressed and decoded source hashes, line references, and the module-inventory
digest are preserved in the evidence.

The full candidate contexts were also accepted by `sepol_context_to_sid`.
This API reaches `context_from_record()` and `context_is_valid()`, which check
role/type membership, user/role membership and MLS validity. The returned SIDs
are private to the querying process; they are not live kernel SID numbers.

For the selected existing management domain, the relevant candidate unit
setting is:

```ini
SELinuxContext=system_u:system_r:sysadm_t:s0
```

There is no ignore-failure prefix. The intended scope is the controlled
validation-management service and its explicitly selected test workers, not a
proposal to move unrelated production services into an administrative domain.

All of the following queried permissions were allowed:

- `init_t` to itself, `process:setexec`.
- `init_t` to the candidate `sysadm_t`, `process:transition`.
- `sysadm_t` to both `bin_t` and `shell_exec_t`, `file:{ entrypoint execute read
  open getattr map }`.
- `sysadm_t` to its own FIFO label, `{ create read write getattr ioctl }`, and
  its own descriptor label, `fd:use`.
- D-Bus `send_msg` in both directions between `sysadm_t` and each of the broker
  and PID 1.

The kernel honors an explicit exec SID before considering a default type
transition; it then checks process transition and the executable entrypoint.
These source and AV checks support this candidate entry. They do not prove a
successful live service exec, or compute the automatic domain transition of a
subsequent `systemd-run` exec. Query 02 additionally found
`sysadm_t` to `bin_t:file execute_no_trans` allowed. The new VM must still read
back the actual validator, client and worker contexts. No shell intermediary
or blanket assumption about later process labels is needed.

## Query 02: worker, stdin and actual-policy export

The new profile's selected worker is explicitly `sysadm_t`. Its
`fd:use` and all five FIFO permissions toward a `sysadm_t` creator were allowed.
The default `unconfined_service_t` worker was queried as a comparison and also
allowed those six permissions, but it is not the chosen worker contract.

The input-integration work plans a newly created stdin pipe owned by the
management domain, alongside observable stdout and stderr endpoints. This
gives an explicit creator history and allows the actual descriptor direction,
inode identity and process context to be checked. It avoids treating a
`/dev/null` inode label as proof of an inherited descriptor's opener SID.

The additional null-device queries remain auxiliary facts:

| Query | Offline result | Required by the new stdin-pipe contract? |
|---|---|---|
| `sysadm_t` → `null_device_t:chr_file` `open/read/write/ioctl/getattr` | Allow | No; auxiliary userspace compatibility check |
| `sysadm_t` → `null_device_t:chr_file` `map` | **Deny** | **No** |
| Broker, PID 1, selected worker and comparison worker → `null_device_t:chr_file` `read/write/ioctl/getattr` | Allow | No; the new controlled stdin is a pipe |

No null-device mapping permission is proposed. Query 02's only additional
denial is this explicitly nonrequired `map` check.

For the management service's planned export of the actual policy, all of these
were allowed:

- `sysadm_t` → `security_t:security read_policy`.
- `sysadm_t` → `security_t:file open/read/getattr`.
- `sysadm_t` → `security_t:dir search/getattr`.

The new VM must perform a bounded read, preserve the original bytes in a
restricted ordinary file, and run its expanded AV checks on those exact bytes.
This is assigned to the management service; PID 1's `read_policy` denial remains
unchanged. Offline results cannot substitute for the new same-boot checks.

## Execution and source identity

Both runs used direct `/usr/bin/qemu-aarch64` with the qualified Fedora v3
Python and runtime prefix, `-I -B`, and private copies of the fixed inputs.
There was no PRoot, mount, nested VM, libselinux call, kernel policy write,
boolean change, or rootfs assembly in this task. The sampled root, `dev` and
`etc` directory inode/mtime/ctime values in both R1 and v3 were unchanged.
That sampling is a limited metadata observation, not a whole-filesystem audit.

| Run | Exit / elapsed | AV rows | Source SHA-256 | Stdout SHA-256 |
|---|---|---:|---|---|
| Query 01 | 0 / 5.168 s | 147 | `5599609752013d791957a5cfd7ae07488a6fced8fe00b8e5ce6e0d2a98bf895a` | `41527c5461209fcf066ba326947e111525fea6782f57a352466201ac8bd699f9` |
| Query 02 | 0 / 3.973 s | 188 | `bfc36fc4896b4fbd9f3ccdd897294e361389cb8955252befcc4c44c43c1c55d7` | `a8fbc85d57b9d17393ab12dcccad3b662f6fa72958cffb81a69b5fceaf08da7d` |

Public source files are
[query_runtime_contract.py](../../../scripts/research/selinux/query_runtime_contract.py)
and
[query_runtime_contract_v2.py](../../../scripts/research/selinux/query_runtime_contract_v2.py).
Query 01 is retained unchanged. Query 02 has a separate source, output and
execution record under `/work/selinux-runtime-contract-v1/query-02`.
Both stderr streams are empty and every AV call returned zero. Expected
permission denials are recorded as denials, not failed API calls; audit masks
are recorded separately from the allowed mask.

The ABI is pinned to SELinux Project commit
`2233a23a4d4f1bf29054037babec13f30d038e65`, including the public
[services API](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/include/sepol/policydb/services.h),
[AV structure](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/include/sepol/policydb/flask_types.h),
and [context validation](https://raw.githubusercontent.com/SELinuxProject/selinux/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/src/context.c).
The scripts check the 20-byte, five-`uint32_t` AV structure, use the public
process-private policydb loader, and retain all buffers until the corresponding
file/serialization operations are complete. Neither script calls the kernel's
policy-load interface.

Both foreground query processes have ended. No background query job or
additional hardware test remains from this task. The next decisive evidence is
the independently built profile's real Enforcing execution, including the
manager and worker descriptor checks, actual loaded-policy bytes, and unchanged
domains across the behavioral probes.
