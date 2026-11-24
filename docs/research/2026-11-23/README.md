# Independent TB371FC evidence and research builds, 2026-11-23

This contribution adds a second owner's hardware evidence and offline analysis
to the project at base commit `d157b92721fbeeab823f56a677b3593babf3afe6`.
The reference system is Lenovo TB371FC, Android 14, kernel
`4.19.157-perf+`. Capture timestamps are UTC; this directory uses the owner's
Asia/Shanghai date. See the [Chinese overview](README.zh-CN.md).

**These results answer several board-specific questions without claiming a new
mainline boot, a power saving, working suspend, or a completed driver port.**
The R226 installation/reproducibility limitations in
[INSTALL_CURRENT.md](../../INSTALL_CURRENT.md) still apply.

## Build follow-up and completion standard

The [R5 boot-candidate contract](boot-bundle-contract.md) now provides executable
checks for the frozen 106-file input set, current payload identities and final-root
module dependencies. It keeps native entry/board-root-selection/recovery prerequisites
explicitly open and does not add an owner-tablet Linux pass.

**Current follow-up: the [2026-11-24 R5 runtime checkpoint](../2026-11-24/r5-runtime.md)
records successful run04 construction and both maintenance and production VM
phases. The repaired R5 system reached systemd multi-user with SELinux Enforcing,
runtime module-signature enforcement and all existing production gates passed.
Run03's worker-identity failure remains retained, together with the earlier
[v8 AVC failure](fedora-r4e-persistent-result-failed.md) and
[first v9 image timeout](fedora-r4f-image-failed.md) remain historical failures.
Owner-tablet Linux remains at 0 runs and 0 passes.**

The new `6.12.114-tb371fc-research1` Image, matching modules and native board
DTB have now compiled in an isolated CT102 container. A generic ARM64 VM boot
first exposed an inherited early page-table pool panic; after a board-scoped
fix, the same final Image reached ARM64 userspace. This is a host/VM result,
not a new physical-tablet pass. The base DT still disables native display
and touch, so it is not a completed all-device profile.

The independent `6.12.114-tb371fc-research2-display` candidate has also completed
its full build, matching 83-module inventory and generic ARM64 VM boot. Its
versioned DT enables the native display path with corrected driver matching
and framebuffer ownership, while touch remains disabled. Physical display,
rendering, input and whole-device acceptance remain open.

The follow-up [input integration](input-integration.md) has now compiled two
Novatek fixes and a joint display/input DT. Its 18 source-derived error-path
test groups passed. A separately [signed research2 bundle](input-signed-integration.md)
retains the original Image and 82 original modules, replaces only Novatek,
and includes the joint DT. Offline signature verification and the 63 imported
symbol CRCs match the frozen build; runtime module acceptance and input
behavior remain untested.

The subsequent [research3 system kernel](research3-system-kernel.md) and
[research4 system kernel](research4-system-kernel.md) each have their own full
Image and 84-module qualification. Both retain the same joint display/input
DT and standard Adreno SMMU references. Research4 also resolves the
[ARM64 BPF function-entry dependency](arm64-bpf-trampoline.md); its actual
object contains the required instrumentation. These are build and ABI facts,
with runtime resource-enforcement and physical-device gates kept separate.

The separate [full Fedora system](fedora-system-integration.md) has actually
booted the research1 Image through a corrected dracut initramfs to an ext4
root and systemd multi-user in generic ARM64 QEMU. The final boot used SELinux
Enforcing, an actual loaded version-33 policy and PID 1 in `init_t`; all 83
module and 69 firmware hashes matched. This closes a host system-integration
gap, while the recorded baseline autofs4/pids/BPF-LSM/virtual-GPIO notices
and every physical-tablet hardware test remain separate.

The later [Fedora research3 run](fedora-research3-system.md) remains a recorded
failure before its pids/BPF behavioral tests: `systemd-run --wait --pipe`
encountered a transport reset. The [offline policy queries](selinux-access-query.md)
identify a concrete FIFO access distinction, and the
[copy follow-up](selinux-query-copy-followup.md) preserves the separate PRoot
directory-metadata qualification. The
[first research4 system attempt](fedora-research4-bus-failed.md) also remains
failed: the real broker answered ordinary queries, but even unrestricted
`--wait --pipe true` reset before pids/BPF. A matched-source
[early SELinux investigation and native bootstrap](early-initramfs-selinux.md)
addresses another actual failure: policy and executable labels were absent
from the old initramfs, and a queued udev descriptor was refused after
switching root. The new helper has compiled twice to identical bytes and
passed only its ARM API/negative-entry checks at that checkpoint. The
[subsequent v5 production boot](fedora-r4b-early-failed.md) loaded policy
Enforcing, then stopped at `/var` filesystem association before executing
systemd. The [rootfs/policy source audit](selinux-rootfs-association.md)
explains the different ordinary-tmpfs contract. A new
[pre-policy tmpfs entry and cleanup waiter](tmpfs-initramfs-bootstrap.md)
have compiled and passed limited entry checks while preserving the original
helper. The [actual v6 attempt](fedora-r4c-tmpfs-failed.md) subsequently
observed migration, completed old-root cleanup and same-boot `init_t`/`udev_t`
domains. Its full verification still failed on policy/API-label AVCs and
manager-side FIFO rejection with truncated descriptors; pids/BPF workers did
not run. The raw partial observations and original failed aggregate are both
retained, with no complete-system or hardware pass inferred.

