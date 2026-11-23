# R4D / v7: real FD forwarding and TasksMax work; complete verification fails

**The production VM failed.** This independent candidate reached the real
system-bus FD route and completed the controlled `TasksMax=3` behavior test.
It also produced the source-qualified BPF-attachment log. It did not reach
the BPF filesystem-restriction behavior test: the verifier stopped at an
incorrect PL061 driver-directory check. Two visible Enforcing SELinux
denials remain failures, independently of that fixture error. Concurrent
console output also corrupted two JSON progress frames, causing the host's
strict parser to reject the serial result. None of these failures is erased
or rescored.

The immutable machine record is
[evidence/fedora-r4d-reload-fd-failed.json](evidence/fedora-r4d-reload-fd-failed.json),
242,167 bytes, SHA-256
`6fb7125cc66bbb650c168a233eb6f13bbe56be759df11f47403ff7e2fc410e74`.
This is a generic ARM64 QEMU result. It adds **zero owner-tablet Linux boots
and zero device acceptance passes**. QEMU used no Lenovo board DT, physical
device passthrough, network or host filesystem share.

## Candidate and exact execution source

The independent work directory is `/work/fedora-input-system-v7` in the
standard HDD Docker builder `tb371fc-build-20261123` on CT102. It uses the
frozen `6.12.114-tb371fc-research4-system` Image, its qualified 84 modules,
69 owner firmware files and the joint display/input DT. That DT is staged
as a board artifact; it is not passed to generic `virt`.

The actual 18-file recipe is
`/work/fedora-input-system-recipe-r4-v5`. Its 2,408-byte manifest has SHA-256
`0779fa0982a23fe9e30c58d17f721df8222d438b7329370fdaa918d13075879b`.
The public profile is
`scripts/research/input/system-integration/profiles/reload-and-fd-contract-v7`.
The [execution source record](evidence/fedora-r4d-execution-source.json)
maps every executed file to its public source and records the actual
materialization/readback. The profile-source manifest SHA-256 is
`8b70be328295fa01789a34b7a8212c9424c926890889b2881002a7163d8c619f`.
Those sources and manifests remain the exact executed versions.

The [native baseline preparation](evidence/fedora-r4d-baseline-preparation.json)
completed before target execution. Source and destination canonical streams
were each 1,323,141,120 bytes with SHA-256
`1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96`.
The copy preserved ACLs, xattrs, modes and numeric ownership. This profile
did not run PRoot against the original R1 source tree; target commands used
the separate candidate. Earlier source-copy failures and their timestamp
differences remain in their original records.

The [pre-execution plan](fedora-r4d-profile-plan.md) remains a historical
contract. This report is its subsequent execution outcome.

## Actual phase results

The only full pipeline was CT unit `tb371fc-r4d-full-01`, started at
2026-11-23 06:28:51 UTC. It ended at 06:39:03 UTC with **exit 1**, after
612.119 seconds.

| Phase | Actual result | Duration |
|---|---:|---:|
| Checked runtime staging | Exit 0 | 4.006 s |
| Independent system configuration | Exit 0 | 6.002 s |
| Maintenance and production archives/checks | Exit 0 | 246.064 s |
| New ext4 image construction | Exit 0 | 50.807 s |
| Maintenance labeling job | Exit 0 | 171.605 s |
| Production verification job | **Exit 1** | 133.549 s; QEMU lifetime 130.727 s |
| Separate full-log udev qualifier | **Exit 1** | Original failure retained |
| Successful-system finalizer | Not run | Prerequisite failed |

The maintenance QEMU lifetime was 170.773 seconds and its controller passed.
Its explicit permissive labeling phase and production Enforcing phase used
separate archives. Maintenance denials are retained in its own raw log;
they are not presented as a clean production run.

The production controller observed `guest reported failure` and reaped its
owned QEMU child. QEMU's exit code was 0, but the controller's result remains
`passed=false`. Its `parse_error` is `JSONDecodeError: Extra data: line 1
column 344 (char 343)`. No complete-system marker or final successful guest
record was produced. A clean production poweroff is not claimed.

