# USB follow-up: the owner-to-doesvm data link is still unobserved

A fresh read at **2026-11-23 12:00:33–12:00:35 Asia/Shanghai**
(04:00:33–04:00:35 UTC) reconfirmed the earlier
[USB transport snapshot](usb-transport-readiness.md). Both bounded commands
exited 0. The complete fixed-field observations are retained in
[evidence/usb-transport-followup.json](evidence/usb-transport-followup.json).

| Surface | Actual observation |
| --- | --- |
| Android primary UDC | `a600000.dwc3`: `not attached`, current speed `UNKNOWN` |
| Android secondary UDC | `a800000.dwc3`: `not attached`, current speed `UNKNOWN` |
| Configured Android gadget | `g1` names `a600000.dwc3`, VID:PID `17ef:7e31` |
| Type-C role | Device / sink; dual-role port |
| doesvm USB inventory | 14 entries; no Lenovo `17ef`, Google `18d1` or Qualcomm `05c6` vendor candidate |
| Bootloader/recovery | Neither entered nor observed; no recovery transport demonstrated |

This establishes the state of these two surfaces at that time. It does not
identify every possible connection through another computer or claim that two
UDCs mean two physical sockets. The advertised maximum-speed strings do not
measure an active link.

The unchanged [capture helper](../../../scripts/research/capture_usb_transport.py),
SHA-256 `70f7e9adc8f2acc2162510bec375ceff94710bfa7fb46da7c287a30db4336ea0`,
read only its fixed metadata attributes. It did not read serial numbers, change
USB roles, configure a gadget, request a reboot, inspect a bootloader variable,
or write a partition. The first snapshot and its evidence remain unchanged.

## Consequence for the next owner-device experiment

The separate [owner-UDC rescue correction](first-stage-owner-udc.md) has passed
its named host checks. This new snapshot still supplies no physical USB
enumeration or recovery proof for that image. Actual entry remains a separate
gate, together with the unresolved Android-property/kernel-command-line lock
state disagreement described in [boot readiness](boot-readiness.md).

The next physical step is a data-capable USB connection from the tablet to a
port that doesvm can access, with the tablet initially remaining in Android.
A fresh host/device identification can then precede the already authorized
entry and recovery investigation. This report does not authorize or execute
an unlock, userdata erase, slot change, or flash operation, and it adds no
native-Linux hardware pass to the [acceptance ledger](acceptance.json).
