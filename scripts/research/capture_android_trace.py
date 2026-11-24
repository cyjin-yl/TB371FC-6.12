#!/usr/bin/env python3
"""Capture a short, isolated trace instance and emit only hardware aggregates.

Uses an existing tracefs mount. Does not touch global trace settings, record
input events, change clocks/power policy, suspend, or issue register accesses.
The private trace instance is removed on completion or a handled exception.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

ROOT = Path("/sys/kernel/tracing")
EVENTS = ("power:cpu_frequency", "power:cpu_idle", "power:gpu_frequency",
          "power:suspend_resume", "power:device_pm_callback_start",
          "power:device_pm_callback_end", "kgsl:kgsl_pwr_set_state",
          "drm:drm_vblank_event")
LINE = re.compile(r"(?P<t>\d+\.\d+):\s+(?P<event>[\w:]+):\s*(?P<payload>.*)$")


def read(path, limit=8 * 1024 * 1024):
    def expired(signum, frame):
        raise TimeoutError("bounded trace/sysfs read")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 0.75)
    try:
        with Path(path).open() as stream:
            result = stream.read(limit + 1)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)
    if len(result) > limit:
        raise ValueError("bounded trace read exceeded")
    return result.strip()


def global_state():
    return {name: read(ROOT / name) for name in ("tracing_on", "current_tracer", "buffer_size_kb")}


def summarize_trace(text):
    """Discard task names, PIDs, raw device payloads, and addresses."""
    counts = Counter()
    frequencies = defaultdict(set)
    idle = Counter()
    gpu_states = Counter()
    vblank = defaultdict(list)
    unknown = 0
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = LINE.search(line)
        if not match:
            unknown += 1
            continue
        name = match["event"].rsplit(":", 1)[-1]
        if name not in {e.split(":")[1] for e in EVENTS}:
            unknown += 1
            continue
        counts[name] += 1
        payload = match["payload"]
        fields = dict(re.findall(r"\b([a-zA-Z_]+)=(-?[0-9]+)\b", payload))
        if name == "cpu_frequency" and "cpu_id" in fields and "state" in fields:
            frequencies[fields["cpu_id"]].add(int(fields["state"]))
        elif name == "cpu_idle" and "cpu_id" in fields and "state" in fields:
            idle["cpu" + fields["cpu_id"] + ":state=" + fields["state"]] += 1
        elif name == "kgsl_pwr_set_state":
            state = re.search(r"\bstate=(ACTIVE|NAP|SLEEP|SLUMBER|INIT|SUSPEND|AWARE|RESET)\b", payload)
            gpu_states[state[1] if state else "unclassified"] += 1
        elif name == "drm_vblank_event" and "crtc" in fields:
            vblank[fields["crtc"]].append(float(match["t"]))
    rates = {}
    for crtc, timestamps in vblank.items():
        span = max(timestamps) - min(timestamps) if timestamps else 0
        rates[crtc] = {"events": len(timestamps), "observed_span_s": span,
                       "event_rate_hz": (len(timestamps) - 1) / span if span > 0 else None,
                       "meaning": "trace event cadence; not compositor FPS or proof of panel refresh"}
    return {"event_counts": dict(sorted(counts.items())),
            "cpu_frequency_khz": {cpu: sorted(vals) for cpu, vals in sorted(frequencies.items())},
            "cpu_idle_transition_counts": dict(sorted(idle.items())),
            "gpu_state_counts": dict(gpu_states), "vblank_observations": rates,
            "unparsed_lines": unknown}


def sample_power(phase):
    result = {"monotonic_s": time.monotonic(), "phase": phase}
    for supply, attrs in (("battery", ("status", "capacity", "current_now", "voltage_now", "temp")),
                          ("usb", ("real_type", "pd_active", "voltage_now", "current_max"))):
        result[supply] = {}
        for attr in attrs:
            try:
                result[supply][attr] = read(Path("/sys/class/power_supply") / supply / attr, 512)
            except (OSError, ValueError) as exc:
                result[supply][attr] = {"unavailable": exc.__class__.__name__}
    return result


def interrupted(signum, frame):
    raise InterruptedError("bounded trace capture interrupted")


@contextmanager
def blocked_interrupts():
    """Protect instance creation until ownership is recorded for cleanup."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, (signal.SIGINT, signal.SIGTERM))
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextmanager
def cleanup_interrupts():
    """A second handled signal must not interrupt cleanup of our instance."""
    previous = {}
    with blocked_interrupts():
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous[sig] = signal.signal(sig, signal.SIG_IGN)
    try:
        yield
    finally:
        with blocked_interrupts():
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def capture(seconds, include_cpu_idle=False):
    before = None
    instance = ROOT / "instances" / ("tb371fc_research_" + str(os.getpid()) + "_" + str(time.monotonic_ns()))
    enabled = []
    result = {"schema_version": 1, "capture_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "requested_seconds": seconds,
              "conditions": "existing Android workload; no screen/refresh/charger/input changes requested",
              "samples": [], "unavailable_events": [], "instance_created": False,
              "sample_timing": "power attributes are sampled before and after tracing, never while the trace is active",
              "cpu_idle_enabled": include_cpu_idle}
    try:
        if not 1 <= seconds <= 12:
            raise ValueError("capture duration must be between 1 and 12 seconds")
        if os.geteuid() != 0:
            raise PermissionError("requires an existing root shell")
        if not (ROOT / "instances").is_dir():
            raise RuntimeError("existing tracefs instances required; global trace is never used as a fallback")
        before = global_state()
        result["global_before"] = before
        result["kernel_release"] = read("/proc/sys/kernel/osrelease")
        with blocked_interrupts():
            instance.mkdir()
            result["instance_created"] = True
        (instance / "tracing_on").write_text("0")
        (instance / "current_tracer").write_text("nop")
        (instance / "buffer_size_kb").write_text("128")
        clocks = read(instance / "trace_clock").replace("[", "").replace("]", "").split()
        if "mono" in clocks:
            (instance / "trace_clock").write_text("mono")
        (instance / "trace").write_text("")
        for event in EVENTS:
            if event == "power:cpu_idle" and not include_cpu_idle:
                continue
            category, name = event.split(":")
            control = instance / "events" / category / name / "enable"
            if not control.exists():
                result["unavailable_events"].append(event)
                continue
            control.write_text("1")
            enabled.append(control)
        result["enabled_events"] = [p.parts[-3] + ":" + p.parts[-2] for p in enabled]
        if not enabled:
            raise RuntimeError("none of the selected hardware events are available")
        result["samples"].append(sample_power("before_tracing"))
        start = time.monotonic()
        (instance / "tracing_on").write_text("1")
        # Potentially blocking sysfs reads must not extend the active window.
        # Scheduling and tracefs writes can still delay the requested deadline;
        # observed_seconds records the elapsed interval rather than assuming it.
        time.sleep(max(0, start + seconds - time.monotonic()))
        (instance / "tracing_on").write_text("0")
        result["observed_seconds"] = time.monotonic() - start
        result["samples"].append(sample_power("after_tracing"))
        result["summary"] = summarize_trace(read(instance / "trace"))
        result["per_cpu_buffer_stats"] = {}
        for stats in sorted((instance / "per_cpu").glob("cpu*/stats")):
            values = {}
            for line in read(stats).splitlines():
                key, separator, value = line.partition(":")
                if separator and re.fullmatch(r"[0-9.]+", value.strip()):
                    values[key.strip()] = value.strip()
            result["per_cpu_buffer_stats"][stats.parent.name] = values
        losses = ("overrun", "commit overrun", "dropped events")
        stats_complete = bool(result["per_cpu_buffer_stats"]) and all(
            all(name in values for name in losses)
            for values in result["per_cpu_buffer_stats"].values())
        result["buffer_loss_detected"] = (any(
            float(values[name]) > 0
            for values in result["per_cpu_buffer_stats"].values() for name in losses)
            if stats_complete else None)
        result["interpretation"] = (
            "buffer-loss status unavailable; do not assume the event stream is complete"
            if result["buffer_loss_detected"] is None else
            "partial ring-buffer sample; event counts are lower bounds"
            if result["buffer_loss_detected"] else
            "no ring-buffer loss reported; this is an uncontrolled workload sample")
    except (Exception, KeyboardInterrupt) as exc:
        # Publish the failure class and cleanup state, never a raw payload or
        # exception message that could contain device-specific identifiers.
        result["capture_error"] = type(exc).__name__
    finally:
        with cleanup_interrupts():
            cleanup_errors = []
            if result["instance_created"]:
                for control in [instance / "tracing_on"] + enabled:
                    try:
                        control.write_text("0")
                    except OSError as exc:
                        cleanup_errors.append(type(exc).__name__)
                try:
                    instance.rmdir()
                except OSError as exc:
                    cleanup_errors.append(type(exc).__name__)
                try:
                    result["instance_removed"] = not instance.exists()
                except OSError as exc:
                    result["instance_removed"] = None
                    cleanup_errors.append(type(exc).__name__)
            else:
                result["instance_removed"] = None  # No instance to remove.
            result["cleanup_errors"] = cleanup_errors
            result["global_settings_unchanged"] = None
            if before is not None:
                try:
                    result["global_after"] = global_state()
                    result["global_settings_unchanged"] = result["global_after"] == before
                except (OSError, ValueError) as exc:
                    result["global_after"] = {"unavailable": type(exc).__name__}
    result["capture_succeeded"] = ("capture_error" not in result and not result["cleanup_errors"]
                                   and result["instance_removed"] is True
                                   and result["global_settings_unchanged"] is True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--cpu-idle", action="store_true", help="include high-volume CPU idle transitions; inspect loss counters")
    parser.add_argument("--summarize", type=Path, help="offline raw trace to aggregate; no device access")
    args = parser.parse_args()
    if args.summarize:
        print(json.dumps(summarize_trace(read(args.summarize)), indent=2, sort_keys=True))
        return
    if not 1 <= args.seconds <= 12:
        parser.error("capture duration must be between 1 and 12 seconds")
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    result = capture(args.seconds, args.cpu_idle)
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["capture_succeeded"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
