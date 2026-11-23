# Research5: build the original NixOS and Nura service prerequisites

**The independent `6.12.114-tb371fc-research5-services` kernel has completed its
full build, offline module/DT qualification and transfer into the shared system
builder.** This checkpoint supplies the missing kernel features identified in
the retained original NixOS and Nura service files. It contains no R5 system-VM
result and no owner-tablet Linux run.

The complete inspector result is
[research5-services-build.json](evidence/research5-services-build.json),
136,930 bytes, SHA-256
`69d0b558c99bdfb339df8b3b9baca8bb1ee4d0cb2e46dd9b3b7fef3ab69aaad2`.
The separate [publication and transfer verification](evidence/research5-services-verification.json)
indexes 55 retained raw records, all execution-source identities and the
original service inputs. Raw command logs retain their original bytes.

## Why this kernel is needed

R4 resolves the ARM64 function-entry dependency needed by the Fedora BPF
workload. Reading the other two original userspaces identified additional
requirements before either could be tested fairly:

- Nura's original nftables configuration creates an `inet` stateful firewall
  with conntrack and reject expressions. Its unchanged `zramstart` explicitly
  chooses `zstd` when deviceinfo has no override. R4 does not provide the
  required nftables selections or that zram backend.
- The original NixOS firewall is generated for iptables-nft 1.8.13. Its rules
  include `rpfilter`, `conntrack` and `pkttype`. The exact upstream `add_match`
  path handles only a limited set of matches natively; these remaining names
  use the nft compatibility expression with the already enabled x_tables
  implementations. An extension's separate translation callback does not
  prove that this installation path uses the native nft `fib` expression.
- The generic QEMU model supplies a PL031 RTC. The original Nura `hwclock`
  script can return zero after a failed clock operation, so a later guest
  check must observe the actual driver and RTC readback. Enabling PL031
  supports that VM check; it is not a physical-tablet RTC result.

The fixed [configuration contract](../../../scripts/research/system-kernel/research5-services/recipe-v1/services-contract.json)
contains every expected semantic delta and hashes each source used to derive
it. Public copies include the original
[Nix firewall script](evidence/research5-services-source-inputs/nixos-firewall-start.sh),
[iptables installation code](evidence/research5-services-source-inputs/iptables-nft.c.txt),
[Nura nftables rules](evidence/research5-services-source-inputs/nura-nftables.nft.txt),
[zram service](evidence/research5-services-source-inputs/nura-zramstart.sh) and
[hwclock service](evidence/research5-services-source-inputs/nura-hwclock.sh).
The [upstream iptables source capture](evidence/research5-services-source-inputs/iptables-official-source.json)
retains the acquisition record and original archive identity.

## Exact configuration scope

The build starts from the exact resolved R4 configuration, SHA-256
`0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275`.
The resolved R5 configuration differs in exactly 14 values:

| Group | Resolved changes |
| --- | --- |
| Release | `CONFIG_LOCALVERSION`: research4-system to research5-services |
| nftables core and families | `CONFIG_NF_TABLES`, `CONFIG_NF_TABLES_INET`, `CONFIG_NF_TABLES_IPV4`, `CONFIG_NF_TABLES_IPV6`: `n` to `y` |
| Stateful rules and compatibility | `CONFIG_NFT_CT`, `CONFIG_NFT_COMPAT`: `n` to `y` |
| Reject expressions | `CONFIG_NFT_REJECT`, `CONFIG_NFT_REJECT_INET`, `CONFIG_NFT_REJECT_IPV4`, `CONFIG_NFT_REJECT_IPV6`: `n` to `y` |
| zram | `CONFIG_ZRAM_BACKEND_ZSTD`: `n` to `y`; the exclusive `CONFIG_ZRAM_BACKEND_FORCE_LZO` selection becomes `n` |
| Generic VM RTC | `CONFIG_RTC_DRV_PL031`: `n` to `y` |

All other R4 semantic configuration values must remain equal. In particular,
the existing LZO backend and `lzo-rle` kernel default remain enabled. Nura's
service can request zstd explicitly; this build does not establish its
performance, energy cost or suitability for every workload.

The guard retains the existing module-signing selections, LSM order, SELinux,
BPF/ftrace/BTF, display, input and GPU/IOMMU settings. Features such as extra
logging, NAT, masquerade and FIB expressions were not added speculatively.
The [resolved configuration record](evidence/research5-services-records/container/configuration.json)
and [complete configuration bytes](evidence/research5-services-records/container/artifacts/kernel.config.txt)
make this comparison reviewable.

