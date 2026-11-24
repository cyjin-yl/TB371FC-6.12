#!/usr/bin/env python3
"""Build the pinned V4 loader in the SSD container, retain it in HDD, and check non-PID1 refusal."""
import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

PRIVATE=Path('/tank/shared/projects/tb371fc-linux/private/early-selinux-socket-probe-20261123')
PREFIX='/work/early-selinux-socket-probe-20261123'
HDD='tb371fc-build-20261123'
SSD='tb371fc-build-ssd-20261123'
BASE=['sudo','-n','/usr/sbin/pct','exec','102','--','docker','exec']


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name,value):
    with (PRIVATE/name).open('x') as stream:
        json.dump(value,stream,indent=2,sort_keys=True);stream.write('\n')
    (PRIVATE/name).chmod(0o600)


def call(label,container,argv,*,data=None,timeout=120):
    command=BASE+(['-i'] if data is not None else [])+[container,*argv]
    started=time.monotonic();at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    value=subprocess.run(command,input=data,capture_output=True,timeout=timeout)
    for suffix,raw in [('stdout',value.stdout),('stderr',value.stderr)]:
        path=PRIVATE/(label+'.'+suffix)
        with path.open('xb') as stream:stream.write(raw)
        path.chmod(0o600)
    record={'command':command,'started_utc':at,'finished_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'seconds':time.monotonic()-started,'exit_code':value.returncode,
            'stdout_bytes':len(value.stdout),'stdout_sha256':sha(value.stdout),
            'stderr_bytes':len(value.stderr),'stderr_sha256':sha(value.stderr)}
    save(label+'.json',record)
    print(json.dumps({'phase':label,'exit_code':value.returncode,'seconds':record['seconds']}),flush=True)
    if value.returncode:
        raise RuntimeError(label+' failed; exact output retained')
    return value.stdout


INSTALL=r'''from pathlib import Path
import base64,hashlib,json,os,stat,sys
root=Path('/work/early-selinux-socket-probe-20261123')
packet=json.loads(sys.stdin.buffer.read())
assert not root.exists() and not root.is_symlink()
assert packet['schema_version']==1
members=[]
seen=set()
for item in packet['files']:
 name=item['name'];p=Path(name)
 assert not p.is_absolute() and '..' not in p.parts and name not in seen
 assert str(p)==name and len(p.parts)<=2
 seen.add(name);raw=base64.b64decode(item['base64'],validate=True)
 assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
 assert item['mode'] in (0o600,0o644,0o755)
 members.append((item,raw))
root.mkdir(mode=0o700)
out=[]
for item,raw in members:
 p=root/item['name'];p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 with p.open('xb') as stream:stream.write(raw)
 p.chmod(item['mode']);s=p.lstat()
 assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0
 assert p.read_bytes()==raw
 out.append({k:v for k,v in item.items() if k!='base64'})
print(json.dumps({'files':out,'all_byte_verified':True,'kernel_policy_load_attempted':False,'vm_started':False}))
'''


