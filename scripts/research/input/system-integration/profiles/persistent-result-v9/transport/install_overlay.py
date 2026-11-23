
import base64,gzip,hashlib,io,json,os,stat,subprocess,sys,tarfile
from pathlib import Path,PurePosixPath
root=Path('/work/fedora-r4f-source-overlay-v1')
recipe=Path('/work/fedora-input-system-recipe-r4-v7')
work=Path('/work/fedora-input-system-v9')
expected_recipe='927fd0755f54f303adac25daa8342bfe4615d0d42ff9a07361d29226f7cdf947'
if root.exists() or root.is_symlink() or recipe.exists() or recipe.is_symlink():raise ValueError('fresh overlay and recipe required')
q=work/'baseline-copy-qualification.json'
assert q.is_file() and not q.is_symlink() and hashlib.sha256(q.read_bytes()).hexdigest()=='aea118880abaff3eee5c7aafc311f614d6c4f897308e6216e93e36c9ae964143'
assert not any((work/n).exists() for n in ('pipeline-command.json','pipeline.log','pipeline.exit.json'))
packet=base64.b64decode(sys.argv[1],validate=True)
assert len(packet)==82271 and hashlib.sha256(packet).hexdigest()=='05ddecf0957fb1b4f8201a521543979d72d603402061363dc048a2d8922b470c'
raw=gzip.decompress(packet)
assert len(raw)<2*1024**2
archive=tarfile.open(fileobj=io.BytesIO(raw),mode='r:')
members=archive.getmembers()
assert len(members)==26 and len({m.name for m in members})==26
manifest_member=archive.getmember('upload-manifest.json')
manifest=json.loads(archive.extractfile(manifest_member).read())
assert len(manifest)==25 and set(manifest)|{'upload-manifest.json'}=={m.name for m in members}
values={}
for m in members:
 p=PurePosixPath(m.name)
 assert m.isfile() and not p.is_absolute() and str(p)==m.name and '..' not in p.parts and m.size<=256*1024 and m.mode in (0o644,0o755)
 body=archive.extractfile(m).read()
 if m.name!='upload-manifest.json':
  assert {'size':len(body),'sha256':hashlib.sha256(body).hexdigest(),'mode':m.mode}==manifest[m.name]
  if m.name.endswith('.py'):compile(body,m.name,'exec')
 values[m.name]=(body,m.mode)
root.mkdir()
for name,(body,mode) in values.items():
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(body)
 p.chmod(mode)
 assert p.read_bytes()==body
profile=root/'scripts/research/input/system-integration/profiles/persistent-result-v9'
command=['python3',str(profile/'materialize_recipe.py'),'--repo',str(root)]
result=subprocess.run(command,capture_output=True,text=True,timeout=20)
record={'schema_version':1,'packet_size':len(packet),'packet_sha256':hashlib.sha256(packet).hexdigest(),'file_count':len(manifest),'source_readback_verified':True,'command':command,'materializer_exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'recipe':str(recipe),'physical_tablet_tested':False}
if result.returncode==0:
 raw=(recipe/'recipe-manifest.json').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==expected_recipe
 items=json.loads(raw)
 assert len(items)==20
 for name,ident in items.items():
  p=recipe/name;assert p.is_file() and not p.is_symlink()
  b=p.read_bytes();assert ident=={'size':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 record.update({'recipe_manifest_sha256':expected_recipe,'recipe_files_readback_verified':True,'recipe_file_count':len(items)})
with (root/'materialization-readback.json').open('x') as f:json.dump(record,f,sort_keys=True,indent=2);f.write('\n')
print(json.dumps(record,sort_keys=True))
if result.returncode:raise SystemExit(result.returncode)
