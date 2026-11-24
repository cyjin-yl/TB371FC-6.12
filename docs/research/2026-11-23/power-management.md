# Android reference evidence for power management

Date: 2026-11-23 (Asia/Shanghai). Source audit baseline:
`d157b92721fbeeab823f56a677b3593babf3afe6`.

This note records questions that can be answered using the running TB371FC
Android system and explains how those answers relate to the existing Linux
experiments. Source inspection, Android observations, and a successful Linux
hardware test are separate evidence classes. No charger, regulator, Type-C, or
suspend policy is changed by the reference collection.

## Observed on this tablet

The source is [android-stock.json](evidence/android-stock.json), captured from
Android kernel `4.19.157-perf+` beginning at `2026-11-22T20:30:07.299342+00:00`
(2026-11-23 04:30 in Asia/Shanghai). Attributes were read sequentially; this is
not an atomic sample. [power-summary.json](evidence/power-summary.json) retains
the relevant raw values and the source-file hash.

### USB labels do not establish an active PD contract

| Interface / attribute | Observed value |
| --- | --- |
| `power_supply/usb/type` | `USB_PD` |
| `typec/port0/power_operation_mode` | `usb_power_delivery` |
| `power_supply/usb/real_type` | `USB_HVDCP_3` |
| `power_supply/usb/pd_active` | `0` |
| `power_supply/usb/pd_current_max` | `-22` |
| `power_supply/usb/voltage_now` | `7137324` microvolts |
| `power_supply/usb/typec_cc_orientation` | `2` |
| `typec/port0/power_role` | `source [sink]` |
| `typec/port0/data_role` | `host [device]` |

The driver's runtime fields identify HVDCP 3 with PD inactive in this sample.
The two abstract PD labels therefore cannot be used as evidence of successful
USB PD negotiation. `pd_current_max=-22` is an invalid/error-like value, not
a physical negative-current measurement; its exact meaning needs the matched
stock driver's getter. Preserve the raw value rather than silently converting
it to a current. A later protocol comparison must capture attachment and
negotiation with the actual power source; this snapshot cannot determine all
capabilities of either the tablet or that source.

### Battery telemetry is a baseline, not an efficiency result

The battery class reports `Charging`, `Good`, capacity 28%, temperature 341
(34.1 degrees C), voltage `3789000` microvolts and current `426000` microamps.
The BMS class agrees on those numeric fields. The positive current together
with `Charging` is a useful stock-driver observation, but a single sample
does not establish its sign convention across all states. In particular, do
not apply the earlier mainline MM8013 negative-for-charging convention to it.

`charge_counter` reports only `90`, while `charge_full` and
`charge_full_design` both report `10200000`. Do not treat that counter as an
already validated standard coulomb-count reading, derive battery health from
the equal design/full values, or infer charger efficiency from these fields.
Their vendor-specific implementation and time evolution need checking.

The live device tree confirms `mitsumi,mm8013c06` at I2C address `0x55` and
`qcom,qpnp-smb5` under PM8150B. SMB5's `qcom,chg-control-gpio` resolves to
PM8150 GPIO10, and `qcom,wd-bark-time-secs` is 16. `lenovo,jeita_enable` is 1;
both regular and PD thermal-mitigation arrays contain 16 entries. These are
configuration facts, not evidence that a new mainline driver reproduces all
vendor charging and thermal policies. The capture does not resolve every
battery-profile or ADC phandle yet.

### Existing Android policy already limits CPU frequencies

All three cpufreq policies use `schedutil`. Values below are kHz.

| CPUs | Hardware-reported min/max | Current policy min/max | Current sample |
| --- | --- | --- | --- |
| 0-3 | 300000 / 1804800 | 691200 / 1075200 | 1075200 |
| 4-6 | 710400 / 2419200 | 710400 / 710400 | 710400 |
| 7 | 844800 / 3187200 | 844800 / 844800 | 844800 |

This is a policy-limited stock baseline. The snapshot does not identify whether
user settings, power policy, thermal constraints or another owner imposed the
limits. A Linux performance or power comparison must record these constraints;
using the current policy maximum as the SoC's maximum would be incorrect.

Android exposes both `wfi` and `rail-pc` idle states, `freeze mem` sleep states
and `s2idle [deep]`. Historical suspend counters report 4,146 successes and
1,941 failures, including 1,685 failed-freeze entries. These are cumulative
counters from the existing Android session, not failures introduced or
reproduced by this collection. No attended suspend/resume test was performed.
They justify capturing deltas and failure stages during a later controlled
test, not attributing a current bug to a particular device or application.

Runtime-PM reports the keyboard and QCA6390 as active, with zero recorded
suspended time at those device nodes. Novatek, CTN730 and PS5169 report
`unsupported`. The latter means that these nodes do not expose supported
runtime-PM accounting; it does not prove that their vendor drivers leave the
hardware powered continuously.

