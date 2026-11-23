#!/usr/bin/env python3
"""Rebuild a fresh Fedora policy with the three reviewed PID1 permissions.

Runs the fixed ARM Fedora semodule/setfiles/sefcontext_compile through explicit
QEMU user emulation. No PRoot, binfmt registration, policy loading, host labeling,
VM, or modification of the source root is part of this recipe.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time


PINS = {
    "etc/selinux/targeted/policy/policy.35": "928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430",
    "etc/selinux/config": "80134a263d874d1687a43513a09b6cc8fdc2998e623c1c1670cb5769a85ce942",
    "etc/selinux/semanage.conf": "8ba0df9a109dd136f1e8827343806ced9a0652c670c2572b4dd8642c67c27734",
    "usr/sbin/semodule": "1fee7d2141b111197eb4bbcc72f626646af702c45e5f5212347e0e6c5e028029",
    "usr/sbin/setfiles": "75a118afe1060f2a402ac9c25498699b8b8493501bc7bd56099ee47fb0aa435b",
    "usr/sbin/sefcontext_compile": "4a4f15badf7f975f4a10f14d5706e6f53a3765ead74531110c64da4797767936",
    "usr/lib64/libsemanage.so.2": "246206662c92e1df56f5f4f0d173bfb1bd6f97827fa189538e0857b6dc6058e8",
    "usr/lib64/libsepol.so.2": "46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b",
    "usr/lib64/libselinux.so.1": "c9edfec980b8a05666d24dc3a4e15b502431334e2c7e3adcae189402b5031f6d",
}
QEMU_SHA = "73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943"
PREFIXES = ("etc/selinux", "var/lib/selinux/targeted")
# Canonical content/owner/mode inventory from the immutable original source;
# only timestamps are excluded here and remain checked before/after this run.
SOURCE_CONTENT_SHA = 'c0070c6fb7f209ed7e391d4707a1058caedbaf1ad96c076a17624661e5558b50'
SOURCE_INVENTORY_SHA = "3ab1550b558272ac17ff8a89520238bac8d2b5c108958e4458210da52fb10534"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def save(path, value):
    with path.open("x") as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")


def guest_path(root, rel):
    """Resolve absolute guest symlinks inside root, never against the host /."""
    pending = list(Path(rel).parts)
    parts = []
    links = 0
    while pending:
        item = pending.pop(0)
        if item in ("", "/", "."):
            continue
        if item == "..":
            if not parts:
                raise RuntimeError("guest symlink escapes its root")
            parts.pop()
            continue
        node = root.joinpath(*parts, item)
        if node.is_symlink():
            links += 1
            if links > 40:
                raise RuntimeError("guest symlink loop")
            target = os.readlink(node)
            if target.startswith("/"):
                parts = []
            pending = list(Path(target).parts) + pending
        else:
            node.lstat()
            parts.append(item)
    return root.joinpath(*parts)


def inventory(root):
    out = {}
    for prefix in PREFIXES:
        top = root / prefix
        for path in [top, *sorted(top.rglob("*"))]:
            s = path.lstat()
            item = {"mode": oct(stat.S_IMODE(s.st_mode)), "uid": s.st_uid,
                    "gid": s.st_gid, "mtime_ns": s.st_mtime_ns,
                    "ctime_ns": s.st_ctime_ns}
            if stat.S_ISLNK(s.st_mode):
                item.update(type="symlink", target=os.readlink(path))
            elif stat.S_ISREG(s.st_mode):
                item.update(type="file", size=s.st_size, sha256=digest(path))
            elif stat.S_ISDIR(s.st_mode):
                item.update(type="directory")
            else:
                raise RuntimeError(f"unexpected source node: {path}")
            out[str(path.relative_to(root))] = item
    return out


def content(item):
    return {k: v for k, v in item.items() if k not in ("mtime_ns", "ctime_ns")}


def differences(before, after):
    return [{"path": p, "before": before.get(p), "after": after.get(p)}
            for p in sorted(before.keys() | after.keys())
            if (content(before[p]) if p in before else None) !=
               (content(after[p]) if p in after else None)]


def tool_closure(source, target):
    pending = ["usr/sbin/semodule", "usr/sbin/setfiles",
               "usr/sbin/sefcontext_compile", "usr/libexec/selinux/hll/pp"]
    copied = {}
    for name in ("lib", "lib64"):
        (target / name).symlink_to("usr/" + name)
    while pending:
        rel = pending.pop()
        if rel in copied:
            continue
        src = guest_path(source, rel)
        data = src.read_bytes()
        if data[:6] != b"\x7fELF\x02\x01" or int.from_bytes(data[18:20], "little") != 183:
            raise RuntimeError(f"not an ARM64 ELF: {src}")
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        dyn = subprocess.run(["readelf", "-d", str(dest)], check=True,
                             capture_output=True, text=True).stdout
        phdr = subprocess.run(["readelf", "-l", str(dest)], check=True,
                              capture_output=True, text=True).stdout
        if re.search(r"\((?:RPATH|RUNPATH)\)", dyn):
            raise RuntimeError(f"unexpected loader search path: {src}")
        needed = re.findall(r"\(NEEDED\).*\[([^\]]+)\]", dyn)
        interp = re.findall(r"Requesting program interpreter: ([^\]]+)", phdr)
        copied[rel] = {"size": len(data), "sha256": digest(dest), "needed": needed,
                       "source_payload": str(src.relative_to(source)),
                       "interp": interp, "mode": oct(stat.S_IMODE(src.stat().st_mode))}
        for name in needed:
            matches = ["usr/lib64/" + name, "usr/lib/" + name]
            matches = [x for x in matches if (source / x).is_file()]
            if len(matches) != 1:
                raise RuntimeError(f"ambiguous or absent library {name}: {matches}")
            pending.extend(matches)
        for name in interp:
            if name != "/lib/ld-linux-aarch64.so.1":
                raise RuntimeError(f"unexpected interpreter: {name}")
            pending.append("usr/lib/ld-linux-aarch64.so.1")
    for rel in ("etc/ld.so.cache", "etc/nsswitch.conf", "etc/passwd", "etc/group"):
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = guest_path(source, rel)
        shutil.copy2(src, dst)
        copied[rel] = {"size": dst.stat().st_size, "sha256": digest(dst),
                       "source_payload": str(src.relative_to(source))}
    return copied


def create_wrapper(path, kind, qemu, toolroot, candidate, log):
    # Native wrapper dispatches one fixed ARM program; callers cannot choose it.
    code = f'''#!/usr/bin/python3
import json, os, pathlib, sys
kind = {kind!r}
args = sys.argv[1:]
prefix = {str(candidate)!r} + "/"
if kind == "setfiles":
    valid = len(args) == 4 and args[:2] == ["-q", "-c"] and all(x.startswith(prefix) for x in args[2:])
elif kind == "sefcontext_compile":
    valid = len(args) == 2 and args[0] == "-r" and args[1].startswith(prefix)
elif kind == "pp":
    valid = not args
else:
    valid = False
with open({str(log)!r}, "a") as out:
    out.write(json.dumps({{"tool": kind, "argv": args, "accepted": valid}}) + "\\n")
if not valid:
    raise SystemExit("blocked external tool invocation")
binary = {str(toolroot)!r} + ("/usr/libexec/selinux/hll/pp" if kind == "pp" else "/usr/sbin/" + kind)
os.execv({str(qemu)!r}, [{str(qemu)!r}, "-L", {str(toolroot)!r}, binary, *args])
'''
    path.write_text(code)
    path.chmod(0o755)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--module", type=Path, required=True)
    args = ap.parse_args()
    source = args.source_root.resolve(strict=True)
    work = args.work.absolute()
    if not str(work).startswith("/work/selinux-reload-map-self-20261123/") or work.exists():
        ap.error("require a fresh child of /work/selinux-reload-map-self-20261123")
    rule = args.module.read_text()
    actual = [line.strip() for line in rule.splitlines()
              if line.strip() and not line.lstrip().startswith(";")]
    if actual != ["(allow init_t semanage_store_t (file (map)))",
                  "(allow init_t init_t (process (setcurrent dyntransition)))"]:
        ap.error("module must contain exactly the two reviewed allow rules")
    for rel, expected in PINS.items():
        if digest(source / rel) != expected:
            raise RuntimeError(f"source hash mismatch: {rel}")
    if digest(Path("/usr/bin/qemu-aarch64")) != QEMU_SHA:
        raise RuntimeError("QEMU hash mismatch")
    work.mkdir(mode=0o700)
    record = {"schema": 1, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "source_root": str(source), "script_sha256": digest(Path(__file__)),
              "physical_device_actions": False, "kernel_policy_loaded": False,
              "rootfs_booted": False, "source_pins": PINS, "status": "started"}
    before = inventory(source)
    canonical_source = json.dumps({p: content(item) for p, item in before.items()},
                                  sort_keys=True, separators=(",", ":")).encode()
    source_content_sha = hashlib.sha256(canonical_source).hexdigest()
    if source_content_sha != SOURCE_CONTENT_SHA:
        raise RuntimeError("original complete source policy/store content inventory differs")
    record["original_source_inventory_reference_sha256"] = SOURCE_INVENTORY_SHA
    record["source_complete_content_inventory_sha256"] = source_content_sha
    save(work / "source-before.json", before)
    started = time.monotonic()
    try:
        candidate = work / "candidate"
        for prefix in PREFIXES:
            dest = candidate / prefix
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source / prefix, dest, symlinks=True)
        copied = inventory(candidate)
        if differences(before, copied):
            raise RuntimeError("initial copy content or metadata differs")
        save(work / "candidate-before.json", copied)
        toolroot = work / "tool-root"
        toolroot.mkdir()
        record["tool_closure"] = tool_closure(source, toolroot)
        qemu = work / "qemu-aarch64"
        shutil.copy2("/usr/bin/qemu-aarch64", qemu)
        record["qemu"] = {"size": qemu.stat().st_size, "sha256": digest(qemu)}
        module = work / "tb371fc_init_reload_contract.cil"
        shutil.copy2(args.module, module)
        record["module"] = {"size": module.stat().st_size, "sha256": digest(module),
                            "rules": actual, "priority": 400}
        wrappers = work / "wrappers"
        wrappers.mkdir()
        helper_log = work / "external-tools.jsonl"
        for kind in ("setfiles", "sefcontext_compile", "pp", "load_policy"):
            create_wrapper(wrappers / kind, kind, qemu, toolroot, candidate, helper_log)
        conf = (source / "etc/selinux/semanage.conf").read_text()
        needle = "path = /usr/sbin/sefcontext_compile"
        if conf.count(needle) != 1:
            raise RuntimeError("unexpected source configuration")
        conf = conf.replace(needle, f"path = {wrappers}/sefcontext_compile")
        conf += (f"\ncompiler-directory = {wrappers}\n"
                 f"[setfiles]\npath = {wrappers}/setfiles\nargs = -q -c $@ $<\n[end]\n"
                 f"[load_policy]\npath = {wrappers}/load_policy\n[end]\n")
        config = work / "semanage-build.conf"
        config.write_text(conf)
        record["build_config"] = {"size": config.stat().st_size, "sha256": digest(config),
                                  "changes": "Only fixed emulated executable paths; load_policy rejects every invocation."}
        command = [str(qemu), "-L", str(toolroot), str(toolroot / "usr/sbin/semodule"),
                   "-p", str(candidate), "-S", "/var/lib/selinux", "-s", "targeted",
                   "-g", str(config), "-n", "-v", "-X", "400", "-i", str(module)]
        record["command"] = command
        print(json.dumps({"phase": "semodule-start", "argv": command}), flush=True)
        with (work / "semodule.log").open("xb") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
        record["semodule_exit_code"] = result.returncode
        record["semodule_log"] = {"size": (work / "semodule.log").stat().st_size,
                                  "sha256": digest(work / "semodule.log")}
        after = inventory(candidate)
        save(work / "candidate-after.json", after)
        delta = differences(copied, after)
        save(work / "candidate-content-diff.json", delta)
        record["candidate_content_differences"] = delta
        record["external_tools"] = [json.loads(x) for x in helper_log.read_text().splitlines()] if helper_log.exists() else []
        if result.returncode:
            raise RuntimeError(f"semodule exited {result.returncode}")
        if any(not x["accepted"] or x["tool"] == "load_policy" for x in record["external_tools"]):
            raise RuntimeError("unexpected external helper invocation")
        policy = candidate / "etc/selinux/targeted/policy/policy.35"
        record["candidate_policy"] = {"path": str(policy), "size": policy.stat().st_size,
                                      "sha256": digest(policy), "mode": oct(stat.S_IMODE(policy.stat().st_mode))}
        record["status"] = "built_pending_delta_and_runtime_qualification"
        print(json.dumps({"phase": "semodule-complete", "policy": record["candidate_policy"],
                          "changed_paths": [x["path"] for x in delta]}), flush=True)
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        source_after = inventory(source)
        save(work / "source-after.json", source_after)
        record["source_inventory_unchanged_including_mtime_ctime"] = before == source_after
        record["elapsed_seconds"] = time.monotonic() - started
        record["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(work / "result.json", record)
        if before != source_after:
            raise RuntimeError("source inventory changed; candidate is not qualified")


if __name__ == "__main__":
    main()
