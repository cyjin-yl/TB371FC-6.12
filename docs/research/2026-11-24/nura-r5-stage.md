# Isolated Nura R5 stage (implementation, not executed on retained input)

This independent lane follows the retained Nura export and entry inventory.
It does not modify the original 382-package archive, stopped chroot, Fedora
run04 or any other lane. A new directory under /work/nura-r5-stage-* is required.

The stage pins the archive and original inventory, copies the archive before
extraction, rejects unsafe member layouts, preserves numeric owners and archive
metadata with GNU tar, and checks the original PID1, OpenRC, runlevel links and
boot entries. It stages the frozen R5 module/Kbuild files in a new namespace,
uses the separately retained 69-file firmware manifest without overwriting any
different distribution file, and runs the existing kernel and root module gates.
The original generic kernel and boot entries remain in the root; R5 boot inputs
are sibling files, not an active loader.

Run in the existing CT102 build environment (archive may be supplied from the
HDD builder by an ordinary file copy with its exact pinned identity):

```sh
python3 scripts/research/rootfs/stage_r5_nura.py \
  --repo /src --work /work/nura-r5-stage-01
```

This recipe requires the existing pinned R5 inputs, canonical firmware, GNU
tar, target AArch64 kmod and the previously pinned PRoot/QEMU host executors.
An incompatible host or colliding firmware is a real failure, not a reason
to weaken a gate. Retain the partial directory, command receipts and
nura-r5-stage.json; retry in a new directory.

The CI exercises only archive and guest-path contracts. It does not establish
actual archive compatibility, successful target depmod, image, initramfs,
OpenRC boot, signature enforcement or physical device behavior. The next
step after actual staging is a qualified minimal R5 root loader and normal
OpenRC VM verification. No owner-native acceptance cases are credited.
