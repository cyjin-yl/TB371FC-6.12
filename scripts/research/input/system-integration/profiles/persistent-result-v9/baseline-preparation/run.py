import datetime,json,pathlib,subprocess,time
p=pathlib.Path('/work/fedora-r4f-baseline-recipe-v1')
command=['python3',str(p/'prepare_baseline.py'),'--copy-helper',str(p/'copy_local_baseline.py'),'--runtime-helper',str(p/'reuse_verified_runtime.py')]
r={'command':command,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'new_vm_started':False,'scope':'native quiescent copy and qualified unchanged R4 runtime only'}
t=time.monotonic()
with (p/'stdout.log').open('xb') as out,(p/'stderr.log').open('xb') as err:
 try:
  value=subprocess.run(command,stdout=out,stderr=err,timeout=3600)
  r['exit_code']=value.returncode
 except Exception as error:r.update(exit_code=None,error={'type':type(error).__name__,'message':str(error)})
r.update(finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-t)
with (p/'exit.json').open('x') as f:json.dump(r,f,sort_keys=True,indent=2);f.write('\n')
raise SystemExit(0 if r['exit_code']==0 else 1)