## Actual construction and qualification

The source was reproduced into a new SSD-container tree from the pinned
input-integration preparation. No old object directory or private signing
key was copied. Source preparation completed with exit 0; the full build
then used the independently generated signing key. Kbuild strips the
installed module copies before signing their final bytes.

| Actual phase | Exit | Elapsed time |
| --- | --- | --- |
| Recipe installation and readback | 0 | 1.509 s |
| Configuration and exact-delta check | 0 | 40.083 s |
| Image, modules, DT and artifact staging | 0 | 1,681.092 s |
| Offline artifact inspection | 0 | 15.765 s |

The driver completed at **2026-11-23 10:04:06 UTC**. Its complete phase records
and stderr identities are retained in the
[original driver result](evidence/research5-services-records/control/host-build/build-driver-result.json).
The [full build log](evidence/research5-services-records/container/jobs/build-01.log)
contains 222,140 bytes; no excerpt substitutes for it in the evidence bundle.

The inspector qualifies all **84** installed ARM64 modules. Their relative
module-path set is exactly the R4 set. Every module has the expected vermagic,
the same new signer/key/hash algorithm, a verified CMS signature and module
BTF, with DWARF sections stripped. All **4,308** imported-symbol CRC entries
match the newly built `Module.symvers`. This is offline module qualification;
the inspector does not load a module.

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Image | 41,091,080 | `d80bfce0feb5f6c0cec1b0b0dd4691323720ec3f34a373c7a109001e2cf42e76` |
| BTF | 6,466,067 | `fee84441d208c1ce5e920a3a26e5132f74095f1d2eb3e692b95a9343ac9a43f4` |
| Joint native DTB | 126,877 | `af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730` |
| Resolved configuration | 223,395 | `a4980121abcc3e2bac47f7020e63c8c00949c53c289019c22b67808d84cd3afa` |
| Public signing certificate | 1,324 | `07a54ba929080f3c5d74cb485afeca7d7acf7c920fde0b26cf003ba45fd57627` |

The complete BTF and new public-certificate bytes are present in the Image.
The certificate differs from both R2 and R4. Kbuild uses the private key
inside the build container; the evidence collectors and runtime transfer do
not read, hash or export private-key material. A newly generated signing key
intentionally changes artifact bytes, and no bit-identical independent
rebuild is claimed. Tool package versions are recorded; their whole package
set is not pinned to a historical distribution snapshot.

The joint native DTB is unchanged. The display and input nodes remain
enabled in the qualified joint profile, and the standard Adreno SMMU
compatibles, `dma-coherent` property and GPU IOMMU references remain intact.
This does not establish runtime address-space isolation or GPU rendering.

## Shared public-runtime transfer

The completed output was copied from `tb371fc-build-ssd-20261123` to
`tb371fc-build-20261123`, both within CT102, under the new destination:

```text
/work/research5-services-kernel-inputs-v1
```

The allowlist contains exactly **106 ordinary files**: 17 public artifacts,
the actual inspector report, its derived checksum index, 84 signed modules
and the three original Kbuild module-metadata files. Each endpoint is a
container operation. The transfer does not include a signing private key,
firmware payload, build/source symlink or old depmod index.

Source files were fully hashed before and after copying; the destination was
fully read back. Contents, ordinary modes and numeric owners match across
all three observations. The canonical source and destination archive streams
also match: **66,263,040 bytes**, SHA-256
`ae57626102a400b8a6ef85369d40ed72e68b5639f0b8c7f241c067212e6c8bf9`.
The complete [transfer record](evidence/research5-services-records/control/shared-transfer/transfer.json)
preserves all 106 identities, both stream results and source/destination
comparisons. The driver completed at **10:07:21 UTC**, exit 0, in 6.227 s.
Each new distro root must generate its own native depmod indexes.

## What remains open

At this checkpoint, the original NixOS and Nura userlands still need their
separate real system boots and complete service checks against the actual
R5 artifact identities. A successful archive, configuration check or
ordinary result-file extraction is not a complete-system pass. Their
firewalls, service startup, zram, clock readback, normal signed-module load
and shutdown still require runtime observations.

Owner-tablet Linux remains **0 runs and 0 passes**. The
[whole-device acceptance plan](acceptance.md) still requires native display,
touch and pen behavior, keyboard hotplug and accessories, hardware OpenGL and
Vulkan, radios, audio, charging, thermal control, suspend/resume and matched
Android performance/energy comparisons. R5 closes a reproducible kernel
construction gap; it does not change those physical-device outcomes.