The follow-up [reload and three-recipient permission audit](selinux-runtime-contract-query.md)
keeps broker, PID 1 and worker rights separate. The initial
[map-only policy build](selinux-policy-map-candidate.md) preserves its own
complete single-permission comparison, but the
[postreload check](selinux-postreload-contract-query.md) found two further
same-type process rights missing. A separate
[combined policy build](selinux-policy-map-self-candidate.md) now adds exactly
policy `map` plus `init_t` to `init_t` `setcurrent`/`dyntransition`. Complete
version-35 and fresh-version-33 CIL comparisons exclude every other rule or
constraint change; original context/config payloads remain unchanged. An
[independent 54-row query](selinux-postreload-combined-query.md) confirms the
required permission subset while retaining both denial controls.

The separate [V2 loader](early-selinux-reload-loader.md) has compiled and
passed non-PID1 rejection. Its original map-only build record is retained;
the new combined policy is the same length and requires a separate full-hash
archive/runtime binding. Those construction records retain their original scope.
The [actual v7 result](fedora-r4d-reload-fd-failed.md) now observes successful
standard reload/context setup and same-boot API/journal labels. The real
system-bus held-worker route forwards all three qualified FIFO descriptors;
its controlled noop exits 0. `TasksMax=3` admits two children, rejects a third
with `EAGAIN`, records `pids.events:max` changing from 0 to 1 and reaps them.

**The complete v7 verification still fails.** An incorrect PL061 driver-directory
check stops the workload sequence; the correct runtime sysfs binding was not
read. Two visible Enforcing AVCs and corrupted JSON progress frames remain
failures. The raw log contains two positive attachment messages qualified by
the [matched systemd source](systemd-bpf-runtime-contract.md), but neither the
baseline proc-open nor the restricted `EPERM`/zero-byte test ran. The actual
same-boot policy export is retained separately from offline conversions.
Independent follow-up construction and the actual v8 result are recorded
below. No old result or physical-tablet case is upgraded.

The [standard-service permission diagnosis](selinux-varlink-cleanup.md)
queries both the offline candidate and actual retained v7 policy bytes. It
confirms the two observed link/socket denials and the required next
`connectto` check; the latter was not an AVC reached in this run. The fixed
client needs no target-socket `getattr`, and the original labels are correct.
These 32-query subset results do not establish whole-policy equivalence.

The next independent [standard-service policy](selinux-standard-service-policy.md)
has now completed construction and complete original/candidate CIL comparison.
Only six permissions in five allow tuples change, including the three
source-qualified service gaps; original contexts, booleans and all other
policy rules remain intact. A separate [86-row offline query](selinux-standard-service-av-query.md)
finds every required right allowed and all retained denial controls intact.
Those rows contain 79 unique tuples and come from one query execution; they
are not 86 independent tests or an observation of live services.

The [audit visibility review](audit-observability.md) explains why the old
shared printk suppression cannot establish a complete absence of AVCs. The
separately [compiled V3 loader](early-selinux-standard-services-loader.md)
requires an explicit generic-VM opt-in and actual device-tree compatibility
before changing only that limiter's interval, with fresh readbacks before
policy loading. Its 72,528-byte ELF and the new [cleanup waiter V2](tmpfs-waiter-v2.md)
have passed their limited non-PID1 checks. Archive/profile checks still must
pin both full ELF hashes and the policy hash; length checks are insufficient.
These construction records retain their original limited scope; the separate
actual run below supplies the new runtime observations.

The [actual v8 result](fedora-r4e-persistent-result-failed.md) now completes
all defined guest behavior and ordinary-file transport checks, but **still
fails overall**. The real bus and three-FD route work; four actual routes each
check 82 live-policy tuples. These matrices remain separate from the single
86-row/79-unique-tuple offline candidate query. TasksMax again admits two
children, rejects the third with `EAGAIN`, advances max-events 0 to 1 and
reaps every owned child. The same-worker BPF comparison reads 181 bytes
unrestricted and returns **`open`-stage `EPERM`/errno 1 with zero bytes** under
`RestrictFileSystems=~proc`. Actual `pl061_gpio` binding, all 84 module and 69
firmware hashes, signature enforcement, loaded autofs4 and taint 0 are checked.

The 413,706-byte guest result survives normal QEMU shutdown and fixed-path,
read-only extraction with exact metadata/hash/boot/profile checks. There is
no parse error, and all configured production loss/suppression counts are
zero. One visible Enforcing AVC nevertheless remains: `journalctl_t` is
denied self `unix_dgram_socket create` during `journalctl --sync`, even though
that command exits 0. The unchanged host controller stays false and the
pipeline exits 1. The subsequent source diagnosis, new candidate and failed image attempt are separately recorded below.
The actual exported policy `9d7aa2b3…` is retained privately with public
metadata; it is not equated to the offline conversion. Post-qualification,
finalization and postboot e2fsck did not run. No positive udev count pair
proves an empty or completely preserved queue. The earlier synthetic
transport checks do not establish recovery after abrupt termination.
Every physical-tablet case remains unchanged.

### Subsequent construction checkpoint

The [matched socket-probe diagnosis](selinux-journalctl-socket-probe.md) now
identifies the v8 datagram denial precisely. The fixed systemd path creates a
socket to test xattr support; the kernel rejects the attempted `user.*` xattr
on that special inode before its LSM xattr hook. A direct query of the saved
actual v8 policy confirms the gap. The independent
[seven-permission candidate](selinux-socket-probe-policy.md) adds only self
datagram `create` to the prior six permissions. Complete version-35 and fresh
version-33 CIL comparisons and a 19-tuple offline matrix pass, with 12 denied
controls/diagnostics retained. The independently
[compiled V4 loader](early-selinux-socket-probe-loader.md) and its non-PID1
rejection are construction evidence; the old v8 result remains failed.

