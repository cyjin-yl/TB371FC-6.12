# R5 transient-worker identity derivation

## Observed failure

The candidate assembled from `28adcae4d9c5ed602a17225c68f5042cf494bd1f`
completed its eight build phases. The real generic ARM64 VM subsequently
completed maintenance labeling, but production verification returned exit 1.
The original closed run is retained in
[run03-failure.json](evidence/r5-worker/run03-failure.json).

Production serial output reached the runtime hash and system-bus checks,
then reported the worker error `worker is limited to the owned research4 ARM64
kernel`. The R5 materializer had updated the parent verifier's root label but
copied the frozen v9 worker unchanged. That worker separately required the R4
kernel release, R4 profile name and R4 root label. Changing only the release
would therefore expose another identity failure immediately afterward.

The original host result also rejected extraction of the persistent guest
failure record. This patch does not weaken the read-only result reader or
reinterpret the original failed run as successful.

## Change

After checking the original v9 source hashes, the R5 materializer now derives
the worker's three exact identities:

| Identity | R5 value |
| --- | --- |
| Kernel release | `6.12.114-tb371fc-research5-services` |
| Profile name | `research5-services-fedora45-derived-v9` |
| Root label | `tb371fc-r5-f45` |

The worker also checks that the profile's kernel release equals the actual
`uname` release and this fixed R5 release. The generated profile continues to
bind the resulting worker's SHA-256. Every source replacement requires one
exact anchor; a missing or duplicate anchor fails derivation.

The original v9 files remain unchanged. ARM64, root identity, generic-VM
compatible, bounded profile, profile digest, nonce, SELinux context, descriptor
observation and parent GO checks remain required. Existing `R4F` protocol
markers and service/proof paths remain consistent across the preserved worker,
parent and result-reader protocol; their names do not select a kernel version.
The SELinux, BPF, module-signature and system acceptance gates are unchanged.

## Verification and scope

The new tests execute `main()` from both the actual frozen worker and the
actual generated worker, using synthetic VM identity and a noop operation.
FD observation and parent GO are fixtures, not runtime evidence. The old worker
reproduces the observed R5 rejection; the new worker accepts the exact R5
contract and rejects the R4 or an unknown release, another architecture,
mismatching profile/root label/profile release/context, bad nonce and wrong
profile digest. The derivation test also verifies the original source hashes
and which generated files changed.

All four new worker tests and the other five non-ext4 recipe tests passed in
the local workspace. The pre-existing ordinary-ext4 fixture could not set its
POSIX ACL xattr in that workspace (`EINVAL`); its requirement was retained for
the normal Linux CI runner and CT102 validation. The existing R5 workflow runs
the complete recipe test suite.

A fresh staged root, profile, initramfs pair and image must be generated before
testing the corrected worker in a VM. The old v3 candidate and failure records
are preserved. This source repair does not establish a production VM pass or
add any physical TB371FC hardware passes.
