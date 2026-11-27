# R7 second-stage input qualification

The `r7-rpmh-v1` input path binds one completed
`6.12.114-tb371fc-research7-rpmh-clock` build and its independently constructed
Fedora system to the existing paused TB371FC board-model gate. The original
R5 input verifier, fixed payload identities, default command and result fields
remain unchanged. Selecting R7 requires both a separate manifest and an
explicit SHA256 pin for a reviewed R7 receipt contract.

No actual R7 build, root image or VM success is asserted by this source or its
synthetic tests. The real Image, new public certificate, signed modules,
initramfs and root hashes must come from completed retained jobs. The
contract is deliberately not populated with invented or previous-release
payload identities.

## Root qualification phases

The closed contract names exactly one root phase:

| Phase | Required root identity | Recorded acceptance |
| --- | --- | --- |
| `constructed-unbooted-prelabel-v1` | The exact 4 GiB root in `r7-construction-result.json` | Construction and offline archive/module checks only; no label boot or production VM claim |
| `generic-vm-verified-v1` | The exact 4 GiB `final_rootfs` in `r7-generic-vm-result.json` | Both inherited generic `virt` maintenance-label and production-verify phases, including their separately retained acceptance reparse |

The second phase explicitly binds the constructor's original root hash to
the label boot's before/after hashes, then to the production boot's
before/after hashes and the final launched image. Both phases must have
exited successfully with their driver and all owned descendants reaped.
The original construction receipt is not rewritten, and a post-VM image
cannot pass the pre-label phase by replacing its old hash.

For a production board experiment, use the completed generic-VM phase when
available. The pre-label phase is a separately identified construction
diagnostic, not evidence that the SELinux-labelled system has booted.

The generic receipt must bind wrapper source
`5deaaa2619979af919b8047ee0410fe40f96257267c7acb5c2d2187626c27750`
and unchanged inherited driver
`4d1f59691bb4faccdcdbd791ae2120a89e56f7712fd63270f0a2204662842736`.
It uses the same constructor
`f556256e8764b7c6060b05ffe5e7350046055d87e1393ed2acd9ef4c00126042`
as the construction evidence. The input verifier checks the retained
results, exact generic-QEMU argv, log identities, extracted same-boot guest
result and independently reparsed gates. It does not execute another generic
VM or result extractor during board preflight.

## Public input bundles

Create a new ordinary directory containing exactly 102 kernel files:

- Eleven files below `artifacts/`: `Image`, `board.dtb`, `kernel.config`,
  `kernel.release`, `Module.symvers`, `System.map`, `signing-cert.der`,
  `kernel.btf`, `modules.builtin`, `modules.builtin.modinfo`, `modules.order`.
- Exactly the 84 `.ko` paths named in the qualified build receipt, below
  `modules/lib/modules/6.12.114-tb371fc-research7-rpmh-clock/kernel/`.
- The three installed Kbuild metadata files below that release directory.
- `build-result.json`, `module-signatures.json`, `module-abi.json` and
  `source-inventory.json` at the bundle root.

Preserve module and metadata modes from `r7-module-contract.json`. Extra
files, links and special files fail the closed inventory. The bundle does
not include the build source tree, `out/`, `vmlinux`, private key or the
Kbuild directory symlink. Every permitted file is rehashed, including the
source inventory and both recorded offline qualification receipts.

The separate construction evidence directory contains these eight files:

```text
r7-construction-result.json
r7-module-contract.json
r7-runtime-stage.json
runtime.json
system-profile.json
root-module-report.json
r7-initrd-modules.json
recipe/derivation.json
```

For `generic-vm-verified-v1`, the same evidence directory additionally
contains exactly these thirteen files:

```text
r7-generic-vm-result.json
vm-label-01/result.json
vm-label-01/command.json
vm-label-01/serial.log
vm-verify-01/result.json
vm-verify-01/command.json
vm-verify-01/serial.log
vm-verify-01/guest-result.json
r7-generic-vm/label.driver.log
r7-generic-vm/verify.driver.log
r7-generic-vm/reparse-label/inspection.json
r7-generic-vm/reparse-verify/inspection.json
r7-generic-vm/reparse-verify/guest-result.json
```