| Retained artifact | Bytes | SHA-256 |
|---|---:|---|
| R4 kernel Image | Frozen R4 artifact | `8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb` |
| Maintenance initramfs | 30,710,088 | `b3c7da991b932c99205a1f26aa13f6a9f6452321468899dd526e12ce6346b3a6` |
| Production initramfs | 32,529,897 | `025a6a91d03ccf7804eaf13c41045dcc5eaefe460c5c554886b2b17ba34cff3a` |
| Actual system profile | 2,639 | `4ea240ace9d45f49d9b594085eb7b8d59f3aafdcdcd427082b86a7a307bbb2a6` |
| Failed image after owned QEMU exited | 4,294,967,296 | `ca8ef996fe1f1436c12a4da5db3828fbd914326e4f88bc72a52bf3bddacee148` |
| Original production controller result | 1,261 | `0543d6f1cdc346c19977639faa9ac7776196c10bd827ecef093580e8b61355c5` |

The failed image is retained at
`/work/fedora-input-system-v7/fedora45-research4d-reload-fd-contract.ext4`.
Freezing evidence did not mount, replay, repair or write that image. No old
R1/R3/R4/v5/v6 candidate, kernel build or source recipe was modified.

## Policy and early-boot improvements actually observed

The source policy.35 is the separately built and fully compared
[combined candidate](selinux-policy-map-self-candidate.md): 3,835,432 bytes,
SHA-256 `e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269`.
Against the original policy, its full version-35 and independently converted
version-33 CIL differ only in `init_t` mapping the correctly labelled
`semanage_store_t` policy file and `init_t` self `setcurrent`/`dyntransition`.
Contexts and the remaining SELinux tree retain their fixed original bytes.
Those narrowly scoped additions are not a claim that all policy/runtime
contracts are now complete; the new denials below show otherwise.

The 72,048-byte V2 native loader has SHA-256
`cc042c9fc4e92c75803215649c99bd87badd301bb05aa16820b43aaeb8fb50bc`.
Its original build record used the same-size map-only `0dd46af3…` policy.
That record is unchanged. The ELF has no embedded policy hash; v7's joint
input record, archive checker and guest separately pin the complete `e1a63…`
policy identity. No rebuild against the combined policy is invented.

The actual production archive passed the independently derived checker
`8028eb780ff6f9d13485904bde6b8b5b3599bb555037a264d1c88ca02d417e82`.
The [full archive validation](evidence/fedora-r4d-reload-fd-initramfs-validation.json)
retains the original baseline, policy/context comparison, exact bootstrap
artifacts, firmware payloads, ARM64 ELF/dependency closure and target-cache
semantics. The explicit new `stat` tool comes from the fixed Fedora source
payload, rather than being assumed present in the old archive. The
[construction records](evidence/fedora-r4d-reload-fd-construction.json) retain
the exact phase metadata, and the
[proof-payload record](evidence/fedora-r4d-reload-fd-initrd-proof-payloads.json)
identifies the actual script, service and activation link.

The raw production log contains, in order, the original root-migration and
cleanup markers, V2 initial policy load, successful standard systemd
calculated-init-label transition and policy reload, and the schema-3
initrd-domain record. The same-boot record observes PID 1 as `init_t`, udevd
as `udev_t`, and journald as `syslogd_t`. It also observes the correct
`null_device_t` and `kmsg_device_t` labels on `/dev/null` and `/dev/kmsg`,
`var_run_t` on `/run`, and `syslogd_var_run_t` on the actual journal paths.
The ordinary tmpfs root has device `0:20`, distinct from the cleaned old
root `0:2`. These are retained partial observations, not a rewritten
aggregate controller pass.

### Actual exported kernel policy

This time the management service exclusively created and fsynced a bounded
ordinary export of that boot's `/sys/fs/selinux/policy`, together with its
identity record. The actual exported version-33 bytes are **3,835,420 bytes**,
SHA-256
`0fe3c0e16007f42cb15f05e5ec35fe4b20c5d876a7d1219a558fc3593a3a0e29`.
This is not the offline conversion `ce6ccbfd…`, and no equality between those
serialized artifacts is presumed.

After QEMU exited, read-only `debugfs` retained the two ordinary files under
`/work/fedora-r4d-closed-image-evidence-v1`. The policy payload, version,
0600/root metadata and accompanying JSON were checked against the intact
same-boot serial export record. Source image size, inode, mtime and ctime
did not change. No `debugfs -w`, mount, filesystem replay, repair, policy
load or extra VM was used. The public
[export metadata](evidence/fedora-r4d-loaded-policy-export.json) keeps the
identity; the retained ordinary policy can support subsequent read-only AV
analysis without inventing an earlier policy export.

