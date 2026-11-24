# R4E: persistent results and standard-service verification

This is the v8 execution contract. Its native userspace copy and unchanged R4
runtime transfer have completed; archive and VM outcomes are recorded
separately. This document does not declare a successful VM. Earlier executed
recipes, failed images and raw logs remain immutable.

## Independent inputs

Work is /work/fedora-input-system-v8, recipe is
/work/fedora-input-system-recipe-r4-v6, and image label is
tb371fc-r4e-f45. The unchanged release is
6.12.114-tb371fc-research4-system, with 84 qualified modules and
69 staged firmware files. QEMU uses its generic virt DT, never the Lenovo
board DT, physical devices, networking or a host filesystem share.

Native baseline preparation returned exit 0 in 269.954 seconds. Source and
destination canonical streams each contained 1,323,141,120 bytes, SHA-256
1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96.
Modes, numeric ownership, links, ACLs and xattrs were preserved. Independent
qualification SHA is
d1136513b108ebc0a18abe859d28d2a913fbf75446b4ebacb02fd926f281a840.
All 96 ordinary R4 input files were rechecked. This preparation performed no
PRoot, initramfs, VM or policy-load operation. Full metadata:
docs/research/2026-11-23/evidence/fedora-r4e-baseline-preparation.json.

Only this candidate's policy.35 is replaced after archiving its copied
original. The original R1 tree and earlier candidates are read-only inputs.
The new 3,835,456-byte policy from
/work/selinux-standard-services-20261123/build-01/candidate/ has SHA-256
727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502.
Complete version-35 and fresh version-33 CIL comparisons limit the changes to:

| Source | Target | Class | Added permissions |
| --- | --- | --- | --- |
| init_t | semanage_store_t | file | map |
| init_t | init_t | process | setcurrent, dyntransition |
| init_t | systemd_varlink_registry_t | lnk_file | unlink |
| journalctl_t | syslogd_var_run_t | sock_file | write |
| journalctl_t | syslogd_t | unix_stream_socket | connectto |

The journal socket's getattr denial remains; the matched short sync path does
not require it. Labels, booleans and unrelated rules are unchanged. The new
candidate also passed a separate 86-query userspace AV qualification, including
the necessary permissions and retained negative controls. Neither test proves
runtime behavior. See selinux-standard-service-policy.md and its evidence.

V3 /init is the actually built 72,528-byte ELF
84cc4868317fd1799ab1ff8f8ba5ae8bf85445dda5d65c3f11e1637aadb599c3.
Its build input is this same new policy. Its size condition is supplemented
by full archive and guest policy hashes. Stage0 remains
15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d.
The new 71,872-byte V2 waiter
7e593ef9b2c40834b97ad35b1bc21fcd54b00e34dce72381832f88329e28b3ec
requires the actual V3 size and emits STAGE1_V2. Its size/shape checks do not
replace complete artifact hashes. Old loaders and the V1 waiter are unchanged.

The archive checker retains the original baseline, fixed parsers, unchanged
config/context payloads, firmware, libraries and prior userspace ELF bytes.
Only explicit native loader/waiter and fixed switch_root/stat ELF roots are
allowed, with their recursive fixed dependencies. Python result helpers add
no initramfs ELF. The separate maintenance archive retains the original
unchanged verifier.

## Complete result file, short receipt

V7's actual kernel messages interleaved with long console JSON. Its parse
failure remains failed; no raw frame was repaired or rescored. V8 stores
complete progress and final evidence in the fixed ordinary file
/var/lib/tb371fc-r4e-proof/system-result.json.

After exact VM/root/profile/Enforcing guards, the observed sysadm_t writer uses
a root-owned 0700 directory, O_EXCL/O_NOFOLLOW creation, mode 0600 and one link.
It writes bounded canonical JSON, fsyncs, reads back exact bytes and fsyncs the
parent. Writer and reader hashes must match the profile. The console carries
one receipt under 300 bytes: status, boot UUID, profile SHA, file SHA, size,
and an exact end marker.

Only after its QEMU child exits and is reaped does the host open the image
read-only and use fixed debugfs requests. It never supplies -w, mounts,
replays or repairs. Parent directories and the final regular inode are
checked for ownership, mode, links, size and SHA. Receipt/file boot and
profile must match the same-boot initrd/policy evidence. Missing data,
duplicates, symlinks, interleaving or mismatched identities fail. Transport
qualification alone cannot pass the system and full-log gates.

A real 8 MiB offline synthetic ext4 qualification passed six cases: exact
ordinary-file positive, duplicate/interleaved receipt rejection, wrong SHA,
wrong boot and final symlink rejection. The positive preserved image SHA.
It performed no VM, mount, PRoot, policy operation or old-image write.

Fsync makes updates durable in the journal, but read-only debugfs does not
replay it. A failed VM terminated before checkpoint may leave the latest
evidence unavailable. That remains a failed transport contract; the clean
synthetic test does not prove crash-time recovery. Full raw console is retained.

## Audit observation and early startup

