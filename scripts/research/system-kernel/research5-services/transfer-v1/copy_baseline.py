#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run on CT102: stream only the frozen project Fedora tree to the SSD builder.

Both tar processes run in their standard Docker containers. Numeric ownership,
symlinks, hardlinks, modes, ACLs and xattrs are preserved; no host chown, storage
change, daemon reconfiguration or source deletion is performed. The exact same
canonical tar is regenerated at the destination and its stream hash compared.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import time

SOURCE = "tb371fc-build-20261123"
DEST = "tb371fc-build-ssd-20261123"
BASE = "/work/fedora-system-integration-v1"
WORK = "/work/fedora-input-system-v1"
RUNTIME_SHA = "10a373bfc3291aabe564c8f7af90265900763eadfe3167a7384cc4dcd596544b"
PROOT_SHA = "313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f"
QEMU_SHA = "73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943"
cancelled = False


def handle_signal(signum, frame):
    global cancelled
    cancelled = True


def docker_python(container, code, arguments=(), content=None):
    command = ["docker", "exec"] + (["-i"] if content is not None else [])
    command += [container, "python3", "-c", code, *map(str, arguments)]
    result = subprocess.run(command, input=content, capture_output=True, timeout=40)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors="replace")[:4000])
    return result.stdout


def tar_args(root, names):
    return ["timeout", "--signal=TERM", "--kill-after=10s", "900s", "tar",
            "--sort=name", "--format=posix",
            "--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime",
            "--numeric-owner", "--acls", "--selinux", "--xattrs", "--xattrs-include=*",
            "-cf", "-", "-C", root, *sorted(names)]


