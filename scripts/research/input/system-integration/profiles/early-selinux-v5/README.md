# R4B / v5: early SELinux and a legitimate verification service domain

This is a separate, fixed recipe for `/work/fedora-input-system-v5` in the HDD
project builder. It uses the frozen `6.12.114-tb371fc-research4-system` kernel,
its inspected module inventory and the packaged joint Lenovo display/input DT.
QEMU still receives its own generic `virt` DT, no network, no physical-device
passthrough and no host share. Successful VM execution cannot pass a tablet
hardware acceptance case.

The nine files in `profile-source-manifest.json` are the exact new executed
sources. They are full independent overrides of the earlier R4 recipe whose
manifest is retained in `base-recipe-manifest.json` (SHA-256
`35fc0c3401cd1402bb2e851fb4223474ccefae08e520b6224e1af98ac3f1288e`).
The old R3 sources, R4 derivation, diagnostic patch, failed images and logs stay
unchanged. `materialize_recipe.py` verifies the new source manifest and five
independently pinned supplemental files before creating the fresh immutable
`/work/fedora-input-system-recipe-r4-v3` directory.

## Specific corrections

The validation service explicitly enters the policy's existing `initrc_t`
domain. The guest reads its actual process context and the actual broker child
context, queries **the actual kernel-exported policy bytes** through the fixed
public libsepol ABI, and requires both allowed service FD/FIFO access and the
retained restriction on `unconfined_service_t` FIFOs. This does not introduce a
global policy allow, relabel a pipe, disable Enforcing, or prove all production
services have the same IPC permissions.

The production initramfs contains the reviewed, pinned native ARM64 bootstrap
at `/init`. In one process it uses the standard libselinux policy-load and
recursive relabel APIs, then executes the original systemd. The original
`/init` symlink remains at `/init.systemd`. Config, policy version 35, contexts,
libselinux and the added libsepol come from the fixed Fedora source tree. The
native bootstrap's two `dlopen` dependency edges are explicit. Its built ELF
is pinned to `e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d`.
The source and reproducing build recipe are under `scripts/research/selinux`.

A new initrd oneshot records actual post-exec PID1 `init_t` and udevd `udev_t`
contexts, tied to this boot ID. The root-side verifier checks that proof. The
host additionally requires the native bootstrap success lines, zero AVCs and
no lost event-serialization FD. If udev logs positive queued-event
serialization, the host requires root-side PID1 FD-store acceptance and
root udevd event deserialization with matching positive event counts.

The real system-bus GetId and manager-property round trips are followed by the
same `systemd-run --wait --pipe` true control, bounded TasksMax/EAGAIN probe,
and identical-command RestrictFileSystems baseline/deny pair. There is no
private-socket replacement for the broker path. Signed autofs loading,
`module.sig_enforce=1`, taint zero, kernel BTF, cgroup pids, PL061, package and
runtime inventories remain required. Compiled `MODULE_SIG_FORCE=n` is retained
and is reported separately from the explicit VM runtime signature policy.

## Two distinct archives

`early_initramfs.py` first builds a fresh maintenance archive for the copied
filesystem's first labeling boot. It uses the unchanged original verifier and
an explicit `enforcing=0` maintenance phase. It cannot qualify as the production
archive. The production archive is built independently from the retained tree
and requires `enforcing=1 rd.tb371fc.early-selinux=1`.

The new production verifier is pinned to SHA-256
`58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e`.
Its independent anchor is the original 30,649,939-byte R1 archive,
`2741ed3f3b5814b40dd303f4666b6f629c55ad11fd057a6e99f9f6be5e01c543`,
verified by the unchanged legacy checker. The qualified old 38 library cache
mappings plus the actual native-bootstrap dependency closure determine the
new map. Actual ARM `ldconfig -p -C` output must agree with those mappings.
All policy/context, bootstrap, firmware and library payloads are then checked
in the actual compressed newc archive. The initrd-domain-proof script, unit
and activation link have separate byte/mode/link checks.

Only the new candidate root is executed through PRoot. The original Fedora
root is read natively. Its historical directory timestamps are not reset.
The failed v4 copy is retained; the independent quiescent v5 copy was verified
against its source. A full native comparison found only three directory mtime
differences between retained v4 and v5 copies, with identical regular payloads,
other metadata, xattrs, symlink targets and hardlink groups. That result does
not reconstruct the historical tar hash or turn the original tar exit 1 into
success.

## Fixed builder execution

Prerequisites are the separately qualified v5 baseline copy, the verified
runtime input bundle, and the pinned native bootstrap already present in their
recorded project prefixes. Their creation helpers and retained failures are
outside this recipe. Do not use another source root, an uninspected module
set, a maintenance archive as the production baseline, or an author-private
signing key.

From a checkout or checked source overlay in the authorized project builder:

```sh
python3 scripts/research/input/system-integration/profiles/early-selinux-v5/materialize_recipe.py --repo /path/to/checked/source
python3 /work/fedora-input-system-recipe-r4-v3/run_pipeline.py \
  --report-sha256 0db9a7e6164b44ac845a80974c3a369476ede23ac6f094de9c14c8602fa3faa6 \
  --bundle-sha256 82ffa9d01bd5cab5fe859e0182cac9998f103391ca5dac469b0044234fa18627
```

Each phase writes a new log and exit record. An existing output is refused.
A failure stops the sequential pipeline and remains a failure. The final
report is created only after both owned VM phases and post-boot filesystem,
package and runtime checks pass. No command here operates on the tablet.
