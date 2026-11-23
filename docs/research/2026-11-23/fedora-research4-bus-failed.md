# First R4 Fedora system attempt: retained broker-path failure

**Result: failed, not a verified system candidate.** The first R4 system image
booted the fixed research4 kernel and reached the Enforcing root-side verifier,
but the unrestricted real-broker `systemd-run --wait --pipe /usr/bin/true`
control returned `Connection reset by peer`. It did not reach the TasksMax
worker or the controlled BPF filesystem-denial test. The completed image,
recipe, partial progress, diagnostics and original serial bytes are retained.
This is generic ARM64 VM evidence; it provides no owner-tablet Linux result.

The frozen machine report is
[evidence/fedora-research4-bus-failed.json](evidence/fedora-research4-bus-failed.json)
(44,664 bytes, SHA-256
`b0b92ba42e47b959c1f295e0309e54ce45ee47acef2e3dabf28d268269cfbef1`).
The independently retained controller result is
[evidence/fedora-research4-bus-failed-verify.json](evidence/fedora-research4-bus-failed-verify.json).

## Exact candidate and source

| Item | Actual value |
|---|---|
| Builder | `tb371fc-build-20261123`, CT102, standard Docker |
| New work prefix | `/work/fedora-input-system-v3` |
| Actual source recipe | `/work/fedora-input-system-recipe-r4-v2` |
| Recipe manifest SHA-256 | `35fc0c3401cd1402bb2e851fb4223474ccefae08e520b6224e1af98ac3f1288e` |
| Active kernel release | `6.12.114-tb371fc-research4-system` |
| Image SHA-256 | `8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb` |
| Kernel build report SHA-256 | `0db9a7e6164b44ac845a80974c3a369476ede23ac6f094de9c14c8602fa3faa6` |
| Runtime payloads checked before failure | 84 module files and 69 firmware files |
| Initramfs SHA-256 | `2297d486c5bd79984926f129afa7bfa719a3f3490aa7e0dc3752bceeb4ad4958` |
| Failed image file | `/work/fedora-input-system-v3/fedora45-research4-system.ext4` |
| Failed image size | 4,294,967,296 bytes |
| Failed image SHA-256 after owned QEMU exit | `8f8733a1feb67efe76eecd66fe40ba6c32cb86d4a23fdbbf53b0d674b45523e6` |

The source is publicly reconstructible from the unchanged R3 runtime templates,
`derive_research4_profile.py`, then `refine_research4_bus.py` and its fixed
`history/r4-bus-diagnostics.patch`. The latter adds failure diagnostics before
the terminal failure marker; it does not replace the real broker transport.
The newer v5 source is a separate full profile and does not overwrite this
executed recipe.

## Phase results

| Actual phase | Controller result | Duration |
|---|---:|---:|
| Runtime staging | Exit 0 | 2.50 s |
| Root configuration | Exit 0 | 5.00 s |
| Fresh initramfs and archive checks | Exit 0 | 228.10 s |
| New ordinary ext4 image | Exit 0 | 61.05 s |
| Maintenance labeling VM | Exit 0 | 169.09 s |
| Enforcing verification VM | **Exit 1** | 110.55 s |

The verification QEMU lifetime was 109.48 s. The controller terminated only
its owned QEMU after the guest emitted its failure marker. This is not a clean
system poweroff or a post-boot filesystem qualification. The failed image has
not been repaired or reused as the baseline for a later candidate.

The VM used generic `virt`, a Cortex-A72 model, 2 vCPUs and 2 GiB RAM. It had no
network, board DT, physical-device passthrough or host filesystem share. The
packaged Lenovo DT was a runtime artifact checked by hash, not the DT supplied
to QEMU. Compiled `CONFIG_MODULE_SIG_FORCE=n` was retained; this VM separately
requested `module.sig_enforce=1` and verified the runtime enforcement setting.

## What actually succeeded before failure

The guarded root-side verifier observed the expected kernel and dedicated root
filesystem, loaded policy version 33 with Enforcing active, and checked the
entire staged runtime manifest, including all 84 module files and 69 firmware
files. Those are payload and VM facts; no firmware was authenticated or used
by a tablet device in this test.

