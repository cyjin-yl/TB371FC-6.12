# R5 boot-candidate integrity and composition

This adds executable checks for the next native-boot candidate. The existing
[R5 build](research5-services-kernel.md) supplies an Image, joint DT and 84
signed modules. It does not yet supply a qualified native root loader, final
root filesystem, firmware selection, entry or reachable recovery procedure.
The [candidate](boot-candidate-r5.json) records those remaining requirements
without inventing absent payloads or changing the hardware acceptance ledger.

## Three independent results

| Result | What is actually checked | What it cannot establish |
| --- | --- | --- |
| Evidence consistency | Frozen published inputs, build/report/transfer links, all 106 file identities across source-before/source-after/destination records, all 84 module mappings | That the remote files still exist or remain unchanged today |
| Current kernel payload | Every supplied file's bytes, length and mode, exact file set, raw Image header, real DT root compatible, release, required config and embedded public certificate | That the bootloader will load it, the running kernel accepts a module, or any peripheral works |
| Optional root-module tree | Exact R5 module/Kbuild bytes, complete text dependency graph, presence and identities of depmod indexes | Binary index semantics, which depmod execution produced them, root-loader handoff or runtime success |

`native_boot_readiness` remains `blocked`. No code path in this version upgrades
that status from file presence, a historical `true` field or a generic VM pass.
`native_boot_attempted=false` and `owner_native_linux_passes_added=0` make the
execution boundary explicit.

## Reproduce the candidate

Run at the repository root with Python 3.10 or newer on Linux. The tools use
only the standard library and do not require root for readable input files.

```bash
python3 scripts/research/derive_boot_candidate.py \
  --check docs/research/2026-11-23/boot-candidate-r5.json

python3 scripts/research/qualify_boot_bundle.py --gate evidence
```

The [generator](../../../scripts/research/derive_boot_candidate.py) binds the
original evidence bytes by exact size and SHA-256. It cross-checks complete
inventories and identities rather than accepting recorded success booleans.
Its output is deterministic. `--output PATH` creates a new file exclusively;
`--check PATH` compares an existing candidate with that derivation. A changed
build or a new candidate needs a reviewed new contract, not edits to the
historical evidence or changing `blocked` to `passed` by hand.

The candidate keeps actual per-file modes: 18 files are `0644`, 88 are `0600`.
It does not normalize those modes or copy a private signing key.

## Check the actual transferred R5 files

The historical destination is the **`tb371fc-build-20261123` container inside
CT102**, with this path inside that container:

```bash
python3 scripts/research/qualify_boot_bundle.py \
  --kernel-root /work/research5-services-kernel-inputs-v1 \
  --gate kernel \
  --output /work/r5-kernel-qualification-new.json
```

Use a new report filename. A report cannot be written inside `--kernel-root`
or `--rootfs-root`, including ordinary symlink and bind-mount aliases; doing
so would invalidate the exact input set just inspected. No source file is
rewritten, no module is loaded and no input program is executed. Reads reject
symlink/special-file members, bound sizes and compare file/directory identities
before and after the whole inspection. The output is an observation of those
bytes during that run, not a lock against future changes by another writer.

The exact file set includes 84 `.ko` files and the installed
`modules.order`, `modules.builtin` and `modules.builtin.modinfo`. These three
Kbuild metadata files are valid inputs. It deliberately excludes old
`modules.dep*`, `modules.alias*` and other generated depmod indexes.

The real destination also retains `bundle.json` and `transfer.json` beside the
106 payload files. These two optional evidence sidecars have their own frozen
length/hash bindings and a separate report count. A present but changed sidecar
fails; arbitrary other JSON files are not allowed. Their observed modes are
recorded, while the payload mode contract remains exact. The first real run
exposed these sidecars as unexpected files; its failed receipt is retained.

The original inspector already executed CMS verification and imported-symbol
CRC checks. Matching every current module byte to that frozen qualification
reuses that evidence. The new report explicitly sets
`module_signatures_reexecuted=false` and
`module_symbol_crc_commands_reexecuted=false`; it does not pretend to execute
those commands again. A current-byte mismatch fails before reusing the result.

R5 deliberately inherits `CONFIG_MODULE_SIG_FORCE=n` from R4. It builds and
signs modules, but the existing enforcing VM contract uses
`module.sig_enforce=1` and verifies the live
`/sys/module/module/parameters/sig_enforce` value. The initial checker incorrectly
required compiled FORCE=y; its second real-payload run exposed that assumption.
The corrected checker records the actual compiled setting and the required
runtime argument separately, with `runtime_verified=false`. It does not alter
the kernel or substitute a permissive runtime result for enforcement.

| Selected CLI gate | Exit 0 means | Exit 2 means |
| --- | --- | --- |
| `--gate evidence` | The frozen evidence and candidate agree; any supplied payload also passed its supported checks | Not used for this gate |
| `--gate kernel` | The current complete 106-file R5 kernel bundle passed | No kernel payload was supplied |
| `--gate native` (default) | Not implemented by this version | Physical boot prerequisites remain open |

