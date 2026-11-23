# Owner TB371FC: whole-device Linux acceptance plan

Research folder date: 2026-11-23, Asia/Shanghai. Evidence timestamps retain UTC.
Plan revision: 8. Machine-readable ledger: [acceptance.json](acceptance.json).

**Current outcome: not accepted. There are 44 planned cases, 12 explicitly
blocked and 32 not run; no native-Linux run or hardware pass on this owner
tablet has been recorded.** A case marked `not_run` can still depend on a
blocked prerequisite. That status does not claim it is immediately executable.

This is an attended runbook and evidence contract. It does not execute its
command templates, deploy an image, or grant additional device permissions.
The source review, Android observations, successful host compilation and generic
QEMU execution remain useful evidence within their own limits.

## What “best working state” means here

Acceptance requires every feature actually fitted to this tablet and every
confirmed stock mode needed by the owner to work together in one reproducible
Linux stack. That includes native full-panel output, all verified refresh
rates, ten-contact touch, pen pressure/tilt/hover/buttons and charging, keyboard
and touchpad, Wi-Fi/Bluetooth and the fitted FM receiver, storage, audio, cameras, sensors, charging, sleep and
graphics/video hardware paths. CPU execution, usable memory and data integrity
are also checked.

Performance is compared with controlled measurements on this same tablet's
Android reference, with matched workloads, conditions and uncertainty.
Throughput must reach stock parity; latency and energy must be no worse than
the reference. Measurement uncertainty is specified separately from that goal. “Best”
does not mean a claim of an unlimited or universal optimum. It means meeting
predeclared functional, quality, responsiveness, energy, stability and recovery
targets in named daily-use, high-refresh/pen, media and connected-sleep profiles.
Unmeasured combinations remain outside the claim.

No unresolved functional or isolation regression can be hidden by changing
the test configuration. Software rendering/decoding, a single working panel
half, lower refresh caps, permanently disabled touch/radios/sensors, a global
GPU address space, or slower fallback charging can be useful diagnostics.
They cannot satisfy a case requiring the corresponding full feature. Missing
Linux support never proves a feature is physically absent.

## Evidence levels and current position

| Evidence class | What it can establish | What it cannot establish |
| --- | --- | --- |
| `source_clue` | Driver behavior, DT wiring, donor comparison, offline descriptor/command interpretation, historical project reports | Operation on this owner's tablet |
| `host_build` | A specified build, package/staging check, mock test or generic QEMU result | Tablet boot, signed firmware acceptance, physical GPU rendering or peripheral behavior |
| `device_android` | A bounded observation on the owner tablet's Android reference | Native Linux operation; a passive capability list also does not establish a completed Android action |
| `device_linux` | A measured action on this same tablet using a named immutable Linux stack | Untested hardware combinations, configurations or modes |

The existing Android capture identifies the selected Tianma panel and
2944 × 1840 modes, Novatek touch/pen capabilities, the 17ef:6175 I2C-HID keyboard
cover, a four-contact touchpad, CTN730, QCA6390, SMB5 and MM8013. It contains no
live strokes, attended key/gesture sequence, controlled charge/sleep trial or
performance benchmark. The 8.012-second CPU/GPU trace is bounded Android activity,
not an energy, residency or frame-rate result. The later
boot-capability capture confirms an MMC card with three partition nodes;
its filesystem, negotiated speed and integrity/performance remain unmeasured.

The [current-owner peripheral inventory](android-peripheral-inventory.md)
adds static CameraService/SensorService identities and actual driver bindings.
SensorService advertises TDK-Invensense `icm4x6xx` acceleration/gyroscope
descriptors at 1–400 Hz, rather than the historical BMI3x0 lead; QST `qmc630x`
is advertised at 1–100 Hz. These are family/rate declarations, not chip-ID or
sample measurements. The ams `tcs3408` light/RGB and ROHM `bu52053nvx` Hall
descriptors are also present. The separate unbound `OCH8801-0` DT/I2C candidate
remains unresolved and is not substituted for the Hall service identity.

CameraService ID 0 is BACK with a 3264 × 2448 pixel array and 90° orientation;
ID 1 is FRONT with a 4240 × 3152 pixel array and 270° orientation. Pixel arrays
and AE rate declarations are not output-stream matrices or measured frame
rates. Exact camera silicon remains unconfirmed. Android also exposes one
`kona-qrd-snd-card`, 32 PCM interfaces and four bound `tfa98xx` clients at
0x34–0x37; that does not identify the exact TFA/codec/acoustic variants or prove
speaker/microphone operation. The bound `rtc6226` client and `radio0` interface
add a separate required **FM-01** case. Antenna, reception, routes and Android
functional baseline remain untested; no online radio stream can substitute.
This new evidence expands the plan by one case rather than omitting the tuner.

The later [shipping TFA cache audit](tfa9894-cached-metadata.md) narrows the
container lead: the shared HQ slot reports `tfa98xx_QS.cnt`. The exact shipping
module and kernel show that first-registration metadata is stored before
asynchronous firmware completion. It is not four independent amplifier
selections, a silicon/acoustic inventory, DSP success or calibration evidence.
The separate [TFA module prototype](tfa-module-prototype.md) now compiles
against research4, with BTF and 75 matching imported symbol CRCs. It is
unsigned, uninstalled and unexecuted, retains 35 warnings, and does not change
the 84 signed modules or disabled amplifier DT. Complete persistent-write
protection, DAI/TDM routing and container integration still precede any sound
or power-quality claim.

Research1's base DTB retains disabled DSI1 and touch. The independent
[research2-display build](research2-display-build.md) now has its own complete
Image, exact 83-module set and native diagnostic DTB. Both DSI/PHY links and
the Tianma panel are enabled in that DT, with qualified driver matches; SPI14
and touch remain disabled. The same research2 Image reached the exact release,
`aarch64` and EL0 markers in a generic ARM64 VM. These are actual host build and
VM results; no panel scanout, input event, board handoff or owner Linux boot
has been demonstrated. Device-tree availability is not a driver-probe result.

The later [input integration](input-integration.md) supplies a separately
compiled joint display/input DT and a replacement Novatek module. Patches
0018/0019 remove unsupported donor physical dimensions and repair specific
probe, firmware, IRQ, wake-reference and cleanup paths. Eighteen groups of
source-derived fault-injection checks passed; they are not input samples or
complete controller-recovery tests. The joint DT enables inherited SPI14/touch
without guessed GPIOs or millimetre dimensions. A separate
[signed composition](input-signed-integration.md) contains the unchanged
research2 Image, that DT and 83 modules, with exactly one module replaced.
Its 63 imported CRCs and CMS signature were checked against the frozen build.
The signature has not been accepted by a running kernel in this experiment,
and no physical touch, pen, cover or panel-follower behavior was tested.

The subsequent [research3](research3-system-kernel.md) and
[research4](research4-system-kernel.md) kernels each have a complete,
independent 84-module build with full inventory, 4,308 imported CRC comparisons,
CMS signatures and BTF checks. Both retain the same joint display/input DT.
The [ARM64 trampoline audit](arm64-bpf-trampoline.md) identified research3's
missing native function-entry path; research4 resolves the complete
ftrace/direct-call configuration and its actual `bpf_lsm.o` emits 266
patchable-entry sections. These are host facts. Neither an enabled BPF LSM
name nor instrumentation replaces an actual restricted-operation test.

The [frozen firmware request audit](firmware-kernel-contract.md) makes further
configuration gaps explicit for the original display-only profile. GPU/GMU,
ADSP/CDSP/SLPI and Bluetooth paths are available in that research2 DT. All
three PCIe controllers, SPI14/touch, four TFA amplifiers and Venus are disabled
there; only the separately recorded joint profile enables touch. The generic
TFA989X driver is unset and
does not match TFA9894, so copying acoustic containers cannot complete the
amplifier route. Conditional WLAN board selection, Bluetooth ROM suffixes,
Novatek panel-ID selection and secure firmware acceptance still need runtime
evidence. These static findings do not establish a successful probe or load.

Actual owner-matched GPU firmware staging succeeded in both full-ELF and
packed-MDT forms. This establishes byte provenance and packaging, not
authentication or execution by the GPU. The later
[fixed stock-firmware transfer](stock-firmware-bundle.md) independently verified
118 original files totalling 38,546,828 bytes and all loader-required segment
lengths in six ELF/MDT variants. Its private archive retains original names;
the later [canonical staging](stock-firmware-staging.md) actually produced
verified 69-file ELF and 70-file MDT trees. Indexed siblings were checked again
under their destination names. Both Novatek revision-6 variants and both
Bluetooth ROM candidate pairs are retained; no arbitrary WLAN board file or
unmatched TFA container was installed. File completeness does not establish
firmware ABI, signatures, services or physical operation.

The owner's fixed radio metadata and
[current retained-buffer filter](evidence/android-radio-boot-selection.json)
did not resolve WLAN board selection or Bluetooth ROM suffixes. The filter
found no selection tokens; it did not clear the log or restart a radio.
Neither the PCI subsystem value nor the `hastings` family property selects a
runtime firmware branch. This bounded negative result is not a full boot trace
or evidence that a device is absent.

The later [cached-version capture and source audit](radio-board-selection.md)
found `/sys/kernel/wifi/wlan/fw/1/version` and read only that bounded attribute.
It reports FW `1.0.1.0.1596.0`, BDF version `0x8`, reference/customer/project
zero and board revision 1. The reviewed public getter formats cached fields;
these are not the CNSS QMI `board_id` or a selected BDF filename. The owner
shipping binary is not proven identical to the public source. No arbitrary
`bdwlan` candidate or Bluetooth ROM pair can be selected from these values.

The [CNSS IPC audit](radio-ipc-readiness.md) then found no approved endpoint
in the running `CONFIG_DEBUG_FS=n` kernel, so it did not read ring bytes or
advance a cursor. The [kprobe capability check](radio-probe-capabilities.md)
blocks that specific route; it does not exclude ordinary tracepoint BPF.
The fixed fork-tracepoint interface exists, and the
[actual shipping-Image audit](cnss-shipping-static.md) confirms the relevant
helper dispatch and unique cached-field chain. However, QMI response-valid
bits are not retained with the cache, its live lifetime was not pinned, and
the historical requested BDF filename is not cached. No dynamic BPF program
or live-memory read was implemented. A default or cached `board_id = 0xff`
cannot by itself identify which firmware request actually happened.

The [new GPU identity comparison](gpu-chipid.md) resolves a separate ambiguity:
`Adreno650v3` accompanies the actual owner DT chip ID `0x06050002`, matching
the compiled `qcom,adreno-650.2` path. The
[actual research1 GPU/SMMU DT](evidence/gpu-dt-contract.json) retains
`qcom,adreno-smmu`, `dma-coherent` and the correct GPU reference. Historical
R185 removal is not applied to this artifact. No restoration patch is needed
to put back a compatible that is already present. Runtime process isolation,
fault containment and recovery remain unobserved; two successful rendering
clients would not alone establish isolation.
The research3/research4 inspectors independently retain that standard SMMU
contract and GPU reference in their unchanged joint DT.

The [earlier distro build comparison](distro-builds.md) retains its experiment
body with a follow-up status notice. The original whole-text hash is recorded
there; selected-package totals and incomplete-system statements in that body
remain historical observations, rather than the latest system-build status.

