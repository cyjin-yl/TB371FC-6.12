set -uo pipefail
docker exec tb371fc-build-20261123 bash -lc 'set -eu
test ! -e /work/r5-novatek-runtime-export-c1296-01/public-tools-source.stderr
set +e
timeout --signal=TERM --kill-after=10s 600s tar --sort=name --format=posix --pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime --numeric-owner --acls --selinux --xattrs --xattrs-include='\''*'\'' -cf - -C /work '\''fedora-system-integration-v1/fedora-system-integration.json'\'' '\''fedora-system-integration-v1/runtime.json'\'' '\''fedora-system-integration-v1/vm-verify-01/result.json'\'' '\''fedora-proot-src/src/proot'\'' '\''fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu'\'' 2>/work/r5-novatek-runtime-export-c1296-01/public-tools-source.stderr
novatek_public_source=$?
printf '\''%s\n'\'' "$novatek_public_source" >/work/r5-novatek-runtime-export-c1296-01/public-tools-source.exit
exit "$novatek_public_source"' | docker exec -i tb371fc-build-ssd-20261123 python3 -B -c 'from pathlib import Path
import hashlib,json,subprocess,datetime,os
names=['\''fedora-system-integration-v1'\'','\''fedora-proot-src'\'','\''fedora-host-tools'\'']
base=Path('\''/work'\'');work=base/'\''r5-novatek-public-tools-c1296-01'\'';pins={"fedora-system-integration-v1/fedora-system-integration.json":"66ac854b2bc938aed147afe0355b57fcbba856c874e9d82cec4cad663b1c87d9","fedora-system-integration-v1/runtime.json":"10a373bfc3291aabe564c8f7af90265900763eadfe3167a7384cc4dcd596544b","fedora-system-integration-v1/vm-verify-01/result.json":"223f73b253a48995dd238575e64aad055e11f311c658aa03534b49c570095675","fedora-proot-src/src/proot":"313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f"}
for n in names:
 p=base/n
 if p.exists() or p.is_symlink():raise RuntimeError('\''destination already exists: '\''+str(p))
work.mkdir(mode=0o700)
report={'\''schema'\'':'\''tb371fc-public-tool-copy-v1'\'','\''started_utc'\'':datetime.datetime.now(datetime.timezone.utc).isoformat(),'\''complete'\'':False,'\''inputs'\'':{},'\''copied_private_key'\'':False}
try:
 tree=work/'\''tree'\'';tree.mkdir()
 argv=['\''timeout'\'','\''--signal=TERM'\'','\''--kill-after=10s'\'','\''660s'\'','\''tar'\'','\''--extract'\'','\''--file'\'','\''-'\'','\''--directory'\'',str(tree),'\''--numeric-owner'\'','\''--same-owner'\'','\''--same-permissions'\'','\''--acls'\'','\''--selinux'\'','\''--xattrs'\'','\''--xattrs-include=*'\'','\''--delay-directory-restore'\'']
 with (work/'\''extract.stdout'\'').open('\''xb'\'') as o,(work/'\''extract.stderr'\'').open('\''xb'\'') as e:
  result=subprocess.run(argv,stdout=o,stderr=e,check=False)
 report['\''extract_exit_code'\'']=result.returncode
 if result.returncode or (work/'\''extract.stderr'\'').stat().st_size:raise RuntimeError('\''public tool extraction failed or emitted diagnostics'\'')
 for rel,expected in pins.items():
  p=tree/rel
  if p.is_symlink() or not p.is_file():raise RuntimeError('\''regular pinned file required'\'')
  b=p.read_bytes();actual=hashlib.sha256(b).hexdigest()
  if actual!=expected:raise RuntimeError('\''public pin mismatch: '\''+rel)
  report['\''inputs'\''][rel]={'\''bytes'\'':len(b),'\''sha256'\'':actual,'\''mode'\'':p.stat().st_mode&0o777}
 libs=tree/'\''fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu'\''
 if libs.is_symlink() or not libs.is_dir():raise RuntimeError('\''ordinary library directory required'\'')
 report['\''host_library_entries'\'']=sum(1 for p in libs.rglob('\''*'\''))
 for n in names:
  if (base/n).exists() or (base/n).is_symlink():raise RuntimeError('\''destination appeared during copy'\'')
 for n in names:os.rename(tree/n,base/n)
 report['\''complete'\'']=True
except BaseException as e:
 report['\''failure'\'']={'\''type'\'':type(e).__name__,'\''message'\'':str(e)}
 raise
finally:
 report['\''finished_utc'\'']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 with (work/'\''receipt.json'\'').open('\''x'\'') as f:json.dump(report,f,indent=2);f.write('\''\n'\'')
 print(json.dumps(report))
'
novatek_public_pipe=("${PIPESTATUS[@]}")
docker exec tb371fc-build-ssd-20261123 python3 -c 'from pathlib import Path
import json,sys,datetime
p=Path('\''/work/r5-novatek-public-tools-c1296-01/pipeline.json'\'')
with p.open('\''x'\'') as f:json.dump({'\''finished_utc'\'':datetime.datetime.now(datetime.timezone.utc).isoformat(),'\''source_exit_code'\'':int(sys.argv[1]),'\''receiver_exit_code'\'':int(sys.argv[2])},f,indent=2);f.write('\''\n'\'')' "${novatek_public_pipe[0]}" "${novatek_public_pipe[1]}"
test "${novatek_public_pipe[0]}" -eq 0 && test "${novatek_public_pipe[1]}" -eq 0