## Actual system-bus and TasksMax results

The validator and all controlled transient workers use the existing
`system_u:system_r:sysadm_t:s0` management-test domain. This is a scoped
test-service choice, not a claim that production daemons can generally use
that domain. The actual broker child was observed as
`system_u:system_r:system_dbusd_t:s0-s0:c0.c1023`, PID 226 with parent 222.
It had a 16,384-descriptor limit and 24 open descriptors in the retained
failure diagnostics. PID 1 remained `init_t`.

The broker `GetId` and systemd manager `Version` requests returned over the
real system bus. The subsequent controlled `noop` worker completed through
`systemd-run --wait --pipe --collect` with exit 0 and no payload stdout.
It did not execute `/usr/bin/true` and did not replace the system bus with
the manager's private socket.

Before GO, the parent externally observed the same held worker's executable,
argv, start identity, cgroup, requested/actual unit properties and all three
forwarded FIFO endpoints. Creator, client and worker contexts, inode labels,
endpoint identities and read/write directions matched the contract. All
82 same-boot AV queries completed for each exercised route using the actual
exported bytes. They cover the broker, PID 1 and qualified worker receiving
ends, policy reload/export/entry requirements and retained restrictions.
The worker-domain premise in the AV helper was separately closed by actual
process readback; it was not silently treated as an observation.

The actual controlled TasksMax worker then produced:

| Measured behavior | Actual result |
|---|---|
| Unit and cgroup process limit | `3` |
| Child-creation attempts | `3` |
| Successfully created children | `2` |
| Rejected third creation | `EAGAIN`, errno `11` |
| `pids.events:max` | `0` → `1` |
| All owned children reaped | `true` |
| Worker/client outcome | Exit `0`, no payload stdout |

This is a real enforcement observation, beyond a readable controller file.
The worker and two children account for the three allowed tasks. It does
not establish complete system acceptance or physical-tablet behavior.

The earlier runtime-hash checkpoint also matched the active 84-module and
69-firmware inventories. Later source-order checks reached the PL061 guard,
but no final full-foundation result was emitted. Unemitted aggregate results
are not reconstructed as passes from that control-flow inference.

## Exact stopping gate: wrong PL061 fixture path

The first guest exception is:

```text
require(bool(bound_gpio), 'virtual PL061 driver is not bound')
RuntimeError: virtual PL061 driver is not bound
```

The frozen verifier searched `/sys/bus/amba/drivers/pl061`. The actual R4
`drivers/gpio/gpio-pl061.c` registers `.drv.name = "pl061_gpio"`; the correct
directory is `/sys/bus/amba/drivers/pl061_gpio`. The qualified source is
11,443 bytes, SHA-256
`b292ee41f60cd68e0d1a398a0ee97931983ebba43eb99c4370591ac473333d86`.
The raw VM log also contains:

```text
[    1.413804] pl061_gpio 9030000.pl061: PL061 GPIO chip registered
```

This establishes a concrete fixture bug and an actual driver-registration
message. The failed run did not read the corrected sysfs directory. Its
binding gate remains failed; source inspection and a registration log do not
retroactively produce the required actual symlink/compatible observation.
The correction belongs in a new profile, followed by a full new execution.

### BPF attachment is observed; restricted behavior is not run

The complete raw production log contains the exact source-qualified marker
`bpf-restrict-fs: LSM BPF program attached` twice, at byte offsets 27,095 and
224,713. Both are actual startup console lines. The matched
[systemd source contract](systemd-bpf-runtime-contract.md) places that log
after a successful LSM-program attachment. It is therefore positive
attachment evidence, independently of the R4 configuration.

The PL061 exception occurred before the unrestricted `proc-read` worker was
started. Neither the baseline read nor the `RestrictFileSystems=~proc`
direct-open/`EPERM` behavior test ran. The attachment messages cannot fill
that missing behavior result. No BPF-denial success is claimed.

## Two visible Enforcing denials remain

| Actual point | Visible kernel AVC | Relationship to the failure |
|---|---|---|
| 36.352137 s, audit 4 | PID 1 `init_t` → `systemd_varlink_registry_t`, `lnk_file unlink`, `io.systemd.Udev`, `dev="tmpfs"`, `permissive=0` | During the udev varlink-socket stop/deactivation sequence; independently violates the zero-AVC gate. |
| 126.049789 s, audit 68 | `journalctl_t` → `syslogd_var_run_t`, `sock_file write`, `io.systemd.journal`, `dev="tmpfs"`, `permissive=0` | Produced by the failure handler's `journalctl --sync`, after the PL061 exception. It is not the cause of the earlier FD or TasksMax operation. |

