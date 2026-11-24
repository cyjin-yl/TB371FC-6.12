#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Replay only a new diagnostic image copy, then extract its generic VM journal.

The original failed image is opened only for reading and hashed before/after.
No filesystem is mounted and no physical block device or new VM is used.
"""
import datetime
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

SOURCE = Path('/work/fedora-input-system-v2/fedora45-research3-system.ext4')
OUTPUT = Path('/work/fedora-r3-bus-diagnostics-v2')


def identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary project file required')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'size': path.stat().st_size, 'sha256': digest}


def execute(name, command, timeout=120):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    with (OUTPUT / (name + '.stdout')).open('x') as stream:
        stream.write(result.stdout)
    with (OUTPUT / (name + '.stderr')).open('x') as stream:
        stream.write(result.stderr)
    return result


def list_directory(image, path, label):
    result = execute(label, ['/usr/sbin/debugfs', '-R', 'ls -p ' + path, str(image)])
    if result.returncode:
        raise ValueError('read-only debugfs listing failed')
    entries = []
    for line in result.stdout.splitlines():
        fields = line.split('/')
        if len(fields) >= 8 and fields[1].isdigit():
            entries.append({'name': fields[5], 'mode': int(fields[2], 8),
                            'size': int(fields[6]) if fields[6].isdigit() else None})
    return entries


def main():
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh diagnostic prefix required')
    original = identity(SOURCE)
    if original['size'] != 4 * 1024**3:
        raise ValueError('unexpected ordinary failed-image size')
    OUTPUT.mkdir()
    record = {'schema_version': 1, 'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source': {'path': str(SOURCE), **original}, 'original_image_written': False,
              'new_vm_started': False, 'filesystem_mounted': False, 'physical_device_accessed': False,
              'diagnostic_copy_is_a_qualified_candidate': False, 'complete': False}
    clone = OUTPUT / 'journal-replayed-copy.ext4'
    try:
        copied = execute('copy', ['cp', '--reflink=auto', '--sparse=always', str(SOURCE), str(clone)], timeout=600)
        record['copy_exit_code'] = copied.returncode
        if copied.returncode or copied.stdout or copied.stderr:
            raise ValueError('diagnostic copy failed or warned')
        record['clone_before_replay'] = identity(clone)
        if record['clone_before_replay'] != original:
            raise ValueError('diagnostic copy differs before journal replay')
        result = execute('journal-replay', ['/usr/sbin/e2fsck', '-y', '-E', 'journal_only', str(clone)])
        record['journal_only_replay_exit_code'] = result.returncode
        if result.returncode not in (0, 1):
            raise ValueError('journal-only replay failed on the diagnostic copy')
        record['clone_after_replay'] = identity(clone)
        machine_dirs = [entry['name'] for entry in list_directory(clone, '/var/log/journal', 'journal-directories')
                        if stat.S_ISDIR(entry['mode']) and re.fullmatch('[0-9a-f]{32}', entry['name'])]
        if len(machine_dirs) != 1:
            raise ValueError('expected one owned generic VM journal directory')
        journal_root = '/var/log/journal/' + machine_dirs[0]
        journals = [entry for entry in list_directory(clone, journal_root, 'journal-files')
                    if stat.S_ISREG(entry['mode']) and
                    re.fullmatch(r'[A-Za-z0-9@_.-]+\.journal~?', entry['name'])]
        if not 1 <= len(journals) <= 8 or any(not entry['size'] or entry['size'] > 64 * 1024**2 for entry in journals):
            raise ValueError('journal file inventory outside its bound')
        destination = OUTPUT / 'journals'
        destination.mkdir()
        record['extracted_journals'] = {}
        for index, entry in enumerate(journals):
            target = destination / entry['name']
            dumped = execute(f'journal-dump-{index:02d}', ['/usr/sbin/debugfs', '-R',
                             f'dump -p {journal_root}/{entry["name"]} {target}', str(clone)])
            if dumped.returncode or not target.is_file():
                raise ValueError('read-only journal extraction failed')
            record['extracted_journals'][entry['name']] = identity(target)
        outputs = {}
        for name, arguments in (
            ('boots', ['--list-boots']),
            ('broker-all-boots', ['-o', 'json', '_SYSTEMD_UNIT=dbus-broker.service']),
            ('diagnostics-all-boots', ['-o', 'json', '--grep',
                                    'being disconnected|protocol|file descriptors|SASL|denied|avc|reset|pids-proof']),
        ):
            result = execute(name, ['/usr/bin/journalctl', '--directory', str(destination), '--no-pager', *arguments])
            outputs[name] = {'exit_code': result.returncode, 'stdout': identity(OUTPUT / (name + '.stdout')),
                             'stderr': identity(OUTPUT / (name + '.stderr'))}
        record['journalctl_outputs'] = outputs
        record['complete'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        record['original_after_diagnostics'] = identity(SOURCE)
        record['original_byte_identical'] = record['original_after_diagnostics'] == original
        record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (OUTPUT / 'diagnostics.json').open('x') as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write('\n')
    if not record['original_byte_identical']:
        raise ValueError('original failed image changed unexpectedly')
    print(json.dumps({'complete': record['complete'], 'original_byte_identical': True,
                      'report': identity(OUTPUT / 'diagnostics.json')}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
