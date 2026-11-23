# R4D: independent early-policy and three-receiver FD contract

This is the v7 execution source contract. Its native baseline copy and
unchanged R4 runtime transfer have completed. Archive and VM results are
recorded separately; this document does not declare a successful VM. The
materializer checks the complete fixed input/source manifest before execution. Previous v3, v5 and v6 failures remain immutable.

## Fixed candidate and source boundaries

The new work directory is `/work/fedora-input-system-v7`, the recipe directory
is `/work/fedora-input-system-recipe-r4-v5`, and the private ext4 label is
`tb371fc-r4d-f45`. Its unchanged kernel is
`6.12.114-tb371fc-research4-system`. The recipe stages the actual R4 inventory
(84 modules) and the existing qualified 69-file firmware inventory. QEMU uses
its generated generic `virt` DT; it never receives the packaged Lenovo joint
display/input DT, physical hardware, a host filesystem share, or networking.

The native baseline preparation executed in the original standard HDD builder.
Its source and destination canonical streams both contained 1,323,141,120 bytes
with SHA-256 `1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96`.
The copy preserved modes, numeric ownership, links, ACLs and extended attributes.
The independently retained qualification has SHA-256
`b87d15dd82a7e411390046f7fed808c253558849c55b1c42bf91d377d176f25b`.
The same native job rechecked all 96 ordinary files in the existing R4 transfer
bundle. It executed no PRoot, initramfs, policy load or VM.

Only the new candidate's `etc/selinux/targeted/policy/policy.35` is replaced.
Its copied original payload is first archived under
`usr/share/tb371fc/research1-policy-archive/`; the original R1 tree and all
previous candidates are read-only inputs. The proposed replacement is the
separate combined candidate from
`/work/selinux-reload-map-self-20261123/build-01/candidate/`, SHA-256
`e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269`.
Its independently qualified complete CIL difference is limited to `init_t` mapping the correctly
labelled `semanage_store_t` policy file and `init_t` performing `setcurrent` and
`dyntransition` to its own domain. Complete version-35 and fresh version-33 CIL comparisons found only those
three permission additions; source permissions do not prove a successful boot.

The native V2 `/init` is the already compiled 72,048-byte artifact
`cc042c9fc4e92c75803215649c99bd87badd301bb05aa16820b43aaeb8fb50bc`.
Its original build recorded the earlier map-only policy `0dd46af3...`; that
record is preserved. The loader embeds a policy size condition, not a policy
hash. Both policies have 3,835,432 bytes, so this profile independently binds
the unchanged loader to the combined policy by complete archive and guest
hash checks. It does not relabel the old build as a combined-policy build.
The frozen stage0 and cleanup waiter remain `15905f39...` and `cc30c123...`.
The waiter's old source comment describing `e53...` belongs to v6; its size
condition is not this profile's identity check. The new archive checker pins
the complete V2 `/init` hash.

The production archive retains the fixed original source baseline and parsers,
the complete unchanged config/context tree, all firmware and qualified shared
libraries. The sole additional observation executable is the existing Fedora
`usr/bin/stat`, 135,480 bytes, mode 0755, root-owned, SHA-256
`f54c956a5e840a22480869e0f5093f51e3a39b42374dd1045d527e8560ad5d5e`.
Its actual ELF dependencies (`libselinux`, `libc`, and the ARM64 loader) are
resolved recursively against the fixed library catalog. No arbitrary new ELF
or caller-supplied hash is accepted. The maintenance archive is separate and
still passes the original unmodified verifier.

## Actual startup observations required

Production retains `enforcing=1`, `selinux=1`, `module.sig_enforce=1`, and the
unique `rdinit=/init.tmpfs`, early-SELinux and tmpfs opt-ins. It requires the
real copy, cleanup, native policy load, systemd exec, and same-boot domain proof
in that order. Device numbers must agree across the stage markers and actual
PID 1 mountinfo. The root must be ordinary tmpfs without `nosuid` or `noexec`.