def hash_or_copy(label, source_root, destination_root, names, copy):
    """Bounded stream and owned CLI cleanup; inner tar also has a timeout."""
    logs = Path("/var/tmp/tb371fc-input2-copy-logs")
    logs.mkdir(exist_ok=True)
    before = time.monotonic()
    src_log = (logs / (label + ".source.log")).open("xb")
    dst_log = (logs / (label + ".destination.log")).open("xb") if copy else None
    reader = writer = None
    checksum = hashlib.sha256()
    size = 0
    try:
        container = SOURCE if copy else DEST
        root = source_root if copy else destination_root
        reader = subprocess.Popen(["docker", "exec", container, *tar_args(root, names)],
                                  stdout=subprocess.PIPE, stderr=src_log, start_new_session=True)
        if copy:
            writer = subprocess.Popen(["docker", "exec", "-i", DEST, "timeout", "--signal=TERM",
                                       "--kill-after=10s", "900s", "tar", "--numeric-owner", "--acls",
                                       "--selinux", "--xattrs", "--xattrs-include=*", "-xpf", "-",
                                       "-C", destination_root], stdin=subprocess.PIPE,
                                      stdout=dst_log, stderr=dst_log, start_new_session=True)
        os.set_blocking(reader.stdout.fileno(), False)
        if writer:
            os.set_blocking(writer.stdin.fileno(), False)
        buffered = bytearray()
        eof = False
        while not eof or buffered:
            if cancelled or time.monotonic() - before > 900:
                raise TimeoutError("cancelled or stream time bound reached")
            reads = [reader.stdout] if not eof and len(buffered) < 1024 * 1024 else []
            writes = [writer.stdin] if writer and buffered else []
            ready_read, ready_write, unused = select.select(reads, writes, [], 1)
            if ready_read:
                block = os.read(reader.stdout.fileno(), 131072)
                if block:
                    checksum.update(block); size += len(block)
                    if writer:
                        buffered.extend(block)
                else:
                    eof = True
            if ready_write:
                used = os.write(writer.stdin.fileno(), buffered)
                del buffered[:used]
        reader.stdout.close()
        if writer:
            writer.stdin.close()
        exits = [reader.wait(timeout=20)]
        if writer:
            exits.append(writer.wait(timeout=20))
        if any(exits):
            raise RuntimeError("tar stream did not finish successfully: " + repr(exits))
        return {"sha256": checksum.hexdigest(), "bytes": size, "exit_codes": exits,
                "elapsed_seconds": time.monotonic() - before}
    finally:
        for child in (reader, writer):
            if child is not None and child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=5)
        src_log.close()
        if dst_log:
            dst_log.close()


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    guard_code = """from pathlib import Path
import json,hashlib
w=Path('/work/fedora-system-integration-v1')
v=json.loads((w/'vm-verify-01/result.json').read_text())
assert v['passed'] and v['guest_gates_match']
assert v['guest_result']['selinux']=='Enforcing'
assert v['guest_result']['kernel_release']=='6.12.114-tb371fc-research1'
assert hashlib.sha256((w/'runtime.json').read_bytes()).hexdigest()==%r
assert hashlib.sha256(Path('/work/fedora-proot-src/src/proot').read_bytes()).hexdigest()==%r
assert hashlib.sha256(Path('/usr/bin/qemu-aarch64').read_bytes()).hexdigest()==%r
print(json.dumps({'vm_result_sha256':hashlib.sha256((w/'vm-verify-01/result.json').read_bytes()).hexdigest(),'guest_result':v['guest_result']}))
""" % (RUNTIME_SHA, PROOT_SHA, QEMU_SHA)
    source_guard = json.loads(docker_python(SOURCE, guard_code))
    create = """from pathlib import Path
import shutil,hashlib
w=Path(%r)
assert not w.exists() and not w.is_symlink()
assert shutil.disk_usage(w.parent).free > 10*1024**3
assert hashlib.sha256(Path('/usr/bin/qemu-aarch64').read_bytes()).hexdigest()==%r
w.mkdir()
for name in ('rootfs','builder-tools','baseline-records'): (w/name).mkdir()
""" % (WORK, QEMU_SHA)
    docker_python(DEST, create)
    record = {"schema_version": 1, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "source_container": SOURCE, "destination_container": DEST, "source_tree": BASE + "/rootfs",
              "destination_work": WORK, "source_guard": source_guard, "streams": {},
              "numeric_ownership_preserved_by_container_tar": True, "manual_host_chown": False,
              "source_deleted_or_moved": False, "source_modified_by_this_recipe": False,
              "complete": False}
    groups = (
        ("rootfs", BASE + "/rootfs", WORK + "/rootfs", ["."]),
        ("tools", "/work", WORK + "/builder-tools", ["fedora-proot-src/src/proot",
            "fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu/libtalloc.so.2.4.3",
            "fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu/libtalloc.so.2"]),
        ("records", BASE, WORK + "/baseline-records", ["runtime.json", "packages.after.tsv",
            "seed.json", "package-pins.json", "configured.json", "initramfs.json",
            "vm-label-02/result.json", "vm-verify-01/result.json"]),
    )
    try:
        for name, source, destination, names in groups:
            transferred = hash_or_copy(name + "-copy", source, destination, names, True)
            verified = hash_or_copy(name + "-verify", source, destination, names, False)
            if (transferred["sha256"], transferred["bytes"]) != (verified["sha256"], verified["bytes"]):
                raise ValueError("canonical copied stream differs: " + name)
            record["streams"][name] = {"transfer": transferred, "destination_rearchive": verified,
                                       "byte_identical": True}
            print(json.dumps({"copied_and_verified": name, **transferred}), flush=True)
        after = json.loads(docker_python(SOURCE, guard_code))
        if after != source_guard:
            raise ValueError("frozen source guard changed during copy")
        record["complete"] = True
    except BaseException as error:
        record["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        record["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write = "from pathlib import Path; import sys; p=Path(%r); f=p.open('xb'); f.write(sys.stdin.buffer.read()); f.close()" % (WORK + "/baseline-copy.json")
        docker_python(DEST, write, content=(json.dumps(record, sort_keys=True, indent=2) + "\n").encode())
    print("FEDORA_INPUT2_BASELINE_COPY_VERIFIED", flush=True)


if __name__ == "__main__":
    main()
