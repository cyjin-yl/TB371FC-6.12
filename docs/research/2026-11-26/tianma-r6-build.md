# Tianma OFF R6: completed ARM64 build and offline module signatures

Date: **2026-11-26, Asia/Shanghai**. Execution timestamps below are UTC.

The [corrected Tianma OFF candidate](tianma-off-lifecycle.md) completed a
fresh ARM64 Image, modules and DTB build. All **84 installed modules** then
passed detached PKCS#7 verification against the candidate's public signing
certificate. The frozen R5 inputs were reverified after construction.

This is construction and offline cryptographic evidence. The R6 kernel was
not booted, its modules were not loaded into a running kernel, and no native
panel-off, suspend/resume or tablet acceptance pass is added.

## Exact execution and input relationship

| Item | Observed value |
| --- | --- |
| New release | `6.12.114-tb371fc-research6-tianma-off` |
| Host/container | doesvm / CT102 / `tb371fc-build-ssd-20261123` |
| Dedicated candidate | `/work/tianma-r6-build-ec332-01` |
| Build start / completion | `2026-11-25T18:15:51.504728+00:00` / `2026-11-25T19:00:10.297168+00:00` |
| Elapsed build time | 2,658.797 seconds, about 44 minutes 19 seconds |
| Compiler / linker / BTF tool | Debian Clang 19.1.7 / LLD 19.1.7 / pahole 1.30 |
| Admission and parallelism | Existing host `agent-heavy` guard; `MAKEFLAGS=-j2` |
| Offline signature check | `2026-11-25T19:00:53.476797+00:00` to `19:00:59.267647+00:00`, exit 0 |
| Signature implementation | OpenSSL 3.5.9; public certificate only |

