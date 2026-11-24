# Novatek firmware parser bounds and stock-file compatibility

Observed on 2026-11-23 UTC. This is a bounded follow-up to
[input integration](input-integration.md), applying after input patch 0019.

**Patch 0020 builds as an AArch64 module for the frozen research5 kernel. All
eight owner-matched stock files pass both CRC paths with identical active
partition metadata and identical copied payload bytes. Eighteen range/decode
predicate checks also pass under ASan/UBSan. These are offline software and
build results; the module has not been signed, installed or loaded.**

## Concrete change

[`0020-input-nt36523-validate-firmware-ranges.patch`](../../../mainline-port/backports/linux-6.12/0020-input-nt36523-validate-firmware-ranges.patch)
repairs the inherited firmware parser and staging checks:

| Previous implementation | Corrected behavior |
| --- | --- |
| Reads fixed-header fields before checking their availability | Requires the fixed 0x30-byte header, then checks its declared end |
| Counts information records in an eight-bit counter | Uses a wide count, bounded by the checksum transfer-buffer capacity |
| Computes ranges with `offset + size`, while the transfer actually copies `size + 1` bytes | Checks the complete inclusive payload with subtraction before checksum or copy |
| Does not validate all information/overlay record headers before decoding them | Checks each full record, including the relative overlay range before adding offsets |
| Decodes high little-endian bytes using signed integer shifts | Promotes bytes to `uint32_t` before shifting |

The change retains zero-size reserved entries, active cascade/overlay ordering,
firmware names, GPIOs, timing and SPI protocol. The existing 0019 release path
continues to clean up a rejected parser result. This does not audit the whole
WDT/ESD recovery transaction or establish panel-before-touch ordering.

## Fresh owner reference

The [live Android capture](evidence/novatek-stock-live-20261123.json) was obtained
at **20:35:33 UTC**, with the checked-in
[`capture_stock_novatek.py`](../../../scripts/research/input/capture_stock_novatek.py).
It identifies TB371FC, kernel `4.19.157-perf+`, the `NVT-ts` SPI driver binding,
the stock pen properties and eight fixed firmware filenames. Each file is
245,760 bytes. Their SHA-256 values match the existing private doesvm archive.
The public record contains metadata and hashes, not firmware payloads or input
events. The registered driver and DT declarations do not demonstrate Linux
touch or pen operation.

## Actual validation

The reproducible validator is
[`validate_stock_novatek.py`](../../../scripts/research/input/validate_stock_novatek.py).
It extracts the actual C checksum, decoder, parser and firmware-staging functions.
Memory allocation and logging use host substitutes; the SPI sink writes into
private files. No hardware bus is opened. The normal old/new paths are compared
for all eight files under software CRC and hardware CRC, giving **16 cases**.

The comparisons cover every active partition's name, file/SRAM offsets, encoded
size and checksum, plus call counts, copied length and a direct comparison of
all copied bytes. SHA-256 values of those copied bytes are retained. Reserved
zero-size entries remain excluded from CRC comparison as in the download path.
The additional **18 checks** cover the range predicates, inclusive-length
boundary, reserved entries and high-bit little-endian decoding; these do not
exercise a real controller or the full malformed-file state space.

The patched harness runs with AddressSanitizer and UndefinedBehaviorSanitizer,
with diagnostics causing failure. The baseline is unsanitized because its
signed-shift decoder is the behavior being replaced. Final compiler:
**GCC 14.2.0 (Debian 14.2.0-19)**. Results:
[stock validation](evidence/novatek-bounds-stock-validation.json).

The first host-harness link with Clang failed because this builder lacks the
Clang ASan runtime archives. That failure is preserved in
[its log](evidence/novatek-bounds-clang-harness-failure.log); the successful run
uses the already installed GCC sanitizer runtime. The first successful GCC
version compared payload hashes; the final run additionally compares the
private payload files directly and runs the 18 predicates.

## R5 module build

[`build_novatek_bounds.py`](../../../scripts/research/input/build_novatek_bounds.py)
copies only the module source into a new directory, applies the patch there,
and invokes external-module Kbuild against the frozen research5 output. The
actual build completed with exit zero, including MODPOST and BTF, in the
existing `tb371fc-build-ssd-20261123` container on doesvm/CT102.

| Artifact property | Observed value |
| --- | --- |
| Architecture | ELF64, little-endian, AArch64 |
| Vermagic | `6.12.114-tb371fc-research5-services SMP preempt mod_unload modversions aarch64` |
| Module size | 696,520 bytes |
| Module SHA-256 | `2b8669fda09fa29aad1e22c13386f3e0377193884440a2845cfb82269b02068d` |
| Signing / installation / load | None |

The original firmware-update source, R5 `.config` and `Module.symvers` hashes
were checked before and after and are unchanged. This is the exact three-file
scope of the `baseline_unchanged` field, not an assertion about every file in
the baseline directory. See the [build record](evidence/novatek-bounds-r5-build.json)
and [complete build log](evidence/novatek-bounds-build.log).

Private build locations:

- Candidate module/source: `/work/novatek-bounds-build-20261123`.
- Final stock compatibility execution: `/work/novatek-stock-validation-20261123-final`.
- Frozen kernel baseline: `/work/research5-services`.

The candidate is separate from R5's signed 84-module set. Composing a bootable
stack requires a newly qualified module manifest and signing/trust validation;
this patch does not silently alter an existing frozen boot candidate.

## Reproduction

Within the prepared builder, use new output directories and the private stock
archive whose hashes match the live capture:

```sh
python3 scripts/research/input/build_novatek_bounds.py \
  --baseline /work/research5-services \
  --patch mainline-port/backports/linux-6.12/0020-input-nt36523-validate-firmware-ranges.patch \
  --work /work/novatek-bounds-next --jobs 2

python3 scripts/research/input/validate_stock_novatek.py \
  --baseline /work/research5-services/source-input/linux-6.12.114-input-integration/drivers/input/touchscreen/nt36523/nt36xxx_fw_update.c \
  --patched /work/novatek-bounds-next/source/drivers/input/touchscreen/nt36523/nt36xxx_fw_update.c \
  --archive /path/to/private/current-vendor-firmware-20261123.tar.gz \
  --capture docs/research/2026-11-23/evidence/novatek-stock-live-20261123.json \
  --out /work/novatek-stock-next --cc gcc
```

The extraction helper is deliberately tied to the recorded source. Its simple
brace scan was independently checked against the seven current C functions;
future changes adding braces in strings/comments need renewed review or a
proper C lexer. The stock compatibility run is not a firmware authentication
test, full parser fuzz campaign or native tablet acceptance. All existing
physical Linux acceptance cases retain their previous state.
