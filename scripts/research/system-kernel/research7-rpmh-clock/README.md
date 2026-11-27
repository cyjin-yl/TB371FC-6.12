# R7 RPMh clock and explicit model page-table candidate

Status: the first retained R7 construction stopped before compilation when
`clang --version` exceeded its former 10-second limit. Build 02 passed the
revised tool probes, complete source comparison, source copy and MMU patch,
then reached the 120-second outer limit of the actual-source C regression
without a diagnostic line. Its terminal and cleanup receipts are retained in
the [build 02 report](../../../../docs/research/2026-11-27/r7-build02-regression-timeout.md).
Each tool probe retains its 120-second limit and 64 KiB diagnostic cap.
The C regression now has flushed step diagnostics and a separate coherent
1200-second outer limit. No completed R7 kernel or boot pass is asserted here. The actual R5 board
observation and early mapping panic are recorded in
[`early-page-table-pool-attempt04.md`](../../../../docs/research/2026-11-27/early-page-table-pool-attempt04.md).

## Configuration and source lineage

`system.config` is a new profile fragment. Apply it to the complete qualified
R6 config, not to `defconfig`. It changes exactly two symbols:

- `CONFIG_LOCALVERSION`: `-tb371fc-research6-tianma-off` to
  `-tb371fc-research7-rpmh-clock`.
- `CONFIG_QCOM_CLK_RPMH`: `n` to `y`.

Linux 6.12.114's RPMh clock option depends on `CONFIG_QCOM_RPMH`, which is
already built in. `CONFIG_COMMON_CLK_QCOM` and `CONFIG_QCOM_COMMAND_DB` are also
already built in. Enabling the clock provider therefore has no intended module
selection or security-policy change.

The source baseline is the completed R6 candidate at
`/work/tianma-r6-build-ec332-01/linux`. It already contains the qualified Tianma
OFF-sequence repair. Copy that source into a new work directory and use a new
Kbuild output directory. Do not copy the R6 output, modules or signing key.
The new candidate applies the reviewed
`0023-arm64-tb371fc-explicit-memblock-page-tables.patch` only to
`arch/arm64/mm/mmu.c`. Complete source inventories bind both the unchanged
R6 baseline and the patched candidate, including file modes. No other new
kernel source change is accepted.

The frozen R5 recipe at
`scripts/research/system-kernel/research5-services/recipe-v1/` and the executed
R6 builder `scripts/research/display/build_tianma_candidate.py` are retained
inputs. The existing Tianma CI checks their recorded source identities. This
proposal adds a new profile and does not change either executed recipe.

| Input or expectation | SHA256 |
| --- | --- |
| R6 complete config, 223397 bytes | `5a8ec0c9e1c8eccb10fd12f25a05268b0d739f8bc77d9536a9e664f24bae0e72` |
| R6 patched panel source, 76971 bytes | `9bc1c7fb376af05823bc933bbd730f0dcdc45807da383dc47e266509f75ed149` |
| Unchanged native board DTB, 126877 bytes | `af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730` |
| Expected R7 resolved config, 223386 bytes | `84747cefce945deaf0134e52c3b1a8a2bf771f3082853d6903be59ab6d5a92a4` |

The expected R7 config identity is an offline derivation from the published R6
config. It is an expectation for `olddefconfig`, not a completed Kconfig result.
Reject any other resolved configuration change.

## Guarded construction

`build_rpmh_candidate.py` implements the recipe below. Run it inside the
established `tb371fc-build-ssd-20261123` container through the unchanged host
admission guard, with a fresh work directory and `MAKEFLAGS=-j2`:

```bash
python3 -B "$R7_REPO/scripts/research/system-kernel/research7-rpmh-clock/build_rpmh_candidate.py" \
  --repo "$R7_REPO" --r5 /work/research5-services \
  --baseline /work/tianma-r6-build-ec332-01 \
  --work /work/r7-rpmh-clock-406f-03
```

The helper rechecks the published R6 build and signature receipts and every
retained payload; compares the complete R6 source inventory with R5, permitting
only the byte-pinned Tianma repair. It copies that source into a fresh
output, applies the byte-pinned MMU patch, and requires exactly that one
additional source delta before creating the new module artifacts. It requires the exact toolchain and full
resolved configuration, then builds and installs all 84 modules with a new
signing certificate. Actual command output appears in the caller's pane and
per-command logs. Signal cancellation stops and reaps the owned command group;
the outer host driver must retain admission until container ownership is
resolved. A `build-result.json` terminal receipt preserves success or failure.

After the existing cryptographic signature verifier,
`verify_module_abi.py` checks the exact module path set, release/profile
vermagic, each recorded imported symbol CRC and every undefined strong import,
retained BTF sections with bounded nonoverlapping header ranges, and absence
of DWARF debug sections. This does not semantically validate every BTF type or
load any module. Twenty-five focused positive and negative cases run with:

```bash
python3 -B -O "$R7_REPO/scripts/research/system-kernel/research7-rpmh-clock/test_rpmh_candidate.py"
```

The ABI verifier was also replayed read-only against all 84 retained R6 modules:
4,308 versioned imports matched the retained `Module.symvers`. This is a check
of the verifier against existing R6 artifacts; R7 still needs its own completed
build and qualification receipts.

## Explicit board-model allocator

The retained board workaround uses 256 embedded page-table pages and remains
unchanged by default. With the current 4 KiB granule and full read-only-data
protection, the simulated RAM map requires thousands of PTE pages. R7 adds
`tb371fc.early_pgtable=memblock` to select the existing upstream memblock
allocation path for this explicit model experiment. The option is parsed
before `paging_init`; missing or unknown values are rejected by its parser.

The `r7-rpmh-v1` launcher contract requires exactly one canonical option and
rejects duplicate, aliased, or conflicting tokens before guest execution.
The generic `virt` control keeps its original command line and follows the
existing non-TB371FC allocator branch. This change does not enlarge the
embedded pool or claim that memblock allocation is qualified for a physical
vendor-kernel handoff. Native-default behavior and native acceptance remain
unverified.

The executable recipe is `build_rpmh_candidate.py`; the invocation above is
the supported entry. Its receipts preserve the exact source patch, original
and patched MMU identities, complete candidate source inventory, command
arguments and bounded toolchain probes. It runs the MMU regression against
the actual copied source before Kbuild. The harness permits 300 seconds for
host compilation and 30 seconds for each of its 16 C cases (780 seconds in
total); the 1200-second enclosing command allows additional startup and
setup time. The fixture-only patch command remains bounded at 30 seconds.
Each validation, compilation and case step emits flushed progress with
elapsed time and useful bounded diagnostics on failure. The compiled C,
source hashes and assertions are unchanged. The enclosing command still
uses the existing owned-process cleanup, and the original 10800-second
builder and 11000-second host limits are unchanged. It then derives the full config,
builds Image and all modules, builds the unchanged native DTB, installs with
`INSTALL_MOD_STRIP=1`, and performs the signature and ABI checks below.
The retained R5 and R6 recipes are never edited or replayed in place.

## Required resulting evidence

Require release `6.12.114-tb371fc-research7-rpmh-clock`; the expected complete
config; the same native DTB; and exactly the R6 set of 84 module-relative paths
under the new release. Rebuild all modules. The existing signature-verifier
command checks AArch64 ELF, module count and CMS signatures using the new public
certificate. The complementary ABI verifier then checks vermagic, imported
symbol CRCs, retained BTF sections and stripped DWARF data. These remain offline
checks; a later runtime must establish actual module loading and enforcement.
`INSTALL_MOD_STRIP=1` performs debug stripping before Kbuild signs the installed
modules. Check that the generated certificate differs from R5 and R6 and that
retained source/config/certificate identities are unchanged afterward.

Preserve `CONFIG_MODULE_SIG_ALL=y`, SHA-512, the default newly generated
`certs/signing_key.pem`, `CONFIG_MODVERSIONS=y`, SELinux, and the remaining
security settings. The inherited `CONFIG_MODULE_SIG_FORCE=n` still requires
exactly one effective `module.sig_enforce=1` and later runtime readback; a
successful build/signature check does not establish runtime enforcement.

The native UART node remains disabled, and the native DT/pinmux is unchanged.
This profile does not provide firmware-owned Command DB, SMEM or AOSS state.
The simulator's default-off RPMh profile remains a separate observed model
boundary; enabling this driver alone cannot establish a working RPMh handoff.

R7 artifacts need their own kernel/module/root/initramfs qualification and
release/identity contract. The existing R5 launcher pins R5 inputs and must
continue rejecting an R7 substitution until that separate contract is reviewed.

## Sources

- Linux repository main inspected at `50531b5cfe959541bc6c4b89bedbbbe85318e5d7`.
- `docs/research/2026-11-26/tianma-r6-build.md` and its retained build/config/
  signature receipts.
- `scripts/research/display/build_tianma_candidate.py`: actual R6 build steps,
  new-key policy, exact config guard and 84-module installation.
- `scripts/research/system-kernel/research5-services/recipe-v1/build_system.py`:
  the existing `merge_config.sh -m` plus `olddefconfig` configuration workflow.
- Upstream Linux `v6.12.114`, `drivers/clk/qcom/Kconfig`, `QCOM_CLK_RPMH`.

Use a new work directory and an exact reviewed source revision for every
construction attempt. Preserve failed terminal receipts and inspect actual
completion and cleanup before starting a successor.
