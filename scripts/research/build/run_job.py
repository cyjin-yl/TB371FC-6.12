#!/usr/bin/env python3
"""Run a build command in its visible tmux pane and retain log/exit metadata."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--work", type=Path, default=Path("/work"))
parser.add_argument("--name", required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
args = parser.parse_args()
if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.name):
    parser.error("use a simple job name")
command = args.command[1:] if args.command[:1] == ["--"] else args.command
if not command:
    parser.error("a command is required")
args.work.mkdir(parents=True, exist_ok=True)
log = args.work / (args.name + ".log")
if log.exists():
    parser.error("job log already exists; use a new job name")
started = time.monotonic()
record = {"command": command, "start_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
with log.open("x") as output:
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    for line in process.stdout:
        output.write(line)
        output.flush()
        sys.stdout.write(line)
        sys.stdout.flush()
    record["exit_code"] = process.wait()
record["elapsed_seconds"] = time.monotonic() - started
(args.work / (args.name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
raise SystemExit(record["exit_code"])
