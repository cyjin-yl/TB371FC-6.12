# R4E / v8: complete guest behavior and result transport work; one AVC fails the run

**The production VM failed overall.** Its complete guest result was written,
fsynced, recovered from the closed image and qualified without console JSON
repair. The actual system-bus/three-FD route, TasksMax enforcement, PL061
binding, signature enforcement, early SELinux domains and BPF filesystem
restriction behavior passed their guest checks. The original host controller
still returned `passed=false`: the full production log contains one Enforcing
SELinux denial during the successful-path `journalctl --sync`. That command
returned exit 0, so the separate full-log gate is essential.

The authoritative [failed-attempt record](evidence/fedora-r4e-persistent-result-failed.json),
[original controller](evidence/fedora-r4e-persistent-result-failed-verify.json),
[complete guest file](evidence/fedora-r4e-persistent-result-failed-guest.json) and
[unaltered raw production log](evidence/fedora-r4e-persistent-result-failed-verify.log)
retain this distinction. The aggregate record is 773,286 bytes, SHA-256
`099bcd2a4c76de06ce73aa2c985d0dca6e1d32725ca748a03e63c4b28ced1392`.
No failed controller or prior candidate was rescored.
This is **host-build/generic-VM evidence**. It adds **zero owner-tablet Linux
boots, zero physical-device passes and zero complete-system acceptance passes**.

## Exact candidate and execution

The independent work directory is `/work/fedora-input-system-v8` in the
standard Docker builder `tb371fc-build-20261123` on CT102. It retains the
qualified R4 Image, 84 modules, 69 firmware files and joint display/input DT.
The DT is staged as a board artifact. QEMU uses its own generic `virt` tree,
two Cortex-A72 virtual CPUs and 2 GiB RAM, with no network, physical-device
passthrough or host filesystem share. No tablet, GPU, touchscreen, pen,
keyboard, Wi-Fi or other owner hardware is exercised by this VM.

The [historical execution plan](fedora-r4e-profile-plan.md) records the launch
contract at 07:45 UTC. The [execution-source record](evidence/fedora-r4e-execution-source.json)
records actual materialization and readback. The executed public profile is
`scripts/research/input/system-integration/profiles/persistent-result-v8`.

| Frozen source identity | Value |
|---|---|
| Profile-source manifest | `f705c87a1c5efe082ae134febc139e8ce437818951c83a9709bd475d17fc60d2` |
| Actual 20-file recipe manifest | `c453d67a35b466be76924eceb7f3af96bfd15ed313ee5cba11963a9de91fcb94` |
| 28-file source packet | 90,499 bytes; `b844cda5e2cbb488248205eb974ee2c6dbc614a2d42656c760db5b1326f46698` |
| Materialized recipe | `/work/fedora-input-system-recipe-r4-v6` |
| Immutable overlay | `/work/fedora-r4e-source-overlay-v1` |
| Unique pipeline unit | `tb371fc-r4e-full-01.service` |
| Invocation ID | `1627fbd7f92047d490302551aa1d3f98` |

All 20 executed files were checked before launch and again during evidence
retention. The temporary local-editor outage did not execute a fallback VM;
the recovered local source supplied this packet. The unused private fallback
base remains separate. The [native baseline preparation](evidence/fedora-r4e-baseline-preparation.json)
retains the actual ACL/xattr/ownership-preserving source copy and all 96 checked
ordinary runtime inputs. No PRoot was run against the original R1 source tree.

## Actual phase outcomes

The unique pipeline ran from **2026-11-23 07:45:46.156 UTC** to
**07:56:44.567 UTC**, returning **exit 1** after **658.410 seconds**.

| Phase | Actual outcome | Duration |
|---|---:|---:|
| Checked runtime staging | Exit 0 | 4.002 s |
| Independent system configuration | Exit 0 | 6.002 s |
| Both initramfs archives and their distinct validators | Exit 0 | 249.111 s |
| New ext4 image construction | Exit 0 | 57.028 s |
| Maintenance labeling | Exit 0 | 188.574 s |
| Production verification | **Exit 1** | 153.082 s |
| Separate udev post-qualification | **Not run** | Pipeline stopped |
| Successful-system finalizer | **Not run** | Pipeline stopped |