The [first v9/R4F attempt](fedora-r4f-image-failed.md) then fails **before any
VM**. Its new production and maintenance archives pass their original checks,
but `mkfs.ext4` exceeds the unchanged 600-second subprocess deadline. The image
phase records 615.382 seconds including cleanup, and the pipeline exits 1.
The source, full traceback and partial image remain retained. No new live
policy, FD, TasksMax, BPF or zero-AVC result follows; a separate recovery must
report its own outputs. Concurrent HDD work is context, not a proven exclusive
cause of the timeout.

The separate [research5-services kernel](research5-services-kernel.md) has now
completed a full build and offline qualification. Its exactly 14 semantic
configuration changes supply the original Nix/Nura nftables requirements,
Nura's explicitly selected zstd zram backend, the generic PL031 RTC and the new
release. The 84 signed modules, all 4,308 imported CRCs, Image/BTF/public
certificate and unchanged joint display/input DT are checked. All 106 ordinary
files transferred into the shared builder match source before/after and
destination contents, modes and owners. This is **not an R5 system boot**:
original firewall rules, OpenRC services, zram, RTC and native module loading
still require actual runtime observations. No owner hardware case is closed.

The [bounded Nura entry inventory](nura-entry-inventory.md) separately confirms
the original BusyBox PID1 and inittab-driven OpenRC sequence. It executes no
target binary and does not turn retained service definitions or the earlier
generic rootfs export into a successful target boot.

The [NixOS follow-up](nixos-system-build.md) has now actually realized the full
fixed `system.build.toplevel`: 894 reference-closed store paths, totalling
3,751,712,072 NAR bytes. ARM systemd `--version` and generated-script syntax
checks passed under explicit PRoot/QEMU. No NixOS rootfs image, activation,
PID 1 boot or integration of the research kernel/modules/private firmware
has been performed. This advances the earlier selected-package checkpoint
without claiming a booted tablet system. An independent rootfs/VM experiment
is being prepared outside this frozen evidence set and has no boot result here.

The [first native Nix registered-root preparation](nixos-store-preparation-failed.md)
now has a definite failure record: source verification exits zero, then the
signed-cache copy reaches its original 3600-second timeout. The job exits one;
destination qualification, image creation, activation and system boot were not
reached. The old partial cache and full original logs are retained, without
changing `require-sigs`, extending that attempt or scoring an incomplete root.

### Current distro checkpoints

| Candidate | Completed host evidence | Outstanding boundary |
| --- | --- | --- |
| Fedora, frozen research1 system | Full systemd multi-user boot with Enforcing, 83 modules and 69 firmware hashes checked | Baseline resource/GPIO notices remain; no physical tablet |
| Fedora, research3/research4 follow-up | Both 84-module kernels; v8 completes early labels, real FD/TasksMax/BPF behavior, PL061 binding and normal-shutdown result transport | v8 remains failed; the first v9 image times out before any VM; later runtime/finalization and tablet tests remain open |
| [Fedora, R5 run04](../2026-11-24/r5-runtime.md) | New root/initramfs/image; maintenance and production phases pass, with multi-user, Enforcing, signature enforcement, actual TasksMax/BPF behavior and qualified persistent result | Generic virt only; no Lenovo board DT or physical passthrough; native entry, recovery and hardware acceptance remain open |
| NixOS | Full 894-path `system.build.toplevel`; ARM version/syntax checks; separate R5 service-prerequisite build | First signed-cache copy times out after source verification; no qualified root/image, activation or PID 1 boot |
| Nura/postmarketOS experiment | ARM builder installed 382 target packages and exported a checked rootfs; actual BusyBox/OpenRC entry inventory and separate R5 prerequisite build | Target not booted; only 371 versions retained in its earlier offline cache; full reconstruction and hardware integration remain open |

The [early distro build comparison](distro-builds.md) retains its earlier
experiment body and now includes a follow-up status notice. Its original
whole-text hash is recorded there; selected-package and software-graphics
totals in that body are not the latest full-system status above.

The [new first-stage reconstruction](first-stage-reconstruction.md) also
compiled a public-source 4.19.325 replacement and a default-HOLD rescue
initramfs. The downstream kernel failed before PID 1 in generic QEMU's
Qualcomm SCM path; the same initramfs passed only with the frozen research2
reference Image. A private unsigned Android v2 candidate passed independent
format checks with the owner recovery_a header/DTB/DTBO preserved. It is not
the historical V56.6/R201 chain, and no bootloader acceptance, physical entry,
kexec transfer, rescue transport or AVB trust was demonstrated.

The [actual USB snapshot](usb-transport-readiness.md) then identified two owner
UDCs, both not attached, with Android `g1` configured on `a600000.dwc3` and no
matching gadget enumerated by doesvm. A separate
[owner-UDC ramdisk revision](first-stage-owner-udc.md) fixes the old
exactly-one-controller assumption: it selects only that observed primary and
holds when the target or required metadata is missing/invalid. Ten predicate
fixtures, reference-kernel PID 1 and a new private v2 format check passed;
physical USB binding, entry and recovery remain unverified.
The [fresh paired USB follow-up](usb-transport-followup.md) again found both
owner UDCs not attached and no corresponding host candidate. The
[later 05:18 UTC recheck](usb-transport-recheck.md) retains that bounded
result without inferring cable presence or other hosts. The
[earlier 14:09 Shanghai paired check](usb-transport-recheck-1409.md) again records
that same bounded state; the entry and recovery control gate remains open.