### Bounded Android traces: dynamic behavior and capture quality

Two subsequent captures retain only hardware aggregates:

| Evidence | Window | Retained records | Quality |
| --- | --- | --- | --- |
| [Idle-inclusive capture](evidence/android-trace-idle-partial.json) | 8.0156 s, starting 20:35:24 UTC | 47,159 CPU-idle records, 52 CPU-frequency records, 11 GPU-frequency records and 17 KGSL state records | Ring-buffer overrun reported; partial sequence and lower-bound counts |
| [Lower-volume capture](evidence/android-trace-summary.json) | 8.0120 s, starting 20:36:39 UTC | 196 CPU-frequency records, 12 GPU-frequency records and 18 KGSL state records | No reported per-CPU overrun, commit overrun or dropped events; zero unparsed lines |

The lower-volume profile intentionally excludes `power:cpu_idle`. Its empty
idle-count map must not be read as absence of idle transitions. The partial
capture shows why the exclusion matters: CPU-idle transitions can fill these
buffers quickly. State `4294967295` is the idle-exit marker, not another
hardware idle state. Neither capture establishes a complete time-weighted
idle-residency distribution.

In the lower-volume capture, observed CPU-frequency events reached 1,804,800
kHz on CPUs 0-3, 2,054,400 kHz on CPUs 4-6 and 2,361,600 kHz on CPU7. These
exceed the policy maxima in the earlier static snapshot. The constraints or
workload changed between captures; the earlier snapshot cannot be used as a
permanent frequency ceiling. The collected data does not identify the owner
of that change. These are event-reported frequencies, not an independent
hardware clock measurement. Counts represent trace records; a shared-policy
transition may produce records for multiple CPUs.

KGSL reported six `ACTIVE`, six `AWARE` and six `SLUMBER` transitions in the
lower-volume capture. This confirms that those power-state transitions occur
in the existing Android workload. It does not measure time spent in each
state or quantify the savings from slumber. No suspend, device-PM callback or
DRM-vblank records were observed in that window, although those events were
enabled. That does not establish unsupported suspend, a non-updating screen,
or a zero display refresh rate.

The lower-volume power samples retained `USB_HVDCP_3`, `pd_active=0` and
`Charging`. Capacity was 29%, temperature 333, and the reported battery current
was 426,000-427,000 microamps. The later capacity is consistent with continued
charging since the earlier 28% snapshot, but is not a calibrated charging-rate
or efficiency result. No workload, brightness, refresh rate, charger or input
policy change was requested by either capture.

Both artifacts report unchanged global tracing settings, removal of the
private trace instance and no cleanup errors. The partial artifact is kept
explicitly as partial evidence; it is not substituted for the loss-free
lower-volume observation.

## Separate the control paths

| Path | Existing implementation | What it establishes | What it does not establish |
| --- | --- | --- | --- |
| Battery measurement | MM8013 fuel gauge on QUPv3 SE3 / I2C address `0x55` | Capacity, temperature, voltage and current can be exposed to userspace | Charging policy, a PD contract, input-current safety or system suspend |
| Capacity-based charging hold | R189 `tb371fc-chglimit` | Changes the SMB5 charging-enable command using gauge capacity and thresholds | A complete charger driver, Type-C ownership or negotiated input power |
| Legacy sink recovery | R231 charge keepalive | Re-arms sink attachment and services the inherited charger watchdog | Robust replug handling, a complete charger driver or working TCPM |
| PD experiment | R235/R236/R237 with the R241 TCPM/PMIC sources | Contains a guarded watchdog service, bounded input-current callback and diagnostics | A successful PD hardware result or an installable stable profile |
| System low-power states | CPU idle/frequency, runtime PM and platform suspend | Requires independent observation and acceptance | Cannot be inferred from a battery icon or a blank display |

References: [R184 gauge bring-up](../../../scripts/prepare-r184-battery-dt.sh),
[R189 limiter](../../../scripts/r189-chglimit/tb371fc-chglimit.c),
[R231 service](../../../scripts/r231-charge-keepalive/r231-charge-keepalive.c),
and [community handoff](../../../experimental/community-handoff/README.md).

## Documentation corrections supported by the existing source

### PWR-01: label the fuel-gauge failure by kernel and experiment

The fuel-gauge row in [HARDWARE_MATRIX.md](../../HARDWARE_MATRIX.md) preserves an
early 4.19.325 diagnostic failure (`exfg not found`, invalid SOC). That is useful
history, but it must not be read as the status of every later Linux profile.
The R184 script enables the gauge's I2C controller, frees GPIO119/120 from the
temporary reserved range, and builds the MM8013 module. The later
[battery service](../../../scripts/r184-config/tb371fc-battery.service) says that
R187 and later kernels have the gauge built in. The current README reports
working battery telemetry.

