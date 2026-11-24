#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Capture complete raw R5 host orchestration and public-runtime transfer records."""
from pathlib import Path
import base64
import hashlib
import json
import os
import stat
import subprocess
import traceback
import zlib

BUILD = Path('/tank/shared/projects/tb371fc-linux/private/research5-services-20261123')
TRANSFER = Path('/tank/shared/projects/tb371fc-linux/private/research5-services-transfer-20261123')
OUTPUT = BUILD / 'control-records-v1'
BASE = ['sudo', '-n', '/usr/sbin/pct', 'exec', '102', '--']


def ordinary(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        assert stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 <= before.st_size <= 4 * 1024**2
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read()
        after = os.fstat(descriptor)
        stable = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
                            s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        assert stable(before) == stable(after) and len(raw) == before.st_size
        return raw
    finally:
        os.close(descriptor)


def main():
    os.umask(0o077)
    assert not OUTPUT.exists() and not OUTPUT.is_symlink()
    OUTPUT.mkdir(mode=0o700)
    members = []
    record = {'schema_version': 1, 'complete': False, 'commands': [],
              'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'private_key_read': False, 'binary_artifacts_included': False,
              'firmware_included': False, 'physical_hardware_tested': False}

    def add(name, raw, source):
        assert name not in {row['path'] for row in members}
        raw.decode('utf-8')
        members.append({'path': name, 'source': source, 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'base64': base64.b64encode(raw).decode()})

    def command(name, argv):
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=40)
        item = {'name': name, 'command': argv, 'exit_code': result.returncode,
                'stdout_bytes': len(result.stdout), 'stdout_sha256': hashlib.sha256(result.stdout).hexdigest(),
                'stderr': result.stderr.decode(errors='replace')}
        record['commands'].append(item)
        assert result.returncode == 0 and result.stderr == b''
        return result.stdout

    try:
        done = json.loads(ordinary(BUILD / 'build-driver-result.json'))
        copied = json.loads(ordinary(TRANSFER / 'driver-result.json'))
        assert done['completed'] is copied['completed'] is True and done['exit_code'] == copied['exit_code'] == 0
        names = {'build-driver-result.json', 'build-launch.json', 'prepare-driver-result.json',
                 'prepare-driver.stdout', 'prepare-driver.stderr', 'prepare-launch.json',
                 'collect-public-launch.json'}
        for phase in ('install-recipe', 'configure-invocation', 'build-invocation', 'inspect-invocation', 'collect-public-01'):
            names.update(phase + suffix for suffix in ('.json', '.stdout', '.stderr'))
        for name in sorted(names):
            add('host-build/' + name, ordinary(BUILD / name), str(BUILD / name))
        names = {'driver-result.json', 'launch.json'}
        for phase in ('install', 'transfer'):
            names.update(phase + suffix for suffix in ('.json', '.stdout', '.stderr'))
        for name in sorted(names):
            add('host-transfer/' + name, ordinary(TRANSFER / name), str(TRANSFER / name))
        read = "from pathlib import Path; import os,stat,sys; p=Path(sys.argv[1]); s=p.lstat(); assert stat.S_ISREG(s.st_mode) and s.st_size<1024**2; sys.stdout.buffer.write(p.read_bytes())"
        for name in ('bundle.json', 'transfer.json'):
            source = '/work/research5-services-kernel-inputs-v1/' + name
            raw = command('shared-' + name, BASE + ['docker', 'exec', 'tb371fc-build-20261123', 'python3', '-B', '-c', read, source])
            if name == 'transfer.json':
                value = json.loads(raw)
                assert value['complete'] is True and value['files_verified'] == 106
                assert value['source_before'] == value['source_after'] == value['destination_readback']
            add('shared-transfer/' + name, raw, source)
        for name in ('r5-services-kernel-copy-v1.source.log', 'r5-services-kernel-copy-v1.destination.log',
                     'r5-services-kernel-verify-v1.source.log'):
            source = '/var/tmp/tb371fc-input2-copy-logs/' + name
            add('ct-transfer/' + name, command(name, BASE + ['python3', '-B', '-c', read, source]), source)
        assert len(members) == 35
        packet = (json.dumps({'schema_version': 1, 'members': members}, sort_keys=True, separators=(',', ':')) + '\n').encode()
        compressed = zlib.compress(packet, 9)
        with (OUTPUT / 'packet.zlib').open('xb') as stream:
            stream.write(compressed)
        parts = []
        for number, offset in enumerate(range(0, len(compressed), 32768)):
            block = compressed[offset:offset + 32768]
            name = 'part-%02d.b64' % number
            with (OUTPUT / name).open('x') as stream:
                stream.write(base64.b64encode(block).decode() + '\n')
            parts.append({'name': name, 'bytes': len(block), 'sha256': hashlib.sha256(block).hexdigest()})
        record.update({'complete': True, 'member_count': len(members), 'packet_bytes': len(packet),
                       'packet_sha256': hashlib.sha256(packet).hexdigest(), 'compressed_bytes': len(compressed),
                       'compressed_sha256': hashlib.sha256(compressed).hexdigest(), 'parts': parts,
                       'members': [{key: value for key, value in row.items() if key != 'base64'} for row in members]})
    except Exception as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
    finally:
        with (OUTPUT / 'result.json').open('x') as output:
            json.dump(record, output, sort_keys=True, indent=2)
            output.write('\n')
    print(json.dumps({key: record.get(key) for key in ('complete', 'member_count', 'packet_bytes',
          'packet_sha256', 'compressed_bytes', 'compressed_sha256', 'parts', 'error')}, sort_keys=True), flush=True)
    raise SystemExit(0 if record['complete'] else 1)


if __name__ == '__main__':
    main()