The [earlier 15:46:57–59 Shanghai paired read](usb-transport-recheck-20261123T074657Z.md)
again records both owner UDCs `not attached`/`UNKNOWN`, the same configured
primary and 14 doesvm USB entries without a matching vendor candidate. Both
reads exit 0. It establishes no data/recovery link and changes no USB or boot
state; it does not diagnose a cable or another host.

The [latest 17:36:24–25 Shanghai / 09:36 UTC paired read](usb-transport-recheck-20261123T093624Z.md)
again exits 0 on both ends: both UDCs remain `not attached`/`UNKNOWN`, `g1`
retains `a600000.dwc3` and `17ef:7e31`, and doesvm has 14 entries without a
corresponding vendor candidate. This establishes no data/recovery link and
changes no USB or boot state. Cable failure, physical connection and another
host's state are not inferred.

- [Research5 original-service kernel prerequisites, full build and shared transfer](research5-services-kernel.md).
- [Matched journalctl socket-probe diagnosis](selinux-journalctl-socket-probe.md),
  [minimal seven-permission policy](selinux-socket-probe-policy.md),
  [V4 loader construction](early-selinux-socket-probe-loader.md) and
  [retained v9 image failure before any VM](fedora-r4f-image-failed.md).
- [Original Nura BusyBox/OpenRC entry inventory](nura-entry-inventory.md).
- [Actual kernel build, failure/fix and VM retest](kernel-build.md).
- [Native 6.12 DT/driver qualification and framebuffer fix](diagnostic-dt-profiles.md),
  [independent display candidate](research2-display-build.md) and [SSD builder](ssd-builder.md).
- [GPU acceleration audit and runtime evidence requirements](gpu-acceleration.md).
- [Owner numeric GPU chip ID and current Adreno SMMU contract](gpu-chipid.md).
- [Research3 full system-kernel build](research3-system-kernel.md),
  [ARM64 BPF dependency correction](arm64-bpf-trampoline.md) and
  [research4 full system-kernel build](research4-system-kernel.md).
- [Compiled input fixes and joint DT](input-integration.md), followed by the
  [signed module/DT/kernel composition](input-signed-integration.md).
- [Actual private GPU firmware staging, public manifests and tests](firmware.md).
- [Canonical 69/70-file stock firmware staging and unresolved radio selection](stock-firmware-staging.md).
- [Bounded cached WLAN version read and exact limits of board-selection evidence](radio-board-selection.md).
- [CNSS IPC interface limits](radio-ipc-readiness.md),
  [kprobe capability boundary](radio-probe-capabilities.md) and
  [actual shipping-kernel tracepoint/CNSS cache audit](cnss-shipping-static.md).
- [Early distro build comparison](distro-builds.md), [Fedora experiment](fedora-build.md)
  and [Nura experiment](nura-build.md); [NixOS configuration](../../../distros/nixos/README.md).
- [Full NixOS system-store build, with the system-boot gap kept explicit](nixos-system-build.md),
  and [the original registered-root preparation timeout](nixos-store-preparation-failed.md).
- [Full Fedora systemd/Enforcing VM](fedora-system-integration.md),
  [fixed-policy compatibility](selinux-compatibility.md) and
  [independent packed-initramfs checks](evidence/initramfs-validation.json).
- [Retained Fedora research3 system failure](fedora-research3-system.md),
  [retained first-research4 broker/udev failure](fedora-research4-bus-failed.md),
  [offline SELinux access queries](selinux-access-query.md) and their
  [copy qualification follow-up](selinux-query-copy-followup.md).
- [Matched-source early SELinux audit and native bootstrap](early-initramfs-selinux.md),
  [retained v5 rootfs-association failure](fedora-r4b-early-failed.md),
  [fixed rootfs/policy audit](selinux-rootfs-association.md) and
  [new pre-policy tmpfs bootstrap](tmpfs-initramfs-bootstrap.md) and
  [retained v6 partial progress and complete-system failure](fedora-r4c-tmpfs-failed.md).
- [Reload and complete receiver-policy contracts](selinux-runtime-contract-query.md),
  [retained map-only policy build](selinux-policy-map-candidate.md),
  [its remaining same-type permission gap](selinux-postreload-contract-query.md),
  [new combined policy/full comparison](selinux-policy-map-self-candidate.md) and
  [independent combined-permission query](selinux-postreload-combined-query.md),
  [separate V2 loader construction](early-selinux-reload-loader.md) and
  [matched BPF behavior contract](systemd-bpf-runtime-contract.md).
- [Actual v8 guest/transport progress and retained one-AVC full-system failure](fedora-r4e-persistent-result-failed.md), with [complete guest evidence](evidence/fedora-r4e-persistent-result-failed-guest.json) and [unaltered production serial](evidence/fedora-r4e-persistent-result-failed-verify.log).
- [Actual v7 progress and retained complete-verification failure](fedora-r4d-reload-fd-failed.md), with [exact exported-policy metadata](evidence/fedora-r4d-loaded-policy-export.json).
- [Whole-device acceptance runbook](acceptance.md) and [machine-readable ledger](acceptance.json).
- [Actual entry prerequisites and verified off-device backups](boot-readiness.md),
  plus [matched R241 diagnostic module compilation](r241-build.md).
- [First-stage source, toolchain and private-intermediate dependency audit](entry-source-audit.md).
- [New public first-stage build, retained VM failure and format-only v2 candidate](first-stage-reconstruction.md).
- [Actual USB transport snapshot](usb-transport-readiness.md) and
  [paired follow-up](usb-transport-followup.md) and
  [later bounded recheck](usb-transport-recheck.md) and
  [14:09 Shanghai paired check](usb-transport-recheck-1409.md),
  [earlier 15:46 paired read](usb-transport-recheck-20261123T074657Z.md), plus the
  [independently qualified owner-UDC rescue revision](first-stage-owner-udc.md).
