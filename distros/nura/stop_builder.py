#!/usr/bin/env python3
"""Stop only this completed experiment's QEMU and loopback media server.

Run inside the original build container after the rootfs export has succeeded.
The archived tree and all work files are retained. No guest package operation
may still be active: the successful export follows the recorded chroot stop.
"""
import datetime
import json
import os
import pathlib
import signal
import time


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    work = pathlib.Path("/work")
    project = work / "pmwork"
    record = project / "cleanup.json"
    if record.exists():
        raise SystemExit("A cleanup record already exists; inspect it before another action")
    export = json.loads((project / "guest-share/rootfs-export.json").read_text())
    if export.get("archive_exit_code") != 0:
        raise SystemExit("No successful rootfs export")
    artifact = pathlib.Path(export["artifact"]["path"])
    if not artifact.is_file() or artifact.stat().st_size != export["artifact"]["size_bytes"]:
        raise SystemExit("The recorded rootfs archive is absent or changed in size")

    http_args = ["python3", "-u", "-m", "http.server", "18083", "--bind",
                 "127.0.0.1", "--directory", "/work/pmwork/boot/alpine"]
    matches = []
    for proc in pathlib.Path("/proc").glob("[0-9]*"):
        try:
            raw = (proc / "cmdline").read_bytes()
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        argv = [part.decode() for part in raw.split(b"\0") if part]
        if not argv:
            continue
        role = None
        if argv == http_args:
            role = "loopback_verified_media_server"
        elif (pathlib.Path(argv[0]).name == "qemu-system-aarch64"
              and "/work/pmwork/boot/alpine/Image" in argv
              and any("path=/work/pmwork/console.sock," in arg
                      and "logfile=/work/pmwork/console-03.log" in arg for arg in argv)):
            role = "generic_arm_builder_vm_03"
        if role:
            matches.append({"pid": int(proc.name), "role": role, "argv": argv,
                            "raw_cmdline": raw})
    if len(matches) != 2 or len({item["role"] for item in matches}) != 2:
        raise SystemExit("Expected exactly the owned VM and media server; inspect processes")
    result = {"started_at_utc": utc(),
              "reason": "Target chroots stopped and rootfs archive exported; release only owned infrastructure",
              "artifact_retained": export["artifact"],
              "signal": "SIGTERM", "processes": []}
    record.write_text(json.dumps(result, indent=2) + "\n")
    for item in matches:
        cmdline = pathlib.Path(f"/proc/{item['pid']}/cmdline")
        if cmdline.read_bytes() != item["raw_cmdline"]:
            raise SystemExit("Owned process identity changed before signal")
        os.kill(item["pid"], signal.SIGTERM)
        result["processes"].append({key: value for key, value in item.items()
                                    if key != "raw_cmdline"})
    for _ in range(50):
        if all(not pathlib.Path(f"/proc/{item['pid']}").exists() for item in matches):
            break
        time.sleep(0.1)
    for item in result["processes"]:
        item["exited"] = not pathlib.Path(f"/proc/{item['pid']}").exists()
    result["all_owned_processes_exited"] = all(item["exited"] for item in result["processes"])
    result["finished_at_utc"] = utc()
    record.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if not result["all_owned_processes_exited"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
