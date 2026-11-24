# USB transport recheck during the tmpfs startup correction

At **13:18:28–30 Asia/Shanghai on 2026-11-23** (05:18:28–30 UTC), the
unchanged bounded [capture helper](../../../scripts/research/capture_usb_transport.py)
was executed again on the owner Android tablet and doesvm. Both commands
returned zero. The exact parsed observations are retained in
[usb-transport-recheck.json](evidence/usb-transport-recheck.json).

| Observation | Actual result |
| --- | --- |
| Android `a600000.dwc3` | `not attached`; current speed `UNKNOWN` |
| Android `a800000.dwc3` | `not attached`; current speed `UNKNOWN` |
| Type-C data role | Device selected |
| Type-C power role | Sink selected |
| doesvm USB inventory | 14 devices; no Lenovo/Google/Qualcomm vendor candidate |
| Bootloader or recovery transport | Not exercised or qualified |

The script source has SHA-256
`70f7e9adc8f2acc2162510bec375ceff94710bfa7fb46da7c287a30db4336ea0`.
It ran as source text through `python -B -c`; no new helper file was created
on Android. It reads only its fixed attribute allowlist. Serial attributes,
USB role changes, gadget reconfiguration and reboot/bootloader commands remain
outside this capture.

This independently repeats the earlier
[12:00 transport follow-up](usb-transport-followup.md), which remains frozen.
It establishes the sampled absence of an attached USB data transport, not
whether a cable is physically present, whether a particular cable can carry
data, or what another host may have enumerated.

A data-capable connection to a USB port accessible from doesvm is still
required for the next attended entry/recovery checks. Android can remain
running while that connection is established. The current result adds no
native Linux boot, recovery or peripheral acceptance pass.
