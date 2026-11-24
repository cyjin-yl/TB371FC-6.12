# R5 Fedora runtime and merged-source checkpoint

Date: **2026-11-24, Asia/Shanghai**. Execution timestamps below are UTC.
Machine-readable continuation: [r5-runtime-checkpoint.json](r5-runtime-checkpoint.json).

## Current state

**Run04 passed its complete construction and both generic-VM phases at
2026-11-24 02:17:32 UTC (10:17:32 Asia/Shanghai).** The repaired R5 system
switched to the real ext4 root and reached systemd multi-user with SELinux
Enforcing, actual module-signature enforcement and every existing production
acceptance gate passed. Its complete original host result is retained, including
the expanded guest result, source/artifact bindings and behavioral proofs.

The reviewed Linux source stack is integrated into this fork's `main`. The
previous run03's production worker-identity failure remains unchanged. Run04
uses a newly staged root and image from the exact repaired source; the old
attempt is not reused or rescored.

This is a generic ARM64 VM integration lane. It does not use the Lenovo board DT
for VM execution, pass physical devices through, or add owner-tablet Linux
hardware passes. Native entry, reachable recovery and whole-device acceptance
retain their existing unmet requirements.

## Source integration

| Item | Exact revision / result |
| --- | --- |
| Reviewed source integration | [PR #8](https://github.com/cyjin-yl/TB371FC-6.12/pull/8), `main` merge `9b5b34ee43123eca48a1f512747abf21b3af1883` |
| Integrated research tree | `811b5f427d775876130213ca25bc29ca34eb8d04` |
| Same tree on both refs | `3e0c70c219a0f60f7e26bb1a6442a85b4f32a5f0` |
| Actual run04 source | `6b24e66087e80c6847f0a759e1f6e9a2b9bd4f0d` |
| R5 source relationship | Runtime scripts, tests and workflows match the integrated tree byte for byte |

PRs #1–#7 are merged: mainline direction and evidence, Novatek bounds,
boot-bundle qualification, R5 runtime staging, VM image lineage, guest TMPDIR
and transient-worker identity. The branch integration preserves the frozen
source inputs, original failures and existing acceptance boundaries.

The [Novatek 0020 repair](../2026-11-23/novatek-firmware-bounds.md) is present in
source, but its newly built unsigned module is not inserted into the frozen R5
84-module candidate. A later replacement requires its own signing/trust, ABI,
dependency and complete manifest qualification.

## Preserved run03 failure

Source: `28adcae4d9c5ed602a17225c68f5042cf494bd1f`. Candidate:
`/work/fedora-r5-system-v3`. The original result records and selected serial
markers are retained in [run03-failure.json](evidence/r5-worker/run03-failure.json).

| Phase | Observed result |
| --- | --- |
| Construction | Eight phase receipts exit 0; actual initramfs pair and 4 GiB ext4 image produced |
| Maintenance label | Exit 0; lineage record passed |
| Production verify | Exit 1; lineage record failed |
| Immediate guest failure | The R4 kernel guard rejected R5; source inspection also found inherited R4 profile-name and root-label guards |
| Persistent failure-result extraction | Failed; original host result retained, with no relaxed reader or rescored result |

The [worker identity repair](r5-worker-identity.md) derives only the exact R5
release/profile/label and explicitly binds the profile release to the running
kernel. Frozen v9 files and the system, signature, SELinux, FD-route and nonce
gates remain unchanged. The [accurate-source CI](https://github.com/cyjin-yl/TB371FC-6.12/actions/runs/45309157177)
passed all 15 staging and 10 recipe tests, including the real ordinary-file
ext4/ACL fixture. The synthetic worker tests do not establish a runtime pass.

## Completed run04 attempt

| Item | Value |
| --- | --- |
| Host/container | CT102 / `tb371fc-build-20261123` |
| Job | `/work/r5-fedora-job-6b24e66-run04` |
| Source directory | `/work/r5-fedora-source-6b24e66-run04` |
| New candidate | `/work/fedora-r5-system-v4` |
| Kernel contract | `6.12.114-tb371fc-research5-services`, frozen 84-module input |
| Construction | Download, extraction, regression, stage, materialize, configure, initrd and image: each exit 0 |
| Initramfs / image finished | `2026-11-24T02:10:22Z` / `2026-11-24T02:11:20Z` |
| Maintenance phase | Exit 0, completed `2026-11-24T02:14:42Z` |
| Production phase / complete job | Exit 0, completed `2026-11-24T02:17:32Z` |

The executed [pipeline script](evidence/r5-run04/run.sh) held the existing
exclusive R5 lane lock while building, then released it before invoking the
guarded VM phases, whose wrapper acquires its own lock. Maintenance passed
before production started. Both phases are bound to the same actual image and
exact kernel, profile, archive and runner identities; the maintenance output
hash equals the production input hash.

### Actual production results

| Gate | Observed result |
| --- | --- |
| Kernel and root | `6.12.114-tb371fc-research5-services`; `/dev/vda`, ext4, label `tb371fc-r5-f45` |
| PID 1 and services | `/usr/lib/systemd/systemd`, `init_t`; multi-user, D-Bus and udev active; no failed units |
| SELinux | Enforcing; actual loaded version-33 policy exported and unchanged across probes |
| Modules and firmware | All 84 module files and 69 firmware files matched; signed autofs actually loaded; runtime `sig_enforce=Y`; taint 0 |
| PID-controller behavior | `TasksMax=3`: two owned children created, third denied with EAGAIN; counter increment and child cleanup verified |
| BPF filesystem restriction | Unrestricted same-worker `/proc/version` read succeeded; restricted open returned EPERM with no stdout payload |
| Transient route and policy | Four actual routes and four independent same-boot policy gates passed |
| Initrd and switch-root | Early tmpfs migration, policy reload, PID1/udev/journald domain proofs and root handoff passed |
| Other runtime checks | PL061 binding, booted journal ACL readback and success-path journal synchronization passed |
| Shutdown and retained result | QEMU exit 0; no termination reason; same-boot persistent result qualified with `status=pass` |
| Production warning counters | All 11 defined counters zero, including AVC, audit loss/suppression, descriptor loss and prior resource/GPIO notices |

The result reader opened the closed image read-only, without mounting, replaying
or repairing its filesystem, and matched the retained result to its same-boot
receipt. The full host JSON binds the separate original guest-envelope file by
size (413,725 bytes) and SHA-256; it is not described as a byte-for-byte copy of
that separate envelope.

Maintenance intentionally uses its separate permissive labeling profile. It
retains **44 AVC observations and eight audit-printk suppression events**. Those
counts are not production results. The build also retains dracut/ldconfig
warnings in its [original stderr](evidence/r5-run04/initrd.stderr). The production
archive records subsequent cache construction with the fixed Fedora AArch64
ldconfig outside PRoot and a matching fixed-source semantic map; the complete
archive/cache gates and phase exits passed.
Neither the build nor maintenance phase is described as warning-free.

The executed pipeline did not invoke the old R4-specific distribution release
finalizer. This checkpoint records the actual strict production VM result,
not an additional release-sealing step or physical deployment.

### Artifact identities and retained evidence

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Maintenance initramfs | 30,709,186 | `4b09577be4a3848361617de47e4a4e8c9c8a5593057ff19538eb5328944d71c8` |
| Production initramfs | 32,535,823 | `6f63a7048f6664d1ff4473c0ddf580412172b50f9495073a4e7af5cd23465321` |
| Original ext4 image | 4,294,967,296 | `42908e1e4c2932bd5a4873c13e4a890bb1cced14bb82245c6f1f207ff203e51f` |
| Image after maintenance | 4,294,967,296 | `cac37e6d1fdc8cd4517eed49c55b8e2232e2d5a29153ef9718c7029ff009742d` |
| Image after production | 4,294,967,296 | `f3d260f5e91ed6a2b67e84fd4f7b3d07b1ff2dda5c88be43d1dac242774043ad` |
| Full production host result | 675,980 | `9f67a541172b9711fd05fdc76e6501ad6ddd956464aa86c43d515da086144c5f` |

The profile SHA-256 is
`b4895772ff512baad132216a988de13bfe928d113c16cbe369b1aa9ee2525bec`;
the actual kernel Image remains
`d80bfce0feb5f6c0cec1b0b0dd4691323720ec3f34a373c7a109001e2cf42e76`.

The [evidence index](evidence/r5-run04/index.json) binds the complete
[production result](evidence/r5-run04/verify-result.json), actual pipeline
script and [collected construction/lineage records](evidence/r5-run04/collected-build-and-lineage.json).
The latter retains parsed contents alongside each original file's measured
size and hash, plus the original-file inventory; it does not pretend that
re-serialized embedded JSON preserves the originals' whitespace bytes.

The previous [boot-bundle checkpoint](../2026-11-23/r5-boot-bundle-checkpoint.json)
remains a timestamped historical record. Later staging and VM results belong
to this new checkpoint and do not rewrite that earlier observation.
