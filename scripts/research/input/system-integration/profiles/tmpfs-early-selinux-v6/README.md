# R4C / v6: ordinary tmpfs before the fixed early SELinux loader

This independent profile uses `/work/fedora-input-system-v6` and the unchanged
R4 Image, inspected 84-module set and 69 owner firmware files. It follows the
retained v5 failure: policy loaded successfully, but relabeling `/var` on the
special `rootfs` filesystem was denied `filesystem associate`. No v5 result,
image, log, policy or native loader is overwritten.

The production command line selects exactly `rdinit=/init.tmpfs` and
`rd.tb371fc.tmpfs-root=1`, together with the existing explicit Enforcing and
early-policy flags. The reviewed stage0 copies a fixed, complete set of
ordinary top-level payload roots to a real tmpfs; API roots are excluded. It
uses the fixed Fedora `switch_root` to enter the separately built stage1.
Stage1 requires the actual old/new filesystem identities to differ, reaps the
one successful cleanup child, verifies that the old root is empty, reconnects
the proper console, and only then executes the unchanged `/init` ELF
`e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d`.
There is no policy allow, force-context mount, `setcon`, `setenforce` or ignored
relabel failure.

The independent source/build recipe for stage0/stage1 is under
`scripts/research/selinux/tmpfs-root`. Its fixed inputs here are:

- `init.tmpfs`: 6,039 bytes, SHA-256 `15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d`.
- `init.tmpfs-wait`: 71,872 bytes, SHA-256 `cc30c123b32259b1097eeb2f34cc13528d510cfc2521aac170bae23c4880a63a`.
- Fedora `usr/bin/switch_root`: 69,104 bytes, SHA-256 `6b6c1803111f117b76b553a664cec1a074827d025618446319d7871f9c127f75`.

The new checker is pinned to
`92f02fd33fcc5f7aaea6d1d0e06c04589af024b09e8f678f772798909c2ebb07`.
It requires the unchanged v5 checker `58a5...` beside it, reuses only its fixed
parsers/readers, and independently retains the original `263866...` verifier
and `2741...` R1 archive as trust anchors. The three handoff inputs, full copy
domain, API exclusions, cross-domain hardlinks, command/dependency closure,
policy, loader cache, firmware and every userspace ELF are checked in the
actual newc archive. An archive pass does not prove that copy, cleanup or
SELinux operations have executed successfully.

The same-boot initrd proof reads actual PID1/udevd contexts and PID1 mountinfo.
It requires root tmpfs with source `tb371fc-initroot`, read/write operation,
no `nosuid` or `noexec`, and the exact unique command-line opt-ins. The host
requires the actual sequence COPY_COMPLETE → CLEANUP_COMPLETE → original
POLICY_LOADED → EXEC_SYSTEMD → post-exec initrd proof, matches both stage
device-number records and compares the new device to the independent proof.
The original real-broker FD route, loaded-policy query, strict validator
`initrc_t`, TasksMax/EAGAIN, BPF baseline/deny, module signature enforcement,
autofs, taint-zero, BTF, runtime hashes and zero-AVC gates remain mandatory.

A separate full-raw-log udev loss qualification is now an explicit pipeline
phase before finalization. It rejects the matched storage/restore failure
messages. Missing count debug lines do not imply an empty original queue;
equal counts describe only successful stored/inserted events. The finalizer
binds that qualification to the exact successful VM result and raw-log hashes.

The maintenance archive stays separate and has no `rdinit` stage0 selection.
It is used only to label this newly created ext4 image; the full production
boot is independently verified with Enforcing. QEMU continues to use generic
`virt`, no Lenovo DT, no physical devices, no network and no host share. No
result from this profile passes an owner-tablet hardware case.

`profile-source-manifest.json` fixes all twelve profile files. The materializer
adds four independently pinned supplemental files and refuses an existing
recipe directory. After the native quiescent-copy/runtime preparation and
stage1 source build have qualified their independent inputs:

```sh
python3 scripts/research/input/system-integration/profiles/tmpfs-early-selinux-v6/materialize_recipe.py --repo /path/to/checked/source
python3 /work/fedora-input-system-recipe-r4-v4/run_pipeline.py \
  --report-sha256 0db9a7e6164b44ac845a80974c3a369476ede23ac6f094de9c14c8602fa3faa6 \
  --bundle-sha256 82ffa9d01bd5cab5fe859e0182cac9998f103391ca5dac469b0044234fa18627
```

Every actual phase retains its own log and exit record. Failures stop the
pipeline; no later phase may turn a failed bootstrap into a completed system.
