# Owner tracing capabilities and the blocked perf/kprobe route

The requested capability-only audit found that the running owner Android
kernel enables several BPF/perf facilities but **explicitly disables
`CONFIG_KPROBES`**. Its fixed
`/sys/bus/event_source/devices/kprobe/type` interface is also absent. The
proposed normal perf/kprobe attachment route therefore does not meet its
prerequisites on this running kernel. No probe was implemented or attached.

The [complete filtered evidence](evidence/android-trace-probe-capabilities.json)
records a capture at `2026-11-23T03:32:30.472369+00:00` on
`4.19.157-perf+`, the exact acquisition program and its hash. Only the six
requested configuration keys and the metadata of the one fixed interface
were inspected.

| Item | Actual observation |
| --- | --- |
| `CONFIG_BPF_SYSCALL` | `y` |
| `CONFIG_BPF_EVENTS` | `y` |
| `CONFIG_BPF_JIT` | `y` |
| `CONFIG_KPROBES` | Explicit `# CONFIG_KPROBES is not set` |
| `CONFIG_KPROBE_EVENTS` | No matching line was emitted in the captured configuration; this is retained as an absent line rather than a fabricated explicit `n` |
| `CONFIG_PERF_EVENTS` | `y` |
| `/sys/bus/event_source/devices/kprobe/type` | Absent; no type value was read |

The configuration came from the existing `/proc/config.gz`: 38,068 compressed
bytes with SHA256
`20dcd5ebdb9908d83ee68593b56fc5723bdf287905284b16d1e6753c4a34da59`;
171,764 decoded bytes with SHA256
`23d3db565be3cd6cfc07bb90541d971dc70e6a6ce3516360155b8fd15590e726`.
The complete configuration was not published. Both metadata operations used
a one-second deadline; decompression and input lengths had explicit bounds.

## What this does and does not establish

The earlier [private trace-instance capture](evidence/android-trace-summary.json)
actually used existing tracepoints. Its success does not imply that arbitrary
dynamic kprobes are compiled or available. The new observations are
consistent with that earlier result: existing tracing can work while kprobes
are unavailable.

Likewise, compiled BPF syscall, event, JIT and perf support does not demonstrate
that a particular program can load, that JIT execution is enabled at runtime,
or that a chosen attach mechanism and its privileges are available. No other
BPF program type or alternative attachment route was evaluated in this audit.
No CNSS runtime pointer, structure offset or cached board-data field was read
or inferred from these booleans.

This is separate from the [IPC endpoint finding](radio-ipc-readiness.md),
which identified `CONFIG_DEBUG_FS=n` alongside `CONFIG_IPC_LOGGING=y` and
performed zero IPC payload reads. Neither result supplies the QMI board ID
or a selected BDF filename. The earlier cached BDF descriptors and PCI
subsystem ID still cannot substitute for that runtime selection evidence.

The acquisition issued no BPF/map/perf syscall, loaded no module or BPF
program, attached no probe, created no tracing instance, mounted no debugfs,
changed no sysctl, restarted no radio and made no QMI request. It read no
arbitrary kernel memory or register. The result is an Android capability
gate, with **no owner Linux or radio-operation pass**.
