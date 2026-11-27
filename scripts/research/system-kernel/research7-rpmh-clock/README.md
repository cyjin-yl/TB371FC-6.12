# R7 RPMh clock candidate proposal

Status: guarded construction helper and offline qualification are staged;
no R7 kernel build or boot result is recorded here.
The unchanged R5 board observation is tracked separately in Linux PR #21.

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
  --work /work/r7-rpmh-clock-406f-01
```

The helper rechecks the published R6 build and signature receipts and every
retained payload; compares the complete R6 source inventory with R5, permitting
only the byte-pinned Tianma repair; and copies only that source into fresh
output and module directories. It requires the exact toolchain and full
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
load any module. Twenty focused positive and negative cases run with:

```bash
python3 -B -O "$R7_REPO/scripts/research/system-kernel/research7-rpmh-clock/test_rpmh_candidate.py"
```

The ABI verifier was also replayed read-only against all 84 retained R6 modules:
4,308 versioned imports matched the retained `Module.symvers`. This is a check
of the verifier against existing R6 artifacts; R7 still needs its own completed
build and qualification receipts.

## Exact underlying build recipe

The following is the inside-container recipe. The owner must first refresh
active-job/worktree ownership, retain the original admission wrapper, and
select fresh source and output paths. It uses the same two-job build envelope
and toolchain arguments as the accepted R6 build: LLVM/Clang and LLD 19.1.7,
with pahole 1.30. Keep all blocks in the same admitted Bash environment and
retain that toolchain throughout. The source checkout containing this profile
supplies `R7_REPO`. The guarded helper above performs these steps and the
input/output checks around them.

Set `R7_BASE=/work/tianma-r6-build-ec332-01`,
`R7_WORK=/work/r7-rpmh-clock-406f-01`, and `MAKEFLAGS=-j2` in that environment.
Before creating `R7_WORK`, verify the input identities above, the R6 build and
84-module signature receipts, and that the copied source contains no generated
Kbuild output, signing keys, absolute symlinks or symlinks escaping its root.
`R7_WORK` must not exist.

```bash
set -euo pipefail
: "${R7_REPO:?set the reviewed source checkout}"
: "${R7_BASE:?set the qualified R6 baseline}"
: "${R7_WORK:?set the fresh R7 work directory}"
test "${MAKEFLAGS-}" = '-j2'
python3 -B - <<'PY_R7_TOOLCHAIN'
import subprocess
expected = {
    "clang": "Debian clang version 19.1.7 (3+b1)",
    "ld.lld": "Debian LLD 19.1.7 (compatible with GNU linkers)",
    "pahole": "v1.30",
}
for tool, version in expected.items():
    actual = subprocess.check_output(
        [tool, "--version"], text=True, timeout=10).splitlines()[0]
    if actual != version:
        raise SystemExit(f"R6 toolchain differs: {tool}: {actual}")
PY_R7_TOOLCHAIN

mkdir -m 700 "$R7_WORK"
mkdir "$R7_WORK/out"
cp -a --reflink=auto "$R7_BASE/linux" "$R7_WORK/linux"
cp "$R7_BASE/artifacts/kernel.config" "$R7_WORK/out/base.config"

python3 -O "$R7_REPO/scripts/research/display/test_tianma_off.py" \
  --repo "$R7_REPO" \
  --drm-panel-source "$R7_WORK/linux/drivers/gpu/drm/drm_panel.c"

KCONFIG_CONFIG="$R7_WORK/out/.config" \
  bash "$R7_WORK/linux/scripts/kconfig/merge_config.sh" -m \
  -O "$R7_WORK/out" "$R7_WORK/out/base.config" \
  "$R7_REPO/scripts/research/system-kernel/research7-rpmh-clock/system.config"

make -C "$R7_WORK/linux" O="$R7_WORK/out" KCONFIG_CONFIG=.config \
  ARCH=arm64 LLVM=1 \
  'CC=clang --sysroot=/work/research5-services/target-sysroot' olddefconfig
```

The merge sets `KCONFIG_CONFIG` explicitly because an ambient value overrides
`merge_config.sh -O` when selecting its output file.

At this boundary, require the entire resulting `.config` to match the expected
R7 identity above. Verify the copied panel source identity again. Then use the
same `make` prefix for these existing targets, recording each argv, log, exit
code and input identity separately:

```bash
set -euo pipefail
make -C "$R7_WORK/linux" O="$R7_WORK/out" KCONFIG_CONFIG=.config \
  ARCH=arm64 LLVM=1 \
  'CC=clang --sysroot=/work/research5-services/target-sysroot' Image modules

make -C "$R7_WORK/linux" O="$R7_WORK/out" KCONFIG_CONFIG=.config \
  ARCH=arm64 LLVM=1 \
  'CC=clang --sysroot=/work/research5-services/target-sysroot' \
  qcom/sm8250-lenovo-tb371fc-display-input-test-6.12.dtb

make -C "$R7_WORK/linux" O="$R7_WORK/out" KCONFIG_CONFIG=.config \
  ARCH=arm64 LLVM=1 \
  'CC=clang --sysroot=/work/research5-services/target-sysroot' \
  INSTALL_MOD_PATH="$R7_WORK/modules" INSTALL_MOD_STRIP=1 modules_install

python3 -B "$R7_REPO/scripts/research/display/verify_module_signatures.py" \
  --modules "$R7_WORK/modules" \
  --certificate "$R7_WORK/out/certs/signing_key.x509" \
  --expected-count 84 --output "$R7_WORK/module-signatures.json"
```

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

At preparation, all 26 public branches and the single open PR21 were inspected;
no R7/research7/RPMh-clock lane was present. Recheck before claiming a build.