The large root image and launch initramfs can remain outside the evidence
directory. The operator manifest supplies their actual canonical absolute
paths. Identical copied payloads are accepted by their complete identity;
container paths in historical receipts do not need to be the current host
paths. The actual root image is streamed and hashed in full, not sampled or
loaded into memory. Before `cont` and after observation, stable ordinary-file
fingerprints and the complete bundle inventories must still match.

## Contract and manifest

Each identity object below has exactly `bytes` and lowercase `sha256` fields.
The versioned contract has exactly these top-level fields:

| Field | Required value |
| --- | --- |
| `schema` | `tb371fc-r7-second-stage-input-contract-v1` |
| `input_profile` | `r7-rpmh-v1` |
| `release` | `6.12.114-tb371fc-research7-rpmh-clock` |
| `rootfs_phase` | One of the two explicit phases above |
| `build_result` | Identity of the actual completed R7 build receipt |
| `construction_files` | Map of the eight exact relative paths to identities |
| `launch_files` | Exact keys `kernel`, `dtb`, `initrd`, `config`, `certificate`, `rootfs`, each mapped to an identity |
| `dtb_derivation` | `native-memory-reg-only-v1` |
| `generic_vm_files` | Present only for `generic-vm-verified-v1`; map of the thirteen exact relative paths to identities |

The caller supplies the contract's SHA256 separately on the command line.
A hash stored only inside the manifest cannot authorize that manifest's
own replacement contract. Review and pin the completed contract before
using it; no ready-to-run contract is included in this source change.

The R7 operator manifest has exactly these fields:

| Field | Required value |
| --- | --- |
| `schema_version` | Integer `1` |
| `input_profile` | `r7-rpmh-v1` |
| `release` | The exact R7 release above |
| `kernel_bundle` | Canonical absolute path of the 102-file public kernel bundle |
| `construction_bundle` | Canonical absolute path of the 8-file or 21-file evidence bundle |
| `kernel_load_base` | The existing bounded, 2 MiB-aligned simulated load-base selection |
| `bootargs` | Explicit kernel command line satisfying the R7 security/root arguments below |
| `files` | Exact keys `qemu`, `kernel`, `dtb`, `initrd`, `config`, `certificate`, `rootfs`, each with exactly `path`, `bytes`, `sha256` |

The six payload identities must equal the independently pinned contract.
The QEMU executable remains independently selected and pinned in the
manifest, as in the existing R5 experiment. QEMU artifact qualification
and host admission remain separate mandatory runtime preparation.

The command line must contain each of these tokens exactly once:

```text
rdinit=/init.tmpfs
rd.tb371fc.early-selinux=1
rd.tb371fc.tmpfs-root=1
enforcing=1
module.sig_enforce=1
root=LABEL=tb371fc-r7-f45
tb371fc.early_pgtable=memblock
```

The allocator option selects the upstream memblock path for the explicit
board-model experiment. The native-compatible default embedded allocator
remains unchanged, and this option is not added to the generic VM command.
The observed reason for the mode is recorded in
[`early-page-table-pool-attempt04.md`](early-page-table-pool-attempt04.md).

Aliases that conflict after hyphen/underscore normalization are rejected.
The R7 path also rejects `lsm=`, `security=` and `rodata=` overrides, along with the
existing init, SELinux, memory, firmware and FDT override exclusions. This
does not change the frozen R5 parser.

## Immutable build and DT relationships

The verifier requires the reviewed R7 builder
`509aa9cb8f3b43292ae6708622066bec1d22eb92330d6dfb090a286534c2b5d6`,
the exact R7 config (223386 bytes,
`84747cefce945deaf0134e52c3b1a8a2bf771f3082853d6903be59ab6d5a92a4`),
the same 84 relative module paths as the frozen R6/R7 build, and identical
module bytes in the build, signature and ABI receipts. The new public
certificate must match the offline signer evidence and occur in the
launched Image. The source records do not reuse the old signing certificate.
No old R5 Image size is assumed; the actual R7 ARM64 header and loaded bytes
go through the existing layout validator.

