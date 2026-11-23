# Fedora 45 policy format and the 6.12.114 kernel

The fixed Fedora 45 targeted policy can be converted from binary policy
version **35 to 33** by the exact ARM64 `libsepol` already installed in the
system-integration rootfs. The checked 6.12.114 kernel source accepts at most
version **33**. The actual conversion returned 0 at every step, produced the
expected version-33 bytes entirely in memory, and emitted no warnings.

This establishes **offline binary-format compatibility for these fixed
inputs**. It does not establish successful kernel policy loading, file labels,
an Enforcing systemd boot, or any tablet hardware operation. Neither the
rootfs policy nor its configuration was modified by this examination. The
[evidence JSON](evidence/selinux-compatibility.json) records the actual command,
return codes, source pins, binary identities and retained log hashes.

## Actual inputs and result

The inspection used the original CT102 `tb371fc-build-20261123` container and
`/work/fedora-system-integration-v1/rootfs`. The standalone check ran through
the existing PRoot 5.5.0 and `qemu-aarch64-static`, executing this rootfs's own
ARM64 Python and shared library. No `/sys` bind or SELinux kernel operation
was involved.

| Item | Actual observation |
| --- | --- |
| Kernel header | `/work/linux-6.12.114-research1/security/selinux/include/security.h` |
| Kernel header SHA256 | `1ae5425cd22ecb5089f6c3645abf65e6fd109b5faabc7df7b801deceefb800fa` |
| Maximum kernel policy version | `POLICYDB_VERSION_MAX` resolves to `POLICYDB_VERSION_COMP_FTRANS`, value `33` |
| Policy packages | `selinux-policy` and `selinux-policy-targeted`, `45.24-1.fc45.noarch` |
| Actual library packages | `libselinux-3.11-5.fc45`, `libsepol-3.11-2.fc45`, `libsemanage-3.11-4.fc45`, all AArch64 |
| Policy tools | `policycoreutils-3.11-2.fc45.aarch64` and `libselinux-utils-3.11-5.fc45.aarch64` |
| Input policy | `/etc/selinux/targeted/policy/policy.35`, 3,835,432 bytes |
| Input policy SHA256 | `928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430` |
| Actual `libsepol.so.2` | 802,880 bytes; SHA256 `46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b` |
| Actual library format range | Minimum 15, maximum 35 |
| Converted image in memory | Version 33, 3,835,420 bytes |
| Converted image SHA256 | `aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe` |
| Return values | Create database, read image, set version and serialize image: all `0` |
| Warnings / kernel load | Captured stderr empty; no kernel load attempted |

The binary header was checked, rather than inferred from the filename. It
contains the little-endian magic `0xf97cff8c`, an identifier length of 8,
the eight bytes `SE Linux`, then the little-endian policy version at byte
offset 16. The input was actually version 35 and the converted image was
actually version 33. Renaming a version-35 file to `policy.33` would not
perform this conversion.

## Automatic downgrade is an existing upstream mechanism

The upstream SELinux 3.11 tag resolves to tag object
`6fe03fd7524eccc5db74e74320684391805df9a0` and commit
`2233a23a4d4f1bf29054037babec13f30d038e65`. Eight relevant source files were
read at that commit and individually hashed in the evidence. They are
upstream source references; this report does not claim that Fedora's patched
source packages are byte-identical to them. The installed Fedora shared
libraries are separately pinned by their actual hashes.

