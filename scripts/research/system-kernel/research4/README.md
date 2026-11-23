# Independent research4 system kernel

This recipe combines the source-pinned research2 display work, input patches
0018/0019, the already qualified joint display/input DT, and the configuration
gaps diagnosed in
[`runtime-config-gaps.md`](../../../../docs/research/2026-11-23/runtime-config-gaps.md).
Its release is `6.12.114-tb371fc-research4-system`. It never changes the frozen
research1/research2 or input-integration-v3 trees.

## Preparation and build

Run only in the dedicated CT102 SSD build container, with `/src` mounted
read-only and a new `/work/research4-system` prefix. LLVM 19, make, flex, bison,
OpenSSL, pahole, libelf development files, dtc, kmod and Python are required;
the actual complete Debian package inventory is recorded in the artifacts.
The existing pinned kernel archive and frozen recipe overlays are inputs.

```sh
python3 /work/input-integration-repo-v3/scripts/research/input/prepare_input.py \
  --repo /work/input-integration-repo-v3 \
  --baseline-repo /work/research2-repo \
  --baseline-work /work/research2-display \
  --work /work/research4-system/source-input \
  --cache /work/downloads/linux-6.12.114.tar.xz

python3 -B /src/scripts/research/system-kernel/research4/build_system.py configure
python3 -B /src/scripts/research/system-kernel/research4/build_system.py build --jobs 4
python3 -B /src/scripts/research/system-kernel/research4/inspect_system.py
```

The real runs wrap each command with `scripts/research/build/run_job.py` in a
visible tmux pane. Its `--work /work/research4-system/jobs --name UNIQUE --`
arguments retain the exact command, log, exit code and duration. Keep failed
attempts; a build or inspection retry uses a new `--attempt` and job name.
Configuration refuses to replace an existing output directory.

The configure stage checks the exact prepared input manifest, copies the frozen
research2 configuration, merges `system.config`, and checks every requested
resolved value. An explicitly empty target sysroot keeps freestanding compiler
capability probes independent of subsequently installed ARM userspace headers.
The full effective configuration diff and all preserved security/signing options
are saved. Review those before starting the build.

Kconfig derives the BPF events dependencies from the selected Kprobe path.
Uprobe events and function-graph tracing remain disabled. ARM64 BPF LSM
attachment requires the FUNCTION_TRACER/DYNAMIC_FTRACE build infrastructure and
derived direct-call/argument/call-ops support. No command enables a running
function tracer. The exact source dependency is recorded in the ARM64 BPF
trampoline report. The original LSM order,
SELinux options, unprivileged-BPF default restriction and module-signing policy
remain unchanged. DWARF4 and pahole produce kernel and module BTF; deployed
modules are stripped by `modules_install` **before** they are signed.

A fresh key is generated only inside the new private build output. No old key
is copied. Only its public certificate is exported. Independent builds are not
claimed to have identical bytes.

## Artifact and validation interface

Consumers must wait for `artifacts/research4-system-build.json` with `passed`
true and its `qualified-artifacts.SHA256SUMS`. The build directory alone is not
a qualification marker.

The stable output paths are:

- `artifacts/Image`, `board.dtb`, `kernel.config`, `Module.symvers`,
  `System.map`, `kernel.release` and `source-manifest.json`.
- `artifacts/modules.SHA256SUMS`, with the **actual** complete module set and
  new release. No fixed module count is assumed.
- `artifacts/modules.order`, `modules.builtin` and `modules.builtin.modinfo`,
  copied from the installed module-tree root and independently hashed. Copy
  these ordinary files with the modules, then regenerate binary depmod indices
  in the new userspace image; do not copy build/source symlinks.
- `modules/lib/modules/6.12.114-tb371fc-research4-system/`, installed by Kbuild.
- `artifacts/kernel.btf`, containing the exact BTF bytes verified in Image.
- `artifacts/signing-cert.der`, containing public certificate data only.

The inspector reuses pinned module-inventory, CMS-signature and DT parsers. It
checks complete build/install module-order agreement, every AArch64 module,
every imported symbol CRC against the new `Module.symvers`, full consistent
vermagic, every CMS signature against the certificate embedded in Image, BTF
presence and stripped DWARF. It checks the exact joint DT hash and records the
unchanged Adreno SMMU compatibles, `dma-coherent` property and resolved GPU
`iommus` reference. It does not reinterpret historical GPU experiments as changes
present in this candidate.

The full Fedora generic-VM integration separately validates the active PIDs
controller, autofs, active BPF LSM and systemd attachment, live kernel BTF,
SELinux Enforcing and the virtual PL061 GPIO consumer. A generic VM does not
qualify the Lenovo display, GPU, touch/pen, keyboard, power or physical boot entry.
