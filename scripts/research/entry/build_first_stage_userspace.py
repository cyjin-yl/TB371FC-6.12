#!/usr/bin/env python3
"""Build a clean static ARM64 rescue initramfs; never loads or executes kexec.

The binaries' only execution checks use explicit qemu-aarch64 --version/help
or a BusyBox shell builtin. No host binfmt registration is needed or changed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import time
import urllib.request

SOURCES = {
    "busybox": ("https://busybox.net/downloads/busybox-1.37.0.tar.bz2",
                "3311dff32e746499f4df0d5df04d7eb396382d7e108bb9250e7b519b837043a4"),
    "kexec": ("https://www.kernel.org/pub/linux/utils/kernel/kexec/kexec-tools-2.0.32.tar.xz",
              "8f81422a5fd2362cf6cb001b511e535565ed0f32c2f4451fb5eb68fed6710a5d"),
}
BB_ENABLE = "BUSYBOX STATIC ASH SH_IS_ASH ASH_ALIAS ASH_JOB_CONTROL ASH_BASH_COMPAT ASH_TEST TEST TEST1 FEATURE_SH_STANDALONE FEATURE_PREFER_APPLETS FEATURE_INSTALLER CAT CHMOD CHOWN CP DD DF DMESG ECHO ENV EXPR FALSE FIND GREP HEAD HOSTNAME ID IP FEATURE_IP_ADDRESS FEATURE_IP_LINK FEATURE_IP_ROUTE LN LS MKDIR MKNOD MOUNT UMOUNT MOUNTPOINT MV POWEROFF REBOOT SWITCH_ROOT SLEEP SETSID CTTYHACK STTY SYNC TRUE UNAME UPTIME SHA256SUM AWK SED CUT TR WC XARGS TIMEOUT".split()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def unpack(archive, destination):
    destination.mkdir(exist_ok=False)
    with tarfile.open(archive, "r:*") as tf:
        members = tf.getmembers()
        root = PurePosixPath(members[0].name).parts[0]
        selected = []
        for m in members:
            path = PurePosixPath(m.name)
            if path.is_absolute() or ".." in path.parts or path.parts[0] != root or m.isdev() or m.isfifo():
                raise ValueError("unsafe source archive member")
            m.name = str(PurePosixPath(*path.parts[1:]))
            if m.islnk():
                link = PurePosixPath(m.linkname)
                if link.parts[0] != root:
                    raise ValueError("unsafe source hard link")
                m.linkname = str(PurePosixPath(*link.parts[1:]))
            if m.name not in {"", "."}:
                selected.append(m)
        tf.extractall(destination, members=selected, filter="data")


def newc(entries):
    """Produce a deterministic newc archive without creating host device nodes."""
    out = bytearray()
    for ino, (name, mode, data, rmajor, rminor) in enumerate(entries + [("TRAILER!!!", 0, b"", 0, 0)], 1):
        encoded = name.encode() + b"\0"
        fields = [ino, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, len(data), 0, 0, rmajor, rminor, len(encoded), 0]
        out.extend(b"070701" + b"".join(f"{x:08x}".encode() for x in fields))
        out.extend(encoded)
        out.extend(b"\0" * (-len(out) % 4))
        out.extend(data)
        out.extend(b"\0" * (-len(out) % 4))
    out.extend(b"\0" * (-len(out) % 512))
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", type=Path, default=Path("/work/first-stage-research"))
    ap.add_argument("--recipe", type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument("--name", default="userspace-r1")
    ap.add_argument("--jobs", type=int, default=1)
    args = ap.parse_args()
    if not re.fullmatch(r"userspace-r[1-9][0-9]*(?:-attempt[1-9][0-9]*)?", args.name) or not 1 <= args.jobs <= 3:
        ap.error("invalid isolated build name/jobs")
    work, recipe = args.work.resolve(), args.recipe.resolve()
    run = work / args.name
    run.mkdir(exist_ok=False)
    rec = {"schema": "tb371fc-clean-entry-userspace-v1", "started_utc": datetime.now(timezone.utc).isoformat(),
           "sources": {}, "commands": [], "artifacts": {}, "physical_device_tested": False,
           "kexec_load_or_execute_tested": False, "default_action": "hold"}
    env = dict(os.environ, PATH="/usr/bin:/bin", LC_ALL="C", TZ="UTC", SOURCE_DATE_EPOCH="1786245476",
               KCONFIG_NOTIMESTAMP="1")
    started = time.monotonic()

    def cmd(argv, cwd=None, capture=False):
        argv = [str(x) for x in argv]
        print("COMMAND " + json.dumps(argv), flush=True)
        p = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE if capture else None,
                           stderr=subprocess.STDOUT if capture else None, stdin=subprocess.DEVNULL, text=True)
        result = {"argv": argv, "exit_code": p.returncode}
        if capture:
            result["output"] = p.stdout
            print(p.stdout, end="", flush=True)
        rec["commands"].append(result)
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, argv)
        return p.stdout if capture else None

    try:
        tools = work / "userspace-toolchain.json"
        rec["toolchain_manifest_sha256"] = sha(tools)
        rec["toolchain"] = json.loads(tools.read_text())["packages"]
        for name, version in rec["toolchain"].items():
            if cmd(["dpkg-query", "-W", "-f=${Version}", name], capture=True) != version:
                raise RuntimeError("toolchain version drift: " + name)
        cmd(["aarch64-linux-gnu-gcc", "--version"], capture=True)
        cmd(["qemu-aarch64", "--version"], capture=True)
        for name, (url, expected) in SOURCES.items():
            archive = work / "downloads" / url.rsplit("/", 1)[-1]
            if not archive.exists():
                raw = urllib.request.urlopen(url, timeout=30).read(16 * 1024 * 1024)
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise RuntimeError("source download mismatch: " + name)
                with archive.open("xb") as f:
                    f.write(raw)
            if sha(archive) != expected:
                raise RuntimeError("cached source mismatch: " + name)
            unpack(archive, run / name)
            rec["sources"][name] = {"url": url, "sha256": expected, "bytes": archive.stat().st_size}

        bb = run / "busybox"
        bbout = run / "busybox-out"
        bbout.mkdir()
        make = ["make", "-C", bb, f"O={bbout}", "ARCH=arm64", "CROSS_COMPILE=aarch64-linux-gnu-"]
        cmd(make + ["allnoconfig"])
        config = (bbout / ".config").read_text()
        for key in BB_ENABLE:
            pattern = rf"^(?:# CONFIG_{key} is not set|CONFIG_{key}=.*)$"
            if not re.search(pattern, config, re.M):
                raise RuntimeError("unknown BusyBox configuration key " + key)
            config = re.sub(pattern, f"CONFIG_{key}=y", config, flags=re.M)
        config = re.sub(r"^CONFIG_SH_IS_NONE=y$", "# CONFIG_SH_IS_NONE is not set", config, flags=re.M)
        (bbout / ".config").write_text(config)
        # BusyBox 1.37 retains the older kconfig target names. Every option is
        # already present from allnoconfig, so oldconfig needs no interactive input.
        cmd(make + ["oldconfig"])
        resolved = (bbout / ".config").read_text()
        for key in ["STATIC", "ASH", "SH_IS_ASH", "ASH_TEST", "TEST", "TEST1", "FEATURE_INSTALLER", "MOUNT", "CTTYHACK", "SHA256SUM"]:
            if f"CONFIG_{key}=y\n" not in resolved:
                raise RuntimeError("required BusyBox option lost: " + key)
        rec["busybox_config_sha256"] = sha(bbout / ".config")
        cmd(make + [f"-j{args.jobs}"])

        ksrc = run / "kexec"
        kobj = run / "kexec-objects"
        cmd([ksrc / "configure", "--build=x86_64-linux-gnu", "--host=aarch64-linux-gnu",
             f"--with-objdir={kobj}", "--without-zlib", "--without-lzma", "--without-zstd", "--without-xen",
             "CC=aarch64-linux-gnu-gcc", "LDFLAGS=-static", "CFLAGS=-Os"], cwd=ksrc)
        cmd(["make", f"-j{args.jobs}"], cwd=ksrc)
        # This fixed release emits its install-tree payload under build/sbin;
        # --with-objdir is not the location of the resulting executable.
        kexec_elf = ksrc / "build/sbin/kexec"
        if not kexec_elf.is_file() or kexec_elf.read_bytes()[:4] != b"\x7fELF":
            raise RuntimeError("missing kexec ELF at the verified release output path")
        output = run / "artifacts"
        output.mkdir()
        cmd(["aarch64-linux-gnu-gcc", "-Os", "-static", "-fno-ident", "-Wl,--build-id=none",
             "-o", output / "entry-return-bootloader", recipe / "return_bootloader.c"])
        shutil.copyfile(bbout / "busybox", output / "busybox")
        shutil.copyfile(kexec_elf, output / "kexec")
        for name in ["busybox", "kexec", "entry-return-bootloader"]:
            p = output / name
            raw = p.read_bytes()
            if raw[:4] != b"\x7fELF" or raw[4:6] != b"\x02\x01" or struct.unpack_from("<H", raw, 18)[0] != 183:
                raise RuntimeError("not a little-endian ARM64 ELF: " + name)
            headers = cmd(["aarch64-linux-gnu-readelf", "-l", p], capture=True)
            if re.search(r"^\s*INTERP\s", headers, re.M):
                raise RuntimeError("unexpected dynamic interpreter: " + name)
            p.chmod(0o755)
            rec["artifacts"][name] = {"bytes": len(raw), "sha256": sha(p), "elf_machine": 183, "pt_interp": False}
        applets = cmd(["qemu-aarch64", output / "busybox", "--list"], capture=True).splitlines()
        for app in ["sh", "[", "test", "mount", "mkdir", "cat", "uname", "setsid", "cttyhack", "ln", "sha256sum", "stty", "sleep"]:
            if app not in applets:
                raise RuntimeError("missing rescue applet " + app)
        rec["busybox_applets"] = applets
        cmd(["qemu-aarch64", output / "busybox", "sh", "-c", "echo TB371FC_ENTRY_SHELL_OK"], capture=True)
        cmd(["qemu-aarch64", output / "busybox", "sh", "-c", "[ -r /proc/self/stat ] && test 1 -eq 1 && echo TB371FC_ENTRY_TEST_OK"], capture=True)
        cmd(["qemu-aarch64", output / "kexec", "--version"], capture=True)
        cmd(["qemu-aarch64", output / "entry-return-bootloader", "--version"], capture=True)
        # Validate shell syntax without executing mounts, gadget writes or boot.
        cmd(["qemu-aarch64", output / "busybox", "sh", "-n", recipe / "ramdisk-init"], capture=True)
        entries = [(p, 0o40755, b"", 0, 0) for p in ["bin", "sbin", "dev", "dev/pts", "proc", "sys", "run", "tmp"]]
        entries += [("dev/console", 0o20600, b"", 5, 1), ("dev/null", 0o20666, b"", 1, 3),
                    ("bin/sh", 0o120777, b"busybox", 0, 0),
                    ("init", 0o100755, (recipe / "ramdisk-init").read_bytes(), 0, 0)]
        entries += [("bin/" + name, 0o100755, (output / name).read_bytes(), 0, 0)
                    for name in ["busybox", "kexec", "entry-return-bootloader"]]
        archive = output / "entry-initramfs.cpio.gz"
        archive.write_bytes(gzip.compress(newc(entries), compresslevel=9, mtime=0))
        rec["artifacts"][archive.name] = {"bytes": archive.stat().st_size, "sha256": sha(archive)}
        rec["cpio_entries"] = [{"path": n, "mode": oct(m), "bytes": len(data), "rdev": [maj, minor]}
                               for n, m, data, maj, minor in entries]
        rec["recipe_hashes"] = {n: sha(recipe / n) for n in ["ramdisk-init", "return_bootloader.c", "build_first_stage_userspace.py"]}
        rec["completed"] = True
    except Exception as exc:
        rec["completed"] = False
        rec["failure"] = str(exc)
        raise
    finally:
        rec["elapsed_seconds"] = time.monotonic() - started
        rec["ended_utc"] = datetime.now(timezone.utc).isoformat()
        (run / "build.json").write_text(json.dumps(rec, indent=2) + "\n")


if __name__ == "__main__":
    main()