def member(name,raw,mode):
    return {'name':name,'bytes':len(raw),'sha256':sha(raw),'mode':mode,'base64':base64.b64encode(raw).decode()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-sha256',required=True)
    args=parser.parse_args()
    os.umask(0o077)
    report={'schema_version':1,'completed':False,'physical_hardware_tested':False,
            'kernel_policy_loaded':False,'vm_started':False,
            'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    started=time.monotonic();exit_code=1
    try:
        raw=(PRIVATE/'source-packet.json').read_bytes()
        assert sha(raw)==args.packet_sha256 and re.fullmatch('[0-9a-f]{64}',args.packet_sha256)
        packet=json.loads(raw);policy=packet['policy']
        assert packet['schema_version']==1 and len(packet['files'])==4
        assert policy['path']=='/work/selinux-socket-probe-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35'
        assert re.fullmatch('[0-9a-f]{64}',policy['sha256']) and 3000000<policy['bytes']<5000000
        code=('from pathlib import Path\nimport hashlib,stat,sys\np=Path('+repr(policy['path'])+')\n'
              's=p.lstat();b=p.read_bytes()\nassert stat.S_ISREG(s.st_mode) and s.st_uid==0\n'
              'assert len(b)=='+str(policy['bytes'])+' and hashlib.sha256(b).hexdigest()=='+repr(policy['sha256'])+'\n'
              'sys.stdout.buffer.write(b)\n')
        blob=call('policy-source',HDD,['python3','-c',code],timeout=30)
        assert len(blob)==policy['bytes'] and sha(blob)==policy['sha256']
        sources=packet['files']+[member('input-policy.35',blob,0o644)]
        installed=call('input-transfer',SSD,['python3','-c',INSTALL],
                       data=json.dumps({'schema_version':1,'files':sources}).encode(),timeout=60)
        report['input_transfer']=json.loads(installed)
        command=['python3',PREFIX+'/recipe-v1/build_early_init_v4.py',
                 '--repo','/work/early-selinux-bootstrap-20261123/recipe-v1/repo',
                 '--policy',PREFIX+'/input-policy.35','--policy-sha256',policy['sha256'],
                 '--policy-size',str(policy['bytes']),'--work',PREFIX+'/build-01',
                 '--header-cache','/work/early-selinux-bootstrap-20261123']
        built=call('build-invocation',SSD,command,timeout=120)
        outcome=json.loads(built)
        assert outcome['completed'] is True and outcome['compile_exit_code']==0
        artifact=outcome['artifact']
        assert artifact['path']==PREFIX+'/build-01/early-init' and artifact['mode']=='0755'
        report['build']=outcome
        export=r'''from pathlib import Path
import base64,hashlib,json,stat
root=Path('/work/early-selinux-socket-probe-20261123')
files=[]
for parent in ('recipe-v1','build-01'):
 for p in sorted((root/parent).iterdir()):
  s=p.lstat()
  if stat.S_ISDIR(s.st_mode):
   assert parent=='build-01' and p.name=='headers';continue
  assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_size<1024**2
  b=p.read_bytes();files.append({'name':str(p.relative_to(root)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'mode':stat.S_IMODE(s.st_mode),'base64':base64.b64encode(b).decode()})
print(json.dumps({'schema_version':1,'files':files}))
'''
        transfer=call('ssd-artifacts',SSD,['python3','-c',export],timeout=30)
        bundle=json.loads(transfer)
        outputs={item['name']:item for item in bundle['files']}
        assert outputs['build-01/early-init']['sha256']==artifact['sha256']
        assert outputs['build-01/early-init']['bytes']==artifact['size']
        hdd=call('hdd-transfer',HDD,['python3','-c',INSTALL],data=transfer,timeout=60)
        report['hdd_transfer']=json.loads(hdd)
        negative=call('negative-invocation',HDD,['python3',PREFIX+'/recipe-v1/qualify_non_pid1.py',
            '--sha256',artifact['sha256'],'--size',str(artifact['size']),
            '--result',PREFIX+'/negative-nonpid1.json'],timeout=45)
        report['negative']=json.loads(negative)
        assert report['negative']['passed'] is True
        report.update({'completed':True,'waiter_v2_size_compatible':artifact['size']==72528,
                       'artifact':artifact})
        exit_code=0
    except Exception as error:
        report['error']={'type':type(error).__name__,'message':str(error)}
    finally:
        report.update({'seconds':time.monotonic()-started,'exit_code':exit_code,
            'finished_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'driver_sha256':sha(Path(__file__).read_bytes())})
        save('driver-result.json',report)
        print(json.dumps({k:report.get(k) for k in ('completed','exit_code','seconds','artifact','error')}),flush=True)
    raise SystemExit(exit_code)


if __name__=='__main__':
    main()
