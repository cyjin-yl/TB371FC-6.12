# Research3 system kernel: completed host build and a retained ARM64 BPF limit

## Result and evidence boundary

The independent `6.12.114-tb371fc-research3-system` kernel completed its full
Image, module and joint display/input DT build. The offline inspector passed
with **84 installed AArch64 modules**, matching module order, **4,308 imported
symbol CRC comparisons**, verified CMS signatures and retained BTF. Its frozen
machine-readable result is
[`evidence/research3-system-build.json`](evidence/research3-system-build.json),
SHA-256
`c785afdeb088dc59d2bb9403a5296509399bf3393a29efaeeb28e0f44efa82dc`.

That success is a **host-build result**. It does not establish BPF LSM attachment,
PIDs enforcement, tablet boot, display, touch, keyboard, GPU operation or sound.
In particular, this candidate retains `CONFIG_FUNCTION_TRACER=n`: the subsequent
[ARM64 trampoline audit](arm64-bpf-trampoline.md) identifies why a compiled
`CONFIG_BPF_LSM=y` is insufficient for native kernel LSM hooks on this ARM64
implementation. Research3 is preserved unchanged for the separate full Fedora
runtime comparison. Research4 uses a new source/output prefix to address that
specific function-entry dependency. No runtime BPF success is inferred here.

## Exact inputs and scope

The build ran inside CT102's SSD build container, in the independent
`/work/research3-system` prefix. It replayed the pinned Linux 6.12.114 research2
source recipe, then input patches `0018` and `0019` and the qualified joint DT.
The source-input manifest SHA-256 is
`5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0`.
The configuration baseline is the frozen research2 configuration,
`e024e6d2094180d31d2b3f64a643801d95c544c0bb9593a64b6d117c2ffb86a8`.
No previous object tree or signing private key was copied.

The recipe is in
[`scripts/research/system-kernel/`](../../../scripts/research/system-kernel/).
It records the source manifests, complete resolved configuration changes and
builder package inventory. The nested `source_input` object in the result
describes the earlier source/module preparation stage; its `image_built=false`
does not describe this subsequent full build. The top-level completed artifact
fields describe research3.

| Purpose | Resolved research3 setting | Remaining proof |
| --- | --- | --- |
| Per-cgroup process limits | `CONFIG_CGROUP_PIDS=y` | Actual controller and `TasksMax` behavior in the full VM |
| Automount support | `CONFIG_AUTOFS_FS=m` | Signed `autofs4` module loading and runtime behavior |
| Generic QEMU GPIO supplier | `CONFIG_GPIO_PL061=y` | Probe result on the QEMU `virt` machine; no physical tablet GPIO claim |
| BPF LSM and its selected infrastructure | `BPF_LSM`, `BPF_EVENTS`, `FTRACE`, `KPROBES`, `KPROBE_EVENTS` enabled | Native ARM64 hook attachment remains blocked by the missing dynamic function-entry path |
| Kernel and module type metadata | DWARF4, `DEBUG_INFO_BTF`, `DEBUG_INFO_BTF_MODULES` enabled | Runtime `/sys/kernel/btf/vmlinux` identity checked separately |

`FUNCTION_TRACER`, `FUNCTION_GRAPH_TRACER` and `UPROBE_EVENTS` remain disabled
in research3. The earlier LSM/security configuration, including SELinux and the
default LSM list containing `bpf`, was preserved. Module signing, signing all
modules and SHA-512 were preserved. `CONFIG_MODULE_SIG_FORCE=n` was also
preserved; a VM that requires enforcement must request and verify
`module.sig_enforce=1`, rather than misreport this compile-time setting.

## Actual build and inspection

The full build used four jobs and exited **0 after 1,340.16 seconds**. Kbuild's
`modules_install` ran with `INSTALL_MOD_STRIP=1`; its install sequence strips
debug information before signing the final module bytes. The inspector then
verified those final bytes, rather than a pre-strip copy. Every module retains
`.BTF`, has no `.debug_*` sections, imports CRCs from this build's
`Module.symvers`, and carries the same release/signing identity.

