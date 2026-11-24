#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Observe the pinned V4 helper's direct non-PID1 refusal; never run it as init."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

ARTIFACT=Path('/work/early-selinux-socket-probe-20261123/build-01/early-init')
REFERENCE=Path('/work/fedora-input-system-v6/rootfs')
QEMU=Path('/usr/bin/qemu-aarch64')
QEMU_SHA='73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943'


def metadata():
    result={}
    for name in ('.','etc','dev'):
        info=(REFERENCE/name).lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('ordinary reference directory required')
        result[name]={'inode':info.st_ino,'mtime_ns':info.st_mtime_ns,'ctime_ns':info.st_ctime_ns}
    return result


def sysctls():
    return {name:Path('/proc/sys/kernel',name).read_text().strip()
            for name in ('printk_ratelimit','printk_ratelimit_burst')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha256',required=True)
    parser.add_argument('--size',type=int,required=True)
    parser.add_argument('--result',type=Path,required=True)
    args=parser.parse_args()
    if (os.geteuid()!=0 or os.getpid()==1 or
        args.result!=ARTIFACT.parent.parent/'negative-nonpid1.json' or args.result.exists()):
        raise ValueError('fixed new negative result and non-PID1 root invocation required')
    info=ARTIFACT.lstat();raw=ARTIFACT.read_bytes()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or stat.S_IMODE(info.st_mode)!=0o755 or
        len(raw)!=args.size or hashlib.sha256(raw).hexdigest()!=args.sha256):
        raise ValueError('artifact identity differs')
    if hashlib.sha256(QEMU.read_bytes()).hexdigest()!=QEMU_SHA:
        raise ValueError('QEMU user binary differs')
    before,settings=metadata(),sysctls()
    command=[str(QEMU),'-L',str(REFERENCE),str(ARTIFACT)]
    at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    started=time.monotonic()
    child=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,timeout=20)
    elapsed=time.monotonic()-started
    after,settings_after=metadata(),sysctls()
    expected=b'TB371FC_EARLY_SELINUX_V4 FAILED phase=entry reason=pid1-with-no-arguments-required errno=0\n'
    passed=(child.returncode==1 and child.stdout==b'' and child.stderr==expected and
            before==after and settings==settings_after and ARTIFACT.read_bytes()==raw)
    record={'schema_version':1,'at_utc':at,
        'scope':'direct AArch64 non-PID1 refusal only; no API-only check or PID1 execution',
        'artifact':{'size':len(raw),'sha256':args.sha256},'qualifier_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'command':command,'exit_code':child.returncode,'elapsed_seconds':elapsed,
        'stdout':child.stdout.decode(errors='replace'),'stderr':child.stderr.decode(errors='replace'),
        'reference_directory_metadata_before':before,'reference_directory_metadata_after':after,
        'container_sysctl_values_before':settings,'container_sysctl_values_after':settings_after,
        'passed':passed,'audit_sysctl_guard_reached':False,'policy_load_attempted':False,
        'mount_operation_attempted':False,'sysctl_write_attempted':False,'physical_hardware_tested':False,
        'limit':'The exact failure marker and fixed source entry order identify the refused branch. Sampled metadata is limited corroboration, not a full syscall trace or a VM result.'}
    with args.result.open('x') as stream:
        json.dump(record,stream,sort_keys=True,indent=2);stream.write('\n')
    args.result.chmod(0o600)
    print(json.dumps(record,sort_keys=True,indent=2),flush=True)
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
