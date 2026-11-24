# Fixed systemd source contract for the BPF behavior check

The matched Fedora systemd source confirms that the existing attachment log
gate is a positive observation of a successful LSM attachment. It also gives
a more precise expected result for the new direct-syscall worker: denying
`/proc/version` with `RestrictFileSystems=~proc` must fail **at open with
`EPERM`**, before reading any bytes. An arbitrary nonzero exit, `EACCES`, or a
later read failure does not establish that this particular program enforced
the restriction.

This is a source inspection, not an observed BPF attachment or successful
VM. The complete source identities and boundaries are in
[systemd-bpf-runtime-contract.json](evidence/systemd-bpf-runtime-contract.json).
The independent [v7 profile plan](fedora-r4d-profile-plan.md) applies this
contract to its actual same-worker unrestricted/restricted pair.

## Matched package source

The audit read the already retained official
[`systemd-262.1-1.fc45.src.rpm`](https://kojipkgs.fedoraproject.org/packages/systemd/262.1/1.fc45/src/systemd-262.1-1.fc45.src.rpm)
inside the existing CT102 HDD build container. Its SHA-256 is
`de8e6ebb2fb7b7aa0e1297c0c27c3339d15c37b24b57ca16a762483580ea7168`.
The embedded `systemd-262.1.tar.gz` is 19,088,198 bytes with SHA-256
`100fc873b848b9b0297d8a705e8e2ed326256c8483d9960ee1ffe264c8a5c3e3`.

The packaged spec's older `26494.patch` is conditional on Fedora below 40
and RHEL below 10, so it is not active for Fedora 45. The three included
downstream patches affect `uid-classification.c`, `core/varlink.c` and
`machine/machined-varlink.c`. None touches either audited BPF source file.
The evidence records the spec and patch hashes, conditions and targets.

| Source | Bytes | SHA-256 |
| --- | ---: | --- |
| `src/core/bpf-restrict-fs.c` | 9,766 | `e99314f8c40795ca85959fbb151d40a9ef5446b1ec32b377039fe500b582aa14` |
| `src/bpf/restrict-fs.bpf.c` | 2,740 | `0674d7a0e740bd4f347aaa96a942c416872735965d9b426e23dcb9b00b2bfe4c` |

## What the positive log message proves

In `bpf_restrict_fs_setup`, the object must load successfully before
`bpf_program__attach_lsm` is called. A nonzero translated attachment error
returns immediately. Only the following success path emits
`bpf-restrict-fs: LSM BPF program attached`, then retains the link and object
in the manager. Thus this exact marker is stronger than a compiled feature
flag or an attempted attachment.

The marker alone does not show that the intended task had the correct
cgroup map. `bpf_restrict_fs_update` separately inserts the cgroup's inner
map, selects allow-list or deny-list semantics, and populates filesystem
magic values. A runtime pass must establish the behavior as well.

## Why the direct denial must be `open` / `EPERM`

The BPF program is attached to `lsm/file_open`. It reads the file's
superblock magic and current cgroup ID. A missing cgroup map permits the
operation; a valid deny list containing that filesystem returns `-EPERM`.
This source does not attach a read hook. It also propagates an earlier BPF
program's error, which is another reason to retain the unrestricted control
and actual identity checks rather than accepting any denial as a pass.

The new worker therefore performs the same direct open/read in both runs,
with the same executable script/hash, argv, SELinux domain and normal unit
settings. The parent observes the held worker and its cgroup and reads the
actual unit properties before allowing it to continue. Only the filesystem
restriction changes. The unrestricted result must return the expected
kernel-version data; the restricted result must record `open`, errno 1,
zero bytes read and no stdout payload. Successful attachment, Enforcing,
the live kernel/BTF/LSM identities and zero observed AVCs remain required.

This tightens the new candidate's causal evidence without rewriting any
earlier failed VM or reclassifying an offline kernel build as a behavioral
pass. The [ARM64 ftrace/trampoline work](arm64-bpf-trampoline.md) supplies the
kernel construction side; the new VM must still demonstrate the actual
attachment and operation. No tablet hardware result is added by this audit.
