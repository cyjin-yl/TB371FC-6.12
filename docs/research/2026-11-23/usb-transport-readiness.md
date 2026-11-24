# Actual USB transport state and the two-UDC entry gap

At approximately **2026-11-23 11:01 Asia/Shanghai**, a new bounded read-only
capture checked both the running owner Android system and doesvm. It found
no established USB data/recovery connection between them. It also exposed a
specific limitation in the already built first-stage rescue script: the
owner's Android system exposes **two** USB device controllers, whereas that
script only selects a controller when exactly one exists.

The reusable [collector](../../../scripts/research/capture_usb_transport.py)
has SHA256 `70f7e9adc8f2acc2162510bec375ceff94710bfa7fb46da7c287a30db4336ea0`.
It reads only bounded, named USB attributes. It does not read serial numbers,
read arbitrary gadget strings, change a role/configuration, bind a gadget,
restart USB, or issue any reboot/bootloader command. Both actual commands
returned exit 0. The Android capture ran through the already available root
connection; its existence is not evidence of a USB connection.

## Owner Android observation

The [owner capture](evidence/android-usb-transport.json) records
`2026-11-23T03:01:21.841003+00:00`:

| Object | Observed values |
| --- | --- |
| UDC `a600000.dwc3` | `state=not attached`, `current_speed=UNKNOWN`, `maximum_speed=super-speed-plus` |
| UDC `a800000.dwc3` | `state=not attached`, `current_speed=UNKNOWN`, `maximum_speed=super-speed` |
| Android gadget `/config/usb_gadget/g1` | Bound UDC name `a600000.dwc3`; VID/PID `0x17ef:0x7e31` |
| Android gadget `/config/usb_gadget/g2` | Empty bound UDC; VID/PID both zero |
| Type-C `port0` | Selected data role `device`, power role `sink`, port type `dual` |

The controller's advertised maximum speed is not a measured cable speed or
proof of a functioning SuperSpeed link. Two UDCs do not establish two external
USB connectors. A configured gadget identity does not establish host enumeration.
These are Android observations, not observations of the new first-stage kernel.

## doesvm observation

The [host capture](evidence/doesvm-usb-transport.json), taken at
`2026-11-23T03:01:23.513808+00:00`, contains 14 USB device entries. None has
Lenovo VID `17ef`, and none matches the additional Google/Qualcomm vendor
candidate IDs `18d1`/`05c6`. In particular, the owner's currently configured
Android `17ef:7e31` gadget was not present in this host snapshot.

This is a result for **doesvm at that instant**, not a claim that another
computer cannot see the tablet or that a different boot mode must use the
same product ID. Vendor-ID matching alone would not establish tablet identity
or a working fastboot/recovery protocol even if a candidate appeared.

## Concrete first-stage implication

The frozen [first-stage reconstruction](first-stage-reconstruction.md) uses a
rescue init that enumerates `/sys/class/udc/*` and creates ACM only when its
count is exactly one. With the two entries observed here, that branch would
report `TB371FC_ENTRY_UDC_UNRESOLVED` and hold without creating ACM. This is a
code/observed-topology mismatch, not a failed physical boot of that image.

The observed Android binding supplies a specific controller candidate,
`a600000.dwc3`, for a separate owner-specific rescue revision. Its selection
must require that exact controller to exist, must retain a hold path if it
is missing or unavailable, and must not silently select another controller
or force USB role changes. The frozen first-stage artifact is retained;
any amended ramdisk needs its own hash, userspace checks and image-format
verification. Successful shell selection or a generic QEMU run still cannot
prove electrical connectivity, ACM enumeration, recovery, or kexec on the tablet.

## Remaining physical gate

A data cable and a controllable USB host must first provide an independently
identified tablet connection. The actual bootloader state and a usable return
path then need observation before any experimental entry. The Android
property/command-line lock-state disagreement remains as recorded in
[boot readiness](boot-readiness.md); neither this USB snapshot nor the existing
verified partition backups resolve it. No slot, partition, bootloader state or
owner filesystem was changed by this capture.