The production QEMU itself ended normally with **exit 0**, no controller
termination reason and a lifetime of **151.153 seconds**. There is exactly one
complete-system marker, no result-parse error and no result-file transport
error. The guest's `pass` envelope means its defined behavioral checks
completed before independent host qualification; it explicitly retains
`host_full_log_qualification_pending=true` and `complete_system_accepted=false`.

The maintenance phase uses a separate archive with explicit `enforcing=0` to
label the new image. Its [controller](evidence/fedora-r4e-persistent-result-failed-label.json)
passed, but its [raw log](evidence/fedora-r4e-persistent-result-failed-label.log)
retains 47 visible denials and nine suppressed-callback notices. Those are
maintenance observations, not evidence of a clean Enforcing production boot.

## Complete results survive console interleaving

The prior [R4D failure](fedora-r4d-reload-fd-failed.md) included damaged long
serial JSON. V8 instead creates a fixed, private ordinary result file using
exclusive creation, no symlink following, root ownership, mode 0600 and one
link. It fsyncs the file and directory, reads the bytes back, and emits a short
receipt containing status, boot ID, profile SHA, size and file SHA.

Only after reaping its own QEMU process does the host open the image read-only
and use `debugfs` without `-w` to inspect the fixed ancestors, file metadata and
payload. It does not mount, replay or repair the image. It checks the unique
full-line receipt, actual file bytes and same-boot identities. The actual
recovered result is **413,706 bytes**, SHA-256
`3e48c9a429cad37d8baabf3fed31fe9abefdbaedfb065a484faf445bb6c2fa11`.

Its boot ID is `905bf18c-cba9-4c58-99f6-9c8ff8d11366`; its actual profile SHA is
`08219c35262b1db44ed2ad55beea78785a7826057b24eb2f41861a4072a9c3fc`.
The reader's `qualified=true` only qualifies evidence transport. It never
overrides the separate raw-log failures. The earlier [six offline transport
cases](evidence/fedora-r4e-result-transport-qualification.json) are retained as
construction checks; this run adds actual normal-shutdown transport evidence.
It does not prove that read-only debugfs can recover every newly journaled file
after abrupt termination without journal replay.

## Early boot, policy and audit observation

The [standard-service candidate](selinux-standard-service-policy.md) has a full
version-35 and fresh-version-33 semantic difference limited to six permissions:
the existing map/self-setcon requirements, registry-link cleanup, journal
socket write and journal stream connect. The original file contexts, booleans
and unrelated permissions remain fixed. Its separately qualified
[86-row offline AV matrix](selinux-standard-service-av-query.md) is distinct
from the **82 unique live tuples per actual transient route** in this VM.
An offline candidate matrix does not predict every future service operation.

The [V3 loader](early-selinux-standard-services-loader.md) and [V2 cleanup
waiter](tmpfs-waiter-v2.md) are exact new inputs. The ordinary tmpfs migration
and old-root cleanup occurred before policy load. The host observed old device
`0:2`, new device `0:20`, and the strict stage0 → waiter V2 → V3 audit guard →
policy → systemd exec → same-boot process-proof order. The actual initrd proof
reports PID 1 in `init_t`, udevd in `udev_t` and journald in `syslogd_t`, along
with the required real `/dev`, `/run` and journal labels. Standard systemd
reload and calculated-init-label transition succeeded without their failure
warnings. Final PID 1 remained `init_t` and SELinux remained **Enforcing**.

The explicit generic-VM opt-in set only `printk_ratelimit` from **5 to 0** before
policy load. It reopened both settings and retained burst **10**. The guest
observed interval 0 and burst 10 before and after its behavioral tests. This
does not disable audit or SELinux, alter queue-loss behavior or change global
host settings. The V3 real `linux,dummy-virt` guard means this production
archive is a **generic-VM qualification artifact** and rejects the physical
tablet. It is not an owner-tablet boot archive.

Every configured production loss/suppression counter is zero: any caller's
positive callback-suppression notice, audit-specific suppression, backlog
overflow, positive `audit_lost` and the fixed audit loss reasons. The gate
deliberately treats generic callback suppression conservatively because the
printk limiter is shared. These are zero observed source-qualified signals;
they do not claim to disprove every theoretically unobservable event.

