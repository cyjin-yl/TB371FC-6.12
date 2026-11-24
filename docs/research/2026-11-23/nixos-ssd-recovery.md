# NixOS SSD registered-root recovery, 2026-11-24

The new native SSD-local attempt succeeded. This advances the preserved
[original signed-cache timeout](nixos-store-preparation-failed.md) without
editing or restarting that failed attempt. The [earlier system closure
build](nixos-system-build.md) is unchanged.

## Executed result

- Builder: doesvm CT102, existing `tb371fc-build-ssd-20261123`.
- Executed source commit `9f04ed18f306f266172a641a4378e0f4b2f6a889`;
  [recipe](../../../scripts/research/nixos/store-preparation-ssd-v1/recover_store.py)
  SHA-256 `fa3ebb5e3822f289e6636ffaddfaa5cfefe492eb11dc25872cda5d72da8b152d`.
- Four contract self-checks passed; native job started 02:28:30 UTC and
  finished 02:29:10 UTC, exit 0, 40.146 seconds total.
- Reused 890 retained cache records with 868 distinct compressed objects.
  Added the exact official source NAR with its original official signature
  and three small original NAR dumps, hashed against the frozen source
  inventory and signed by a new project-specific Ed25519 key. The assembled
  cache contains 894 narinfo records and 872 objects.
- Native Nix 2.26.3 registered the complete 894-path closure
  (3,751,712,072 NAR bytes) into a new local store, with explicit
  `require-sigs=true`, explicit trusted public keys, and network
  substituters disabled. The copy took 24.550 seconds. The native
  destination metadata query took 0.346 seconds; complete recursive
  content and signature verification exited 0 after 8.768 seconds.
- Exact destination path set, NAR hashes/sizes, references, content
  addresses, original signature retention and each required key's
  presence were checked. The original init and activate hashes match.
  No host activation occurred.

The [allowlisted receipt](evidence/nixos-ssd-recovery-v1.json) binds the
retained 10,350-byte result (SHA-256
`44d633777bf13b21964e3714ffc37d85daa7a356dc895564ef6dd7cc34e0397e`).
The private key and raw job files remain on the builder, not in Git.

## Independent follow-up checks

The original HDD store's native recursive metadata query was repeated
after the new SSD registration, with signature checking required.
Normalization used NAR hash/size, sorted references, sorted signatures,
ultimate and content-address fields. All 894 paths match the frozen
before inventory. Both normalized inventories have SHA-256
`eb364fcdd70aba00506f9aabbe64250f3672c0f50a6afc061bc152b4f275dd7a`.
The source-before file SHA-256 is
`3f5772abcfb979a5413ab2e76d8db06022fa60a7a7b2a9b34d5a4c8abc0c0eaa`.
This is a metadata comparison, not a second HDD content scrub.

A separate post-run check hashed the 64 native importer ELF files (including
the loader, private dependencies and Nix binary, 48,979,824 bytes) and
compared paths, sizes, modes and UID/GID to the retained tool report.
There were no mismatches; the sorted name/hash manifest SHA-256 is
`befbf3595f4de94a7d08a518fe388ae9efbf3dc8b76dbc361e25ccdc0e928c28`.
The native tool report SHA-256 is
`afaa0995663626f443a9bc5507f1873ea3043a8ec44b4576e8316798e436101b`.
This follow-up establishes the observed post-run file identities, not
a new execution of the registration.

## Handoff

The successful registered root is retained at
`/work/nixos-ssd-recovery-20261124-v1/rootfs`, with the result and
logs in that prefix. The recipe and job exit receipt are at
`/work/nixos-ssd-recovery-recipe-20261124-v1`. Do not repeat this copy or
modify this registered root in place.

The existing `/work/nixos-system-boot-assembly-recipe-v1` was inspected
on the HDD builder. It consumes the old preparation schema and the
older kernel bundle, so do not blindly invoke it with the new root.
Next create an independent derived assembly root, bind the new registered
root and source-after metadata receipt, update the fixed runtime
contract to the actual R5 kernel/module/firmware identities, and use the
existing BusyBox stage1 and verification service only after their
contract checks. Construct the ordinary ext4 image and run the real
NixOS stage1 and generated stage2 init in generic ARM64 QEMU.

The old project key attests the earlier verified import, the official
key authenticates the exact official source, and the new project key
attests only three verified local NARs. None is falsely described as
a new official signature on every path.

No NixOS image, activation, stage1, PID1, or VM boot was executed in this
attempt. Owner native Linux remains 44 cases, 12 blocked, 32 not run,
zero boots and zero passes.
