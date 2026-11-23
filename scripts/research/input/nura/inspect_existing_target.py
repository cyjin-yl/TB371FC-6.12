
import os,stat,json,hashlib,datetime,base64,gzip
from pathlib import Path,PurePosixPath
root=Path('/work/pmwork/guest-share/pmwork/chroot_rootfs_qemu-aarch64')
export_path=Path('/work/pmwork/guest-share/rootfs-export.json')
archive_path=Path('/work/pmwork/artifacts/nura-qemu-aarch64-userspace-20261123.tar.gz')
def identity(raw):return {'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
def info(path):
 s=path.lstat()
 return {'size':s.st_size,'mode':oct(stat.S_IMODE(s.st_mode)),'uid':s.st_uid,'gid':s.st_gid,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns,'kind':'file' if stat.S_ISREG(s.st_mode) else 'symlink' if stat.S_ISLNK(s.st_mode) else 'directory' if stat.S_ISDIR(s.st_mode) else 'other'}
def target(name):
 todo=list(PurePosixPath(name).parts);done=[];links=[]
 for step in range(128):
  if not todo:return root.joinpath(*done),links
  part=todo.pop(0)
  if part in ('','/','.'):continue
  if part=='..':
   if not done:raise ValueError('escape')
   done.pop();continue
  p=root.joinpath(*done,part);s=p.lstat()
  if stat.S_ISLNK(s.st_mode):
   value=os.readlink(p);links.append({'path':'/'.join(done+[part]),'target':value})
   if value.startswith('/'):done=[]
   todo=list(PurePosixPath(value).parts)+todo
  else:done.append(part)
 raise ValueError('link cap')
def member(name,as_text=False):
 try:
  p,links=target(name);r={'path':name,'resolved_path':str(p.relative_to(root)),'links':links,**info(p)}
  if r['kind']!='file':return r
  if r['size']>16*1024**2:raise ValueError('payload cap')
  raw=p.read_bytes();r.update(identity(raw))
  if as_text:
   if len(raw)>16384:raise ValueError('text cap')
   r['text']=raw.decode()
  if raw[:4]==b'\x7fELF':
   r['elf_class']=raw[4]*32;r['elf_machine']=int.from_bytes(raw[18:20],'little')
  return r
 except (OSError,ValueError,UnicodeError) as e:return {'path':name,'unavailable':str(e)}
assert root.is_dir() and not root.is_symlink()
before={p:info(root/p) for p in ('.','dev','etc')}
raw=export_path.read_bytes()
assert identity(raw)=={'size':5457,'sha256':'85aa1f9d979e92ee3c6efa40d344fdea224d6ab5b6be3dc10b65ef5b907aa0e5'}
export=json.loads(raw)
result={'schema_version':1,'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Native ordinary-file inventory only; no target program execution or archive scan','target_root':str(root),'export_record':{'path':str(export_path),**identity(raw)},'recorded_archive':export['artifact'],'current_archive_stat':info(archive_path),'archive_rehashed_now':False,'files':[],'directories':{}}
result['files']=[member(n) for n in ('sbin/init','sbin/openrc-init','sbin/openrc','sbin/rc-service','sbin/rc-status','bin/busybox','bin/sh','usr/bin/python3','usr/bin/python3.14','sbin/modprobe','usr/bin/dbus-send')]
result['files'] += [member(n,True) for n in ('etc/os-release','etc/alpine-release','etc/inittab','etc/rc.conf','etc/fstab','etc/init.d/devfs','etc/init.d/procfs','etc/init.d/sysfs','etc/init.d/cgroups','etc/init.d/udev','etc/init.d/udev-trigger','etc/init.d/udev-settle','etc/init.d/dbus','etc/init.d/networkmanager','etc/init.d/local','boot/loader/entries/pmos.conf')]
for n in ('etc/runlevels/sysinit','etc/runlevels/boot','etc/runlevels/default','boot','lib/modules'):
 try:
  p,links=target(n);items=[]
  for e in sorted(p.iterdir()):
   if len(items)>=128:raise ValueError('directory cap')
   i=info(e);v={'name':e.name,'kind':i['kind']}
   if i['kind']=='symlink':v['target']=os.readlink(e)
   items.append(v)
  result['directories'][n]={'resolved_path':str(p.relative_to(root)),'links':links,'entries':items}
 except (OSError,ValueError) as e:result['directories'][n]={'unavailable':str(e)}
result['directory_metadata_before']=before
result['directory_metadata_after']={p:info(root/p) for p in ('.','dev','etc')}
result['directory_metadata_stable']=before==result['directory_metadata_after']
payload=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
print(json.dumps({**identity(payload),'gzip_base64':base64.b64encode(gzip.compress(payload,mtime=0)).decode()},sort_keys=True))
