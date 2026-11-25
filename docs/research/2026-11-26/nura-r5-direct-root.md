# Independent Nura R5 direct-root VM

This tool continues a successful `stage_r5_nura.py` receipt. It copies that
qualified root into a new integration directory and boots a separate ordinary
ext4 image with the frozen R5 kernel on QEMU's generic ARM `virt` machine.
It does not build an initramfs, execute the board DT, access physical devices,
or add any owner-native Linux acceptance passes.

## Construction and execution

Use the existing CT102 build environment, the exact source revision that
performed staging, and a new candidate directory. Preparation requires root
to preserve the root filesystem's numeric ownership and archive metadata.

```sh
python3 scripts/research/rootfs/nura_r5_vm.py prepare \
  --repo /src \
  --stage /work/nura-r5-stage-01 \
  --work /work/nura-r5-vm-01
```

Preparation rechecks the completed stage's archive, original init inventory,
module/Kbuild/depmod files, firmware and kernel artifacts. Canonical GNU tar
streams compare the copied root with the original and verify the source
remained unchanged. Only the new root receives a background OpenRC observer;
the original service definitions and runlevel entries remain present.
`mkfs.ext4 -d` builds a new 2 GiB ordinary file, followed by read-only fsck and
label checks. `--size-gib 3` or `4` selects a larger independent image.

Record the actual QEMU executable hash before starting a run, then supply it
explicitly. A new run directory is required each time:

```sh
sha256sum /usr/bin/qemu-system-aarch64
python3 scripts/research/rootfs/nura_r5_vm.py run \
  --work /work/nura-r5-vm-01 --run run-01 \
  --qemu-sha256 RECORDED_EXECUTABLE_SHA256 --timeout 600
```

The runner clones the prepared disk for each run, checks its identity, and
starts an owned QEMU child without networking, host shares, passthrough or a
board DT. The kernel command line selects `/dev/vda`, ext4, the original
`/sbin/init`, and `module.sig_enforce=1`. The R5 config is checked for built-in
virtio MMIO/block, ext4 and automatic devtmpfs, and for no embedded initramfs.
Timeout, cancellation and excessive serial output terminate and reap only the
owned QEMU process group. Failed disks and logs remain available.

## Evidence and acceptance

`prepare.json` records copy lineage, input identities and image construction.
Each run retains `command.json`, `serial.log`, filesystem/readback command
receipts, the guest result and `result.json`. The guest writes a JSON file to
its disk, syncs it, and prints a nonce/hash receipt before asking BusyBox init
for normal shutdown. The host reads the file back with read-only `debugfs` and
requires its hash to match the serial receipt; a boot banner cannot pass.

Core acceptance requires the original BusyBox PID1, R5 release, correct root
device/type/label, runtime file hashes, enforced module signatures, a signed
`autofs4` module load, actual OpenRC default runlevel, udev, D-Bus and a real
D-Bus round trip. All original services are separately reported, including
crashed services discovered by OpenRC's dynamic daemon checks. A failed
hardware-related service is retained as a failure even when the narrower core
boot passes. The whole default runlevel is reported healthy only when every
original default service is started without a crashed state.

The actual security state is recorded without claiming Fedora SELinux parity.
`root_loader_built=false`, `board_dtb_used=false` and
`owner_native_linux_passes_added=0` remain true limitations of this experiment.
The dedicated minimal root-loader and tablet hardware gates remain separate.

Local CI checks archive/path contracts, evidence rejection, OpenRC's unusual
`rc-status --crashed` return-code convention, and termination/reaping of a real
owned test child. It does not execute the retained Nura archive or an ARM VM.