The same-boot actual `/sys/fs/selinux/policy` export contains **3,835,444 bytes**,
version 33, SHA-256
`9d7aa2b3d3c64e8c24dbff83e8850036b8e15cec63aaa1521bbea555f42b2342`.
The source policy.35 for this candidate is
`727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502`;
the independently converted offline v33 is `9b39b5a5…`, not the runtime export.
The complete result proves the active policy bytes stayed unchanged across
the tests. No equality between different serialized policy artifacts is
invented.

After this failed run ended, the new, separate
`freeze_persistent_result_failed_attempt.py` retained the already-created
ordinary policy and its metadata using read-only debugfs. The old passed-only
pipeline retention helper was not weakened or changed. The [retention
record](evidence/fedora-r4e-persistent-result-failed-policy-retention.json)
checks root/0600/single-link members, bounded sizes, header/version, complete
metadata and the qualified result's boot/hash identity. The private output is
`/work/fedora-r4e-closed-image-evidence-v1`. Public evidence contains metadata,
not the policy binary. No extra VM, kernel-policy load or image write occurred.

## Actual FD route and process limits

The management validation service, client and controlled workers were all
observed in the existing `system_u:system_r:sysadm_t:s0` test domain. This is a
scoped management-test choice, not a replacement domain for ordinary desktop
services. The broker and PID 1 retained their distinct domains. The real
system bus answered `GetId` and manager `Version` (`262.1-1.fc45`), and a held
`noop` worker completed through `systemd-run --wait --pipe --collect` with exit 0
and no payload stdout. It did not execute `/usr/bin/true` or bypass the broker
through the manager's private socket.

Before GO, the parent checked actual worker/client identity, start time,
executable, argv, cgroup, live unit properties, FIFO inode labels and all three
FD identities and access directions. The actual loaded-policy query checked
the broker, PID 1 and worker receiving ends as separate requirements. Each
route's exact 82-tuple set, raw decision bits, identities, retained denials and
composite flags passed. The worker-domain premise was independently closed by
actual process readback, not promoted from the query input into an observation.

The process-limit probe was behavioral:

| TasksMax measurement | Actual result |
|---|---|
| Target service limit | `3` |
| Child-creation attempts | `3` |
| Children created | `2` |
| Third attempt | `EAGAIN`, errno `11` |
| `pids.events:max` | `0` → `1` |
| Owned children reaped | All |

The worker plus two children occupy the three allowed tasks. The owned unit
was collected without changing a global limit or leaving a failed unit.

## BPF restriction is now measured, beyond attachment

The full raw log has **two** exact
`bpf-restrict-fs: LSM BPF program attached` lines. The matching
[Fedora/systemd source contract](systemd-bpf-runtime-contract.md) places this
message after successful LSM attachment. The behavioral test then completed
on this same boot rather than inferring behavior from a configuration symbol
or the attachment message.

| Same-worker comparison | Unrestricted baseline | Restricted case |
|---|---|---|
| Observed domain | `sysadm_t` | `sysadm_t` |
| `RestrictFileSystems` readback | `~` | `~proc` |
| Operation | Direct `open`/`read` of `/proc/version` | Same |
| Exit | 0 | 1 |
| Failure phase | None | **`open`** |
| Error | None | **`EPERM`, errno 1** |
| Data | **181 bytes**, expected actual release | **0 bytes**, empty stdout |

Both runs used the same installed worker hash, argv, nonce, service/cgroup and
management domain; the restriction property was the intended difference.
The parent observed held worker FDs and live unit properties in both cases.
The unrestricted payload SHA is
`70c530fd5053b65b51cae92c6f4a122d3b4a998f7cbd67cad02d94a10dab2188`.
The restricted result matches the fixed source's `lsm/file_open` denial with
`-EPERM`; a read-stage failure, EACCES or generic nonzero status would not pass.
The active policy was unchanged across this comparison. All owned workers
and units were cleaned up.

Other completed guest checks matched **84 modules** and **69 firmware files**,
the actual kernel BTF, signature enforcement and the signed loaded `autofs4`.
The frozen kernel still has `CONFIG_MODULE_SIG_FORCE=n`; this VM explicitly
uses `module.sig_enforce=1` and reads enforcement back. This does not claim
that the compile-time setting changed or that an unsigned-module negative
load test was performed.
Kernel taint stayed **0**, no failed units remained, and systemd/udev/D-Bus
were active. The actual PL061 driver directory is
`/sys/bus/amba/drivers/pl061_gpio`; the observed device
`/sys/devices/platform/9030000.pl061` points back to that driver and reports
`arm,pl061` and `arm,primecell`. This fixes and actually exercises the previous
fixture's wrong `/pl061` path. It says nothing about a tablet GPIO controller.

