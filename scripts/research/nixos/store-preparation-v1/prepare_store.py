#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Register the fixed original Nix closure in one new isolated root.

This native preparation never activates a NixOS system, boots a VM, changes
the default store settings, signs source-store metadata, or lowers signature
checking.  The private cache key is never included in the JSON report.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import traceback

NIX = Path('/usr/bin/nix')
NIX_SHA = '1795adb32a21c0aeef19e19530e96b933b603465a99dc6cf3ceed5b96948de58'
TOP = '/nix/store/j1g4ih1ajpffx2vhp5z0iyns13h59c4a-nixos-system-tb371fc-research-26.05.20261121.94c3211'
INVENTORY_SHA = '466e2d7d84b26a5d359148da5b3f44f2d8562d0216b546b780833bcedfb4135a'
ENTRY_HASHES = {
    'init': 'd7440ba41d2fb1abdbe1a9a2a1267cde841deb9dd4bd088a59586b12a719becd',
    'activate': '8e8c85675ceca709cd0445f5211a556cb3d0edf52d94e63cd1ea1bdf989f2ea9',
}
KEY_NAME = 'tb371fc-nixos-boot-20261123-1'
NAR_BYTES = 3751712072
COUNT = 894


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def identity(path):
    path = Path(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), 'ordinary file required: ' + str(path))
    return {'path': str(path), 'size': info.st_size, 'sha256': digest(path)}


def json_unique(raw):
    def pairs(values):
        out = {}
        for key, value in values:
            require(key not in out, 'duplicate JSON key')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs)


def normalize(value):
    if isinstance(value, list):
        result = {}
        for row in value:
            require(isinstance(row, dict) and row.get('path') not in result, 'invalid duplicate store path')
            result[row['path']] = row
        return result
    require(isinstance(value, dict), 'unexpected native path-info JSON shape')
    return value


