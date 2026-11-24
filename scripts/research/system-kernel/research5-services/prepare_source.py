#!/usr/bin/env python3
"""Reproduce the frozen source inputs in a fresh SSD-container R5 directory.

The host is an orchestrator only. No old build objects or private signing key
are copied, and no target device, VM, or module is operated on.
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import time

PRIVATE = Path('/tank/shared/projects/tb371fc-linux/private/research5-services-20261123')
CONTAINER = 'tb371fc-build-ssd-20261123'
BASE = ['sudo', '-n', '/usr/sbin/pct', 'exec', '102', '--', 'docker', 'exec']

PREPARE = r'''from pathlib import Path
import datetime, hashlib, json, os, shutil, subprocess, time
os.umask(0o077)
w=Path('/work/research5-services')
r4=Path('/work/research4-system')
h=r4/'source-input/input-recipe/scripts/research/input/prepare_input.py'
def sha(p):
 with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def ident(p):
 p=Path(p);return {'bytes':p.stat().st_size,'sha256':sha(p)}
def save(p,d):
 with Path(p).open('x') as f: json.dump(d,f,indent=2,sort_keys=True);f.write('\n')
assert not w.exists() and not w.is_symlink()
pins={h:'0f3334412a7711d3a38d4bfdb0b0b5a35f5a5cb97c1d65868155d34e0c966059',
 r4/'artifacts/kernel.config':'0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275',
 r4/'artifacts/signing-cert.der':'da222772fe59edc2d0efc6826ff4c31504ee9420b057121cd0a2e2503d81788d',
 r4/'source-input/source-manifest.json':'5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0'}
assert all(sha(p)==s for p,s in pins.items())
assert shutil.disk_usage('/work').free > 30*1024**3
w.mkdir(mode=0o700);(w/'jobs').mkdir(mode=0o700);(w/'baseline-r4').mkdir(mode=0o700)
record={'schema_version':1,'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'old_objects_copied':False,'old_private_key_copied':False,'physical_hardware_tested':False,
 'virtual_machine_started':False,'original_source_helper':ident(h),'passed':False}
started=time.monotonic();code=1
try:
 originals={}
 for name in ('kernel.config','signing-cert.der','modules.SHA256SUMS','research4-system-build.json'):
  p=r4/'artifacts'/name;raw=p.read_bytes();dst=w/'baseline-r4'/name
  with dst.open('xb') as f:f.write(raw)
  dst.chmod(0o600);assert dst.read_bytes()==raw
  originals[name]={'source_path':str(p),**ident(dst)}
 record['baseline_r4']=originals
 command=['python3',str(h),'--repo',str(r4/'source-input/input-recipe'),
  '--baseline-repo','/work/research2-repo','--baseline-work','/work/research2-display',
  '--work',str(w/'source-input'),'--cache','/work/downloads/linux-6.12.114.tar.xz']
 record['command']=command
 print('COMMAND '+json.dumps(command),flush=True)
 with (w/'jobs/prepare-source-01.log').open('x') as log:
  child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
  record['child_pid']=child.pid
  for line in child.stdout:
   log.write(line);log.flush();print(line,end='',flush=True)
  code=child.wait()
 record['exit_code']=code
 if code:raise RuntimeError('frozen input preparation failed')
 manifest=w/'source-input/source-manifest.json'
 assert sha(manifest)=='5beb548c33bad0f487241984097216f33a478719826f368d34fb50d04304cdf0'
 assert not (w/'kernel-out').exists()
 assert all(ident(r4/'artifacts'/name)=={k:v for k,v in meta.items() if k!='source_path'} for name,meta in originals.items())
 record['reproduced_manifest']=ident(manifest)
 record['source_inputs_unchanged']=True;record['passed']=True;code=0
except Exception as exc:
 record['error']={'type':type(exc).__name__,'message':str(exc)};code=1
finally:
 record.update({'exit_code':code,'elapsed_seconds':time.monotonic()-started,
  'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()})
 save(w/'jobs/prepare-source-01.json',record)
 print(json.dumps(record,sort_keys=True),flush=True)
raise SystemExit(code)
'''


def main():
    os.umask(0o077)
    result_path = PRIVATE / 'prepare-driver-result.json'
    stdout_path = PRIVATE / 'prepare-driver.stdout'
    stderr_path = PRIVATE / 'prepare-driver.stderr'
    assert PRIVATE.is_dir() and not any(p.exists() for p in (result_path, stdout_path, stderr_path))
    command = BASE + [CONTAINER, 'python3', '-c', PREPARE]
    record = {'schema_version': 1, 'command': command,
              'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'physical_hardware_tested': False}
    started = time.monotonic()
    with stdout_path.open('xb') as out, stderr_path.open('xb') as err:
        child = subprocess.Popen(command, stdout=out, stderr=err)
        record['child_pid'] = child.pid
        code = child.wait()
    record.update({'exit_code': code, 'elapsed_seconds': time.monotonic() - started,
                   'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    for suffix, path in (('stdout', stdout_path), ('stderr', stderr_path)):
        raw = path.read_bytes()
        record[suffix] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    with result_path.open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({k: record[k] for k in ('exit_code', 'elapsed_seconds', 'stdout', 'stderr')}, sort_keys=True), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
