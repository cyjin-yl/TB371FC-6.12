#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise actual patched C function bodies with fault-injected kernel APIs.

This is an offline software regression, not an input simulator or a tablet test.
The test code is extracted from the prepared source, never reimplemented in
Python. API stubs expose ordering, state, error propagation and allocation bugs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def extract(text, name):
    # Match a complete definition, then count braces outside comments/strings.
    match = re.search(r"(?m)^(?:static\s+)?(?:inline\s+)?[\w *]+\b" +
                      re.escape(name) + r"\([^;{}]*\)\s*\{", text)
    if not match:
        raise ValueError("function definition not found: " + name)
    start = match.start()
    pos = text.index("{", match.start())
    depth = 0
    token = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[{}]', re.S)
    for item in token.finditer(text, pos):
        if item[0] == "{":
            depth += 1
        elif item[0] == "}":
            depth -= 1
            if depth == 0:
                return text[start:item.end()] + "\n"
    raise ValueError("unclosed function: " + name)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cc", default="cc")
    args = p.parse_args()
    if args.output.exists() or args.output.is_symlink():
        raise SystemExit("retain previous regression output; choose a fresh --output")
    args.output.mkdir(parents=True)
    paths = {"driver": args.source / "drivers/input/touchscreen/nt36523/nt36xxx.c",
             "firmware": args.source / "drivers/input/touchscreen/nt36523/nt36xxx_fw_update.c"}
    texts = {name: path.read_text() for name, path in paths.items()}
    groups = {
        "driver": ("nvt_irq_enable", "nvt_irq_set_wake", "nvt_parse_phys_size",
                   "nvt_set_abs_resolution", "nvt_ts_suspend", "nvt_ts_resume"),
        "firmware": ("update_firmware_release", "nvt_update_firmware"),
    }
    bodies = {name: "\n".join(extract(texts[name], fn) for fn in names)
              for name, names in groups.items()}
    harness = (Path(__file__).with_name("regression_harness.c")).read_text()
    for name, body in bodies.items():
        marker = "/* INSERT_ACTUAL_" + name.upper() + "_FUNCTIONS */"
        if harness.count(marker) != 1:
            raise SystemExit("missing/duplicate harness insertion marker")
        harness = harness.replace(marker, body)
    out_c = args.output / "actual-input-regression.c"
    out_c.write_text(harness)
    executable = args.output / "actual-input-regression"
    compile_result = subprocess.run([args.cc, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra",
                                     "-Werror", "-Wno-unused-parameter", str(out_c), "-o", str(executable)],
                                    capture_output=True, text=True, timeout=60)
    (args.output / "compile.log").write_text(compile_result.stdout + compile_result.stderr)
    result = {"scope": "host C API fault injection; no device execution",
              "source_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()},
              "functions": groups, "compile_exit": compile_result.returncode,
              "generated_c_sha256": hashlib.sha256(out_c.read_bytes()).hexdigest(),
              "physical_device_tested": False}
    if compile_result.returncode:
        print(compile_result.stderr)
    else:
        execution = subprocess.run([str(executable)], capture_output=True, text=True, timeout=15)
        (args.output / "run.log").write_text(execution.stdout + execution.stderr)
        result["run_exit"] = execution.returncode
        result["cases"] = [line.removeprefix("PASS ") for line in execution.stdout.splitlines() if line.startswith("PASS ")]
        print(execution.stdout, end="")
        print(execution.stderr, end="")
    (args.output / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    raise SystemExit(compile_result.returncode or result.get("run_exit", 1))


if __name__ == "__main__":
    main()