Keep the early failure as historical evidence and identify the exact booted
kernel/profile for every new gauge result. An Android `battery` or `bms` class
name is not the expected mainline class name: R189, R231 and R235 explicitly
look up a power supply named `mm8013`. Matching numerical data alone does not
prove that these helpers can find the supply on another kernel.

### PWR-02: R189 assumes exclusive charging-command ownership

R189 changes SMB5 `CHARGING_ENABLE_CMD` (`0x1042`, bit 0) every 60 seconds as
needed, using a stop/start hysteresis. Its source comment assumes that no Linux
charger driver is bound. The implementation does not enforce a generic
charger-owner arbitration contract. It also re-enables charging when it
believes it previously held charging and the gauge becomes unreadable, the
limiter is disabled, the module unloads, or the system shuts down.

This is a compatibility helper for its documented profile. A future complete
charger driver must own this policy, or expose a supported interface for the
limiter; simply retaining both would allow competing writes. The helper's
charge hold must also not be described as proof of electrical battery bypass
or zero battery current without a current measurement.

### PWR-03: R231 and TCPM cannot be stacked

R231 performs two kinds of writes: it sequences Type-C mode through disable
and sink-only at `0x1544`, and it writes the watchdog pet command at `0x1643`.
It checks for a bound Type-C driver and guard failures stop watchdog servicing.
The successful legacy charging observation does not cover automatic recovery
after every unplug or reboot; the handoff explicitly records service restarts
being necessary on some attempts.

R235 is a different design: it requires an explicitly marked DT and a bound
sink-only TCPM owner and only services the watchdog after its checks. The
R237/R238 integration masks R231 before loading TCPM. This distinction is a
control-ownership requirement, not an optional packaging preference.

References: [R231](../../../scripts/r231-charge-keepalive/r231-charge-keepalive.c),
[R235](../../../scripts/r235-watchdog-only/r235-watchdog-only.c), and
[manual R238 probe](../../../scripts/r237-pd-integration/probe-r238.sh).

### PWR-04: current limits and supply voltages are profile constraints

The [R236 policy](../../../scripts/r236-current-limit/policy.h) accepts only
5 V requests and clamps the current to the smaller of the request, inherited
cap and 1.5 A, rounded downward in 50 mA units. Its
[callback](../../../scripts/r236-current-limit/callback.inc) suspends input
before programming the limit, checks the register state, and resumes only its
own suspension. It is not a general fast-charge implementation.

The PD PHY's L2A supply is explicitly `3072000` microvolts in the board DT.
The label `vreg_l2a_3p1` is a name, not permission to round that setting to
3.1 V. [R237](../../../scripts/r237-pd-integration/prepare-regulator.py) adds the
rail only to a gated copy of the existing regulator provider. Two regulator
providers must not manage the same hardware concurrently. An Android DT value
confirms a software constraint; it is not an analog voltage measurement.

### PWR-05: the R240 reset cause remains open

The handoff reports a first R240 message with raw size 21 (22 bytes including
the encoded length adjustment), successful read and successful buffer release.
A partner hard reset followed about 29 ms later. The later RX-disable event
occurred after that reset; ordering alone does not make it the initiating bug.

The [R240 receiver](../../../scripts/r240-rx-cleanup/receive.inc) validates the
received length and attempts buffer release on every exit path. The
[R241 TCPM instrumentation](../../../scripts/r241-tcpm-trace/prepare.py) adds
header, message count, TCPM state, attached flag, data/power roles and SOP type
before the existing `port->attached` guard. R241 was built but not booted.
Attachment timing is a testable hypothesis, not an established explanation.

Android steady-state power-supply fields cannot reconstruct that failed
mainline negotiation. Answering it requires a timestamped mainline trial
covering port attachment, first RX, its TCPM processing, TX completion and the
partner reset. A USB PD analyzer or existing vendor event logs can supply an
independent timeline later. Do not shorten debounce or suppress resets based
only on the current hypothesis.

## Android read-only collection contract

The collector should record missing attributes as unavailable, not as zero.
Every snapshot needs a timestamp and the running kernel release. No serial
number, network profile, app wake lock, process name, full kernel command line,
or general-purpose register dump belongs in the published evidence.

### Power supply attributes

Read only these names, where present, under
`/sys/class/power_supply/{battery,bms,usb,main,dc,charge_pump_master,pc_port}`:

```text
status health present online type real_type usb_type
capacity temp current_now voltage_now current_max voltage_max
voltage_max_design charge_counter charge_full charge_full_design cycle_count
input_current_limit input_current_limited
constant_charge_current_max constant_charge_voltage_max
typec_mode typec_power_role typec_cc_orientation
pd_active pd_current_max pd_voltage_min pd_voltage_max
```

