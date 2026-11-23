#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Retain bounded raw R5 text evidence; no Image, module, firmware or key payload."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os

PRIVATE = Path('/tank/shared/projects/tb371fc-linux/private/research5-services-20261123')
DRIVER_SHA = '0d0e9fe0c62f962ed123d3bafed407a901f2b4af9e52accfa301e544db7d6630'
REPORT_SHA = '69d0b558c99bdfb339df8b3b9baca8bb1ee4d0cb2e46dd9b3b7fef3ab69aaad2'

COLLECT = r'''from pathlib import Path
import base64,hashlib,json,os,stat,zlib
root=Path('/work/research5-services')
output=root/'public-records-v1'
assert not output.exists() and not output.is_symlink()
report=(root/'artifacts/research5-services-build.json').read_bytes()
assert hashlib.sha256(report).hexdigest()=='69d0b558c99bdfb339df8b3b9baca8bb1ee4d0cb2e46dd9b3b7fef3ab69aaad2'
parsed=json.loads(report)
assert parsed['passed'] is True and parsed['module_count']==84
names=['artifacts/research5-services-build.json','artifacts/qualified-artifacts.SHA256SUMS',
 'artifacts/kernel.config','artifacts/builder-packages.tsv','artifacts/modules.SHA256SUMS',
 'configuration.json','source-manifest.json','source-input/source-manifest.json',
 'configure-attempt-01.json','build-attempt-01.json','inspection-attempt-01.json','recipe-install.json']
for phase in ['prepare-source-01','configure-01','build-01','inspect-01']:
 names.extend(['jobs/'+phase+'.json','jobs/'+phase+'.log'])
assert len(names)==len(set(names))==20
members=[]
for name in sorted(names):
 p=root/name;fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
 try:
  before=os.fstat(fd)
  assert stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0 and 0<=before.st_size<=4*1024**2,name
  with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read()
  after=os.fstat(fd)
  stable=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
  assert stable(before)==stable(after) and len(raw)==before.st_size,name
  raw.decode('utf-8')
  if name.endswith('.json'):json.loads(raw)
  members.append({'path':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
   'mode':stat.S_IMODE(before.st_mode),'base64':base64.b64encode(raw).decode()})
 finally:os.close(fd)
manifest={'schema_version':1,'kernel_report_sha256':hashlib.sha256(report).hexdigest(),
 'member_count':len(members),'members':[{k:v for k,v in row.items() if k!='base64'} for row in members],
 'raw_bytes_preserved':True,'binary_artifacts_included':False,'private_key_read':False,
 'firmware_included':False,'physical_hardware_tested':False}
packet=(json.dumps({'schema_version':1,'manifest':manifest,'members':members},sort_keys=True,separators=(',',':'))+'\n').encode()
compressed=zlib.compress(packet,9)
os.umask(0o077);output.mkdir(mode=0o700)
for name,raw in [('packet.zlib',compressed),('manifest.json',(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())]:
 with (output/name).open('xb') as f:f.write(raw)
 assert (output/name).read_bytes()==raw
print(json.dumps({'output':str(output),'packet_bytes':len(packet),'packet_sha256':hashlib.sha256(packet).hexdigest(),
 'compressed_bytes':len(compressed),'compressed_sha256':hashlib.sha256(compressed).hexdigest(),
 'member_count':len(members),'physical_hardware_tested':False},sort_keys=True))
'''


def main():
    os.umask(0o077)
    driver = PRIVATE / 'run_build.py'
    assert hashlib.sha256(driver.read_bytes()).hexdigest() == DRIVER_SHA
    prior = json.loads((PRIVATE / 'build-driver-result.json').read_bytes())
    assert prior['completed'] is True and prior['exit_code'] == 0
    spec = importlib.util.spec_from_file_location('tb371fc_r5_record_driver', driver)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.call('collect-public-01', ['python3', '-B', '-c', COLLECT])
    print(json.dumps({'capture_exit_code': result['exit_code'], 'kernel_report_sha256': REPORT_SHA,
                      'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}), flush=True)


if __name__ == '__main__':
    main()
