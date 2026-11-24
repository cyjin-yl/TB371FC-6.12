#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Recover the frozen 894-path NixOS closure on a new SSD-local store.

This is an isolated registered-root experiment, not activation or a boot.
It uses the already qualified 890-record cache transfer, the exact official
source NAR, and three small NARs dumped from the verified original store.
The three small NARs receive a new project signature only after hash checking.
No old cache, source store, key, or global Nix configuration is modified.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import traceback

TOP = "/nix/store/j1g4ih1ajpffx2vhp5z0iyns13h59c4a-nixos-system-tb371fc-research-26.05.20261121.94c3211"
COUNT, NAR_BYTES = 894, 3751712072
PAYLOAD = Path("/work/nixos-cache-inputs-ssd-v2/payload")
EXACT = Path("/work/nixos-exact-source-nar-20261123-v1/source.nar.zst")
OFFICIAL_INFO = Path("/work/nixos-narinfo-recovery-v1/response.body")
TOOL = Path("/work/nixos-native-tool-20261123-v1/tool")
CAT_SHA = "dfa73bc5734e9aebf58321b0c383dd4b4eeccd22b619274a5395e6fe716d3b19"
INVENTORY_SHA = "3f5772abcfb979a5413ab2e76d8db06022fa60a7a7b2a9b34d5a4c8abc0c0eaa"
OLD_KEY_SHA = "72657aba2a60a6ff9fd8e10a9ca626dd5dce90e98bde24b3386651441417faa2"
NIX_SHA = "1795adb32a21c0aeef19e19530e96b933b603465a99dc6cf3ceed5b96948de58"
EXACT_SHA = "0b1a2a30731ce58f252105a79c48ae07d7b56b965619d89dc33b547babd40a57"
OFFICIAL = "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
NEW_KEY_NAME = "tb371fc-nixos-ssd-recovery-20261124-v1"
SOURCE = "/nix/store/0j3mwnl5n7xfl45ar8nn4z08iq5l34qq-source"
SMALL = {
    "/nix/store/d82cbv5vl29wgs9m51y6vd2r094w8648-etc",
    TOP,
    "/nix/store/shgbb71xj6266hipw2p7lbijkvl4x9qa-etc-nix-registry.json",
}
ENTRY_HASHES = {
    "init": "d7440ba41d2fb1abdbe1a9a2a1267cde841deb9dd4bd088a59586b12a719becd",
    "activate": "8e8c85675ceca709cd0445f5211a556cb3d0edf52d94e63cd1ea1bdf989f2ea9",
}
ALPHABET = "0123456789abcdfghijklmnpqrsvwxyz"
STORE = re.compile(r"/nix/store/[0-9a-z]{32}-[^/\x00\n ]+")
URL = re.compile(r"nar/[0-9a-z]{52}\.nar(?:\.zst)?")

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def sha(path):
    require(path.is_file() and not path.is_symlink(), "ordinary input required: " + str(path))
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def atomic_json(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)

