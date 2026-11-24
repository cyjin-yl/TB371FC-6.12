# R4D / v7 integration contract — pre-execution plan

**Historical status at source freeze, before the 2026-11-23 06:28:51 UTC
pipeline: source preparation, no v7 VM had run.** The subsequent actual
[v7 execution failed](fedora-r4d-reload-fd-failed.md); that separate report
preserves its partial runtime results and all remaining failures. The
executed source contract below is retained. This plan follows the
retained [v6 failure](fedora-r4c-tmpfs-failed.md). It does not modify the v5/v6
images, executed recipes, original policy, e53 native helper, or the 58a5 and
92f02 archive checkers. The separate candidate prefix is
`/work/fedora-input-system-v7`; the proposed execution recipe is
`/work/fedora-input-system-recipe-r4-v5` and its public full overrides are in
`scripts/research/input/system-integration/profiles/reload-and-fd-contract-v7`.
The R4 Image/module/firmware identities remain unchanged.

## Repair boundaries

The observed v6 errors expose two independent contracts. Early systemd must
successfully reload policy and perform its normal API-filesystem label
initialization. Separately, an FD-bearing management request must be allowed
at all three receiving processes: broker, PID 1 and the actual transient
worker. A successful ordinary D-Bus reply or broker-only AV query cannot
stand in for either contract.

The combined candidate was qualified from the original policy.35 and three
explicit permission additions: `init_t` mapping the correctly labelled
`semanage_store_t` policy file, and `init_t` self `setcurrent`/`dyntransition`.
Complete version-35 and independently converted version-33 CIL comparisons
contain only those additions; the map-only candidate remains preserved as an
incomplete preflight. Its missing same-domain setcon permissions were found
before any v7 VM. Only this one policy payload may differ in the copied
`etc/selinux` tree; contexts and every other payload remain compared with
their original fixed sources. The V2 native loader has a separate source,
marker and binary identity. It is not substituted into an old report.

The root-managed V2 artifact is 72,048 bytes, SHA-256
`cc042c9fc4e92c75803215649c99bd87badd301bb05aa16820b43aaeb8fb50bc`.
The candidate policy is 3,835,432 bytes, SHA-256
`e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269`.
The unchanged V2 loader was originally built against the same-size map-only
`0dd46af3...` input; that original record is preserved. It embeds no policy
hash, so the new joint profile independently requires the complete combined
policy hash in both archive and guest checks.
These are construction identities, not startup qualification. The old
stage1 waiter's size-only `/init` condition is compatible with the new binary
size; its source comment naming e53 describes v6. The new archive checker
must pin the V2 content hash independently. A size match cannot establish
bootstrap identity.

## Actual service and FD route

The explicit management test domain is the existing
`system_u:system_r:sysadm_t:s0`, both for the validator and for each controlled
transient. It is not `init_t`, and no arbitrary production daemon is placed
in this test domain. The fixed-policy offline candidate queries cover its
entry and all three receivers; every new VM must verify its own actual contexts
and exported policy again.

The new `guest_transient_worker.py` has three fixed modes: `noop`, `pids`, and
`proc-read`. `transient_protocol.py` implements the parent side. The sequence
is deliberately observable:

1. The parent reads its actual context, creates three ordinary pipes, and
   observes both type and SELinux inode context of each forwarded endpoint.
   The stdin endpoint is read-only; stdout/stderr endpoints are write-only.
   The creator context is recorded separately from inode labels. There is no
   inherited stdin descriptor with an unknown opening context.
2. The actual pipe labels, creator, PID 1 and broker contexts are supplied to
   the same-boot exported-policy query. The requested worker domain is an
   explicit premise at this point, not an observed process.
3. The unchanged real `systemd-run --wait --pipe` system-bus path starts a
   fresh owned unit with `RuntimeMaxSec=8s` and strict `SELinuxContext`.
4. The actual worker checks its three descriptors and emits one bounded
   READY frame containing nonce, PID, profile identity and descriptor
   observations. It waits at most three seconds for GO.
5. While that same worker is waiting, the parent reads its real `/proc`
   context, executable/argv, cgroup, process start identity, FD targets,
   inode identities, labels and access directions. A single manager query
   reads actual `MainPID`, `ControlGroup`, `SELinuxContext`, `TasksMax`,
   `RuntimeMaxUSec` and `RestrictFileSystems`. Every premise must match before
   GO. The controller still has a twelve-second operation deadline.
6. The same worker PID executes the requested behavior without another exec
   that could change the observed domain. Results must match the same
   nonce/PID/profile and actual client exit status. The parent reaps its
   client, closes its descriptors and collects only its explicitly owned
   unit, including on failure.

The policy engine runs before launch to avoid consuming the three-second
READY budget. Its requested-worker premise is accepted only after the exact
actual worker context matches. Full AV results remain evidence; the short
in-window progress record contains their identity and summary, avoiding a
large console write in the deadline.