- [Frozen kernel firmware requests, effective device states and loader rules](firmware-kernel-contract.md).
- [Verified private transfer and structure of 118 selected stock firmware files](stock-firmware-bundle.md).
- [Owner-specific camera, audio and sensor inventory](android-peripheral-inventory.md).
- [Shipping TFA cached selection](tfa9894-cached-metadata.md) and
  [independent unsigned TFA module prototype](tfa-module-prototype.md).

The owner's definition of completion requires every fitted device to operate
at its best demonstrated state, with measured stock comparisons where
appropriate. Enumeration, a successful build, software rendering, disabled
hardware or an unmeasured power claim do not satisfy that requirement.
The measured completion target is Android parity or better for matched
throughput, latency and energy, with intact features, thermal policy, isolation
and recovery. Measurement uncertainty is frozen before Linux comparisons;
inconclusive evidence cannot be converted into a pass by relaxing the target.
Revision 8 of the ledger still has **44 cases: 12 blocked and 32 not run,
with zero owner native-Linux runs and zero hardware passes**. A `not_run`
case may also depend on a blocked prerequisite.

## Findings

| Question | Evidence obtained | Consequence |
| --- | --- | --- |
| Which panel is fitted/selected? | The current Android selector chooses the Tianma NT36532 path; its DT and four advertised DRM modes are attached | Compare this exact path before changing native display initialization |
| How does Android group DSC slices? | The selected live DT specifies `slice-per-pkt = 1` | Review the later 6.12 export's two-slice packet change; it is not yet proven to cause the historical half-screen corruption |
| Are the Tianma ON payloads still missing? | All 86 vendor payloads match the checked-in 6.12 source; the captured table contains 88 records including Sleep Out and Display On | Further work should prioritize transport, topology, transitions and power sequencing, rather than guessing a new vendor table |
| Does shutdown match Android? | Android declares HS OFF commands with 15 ms and 60 ms waits; the current native path differs | Reconcile command state and waits before relying on blank/unblank or suspend |
| Does the panel have pen-related mode commands? | The saved 144 Hz pen table differs at `B3` from the 30/60/120 Hz tables | Treat display-mode and pen acceptance as a joint test; register semantics remain unproven |
| Is the keyboard protocol unknown? | A 604-byte I2C-HID descriptor identifies touchpad, keyboard and consumer collections | Reuse HID infrastructure; validate board wake/reset, IRQ and attach lifecycle |
| Can another Lenovo cover's status parser be reused? | This cover is `17ef:6175` and has no Input report ID 6; the inspected donor side channel targets `17ef:6127` | Do not copy that parser based only on the manufacturer |
| Is a pen-charging implementation available to study? | CTN730 is bound on the actual device and GPL downstream source exists | Study its lifecycle and mainline binding separately from Novatek inking and Bluetooth controls |
| Is this Android capture using USB PD? | Runtime fields say HVDCP 3 and `pd_active = 0`, despite two generic PD labels | Class labels are insufficient to validate a PD contract |
| What does a short power trace establish? | An isolated low-volume trace retained 196 CPU-frequency, 12 GPU-frequency and 18 GPU-state events with no reported buffer loss | It provides a bounded Android baseline, not residence time, battery efficiency, FPS or a sleep test |
| Can the historical motion-sensor identity be reused? | This owner's SensorService reports TDK-Invensense `icm4x6xx` acceleration/gyroscope entries, differing from the historical Bosch BMI3x0 row | Confirm driver and orientation choices from this owner's evidence; declared rates are not measured performance |
| Are camera and amplifier variants now established? | Two cameras enumerate and four `tfa98xx` I2C clients have drivers bound; a later shared HQ slot reports `tfa98xx_QS.cnt` | The slot is registered before load completion and is not four independent choices; camera/amplifier silicon, calibration and actual capture/playback remain unconfirmed |
| Does `Adreno650v3` require a new `650.3` DT match? | The actual owner numeric chip ID is `0x06050002`, matching the existing `qcom,adreno-650.2` parser/catalog path | The model suffix must not replace the captured numeric patch field |
| Does the current candidate use the historical global GPU page table? | The compiled research1 and later research3/research4 joint DT checks retain `qcom,adreno-smmu`, `dma-coherent` and the GPU's reference to it | Historical R185 removal is not applied; actual per-process isolation and recovery still require a hardware test |
| Are stock firmware files ready for image assembly? | Canonical 69-file ELF and 70-file MDT trees were independently checked, including indexed segment dependencies | WLAN board data, BT ROM selection, TFA containers and runtime authentication remain separate open contracts |
| Does the cached WLAN version reveal the board file? | A bounded read reports FW 1.0.1.0.1596.0 and BDF version/reference/customer/project/revision descriptors | These are not CNSS QMI `board_id` or a selected filename; the candidate pool remains unselected |
| Did shipping-kernel analysis resolve WLAN board selection? | Exact binary analysis confirms helper dispatch and CNSS cache layout; the current IPC and kprobe routes are unavailable | Response-valid bits and lifetime remain unresolved, and the historical filename is not cached; no dynamic probe or arbitrary BDF selection was made |
| Is there a concrete TFA driver build route? | An isolated TFA9894-matching prototype compiled with BTF and 75 matching imported CRCs | It remains unsigned, uninstalled and unexecuted with 35 warnings; routing, container integration and complete persistent-write protection remain open |
| Can the frozen rescue init select this owner's USB controller? | Android exposes two UDCs and configures `g1` on `a600000.dwc3`; the old exactly-one check would hold | A separate fixed-primary ramdisk passes host logic/userspace/format checks; a working cable, host enumeration and recovery path remain unverified |

