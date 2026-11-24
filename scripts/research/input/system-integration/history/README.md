# Reconstructing the actual system recipes

These files preserve the source of a failed check. They do not approve that
historical check as a correct requirement for a new candidate.

## R3 stage attempt 01

The attempted recipe at `/work/fedora-input-system-recipe-r3-final` had manifest
SHA-256 `485c66848d4acc7948271770688812f28d4b4554d55528015fbb393bed7e6ea1`.
It incorrectly required the mainline build to have `CONFIG_MODULE_SIG_FORCE=y`.
The actual unchanged research kernel has `CONFIG_MODULE_SIG=y`,
`CONFIG_MODULE_SIG_ALL=y`, `CONFIG_MODULE_SIG_SHA512=y`, and
`CONFIG_MODULE_SIG_FORCE=n`. Android's separate FORCE setting was not evidence
for the mainline setting. Stage attempt 01 stopped before runtime writes.

The public files one directory above correspond to the corrected R3 recipe,
whose twelve-file manifest is
`dcd451b8d7bc50033f5f7dcbd4fa671af968f27df5f4fef4580de4c0ba7fb1b0`.
`r3-stage01-reconstruction.json` gives every original and corrected file hash.
For `verify_initramfs.py`, use the unchanged public file at
`scripts/research/rootfs/verify_initramfs.py`.

To reproduce the old source, copy those twelve corrected files into a **new**
recipe directory and apply the patch there:

```sh
patch --batch --fuzz=0 -p1 -d NEW_RECIPE_COPY \
  < scripts/research/input/system-integration/history/r3-stage01-from-runtime-signing.patch
```

Verify every resulting file against `target_files` in the reconstruction JSON.
The patch changes four files; the other eight are identical. The recorded
`reconstruction-check.json` is an actual successful patch application followed
by all twelve target hash checks. It did not execute the obsolete recipe.

## Corrected R3 and independent R4

The corrected R3 recipe ran from
`/work/fedora-input-system-recipe-r3-v2`. It checks the actual compiled signing
configuration and uses the explicit `module.sig_enforce=1` parameter in its
owned VM, with a guest readback of the enforcement state. This is distinct from
changing the kernel's compiled `MODULE_SIG_FORCE` value.

`derive_research4_profile.py` consumes only those exact twelve R3 template
hashes, verifies the template manifest, and writes a new R4 recipe prefix. Its
derivation record describes each identifier substitution and the additional
resolved ARM64 ftrace configuration guards. The R4 work directory, root label,
release, command-line guards, console markers, transient unit names and image
filename are separate. Every runtime gate is executed again for R4.

With the public checkout mounted in the normal builder, the source-only
derivation is reproducible using:

```sh
python3 scripts/research/input/system-integration/derive_research4_profile.py \
  --templates scripts/research/input/system-integration \
  --validator scripts/research/rootfs/verify_initramfs.py
```

The output prefix must not already exist. The command prepares recipes only;
it neither builds an image nor starts a VM. It never writes to a tablet.

## R4 system-bus diagnosis

The initial R4 derivation has twelve-file manifest SHA-256
`c532046cfb8458c8ee6a8ab545e95118f53b913c74b8e9882fce13aaf8a6f9c1`.
Its baseline-copy helper was executed before the runtime diagnosis was added.
The completed R3 VM stopped at `systemd-run --wait --pipe`, before either the
controlled pids worker or the BPF restriction probe ran. A source diagnosis of
R3's ftrace configuration is not an observed BPF runtime failure.

`refine_research4_bus.py` verifies that complete initial R4 recipe and applies
the fixed `r4-bus-diagnostics.patch` to a new recipe directory. The resulting
twelve-file manifest is
`35fc0c3401cd1402bb2e851fb4223474ccefae08e520b6224e1af98ac3f1288e`.
The actual runtime recipe is `/work/fedora-input-system-recipe-r4-v2`.
`r4-bus-diagnostics.json` describes the two changed files, and
`r4-bus-reconstruction-check.json` records a real zero-fuzz application and
validation of all twelve resulting hashes.

```sh
python3 scripts/research/input/system-integration/refine_research4_bus.py \
  --base /work/fedora-input-system-recipe-r4-v1 \
  --patch scripts/research/input/system-integration/history/r4-bus-diagnostics.patch
```

This requires the normal `patch` executable. The HDD builder's first source
preparation failed because that program was absent. Its twelve unchanged base
templates were retained at
`/work/fedora-input-system-recipe-r4-v2-prepare-failed`; the rootfs had not been
changed by that preparation. Installing the single Debian `patch` dependency
inside the owned Docker builder allowed the source-only derivation to finish.
The dependency log and first-preparation record remain with the remote recipe.

The new guest performs real system-bus `GetId` and systemd manager queries,
then an otherwise unrestricted `--wait --pipe` transient `/usr/bin/true` before
the pids test. It records the actual caller, client, broker and pipe contexts.
Only after the exact generic-VM, root image, profile and Enforcing guards have
passed can the failure handler collect bounded current-boot diagnostics. It
syncs the journal and image before emitting the terminal failure marker. The
host continues to require the real broker route, all original behavioral
gates and a complete success record. Neither a private-socket substitution nor
a weaker SELinux policy is introduced.