The native R7 DTB remains 126877 bytes with SHA256
`af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730`.
The declared RAM candidate is 126893 bytes with SHA256
`7092d992582a2f49b65e8eb1a4209fede3b41ccbbacb3abc28d29b649b33423c`.
The verifier independently compares their complete parsed trees and
reservation tables using the unchanged `check_delta` helper. The only
permitted property change is `/memory@80000000/reg`, from the zero-sized
placeholder at `0x80000000` to `(0x80000000, 0x3bb00000)` and
`(0xc0000000, 0x1c0000000)`. All other properties, node inventories, PSCI
topology and header reservations remain identical.

This input relation is separate from QEMU's final loaded-FDT gate. The
full final FDT is still captured from paused guest memory and passed
unchanged to the existing layout validator. Selecting
`--firmware-profile linux-reference-v1` adds its already-reviewed explicit
synthetic CommandDB, AOP and SMEM measurements; it does not alter input
qualification or grant native firmware provenance.

## Invocation and evidence scope

After staging the exact public bundles, `prepare_r7_second_stage_inputs.py`
can materialize the **post-generic-VM** contract and manifest. Its path plan
has exactly `kernel_bundle`, `construction_bundle`, `kernel_load_base`,
`bootargs` and `files`. The first four have the meanings in the manifest
table above; `files` has the seven launch-role keys with canonical absolute
path strings as values. A plan contains paths and placement choices, not
guessed output hashes.

Supply three independent pins from the actual retained successful jobs:

```bash
python3 -B -O scripts/research/prepare_r7_second_stage_inputs.py \
  --plan "$R7_PATH_PLAN" \
  --build-result-sha256 "$ACTUAL_R7_BUILD_RESULT_SHA256" \
  --construction-result-sha256 "$ACTUAL_R7_CONSTRUCTION_RESULT_SHA256" \
  --generic-vm-result-sha256 "$ACTUAL_R7_GENERIC_VM_RESULT_SHA256" \
  --out "$NEW_PREPARATION_DIRECTORY"
```

The materializer derives the Image/config/certificate identities from the
build receipt, the production initrd from the construction receipt and the
final root identity from the generic-VM receipt. It rehashes all evidence
files and QEMU, creates a new contract and manifest exclusively, and invokes
the complete R7 input qualification. That qualification streams the entire
root once. Preparation starts no QEMU and modifies no input bundle. Its
`qualification.json` must say `status="verified"`; an unsuccessful
preparation retains failed drafts with `status="failed"` and cannot
auto-activate them. Existing output directories are rejected.

The successful output gives `input-contract.json`, `input-manifest.json`
and `qualification.json`. The launcher requires the separately reviewed
SHA256 of that actual contract even after preparation. No construction or
VM receipt is substituted, rewritten or inferred from a log marker.

After the actual completed receipts, bundles and contract have been
reviewed, invoke through the parent's existing admitted foreground wrapper:

```bash
python3 -B -O scripts/research/launch_second_stage.py \
  --input-profile r7-rpmh-v1 \
  --input-contract "$R7_INPUT_CONTRACT" \
  --input-contract-sha256 "$R7_INPUT_CONTRACT_SHA256" \
  --manifest "$R7_INPUT_MANIFEST" \
  --firmware-profile linux-reference-v1 \
  --out "$NEW_OWNED_ATTEMPT" \
  --run-seconds 45
```

Omitting `--input-profile` selects the unchanged frozen R5 path. R7 contract
arguments are rejected with the R5 selection. The firmware profile remains
an independent fixed choice and defaults to `none`.

`generic_vm_recorded_acceptance` reports only a qualified historical generic
VM phase. `generic_vm_acceptance_reexecuted`, module-signature command
reexecution, current board-model runtime signature enforcement, current
userspace acceptance and physical boot remain false. Every actual board
attempt still needs its own paused gate, bounded observation and retained
trace. The synthetic regression fixtures verify rejection behavior and byte
relationships; they do not compile R7, validate cryptographic signatures or
execute a guest.