The build used staged working-tree inputs. The four relevant published files
— candidate patch, build recipe, regression harness and complete upstream DRM
panel-core fixture — match
[`4d640cfea2e46df297311eecbcf8a211603e3ef0`](https://github.com/cyjin-yl/TB371FC-6.12/commit/4d640cfea2e46df297311eecbcf8a211603e3ef0)
byte for byte. The retained worktree's observed Git HEAD remained
`0acacec10d2864dca3fc44f57d27b853493363f9`; this is not a claim that execution
used a clean checkout of the published commit. The later signature verifier
is identified separately by its executed source hash.

The [evidence index](evidence/tianma-r6-build/index.json) pins all five source
files and all 14 exported receipt/log/public-artifact files. Its build recipe
SHA-256 is `226393ac5b102fd359658adba25019a0e38697bbcf30f39b46aeadc871646dc1`;
the signature verifier is
`8e7fb179b500bf13cfadd3843fdb3104a5740005f1cd394f2be8112732ee0082`.
The exporter rehashed the installed modules and retained build artifacts
after the signature check. The published file bytes were checked again
after export, including the complete logs.

## Construction result

The [recipe](../../../scripts/research/display/build_tianma_candidate.py)
copies the verified retained R5 source into a new directory and uses a new
Kbuild output directory. It rejects nonrelocatable source symlinks and old
generated outputs/signing keys before copying. It applies the corrected
Tianma patch with zero fuzz, reruns the actual-core C regression against the
build tree and changes only `CONFIG_LOCALVERSION` in the frozen R5 config.
The complete config is compared after `olddefconfig` and again after Kbuild.

| Actual phase | Exit | Retained evidence |
| --- | ---: | --- |
| Copy original source into the new candidate | 0 | [copy-source.log](evidence/tianma-r6-build/copy-source.log) |
| Apply the byte-pinned Tianma patch | 0 | [apply-panel.log](evidence/tianma-r6-build/apply-panel.log) |
| Actual panel functions and Linux DRM core regression | 0 | [actual-core-regression.log](evidence/tianma-r6-build/actual-core-regression.log), all 34 cases passed |
| Preserve config except the candidate local version | 0 | [olddefconfig.log](evidence/tianma-r6-build/olddefconfig.log) |
| Complete ARM64 Image and modules build | 0 | [kernel-modules.log](evidence/tianma-r6-build/kernel-modules.log) |
| Compile the retained board DT target | 0 | [device-tree.log](evidence/tianma-r6-build/device-tree.log) |
| Install, strip and sign the 84 modules | 0 | [modules-install.log](evidence/tianma-r6-build/modules-install.log) |

The complete [build-result.json](evidence/tianma-r6-build/build-result.json)
records the commands, timestamps, log digests, patched source, configuration,
public certificate, every module and all retained artifacts. All 84 installed
files have AArch64 ELF64 headers and appended module signatures. The new
public certificate differs from R5's certificate; the R5 private key and old
build objects were not copied.

The original panel and config hashes still match at completion. The existing
R5 source verifier also passes before and after the build. Its stated scope
is the pinned assembled source files, baseline ABI inputs and recipe
manifests; it is not a hash inventory of every upstream source byte.

### Key artifact identities

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Image` | 41,091,080 | `0732ed1bbfcf616140e4ee20964faa0fb93db96b6e6e150c6e1711a3e90386b4` |
| `board.dtb` | 126,877 | `af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730` |
| `kernel.config` | 223,397 | `5a8ec0c9e1c8eccb10fd12f25a05268b0d739f8bc77d9536a9e664f24bae0e72` |
| Public `signing-cert.der` | 1,324 | `0ef0ef0c4bfbd0291e76a451b03d05b9c601d6c40a882e54dcf06ab1f9065107` |
| Installed `panel-novatek-nt36523.ko` | 218,497 | `fe2f5d305227b8eaee4e6015c6eedae8ae1bab849c31440ba3dc9229f47c1aec` |

The DTB is byte-identical to the frozen R5 build DTB. It is not the separate
[`7092d992...` second-stage RAM-declaration candidate](../2026-11-24/r5-second-stage-dtb.md),
and its construction does not establish safe load addresses or board entry.
`Module.symvers` also matches the retained R5 artifact, but the new release
and signing identity still require a coherent R6 runtime/module set.

The configuration uses `CONFIG_MODULE_SIG_ALL=y` and SHA-512. It does **not**
set `CONFIG_MODULE_SIG_FORCE`; a future runtime acceptance must separately
prove the effective enforcement policy, trusted keyring and actual module
loads. The earlier Fedora/Nura R5 VM results do not establish these for R6.

## All 84 offline signatures verified

The [read-only verifier](../../../scripts/research/display/verify_module_signatures.py)
parses each module's Linux signature trailer, checks the ARM64 relocatable
ELF structure and verifies the detached CMS signature over the original
unsigned module bytes. OpenSSL receives only the explicit candidate public
certificate as a possible signer. The verified output must equal the original
module content, and the actual signer DER must equal that certificate.

Certificate-chain validation is intentionally separate: the explicit public
certificate is the offline verification anchor. This does not establish its
presence or trust in any running kernel. No candidate private key is read by
the verifier or included in the exported evidence.

The actual [command receipt](evidence/tianma-r6-build/module-signatures-command.json)
binds the source, complete argv, zero exit code, empty process log and the
[94,541-byte per-module result](evidence/tianma-r6-build/module-signatures.json).
All 84 results passed, every signer matches the new public certificate and
the complete module path/size/hash set equals the build result. Input
snapshots stayed stable throughout verification.

The four small [crypto/parser regressions](../../../scripts/research/display/test_verify_module_signatures.py)
cover a valid detached signature, altered module content, an embedded signer
certificate that must not override the supplied wrong certificate, and
nonzero trailer padding. They use synthetic ELF samples and temporary keys;
they are not real kernel module-loading tests.

## Reuse and remaining acceptance

Repeat construction through the existing host admission guard with the
retained R5 inputs and a new `/work/tianma-r6-build-*` directory. The recipe
is repeatable at the source/configuration level; new signing material means
fresh runs are not promised to produce identical Image/module hashes.

The PR workflow reruns the C and signature regressions and checks the exact
retained source, log, certificate and module-result relationships. CI neither
rebuilds this kernel nor boots R6. The Image and installed modules remain in
the dedicated build directory; this publication contains their identities,
public configuration/certificate and complete text receipts.

The original [November 24 host evidence](../2026-11-24/tianma-off-sequence.md)
and both negative controls remain preserved. Physical HS transport, bonded
DSI timing, panel-off, suspend/resume, runtime signing trust and native boot
remain separate unmet checks. **Owner-native passes added: zero.**
