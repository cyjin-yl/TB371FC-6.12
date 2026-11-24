# Bounded Android CPU and memory correctness reference

One source-bound execution on the owner's TB371FC completed **24 short
checksum trials**, three on each CPU permitted by the application's normal
affinity mask, with actual tool exit **0** and empty stderr. The workload ran
on Android kernel **4.19.157-perf+**, not the native Linux 6.12 target. It used
one 2 MiB immutable fixture and one 2 MiB mutable copy, sequentially in one
unprivileged workload process.

This adds a short Android computation reference alongside the
[passive topology and memory accounting](android-memory-topology.md).
[Native SYS-04](../2026-11-23/acceptance.md#sys-04) remains `not_run`: its
multiworker, sustained, post-suspend and final-soak requirements are not
established here. **Native Linux passes added: 0.**

## The original report and this separate attempt

The initial [Android smoke JSON](evidence/android-cpu-memory-smoke.json) is
preserved byte-for-byte. Its 24 rows and two deterministic hashes are internally
consistent, but it does not retain a command, UTC capture interval, actual tool
exit/stdout/stderr, executing UID or source/runner hash binding. Its historical
execution provenance has not been independently established. It is not used
as the verdict or receipt for the execution below.

The independently captured attempt is in
[attempt-01/source-binding.json](evidence/android-cpu-memory-bound/attempt-01/source-binding.json).
It binds the reviewed source, the exact command, the bytes actually supplied
to stdin, the reviewed runner template and the unmodified tool response.

## Observed execution

| Observation | Actual result |
| --- | --- |
| UTC interval reported inside Android | `2026-11-24T11:12:50.841685+00:00` to `2026-11-24T11:12:52.089945+00:00` |
| Wrapper monotonic elapsed time | **1.248316 seconds** |
| Core-reported monotonic interval | **1.144031 seconds** |
| Model / machine | `TB371FC` / `aarch64` |
| Kernel / Python | `4.19.157-perf+` / `3.12.11` |
| Workload UID / EUID | **10290 / 10290** |
| Actual tool exit / stderr | **0 / 0 bytes** |
| Affinity before and after | CPUs **0–7**, identical |
| Requested trials | **24**, three for each permitted CPU; every original and reversed checksum matched |
| Largest pair of live workload arrays | **4,194,304 bytes**: 2 MiB fixture plus 2 MiB copy |
| MemAvailable before / after | **2,362,114,048 / 2,357,432,320 bytes** |
| Battery readings before / after | **100% / 100%**, battery sensor **26.4°C / 26.4°C** |

The UTC values and elapsed times come from the actual Android process. The
tool response does not supply independent outer start/end timestamps. Uptime
was not sampled for this attempt. MemAvailable changes are not attributed to
the test process, and the two battery-sensor readings do not establish thermal
stability. These intervals are not throughput measurements.

## Reviewed source and limits

The [reviewed core at c461ca2](https://github.com/cyjin-yl/TB371FC-6.12/blob/c461ca2f1b9fd4a6758011e2216ef2855d1142ef/scripts/research/android_cpu_memory_smoke.py)
is exactly **3,454 bytes**, SHA-256
`771f751d9e7bb7b0712186d242cb17dfa7853511204acf8d20b90fcbe079460e`.
The runner embeds those exact bytes, loads the definitions and calls the
unchanged `run()` function. It skips the core's `__main__` block so that the
wrapper's deadline handler remains installed. It does not increase the core's
buffer sizes, CPU set or trial count.

The fresh interpreter used `-I -S -B`; the receipt reports isolated execution,
site initialization disabled and bytecode generation disabled. The wrapper
requires an unprivileged UID, the observed model and kernel, and installs a
self CPU limit of **5 seconds soft / 6 seconds hard**, confirmed by
`getrlimit`. It configures a **12-second SIGALRM** hard-exit path, and the tool
request timeout was **20,000 ms**. The successful call did not reach either
timeout; those failure paths were not exercised as additional hardware tests.

The core refuses a preflight with MemAvailable below 128 MiB, battery
temperature outside 0–37.9°C, battery charge below 20%, or an unexpected
affinity mask. It calls `sched_setaffinity(0, ...)` only for itself and restores
the original mask in `finally`; both the core and wrapper check the successful
restoration. Forced process termination ends that process's affinity setting.
It does not change a global CPU mask or cgroup policy.

The 4 MiB bound describes the two active arrays, not total interpreter/helper
RSS. `RLIMIT_AS` was observed and left unchanged; this avoids assuming that a
small virtual-address ceiling is valid for the Android runtime. The workload
mutates private memory and its own affinity. It requests no persistent output
file, partition/block-device write, hardware-register write or global power
policy change. The existing `su` helper reads only MemAvailable, battery
temperature and capacity; the wrapper also reads `ro.product.model` through
the absolute `/system/bin/getprop` path.

## Exact receipt bytes

| File | Bytes | Role |
| --- | ---: | --- |
| [reviewed-runner.py](evidence/android-cpu-memory-bound/attempt-01/reviewed-runner.py) | 9,638 | Frozen reviewed input template |
| [actual-stdin.py](evidence/android-cpu-memory-bound/attempt-01/actual-stdin.py) | 9,639 | Actual stdin, including one additional trailing LF |
| [actual-command.txt](evidence/android-cpu-memory-bound/attempt-01/actual-command.txt) | 9,735 | Recorded single quoted heredoc command, with no following command to mask exit status |
| [tool-result.json](evidence/android-cpu-memory-bound/attempt-01/tool-result.json) | 7,377 | Original tool response containing actual exit, stdout and stderr |
| [stdout.json](evidence/android-cpu-memory-bound/attempt-01/stdout.json) | 6,781 | Exact stdout bytes extracted without reformatting |
| [stderr.log](evidence/android-cpu-memory-bound/attempt-01/stderr.log) | 0 | Exact empty stderr |

The actual stdin equals the reviewed template followed by exactly one LF.
Their distinct SHA-256 values are retained; the template hash is not presented
as the actual stdin hash. Static validation also verifies that the embedded
3,454-byte core is unchanged, the nonce matches the frozen input, all 24 rows
match the expected CPU/trial order and checksums, and the tool's actual exit 0
agrees with the wrapper's requested return code. The source binding records
the byte count and SHA-256 of each raw file.

This is one bounded sequential Android reference. It does not qualify
parallel or sustained computation, physical memory coverage, thermal
stability, post-suspend correctness, reserved-memory ownership or a native
Linux hardware pass.