Invalid evidence, mismatched supplied files, failed supplied root-module checks
or an invalid output destination return 1. An absent required rootfs index is
reported as blocked by the helper but still fails an explicitly requested
inspection. A zero evidence/kernel exit code never means native boot readiness.

## Image, DT and planned memory layout

The actual R5 Image stores **41,091,080 bytes**, but its header reserves an
effective **42,729,472-byte** region. Its `text_offset` is **0**, not the
`0x80000` recorded for the owner's vendor 4.19 kernel. Memory placement must
use the effective size. The native DT root compatible must be exactly
`["lenovo,tb371fc", "qcom,sm8250"]`; a string elsewhere in a Qualcomm
first-stage DT cannot satisfy that requirement.

[boot_formats.py](../../../scripts/research/boot_formats.py) implements the
current raw Image and v17/v16-compatible DTB profile. It checks complete section
bounds, alignment, reservation termination, root/tree structure, string lists,
duplicate nodes/properties and the final structure token. This is an explicitly
limited profile, not a claim to accept every past or future DTB format.

Its separate `validate_memory_layout()` API checks a supplied **plan**:
Image base alignment after subtracting `text_offset`, DTB alignment/size,
effective extents, overlapping payload/reserved ranges, RAM coverage and the
kernel/initramfs common address window. It returns `planned_layout_valid`,
never `physical_boot_verified`. No real TB371FC address plan has been supplied
to this new API. The DT header reservation list alone is not the complete
`/reserved-memory` and firmware exclusion map. CPU state, cache/MMU/DMA
quiescence, memory provenance and actual loader placement still require their
own evidence.

Primary references:

- [Linux 6.12 ARM64 boot protocol](https://www.kernel.org/doc/html/v6.12/arch/arm64/booting.html).
- [Devicetree flattened format](https://devicetree-specification.readthedocs.io/en/stable/flattened-format.html).
- [Linux 6.12 module signing](https://www.kernel.org/doc/html/v6.12/admin-guide/module-signing.html).

## Final-root module integration

The optional root check reads an **unpacked candidate root**, not a physical
partition or mounted Android root:

```bash
python3 scripts/research/qualify_boot_bundle.py \
  --kernel-root /work/research5-services-kernel-inputs-v1 \
  --rootfs-root /work/NEW-R5-ROOT \
  --gate kernel \
  --output /work/r5-root-module-inspection-new.json
```

[boot_rootfs.py](../../../scripts/research/boot_rootfs.py) supports ordinary
`lib` and the distribution's `lib -> usr/lib` or `lib -> /usr/lib` alias,
resolved within the supplied root. It checks the R5 module set and the three
Kbuild metadata files against their exact identities. `modules.dep` must name
every module exactly once, reference only this release's existing modules and
contain no duplicate/self/cyclic dependencies. Other installed releases may
exist but cannot satisfy the R5 graph.

Required indexes are `modules.dep`, `modules.dep.bin`, `modules.alias`,
`modules.alias.bin`, `modules.symbols`, `modules.symbols.bin`, `modules.softdep`
and `modules.builtin.bin`. `modules.builtin.alias.bin`, `modules.devname` and
`modules.weakdep` are recorded when present, allowing for kmod version
differences. Nonempty binary files are **inventoried, not semantically verified**.
The report always retains `binary_index_semantics_verified=false`,
`native_depmod_provenance_not_verified=true` and `rootfs_runtime_ready=false`.
The next assembly step must bind the real target depmod invocation, exact root
identity and generated indexes together. Filename presence does not close it.

## The next implementation uses the existing distro loader

The repository already has a real Fedora dracut/systemd root loader with
`systemd systemd-initrd rootfs-block kernel-modules selinux`. It mounts a real
ext4 root by an explicit label and performs switch-root. Its historical
research1 success and later research4 failures are retained in the linked
[Fedora integration records](fedora-system-integration.md). Current v9 scripts
remain bound to R4; they are not silently rewritten by this contribution.

The next independent R5 profile should reuse that distribution implementation,
install these exact modules in a fresh root, generate and record target depmod
indexes, build a new initramfs, and demonstrate the exact root/release/PID 1 in
generic ARM64 QEMU first. The VM label is not the owner's microSD partition
selection. NixOS must instead enter its actual built stage-2 init with the store
closure/registration intact; Nura keeps its OpenRC service contract.

The existing 69-file canonical firmware tree is available, but its original
metadata binds research2-display. It must be rebound and verified against the
R5 DT/config and final root/initramfs. WLAN board data, BT ROM selection and
other device-specific loading conditions stay open. Compiled driver support
for unrelated adapters does not add those adapters' firmware to this board's
requirements.

## Regression scope

```bash
python3 -m unittest discover -s scripts/research -p 'test_boot_*.py' -v
```

Tests use frozen public metadata or isolated synthetic payloads. They exercise
same-size module corruption, old depmod contamination, malformed/wrong-board
DTs, Image effective-tail overlap, missing/cyclic dependency entries, changed
input snapshots, root-path aliases, unsafe outputs, JSON type substitution and
hand-edited completion claims. Synthetic payloads are never described as real
signed modules, a real rootfs boot or a physical-tablet result. The dedicated
GitHub workflow runs these offline checks without private firmware or devices.
