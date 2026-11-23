# Nura: existing native init inventory and bounded next-boot plan

This read-only inspection identifies the actual target's startup chain. It does
not boot the target, run its binaries or modify the stopped target directory.
The earlier native ARM builder boot and package installation remain separate
from a successful boot of the exported target root filesystem.

## Exact material inspected

The stopped target is
`/work/pmwork/guest-share/pmwork/chroot_rootfs_qemu-aarch64` in the original HDD
project builder. The recorded export JSON is 5,457 bytes, SHA-256
`85aa1f9d979e92ee3c6efa40d344fdea224d6ab5b6be3dc10b65ef5b907aa0e5`,
and was re-read and matched before this inventory. It identifies the original
307,393,454-byte archive, SHA-256
`eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46`.
This probe checked the archive's current ordinary-file metadata and size; it
did not scan, extract or rehash the entire archive again. Therefore the newly
inspected stopped-tree files are not claimed to have been independently matched
against every archive member in this probe.

The complete bounded inventory is [nura-entry-inventory.json](evidence/nura-entry-inventory.json),
58,260 bytes, SHA-256
`8e9f289acc6b7be0d40e6e89dec21125a8e9a3a2f16189adbab7e774e7ec991d`.
The exact native collector source is
`scripts/research/input/nura/inspect_existing_target.py`. It resolves absolute
symlinks relative to the target root, rejects escapes, bounds file/directory
reads and does not invoke PRoot, a chroot, target binaries or a VM. The native
collector exited 0. Root, `dev` and `etc` metadata were identical before and
after; this is not a claim about every inode's access time.

## Actual entry and services

| Item | Actual static observation |
| --- | --- |
| `/sbin/init` | Resolves through merged `/sbin` and `/bin` to `/usr/bin/busybox`, AArch64 ELF, 919,296 bytes, SHA-256 `79d9f5301a6781f5b4c885a190e32c1bef4d441b180fac1d2af5672e2cda0b77`. |
| `/sbin/openrc-init` | Absent. It must not be substituted for or described as the existing PID 1. |
| `/sbin/openrc` | AArch64 ELF, 67,440 bytes, SHA-256 `2a52e80af8e15cd83f67ffb01deee58323cfd72e813d8f78673ac4c2c2828bed`. |
| `/etc/inittab` | Original BusyBox init sequence invokes `/sbin/openrc sysinit`, `boot`, then `default`; it already includes a `ttyAMA0` getty. SHA-256 `069974fcce1908d8bbd64daee7ab1cc7b32e0a0e102044509f6d81debfce4c5d`. |
| Python | `/usr/bin/python3` resolves to the AArch64 `/usr/bin/python3.14`, 67,328 bytes, SHA-256 `b776d2d6601ffe3bebbae359a8560a7efd0fe1d80b33b6235035225090a567db`. Presence/ELF identity is not a Python runtime or module-closure test. |
| Root mounting | The original 98-byte `/etc/fstab` explicitly does not mount `/` or `/boot`. Its SHA-256 is `001260aa450333d1757fddae7bcf01cf006ce323050dc2fa51d749802bde5ea2`. |
| Existing kernel | The export identifies `linux-postmarketos-stable-7.3.5-r0`; the stopped target's sole original module directory is `7.3.5`. Its original boot files do not constitute an R4 initramfs/module combination. |
| Identity | Actual `/etc/os-release` resolves to the original `Nura edge` file, SHA-256 `4fff1905e56583d53e102a80c42721c662e3310ddca1fab2bc4c51881bdae3d1`. |

The existing `sysinit` runlevel includes devfs, udev, udev-trigger and udev-settle,
plus the installed sysusers/tmpfiles service wrappers. `default` already includes
D-Bus, NetworkManager, cgroups, nftables, wpa_supplicant and other original
services. D-Bus starts the original `dbus-daemon`; NetworkManager declares a
dependency on it. These are service definitions and activation links, not
observed running services.

The inventory also preserves hardware-dependent/default entries, including the
USB-network DHCP service in `boot`, zram and rfkill-related services. It would be
incorrect to silently delete their activation and then describe the entire
original default runlevel as validated. A generic VM cannot prove their owner
tablet behavior.

## Minimum independent next candidate

The feasible next construction is a new root/image prefix with the original
BusyBox PID 1 and OpenRC sequence retained. A separately qualified minimal
initramfs must mount that dedicated virtio-backed ext4 root and required API
filesystems, then execute the existing `/sbin/init`. It must not reuse the
original 7.3.5 initramfs as if it were built for the unchanged R4 kernel.

The new copy must first qualify its source archive or full source-copy identity.
Any early static tool and its actual commands/format must also be pinned before
boot. The exact R4 Image, module release, all 84 signed modules and 69 firmware
payloads must be installed in a new release namespace with depmod metadata;
original boot files and the 7.3.5 module tree remain retained as prior material.

A native OpenRC verification service can be added only to the new candidate.
It should prove the original PID 1 executable, expected release/root identity,
actual OpenRC runlevel and service status, real D-Bus round trip, ordinary udev
and module loading, runtime hashes and observed security state. It must record
the actual status of original services and any failures rather than predeclare
all services healthy. Its result transport should use the qualified ordinary
file plus short receipt pattern, followed by normal VM closure and a read-only
host extraction. No Fedora SELinux equivalence follows merely from using the
same R4 kernel.

These are construction requirements inferred from the inspected entry chain.
The target Python runtime, complete dependencies, minimal initramfs, original
OpenRC startup and normal shutdown still require their own actual qualification.
At this inventory point there is no new Nura VM, no target-root boot result and
no owner-tablet Linux acceptance change.
