#!/usr/bin/env python3
"""Run the independently prepared R5 configure/build/inspection in the SSD container."""
from pathlib import Path
import argparse
import base64
import datetime
import hashlib
import json
import os
import re
import subprocess
import time

PRIVATE = Path('/tank/shared/projects/tb371fc-linux/private/research5-services-20261123')
PREFIX = '/work/research5-services'
CONTAINER = 'tb371fc-build-ssd-20261123'
BASE = ['sudo', '-n', '/usr/sbin/pct', 'exec', '102', '--', 'docker', 'exec']

INSTALL = r'''from pathlib import Path
import base64,hashlib,json,os,stat,sys
os.umask(0o077)
w=Path('/work/research5-services');dst=w/'recipe-v1'
assert w.is_dir() and not w.is_symlink() and not dst.exists()
source_record=json.loads((w/'jobs/prepare-source-01.json').read_text())
assert source_record['passed'] is True and source_record['exit_code']==0
assert source_record['source_inputs_unchanged'] is True
assert source_record['old_objects_copied'] is False and source_record['old_private_key_copied'] is False
assert not (w/'kernel-out').exists() and not (w/'configuration.json').exists()
packet=json.loads(sys.stdin.buffer.read())
assert packet['schema_version']==1
assert {x['name'] for x in packet['files']}=={'build_system.py','inspect_system.py','system.config','services-contract.json','run_job.py'}
assert len(packet['files'])==5
members=[]
for item in packet['files']:
 raw=base64.b64decode(item['base64'],validate=True)
 assert len(raw)==item['bytes'] and hashlib.sha256(raw).hexdigest()==item['sha256']
 assert item['mode'] in (0o644,0o755)
 members.append((item,raw))
dst.mkdir(mode=0o700)
readback=[]
for item,raw in members:
 p=dst/item['name']
 with p.open('xb') as f:f.write(raw)
 p.chmod(item['mode']);s=p.lstat()
 assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==item['mode']
 assert p.read_bytes()==raw
 readback.append({k:v for k,v in item.items() if k!='base64'})
record={'schema_version':1,'files':readback,'all_byte_and_mode_verified':True,'source_preparation_passed':True,
 'old_objects_copied':False,'old_private_key_copied':False,'vm_started':False,'physical_hardware_tested':False}
with (w/'recipe-install.json').open('x') as f:json.dump(record,f,indent=2,sort_keys=True);f.write('\n')
print(json.dumps(record,sort_keys=True))
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(name, record):
    with (PRIVATE / name).open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')


def call(label, arguments, *, data=None):
    command = BASE + (['-i'] if data is not None else []) + [CONTAINER, *arguments]
    record = {'command': command, 'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    started = time.monotonic()
    out, err = PRIVATE / (label + '.stdout'), PRIVATE / (label + '.stderr')
    with out.open('xb') as stdout, err.open('xb') as stderr:
        child = subprocess.Popen(command, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                 stdout=stdout, stderr=stderr)
        record['child_pid'] = child.pid
        if data is not None:
            child.communicate(data)
            code = child.returncode
        else:
            code = child.wait()
    for name, path in [('stdout', out), ('stderr', err)]:
        with path.open('rb') as stream:
            record[name] = {'bytes': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    record.update({'exit_code': code, 'elapsed_seconds': time.monotonic() - started,
                   'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save(label + '.json', record)
    print(json.dumps({'phase': label, 'exit_code': code, 'elapsed_seconds': record['elapsed_seconds']}, sort_keys=True), flush=True)
    if code:
        raise RuntimeError(label + ' failed; exact records retained')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-sha256', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    assert re.fullmatch('[0-9a-f]{64}', args.packet_sha256)
    assert PRIVATE.is_dir() and not (PRIVATE / 'build-driver-result.json').exists()
    report = {'schema_version': 1, 'start_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'kernel_release': '6.12.114-tb371fc-research5-services', 'completed': False,
              'old_objects_copied': False, 'old_private_key_copied': False,
              'virtual_machine_started': False, 'physical_hardware_tested': False, 'phases': []}
    started = time.monotonic()
    code = 1
    try:
        packet = (PRIVATE / 'recipe-packet.json').read_bytes()
        assert sha(packet) == args.packet_sha256
        report['source_packet'] = {'bytes': len(packet), 'sha256': sha(packet)}
        report['phases'].append(call('install-recipe', ['python3', '-c', INSTALL], data=packet))
        for phase in ('configure', 'build', 'inspect'):
            runner = ['python3', PREFIX + '/recipe-v1/run_job.py', '--work', PREFIX + '/jobs', '--name', phase + '-01', '--']
            if phase == 'inspect':
                command = ['python3', PREFIX + '/recipe-v1/inspect_system.py', '--work', PREFIX,
                           '--repo', '/src', '--baseline-repo', '/work/research2-repo', '--attempt', '1']
            else:
                command = ['python3', PREFIX + '/recipe-v1/build_system.py', phase, '--work', PREFIX, '--jobs', '4', '--attempt', '1']
            report['phases'].append(call(phase + '-invocation', runner + command))
        report['completed'] = True
        code = 0
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        report.update({'exit_code': code, 'elapsed_seconds': time.monotonic() - started,
                       'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'driver_sha256': sha(Path(__file__).read_bytes())})
        save('build-driver-result.json', report)
        print(json.dumps({k: report.get(k) for k in ('completed', 'exit_code', 'elapsed_seconds', 'error')}, sort_keys=True), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
