# ARM64 BPF LSM attachment needs dynamic ftrace entries

Date: 2026-11-23. Source identities, exact configuration changes and scope: [arm64-bpf-trampoline.json](evidence/arm64-bpf-trampoline.json).

**The initial BPF LSM configuration advice was incomplete for the ARM64 attachment path.** Research3 successfully compiles BPF LSM, BTF and the probe-events dependencies, but it disables `FUNCTION_TRACER`. The actual 6.12.114 implementation relies on dynamic ftrace when a BPF trampoline attaches to a native kernel function. Research4 enables that build infrastructure in a new work directory and preserves research3 as a separate, unchanged result.

This corrects the sufficiency implied by the BPF section of [runtime-config-gaps.md](runtime-config-gaps.md). Its PIDs-controller, autofs and virtual-PL061 diagnoses remain unaffected. Enabling the function-entry build support does not request continuous tracing of every function; this work issues no command to select or start such a tracer.

## Exact source path

The reviewed tree is the reproduced research2 display source plus input patches 0018/0019 and the qualified joint DT. The input manifest is `5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0`. The JSON records SHA-256 identities for every source below.

1. `kernel/bpf/trampoline.c` allocates the trampoline's ftrace operations only with `CONFIG_DYNAMIC_FTRACE_WITH_DIRECT_CALLS`. Its `register_fentry()` checks `ftrace_location()`, then uses `register_ftrace_direct()` for a managed native function. The alternative is `bpf_arch_text_poke()`.
2. The disabled dynamic-ftrace implementation in `include/linux/ftrace.h` returns zero from `ftrace_location()`.
3. ARM64's `bpf_arch_text_poke()`, in `arch/arm64/net/bpf_jit_comp.c`, requires an address found in JIT BPF text. It explicitly delegates native kernel function entry to ftrace and returns `-ENOTSUPP` otherwise. A native LSM hook does not become JIT BPF text merely because its name starts with `bpf_lsm_`.
4. `arch/arm64/Makefile` emits `-fpatchable-function-entry=4,2` with `DYNAMIC_FTRACE_WITH_CALL_OPS`, or the `=2` alternative with `DYNAMIC_FTRACE_WITH_ARGS`. The BPF object's Makefile has no special exception that supplies these entries when the architecture build option is absent.

This is a source-based reason to expect research3's native LSM link to fail, not a substitute for the retained VM observation. Research3's actual `kernel/bpf/.bpf_lsm.o.cmd` has no `-fpatchable-function-entry` flag; its SHA-256 is `76cc3665d87605f6dd4b11d251d2bb3051a1d1107650805a901c3708845802b1`.

## Research4's resolved correction

Research4 starts from the same reproduced source and baseline configuration, with a fresh output directory and independent release. Its configure command exited zero in 7.38 seconds. The actual resolved configuration hashes to:

```text
0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275
```

| Build option | Research3 | Research4 |
| --- | --- | --- |
| `FUNCTION_TRACER` | disabled | enabled |
| `DYNAMIC_FTRACE` | not enabled | enabled |
| `DYNAMIC_FTRACE_WITH_ARGS` | not enabled | enabled |
| `DYNAMIC_FTRACE_WITH_CALL_OPS` | not enabled | enabled |
| `DYNAMIC_FTRACE_WITH_DIRECT_CALLS` | not enabled | enabled |
| `FTRACE_MCOUNT_RECORD` | not enabled | enabled |
| `FTRACE_MCOUNT_USE_PATCHABLE_FUNCTION_ENTRY` | not enabled | enabled |
| `FUNCTION_GRAPH_TRACER` | disabled | disabled |
| `UPROBE_EVENTS` | disabled | disabled |

The user-selectable additions are `FUNCTION_TRACER=y` and `DYNAMIC_FTRACE=y`. The architecture and tracing Kconfig derive the remaining capabilities, and the recipe strictly checks that they actually resolve to `y`. The existing compiler supports argument-aware dynamic ftrace, and `CFI_CLANG` remains disabled. The automatic changes include eight-byte function alignment and the required RCU support; the JSON records the complete diff.

The original SELinux/LSM order, module-signing policy and unprivileged-BPF default restriction remain unchanged. `CONFIG_MODULE_SIG_FORCE=n` is an existing baseline value. A controlled VM may separately request `module.sig_enforce=1` and verify the actual enforcement state; that is distinct from either the compile-time setting or offline CMS signature checks.

## Acceptance remains behavioral

Research3's complete Image, 84 signed modules, BTF and joint DT passed offline artifact inspection. That result does not assert that the LSM program links or enforces a filesystem restriction. The separate research3 system run retains its actual outcome; its warning or failure must not be suppressed to create a pass.

Research4's full build is separate at `/work/research4-system`. A final system pass still requires the active LSM list, exact live BTF, successful systemd attachment and an actual denied operation under a controlled `RestrictFileSystems` rule. The full-log failure checks and SELinux Enforcing gates remain in force. Neither this configuration correction nor a generic VM test establishes any physical tablet hardware result.

