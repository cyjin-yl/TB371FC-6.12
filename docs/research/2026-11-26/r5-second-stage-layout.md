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

After a positive-duration observation reaches its deadline, a live model is
stopped and independently confirmed paused before an optional diagnostic
snapshot. It records CPU 0/4 registers, all CPU identities, UART clock/reset/TX
state, UFS link state and block statistics. The snapshot has a 12-second total
budget, short per-command timeouts and a bounded retained size. Missing getters
remain explicit unavailable observations; they do not supply or erase a boot
verdict. Failed pre-cont gates and paused-only runs never enter this phase.

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

## Fixed producer and independently qualified replacement

[QEMU PR #50](https://github.com/cyjin-yl/qemu-tb371fc/pull/50) was merged as
`1e84aa1eeeb6cf58a1615286cbec150ed9a0830f` after both jobs in
[run 45889294881](https://github.com/cyjin-yl/qemu-tb371fc/actions/runs/45889294881)
passed. Its merge tree equals the tested producer-fix tree.

The separate integration `d46f660a464e850b94ed483a5f823a11196dfd49` retains the
previously qualified board source and all 115 component/Linux gates. Both jobs
in its exact [push run 45889546070](https://github.com/cyjin-yl/qemu-tb371fc/actions/runs/45889546070)
passed, including the 17 new actual-function producer fixtures. The independent
[artifact qualification summary](evidence/r5-second-stage-layout/qemu-d46f660a-qualification.json)
binds the source/tree, nine actual source files, required job steps, ZIP digest,
all 115 ordered cases, all suite inventory hashes, producer fixture contents,
DSU evidence and the extra UFS continuation receipts to the deployed executable.
The full private audit receipt's identity is retained in that summary.

| Replacement artifact | Identity |
| --- | --- |
| Core artifact | `15152197800`, 87,987,387 bytes |
| ZIP SHA256 | `71ca01177f849d90092d64fe472719643de8bb08996a75566f7bd26281d4aef8` |
| QEMU executable | 64,040,880 bytes |
| QEMU SHA256 | `e97b5500bf534c51ac9e7e91bdd1df403dea44b822438a21311f731b9b43efcc` |
| Full audit receipt SHA256 | `7a33168c3925c825550c09216e06a66da8bb072b8f5505d7ed9ed0e749545ef2` |

The audit did not execute a guest. Architecture-job success was checked against
the exact GitHub API records; its separate architecture ZIP was not independently
audited. The selected executable is from the board/core ZIP.

## Repeated board observation: execution checkpoint

The repeated experiment is prepared against Linux source
`4b1700e1ab814696dbbe73e852bd71525a9f6f08`. Its public
[CI run 45891384595](https://github.com/cyjin-yl/TB371FC-6.12/actions/runs/45891384595)
passed all 79 second-stage fixtures. The original R5 manifest is preserved
except for the independently qualified QEMU entry; its bootargs, kernel,
DTB, initrd, root image, configuration and certificate are unchanged.

The first two execution-admission controllers expired without starting their
worker, cloning `source2`, creating `attempt-02`, or executing a guest. Their
exclusive markers and logs remain preserved. A subsequent isolated controller
uses the original five-slot admission tool's nonblocking form, with a bounded
wait and 15-second polling. It retries only an exit-75 non-admission with no
worker/source/output present; a started worker is never replayed. No shared
capacity setting, lock inode or other owner's process is modified.

At this checkpoint, a fixed-producer R5 board result is still pending resource
admission. Qualified CI and an audit receipt do not supply that missing result.

Source/config inspection also found that both R5 and R6 omit the RPMh clock
driver despite their native DT's GCC/UFS clock references. The isolated
[R7 profile proposal in PR #22](https://github.com/cyjin-yl/TB371FC-6.12/pull/22)
enables `CONFIG_QCOM_CLK_RPMH` over the complete qualified R6 config, while
preserving the native DT and existing module selections. It has no R7 build,
root/initrd qualification or runtime result yet.
