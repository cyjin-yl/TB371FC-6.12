# V4 early SELinux loader for the reviewed socket-probe policy

Date: 2026-11-23, Asia/Shanghai. This is a completed independent **build,
transfer and negative-entry qualification**, not a new system-boot result.
The complete driver returned **0 in 21.694 seconds**; the ARM compilation
returned **0 in 6.430 seconds**. The helper has been copied byte-for-byte into
the HDD builder for the independent Fedora V9 profile. The owner tablet was
not booted, modified or used for any of these checks.

The reason for this candidate is the actual R4E `journalctl_t` self
`unix_dgram_socket create` denial, retained in the
[failed V8 system run](fedora-r4e-persistent-result-failed.md). The matched
[source investigation](selinux-journalctl-socket-probe.md) and separate
[minimal policy qualification](selinux-socket-probe-policy.md) explain the
socket-xattr feature probe and the seven-permission candidate. This loader
report qualifies the new policy identity and entry executable; it does not
replace those policy proofs or a new enforcing VM run.

## Exact inputs and output

| Object | Bytes | SHA-256 |
| --- | ---: | --- |
| New candidate `policy.35` | 3,835,468 | `ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798` |
| V4 build recipe | 13,152 | `5a9ae51cc0f5f3526f27564058a6cbd3603efda87166849cb8bd42b1f4462b75` |
| Unchanged audit guard | 7,393 | `f715d823ac20181b916afac5c4db9ae9af8226454508e2dff9bb9b8f35e035cc` |
| Derived C source | 20,011 | `7badcfe780ff18e906ad03de6e907f038b3c80505a64c631c0579c62850548f5` |
| V4 `early-init` | 72,528 | `0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14` |
| Reused V2 `init.tmpfs-wait` | 71,872 | `7e593ef9b2c40834b97ad35b1bc21fcd54b00e34dce72381832f88329e28b3ec` |

The loader is an AArch64 ELF64 PIE, with interpreter
`/lib/ld-linux-aarch64.so.1`, required objects `libc.so.6` and
`ld-linux-aarch64.so.1`, and GLIBC version references 2.17, 2.33 and 2.34.
The build checked the pinned cross compiler, package versions, headers,
source files and policy before compilation, then rechecked its inputs.
Compiler stdout/stderr and complete `readelf` results remain in the SSD
build directory. The [raw build record](evidence/early-selinux-socket-probe-build.json)
contains their observations, exact compilation arguments and package pins.

The actual artifact path is the same within the two independent builders:

```text
/work/early-selinux-socket-probe-20261123/build-01/early-init
```

This path identifies a new experiment prefix. The old V3 artifact, V8 image,
old policy stores and prior results remain intact. The binary policy is
retained privately and is not included as a payload in this public report.

## What changed in the loader

The [recipe derivation](evidence/early-selinux-socket-probe-recipe-derivation.json)
starts from the frozen V3 recipe
`21e912fa4a2b79b771b70e7b6a46187bde2f746425e549e7e4151d0ce3caf268`.
Both recipes derive their C source from the same original V1 source and the
same independently pinned guard fragment.

An independent local source comparison reproduced the previously compiled
V3 C hash `58fe1187109bc0feaedec249274815490ac69aa2e892cb3534c32a2f793cf4b8`.
It then confirmed that the complete V4 C differs in exactly two substitutions:

1. The marker changes from `TB371FC_EARLY_SELINUX_V3` to
   `TB371FC_EARLY_SELINUX_V4`.
2. The checked policy length changes from 3,835,456 to 3,835,468 bytes.

There are no additional C logic changes. The
[source-delta record](evidence/early-selinux-socket-probe-source-delta.json)
retains both full hashes and exact substitutions; its independently derived
V4 source hash agrees with the actual compiler input recorded by the build.

The early C helper checks policy shape and length. It **does not embed or
verify the complete policy SHA-256**. Consequently, its size check is not a
policy identity proof. The build recipe checks the complete `ff65…` input,
and the separate V9 archive checker and guest profile must bind the exact
policy, loader and runtime inputs by full hashes. This distinction was
already explicit in V3 and remains unchanged here.

## Audit observation and entry contract

The unchanged guard runs only on the normal root PID 1 entry, after the
initial root has been cleaned up and before the first libselinux policy load.
It requires the unique explicit command-line option
`rd.tb371fc.audit-printk-unlimited=1` and the actual device-tree compatible
`linux,dummy-virt`. It checks ordinary proc/sysfs objects and bounded numeric
values, writes only `0\n` to `/proc/sys/kernel/printk_ratelimit`, then requires
a fresh interval readback of zero and an unchanged burst value. Its flushed
marker precedes the policy-load marker.

