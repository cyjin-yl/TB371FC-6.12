# Nura with frozen R5: completed direct-root ARM64 boot

Date: 2026-11-26 Asia/Shanghai. The actual run started at 2026-11-25 18:24:38 UTC and its final host receipt completed at 18:26:42 UTC.

**Result: the generic ARM64 direct-root core boot passed.** The original BusyBox PID1 and OpenRC startup reached default, all 15 core checks passed, normal shutdown completed, QEMU exited 0 and the post-shutdown read-only filesystem check exited 0.

## What actually ran

- Kernel: `6.12.114-tb371fc-research5-services`, original Image SHA-256 `d80bfce0feb5f6c0cec1b0b0dd4691323720ec3f34a373c7a109001e2cf42e76`.
- Machine: generic QEMU `virt`, Cortex-A72, 2 virtual CPUs, 2 GiB RAM; an independent ordinary-file ext4 disk.
- Init: original `/sbin/init` resolving to `/usr/bin/busybox`; original OpenRC sysinit, boot and default runlevels.
- Runtime: udev and D-Bus started; a real D-Bus method call completed; `module.sig_enforce=1` was observed and signed `autofs4` loaded.
- Integrity: 49 original file checks, 167 runtime-file checks and 2 added observer-file checks had no mismatches.
- Service snapshot: all 31 original service names were in started state; all 14 original default services were started, and OpenRC reported no crashed service.
- Isolation: no networking, physical passthrough, host filesystem share or board DT. The frozen stage and prepared base image were preserved.

The QEMU execution took about 101.55 seconds. The [raw serial log](evidence/nura-r5-vm/run-01/serial.log) reaches ext4 root mounting, the original init chain and normal `Power down`. The [actual invocation](evidence/nura-r5-vm/run-01/command.json), [guest result](evidence/nura-r5-vm/run-01/guest-result.json), [host result](evidence/nura-r5-vm/run-01/result.json), and [filesystem check](evidence/nura-r5-vm/run-01/filesystem.json) are retained unchanged.

## Evidence binding

The [preparation receipt](evidence/nura-r5-vm/prepare.json) binds the executed host and guest sources, copied root lineage, kernel and prepared image. The [profile](evidence/nura-r5-vm/profile.json) binds the original init/services and retained runtime files.

The guest synced its result to disk and emitted its nonce plus SHA-256. The host then used read-only debugfs after shutdown to recover that same JSON. Its SHA-256 is `5ac109386a8b38064b16f227954b5a16dba8861f28b989f6253300e3b30ed36b`; the original serial log SHA-256 is `436a0352f24488beee68e2136b2027d87bf78e02a54c8581e7f6e558e87a30e5`. Source file and raw evidence identities were independently checked after export. All 33 exported files matched their recorded lengths and hashes; independent review found the core-boot conclusion supported.

CI validates the retained package's identities and acceptance relationships, explicitly without executing an ARM VM. The actual run was performed in CT102; CI results are not substituted for that execution.

## Limits and remaining work

Started services do not prove physical wireless, USB, rfkill, display, touch or suspend operation. The log includes a missing wireless-interface notice, a logbookd restore notice and a swap service-name notice; this is not an error-free-log claim.

The guest recorded SELinux `enforce=0` and PID1 context `kernel`. This result does not establish Fedora's Enforcing policy state.

This is a direct-root boot on generic virt: no dedicated root-loader/initramfs was built, no board DT was executed and no tablet was rebooted or flashed. `root_loader_built=false` and `owner_native_linux_passes_added=0` remain. The owner-native 44-case ledger is unchanged.
