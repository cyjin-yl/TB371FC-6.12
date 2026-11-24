#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Correlate a stable resource capture with the exact pre-inspected live FDT."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from android_memory import compare, sha256


def load(path):
    with path.open("rb") as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("evidence JSON exceeds bound")
    return raw, json.loads(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-dt", type=Path, required=True)
    parser.add_argument("--memory-observation", type=Path, required=True)
    args = parser.parse_args()
    dt_raw, live = load(args.live_dt)
    memory_raw, observation = load(args.memory_observation)
    result = compare(live, observation)
    result["inputs"] = {"live_dt_sha256": sha256(dt_raw), "memory_observation_sha256": sha256(memory_raw)}
    result["source_sha256"] = sha256(Path(__file__).read_bytes())
    result["parser_sha256"] = sha256(Path(__file__).with_name("android_memory.py").read_bytes())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
