#!/usr/bin/env python3
"""Reviewed PR17 core, unchanged, with provenance and self CPU/wall limits.

Invoke a fresh unprivileged interpreter using -I -S -B and this file's bytes
as stdin. This wrapper is not a device execution receipt until that command
really runs and its tool-reported exit/stdout/stderr are retained.
"""
import datetime
import hashlib
import json
import os
import resource
import signal
import subprocess
import sys
import time

SOURCE = b'#!/usr/bin/env python3\n# SPDX-License-Identifier: GPL-2.0-only\n"""Short, single-process Android SYS-04 correctness smoke; not a benchmark."""\nimport hashlib\nimport json\nimport os\nimport re\nimport signal\nimport subprocess\nimport sys\nimport time\n\nSIZE = 2 * 1024 * 1024\nEXPECTED = "91d3beb88a9b2f778a6c44a1c53b63d3c79931845a9aef84b3fb414610bd1938"\nREVERSED = "5d0930c72a53828aec014fbecdaf87dfc6f71723521bc2a723a515bfc52353c5"\n\ndef deadline(*_):\n    raise TimeoutError("12-second smoke deadline")\n\ndef read_conditions():\n    # Only three allowlisted read-only values; never read user files.\n    p = subprocess.run(["su", "-c", "grep \'^MemAvailable:\' /proc/meminfo; cat /sys/class/power_supply/battery/temp; cat /sys/class/power_supply/battery/capacity"],\n                       capture_output=True, text=True, timeout=3, check=True)\n    match = re.fullmatch(r"MemAvailable:\\s+(\\d+) kB\\s*\\n(-?\\d+)\\s*\\n(\\d+)\\s*", p.stdout)\n    if not match:\n        raise ValueError("unexpected preflight values")\n    return {"available_bytes": int(match[1])*1024, "battery_temp_deci_c": int(match[2]), "battery_percent": int(match[3])}\n\ndef run():\n    if os.geteuid() == 0:\n        raise ValueError("workload must be unprivileged")\n    before = read_conditions()\n    if before["available_bytes"] < 128*1024*1024 or not 0 <= before["battery_temp_deci_c"] < 380 or before["battery_percent"] < 20:\n        raise ValueError("resource/temperature preflight refused")\n    allowed = sorted(os.sched_getaffinity(0))\n    if not allowed or len(allowed) > 8 or any(c not in range(8) for c in allowed):\n        raise ValueError("unexpected process affinity")\n    started = time.monotonic()\n    fixture = bytes(range(256)) * (SIZE//256)\n    rows = []\n    try:\n        for cpu in allowed:\n            os.sched_setaffinity(0, {cpu})\n            if os.sched_getaffinity(0) != {cpu}:\n                raise ValueError("affinity readback mismatch")\n            for trial in range(3):\n                copy = bytearray(fixture)\n                first = hashlib.sha256(copy).hexdigest()\n                copy.reverse()\n                second = hashlib.sha256(copy).hexdigest()\n                if first != EXPECTED or second != REVERSED:\n                    raise ValueError("deterministic checksum mismatch")\n                rows.append({"cpu": cpu, "trial": trial+1, "original_sha256": first, "reversed_sha256": second})\n                del copy\n    finally:\n        os.sched_setaffinity(0, set(allowed))\n    if os.sched_getaffinity(0) != set(allowed):\n        raise ValueError("affinity restoration failed")\n    after = read_conditions()\n    return {"schema":"tb371fc-android-cpu-memory-smoke-v1","kernel_release":os.uname().release,\n            "python":sys.version.split()[0],"conditions_before":before,"conditions_after":after,\n            "allowed_cpus":allowed,"unavailable_cpus":sorted(set(range(8))-set(allowed)),\n            "trials":rows,"fixture_bytes":SIZE,"live_fixture_and_copy_bytes":2*SIZE,\n            "elapsed_seconds":round(time.monotonic()-started,6),"affinity_restored":True,\n            "all_requested_checks_passed":True,"native_linux_passes_added":0,\n            "scope":"short sequential Android userspace checksum smoke; not sustained, parallel, thermal or throughput qualification"}\n\nif __name__ == "__main__":\n    signal.signal(signal.SIGALRM, deadline)\n    signal.alarm(12)\n    try:\n        print(json.dumps(run(),sort_keys=True))\n    finally:\n        signal.alarm(0)\n'
EXPECTED_SOURCE_SHA256 = '771f751d9e7bb7b0712186d242cb17dfa7853511204acf8d20b90fcbe079460e'
CAPTURE_NONCE = '38395c9c6a26431736df7269c48c8fc6'


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def hard_wall_deadline(*_):
    # A hard deadline must not wait for subprocess context-manager cleanup.
    # This exits only this fresh probe process; its self affinity disappears.
    # There is intentionally no success JSON on this path. The caller must
    # retain the actual exit code (124), not infer success from partial text.
    os._exit(124)


