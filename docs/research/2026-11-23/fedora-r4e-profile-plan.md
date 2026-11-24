# R4E / v8: frozen execution plan

This records the source and launch state at **2026-11-23 07:45 UTC**. The unique
pipeline had started; no archive or VM success is claimed by this plan. Its
subsequent outcome is recorded in the
[failed execution report](fedora-r4e-persistent-result-failed.md): the guest
behavior and result transport completed, but one production AVC failed the
overall run. This historical plan does not replace that result. Owner
tablet Linux boots and hardware passes remain zero.

## Why this candidate exists

The prior [R4D failure](fedora-r4d-reload-fd-failed.md) preserved real early
process-domain, bus/FD and TasksMax observations, but failed overall. Its
PL061 verifier used the wrong driver directory, the raw log contained two
visible Enforcing denials and a suppressed-callback notice, and mixed console
output broke the long final JSON. BPF attachment was observed; BPF restriction
behavior was not reached. None of those failed records are rewritten here.

R4E keeps the actual R4 kernel, 84 modules, 69 firmware files and Fedora package
baseline. It changes only the independently copied candidate, the explicit
startup policy/bootstrap inputs and the verification fixture. The source
contract is in the [profile README](../../../scripts/research/input/system-integration/profiles/persistent-result-v8/README.md).

## Concrete inputs and completed preparation

The native copy and R4 runtime transfer returned exit 0 in 269.954 seconds.
The canonical source and copied streams each contained 1,323,141,120 bytes
with SHA-256 `1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96`;
ownership, modes, ACLs and xattrs were retained. All 96 ordinary runtime input
files were checked. This preparation performed no PRoot, initramfs or VM
execution. See the [complete preparation record](evidence/fedora-r4e-baseline-preparation.json).

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| V3 native `/init` | 72,528 | `84cc4868317fd1799ab1ff8f8ba5ae8bf85445dda5d65c3f11e1637aadb599c3` |
| V2 cleanup waiter | 71,872 | `7e593ef9b2c40834b97ad35b1bc21fcd54b00e34dce72381832f88329e28b3ec` |
| New policy.35 | 3,835,456 | `727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502` |
| Production archive verifier | 30,122 | `0ced7a067f49371049502548c3685374f8c4b8b398b6c498afcfb4cebf9eda6d` |
| Complete-result writer | 5,302 | `89089a01d19113ac42d93f30cf86809e47dadfc7da28027733bf8a19c340c8a0` |
| Closed-image result reader | 8,311 | `71df5f32894a0f8b232173378786c39f39aca567af801dc3c5e035b04577dc25` |

The [new policy](selinux-standard-service-policy.md) has a complete, independently
checked CIL difference limited to six permissions: the prior map and
same-domain setcon permissions, registry-link cleanup, journal socket write
and journal stream connect. Its labels, booleans and unrelated rules remain
unchanged. A separate [86-row userspace AV qualification](selinux-standard-service-av-query.md) also checked the
necessary permissions and retained denials. These are static qualifications;
the new VM must exercise actual service behavior and read its actual loaded
policy bytes.

## What the new execution must prove

Complete evidence is written to a new private ordinary file with exclusive
creation, no symlink following, mode 0600, file/directory fsync and exact
readback. The console contains one short boot/profile/size/SHA receipt. Only
after its own QEMU exits does the host read the fixed path using read-only
debugfs and check the file's metadata and identities. Six actual offline
synthetic-ext4 cases qualified the reader's positive and rejection paths;
see [their unchanged result](evidence/fedora-r4e-result-transport-qualification.json).
That qualification does not prove crash-time journal visibility: unavailable
evidence after forced termination remains a failure.

The V3 loader's explicit generic-VM-only opt-in sets only the printk rate
interval to zero before policy load, checks the real `linux,dummy-virt`
compatibility and reopens interval/burst for readback. The host requires the
single marker in the correct startup order, and the guest rechecks both values
around behavior. Audit and SELinux remain enabled. Any source-qualified audit
loss or any positive caller suppression message still fails. The latter is
deliberately conservative because the printk limiter's missed count is shared.

The production initramfs is therefore a **generic-VM qualification artifact**.
Its V3 guard rejects a physical tablet. This file is not a claim that an owner
tablet boot initramfs or first-stage route has been completed.

The correct PL061 driver path must be read in the running VM, with actual
device and driver symlinks and compatibility. `journalctl --sync` is required
on the successful path. All earlier gates remain: true system-bus/three-FD
forwarding, held-worker identity, 82 unique live AV tuples, actual TasksMax
EAGAIN, actual BPF direct-open EPERM with zero data, Enforcing, early process
and file labels, module enforcement, zero taint, BTF/runtime hashes, ACLs,
services, complete raw-log checks and independent udev handoff qualification.
Partial results from R4D cannot substitute for these new runs.

## Actual source materialization and launch

The 28-file source packet was copied into a new private overlay. All 20
materialized recipe files and the four joint inputs above were read back
before launch. The separate supervisor source is also pinned in the
[execution-source record](evidence/fedora-r4e-execution-source.json).

* Profile manifest: `f705c87a1c5efe082ae134febc139e8ce437818951c83a9709bd475d17fc60d2`.
* Actual recipe manifest: `c453d67a35b466be76924eceb7f3af96bfd15ed313ee5cba11963a9de91fcb94`.
* Packet: 90,499 bytes, `b844cda5e2cbb488248205eb974ee2c6dbc614a2d42656c760db5b1326f46698`.
* Overlay: `/work/fedora-r4e-source-overlay-v1`.
* Recipe: `/work/fedora-input-system-recipe-r4-v6`.
* Work: `/work/fedora-input-system-v8` in `tb371fc-build-20261123`.
* Unique CT unit: `tb371fc-r4e-full-01`, launch exit 0, active/running at capture.
* Invocation: `1627fbd7f92047d490302551aa1d3f98`.

Each sequential phase retains its own source identity, log and exit under
`jobs/`; the outer record is `pipeline.exit.json`. A failed phase stops the
sequence without rewriting its status. The temporary local-editor outage did
not execute a fallback VM: the recovered local draft supplied the actual
packet, while the extra private fallback base remains unused. Public source
and all prior candidates remain available for audit and reproduction.
