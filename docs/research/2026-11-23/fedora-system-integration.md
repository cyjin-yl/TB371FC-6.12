# Fedora 45: full systemd and Enforcing boot with the research kernel

The separately assembled Fedora 45 AArch64 system has now **booted its ext4
root filesystem with the actual research1 kernel**, reached multi-user
systemd, verified its installed runtime files, and shut down cleanly in
generic ARM64 QEMU. The final boot used **SELinux Enforcing**, a genuinely
loaded version-33 policy, and PID 1 in `system_u:system_r:init_t:s0`.

This closes the earlier gap between a PRoot userspace/package experiment and
an actual kernel → initramfs → mounted distribution root → systemd boot.
It remains a **host/VM result**. The owner tablet is still running Android;
no Lenovo DT was passed to QEMU, no physical device was passed through, and
no A650, display, touch, radio, audio or suspend result is claimed.

The [frozen result](evidence/fedora-system-integration.json), SHA256
`66ac854b2bc938aed147afe0355b57fcbba856c874e9d82cec4cad663b1c87d9`,
contains the actual job records, artifact hashes, final guest result and
retained failures. The [367-package inventory](evidence/fedora-system-packages.tsv)
has SHA256 `6daee65e1e3b07e7aee764b2ec4bc75cac2864f47fa7372b709097782a20bdaa`.

## What was actually integrated

The original Fedora experiment at `/work/fedora-bundle/rootfs` was retained.
The new work lives under `/work/fedora-system-integration-v1` in CT102's
`tb371fc-build-20261123` container. Package installation used the previously
qualified PRoot 5.5.0 and explicit QEMU user interpreter; no host binfmt
handler, physical block device or host bootloader was installed.

| Component | Actual input/result |
| --- | --- |
| Kernel | `6.12.114-tb371fc-research1`, existing frozen Image |
| Kernel Image SHA256 | `5b7dbf8ac810ef4b488d394f6b976d876e52372621428f751f02f8deac5667f5` |
| Native board DTB, packaged only | SHA256 `129bbee33b0c71be120d1d724be6267d0e4f99c07ec9ed951a823ab9241998dc` |
| Runtime modules | All 83 frozen matching modules; builder `build` link omitted |
| Canonical private firmware | 69 files, 35,332,142 bytes; all re-hashed before copying |
| Firmware manifest | SHA256 `4feb4264605198fc56114fb8b8044ffcd51f662107270a857f59fdaf2e8bcf7c` |
| Installed Fedora packages | 367, with RPM database and dependency checks passing |
| Final initramfs | 30,649,939 bytes; SHA256 `2741ed3f3b5814b40dd303f4666b6f629c55ad11fd057a6e99f9f6be5e01c543` |
| Dedicated ext4 image | 4,294,967,296-byte ordinary file, label `tb371fc-f45` |
| Image after both clean boots | SHA256 `6a759bd9a7072b004b55c80cd6fa3bd584c5e6d6a8aa45584af91ec8a2fc4eaf` |
| Final offline filesystem check | `e2fsck -fn`, exit 0 |

The image is an ordinary file created exclusively for this test. Its label
is not a claim about the owner's existing three-partition SD card. It is not
an Android boot/recovery image and does not establish AVB, bootloader or
first-stage compatibility.

The selected additions were pinned before installation: systemd/udev
`262.1-1.fc45`, dracut/dracut-network `111-5.fc45`, NetworkManager
`1:1.58.1-3.fc45`, BlueZ `5.88-1.fc45`, PipeWire `1.6.11-1.fc45`, WirePlumber
`0.5.19-1.fc45`, ALSA utilities `1.2.16-2.fc45`, kmod `34.2-6.fc45`,
e2fsprogs `1.47.4-2.fc45`, util-linux `2.42.4-1.fc45`, policycoreutils and
libselinux-utils `3.11-2.fc45` / `3.11-5.fc45`, and targeted policy
`45.24-1.fc45`. The complete final package inventory was read again after
boot preparation and matched the recorded installation inventory.

## Firmware reuse was checked against the active kernel

The canonical firmware tree was originally staged against the frozen
research2-display contract. Before using it with research1, the staging
helper compared **all 22 audited loader-source hashes** and the relevant
compiled DT firmware-name properties, including significant absent
overrides. Every comparison matched.

This checks names and loader rules across these two profiles. It does not
equate their enabled devices or display behavior. WLAN board selection,
Bluetooth ROM selection, TFA containers, secure authentication and firmware
runtime ABI remain the open gates documented in
[stock firmware staging](stock-firmware-staging.md). No arbitrary board
database or acoustic variant was inserted to make the package look complete.

The final guest also re-read and checked all 83 module and 69 firmware payload
hashes from the mounted root. Their presence does not mean their physical
consumers were probed or that proprietary firmware executed in QEMU.

## The complete boot and security gate

QEMU used its generic `virt` machine, Cortex-A72 CPU model, two virtual CPUs
and 2 GiB RAM, with the new image as its only virtual disk. Networking,
physical passthrough, host shares, monitor sockets and incoming control
channels were absent. The runner bounded runtime and log size and reaped
only its own child process.

The first clean-archive boot was an explicit **permissive maintenance boot
of this new VM filesystem**. It loaded the policy and ran `setfiles` to
label the image, then shut down. The second boot used `enforcing=1`; it did
not relax policy to get the acceptance marker.