The schema-3 initrd proof requires actual PID 1 `init_t`, udevd `udev_t`, and
journald `syslogd_t`. It reads the live labels of `/dev/null`, `/dev/kmsg`,
`/run`, `/run/log`, `/run/log/journal`, and the actual runtime journal files.
The proof service starts after the real journald notify-reload service. A
service-ready state cannot substitute for these file observations.

The host additionally requires the version-matched standard systemd loader's
successful reload and calculated-init-label transition messages between the
native exec and the initrd proof. It rejects transition/reload errors anywhere
in the raw log. Zero visible AVCs, no lost event-serialization FD, actual
signed-module enforcement, taint zero and the other previous system gates
remain required. The separate full-log udev qualifier rejects all known
storage/push/wait/receive/insert failure messages. Missing positive event
counts never prove that the original queue was empty.

## Three-receiver transport and behavioral tests

The root verification service and each owned transient worker explicitly use
the existing administration domain `system_u:system_r:sysadm_t:s0`. The test
does not run arbitrary workers in `init_t`, modify global policy booleans, or
relax the previous `unconfined_service_t` FIFO restriction.

The parent creates all three standard pipes in its observed unchanged domain.
The actual `systemd-run --wait --pipe --collect` path goes through the system
bus, broker and PID 1. Each worker emits a bounded nonce/PID READY record and
waits up to three seconds. Before GO, the parent reads the held process's
actual domain, executable, argv, PID starttime, cgroup, and three descriptor
inode identities, labels and directions. One bounded manager property query
reads the actual MainPID, ControlGroup, SELinuxContext, TasksMax,
RestrictFileSystems and RuntimeMaxUSec. This binds the requested policy domain
to the observed worker before any tested operation. Unit runtime is eight
seconds; the parent operation deadline is twelve seconds. All owned children,
FDs and transient units have bounded cleanup.

The actual running version-33 policy is read once, written only to a new
ordinary 0600 file in this candidate's private evidence directory, and checked
again after the tests. Its hash is measured, never assumed to equal a userspace
conversion or an old VM export. `probe_fd_route_v2.py` performs 82 read-only
public-libsepol AV calculations on these exact bytes: three descriptors across
broker, PID 1 and worker; service entry; source-policy read/map/load;
same-domain setcon; policy export; and retained restrictions. Its requested
worker premise is insufficient until the held worker readback agrees. The host
also validates the exact unique AV tuple set and binds every descriptor input
to the actual observations. The original 80-query probe remains preserved.

Three fixed worker modes are permitted:

* `noop` proves the real bus and complete FD route before restrictions are tested.
* `pids` uses actual `TasksMax=3`, tries exactly three short-lived child processes,
  requires two creations and one `EAGAIN`, requires an increase in
  `pids.events:max`, and reaps its own children.
* `proc-read` runs the same worker bytes, argv, nonce, domain and unit once with
  no filesystem restriction and once with only `RestrictFileSystems=~proc`.
  The baseline output must match the running kernel release and its reported
  byte count/hash. The restricted direct `open('/proc/version')` must fail
  with **EPERM at the open phase**, without data. EACCES, a read-phase failure,
  failure before READY, or only an unsuccessful exit cannot pass this test.

The BPF criterion comes from the matched systemd `lsm/file_open` source and its
post-success attachment log, not configuration or package presence. See
`docs/research/2026-11-23/systemd-bpf-runtime-contract.md`. Both BPF runs must
retain the same observed worker properties apart from the intended restriction.

After a successful, cleanly stopped VM, the finalizer uses read-only debugfs
commands to retain the guest's actual policy and export metadata from the
closed private ext4 image. These must match the raw same-boot result exactly.
This adds no VM, policy load, mount, host share, or owner-tablet operation.

## Reproduction after source freeze

The materializer requires the exact new profile manifest and fixed supplemental
sources, and refuses an existing recipe directory. Every phase preserves its own log and exit status, and source bytes are
verified again in the materialized recipe before execution.
The intended sequence is stage, configure, separate archive qualification,
image creation, maintenance labelling, production verification, full-log udev
qualification, and final retention. A failed phase stops the sequence and stays
failed. Successful construction or generic-VM results cannot satisfy the owner
tablet's Linux hardware acceptance cases.