def read_json(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            require(k not in out, "duplicate JSON key: " + k)
            out[k] = v
        return out
    return json.loads(path.read_text(), object_pairs_hook=unique)

def nix32(raw):
    require(len(raw) == 32, "SHA-256 required")
    n = int.from_bytes(raw, "little")
    return "".join(ALPHABET[(n >> (5*i)) & 31] for i in reversed(range(52)))

def hash32(sri):
    require(sri.startswith("sha256-"), "expected SHA-256 SRI")
    return "sha256:" + nix32(base64.b64decode(sri[7:], validate=True))

def narinfo(raw):
    result = {"Sig": []}
    for line in raw.decode("ascii").splitlines():
        if not line:
            continue
        name, sep, value = line.partition(": ")
        require(sep and (name == "Sig" or name not in result), "invalid/duplicate narinfo field")
        if name == "Sig":
            require(value not in result["Sig"], "duplicate signature")
            result["Sig"].append(value)
        else:
            result[name] = value
    return result

def check_row(info, name, row):
    require(STORE.fullmatch(name) and info["StorePath"] == name, "wrong narinfo store path")
    require(info["NarHash"] == hash32(row["narHash"]) and int(info["NarSize"]) == row["narSize"],
            "NAR metadata mismatch: " + name)
    refs = ["/nix/store/" + p for p in info.get("References", "").split()]
    require(sorted(refs) == sorted(row["references"]), "references mismatch: " + name)
    require(info.get("CA") == row.get("ca"), "content address mismatch: " + name)
    require(URL.fullmatch(info["URL"]), "unexpected cache object URL")
    require(info["Compression"] in ("none", "zstd"), "unexpected compression")
    require(set(row.get("signatures", [])).issubset(info["Sig"]), "original signature missing")
    require(info["Sig"], "unsigned cache record")

def copy_checked(source, target, expected_hash, expected_size):
    require(source.is_file() and not source.is_symlink(), "not an ordinary input")
    require(not target.exists() and not target.is_symlink(), "new target required")
    digest = hashlib.sha256()
    length = 0
    with source.open("rb") as src, target.open("xb") as dst:
        while chunk := src.read(1024*1024):
            digest.update(chunk)
            length += len(chunk)
            dst.write(chunk)
    require(length == expected_size and digest.hexdigest() == expected_hash,
            "copy content mismatch: " + str(source))

def fingerprint(name, row):
    return ("1;" + name + ";" + hash32(row["narHash"]) + ";" + str(row["narSize"]) + ";" +
            ",".join(sorted(row["references"]))).encode("ascii")

def self_test():
    require(hash32("sha256-IEuDsf80ubivfpidbRsIm30HVo7PZIdZt1stRsbaY4Y=") ==
            "sha256:11k3vb34cbavnxcqfr6girb0fzcv10dnv7cqgspvif9lzyqq6jr0", "Nix32 vector")
    require(hash32("sha256-" + base64.b64encode(bytes(32)).decode()) == "sha256:" + "0"*52,
            "zero vector")
    try:
        narinfo(b"StorePath: x\nStorePath: y\n")
    except RuntimeError:
        pass
    else:
        raise RuntimeError("duplicate field not rejected")
    row = {"narHash": "sha256-IEuDsf80ubivfpidbRsIm30HVo7PZIdZt1stRsbaY4Y=",
           "narSize": 207320816, "references": []}
    require(hashlib.sha256(fingerprint(SOURCE, row)).hexdigest() ==
            "bb137a0cfb53850dfaf4dc2f5c806a1809089866274805e91c39081920de2131",
            "pinned upstream fingerprint vector")
    print("4 contract self-checks passed")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--work", type=Path)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    work = args.work
    require(os.geteuid() == 0 and os.uname().machine == "x86_64", "native SSD builder root required")
    require(work and re.fullmatch(r"/work/nixos-ssd-recovery-[A-Za-z0-9_-]+", str(work)),
            "isolated /work prefix required")
    require(not work.exists() and not work.is_symlink(), "new work prefix required")
    os.umask(0o077)
    lock = open("/work/nixos-ssd-recovery-lane.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    work.mkdir(mode=0o700)
    jobs = work / "jobs"
    cache = work / "cache"
    private = work / "private"
    root = work / "rootfs"
    for p in (jobs, cache, private, root, cache/"nar", private/"config", private/"xdg", private/"home"):
        p.mkdir()
    root.chmod(0o755)
    report = {"schema_version": 1, "scope": "SSD-local registered-root recovery, not a system boot",
              "recipe_sha256": sha(Path(__file__)), "started_utc": time.strftime("%FT%TZ", time.gmtime()),
              "complete": False, "cache_assembled": False, "root_registered": False,
              "require_sigs": True, "old_cache_modified": False, "source_store_modified": False,
              "global_configuration_written": False, "activation_executed": False,
              "vm_started": False, "physical_hardware_tested": False, "commands": []}
    start = time.monotonic()
    def checkpoint():
        report["elapsed_seconds"] = time.monotonic() - start
        atomic_json(work/"result.json", report)
    env = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C", "TERM": "dumb",
           "NIX_CONFIG": "", "NIX_CONF_DIR": str(private/"config"), "NIX_USER_CONF_FILES": "",
           "NIX_PAGER": "cat", "XDG_CACHE_HOME": str(private/"xdg"), "HOME": str(private/"home")}
    def command(name, argv, timeout=180, hidden_stdout=False):
        out, err = jobs/(name+".stdout"), jobs/(name+".stderr")
        require(not out.exists() and not err.exists(), "new log names required")
        rec = {"name": name, "argv": argv, "timeout_seconds": timeout}
        report["commands"].append(rec)
        t = time.monotonic()
        try:
            with out.open("xb") as a, err.open("xb") as b:
                proc = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, stdout=a, stderr=b,
                                      timeout=timeout, check=False)
            rec["exit_code"] = proc.returncode
            require(proc.returncode == 0, "command failed: " + name)
        except subprocess.TimeoutExpired:
            rec["timed_out"] = True
            raise
        finally:
            rec["elapsed_seconds"] = time.monotonic() - t
            if out.exists():
                rec["stdout"] = ({"excluded": True} if hidden_stdout else
                                 {"bytes": out.stat().st_size, "sha256": sha(out)})
            if err.exists():
                rec["stderr"] = {"bytes": err.stat().st_size, "sha256": sha(err)}
            checkpoint()
        return out
    try:
        self_test()
        meta = PAYLOAD/"metadata"
        require(sha(meta/"catalog.json") == CAT_SHA, "catalog hash changed")
        require(sha(meta/"source-inventory-before.json") == INVENTORY_SHA, "source inventory hash changed")
        require(sha(meta/"cache-public-key") == OLD_KEY_SHA, "old project public key changed")
        require(sha(TOOL/"bin/nix") == NIX_SHA, "native Nix executable changed")
        tool_report = read_json(TOOL.parent/"result.json")
        require(tool_report["complete"] and tool_report["private_dependency_resolution_qualified"],
                "native importer prerequisites absent")
        # Read the already-qualified private dependency identities. No package installation.
        report["native_tool_report_sha256"] = sha(TOOL.parent/"result.json")
        catalog = read_json(meta/"catalog.json")
        rows = read_json(meta/"source-inventory-before.json")
        require(len(rows) == COUNT and sum(x["narSize"] for x in rows.values()) == NAR_BYTES,
                "closure identity changed")
        require(all(STORE.fullmatch(n) and set(r["references"]).issubset(rows)
                    for n, r in rows.items()), "closure reference escapes")
        require(set(catalog["records"]) == set(rows) - SMALL - {SOURCE}
                and len(catalog["objects"]) == 868 and set(catalog["small_nars"]) == SMALL,
                "unexpected recovery coverage")
        old_key = (meta/"cache-public-key").read_text().strip()
        report["inputs"] = {"catalog_sha256": CAT_SHA, "inventory_sha256": INVENTORY_SHA,
                            "old_project_public_key": old_key, "official_public_key": OFFICIAL,
                            "exact_source_sha256": EXACT_SHA}
        (cache/"nix-cache-info").write_text("StoreDir: /nix/store\n")
        for url, obj in sorted(catalog["objects"].items()):
            require(URL.fullmatch(url), "unsafe object path")
            copy_checked(PAYLOAD/"cache"/url, cache/url, obj["expected_sha256_from_narinfo"], obj["size"])
        for name, item in sorted(catalog["records"].items()):
            filename = Path(name).name.split("-",1)[0]+".narinfo"
            src = PAYLOAD/"cache"/filename
            copy_checked(src, cache/filename, item["retained"]["sha256"], item["retained"]["size"])
            info = narinfo((cache/filename).read_bytes())
            check_row(info, name, rows[name])
            obj = catalog["objects"][info["URL"]]
            require(info["FileHash"] == "sha256:" + nix32(bytes.fromhex(obj["expected_sha256_from_narinfo"]))
                    and int(info["FileSize"]) == obj["size"], "compressed object metadata mismatch")
            require(any(s.startswith(old_key.split(":")[0]+":") for s in info["Sig"]),
                    "old project signature absent")
        # Preserve the exact official narinfo and compressed object; do not re-sign it.
        raw = OFFICIAL_INFO.read_bytes()
        info = narinfo(raw)
        check_row(info, SOURCE, rows[SOURCE])
        require(info["FileHash"] == "sha256:" + nix32(bytes.fromhex(EXACT_SHA)), "official compressed hash mismatch")
        require(any(s.startswith("cache.nixos.org-1:") for s in info["Sig"]), "official signature absent")
        copy_checked(EXACT, cache/info["URL"], EXACT_SHA, 36199412)
        (cache/(Path(SOURCE).name.split("-",1)[0]+".narinfo")).write_bytes(raw)
        # Sign only the three exact local NARs using a fresh key in the isolated prefix.
        key = private/"recovery-ed25519.pem"
        command("generate-recovery-key", ["openssl","genpkey","-algorithm","ED25519","-out",str(key)])
        require(stat.S_IMODE(key.stat().st_mode) == 0o600, "private key permissions")
        public = command("derive-recovery-public-key", ["openssl","pkey","-in",str(key),"-pubout","-outform","DER"]).read_bytes()
        require(len(public) == 44 and public[:12] == bytes.fromhex("302a300506032b6570032100"), "unexpected Ed25519 DER")
        new_key = NEW_KEY_NAME + ":" + base64.b64encode(public[12:]).decode()
        report["inputs"]["new_project_public_key"] = new_key
        for i, name in enumerate(sorted(SMALL)):
            row = rows[name]
            item = catalog["small_nars"][name]["artifact"]
            src = PAYLOAD/"small-nars"/(Path(name).name+".nar")
            require(row.get("ultimate") is True, "small NAR not from locally trusted source")
            expected = base64.b64decode(row["narHash"][7:], validate=True).hex()
            require(expected == item["sha256"] and row["narSize"] == item["size"], "small NAR identity differs")
            url = "nar/" + hash32(row["narHash"])[7:] + ".nar"
            copy_checked(src, cache/url, expected, row["narSize"])
            fp = private/("fingerprint-"+str(i))
            fp.write_bytes(fingerprint(name,row))
            sig = command("sign-small-"+str(i), ["openssl","pkeyutl","-sign","-rawin","-inkey",str(key),"-in",str(fp)]).read_bytes()
            require(len(sig) == 64, "unexpected Ed25519 signature length")
            lines = ["StorePath: "+name, "URL: "+url, "Compression: none",
                     "FileHash: "+hash32(row["narHash"]), "FileSize: "+str(row["narSize"]),
                     "NarHash: "+hash32(row["narHash"]), "NarSize: "+str(row["narSize"]),
                     "References: "+" ".join(Path(x).name for x in sorted(row["references"]))]
            if row.get("deriver"):
                lines.append("Deriver: "+Path(row["deriver"]).name)
            if row.get("ca"):
                lines.append("CA: "+row["ca"])
            lines += ["Sig: "+x for x in row.get("signatures",[])]
            lines.append("Sig: "+NEW_KEY_NAME+":"+base64.b64encode(sig).decode())
            data = ("\n".join(lines)+"\n").encode("ascii")
            check_row(narinfo(data),name,row)
            (cache/(Path(name).name.split("-",1)[0]+".narinfo")).write_bytes(data)
        require(len(list(cache.glob("*.narinfo"))) == COUNT and len(list((cache/"nar").iterdir())) == 872,
                "assembled cache counts differ")
        report.update(cache_assembled=True, cache_records=COUNT, cache_objects=872,
                      recovered_official_records=1, newly_signed_local_records=3)
        checkpoint()
        prefix = [str(TOOL/"lib/ld-linux-x86-64.so.2"),"--inhibit-cache","--library-path",str(TOOL/"lib"),str(TOOL/"bin/nix")]
        require(command("nix-version",prefix+["--version"]).read_text().strip()=="nix (Nix) 2.26.3",
                "native tool version changed")
        destination = "local?root="+str(root)
        keys = " ".join((old_key, OFFICIAL, new_key))
        base = prefix+["--extra-experimental-features","nix-command","--store",destination,
                       "--option","require-sigs","true","--option","trusted-public-keys",keys,
                       "--option","substituters","","--option","build-users-group",""]
        command("register-root",base+["copy","--from",cache.as_uri(),"--to",destination,TOP],timeout=3600)
        imported = read_json(command("destination-inventory",base+["path-info","--recursive","--json",TOP]))
        if isinstance(imported,list):
            require(len(imported)==len({r["path"] for r in imported}), "duplicate destination path")
            imported = {r["path"]:r for r in imported}
        require(set(imported)==set(rows),"registered closure differs")
        for name,row in rows.items():
            got=imported[name]
            require(got["narHash"]==row["narHash"] and got["narSize"]==row["narSize"]
                    and sorted(got["references"])==sorted(row["references"]) and got.get("ca")==row.get("ca"),
                    "registered metadata differs: "+name)
            expected_key = (NEW_KEY_NAME if name in SMALL else "cache.nixos.org-1" if name==SOURCE else old_key.split(":")[0])
            require(any(s.startswith(expected_key+":") for s in got.get("signatures",[])),
                    "registered signature missing: "+name)
            require(set(row.get("signatures",[])).issubset(got.get("signatures",[])),
                    "registered original signatures missing: "+name)
        report["root_registered"] = True
        checkpoint()
        command("verify-destination",base+["store","verify","--recursive","--sigs-needed","1",TOP],timeout=3600)
        for name,want in ENTRY_HASHES.items():
            require(sha(root/TOP.lstrip("/")/name)==want,"registered entry changed: "+name)
        db=root/"nix/var/nix/db/db.sqlite"
        require(db.is_file() and not db.is_symlink(),"independent Nix DB absent")
        report.update(complete=True,path_count=COUNT,nar_bytes=NAR_BYTES,
                      independent_db_sha256=sha(db),entry_hashes=ENTRY_HASHES,
                      destination_content_signature_verify_exit_code=0)
    except Exception as e:
        report["failure"]={"type":type(e).__name__,"message":str(e),"traceback":traceback.format_exc()}
        raise
    finally:
        report["finished_utc"]=time.strftime("%FT%TZ",time.gmtime())
        checkpoint()

if __name__ == "__main__":
    main()
