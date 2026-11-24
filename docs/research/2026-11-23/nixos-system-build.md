# NixOS: the complete custom ARM64 userspace system now builds

The same pinned NixOS configuration that previously only evaluated has now
**completed its full custom `system.build.toplevel` build** inside doesvm
CT102. Its recursive runtime closure contains **894 existing store paths**,
all with their recorded references present, totaling **3,751,712,072 bytes of
serialized NAR size**. The actual AArch64 systemd executable also ran under
explicit QEMU and reported **systemd 260.5**.

This closes the foreign-builder and full-system-realization gaps recorded in
the [earlier NixOS experiment](../../../distros/nixos/README.md). It does not
assemble or boot a NixOS root filesystem, activate this configuration, install
a bootloader, integrate the research kernel/modules/private firmware, or test
the tablet's GPU and peripherals. The external boot artifact options remain
unset in the unchanged source profile.

## Exact result

The [frozen machine-readable report](evidence/nixos-system-build.json) has
SHA256 `ee99b0aaf21a989fc4045e0b4ed81a228c9d7f091ea9b88c6f4001db6f2bd5c0`.
The complete [store inventory](evidence/nixos-system-store-paths.tsv) has
SHA256 `466e2d7d84b26a5d359148da5b3f44f2d8562d0216b546b780833bcedfb4135a`.

| Check | Actual observation |
| --- | --- |
| Nixpkgs source | `94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd`, unchanged NixOS 26.05 pin |
| Native build engine | Nix 2.26.3 on x86_64, existing dedicated Debian container |
| Foreign execution | Existing PRoot 5.5 mixed execution plus explicit `qemu-aarch64-static` |
| Tiny custom ARM derivation | Exit 0; ARM bash executed a nested ARM `hello`, with exact output checked |
| Full-system dry run | 241 custom derivations; 304 additional cached paths, estimated 1047.02 MiB download / 1572.11 MiB unpacked |
| Full-system build | Exit 0, 879.574 seconds including the recorded job wrapper |
| Recursive realized system closure | 894 paths; 3,751,712,072 NAR bytes |
| Referenced paths | All exist; every recorded reference remains inside the recursive closure |
| Actual systemd binary | ELF64 little-endian AArch64, machine ID 183; `--version` exit 0 |
| Generated `init` and `activate` | Both pass the actual ARM bash syntax check; neither script was executed |
| Post-build inspection | Exit 0, 1.776 seconds |
| Default Nix controls after the build | Equal to the recorded pre-build values |

The output is exactly the path predicted by the earlier evaluation:

```text
/nix/store/j1g4ih1ajpffx2vhp5z0iyns13h59c4a-nixos-system-tb371fc-research-26.05.20261121.94c3211
```

Its NAR hash is
`sha256-AkVctNvTyfC7P4IE43KUYLOej/pE0skdk6e/PtYr3Ds=`. The small top-level
output itself occupies 17,152 NAR bytes and references the much larger
recursive closure; it is not a standalone image. The exact completed
derivation is:

```text
/nix/store/9qpn9nzy4xmcrfv6jc5liymr8mnzwdpg-nixos-system-tb371fc-research-26.05.20261121.94c3211.drv
```

`/work/nixos-system-v1/system-result` is an indirect GC root retaining that
closure in the build container's Nix store. It is a normal Nix result link,
not a compatibility link replacing a moved project directory. Build logs,
per-command output, phase metadata and the inventory are retained in
`/work/nixos-system-v1` and `/work/nixos-system-jobs`.

## The missing execution route was supplied explicitly

The earlier cache experiment proved that packaged ARM programs were available,
but did not make Nix's new ARM builders executable. The new
[foreign-builder recipe](../../../scripts/research/nixos-system/foreign_builder.py)
first verified the actual ARM ELF identities. It then ran a native Python
process that spawned the ARM bash and ARM hello through PRoot's mixed
execution mechanism. Finally, Nix itself built a new `aarch64-linux`
derivation whose ARM shell executed the ARM program and wrote exact checked
output into the Nix store. Only that successful build enabled the full-system
attempt.

