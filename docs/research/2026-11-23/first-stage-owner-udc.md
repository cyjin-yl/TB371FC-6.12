# Owner-specific UDC selection for the rescue userspace

The separate **owner-UDC r2** rescue ramdisk fixes the concrete two-controller
selection gap found by the [USB transport capture](usb-transport-readiness.md).
Its ten source-derived selection checks, reference-kernel PID 1 smoke test,
and independent Android v2 image-format check completed successfully. These
are host qualifications. **The tablet has not booted this image, no physical
USB console has been established, and the default action remains HOLD.**

The [complete evidence record](evidence/first-stage-owner-udc.json) contains
the exact source and input hashes, all ten selector cases, the new archive
manifest, the raw reference-VM serial output encoded as base64, and the
private image's format metadata. It does not publish the owner partition,
its raw stored command line, or the private image bytes.

## Why the controller selection changed

The frozen [first-stage reconstruction](first-stage-reconstruction.md)
created an ACM gadget only when `/sys/class/udc/*` contained exactly one
controller. The owner's Android capture at
`2026-11-23T03:01:21.841003+00:00` instead found both `a600000.dwc3` and
`a800000.dwc3`. Android gadget `g1` was configured against `a600000.dwc3`.
Both controllers were then `not attached`; the doesvm snapshot did not
enumerate the configured `17ef:7e31` identity. This observation identifies
which controller Android configured, not a working host connection.

The new [init](../../../scripts/research/entry/owner-udc/ramdisk-init) uses
one fixed target, `/sys/class/udc/a600000.dwc3`. It requires that target to be
a directory and its `state` and `maximum_speed` attributes to be regular,
readable files. If those predicates fail, it holds without trying the other
controller. No command-line argument, environment variable, alternative
sysfs root or arbitrary-controller fallback was added to the production
selector. It does not force a USB role or PD state.

These metadata predicates establish only that the expected UDC interface is
present. They do not establish that the controller can bind a new gadget or
that a cable/host is attached. The existing gadget-binding operation retains
its failure branch and local console. The successful-binding message also
explicitly leaves host enumeration unverified. No such operation was run on
the tablet during this qualification.

The [repacker](../../../scripts/research/entry/owner-udc/repack.py) reverses
the new selector insertion, call-site change and diagnostic text and requires
the result to match the frozen original init exactly. It reuses the same
three static AArch64 executables. Decoding and comparing the complete old
and new archives showed that **only `init` changed**, among fifteen archive
entries; the other entry contents and recorded modes remain identical.
The old source, archives, kernel, reports and private candidate remain intact.

## Actual checks and their scope

The isolated job started at `2026-11-23T03:09:48.634222+00:00` in CT102's
`tb371fc-build-ssd-20261123` container. It exited 0 after **11.712 seconds**.
Its independent output prefix is
`/work/first-stage-research/userspace-r2-owner-udc`.

| Check | Observed result | Limit |
| --- | --- | --- |
| Reused binary identity | All three pinned hashes matched; AArch64 ELF64 and absence of `PT_INTERP` rechecked | No new binary or downstream kernel compilation |
| ARM userspace checks | BusyBox shell syntax, `kexec --version`, and return-helper `--version` exited 0 under QEMU user emulation | No kexec or reboot syscall exercised |
| Both observed controllers present | Selected only `a600000.dwc3` | Source-derived predicate fixture, not actual sysfs |
| Only the observed primary present | Selected `a600000.dwc3` | Same logic-only scope |
| Only secondary, no controller, or only unknown controller | HOLD in all three cases | No fallback was queried |
| Target not a directory; either required attribute absent/nonregular or unreadable | HOLD in all five cases | File predicates were mocked, not changed on a device |
| Repacked archive | Exactly one changed entry: `init`; all other decoded entries unchanged | Archive consistency, not a bootloader test |
| Reference-kernel VM | Actual PID 1, exact release and AArch64 EL0 markers; controller result `pass` in **3.865 seconds**; child reaped | Frozen research2 kernel on generic `virt`, not the new downstream entry kernel |
| Private Android v2 format | Local parser and pinned independent AOSP unpacker agreed on all four payload hashes and image ID | Unsigned, not AVB-trusted or physically booted |

The fixture harness executes the **unaltered production selector function**
with ARM BusyBox. It mocks only the shell `test` primitive and records every
queried predicate. All ten cases passed; all queries referred to the fixed
primary path, and neither the secondary nor an unknown controller was queried.
This checks the fail-closed branch logic without weakening the actual init's
fixed `/sys` path or writing any sysfs tree.

The VM deliberately uses `tb371fc.entry_smoke=1`, which skips the gadget
branch. It therefore does not separately test controller selection or ACM
binding. It used QEMU 10.0.13, TCG, `cortex-a76`, two virtual CPUs, 1 GiB RAM,
no network interface and no disk. The observed kernel was
`6.12.114-tb371fc-research2-display`; its Image hash remains
`181f0152868a2dc501191f09cb839ff295f6814f38f0bf027d6f55833382b27d`.
The serial stream reported `TB371FC_ENTRY_KEXEC_LOADED=0` before the ready
markers. The controller terminated and reaped the guest after those markers.

