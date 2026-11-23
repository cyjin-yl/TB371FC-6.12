# USB transport recheck at 17:36 Shanghai

The unchanged bounded helper ran once per endpoint at **2026-11-23
09:36:24.304084–09:36:25.154071 UTC** (17:36:24–25 Asia/Shanghai). Both
commands exited zero with empty standard error. The complete
[original capture record](evidence/usb-transport-recheck-20261123T093624Z.json) retains each exact
returned bridge/stdout/stderr string, command, output identity and parsed
observation. The [07:46 UTC capture](usb-transport-recheck-20261123T074657Z.md)
remains unchanged.

| Surface | Actual observation |
| --- | --- |
| Android a600000.dwc3 | `not attached`; negotiated speed `UNKNOWN` |
| Android a800000.dwc3 | `not attached`; negotiated speed `UNKNOWN` |
| Configured Android g1 | UDC `a600000.dwc3`, configured `17ef:7e31` |
| doesvm USB inventory | 14 entries including root hubs |
| doesvm candidate vendors | No `17ef`, `18d1` or `05c6` entry |

The bounded capture fields equal the previous snapshots. This only compares
the observed instants. It does not establish continuous state, a defective
cable, whether a cable is physically present, or another host's inventory.
Controller maximum-speed fields remain capability metadata; a configured
gadget identity remains distinct from successful host enumeration.

A usable data link from this tablet to doesvm is still **unverified**. The next
physical action is to connect a known data-capable cable between those two
endpoints. If the intended USB host is another computer, identify that host
and inspect its inventory. No owner Linux boot or hardware acceptance result
was produced. R5 kernel compilation and the independent distribution-system
preparation continue separately from this physical-link gap.

The [capture helper](../../../scripts/research/capture_usb_transport.py) is
unchanged: 3,781 bytes, SHA-256
`70f7e9adc8f2acc2162510bec375ceff94710bfa7fb46da7c287a30db4336ea0`.
Each interpreter used `-B -c`, a 15-second process timeout and a 30-second
bridge limit. No new Android script file, serial-number read, role/configfs
write, reboot, bootloader transition, flash, slot change or power-control
operation was performed. This was one capture per endpoint, with no repeated
enumeration or polling loop.
