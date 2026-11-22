# Nura / postmarketOS ARM64 userspace experiment

These scripts create a **generic ARM virtual build environment** and exercise
the pinned `qemu-aarch64` distribution profile. They are not a Lenovo TB371FC
device port, installer, recovery payload or firmware bundle. The actual results,
including unsuccessful attempts, are in
[nura-build.md](../../docs/research/2026-11-23/nura-build.md).

## Fixed inputs

| Input | Pin |
| --- | --- |
| pmbootstrap | `e0dfe2cda7f3a0b70cdcc96f3060100839322aa4`, version 3.12.1 |
| pmaports | `d7e3e81fd579f01d4742157257897e2b07fade5c` |
| Initial ARM VM medium | Alpine `alpine-virt-3.24.4-aarch64.iso` |
| ISO SHA256 | `cf88d8ba67389d20d9ed307366b52e487c15d7d3ee3233b62b95f709daa1d430` |
| Alpine release signing key | `0482D84022F52DF1C4E7CD43293ACD0907D9495A` |

The two Git source revisions and the initial ISO are fixed. The subsequently
resolved Alpine and Nura repositories can change. Preserve the package
inventory, signed repository indexes and downloaded packages when reproducing
an output; source pins alone do not freeze the userspace dependency closure.

## Isolation and paths

The observed experiment used the existing project build container, a two-vCPU,
2 GiB QEMU TCG `virt-10.0` ARM VM, user-mode networking and three explicit 9p
shares. It required no KVM, physical disks, USB passthrough, host loop devices,
host mount privileges or host `binfmt_misc` change.

| Build-container path | ARM guest path | Access |
| --- | --- | --- |
| `/work/pmwork/guest-share` | `/work` | Read/write project work files |
| `/work/pmbootstrap` | `/work/pmbootstrap` | Read-only pinned tooling |
| `/work/pmaports` | `/work/pmaports` | Read-only pinned recipes |

Thus the guest work directory `/work/pmwork` is actually
`/work/pmwork/guest-share/pmwork` in the containing Docker filesystem. Keep this
distinction when inspecting logs or copying artifacts. The guest config is
`/work/pmwork/guest-share/pmos.cfg` in the build container.

## Media preparation

The container needs Python 3, GnuPG, QEMU system AArch64 and tmux. Download and
verify the public medium using:

```sh
python3 /src/distros/nura/fetch_media.py --output /work/pmwork/boot/alpine
```

`fetch_media.py` checks the fixed ISO checksum, its official checksum file and
its detached GPG signature in an isolated keyring. It extracts the ISO's three
boot files and its signed APK repository using ISO9660 metadata. Alpine's
`vmlinuz-virt` is an EFI zboot wrapper; the script uses its declared gzip payload
offset/length and verifies the decompressed ARM64 `Image` magic before saving
`Image`. It does not format or attach a disk.

Serve only this public, verified bootstrap directory on container loopback:

```sh
python3 -u -m http.server 18083 --bind 127.0.0.1 \
  --directory /work/pmwork/boot/alpine
```

The guest reaches that server at `10.0.2.2:18083` through QEMU user networking.
The initial repository is local HTTP because the minimal initramfs did not
contain the external HTTPS CA trust needed during the first attempt. APK
signature validation remains enabled. Once the VM has booted, the guest script
installs the CA bundle from that signed repository and switches ordinary
package downloads to HTTPS.

## Recorded VM command

Create the three share directories and copy the guest scripts/config into
`/work/pmwork/guest-share` before starting a new VM. The successful bootstrap
used this argument set, recorded in `/work/pmwork/vm-command-03.json`:

```sh
qemu-system-aarch64 \
  -machine virt-10.0,gic-version=3 -cpu cortex-a72 \
  -smp 2 -m 2048 -accel tcg,thread=multi \
  -kernel /work/pmwork/boot/alpine/Image \
  -initrd /work/pmwork/boot/alpine/initramfs-virt \
  -append 'console=ttyAMA0 ip=dhcp alpine_repo=http://10.0.2.2:18083/apks modloop=http://10.0.2.2:18083/modloop-virt' \
  -display none -monitor none -no-reboot \
  -chardev socket,id=serial0,path=/work/pmwork/console.sock,server=on,wait=on,logfile=/work/pmwork/console-03.log \
  -serial chardev:serial0 \
  -netdev user,id=net0 -device virtio-net-device,netdev=net0 \
  -fsdev local,id=work,path=/work/pmwork/guest-share,security_model=none \
  -device virtio-9p-pci,fsdev=work,mount_tag=work \
  -fsdev local,id=pmbsrc,path=/work/pmbootstrap,security_model=none,readonly=on \
  -device virtio-9p-pci,fsdev=pmbsrc,mount_tag=pmbsrc \
  -fsdev local,id=ports,path=/work/pmaports,security_model=none,readonly=on \
  -device virtio-9p-pci,fsdev=ports,mount_tag=ports
```

Choose new console/record filenames for a new attempt. Do not start a second
process using a live VM's socket. QEMU's `wait=on` starts guest execution when
the serial controller connects.

After logging in as the bootstrap medium's root account, mount the shares
inside that disposable guest:

```sh
modprobe 9pnet_virtio
mkdir -p /work
mount -t 9p -o trans=virtio,version=9p2000.L work /work
mkdir -p /work/pmbootstrap /work/pmaports /work/pmwork
mount -t 9p -o trans=virtio,version=9p2000.L,ro pmbsrc /work/pmbootstrap
mount -t 9p -o trans=virtio,version=9p2000.L,ro ports /work/pmaports
```

