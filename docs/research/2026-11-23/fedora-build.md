# Fedora 45 ARM64 userspace: completed assembly and emulated graphics checks

## Result

The signed Fedora 45 ARM64 container root filesystem was extended with **160
packages**, including Mesa 26.2.7, its Freedreno and Turnip components, EGL/GBM,
Weston 15.0.1, Vulkan Tools and input/Wayland utilities. The normal DNF/RPM
transaction completed successfully **with scriptlets enabled**. Installed-package
dependency checks, RPM database verification, verification of the selected
graphics packages, and seven dynamic-link checks then passed.

The assembled ARM64 userspace also performed real software graphics work under
QEMU user emulation: an EGL pbuffer clear and exact pixel readback, a running
Weston compositor with communicating Wayland clients, and an eight-frame Vulkan
cube run through Lavapipe. This goes beyond package-file presence.

**No Adreno hardware, native DPU/DSI output, GPU memory isolation or video engine
was validated by this experiment.** Turnip's packaged library and dependencies
are present, but selecting the Turnip ICD in this environment found no GPU and
returned an initialization error. The installed ICD's advertised API version is
not a measured Adreno 650 capability. No tablet was booted or flashed, and no
bootable tablet image was produced here.

The machine-readable record is
[`evidence/fedora-build.json`](evidence/fedora-build.json). The experiment used
doesvm CT102's `tb371fc-build-20261123` container; all experiment files are under
`/work/fedora-*`. `/src` remained read-only, and the main kernel source/output
directories and kernel tmux job were not changed.

## Verified input and execution environment

