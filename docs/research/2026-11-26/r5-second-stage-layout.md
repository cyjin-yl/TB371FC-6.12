# R5 second-stage load-layout gate

This change connects the completed R5 Fedora inputs to a paused TB371FC QEMU
handoff. It verifies the contents actually loaded into simulated RAM before
the controller can issue `cont`. A successful layout result does not establish
userspace execution or native hardware readiness.

## Inputs and ownership

[`second_stage_inputs.py`](../../../scripts/research/second_stage_inputs.py)
pins the R5 Image, configuration, public certificate, retained second-stage
DTB, production-qualified initrd, and completed run04 post-verify root image.
It requalifies the complete 84-module kernel bundle against the published
[`boot-candidate-r5.json`](../2026-11-23/boot-candidate-r5.json), reads and hashes
the 4 GiB root image, and checks the release/certificate/Image relationship.
The executable QEMU identity is supplied explicitly from a separately qualified
artifact; this Linux gate does not replace the QEMU functional qualification.

The source bytes and prior results remain unchanged. See the
[R5 runtime checkpoint](../2026-11-24/r5-runtime-checkpoint.json),
[retained DT derivation](../2026-11-24/r5-second-stage-dtb.md), and the separate
[Nura direct-root VM result](nura-r5-vm-result.md). Nura's passing generic VM
does not supply the Fedora initrd/root pair selected here.

## Manifest and command

The version-1 manifest has exactly these top-level members:

| Member | Contract |
| --- | --- |
| `schema_version` | Integer `1` |
| `release` | `6.12.114-tb371fc-research5-services` |
| `kernel_bundle` | Absolute path to the complete retained R5 kernel bundle |
| `kernel_load_base` | Integer aligned to 2 MiB; typical value `2684354560` (`0xa0000000`) |
| `bootargs` | One nonempty, unquoted kernel command line |
| `files` | Exactly `kernel`, `dtb`, `initrd`, `config`, `certificate`, `rootfs`, `qemu` |

Each `files` member contains exactly `path`, `bytes`, and lowercase `sha256`.
Paths must be canonical absolute paths to ordinary files; symlinks and commas
are rejected. The six R5 identities must equal `FIXED` in the input verifier;
substituting a newer build requires a separate, reviewed contract. The manifest
parser rejects duplicate JSON keys and boolean values masquerading as integers.

The command line must contain exactly one of each:

```text
rdinit=/init.tmpfs rd.tb371fc.early-selinux=1 rd.tb371fc.tmpfs-root=1 enforcing=1 module.sig_enforce=1 root=LABEL=tb371fc-r5-f45
```

Add the intended serial console and diagnostic arguments explicitly. Conflicting
root/entry/enforcement arguments, `--`, and memory/DT overrides are rejected.
Run the controller from an isolated source checkout under the established
shared-host execution limits, with a fresh output directory whose parent exists:

```sh
python3 -O scripts/research/launch_second_stage.py --manifest /absolute/manifest.json --out /absolute/run-01 --run-seconds 0
```

`--run-seconds 0` validates the paused state and exits. A value from `1` through
`120` permits that many seconds of observation after every gate succeeds.
QEMU uses TCG, eight CPUs, 8 GiB RAM, the explicit `-dtb` and `kernel-load-base`,
and a single UFS LUN containing the root image with `snapshot=on`. This experiment
does not use a physical disk or tablet device.

## What the paused gate checks

The controller reads the actual ROM map, compares the entire loaded Image and
initrd with their pinned input bytes, and reads the final memory-resident FDT.
For R5's zero `text_offset`, the ARM loader protects its boot stub by placing
the Image 2 MiB after the load base. The verifier checks the effective Image
extent, not just its stored file length. Its ARM64 alignment and size rules
follow the [Linux 6.12 boot protocol](https://docs.kernel.org/6.12/arch/arm64/booting.html).

[`second_stage_layout.py`](../../../scripts/research/second_stage_layout.py)
checks actual payload intervals against the independently selected RAM banks,
both DTs' static reservations, and the other resident loader ROMs. The final DT
must retain the selected board identity and unrelated properties. Only explicit
memory/chosen/PSCI/firmware-hole fixups and the known SMEM reservation addition
are accepted. Final initrd bounds and bootargs must agree with the invocation.
The configured bootloader command-line mode must make `module.sig_enforce=1`
effective; the R5 built-in fallback is recorded as overridden.

The launcher checks inputs and validation sources again before `cont` and on
exit. A failed check never continues the guest. It preserves `result.json`,
commands, QMP messages, ROM information, loaded payload copies, and serial/log
observations in the private output directory, then reaps its own QEMU child.
Exit `0` describes the simulated layout/controller result; exit `3` preserves
a detected kernel failure. Neither exit code is a boot-completion verdict.

## Native readiness and validation scope

The owner's independent Android observation still has twelve unresolved dynamic
reservations; the mainline candidate does not resolve their individual placement.
Firmware/loader ownership, DMA quiescence, and reachable native entry/recovery
also remain unresolved. Every result retains `physical_boot_verified=false`,
blocked native readiness, and zero added owner-native Linux passes.

The workflow exercises synthetic binary fixtures, corrupted inputs, and a fake
QMP process under `python3 -O`. It also includes the existing second-stage DT
derivation fixtures. Public CI cannot reproduce the private payload qualification
or claim a new board execution from these tests.

## Actual experiment: retained QEMU 23e84312

The first host attempt used Linux source `ea40eb660376f043bbf06ace795cce243610b4aa`
and the separately qualified QEMU `23e84312f14cfe6f9b6033b83b026cf5bbf7e4cc`
binary (SHA-256 `30e20c1befb5dc546a4d9ef060e0e8050ad592496386198e0433a0cad837541d`).
The [unmodified result](evidence/r5-second-stage-layout/attempt-01/result.json)
records successful qualification of 106 kernel-bundle files, including 84 modules,
and complete identity checks on the completed root and launch inputs.

| Loaded payload | Actual start | Stored bytes |
| --- | --- | ---: |
| Image | `0xa0200000` | 41,091,080 |
| initrd | `0xa8000000` | 32,535,823 |
| final DTB | `0xaa000000` | 273,786 |

The Image's effective memory extent is 42,729,472 bytes. Independently rehashed
copies of the complete loaded Image and initrd match the frozen source files.
The [ROM map](evidence/r5-second-stage-layout/attempt-01/roms.txt) and
[forensic diagnosis](evidence/r5-second-stage-layout/attempt-01/fdt-diagnosis.json)
preserve those observations.

The strict gate failed before `cont`: QEMU's final FDT had nonzero property
padding at offsets 367, 511 and 2854. A separately labelled forensic parse
also showed that the loader had removed all nine `/psci` power-domain children,
including their phandles. The original candidate had eight CPU domains and
one cluster domain. The QEMU child exited normally after the controller's quit,
all original input identities remained unchanged, and no guest CPU was resumed.

The producer repairs must zero property-alignment padding and preserve the
original PSCI topology while updating QEMU's known ABI fields. The stricter
consumer remains unchanged on padding; its updated topology contract requires
every original extra property and descendant to survive byte-for-byte.
The padding issue is independently described by the upstream
[libfdt fix](https://qemu.googlesource.com/dtc/+/ce51dcbd84209527eb82a64a3ce831bcac82d166).
A fixed-producer board execution result is still pending.