The `serial_command.py` helper records raw serial output, the exact submitted
command, elapsed time, an explicit command exit marker and the log SHA256. Use
`--login-root` for a newly booting guest and omit it for an already logged-in
shell. `--interrupt` is only for deliberately interrupting a known previous
foreground command in this dedicated guest; it sends Ctrl-C before waiting for
the shell prompt. Every attempt requires a new `--record` filename.

## Distribution configuration and stages

The tested configuration was written with pmbootstrap's own `Config` and
`pmb.config.file.save()` APIs:

```ini
[pmbootstrap]
aports = /work/pmaports
build_pkgs_on_install = False
device = qemu-aarch64
hostname = nura-qemu-research
jobs = 2
service_manager = openrc
user = research
work = /work/pmwork

[providers]

[mirrors]
alpine = https://dl-cdn.alpinelinux.org/
pmaports = https://mirror.postmarketos.org/postmarketos/
```

`guest-bootstrap.sh` asserts the ARM architecture and exact Git pins, installs
the tooling inside the ARM VM, and uses the official `PMB_CHANNELS_CFG` override
to read `channels.cfg` from the pinned recipe checkout. For a new empty work
directory only, it initializes the same work-version/cache directory state as
pmbootstrap's interactive new-directory routine. It refuses a nonempty
unversioned directory. This does not mean the interactive `pmbootstrap init`
command was executed.

The subsequent native `pmbootstrap chroot` probe must succeed before running
`guest-install.sh`. The latter requests the `qemu-aarch64` rootfs with console
defaults and selected Mesa/Freedreno/Turnip, Weston, libinput, network and
Bluetooth userspace packages. `--no-image` deliberately produces a filesystem
tree without a disk image. A public dummy password is used only to make the
build noninteractive; the root/research passwords must be locked before any
rootfs export. No user password or SSH key is imported.

Run sustained work in a real tmux pane using the shared job recorder, for
example:

```sh
python3 /src/scripts/research/build/run_job.py --name nura-guest-bootstrap-NEW -- \
  python3 /work/pmwork/serial_command.py \
  --socket /work/pmwork/console.sock \
  --record /work/pmwork/guest-bootstrap-NEW.json --timeout 1800 \
  --command 'sh /work/guest-bootstrap.sh'
```

Check the resulting command-exit JSON and serial log. The outer tmux session
remaining open is not an exit result. A booted builder, a successful native
package transaction, a rootfs archive and a physical-tablet boot are separate
milestones; the result report states which were actually reached.

## File export after verification

After `guest-install.sh` returns 0, `complete_package_cache.py` provides a
bounded optional cache diagnostic inside the ARM VM through the same serial
helper. In the observed APK transaction,
11 installed packages with zero installed payload size had no archive in the
automatic cache. This helper compares the exact installed version list with
that cache, tries one exact-version `apk fetch` with an explicit cache path
inside the target chroot, and only fetches the other missing packages if that
probe succeeds. It stops the chroot again and does not run another target
package transaction. The observed probe failed to resolve the metapackage;
the retained failure and missing-package list remain part of the evidence.

Then export the stopped chroot tree from inside the containing build container:

```sh
python3 /src/scripts/research/build/run_job.py --name nura-rootfs-export-NEW -- \
  python3 /src/distros/nura/export_rootfs.py \
  --install-record /work/pmwork/guest-install-NEW.json \
  --output /work/pmwork/artifacts/nura-qemu-aarch64-userspace-20261123.tar.gz
```

The exporter requires the recorded successful guest command, a package
inventory, two locked synthetic account passwords and an AArch64 ELF Turnip
library. It separately records which installed package versions have a unique
retained APK, including every missing version and its installed metadata.
`--require-complete-cache` adds an optional strict cache gate. A successful
rootfs archive does not imply that an independent offline rebuild is possible.
GNU tar then preserves numeric ownership, extended attributes and
ACLs in a regular archive file. The exporter removes the diagnostic chroot's
private `/mnt/pmbootstrap/packages/edge` APK repository entry and records the
before/after hashes of that configuration. The four actual public repository
URLs are retained. It writes the archive checksum,
package/cache manifests and exact command to
`/work/pmwork/guest-share/rootfs-export.json`. It refuses to overwrite previous
outputs; explicit alternative record/manifest paths are available for a new
attempt.

The tarball is a userspace tree. It has not been made into a tablet disk image
or tested as the tablet's boot filesystem. Sorting tar members and retaining
the package inputs also do not constitute a demonstrated byte-for-byte
rebuild: generated files and timestamps remain part of the observed artifact.

`collect_evidence.py` is a read-only inventory helper. It combines this
experiment's named job/serial records, media verification, source snapshots
and export manifest. It accepts `--work-root /work` inside the build container
or the confirmed path of the same Docker volume for a read-only host-side
collection. It never executes a guest command or reads unrelated container
state.

After a successful export, `stop_builder.py` can release this experiment's
owned VM and media server. It runs inside the original container, verifies
the successful export and exact process identities, sends SIGTERM only to
those two children, and records their exits in `/work/pmwork/cleanup.json`.
It retains all build files. The observed run also verified the final archive
with `gzip -t`; the archive is 307,393,454 bytes with SHA256
`eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46`.
Its 382 installed packages have 371 retained APKs, so the evidence explicitly
keeps `offline_cache_complete=false` and records all 11 missing versions.