V7 contained "kauditd_printk_skb: 6 callbacks suppressed"; its two visible AVCs
are not an exhaustive audit inventory. Fixed R4 source shows the fallback
uses the shared printk limiter. Interval zero bypasses its quota and trylock
drop paths, separately from audit queue/backlog loss.

V3 requires unique rd.tb371fc.audit-printk-unlimited=1 and actual
linux,dummy-virt. After API mounts and before policy load, it reads interval
and burst, writes only interval 0, reopens both and requires zero interval
with unchanged burst. Its unique marker must follow cleanup and precede
policy load. No old interval/burst value is assumed. Guest readbacks before
and after behavior must match this marker. The verifier writes no sysctl;
audit, SELinux, burst and audit queue settings remain enabled/unchanged.

This production initramfs is therefore an explicitly guarded **generic-VM
qualification artifact**, not a qualified tablet boot initramfs. Its V3 path
rejects non-dummy-virt hardware. A physical owner boot profile remains separate.

The host still requires zero visible AVCs and rejects source-qualified
printk suppression, positive audit_lost, backlog/queue overflow, rate-limit
loss and audit allocation loss. Interval zero alone does not prove complete
delivery. Any such observation fails with its complete raw log retained.
Because the printk limiter is shared, a positive callbacks-suppressed message
from any caller also fails conservatively; this can reject non-audit limiter
activity instead of assuming that its shared missed count excluded audit.

Production requires enforcing=1, selinux=1, module.sig_enforce=1 and unique
rdinit/early-policy/tmpfs opt-ins. Stage0 copy, V2 cleanup, V3 observation,
policy load, systemd exec and same-boot domain proof must appear in order.
Actual PID 1 mountinfo must agree with marker device numbers and show ordinary
tmpfs without nosuid/noexec.

Schema-3 proof reads actual PID 1 init_t, udevd udev_t, journald syslogd_t and
correct /dev/null, /dev/kmsg, /run, /run/log, /run/log/journal and journal-file
labels after real journald notify-reload startup. Standard systemd reload and
calculated-init-label successes are required. Reload/transition errors
anywhere remain fatal.

PL061 now uses /sys/bus/amba/drivers/pl061_gpio and requires a real device
symlink, bounded arm,pl061 compatibility and correct driver backlink. The old
/pl061 fixture failure is preserved; source registration/logging is insufficient.

The successful path explicitly runs journalctl --sync and requires exit 0
with untruncated output, so new journal permissions receive a positive test.
Registry cleanup remains subject to zero AVC. Signed-module enforcement,
BTF/runtime hashes, taint zero, ACLs and service gates are retained. The
separate udev full-log qualifier rejects known storage/push/wait/receive/
insert and FD-loss errors. Missing positive counts never prove an empty queue.

## Actual FD and restriction behavior

The validator and owned workers use strict existing sysadm_t. Old
unconfined_service_t FIFO restrictions remain checked; workers are not put in
init_t. Actual systemd-run --wait --pipe --collect traverses system bus,
broker and PID 1. Three pipes are created in the observed domain. Bounded
nonce/PID READY holds the worker up to three seconds. Before GO the parent
reads real domain, executable, argv, PID starttime, cgroup, FD identities/
labels/directions and actual manager properties. Worker runtime is eight
seconds, parent deadline twelve; only owned units/processes are cleaned.

Actual version-33 policy is exported to a new 0600 ordinary file and rechecked
after tests; its hash is measured, not predetermined by a fresh conversion.
The unchanged 82-query helper uses fixed public libsepol ABI. Host checks
the exact unique tuple set across broker/PID1/worker, entry, policy read/map/
load, same-domain setcon, export and retained restrictions, bound to real FDs.

* Noop proves actual bus and complete FD forwarding.
* Pids requires real TasksMax=3, exactly three attempts, two child creations,
  one EAGAIN, increased pids.events:max and all own children reaped.
* Proc-read uses identical bytes/argv/nonce/domain/unit before and after the
  sole RestrictFileSystems=~proc change. Baseline must match release and
  recorded size/SHA. Restricted direct open must return **EPERM during open
  with zero data**. EACCES, read-phase failure or no READY cannot pass.

BPF also requires the matched post-attach log, independently of packages or
configuration. See systemd-bpf-runtime-contract.md.

## Execution boundary

Materialization requires the exact new source manifest, frozen prior v7
manifest and fixed supplemental sources, and refuses an existing output.
All 20 materialized recipe files are read back before launch. The separately pinned launch_pipeline.py owns their supervisor and preserves the outer exit record. Phases are stage,
configure, maintenance/production archive qualification, image, maintenance
label, production verify, udev post-qualification and final retention.
Each preserves source identities, logs and exits; failure stops the sequence.

Final retention after clean shutdown checks the full result, actual policy,
filesystem, packages and runtime inventory. Construction and generic-VM
results remain host-build evidence. Owner tablet Linux hardware, display,
input, pen charging, GPU and Android parity gates remain unpassed.
