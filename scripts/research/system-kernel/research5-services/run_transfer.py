#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run and retain one new R5 public-runtime transfer in a real doesvm tmux pane."""
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

PRIVATE = Path('/tank/shared/projects/tb371fc-linux/private/research5-services-transfer-20261123')
CT_RECIPE = '/var/tmp/tb371fc-r5-services-transfer-v1'
BASE = ['sudo', '-n', '/usr/sbin/pct', 'exec', '102', '--']
INSTALL = r'''from pathlib import Path
import base64,hashlib,json,os,stat,sys
root=Path('/var/tmp/tb371fc-r5-services-transfer-v1')
assert not root.exists() and not root.is_symlink()
packet=json.loads(sys.stdin.buffer.read())
assert packet['schema_version']==1 and len(packet['files'])==2
assert {x['name'] for x in packet['files']}=={'copy_baseline.py','transfer_kernel.py'}
members=[]
for row in packet['files']:
 raw=base64.b64decode(row['base64'],validate=True)
 assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
 assert row['mode']==0o755
 members.append((row,raw))
os.umask(0o077);root.mkdir(mode=0o700)
for row,raw in members:
 p=root/row['name']
 with p.open('xb') as f:f.write(raw)
 p.chmod(row['mode']);s=p.lstat()
 assert stat.S_ISREG(s.st_mode) and s.st_uid==s.st_gid==0 and stat.S_IMODE(s.st_mode)==row['mode'] and p.read_bytes()==raw
print(json.dumps({'files':[{k:v for k,v in x.items() if k!='base64'} for x,_ in members],
 'all_source_bytes_modes_read_back':True,'transfer_started':False},sort_keys=True))
'''


def save(name, value):
    with (PRIVATE / name).open('x') as output:
        json.dump(value, output, sort_keys=True, indent=2)
        output.write('\n')


def call(name, argv, data=None):
    started = time.monotonic()
    record = {'command': argv, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    stdout, stderr = PRIVATE / (name + '.stdout'), PRIVATE / (name + '.stderr')
    with stdout.open('xb') as out, stderr.open('xb') as err:
        child = subprocess.Popen(argv, stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                                 stdout=out, stderr=err)
        record['child_pid'] = child.pid
        if data is not None:
            child.communicate(data)
        else:
            child.wait()
    record['exit_code'] = child.returncode
    for key, path in [('stdout', stdout), ('stderr', stderr)]:
        with path.open('rb') as stream:
            record[key] = {'bytes': path.stat().st_size, 'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
    record.update({'elapsed_seconds': time.monotonic() - started,
                   'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()})
    save(name + '.json', record)
    print(json.dumps({'phase': name, 'exit_code': child.returncode, 'elapsed_seconds': record['elapsed_seconds']}), flush=True)
    if child.returncode:
        raise RuntimeError(name + ' failed; complete command output retained')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet-sha256', required=True)
    parser.add_argument('--report-sha256', required=True)
    args = parser.parse_args()
    os.umask(0o077)
    assert all(re.fullmatch('[0-9a-f]{64}', value) for value in (args.packet_sha256, args.report_sha256))
    assert PRIVATE.is_dir() and not PRIVATE.is_symlink() and not (PRIVATE / 'driver-result.json').exists()
    started = time.monotonic()
    report = {'schema_version': 1, 'completed': False, 'kernel_report_sha256': args.report_sha256,
              'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'phases': [],
              'private_key_transferred': False, 'firmware_transferred': False,
              'module_loaded': False, 'vm_started': False, 'physical_hardware_tested': False}
    code = 1
    try:
        packet = (PRIVATE / 'source-packet.json').read_bytes()
        assert hashlib.sha256(packet).hexdigest() == args.packet_sha256
        report['source_packet'] = {'bytes': len(packet), 'sha256': args.packet_sha256}
        report['phases'].append(call('install', BASE + ['python3', '-B', '-c', INSTALL], packet))
        report['phases'].append(call('transfer', BASE + ['python3', '-B', CT_RECIPE + '/transfer_kernel.py',
                                                        '--report-sha256', args.report_sha256]))
        report['completed'] = True
        code = 0
    except Exception as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        report.update({'exit_code': code, 'elapsed_seconds': time.monotonic() - started,
                       'ended_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
        save('driver-result.json', report)
        print(json.dumps({key: report.get(key) for key in ('completed', 'exit_code', 'elapsed_seconds', 'error')}), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    main()
