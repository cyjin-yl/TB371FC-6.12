set -uo pipefail
docker exec tb371fc-build-20261123 bash -lc 'set -eu
mkdir -m 700 /work/r5-novatek-runtime-export-c1296-01
set +e
timeout --signal=TERM --kill-after=10s 3600s tar --sort=name --format=posix --pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime --numeric-owner --acls --selinux --xattrs --xattrs-include='\''*'\'' -cf - -C /work/fedora-system-integration-v1/rootfs . 2>/work/r5-novatek-runtime-export-c1296-01/source.stderr
novatek_source_status=$?
printf '\''%s\n'\'' "$novatek_source_status" >/work/r5-novatek-runtime-export-c1296-01/source.exit
exit "$novatek_source_status"' | docker exec -i tb371fc-build-ssd-20261123 env PYTHONDONTWRITEBYTECODE=1 python3 -u /work/r5-novatek-runtime-receiver-c1296-01.py --receive-timeout 3650 --extract-timeout 600
novatek_pipe_status=("${PIPESTATUS[@]}")
docker exec tb371fc-build-ssd-20261123 python3 -c 'from pathlib import Path
import json,sys,datetime
p=Path('\''/work/r5-novatek-runtime-transfer-pipeline-c1296-01.json'\'')
r={'\''schema'\'':'\''tb371fc-runtime-copy-pipeline-v1'\'','\''finished_utc'\'':datetime.datetime.now(datetime.timezone.utc).isoformat(),'\''source_exit_code'\'':int(sys.argv[1]),'\''receiver_exit_code'\'':int(sys.argv[2]),'\''source_container'\'':'\''tb371fc-build-20261123'\'','\''receiver_container'\'':'\''tb371fc-build-ssd-20261123'\'','\''source_directory'\'':'\''/work/fedora-system-integration-v1/rootfs'\'','\''receiver_source_sha256'\'':'\''63cb331c63ca2fd1e659811fefa614955e0fdd6a331aaa7b873370e478cdc1c2'\'','\''source_stream_timeout_seconds'\'':3600,'\''target_gate_timeout_changed'\'':False}
with p.open('\''x'\'') as f:json.dump(r,f,indent=2);f.write('\''\n'\'')
print(json.dumps(r))' "${novatek_pipe_status[0]}" "${novatek_pipe_status[1]}"
test "${novatek_pipe_status[0]}" -eq 0 && test "${novatek_pipe_status[1]}" -eq 0
