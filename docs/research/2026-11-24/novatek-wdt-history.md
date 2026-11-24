# Preserve Novatek WDT recovery when its history diagnostic fails

Date: 2026-11-24, Asia/Shanghai. Executed source:
`17c61c20b7955f39c62c7f89d922b999562c9122`.

The diagnostic that runs before Novatek firmware reload ignored page-selection
and SPI-read errors, and formatted into an unchecked allocation. Under an
allocation failure it could dereference a null pointer before reaching the
existing recovery operation. This change corrects that specific path. It does
not establish that the complete physical WDT/ESD recovery sequence works.

## Change

[Patch 0021](../../../mainline-port/backports/linux-6.12/0021-input-nt36523-handle-wdt-history-failures.patch)
applies after the previously reviewed firmware-range patch 0020. It:

- Checks the actual zero-success returns from history-page selection and SPI
  reading before using the buffer.
- Checks the allocation before formatting the original 128-byte history.
- Returns a signed errno, attempts event-page restoration on every path, and
  preserves the first error when restoration also fails.
- Logs an unavailable diagnostic while continuing the existing firmware-reload
  call. It preserves the exact successful 392-byte text format and existing
  locking, firmware name and download protocol.

The broader recovery transaction still needs work: firmware-reload error
handling, pen-state restoration, panel coordination and physical recovery are
not qualified by this diagnostic correction.

## Actual validation

The [C regression runner](../../../scripts/research/input/validate_novatek_history.py)
reconstructs the six public driver files from the existing patches and requires
the exact frozen R5 `nt36xxx.c` hash. It extracts the original/patched function
and the actual WDT caller block without substituting a rewritten algorithm.

In the CT102 `tb371fc-build-ssd-20261123` container, with AddressSanitizer,
UndefinedBehaviorSanitizer and LeakSanitizer still enabled:

- The unchanged original source reproduced the page-error, read-error and
  allocation-error defects.
- All **24 corrected checks passed**: 12 inputs through the direct diagnostic
  and through the real WDT caller. These cover individual/combined operation
  failures, a missing history address, successful data and all-zero/all-FF
  data. The checks require exactly one attempted event-page restoration and
  the caller's continued firmware-reload operation.
- Regression exited 0 at **02:21:12 UTC**. The subsequent complete ARM64
  external-module build exited 0 at **02:21:23 UTC**, including MODPOST/BTF.
- The four pinned baseline files were identical before and after the build.
- [Exact-source CI](https://github.com/cyjin-yl/TB371FC-6.12/actions/runs/45311508226)
  also passed the actual C regression.

The first local attempt is retained separately. It stopped at the unchanged
success fixture because LeakSanitizer cannot operate under that workspace's
ptrace environment. No sanitizer option was weakened to make it pass; the
same source and checks then ran in CT102 and GitHub Actions.

### Separate unsigned module

| Field | Actual result |
| --- | --- |
| Architecture | ELF64 AArch64 |
| Release | `6.12.114-tb371fc-research5-services` |
| Module bytes | 698,512 |
| Module SHA-256 | `998623b5b8d5666493162b04b01e3b3453777b3586d644d2296b23674881dc69` |
| Signer | Empty; unsigned |
| Installed / loaded | No / no |
| Owner native Linux passes added | 0 |

This candidate contains both 0020 and 0021. It has not replaced the frozen
84-module R5 bundle or the independently recorded 0020-only module. Any later
deployment must use a separately qualified module set, kernel trust binding,
manifest and target depmod records.

## Reproduction and retained records

Use the exact source above and an independent new work directory:

```sh
python3 scripts/research/input/validate_novatek_history.py \
  --repo "$REPO" --work "$NEW_REGRESSION_WORK"

python3 scripts/research/input/build_novatek_bounds.py \
  --baseline /work/research5-services \
  --patch "$REPO/mainline-port/backports/linux-6.12/0020-input-nt36523-validate-firmware-ranges.patch" \
  --followup-patch "$REPO/mainline-port/backports/linux-6.12/0021-input-nt36523-handle-wdt-history-failures.patch" \
  --work "$NEW_BUILD_WORK" --jobs 1
```

Original container work is retained at
`/work/novatek-history-job-17c61c2-20261124`. Public records:

- [Execution receipt](evidence/novatek-wdt-history/ct102-execution.json)
- [Actual C regression](evidence/novatek-wdt-history/ct102-regression.json)
- [ARM64 build receipt](evidence/novatek-wdt-history/ct102-arm64-build.json)
- [Build log](evidence/novatek-wdt-history/arm64-build.log)
- [Evidence identities](evidence/novatek-wdt-history/index.json)

The existing 44-case hardware ledger remains **12 blocked, 32 not run, zero
owner native Linux passes**. Host fault injection and compilation do not change
that ledger.