The unchanged public `4.19.325-cip134-st18-tb371fc-entry-r1` kernel retains
its previously recorded generic-`virt` Qualcomm SCM failure before PID 1.
This ramdisk revision neither bypasses SCM nor supplies the missing Lenovo
board-driver and historical handoff contracts. A successful reference-kernel
userland test cannot be counted as a downstream-kernel runtime pass.

## New artifacts and exact identities

| Item | Bytes | SHA256 |
| --- | ---: | --- |
| New init source | 3,336 | `442a69181a7e8bb9802afbe23d94929d9844eb9163ee0be2a3080aa2a65c829f` |
| New rescue initramfs | 1,351,720 | `4e89de6d7de7535eb0e70a2557a3ad123f0e89d5d2724ec9104984aeb7db92a5` |
| Repack manifest | 14,502 | `f388996a70a8d2deded1853d6213ed6896cb06ec6cd4dba34b4ba6e64e5400bc` |
| Reference-VM result | 2,432 | `951713a0923a941000651ee1a40e556ae84d66d8fd4499d3319d6426c47cc194` |
| Reference-VM raw serial | 17,441 | `c82842509d1d7aee64bb676834be9ef17f7c914cfc53e46e7a7961018f1c749c` |
| Private v2 image | 53,587,968 | `7239c215ebb56ff5580a9b7ac9599859ab8242443e5204d70e4b618ef51587a6` |
| Private format manifest | 6,868 | `656e207404ed1dca080f8de6fdcf7f04fac259406066c65eb4414cf1a1f9342d` |

The repacker source SHA256 is
`5900579a1d844a2929886254d3275d1a09b768a0922067a68e3f9af103f26974`;
the [qualification wrapper](../../../scripts/research/entry/owner-udc/qualify.sh)
SHA256 is
`eee790221b0469d7ccc132d7cf9118eda33b53836f97d4efcd1a19a64324be48`.
The full record also binds the unchanged old helpers, original source and
userspace manifests, owner USB capture, private recovery input and reference
kernel. The actual completed job log is retained on the builder with SHA256
`8ea816deb21162395442db126ea67884e623385327104e633f77eff07225133a`.

The private candidate is under the new prefix at
`private-owner-v2/entry-r1-owner-recovery-a-unsigned-v2.img`. Its existing
`entry-r1` basename denotes the unchanged kernel lineage; the containing
prefix and manifests identify the new owner-UDC ramdisk. The old candidate
was not replaced.

## Android v2 format boundaries

The frozen packaging helper preserved the original 4 KiB header page except
for the necessary kernel/ramdisk sizes, component offset and image-ID bytes.
Exactly 27 header byte positions differ; all other header bytes are identical.
The owner's recovery DTBO and DTB remain byte-for-byte identical, with SHA256
`279910628e61cad149ccdb16ae0aa0a3a2f46441e21132ac3a1323e565219679`
and `cb0f50f13fd70b5dcd0b12d330ae09d070ae4d6f20f4873b1a9815883726ee0e`.
The original partition padding/trailer was not copied, and the candidate has
no AVB footer. Source backup permissions were not changed.

The independent unpacker is the pinned AOSP `unpack_bootimg.py` at
commit `8d0922bfb932ee532226728b1bf2fe54a2055f5a`. It returned exit 0;
kernel, ramdisk, DTBO and DTB hashes and the calculated image ID matched.
Its raw output remains private. This verifies the container's structure,
not the bootloader's signature policy, rollback constraints, runtime load
addresses, DT-to-driver compatibility or physical bootability.

## Reproduction and remaining gate

The wrapper requires the frozen source and artifact hashes recorded in the
JSON, the already verified owner recovery backup and the reference research2
kernel. With those prerequisites present, a separate attempt can run inside
the same isolated builder using an unused accepted suffix:

```sh
python3 -B /src/scripts/research/build/run_job.py \
  --work /work/first-stage-research --name owner-udc-r2-qualify-02 \
  -- bash /src/scripts/research/entry/owner-udc/qualify.sh \
  userspace-r2-owner-udc-02
```

Existing output prefixes are rejected. This sequence repacks, qualifies the
userland on the reference kernel, and creates a fresh private format-only
candidate. It does not boot, bind USB on, or change a partition of the tablet.

Before any physical experiment, the [USB transport gate](usb-transport-readiness.md)
still requires an independently identified, controllable tablet connection
and a verified recovery/return path. The compiled entry kernel's board
contract and the bootloader's actual acceptance policy remain unresolved.
**Physical USB, downstream entry boot, bootloader acceptance, AVB trust,
kexec handoff and recovery-return results are all unverified.**