Keep the original unit-bearing field names and values. Do not assume that
Android's battery-current sign convention matches the standalone mainline
MM8013 driver. The earlier author's mainline result used negative current
for charging; verify the sign on this tablet against status and a sustained
charge-counter/capacity trend before deriving power. Battery current is net
battery current, not USB input current. Multiplying battery voltage by battery
current does not measure the charger's total power.

The USB `current_max`/PD fields report policy or negotiation state and may not
be ADC measurements. Charging is supported by a consistent combination of
input state, gauge current and an increasing stored-charge trend, not by a
single `online=1` value or desktop icon.

### Type-C, regulators and topology

Read exposed Type-C class attributes `power_role`, `data_role`, `port_type`,
`power_operation_mode` and `orientation`, or the Android dual-role attributes
`mode`, `power_role`, `data_role`, `supported_modes`. An absent class is not
evidence that the controller is absent; Android may export another interface.

For the device tree, retain the gauge's compatible/address, charger and Type-C
compatible values, relevant supply phandles, battery profile/thermal mitigation
properties and their resolved provider paths. These explain the dependency
graph without reading PMIC FIFOs, acknowledgment registers or unrelated buses.
Reading hardware registers through a newly loaded module is outside this
passive capture contract.

### CPU and device low-power state

Capture each cpufreq policy's related CPUs, governor, current/minimum/maximum
frequency and available frequency range. For each exposed CPU-idle state,
capture name, latency, residency, usage, time and disable status. Use two
time-separated snapshots to obtain counter deltas; a lifetime total does not
describe the measurement window.

For already identified hardware devices, read runtime-PM `runtime_status`,
`runtime_active_time`, `runtime_suspended_time`, `control` and
`autosuspend_delay_ms`. A missing or unsupported runtime-PM counter must stay
missing/unsupported. It does not justify enabling autosuspend experimentally.

Read `/sys/power/state`, `mem_sleep` and exposed suspend statistics without
writing them. Do not include an ordinary read of `/sys/power/wakeup_count` in
this collector: it is part of the suspend synchronization protocol and can
block while wakeup events remain in progress. An initial acquisition blocked
in `pm_get_wakeup_count`; that reader was stopped and the final collector
excludes the attribute. Other individual reads are bounded to 750 ms by the
[collector](../../../scripts/research/collect_android_hardware.py).

Display blanking, CPU idle and system suspend are different events. A brief
screen-on observation with no suspend events neither proves nor disproves
suspend support.

### Bounded tracing

The lower-volume profile enables `power:cpu_frequency`, `power:gpu_frequency`,
`power:suspend_resume`, `power:device_pm_callback_start`,
`power:device_pm_callback_end`, `kgsl:kgsl_pwr_set_state` and
`drm:drm_vblank_event`. `power:cpu_idle` belongs in a separate, explicitly
requested higher-volume profile. Retain only event-specific hardware fields
and monotonic timing; strip task names and PIDs and publish aggregate counts
or durations. An isolated trace instance and bounded buffer avoid disturbing
an existing tracing session. Record duration, event availability and dropped
events so an empty or incomplete capture remains interpretable. An unknown
loss status must remain unknown if complete buffer statistics are unavailable.

The TCPM debugfs log is consumptive. Do not add a competing reader to an
existing experiment. Its dedicated
[collector](../../../scripts/r241-tcpm-trace/collect-tcpm.sh) is intended to be
the sole consumer in the matching mainline harness. Ordinary Android reference
capture does not need it.

## Experiments the evidence should enable next

| Question | Evidence needed | A justified next change |
| --- | --- | --- |
| Why is idle power high? | Stable brightness/refresh/workload, CPU-idle and frequency deltas, GPU state and net battery-power samples | Target the subsystem with demonstrated activity; keep workload and thermal state comparable |
| Are display rails retained unnecessarily? | Android panel lifecycle, regulator consumers and clock sequencing compared with the mainline path | Replace specific inherited/always-on dependencies once their consumers and resume order are understood |
| Does a charger reconnect recover? | Timestamped cable attachment, Type-C role, power-supply and gauge trends | Implement event-driven recovery with a single Type-C/charger owner |
| Why does PD reset? | First RX header and TCPM attached/state timeline, transmit completion and partner reset | Correct the observed failed transition, preserving protocol timing and protections |
| Does suspend work? | An attended suspend/resume cycle followed by input, network, panel and charging checks | Fix the first failed device dependency, then repeat the same acceptance cycle |

This reference capture is a baseline for those experiments. It does not
establish reduced energy consumption, successful mainline PD, a safe charging
current increase, or working system suspend.
