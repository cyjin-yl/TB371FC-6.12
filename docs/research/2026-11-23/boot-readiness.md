# Actual boot prerequisites and verified current-partition backups

Date: 2026-11-23, Asia/Shanghai. All observations below concern this owner's
TB371FC. **The eight current boot-related partitions have verified local and
off-device copies. A working mainline entry or recovery procedure has not yet
been demonstrated on this tablet.** No partition was written, no slot changed,
no module loaded, and no unlock or reboot was performed.

## The running Android kernel cannot provide the assumed kexec entry

The [passive capability capture](evidence/android-boot-capabilities.json)
reads the running `4.19.157-perf+` kernel's `/proc/config.gz`, selected boolean
entry controls and MMC node names. It does not attempt a kexec syscall.

| Observed configuration/state | Practical implication |
| --- | --- |
| `CONFIG_KEXEC=n`; no kexec loaded/crash-loaded interfaces | Installing a kexec executable does not supply the missing kernel implementation |
| `CONFIG_MODULES=y`, `CONFIG_MODVERSIONS=y`, `CONFIG_MODULE_SIG_FORCE=y` | A generic or historical unsigned module cannot be assumed loadable; matching release text is insufficient |
| `modules_disabled=0` | The module facility is enabled; this does not cancel the signature or ABI requirements |
| `CONFIG_USB_CONFIGFS_ACM=n`, NCM and FunctionFS enabled | The author's first-stage ACM rescue console is not established by this current Android configuration |
| `CONFIG_PSTORE=n`, `CONFIG_CRASH_DUMP=n` | The current system does not provide those configured capture mechanisms |
| `mmcblk0`, `mmcblk0p1`, `mmcblk0p2`, `mmcblk0p3` present | A card exists with three partitions; the author's two-partition/card-specific installation assumptions must not be applied to it |

The public capture contains only the allowlisted configuration values and
hashes of the original config bytes. It contains no card CID, serial, raw
command line or filesystem contents. Its source is
[collect_boot_capabilities.py](../../../scripts/research/collect_boot_capabilities.py).

The historical [V34 report](../../PANEL_PORT.md) describes a specifically
modified first-stage kernel with kexec enabled and an ARM64 ABI fix. That
historical result belongs to the author's kernel/entry path. It does not
describe the current kernel just measured here.

## Lock state must be resolved at the actual entry

The [earlier boot-state capture](evidence/android-boot-state.json) contains a
real disagreement:

| Source | Device state | Verified-boot color | Slot |
| --- | --- | --- | --- |
| Android properties | `locked` | `green` | `_a` |
| Allowlisted kernel command-line keys | `unlocked` | `orange` | `_a` |

The reason for that disagreement has not been established. Neither a claim
that the bootloader is definitely locked nor one that a particular temporary
boot command will work follows from these two views. An unlock or userdata
erase is not a diagnostic step for this disagreement. The next entry test
must observe the actual bootloader and available recovery transport.

## Copies actually made and checked

[backup_current_boot.py](../../../scripts/research/backup_current_boot.py)
opens only the eight fixed block-device sources with `O_RDONLY`. It checks
their exact sizes and available filesystem capacity before creating a fresh
root-owned `0700` directory. Each `0600` output is flushed, read back and
hashed; the source is read again to detect a change during the copy. A partial
or failed operation is retained and cannot become a verified manifest.

| Partitions | Bytes per partition | Count |
| --- | ---: | ---: |
| `boot_a`, `boot_b` | 100,663,296 | 2 |
| `recovery_a`, `recovery_b` | 104,857,600 | 2 |
| `vbmeta_a`, `vbmeta_b` | 65,536 | 2 |
| `dtbo_a`, `dtbo_b` | 25,165,824 | 2 |
| **Total** | **461,504,512** | **8** |

All three hashes for each partition agree in the
[local copy manifest](evidence/android-boot-backup-local.json). The local
directory is `/data/local/tmp/tb371fc-current-boot-backup-20261123`; it is on
userdata and would not by itself survive a userdata erase.