The real broker answered `org.freedesktop.DBus.GetId`, and the real system-bus
manager query returned `262.1-1.fc45`. The subsequent `systemd-run` debug log
shows connection to `/run/dbus/system_bus_socket`, completed authentication and
Hello, then a `StartTransientUnit` request and a reset. The command being
requested was the unrestricted `/usr/bin/true` control. This establishes that
the failure preceded the pids/BPF workers and that ordinary broker round trips
were working. It does not establish successful Unix-FD forwarding.

The actual Python creator and systemd-run client had
`system_u:system_r:unconfined_service_t:s0`. Both held stdout/stderr pipe inodes
had that same SELinux context and FIFO mode. The inherited stdin inode was
`null_device_t`; its inode label is distinct from its open-time FD SID. The
observed broker **launcher** was `system_dbusd_t` with a high MLS range. Its
15 descriptors and limit 16,384 are launcher observations, not evidence about
the broker child: this recipe attempted the unavailable `/proc/.../children`
interface, so the child was not actually inspected.

The corrected future profile scans PPid and comm to find that child, validates
the actual pipe labels while holding the FDs, and queries the actual exported
policy bytes. Those corrections are separate from the result above.

## Two distinct problems identified

### The validator's pipe domain

The fixed Fedora policy's independent userspace AV query allows the broker's
FD-use permission for `unconfined_service_t`, but denies the FIFO read/write
and related permissions with audit-deny bits suppressed. It allows the
corresponding existing `initrc_t` service-domain permissions. The frozen Linux
receive path and dbus-broker v37 source provide a compatible mechanism:
security checks while receiving an FD can cause ancillary truncation, after
which the broker closes the connection.

This is source and offline-policy support for a specific explanation. This
failed VM did **not** capture a broker `recvmsg` trace or run the AV calculation
on its own exported policy bytes, so this report does not assert that the reset
has been directly traced to that syscall branch. The separate
[SELinux policy query report](selinux-access-query.md) and
[copy side-effect addendum](selinux-query-copy-followup.md) retain their own
scope and serialization boundary. The new v5 profile uses a strict, existing
`initrc_t` service context and retains the restriction on
`unconfined_service_t` FIFOs; it does not modify policy or switch to a private
socket.

### Early udev queued-event FD loss

The raw verification log contains a real early denial at approximately 40.63 s:
PID1 `init_t` was denied `getattr` on a `kernel_t`
`netlink_kobject_uevent_socket`. Immediately during state deserialization,
PID1 reported that it failed to store the `event-serialization` FD and ignored
it. This is a queued-event handoff failure, not the later D-Bus reset and not a
warning that may be counted as harmless.

The controller counted two textual denial occurrences because the same audit
event also appeared in its later diagnostic JSON. They are one deduplicated
observed audit event; the frozen controller count remains unchanged. The
late-label initramfs had no early SELinux configuration, policy, contexts or
libsepol. The matched systemd/udev source analysis and the pinned native
bootstrap proposal are documented in
[early-initramfs-selinux.md](early-initramfs-selinux.md). That report does not
claim the new bootstrap has already passed as PID1. The new profile must prove
early process domains and absence of observed event-storage/restore loss in a
new VM.

## Original evidence bytes

| Evidence | Bytes | SHA-256 |
|---|---:|---|
| [Maintenance serial](evidence/fedora-research4-bus-failed-label.log) | 1,086,250 | `6e3116cba8d6eb5ad9a12101c6c8e08ea6743eacaf5aeda991a4b751964031b2` |
| [Verification serial](evidence/fedora-research4-bus-failed-verify.log) | 889,309 | `f99f7fca24dab4d97ac12ab76a3c531544f76e06e6f61b61f6911bc33a4cb114` |
| [Verification result](evidence/fedora-research4-bus-failed-verify.json) | 32,143 | `17d32a79b4f2b36952077634168804cf71eed24ac8ed49c4a8ff7e98f2064138` |

Raw CR/LF bytes are preserved. The repository's `fedora-*.log -text` attribute
prevents Git text normalization from changing these identities.

The separate source-copy records retain a later failed copy and the fresh
quiescent requalification; they do not revise this failed VM:
[evidence/fedora-source-copy-race-failed.json](evidence/fedora-source-copy-race-failed.json),
[evidence/fedora-source-copy-quiescent.json](evidence/fedora-source-copy-quiescent.json),
and [evidence/fedora-source-copy-comparison.json](evidence/fedora-source-copy-comparison.json).

No owner-tablet boot, display, touch, pen, keyboard, GPU, Wi-Fi or other hardware
case is marked passed by any result in this report.
