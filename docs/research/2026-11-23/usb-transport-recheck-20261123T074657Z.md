# USB transport recheck at 15:46:57 Shanghai

## Actual capture and result

The unchanged bounded helper was run **once on each endpoint**, after the
independent v8 upload and launch completed. The actual capture starts were
**2026-11-23 15:46:57.804759–15:46:59.677840 Asia/Shanghai**
(07:46:57.804759–07:46:59.677840 UTC).
Both commands exited zero with empty standard error.

The [complete original capture record](evidence/usb-transport-recheck-20261123T074657Z.json) retains each
parsed JSON observation, exact returned stdout/stderr and bridge text, output
identities, commands and time bounds. The [14:09 record](usb-transport-recheck-1409.md)
remains unchanged. This filename uses the first actual capture-start time in
UTC, rather than a planned or report-writing time.

| Surface | Observed value |
|---|---|
| Owner Android capture start | 07:46:57.804759 UTC / 15:46:57.804759 Shanghai |
| Android a600000.dwc3 | state: not attached; current_speed: UNKNOWN |
| Android a800000.dwc3 | state: not attached; current_speed: UNKNOWN |
| Configured g1 gadget | UDC a600000.dwc3; vendor/product 0x17ef:0x7e31 |
| Configured g2 gadget | Empty UDC; vendor/product 0x0000:0x0000 |
| Android port0 reported roles | data_role: host [device]; power_role: source [sink] |
| doesvm capture start | 07:46:59.677840 UTC / 15:46:59.677840 Shanghai |
| doesvm USB inventory | 14 sysfs device entries, including root hubs |
| Lenovo/Google/Qualcomm vendor candidates on doesvm | None: no 17ef, 18d1 or 05c6 entry |

The captured Android and doesvm fields match the earlier 14:09 snapshots.
This is equality at those capture instants; it does not establish continuous
state during the interval. The configured gadget identity is not evidence
that a host enumerated it. The maximum_speed strings remain controller
capability metadata, not negotiated link speeds.

## What the result supports

A usable USB data connection from this owner tablet to doesvm is **still not
demonstrated by these two endpoint snapshots**. No fastboot or recovery
transaction was attempted, and this observation supplies no native-Linux boot
or device-pass evidence.

The captures do not determine whether a cable is plugged in, whether it is a
data cable, whether it is damaged, or which other computer may be connected.
The doesvm inventory describes only doesvm at this instant. It cannot exclude
a connection to another host.

## Concrete next physical step

Establish one identified data path: use a cable already known to carry USB
data from the tablet's USB-C data connection to an accessible USB host port
on doesvm. If the intended connection is to another computer, identify that
host and observe its inventory instead of treating doesvm's inventory as a
statement about it.

After that physical connection is identified, attachment and matching host
enumeration remain the next evidence gate. This report does not perform that
physical action or authorize a mode switch, bootloader transition, or flash.
The existing software construction and generic-VM work are separate from this
unverified physical link.

## Capture method and unchanged boundaries

The existing [capture source](../../../scripts/research/capture_usb_transport.py)
is 3,781 bytes, SHA-256
70f7e9adc8f2acc2162510bec375ceff94710bfa7fb46da7c287a30db4336ea0.
Its complete bytes were passed to Python with -B -c. Android used the existing
su route and Termux Python; no script file was created on Android. Each process
had a 15-second timeout, and each bridge call had a 30-second limit.

The helper reads only its fixed USB metadata fields and bounded directory
sets. It does not request serial numbers, personal files, credentials, device
logs or network configuration. No USB role, configfs or sysfs control value
was written. No reboot, mode switch, bootloader, flashing, slot or power
command was issued. There was one capture per endpoint and no polling or
repeat enumeration. This new report preserves the earlier captures and their
original identities.