Detailed evidence, source references and untested questions:

- [Display and native-DRM mapping](display.md)
- [Keyboard, touch and pen](input-and-pen.md)
- [Power, charging and suspend](power-management.md)
- [Applied static driver fixes](static-driver-fixes.md)

The documents also record static source-review findings, including the pen
physical-size inconsistency, negative IRQ error handling, and dual-backlight
probe cleanup. These now have bounded follow-up fixes and successful compilation;
they have not been exercised on this owner's physical tablet under mainline
and are not presented as observed device failures.

## Evidence files

| File | Contents and limits |
| --- | --- |
| [android-stock.json](evidence/android-stock.json) | Reviewed running hardware DT properties with bytes/hash/BE32 interpretations, hardware bindings, descriptor, capability listings, sysfs state and trace capabilities; values were read sequentially |
| [display-summary.json](evidence/display-summary.json) | Offline command/timing comparison derived from that capture |
| [hid-summary.json](evidence/hid-summary.json) | Offline descriptor structure, report lengths, ranges and source hash |
| [power-summary.json](evidence/power-summary.json) | Selected stock values, both trace references, hashes and interpretation limits |
| [android-trace-summary.json](evidence/android-trace-summary.json) | 8.012-second low-volume trace summary; no reported per-CPU loss, zero unparsed lines |
| [android-trace-idle-partial.json](evidence/android-trace-idle-partial.json) | Earlier idle-inclusive trace; buffer overruns explicitly recorded, counts are lower bounds |
| [android-gpu.json](evidence/android-gpu.json) | Stock GPU identity, driver bindings, firmware hashes and ELF layout; no firmware bytes |
| [android-gpu-chipid.json](evidence/android-gpu-chipid.json) / [gpu-dt-contract.json](evidence/gpu-dt-contract.json) | Separate passive owner numeric ID and off-device compiled SMMU linkage; neither is a render or isolation result |
| [android-radio-boot-selection.json](evidence/android-radio-boot-selection.json) | No selection tokens in the inspected retained kernel buffer; no log clear/radio restart and no full-boot or firmware-branch claim |
| [android-radio-version.json](evidence/android-radio-version.json) | Bounded cached WLAN version/BDF descriptors, both parser attempts and pinned getter/selection-source hashes; no QMI board ID or selected filename |
| [IPC capability](evidence/android-radio-ipc-readiness.json), [probe capability](evidence/android-trace-probe-capabilities.json) and [fork tracepoint](evidence/android-tracepoint-capabilities.json) | Fixed owner path/config observations: no IPC endpoint or kprobe route, while the normal tracepoint interface exists; no ring read or probe load |
| [cnss-shipping-static.json](evidence/cnss-shipping-static.json) | Actual backed-up Image helper/cache analysis; no live address or kernel-memory access, and no valid historical board-file assignment |
| [Owner USB snapshot](evidence/android-usb-transport.json) / [doesvm USB snapshot](evidence/doesvm-usb-transport.json) | Two not-attached UDCs and the configured primary on Android, with no matching host gadget at capture time; no role changes or connection test |
| [Paired USB follow-up](evidence/usb-transport-followup.json) / [05:18 UTC recheck](evidence/usb-transport-recheck.json) | Both successful paired reads retain not-attached UDCs and no host candidate; no recovery/temporary boot or inference about cable presence |
| [Latest 15:46 Shanghai paired USB read](evidence/usb-transport-recheck-20261123T074657Z.json) | Both fixed helpers exit0; two owner UDCs remain not attached/UNKNOWN and 14 host entries have no vendor candidate; no role, entry or recovery trial |
| [android-boot-state.json](evidence/android-boot-state.json) | Conflicting Android property and kernel command-line lock states; no raw command line or identifiers |
| [android-boot-capabilities.json](evidence/android-boot-capabilities.json) | Actual `CONFIG_KEXEC=n`, forced module signatures, USB gadget prerequisites and MMC node names; no attempted entry |
| [Local boot-copy manifest](evidence/android-boot-backup-local.json) / [off-device receipt](evidence/boot-backup-off-device.json) | Eight current partitions copied and independently re-hashed on doesvm; no partition bytes published and no restore claimed |
| [boot-header-inspection.json](evidence/boot-header-inspection.json) | Numeric v2 layout, exact kernel/ramdisk/DT component hashes and observed slot differences |
| [GPU ELF staging](evidence/gpu-staging-elf.json) / [MDT staging](evidence/gpu-staging-mdt.json) | Actual package manifests, verified against this owner's captured firmware hashes |
| [kernel-build.json](evidence/kernel-build.json) | Actual source, Image/DT/config/module artifacts and build results |
| [research2-display-build.json](evidence/research2-display-build.json) | Independently built display candidate, exact native DT, configuration and 83-module checks |
| [research2-display-qemu.json](evidence/research2-display-qemu.json) | Successful generic virt boot of that candidate; no native display DT was passed to the VM |
| [Research3 kernel](evidence/research3-system-build.json) / [research4 kernel](evidence/research4-system-build.json) / [research4 verification](evidence/research4-system-build-verification.json) | Independent full Image, 84-module/CRC/CMS/BTF qualification and unchanged joint DT; runtime probes are separate |
| [entry-source-audit.json](evidence/entry-source-audit.json) | Actual source/file/API evidence for the unresolved first-stage build chain |
| [first-stage-reconstruction.json](evidence/first-stage-reconstruction.json) | New 4.19.325 build and static rescue tools, retained downstream VM failure, reference-kernel userspace-only success and private format-candidate metadata; no physical entry |
| [first-stage-owner-udc.json](evidence/first-stage-owner-udc.json) | Separate fixed-primary rescue ramdisk, ten mocked selector cases, reference-VM raw serial and new private v2 format metadata; no physical USB or entry pass |
| [firmware-kernel-contract.json](evidence/firmware-kernel-contract.json) | Exact research2 source/config/DT request rules; disabled consumers and unselected board/ROM variants remain explicit |
| [stock-firmware-bundle.json](evidence/stock-firmware-bundle.json) | 118 privately archived vendor files, source/receiver hashes and six ELF/MDT file-set checks; no firmware bytes or load/authentication claim |
| [stock-firmware-staging.json](evidence/stock-firmware-staging.json) | Actual 69/70-file canonical manifests and rejection checks; bounded Android radio metadata is separately scoped within the same file |
| [input-integration.json](evidence/input-integration.json) / [signed composition](evidence/input-signed-integration.json) | Compiled driver fixes/joint DT, 18 source-derived groups, matching ABI and verified signature; no running-kernel load or physical input |
| [selinux-compatibility.json](evidence/selinux-compatibility.json) | Actual fixed-policy conversion in memory, separately from a kernel policy load |
| [fedora-system-integration.json](evidence/fedora-system-integration.json) / [packages](evidence/fedora-system-packages.tsv) | Full generic-system boot with research1, 367 packages, loaded policy 33, Enforcing/init_t, runtime hashes and retained failures/warnings |
| [Fedora research3 failure](evidence/fedora-research3-system.json) | Retained descriptor-transport failure before pids/BPF behavior; Enforcing/hash preconditions do not make the whole attempt pass |
| [First Fedora research4 failure](evidence/fedora-research4-bus-failed.json) / [raw verification serial](evidence/fedora-research4-bus-failed-verify.log) | Ordinary broker queries succeed but unrestricted FD transport resets; a distinct early udev queued-event descriptor is lost; no pids/BPF worker ran |
| [SELinux access queries](evidence/selinux-access-query.json) / [copy follow-up](evidence/selinux-query-copy-followup.json) | Fixed offline policy distinctions and separately qualified PRoot metadata/copy effects; no live policy change |
| [early-initramfs-selinux.json](evidence/early-initramfs-selinux.json) | Frozen SRPM/source audit, same-process ARM helper builds and API-only checkpoint; the subsequent failed PID 1 run is separate |
| [v5 rootfs-association failure](evidence/fedora-r4b-early-failed.json) / [archive qualification](evidence/fedora-r4b-early-initramfs-validation.json) | The archive passed, policy loaded Enforcing, then /var association failed before systemd; no pids/BPF worker ran |
| [Rootfs/policy audit](evidence/selinux-rootfs-association.json) / [tmpfs bootstrap construction](evidence/tmpfs-initramfs-bootstrap.json) | Fixed source/policy/tool evidence plus new stage build and non-PID1 checks; no new root migration or full-system pass at these checkpoints |
| [v6 actual attempt](evidence/fedora-r4c-tmpfs-failed.json) / [raw production serial](evidence/fedora-r4c-tmpfs-failed-verify.log) | Ordered root migration/cleanup/domain evidence, then policy/API-label AVCs and manager FIFO/MSG_CTRUNC failure; full result and udev qualifier remain failed |
| [v7 actual attempt](evidence/fedora-r4d-reload-fd-failed.json) / [raw production serial](evidence/fedora-r4d-reload-fd-failed-verify.log) / [actual policy export](evidence/fedora-r4d-loaded-policy-export.json) | Real three-FD route and TasksMax behavior succeed; BPF attachment observed; overall failed with fixture/AVC/framing gaps and no restricted-filesystem workload |
| [v8 actual attempt](evidence/fedora-r4e-persistent-result-failed.json) / [complete guest file](evidence/fedora-r4e-persistent-result-failed-guest.json) / [original controller](evidence/fedora-r4e-persistent-result-failed-verify.json) | Real four-route FD/AV, TasksMax and paired BPF behavior plus normal-shutdown transport; one Enforcing journalctl AVC keeps overall false, with later phases not run |
| [Standard-service policy](evidence/selinux-standard-service-policy.json) / [independent AV query](evidence/selinux-standard-service-av-query.json) | Fresh six-permission candidate with full CIL comparison and all required rights in one 86-row query; no policy load or live service test |
| [Audit observation source](evidence/audit-observability.json) / [guard derivation](evidence/audit-observability-source-manifest.json) | Exact shared printk mechanism and a bounded generic-VM opt-in contract; no runtime sysctl setting or losslessness claim |
| [V3 loader build](evidence/early-selinux-standard-services-build.json) / [negative entry](evidence/early-selinux-standard-services-negative.json) / [waiter V2](evidence/tmpfs-waiter-v2.json) | Actual separate ARM builds, full transfer identities and non-PID1 refusals; subsequent v8 observations and physical entry remain separate |
| [TFA cached metadata](evidence/tfa9894-cached-metadata.json) / [module prototype](evidence/tfa-module-prototype.json) | Bounded owner selection lead plus separate offline driver/ABI build; neither is calibration, playback or all-amplifier acceptance |
| [initramfs-validation.json](evidence/initramfs-validation.json) | Independent parsing rejects the old archive ordering and accepts the corrected compressed bytes, firmware, ELF and library-cache contracts |
| [android-peripheral-inventory.json](evidence/android-peripheral-inventory.json) | Filtered owner Android camera/sensor/audio identities and declarations; no capture, playback or native Linux test |
| [Initial VM failure](evidence/kernel-qemu-initial.json) / [fixed VM result](evidence/kernel-qemu-fixed.json) | Retained generic ARM64 early-boot failure and successful EL0 retest |
| [nixos-build.json](evidence/nixos-build.json) | Earlier evaluation/selected ARM64 closure checkpoint and its then-missing-artifact gate; retained unchanged |
| [nixos-system-build.json](evidence/nixos-system-build.json) / [store paths](evidence/nixos-system-store-paths.tsv) | Later actual full system-store realization and 894-path inventory; ARM version/syntax execution only, with no NixOS rootfs or PID 1 boot |
| [SHA256SUMS](evidence/SHA256SUMS) | Integrity of the published evidence files, not a boot-image manifest |