A second copy was therefore streamed to doesvm using the owner's existing
SSH identity and strict host-key verification. The expected host public key
was independently read through the existing device connection. The existing
known-hosts entry already matched; no key was replaced or verification disabled.
An exact remote Python marker was checked before the successful transfer.

The first attempt used OpenSSH-specific arguments against a Dropbear client.
It returned a version banner without executing the remote command, and the
producer got a broken pipe. That attempt is retained as failed. The corrected
Dropbear invocation executed the receiver, both processes exited zero, and
the transfer took 18.00 seconds on the tablet's monotonic clock.

[receive_boot_backup.py](../../../scripts/research/receive_boot_backup.py)
checks the archive's complete file-name/type/size set without extracting its
members to the host filesystem. It re-hashes every embedded partition image,
checks its per-partition sidecar against the original manifest, and independently
re-reads the stored compressed archive. The successful
[off-device receipt](evidence/boot-backup-off-device.json) records:

- Compressed archive: **93,319,878 bytes**.
- Archive SHA-256:
  `6fb0d1964bef82d0b1bcb91282da48a6223910f5987ab1c8466d5746e7ead8e2`.
- Original local-manifest SHA-256:
  `12d63dd3386abdfdf64ea89fbd70326dc63a0247b760b4edaae2185b82621774`.
- Eight independently verified off-device image hashes, all equal to the
  original source/copy/source-recheck hashes.

The private archive and receipt are retained on doesvm at:

```text
/tank/shared/projects/tb371fc-linux/private/boot-backups/current-20261123/
```

The archive is ignored by Git. Only scripts and metadata are published.
These are **current partition copies**, not certified pristine factory images,
not a backup of Android userdata/super/persist, and not a demonstrated restore.
The active A slot was observed running Android; inactive B has not been boot
tested in this session.

## Actual image layout and slot differences

[inspect_boot_backup.py](../../../scripts/research/inspect_boot_backup.py)
first verifies the stored archive hash, then interprets only the four
boot/recovery images' reviewed version-2 layout. The
[inspection evidence](evidence/boot-header-inspection.json) records numeric
header fields, component offsets/sizes/hashes and bounded kernel release
strings. It omits command lines, image IDs and ramdisk paths/contents.

All four images have Android header version 2, header size 1660 and page size
4096. The kernels are uncompressed ARM64 Images containing the release string
`4.19.157-perf+`; the ramdisks are gzip. Each kernel component occupies
37,445,648 bytes, while its ARM64 header requires an effective image region
of 44,785,664 bytes, with `text_offset=0x80000` and `flags=0xa`. The effective
memory region is a distinct boot contract from the stored file length.

The A-slot boot and recovery kernels have equal hashes. The two B-slot kernels
also match each other, but differ from A despite equal release strings and
sizes. The boot-A DTB component differs from the other three DTB components.
No cause is assigned to these differences without further evidence; artifacts
must be paired by exact slot and hash rather than release text alone.

The two recovery images additionally contain a 4,299,963-byte recovery-DTBO
component at offset 46,030,848, with equal hashes. Their normal DTB component
is at offset 50,331,648. The format parser does not establish AVB signature
validity, rollback-index compatibility or that a newly packed image will boot.

Primary format references:

- [AOSP boot image header](https://source.android.com/docs/core/architecture/bootloader/boot-image-header).
- [Linux ARM64 boot protocol](https://docs.kernel.org/arch/arm64/booting.html).

## Remaining concrete entry work

The next physical experiment needs a matched, independently identified
first-stage/loader, an actual root-loading initramfs, exact final DT and module
set, required private firmware, and a reachable console/recovery path. The
generic [QEMU probe init](kernel-build.md) is not that root loader, and Nura's
qemu-profile boot files are not TB371FC boot files.

In particular, the final second-stage flattened DT must retain the intended
`lenovo,tb371fc` root compatible so that the board-specific early page-table
path is selected. A first-stage Qualcomm recovery DT is not interchangeable
with it. DMA quiescence, memory reservations and the original kexec handoff
problem still need physical evidence.

The successful copies close the missing off-device-backup item. They do not
close boot, recovery, display, GPU or any other hardware acceptance case in
the [whole-device ledger](acceptance.md).