| Final enforcing guest check | Observed result |
| --- | --- |
| Kernel / architecture | Exact research1 release / AArch64 |
| Actual PID 1 executable | `/usr/lib/systemd/systemd`, ELF64 AArch64 |
| Root source and filesystem | `/dev/vda`, ext4, expected new label |
| systemd | `systemd 262 (262.1-1.fc45)` |
| Multi-user target | Active |
| udev / system D-Bus | Both active |
| Failed systemd units | Empty list |
| SELinux enforcement | `Enforcing` |
| Kernel-supported policy maximum | 33 |
| Actual exported loaded-policy header | Version 33, valid SELinux binary header |
| Loaded policy size / SHA256 | 3,835,420 bytes / `9c79cb12810a781d6cb91f9b7dff160a1d768c534b784743b4256015799f22a8` |
| PID 1 security context | `system_u:system_r:init_t:s0` |
| Re-read module / firmware payloads | 83 / 69, all matching |
| SELinux AVC denials in final serial log | 0 |
| Panic / invalid-initramfs marker | Neither present |
| Guest shutdown / QEMU exit | Clean power-off / exit 0 |

The clean labeling run took 135.638 seconds; the enforcing run took 88.595
seconds including guest shutdown. These are virtual execution times, not
tablet boot-performance measurements.

The [separate SELinux examination](selinux-compatibility.md) had already
proved that the fixed Fedora policy.35 could be converted to version 33 by
its actual ARM64 libsepol. This VM result adds the missing actual policy
load, labeling, Enforcing operation and correct systemd domain transition.
The exported policy hash differs from the userspace conversion's hash;
the kernel has parsed and reserialized the loaded policy. Its actual bytes
and header were recorded independently rather than equating `policyvers`
with the loaded policy's version.

## Failures retained and corrected

The initial DNF5 query omitted an explicit newline in its format string.
Strict parsing rejected it before installation; the corrected query and
the exact package pins are retained separately.

The first dracut run exposed missing `/dev/fd` aliases in the container root.
That broke shell process substitution. Its owned process tree was stopped,
the cancellation was recorded, and ordinary descriptor symlinks were added
before the new run. No system-wide device setup was changed.

The next dracut run produced a complete archive but its nested PRoot
`ldconfig` could not create the target cache. The retained initramfs tree
was repaired using Fedora's actual static AArch64 `ldconfig` under explicit
QEMU, outside PRoot, with `-X -r` against that private tree. Native x86
ldconfig was not substituted for the target cache generator.

The first native repack then exposed a real ordering bug: Python buffered
the 512-byte early CPIO prefix, while the gzip child wrote through the same
file descriptor before the buffer was flushed. The result began with gzip
and ended with the early CPIO. It could reach userspace and label the image,
but the kernel logged invalid initramfs magic. That old image and its
limited labeling result are retained; they are not the accepted candidate.

The recipe now explicitly flushes the prefix before invoking gzip. The
corrected artifact preserves the exact gzip stream and places the exact
early archive first. A **new ext4 image** was created and both boot phases
were repeated. The final log has no invalid-initramfs warning.

The independent [archive verifier](../../../scripts/research/rootfs/verify_initramfs.py)
and [results](evidence/initramfs-validation.json) check the actual compressed
artifact, not just the source directory. They reject the old image and
accept the corrected image, both with the default and explicit manifest
path. They validate the newc/gzip boundaries, CRC, trailer and hardlinks;
all 69 firmware payloads; all 38 ARM library-cache entries; and 134
non-firmware AArch64 ELF files. They do not extract or execute the image.

## Reproduction and retained work

The public helpers are under
[`scripts/research/rootfs`](../../../scripts/research/rootfs):

1. `fedora_system.py prepare`, `query`, `install` create a new root and
   install the pinned system packages from the qualified Fedora seed.
2. `stage_runtime.py` validates the frozen kernel, modules and canonical
   firmware before copying runtime files.
3. `assemble_image.py configure`, `initrd`, `repair-initrd`, `image` configure
   the test root, build dracut, complete the target cache and create the
   ordinary-file ext4 image. The repaired recipe flushes the archive prefix.
4. `verify_initramfs.py IMAGE --firmware-manifest MANIFEST` verifies the
   actual packed bytes against the fixed firmware and userspace contracts.
5. `boot_vm.py label --run vm-label-NN`, then `verify --run vm-verify-NN`
   perform the two explicit VM phases. The final gate requires the complete
   guest result and rejects failure markers anywhere in the final log.
6. `finalize_system.py` records this particular historical run set, rechecks
   the package identities and filesystem, and hashes the powered-off image.
   New experiments must use new run/output names rather than overwrite it.

The final raw serial logs remain in `vm-label-02` and `vm-verify-01` beneath
the work directory. Their hashes are in the frozen report. The earlier
archives, canceled run, old image and verifier revisions were retained.
Private firmware and the image itself are not committed to the public fork.

## Remaining integration limits

The final boot has no failed unit or SELinux denial, but it still records
two missing `autofs4` notices, two unavailable BPF-LSM notices, 32
`pids.max` read notices and one generic-QEMU GPIO deferred probe. These are
explicit follow-up configuration observations, not hidden successful
feature tests. A normal systemd boot does not prove every optional kernel
feature is configured.

The baseline research1 DT still disables native display and touch. The
separately built and signed [research2 input combination](input-signed-integration.md)
must keep its own kernel/module/DT identities and image validation. Neither
candidate has booted this owner's tablet. The physical entry/recovery path,
native display and pen coordination, GPU isolation and rendering, wireless
board selection, audio, cameras, sensors, charging, suspend and measured
stock parity remain open in the [whole-device ledger](acceptance.json).

Finally, retained package versions and source/artifact hashes are not a
claim of an independent, offline, bit-for-bit rebuild. Repository retention,
all transitive package inputs, generated filesystem identities, timestamps
and existing private module-signing keys still need to be accounted for in
that stronger reproducibility claim.
