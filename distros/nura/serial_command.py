#!/usr/bin/env python3
"""Run one logged command over the private ARM build VM's serial socket."""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import socket
import sys
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", type=pathlib.Path, required=True)
    parser.add_argument("--record", type=pathlib.Path, required=True)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--login-root", action="store_true")
    parser.add_argument("--interrupt", action="store_true",
                        help="Interrupt the previous foreground guest command before waiting for its shell")
    parser.add_argument("--command", required=True)
    args = parser.parse_args()
    if args.record.exists() or args.record.with_suffix(".serial.log").exists():
        parser.error("Use a new record path for every attempt")
    args.record.parent.mkdir(parents=True, exist_ok=True)
    log_path = args.record.with_suffix(".serial.log")
    started = time.monotonic()
    record = {
        "start_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "transport": "Private QEMU serial Unix socket",
        "socket": str(args.socket),
        "guest_command": args.command,
        "guest_login": "root" if args.login_root else None,
        "interrupt_previous_guest_command": args.interrupt,
    }
    buffer = b""
    log = log_path.open("xb")
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

    def wait_for(pattern):
        nonlocal buffer
        regex = re.compile(pattern)
        while True:
            match = regex.search(buffer)
            if match:
                buffer = buffer[match.end():]
                return match
            if time.monotonic() - started > args.timeout:
                raise TimeoutError("Timed out waiting for the ARM guest")
            try:
                data = connection.recv(65536)
            except socket.timeout:
                continue
            if not data:
                raise EOFError("ARM guest serial connection closed")
            log.write(data)
            log.flush()
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            buffer += data
            if args.login_root and b"Launching initramfs emergency recovery shell" in buffer:
                raise RuntimeError("ARM guest entered its initramfs emergency shell before login")
            if len(buffer) > 2 * 1024 * 1024:
                buffer = buffer[-1024 * 1024:]

    try:
        connection.settimeout(1)
        connection.connect(str(args.socket))
        if args.interrupt:
            connection.sendall(b"\x03\n")
        elif args.login_root:
            wait_for(rb"login:\s*")
            connection.sendall(b"root\n")
        else:
            connection.sendall(b"\n")
        wait_for(rb"(?:^|[\r\n])[^\r\n]*# ")
        marker = "__NURA_DONE_" + uuid.uuid4().hex + "__"
        command = (
            "( " + args.command + " ); nura_status=$?; "
            + "printf '\\n" + marker + ":%s\\n' \"$nura_status\"\n"
        )
        connection.sendall(command.encode())
        match = wait_for(re.escape(marker.encode()) + rb":([0-9]+)")
        record["guest_exit_code"] = int(match.group(1))
        returncode = record["guest_exit_code"]
    except Exception as error:
        record["error"] = str(error)
        returncode = 1
    finally:
        connection.close()
        log.close()
        record["elapsed_seconds"] = time.monotonic() - started
        record["serial_log"] = str(log_path)
        record["serial_log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
        args.record.write_text(json.dumps(record, indent=2) + "\n")
    print("\n" + json.dumps(record, indent=2), flush=True)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
