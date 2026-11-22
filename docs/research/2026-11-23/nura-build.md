# Nura / postmarketOS: native ARM build experiment

Experiment date: 2026-11-23, Asia/Shanghai. The source scripts live in
[`distros/nura`](../../../distros/nura/README.md). This report distinguishes
the generic ARM **builder VM** from the selected **distribution rootfs** and
from the physical **Lenovo TB371FC**. No result on QEMU's `virt` machine proves
tablet support.

## Confirmed result

A fixed, officially signed Alpine ARM64 bootstrap medium has been verified and
booted to a functioning root shell in QEMU TCG. The guest ran native AArch64
commands, installed the tooling needed by pmbootstrap, and verified the exact
pmbootstrap/pmaports Git revisions. pmbootstrap then created its native ARM64
build chroot with signed packages and normal package scripts. The corrected
probe executed `/bin/sh`, checked `uname` and APK architecture as `aarch64`, and
verified the four intended base packages; it completed with `DONE!` and the
explicit `NURA_NATIVE_CHROOT_VERIFIED` stage marker. The subsequent Nura edge
`qemu-aarch64` transaction installed **382 packages**, generated its generic
boot files, and passed native ARM chroot checks. The stopped target tree was
exported to a **307,393,454-byte gzip tar archive**; export and a separate
`gzip -t` integrity check both returned 0. Its SHA256 is
`eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46`.

This completes a generic userspace build/export, not a TB371FC boot or hardware
test. The target rootfs itself was not booted: the VM that ran was the separate
Alpine builder. The retained download cache covers **371 of 382** installed
package versions. `offline_cache_complete=false`; an independent offline
rebuild and byte-for-byte reproduction have not been demonstrated. The owned
builder VM and loopback media server were stopped after export; all source,
cache, log and artifact files remain in the original build volume.

The machine-readable [evidence record](evidence/nura-build.json) contains the
source pins, exact completed job commands, exit codes, elapsed times and
metadata/log hashes. It also records which stages have actually completed.

The experiment uses the already authorized `tb371fc-build-20261123` Docker
container inside CT 102 on doesvm. It changes neither the host's binfmt
registrations nor its physical-device exposure. The ARM guest uses its own
kernel and native chroot/mount operations. The reasons for this boundary are
practical: foreign `execve()` needs more than launching one program with
`qemu-aarch64`, and pmbootstrap's foreign-architecture support includes binfmt
registration. The full ARM VM supplies a native execution environment without
changing that shared host facility.

## Fixed sources