In upstream
[`libselinux/src/load_policy.c`](https://github.com/SELinuxProject/selinux/blob/2233a23a4d4f1bf29054037babec13f30d038e65/libselinux/src/load_policy.c),
`selinux_mkload_policy()` obtains the kernel's supported version, opens
`libsepol.so.2`, and searches the policy files supported by that library. When
the selected file is newer than the kernel, it reads the policy database,
sets the target version and serializes a replacement image in memory before
loading it. If conversion fails, it searches for an older policy file. The
actual installed `libselinux.so.1` contains the corresponding dynamic-symbol
names and downgrade-error string.

The converter therefore is not a newly invented workaround. The read-only
probe exercises the same `libsepol` read/set-version/serialize primitives on
the exact policy and library that this initial-load path would use. It does
**not** call `selinux_mkload_policy()` or attempt its final kernel load.
Upstream's [userspace package description](https://github.com/SELinuxProject/selinux/wiki/Userspace-Packages)
also describes libselinux's use of libsepol for older-kernel policy formats.

Automatic conversion is conditional on the actual rules. In the pinned
[`libsepol/src/write.c`](https://github.com/SELinuxProject/selinux/blob/2233a23a4d4f1bf29054037babec13f30d038e65/libsepol/src/write.c),
conditional extended-permission rules cannot be written below version 34;
the writer returns an error. A nonempty neveraudit type map produces a
warning below version 35 and is omitted from that older representation.
Neither condition produced an error or warning for this exact policy.
That result must not be generalized to later Fedora policy updates.

## The actual dracut load path

This rootfs contains **`77selinux`**, not the older assumed `98selinux`
directory. Its module setup installs a pre-pivot hook. The hook enters the
mounted new root with `chroot` and invokes its `/sbin/load_policy -i`, with
the `/usr/sbin` alternative when appropriate. That process reaches the policy
and libraries in the **new rootfs**. It does not require a second copy of
those files at the initramfs root for this particular hook.

The observed module-setup hash is
`6b49435cb4c6d7158f96d714678a1b8ac1c129d71851550319b029d483617310`;
the load hook hash is
`8fe83554141667c99eda1fa3a96ce621cdea09feae2c2f3617074d8548b28e45`.
Both files are included in the evidence inventory. The generated initramfs
must still be inspected to establish that its selected modules actually
include the hook and that the new-root loader and libraries are available
at execution time. This examination did not generate or boot the initramfs.

Keeping the fixed `policy.35` and the installed libraries preserves that
normal load path. The real VM must then demonstrate a policy load and
Enforcing operation. `/sys/fs/selinux/policyvers` is the **kernel-supported
maximum**; it is not the format version of the policy currently loaded.
An actual loaded-policy header from `/sys/fs/selinux/policy`, together with
the enforcement state and PID 1's SELinux context, provides the required
additional evidence. Record the exported policy's own size and hash. Its
bytes need not equal the userspace conversion hash after the kernel has
parsed and reserialized it.

## Reproducible read-only check

[`verify_selinux_compatibility.py`](../../../scripts/research/verify_selinux_compatibility.py)
has SHA256
`6c3c9d4e75c9da1d30c977ae7d99be4dcb57ebb0bb68d247e9ec12a3d870bf6d`.
It pins the exact input policy, actual shared library and expected converted
bytes. Changed inputs, symlinks at the input file, non-regular inputs,
unexpected return codes or a different output hash fail the check. It
re-reads both controlled inputs after conversion and then frees the temporary
image. It has no output-policy filename, installation option or load call.

Run this script with the fixed Fedora ARM64 userspace, not the build
container's unrelated native Python/library. The actual execution read the
script from the read-only `/src` repository mount and passed its text as the
guest Python `-B -I -c` argument through PRoot. The full structured command
is retained in the evidence JSON; the guest had no host `/sys` or physical
device bind. The outer process imposed a 45-second bound.

The recorded `fixed-policy-memory-01` job finished with exit 0 in 3.47
seconds. Its command/exit record remains at
`/work/selinux-compatibility-v1/fixed-policy-memory-01.json`, SHA256
`469a8491c7d95a7cc819e4981bb5b8afd0b62f4692220124a097e5d074636997`.
The retained log's SHA256 is
`53176b312895d38264e67adc9de739f5bc06504faacd8de58e217ed9f8ec74c8`.
There is no continuing process from this check and no converted policy file
to mistake for an installed or loaded artifact.

## Optional offline rebuild using the existing fixed packages

The rootfs already has `semodule`, libsemanage, libsepol and the installed
targeted module store at `/var/lib/selinux/targeted/active/modules/100`.
Its standalone `checkpolicy` and `secilc` executables are absent; neither is
needed for libsemanage's embedded CIL compilation path. The pinned
[`direct_api.c`](https://github.com/SELinuxProject/selinux/blob/2233a23a4d4f1bf29054037babec13f30d038e65/libsemanage/src/direct_api.c)
passes the configured policy version into that compiler, and
[`semanage_store.c`](https://github.com/SELinuxProject/selinux/blob/2233a23a4d4f1bf29054037babec13f30d038e65/libsemanage/src/semanage_store.c)
uses the selected version in the installed policy filename.

If an explicitly generated version-33 build artifact is later wanted, the
source-supported route is:

1. Create a separate copy of the prepared rootfs, preserving the installed
   module store, libraries and tools. Keep the original integration rootfs
   and its evidence unchanged.
2. In that copy, set `policy-version = 33` in
   `/etc/selinux/semanage.conf`, preserving its other configuration.
3. Through the same ARM64 execution wrapper pointed at the copy, run
   `/usr/sbin/semodule -n -B -s targeted`. The `-n` flag suppresses kernel
   reload; this is an offline policy-store rebuild.
4. Require an exit of 0, retain all diagnostics, and inspect the generated
   `/etc/selinux/targeted/policy/policy.33` header, size and hash before using
   it in another image. A rebuilt policy need not be byte-identical to the
   direct binary conversion because compiler options and ordering can differ.

This full rebuild route was **not executed** in this examination. The actual
completed experiment is the fixed binary's in-memory conversion. The
[`semodule` source](https://github.com/SELinuxProject/selinux/blob/2233a23a4d4f1bf29054037babec13f30d038e65/policycoreutils/semodule/semodule.c)
and configuration parser establish the route and its options, rather than
an invented successful build claim. Any later policy or library update must
produce new compatibility evidence. An old fallback `policy.33` must not
silently stand in for an updated policy that fails conversion.