This changes the shared printk interval in the opted-in generic VM. It does
not disable enforcing mode, change audit backlog/rate admission controls, or
prove that every possible audit message has been observed. The following VM
must still fail on any visible relevant denial, positive suppression count,
audit loss, malformed/interleaved evidence, forced termination or missing
required result. The fixed-kernel source reasoning remains in
[audit observability](audit-observability.md).

The existing `--check-api` branch is unchanged. It was **not executed** by
this V4 qualification. The source report must not turn the successful
negative-entry test into a policy-loading, namespace, mount or PID 1 test.

## Actual negative-entry observation

The new [negative qualifier](../../../scripts/research/selinux/socket-probe-loader/qualify_non_pid1.py)
checked the full ELF and native QEMU identities, then ran this command in the
HDD development container:

```text
/usr/bin/qemu-aarch64 -L /work/fedora-input-system-v6/rootfs \
  /work/early-selinux-socket-probe-20261123/build-01/early-init
```

At **16:56:27 Asia/Shanghai**, the child returned **1 in 0.984 seconds** with
empty stdout and exactly this stderr line:

```text
TB371FC_EARLY_SELINUX_V4 FAILED phase=entry reason=pid1-with-no-arguments-required errno=0
```

The qualification process itself returned 0 because refusal is the expected
outcome for a non-PID 1 child. The before/after printk values remained 5 and
10. The sampled reference root, `etc` and `dev` directory inode/timestamp
metadata also remained unchanged, and the artifact bytes were rechecked.
The [raw negative record](evidence/early-selinux-socket-probe-negative.json)
retains these observations without rounding or JSON-number reserialization.

The fixed entry order and exact refusal identify the branch before mounting,
audit adjustment or policy loading. Directory metadata is limited
corroboration, not a complete syscall trace. This test does not execute the
successful VM guard path and provides no physical-tablet result.

## Reusing the V2 waiter

The actual new ELF remains **72,528 bytes**, matching the V2 waiter's pinned
helper size. The independently built
[V2 waiter](tmpfs-waiter-v2.md) can therefore be retained unchanged, with its
existing `TB371FC_TMPFS_STAGE1_V2` marker. No new waiter build is claimed.
Its checks of PID 1, FD 3, the sole owned child, child reaping, the 30-second
bound, empty old root and console handoff remain unchanged.

The waiter checks the next helper's ordinary-file shape and length, not its
full SHA-256. V9 must include the actual V4 ELF and check its complete
`0bc3…` hash in the final archive. A shared length alone does not authorize
substituting V3 or another executable.

## Execution, transfer and reproducibility records

The job was an actual retained Python process in tmux
`tb371fc-early-selinux-v4:build`, with pane `%248` recorded at launch. It
orchestrated container-side compilation and data transfers; it did not
compile on the doesvm or CT 102 host. The four source/control members and
binary policy were qualified before their new SSD destination was written.
The new ELF, derived C and build records were then copied into a fresh HDD
prefix with full byte verification.

| Record | Purpose |
| --- | --- |
| [Driver result](evidence/early-selinux-socket-probe-driver.json) and [log](evidence/early-selinux-socket-probe-driver.log) | Complete actual phases and final exit, including build, transfer and negative qualification |
| [Launch](evidence/early-selinux-socket-probe-launch.json) | Actual tmux target, pane, command and pinned source packet |
| [Build invocation](evidence/early-selinux-socket-probe-invocation.json) | Exact native container command and retained output hashes |
| [Negative invocation](evidence/early-selinux-socket-probe-negative-invocation.json) | Actual direct-QEMU qualifier invocation and output hashes |
| [Input transfer](evidence/early-selinux-socket-probe-input-transfer.json) | Checked recipe, guard, derivation, qualifier and policy input identities |
| [HDD transfer](evidence/early-selinux-socket-probe-hdd-transfer.json) | Exact retained artifact and source/record identities |
| [Record transport](evidence/early-selinux-socket-probe-record-transfer.json) | Nine original records transferred losslessly, plus two separately identified local derivation records |

Executed source files are retained in
[`scripts/research/selinux/socket-probe-loader`](../../../scripts/research/selinux/socket-probe-loader/).
The source packet is reconstructible from its fixed file names, modes,
source bytes, derivation JSON and policy identity. The original private
policy and ELF transfer payloads are excluded from public evidence transport.

The next result must come from the independent V9 production run. This report
adds a qualified loader input; it does not change V8's failed verdict,
complete a tablet boot, validate GPU acceleration or establish optimal device
operation.