| Component | Actual source |
| --- | --- |
| pmbootstrap | [Official repository](https://gitlab.nura.eco/nura/pmbootstrap), `e0dfe2cda7f3a0b70cdcc96f3060100839322aa4`, version 3.12.1 |
| pmaports | [Official repository](https://gitlab.nura.eco/nura/pmaports), `d7e3e81fd579f01d4742157257897e2b07fade5c` |
| Selected device recipe | `device/community/device-qemu-aarch64`, version `16-r1` at that revision |
| Bootstrap ISO | [Alpine 3.24.4 aarch64 virt](https://dl-cdn.alpinelinux.org/alpine/v3.24/releases/aarch64/alpine-virt-3.24.4-aarch64.iso), 93,464,576 bytes |
| ISO SHA256 | `cf88d8ba67389d20d9ed307366b52e487c15d7d3ee3233b62b95f709daa1d430` |
| Signing key | `0482D84022F52DF1C4E7CD43293ACD0907D9495A` |

The ISO checksum matched both the fixed expected value and the official
checksum file. GnuPG returned exit 0 and `VALIDSIG` for the fingerprint above.
The key was obtained from Alpine's official site and checked against the
[official downloads page](https://alpinelinux.org/downloads/). The isolated
keyring still emitted the normal unknown web-of-trust warning; this experiment
does not claim an independently established key identity chain. The
[Alpine installation-medium documentation](https://docs.alpinelinux.org/user-handbook/0.1a/Installing/medium.html)
describes the signature/checksum verification route.

The initial medium and source commits are fixed. Alpine stable and Nura edge
package repositories remain moving inputs. A reproducible package closure
requires retaining the actual signed indexes, downloaded APKs and package
manifest; merely recording the Git commits is insufficient.

## Builder that actually ran

The observed QEMU was Debian `10.0.13`, using `virt-10.0`, a Cortex-A72 CPU model,
two virtual CPUs, 2 GiB guest RAM and the multi-threaded TCG accelerator. QEMU
`virt` is a generic virtual platform, as described in its
[official documentation](https://www.qemu.org/docs/master/system/arm/virt.html).
It does not emulate the tablet's SM8250 display, charger, input devices, GPU,
radio, storage controller or firmware handoff.

The successful guest reported:

```text
Linux localhost 6.18.60-0-virt #1-Alpine SMP PREEMPT_DYNAMIC 2026-11-01 07:26:31 aarch64 Linux
Python 3.14.10
pmbootstrap 3.12.1
```

The bootstrap root reached 105 installed packages / 84.8 MiB after installing
Python, Git, kpartx, util-linux, OpenSSL, procps, tar, rsync and CA certificates.
These are the **builder's** packages, not a count for the requested Nura target
rootfs. The guest's package inventory is retained at
`/work/pmwork/guest-share/arm-builder-packages.txt` in the build container.

QEMU exposes only three project-specific 9p shares: a writable work share and
read-only tooling/recipe checkouts. It uses user networking with no guest port
forwarding. A loopback-only HTTP server supplies public files extracted from
the verified ISO. These paths and the exact VM command are documented in the
[script README](../../../distros/nura/README.md).

## Target package transaction and archive

`nura-target-install-01` returned 0 after 1,165.481 seconds. pmbootstrap used
`install --no-image --no-sshd --no-recommends --no-local-pkgs`, console defaults,
and the explicitly requested Mesa, Turnip, Weston, libinput, input-event,
NetworkManager and Bluetooth tools. Normal APK package scripts ran. The
transaction reported 382 packages / 681.5 MiB; the complete version inventory
has SHA256 `76764f419b983efde5e49bb1fc1ba6e4ef393989368ebc4c60d4ce37014cdb9f`.

| Target component | Resolved package version / observed check |
| --- | --- |
| Distribution | `/etc/os-release`: `Nura edge`, `ID=nura`, `ID_LIKE=alpine` |
| Device recipe | `device-qemu-aarch64-16-r1` |
| Generic packaged kernel | `linux-postmarketos-stable-7.3.5-r0`; modules directory `7.3.5` |
| Mesa / Gallium / Turnip | `26.3.1-r0`; Turnip shared library verified as AArch64 ELF64, machine 183 |
| Weston | `16.0.0-r0`; native chroot `weston --version` returned 0 |
| libinput | `1.32.0-r0`; native version command returned 0 |
| NetworkManager | `1.58.1-r1`; native version command returned 0 |
| BlueZ | `5.87-r0`; package installed, radio operation not tested |

The generic target's 7.3.5 kernel is different from both the Alpine builder's
6.18.60 kernel and the separate TB371FC 6.12 research kernel. No kernel/modules
interchangeability is claimed. The APK kernel trigger initially deferred
initramfs generation inside pmbootstrap; pmbootstrap subsequently ran
`mkinitfs` and `boot-deploy` explicitly, completing both. The target contains
`boot/vmlinuz`, `boot/initramfs`, `boot/EFI/BOOT/BOOTAA64.EFI` and
`boot/loader/entries/pmos.conf`, with individual hashes in the evidence JSON.
Generating those files did not test booting them.

The root and research accounts' synthetic passwords were locked and verified
before export; no user password or SSH key was imported. Target and native
pmbootstrap chroots were stopped and their guest mounts released. The exporter
then verified the two account locks, package inventory, boot files, AArch64
Turnip library and the AArch64 loader behind `msm_dri.so -> libdril_dri.so`.
The latter is a DRI loader entry, not evidence that Freedreno initialized an
Adreno device. Neither OpenGL/Vulkan acceleration nor a compositor was tested
against tablet hardware in this experiment.

`nura-rootfs-export-02` returned 0 after 213.547 seconds. GNU tar 1.35 retained
numeric ownership, ACLs and extended attributes in a sorted POSIX archive;
gzip 1.13 ran with `-n -1`. The exporter removed only the diagnostic build
repository `/mnt/pmbootstrap/packages/edge` from the target APK configuration,
recorded its before/after hashes, and retained the four public repository URLs.
It did not format a disk or generate a tablet installer.

| Retained item in the original build container | Result |
| --- | --- |
| `/work/pmwork/artifacts/nura-qemu-aarch64-userspace-20261123.tar.gz` | 307,393,454 bytes; SHA256 `eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46` |
| `/work/pmwork/guest-share/rootfs-export.json` | Export command, input/output hashes, boot/library files and explicit scope flags |
| `/work/pmwork/guest-share/target-package-cache.json` | 379 retained cache files: 371 APKs and eight index files; SHA256 `2c5af8effe7285a79c5303e5cda6a1be5a472b619a35b1f2be2b434be7ba8e4a` |
| `/work/pmwork/guest-install-01.serial.log` | Successful native probe, package transaction, generated boot files, target checks and chroot stop; SHA256 `9ba8d922b03b2587a86d63a8602bb9527e243e1f07930a8f7913708d6310758d` |

The subsequent `nura-archive-integrity-01` ran `gzip -t` against the final file
and returned 0. `nura-cleanup-01` checked exact owned process identities and
stopped only VM 03 and the loopback media server. Both processes exited. Their
job exit values reflect deliberate infrastructure termination, not another
boot test. The stopped chroot, source checkouts, cache, original failed jobs
and successful archive remain available on doesvm.

## APK cache limitation and bounded follow-up

The initial exporter required one retained APK for every installed version
and refused export because the following 11 archives were absent. Each has
`I:0` in the installed APK database. Their recorded archive sizes are nonzero;
the cause of their automatic-cache omission has not been established. They
must not be described as invented packages or treated as cached without an
actual archive.

```text
linux-firmware-none-20261019-r0
postmarketos-base-apk-79-r0
postmarketos-base-fwupd-79-r0
postmarketos-base-mesa-79-r0
postmarketos-base-nftables-79-r0
postmarketos-base-nofde-62-r0
postmarketos-base-ui-wifi-wpa_supplicant-66-r0
postmarketos-bootsplash-openrc-3-r0
postmarketos-ui-console-1-r0
pyc-3.14.10-r1
python3-pyc-3.14.10-r1
```

The first cache helper spent its time rescanning the 9p cache directory and was
explicitly interrupted before fetching packages. The corrected helper indexed
the cache once and supplied actual `NAME=VERSION` APK selectors in the native
pmbootstrap chroot, using its Nura/Alpine edge repositories and AArch64
architecture. All 11 fetches failed to resolve their requested version. A
final bounded retry used the **target chroot** and the original installation's
explicit `--cache-dir /var/cache/apk`, first requesting only
`postmarketos-ui-console=1-r0`. That probe also failed; the remaining ten were
not retried. Chroot cleanup still completed. These failure logs and exact
commands are retained, including the unsuccessful initial export.

The final exporter separates a verified filesystem-tree export from the
stronger claim that a complete APK cache can recreate it offline. It records
371 cached versions, all 11 missing versions and their installed metadata,
with `offline_cache_complete=false` and
`independent_offline_rebuild_tested=false`. An optional
`--require-complete-cache` gate remains available. No package was silently
substituted and no APK signature or TLS validation was disabled to obtain the
archive. Sorted archive members and source pins are also insufficient to claim
a byte-identical rebuild of generated files.

## Preserved builder failures and corresponding corrections

### Optional network ROM absent

The first VM command selected `virtio-net-pci`; QEMU exited because the minimal
container lacked `efi-virtio.rom`. The next command selected
`virtio-net-device`, which uses the ARM virtual machine's MMIO transport and
does not need that optional EFI network-boot ROM. This was a builder setup
failure, not a tablet driver result.

### Initramfs HTTPS trust absent

The second VM booted the kernel and acquired networking, but the minimal
initramfs could not validate the external Alpine HTTPS repository's
certificate. No base packages were installed, `/sbin/init` was absent and the
guest entered its initramfs emergency shell. Certificate checks were kept
enabled.

The third VM used the signed APK repository extracted from the already
verified fixed ISO, served on container loopback. It then booted to a complete
Alpine root shell. The guest installed the CA bundle from this signed local
repository and used ordinary HTTPS repositories for subsequent tools. The
96-file bootstrap repository has a recorded checksum manifest; its SHA256 is
`3840f292ba94bcbe8d0897f27cef22c1507b7139cd6167d4128b60f93a77b32b`.

### Native pmbootstrap initialization

The first native invocation exited 1 after 436 seconds. After its initial
version line and a long pause, the complete log reported that
`get_upstream_remote()` could not match the configured Nura Git remote against
its two older `gitlab.postmarketos.org/postmarketOS/pmaports.git` URLs. No
chroot/work content had been created. Its raw serial log was preserved with
SHA256 `e111f5044fa0c0eacb9fe11e54547a43d0f36f469b37a47eefe849c724c775a6`.
The process exited before the planned interrupt was needed; the second attempt
connected to the existing shell normally. Source inspection identified two
details that improve the next invocation:

1. The official `PMB_CHANNELS_CFG` environment override can read `channels.cfg`
   from the pinned checkout directly, avoiding a moving remote-main reference.
2. An empty noninteractive work directory must first receive the same work
   version/cache directory state that pmbootstrap's interactive new-directory
   routine writes. `work_migrate` is not a substitute for first initialization
   of an unversioned empty directory.

The retry script refuses to initialize an existing nonempty unversioned work
directory and adds a 180-second timeout for pmbootstrap's child commands. The
error's cause is established by the final traceback; the reason for the long
pause before that traceback is not established. The kernel reported
`crng init done` at boot, which does not support an entropy-starvation claim.
Container storage and relay response delays are retained as limitations when
interpreting elapsed times.

Two subsequent probe errors were in the research wrapper and were corrected
without changing the upstream source revisions. One command passed
`--output STDOUT`, whereas this version's parser accepts lowercase `stdout`.
The next probe created and executed the ARM chroot successfully but then tried
to read `/etc/alpine-release`. pmbootstrap intentionally installs a minimal
build chroot rather than the distribution release package, so that optional
file was absent. The corrected probe checks APK's architecture and the actual
`alpine-baselayout`, `apk-tools`, `busybox` and `musl-utils` dependencies instead.
Its successful output is preserved in the target-install job before that job
starts the separate rootfs transaction.

## Boot-media artifacts retained

The build-container directory is `/work/pmwork/boot/alpine`.

| File | Bytes | SHA256 |
| --- | ---: | --- |
| `vmlinuz-virt` | 10,412,544 | `cd05fed9e617b5df93dc62ece9b78c422fd94e9b432a2f7c092714b139d5eef4` |
| `initramfs-virt` | 10,167,867 | `a0aca3b06df6b029711099e78cf01635f53331754d14af608f87bf9254630bac` |
| `modloop-virt` | 17,788,928 | `a726889467d1d4fefa4ba1ed710f28b9db1fbd019ca3eba2d4c6c65b33536343` |
| `Image` | 36,306,944 | `a2cecb9b6fdbd83e87bd43c8040de67300d5b8dde1fc50c34714faa272888f17` |

The raw `Image` comes from the declared gzip payload of Alpine's EFI zboot
wrapper, with payload offset 51,832 and length 10,353,483 bytes. The script
checks the resulting ARM64 Image magic. This follows the header fields in
Linux's [EFI zboot assembly header](https://github.com/torvalds/linux/blob/v6.12/drivers/firmware/efi/libstub/zboot-header.S),
instead of treating the wrapper as an interchangeable raw ARM64 kernel.

The signature log, `media.json`, original ISO/checksum/signature and the
extracted APK checksum manifest remain beside these files. They identify the
generic builder medium; none is an exported TB371FC boot artifact.

## Remaining tablet integration contract

The pinned pmaports checkout has a `qemu-aarch64` profile and other SM8250 donor
work, but it supplies no tested `device-lenovo-tb371fc` package in this
experiment. A tablet-specific package must bind the chosen kernel Image,
matching module ABI, DT, initramfs entry, signed firmware layout and recovery or
kexec handoff. Native panel/touch integration, real DRM/A650 acceleration,
Wi-Fi/BT, input, storage, audio, camera, sensors, charger ownership, thermal
protection and suspend/resume each retain their own physical Linux acceptance
gates. Installing their userspace packages does not pass those gates.

