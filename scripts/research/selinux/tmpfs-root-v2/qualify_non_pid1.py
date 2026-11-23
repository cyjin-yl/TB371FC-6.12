from pathlib import Path
import datetime,hashlib,json,os,subprocess,time
r=Path('/work/tmpfs-waiter-v2-20261123')
b=json.loads((r/'build-01/build-result.json').read_text())
p=r/'build-01/init.tmpfs-wait';raw=p.read_bytes()
assert os.getpid()!=1 and len(raw)==b['elf']['size'] and hashlib.sha256(raw).hexdigest()==b['elf']['sha256']
qemu=Path('/usr/bin/qemu-aarch64')
assert hashlib.sha256(qemu.read_bytes()).hexdigest()=='73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943'
runtime=Path('/work/fedora-input-system-v3/rootfs')
libs={}
for rel in ['usr/lib64/libc.so.6','usr/lib/ld-linux-aarch64.so.1']:
 f=runtime/rel;data=f.read_bytes();libs[rel]={'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
cmd=[str(qemu),'-L',str(runtime),str(p)]
start=time.monotonic();v=subprocess.run(cmd,capture_output=True,timeout=8);elapsed=time.monotonic()-start
expected=b'TB371FC_TMPFS_STAGE1_V2 FAILED phase=entry reason=pid1-root-with-no-arguments-required errno=0\n'
ok=v.returncode==1 and v.stdout==b'' and v.stderr==expected
record={'schema_version':1,'scope':'same-baseline ARM user-emulation non-PID1 rejection only','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'passed':ok,'command':cmd,'exit_code':v.returncode,'elapsed_seconds':elapsed,'stdout':v.stdout.decode(errors='replace'),'stderr':v.stderr.decode(errors='replace'),'expected_stderr':expected.decode(),'target':{'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()},'runtime_root':str(runtime),'runtime_libraries':libs,'qemu_sha256':hashlib.sha256(qemu.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'proot_used':False,'mount_operation_performed':False,'policy_load_attempted':False,'pid1_executed':False,'virtual_machine_started':False,'physical_hardware_tested':False}
assert p.read_bytes()==raw
with (r/'non-pid1-result.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(record,indent=2,sort_keys=True))
raise SystemExit(0 if ok else 1)