## Remaining failure: journalctl's local datagram socket

After the restricted BPF observation and during successful-path
`/usr/bin/journalctl --sync`, raw production line 15,691 contains:

```text
[  138.067420] audit: type=1400 audit(1792195325.484:73): avc:  denied  { create } for  pid=345 comm="journalctl" scontext=system_u:system_r:journalctl_t:s0 tcontext=system_u:system_r:journalctl_t:s0 tclass=unix_dgram_socket permissive=0
```

The associated ARM64 syscall record has `syscall=198`, result `-13`, and
arguments `a0=1`, `a1=80002`, `a2=0`, with executable `/usr/bin/journalctl` and
proctitle `journalctl --sync`. This identifies the denied local datagram-socket
creation operation. It does not, by itself, identify which internal caller
requested it or prove that the journal synchronization stream failed.
The command actually returned **exit 0 with empty stdout/stderr**. The guest's
exit-code check passed; the full-log check correctly rejected the permission
failure. No denial is discarded because it was nonfatal or lacked a pathname.

The exact source caller and effective same-boot permission are a separate
follow-up. This report does not add a policy rule, change a domain, suppress
audit, relabel a socket or claim a repair. Any future candidate must retain
the complete behavior, evidence transport and zero-denial/loss gates.

## Udev handoff and retained artifacts

The original controller observed the root-side accepted
`event-serialization` FD and no reported FD loss. Its conditional restoration
gate is true. However, the actual raw log contains **no positive serialized
or restored event counts**. This is not evidence that the original queue was
empty or that every original queued event was recovered. The separate stricter
post-qualification program was **not executed** after the production failure.
It is not silently run or backfilled here.

The source, all phase records, both original controller records, raw CR/LF logs
and complete result file are immutable. The pipeline stopped before its normal
finalizer. No postboot e2fsck result or successful-system manifest is invented.
The retained image is
`/work/fedora-input-system-v8/fedora45-research4e-persistent-result.ext4`.

| Retained artifact | Bytes | SHA-256 |
|---|---:|---|
| R4 kernel Image | Frozen R4 artifact | `8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb` |
| Maintenance initramfs | 30,710,087 | `63d49544b2134249b5a1d3dad3e26906c1c7ca807625fd2f7230d499d97cf8c0` |
| Production initramfs | 32,532,049 | `e84bc6e03e4e4084c9f1beb38e3b4bffce56c4fa5a91503c73b2f33211c38652` |
| Closed image after normal production shutdown | 4,294,967,296 | `fd355b5f825fcc37b5877b49aa42d67889cf1599f6c00563487a6f8cdc26ab00` |
| Production raw log | 1,395,418 | `a88df1ce7489884a0c228a4a2a0320c4dc2c2f425b2a769b88c1f170823f3534` |
| Original production controller | 676,766 | `ac6db6cac9ad5d375e1b054ac3c70c8bef877b994b28662488f368888412f478` |
| Complete ordinary guest result | 413,706 | `3e48c9a429cad37d8baabf3fed31fe9abefdbaedfb065a484faf445bb6c2fa11` |
| Maintenance raw log | 1,095,153 | `ede72b8afc61c2310cff7c7e499040df06df5a57381b6a47041309422c3f584f` |

The independent freezer completed with exit 0 in 13.602 seconds; its
[actual execution record](evidence/fedora-r4e-freeze-execution.json) is retained.
The eight public JSON/log members were copied through a compressed packet,
with every member checked against its original size and SHA. The same tar
payload was rewrapped from gzip into xz to reduce relay requests; no member
was reserialized or rewritten. The [transport record](evidence/fedora-r4e-failed-evidence-transfer.json)
retains both container identities and the unchanged tar-payload hash.

The post-run freezer only retains existing bytes and computes identities; it
does not mount, repair, replay or write the closed image. Old R1, R3/R4, v5,
v6 and v7 sources, images and failure records remain available. Physical
tablet entry, native DPU/dual-DSI, Novatek touch/pen, keyboard wake, GPU rendering
and isolation, radio, audio, cameras, power and all remaining owner acceptance
cases still require their own device tests.