def cpu_soft_deadline(*_):
    raise TimeoutError('five-second CPU soft limit')


def main():
    started = time.monotonic()
    report = {
        'schema': 'tb371fc-android-cpu-memory-bound-run-v1',
        'capture_nonce': CAPTURE_NONCE,
        'capture_utc': utc(),
        'source_revision': 'c461ca2f1b9fd4a6758011e2216ef2855d1142ef',
        'source_sha256': hashlib.sha256(SOURCE).hexdigest(),
        'source_bytes': len(SOURCE),
        'uid': os.getuid(), 'euid': os.geteuid(),
        'gid': os.getgid(), 'egid': os.getegid(),
        'pid': os.getpid(),
        'kernel_release': os.uname().release,
        'machine': os.uname().machine,
        'python': sys.version.split()[0],
        'python_isolated': bool(sys.flags.isolated),
        'python_site_disabled': bool(sys.flags.no_site),
        'python_bytecode_disabled': bool(sys.dont_write_bytecode),
        'source_main_block_executed': False,
        'entrypoint': 'unchanged reviewed module run() function',
        'wall_hard_seconds': 12,
        'workload_fixture_bytes': 2097152,
        'workload_copy_bytes': 2097152,
        'workload_max_cpus': 8,
        'workload_trials_per_allowed_cpu': 3,
        'whole_process_rss_cap_claimed': False,
        'rlimit_as_changed': False,
        'device_global_affinity_or_cgroup_changes': False,
        'native_linux_passes_added': 0,
        'completed': False,
    }
    result_code = 1
    signal.signal(signal.SIGALRM, hard_wall_deadline)
    signal.signal(signal.SIGXCPU, cpu_soft_deadline)
    signal.alarm(12)
    try:
        if report['source_sha256'] != EXPECTED_SOURCE_SHA256:
            raise ValueError('reviewed source SHA-256 mismatch')
        if report['euid'] == 0:
            raise ValueError('fresh workload process must be unprivileged')
        if not (report['python_isolated'] and report['python_site_disabled'] and
                report['python_bytecode_disabled']):
            raise ValueError('invoke the fresh interpreter with -I -S -B')
        if report['machine'] != 'aarch64' or report['kernel_release'] != '4.19.157-perf+':
            raise ValueError('this wrapper is scoped to the observed Android kernel')
        previous = resource.getrlimit(resource.RLIMIT_CPU)
        report['rlimit_cpu_before'] = list(previous)
        if ((previous[0] != resource.RLIM_INFINITY and previous[0] < 5) or
                (previous[1] != resource.RLIM_INFINITY and previous[1] < 6)):
            raise ValueError('existing CPU limit is stricter; do not relax it')
        resource.setrlimit(resource.RLIMIT_CPU, (5, 6))
        report['rlimit_cpu_effective'] = list(resource.getrlimit(resource.RLIMIT_CPU))
        if report['rlimit_cpu_effective'] != [5, 6]:
            raise ValueError('CPU limit readback mismatch')
        report['rlimit_as_observed'] = list(resource.getrlimit(resource.RLIMIT_AS))
        prop = subprocess.run(['/system/bin/getprop', 'ro.product.model'],
                              capture_output=True, text=True, timeout=2, check=True)
        if len(prop.stdout) > 128 or prop.stderr:
            raise ValueError('unexpected model property result')
        report['model'] = prop.stdout.strip()
        if report['model'] != 'TB371FC':
            raise ValueError('unexpected device model')
        report['affinity_before'] = sorted(os.sched_getaffinity(0))
        namespace = {'__name__': 'reviewed_android_smoke',
                     '__file__': '<sha256:' + EXPECTED_SOURCE_SHA256 + '>'}
        exec(compile(SOURCE, namespace['__file__'], 'exec'), namespace)
        # The reviewed core's try/finally restores its own affinity. Its
        # __main__ block is skipped so it cannot replace the hard wall guard.
        report['result'] = namespace['run']()
        report['affinity_after'] = sorted(os.sched_getaffinity(0))
        if report['affinity_after'] != report['affinity_before']:
            raise ValueError('outer affinity readback mismatch')
        if not (report['result']['all_requested_checks_passed'] and
                report['result']['affinity_restored'] and
                report['result']['native_linux_passes_added'] == 0):
            raise ValueError('reviewed core did not pass its requested checks')
        report['completed'] = True
        result_code = 0
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)[:240]}
    finally:
        report['completed_utc'] = utc()
        report['wrapper_elapsed_seconds'] = round(time.monotonic() - started, 6)
    # This is the code requested by the wrapper, not an independent receipt
    # of process termination. The RPC's actual exit code is required too.
    report['exit_code_to_return'] = result_code
    encoded = (json.dumps(report, sort_keys=True) + '\n').encode('utf8')
    if len(encoded) > 16384:
        raise ValueError('bounded report exceeds 16 KiB')
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    signal.alarm(0)
    return result_code


if __name__ == '__main__':
    raise SystemExit(main())
