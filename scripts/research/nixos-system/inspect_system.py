#!/usr/bin/env python3
"""Inspect the completed NixOS closure without activating or booting it."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
import re
import struct

from foreign_builder import BASH, EXPECTED, FLAKE, QEMU, SYSTEM, WORK, command, digest, require, save


def summary_record(record):
    return {key: value for key, value in record.items() if key not in ('stdout', 'stderr')}


def elf(path):
    with path.open('rb') as stream:
        header = stream.read(64)
    if header[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', header, 18)[0] != 183:
        raise SystemExit('not an AArch64 ELF64 executable: ' + str(path))
    return {'path': str(path), 'resolved_path': str(path.resolve(strict=True)),
            'elf_machine': 183, 'size_bytes': path.stat().st_size, 'sha256': digest(path)}


def main():
    built = json.loads((WORK / 'system-build.json').read_text())
    require(built)
    if built['stdout'].strip() != EXPECTED:
        raise SystemExit('unexpected full-system output')
    retained = json.loads((WORK / 'retention.json').read_text())
    require(retained)
    if (WORK / 'system-result').resolve(strict=True) != Path(EXPECTED):
        raise SystemExit('system GC root missing or different')
    probe = json.loads((WORK / 'probe.json').read_text())
    if not probe['probe_passed']:
        raise SystemExit('ARM builder qualification missing')
    source_hashes = {
        'flake.nix': 'e99faf0dae7f02939ea51cfae7f8a0540697ee98a33df46f4935e3bf97c9608f',
        'hardware-configuration.nix': 'b4bf8962790d8e12793fee0151f1cf58007432ccd338e4bb14c2660423353ce4',
        'flake.lock': '663995d8f6b6a0d197a4b582e85b998fccb0d48108abcafbcf33f091ec0855e8',
    }
    for name, value in source_hashes.items():
        if digest(FLAKE / name) != value:
            raise SystemExit('original pinned NixOS source changed: ' + name)
    info = command(['nix', '--extra-experimental-features', 'nix-command flakes',
                    '--store', 'local', 'path-info', '--recursive', '--json', EXPECTED])
    save('closure-query.json', info)
    require(info)
    rows = json.loads(info['stdout'])
    if isinstance(rows, list):
        rows = {row.pop('path'): row for row in rows}
    if not isinstance(rows, dict) or EXPECTED not in rows:
        raise SystemExit('unexpected Nix closure response')
    paths = set(rows)
    for path, row in rows.items():
        if not re.fullmatch(r'/nix/store/[a-z0-9]{32}-[^/\s]+', path):
            raise SystemExit('invalid store member path')
        if not Path(path).exists() or not set(row['references']).issubset(paths):
            raise SystemExit('incomplete realized recursive closure: ' + path)
    table = ['store_path\tnar_sha256\tnar_size_bytes\tsignature_count\tlocally_trusted']
    for path, row in sorted(rows.items()):
        table.append('\t'.join((path, row['narHash'], str(row['narSize']),
                                str(len(row.get('signatures', []))),
                                str(bool(row.get('ultimate', False))).lower())))
    with (WORK / 'store-paths.tsv').open('x') as stream:
        stream.write('\n'.join(table) + '\n')
    root = Path(EXPECTED)
    entries = {}
    for path in sorted(root.iterdir()):
        entries[path.name] = {'symlink': path.is_symlink(), 'directory': path.is_dir(),
                              'resolved_path': str(path.resolve(strict=True))}
    systemd = root / 'systemd/lib/systemd/systemd'
    systemd_identity = elf(systemd)
    executed = command([str(QEMU), str(systemd), '--version'])
    save('systemd-version.json', executed)
    require(executed)
    if not executed['stdout'].startswith('systemd '):
        raise SystemExit('systemd version command did not produce its identity')
    scripts = {}
    for name in ('init', 'activate'):
        path = root / name
        if not path.is_file() or not path.read_bytes().startswith(b'#!'):
            raise SystemExit('expected generated shell entry: ' + name)
        syntax = command([str(QEMU), str(BASH / 'bin/bash'), '-n', str(path)])
        save(name + '-syntax.json', syntax)
        require(syntax)
        scripts[name] = {'sha256': digest(path), 'resolved_path': str(path.resolve(strict=True)),
                          'size_bytes': path.stat().st_size, 'aarch64_shell_syntax_check': syntax,
                          'executed': False}
    configuration = command(['nix', '--extra-experimental-features', 'nix-command flakes',
                             '--store', 'local', 'config', 'show', '--json'])
    save('configuration.after.json', configuration)
    require(configuration)
    before = json.loads(probe['default_configuration']['stdout'])
    after = json.loads(configuration['stdout'])
    controls = {}
    for key in ('sandbox', 'sandbox-fallback', 'build-users-group', 'extra-platforms',
                'system', 'require-sigs', 'substituters', 'trusted-public-keys'):
        if before[key]['value'] != after[key]['value']:
            raise SystemExit('default Nix control changed: ' + key)
        controls[key] = after[key]['value']
    jobs = {}
    for name in ('nix-foreign-probe-01', 'nix-system-plan-01', 'nix-system-build-01'):
        path = Path('/work/nixos-system-jobs') / (name + '.json')
        row = json.loads(path.read_text())
        if row['exit_code'] != 0:
            raise SystemExit('unexpected failed Nix phase: ' + name)
        log = path.with_suffix('.log')
        row.update(metadata_sha256=digest(path), log_sha256=digest(log), log_size_bytes=log.stat().st_size)
        jobs[name] = row
    plan = json.loads((WORK / 'system-plan.json').read_text())
    report = {
        'schema_version': 1, 'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': {'nixpkgs_revision': '94c3211b0ee8ba969a3f12eb4aff8ba0f72971dd',
                   'flake_root': str(FLAKE), 'files_sha256': source_hashes,
                   'recipes_sha256': {path.name: digest(path) for path in sorted(Path(__file__).parent.glob('*.py'))}},
        'environment': {'device': 'doesvm', 'ct_id': 102, 'container': 'tb371fc-build-20261123',
                        'builder_architecture': 'x86_64', 'target_system': 'aarch64-linux',
                        'execution': 'PRoot 5.5 mixed native/explicit QEMU user execution in existing isolated container',
                        'tools': probe['tools'], 'nix_defaults_unchanged': controls,
                        'per_invocation_overrides': {'sandbox': False, 'build-users-group': '',
                                                     'extra-platforms': 'aarch64-linux',
                                                     'store': 'local', 'max-jobs': 1, 'cores': 2},
                        'binfmt_registration_changed': False, 'host_or_ct_configuration_changed': False},
        'jobs': jobs,
        'foreign_builder_probe': {'mixed_execution': probe['mixed_execution'],
                                  'derivation_build': probe['derivation_build'],
                                  'output': probe['derivation_output'], 'passed': True},
        'build_plan_summary': re.findall(r'[^\n]*(?:will be built|will be fetched)[^\n]*', plan['stderr']),
        'full_system_build': {**summary_record(built), 'derivation_path': SYSTEM, 'output_path': EXPECTED,
                              'completed': True, 'output_nar': rows[EXPECTED], 'root_entries': entries,
                              'stderr_sha256': digest(built['stderr_path']),
                              'stdout_sha256': digest(built['stdout_path'])},
        'closure': {'store_path_count': len(rows), 'all_paths_exist': True, 'all_references_in_closure': True,
                    'total_nar_size_bytes': sum(row['narSize'] for row in rows.values()),
                    'inventory_path': str(WORK / 'store-paths.tsv'),
                    'inventory_sha256': digest(WORK / 'store-paths.tsv'),
                    'signature_bearing_paths': sum(bool(row.get('signatures')) for row in rows.values()),
                    'locally_trusted_paths': sum(bool(row.get('ultimate')) for row in rows.values()),
                    'retained_gc_root': str(WORK / 'system-result')},
        'systemd': {'identity': systemd_identity, 'aarch64_version_execution': executed,
                    'executed_as_pid1': False},
        'entry_scripts': scripts,
        'scope': 'complete custom NixOS userspace closure, not a rootfs/boot image or target hardware test',
        'rootfs_image_assembled': False, 'system_activation_performed': False,
        'nixos_system_boot_tested': False, 'kernel_modules_firmware_integrated': False,
        'tablet_accessed': False, 'tablet_boot_tested': False, 'hardware_support_demonstrated': False,
    }
    save('nixos-system-build.json', report)
    print(json.dumps({'status': 'complete_system_closure_qualified', 'paths': len(rows),
                       'nar_bytes': report['closure']['total_nar_size_bytes'],
                       'systemd': executed['stdout'].splitlines()[0], 'hardware_tested': False}, indent=2))


if __name__ == '__main__':
    main()