The collector excludes serial numbers, MAC addresses, credentials, network
profiles, raw input streams, unrelated process names and firmware binaries.
Two Novatek manufacturing-test threshold matrices were additionally removed
from the publication copy; the JSON records that transformation. The private
transport capture is not a public distribution of Android partitions or firmware.
The snapshot's collector hash identifies the acquisition revision before that
additional omission was implemented in the reusable collector. The reusable
collector was subsequently tightened to an explicit DT property allowlist;
unknown properties retain names only, with no values or hashes. Failed, empty
or oversized command output is recorded as unavailable rather than accepted
or silently truncated. These changes do not rewrite the saved acquisition.

The initial acquisition attempted `/sys/power/wakeup_count`, whose read blocked
in `pm_get_wakeup_count`; no successful capture is attributed to that attempt.
The final collector omits this suspend synchronization interface and bounds
individual reads. An initial trace exceeded a 2 MiB text cap and was discarded;
its private instance was removed. The saved idle-inclusive trace used a larger
read bound but had overruns, so a separate low-volume capture was collected.
The failed and partial attempts are not silently promoted to complete samples.

## Reproduce the observations

The Python helpers require only the standard library. Use the tablet's existing
root access and Python; no installation, SELinux change or driver rebinding is
performed by the helpers. Keep captures private until reviewing their contents.