The matched Fedora systemd 262.1 formatter emits
`RestrictFileSystems=~` for the unconstrained default when explicitly queried
with `-p`, and `RestrictFileSystems=~proc` for this restriction. Treating the
default as an empty string would be a fixture error. This is established by
the matched `src/core/dbus-execute.c` and `src/systemctl/systemctl-show.c`,
not by a guessed VM output.

## Required same-boot policy evidence

The new 82-query probe is a separate pure user-space helper; the earlier
80-query source remains unchanged. The host independently checks the exact
unique permission tuple set and actual descriptor premises. It accepts only bytes
read from that boot's `/sys/fs/selinux/policy`; it does not convert versions,
load kernel policy, modify booleans or call an enforcement toggle. Its
libsepol ABI and binary stay fixed. Every API return code and permission
decision is recorded, including denial-audit masks rather than confusing
`dontaudit` with permission.

| Required query group | Subjects and objects |
|---|---|
| Forwarded FD use | Actual broker, actual PID 1 and qualified/then observed worker → explicit pipe-opening context |
| FIFO access | All three receivers → each actual FIFO inode context; read/write/append/getattr/ioctl are queried separately |
| Service entry | `init_t` setexec/transition plus selected service domain and actual entry executable label |
| Policy reload | `init_t` source-policy open/read/getattr/map and load permission; self setcurrent/dyntransition |
| Policy export | The management domain's actual read-policy permission; preserve `init_t` read-policy denial |
| Retained restriction | The original broker-to-`unconfined_service_t` FIFO restriction remains denied |

The actual exported policy is also saved as a fresh bounded ordinary file
inside this candidate, with exclusive creation, no-follow handling, mode
0600, fsync and a same-boot identity record. The declared source policy.35 and
actual kernel-exported policy.33 are different artifacts. Their size/hash
must both be retained; a future policy hash is not predicted from the old
9c79 result. V6 only queried those bytes in memory and did not retain an
ordinary exported file, so no such old file is invented.

## Security behavior remains required

Changing the management service domain does not count as a security test.
The behavior is still checked separately in the actual controlled worker.

**TasksMax:** the same worker is observed in the actual owned pids cgroup.
The unit and cgroup must both show limit 3. It attempts exactly three
two-second `sleep` children: exactly two creations, exactly one `EAGAIN`, an
increase of `pids.events:max`, and all created children reaped are required.
The READY/GO mechanism adds no process inside that cgroup. An SELinux denial,
an unrelated spawn error or a missing child cannot satisfy this result.

**BPF filesystem restriction:** both runs use the same worker file/hash,
mode, argv, pair nonce, SELinux domain, unit name and normal unit settings.
The only requested restriction difference is `RestrictFileSystems=~proc`.
The worker uses direct `open`/`read` on `/proc/version` after GO; it never
reads `/proc` for self-identification. The unrestricted stdout must match the
actual kernel release and the recorded byte count/hash. The restricted
result must report failure specifically at `open`, errno `EPERM` (1), no
bytes read and no stdout payload. Exit status 1 alone is insufficient.
The matched BPF source uses an LSM `file_open` hook and returns `-EPERM` for this deny-list match; a read-phase failure or EACCES remains a different failure. Actual BPF attachment, the expected LSM stack, unchanged policy/domain and
zero AVCs remain required. The test cannot pass because the new management
domain merely changes an SELinux denial. Python startup is not assumed
free of `/proc` access: a missing READY or an actual denial remains failure.

## Early-process and archive gates retained

The new full profile still requires the exact root-migration/cleanup order,
same-boot initrd PID 1 and udevd domains, actual tmpfs source/device/options,
and matching controller/guest evidence. It additionally needs a successful
normal systemd policy-reload observation and correct `/dev`/`run`/journal
labels before switch-root. Expected labels must come from the fixed context
lookup and actual source contract, not invented type names. The old archive does **not** contain coreutils `stat`. The new checker
explicitly adds only the fixed original Fedora `usr/bin/stat` (135,480 bytes,
0755/root, SHA-256 `f54c956a5e840a22480869e0f5093f51e3a39b42374dd1045d527e8560ad5d5e`)
and verifies its complete dependency closure against the existing catalog.
Schema-3 proof records live device/run/journal labels and journald domain.
The host requires both successful standard systemd policy reload and
calculated-init-label transition before the actual initrd process proof,
and rejects reload/transition errors in the complete raw log.

The original archive baseline, all 69 firmware payloads, ARM64 dependency
closure/cache validation, module identities/signatures, runtime enforcement,
autofs, BTF, zero taint, PL061, no failed units, zero AVCs and full-log udev
handoff qualification remain separate required gates. Maintenance labeling
and production Enforcing archives remain separate. No new VM is started
until the policy and loader inputs, probe interface and complete profile
have been qualified and frozen.

All of this remains host construction/VM work. It cannot complete the
owner-tablet display/input/radio/power or Android-parity acceptance cases.

The native v7 baseline copy and R4 runtime transfer completed with exit 0
before the system VM. The full source contract is documented in the frozen
profile README. The later [actual execution report](fedora-r4d-reload-fd-failed.md)
is authoritative for runtime outcomes; they must not be inferred from this
pre-execution plan. No executed source or manifest was changed to update
this navigation.