The first inspector attempt exited 1 because its default repository path did
not contain the pinned, previously frozen signature helper. This was a recipe
path failure before signature verification. That attempt and log were retained.
The exact helper
(`ad270d83f89ce08d2488906b8246167227e0e352a91294042489d0a0737908df`)
was placed in a separate inspection overlay with the expected directory
structure; no kernel artifact was altered. Inspector attempt 02 exited
**0 after 5.88 seconds**. Its job-result SHA-256 is
`7a8dcf75a4a192716455d9460e1957393529726e487acb91ba2bb0c9e846221e`,
and its log SHA-256 is
`5742a2deaa16d1658fb947e772aee821b7305625e700dae3ed50b40ce92e2f82`.
The full build log SHA-256 is
`f4f49fa9c21a5070253abf07e0f22de01465e5d940ae252dea43fe2f26a31b2e`.

Relative to the frozen research2 module list, the only added module is
`fs/autofs/autofs4.ko`; no module was removed. The complete order-to-installed-set
check derives its expected inventory from Kbuild, without an assumed module
count. The report includes the ordinary installed metadata files
`modules.order`, `modules.builtin` and `modules.builtin.modinfo` needed by the
downstream rootfs integration.

## Qualified artifact identities

All paths in this table are under
`/work/research3-system/artifacts/`. The complete per-module list and hashes are
in the frozen report and `modules.SHA256SUMS`.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `Image` | 39,051,272 | `0038f8d60bdb109e30f992ac65a37de4c4eff06baa2e4b38744d183342297444` |
| `board.dtb` | 126,877 | `af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730` |
| `kernel.config` | 221,645 | `17479c824b087d888f586c1800729ab01746db568685a2bd21c008aea9ca0d51` |
| `Module.symvers` | 834,796 | `adc13232a777ee2fb409cf25c4d3f6b7a3adc1c17a479dec5c871812b45a7bdd` |
| `modules.SHA256SUMS` | 13,089 | `ccc6b8dbdfe0c5e76061750bc86839f1b894be47d202b411e50580214034fe46` |
| `kernel.btf` | 6,385,387 | `d2e2b5596ea570ffe51a4e4981f01e36463428e701aa8deb31969ca62ad3b8e8` |
| `signing-cert.der` | 1,324 | `652e92353cb6ce1dff099d9f7753314447f38a9cfa8397ede3feeaf152ea16e6` |

The inspector located the exact extracted BTF and public certificate bytes in
the linked uncompressed `Image`. All 84 module CMS signatures verified against
that public certificate. This is cryptographic consistency within this new
build, not a claim of a public CA trust chain. The independent private signing
key remains owner-only in the build directory; it was not copied, published,
read or hashed by the inspector. A byte-identical independent rebuild has not
been demonstrated, and the fresh signing identity makes it inappropriate to
promise one.

## Native DT checks and remaining hardware work

The joint DT exactly matches its previously qualified SHA-256. Display nodes,
Novatek touchscreen/SPI ancestors and the keyboard node are available in the
compiled DT. The input changes remain restricted to the qualified joint DT
changes; no unmeasured touchscreen physical dimensions were inserted. These
are source and compiled-DT checks, not successful peripheral probes.

The GPU IOMMU still has all four compatible strings
`qcom,sm8250-smmu-500`, `qcom,adreno-smmu`, `qcom,smmu-500`, and
`arm,mmu-500`, with `dma-coherent` present. The GPU `iommus` property resolves to
that SMMU and is unchanged from research2. The historical experiment removing
`qcom,adreno-smmu` was not applied. The compiled configuration does not prove
runtime per-process GPU address spaces, GL/Vulkan rendering or video decode.

The artifact handoff is suitable for the separately documented generic Fedora
VM integration. Physical TB371FC boot entry, hardware operation and recovery
remain separate acceptance work; the absence of a completed physical entry
test is not evidence that mainline Linux cannot boot this tablet.