def stable_rows(value):
    result = {}
    for name, row in normalize(value).items():
        require(re.fullmatch(r'/nix/store/[0-9a-z]{32}-[^/\x00\n]+', name), 'unexpected store path spelling')
        refs = row.get('references')
        require(isinstance(refs, list) and len(refs) == len(set(refs)), 'invalid references')
        result[name] = {
            'narHash': row['narHash'], 'narSize': row['narSize'],
            'references': sorted(refs), 'signatures': sorted(row.get('signatures', [])),
            'ultimate': row.get('ultimate', False), 'ca': row.get('ca'),
        }
    require(len(result) == COUNT and sum(row['narSize'] for row in result.values()) == NAR_BYTES,
            'original closure count/NAR size differs')
    require(all(set(row['references']).issubset(result) for row in result.values()),
            'closure references escape the fixed recursive path set')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--expected-inventory', required=True, type=Path)
    args = parser.parse_args()
    require(os.geteuid() == os.getegid() == 0 and os.uname().machine == 'x86_64',
            'native root preparation in the existing x86 builder required')
    work = args.work
    require(re.fullmatch(r'/work/nixos-system-boot-[a-zA-Z0-9_-]+', str(work)) and
            not work.exists() and not work.is_symlink(), 'new isolated /work prefix required')
    require(identity(NIX)['sha256'] == NIX_SHA and identity(NIX)['size'] == 12037520,
            'fixed native Nix importer differs')
    require(digest(args.expected_inventory) == INVENTORY_SHA, 'fixed original TSV differs')
    expected = {}
    with args.expected_inventory.open(newline='') as stream:
        for row in csv.DictReader(stream, delimiter='\t'):
            require(row['store_path'] not in expected, 'duplicate original TSV row')
            expected[row['store_path']] = row
    require(len(expected) == COUNT, 'original TSV path count differs')
    for name, value in ENTRY_HASHES.items():
        require(digest(Path(TOP) / name) == value, 'original NixOS entry differs: ' + name)
    os.umask(0o077)
    work.mkdir(mode=0o700)
    logs = work / 'store-jobs'
    logs.mkdir(mode=0o700)
    private = work / 'private'
    private.mkdir(mode=0o700)
    root = work / 'rootfs'
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    cache = private / 'signed-cache'
    cache.mkdir(mode=0o700)
    report = {'schema_version': 1, 'scope': 'native registered Nix root preparation only',
              'toplevel': TOP, 'work': str(work), 'rootfs': str(root),
              'native_nix': identity(NIX), 'recipe': identity(__file__),
              'source_inventory': identity(args.expected_inventory),
              'commands': [], 'complete': False, 'activation_executed': False,
              'vm_started': False, 'source_store_signed_or_repaired': False,
              'global_configuration_written': False, 'require_sigs': True,
              'private_key_published_or_copied_to_guest': False,
              'physical_hardware_tested': False}
    started = time.monotonic()
    base = [str(NIX), '--extra-experimental-features', 'nix-command']
    env = {**os.environ, 'LC_ALL': 'C', 'TERM': 'dumb', 'NIX_PAGER': 'cat'}

    def command(name, argv, *, timeout=3600, stdin_path=None, stdout_path=None, sensitive=False):
        require(re.fullmatch(r'[a-z0-9-]+', name), 'closed log name required')
        out = stdout_path or logs / (name + '.stdout')
        err = logs / (name + '.stderr')
        require(not out.exists() and not err.exists(), 'new command output paths required')
        begin = time.monotonic()
        in_handle = stdin_path.open('rb') if stdin_path else subprocess.DEVNULL
        try:
            with out.open('xb') as stdout, err.open('xb') as stderr:
                value = subprocess.run(argv, stdin=in_handle, stdout=stdout, stderr=stderr,
                                       timeout=timeout, env=env)
            record = {'name': name, 'argv': argv, 'exit_code': value.returncode,
                      'elapsed_seconds': time.monotonic() - begin,
                      'stderr': identity(err)}
            if sensitive:
                # This is the private-key-producing command. Do not put key
                # bytes or even a transferable key-file object in the report.
                record['stdout'] = {'private_material_excluded': True}
            else:
                record['stdout'] = identity(out)
            if stdin_path:
                record['stdin'] = {'private_key_file': True, 'contents_excluded': True}
            report['commands'].append(record)
            require(value.returncode == 0, 'native command failed: ' + name)
            print(json.dumps({'phase': name, 'exit_code': 0, 'elapsed_seconds': record['elapsed_seconds']}), flush=True)
            return out
        finally:
            if stdin_path:
                in_handle.close()

    def query(name, store, keys=None):
        argv = base + ['--store', store]
        if keys:
            argv += ['--option', 'trusted-public-keys', keys]
        argv += ['path-info', '--recursive', '--json', TOP]
        return stable_rows(json_unique(command(name, argv, timeout=180).read_bytes()))

    try:
        version = command('nix-version', [str(NIX), '--version'], timeout=30).read_text().strip()
        require(version == 'nix (Nix) 2.26.3', 'native Nix version differs')
        before = query('source-inventory-before', 'local')
        require(set(before) == set(expected), 'original recursive store path set differs')
        for name, row in before.items():
            old = expected[name]
            require(row['narHash'] == old['nar_sha256'] and row['narSize'] == int(old['nar_size_bytes']) and
                    len(row['signatures']) == int(old['signature_count']) and
                    row['ultimate'] is (old['locally_trusted'] == 'true'),
                    'source metadata differs from original frozen inventory: ' + name)
        command('source-verify', base + ['--store', 'local', '--option', 'require-sigs', 'true',
                                       'store', 'verify', '--recursive', TOP])
        key = private / 'cache-signing-key'
        command('generate-project-key', base + ['key', 'generate-secret', '--key-name', KEY_NAME],
                timeout=30, stdout_path=key, sensitive=True)
        require(stat.S_IMODE(key.stat().st_mode) == 0o600 and key.stat().st_uid == 0,
                'private signing key permissions differ')
        public_file = private / 'cache-public-key'
        command('project-public-key', base + ['key', 'convert-secret-to-public'], timeout=30,
                stdin_path=key, stdout_path=public_file)
        public_key = public_file.read_text().strip()
        require(re.fullmatch(re.escape(KEY_NAME) + r':[A-Za-z0-9+/]{43}=', public_key),
                'unexpected Ed25519 public key representation')
        cache_url = (cache.as_uri() + '?compression=zstd&compression-level=3&parallel-compression=false&secret-key=' + str(key))
        command('signed-cache-copy', base + ['--store', 'local', '--option', 'require-sigs', 'true',
                                             '--option', 'max-jobs', '1', '--option', 'cores', '2',
                                             'copy', '--to', cache_url, TOP])
        # Receiving from the file cache does not need the secret key setting.
        # The explicit public key is trusted for this command only.
        destination = 'local?root=' + str(root)
        command('registered-root-copy', base + ['--option', 'require-sigs', 'true',
                    '--option', 'trusted-public-keys', public_key,
                    'copy', '--from', cache.as_uri(), '--to', destination, TOP])
        after = query('destination-inventory', destination, public_key)
        require(set(after) == set(before), 'destination closure path set differs')
        for name, row in after.items():
            for field in ('narHash', 'narSize', 'references', 'ca'):
                require(row[field] == before[name][field], 'destination metadata differs: ' + name + ':' + field)
            require(any(signature.startswith(KEY_NAME + ':') for signature in row['signatures']),
                    'destination member lacks the explicit project signature')
        command('destination-verify-content-and-signatures', base + ['--store', destination,
                    '--option', 'require-sigs', 'true', '--option', 'trusted-public-keys', public_key,
                    'store', 'verify', '--recursive', '--sigs-needed', '1', TOP])
        unchanged = query('source-inventory-after', 'local')
        require(unchanged == before, 'source registered metadata changed during isolated import')
        for name, value in ENTRY_HASHES.items():
            require(digest(Path(TOP) / name) == value and digest(root / (TOP + '/' + name).lstrip('/')) == value,
                    'original/registered entry bytes differ after import')
        db = root / 'nix/var/nix/db/db.sqlite'
        require(db.is_file() and not db.is_symlink(), 'independent local-store database absent')
        inventory = {
            'schema_version': 1, 'toplevel': TOP, 'path_count': COUNT, 'nar_size_bytes': NAR_BYTES,
            'project_public_key': public_key,
            'signature_provenance': 'Original signatures retained; new project key attests this verified import, not upstream publication.',
            'paths': {name: {'narHash': row['narHash'], 'narSize': row['narSize'],
                            'references': row['references'], 'source_signatures': row['signatures'],
                            'source_ultimate': row['ultimate'], 'source_ca': row['ca']}
                      for name, row in sorted(before.items())},
        }
        inventory_path = work / 'store-inventory.json'
        inventory_path.write_text(json.dumps(inventory, sort_keys=True, indent=2) + '\n')
        report.update({'complete': True, 'store_inventory': identity(inventory_path),
                       'path_count': COUNT, 'nar_size_bytes': NAR_BYTES,
                       'project_public_key': public_key, 'source_metadata_unchanged': True,
                       'source_signature_bearing_paths': sum(bool(row['signatures']) for row in before.values()),
                       'source_ultimate_paths': sum(bool(row['ultimate']) for row in before.values()),
                       'source_ca_paths': sum(bool(row['ca']) for row in before.values()),
                       'source_unsigned_nonultimate_paths': sum(not row['signatures'] and not row['ultimate'] for row in before.values()),
                       'destination_project_signature_bearing_paths': COUNT,
                       'source_content_verify_exit_code': 0, 'destination_content_signature_verify_exit_code': 0,
                       'independent_database': identity(db),
                       'system_profile_registered': False, 'image_assembled': False})
    except Exception as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error),
                             'traceback': traceback.format_exc()}
        raise
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        (work / 'store-preparation.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