These are visible direct kernel records, not a claim that all possible audit
events are exhaustively inventoried: the raw log also reports
`kauditd_printk_skb: 6 callbacks suppressed`. Their raw lines and the original
diagnostic outcome are retained. No blanket allowance, relabel to another
type, enforcement toggle, ignored sync error or live-image policy edit was
used to make this run pass. Further exact-source and actual-policy analysis
must distinguish required registry cleanup and journal transport operations
from the independent verifier bugs.

## Serial framing failure and preservation boundary

The independent freeze operation accepts only complete original progress
lines that parse as one JSON object. It retained 19 such frames and records
two malformed frames with their byte offsets, lengths, hashes and bounded
excerpts. It does not strip appended kernel text, concatenate broken JSON
fragments or rerun the controller's acceptance decision.

One `journal_sync` progress object is immediately followed on the same
serial line by a kernel audit record. That produces the original
`Extra data` parser error. A later large `kernel_security_journal` object is
interrupted inside its escaped string by an `hrtimer` warning and a newline.
Direct writes to the console therefore did not provide a lossless JSON
channel under concurrent kernel output. The intact noop, descriptor,
TasksMax and failure-context frames remain useful partial evidence; the
missing complete result remains missing.

The next independent profile should persist its complete result to a fixed
ordinary file with exclusive/no-follow creation, 0600 permissions, and file
and parent-directory fsync. A short unique console credential can identify
that boot/profile and the file's bytes/hash. Only after QEMU is closed can
read-only image extraction qualify the regular file's metadata and identity.
All functional gates, actual process/FD observations, QEMU lifecycle checks,
full-raw zero-AVC requirement and initrd evidence must remain required. This
design is not applied to repair the old v7 log or result.

## Udev boundary, raw artifacts and freeze identity

The separately executed
[udev qualifier](evidence/fedora-r4d-reload-fd-udev-qualification.json)
retains the original failed VM result and returns exit 1. Its conditional
full-log scan found no matching storage/restore failure prefixes, no positive
serialized/restored count pair and no root-side accepted serialization-FD
line. Those observations do not turn the failed system into a pass. Missing
count lines cannot prove that the original queue was empty; counts only
cover successful stores/inserts when they are actually present.

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| [Maintenance raw log](evidence/fedora-r4d-reload-fd-failed-label.log) | 1,085,516 | `4a962aaf2c0c1b02f67e41e20a870251e53e44106ec059c40c7325abcb365b5d` |
| [Production raw log](evidence/fedora-r4d-reload-fd-failed-verify.log) | 1,115,806 | `cfe215d2a33dc01f8ffdf7ab5bc2d7dd2f7fafec309d06c82eb3db48bb5658aa` |
| [Production controller](evidence/fedora-r4d-reload-fd-failed-verify.json) | 1,261 | `0543d6f1cdc346c19977639faa9ac7776196c10bd827ecef093580e8b61355c5` |
| [Full archive check](evidence/fedora-r4d-reload-fd-initramfs-validation.json) | 125,540 | `4bbe5d096d2dcd6f498fb9746b9a417774a30bf0073fe504c734b1d40adf04b3` |
| [Independent udev qualification](evidence/fedora-r4d-reload-fd-udev-qualification.json) | 2,131 | `7c19e4eaef136b4eb584f3b82ff5113fab1b0508049fda340b17ce4a13b686f9` |

All raw CR/LF bytes are preserved. The independent freezer is
`scripts/research/input/system-integration/freeze_reload_fd_failed_attempt.py`,
13,119 bytes, SHA-256
`19822e3f21ff44a98d683a21e59a74fd37744e7032c85eef7cb539f23a2f3c5d`.
Its [job record](evidence/fedora-r4d-failure-freeze-job.json) retains the
qualifier's exit 1 and freezer's exit 0. The latter means the completed
failure and ordinary export were preserved, not that the VM passed. A later
candidate must execute the full system gates again; all physical display,
input, pen charging, radio, audio, camera, power and Android-parity acceptance
remains unpassed.