The older selected Nix ARM64 closure and QEMU hello checkpoint is now followed
by an actual [full NixOS system.build.toplevel realization](nixos-system-build.md).
It completed under explicit PRoot/QEMU in 879.574 seconds, with 894 existing,
reference-closed store paths and 3,751,712,072 NAR bytes. ARM systemd 260.5
`--version` succeeded; generated `init` and `activate` scripts passed ARM shell
syntax checks only. No NixOS rootfs image, activation, PID 1 boot or integration
of the research kernel/modules/private firmware was performed. The explicit
QEMU argument remains emulation even where metadata disables an automatic
wrapper. This is a full store build, with a separate system-boot gap. Fedora's ARM64
package assembly and actual emulated software graphics checks are also host
results. [Nura's native ARM builder](nura-build.md) installed 382 target packages
and exported a 307,393,454-byte generic rootfs archive, followed by a successful
gzip integrity check and cleanup of its owned VM/media server. That target
rootfs has not booted. Its cache retains 371 of the 382 installed package
versions, so offline reconstruction remains incomplete. The generic target's
7.3.5 kernel/modules are separate from both 6.12 research candidates. Each
candidate's build and userspace results remain separate from whole-device
acceptance.

The later [full Fedora system](fedora-system-integration.md) goes beyond the
earlier userspace experiment: the actual research1 Image booted a separate
367-package ext4 root through the corrected dracut initramfs into systemd
multi-user. After an explicit VM-only maintenance labeling boot, the final
boot was SELinux Enforcing with an actual loaded version-33 policy and PID 1
in `init_t`. It rechecked all 83 modules and 69 firmware files, had no failed
units or AVC denials, powered off cleanly and passed offline filesystem checks.
The [archive verifier](evidence/initramfs-validation.json) independently
rejected the retained bad CPIO/gzip ordering and accepted the corrected bytes,
including all firmware, cache entries and ARM ELF files. The earlier
[in-memory policy conversion](selinux-compatibility.md) and this real policy
load have separate evidence. The baseline's autofs4, pids, BPF-LSM and virtual
GPIO notices remain recorded. Generic QEMU used no Lenovo DT or physical
device, so none of these results closes a hardware case.

The later [Fedora research3 attempt](fedora-research3-system.md) remains
failed. It reached its Enforcing and runtime-hash preconditions, but the
`systemd-run --wait --pipe` route reset before pids enforcement or BPF
filesystem-denial tests. This was not the expected BPF-denial outcome.
The separate [offline access queries](selinux-access-query.md) distinguish
allowed descriptor use from denied, unaudited FIFO access and identify the
existing `initrc_t` service route. Their converted policy is not asserted
identical to the policy exported by the VM. The
[copy follow-up](selinux-query-copy-followup.md) also preserves the failed
metadata-raced copy and qualifies a new quiescent copy; PRoot bind placeholders
mean a read-only payload cannot establish a wholly unchanged source tree.

Another retained research4 boot showed an early Enforcing denial when PID 1
tried to retain udev's `kernel_t` queued-event socket after switching root.
That [first research4 attempt](fedora-research4-bus-failed.md) also passed
ordinary real-broker `GetId` and manager-version queries but failed
unrestricted `--wait --pipe true` before pids/BPF workers. Its actual
creator/client/FIFO context was `unconfined_service_t`; only the broker
launcher, not the child, was identified by that old recipe. One early audit
event appears twice textually in its immutable controller/log evidence.
The [matched Fedora source audit and native bootstrap](early-initramfs-selinux.md)
locate the omitted initramfs policy/labels and use the official
load-policy, restorecon and executable-transition path within one process.
A two-process shell proposal was rejected after an actual offline
`execute_no_trans` denial. The new ARM helper built twice to identical bytes
and passed API-only and non-PID1 rejection checks. The subsequent
[v5 production run](fedora-r4b-early-failed.md) is now retained as failed:
the fixed archive passed and policy loaded Enforcing, but restorecon denied
`var_t` to `root_t` filesystem associate at `/var`; PID 1 stopped before systemd.

The [fixed rootfs/policy audit](selinux-rootfs-association.md) explains why
ordinary tmpfs has a different superblock contract and why remounting this
initialized rootfs cannot supply it. A new
[pre-policy tmpfs bootstrap](tmpfs-initramfs-bootstrap.md) preserves e53,
uses the fixed standard switch_root and waits for one cleanup child plus an
empty old-root directory before policy load. Its build, ARM syntax and
non-PID1 checks passed. The [actual v6 attempt](fedora-r4c-tmpfs-failed.md) then
observed the distinct tmpfs root, cleanup completion and same-boot PID 1
`init_t`/udevd `udev_t` sequence. It still failed complete verification:
policy-file mapping and API-filesystem labels produced AVCs, and PID 1
rejected a FIFO descriptor on the real system-bus route, followed by
truncated FD delivery and `InconsistentMessage`. Broker-side permission
checks did not cover this manager recipient. Pids/BPF probes did not run.

The original controller's aggregate migration flag remains false because
the failed attempt has no final guest result. Raw ordered markers and the
independent initrd proof remain valid partial observations; they are not
rewritten into a full-system pass. The udev qualifier also found no positive
count pair, so absence of its error prefixes is not proof of an empty queue.
The retained v6 result and all owner Linux hardware cases remain unpassed.

The [follow-up reload/FD contract](selinux-runtime-contract-query.md) queries
all three recipients independently and keeps a requested worker domain
separate from an observed worker. Its 147/188 offline access-vector results
identify the existing `sysadm_t` route and the original `init_t` policy-file
`map` gap. They do not substitute the unpersisted old `9c79` kernel-export
identity with the fixed offline `aab7` bytes.

The [first standard policy build](selinux-policy-map-candidate.md) adds only
`(allow init_t semanage_store_t (file (map)))`. Its complete comparison and
unchanged context/config inventories remain frozen. The
[53-row postreload audit](selinux-postreload-contract-query.md) then identifies
two further required denials: `init_t` to itself for `setcurrent` and
`dyntransition`. The fixed library's initial setter cache is unset and is not
filled by `getcon`; the kernel does not bypass the two checks for equal SIDs.
That query completed successfully but the map-only permission contract is
incomplete. Neither its exit code nor source analysis is a later VM result.

A [separate combined build](selinux-policy-map-self-candidate.md) starts from
the original complete source store and adds exactly two rules: the existing
map correction and `(allow init_t init_t (process (setcurrent dyntransition)))`.
Complete original/candidate CIL exports for version 35 and freshly converted
version 33 match after only those two substitutions. The 3,835,432-byte binary
changes at three bytes; no other rule, cross-type transition, boolean,
permissive declaration or constraint changes. All 32 original context files
and config remain unchanged. The original 1,766-entry source inventory is
identical before/after including mtime/ctime, and full candidate/store
inventories and the optional context-handle warning are retained. No kernel
policy load or enforcement change was performed.

The [independent 54-vector query](selinux-postreload-combined-query.md) confirms
52 required permissions allowed, while `init_t` policy export and mapping the
old journald file type remain denied. Its independently measured `ce6ccb…`
fresh conversion agrees with the full-comparison process. It is still an
offline serialization, not the assumed identity of a future exported policy.
Actual same-boot bytes and the real receiver/worker/descriptor observations
remain required.

The independently built [V2 loader](early-selinux-reload-loader.md) preserves
its original control flow and passes non-PID1 rejection. Its original build
input was map-only `0dd46a…`; that record stays unchanged. Because both
candidates have the same length, the native size check cannot distinguish
them. The new archive/runtime profile must pin the combined `e1a63e…` full
hash and separately verify its binding to the existing `cc042c…` loader.
The [actual v7 run](fedora-r4d-reload-fd-failed.md) now observes the successful
standard reload and same-type context setup, actual API/journal labels and
the held worker's complete three-descriptor route. Its controlled TasksMax
worker admits two children, gets `EAGAIN` on the third, observes max-events
0 to 1 and reaps them. The same-boot exported version-33 policy `0fe3c0e1…`
is retained separately; it is not assumed equal to offline `ce6ccb…`.

The full production controller still fails. Its first guest exception is a
PL061 check using the wrong driver directory; the correct sysfs observation
was never made. Two visible Enforcing AVCs, six suppressed callbacks and two
corrupted JSON progress frames remain in the original record. Both the
controller and separate udev qualifier retain their failed aggregates.
Independent follow-up corrections are being prepared, without rescoring
this attempt or changing any owner hardware result.

The [subsequent standard-service audit](selinux-varlink-cleanup.md) confirms
three required permission gaps using matched source, original contexts and
two independent 32-row queries. Actual exported `0fe3…` bytes are parsed
directly. Registry-link `unlink` and journal-socket `write` match the two
observed AVCs; journald `connectto` is a predicted next check, not an
invented observed denial. Target-socket `getattr` is excluded because the
fixed short-path connection performs no target stat. The queried subset
agreement does not claim whole-policy equivalence or a repaired runtime.

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

The [matched BPF source audit](systemd-bpf-runtime-contract.md) requires a real
positive attachment and a same-worker denial at `open`, errno `EPERM`, with
zero bytes read. Failure before that call or at an unrelated operation does
not satisfy the restriction test. V7's exact raw serial contains the positive
attachment marker twice but stopped before the workers. The separate v8 run
now supplies both controlled results described above, with the same worker,
live property/FD checks and unchanged policy. Its later journalctl AVC still
fails overall. None of these VM results changes an owner Linux hardware case.

Boot-state evidence needs explicit interpretation: Android properties report
locked/green while the captured kernel arguments report unlocked/orange.
Neither representation alone establishes the intended bootloader state or
safe boot entry. A recovery/boot contract must be demonstrated without guessing
that an unlock or data wipe is required. The final DTB root compatibility also
matters: the scoped early-page-table workaround selects `lenovo,tb371fc`; the
historical recovery overlay keeps generic Kona compatibility and therefore
takes the other allocator branch. A generic-QEMU success does not validate the
Lenovo branch or the final tablet boot/handoff contract. The separately built
initramfs and root image are concrete host artifacts with that boundary.

The [boot-readiness review](boot-readiness.md) now has verified preparation
material: eight current boot/recovery/vbmeta/dtbo A/B partition copies total
461,504,512 bytes. Their local source/copy/source-recheck hashes agree, and the
93,319,878-byte off-device archive has independently checked image hashes.
This closes the missing off-device-copy item. It does not demonstrate restore,
inactive-slot boot, AVB/rollback validity or Linux entry, and it is not a backup
of Android userdata, super or persist. Equal `4.19.157-perf+` release strings
mask different A/B kernel bytes, so entry artifacts must be matched by exact
slot and hash.

The same owner's running kernel has `CONFIG_KEXEC=n`, enforced module
signatures and version checks, and `CONFIG_USB_CONFIGFS_ACM=n`. NCM and
FunctionFS are configured, but their presence is not a demonstrated rescue
transport. Installing a kexec executable or reusing a historical module cannot
supply those missing or incompatible kernel contracts. The exact first-stage,
usable console/recovery route and final board/root-loading integration have
not been exercised. The three-partition card must retain its actual layout;
the author's historical two-partition recipe is not an applicable layout
assumption.

The [first-stage source audit](entry-source-audit.md) also finds an unresolved
build dependency: R226's selector repackages a private R201 recovery, while
the checked `d157b927` checkout lacks nine referenced vendor patches and the
resolved V56.6 source/configuration and ramdisk inputs. No alternative complete
recipe was found in the three enumerated public branches, two distinct heads,
empty tag list and queried path histories. This is a bounded source finding,
not a claim about every old or private source. The public tem423 `9d8abeb`
4.19.325 candidate is accurately identified, but is not V56.6's unknown
4.19.157 source; its inspected defconfig disables KEXEC, ACM and DEVTMPFS.
The owner's backups can supply matched layout/board inputs, but cannot supply
the missing source or turn a new payload hash into a working first stage.

The later [public-source reconstruction](first-stage-reconstruction.md) has
now produced a **new replacement**: `4.19.325-cip134-st18-tb371fc-entry-r1`,
with explicit KEXEC/DEVTMPFS/ACM configuration, four new bounded source fixes,
static BusyBox/kexec/return binaries and a default-HOLD rescue initramfs. It
does not recover the missing historical patch chain. Its actual generic VM
failed in Qualcomm SCM before PID 1; the same rescue initramfs passed its
userspace checks only under the frozen research2 reference Image. Those two
outcomes remain distinct.

An unsigned private Android v2 candidate was also assembled and independently
reparsed with pinned AOSP tools. It preserves the owner recovery_a header,
DTB and DTBO except the necessary recorded size, offset and image-ID fields.
The 53,583,872-byte output has SHA256
`46a4f7c862b3a57ac95c5c11d5e746433d5f78239e1a9900eb77790013256f0e`.
This verifies format and byte provenance only. Several board drivers and a
matching Spinel DTS remain absent from the selected public source; preserved
owner DT bytes cannot prove a driver match. No AVB trust, actual runtime
placement, temporary-boot acceptance, USB rescue transport or kexec execution
was tested. Direct-mainline Android v2 packaging could avoid the bridge in
format, but physical boot entry and cold-boot/handoff compatibility remain
unverified. The candidate stays private and defaults to HOLD.

A subsequent [bounded USB capture](usb-transport-readiness.md) found two owner
UDCs, both not attached, with Android `g1` configured on `a600000.dwc3`; doesvm
did not enumerate the owner gadget. This exposed a specific source mismatch
in the frozen rescue init's exactly-one-controller assumption. The independent
[owner-UDC r2 revision](first-stage-owner-udc.md) selects only the observed
primary when its fixed metadata checks pass, with no secondary fallback or
role change. Ten mocked predicate fixtures passed, and only `init` changed in
the decoded archive. The new userland passed PID 1 under the reference kernel,
with gadget setup deliberately skipped; a new private v2 image passed format
checks. These results do not demonstrate physical USB binding, an owner boot,
a working 4.19 bridge, kexec or recovery. All old artifacts remain preserved.
The [fresh paired follow-up](usb-transport-followup.md) at 04:00 UTC again
finds two not-attached owner UDCs and no corresponding host USB candidate.
It changes no role, gadget or boot state and does not close the entry gate.
The [later 05:18 UTC paired recheck](usb-transport-recheck.md) again reports
both UDCs not attached/UNKNOWN and no host vendor candidate. This does not
establish cable presence or what another host would see. The later
[06:09 UTC / 14:09 Shanghai paired check](usb-transport-recheck-1409.md) again
finds both owner UDCs not attached/UNKNOWN and 14 doesvm USB entries without a
matching vendor candidate. Both reads succeeded; no role/gadget/boot change
or physical recovery test was performed.

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

A [separate standard Docker builder](ssd-builder.md) is also ready with an SSD
work bind, the same 4 CPU / 8 GiB limits, LLVM 19 and a checked AArch64 compiler
probe. Its old HDD predecessor and the ongoing userspace work were retained.
This is build infrastructure evidence; later kernel candidates keep separate
source, output and validation records.

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

The [targeted offline privacy-check regression](evidence/research-tools-mac-boundary.json)
also fixes a token-boundary bug: a 20-byte public module-signing key ID must not
be classified as a six-octet MAC address. The single specified test passes;
no original evidence bytes or hardware acceptance result are changed.

The [first native Nix registered-root preparation](nixos-store-preparation-failed.md)
now has a definite failure record: source verification exits zero, then the
signed-cache copy reaches its original 3600-second timeout. The job exits one;
destination qualification, image creation, activation and system boot were not
reached. The old partial cache and full original logs are retained, without
changing `require-sigs`, extending that attempt or scoring an incomplete root.

## Measurement protocol and proposed thresholds

Record Android baselines before judging Linux. Use the same physical battery,
pen/nib, cover, chargers/cables, dock, card, LAN endpoint and test fixtures.
Keep identifiers private and use stable local aliases in published results.
Freeze application/workload versions and fixture hashes. Match actual active
resolution/refresh, measured luminance and audio level, radio conditions,
charging protocol, starting SOC and temperature, background services and
normal power/thermal policy. Record instrument uncertainty and every failed
trial; do not select only favorable runs.

An initial controlled environment of 23 ± 2 °C, 40–70% SOC and a five-minute
warmup is proposed where appropriate. These are experiment controls, not
manufacturer safety limits. Charging tests need their own fixed comparable
SOC window; brightness numbers from two different drivers are not equal
luminance. Alternate Android/Linux trial order where practical and retain at
least three paired trials. Add repetitions if that is insufficient to resolve
the chosen threshold; inconclusive data stays pending.

| Comparison profile | Proposed target to adopt before Linux testing | Required qualification |
| --- | --- | --- |
| Throughput | Linux median at least the matched Android median: ratio **≥ 1.0** | Comparable CPU/app/compiler and hardware paths; freeze effective precision and the uncertainty/confidence decision rule after the controlled Android baseline and before Linux trials |
| Tail latency | Linux p95 no greater than Android p95: ratio **≤ 1.0** | Same method and sampling; freeze timing uncertainty and precision, with an equivalent absolute parity bound when the denominator is below instrument resolution |
| Energy | Linux energy no greater than Android for the same work/interval: ratio **≤ 1.0** | Calibrated battery energy measurement and frozen uncertainty; USB input watts, unvalidated `charge_counter`, or short SOC-only samples cannot substitute |
| Quality | No regression beyond the adopted metric's combined measurement uncertainty | Freeze actual metrics and tolerances per case: spatial error/jitter, luminance/color, audio noise/distortion, camera quality, sensor bias, and so on |
| Active refresh | Measured cadence within 1% of the owner-verified target | Active DRM/link settings plus independent cadence observation; mode names or generic tracepoint counts alone are insufficient |

The throughput, latency and energy completion target is **stock parity at
ratio 1.0**. There is no default allowance for lower throughput or higher
latency/energy. The measurement methods and other engineering thresholds remain
proposals, not achieved results, product guarantees or universal standards;
every profile starts as `proposed` until its method is qualified. After the
controlled Android baseline, freeze effective precision, the uncertainty and
decision method, the exact metric and timestamp before its Linux trial.
Uncertainty cannot be converted into an arbitrary performance discount. If it
prevents a defensible parity conclusion, record the result as inconclusive.
No target may be loosened after observing a failed Linux result.
A selected desktop-GL feature without an Android equivalent needs
an explicit Linux correctness/conformance target; compare performance only for
a genuinely common workload/API. Unavailable or invalid readings remain unknown,
never numeric zero or an implicit pass.

## Execution order and release gate

1. **Assemble and identify the stack.** Finish one Image/DTB/initramfs/config/
   Module.symvers/modules/firmware/rootfs manifest, resolve entry/recovery and
   record effective enabled devices and diagnostic workarounds. Generic VM
   boot is a host gate; it is not SYS-01.
2. **Establish the owner baseline and minimum native session.** Confirm the
   remaining hardware inventory under Android, then complete boot/recovery,
   CPU/memory, native panel, input, gauge and storage checks under Linux.
3. **Complete independent hardware functions.** Validate Wi-Fi, Bluetooth, FM, USB, audio,
   camera, sensors, CTN730 and charging ownership. Keep absent/unimplemented
   modes visible rather than deleting their cases.
4. **Validate integration and power.** Exercise all refresh/pen modes, GL and
   Vulkan render/readback, compositor presentation, isolation/recovery,
   hardware video, runtime power, suspend and thermal performance. Dependencies
   in the JSON define the actual order; later post-resume checks revisit early
   device gates without creating a dependency cycle.
5. **Run one final configuration.** Recheck gates affected by a stack change,
   then complete the 24-hour mixed-use case. Every applicable required case
   must pass on the same final stack. A changed Image/DT/config/module/firmware/
   rootfs identity starts a new stack ID and invalidates dependent old passes
   until reviewed and retested.

The planned repetition counts and durations are a bounded acceptance campaign,
not a statistical guarantee of failure-free lifetime operation. A regression
stops the affected gate and remains in the result ledger. Hardware-protection
paths use reviewed driver tests and normal operating observations; this plan
does not call for forced overheating, overcharging, raw register guesses or
destructive storage tests.

## Recording a run and validating the ledger

Use [acceptance.json](acceptance.json) as the result ledger. Preserve the
baseline evidence and append new records; do not relabel the existing Android
or host records as Linux results. Each evidence item has a path, SHA256, class,
claims and limits. A controlled Android baseline additionally uses
`controlled_measurement: true` and must actually contain its method/results.

Register each immutable stack in `stack_manifests` with `id`, `evidence_id`
pointing to its reviewed manifest, and SHA256 values for all eight keys listed
in `stack_component_keys`. Tree artifacts use the hash of a complete file
manifest, not a directory name. Linux evidence includes `device_id`, `stack_id`
and `run_id`. A run records start/finish with timezones, profile, repetitions,
conditions-evidence ID and reviewer. Evidence from a VM has class `host_build`
even if it prints a Linux uname.

For each criterion, record `criterion_id`, `met`, `actual`, `unit` and its
Linux `evidence_ids`. Use Boolean `actual: true` for the fixed functional
assertions, with the measurements/observations in their linked evidence; an
unknown or a failed assertion cannot be encoded as true. Every comparison
profile used by the case also needs a `comparison_results` entry containing
the exact metric, adopted target/unit, threshold-freeze timestamp, paired
trial count, Android baseline IDs, Linux evidence IDs, measured actual,
uncertainty and `met`. Store samples and confidence calculations in the
referenced evidence, not just a claimed ratio. Freeze the reusable profile
and case-specific threshold before the Linux start time.

Set `pass` only after all dependencies, criteria, comparisons and repetitions
are satisfied with no open issue or degrading workaround. The same evidence
can support several clearly stated criteria, but its claims must support each
one. `not_applicable` is limited to cases marked `confirm_on_owner_android`:
add `result.absence` with reviewer, reason and controlled owner-Android
absence evidence. A missing Linux driver or unavailable accessory needed by
the owner's use is not absence. Update the decision's unique run and pass
counts from the ledger.

From the repository root:

```sh
# Offline only: structure, references, hashes and evidence/gate rules.
python3 scripts/research/validate_acceptance.py --check-files

# A valid unfinished plan exits 2; it must not be interpreted as acceptance.
python3 scripts/research/validate_acceptance.py --check-files --require-accepted
```

The first command's exit 0 means the ledger is internally consistent. Its
output must still say `hardware_accepted: false` while gates remain pending.
Exit 1 denotes a malformed or inconsistent ledger; exit 2 with
`--require-accepted` means valid but incomplete. The validator does not execute
the command catalog, authenticate a measurement, judge arbitrary narrative
evidence or replace review of the recorded criteria and calculations. Hashes
detect changes, not truth. Source reports edited later need review and updated
fingerprints; immutable acquisition JSON should not be silently rewritten.

### Command templates and privacy

Only run a template after mapping its live target and satisfying its case's
conditions. `${TB_ACCEPT_EVENT}` is a current Linux event node selected by
identity, never a copied Android event number. `${TB_ACCEPT_SERVER}` is the
chosen private LAN test endpoint. The command catalog's effects are explicit.
`evtest` is limited to an attended synthetic test sequence; do not collect
unrelated typing. Audio/camera fixtures must be test material. Publish sanitized
metrics and driver counters, not personal photos, voices, SSIDs, MACs, serials,
credentials or raw GPU firmware.

Do not read arbitrary sysfs/debugfs trees: the downstream CTN730 `cn_test`
getter initiates hardware activity. No raw block-device write, guessed
regulator transaction or competing charge-policy helper is part of this plan.
Existing session permissions continue to govern any actual device operation.

## Current preflight snapshot

### PF-OWNER-PERIPHERALS — `passive_owner_inventory_recorded`

The owner capture at 2026-11-22T23:47:37.939173Z enumerates two HAL 3.5 cameras, 49 logical SensorService entries, one ALSA card/32 PCM interfaces and four actually bound tfa98xx I2C clients. SensorService advertises icm4x6xx rather than historical BMI3x0, plus qmc630x, tcs3408 and bu52053nvx; reported rate limits are not samples. FSA4480 and RTC6226/radio0 are bound, so FM-01 is now a required separate gate. The scan retained 69 compatible-bearing DT declarations within its bounds; OCH8801-0 remains an unbound candidate. Exact camera/amp/codec/acoustic variants, microphones, streams, sensor transports and dynamic baseline quality remain open. No camera, audio, sensor or tuner stream was started and no Linux test was performed.

Evidence: `ANDROID-PERIPHERALS`, `PERIPHERAL-REVIEW`, `HISTORICAL-MATRIX`.

### PF-KERNEL — `host_build_and_generic_vm_pass`

Full Image/modules and scoped-pool rebuild exited 0. Initial generic QEMU virt boot exhausted the historical early page-table pool; patch 0017 rebuild and the same virt/max/2CPU/1GiB QEMU now reach ARM64 /init and EL0_READY. New Image SHA256 5b7dbf8ac810ef4b488d394f6b976d876e52372621428f751f02f8deac5667f5; all 83 expected installed modules exactly match the build/installed module orders and actual file set, with matching release strings and ARM64 ELF headers. The lenovo,tb371fc branch and real tablet boot remain untested; the generic QEMU initramfs is not a tablet rootfs. Module signing keys and unsnapshotted APT dependencies mean bit-for-bit independent reproduction is not established.

Evidence: `KERNEL-HOST`, `KERNEL-ARTIFACTS`, `QEMU-INITIAL`, `QEMU-FIXED`, `STATIC-FIXES`, `DISTRO-SOURCE`.

### PF-KERNEL-R2 — `host_build_and_generic_vm_pass`

Independent 6.12.114-tb371fc-research2-display preparation reproduced the frozen research1 source/config, then added only historical 0002 and the qualified display wrapper. Full build exited 0 in 1268.915 seconds. Image SHA256 181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d and DTB SHA256 50ad113c0f50b5586190c30fa9a6b4bedc7cbb64174c5ef4450ce558c593b63e have their own config, Module.symvers and 83 exactly matched modules. The same Image reached exact generic-QEMU release/machine/EL0 markers in 7.079 seconds; original serial and package/module manifests are retained. The native DT enables display but keeps SPI14/touch disabled. No physical display/input/GPU/Lenovo handoff or owner boot has been tested.

Evidence: `R2-BUILD`, `R2-ARTIFACTS`, `R2-QEMU`, `R2-QEMU-SERIAL`, `R2-MODULES`, `R2-PACKAGES`, `SSD-BUILDER`.

### PF-DTB — `base_display_and_joint_input_profiles_compiled`

Research1 base DT and the original research2 display DT retain their frozen configurations. The separately built joint display/input DT af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730 enables inherited SPI14/touch and explicitly marks the already available keyboard okay; all other property bytes match the qualified research2 display DT except model text. Native DSI/PHY/panel matches and real framebuffer stdout ownership are retained. OF availability is not pin ownership, driver probe, scanout, input delivery or owner boot. Full research3 and research4 builds retain this exact af80 joint DT and independently check standard Adreno SMMU/dma-coherent linkage.

Evidence: `DTB-HOST`, `KERNEL-HOST`, `R2-BUILD`, `R2-ARTIFACTS`, `INPUT-ARTIFACTS`, `INPUT-SIGNED-ARTIFACTS`, `R3-KERNEL-ARTIFACTS`, `R4-KERNEL-ARTIFACTS`.

### PF-INPUT-INTEGRATION — `compiled_and_offline_signature_verified`

Patches 0018/0019 remove unverified donor physical dimensions and correct probe/firmware/IRQ/wake/resource error paths. The actual Novatek module, three HID objects and joint DT compiled; 18 source-derived injected-error groups passed. A separately copied module was signed with the existing research2 key and CMS-verified against the exact public certificate embedded in the unchanged Image. All 63 imported CRCs match; the staged set contains 83 modules, exactly 82 unchanged and one replacement. No module insertion, signature acceptance by a running kernel, hardware timing, pen sample, keyboard event, panel-follower ordering or CTN730 charging was tested.

Evidence: `INPUT-BUILD`, `INPUT-ARTIFACTS`, `INPUT-SIGNED`, `INPUT-SIGNED-ARTIFACTS`.

### PF-GPU-FIRMWARE — `staging_verified`

Actual full-ELF3-file and MDT4-file packages match captured hashes; authentication/load remains untested.

Evidence: `GPU-STAGE-ELF`, `GPU-STAGE-MDT`.

### PF-GPU-IDENTITY — `owner_chip_id_and_compiled_smmu_contract_matched`

Owner Adreno650v3 has exact DT chip ID 0x06050002, matching qcom,adreno-650.2 and the pinned A650 catalog. Compiled research1 retains qcom,adreno-smmu, dma-coherent and the GPU reference to that SMMU. Historical R185 compatible removal is not applied to this artifact; a new restoration patch would be unjustified. Runtime per-process page tables, fault containment, firmware authentication, rendering and presentation remain untested. Research3/research4 inspectors independently retain the same standard GPU IOMMU compatible chain and referenced phandle; runtime address-space isolation remains untested.

Evidence: `ANDROID-GPU-CHIPID`, `GPU-CHIPID-REVIEW`, `GPU-DT-CONTRACT`, `GPU-SOURCE`, `R3-KERNEL-ARTIFACTS`, `R4-KERNEL-ARTIFACTS`.

### PF-FIRMWARE-CONTRACT — `static_request_map_reviewed`

The frozen original research2-display source/config/DT contract maps GPU/GMU/ZAP, three DSPs, QCA6390 WLAN/BT, Novatek and Venus requests. In that original DT, GPU/GMU, ADSP/CDSP/SLPI and Bluetooth paths are available while PCIe, SPI14/touch, four TFA amps and Venus are disabled. The later joint DT separately enables SPI14/touch without changing the declared firmware paths. TFA989X remains unset and lacks a TFA9894 match. Conditional WLAN/BT/Novatek selection and secure authentication/runtime services remain open. The original contract is not evidence that every later profile has identical source hashes or enabled devices.

Evidence: `FIRMWARE-CONTRACT`, `FIRMWARE-CONTRACT-METADATA`, `R2-ARTIFACTS`, `INPUT-ARTIFACTS`.

### PF-STOCK-FIRMWARE — `private_capture_copy_and_structure_verified`

The fixed owner capture and private SSH transfer completed with exit 0. The receiver independently verified 118 original files totalling 38546828 bytes, all manifest lengths/hashes, gzip integrity and a separate archive re-read. The 15747897-byte archive SHA256 is fc331d84ed585457b4183b08f799a49d9839d3114bf5ec2f281a725b87fe5f92. Complete A650 ELF plus A650/ADSP/CDSP/SLPI/Venus MDT variants have all loader-required segments with correct lengths; sparse BSS indices and packed metadata are preserved correctly. This original capture/transfer supplies private materials with original filenames. The later canonical staging is a separately registered result; neither step proves all-device firmware compatibility. Vendor authentication, load, WLAN board selection, BT ROM matching, hardware decode and Linux hardware operation remain untested.

Evidence: `STOCK-FIRMWARE-REPORT`, `STOCK-FIRMWARE-RECEIPT`, `FIRMWARE-CONTRACT`, `FIRMWARE-CONTRACT-METADATA`.

### PF-FIRMWARE-STAGING — `canonical_elf_and_mdt_trees_verified`

The fixed 118-file archive produced verified 69-file ELF and 70-file MDT canonical trees with exact destination hashes and loader-required segment indices. The ELF tree holds 35332142 payload bytes and was later incorporated in the separate research1 Fedora system. Two Novatek revision-6 alternatives and both BT ROM pairs are retained deliberately. No WLAN board file or TFA container is selected; all_hardware_firmware_contracts_satisfied=false. Staging and guest re-hashing are not firmware authentication or physical driver operation. The later QS shared-slot observation is a separate selection lead; no TFA container was added to these frozen canonical trees or the runtime.

Evidence: `STOCK-FIRMWARE-STAGING`, `FIRMWARE-CONTRACT-METADATA`, `FEDORA-SYSTEM-ARTIFACTS`, `TFA-CACHED-REVIEW`, `TFA-PROTOTYPE-ARTIFACTS`.

### PF-RADIO-SELECTION — `cached_version_and_shipping_source_recorded_selection_unresolved`

Owner PCI metadata identifies 17cb:1101 / subsystem 17cb:0108 and Bluetooth properties say hastings. Inspected static files/DT/debug paths did not establish QMI board ID, BDF branch or BT ROM suffix. The current retained kernel buffer yielded no filename or board-ID selection tokens without clearing logs or restarting radios. This is a bounded negative observation, not a full boot trace, proof of hardware absence or permission to choose an arbitrary board file. A later bounded cached-version read returned FW 1.0.1.0.1596.0, BDF version 0x8, reference/customer/project zero and board revision 1. The public getter formats cached descriptors; these fields are not QMI board_id or a selected filename. No unique BDF or BT ROM can be assigned from them. Subsequent bounded checks found DEBUG_FS=n and no approved IPC endpoint; no ring read/cursor advance occurred. KPROBES=n blocks that route, but BPF events and the fixed fork tracepoint interface exist. Exact shipping-Image static analysis verifies legacy tracepoint probe_read and the unique CNSS cache chain, while showing that response-valid bits and a safe lifetime are not established and the historical requested filename is not retained. No BPF program/live-memory read was implemented, and no board-2.bin candidate was chosen.

Evidence: `ANDROID-RADIO-METADATA`, `ANDROID-RADIO-SELECTION`, `STOCK-FIRMWARE-STAGING`, `ANDROID-RADIO-VERSION`, `RADIO-SELECTION-REVIEW`, `RADIO-IPC-REVIEW`, `ANDROID-RADIO-IPC`, `RADIO-PROBE-REVIEW`, `ANDROID-RADIO-PROBE`, `ANDROID-TRACEPOINT-CAPABILITY`, `CNSS-SHIPPING-REVIEW`, `CNSS-SHIPPING-STATIC`.

### PF-USERSPACE — `host_userspace_evidence_only`

The older Nix selected-closure/evaluation/QEMU-hello checkpoint remains recorded. A later separate full system.build.toplevel realization has its own PF-NIX-SYSTEM record and still has no booted NixOS rootfs. Fedora ARM64 userspace has 309 packages after adding 160 with normal scriptlets; dependency/loading checks and actual emulated software EGL/Wayland/Vulkan checks passed. Turnip found no physical GPU. This original package/graphics experiment did not boot a full system. The later research1 Fedora systemd/Enforcing boot and corrected initramfs have separate host evidence; neither establishes owner tablet boot or native rendering. Nura generic ARM builder checkpoint: alpine_builder_booted=true, native_pmb_bootstrap_complete=true, target_rootfs_exported=true, rootfs_gzip_integrity_verified=true, owned_vm_and_media_server_stopped=true, offline_cache_complete=false, target_rootfs_booted=false, tablet_linux_boot_tested_by_this_experiment=false. The completed generic target has 382 installed packages and 371 retained APKs. Its 307393454-byte archive has SHA256 eb8786e4fb51b25f077d5ade55e89123eb702d8c99076bbce5c11083f112ed46. Its qemu-profile 7.3.5 kernel/modules are not the TB371FC 6.12 stack; independent offline reconstruction and tablet root-loader integration remain open.

Evidence: `NIX-HOST`, `FEDORA-HOST`, `FEDORA-ARTIFACTS`, `NURA-HOST`, `NURA-ARTIFACTS`, `DISTRO-SOURCE`, `NIX-SYSTEM-ARTIFACTS`.

### PF-NIX-SYSTEM — `full_system_store_realized_not_booted`

Pinned system.build.toplevel actually built in 879.574 seconds using native Nix with explicit mixed-mode PRoot/QEMU for ARM processes. All 894 store paths and their references exist, totalling 3751712072 NAR bytes; ARM systemd 260.5 --version succeeded and generated init/activate passed ARM shell syntax checks. These scripts were not activated, no NixOS rootfs was created or booted, and no research kernel/modules/private firmware were integrated. Defaults, global Nix configuration and host binfmt were unchanged. This advances the earlier selected-closure checkpoint without providing a tablet system or hardware pass.

Evidence: `NIX-HOST`, `NIX-SYSTEM-HOST`, `NIX-SYSTEM-ARTIFACTS`, `NIX-SYSTEM-PATHS`.

### PF-FEDORA-SYSTEM — `research1_full_system_enforcing_vm_pass`

A separate 367-package Fedora 45 root, research1 Image, 83 matching modules and 69 verified firmware payloads booted through the corrected 30649939-byte dracut initramfs into systemd on generic virt. The explicit maintenance label boot was followed by Enforcing verification: actual loaded SELinux policy 33, PID1 init_t, multi-user/udev/D-Bus active, zero failed units/AVC denials, clean poweroff and e2fsck exit 0. An independent archive verifier rejects the retained ordering failure and accepts the corrected CPIO/gzip bytes, all firmware, 38 cache entries and 134 non-firmware ARM ELF files. Baseline autofs4/pids/BPF-LSM/virtual-GPIO notices remain recorded; no physical DT or device was passed through and no owner case is satisfied.

Evidence: `SELINUX-HOST`, `FEDORA-SYSTEM-HOST`, `FEDORA-SYSTEM-ARTIFACTS`, `FEDORA-SYSTEM-PACKAGES`, `INITRAMFS-VALIDATION`.

### PF-BOOT-BACKUPS — `verified_preparation_only`

Eight current A/B boot/recovery/vbmeta/dtbo partitions total 461504512 bytes. All local source/copy/source-recheck hashes agree; the actually received 93319878-byte off-device archive and all eight embedded images independently match the manifest. This closes the missing off-device-copy preparation item. The copies are not certified pristine factory images, do not cover userdata/super/persist, do not prove B boots and are not a demonstrated restore. Header inspection requires exact slot/hash pairing despite equal kernel release strings.

Evidence: `ANDROID-BOOT-BACKUP`, `BOOT-BACKUP-OFFDEVICE`, `BOOT-HEADER-HOST`, `BOOT-READINESS`.

### PF-USB-TRANSPORT — `owner_controller_identified_host_transport_unverified`

The bounded owner Android snapshot exposes a600000.dwc3 and a800000.dwc3, both not attached; g1 is configured on a600000.dwc3 with 17ef:7e31. The contemporaneous doesvm snapshot has 14 USB entries and no such device. Controller maximum-speed values and a configured gadget do not demonstrate a data link. No role, PD, gadget, bootloader or recovery action was performed. A usable independently identified host connection and recovery-return path remain required. A fresh paired follow-up at 2026-11-23 04:00 UTC again found both owner UDCs not attached, g1 on the same primary and 14 host entries without a 17ef/18d1/05c6 candidate. It did not change role, gadget or boot state. The later 05:18:28-30 UTC paired recheck again returned exit 0 on both hosts, two not-attached/UNKNOWN UDCs and 14 doesvm devices without a vendor candidate; this does not determine cable presence or other hosts. The later paired 06:09:03-05 UTC (14:09 Shanghai) snapshot again records the same owner UDC/g1 state and 14 host entries without a matching vendor candidate; both reads exited zero and no transport or boot state changed. The earlier paired 07:46:57-59 UTC (15:46 Shanghai) read again returns exit0 on both ends: two not-attached/UNKNOWN UDCs, g1 on a600000.dwc3 with 17ef:7e31, and 14 doesvm entries without a 17ef/18d1/05c6 candidate. No role, gadget or boot action occurred and physical entry/recovery remains unverified. The latest retained paired snapshot at 09:36:24-25 UTC (17:36 Shanghai) again exits zero on both ends: two not-attached/UNKNOWN UDCs, unchanged g1 primary/VID/PID, and 14 doesvm entries without a corresponding vendor candidate. It establishes no owner data/recovery link and changes no USB or boot state.

Evidence: `ANDROID-USB-TRANSPORT`, `HOST-USB-TRANSPORT`, `USB-TRANSPORT-REVIEW`, `USB-FOLLOWUP-REVIEW`, `ANDROID-USB-FOLLOWUP`, `HOST-USB-FOLLOWUP`, `USB-RECHECK-REVIEW`, `ANDROID-USB-RECHECK`, `HOST-USB-RECHECK`, `USB-RECHECK-1409-REVIEW`, `ANDROID-USB-RECHECK-1409`, `HOST-USB-RECHECK-1409`, `USB-RECHECK-1546-REVIEW`, `ANDROID-USB-RECHECK-1546`, `HOST-USB-RECHECK-1546`, `USB-RECHECK-1736-REVIEW`, `ANDROID-USB-RECHECK-1736`, `HOST-USB-RECHECK-1736`.

### PF-BOOT-RECOVERY — `unresolved_stock_entry`

The running owner 4.19 kernel has CONFIG_KEXEC=n, forced module signatures/MODVERSIONS and no ACM function; NCM/FunctionFS configuration does not demonstrate rescue transport. Android properties and captured boot arguments still disagree about locked/green versus unlocked/orange. A new public bridge, default-HOLD rescue initramfs, format-only v2 image and separately booted Fedora system now exist, but stock-to-entry execution, bootloader acceptance, actual runtime placement, final board handoff and a usable recovery control route remain unverified. Current mmcblk0 has three partitions; no historical two-partition recipe is assumed. Existing session authorization governs operations; this ledger adds no deployment permission or confirmation step. Actual USB snapshots now identify two owner UDCs, Android g1 on a600000.dwc3, both not attached, and no owner gadget in doesvm. The separate fixed-target ramdisk closes the source selection mismatch only; physical transport and recovery remain unverified.

Evidence: `ANDROID-BOOT`, `ANDROID-BOOT-CAPABILITIES`, `BOOT-READINESS`, `ENTRY-RECONSTRUCTION-ARTIFACTS`, `FEDORA-SYSTEM-ARTIFACTS`, `ANDROID-USB-TRANSPORT`, `HOST-USB-TRANSPORT`, `USB-TRANSPORT-REVIEW`, `ENTRY-OWNER-UDC-ARTIFACTS`, `USB-RECHECK-REVIEW`, `ANDROID-USB-RECHECK`, `HOST-USB-RECHECK`.

### PF-FIRST-STAGE-SOURCE — `public_replacement_built_format_only_entry`

The original R226/R201/V56.6 audit still lacks nine historical patches and exact private intermediates. Separately, pinned tem423 9d8abebf4ac4d45cf4cc11b5b6bc5e4483d10fd1 plus four new bounded patches built 4.19.325-cip134-st18-tb371fc-entry-r1 with KEXEC/DEVTMPFS/ACM and a static default-HOLD rescue initramfs. The downstream generic VM failed before PID1 in Qualcomm SCM; the same initramfs passed its userspace-only checks under frozen research2, not under the bridge. A 53583872-byte unsigned v2 candidate independently reparses with exact owner recovery_a DTB/DTBO/header preservation except recorded size/offset/ID fields. No missing historical patch was fabricated; public source lacks several board drivers and any matching Spinel DTS. No AVB/signature, physical boot, kexec, USB rescue or runtime-memory contract is demonstrated. The later owner-UDC r2 ramdisk and 53587968-byte v2 candidate are separately qualified host artifacts; the kernel and its SCM failure are unchanged.

Evidence: `ENTRY-SOURCE`, `ENTRY-METADATA`, `ENTRY-RECONSTRUCTION`, `ENTRY-RECONSTRUCTION-ARTIFACTS`, `ANDROID-BOOT-CAPABILITIES`, `BOOT-HEADER-HOST`, `ENTRY-OWNER-UDC-ARTIFACTS`.

### PF-ENTRY-OWNER-UDC — `fixed_selector_reference_vm_and_format_only_pass`

A new independent ramdisk selects only the observed a600000.dwc3 after fixed directory/readable-metadata checks; absent or invalid target holds without a800000 fallback. Ten source-derived ARM BusyBox predicate fixtures passed. Only init changed among 15 decoded archive entries; all three static binaries are unchanged. The new initramfs SHA 4e89de6d7de7535eb0e70a2557a3ad123f0e89d5d2724ec9104984aeb7db92a5 reached PID1/EL0 under research2 in 3.865 seconds with gadget setup deliberately skipped. A new 53587968-byte private v2 candidate SHA 7239c215ebb56ff5580a9b7ac9599859ab8242443e5204d70e4b618ef51587a6 independently reparsed. No physical USB binding/enumeration, 4.19 runtime, owner boot, AVB, kexec or recovery result is implied; original source/artifacts remain intact.

Evidence: `ANDROID-USB-TRANSPORT`, `ENTRY-RECONSTRUCTION-ARTIFACTS`, `ENTRY-OWNER-UDC`, `ENTRY-OWNER-UDC-ARTIFACTS`.

### PF-BUILDER — `ssd_work_builder_ready`

A separate standard Docker builder completed bootstrap with exit 0 in 617.685 seconds. Its /work is SSD, /src is read-only, CPU/RAM limits remain 4/8 GiB, LLVM 19.1.7 produced a real AArch64 object, and the official archive/reference manifest copies match expected hashes. The old build/Nura container remains intact. This is infrastructure readiness, with no kernel or tablet pass implied.

Evidence: `SSD-BUILDER`.

### PF-KERNEL-R3 — `host_build_and_offline_consistency_pass`

Independent research3 adds the joint input/display source and PIDS/autofs/PL061/BPF/BTF configuration to the replayed research2 baseline. The complete Image and 84-module set pass CRC/CMS/BTF/DT checks, including 4308 imported CRC comparisons. Its source-level ARM64 native function-entry gap is retained in the separate trampoline audit. No device probe or successful behavioral BPF test follows from this build.

Evidence: `R3-KERNEL`, `R3-KERNEL-ARTIFACTS`, `ARM64-BPF-REVIEW`, `ARM64-BPF-METADATA`.

### PF-KERNEL-R4 — `host_build_and_offline_consistency_pass`

Independent 6.12.114-tb371fc-research4-system builds the complete resolved ARM64 ftrace/direct-call chain, with 266 actual bpf_lsm.o patchable-entry sections. Its Image, BTF, unchanged af80 joint DT and 84 signed modules pass full inventory/CRC/CMS checks. The compiled standard Adreno SMMU contract is retained. Module-signature force is explicitly a runtime VM command-line/sysfs gate; kernel configuration alone is not enforcement, BPF operation or a tablet pass.

Evidence: `R4-KERNEL`, `R4-KERNEL-ARTIFACTS`, `R4-KERNEL-VERIFICATION`, `ARM64-BPF-REVIEW`.

### PF-FEDORA-R3 — `failed_before_pids_and_bpf_behavioral_probes`

The separate research3 Fedora system reached the guarded Enforcing/runtime-hash preconditions but systemd-run --wait/--pipe reset before the controlled pids/BPF operations. The failed image and raw records remain retained. This is not an expected BPF-denial result, and the partial journal cannot establish absence of a security/broker error in the later reset window.

Evidence: `FEDORA-R3-HOST`, `FEDORA-R3-ARTIFACTS`.

### PF-SELINUX-FD-POLICY — `offline_access_vectors_and_copy_followup_recorded`

Fixed offline policy queries distinguish allowed fd use from denied and dontaudited access to unconfined-service FIFO inodes, and identify an existing initrc service-entry route. They do not prove the actual loaded-policy serialization or broker child context. A separate follow-up records that PRoot bind placeholders can alter directory metadata, preserves the failed earlier canonical copy, and qualifies the later quiescent copy without weakening integrity checks.

Evidence: `SELINUX-AV-REVIEW`, `SELINUX-AV-ARTIFACTS`, `SELINUX-COPY-REVIEW`, `SELINUX-COPY-ARTIFACTS`, `FEDORA-R4-FIRST`, `FEDORA-R4-FIRST-VERIFY`, `FEDORA-R4-FIRST-SERIAL`.

### PF-EARLY-SELINUX — `native_helper_build_and_api_only_qualification_pass`

The exact Fedora sources explain the early init_t-to-kernel_t queued-udev-socket denial and missing initramfs policy/labels. A two-process shell route was rejected because execute_no_trans is denied after policy load. The single native ARM64 bootstrap calls standard libselinux load/relabel APIs and execs labelled systemd, preserving policy/enforcement. Two builds produced identical e53cf407... bytes, API-only ARM execution succeeded, and non-PID1 default execution was rejected. Production archive/PID1/domain/event-handoff tests remain the independent integration candidate responsibility. The subsequent retained v5 production result loaded policy Enforcing but failed at /var filesystem associate before systemd; the original build-only record remains unchanged.

Evidence: `EARLY-SELINUX-REVIEW`, `EARLY-SELINUX-ARTIFACTS`, `SELINUX-COPY-REVIEW`, `FEDORA-R4-FIRST`, `FEDORA-R4-FIRST-VERIFY`, `FEDORA-R4-FIRST-SERIAL`, `FEDORA-R4B-EARLY`, `FEDORA-R4B-EARLY-ARTIFACTS`.

### PF-TFA-CACHED — `bounded_owner_cached_selection_and_shipping_binary_contract_recorded`

The owner shared HQ ID 131 slot reports tfa98xx_QS.cnt. Exact shipping module/Image analysis shows a first-registration cache populated before asynchronous firmware completion. This narrows the container lead, without proving four independent amplifier choices, all silicon/acoustic identities, successful load/DSP processing/calibration or speaker performance. No register/I2C/calibration/playback operation was performed.

Evidence: `TFA-CACHED-ANDROID`, `TFA-CACHED-STATIC`, `TFA-CACHED-REVIEW`, `ANDROID-PERIPHERALS`.

### PF-TFA-PROTOTYPE — `isolated_unsigned_module_build_and_abi_check_pass`

The separate TFA98xx downstream prototype compiled against frozen research4 in 6.006 seconds and passed AArch64/BTF/75 imported-CRC inspection in 0.471 seconds. The 1759864-byte module is unsigned, uninstalled and unexecuted, with 35 warnings retained. Only the named API adaptation and historical MTP guard transformation were applied. Complete persistent-write protection, machine/DAI/TDM routing, exact container integration and physical behavior remain open; the 84 signed runtime modules and DT are unchanged.

Evidence: `TFA-PROTOTYPE-HOST`, `TFA-PROTOTYPE-ARTIFACTS`, `TFA-PROTOTYPE-HISTORY`, `TFA-PROTOTYPE-LOG`, `TFA-CACHED-REVIEW`.

### PF-FEDORA-R4-FIRST — `failed_real_broker_descriptor_transport_and_early_udev_handoff`

First research4 system verification reached Enforcing and checked 84 module/69 firmware hashes. Actual system-bus GetId and Manager.Version succeeded; unrestricted systemd-run --wait/--pipe true reset before the pids/BPF workers. Actual creator/client/pipe inodes were unconfined_service_t. The broker launcher was observed, but its child was not identified in this old recipe. A separate early init_t-to-kernel_t netlink getattr denial lost the event-serialization FD during root-state deserialization. One audit event appears twice textually. The image and raw logs remain failed and retained; the newer v5 candidate has separate source, archives and outcomes.

Evidence: `FEDORA-R4-FIRST`, `FEDORA-R4-FIRST-ARTIFACTS`, `FEDORA-R4-FIRST-VERIFY`, `FEDORA-R4-FIRST-SERIAL`, `FEDORA-R4-FIRST-LABEL`, `SELINUX-AV-ARTIFACTS`, `SELINUX-COPY-ARTIFACTS`, `EARLY-SELINUX-ARTIFACTS`.

### PF-FEDORA-R4B-EARLY — `failed_rootfs_label_association_before_systemd`

The independent v5 archive passed fixed layout/ELF/policy/firmware checks. Its actual production native PID1 loaded the fixed policy Enforcing, then restorecon denied var_t to root_t filesystem associate at /var, exited and panicked before systemd. The production serial, result and separate maintenance phase remain frozen. No postexec domain, event handoff, broker, pids or BPF result was reached.

Evidence: `FEDORA-R4B-EARLY`, `FEDORA-R4B-EARLY-ARTIFACTS`, `FEDORA-R4B-EARLY-VERIFY`, `FEDORA-R4B-EARLY-SERIAL`, `FEDORA-R4B-EARLY-LABEL`, `FEDORA-R4B-EARLY-ARCHIVE`.

### PF-SELINUX-ROOTFS — `fixed_source_and_offline_policy_contract_reviewed`

The exact 6.12 hooks and fixed Fedora CIL explain rootfs superblock root_t, its failed inode association and ordinary tmpfs_t behavior. Pre-policy context remount is rejected by option parsing, while postload remount cannot change this initialized SID. Fixed switch_root source and the actual package payload match; its asynchronous cleanup and warning-only deletion outcomes require a separate wait/empty-directory check. No target mount or policy modification was made by the audit.

Evidence: `SELINUX-ROOTFS-REVIEW`, `SELINUX-ROOTFS-ARTIFACTS`, `FEDORA-R4B-EARLY-SERIAL`.

### PF-TMPFS-BOOTSTRAP — `stage_construction_qualified_runtime_subsequence_observed`

A new explicit /init.tmpfs route creates a bounded ordinary tmpfs before policy, copies the exact static top-level payload with one cp invocation and uses the fixed standard switch_root. The 71872-byte native waiter requires one successful cleanup child, distinct roots, an empty rewound old-root directory and a closed saved FD before execing unchanged e53. AArch64 compile, ARM Bash syntax and both non-PID1 rejections passed. The separate v6 record now qualifies its archive and observes distinct tmpfs root, one reaped cleanup child, empty old-root directory, native policy/exec and same-boot init_t/udev_t sequence. Its original aggregate remains false without a final guest record; API-label AVCs and manager FD rejection still fail complete-system gates. The frozen construction report remains limited to its own checks and no owner hardware pass is added.

Evidence: `TMPFS-BOOTSTRAP-REVIEW`, `TMPFS-BOOTSTRAP-ARTIFACTS`, `SELINUX-ROOTFS-ARTIFACTS`, `EARLY-SELINUX-ARTIFACTS`, `FEDORA-R4C-TMPFS`, `FEDORA-R4C-TMPFS-VERIFY`, `FEDORA-R4C-TMPFS-ARCHIVE`.

### PF-FEDORA-R4C-TMPFS — `partial_tmpfs_sequence_observed_full_system_failed`

Independent v6 passed fixed archive qualification and actually moved root 0:2 to ordinary tmpfs 0:20, reaped one cleanup child, checked old-root emptiness, loaded policy Enforcing and execed unchanged e53 to systemd. Same-boot mountinfo/process proof saw tmpfs and PID1 init_t/udevd udev_t. The full run still failed: policy.35 map and API dev/run labels caused AVCs; at the real system-bus control PID1 init_t was denied FIFO write to the observed initrc_t stdout pipe, followed by MSG_CTRUNC (1/3 FDs) and InconsistentMessage. Actual broker child/domain and exported-policy broker-side allows do not cover the manager recipient. Neither pids nor BPF worker ran. The controller aggregate stays false without a final result; no positive udev count pair proves an empty queue, and no production clean shutdown or hardware pass is claimed.

Evidence: `FEDORA-R4C-TMPFS`, `FEDORA-R4C-TMPFS-ARTIFACTS`, `FEDORA-R4C-TMPFS-VERIFY`, `FEDORA-R4C-TMPFS-SERIAL`, `FEDORA-R4C-TMPFS-LABEL`, `FEDORA-R4C-TMPFS-ARCHIVE`, `FEDORA-R4C-TMPFS-PROOF-PAYLOAD`, `FEDORA-R4C-TMPFS-UDEV`, `FEDORA-R4C-TMPFS-SOURCE`, `TMPFS-BOOTSTRAP-ARTIFACTS`, `SELINUX-ROOTFS-ARTIFACTS`.

### PF-SELINUX-RELOAD-CONTRACT — `fixed_source_and_offline_three_recipient_contract_reviewed`

The original fixed-policy queries close the selected sysadm_t service/worker entry and broker, manager and worker FD/FIFO premises, while preserving the separate init_t map denial and manager read_policy restriction. They do not establish the actual exported policy, receiver/worker contexts or descriptor transfer in a later VM. The old unpersisted 9c79 identity is not substituted with the aab7 offline candidate.

Evidence: `SELINUX-RELOAD-CONTRACT-REVIEW`, `SELINUX-RELOAD-CONTRACT-ARTIFACTS`, `FEDORA-R4C-TMPFS-VERIFY`.

### PF-SELINUX-POLICY-MAP — `standard_offline_build_and_complete_single_rule_comparison_passed`

The independent standard Fedora semodule no-load build produces policy35 0dd46a with only init_t semanage_store_t:file map added. Original/candidate whole CIL exports have exactly the one permission substitution and the binaries differ at one byte; all 32 original context files and config are unchanged. Full store/input/output inventories and the retained build failure and warning are recorded. No loaded policy, enforcement setting, label or runtime outcome changed through this construction; VM gates remain pending.

Evidence: `POLICY-MAP-REVIEW`, `POLICY-MAP-ARTIFACTS`, `POLICY-MAP-SOURCE-INVENTORY`, `POLICY-MAP-BEFORE-INVENTORY`, `POLICY-MAP-CANDIDATE-INVENTORY`, `POLICY-MAP-BUILD-LOG`.

### PF-EARLY-RELOAD-LOADER — `independent_compile_and_negative_entry_passed_success_path_not_run`

The V2 72048-byte loader compiled and rejected non-PID1 entry. Its control flow remains unchanged from V1 because both source policies have the same length; the candidate archive/runtime must therefore verify the full 0dd46a policy hash independently of native size checks. No PID1 execution, mount, policy load, device boot or VM completion is claimed by this construction record.

Evidence: `EARLY-RELOAD-LOADER-REVIEW`, `EARLY-RELOAD-LOADER-BUILD`, `EARLY-RELOAD-LOADER-NEGATIVE`, `POLICY-MAP-ARTIFACTS`.

### PF-SYSTEMD-BPF-CONTRACT — `matched_source_attachment_and_v8_paired_open_denial_observed`

The fixed Fedora 262.1 source places the positive LSM attachment log after load/attach and returns EPERM from the proc-denying file_open hook. V7 retained two attachment markers but ran neither worker. Independent v8 now records two markers and the same-worker comparison: unrestricted open/read returns the actual release in 181 bytes; RestrictFileSystems=~proc returns open-stage errno 1/EPERM with 0 bytes. Actual worker domain/FDs/unit properties and unchanged loaded policy close the comparison. This is a generic-VM behavioral result; a separate journalctl AVC still fails v8 overall, and no owner hardware case changes.

Evidence: `SYSTEMD-BPF-CONTRACT-REVIEW`, `SYSTEMD-BPF-CONTRACT-ARTIFACTS`, `FEDORA-R4C-TMPFS-VERIFY`, `FEDORA-R4D-SERIAL`, `FEDORA-R4E-GUEST`, `FEDORA-R4E-SERIAL`, `FEDORA-R4E-VERIFY`.

### PF-POSTRELOAD-MAPONLY — `retained_offline_candidate_contract_incomplete`

The map-only policy passes queried device/run relabel and intended journal rights but denies same-type init_t setcurrent and dyntransition. Fixed libselinux begins with an unset setter cache and getcon does not fill it; the matching kernel does not skip the checks for equal SIDs. The actual query completed 53 rows but the required contract remains incomplete, and no future VM outcome is inferred.

Evidence: `POSTRELOAD-MAPONLY-REVIEW`, `POSTRELOAD-MAPONLY-ARTIFACTS`, `POLICY-MAP-ARTIFACTS`.

### PF-SELINUX-POLICY-MAP-SELF — `independent_combined_build_and_full_semantic_comparison_passed`

A fresh original-store build contains exactly two source rules adding only map plus init_t-to-init_t setcurrent/dyntransition. Complete original/candidate policy35 and fresh33 CIL exports match after just those two substitutions; no cross-type transition or other rule/constraint changes. All 32 original contexts and config remain unchanged, and the full 1766-entry source inventory is identical before/after. The new e1a63 policy keeps the same byte length, so full-hash archive/runtime binding is still required when reusing the separately built cc042 loader. No live policy or VM action was performed.

Evidence: `POLICY-MAP-SELF-REVIEW`, `POLICY-MAP-SELF-ARTIFACTS`, `POLICY-MAP-SELF-SOURCE`, `POLICY-MAP-SELF-BEFORE`, `POLICY-MAP-SELF-AFTER`, `POLICY-MAP-SELF-BUILD-LOG`, `EARLY-RELOAD-LOADER-BUILD`.

### PF-POSTRELOAD-COMBINED — `independent_candidate_permission_subset_satisfied_later_vm_separately_failed`

The independent 54-row direct-QEMU query confirms 52 required allows and both retained denial controls on the combined e1a63 candidate. Its fresh33 conversion matches ce6ccb. The later v7 run separately retains actual policy33 0fe3c0e1, observed reload/labels and held-worker FD/pids progress, but the complete VM fails on further AVCs, a PL061 fixture and serial framing. Offline permission-subset closure never establishes full policy or system acceptance.

Evidence: `POSTRELOAD-COMBINED-REVIEW`, `POSTRELOAD-COMBINED-ARTIFACTS`, `POSTRELOAD-MAPONLY-ARTIFACTS`, `POLICY-MAP-SELF-ARTIFACTS`, `FEDORA-R4D-ARTIFACTS`, `FEDORA-R4D-POLICY-EXPORT`.

### PF-FEDORA-R4D-RELOAD-FD — `failed_with_observed_three_fd_route_pids_and_bpf_attachment`

Independent v7 production verification failed. Ordered tmpfs cleanup, standard policy reload/context setup and same-boot PID1/udevd/journald plus API/journal labels were observed. The real system-bus held-worker route forwarded all three qualified FIFO descriptors; the unrestricted noop exited 0. TasksMax=3 admitted two children, rejected a third with EAGAIN, advanced pids.events max 0 to 1 and reaped the owned children. Two source-qualified BPF attachment logs are present, but an incorrect PL061 directory guard stopped execution before either baseline proc-open or restricted behavior. Source and registration logs identify pl061_gpio, but corrected runtime sysfs binding was not read. Two visible Enforcing AVCs and six suppressed callbacks remain, and interleaved console bytes corrupt two JSON progress frames; the original controller and udev aggregates remain false. Actual policy33 0fe3c0e1 was retained without image writes. Follow-up fixture and minimal policy fixes are being prepared in separate work; no owner hardware case changes.

Evidence: `FEDORA-R4D-REVIEW`, `FEDORA-R4D-ARTIFACTS`, `FEDORA-R4D-VERIFY`, `FEDORA-R4D-SERIAL`, `FEDORA-R4D-LABEL`, `FEDORA-R4D-LABEL-SERIAL`, `FEDORA-R4D-ARCHIVE`, `FEDORA-R4D-PROOF-PAYLOAD`, `FEDORA-R4D-UDEV`, `FEDORA-R4D-CONSTRUCTION`, `FEDORA-R4D-POLICY-EXPORT`, `FEDORA-R4D-FREEZE-JOB`, `FEDORA-R4D-SOURCE`, `FEDORA-R4D-BASELINE`, `FEDORA-R4D-PLAN`.

### PF-VARLINK-CLEANUP — `exact_standard_service_permission_gaps_confirmed_repair_not_tested`

Fixed source and two completed 32-row AV queries independently establish three required gaps: init_t to registry lnk_file unlink, journalctl_t to the correctly labeled journal sock_file write, and journalctl_t to syslogd_t unix_stream_socket connectto. The first two have actual v7 AVCs; connectto is a source-and-policy prediction of the next check. The captured version33 0fe3 bytes are queried directly without conversion; agreement with offline ce6ccb is only this subset. Existing directory and link rights already allow, while target-socket getattr is intentionally not requested by the fixed short-path client and must not be added. No policy repair or new runtime outcome is claimed by this audit.

Evidence: `VARLINK-CLEANUP-REVIEW`, `VARLINK-CLEANUP-ARTIFACTS`, `FEDORA-R4D-ARTIFACTS`, `FEDORA-R4D-POLICY-EXPORT`, `FEDORA-R4D-SERIAL`.

### PF-STANDARD-SERVICE-POLICY — `fresh_build_and_full_six_permission_semantic_comparison_passed`

A fresh original module-store build adds the prior policy map and same-init_t setcurrent/dyntransition rights plus registry-link unlink, journal socket write and journald connectto. Complete version-35 and fresh-version-33 CIL comparisons allow only those five tuples and six permissions. All original contexts/config and the 1,766-entry source inventory remain unchanged. Candidate 727cd98e is 3,835,456 bytes; no target-socket getattr or additional privilege is introduced. The separate v8 run now exercises the prior service fixes but exposes an additional journalctl self datagram-create denial; the qualified six-permission semantic comparison remains unchanged.

Evidence: `STANDARD-POLICY-REVIEW`, `STANDARD-POLICY-ARTIFACTS`, `STANDARD-POLICY-SOURCE`, `STANDARD-POLICY-BEFORE`, `STANDARD-POLICY-AFTER`, `STANDARD-POLICY-BUILD-LOG`, `FEDORA-R4E-ARTIFACTS`.

### PF-STANDARD-SERVICE-AV — `independent_offline_required_permission_subset_satisfied`

One direct-QEMU userspace process checked the complete preserved 54-row and 32-row matrices: 86 rows, 79 unique tuples, 80 ALLOW and 6 DENY. All 73 required-allow rows pass; the diagnostic target-socket getattr and original denial controls remain denied. The independent fresh33 hash matches 9b39b5a5. This is a candidate permission check, not a live policy export, service connection or owner Linux run.

Evidence: `STANDARD-AV-REVIEW`, `STANDARD-AV-ARTIFACTS`, `STANDARD-POLICY-ARTIFACTS`.

### PF-AUDIT-OBSERVABILITY — `source_guard_and_v8_readbacks_observed_zero_configured_loss_markers`

The fixed shared printk limiter explains why v7 suppressed callbacks do not identify missing content. In separate v8 the exact generic-VM/PID1 guard actually sets only interval 5 to 0 before policy load; fresh burst readbacks retain 10, and guest before/after tests still read 0/10. Audit admission/backlog and Enforcing are unchanged. Every configured production audit/loss/suppression count is 0; one visible AVC nevertheless fails the run. These observed markers do not disprove every theoretically unobservable event. The separate permissive maintenance log retains its own 47 denials and 9 suppression notices.

Evidence: `AUDIT-OBSERVABILITY-REVIEW`, `AUDIT-OBSERVABILITY-ARTIFACTS`, `AUDIT-OBSERVABILITY-SOURCE`, `FEDORA-R4D-SERIAL`, `FEDORA-R4E-ARTIFACTS`, `FEDORA-R4E-SERIAL`, `FEDORA-R4E-LABEL-SERIAL`.

### PF-EARLY-STANDARD-LOADER — `independent_build_negative_entry_and_v8_ordered_entry_observed`

The V3 source derivation produces 20,011 bytes from the fixed 12,548-byte original. One actual compile exits 0 in 1.562511 seconds and yields the 72,528-byte 84cc4868 AArch64 PIE; its HDD copy matches. Actual QEMU-user execution exits 1 at the first non-PID1 guard; the audit-setting branch, mounts and policy APIs are not reached. Full policy 727cd98e and loader hashes must be bound by the new archive/profile; neither a length check nor construction proves a successful VM. The separate actual v8 archive/profile now binds the full identities and observes V3 audit guard, policy load, systemd exec and same-boot domain/label proof in order. Its full production verification still fails on a later journalctl AVC, with no owner entry.

Evidence: `EARLY-STANDARD-LOADER-REVIEW`, `EARLY-STANDARD-LOADER-BUILD`, `EARLY-STANDARD-LOADER-NEGATIVE`, `EARLY-STANDARD-LOADER-INVOCATION`, `EARLY-STANDARD-LOADER-INPUT-TRANSFER`, `EARLY-STANDARD-LOADER-HDD-TRANSFER`, `FEDORA-R4E-ARTIFACTS`, `FEDORA-R4E-VERIFY`.

### PF-TMPFS-WAITER-V2 — `independent_build_and_v8_cleanup_observed_full_system_failed`

The independently built 71,872-byte 7e593ef9 waiter targets the measured 72,528-byte V3. Its approved marker/length/comment substitutions reverse to every original C byte; all PID 1, FD 3, child/timeout, root and emptiness guards remain. Actual non-PID1 rejection and destination hashes pass. No cleanup, V3 entry or VM is executed by this qualification, and the native target-size check does not authenticate content. Separate v8 now observes one cleanup child reaped, old-root emptiness and 0:2 to 0:20 root migration before the fully pinned V3 path. That new runtime observation does not change this construction record or the failed full-system verdict.

Evidence: `TMPFS-WAITER-V2-REVIEW`, `TMPFS-WAITER-V2-ARTIFACTS`, `EARLY-STANDARD-LOADER-BUILD`, `FEDORA-R4E-ARTIFACTS`, `FEDORA-R4E-VERIFY`.

### PF-R4E-RESULT-TRANSPORT — `six_offline_cases_and_actual_normal_shutdown_transport_qualified`

The six synthetic ext4 cases retain their offline scope. In actual v8 the complete 413,706-byte guest result is exclusively created, fsynced/read back and bound to a unique short receipt. After normal QEMU exit 0, read-only debugfs verifies fixed parent/file metadata, full hash and same-boot/profile identity without mount or journal replay. Persistent qualification is true and parse_error is null. This closes the actual normal-shutdown transport gap only; abrupt-termination recovery is not guaranteed and the independent one-AVC system verdict remains failed.

Evidence: `FEDORA-R4E-TRANSPORT-CASES`, `FEDORA-R4E-GUEST`, `FEDORA-R4E-VERIFY`, `FEDORA-R4E-SERIAL`, `FEDORA-R4E-TRANSFER`.

### PF-FEDORA-R4E-PERSISTENT — `all_guest_behavior_observed_overall_failed_one_enforcing_avc`

The independent v8 pipeline exits 1 after 658.410 seconds, although its production QEMU exits 0 normally and all defined guest gates/transport pass. Ordered tmpfs cleanup/early Enforcing domains/API labels, real bus queries and three-FD delivery are observed; four routes each query the exact 82 live permission tuples separately from the 86-row offline candidate matrix. TasksMax admits 2 children, rejects the third with EAGAIN and advances max-events 0 to 1. The paired BPF test reads 181 bytes unrestricted and denies restricted open with EPERM/errno 1 and 0 bytes. Actual pl061_gpio binding, all 84 module/69 firmware hashes, enforced signatures, loaded autofs4 and taint 0 are checked. Full production log has one journalctl_t self unix_dgram_socket create AVC despite sync exit 0; all configured loss/suppression counters are 0. Original controller remains false. Post-qualify/finalize and postboot e2fsck did not run; no positive udev count pair proves an empty or completely preserved queue. Actual policy 33 9d7aa2b3 is retained independently, with no raw policy binary published or owner hardware pass.

Evidence: `FEDORA-R4E-REVIEW`, `FEDORA-R4E-ARTIFACTS`, `FEDORA-R4E-VERIFY`, `FEDORA-R4E-SERIAL`, `FEDORA-R4E-GUEST`, `FEDORA-R4E-LABEL`, `FEDORA-R4E-LABEL-SERIAL`, `FEDORA-R4E-PIPELINE`, `FEDORA-R4E-POLICY-RETENTION`, `FEDORA-R4E-FREEZE-JOB`, `FEDORA-R4E-TRANSFER`, `FEDORA-R4E-SOURCE`, `FEDORA-R4E-BASELINE`, `FEDORA-R4E-PLAN`.

### PF-SOCKET-PROBE-SOURCE — `matched_source_and_retained_actual_policy_query`

The fixed systemd 262.1 journalctl varlink path performs a socket-xattr feature probe. It creates an AF_UNIX datagram socket and tries user.testxxx; the fixed kernel rejects that user xattr on a socket before the LSM xattr hook. The no-stat fd_is_opath branch uses F_GETFL only. A direct saved-v8-policy query gives 6 allows and 13 denies over 19 tuples. The required next permission is self datagram create; getattr/setattr/connect/send additions are not justified. This explains an actual retained AVC without ignoring it or proving a repaired run.

Evidence: `SOCKET-PROBE-REVIEW`, `SOCKET-PROBE-ARTIFACTS`, `SOCKET-PROBE-LIVE-POLICY-AV`, `FEDORA-R4E-SERIAL`.

### PF-SOCKET-PROBE-POLICY — `fresh_candidate_exact_semantics_and_offline_av_pass`

The new ff65 version-35 candidate has 3835468 bytes. A fresh original-store build and complete 35/fresh-33 CIL comparison against the six-permission 727 candidate permit exactly journalctl_t self unix_dgram_socket create in addition to the old six. The new 19-tuple matrix yields 7 required allows and 12 retained denies. This is offline evidence; no V9 production policy was loaded and old V8 failure remains unchanged.

Evidence: `SOCKET-POLICY-REVIEW`, `SOCKET-POLICY-ARTIFACTS`, `SOCKET-POLICY-BUILD`, `SOCKET-POLICY-COMPARE`, `SOCKET-POLICY-AV`.

### PF-EARLY-SOCKET-LOADER — `independent_v4_build_and_nonpid1_rejection_pass`

The actual V4 build produces ARM64 ELF 0bc3f0fb, 72528 bytes, for the actual new policy length. Non-PID1 invocation is rejected, and the new artifact transfer matches. The audit guard and official load/relabel/exec behavior are retained. Waiter V2 is reusable by length, but full ELF and policy identity remain separate archive/profile gates. This construction does not run PID1 or establish owner entry.

Evidence: `EARLY-SOCKET-LOADER-REVIEW`, `EARLY-SOCKET-LOADER-BUILD`, `EARLY-SOCKET-LOADER-NEGATIVE`, `EARLY-SOCKET-LOADER-INVOCATION`, `EARLY-SOCKET-LOADER-HDD-TRANSFER`.

### PF-FEDORA-R4F-IMAGE — `original_mkfs_timeout_before_any_vm`

The first R4F/v9 pipeline actually exits one after 1148.676 seconds. Stage, configure and both archives passed their original checks; mkfs.ext4 then exceeded the fixed 600-second subprocess deadline, with the image phase taking 615.382 seconds including cleanup. The partial 4 GiB apparent file, original source and full traceback remain retained. No label/production VM, actual policy export or live behavior was run. Concurrent HDD work is relevant context, not a proven exclusive cause. An independent recovery must retain these limits and report its own outputs.

Evidence: `FEDORA-R4F-REVIEW`, `FEDORA-R4F-ARTIFACTS`, `FEDORA-R4F-PIPELINE`, `FEDORA-R4F-IMAGE`, `FEDORA-R4F-IMAGE-LOG`, `FEDORA-R4F-INITRAMFS`, `FEDORA-R4F-SOURCE`, `FEDORA-R4F-BASELINE`.

### PF-KERNEL-R5 — `full_build_offline_qualification_and_shared_transfer_pass_no_vm`

The independent 6.12.114-tb371fc-research5-services configuration differs from R4 in exactly 14 values derived from the original Nix/Nura services. Full build exits zero in 1681.092 seconds and inspector exits zero in 15.765 seconds. All 84 modules retain the R4 relative path set, new matching CMS/vermagic/BTF/stripping and all 4308 imported CRC checks. Image contains the exact BTF and new public certificate; joint DT and standard Adreno SMMU references are unchanged. All 106 transferred ordinary files have equal source-before/source-after/destination hashes/modes/owners and canonical archive streams. No private key, firmware or old depmod index is transferred. Actual Nix/Nura startup, firewall, zram and RTC behavior still await a separate R5 VM; no owner case changes.

Evidence: `R5-KERNEL`, `R5-ARTIFACTS`, `R5-VERIFICATION`, `R5-CONFIGURATION`, `R5-TRANSFER`, `R5-CONTRACT`.

### PF-NURA-ENTRY — `bounded_original_busybox_openrc_inventory_only`

A native read-only collector identifies original Nura BusyBox PID1, inittab-driven OpenRC sysinit/boot/default, ARM Python, original service definitions and the retained 7.3.5 module tree. It does not execute the target or rehash every exported archive member. Original firewall/zram/hwclock service prerequisites motivated the separate R5 build; no service is silently removed to claim complete startup. Target boot and complete offline package reconstruction remain open.

Evidence: `NURA-HOST`, `NURA-ARTIFACTS`, `NURA-ENTRY-REVIEW`, `NURA-ENTRY-ARTIFACTS`, `R5-CONTRACT`.

### PF-TOOLS-MAC-BOUNDARY — `targeted_offline_token_boundary_regression_pass`

The six-octet privacy-check regex now excludes adjacent colons as well as hexadecimal characters. The specified offline test accepts its synthetic positive/negative cases and leaves original 20-byte public key IDs and raw R4/R5 evidence intact. This is source-tooling qualification only, with no new Linux hardware result.

Evidence: `TOOLS-MAC-BOUNDARY`.

### PF-NIX-REGISTERED-ROOT — `original_signed_cache_copy_timeout_before_image_or_vm`

The original native Nix 2.26.3 job exits one after 5530.405676769966 seconds. Recursive source metadata and content/trust verification pass, the latter in 1922.6411205229815 seconds. The signed cache copy then raises TimeoutExpired at its unchanged 3600-second limit. This executed phase is missing from the commands array because the original helper appends only after subprocess.run returns; its traceback and complete original streams are retained. require-sigs remains true. Destination registration, full destination verification and source-after comparison were not reached, nor any image, activation, PID1 or VM. The original 894-path toplevel build remains valid within its original build scope; the partial cache is not a qualified root. Future SSD recovery is independent and not scored here.

Evidence: `NIX-ROOT-PREPARATION-REVIEW`, `NIX-ROOT-PREPARATION-ARTIFACTS`, `NIX-ROOT-PREPARATION-ORIGINAL`, `NIX-ROOT-PREPARATION-JOB`, `NIX-ROOT-PREPARATION-COPY-STDERR`, `NIX-ROOT-PREPARATION-SOURCE-VERIFY`, `NIX-ROOT-PREPARATION-SOURCE`.

## Test index

| ID | Subsystem and case | Current status | Minimum repetition/duration |
| --- | --- | --- | --- |
| [SYS-01](#sys-01) | Boot identity, reproducible stack and recovery | `blocked` | 20; case sequence |
| [SYS-02](#sys-02) | Owner hardware and feature inventory | `not_run` | 1; case sequence |
| [SYS-04](#sys-04) | CPU topology, usable memory and computation integrity | `not_run` | 3; 10 min per trial |
| [DISP-01](#disp-01) | Cold native full-panel scanout and geometry | `not_run` | 10; case sequence |
| [DISP-02](#disp-02) | All stock refresh modes and transitions | `not_run` | 3; 120 s per steady trial; 5 trials per directed transition |
| [DISP-03](#disp-03) | Backlight range, symmetry and blanking | `not_run` | 20; case sequence |
| [DISP-04](#disp-04) | USB-C external display and docking | `not_run` | 20; case sequence |
| [TOUCH-01](#touch-01) | Ten-contact touch, geometry and rotations | `not_run` | 3; case sequence |
| [PEN-01](#pen-01) | Native inking, pressure, tilt, hover and geometry | `not_run` | 3; case sequence |
| [PEN-02](#pen-02) | Palm rejection and display/pen interaction | `not_run` | 3; 10 min per supported refresh |
| [PEN-03](#pen-03) | Magnetic attachment and actual pen charging | `blocked` | 3; at least 30 min per charge condition |
| [PEN-04](#pen-04) | Bluetooth pen auxiliary functions | `not_run` | 10; case sequence |
| [KEY-01](#key-01) | Cover keyboard, physical layout and lifecycle | `not_run` | 20; case sequence |
| [PAD-01](#pad-01) | Cover touchpad and multi-finger gestures | `not_run` | 3; case sequence |
| [SWITCH-01](#switch-01) | Power/volume keys, cover Hall and wake policy | `not_run` | 20; case sequence |
| [WIFI-01](#wifi-01) | Wi-Fi association, throughput, latency and reliability | `not_run` | 3; 30 s per throughput trial plus 60 min stability |
| [WIFI-02](#wifi-02) | Confirmed hotspot/P2P services and Wi-Fi/BT coexistence | `not_run` | 3; 30 min coexistence |
| [BT-01](#bt-01) | Bluetooth controller, BLE/HID and audio profiles | `not_run` | 3; 30 min audio/profile stability |
| [USB-01](#usb-01) | USB-C device role, link speed and data integrity | `not_run` | 20; case sequence |
| [USB-02](#usb-02) | USB host, hub and role switching | `not_run` | 20; case sequence |
| [AUDIO-01](#audio-01) | All internal speakers and amplifier calibration | `blocked` | 3; 30 min sustained playback |
| [AUDIO-02](#audio-02) | Internal microphones, capture and duplex audio | `blocked` | 3; 10 min duplex |
| [AUDIO-03](#audio-03) | USB-C analog/digital and headset route changes | `not_run` | 20; case sequence |
| [FM-01](#fm-01) | RTC6226 tuning, reception, audio and recovery | `blocked` | 3; 30 min per required route; 20 lifecycle cycles |
| [CAM-01](#cam-01) | Rear camera still/video and application pipeline | `blocked` | 3; 30 stills plus 10 min per required stream |
| [CAM-02](#cam-02) | Front camera still/video and application pipeline | `blocked` | 3; 30 stills plus 10 min per required stream |
| [SENS-01](#sens-01) | Accelerometer, gyroscope, magnetometer and orientation | `blocked` | 3; case sequence |
| [SENS-02](#sens-02) | Ambient/RGB sensing and automatic brightness | `not_run` | 20; case sequence |
| [STOR-01](#stor-01) | UFS filesystem integrity, throughput and recovery | `not_run` | 3; case sequence |
| [STOR-02](#stor-02) | microSD compatibility, integrity and safe reinsert | `not_run` | 3; case sequence |
| [PWR-01](#pwr-01) | Fuel-gauge units, sign, trends and desktop reporting | `not_run` | 3; case sequence |
| [PWR-02](#pwr-02) | Sustained charging and actual negotiated protocols | `blocked` | 3; 45 min steady trial;20 replug cycles |
| [PWR-03](#pwr-03) | Charge limits, thermal controls and watchdog ownership | `blocked` | 3; case sequence |
| [PM-01](#pm-01) | Screen-on/off idle and runtime power management | `not_run` | 3; 30 min per condition |
| [PM-02](#pm-02) | Real suspend entry, wake and complete device restoration | `not_run` | 20; 20 cycles plus3x8h sleep |
| [THERM-01](#therm-01) | Sustained CPU/GPU performance and thermal regulation | `not_run` | 3; 20 min sustained plus idle cooldown |
| [GPU-01](#gpu-01) | Actual native MSM device, firmware and API inventory | `not_run` | 1; case sequence |
| [GPU-02](#gpu-02) | OpenGL/GLES hardware draw and readback correctness | `not_run` | 3; 30 min stability |
| [GPU-03](#gpu-03) | Vulkan submissions, synchronization and readback | `not_run` | 3; 30 min stability |
| [GPU-04](#gpu-04) | Wayland/KWin hardware composition and native presentation | `not_run` | 3; case sequence |
| [GPU-05](#gpu-05) | Per-process GPU address-space isolation and bounded recovery | `blocked` | 3; case sequence |
| [VIDEO-01](#video-01) | Native hardware decode and application use | `blocked` | 3; 10 min per required stream |
| [VIDEO-02](#video-02) | Hardware encode where stock exposes it | `not_run` | 3; 10 min per mode |
| [SYS-03](#sys-03) | Complete daily-use combination and soak | `not_run` | 1; 24 h mixed-use soak |

## Detailed attended procedures

All criteria below are pending. Repetition counts include the case-specific
cycles described in each procedure; three paired performance trials are an
additional comparison requirement where a profile is used. A future result
must name which conditions and modes each trial covered.

### SYS-01

**Boot identity, reproducible stack and recovery** — `blocked`.

**Known baseline:** Owner stock is TB371FC Android 14 / 4.19.157-perf+, with conflicting lock fields, CONFIG_KEXEC=n, forced module signatures/versioning and no ACM. Eight current partitions have verified off-device copies; restore and actual entry remain untested. Research1/research2 builds and generic VM boots succeeded; a separate signed research2 joint input/display bundle and full research1 Fedora systemd/Enforcing VM now exist. The new public 4.19.325 bridge and default-HOLD rescue initramfs compile, but its generic VM fails in Qualcomm SCM before PID1; the initramfs passed only under the frozen research2 reference Image. An unsigned owner-layout v2 candidate passed independent format checks only. No owner Linux boot, bootloader acceptance, runtime placement, kexec execution or recovery transport has been demonstrated. The owner exposes two not-attached UDCs and doesvm has no matching gadget; the later fixed-a600000 ramdisk passed only mocked selection, reference-kernel PID1 and private-v2 format checks. Full NixOS toplevel store realization is separately recorded without activation or system boot. Full independent research3/research4 Image and 84-module builds have passed offline qualification, including the joint DT and standard SMMU. The separate Fedora R3 run failed before pids/BPF behavioral probes. Matched-source early SELinux analysis and a same-process ARM bootstrap now have build/API-only evidence; the separate v5 production result is now retained as failed at rootfs filesystem association before systemd. Fresh owner/host USB snapshots still do not demonstrate an entry/recovery link. The first R4 Fedora verification also remains failed: ordinary real-broker round trips passed, while unrestricted FD transport reset before pids/BPF, with a separate observed early queued-udev-FD loss. The v5 attempt also remains failed: first policy load succeeded Enforcing, but /var relabel was denied by filesystem association before systemd. The separate v6 candidate now has actual archive, tmpfs migration/cleanup and same-boot init_t/udev_t observations, but failed complete verification on policy/API-label AVCs and a manager-side FIFO denial with truncated FDs; pids/BPF workers did not run. The earlier paired USB capture at 06:09 UTC (14:09 Asia/Shanghai) still leaves the owner entry/recovery transport unverified. The separate v7 run observes successful early reload/API labels, the real controlled three-FD route and TasksMax behavior; it still fails overall at a PL061 fixture and retains two visible AVCs plus corrupted serial frames. BPF attachment is observed, but the restricted-filesystem workload did not run. All owner native-Linux counts remain zero. The separate v8 generic run later completed its paired BPF open-EPERM, pids, signed-module and persistent-result gates but still failed on one journalctl AVC. The new seven-permission policy and V4 loader are qualified offline; the first v9 image attempt timed out before any VM. R5 now supplies a fully built, signed 84-module kernel with the original Nix/Nura service prerequisites, without a new R5 boot result. The newest retained USB pair at 09:36:24-25 UTC (17:36 Shanghai) still demonstrates no owner-to-doesvm recovery/data link. The first native Nix registered-root preparation later failed at the original 3600-second signed-cache copy after successful source verification; no destination qualification, image or NixOS boot was reached.

Evidence: ANDROID-STOCK, ANDROID-BOOT, ANDROID-BOOT-CAPABILITIES, ANDROID-BOOT-BACKUP, BOOT-BACKUP-OFFDEVICE, BOOT-HEADER-HOST, BOOT-READINESS, ENTRY-SOURCE, ENTRY-METADATA, KERNEL-HOST, KERNEL-ARTIFACTS, QEMU-INITIAL, QEMU-FIXED, R2-BUILD, R2-ARTIFACTS, R2-QEMU, DTB-HOST, GPU-STAGE-ELF, GPU-STAGE-MDT, DISTRO-SOURCE, INPUT-ARTIFACTS, INPUT-SIGNED-ARTIFACTS, STOCK-FIRMWARE-STAGING, SELINUX-HOST, FEDORA-SYSTEM-ARTIFACTS, INITRAMFS-VALIDATION, ENTRY-RECONSTRUCTION, ENTRY-RECONSTRUCTION-ARTIFACTS, ANDROID-USB-TRANSPORT, HOST-USB-TRANSPORT, USB-TRANSPORT-REVIEW, ENTRY-OWNER-UDC, ENTRY-OWNER-UDC-ARTIFACTS, NIX-SYSTEM-ARTIFACTS, R3-KERNEL-ARTIFACTS, R4-KERNEL-ARTIFACTS, R4-KERNEL-VERIFICATION, FEDORA-R3-ARTIFACTS, ARM64-BPF-REVIEW, SELINUX-AV-ARTIFACTS, SELINUX-COPY-ARTIFACTS, EARLY-SELINUX-ARTIFACTS, ANDROID-USB-FOLLOWUP, HOST-USB-FOLLOWUP, FEDORA-R4-FIRST, FEDORA-R4-FIRST-ARTIFACTS, FEDORA-R4-FIRST-VERIFY, FEDORA-R4-FIRST-SERIAL, FEDORA-R4-FIRST-LABEL, FEDORA-R4B-EARLY, FEDORA-R4B-EARLY-ARTIFACTS, FEDORA-R4B-EARLY-VERIFY, FEDORA-R4B-EARLY-SERIAL, FEDORA-R4B-EARLY-LABEL, FEDORA-R4B-EARLY-ARCHIVE, SELINUX-ROOTFS-REVIEW, SELINUX-ROOTFS-ARTIFACTS, TMPFS-BOOTSTRAP-REVIEW, TMPFS-BOOTSTRAP-ARTIFACTS, USB-RECHECK-REVIEW, ANDROID-USB-RECHECK, HOST-USB-RECHECK, FEDORA-R4C-TMPFS, FEDORA-R4C-TMPFS-ARTIFACTS, FEDORA-R4C-TMPFS-VERIFY, FEDORA-R4C-TMPFS-SERIAL, FEDORA-R4C-TMPFS-LABEL, FEDORA-R4C-TMPFS-ARCHIVE, FEDORA-R4C-TMPFS-PROOF-PAYLOAD, FEDORA-R4C-TMPFS-UDEV, FEDORA-R4C-TMPFS-SOURCE, FEDORA-R4D-ARTIFACTS, FEDORA-R4D-SERIAL, FEDORA-R4D-POLICY-EXPORT, FEDORA-R4E-ARTIFACTS, FEDORA-R4E-GUEST, SOCKET-POLICY-ARTIFACTS, EARLY-SOCKET-LOADER-REVIEW, FEDORA-R4F-ARTIFACTS, R5-ARTIFACTS, R5-TRANSFER, ANDROID-USB-RECHECK-1736, HOST-USB-RECHECK-1736, NIX-ROOT-PREPARATION-ARTIFACTS, NIX-ROOT-PREPARATION-ORIGINAL. Dependencies: preflight assembly and recovery.

**Current blocker:** The compiled bridge, private format-only v2 candidate and separately booted Fedora root do not demonstrate a matched owner entry/board handoff, runtime memory placement or usable recovery control route. The measured stock kernel has CONFIG_KEXEC=n, enforced module signatures/versioning and no configured ACM function; a new payload or historical module cannot establish stock-to-mainline execution. The property/command-line lock-state disagreement and actual bootloader/temporary-boot acceptance remain unresolved.

**Before running:** One named kernel/DTB/initramfs/module/firmware/rootfs stack; owner boot-entry and recovery method resolved first.

**Android work still required:** Confirm the actual owner bootloader entry state, available transport, ordinary Android cold/warm boot and recovery behavior; do not resolve conflicting lock fields by assumption. Retain the verified current-partition backup and exact slot identities. Establish a matched first-stage/loader and usable recovery console: installing a kexec executable cannot supply CONFIG_KEXEC=n, and historical modules/ACM behavior cannot bypass current signature, ABI or USB-function constraints.

**Linux procedure:**

1. Record hashes of all eight stack components and exact native driver/workaround configuration; verify loaded release/build identity against the boot manifest. Record the final flat root compatible: the board-specific early pool guard requires lenovo,tb371fc; a legacy recovery overlay retaining only qcom,kona identifiers takes a different allocator path.
2. Perform 10 controlled cold boots and 10 warm reboots, retaining success/time/error counters and confirming normal shutdown.
3. Demonstrate the documented recovery route returns to the known baseline with its data intact; re-enter the identical test stack.

**Required result:**

- `SYS-01.C01`: All 20 boots reach the intended Linux session without hidden watchdog-reset checkpoints or manual driver rescue.
- `SYS-01.C02`: Loaded modules have the same build ABI/Module.symvers/signing policy; no historical .ko reuse by filename.
- `SYS-01.C03`: Recovery and shutdown succeed; no stock-data or boot-policy corruption.

Minimum repetitions: 20. Comparison profiles: fixed functional criteria only.

### SYS-02

**Owner hardware and feature inventory** — `not_run`.

**Known baseline:** Owner captures now cover selected display/input/radio/power nodes plus two CameraService devices, sensor-family declarations, one ALSA card/32 PCM entries, four bound tfa98xx clients, FSA4480 and RTC6226/radio0. These are passive identities/capabilities, not frames, samples, audio or FM reception. Camera silicon, acoustic/codec variants, microphones, full stream matrices and remaining board/accessory functions are unresolved. OCH8801-0 at 3-0018 has no driver symlink and remains a candidate; it is not proven absent or interchangeable with the advertised ROHM Hall sensor. A later fixed GPU-property read resolves chip ID 0x06050002; bounded radio metadata/current-buffer reads still do not resolve WLAN board or Bluetooth ROM selection. The later cached WLAN version/BDF descriptor fields do not supply QMI board_id or a selected filename. Two USB UDC interfaces and the configured primary are now observed, without proving a host link. The later owner cached HQ amplifier slot reports tfa98xx_QS.cnt, with shipping-binary proof that it is a shared first-registration cache preceding asynchronous load completion; four independent choices or physical amplifier identities remain unproved. CNSS shipping static analysis resolves a cache layout but not a valid, lifecycle-safe live snapshot or historical BDF filename.

Evidence: ANDROID-STOCK, ANDROID-GPU, ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX, ANDROID-GPU-CHIPID, ANDROID-RADIO-METADATA, ANDROID-RADIO-SELECTION, ANDROID-RADIO-VERSION, RADIO-SELECTION-REVIEW, ANDROID-USB-TRANSPORT, TFA-CACHED-ANDROID, TFA-CACHED-STATIC, TFA-CACHED-REVIEW, CNSS-SHIPPING-STATIC, ANDROID-RADIO-IPC, ANDROID-RADIO-PROBE, ANDROID-TRACEPOINT-CAPABILITY, ANDROID-USB-FOLLOWUP, ANDROID-USB-RECHECK. Dependencies: SYS-01.

**Before running:** Same tablet and owned accessories; enumerate before executing device-specific electrical paths.

**Android work still required:** Resolve exact fitted camera and amp/codec/acoustic variants, microphone count/routes, sensor transports/axes and remaining Hall/button candidates without treating generic DT names as chip IDs. Complete UFS/microSD, DP, USB, FM/antenna and other radio/accessory capability inventory with attended checks. Record any physically absent feature explicitly. An absent Linux driver never proves a feature is absent from the tablet.

**Linux procedure:**

1. Build an owner inventory matching each Android-present feature to a Linux driver, userspace route and test ID.
2. Record every additional Android-present feature as a new required case; freeze camera modes, video codecs, radio features and application/API requirements before Linux acceptance.

**Required result:**

- `SYS-02.C01`: Every Android-present hardware feature is covered by a case; no disabled device is deleted from scope.
- `SYS-02.C02`: All identity uncertainty is resolved before loading board-specific firmware/calibration or camera/amp configuration.

Minimum repetitions: 1. Comparison profiles: fixed functional criteria only.

### SYS-04

**CPU topology, usable memory and computation integrity** — `not_run`.

**Known baseline:** Android exposes three CPU frequency policies for CPUs 0-3, 4-6 and 7. The passive capture did not measure available RAM, sustained calculation correctness or cross-core behavior.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: SYS-01, SYS-02, PWR-01.

**Before running:** Normal DVFS/thermal policy; ordinary userspace allocations bounded to at most 25 percent of current MemAvailable; no reserved-memory, raw /dev/mem or forced CPU/voltage writes.

**Android work still required:** Record all eight CPUs, possible/online topology and usable memory/reservations on Android; run the same bounded deterministic CPU/memory workload and retain checksums.

**Linux procedure:**

1. Account for fitted RAM against available/reserved regions and the selected DT; check every expected CPU can execute work under normal scheduler policy.
2. Run a reviewed deterministic multiworker CPU/memory integrity workload three times for ten minutes within the stated allocation bound, checking expected results.
3. Repeat its short correctness subset after suspend and the final soak; distinguish legitimate reservations from lost memory or offlined cores.

**Required result:**

- `SYS-04.C01`: All eight expected CPUs and the accounted usable memory are available under normal policy; no unexplained capacity loss or offline core.
- `SYS-04.C02`: All deterministic results match with no memory error, corruption, OOM, reset or silent protection bypass.

Minimum repetitions: 3. Duration: 10 min per trial. Comparison profiles: paired-throughput.

### DISP-01

**Cold native full-panel scanout and geometry** — `not_run`.

**Known baseline:** Android selects Tianma, 2944x1840 dual-DSI/DSC; one slice per packet in captured DT. Research1 base DT retains disabled DSI1. The separately built research2 display DT enables both DSI/PHY links and the Tianma panel with qualified driver matches, but no native scanout or panel action was tested. The separately compiled joint input/display DT retains that display graph and enables inherited touch; this remains host artifact evidence.

Evidence: ANDROID-STOCK, DISPLAY-DECODE, DISPLAY-SOURCE, DTB-HOST, R2-BUILD, R2-ARTIFACTS, INPUT-ARTIFACTS, INPUT-SIGNED-ARTIFACTS. Dependencies: SYS-01.

**Before running:** Native MSM DPU plus both DSI links; cold init without retained splash; initially fixed 60 Hz and matched luminance.

**Android work still required:** Observe the same full-screen color bars, single-pixel grids, text, gradients and frame counters under Android; record orientation and seam.

**Linux procedure:**

1. Start from cold power state and present test patterns across both halves at 2944x1840.
2. Retain the active mode, per-link DSI timings/clocks and effective DSC/PPS settings from the selected driver diagnostics; distinguish requested DT defaults from applied state and avoid arbitrary raw-register reads.
3. Check edges, seam, gradients, clipping, color/channel order and frame continuity; log DPU/DSI/DSC faults.
4. Repeat after a userspace compositor restart and after the later suspend gate.

**Required result:**

- `DISP-01.C01`: All pixels across both halves are correctly addressed, with no corruption, tearing seam, crop or persistent boot splash.
- `DISP-01.C02`: Native DPU/dual-DSI owns scanout; inherited simpledrm, 640x400 diagnostics or software-only presentation do not satisfy this case.

Minimum repetitions: 10. Comparison profiles: paired-quality.

### DISP-02

**All stock refresh modes and transitions** — `not_run`.

**Known baseline:** Android advertises 30/60/120/144 Hz; actual active rates and 144 Hz transition mechanism were not measured.

Evidence: ANDROID-STOCK, DISPLAY-DECODE, DISPLAY-SOURCE. Dependencies: DISP-01.

**Before running:** Test every owner-verified advertised mode, not just default; same light rendering pattern and measurement method.

**Android work still required:** Measure active cadence at 30/60/120/144 Hz and document which transitions Android actually supports; retain any unsupported-mode evidence instead of assuming advertising means success.

**Linux procedure:**

1. For each supported rate measure three 120-second steady runs using active timings and independent cadence observation.
2. Attach the actual per-link DSI/DSC/PPS and active clock/mode evidence for each rate, with unavailable values left unknown; correlate pen tests with the confirmed B3 table difference without assigning unproven register semantics.
3. Exercise all 12 directed transitions among four rates five times, including the 120-to-144 and 144-to-120 paths.
4. Run a light animated pattern and then pen activity; log each requested/active mode and presentation discontinuity.

**Required result:**

- `DISP-02.C01`: Every confirmed stock mode works at full geometry; silently capping at 60/120 Hz is incomplete.
- `DISP-02.C02`: All planned transitions recover to their requested active mode without stale halves, reset, unexplained fallback or pen loss.

Minimum repetitions: 3. Duration: 120 s per steady trial; 5 trials per directed transition. Comparison profiles: active-refresh, paired-latency.

### DISP-03

**Backlight range, symmetry and blanking** — `not_run`.

**Known baseline:** Android reports requested brightness 294/2047 and actual_brightness 0; that getter alone is not measured darkness. Two KTZ8866 controllers are captured.

Evidence: ANDROID-STOCK, DISPLAY-SOURCE, STATIC-FIXES. Dependencies: DISP-01.

**Before running:** Use measured luminance/reference patterns, identical ambient light and confirmed amp/panel supplies; do not equate raw brightness numbers across drivers.

**Android work still required:** Measure minimum usable and maximum normal luminance, five intermediate levels, left/right uniformity and blank/unblank on Android.

**Linux procedure:**

1. Sweep the supported brightness range including zero and the minimum usable step; compare both halves and flicker.
2. Perform 20 blank/unblank cycles and restoration after compositor/session restart.
3. Record requested and measured brightness independently; inspect I2C error handling without treating mock tests as runtime proof.

**Required result:**

- `DISP-03.C01`: One logical control drives both halves consistently; zero truly blanks and the previous level restores without a stuck half.
- `DISP-03.C02`: Usable luminance range, monotonicity and uniformity meet the frozen Android quality comparison.

Minimum repetitions: 20. Comparison profiles: paired-quality.

### DISP-04

**USB-C external display and docking** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** DP Alt Mode and redriver wiring are historical source clues; the owner capture confirms PS5169 binding, not DP output.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX, DISPLAY-SOURCE. Dependencies: SYS-02, USB-02, DISP-01.

**Before running:** Owned known-good dock/cable/display; both USB-C orientations; test shared USB, charging and audio paths.

**Android work still required:** Confirm owner Android external-display support and exact modes/refresh/audio/USB coexistence with this dock.

**Linux procedure:**

1. Connect/disconnect 20 times, test mirror and extended desktop where supported, and run 30 minutes at each baseline mode.
2. Verify picture, link retraining, display audio, USB transfers and charging coexistence; repeat after suspend.

**Required result:**

- `DISP-04.C01`: All confirmed stock external-display modes remain usable with correct output and no internal-panel corruption.
- `DISP-04.C02`: Dock attach/role changes recover without manual service reload; unsupported Linux DP is not treated as absent hardware.

Minimum repetitions: 20. Comparison profiles: paired-quality.

### TOUCH-01

**Ten-contact touch, geometry and rotations** — `not_run`.

**Known baseline:** Android NVTCapacitiveTouchScreen advertises ten contacts, 18400x29440 ranges, touch-major 255 and finger pressure maximum 1; no live strokes were captured. Original research2 keeps SPI14/touch disabled, while the separately compiled joint DT enables them without new GPIO assumptions. Patches 0018/0019, the Novatek module and 18 source-derived fault-injection groups passed host checks; a separate signed bundle retains exact research2 ABI. Both revision-6 firmware alternatives were staged, but physical panel-ID selection, pin ownership, loading, display-before-touch ordering and actual input remain unobserved.

Evidence: ANDROID-STOCK, INPUT-SOURCE, R2-ARTIFACTS, R2-MODULES, FIRMWARE-CONTRACT, STOCK-FIRMWARE-RECEIPT, INPUT-BUILD, INPUT-ARTIFACTS, INPUT-SIGNED-ARTIFACTS, STOCK-FIRMWARE-STAGING. Dependencies: DISP-01.

**Before running:** Fresh event-node mapping; all four logical orientations and all validated panel rates; test synthetic motions only.

**Android work still required:** Measure edge coverage, grid accuracy/jitter, ten-finger tracking and touch-to-photon timing under Android.

**Linux procedure:**

1. Trace a 5x5 grid and edges, slow diagonals and circles; hold ten contacts and cross/move them without changing IDs.
2. Repeat in all rotations and after 20 blank/unblank and detach/resume interactions.
3. Record dropped/stuck contacts and spatial/timing error against the matched baseline.

**Required result:**

- `TOUCH-01.C01`: Ten independent contacts work with correct orientation, edge coverage and release; no ghost or stuck touch.
- `TOUCH-01.C02`: Coordinate scaling is consistent with 18400x29440 reports; finger pressure is not misrepresented as the pen pressure sensor.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

Command templates: `input-list`, `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### PEN-01

**Native inking, pressure, tilt, hover and geometry** — `not_run`.

**Known baseline:** Novatek pen advertises 18400x29440, pressure 0..4095, tilt +/-60, distance 0..1 and two barrel buttons. Owner Android physical resolution is zero/unknown. Compiled patch 0018 removes donor 148x237 mm constants and accepts only paired valid touchscreen-x-mm/y-mm properties; the joint DT supplies no guessed dimensions, so resolution remains unknown. This fixes metadata handling without measuring active digitizer area or strokes.

Evidence: ANDROID-STOCK, INPUT-SOURCE, STATIC-FIXES, INPUT-BUILD, INPUT-ARTIFACTS, INPUT-SIGNED-ARTIFACTS. Dependencies: TOUCH-01.

**Before running:** Use the same pen/nib and a pressure-aware app; confirm active physical area and axis mapping before changing counts/mm.

**Android work still required:** Measure grid and edge accuracy, pressure ramps, tilt response, hover and stroke latency; identify exact button semantics.

**Linux procedure:**

1. Draw repeated slow/fast diagonals, 5x5 targets and ten normal-force pressure ramps; do not force the pen to reach an advertised maximum.
2. Test controlled tilts, hover entry/exit and both buttons, then repeat at each refresh and orientation.
3. Verify input metadata and application-visible behavior separately, with calibrated physical dimensions.

**Required result:**

- `PEN-01.C01`: Position, pressure, tilt, hover and both buttons function through the Novatek SPI path and the chosen application.
- `PEN-01.C02`: No stuck tool/contact, broken scale or edge offset; BT pen enumeration does not satisfy inking.
- `PEN-01.C03`: Physical resolution metadata is supported by measured active area and orientation, rather than unverified donor defaults.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

Command templates: `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### PEN-02

**Palm rejection and display/pen interaction** — `not_run`.

**Known baseline:** Android pen-related panel commands differ at B3 for 144 Hz. Their runtime meaning/dispatch is unmeasured; native counterpart is not established. The input patches do not add panel-follower coordination or establish the display-before-touch restart order.

Evidence: DISPLAY-DECODE, DISPLAY-SOURCE, INPUT-SOURCE, INPUT-BUILD, INPUT-ARTIFACTS. Dependencies: PEN-01, DISP-02.

**Before running:** Pen hover/contact with palm resting, touch enabled; supported rates/orientations; blank/unblank and GPU workload scenarios.

**Android work still required:** Record Android palm/touch behavior during pen hover and contact, and behavior when entering/leaving 144 Hz.

**Linux procedure:**

1. Write for ten minutes at each supported rate with palm rests, lifting/re-entering hover and pressing the buttons.
2. Switch display modes during pen activity, then blank/unblank and resume; compare false touches and lost strokes.
3. Record any pen-specific panel command implementation and measured effect without inferring semantics from B3 alone.

**Required result:**

- `PEN-02.C01`: No unintended palm strokes or permanent touch suppression; drawing remains continuous across validated transitions.
- `PEN-02.C02`: Touch disabled globally, 144 Hz removed, or pen features disabled is incomplete rather than a fix.

Minimum repetitions: 3. Duration: 10 min per supported refresh. Comparison profiles: paired-quality, paired-latency.

### PEN-03

**Magnetic attachment and actual pen charging** — `blocked`.

**Known baseline:** CTN730 is bound at /soc/i2c@984000/ctn730@28, GPIO84/160/111; distinct from PS5169 at another 0x28. No charging cycle was measured and no complete mainline CTN730 port is established.

Evidence: ANDROID-STOCK, INPUT-SOURCE, HISTORICAL-MATRIX. Dependencies: SYS-02, PWR-01.

**Current blocker:** Reviewed CTN730 Linux driver/binding and actual charging baseline are not yet available.

**Before running:** Known pen starting charge below full; same tablet SOC/charger state, dock position and temperature; independent pen charge telemetry or run-time method.

**Android work still required:** Measure Android dock detection, charge trend over at least 30 minutes, undock recovery and screen-off charging; validate what the pen battery report means.

**Linux procedure:**

1. Repeat 20 attach/detach events and check controller/pen state without reading the downstream cn_test attribute.
2. Measure a 30-minute charge session and a screen-off session, then verify the pen remains usable and charging stops/changes appropriately when removed.
3. Compare energy/charge progress and temperatures with the Android reference; test reattachment after suspend.

**Required result:**

- `PEN-03.C01`: Dock sensing and measurable pen energy/charge increase are both demonstrated; BT pairing, an input node or an attached flag alone cannot pass.
- `PEN-03.C02`: Charging ownership, shutdown and temperature behavior are correct; no CTN730/PS5169 address confusion or forced charging-test getter.

Minimum repetitions: 3. Duration: at least 30 min per charge condition. Comparison profiles: paired-quality.

### PEN-04

**Bluetooth pen auxiliary functions** — `not_run`.

**Known baseline:** Lenovo Precision Pen 3 Mouse and Consumer Control expose Bluetooth VID:PID 17ef:612b; this is separate from SPI inking and CTN730 charging.

Evidence: ANDROID-STOCK, INPUT-SOURCE. Dependencies: BT-01.

**Before running:** Same pen and recorded Android auxiliary-button/battery features; no pairing/address identifiers in published logs.

**Android work still required:** Identify which advertised BT reports have a real owner-visible Android action or telemetry.

**Linux procedure:**

1. Pair/reconnect ten times; exercise every confirmed auxiliary action and test reconnect after pen/tablet sleep.
2. Verify that inking and charging do not falsely depend on a desktop BT button mapping.

**Required result:**

- `PEN-04.C01`: All confirmed pen BT functions operate and reconnect; unsupported unobserved functions remain explicitly unknown.
- `PEN-04.C02`: Passing this test never changes PEN-01 or PEN-03 to pass.

Minimum repetitions: 10. Comparison profiles: fixed functional criteria only.

### KEY-01

**Cover keyboard, physical layout and lifecycle** — `not_run`.

**Known baseline:** Lenovo Keyboard Pack for Spinel 17ef:6175, I2C-HID at a94000/0x60; reset114/wake108/IRQ110. Descriptor has keyboard/touchpad/consumer collections and no Input ID6. Generic I2C-HID OF/core and hid-multitouch objects compiled, and the joint DT explicitly enables the inherited keyboard. The pinned public downstream driver defaults an unspecified trigger to level-low, but it is not proven byte-equivalent to the owner binary; MCU wake assignment and physical lifecycle remain unresolved.

Evidence: ANDROID-STOCK, HID-DECODE, INPUT-SOURCE, INPUT-BUILD, INPUT-ARTIFACTS, INPUT-SIGNED-ARTIFACTS. Dependencies: SYS-01.

**Before running:** Correct cover; synthetic typing in a dedicated test view; cold-attached and hot-attached cases.

**Android work still required:** Map every physical key/Fn/consumer key and LED actually present; record repeat, modifiers and stock hotplug/wake behavior.

**Linux procedure:**

1. Exercise all keys, modifiers/chords, repeats and consumer functions; aggregate expected/received counts.
2. Perform 20 detach/reattach cycles and ten cold-attached boots; test wake and key-release recovery after suspension.
3. Check for stuck keys/IRQ storms and verify the actual wake/reset/IRQ sequence; do not borrow the 17ef:6127 status parser.

**Required result:**

- `KEY-01.C01`: Every physical key and confirmed consumer function maps correctly with zero lost, duplicated or stuck events in the prescribed sequence.
- `KEY-01.C02`: Cold attach, hotplug and wake work without manual rebind or persistent active IRQ storms.

Minimum repetitions: 20. Comparison profiles: paired-latency.

Command templates: `input-list`, `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### PAD-01

**Cover touchpad and multi-finger gestures** — `not_run`.

**Known baseline:** Owner Android touchpad has four slots (0..3), X0..2998/Y0..1771, resolution31, POINTER/BUTTONPAD; HID report ID3 is 29 bytes including ID. The corresponding generic HID objects compiled in the separate input integration; no physical gesture/delivery test followed.

Evidence: ANDROID-STOCK, HID-DECODE, INPUT-SOURCE, INPUT-ARTIFACTS, INPUT-SIGNED-ARTIFACTS. Dependencies: KEY-01.

**Before running:** Same pointer settings recorded on both systems; platform gesture mapping documented separately from raw contact delivery.

**Android work still required:** Record pointer, click/drag, scroll, multi-finger capability, palm rejection and gesture actions actually available on Android.

**Linux procedure:**

1. Test slow/fast motion, edge reaches, clicks, drag-and-drop, two-finger scroll and supported three/four-finger contacts/gestures.
2. Type while resting near the pad to test palm rejection; repeat after 20 cover cycles and suspend.
3. Compare motion/scroll latency and jitter; verify no coordinate-range or contact-count clipping.

**Required result:**

- `PAD-01.C01`: All confirmed raw contacts, button/drag/scroll functions work; gesture bindings are documented and usable in the desktop.
- `PAD-01.C02`: No stuck button, accidental palm click or loss after reattach; an external mouse is not a substitute.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

Command templates: `input-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### SWITCH-01

**Power/volume keys, cover Hall and wake policy** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** Owner SensorService advertises ROHM bu52053nvx Hall wakeup/non-wakeup descriptors, without lid/cover/pen actions. A distinct OCH8801-0 I2C/DT candidate at 3-0018 has no driver symlink; its physical role or absence is not established. Complete physical button mapping and actual wake behavior remain unmeasured.

Evidence: ANDROID-STOCK, ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, KEY-01.

**Before running:** Use actual owner-present buttons and cover states; distinguish wake, display blank and system suspend.

**Android work still required:** Map physical buttons, Hall/lid states, long-press behavior and which inputs Android permits to wake the tablet.

**Linux procedure:**

1. Exercise each switch 20 times, including lid/cover close/open and permitted wake sources.
2. Repeat with pen docked, keyboard attached and charging; confirm no phantom transitions or unintended reboot.

**Required result:**

- `SWITCH-01.C01`: All owner-present buttons/switches work with the intended policy and restore the complete input/display session.
- `SWITCH-01.C02`: A missing Linux Hall/button device cannot be recorded as absent hardware.

Minimum repetitions: 20. Comparison profiles: fixed functional criteria only.

### WIFI-01

**Wi-Fi association, throughput, latency and reliability** — `not_run`.

**Known baseline:** Owner PCI 17cb:1101 is bound to Android cnss_pci; subsystem 17cb:0108/revision 01 identify PCI metadata, not the QMI board ID. Research2 builds ath11k/MHI but disables all PCIe controllers. Canonical API1 amss.bin/m3.bin were staged; no arbitrary board-2.bin/board.bin was selected. Fixed static metadata and the current retained kernel buffer did not reveal BDF/board-ID tokens. No association/throughput trial, firmware ABI or mainline radio probe is demonstrated. A bounded cached-version read reports FW 1.0.1.0.1596.0 and BDF version 0x8/reference 0/customer 0/project 0/board revision 1; source review shows these descriptors are distinct from QMI board_id and cannot select one BDF candidate. No approved IPC debugfs endpoint exists in the running DEBUG_FS=n kernel, so no ring bytes were read. The kprobe route is disabled; a normal fork tracepoint capability is separately present. Actual shipping Image analysis confirms helper dispatch/cache offsets but response validity and object lifetime remain unresolved, and the selected historical filename is not cached. No dynamic BPF program or live-memory read was performed.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX, POWER-SOURCE, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT, STOCK-FIRMWARE-STAGING, ANDROID-RADIO-METADATA, ANDROID-RADIO-SELECTION, ANDROID-RADIO-VERSION, RADIO-SELECTION-REVIEW, ANDROID-RADIO-IPC, RADIO-IPC-REVIEW, ANDROID-RADIO-PROBE, RADIO-PROBE-REVIEW, ANDROID-TRACEPOINT-CAPABILITY, CNSS-SHIPPING-STATIC, CNSS-SHIPPING-REVIEW. Dependencies: SYS-01.

**Before running:** Same AP/server/channel/width/regulatory domain, tablet placement, power state and test data; cover 2.4 and 5 GHz and supported 802.11ax. Do not assume 6 GHz.

**Android work still required:** Measure three paired sessions per band/location, bidirectional LAN throughput and latency, 20 reconnects and sleep reconnection.

**Linux procedure:**

1. Associate using private test credentials; measure 30-second traffic in each direction, repeated at least three times.
2. Run 60-minute mixed traffic and 20 reconnect/roam/replug-equivalent cycles appropriate to the AP setup.
3. Check the final enabled PCIe path, actual ath11k firmware API and runtime board selection before interpreting association results. Raw AMSS is not a firmware-2.bin container, and the stock bdwlan pool cannot justify an arbitrary board-2.bin/board.bin choice.
4. Check PCIe/runtime-PM recovery and filtered error deltas.

**Required result:**

- `WIFI-01.C01`: All confirmed bands/security modes associate without firmware crashes or manual service reload.
- `WIFI-01.C02`: Packet loss/corruption and reconnect failures are zero in the controlled local test; performance meets matched baselines.

Minimum repetitions: 3. Duration: 30 s per throughput trial plus 60 min stability. Comparison profiles: paired-throughput, paired-latency, paired-energy.

Command templates: `wifi-tx`, `wifi-rx` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### WIFI-02

**Confirmed hotspot/P2P services and Wi-Fi/BT coexistence** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** Historical stock interfaces include P2P/Wi-Fi Aware, but owner support/use is not tested. Shared QCA6390 radio coexistence needs its own trial.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX. Dependencies: WIFI-01, BT-01.

**Before running:** Only owner-confirmed services and supported test peers; both radios active under the same baseline workload.

**Android work still required:** Confirm hotspot/P2P/service modes actually exposed on the owner Android system, then measure simultaneous Wi-Fi transfer and BT audio/input.

**Linux procedure:**

1. Exercise each confirmed service with a known peer and repeat reconnects.
2. Run 30 minutes of Wi-Fi load with BT audio and keyboard/pen auxiliary events; measure dropouts, transfer performance and energy.

**Required result:**

- `WIFI-02.C01`: Every confirmed radio service is usable and recovers; no hidden radio disable is used to pass coexistence.
- `WIFI-02.C02`: No audible/event loss or radio firmware crash, and the frozen simultaneous-workload comparison is met.

Minimum repetitions: 3. Duration: 30 min coexistence. Comparison profiles: paired-throughput, paired-latency, paired-energy.

### BT-01

**Bluetooth controller, BLE/HID and audio profiles** — `not_run`.

**Known baseline:** BT pen input 17ef:612b exists on Android. Research2 has available Bluetooth/UART paths and compiled QCA/power-sequencing drivers, without a physical probe. Canonical htbtfw10/20.tlv and htnv10/20.bin pairs are retained because the runtime ROM suffix remains unknown. Owner properties identify hastings only; inspected metadata and current kernel-buffer tokens do not select a ROM. No Linux HCI/profile behavior was tested.

Evidence: ANDROID-STOCK, HISTORICAL-MATRIX, FIRMWARE-CONTRACT, STOCK-FIRMWARE-RECEIPT, STOCK-FIRMWARE-STAGING, ANDROID-RADIO-METADATA, ANDROID-RADIO-SELECTION. Dependencies: SYS-01.

**Before running:** Owned test BLE/HID and audio peers; record supported profiles and codec/microphone route.

**Android work still required:** Confirm Android profile support, connect times, range and 30-minute audio/input behavior on the same peers.

**Linux procedure:**

1. Verify btqca/HCI firmware and controller, pair/reconnect 20 times, and test BLE/HID input.
2. Run stereo playback and any confirmed headset microphone profile for 30 minutes; inspect dropouts and latency.
3. Repeat after suspend, airplane/radio toggles through supported userspace and controller recovery.

**Required result:**

- `BT-01.C01`: All confirmed profiles work with actual traffic/audio and no controller reset loop.
- `BT-01.C02`: No external USB Bluetooth adapter or pen inking is substituted for the internal BT controller.

Minimum repetitions: 3. Duration: 30 min audio/profile stability. Comparison profiles: paired-quality, paired-latency.

### USB-01

**USB-C device role, link speed and data integrity** — `not_run`.

**Known baseline:** Owner Type-C snapshot reports sink/device; PS5169 is bound. Later fixed USB capture exposes a600000.dwc3 and a800000.dwc3, both not attached; Android g1 is configured on a600000.dwc3 with 17ef:7e31. The doesvm snapshot has no matching device. Maximum-speed values and generic USB_PD labels do not prove a data link or PD contract. Android config enables NCM/FunctionFS but not ACM. The separately compiled bridge enables ACM; a new default-HOLD ramdisk selects only the observed a600000 target and holds when missing/invalid. Ten mocked predicate cases, reference-kernel PID1 and private-v2 format checks passed, but no physical UDC binding, host enumeration or usable rescue console has been proved. The fresh paired follow-up again records both UDCs not attached and no matching host candidate; no physical connection or entry success is inferred. The later 05:18 UTC paired recheck retains the same bounded no-link observation, without inferring cable presence or another host. The latest retained fixed-helper pair at 09:36:24-25 UTC (17:36 Shanghai) again exits zero with both UDCs not attached/UNKNOWN, unchanged primary/VID/PID and 14 doesvm entries without a matching vendor candidate. No cable fault or other host state is inferred.

Evidence: ANDROID-STOCK, ANDROID-BOOT-CAPABILITIES, POWER-SOURCE, HISTORICAL-MATRIX, ENTRY-RECONSTRUCTION-ARTIFACTS, ANDROID-USB-TRANSPORT, HOST-USB-TRANSPORT, USB-TRANSPORT-REVIEW, ENTRY-OWNER-UDC-ARTIFACTS, ANDROID-USB-FOLLOWUP, HOST-USB-FOLLOWUP, USB-FOLLOWUP-REVIEW, USB-RECHECK-REVIEW, ANDROID-USB-RECHECK, HOST-USB-RECHECK, USB-RECHECK-1736-REVIEW, ANDROID-USB-RECHECK-1736, HOST-USB-RECHECK-1736. Dependencies: SYS-01, PWR-01.

**Before running:** Known data cable and same host port, both plug orientations; distinct charging-only and data-capable accessories.

**Android work still required:** Record actual owner Android device-role functions and negotiated USB speeds, then transfer the same test data.

**Linux procedure:**

1. Enumerate intended Linux USB data functions and negotiated speed; transfer and verify a test file of at least 1 GiB.
2. Repeat 20 attach/detach events and sleep recovery in both orientations while monitoring charging role.
3. Measure protocol-matched throughput; retain USB controller/redriver errors and any renegotiation.

**Required result:**

- `USB-01.C01`: Confirmed device-role data functions and stock-equivalent physical link speed work with correct hashes.
- `USB-01.C02`: No role confusion, reset loop or loss of charging; USB2-only operation cannot satisfy verified Android SuperSpeed capability.

Minimum repetitions: 20. Comparison profiles: paired-throughput.

Command templates: `usb-tree` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### USB-02

**USB host, hub and role switching** — `not_run`.

**Known baseline:** Dual-role support is advertised in owner Android Type-C class; host/dock functionality is not measured in the capture.

Evidence: ANDROID-STOCK, POWER-SOURCE, HISTORICAL-MATRIX. Dependencies: USB-01.

**Before running:** Known hub, keyboard and storage peripheral; both connector orientations; one charger/Type-C policy owner.

**Android work still required:** Verify Android host mode, simultaneous hub devices, external power and supported role changes with the exact accessories.

**Linux procedure:**

1. Attach USB keyboard/storage/hub; perform known-file transfers and input checks.
2. Cycle host/device and powered/unpowered hub states 20 times, verifying VBUS/data roles and orderly detach.
3. Repeat with DP/audio and after suspend, using only supported role interfaces.

**Required result:**

- `USB-02.C01`: All confirmed host functions and peripherals operate with data integrity and correct power/data roles.
- `USB-02.C02`: No conflicting TCPM/legacy charger writers, phantom power source state or permanent rebind requirement.

Minimum repetitions: 20. Comparison profiles: paired-throughput.

Command templates: `usb-tree` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### AUDIO-01

**All internal speakers and amplifier calibration** — `blocked`.

**Known baseline:** Owner Android registers kona-qrd-snd-card and 32 PCM interfaces with tfa98xx drivers actually bound at I2C 0x34..0x37. That binding alone does not identify silicon or acoustic variants. A later bounded shared HQ slot reports tfa98xx_QS.cnt; exact shipping module/Image analysis places this first-registration cache before asynchronous firmware completion. It does not prove four independent selections, DSP/calibration success or four working speakers. The frozen research2/research4 amplifier DT path remains disabled and its generic TFA989X path does not supply TFA9894 container integration. A separate unsigned TFA98xx prototype now compiles against research4 with BTF and 75 matching imported CRCs, but remains uninstalled/unexecuted with 35 warnings and no selected container. Available ADSP/PAS configuration and staged dependencies are not working audio; full machine/DAI/TDM routing, write-protection review and measured physical quality remain open.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX, DISTRO-SOURCE, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT, STOCK-FIRMWARE-STAGING, TFA-CACHED-ANDROID, TFA-CACHED-STATIC, TFA-CACHED-REVIEW, TFA-PROTOTYPE-HOST, TFA-PROTOTYPE-ARTIFACTS, TFA-PROTOTYPE-HISTORY, TFA-PROTOTYPE-LOG. Dependencies: SYS-02.

**Current blocker:** Exact amplifier silicon/acoustic calibration, TDM routing and controlled speaker baseline remain unresolved; the research2 amplifier path is disabled and lacks compatible DSP/driver integration.

**Before running:** Exact board/amp calibration and TDM routing confirmed before playback; same measured reference sound level, not raw mixer percentage.

**Android work still required:** Confirm every physical speaker, channel assignment, normal volume range and reference tone/speech response under Android.

**Linux procedure:**

1. Verify native ALSA/ASoC path, correct calibration choice and all four output channels with attended reference audio.
2. Test stereo balance, volume/mute, 30-minute playback, routing and resume; inspect underruns and amp errors.
3. Compare noise/distortion and level using the same measurement position and normal reference output.

**Required result:**

- `AUDIO-01.C01`: Every fitted internal speaker functions with correct routing and calibration, without distortion, clipping, reset or thermal-protection bypass.
- `AUDIO-01.C02`: USB/BT audio, partial speaker count or an ALSA card list cannot substitute for internal-speaker completion.

Minimum repetitions: 3. Duration: 30 min sustained playback. Comparison profiles: paired-quality, paired-energy.

Command templates: `audio-playback-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### AUDIO-02

**Internal microphones, capture and duplex audio** — `blocked`.

**Known baseline:** Owner ALSA exposes capture-capable PCM names within 32 registered interfaces. The DT declares Bolero/WCD938x and SoundWire candidates, but exact codec revision/binding and physical microphone count, placement, routing and capture quality were not established. No audio stream was opened.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-01.

**Current blocker:** Owner microphone inventory and Linux capture path remain unresolved.

**Before running:** Known nonpersonal speech/tone source, fixed position/level; identify all owner-present microphone channels.

**Android work still required:** Record Android microphone count/routes, noise level, gain, recording modes and duplex/echo behavior.

**Linux procedure:**

1. Capture a fixed test sequence on every fitted input; compare channel orientation, sample timing, clipping and noise.
2. Run simultaneous speaker playback and capture for ten minutes; test mute/privacy controls and resume.
3. Exercise the intended desktop communication/capture application and retain sanitized metrics.

**Required result:**

- `AUDIO-02.C01`: Every confirmed internal microphone is usable with correct timing and routing; no silent channel or persistent feedback.
- `AUDIO-02.C02`: Duplex and applicable echo-control behavior meet the frozen reference; external headset input is not a substitute.

Minimum repetitions: 3. Duration: 10 min duplex. Comparison profiles: paired-quality, paired-latency.

Command templates: `audio-capture-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### AUDIO-03

**USB-C analog/digital and headset route changes** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** Owner 8-0042 fsa4480-i2c is actually bound to fsa4480-driver. ALSA includes USB/hostless route names, but analog/digital accessory routing was not exercised. Bound RTC6226/radio0 has separate FM-01 acceptance; its audio route must coexist with these paths.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: AUDIO-01, AUDIO-02, USB-02, BT-01.

**Before running:** Only owner-confirmed analog/digital adapters and headset controls; exact accessories on both systems.

**Android work still required:** Confirm which USB-C analog/digital routes, headset microphone/buttons and jack/adapter changes Android supports.

**Linux procedure:**

1. Play and capture through each confirmed route; test volume, microphone, headset buttons and automatic return to speakers.
2. Exercise 20 hotplug/routing changes and repeat with charge/dock coexistence. After FM-01 establishes the tuner route, revisit applicable headset/speaker switching and FM coexistence without substituting streaming radio.

**Required result:**

- `AUDIO-03.C01`: Each confirmed route and control works without wrong-channel audio, silent capture or stuck default device.
- `AUDIO-03.C02`: Working one external route does not hide incomplete internal speaker/microphone tests.

Minimum repetitions: 20. Comparison profiles: paired-quality.

### FM-01

**RTC6226 tuning, reception, audio and recovery** — `blocked`.

**Known baseline:** Owner Android I2C client 6-0064 is bound to rtc6226, and radio0 is named rtc6226-fmtuner. This establishes registration/binding, not a received station, actual frequency band, antenna path, stereo/RDS capability, quality, power use or Linux support. No tuner command or audio stream was opened.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-01, PWR-01.

**Current blocker:** Usable owner FM reception, antenna/accessory and audio-route baseline have not been established; native Linux tuning, reception, power and recovery are untested.

**Before running:** Identify the actual receive-only tuner/antenna and audio path from the owner Android baseline before Linux tuning; use the same antenna/headset, position, frequencies, audio level and stable RF conditions. Validate AUDIO-03 routes if an external accessory is required. Record locally supported band/channel spacing and only owner-confirmed features such as seek, stereo or RDS; keep device identity separate from package/app presence.

**Android work still required:** Confirm the owner can receive FM using its fitted tuner and establish the required antenna/accessory and internal/headset audio routes. Record supported band, tuning steps, stable reference stations and any confirmed seek/stereo/RDS behavior. Measure reception stability, channel separation/audio noise, tuning/recovery latency and calibrated energy under matched RF/audio conditions; repeat enough paired intervals to distinguish broadcast variation from a platform regression.

**Linux procedure:**

1. Verify the native Linux driver and bound physical radio device, then use the supported tuner API to tune the same reference frequencies and exercise every confirmed tune/seek/control mode.
2. Receive and route audio for 30 minutes per required route; compare dropouts, mono/stereo behavior, quality and matched energy. Verify RDS or other metadata only where the Android baseline establishes that feature.
3. Repeat 20 open/close, station-change and applicable antenna/headset attach cycles; verify correct speaker/headset routing and that closing the session releases power.
4. After the platform suspend test, verify wake/reopen/reception and route restoration. Exercise applicable simultaneous Wi-Fi, Bluetooth, charging and display workloads and compare reception, audio and energy with the same Android scenario.

**Required result:**

- `FM-01.C01`: The fitted receiver actually receives the required reference signals and exposes all owner-confirmed tuning/control features through the intended application, with correct audio routing.
- `FM-01.C02`: Reception/audio quality, latency and energy meet the frozen matched Android comparison; no persistent dropout, stuck route, tuner reset loop or post-close high-power state.
- `FM-01.C03`: The receiver and selected audio route recover after lifecycle and suspend tests. An online radio stream, external tuner or missing mainline driver cannot satisfy this case or justify marking the fitted receiver absent.

Minimum repetitions: 3. Duration: 30 min per required route; 20 lifecycle cycles. Comparison profiles: paired-quality, paired-latency, paired-energy.

### CAM-01

**Rear camera still/video and application pipeline** — `blocked`.

**Known baseline:** Owner CameraService ID 0, BACK, HAL 3.5; pixelArraySize 3264x2448, orientation 90 degrees; raw activeArraySize [0,0,3264,2448]; advertised AE FPS pairs [15,15], [12,30], [30,30]. These static tags are not a complete output-stream matrix or measured frame rate. No frames were captured. Generic qcom,cam-sensor/cam-sensor-driver entries do not identify silicon; historical S5K4H7 remains an unconfirmed source lead for this owner.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-02.

**Current blocker:** Owner rear static role/array metadata is available, but silicon identity, full stream matrix, controlled image/video baseline and native Linux capture remain unresolved.

**Before running:** Confirm fitted module and exact power/clock/reset/calibration first; controlled test chart/light, same supported streams and app processing policy.

**Android work still required:** Resolve the owner rear camera silicon/module and full supported output format/resolution/frame-rate matrix, focus behavior if present, and exposure/white-balance ranges. Verify the advertised orientation dynamically; do not turn pixel-array size into an assumed streaming mode. Capture matched test charts and timed video with a known audio marker; freeze the actual stream matrix before Linux trials.

**Linux procedure:**

1. Use native CAMSS/CCI plus the verified sensor/libcamera path to take 30 stills and ten-minute video per required mode.
2. Compare image orientation, geometry, color/exposure, frame count/timestamps, applicable focus and AV synchronization.
3. Repeat open/close, app handoff and post-suspend recovery; inspect CSI/ISP errors and dropped frames.

**Required result:**

- `CAM-01.C01`: The fitted rear camera delivers real frames in every owner-confirmed required stream mode with correct controls.
- `CAM-01.C02`: No black/corrupt frames, persistent CSI errors or unexplained frame loss; a webcam or other camera cannot substitute.

Minimum repetitions: 3. Duration: 30 stills plus 10 min per required stream. Comparison profiles: paired-quality, paired-latency.

Command templates: `camera-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### CAM-02

**Front camera still/video and application pipeline** — `blocked`.

**Known baseline:** Owner CameraService ID 1, FRONT, HAL 3.5; pixelArraySize 4240x3152, orientation 270 degrees; raw activeArraySize [16,16,4208,3120]; advertised AE FPS pairs [15,15], [10,30], [30,30]. These static tags are not a complete output-stream matrix or measured frame rate. No frames were captured. Generic qcom,cam-sensor/cam-sensor-driver entries do not identify silicon; historical HI1339 remains an unconfirmed source lead for this owner.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, AUDIO-02.

**Current blocker:** Owner front static role/array metadata is available, but silicon identity, full stream matrix, controlled image/video baseline and native Linux capture remain unresolved.

**Before running:** Confirm fitted module and exact power/clock/reset/calibration first; controlled test chart/light, same supported streams and app processing policy.

**Android work still required:** Resolve the owner front camera silicon/module and full supported output format/resolution/frame-rate matrix, focus behavior if present, and exposure/white-balance ranges. Verify the advertised orientation dynamically; do not turn pixel-array size into an assumed streaming mode. Capture matched test charts and timed video with a known audio marker; freeze the actual stream matrix before Linux trials.

**Linux procedure:**

1. Use native CAMSS/CCI plus the verified sensor/libcamera path to take 30 stills and ten-minute video per required mode.
2. Compare image orientation, geometry, color/exposure, frame count/timestamps, applicable focus and AV synchronization.
3. Repeat open/close, app handoff and post-suspend recovery; inspect CSI/ISP errors and dropped frames.

**Required result:**

- `CAM-02.C01`: The fitted front camera delivers real frames in every owner-confirmed required stream mode with correct controls.
- `CAM-02.C02`: No black/corrupt frames, persistent CSI errors or unexplained frame loss; a webcam or other camera cannot substitute.

Minimum repetitions: 3. Duration: 30 stills plus 10 min per required stream. Comparison profiles: paired-quality, paired-latency.

Command templates: `camera-list` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### SENS-01

**Accelerometer, gyroscope, magnetometer and orientation** — `blocked`.

**Known baseline:** Owner SensorService advertises TDK-Invensense icm4x6xx accelerometer/gyroscope at 1..400 Hz and QST qmc630x magnetometer at 1..100 Hz, with wakeup/non-wakeup and calibrated/uncalibrated variants. These are HAL family/rate declarations, not measured samples or exact chip IDs. No BMI3x0 descriptor is present. The three captured IIO devices are PMIC ADCs. Research2 DSP OF availability/PAS firmware paths do not establish sensor transport, authentication or delivered data. Staged SLPI/CDSP/ADSP indexed file sets close the packaging dependencies only.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX, FIRMWARE-CONTRACT, STOCK-FIRMWARE-RECEIPT, STOCK-FIRMWARE-STAGING. Dependencies: SYS-02.

**Current blocker:** Owner service-level families are recorded; exact transport/axes, measured sample-rate/quality baseline, DSP services and the native Linux sensor path remain unresolved.

**Before running:** Confirm fitted parts/firmware and orientation matrices; fixed physical orientation/motion test, recorded sample rates.

**Android work still required:** Resolve exact parts/transports and axes using the current icm4x6xx/qmc630x leads; do not import historical BMI3x0 orientation or firmware assumptions. Measure actual units, timestamps, rates/loss, six-face gravity response, gyro zero/rate response, heading and confirmed fusion/gesture behavior.

**Linux procedure:**

1. Verify native sensor/remoteproc/IIO paths and timestamped data; repeat six faces, calibrated rotations and stationary intervals.
2. Test desktop orientation changes and lock, then sensor recovery/power-down after inactivity and suspend.
3. Compare units, bias/noise, timing, axes and orientation latency with the matched Android baseline.

**Required result:**

- `SENS-01.C01`: Every fitted motion/magnetic sensor supplies correctly scaled, oriented and timestamped data without missing samples at required rates.
- `SENS-01.C02`: Auto-rotation/fusion is usable; software fixed rotation or a powered-off sensor cannot count as completion.

Minimum repetitions: 3. Comparison profiles: paired-quality, paired-latency.

### SENS-02

**Ambient/RGB sensing and automatic brightness** — `not_run`.

**Known baseline:** Owner SensorService advertises ams AG tcs3408 ambient-light and RGB wakeup/non-wakeup descriptors. Their retained delay fields are zero; no periodic rate is established. Illumination/color response, calibration and automatic-brightness behavior were not measured.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, HISTORICAL-MATRIX. Dependencies: SYS-02, DISP-03.

**Before running:** Fixed low/mid/high illumination and color reference; distinguish actual sensor data from desktop policy.

**Android work still required:** Confirm owner ALS/RGB capabilities, dynamic response, calibration and automatic-brightness behavior.

**Linux procedure:**

1. Measure monotonic response and timestamps under each reference light; cover/uncover and change light repeatedly.
2. Verify native sensor data feeds usable automatic brightness, with sensible transitions and suspend recovery.

**Required result:**

- `SENS-02.C01`: Every owner-present ALS/RGB channel works and automatic brightness responds without oscillation or a stuck level.
- `SENS-02.C02`: Manual fixed brightness is a useful diagnostic but does not satisfy the confirmed automatic feature.

Minimum repetitions: 20. Comparison profiles: paired-quality, paired-latency.

### STOR-01

**UFS filesystem integrity, throughput and recovery** — `not_run`.

**Known baseline:** UFS is present in the historical board inventory; this collection did not measure owner storage throughput or filesystem behavior.

Evidence: HISTORICAL-MATRIX, DISTRO-SOURCE. Dependencies: SYS-01, SYS-02.

**Before running:** Only an allocated test file under an explicitly selected Linux data filesystem; never raw block-device or Android-partition writes. Record encryption/filesystem/free space/cache policy.

**Android work still required:** Measure the same file workload on an owner-authorized Android test directory with comparable cache/crypto conditions.

**Linux procedure:**

1. Copy, fsync and read/verify at least a 512 MiB generated fixture for three trials; retain file hashes and timings.
2. Check the fixture after controlled reboot and suspend, and exercise concurrent app/storage traffic.
3. Inspect UFS error/correctness counters and performance under the same validated power policy.

**Required result:**

- `STOR-01.C01`: Every verified file remains intact across controlled reboot/suspend and no UFS recovery/error loop occurs.
- `STOR-01.C02`: The intended storage path and filesystem remain usable; redirecting data to another device cannot hide a UFS gap.

Minimum repetitions: 3. Comparison profiles: paired-throughput, paired-energy.

### STOR-02

**microSD compatibility, integrity and safe reinsert** — `not_run`.

**Known baseline:** Owner Android exposes mmcblk0 with three partitions. No card identity, filesystem, negotiated speed or integrity trial was captured. Historical R226 card guards and SD150 experiments do not establish this card or universal high-speed support.

Evidence: ANDROID-BOOT-CAPABILITIES, HISTORICAL-MATRIX, DISTRO-SOURCE. Dependencies: STOR-01, SYS-02.

**Before running:** Owner-confirmed card and supported bus modes; use a removable test card that is not the active root filesystem for insertion tests. Preserve the actual three-partition layout and select an ordinary test file; do not assume the historical two-partition installation layout or remove card-specific guards to claim support.

**Android work still required:** Record owner card capacity, negotiated standard mode and same-file Android integrity/throughput; keep CID/serial private.

**Linux procedure:**

1. Run three filesystem file/verify trials and post-reboot checks on the selected card.
2. Perform 20 orderly unmount/reinsert events for a non-root test card, or document reboot-only testing when it is the root medium.
3. Verify recovery after suspend and concurrent Wi-Fi/USB use without command/CRC errors.

**Required result:**

- `STOR-02.C01`: The tested card works at its confirmed supported mode with zero data corruption and reliable detection.
- `STOR-02.C02`: A single guarded card result is not generalized to all cards; untested card/mode combinations remain explicit.

Minimum repetitions: 3. Comparison profiles: paired-throughput.

### PWR-01

**Fuel-gauge units, sign, trends and desktop reporting** — `not_run`.

**Known baseline:** MM8013C06 at I2C0x55 is confirmed. Android shows 28%, 34.1 C, 3.789 V, +426000 uA while Charging; charge_counter=90 is not calibrated.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: SYS-01.

**Before running:** Same battery; unplugged and charging samples over time; distinguish net battery current from USB input current.

**Android work still required:** Validate sign/units and stored-charge trends under discharge/charge; compare with an appropriate independent reference and determine which counters are trustworthy.

**Linux procedure:**

1. Identify the actual Linux gauge supply and supported attributes; compare voltage/temp/SOC and sign with charge/discharge trends.
2. Verify desktop reporting and low-battery behavior using normal operating ranges, including rest/reboot/resume.
3. Record unavailable/invalid counters as unknown; establish measurement uncertainty before any energy claim.

**Required result:**

- `PWR-01.C01`: Telemetry is coherent in units/sign/trends and reports missing data correctly instead of zero.
- `PWR-01.C02`: A battery icon, equal design/full capacity or a single reading is not accepted as health, efficiency or charge-policy proof.

Minimum repetitions: 3. Comparison profiles: paired-quality.

### PWR-02

**Sustained charging and actual negotiated protocols** — `blocked`.

**Known baseline:** Owner sample has real_type USB_HVDCP_3, pd_active=0 and input-voltage reading about7.137 V despite generic PD labels. Sustained rates and PD capability remain unmeasured.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: PWR-01, USB-01.

**Current blocker:** Complete single-owner charger/protocol implementation and controlled owner rate baseline remain open.

**Before running:** One Type-C/charger policy owner; same known charger/cable, starting SOC window and temperature; independent input/protocol evidence where available.

**Android work still required:** Measure owner stock-charger HVDCP behavior, sustained net charge trend and rate; separately test an appropriate PD source to establish actual PD capability.

**Linux procedure:**

1. Measure at least 45 minutes of steady charging, tracking actual protocol/contract, input voltage/current, net battery trend and temperature.
2. Perform 20 replug cycles in both orientations, changing between confirmed chargers and repeating screen-off and sleep conditions.
3. Verify policy ownership and watchdog continuity, including after driver/application recovery; record protocol downgrades.

**Required result:**

- `PWR-02.C01`: All confirmed owner charging modes negotiate and sustain charging with no resets, repeated manual recovery or unexplained stop.
- `PWR-02.C02`: Generic PD class labels, online=1, a slow fixed5V fallback or inherited charging alone cannot satisfy confirmed fast-charge capability.
- `PWR-02.C03`: Net stored charge rises consistently and rate/temperature meet the matched baseline without bypassing policy limits.

Minimum repetitions: 3. Duration: 45 min steady trial;20 replug cycles. Comparison profiles: paired-throughput, paired-quality.

### PWR-03

**Charge limits, thermal controls and watchdog ownership** — `blocked`.

**Known baseline:** Android SMB5 DT has JEITA enabled,16 thermal entries and16-second watchdog bark. Historical R189/R231/R235/TCPM helpers have mutually constrained ownership.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: PWR-02.

**Current blocker:** Reviewed complete policy/ownership and protection-test evidence are not available.

**Before running:** Reviewed driver policy and normal operating thermal conditions; no competing raw-register helper and TCPM owner.

**Android work still required:** Record owner charge-hold/hysteresis features and normal temperature/current-limit behavior; preserve original policy limits.

**Linux procedure:**

1. Verify the selected Linux driver owns Type-C/charging and supported charge-limit requests; exercise normal limit/hysteresis transitions.
2. Validate boundary/invalid-input handling in a driver-level controlled test and confirm normal runtime telemetry/protection behavior.
3. Check watchdog servicing and shutdown/unplug behavior; do not deliberately overheat/overcharge hardware or suppress protection to complete a test.

**Required result:**

- `PWR-03.C01`: Charge-limit, JEITA/thermal and watchdog policy retain correct ownership and fail safely on invalid/missing data.
- `PWR-03.C02`: No blanket protection disable, forced high current, fake battery bypass or simultaneous legacy/TCPM writes.
- `PWR-03.C03`: Any untested protection path is documented and blocks a blanket best-state claim.

Minimum repetitions: 3. Comparison profiles: fixed functional criteria only.

### PM-01

**Screen-on/off idle and runtime power management** — `not_run`.

**Known baseline:** Android exposes WFI/rail-pc;8-second trace shows dynamic CPU/GPU states but no residency or energy result. Several runtime-PM getters report unsupported.

Evidence: ANDROID-STOCK, ANDROID-TRACE, POWER-SOURCE. Dependencies: PWR-01, DISP-03, WIFI-01, BT-01, KEY-01.

**Before running:** Matched measured luminance/refresh/radio and cover states; same SOC window and ambient; calibrated energy measurement.

**Android work still required:** Collect three30-minute screen-on idle and three30-minute screen-off idle baselines with identical radio/wake policy and before/after counters.

**Linux procedure:**

1. Measure the paired Linux conditions with CPU/GPU/radio/display runtime-state counter deltas and calibrated energy.
2. Verify that idle devices can sleep and still respond to their intended wake source; check interrupt/wakelock activity without collecting app names.
3. Separate normal runtime power management from full-system suspend; document unavailable residency metrics.

**Required result:**

- `PM-01.C01`: Idle energy meets the frozen comparison with all intended features enabled; no forced airplane mode or disabled input used as an equivalent test.
- `PM-01.C02`: State transitions and wake behavior work; unsupported getters or missing trace events are not converted to zero power/residency.

Minimum repetitions: 3. Duration: 30 min per condition. Comparison profiles: paired-energy.

### PM-02

**Real suspend entry, wake and complete device restoration** — `not_run`.

**Known baseline:** Android advertises freeze/mem and selects deep, but cumulative4146 successes/1941 failures are historical counters; no controlled cycle was captured.

Evidence: ANDROID-STOCK, POWER-SOURCE. Dependencies: SYS-01, DISP-01, TOUCH-01, KEY-01, WIFI-01, BT-01, PWR-01.

**Before running:** Verified recovery/wake path, matched radio wake policy; battery/charger and cover-attached/detached matrix; actual suspend-state evidence.

**Android work still required:** Measure20 controlled Android cycles, wake sources and resume timing, plus3 overnight intervals with matched conditions and counter deltas.

**Linux procedure:**

1. Perform20 Linux suspend/resume cycles distributed across battery/charger and keyboard states; verify actual platform entry from counter/trace/residency evidence.
2. After each wake check display, touch, pen, keyboard/pad, radios, audio, storage and gauge; run GPU render/readback again when that gate is ready.
3. Run three8-hour sleep intervals and compare calibrated energy, spurious wakes and recovery.

**Required result:**

- `PM-02.C01`: Every planned cycle resumes to the full usable session with no new failed-suspend counter delta, stuck driver or reset.
- `PM-02.C02`: Panel blanking, an idle userspace process, disabled peripherals or s2idle substituted for confirmed deep-sleep behavior cannot be labeled equivalent.
- `PM-02.C03`: Sleep energy and resume timing meet the frozen owner comparison.

Minimum repetitions: 20. Duration: 20 cycles plus3x8h sleep. Comparison profiles: paired-energy, paired-latency.

Command templates: `sleep-mode`, `suspend-attended` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### THERM-01

**Sustained CPU/GPU performance and thermal regulation** — `not_run`.

**Known baseline:** Android cpufreq policies were constrained during the snapshot and changed later. GPU advertises up to683MHz in this capture; neither field is a universal hardware ceiling.

Evidence: ANDROID-STOCK, ANDROID-GPU, ANDROID-TRACE, POWER-SOURCE. Dependencies: GPU-02, GPU-03, PWR-01, PM-01.

**Before running:** Matched workload/data/build, starting temperature, measured luminance, SOC/charger and ambient; retain normal DVFS/thermal/voltage policy.

**Android work still required:** Measure three20-minute common CPU/GPU workloads on Android, including last10-minute throughput, temperature envelope and idle recovery.

**Linux procedure:**

1. Run the same comparable workloads on Linux and record rolling throughput, tail latency, thermal zones and throttling decisions.
2. Return to idle and confirm frequency/power/temperature recovery; repeat with a normal combined display/network workload.
3. Identify any limitation owner; never infer a new OPP or voltage from a snapshot maximum or another board.

**Required result:**

- `THERM-01.C01`: Sustained rather than burst performance meets the frozen matched comparison, without thermal/voltage protection bypass.
- `THERM-01.C02`: No emergency shutdown, watchdog reset, unbounded temperature rise or persistent post-load high-power state; normal safe throttling is interpreted with Android comparison.

Minimum repetitions: 3. Duration: 20 min sustained plus idle cooldown. Comparison profiles: paired-throughput, paired-latency, paired-energy, paired-quality.

### GPU-01

**Actual native MSM device, firmware and API inventory** — `not_run`.

**Known baseline:** Owner Android exposes KGSL and msm_drm render nodes, which are not proof of mainline Freedreno. Its exact DT chip ID 0x06050002 matches the compiled adreno-650.2 path despite the Adreno650v3 model string. The compiled research1 GPU references the standard Adreno SMMU with dma-coherent. Owner-matched ELF/MDT firmware trees exist and GPU/GMU/ZAP requests are mapped, but physical probe, authentication, initialization and actual rendering remain untested.

Evidence: ANDROID-GPU, GPU-STAGE-ELF, GPU-STAGE-MDT, GPU-SOURCE, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT, ANDROID-GPU-CHIPID, GPU-CHIPID-REVIEW, GPU-DT-CONTRACT, STOCK-FIRMWARE-STAGING. Dependencies: SYS-01.

**Before running:** Actual Linux tablet, coherent distro Mesa/GLVND/GBM/ICD stack, no KGSL launch overrides, no software renderer.

**Android work still required:** Record owner Android actual GL/GLES/Vulkan capabilities and application requirements separately from mode or device-node names.

**Linux procedure:**

1. Collect passive GPU evidence, then fixed EGL/Vulkan/KWin queries on the actual device.
2. Verify driver/physical-device identity, render permissions, loaded firmware/provenance, GMU/SMMU initialization and resolved config.
3. Freeze required API versions/features for the chosen apps using this Mesa driver build; do not copy release-wide version maxima.

**Required result:**

- `GPU-01.C01`: A650/FD650 is genuinely available through native MSM/Freedreno/Turnip with the expected firmware and no initialization faults.
- `GPU-01.C02`: No llvmpipe/lavapipe, old KGSL/msm_drm, forced version strings or TU_DEBUG=noconform is used to satisfy a requirement.
- `GPU-01.C03`: Enumeration alone is reported only as this gate, not as rendering, presentation, isolation or video success.

Minimum repetitions: 1. Comparison profiles: fixed functional criteria only.

Command templates: `gpu-passive`, `gpu-enumeration` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### GPU-02

**OpenGL/GLES hardware draw and readback correctness** — `not_run`.

**Known baseline:** No owner GL/GLES rendering result exists; driver/API enumeration is not a draw test.

Evidence: ANDROID-GPU, GPU-SOURCE. Dependencies: GPU-01.

**Before running:** Pinned GLES/desktop-GL context requirements and a coherent native Mesa driver; deterministic common test scenes and reference images.

**Android work still required:** Run comparable supported GLES scenes and record rendered-reference/feature behavior under Android; desktop-GL-only requirements use an explicit separate reference suite.

**Linux procedure:**

1. Create every required context, draw known color/depth/texture/blend/FBO scenes and compare GPU readbacks with reference tolerances.
2. Repeat with multiple windows/contexts and30-minute rendering, then after compositor restart and suspend.
3. Record actual renderer/context/API version and errors for each run, not only a version query.

**Required result:**

- `GPU-02.C01`: All required GL/GLES feature tests produce correct readbacks on A650 with no graphics corruption or unexplained reset.
- `GPU-02.C02`: Software GL, API-version spoofing or a benchmark showing only frame counters cannot pass.

Minimum repetitions: 3. Duration: 30 min stability. Comparison profiles: paired-throughput, paired-energy.

### GPU-03

**Vulkan submissions, synchronization and readback** — `not_run`.

**Known baseline:** No owner Vulkan submission or correctness result exists; Turnip package/ICD presence is host evidence only.

Evidence: ANDROID-GPU, GPU-SOURCE, NIX-HOST. Dependencies: GPU-01.

**Before running:** Actual Adreno650 Vulkan physical device, fixed API/features, deterministic workload and validated native ICD.

**Android work still required:** Run common supported Vulkan draw/compute/copy/synchronization scenes under Android using the same test revision where possible.

**Linux procedure:**

1. Exercise command submission, images/buffers, barriers/fences, compute if required, and host readback against known references.
2. Repeat multi-context/window presentation and30-minute steady workload, then resume and application restart.
3. Record device-lost events, validation findings, output errors and actual physical-device API/features.

**Required result:**

- `GPU-03.C01`: Required Vulkan workloads submit and complete with correct results on the hardware device.
- `GPU-03.C02`: Lavapipe/software WSI, noconform overrides or an ICD JSON file alone cannot satisfy Vulkan operation.

Minimum repetitions: 3. Duration: 30 min stability. Comparison profiles: paired-throughput, paired-energy.

### GPU-04

**Wayland/KWin hardware composition and native presentation** — `not_run`.

**Known baseline:** Historical launchers infer GPU enablement from paths and may force Zink/private ICD/software WSI. Simpledrm CPU-copy presentation is distinct from native DPU/DSI.

Evidence: GPU-SOURCE, DISPLAY-SOURCE. Dependencies: GPU-02, GPU-03, DISP-01, DISP-02.

**Before running:** Single coherent userspace graphics stack; actual compositor GPU FD/renderer and scanout path observed.

**Android work still required:** Record a matched owner interactive workload: scrolling, window/app transitions and video/pen interaction at selected rates.

**Linux procedure:**

1. Observe KWin renderer and open GPU device, then test GBM/dma-buf import, window movement, scaling and mixed GL/Vulkan apps.
2. Freeze the actually supported dma-buf formats/modifiers and implicit/explicit synchronization combinations for this stack, then exercise each required combination under load and after recovery; do not infer support from package versions.
3. Measure frame pacing and input latency on native DPU output; separately label any inherited-framebuffer copy diagnostic.
4. Run session restart, display transitions and pen interaction with no stale launcher overrides.

**Required result:**

- `GPU-04.C01`: KWin and test applications actually use A650, with correct native full-panel presentation and pacing.
- `GPU-04.C02`: Path existence, software composition or simpledrm copies are not promoted to complete native display/GPU integration.

Minimum repetitions: 3. Comparison profiles: paired-latency, paired-energy.

Command templates: `gpu-enumeration` in the JSON catalog. These are partial observation tools, not the complete acceptance procedure.

### GPU-05

**Per-process GPU address-space isolation and bounded recovery** — `blocked`.

**Known baseline:** Historical R185 experimented with removing qcom,adreno-smmu for a global page table. The actual frozen research1 DT retains that compatible, dma-coherent and correct GPU-to-SMMU reference; the historical removal is not applied. This confirms the intended configuration only. Per-process context switching, fault containment and recovery have not been observed on the owner tablet. Independent research3/research4 checks retain the same correct GPU-to-standard-Adreno-SMMU contract in the joint native display/input DT.

Evidence: GPU-SOURCE, DISTRO-SOURCE, GPU-CHIPID-REVIEW, GPU-DT-CONTRACT, R3-KERNEL-ARTIFACTS, R4-KERNEL-ARTIFACTS. Dependencies: GPU-02, GPU-03.

**Current blocker:** Runtime per-process GPU isolation, bounded fault containment/recovery and the reviewed owner-device test have not been demonstrated; a normal DT or two successful clients cannot supply this evidence.

**Before running:** Current compiled DT retains the intended Adreno SMMU path. Before a fault test, observe separate process address spaces at runtime and use a disposable attended graphics session with a known recovery path and a reviewed bounded self-test.

**Android work still required:** Record Android context/fault behavior where a comparable supported test exists; no private-process memory is used.

**Linux procedure:**

1. Verify compiled DT/kernel and runtime context records show separate process address spaces, not merely two successful apps in one global domain.
2. Use two owned test processes with separate test buffers; run the reviewed isolation case and a bounded context termination/timeout recovery case.
3. Confirm the unaffected process continues correctly, no cross-process data is exposed/corrupted, the device recovers and subsequent GL/Vulkan tests pass.

**Required result:**

- `GPU-05.C01`: Per-process isolation is actually active; using a global address-space diagnostic workaround would remain an explicit unresolved degradation.
- `GPU-05.C02`: The selected fault stays contained, recovery is bounded and usable rendering returns without a tablet reboot or unrelated data damage.
- `GPU-05.C03`: A passing multiclient stress test alone is not evidence of memory isolation.

Minimum repetitions: 3. Comparison profiles: fixed functional criteria only.

### VIDEO-01

**Native hardware decode and application use** — `blocked`.

**Known baseline:** Owner video32/video33 are bound to Android msm_vidc_v4l2, which is not mainline Venus evidence. Research2 enables the required Kconfig parent and Venus module, but its compiled video-codec parent node remains disabled. The exact conditional request is qcom/vpu-1.0/venus.mbn with required indexed siblings. Owner codec/stream matrix, firmware HFI ABI/authentication and hardware decoding remain unverified. The canonical Venus MDT and ten required nonempty indexed payloads were staged and re-parsed under their final names; that does not enable the node or test the HFI/decoder.

Evidence: ANDROID-PERIPHERALS, PERIPHERAL-REVIEW, GPU-SOURCE, DISTRO-SOURCE, KERNEL-HOST, FIRMWARE-CONTRACT, FIRMWARE-CONTRACT-METADATA, STOCK-FIRMWARE-RECEIPT, STOCK-FIRMWARE-STAGING. Dependencies: SYS-02, GPU-04, AUDIO-01.

**Current blocker:** Owner codec matrix and enabled/native Venus hardware result are missing.

**Before running:** Confirmed codec/bit-depth/resolution/frame-rate matrix; known clips with hashes and the same display/audio conditions.

**Android work still required:** Record owner Android hardware decoder identity and supported stream matrix, then play representative H264/HEVC and any other confirmed codec modes.

**Linux procedure:**

1. Enable and verify the actual Venus driver/firmware/queues, then decode representative clips for ten minutes per required mode.
2. Prove the application uses hardware decoding rather than silently falling back, and verify frame correctness, drops and AV synchronization.
3. Repeat seek, pause/resume, app restart and post-suspend playback; compare CPU time/energy with the hardware Android baseline.

**Required result:**

- `VIDEO-01.C01`: Each confirmed required codec/mode uses real hardware decoding with correct frames and synchronized audio.
- `VIDEO-01.C02`: Software decoding, codec-package presence, working OpenGL or a V4L2 node alone cannot count as hardware video support.

Minimum repetitions: 3. Duration: 10 min per required stream. Comparison profiles: paired-quality, paired-energy.

### VIDEO-02

**Hardware encode where stock exposes it** — `not_run`.

Applicability must be confirmed on this owner tablet; only a reviewed proof of physical/stock-feature absence permits exclusion.

**Known baseline:** No owner encode capability or native Linux encoding result was captured. The research2 Venus parent remains disabled; available encoder/decoder child nodes do not make that parent operational.

Evidence: HISTORICAL-MATRIX, GPU-SOURCE, FIRMWARE-CONTRACT. Dependencies: SYS-02, CAM-01, CAM-02.

**Before running:** Only owner-confirmed hardware encode modes; known raw/video source and explicit application encoder selection.

**Android work still required:** Identify Android hardware encoders and required camera/screen recording modes, formats and rates.

**Linux procedure:**

1. Encode a known source through the native hardware path and decode/check the produced bitstream and timestamps.
2. Test ten-minute capture/encode, pause/restart and concurrent audio; record actual encoder driver and application route.

**Required result:**

- `VIDEO-02.C01`: Every confirmed required hardware encoding mode produces correct, playable output at its specified rate.
- `VIDEO-02.C02`: CPU encoding is recorded as a fallback and cannot satisfy a confirmed hardware-encode feature.

Minimum repetitions: 3. Duration: 10 min per mode. Comparison profiles: paired-throughput, paired-quality, paired-energy.

### SYS-03

**Complete daily-use combination and soak** — `not_run`.

**Known baseline:** No owner Linux session has completed any functional gate in this ledger. A separate generic Fedora VM reached systemd with SELinux Enforcing and verified runtime files; it did not use the Lenovo DT or test the whole-tablet combination.

Evidence: ANDROID-STOCK, GPU-SOURCE, POWER-SOURCE, FEDORA-SYSTEM-ARTIFACTS, INPUT-SIGNED-ARTIFACTS. Dependencies: SYS-04, DISP-04, PEN-02, PEN-03, PEN-04, PAD-01, SWITCH-01, WIFI-02, USB-02, AUDIO-03, FM-01, CAM-01, CAM-02, SENS-01, SENS-02, STOR-02, PWR-03, PM-02, THERM-01, GPU-04, GPU-05, VIDEO-01, VIDEO-02.

**Before running:** One immutable final stack and each named usage profile; all applicable features enabled with normal policy.

**Android work still required:** Run a fixed owner Android daily-use script to establish responsiveness, charge/sleep behavior and accessory interactions.

**Linux procedure:**

1. Run a 24-hour mixed-use soak covering pen notes, keyboard/pad, browser/GL/Vulkan, local video, cameras, WiFi/BT, FM reception using its confirmed route, charging and sleep.
2. Exercise the specified dock/cover/pen attach events and resume while preserving the same final configuration.
3. Re-run integrity checks and every critical device smoke after the soak; resolve all regressions before closing the ledger.

**Required result:**

- `SYS-03.C01`: No crash, reset, filesystem corruption, stuck input/radio/audio/camera, persistent high-power state or manual rescue during the planned workload.
- `SYS-03.C02`: Every applicable individual gate remains passed on this same stack; no per-test configuration disables another required feature.
- `SYS-03.C03`: All open functional, isolation, thermal and recovery issues are closed; diagnostic/software fallbacks remain incomplete.

Minimum repetitions: 1. Duration: 24 h mixed-use soak. Comparison profiles: paired-latency, paired-energy.

## Evidence register

| ID | Class | File | Scope and limitations |
| --- | --- | --- | --- |
| `ANDROID-STOCK` | `device_android` | [android-stock.json](evidence/android-stock.json) | Sequential observations; no input motions, charge cycle, controlled suspend, benchmark or Linux test. |
| `ANDROID-GPU` | `device_android` | [android-gpu.json](evidence/android-gpu.json) | No measured GL/Vulkan application, isolation, recovery or mainline rendering. |
| `ANDROID-PERIPHERALS` | `device_android` | [android-peripheral-inventory.json](evidence/android-peripheral-inventory.json) | No frames, audio streams, sensor events, tuner reception or Linux operation. Service names/rate declarations are not chip-ID reads or measured performance. Camera silicon, exact TFA/codec/acoustic variants, physical microphone inventory and full stream matrices remain unresolved; the unbound OCH8801-0 declaration is only a candidate. |
| `PERIPHERAL-REVIEW` | `source_clue` | [android-peripheral-inventory.md](android-peripheral-inventory.md) | A bounded interpretation of passive evidence, not a complete physical inventory, silicon verification, successful functional baseline or Linux hardware test. Interface counts do not equal physical device/channel counts. |
| `ANDROID-TRACE` | `device_android` | [android-trace-summary.json](evidence/android-trace-summary.json) | Uncontrolled workload; no energy/residency/FPS/suspend baseline. |
| `ANDROID-BOOT` | `device_android` | [android-boot-state.json](evidence/android-boot-state.json) | No bootloader entry, unlock, flash, data-clear or physical mainline boot was performed; contradictory fields do not establish a safe deployment method. |
| `ANDROID-BOOT-CAPABILITIES` | `device_android` | [android-boot-capabilities.json](evidence/android-boot-capabilities.json) | Passive configuration/interface evidence only; no module or kexec call, no working rescue transport, no card filesystem assessment and no Linux boot. |
| `ANDROID-BOOT-BACKUP` | `device_android` | [android-boot-backup-local.json](evidence/android-boot-backup-local.json) | Current bytes, not certified factory images; excludes userdata/super/persist, does not prove inactive B boots or any restore. The local copy alone resides on userdata. |
| `BOOT-BACKUP-OFFDEVICE` | `host_build` | [boot-backup-off-device.json](evidence/boot-backup-off-device.json) | A verified off-device backup closes a preparation item, not a working restore, AVB/rollback check or physical Linux boot. Private image bytes are not published. |
| `BOOT-HEADER-HOST` | `host_build` | [boot-header-inspection.json](evidence/boot-header-inspection.json) | Numeric layout and content identity only; no AVB signature, rollback compatibility, new-image bootability or restore has been verified. |
| `BOOT-READINESS` | `source_clue` | [boot-readiness.md](boot-readiness.md) | A reviewed entry/recovery analysis, not demonstrated stock-to-kexec handoff or a Linux hardware result. |
| `ENTRY-SOURCE` | `source_clue` | [entry-source-audit.md](entry-source-audit.md) | That earlier read-only audit did not build or boot a first stage. Missing historical inputs are bounded to the inspected checkout and enumerated refs/path queries; the later public replacement is separate ENTRY-RECONSTRUCTION evidence. |
| `ENTRY-METADATA` | `source_clue` | [entry-source-audit.json](evidence/entry-source-audit.json) | That public candidate is not the unknown V56.6 4.19.157 source/config. No compile, image packaging, module load, kexec, reboot, flash or restore occurred in this audit. |
| `DISPLAY-DECODE` | `source_clue` | [display-summary.json](evidence/display-summary.json) | Derived evidence, not runtime packet capture or native display test. |
| `HID-DECODE` | `source_clue` | [hid-summary.json](evidence/hid-summary.json) | Descriptor support is not successful event delivery or hotplug. |
| `DISPLAY-SOURCE` | `source_clue` | [display.md](display.md) | No owner Linux hardware pass can be inferred from this report. |
| `INPUT-SOURCE` | `source_clue` | [input-and-pen.md](input-and-pen.md) | No owner Linux hardware pass can be inferred from this report. |
| `POWER-SOURCE` | `source_clue` | [power-management.md](power-management.md) | No owner Linux hardware pass can be inferred from this report. |
| `GPU-SOURCE` | `source_clue` | [gpu-acceleration.md](gpu-acceleration.md) | No owner Linux hardware pass can be inferred from this report. |
| `DISTRO-SOURCE` | `source_clue` | [distro-builds.md](distro-builds.md) | Original package totals and incomplete-system statements describe the earlier experiment; they are not the latest follow-up status. No owner Linux hardware pass can be inferred. |
| `STATIC-FIXES` | `source_clue` | [static-driver-fixes.md](static-driver-fixes.md) | No owner Linux hardware pass can be inferred from this report. |
| `FIRMWARE-POLICY` | `source_clue` | [firmware.md](firmware.md) | No owner Linux hardware pass can be inferred from this report. |
| `FIRMWARE-CONTRACT` | `source_clue` | [firmware-kernel-contract.md](firmware-kernel-contract.md) | Static availability/configuration only, not driver probe, blob transfer/content validation, secure authentication, DSP services or hardware operation. TFA989X is not configured and its OF table does not match TFA9894. |
| `FIRMWARE-CONTRACT-METADATA` | `source_clue` | [firmware-kernel-contract.json](evidence/firmware-kernel-contract.json) | No kernel source changes or device actions. Firmware ABI, runtime Bluetooth suffix, WLAN board selection and Novatek panel-ID GPIO value remain untested; canonical request names do not establish valid contents. |
| `STOCK-FIRMWARE-REPORT` | `source_clue` | [stock-firmware-bundle.md](stock-firmware-bundle.md) | Private payloads remain outside the repository. That capture/transfer step did not generate canonical trees; later STOCK-FIRMWARE-STAGING records actual staging separately. Structural completeness and byte provenance do not establish signatures, reserved-memory/ABI fit, services or hardware operation. |
| `STOCK-FIRMWARE-RECEIPT` | `host_build` | [stock-firmware-bundle.json](evidence/stock-firmware-bundle.json) | The JSON also retains the Android source capture/re-read metadata, but this evidence ID covers the off-device verification only. No vendor authentication, load, hardware video or tablet Linux test occurred. WLAN board identity and Bluetooth runtime ROM matching remain false; available file counts do not close those contracts. |
| `HISTORICAL-MATRIX` | `source_clue` | [HARDWARE_MATRIX.md](../../HARDWARE_MATRIX.md) | Historical rows belong to other named author/build observations. Use the separate owner capture for current static identities; no row establishes this owner's Linux hardware operation. |
| `DTB-HOST` | `host_build` | [build-dtb.md](build-dtb.md) | Only base DTB; DSI1 remains disabled; no dtbs_check, variant build, boot or hardware test. |
| `GPU-STAGE-ELF` | `host_build` | [gpu-staging-elf.json](evidence/gpu-staging-elf.json) | Host artifact/provenance check only; no Qualcomm authentication or GPU initialization. |
| `GPU-STAGE-MDT` | `host_build` | [gpu-staging-mdt.json](evidence/gpu-staging-mdt.json) | Host artifact/provenance check only; no Qualcomm authentication or GPU initialization. |
| `NIX-HOST` | `host_build` | [nixos-build.json](evidence/nixos-build.json) | That earlier checkpoint did not assemble a full system or boot the tablet; later NIX-SYSTEM evidence separately records full toplevel realization. Neither checkpoint is physical GPU or owner Linux evidence. |
| `KERNEL-HOST` | `host_build` | [kernel-build.md](kernel-build.md) | Host compilation and generic virt boot only; no owner tablet boot, native display/touch test, complete tablet initramfs or bit-for-bit rebuild claim. |
| `KERNEL-ARTIFACTS` | `host_build` | [kernel-build.json](evidence/kernel-build.json) | Offline artifact inspection; release strings alone do not prove complete ABI compatibility, device loading or physical operation. |
| `QEMU-INITIAL` | `host_build` | [kernel-qemu-initial.json](evidence/kernel-qemu-initial.json) | A failed generic VM test, not evidence that the owner tablet reproduced the historical kexec problem; panic details are in the retained log/report. |
| `QEMU-FIXED` | `host_build` | [kernel-qemu-fixed.json](evidence/kernel-qemu-fixed.json) | Generic virt uses no tablet DT, physical GPU, board firmware or tablet rootfs; no Lenovo allocator-branch or hardware acceptance. |
| `R2-BUILD` | `host_build` | [research2-display-build.md](research2-display-build.md) | Display diagnostic candidate only: SPI14 and touchscreen remain disabled. No owner boot, display, GPU, input or handoff result; no arbitrary ABI or bit-for-bit reproduction claim. |
| `R2-ARTIFACTS` | `host_build` | [research2-display-build.json](evidence/research2-display-build.json) | Device-tree availability and compatible strings are static artifact facts, not bound/operating drivers. The native diagnostic DT was not used in QEMU and touch remains disabled. |
| `R2-QEMU` | `host_build` | [research2-display-qemu.json](evidence/research2-display-qemu.json) | Generic machine DT and probe init only: no physical tablet DT, firmware, network/disk passthrough, native display or board early-allocator/handoff validation. |
| `R2-QEMU-SERIAL` | `host_build` | [research2-display-qemu.log](evidence/research2-display-qemu.log) | A short generic ARM boot log; no physical hardware operation, long-duration stability or recovery result. |
| `R2-MODULES` | `host_build` | [research2-display-modules.SHA256SUMS](evidence/research2-display-modules.SHA256SUMS) | File-byte inventory only; no module load or permission to mix this set with another kernel/rootfs build. |
| `R2-PACKAGES` | `host_build` | [research2-display-builder-packages.tsv](evidence/research2-display-builder-packages.tsv) | Host tool inventory, not an immutable APT snapshot or tablet userspace/hardware result. |
| `FEDORA-HOST` | `host_build` | [fedora-build.md](fedora-build.md) | QEMU userspace software graphics only; Turnip found no physical GPU. No tablet boot, complete tablet initramfs, native DSI, hardware rendering or isolation result. |
| `FEDORA-ARTIFACTS` | `host_build` | [fedora-build.json](evidence/fedora-build.json) | Physical GPU/display/board hardware were not exposed. Turnip-only enumeration exited 1 without a GPU; software results cannot pass any owner hardware case. |
| `NURA-HOST` | `host_build` | [nura-build.md](nura-build.md) | The exported qemu-aarch64 rootfs itself has not booted and is not a TB371FC image. Only 371 of 382 package archives are retained, so the offline cache is incomplete and independent offline/byte-identical reproduction is unproved. No owner Linux hardware result. |
| `NURA-ARTIFACTS` | `host_build` | [nura-build.json](evidence/nura-build.json) | offline_cache_complete, independent_offline_rebuild_tested, target_rootfs_booted and tablet/GPU hardware-test flags remain false. Its generic 7.3.5 target kernel/modules are separate from the Alpine builder kernel and both 6.12 research candidates. |
| `SSD-BUILDER` | `host_build` | [ssd-builder.json](evidence/ssd-builder.json) | Infrastructure preparation only; no kernel was built by this bootstrap. Tool binaries remain on the normal HDD-backed Docker layer, APT is not snapshot-pinned and no speedup or tablet function was measured. |
| `ANDROID-GPU-CHIPID` | `device_android` | [android-gpu-chipid.json](evidence/android-gpu-chipid.json) | A passive identity observation, not a GPU render, register/MMIO test, frequency change or mainline probe. The v3 model suffix is not a numeric DT patch field. |
| `GPU-CHIPID-REVIEW` | `source_clue` | [gpu-chipid.md](gpu-chipid.md) | Source/configuration comparison only. GMU/ZAP authentication, runtime per-process page-table switching, bounded recovery, rendering and native display remain untested. |
| `GPU-DT-CONTRACT` | `host_build` | [gpu-dt-contract.json](evidence/gpu-dt-contract.json) | An offline compiled-DT examination. Compatible strings and correct phandle linkage do not establish actual driver binding or process isolation. |
| `INPUT-BUILD` | `host_build` | [input-integration.md](input-integration.md) | The module in this build step is unsigned and was not loaded. The tests exercise selected source/error paths, not device timing, physical input, concurrent workqueue stress, the inherited firmware parser or complete WDT/ESD recovery. |
| `INPUT-ARTIFACTS` | `host_build` | [input-integration.json](evidence/input-integration.json) | Available DT nodes are not bound hardware. No GPIO level, physical dimensions, controller firmware selection, panel-follower coordination, CTN730 charging or owner Linux operation was verified. |
| `INPUT-SIGNED` | `host_build` | [input-signed-integration.md](input-signed-integration.md) | Offline signature, ABI and composition checks do not prove runtime kernel signature acceptance, module insertion, device binding or owner input behavior. No private key was published. |
| `INPUT-SIGNED-ARTIFACTS` | `host_build` | [input-signed-integration.json](evidence/input-signed-integration.json) | This bundle includes no rootfs, firmware, initramfs or Android boot image. It does not modify the frozen original candidate or establish an owner Linux stack/run. |
| `STOCK-FIRMWARE-STAGING` | `host_build` | [stock-firmware-staging.json](evidence/stock-firmware-staging.json) | This ID covers host staging only; the same JSON separately contains bounded Android radio metadata. No vendor authentication or device load occurred. WLAN board data and TFA containers remain excluded, Bluetooth ROM choice is unresolved, and all_hardware_firmware_contracts_satisfied remains false. |
| `ANDROID-RADIO-METADATA` | `device_android` | [stock-firmware-staging.json](evidence/stock-firmware-staging.json) | This ID does not turn the JSON host staging into Android device execution. Absence is bounded to the inspected sources; PCI subsystem identity is not a QMI board ID, and no radio restart, firmware download or functional trial occurred. |
| `ANDROID-RADIO-SELECTION` | `device_android` | [android-radio-boot-selection.json](evidence/android-radio-boot-selection.json) | The retained buffer is not a full boot trace. No selected WLAN BDF, Bluetooth ROM suffix, authentication or Linux radio operation was established. Empty token sets do not prove missing hardware or firmware. |
| `SELINUX-HOST` | `host_build` | [selinux-compatibility.json](evidence/selinux-compatibility.json) | This isolated conversion did not load policy, label files or boot a kernel. Actual Enforcing proof belongs to the separately registered Fedora full-system VM, and the result does not generalize to later policies. |
| `FEDORA-SYSTEM-HOST` | `host_build` | [fedora-system-integration.md](fedora-system-integration.md) | Generic virt with no board DT or physical passthrough. All owner hardware remains untested; the original research1 DT still disables native display/touch. The recorded autofs, pids, BPF-LSM and virtual GPIO warnings remain part of this frozen baseline. |
| `FEDORA-SYSTEM-ARTIFACTS` | `host_build` | [fedora-system-integration.json](evidence/fedora-system-integration.json) | No owner tablet boot, A650 rendering, firmware authentication or peripheral operation. Kernel configuration follow-up warnings remain explicit. Independent offline, bit-identical reconstruction has not been proved. |
| `FEDORA-SYSTEM-PACKAGES` | `host_build` | [fedora-system-packages.tsv](evidence/fedora-system-packages.tsv) | An installed package inventory does not retain every transitive package input or establish hardware functionality or independent bit-identical reconstruction. |
| `INITRAMFS-VALIDATION` | `host_build` | [initramfs-validation.json](evidence/initramfs-validation.json) | Validation parses the compressed bytes without extracting or executing them. Firmware presence and ELF format do not establish device loading; actual generic-system boot is separate evidence. |
| `ENTRY-RECONSTRUCTION` | `host_build` | [first-stage-reconstruction.md](first-stage-reconstruction.md) | This is a new replacement, not recovered V56.6/R201/R55. The downstream generic VM failed before PID1 at Qualcomm SCM; the same rescue initramfs passed only under the separately frozen research2 reference Image. No physical boot, kexec load/execute, rescue transport, AVB trust, runtime-address validity or complete board-driver equivalence is proved. |
| `ENTRY-RECONSTRUCTION-ARTIFACTS` | `host_build` | [first-stage-reconstruction.json](evidence/first-stage-reconstruction.json) | The replacement is 4.19.325-cip134-st18-tb371fc-entry-r1, distinct from owner 4.19.157 and the unresolved historical build. Generic-VM failures and userspace-only reference success are not interchangeable. Private partition/firmware bytes and signing credentials are not published. All owner execution/deployment gates remain untested. |
| `ANDROID-RADIO-VERSION` | `device_android` | [android-radio-version.json](evidence/android-radio-version.json) | Cached descriptor fields are not QMI board_id, a selected BDF filename or a Bluetooth ROM suffix. No radio restart, explicit QMI request, MMIO or driver rebinding was performed. Shipping-binary equivalence to the reviewed public getter is not established. |
| `RADIO-SELECTION-REVIEW` | `source_clue` | [radio-board-selection.md](radio-board-selection.md) | Public 4.19.325 code is not proven identical to the owner 4.19.157 driver. No unique bdwlan candidate, board-2.bin or BT ROM was established; unrelated IPC rings and registers were not read. |
| `ANDROID-USB-TRANSPORT` | `device_android` | [android-usb-transport.json](evidence/android-usb-transport.json) | Configured gadget identity and advertised maximum speed do not prove cable speed, host enumeration, two physical ports, rescue transport or behavior of another kernel. No role change or gadget operation was executed. |
| `HOST-USB-TRANSPORT` | `host_build` | [doesvm-usb-transport.json](evidence/doesvm-usb-transport.json) | Only a bounded snapshot of doesvm, not another host or boot mode. VID matching alone would not identify a tablet or qualify a recovery protocol. |
| `USB-TRANSPORT-REVIEW` | `source_clue` | [usb-transport-readiness.md](usb-transport-readiness.md) | The mismatch is a code/observed-topology finding, not a failed owner boot. USB capture does not resolve actual bootloader acceptance, lock-state disagreement or recovery return. |
| `ENTRY-OWNER-UDC` | `host_build` | [first-stage-owner-udc.md](first-stage-owner-udc.md) | No physical UDC binding, host enumeration, owner boot, 4.19 runtime success, AVB trust, kexec or recovery-return result. The reference VM deliberately skips gadget setup. Old entry artifacts and SCM failure remain unchanged. |
| `ENTRY-OWNER-UDC-ARTIFACTS` | `host_build` | [first-stage-owner-udc.json](evidence/first-stage-owner-udc.json) | Only shell file predicates were mocked; production fixed /sys paths remain unchanged. Private image bytes are not published. All physical entry/USB/AVB/kexec/recovery flags remain false. |
| `NIX-SYSTEM-HOST` | `host_build` | [nixos-system-build.md](nixos-system-build.md) | No rootfs image, activation, bootloader integration, research kernel/module/firmware integration or PID1 boot. PRoot is not a security sandbox; explicit QEMU remains emulation even when an automatic-wrapper field says false. |
| `NIX-SYSTEM-ARTIFACTS` | `host_build` | [nixos-system-build.json](evidence/nixos-system-build.json) | The init/activate scripts were syntax-checked, not activated. Store realization and version execution are not system boot, policy enforcement or owner hardware results; not every closure path has an independent cache signature. |
| `NIX-SYSTEM-PATHS` | `host_build` | [nixos-system-store-paths.tsv](evidence/nixos-system-store-paths.tsv) | A store inventory is not a bootable disk image, independently offline-reproduced system or complete eight-component owner stack. |
| `R3-KERNEL` | `host_build` | [research3-system-kernel.md](research3-system-kernel.md) | Offline build qualification; no owner boot, physical driver operation or BPF behavior is established. |
| `R3-KERNEL-ARTIFACTS` | `host_build` | [research3-system-build.json](evidence/research3-system-build.json) | A matched build and certificate do not by themselves prove runtime acceptance; the separate Fedora R3 run failed before resource probes. |
| `R4-KERNEL` | `host_build` | [research4-system-kernel.md](research4-system-kernel.md) | No physical tablet or runtime BPF/pids success follows from the configuration or compilation. |
| `R4-KERNEL-ARTIFACTS` | `host_build` | [research4-system-build.json](evidence/research4-system-build.json) | Native DT availability and standard GPU SMMU references are configuration evidence, not probe, scanout or isolation behavior. |
| `R4-KERNEL-VERIFICATION` | `host_build` | [research4-system-build-verification.json](evidence/research4-system-build-verification.json) | Instrumentation is not a successful BPF attachment or a restrictive filesystem action. |
| `ARM64-BPF-REVIEW` | `source_clue` | [arm64-bpf-trampoline.md](arm64-bpf-trampoline.md) | A source-level missing contract is distinct from the earlier system-bus failure and is not a measured owner failure. |
| `ARM64-BPF-METADATA` | `source_clue` | [arm64-bpf-trampoline.json](evidence/arm64-bpf-trampoline.json) | Neither BPF_LSM=y nor an LSM name alone proves an effective enforcement hook. |
| `FEDORA-R3-HOST` | `host_build` | [fedora-research3-system.md](fedora-research3-system.md) | The failure is not a passed system test or the expected result of a BPF denial test; physical hardware was not used. |
| `FEDORA-R3-ARTIFACTS` | `host_build` | [fedora-research3-system.json](evidence/fedora-research3-system.json) | The final reset window was not present in the earlier persisted journal; absence of an entry is not proof of an absent broker or security error. |
| `RADIO-IPC-REVIEW` | `source_clue` | [radio-ipc-readiness.md](radio-ipc-readiness.md) | No IPC bytes were read or cursor advanced. Mounting debugfs cannot supply a feature omitted from the running kernel. |
| `ANDROID-RADIO-IPC` | `device_android` | [android-radio-ipc-readiness.json](evidence/android-radio-ipc-readiness.json) | Negative interface/config evidence only; it does not imply no historical radio messages or no firmware load. |
| `RADIO-PROBE-REVIEW` | `source_clue` | [radio-probe-capabilities.md](radio-probe-capabilities.md) | This does not exclude ordinary tracepoint BPF; no probe was loaded or attached. |
| `ANDROID-RADIO-PROBE` | `device_android` | [android-trace-probe-capabilities.json](evidence/android-trace-probe-capabilities.json) | Capability inspection only, without program load, attachment or kernel-memory reading. |
| `ANDROID-TRACEPOINT-CAPABILITY` | `device_android` | [android-tracepoint-capabilities.json](evidence/android-tracepoint-capabilities.json) | The ID was not read or enabled; existence does not establish a valid, safe cache snapshot. |
| `CNSS-SHIPPING-REVIEW` | `source_clue` | [cnss-shipping-static.md](cnss-shipping-static.md) | QMI response-valid bits are not retained with these cache fields, their lifetime was not pinned, and the historical requested BDF filename is not cached. No dynamic probe was implemented. |
| `CNSS-SHIPPING-STATIC` | `host_build` | [cnss-shipping-static.json](evidence/cnss-shipping-static.json) | Static link offsets are not live addresses. Cached/default board_id 0xff cannot alone distinguish validity or establish a historical filename. No live memory was read. |
| `TFA-CACHED-REVIEW` | `source_clue` | [tfa9894-cached-metadata.md](tfa9894-cached-metadata.md) | The registration precedes firmware-load completion and is not four independent amplifier selections, DSP/calibration success or speaker silicon proof. |
| `TFA-CACHED-ANDROID` | `device_android` | [tfa9894-cached-metadata.json](evidence/tfa9894-cached-metadata.json) | No I2C/register operation, calibration, playback, independent four-device load status or exact acoustic identity was measured. |
| `TFA-CACHED-STATIC` | `host_build` | [tfa9894-cached-metadata.json](evidence/tfa9894-cached-metadata.json) | This offline binary interpretation does not establish firmware execution, all-amplifier selection or physical output. |
| `TFA-PROTOTYPE-HOST` | `host_build` | [tfa-module-prototype.md](tfa-module-prototype.md) | Unsigned, uninstalled and unexecuted, with 35 compiler warnings and no chosen QS/YC container. Complete persistent-write protection and machine/TDM routing remain unproved. |
| `TFA-PROTOTYPE-ARTIFACTS` | `host_build` | [tfa-module-prototype.json](evidence/tfa-module-prototype.json) | The frozen 84-module runtime and its DT were unchanged. An alias and a linked module do not prove a loaded amplifier or sound. |
| `TFA-PROTOTYPE-HISTORY` | `host_build` | [tfa-module-prototype-history.json](evidence/tfa-module-prototype-history.json) | The correction is a build-environment fix, not proof of a resolved hardware issue or a warning-free driver. |
| `TFA-PROTOTYPE-LOG` | `host_build` | [tfa-module-prototype-build.log](evidence/tfa-module-prototype-build.log) | Warnings were not suppressed or converted into a deployment-readiness claim. |
| `USB-FOLLOWUP-REVIEW` | `source_clue` | [usb-transport-followup.md](usb-transport-followup.md) | A static configuration is not a demonstrated cable/data/recovery link. No USB role or boot state changed. |
| `ANDROID-USB-FOLLOWUP` | `device_android` | [usb-transport-followup.json](evidence/usb-transport-followup.json) | No bind/unbind, role change, enumeration trial, reboot or recovery command was performed. |
| `HOST-USB-FOLLOWUP` | `host_build` | [usb-transport-followup.json](evidence/usb-transport-followup.json) | This time-specific host inventory does not prove that every possible cable/host arrangement is unavailable. |
| `SELINUX-AV-REVIEW` | `source_clue` | [selinux-access-query.md](selinux-access-query.md) | The converted userspace policy is not asserted identical to the exported VM policy; actual broker domain and runtime route still need direct checks. |
| `SELINUX-AV-ARTIFACTS` | `host_build` | [selinux-access-query.json](evidence/selinux-access-query.json) | No live policy, boolean or enforcement setting changed. Read-only query intent does not prove that surrounding PRoot bind placeholder metadata was unchanged; see the separate follow-up. |
| `SELINUX-COPY-REVIEW` | `source_clue` | [selinux-query-copy-followup.md](selinux-query-copy-followup.md) | It preserves the failed earlier copy and does not redefine its warning as success or claim all PRoot queries leave a whole rootfs unchanged. |
| `SELINUX-COPY-ARTIFACTS` | `host_build` | [selinux-query-copy-followup.json](evidence/selinux-query-copy-followup.json) | The copy qualification is separate from policy access and boot behavior; no hardware pass follows. |
| `EARLY-SELINUX-REVIEW` | `source_clue` | [early-initramfs-selinux.md](early-initramfs-selinux.md) | This source and helper-build report deliberately excludes a production PID1 or full-system success. The separate VM must verify actual process domains and event handoff under Enforcing. |
| `EARLY-SELINUX-ARTIFACTS` | `host_build` | [early-initramfs-selinux.json](evidence/early-initramfs-selinux.json) | Byte-identical scope is this helper/compiler/container only. No production policy load, initramfs PID1 execution or owner hardware test is claimed here. |
| `FEDORA-R4-FIRST` | `host_build` | [fedora-research4-bus-failed.md](fedora-research4-bus-failed.md) | The early queued-udev-FD loss is a separate actual denial. Neither source/policy explanation is presented as a captured broker recvmsg trace or a complete system pass. |
| `FEDORA-R4-FIRST-ARTIFACTS` | `host_build` | [fedora-research4-bus-failed.json](evidence/fedora-research4-bus-failed.json) | The owned QEMU was terminated after the failure marker; this was not a clean system poweroff, filesystem qualification or owner hardware test. |
| `FEDORA-R4-FIRST-VERIFY` | `host_build` | [fedora-research4-bus-failed-verify.json](evidence/fedora-research4-bus-failed-verify.json) | Two textual AVC occurrences represent one deduplicated early event; the unchanged raw controller count is not two distinct denials. |
| `FEDORA-R4-FIRST-SERIAL` | `host_build` | [fedora-research4-bus-failed-verify.log](evidence/fedora-research4-bus-failed-verify.log) | Raw log text is VM evidence only; it does not demonstrate peripheral activity or a passed full-system attempt. |
| `FEDORA-R4-FIRST-LABEL` | `host_build` | [fedora-research4-bus-failed-label.log](evidence/fedora-research4-bus-failed-label.log) | Maintenance labeling is separate from its subsequent failed Enforcing verification and cannot substitute for that gate. |
| `FEDORA-R4B-EARLY` | `host_build` | [fedora-r4b-early-failed.md](fedora-r4b-early-failed.md) | A passed archive and first policy load did not produce a successful initrd or full-system boot; no broker, pids or BPF behavioral worker ran. |
| `FEDORA-R4B-EARLY-ARTIFACTS` | `host_build` | [fedora-r4b-early-failed.json](evidence/fedora-r4b-early-failed.json) | Original e53 helper, policy, raw logs and failed image remain intact; this is a failed host attempt, not an owner Linux run. |
| `FEDORA-R4B-EARLY-VERIFY` | `host_build` | [fedora-r4b-early-failed-verify.json](evidence/fedora-r4b-early-failed-verify.json) | No postexec initrd domain, queued-event handoff, system-bus or resource-enforcement success was reached. |
| `FEDORA-R4B-EARLY-SERIAL` | `host_build` | [fedora-r4b-early-failed-verify.log](evidence/fedora-r4b-early-failed-verify.log) | This is generic QEMU with no tablet devices; a failure is not silently reclassified as expected success. |
| `FEDORA-R4B-EARLY-LABEL` | `host_build` | [fedora-r4b-early-failed-label.log](evidence/fedora-r4b-early-failed-label.log) | Explicit maintenance labeling does not substitute for the later failed Enforcing production gate. |
| `FEDORA-R4B-EARLY-ARCHIVE` | `host_build` | [fedora-r4b-early-initramfs-validation.json](evidence/fedora-r4b-early-initramfs-validation.json) | This byte/layout/closure check did not test the rootfs superblock association permission or prove runtime bootability. |
| `SELINUX-ROOTFS-REVIEW` | `source_clue` | [selinux-rootfs-association.md](selinux-rootfs-association.md) | No speculative remount or relocation was executed. Ordinary tmpfs source support and cleanup semantics still require independent runtime qualification. |
| `SELINUX-ROOTFS-ARTIFACTS` | `host_build` | [selinux-rootfs-association.json](evidence/selinux-rootfs-association.json) | In-memory converted policy is not claimed identical to exported live policy; source support is not a passed root switch, policy load or physical boot. |
| `TMPFS-BOOTSTRAP-REVIEW` | `source_clue` | [tmpfs-initramfs-bootstrap.md](tmpfs-initramfs-bootstrap.md) | An empty old directory and closed saved FD do not measure freed physical pages. Production copy/mount/wait/PID1/full-system checks remain separate. |
| `TMPFS-BOOTSTRAP-ARTIFACTS` | `host_build` | [tmpfs-initramfs-bootstrap.json](evidence/tmpfs-initramfs-bootstrap.json) | One stage1 build only, with verified copies. No mount, switch_root, new PID1, policy load, system VM or physical tablet action was performed by this checkpoint. |
| `USB-RECHECK-REVIEW` | `source_clue` | [usb-transport-recheck.md](usb-transport-recheck.md) | The bounded result does not establish whether a physical cable exists or what another host or boot mode would enumerate. |
| `ANDROID-USB-RECHECK` | `device_android` | [usb-transport-recheck.json](evidence/usb-transport-recheck.json) | No new Android file, serial/role/gadget write, reboot, binding or temporary-boot operation occurred. |
| `HOST-USB-RECHECK` | `host_build` | [usb-transport-recheck.json](evidence/usb-transport-recheck.json) | The observation is time/host specific; no physical data path or recovery protocol was exercised. |
| `FEDORA-R4C-TMPFS` | `host_build` | [fedora-r4c-tmpfs-failed.md](fedora-r4c-tmpfs-failed.md) | API-filesystem and policy-map AVCs remain; manager-side FIFO denial truncates the FD message before pids/BPF. No owner hardware pass. |
| `FEDORA-R4C-TMPFS-ARTIFACTS` | `host_build` | [fedora-r4c-tmpfs-failed.json](evidence/fedora-r4c-tmpfs-failed.json) | Partial progress is not complete acceptance. The failed image was retained, not repaired or finalized as a success. |
| `FEDORA-R4C-TMPFS-VERIFY` | `host_build` | [fedora-r4c-tmpfs-failed-verify.json](evidence/fedora-r4c-tmpfs-failed-verify.json) | Aggregate migration passed=false remains unchanged because the final guest result is absent. No full-system marker, TasksMax or BPF behavioral pass. |
| `FEDORA-R4C-TMPFS-SERIAL` | `host_build` | [fedora-r4c-tmpfs-failed-verify.log](evidence/fedora-r4c-tmpfs-failed-verify.log) | 83 visible denial identifiers are not a complete audit inventory; callbacks were suppressed. Generic virt has no physical tablet devices. |
| `FEDORA-R4C-TMPFS-LABEL` | `host_build` | [fedora-r4c-tmpfs-failed-label.log](evidence/fedora-r4c-tmpfs-failed-label.log) | Its clean maintenance poweroff does not replace the failed production verification or establish production filesystem completion. |
| `FEDORA-R4C-TMPFS-ARCHIVE` | `host_build` | [fedora-r4c-tmpfs-initramfs-validation.json](evidence/fedora-r4c-tmpfs-initramfs-validation.json) | Archive/source/closure qualification does not prove runtime API filesystem labels, complete system operation or device firmware authentication. |
| `FEDORA-R4C-TMPFS-PROOF-PAYLOAD` | `host_build` | [fedora-r4c-tmpfs-initrd-proof-payloads.json](evidence/fedora-r4c-tmpfs-initrd-proof-payloads.json) | Payload identity is not proof that every label or queued event was correct; runtime observations are separately retained. |
| `FEDORA-R4C-TMPFS-UDEV` | `host_build` | [fedora-r4c-tmpfs-udev-qualification.json](evidence/fedora-r4c-tmpfs-udev-qualification.json) | It found no positive serialization/restoration count pair or accepted-FD line. Absence does not prove an empty queue; qualifier exit 1 is retained. |
| `FEDORA-R4C-TMPFS-SOURCE` | `host_build` | [fedora-r4c-execution-source.json](evidence/fedora-r4c-execution-source.json) | This establishes executed-source provenance, not whole-system bit-identical rebuild or a passed production run. |
| `SELINUX-RELOAD-CONTRACT-REVIEW` | `source_clue` | [selinux-runtime-contract-query.md](selinux-runtime-contract-query.md) | The old 9c79 kernel-export identity was never persisted; the aab7 offline policy is not asserted identical. Actual worker domains, descriptor transfer and policy bytes need their own same-boot evidence. |
| `SELINUX-RELOAD-CONTRACT-ARTIFACTS` | `host_build` | [selinux-runtime-contract-query.json](evidence/selinux-runtime-contract-query.json) | These are userspace AV computations on the fixed offline policy, not a running service transition, live-policy identity, successful FD route or hardware test. |
| `POLICY-MAP-REVIEW` | `host_build` | [selinux-policy-map-candidate.md](selinux-policy-map-candidate.md) | No kernel policy was loaded or modified and no enforcement mode changed. This does not close reload, API relabel, descriptor, resource-enforcement or physical-device runtime gates. |
| `POLICY-MAP-ARTIFACTS` | `host_build` | [selinux-policy-map-candidate.json](evidence/selinux-policy-map-candidate.json) | The candidate is offline. Fresh converted policy33 identities are not predetermined kernel-export identities; original compare-01 serialization and build warning remain recorded. |
| `POLICY-MAP-SOURCE-INVENTORY` | `host_build` | [selinux-policy-map-source-manifest.json](evidence/selinux-policy-map-source-manifest.json) | Host construction/provenance only; no running policy, runtime labeling or owner hardware outcome. |
| `POLICY-MAP-BEFORE-INVENTORY` | `host_build` | [selinux-policy-map-candidate-before-manifest.json](evidence/selinux-policy-map-candidate-before-manifest.json) | Host construction/provenance only; no running policy, runtime labeling or owner hardware outcome. |
| `POLICY-MAP-CANDIDATE-INVENTORY` | `host_build` | [selinux-policy-map-candidate-manifest.json](evidence/selinux-policy-map-candidate-manifest.json) | Host construction/provenance only; no running policy, runtime labeling or owner hardware outcome. |
| `POLICY-MAP-BUILD-LOG` | `host_build` | [selinux-policy-map-build.log](evidence/selinux-policy-map-build.log) | Host construction/provenance only; no running policy, runtime labeling or owner hardware outcome. |
| `EARLY-RELOAD-LOADER-REVIEW` | `host_build` | [early-selinux-reload-loader.md](early-selinux-reload-loader.md) | Size-only native checks cannot distinguish same-length policies. The new archive and runtime profile must pin the complete policy hash. Construction is not a PID1 or policy-load result. |
| `EARLY-RELOAD-LOADER-BUILD` | `host_build` | [early-selinux-reload-loader-build.json](evidence/early-selinux-reload-loader-build.json) | No VM, real PID1, mount, policy-load or physical boot was executed by this construction job. |
| `EARLY-RELOAD-LOADER-NEGATIVE` | `host_build` | [early-selinux-reload-loader-negative.json](evidence/early-selinux-reload-loader-negative.json) | A negative-entry check does not execute or prove the successful early-boot branch. |
| `SYSTEMD-BPF-CONTRACT-REVIEW` | `source_clue` | [systemd-bpf-runtime-contract.md](systemd-bpf-runtime-contract.md) | Source ordering and expected errno are not observations of an attached/running hook or an executed restrictive worker. |
| `SYSTEMD-BPF-CONTRACT-ARTIFACTS` | `source_clue` | [systemd-bpf-runtime-contract.json](evidence/systemd-bpf-runtime-contract.json) | No kernel policy load, BPF program attachment or hardware action was performed by this source audit. |
| `USB-RECHECK-1409-REVIEW` | `source_clue` | [usb-transport-recheck-1409.md](usb-transport-recheck-1409.md) | A bounded static snapshot does not establish cable failure, other hosts or the behavior of another boot mode. |
| `ANDROID-USB-RECHECK-1409` | `device_android` | [usb-transport-recheck-1409.json](evidence/usb-transport-recheck-1409.json) | No role, gadget, radio, serial, bootloader or recovery operation was performed. |
| `HOST-USB-RECHECK-1409` | `host_build` | [usb-transport-recheck-1409.json](evidence/usb-transport-recheck-1409.json) | This host/time-specific observation is not a transport trial, recovery return or statement about another host. |
| `POSTRELOAD-MAPONLY-REVIEW` | `source_clue` | [selinux-postreload-contract-query.md](selinux-postreload-contract-query.md) | Source behavior and candidate AV denials are not a newly observed VM failure or panic. |
| `POSTRELOAD-MAPONLY-ARTIFACTS` | `host_build` | [selinux-postreload-contract-query.json](evidence/selinux-postreload-contract-query.json) | This candidate permission contract remains incomplete. Query exit 0 is completion, not satisfaction of all runtime prerequisites. |
| `POLICY-MAP-SELF-REVIEW` | `host_build` | [selinux-policy-map-self-candidate.md](selinux-policy-map-self-candidate.md) | No cross-type dyntransition rule, label, boolean or permissive domain changes. This is construction/comparison, not actual reload, labels, FD routing or VM/tablet boot. |
| `POLICY-MAP-SELF-ARTIFACTS` | `host_build` | [selinux-policy-map-self-candidate.json](evidence/selinux-policy-map-self-candidate.json) | Fresh33 ce6ccb is an offline serialization, not a predetermined live export. The same-size cc042 loader keeps its original 0dd construction record; a new profile must pin the combined policy hash. |
| `POLICY-MAP-SELF-SOURCE` | `host_build` | [selinux-policy-map-self-source-manifest.json](evidence/selinux-policy-map-self-source-manifest.json) | Host provenance only. No kernel policy was loaded and no runtime labeling or device behavior is established. |
| `POLICY-MAP-SELF-BEFORE` | `host_build` | [selinux-policy-map-self-before-manifest.json](evidence/selinux-policy-map-self-before-manifest.json) | Host provenance only. No kernel policy was loaded and no runtime labeling or device behavior is established. |
| `POLICY-MAP-SELF-AFTER` | `host_build` | [selinux-policy-map-self-candidate-manifest.json](evidence/selinux-policy-map-self-candidate-manifest.json) | Host provenance only. No kernel policy was loaded and no runtime labeling or device behavior is established. |
| `POLICY-MAP-SELF-BUILD-LOG` | `host_build` | [selinux-policy-map-self-build.log](evidence/selinux-policy-map-self-build.log) | Host provenance only. No kernel policy was loaded and no runtime labeling or device behavior is established. |
| `POSTRELOAD-COMBINED-REVIEW` | `source_clue` | [selinux-postreload-combined-query.md](selinux-postreload-combined-query.md) | Offline permission closure cannot replace successful reload/transition, actual path labels, descriptor transfer or enforced worker behavior. |
| `POSTRELOAD-COMBINED-ARTIFACTS` | `host_build` | [selinux-postreload-combined-query.json](evidence/selinux-postreload-combined-query.json) | No new VM, live policy load or hardware test. The two retained denials are init_t read_policy and journald mapping the old syslogd_tmpfs_t file label. |
| `FEDORA-R4D-REVIEW` | `source_clue` | [fedora-r4d-reload-fd-failed.md](fedora-r4d-reload-fd-failed.md) | No corrected PL061 binding observation or restricted-filesystem workload is invented; two visible AVCs and serial-frame corruption remain failures. |
| `FEDORA-R4D-ARTIFACTS` | `host_build` | [fedora-r4d-reload-fd-failed.json](evidence/fedora-r4d-reload-fd-failed.json) | Generic virt only; no owner DT or device passthrough. Controller aggregate remains false, BPF behavior was not run, and owner hardware counts stay zero. |
| `FEDORA-R4D-VERIFY` | `host_build` | [fedora-r4d-reload-fd-failed-verify.json](evidence/fedora-r4d-reload-fd-failed-verify.json) | QEMU exit 0 is not a controller pass or proof of a clean production shutdown. |
| `FEDORA-R4D-SERIAL` | `host_build` | [fedora-r4d-reload-fd-failed-verify.log](evidence/fedora-r4d-reload-fd-failed-verify.log) | No frames are silently repaired; actual restricted proc-open behavior and corrected sysfs binding were not observed. |
| `FEDORA-R4D-LABEL` | `host_build` | [fedora-r4d-reload-fd-failed-label.json](evidence/fedora-r4d-reload-fd-failed-label.json) | Maintenance is separate from production Enforcing and cannot satisfy zero-AVC production or owner-device acceptance. |
| `FEDORA-R4D-LABEL-SERIAL` | `host_build` | [fedora-r4d-reload-fd-failed-label.log](evidence/fedora-r4d-reload-fd-failed-label.log) | This permissive labeling phase is not a clean production boot. |
| `FEDORA-R4D-ARCHIVE` | `host_build` | [fedora-r4d-reload-fd-initramfs-validation.json](evidence/fedora-r4d-reload-fd-initramfs-validation.json) | Archive qualification alone does not prove runtime labels, transport, resource controls or device boot. |
| `FEDORA-R4D-PROOF-PAYLOAD` | `host_build` | [fedora-r4d-reload-fd-initrd-proof-payloads.json](evidence/fedora-r4d-reload-fd-initrd-proof-payloads.json) | Payload identity is distinct from its observed same-boot output; no final aggregate pass is implied. |
| `FEDORA-R4D-UDEV` | `host_build` | [fedora-r4d-reload-fd-udev-qualification.json](evidence/fedora-r4d-reload-fd-udev-qualification.json) | No positive count pair is converted into an empty-queue or complete queue-preservation claim. |
| `FEDORA-R4D-CONSTRUCTION` | `host_build` | [fedora-r4d-reload-fd-construction.json](evidence/fedora-r4d-reload-fd-construction.json) | Successful construction is not successful production verification; later failure remains authoritative. |
| `FEDORA-R4D-POLICY-EXPORT` | `host_build` | [fedora-r4d-loaded-policy-export.json](evidence/fedora-r4d-loaded-policy-export.json) | The actual export is distinct from offline ce6ccb serialization; no whole-policy equality is assumed. |
| `FEDORA-R4D-FREEZE-JOB` | `host_build` | [fedora-r4d-failure-freeze-job.json](evidence/fedora-r4d-failure-freeze-job.json) | Archiving a failed run does not change its outcome. |
| `FEDORA-R4D-SOURCE` | `host_build` | [fedora-r4d-execution-source.json](evidence/fedora-r4d-execution-source.json) | Source provenance is not a runtime or hardware result. |
| `FEDORA-R4D-BASELINE` | `host_build` | [fedora-r4d-baseline-preparation.json](evidence/fedora-r4d-baseline-preparation.json) | No PRoot on the frozen original R1 source; a valid copy does not predict a successful VM. |
| `FEDORA-R4D-PLAN` | `source_clue` | [fedora-r4d-profile-plan.md](fedora-r4d-profile-plan.md) | This plan is not the completed outcome; use the frozen failure report for actual observations. |
| `VARLINK-CLEANUP-REVIEW` | `source_clue` | [selinux-varlink-cleanup.md](selinux-varlink-cleanup.md) | Only registry unlink and journal socket write are observed AVCs; connectto is the next source-qualified permission gate, not a captured AVC. Target socket getattr is not needed by the fixed short-path client. |
| `VARLINK-CLEANUP-ARTIFACTS` | `host_build` | [selinux-varlink-cleanup.json](evidence/selinux-varlink-cleanup.json) | No conversion was applied to actual 0fe3. Agreement is limited to the 32 queried decisions, not whole-policy serialization or semantic equality. No repair, VM or device action is part of this diagnosis. |
| `STANDARD-POLICY-REVIEW` | `host_build` | [selinux-standard-service-policy.md](selinux-standard-service-policy.md) | No label, boolean, permissive-domain or cross-type transition change. This is candidate construction, not a live reload or service result. |
| `STANDARD-POLICY-ARTIFACTS` | `host_build` | [selinux-standard-service-policy.json](evidence/selinux-standard-service-policy.json) | Fresh33 9b39b5a5 is an offline serialization, not a predetermined kernel export. New initramfs and runtime gates must bind their actual policy bytes. |
| `STANDARD-POLICY-SOURCE` | `host_build` | [selinux-standard-service-policy-source-manifest.json](evidence/selinux-standard-service-policy-source-manifest.json) | Host provenance only; no kernel policy load, process transition or hardware behavior is established. |
| `STANDARD-POLICY-BEFORE` | `host_build` | [selinux-standard-service-policy-before-manifest.json](evidence/selinux-standard-service-policy-before-manifest.json) | Host provenance only; no kernel policy load, process transition or hardware behavior is established. |
| `STANDARD-POLICY-AFTER` | `host_build` | [selinux-standard-service-policy-candidate-manifest.json](evidence/selinux-standard-service-policy-candidate-manifest.json) | Host provenance only; no kernel policy load, process transition or hardware behavior is established. |
| `STANDARD-POLICY-BUILD-LOG` | `host_build` | [selinux-standard-service-policy-build.log](evidence/selinux-standard-service-policy-build.log) | Host provenance only; no kernel policy load, process transition or hardware behavior is established. |
| `STANDARD-AV-REVIEW` | `source_clue` | [selinux-standard-service-av-query.md](selinux-standard-service-av-query.md) | This report checks a candidate permission subset, not live domains, object labels, FD identities or the complete runtime. |
| `STANDARD-AV-ARTIFACTS` | `host_build` | [selinux-standard-service-av-query.json](evidence/selinux-standard-service-av-query.json) | Repeated historical rows are not independent runs. Target-socket getattr and the original denial controls remain denied; no VM or policy load occurs. |
| `AUDIT-OBSERVABILITY-REVIEW` | `source_clue` | [audit-observability.md](audit-observability.md) | Six suppressed callbacks do not identify six AVCs. Removing this limiter does not prove audit queues or serial transport are lossless. |
| `AUDIT-OBSERVABILITY-ARTIFACTS` | `source_clue` | [audit-observability.json](evidence/audit-observability.json) | Static analysis performs no sysctl setting, policy load or new VM run; old lost content is not recovered. |
| `AUDIT-OBSERVABILITY-SOURCE` | `source_clue` | [audit-observability-source-manifest.json](evidence/audit-observability-source-manifest.json) | This is source binding, not execution of the guarded branch. Audit admission, queue limits, Enforcing and all runtime gates remain separate. |
| `EARLY-STANDARD-LOADER-REVIEW` | `host_build` | [early-selinux-standard-services-loader.md](early-selinux-standard-services-loader.md) | One successful compilation is not an independent identical rebuild. Runtime C checks policy length; archive and profile must pin the complete policy hash. |
| `EARLY-STANDARD-LOADER-BUILD` | `host_build` | [early-selinux-standard-services-build.json](evidence/early-selinux-standard-services-build.json) | Construction or entry-refusal scope only; no new successful PID1 path, sysctl update, policy load or hardware test. |
| `EARLY-STANDARD-LOADER-NEGATIVE` | `host_build` | [early-selinux-standard-services-negative.json](evidence/early-selinux-standard-services-negative.json) | Construction or entry-refusal scope only; no new successful PID1 path, sysctl update, policy load or hardware test. |
| `EARLY-STANDARD-LOADER-INVOCATION` | `host_build` | [early-selinux-standard-services-invocation.json](evidence/early-selinux-standard-services-invocation.json) | Construction or entry-refusal scope only; no new successful PID1 path, sysctl update, policy load or hardware test. |
| `EARLY-STANDARD-LOADER-INPUT-TRANSFER` | `host_build` | [early-selinux-standard-services-input-transfer.json](evidence/early-selinux-standard-services-input-transfer.json) | Construction or entry-refusal scope only; no new successful PID1 path, sysctl update, policy load or hardware test. |
| `EARLY-STANDARD-LOADER-HDD-TRANSFER` | `host_build` | [early-selinux-standard-services-hdd-transfer.json](evidence/early-selinux-standard-services-hdd-transfer.json) | Construction or entry-refusal scope only; no new successful PID1 path, sysctl update, policy load or hardware test. |
| `TMPFS-WAITER-V2-REVIEW` | `host_build` | [tmpfs-waiter-v2.md](tmpfs-waiter-v2.md) | Its unchanged cleanup code is not a new cleanup run. The target length72528 is not a content hash; both complete ELF identities remain required. |
| `TMPFS-WAITER-V2-ARTIFACTS` | `host_build` | [tmpfs-waiter-v2.json](evidence/tmpfs-waiter-v2.json) | No old-root cleanup, target execution, policy loading or VM was performed by this build. The raw timestamp qualification is explicit. |
| `USB-RECHECK-1546-REVIEW` | `source_clue` | [usb-transport-recheck-20261123T074657Z.md](usb-transport-recheck-20261123T074657Z.md) | A bounded passive snapshot does not establish cable failure, another host, a data link or a recovery return. |
| `ANDROID-USB-RECHECK-1546` | `device_android` | [usb-transport-recheck-20261123T074657Z.json](evidence/usb-transport-recheck-20261123T074657Z.json) | One successful fixed-helper read; no role, gadget, serial, bootloader or recovery action. |
| `HOST-USB-RECHECK-1546` | `host_build` | [usb-transport-recheck-20261123T074657Z.json](evidence/usb-transport-recheck-20261123T074657Z.json) | This host/time-specific observation does not determine physical cable presence or the state of another host. |
| `FEDORA-R4E-REVIEW` | `host_build` | [fedora-r4e-persistent-result-failed.md](fedora-r4e-persistent-result-failed.md) | Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-ARTIFACTS` | `host_build` | [fedora-r4e-persistent-result-failed.json](evidence/fedora-r4e-persistent-result-failed.json) | Source policy35, offline converted33 and actual exported33 have separate hashes. Post-qualify, finalize and postboot e2fsck did not run. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-VERIFY` | `host_build` | [fedora-r4e-persistent-result-failed-verify.json](evidence/fedora-r4e-persistent-result-failed-verify.json) | Guest checks cannot override host full-log denial/loss checks; the controller was not rescored. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-SERIAL` | `host_build` | [fedora-r4e-persistent-result-failed-verify.log](evidence/fedora-r4e-persistent-result-failed-verify.log) | Zero configured production loss markers is a bounded observation, not proof against every theoretically unobservable event. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-GUEST` | `host_build` | [fedora-r4e-persistent-result-failed-guest.json](evidence/fedora-r4e-persistent-result-failed-guest.json) | Its pass envelope explicitly leaves host qualification pending and complete_system_accepted=false. Four matrices are four routes, not four independently booted systems. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-LABEL` | `host_build` | [fedora-r4e-persistent-result-failed-label.json](evidence/fedora-r4e-persistent-result-failed-label.json) | Maintenance is not an Enforcing production result; its denials and suppression remain in its own raw log. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-LABEL-SERIAL` | `host_build` | [fedora-r4e-persistent-result-failed-label.log](evidence/fedora-r4e-persistent-result-failed-label.log) | These preparation observations are not included in a claim of clean Enforcing production. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-PIPELINE` | `host_build` | [fedora-r4e-persistent-result-failed-pipeline.json](evidence/fedora-r4e-persistent-result-failed-pipeline.json) | Later post-qualification/finalization were not executed or backfilled. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-POLICY-RETENTION` | `host_build` | [fedora-r4e-persistent-result-failed-policy-retention.json](evidence/fedora-r4e-persistent-result-failed-policy-retention.json) | The original passed-only pipeline was unchanged; no image replay/write, new policy load or extra VM occurred. Public evidence excludes the policy binary. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-FREEZE-JOB` | `host_build` | [fedora-r4e-freeze-execution.json](evidence/fedora-r4e-freeze-execution.json) | A successful archival job is not a successful system or hardware run. |
| `FEDORA-R4E-TRANSFER` | `host_build` | [fedora-r4e-failed-evidence-transfer.json](evidence/fedora-r4e-failed-evidence-transfer.json) | No raw private policy binary is in the public packet. Transport success does not change the failed production result. |
| `FEDORA-R4E-SOURCE` | `host_build` | [fedora-r4e-execution-source.json](evidence/fedora-r4e-execution-source.json) | Source identity and launch do not establish runtime success. Generic ARM64 VM only; no owner-tablet Linux boot or hardware acceptance. The complete production attempt remains failed. |
| `FEDORA-R4E-BASELINE` | `host_build` | [fedora-r4e-baseline-preparation.json](evidence/fedora-r4e-baseline-preparation.json) | No PRoot ran against the frozen R1 source; copy and input checks are not a boot result. |
| `FEDORA-R4E-PLAN` | `source_clue` | [fedora-r4e-profile-plan.md](fedora-r4e-profile-plan.md) | Planned gates are distinguished from completed phases and from physical acceptance. |
| `FEDORA-R4E-TRANSPORT-CASES` | `host_build` | [fedora-r4e-result-transport-qualification.json](evidence/fedora-r4e-result-transport-qualification.json) | Synthetic clean-image checks are not a VM boot or a crash-consistency guarantee; normal-shutdown transport is separately observed in v8. |
| `SOCKET-PROBE-REVIEW` | `source_clue` | [selinux-journalctl-socket-probe.md](selinux-journalctl-socket-probe.md) | The original v8 AVC and failed verdict remain unchanged. Source control flow and offline permission queries do not establish a repaired runtime. |
| `SOCKET-PROBE-ARTIFACTS` | `source_clue` | [selinux-journalctl-socket-probe.json](evidence/selinux-journalctl-socket-probe.json) | No connect, send, setsockopt or target-getattr permission is inferred. The actual v8 creation denial was retained rather than ignored. |
| `SOCKET-PROBE-LIVE-POLICY-AV` | `host_build` | [selinux-journalctl-socket-probe-query.json](evidence/selinux-journalctl-socket-probe-query.json) | This is a query of a saved policy file, not a newly loaded policy or new guest execution. |
| `SOCKET-POLICY-REVIEW` | `host_build` | [selinux-socket-probe-policy.md](selinux-socket-probe-policy.md) | Offline candidate qualification only. Labels, booleans, cross-domain permissions and old evidence are retained; no new policy load or repaired production result is claimed. |
| `SOCKET-POLICY-ARTIFACTS` | `host_build` | [selinux-socket-probe-policy.json](evidence/selinux-socket-probe-policy.json) | Offline candidate qualification only. Labels, booleans, cross-domain permissions and old evidence are retained; no new policy load or repaired production result is claimed. |
| `SOCKET-POLICY-BUILD` | `host_build` | [selinux-socket-probe-policy-build.json](evidence/selinux-socket-probe-policy-build.json) | Offline candidate qualification only. Labels, booleans, cross-domain permissions and old evidence are retained; no new policy load or repaired production result is claimed. |
| `SOCKET-POLICY-COMPARE` | `host_build` | [selinux-socket-probe-policy-compare.json](evidence/selinux-socket-probe-policy-compare.json) | Offline candidate qualification only. Labels, booleans, cross-domain permissions and old evidence are retained; no new policy load or repaired production result is claimed. |
| `SOCKET-POLICY-AV` | `host_build` | [selinux-socket-probe-policy-query.json](evidence/selinux-socket-probe-policy-query.json) | Offline candidate qualification only. Labels, booleans, cross-domain permissions and old evidence are retained; no new policy load or repaired production result is claimed. |
| `EARLY-SOCKET-LOADER-REVIEW` | `host_build` | [early-selinux-socket-probe-loader.md](early-selinux-socket-probe-loader.md) | Construction/negative-entry/transport evidence only. The unchanged waiter V2 checks target size, while the archive/profile must pin full ELF and policy hashes; no PID1 success or owner entry follows. |
| `EARLY-SOCKET-LOADER-BUILD` | `host_build` | [early-selinux-socket-probe-build.json](evidence/early-selinux-socket-probe-build.json) | Construction/negative-entry/transport evidence only. The unchanged waiter V2 checks target size, while the archive/profile must pin full ELF and policy hashes; no PID1 success or owner entry follows. |
| `EARLY-SOCKET-LOADER-NEGATIVE` | `host_build` | [early-selinux-socket-probe-negative.json](evidence/early-selinux-socket-probe-negative.json) | Construction/negative-entry/transport evidence only. The unchanged waiter V2 checks target size, while the archive/profile must pin full ELF and policy hashes; no PID1 success or owner entry follows. |
| `EARLY-SOCKET-LOADER-INVOCATION` | `host_build` | [early-selinux-socket-probe-invocation.json](evidence/early-selinux-socket-probe-invocation.json) | Construction/negative-entry/transport evidence only. The unchanged waiter V2 checks target size, while the archive/profile must pin full ELF and policy hashes; no PID1 success or owner entry follows. |
| `EARLY-SOCKET-LOADER-HDD-TRANSFER` | `host_build` | [early-selinux-socket-probe-hdd-transfer.json](evidence/early-selinux-socket-probe-hdd-transfer.json) | Construction/negative-entry/transport evidence only. The unchanged waiter V2 checks target size, while the archive/profile must pin full ELF and policy hashes; no PID1 success or owner entry follows. |
| `FEDORA-R4F-REVIEW` | `host_build` | [fedora-r4f-image-failed.md](fedora-r4f-image-failed.md) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-ARTIFACTS` | `host_build` | [fedora-r4f-image-failed.json](evidence/fedora-r4f-image-failed.json) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-PIPELINE` | `host_build` | [fedora-r4f-image-failed-pipeline.json](evidence/fedora-r4f-image-failed-pipeline.json) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-IMAGE` | `host_build` | [fedora-r4f-image-failed-image.json](evidence/fedora-r4f-image-failed-image.json) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-IMAGE-LOG` | `host_build` | [fedora-r4f-image-failed-image.log](evidence/fedora-r4f-image-failed-image.log) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-INITRAMFS` | `host_build` | [fedora-r4f-image-failed-initramfs.json](evidence/fedora-r4f-image-failed-initramfs.json) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-SOURCE` | `host_build` | [fedora-r4f-execution-source.json](evidence/fedora-r4f-execution-source.json) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `FEDORA-R4F-BASELINE` | `host_build` | [fedora-r4f-baseline-preparation.json](evidence/fedora-r4f-baseline-preparation.json) | No VM, actual policy export, live AV/FD/TasksMax/BPF/journal gate or tablet test ran. The partial image was not mounted, repaired, hashed as complete or rescored. Concurrent HDD work is context, not a proven exclusive cause. |
| `NURA-ENTRY-REVIEW` | `source_clue` | [nura-entry-inventory.md](nura-entry-inventory.md) | Static stopped-tree inventory only. It does not rehash every archive member or execute target startup, and its original R4 next-plan is superseded by the separately qualified R5 prerequisites. |
| `NURA-ENTRY-ARTIFACTS` | `host_build` | [nura-entry-inventory.json](evidence/nura-entry-inventory.json) | An ELF or service definition is not a running process, successful OpenRC runlevel or owner hardware result. |
| `R5-KERNEL` | `host_build` | [research5-services-kernel.md](research5-services-kernel.md) | No R5 system VM or module load occurred in this construction/transfer. The new signing key and unsnapshotted packages preclude a bit-identical rebuild claim. Original 894-path Nix and Nura target boot gates remain open. |
| `R5-ARTIFACTS` | `host_build` | [research5-services-build.json](evidence/research5-services-build.json) | No R5 system VM or module load occurred in this construction/transfer. The new signing key and unsnapshotted packages preclude a bit-identical rebuild claim. Original 894-path Nix and Nura target boot gates remain open. |
| `R5-VERIFICATION` | `host_build` | [research5-services-verification.json](evidence/research5-services-verification.json) | No R5 system VM or module load occurred in this construction/transfer. The new signing key and unsnapshotted packages preclude a bit-identical rebuild claim. Original 894-path Nix and Nura target boot gates remain open. |
| `R5-CONFIGURATION` | `host_build` | [configuration.json](evidence/research5-services-records/container/configuration.json) | No R5 system VM or module load occurred in this construction/transfer. The new signing key and unsnapshotted packages preclude a bit-identical rebuild claim. Original 894-path Nix and Nura target boot gates remain open. |
| `R5-TRANSFER` | `host_build` | [transfer.json](evidence/research5-services-records/control/shared-transfer/transfer.json) | No R5 system VM or module load occurred in this construction/transfer. The new signing key and unsnapshotted packages preclude a bit-identical rebuild claim. Original 894-path Nix and Nura target boot gates remain open. |
| `R5-CONTRACT` | `source_clue` | [services-contract.json](../../../scripts/research/system-kernel/research5-services/recipe-v1/services-contract.json) | Source/configuration contract only; no actual firewall packet behavior, zram, RTC, generic R5 VM or owner hardware pass. |
| `USB-RECHECK-1736-REVIEW` | `source_clue` | [usb-transport-recheck-20261123T093624Z.md](usb-transport-recheck-20261123T093624Z.md) | This does not identify a broken cable, a physical connection or another host; no role, gadget, bootloader or recovery action occurs. |
| `ANDROID-USB-RECHECK-1736` | `device_android` | [usb-transport-recheck-20261123T093624Z.json](evidence/usb-transport-recheck-20261123T093624Z.json) | Passive current-state observation only; no Linux entry, binding, transfer or usable recovery is established. |
| `HOST-USB-RECHECK-1736` | `host_build` | [usb-transport-recheck-20261123T093624Z.json](evidence/usb-transport-recheck-20261123T093624Z.json) | The observation is specific to this host/time and cannot determine a different host or physical cable state. |
| `TOOLS-MAC-BOUNDARY` | `host_build` | [research-tools-mac-boundary.json](evidence/research-tools-mac-boundary.json) | No raw evidence exemption, broad test rerun, hardware result or disclosure claim is introduced. Original R4/R5 evidence bytes are unchanged. |
| `NIX-ROOT-PREPARATION-REVIEW` | `source_clue` | [nixos-store-preparation-failed.md](nixos-store-preparation-failed.md) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
| `NIX-ROOT-PREPARATION-ARTIFACTS` | `host_build` | [nixos-store-preparation-failed.json](evidence/nixos-store-preparation-failed.json) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
| `NIX-ROOT-PREPARATION-ORIGINAL` | `host_build` | [store-preparation.json](evidence/nixos-store-preparation-failed-records/store-preparation.json) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
| `NIX-ROOT-PREPARATION-JOB` | `host_build` | [store-01.json](evidence/nixos-store-preparation-failed-records/store-01.json) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
| `NIX-ROOT-PREPARATION-COPY-STDERR` | `host_build` | [signed-cache-copy.stderr.log](evidence/nixos-store-preparation-failed-records/signed-cache-copy.stderr.log) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
| `NIX-ROOT-PREPARATION-SOURCE-VERIFY` | `host_build` | [source-verify.stderr.log](evidence/nixos-store-preparation-failed-records/source-verify.stderr.log) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
| `NIX-ROOT-PREPARATION-SOURCE` | `source_clue` | [prepare_store.py](../../../scripts/research/nixos/store-preparation-v1/prepare_store.py) | No destination registration/content/signature qualification, source-after comparison, image, activation, PID1 or VM was reached. Old partial cache and original timeout are retained, private key bytes excluded, and no exclusive I/O cause or owner hardware result is inferred. |