PRoot's [documented mixed-execution mechanism](https://proot-me.github.io/)
allows native tools and QEMU-interpreted guest programs in the same traced
process tree. Here it leaves the native Nix evaluator/store engine native
while enabling its ARM child builders. No host binfmt handler was registered,
no remote builder was invented, and the target architecture alone was not
treated as an emulator.

Nix's [build settings](https://nix.dev/manual/nix/2.26/command-ref/conf-file)
were supplied only to these commands:

```text
--store local
--option sandbox false
--option build-users-group ''
--option extra-platforms aarch64-linux
--option require-sigs true
--option cores 2
--option max-jobs 1
```

The empty build-user group keeps these builders under the calling process
identity within the already isolated container, so their execution stays in
the traced process tree. Disabling the extra Nix sandbox is recorded, matching
the namespace limitation already demonstrated by the earlier experiment. It
is not a claim that PRoot provides a security sandbox. This route neither
connects to a shared Nix daemon nor changes the host/CT Nix configuration.

The defaults were read before and after: `sandbox=true`, build-user group
`nixbld`, native `x86_64-linux`, the original x86 extra-platform list, official
cache URL/key and `require-sigs=true` all remained unchanged. Cached inputs
and locally built outputs retain their different provenance: 656 closure
paths carry signatures and 227 are marked locally trusted in Nix's metadata.
The custom system output is locally built and has no official cache signature.
Those categories are recorded without asserting that every closure member
is an independently signed upstream release.

## What the binary and script checks establish

The [inspector](../../../scripts/research/nixos-system/inspect_system.py) checked
the unchanged hashes of the original flake, lock file and hardware module;
queried the complete realized closure; recorded every store path/NAR hash;
and resolved the generated system entries. It directly executed this binary:

```text
<system-output>/systemd/lib/systemd/systemd --version
```

The actual command was prefixed with `qemu-aarch64-static`; this was not native
x86 execution or a systemd PID 1 boot. The binary has SHA256
`894b6544ca1428f71990e083f80acb5150914c5fe1c47777d32821b6e3a25595`.
Its feature output includes `-SELINUX`, `+APPARMOR`, `+BPF_FRAMEWORK` and
`-BTF`. These are this package's compiled feature declarations, not observed
kernel security-policy enforcement. They must not be equated with the
separately observed Fedora SELinux Enforcing boot.

The command-record field `emulation_enabled` describes whether the helper
automatically added the PRoot wrapper. It is false for the inspector's
explicit QEMU commands because QEMU is already named in their argument
vectors; it does not mean that those ARM binaries ran natively. The actual
argument vectors and outputs are retained to make that distinction checkable.

The generated stage-2 `init` and activation script were checked only with
ARM bash `-n`. Their hashes are respectively
`d7440ba41d2fb1abdbe1a9a2a1267cde841deb9dd4bd088a59586b12a719becd`
and `8e8c85675ceca709cd0445f5211a556cb3d0edf52d94e63cd1ea1bdf989f2ea9`.
No `nixos-rebuild switch`, activation, boot installation or owner storage
operation occurred. This remains a complete **userspace closure build**.

## Remaining NixOS integration

The external boot contract still needs one coherent kernel Image, board DT,
root-mounting initramfs, matching module tree, approved private firmware tree
and an actual root filesystem with its Nix store. The generated stage-2 init
must then be entered and tested as PID 1 in a separate system boot. The
existing missing-artifact gate is still applicable; no paths were filled with
placeholders merely to make it pass.

The packaged Freedreno/Turnip libraries from the original closure remain
useful inputs, but this new build did not exercise a render node or native
display. It adds no physical tablet pass to the
[whole-device acceptance ledger](acceptance.json).