The seed is the official
[`Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar.xz`](https://dl.fedoraproject.org/pub/fedora/linux/releases/45/Container/aarch64/images/Fedora-Container-Base-Generic-45-1.4.aarch64.oci.tar.xz),
68,993,700 bytes, SHA-256:

```text
bc6c3b3e132e3ed5eff398112d16fcdca13dc8abd63550f8aad40e882b9617b6
```

The Fedora CHECKSUM signature was verified using the official Fedora keyring.
The signed checksum names that exact archive and digest. The Fedora 45 signing
fingerprint is:

```text
4F50A6114CD5C6976A7F1179655A4B02F577861E
```

The original download/unpack job is recorded in `/work/fetch-userspaces-v2.log`
and `.json`; it used `skopeo` and `umoci`. The evidence collector independently
checks the archive digest, its entry in the signed CHECKSUM and the signer. The
working root filesystem is `/work/fedora-bundle/rootfs`.

Initial ARM64 commands reported RPM 6.1.0 and DNF5 5.4.6.0. The emulator is
QEMU 10.0.13 (`1:10.0.13+ds-0+deb13u1`). The environment is QEMU **user-mode**
execution on the container's existing Linux kernel, not an
ARM64 system VM or a boot of the TB371FC kernel. Weston's log reports the host
kernel release `7.0.14-26-pve`; its emulated `aarch64` machine string must not be
mistaken for a tablet boot result.

## Two execution-layer problems were reproduced and resolved

### Direct QEMU invocation does not cover child execution

Explicitly invoking the ARM64 RPM executable through QEMU in `chroot` worked.
Launching ARM64 Bash that way and asking it to execute `/usr/bin/true` produced
`Exec format error`, with the **child command** returning `126`. Bash itself
subsequently printed the result and exited successfully, so the wrapper job's
exit code alone would have hidden this problem. The raw observation is preserved
in `/work/fedora-preflight.log`.

PRoot's `-q` execution support intercepts subsequent guest program executions
without registering a host `binfmt_misc` interpreter. This capability is
documented by [the PRoot project](https://proot-me.github.io/). No host or CT
binfmt configuration was changed.

### PRoot 5.1 was insufficient for the newer userspace

The Debian-provided PRoot 5.1 binary could execute the nested ARM64 command, but
DNF then claimed that downloaded repository metadata was missing. The file was
actually present, and the failure was independently narrowed down:

| Probe against the same downloaded metadata file | PRoot 5.1 result |
| --- | --- |
| `test -e` | Exit `0` |
| `test -f` | Exit `0` |
| `test -r` | Exit `1` |
| `stat` / `statx` | Reported that the file did not exist |

Disabling zchunk and cleaning metadata alone did not resolve it. The failure is
consistent with the older PRoot's missing modern path-system-call support.
Upstream's release history records the subsequent `statx` and `faccessat2`
support; see the [primary changelog](https://github.com/proot-me/proot/blob/25dc6a3134891f98a79f57ce1c2c1b23ff15cad1/CHANGELOG.rst).

The working solution builds **PRoot v5.5.0** from fixed commit
`25dc6a3134891f98a79f57ce1c2c1b23ff15cad1`, with its uthash submodule fixed at
`e493aa90a2833b4655927598f169c31cfcdf7861`. The new binary passed the readable-file,
`statx`, nested-execution and real DNF repository-query checks. Its captured
binary SHA-256 is
`313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f`.

Native build dependencies were downloaded and extracted into
`/work/fedora-host-tools`; no package was installed into the container root
layer. PRoot's source and build output are in `/work/fedora-proot-src`.
PRoot is a compatibility layer, not an additional security boundary. The
explicit launcher binds only `/proc`, basic null/zero/random devices and DNS
configuration; it does not bind the tablet's devices, `/sys`, host `/run`, or a
DRM device directory. The experiment remains inside the existing build container.

## Actual package transaction and closure checks

The transaction used the official Fedora 45 `fedora` and `updates` repositories
with their normal package-signature checks. Weak dependencies were disabled;
the container's existing `tsflags=nodocs` remained in force. **`noscripts` was
never used.** `SYSTEMD_OFFLINE=1` kept service-manager operations offline while
allowing ordinary package scriptlets and filesystem configuration to execute.

| Component | Installed version |
| --- | --- |
| `mesa-dri-drivers`, `mesa-vulkan-drivers`, `mesa-libEGL`, `mesa-libGL`, `mesa-libgbm` | `26.2.7-1.fc45.aarch64` |
| `weston`, `weston-demo` | `15.0.1-3.fc45.aarch64` |
| `vulkan-tools` and Vulkan loader dependency | `1.4.350.0-2.fc45.aarch64` |
| `egl-utils`, `glx-utils` | `9.0.0-12.fc45.aarch64` |
| `libdrm` | `2.4.134-2.fc45.aarch64` |
| `libinput-utils` | `1.32.0-1.fc45.aarch64` |
| `wayland-utils` | `1.3.0-4.fc45.aarch64` |

The Mesa package versions are also documented by the
[Fedora package service](https://packages.fedoraproject.org/pkgs/mesa/mesa-vulkan-drivers/fedora-45-updates.html);
the authoritative record for this particular build is its installed RPM
inventory and retained package hashes in the evidence JSON.

The installation started at `2026-11-22T21:53:17.693282+00:00`, finished with exit
`0`, and took 482.58 seconds. It downloaded approximately 138.8 MiB and reported
approximately 598 MiB of added installed data. These are package-transaction
figures, not storage requirements or tablet performance measurements.
The original inventory contained 149 RPM packages; the final inventory contains
309, with 160 additions and no replaced packages. All 160 downloaded RPM files
were retained and hashed for the evidence manifest.

The long final interval was a real `shared-mime-info` trigger running
`update-mime-database`, rather than an unhandled foreign executable. That trigger
returned `0`; subsequent icon, fontconfig and GDK-Pixbuf trigger completions also
returned `0`. Scriptlet completion records are preserved in the evidence.
The collected DNF logs contain 108 scriptlet-completion records, all with return
code `0`.

The separate check job returned `0` after:

- `dnf5 --cacheonly check` for declared installed-package dependency consistency.
- `rpm --verifydb`.
- Querying all 13 explicitly requested packages and `rpm -V` on the selected
  Mesa/Weston packages.
- Running the ARM64 dynamic loader's `--list` operation on `weston`, `eglinfo`,
  `vulkaninfo`, Mesa's EGL implementation, GBM, `libvulkan_freedreno.so`, and
  `msm_dri.so` (the complete target list is in the reproduction script).

The checks do not prove every possible optional plugin, desktop service or GPU
ioctl works. They establish that the selected installed dependency closure and
the exercised library-loading paths work in this environment.
The collector additionally verified the ELF64 little-endian AArch64 machine
identifier and hashes of ten selected executables/libraries.

## Graphics execution results

All software-driver selections below were child-process environment settings.
No system-wide graphics override or replacement ICD was installed, and no
Android KGSL userspace binary was introduced.

| Check | Observed result | Scope |
| --- | --- | --- |
| EGL/GLES pbuffer clear and readback | EGL 1.5; Mesa `llvmpipe (LLVM 23.1.5, 128 bits)`; reported GLES 3.2; readback `[64, 128, 191, 255]` exactly matched the expected RGBA8 value; GL error `0` | Real software context, framebuffer clear and readback; not a shader or full API conformance test |
| Lavapipe Vulkan enumeration | Exit `0`; physical-device type `CPU`; renderer `llvmpipe` | Software Vulkan loader/driver operation |
| Weston compositor | Weston 15.0.1, headless backend, explicitly selected Pixman renderer, private Wayland socket | Software compositor and protocol operation |
| `wayland-info` | Exit `0`; compositor, output and xdg-shell interfaces reported | Client/server connection and protocol discovery |
| `weston-simple-shm` | 295 frame callbacks observed before the deliberately bounded five-second stop | Actual wl_shm client activity; timeout/exit `255` is retained in the result rather than disguised as a normal application exit |
| `vkcube --wsi wayland --c 8` with Lavapipe | Exit `0`; requested eight frames; 16 observed `wl_surface.commit` requests | Vulkan application execution and Wayland presentation to the software compositor; commit count is not a measured display frame rate or image-quality comparison |
| Turnip-only `vulkaninfo --summary` | Exit `1`; `vkEnumeratePhysicalDevices` returned `ERROR_INITIALIZATION_FAILED` because no valid GPU was found | No physical Adreno was available; this is not a hardware-acceleration pass |

The successful software smoke job ran from approximately `22:02:09` to
`22:03:32` UTC on 2026-11-22. Its 83.50-second wall time includes emulation,
concurrent build load and a fixed-duration client check; it is not a benchmark.
Weston shut down normally after the harness requested termination.

The installed `freedreno_icd.aarch64.json` points to the distribution's
`/usr/lib64/libvulkan_freedreno.so`. Its `api_version` field is `1.4.354`, but an
ICD manifest describes loader-facing capabilities of a driver build. It cannot
establish that this tablet exposes that API version or any required feature.
The observed `1.4.354` physical-device version in the successful software probe
belongs to **Lavapipe**.

Weston's log explicitly identifies Pixman and reports no explicit-sync support
for this chosen headless renderer. Neither GBM/dma-buf hardware presentation nor
the native tablet display path was exercised. The distinction agrees with
[Weston's documented backend/renderer model](https://wayland.pages.freedesktop.org/weston/toc/running-weston.html).
The cube command's frame-limit and Wayland options are implemented in the
[upstream Vulkan Tools example](https://github.com/KhronosGroup/Vulkan-Tools/blob/main/cube/cube.c).

## Reproduction and retained artifacts

The repository scripts are:

- [`fedora_userspace.sh`](../../../scripts/research/build/fedora_userspace.sh):
  fixed PRoot build, package query/install and closure checks.
- [`fedora_guest_egl.py`](../../../scripts/research/build/fedora_guest_egl.py):
  software-only EGL/GLES clear/readback check, executed by Fedora's ARM64 Python.
- [`fedora_smoke.py`](../../../scripts/research/build/fedora_smoke.py):
  fixed graphics commands, bounded process groups, private Weston instance and
  machine-readable results.
- [`fedora_evidence.py`](../../../scripts/research/build/fedora_evidence.py):
  seed/signature verification, package and ELF hashes, job records and runtime
  evidence collection.

Starting with a fresh verified/unpacked seed and the existing build-container
toolchain, the successful path is:

```sh
bash /src/scripts/research/build/fedora_userspace.sh prepare-tools
bash /src/scripts/research/build/fedora_userspace.sh query
bash /src/scripts/research/build/fedora_userspace.sh install
bash /src/scripts/research/build/fedora_userspace.sh check
python3 /src/scripts/research/build/fedora_smoke.py --work /work --run-id reproduction1
```

Run each long command through `run_job.py` in a dedicated tmux window, as in the
completed jobs. The live experiment executed byte copies under `/work`, because
the repository mount was read-only. Run IDs must be unique; the smoke harness
refuses to overwrite an existing run directory. Its temporary compositor and
clients are cleaned up on timeout or completion.

The initial seed preparation is provided by
[`fetch_userspaces.sh`](../../../scripts/research/build/fetch_userspaces.sh).
It also prepares the separate Nura sources, so an already unpacked Fedora seed
should not be unpacked over the modified rootfs. For an independent repeat, use
a fresh work area and preserve the original experiment.

The top-level requested versions and PRoot source commits are fixed in the
script. The evidence additionally records the full resolved RPM inventory and
SHA-256 values of retained RPMs. Fedora repositories can change: replaying from
the same seed and retained RPM bytes gives a stronger reproducibility basis
than resolving only the top-level package names at a future date. An independent
second full installation or offline cache replay was not performed here.

| Container artifact | Purpose |
| --- | --- |
| `/work/fedora-bundle/rootfs` | Assembled ARM64 userspace |
| `/work/fedora-install.log` and `.json` | Actual normal-scriptlet transaction |
| `/work/fedora-check.log` and `.json` | Dependency/RPM/dynamic-link checks |
| `/work/fedora-smoke.log` and `.json` | Fixed runtime-smoke job |
| `/work/fedora-smoke-primary/result.json` and individual logs | Detailed probe results and exact software/hardware boundaries |
| `/work/fedora-build.json` | Consolidated evidence and package/script hashes |
| `/work/fedora-*.log` / `.json` for earlier attempts | Preserved direct-QEMU and old-PRoot failures, and their fixes |

The consolidated JSON is 140,094 bytes and has SHA-256
`f13c47e6ab15f185fcd2c4050233c9c9e9e51290c65bde1c55bf572a63ee58ed`.
The repository copy was transferred without truncation and independently checked
against the same digest as the container copy.

## Remaining integration work

This Fedora userspace is a usable development and runtime-test foundation. It
still needs the actual device kernel, DTB, modules, correctly staged firmware,
boot/initramfs configuration, session/service setup and physical-device tests.
No full systemd PID1 session, real udev device discovery, KWin desktop, tablet
network/input hardware, suspend or native display modes were tested by the
emulation run.

In particular, Fedora packages cannot resolve the R185 global-GPU-page-table
isolation workaround, prove ZAP authentication/GMU startup, enable working native
dual-DSI scanout, or supply a missing Venus hardware path. Those remain separate
items in [the GPU audit](gpu-acceleration.md), [the display audit](display.md),
[the firmware staging report](firmware.md) and
[the whole-device acceptance ledger](acceptance.json). None of its
`device_linux` acceptance gates should be changed to passed from these
`host_build_and_emulated_userspace` results.