```sh
# In an already authorized Android root shell, with Python available:
python3 collect_android_hardware.py > android-stock.json

# Uses a new tracefs instance, never the global trace buffer.
# Defaults to an 8-second low-volume profile, then removes its own instance.
python3 capture_android_trace.py --seconds 8 > android-trace-summary.json

# Optional, high-volume idle events; check per-CPU loss counters before use.
python3 capture_android_trace.py --seconds 8 --cpu-idle > android-trace-idle.json
```

The scripts are [collect_android_hardware.py](../../../scripts/research/collect_android_hardware.py)
and [capture_android_trace.py](../../../scripts/research/capture_android_trace.py).
Root access does not make every read-only-looking sysfs file passive: the
downstream CTN730 `cn_test` getter initiates a test. This is why the collector
does not recursively read arbitrary device attributes, debugfs or register
interfaces. It never records keystrokes or pen motions.

Both saved trace runs report that the global tracer settings were unchanged
and their private instance was removed. A normal exception or handled signal
also runs cleanup. Power loss or SIGKILL cannot run Python cleanup; after an
interrupted process, inspect only the instance created by that invocation.

The reusable trace helper now samples power attributes only before and after
the active trace interval, so slow sysfs reads do not extend that interval.
It preserves cleanup evidence in JSON even after capture failure and exits
nonzero when capture or verification fails. The saved acquisitions predate
this revision and contain four sequential power samples; their actual elapsed
intervals and original evidence have been retained. Scheduling delays remain
possible, so use `observed_seconds` rather than assuming the requested duration.

Offline analysis on a development host:

```sh
python3 scripts/research/display_decode.py commands \
  --capture docs/research/2026-11-23/evidence/android-stock.json \
  --node /soc/qcom,mdss_mdp@ae00000/qcom,mdss_dsi_panel_spinel_tianma_nt36532_dsc_3k_video/qcom,mdss-dsi-display-timings/timing@0 \
  --property qcom,mdss-dsi-on-command

# The HID tool accepts a saved binary/hex/base64 descriptor, never /dev/input.
python3 scripts/research/hid_report.py --help

python3 scripts/research/test_research_tools.py
```

No captured mode name or enabled tracepoint demonstrates an active refresh
rate. No capability listing demonstrates actual pen pressure or palm rejection.
The short traces did not exercise a controlled screen-off or suspend cycle.

## Next changes and their acceptance

1. Select and bind the intended native kernel/DT/module/rootfs/initramfs and
   firmware manifests to a demonstrated owner entry/recovery route. Several
   components now exist and have host checks, but their exact owner-board boot
   combination is untested. The default-HOLD format candidate is not a boot
   or AVB acceptance result; historical transforms are not a stackable patch queue.
2. Reconcile one-slice packetization, dual-DSI/DSC/CTL allocation and source
   fetch splitting. Require a real frame on both halves before mode transitions.
3. Review the now-confirmed OFF/pen-mode differences and explicit resource
   ownership, then test blank/unblank and display/pen transitions together.
4. Verify keyboard cold attach, detach/reattach and IRQ behavior on that kernel;
   verify pen motion, pressure, tilt and hover with an attended test.
5. Port charging with a single owner for Type-C/charger policy, preserve thermal
   and watchdog behavior, and validate the actual negotiated protocol.
6. Establish repeated suspend/resume with before/after counters, wake reason,
   input restoration and a measured battery-energy delta under fixed conditions.

These are follow-up hardware/driver tasks, not completed results of this data
collection. No image was flashed and no new mainline kernel was booted on this
owner's physical tablet in this round; the generic VM result is recorded above.
