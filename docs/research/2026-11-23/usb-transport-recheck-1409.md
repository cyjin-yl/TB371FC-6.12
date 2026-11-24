# USB transport recheck at 14:09 Shanghai

The unchanged bounded capture helper was executed again while the independent
v7 software candidate was being prepared. The actual observations were at
**14:09:03–14:09:05, 2026-11-23, Asia/Shanghai**
(`06:09:03.720133–06:09:05.019569 UTC`). Both commands exited zero. The full
[record](evidence/usb-transport-recheck-1409.json) preserves both observations;
the [13:18 recheck](usb-transport-recheck.md) remains unchanged.

| Surface | Actual observation |
| --- | --- |
| Android `a600000.dwc3` | `not attached`; current speed `UNKNOWN` |
| Android `a800000.dwc3` | `not attached`; current speed `UNKNOWN` |
| Android active gadget configuration | `g1` binds `a600000.dwc3`; vendor/product `17ef:7e31` |
| doesvm USB inventory | 14 entries; no `17ef`, `18d1` or `05c6` vendor candidate |

These reads still do not establish a usable USB data or recovery path to the
tablet. They do not diagnose the physical cable, establish another host's
state, identify a fastboot device, or test recovery. The configured gadget
identity alone is not evidence of an enumerated host connection.

The existing script has SHA-256
`70f7e9adc8f2acc2162510bec375ceff94710bfa7fb46da7c287a30db4336ea0`.
It was passed as source text to Python; no new script file was written on
Android. Serial numbers were not read. No USB role/configuration was changed,
and no reboot, bootloader, flash or slot command was issued. The native-Linux
owner hardware run/pass counts remain zero. The container construction and
generic-VM work can continue independently of this physical transport gap.
