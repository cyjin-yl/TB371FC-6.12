# Owner A650 identity matches the compiled chip-ID path

A new bounded, read-only Android capture resolves a possible ambiguity in the
GPU version strings. On this owner's TB371FC, `gpu_model` reports
**`Adreno650v3`**, while the live KGSL DT property `qcom,chipid` contains the
four bytes **`06 05 00 02`**, interpreted as one big-endian cell
**`0x06050002`**. These are two observations of the same running Android
configuration; the `v3` text must not be substituted for the numeric patch
field in a mainline DT compatible string.

The [new capture](evidence/android-gpu-chipid.json) was taken at
`2026-11-23T02:01:38.014867Z` on `4.19.157-perf+`. The reusable
[collector](../../../scripts/research/capture_gpu_chipid.py) reads only the
fixed GPU model, kernel release, and the three declared DT properties
`compatible`, `qcom,chipid`, and `status`. It performs no register/MMIO read,
frequency change, runtime-power write, rendering, or firmware loading.

## Exact comparison with research1

| Link in the comparison | Actual value |
| --- | --- |
| Owner Android model string | `Adreno650v3` |
| Owner declared numeric chip ID | `0x06050002` |
| Compiled board DT first GPU compatible | `qcom,adreno-650.2` |
| `find_chipid()` result for that string | `0x06050002` |
| A650 catalog entry | `ADRENO_CHIP_IDS(0x06050002)` |
| Catalog firmware names | `a650_sqe.fw`, `a650_gmu.bin` |
| Catalog GMEM declaration | 1 MiB + 128 KiB |

The actual loader parses the first `qcom,adreno-XYZ.W` string into core,
major, minor and patch fields. For `650.2`, those fields are `6`, `5`, `0`,
and `2`, respectively. Its fallback legacy `qcom,chipid` property is not
needed for this compiled board DT. The catalog uses that exact chip ID.
This is a source/DT identity match; it is not an inferred runtime GPU probe.

The inspected files are from the already frozen
`/work/linux-6.12.114-research1` source tree:

| File or artifact | SHA256 |
| --- | --- |
| `drivers/gpu/drm/msm/adreno/adreno_device.c` | `7ddde6ff94c9270a6ed94e6a001e127ee9be2c2fe1904e2c929e41d0e1502091` |
| `drivers/gpu/drm/msm/adreno/a6xx_catalog.c` | `3db6ce0d10dad36533ba832f3fcaae9409bb95376c677b5cab29b5b7e9cc5f37` |
| research1 compiled `board.dtb` | `129bbee33b0c71be120d1d724be6267d0e4f99c07ec9ed951a823ab9241998dc` |

The catalog is also among the files already frozen in the
[firmware loader contract](firmware-kernel-contract.md). The later Fedora
runtime staging checks that contract's 22 loader-source hashes and all
relevant DT firmware-name properties against research1 before reusing the
canonical firmware tree built for research2-display.

## What this closes, and what it leaves open

This closes the narrow identity question: this owner's reported A650
revision does not require guessing a new `qcom,adreno-650.3` string or adding
an unobserved chip ID to the catalog. No GPU driver or DT patch was warranted
by these observations.

The [compiled GPU/SMMU check](evidence/gpu-dt-contract.json) also prevents a
historical experiment from being mistaken for this candidate's configuration.
The actual research1 SMMU compatible list is
`qcom,sm8250-smmu-500`, `qcom,adreno-smmu`, `qcom,smmu-500`, `arm,mmu-500`.
Its `dma-coherent` property is present, and the GPU's `iommus` reference points
to this SMMU. **The historical R185 removal of `qcom,adreno-smmu` has not been
applied to this compiled DT.** There is no need to invent a new DT patch to
restore a string that is already present. This establishes the intended
Adreno SMMU configuration, not successful per-process page-table switching.

It does not establish successful GMU or ZAP authentication, GPU MMU address
space isolation, stable OpenGL/Vulkan rendering, native DSI presentation,
performance, or suspend/resume. Those remain separate physical tests in the
[GPU acceptance discussion](gpu-acceleration.md) and
[whole-device ledger](acceptance.json). In particular, the historical CP/IB
translation-fault report still needs comparison against an actual run of
this configuration. A prior workaround's history is not proof that this
candidate uses it, and a normal DT is not proof that isolation now works.
No owner mainline render or GPU isolation run has been performed.
