# NixOS registered-root preparation: retained cache-copy timeout

This is an **actual failed native preparation**, before an image or system VM.
It extends the [completed original NixOS toplevel build](nixos-system-build.md);
it does not retract that 894-path build or turn it into a boot result.
The first attempt to register that closure in a separate root stopped while
constructing its private signed cache. All original paths and the partial cache
are retained. No tablet, bootloader, USB role or Android setting was changed.

## Actual outcome

The original job started at **2026-11-23 08:49:26.612765 UTC**. Its final record
reports **exit 1 after 5530.405676769966 seconds**; the preparation itself reports
5529.351299453003 seconds. The precise exception is
`subprocess.TimeoutExpired` for the original `signed-cache-copy` command after
**3600 seconds**. Those two durations cover the whole job and preparation,
respectively; neither is a claim that the individual copy had a 5530-second
deadline. The earlier native source verification consumed 1922.6411205229815
seconds and exited zero.

| Completed step | Exit | Actual elapsed seconds |
|---|---:|---:|
| Native Nix version | 0 | 2.8380112510058098 |
| Original recursive source metadata | 0 | 0.4654320700210519 |
| Recursive source content/trust verification | 0 | 1922.6411205229815 |
| Private project-cache key generation | 0 | 1.4704774130368605 |
| Derive public key | 0 | 0.049272598000243306 |
| Signed cache copy | timed out | original 3600-second subprocess limit |

The source is the original
`/nix/store/j1g4ih1ajpffx2vhp5z0iyns13h59c4a-nixos-system-tb371fc-research-26.05.20261121.94c3211`.
The native importer is Nix 2.26.3, executable SHA-256
`1795adb32a21c0aeef19e19530e96b933b603465a99dc6cf3ceed5b96948de58`.
The original inventory is still 894 paths and 3,751,712,072 NAR bytes, as bound
by the [earlier inventory](evidence/nixos-system-store-paths.tsv).

The original command retained `require-sigs=true`, native store verification
and the complete original closure. It did not disable signature checking to
make the copy finish. A private project key was created solely for the isolated
cache/import path; its bytes are excluded from the JSON, logs published here
and any guest. That project trust is distinct from the original official cache
signatures, locally trusted paths and content-addressed paths. Exit zero from
the native verification is not described as a new official signature on every
path.

## Why the timeout is absent from one command list

The retained preparation JSON contains five completed command records. The
original helper appends each record **after** `subprocess.run` returns. The
copy raises `TimeoutExpired` before that append, so it is absent from the
`commands` array even though it ran. Its identity and limit are recorded in
the same JSON's traceback and the full original job log. The separately
retained copy stdout is empty; stderr contains **125629 bytes** of original
copy activity. This publication retains both rather than interpreting the
missing array item as an unexecuted phase.

The [exact executed recipe](../../../scripts/research/nixos/store-preparation-v1/prepare_store.py)
is 13715 bytes, SHA-256
`bae60cfa9cb64b6ce229a30f36c0bf1c0d2eb8b1d7508d63c4a5361e65a7169a`.
It was not edited to extend the limit or resume the failed prefix. The paths
under `/work/nixos-system-boot-v1` and the original job remain separate from
any subsequent recovery attempt.

## What did not run

The registered destination copy, destination metadata comparison, complete
destination content/signature verification, source-after metadata comparison
and root DB/profile qualification were not reached. Neither a root image nor
NixOS stage1, its original activation script, PID1 or a generic system VM was
run. The original NixOS activation script and toplevel are not modified here.
No host activation or global Nix configuration change occurred.

The source-after check is explicitly unfinished: the recipe's intended
read-only/source-preservation behavior is not substituted for that final
comparison. Concurrent storage activity is context; these logs do not prove
a unique physical I/O cause. A partial cache and a stream of copy messages are
not a qualified registered root.

Recovery may use a new independent SSD prefix and an exact authenticated NAR
source, but it must retain the original paths/NAR identities/references,
`require-sigs`, destination registration and whole-content verification.
That future work is outside this failed-attempt result. The separately
[completed research5 kernel and modules](research5-services-kernel.md) do not
make this unbooted NixOS root a system pass.

## Retained source and exact raw records

The [aggregate JSON](evidence/nixos-store-preparation-failed.json) links the
original report, runner record, complete runner log, copy streams and source
verification stderr. Two small transfer records identify the specific
ordinary files read; no private-key-producing stdout was read for this
publication. Log bytes are preserved, including the empty stdout.

| Exact original/transfer record | Bytes | SHA-256 |
|---|---:|---|
| `store-preparation.json` | 7831 | `6a7c5bb1c85d8c76570d99fe51886f99651d60c113ff5e9f625c3725167c5ce9` |
| `store-01.json` | 364 | `6ea23db5edf5b6abb334b066bc3cbe5b825f0cf496454b5f9055c53a03456c8f` |
| `store-01.log` | 2760 | `854e561963ca228adfe75924846bbeaa72a753caa5a96f1e617e2668d8ffb0e8` |
| `signed-cache-copy.stdout.log` | 0 | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` |
| `signed-cache-copy.stderr.log` | 125629 | `d1acbddb90e8d19ebf8c497dea1ea0546c6452826d9b632cb6f215a525500d4a` |
| `source-verify.stderr.log` | 68837 | `9a04bc44277539077171ce0a384c2064b7d45bb5fb703651d25621ffd82e8b1a` |
| `copy-logs-transfer.json` | 667 | `d07ee8a676cbf7edeedf6fdbeae9a6283eef4ad62e7941c2236d0c9c6af6bcf9` |
| `source-verify-transfer.json` | 269 | `07be6a4767938d2c0e0ed0a77f00ef2ce97c9162dc95fb7e8f8d2fe9f7fe4c2b` |

**Owner acceptance remains unchanged:** 44 cases, 12 blocked and 32 not run;
zero owner-native Linux boots and zero hardware passes.
