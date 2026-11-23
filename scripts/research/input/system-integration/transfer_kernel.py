#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""CT102 orchestration: stream only frozen public research3 runtime files.

Both tar processes run inside their standard Docker containers. The transfer
never includes a signing private key, source/build symlink or firmware payload.
It reuses the bounded project tar pump, with new source/destination prefixes.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import signal

import copy_baseline as pump

SOURCE = 'tb371fc-build-ssd-20261123'
DESTINATION = 'tb371fc-build-20261123'
SOURCE_ROOT = '/work/research3-system'
DEST_ROOT = '/work/fedora-input-system-v2/kernel-inputs'
ARTIFACTS = ('Image', 'board.dtb', 'kernel.config', 'Module.symvers', 'source-manifest.json',
             'modules.SHA256SUMS', 'modules.order', 'modules.builtin', 'modules.builtin.modinfo',
             'signing-cert.der', 'kernel.btf')


def write_new(name, content):
    code = ('from pathlib import Path; import sys; p=Path(%r); '
            "f=p.open('xb'); f.write(sys.stdin.buffer.read()); f.close()") % (DEST_ROOT + '/' + name)
    pump.docker_python(DESTINATION, code, content=content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-sha256', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{64}', args.report_sha256):
        parser.error('exact frozen report SHA-256 required')
    if hashlib.sha256(Path(pump.__file__).read_bytes()).hexdigest() != '21e2d3b9887a52ed9fce96366eb71930fd9f5bcdfed901145cfc3a84ebd54ea0':
        raise ValueError('bounded transfer helper changed')
    signal.signal(signal.SIGTERM, pump.handle_signal)
    signal.signal(signal.SIGINT, pump.handle_signal)
    pump.SOURCE = SOURCE
    pump.DEST = DESTINATION
    read = '''from pathlib import Path
import hashlib,json
p=Path(%r)/'artifacts/research3-system-build.json'
b=p.read_bytes()
assert not p.is_symlink() and hashlib.sha256(b).hexdigest()==%r
print(b.decode())
''' % (SOURCE_ROOT, args.report_sha256)
    report_bytes = pump.docker_python(SOURCE, read)
    # print adds a final newline; the file's hash is checked inside the source
    # container rather than asserting that stdout framing is the stored file.
    report = json.loads(report_bytes)
    if not report['passed'] or report['kernel_release'] != '6.12.114-tb371fc-research3-system':
        raise ValueError('qualified research3 build required')
    identities = {'artifacts/' + name: report['files'][name] for name in ARTIFACTS}
    for entry in report['modules']:
        name = entry['path']
        if not re.fullmatch(r'lib/modules/6\.12\.114-tb371fc-research3-system/kernel/[A-Za-z0-9_./+-]+\.ko', name):
            raise ValueError('unexpected runtime module path')
        if '..' in Path(name).parts or 'modules/' + name in identities:
            raise ValueError('duplicate or escaping module path')
        identities['modules/' + name] = {'size': entry['size'], 'sha256': entry['sha256']}
    if len(report['modules']) != report['module_count']:
        raise ValueError('module count mismatch')
    # Report length is taken from its regular file, not the framed stdout.
    info_code = "from pathlib import Path; import json; p=Path(%r); print(json.dumps({'size':p.stat().st_size,'sha256':%r}))" % (
        SOURCE_ROOT + '/artifacts/research3-system-build.json', args.report_sha256)
    identities['artifacts/research3-system-build.json'] = json.loads(pump.docker_python(SOURCE, info_code))
    source_check = '''from pathlib import Path
import hashlib,json,sys
root=Path(%r)
for name,e in json.loads(sys.argv[1]).items():
 p=root/name
 assert p.is_file() and not p.is_symlink() and p.stat().st_size==e['size'],name
 with p.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==e['sha256'],name
print('ALL_FROZEN_RUNTIME_INPUTS_MATCH')
''' % SOURCE_ROOT
    pump.docker_python(SOURCE, source_check, [json.dumps(identities, separators=(',', ':'))])
    create = '''from pathlib import Path
import json
w=Path('/work/fedora-input-system-v2')
assert json.loads((w/'baseline-copy.json').read_text())['complete']
p=w/'kernel-inputs';assert not p.exists() and not p.is_symlink();p.mkdir()
'''
    pump.docker_python(DESTINATION, create)
    transfer = {'schema_version': 1, 'complete': False,
                'source_container': SOURCE, 'destination_container': DESTINATION,
                'source_root': SOURCE_ROOT, 'destination_root': DEST_ROOT,
                'kernel_report_sha256': args.report_sha256,
                'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'private_keys_or_firmware_transferred': False, 'old_artifacts_modified': False}
    try:
        names = sorted(identities)
        sent = pump.hash_or_copy('r3-kernel-copy', SOURCE_ROOT, DEST_ROOT, names, True)
        transfer['source_stream'] = sent
        received = pump.hash_or_copy('r3-kernel-verify', SOURCE_ROOT, DEST_ROOT, names, False)
        transfer['destination_stream'] = received
        if (sent['sha256'], sent['bytes']) != (received['sha256'], received['bytes']):
            raise ValueError('copied kernel stream differs')
        destination_check = source_check.replace(repr(SOURCE_ROOT), repr(DEST_ROOT), 1)
        pump.docker_python(DESTINATION, destination_check, [json.dumps(identities, separators=(',', ':'))])
        bundle = {'schema_version': 1, 'kernel_release': report['kernel_release'],
                  'source_report_sha256': args.report_sha256,
                  'module_count': report['module_count'], 'files': identities,
                  'source_container': SOURCE, 'source_root': SOURCE_ROOT,
                  'private_keys_or_firmware_included': False}
        payload = (json.dumps(bundle, sort_keys=True, indent=2) + '\n').encode()
        write_new('bundle.json', payload)
        transfer['bundle_sha256'] = hashlib.sha256(payload).hexdigest()
        transfer['files_verified'] = len(identities)
        transfer['complete'] = True
    except BaseException as error:
        transfer['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        transfer['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Keep the transfer record outside the manifest's exact runtime set.
        code = ("from pathlib import Path; import sys; p=Path('/work/fedora-input-system-v2/kernel-transfer.json'); "
                "f=p.open('xb'); f.write(sys.stdin.buffer.read()); f.close()")
        pump.docker_python(DESTINATION, code, content=(json.dumps(transfer, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps(transfer, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
