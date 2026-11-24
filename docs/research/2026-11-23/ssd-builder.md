# Dedicated SSD work directory for subsequent kernel builds

Date: 2026-11-23, Asia/Shanghai. Evidence class: **host build**.

**The new standard Docker builder is ready.** Its bootstrap completed with
exit code 0 in 617.69 seconds at `2026-11-22T22:54:15Z`. LLVM 19 actually
compiled a small freestanding C source into a little-endian ELF64 AArch64
object. The public Linux archive and reference source manifest were copied
and checked against their expected SHA-256 values.

This record covers infrastructure preparation. It does not replace the
[research1 kernel build result](kernel-build.md), assert a speedup, or establish
that the tablet boots Linux. Subsequent research2 compilation uses a separate
source and output directory and must retain its own result and artifact hashes.

## Isolation and storage

The new container is `tb371fc-build-ssd-20261123`, inside doesvm CT102. It uses
4 CPU equivalents, 8 GiB RAM, an 8 GiB memory-plus-swap limit and a 2048 PID
limit. It is not privileged, has `no-new-privileges` set, runs with Docker's
init process, has no passed-through device or Docker socket, and has no
automatic restart policy.

The base image was already cached and is pinned as:

```text
debian@sha256:a99cfc517144bc59b1978475ec53b46ecabec7e43635402ee5b77cc54cd1b20a
```

The actual base image ID is
`sha256:ec92d6b34c6a7e6372d87dc9ef2fd6e8ca8125353fe7d033c676f51cf923a13b`.
No snapshot of the old container was used.

| Container path | Source and access | Purpose |
| --- | --- | --- |
| `/work` | CT `/tank/hot/tb371fc-build-20261123`, read/write SSD bind | Active source, build outputs, downloads, logs and temporary files |
| `/src` | CT `/workspaces/tb371fc-linux`, read-only bind | Project recipe inputs; each build still pins the files it consumes |
| `/seed/linux-6.12.114.tar.xz` | One public archive from the old work volume, read-only | Verified archive copy into SSD cache |
| `/seed/source-manifest.json` | One source manifest from the old work volume, read-only | Frozen reference for the existing research1 source combination |

The existing `tb371fc-build-20261123` container, its HDD work volume, its tmux
session, and the ongoing Nura builder were not stopped or moved. No host
storage configuration or Docker daemon setting was changed. The two seed
files are the only mounts from the old work volume; its Nix store, private
firmware, module-signing key and user credentials were not copied.

The compiler and installed tools remain in the fresh standard Docker writable
layer, whose backing storage is still HDD. `/work`, including `TMPDIR=/work/tmp`,
is the SSD bind. Thus this change targets the many source and output file
operations in subsequent builds. No measured compilation-speed ratio is
claimed. APT package installation itself took time on the existing Docker
storage and was allowed to complete without a competing second APT process.

## Verified tools and inputs

The [bootstrap script](../../../scripts/research/build/bootstrap_ssd_builder.sh)
installs the kernel toolchain and the generic ARM VM test tools, then checks
their executable versions and performs the compiler probe.

| Tool | Observed version |
| --- | --- |
| Clang / LLD | Debian LLVM 19.1.7 |
| GNU Make | 4.4.1 |
| Bison / Flex | 3.8.2 / 2.6.4 |
| DTC | 1.7.2 |
| kmod | 34.2 |
| Python | 3.13.5 |
| QEMU system AArch64 | 10.0.13 |
| tmux | 3.5a |
| flock | `/usr/bin/flock` present |

The installation also includes the C/C++ build essentials, ELF/OpenSSL
development headers, `dwarves`, `cpio`, `rsync`, compression tools and
`pkg-config`. The exact 258 installed packages are retained in the
[SSD builder package list](evidence/ssd-builder-packages.tsv), SHA-256
`8ac64da0ebd395e10811716dc4682371323166f29acafd1d4ed40e1b0939cee4`.
The base digest is fixed; these APT packages were not obtained from an
immutable repository snapshot. This record does not claim a bit-for-bit
reproducible toolchain layer.

The two copied inputs are:

| SSD path | Bytes | SHA-256 |
| --- | ---: | --- |
| `/work/downloads/linux-6.12.114.tar.xz` | 148,721,296 | `7a8589912bd7a8adb07fed074283652cf482a35facef8954554654f0154b4af3` |
| `/work/reference-hdd/source-manifest.json` | 3,269 | `1a8788a8e5700287870d9e9ca44ad2be8c69e6f28d927321edd89508c5501821` |

The copy operation refuses a symlink or non-file target, and checks the full
content hash before declaring readiness. No full kernel source tree or build
output was migrated. The small compiler probe's object SHA-256 is
`2bbee578ac6b301e6196eb7c5e1dd5a0017df888e434f8dff11e205d3b3530e7`;
its ELF architecture is AArch64 (`e_machine=183`).

## Observable jobs and handoff

The initial package-install/bootstrap command ran as the actual foreground
job of the host user's `tb371fc-ssd-bootstrap` tmux session, through standard
`pct exec` and `docker exec`. Its job metadata and log remain on the SSD as
`ssd-bootstrap.json` and `ssd-bootstrap.log`. Once tmux was installed in the
new container, the script created the separate internal session
`tb371fc-ssd`, window `ready`, with working directory `/work` and
`remain-on-exit` enabled. No existing build session was reused or restarted.

To review or run the subsequent real build jobs in that container session:

```sh
sudo -n /usr/sbin/pct exec 102 -- docker exec -it \
  tb371fc-build-ssd-20261123 tmux attach -t tb371fc-ssd
```

The container's normal `PATH` starts with `/usr/lib/llvm-19/bin`, making
`clang` and `ld.lld` resolve to version 19. A login shell can reset that path;
build recipes should retain the verified path or explicitly select the
versioned LLVM tools. Research2 owns `/work/research2-repo` for its private
input overlay and `/work/research2-display` for its new source/output tree.
The read-only `/src` mount is not modified by this handoff.

The [machine-readable builder evidence](evidence/ssd-builder.json) preserves
the provisioning, readiness and completed-job records, their remote content
hashes, the observed Docker mount/resource settings, and the package manifest
reference. It records `hardware_accepted: false` and
`tablet_linux_boot_tested: false`. A ready build environment does not satisfy
any physical-device gate in [whole-device acceptance](acceptance.md).
