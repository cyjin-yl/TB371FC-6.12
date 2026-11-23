# Fedora research3: retained failure before the behavioral probes

## Outcome and scope

The independently copied Fedora 45 system reached its Enforcing verification
service with kernel `6.12.114-tb371fc-research3-system`, but its complete system
gate **failed**. The first failing operation was the real system-bus
`systemd-run --wait --pipe` request to create the controlled pids test. It
returned `Connection reset by peer` before the test process executed. This
attempt establishes neither pids enforcement nor the BPF filesystem-denial
behavior. The separate source diagnosis of research3's missing ARM64 function
entry instrumentation must not be reported as an observed BPF runtime failure.

The machine was QEMU's generic ARM64 `virt`, with no network, tablet DT, physical
device passthrough or host filesystem share. The joint Lenovo display/input DT
was packaged as an artifact. No tablet boot, physical input action, GPU rendering,
panel operation or peripheral acceptance occurred. The controlling evidence is
[fedora-research3-system.json](evidence/fedora-research3-system.json), SHA-256
`9a9ff035c1ced6565c531baef5276339fb67f39d3fb4f930e39017f47fbc9860`.

## Inputs and preserved copies

The source was the frozen 367-package Fedora baseline described in
[fedora-system-integration.md](fedora-system-integration.md). An attempted SSD
copy could not preserve POSIX ACLs; that failed copy and its record remain
separate. The used HDD copy passed a canonical source/destination stream
comparison including file content, ownership, modes, links, modification times,
ACLs and xattrs. Its 1,323,141,120-byte stream SHA-256 was
`4e789f5471821ded7c395cc11c665951b15a41a34d35358faa3c97d9e56a83e8`.
The source baseline was not changed. See the actual
[HDD copy record](evidence/fedora-input-copy-hdd.json) and
[failed SSD copy record](evidence/fedora-input-copy-ssd-failed.json).

The new kernel's complete build, 84-module inventory, symbol CRCs, public
certificate, CMS checks and BTF are recorded separately in
[research3-system-kernel.md](research3-system-kernel.md). Staging used only the
fixed regular runtime files, not build symlinks or a private signing key. The
69 owner firmware files already present in the copied baseline were checked
against their manifest. The old research1 runtime remains in this separate
copy; its generic metadata was archived before the active release was changed.

## Actual sequence and first failure

| Phase | Actual outcome | Elapsed time |
|---|---|---:|
| Stage attempt 01 | Failed an incorrect `MODULE_SIG_FORCE=y` assumption before runtime writes | 0.50 s |
| Corrected stage attempt 02 | Passed, new release, 84 modules and 69 firmware files | 2.00 s |
| Userspace configuration | Passed | 4.00 s |
| Initramfs construction and archive verification | Passed | 256.74 s |
| Independent 4 GiB ext4 construction | Passed | 33.54 s |
| Explicit permissive maintenance/relabel VM | Passed and powered off | 180.66 s |
| Enforcing verification VM | Failed at transient-unit system-bus request | 102.20 s |

The source-tree checksum after the first staging failure was unchanged. The
compiled mainline configuration has `CONFIG_MODULE_SIG_FORCE=n`, unlike the
separately observed Android setting. The corrected VM explicitly used
`module.sig_enforce=1` and required its sysfs readback. This did not rebuild or
weaken the kernel. The actual old source and its correction can be reconstructed
from the public [recipe history](../../../scripts/research/input/system-integration/history/README.md).

Before the bus failure, the guarded guest verified the active kernel release,
the exact runtime hashes, all 84 module and 69 firmware file identities,
Enforcing state and loaded SELinux policy version 33. The raw progress record
explicitly marks these as partial results. Its next record has exit status 1,
empty stdout, and the system-bus connection-reset error. There was no
`SYSTEM_COMPLETE` marker. The controller correctly failed even though QEMU
itself returned 0 when the controller terminated its owned child process.

The complete raw [verification serial log](evidence/fedora-research3-verify.log)
is 815,621 bytes, SHA-256
`81657fb6bb6a9d9cdd18da0a606673f767a1708354bff228ecdc3cad68d60c03`.
The separate [relabel serial log](evidence/fedora-research3-label.log) contains
permissive-phase AVC messages; these are not Enforcing-boot denials. A zero
count of particular warnings in the failed verification log is not evidence
that the unreached behavioral tests passed.

## Read-only diagnosis of the retained failure

PID 1 continued answering private-socket `LoadState` queries before and after
the failed call. That does not demonstrate the system bus was functional.
Upstream systemd's `--wait`/non-default-stdio route uses the system bus, and
`--pipe` carries standard input/output/error as D-Bus Unix file descriptors.
The observed failure occurred at the transient-unit call, before the worker
started. The fixed source comparison is
[systemd v258 run.c](https://github.com/systemd/systemd/blob/v258/src/run/run.c);
it corroborates the route but is not a claim of exact source equivalence to the
installed Fedora `262.1-1.fc45` binary.

The first failure handler let the controller end the VM before the newest
journal tail had persisted. Diagnosis therefore copied the ordinary ext4 file,
verified the copy, and replayed **only the copy's** journal. The source image
was never mounted or repaired, and its before/after SHA-256 remained
`8dc33b793be5c1ccd535fe77974d23d3882569e997c9e0bc977b92d83eb29469`.
No new VM or physical device was used for this extraction. The operations and
hashes are in
[fedora-research3-journal-diagnostics.json](evidence/fedora-research3-journal-diagnostics.json).

The extracted [broker journal records](evidence/fedora-research3-broker-journal.jsonl)
show the verification boot's broker ready in `system_dbusd_t` at about 68.7 s.
The persisted verification journal stops around 78 s; the reset occurred later.
Its absence from that incomplete tail does not rule out an LSM rejection or
another transport failure. In
[dbus-broker v37 socket.c](https://github.com/bus1/dbus-broker/blob/v37/src/dbus/socket.c),
`MSG_CTRUNC` on received Unix descriptors closes the socket. The exact 6.12
kernel receive path can produce truncation after either a descriptor-allocation
failure or a `security_file_receive()` rejection. This is a source-supported
diagnostic possibility, not an observed cause in the missing R3 window.

The later R4 recipe therefore records actual creating-process and broker
contexts, file-descriptor information, real broker/manager round trips and an
otherwise unrestricted `--wait --pipe` baseline. On failure it emits bounded
current-boot diagnostics and syncs before the terminal failure marker. It
retains Enforcing and the original broker route. Every required behavioral gate
must execute again for the new kernel; this R3 attempt remains failed.
