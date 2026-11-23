# V2 early SELinux loader for the independently derived policy candidate

## Construction result and scope

A separately identified AArch64 early loader has been built for the new
policy-reload candidate. Compilation completed with exit 0 in **1.617 seconds**
inside the existing SSD build container. The resulting PIE executable is
**72,048 bytes**, SHA-256
`cc042c9fc4e92c75803215649c99bd87badd301bb05aa16820b43aaeb8fb50bc`.
Its transferred copy in the HDD container has the same bytes. An actual
non-PID1 invocation through QEMU exited 1 at the entry guard, before any mount
or policy-load operation.

This report freezes construction and that negative check. It does not claim
that the new loader has executed as PID 1, loaded this candidate policy, or
completed an Enforcing system boot. The independent v7 system experiment owns
those runtime gates. No physical tablet was booted or modified here.

The exact native build record is
[early-selinux-reload-loader-build.json](evidence/early-selinux-reload-loader-build.json),
4,453 bytes, SHA-256
`25b3f844bb59245b49c2be134f8f7341aee566e0c50ec72e8fabd6c439964b68`.
The transfer and negative-check record is
[early-selinux-reload-loader-negative.json](evidence/early-selinux-reload-loader-negative.json),
1,784 bytes, SHA-256
`813f6b82924320d2c7fedf2232ea3a36b469e8a8ca402eadebd256718918f71e`.

## Why this is a separate candidate

The retained [v6 failure](fedora-r4c-tmpfs-failed.md) established that the
ordinary-tmpfs bootstrap can enter `init_t` and `udev_t`, but PID 1 was then
denied a read-only mapping of its correctly labeled policy file. That failed
standard reload left systemd's `loaded_policy` flag false and its corresponding
API-filesystem relabel branch unexecuted. The
[offline access-vector investigation](selinux-runtime-contract-query.md)
confirmed the missing `init_t` to `semanage_store_t:file map` permission in the
fixed source policy; it did not itself load or modify a policy.

The separate [policy derivation](selinux-policy-map-candidate.md) supplies the
new `policy.35`. This loader recipe neither edits policy rules nor chooses a
different file label. It retains the original library/API sequence and gives
the new experiment a distinct serial marker. Standard systemd reload and
relabeling must still succeed in the subsequent full VM.

| Input or output | Bytes | SHA-256 |
| --- | ---: | --- |
| Frozen V1 C source | 12,548 | `6006a0fade3e9e8cc9201b5549cab3339961931feadb842c0f3d5863dc383726` |
| Derived V2 C source | 12,548 | `ab6cf79bcad7d1306bc0e943ef3a4770d8db1c1db82ad577e117c298cce0fda9` |
| New build recipe | 10,461 | `a9679fcbe613297e9ab8e6080e776b1703e798d2225442d280d5eeb89e40e125` |
| Original Fedora `policy.35`, retained | 3,835,432 | `928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430` |
| Independently derived candidate `policy.35` | 3,835,432 | `0dd46af3240a02d1c7399c46facf30cce2a71a471fb70c0d0f5e58e571e53c74` |
| Compiled V2 loader | 72,048 | `cc042c9fc4e92c75803215649c99bd87badd301bb05aa16820b43aaeb8fb50bc` |

The candidate policy has the **same length** as the original. Consequently,
the actual derived C file changes only the serial marker from
`TB371FC_EARLY_SELINUX_V1` to `TB371FC_EARLY_SELINUX_V2`. The length-replacement
entry in the build record has identical old and new values; no control-flow
or length-check change is concealed by that record. The original V1 source,
recipe and `e53cf407…` executable remain untouched.

The native helper's file-length check cannot distinguish these two policies.
The new archive checker and runtime profile must therefore independently
require the complete candidate hash above. A successful helper build or an
equal policy length is insufficient to qualify a boot image.

## Fixed build inputs and actual execution

The [new recipe](../../../scripts/research/selinux/reload-map/build_early_init.py)
hash-checks the frozen V1 source and its
[original build recipe](../../../scripts/research/selinux/build_early_init.py).
It imports only that recipe's pinned Fedora RPM/header extraction helpers;
it does not change the original recipe's source constant or call its
source-specific build function. Both derivation anchors must occur exactly
once.

The existing Fedora `libselinux-devel-3.11-5.fc45.aarch64.rpm` is 128,120 bytes,
SHA-256 `60383ef415eee73f0f2cad12e81010f6a6c2bf810dfed7b3c61f585ea772e6da`.
All seven extracted header hashes are checked. The existing qualified header
cache is outside the new work directory and outside any frozen rootfs.

Compilation used the fixed Debian cross-toolchain: GCC package
`14.2.0-19cross1`, binutils `2.44-3`, and ARM64 libc development package
`2.41-11cross1`. The actual compiler file has SHA-256
`fb743ca27a77466c91da66047eec879a615993feaabd860aaf3750e7b222b131`.
The recipe preserves the original PIE, stack-protection, fortification,
RELRO/NOW, warning-as-error and deterministic-epoch options. Compiler stdout
and stderr were both empty, and the native record reports exit 0.

The built ELF is little-endian AArch64, machine 183, type `ET_DYN`, with
interpreter `/lib/ld-linux-aarch64.so.1`. Its only `DT_NEEDED` entries are
`libc.so.6` and `ld-linux-aarch64.so.1`; there is no RPATH or RUNPATH. Version
requirements are `GLIBC_2.17`, `GLIBC_2.33` and `GLIBC_2.34`. The original
explicit `dlopen`/libselinux API calls remain in the unchanged control flow;
their runtime library identities are the separate archive's responsibility.

Only one V2 compilation is recorded here. Fixed inputs and deterministic
options do not by themselves prove an independent bit-identical rebuild.

## Retained artifacts and negative check

The build ran in `tb371fc-build-ssd-20261123` at:

```text
/work/early-selinux-reload-map-20261123/build-01
```

The input policy was copied natively from the independent HDD
`/work/selinux-reload-map-20261123/build-02/candidate` tree and hash checked on
both sides; the source was then hash checked again. No PRoot process was used
for this transfer or compilation. The frozen V1 source and recipe and the new
policy input were rechecked after the build.

The resulting executable, derived C source and original build-result bytes
were transferred to the same `build-01` path in
`tb371fc-build-20261123`. The HDD qualification directly executed:

```text
/usr/bin/qemu-aarch64-static \
  -L /work/fedora-input-system-v6/rootfs \
  /work/early-selinux-reload-map-20261123/build-01/early-init
```

It returned exit 1, no stdout, and the expected V2
`pid1-with-no-arguments-required` entry failure. The source checks this guard
before the first mount and before `load_api()`. This is a non-PID1 refusal
test; it is not the API-only mode and not a successful policy-load test.
The sampled v6 root, `dev` and `etc` directory inode/mtime/ctime values were
unchanged. QEMU used that directory only to resolve runtime libraries; no
PRoot binding setup, new VM, or rootfs relabel occurred.

The unchanged `cc30c123…` tmpfs cleanup waiter checks the next `/init` file's
shape, owner, mode and 72,048-byte length; it does not internally hash the
next executable. Its size condition still fits V2. The v7 archive must bind
that waiter to the **new** complete loader hash, without reinterpreting the
frozen v6 report or source comments as a v7 identity proof.

All owner-tablet acceptance results remain unchanged. This construction adds
no GPU, display, input, radio, audio or power-management pass to the
[whole-device ledger](acceptance.json).
