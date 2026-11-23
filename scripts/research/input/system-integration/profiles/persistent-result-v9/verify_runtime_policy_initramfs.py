#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only qualification of the independently derived tmpfs-handoff profile.

This version retains the immutable v5 verifier and original baseline as trust
anchors. Its pure archive, ELF, cache and source readers are imported only from
those exact bytes. The verification body is an explicit v5 derivative, adding
only the fixed handoff members, the stat observer, their dependency roots,
the single combined-policy replacement and the reviewed copy-domain contract. No target binary, shell, mount, PRoot or policy operation is executed.

The independently built stage artifacts have explicit fixed identities below.
A caller cannot qualify arbitrary artifacts by supplying hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import types

PARENT_SIZE = 27585
PARENT_SHA = '58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e'


def _fixed_parent():
    path = Path(__file__).with_name('verify_early_policy_initramfs.py')
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size != PARENT_SIZE:
            raise ValueError('ordinary immutable v5 parent verifier required')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(PARENT_SIZE + 1)
    finally:
        os.close(fd)
    if len(raw) != PARENT_SIZE or hashlib.sha256(raw).hexdigest() != PARENT_SHA:
        raise ValueError('immutable v5 parent verifier identity changed')
    module = types.ModuleType('fixed_v5_initramfs_parent')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


_PARENT = _fixed_parent()
for _name in ('require', 'digest', 'ordinary_bytes', 'load_legacy', 'canonical',
              'source_payload', 'dynamic_dependencies', 'parse_image',
              'cache_entries', 'manifest_records', 'LEGACY_SIZE', 'LEGACY_SHA',
              'BASELINE_SIZE', 'BASELINE_SHA', 'SOURCE_ROOT', 'CONFIG_SHA',
              'POLICY_SIZE', 'POLICY_SHA', 'BOOTSTRAP_SIZE', 'BOOTSTRAP_SHA',
              'EXTRA_LIBRARY_CATALOG'):
    globals()[_name] = getattr(_PARENT, _name)

# Independent v9 pins; the imported original baseline verifier is unchanged.
ORIGINAL_POLICY_SIZE, ORIGINAL_POLICY_SHA = POLICY_SIZE, POLICY_SHA
BOOTSTRAP_SIZE = 72528
BOOTSTRAP_SHA = '0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14'
POLICY_SIZE = 3835468
POLICY_SHA = 'ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798'
CANDIDATE_POLICY_SOURCE = Path('/work/selinux-socket-probe-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35')
DERIVED_FROM_TMPFS_CHECKER_SHA = '92f02fd33fcc5f7aaea6d1d0e06c04589af024b09e8f678f772798909c2ebb07'

# These are explicit profile inputs, not an open catalog. The stage0 and stage1
# identities are the independently frozen build-01 artifacts, not caller pins.
HANDOFF_CATALOG = {
    'init.tmpfs': {
        'kind': 'script', 'size': 6039,
        'sha256': '15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d',
        'mode': 0o755,
    },
    'init.tmpfs-wait': {
        'kind': 'elf', 'size': 71872,
        'sha256': '7e593ef9b2c40834b97ad35b1bc21fcd54b00e34dce72381832f88329e28b3ec',
        'mode': 0o755,
    },
    'usr/bin/switch_root': {
        'kind': 'elf', 'size': 69104,
        'sha256': '6b6c1803111f117b76b553a664cec1a074827d025618446319d7871f9c127f75',
        'mode': 0o755,
    },
    'usr/bin/stat': {
        'kind': 'elf', 'size': 135480,
        'sha256': 'f54c956a5e840a22480869e0f5093f51e3a39b42374dd1045d527e8560ad5d5e',
        'mode': 0o755,
    },
}
# The reviewed, byte-pinned stage0 fixes these top-level copy roots, excluded
# API directories, destination, command paths and interpreter.
COPY_CONTRACT = {
    'interpreter': '/usr/bin/bash',
    'new_root_path': '/tb371fc-initroot',
    'mount_filesystem': 'tmpfs',
    'mount_size_bytes': 192 * 1024**2,
    'copy_roots': ['bin', 'etc', 'init', 'init.systemd', 'init.tmpfs',
                   'init.tmpfs-wait', 'lib', 'lib64', 'root', 'sbin',
                   'sysroot', 'tmp', 'usr', 'var'],
    'api_roots': ['dev', 'proc', 'sys', 'run'],
    'command_paths': ['usr/bin/bash', 'usr/bin/mount', 'usr/bin/mkdir',
                      'usr/bin/cp', 'usr/bin/switch_root'],
    'copy_is_one_invocation': True,
    'copy_arguments': ['-a', '-x', '--'],
    'old_root_descriptor': 3,
    'rdinit': '/init.tmpfs',
    'next_after_switch_root': '/init.tmpfs-wait',
    'next_after_cleanup': '/init',
    'policy_loaded_by_stage0_or_stage1': False,
}


def qualify_handoff_sources(core, source_root, manifest, baseline_elfs):
    require(COPY_CONTRACT is not None and all(
        item['size'] is not None and item['sha256'] is not None
        for item in HANDOFF_CATALOG.values()),
        'reviewed tmpfs stage artifacts and copy contract are not yet pinned')
    tools = manifest_records(core, manifest)
    require(set(tools) == set(HANDOFF_CATALOG),
            'exactly the three fixed handoff members and the fixed stat observer are required')
    payloads, roots, records = {}, {}, {}
    for name, fixed in HANDOFF_CATALOG.items():
        item = tools[name]
        require(set(item) == {'path', 'size', 'sha256', 'mode', 'source_path'} and
                item['size'] == fixed['size'] and item['sha256'] == fixed['sha256'] and
                item['mode'] == fixed['mode'], 'unqualified handoff identity: ' + name)
        source = Path(item['source_path'])
        require(source.is_absolute(), 'handoff source must be an explicit absolute file')
        if name in ('usr/bin/switch_root', 'usr/bin/stat'):
            require(source == source_root / name, 'tool must be the fixed Fedora ordinary source: ' + name)
        raw, info = ordinary_bytes(source, 4 * 1024**2)
        require(len(raw) == fixed['size'] and digest(raw) == fixed['sha256'] and
                stat.S_IMODE(info.st_mode) == fixed['mode'], 'handoff source changed: ' + name)
        if name == 'usr/bin/stat':
            require(info.st_uid == info.st_gid == 0,
                    'fixed stat observer must retain root ownership')
        payloads[name] = raw
        records[name] = {'path': name, 'size': len(raw), 'sha256': digest(raw),
                         'mode': stat.S_IMODE(info.st_mode), 'source_path': str(source),
                         'kind': fixed['kind'], 'uid': info.st_uid, 'gid': info.st_gid}
        if fixed['kind'] == 'elf':
            dependency = dynamic_dependencies(raw)
            require(dependency['interpreters'] == ['/lib/ld-linux-aarch64.so.1'] and
                    not dependency['rpath'] and not dependency['runpath'],
                    'unqualified handoff ELF loader or search path: ' + name)
            roots[name] = dependency
        else:
            require(raw.split(b'\n', 1)[0] == ('#!' + COPY_CONTRACT['interpreter']).encode() and
                    b'\0' not in raw, 'unqualified stage0 script interpreter')
    for name in COPY_CONTRACT['command_paths']:
        canonical(core, name)
        if name in roots:
            continue
        record, raw = source_payload(core, source_root, name)
        fixed = baseline_elfs.get(record['resolved_path'])
        require(fixed is not None and record['size'] == fixed['size'] and
                record['sha256'] == fixed['sha256'],
                'copy command is not unchanged qualified baseline userspace: ' + name)
        dependency = dynamic_dependencies(raw)
        require(not dependency['rpath'] and not dependency['runpath'],
                'copy command has a search-path override: ' + name)
        roots[name] = dependency
        records[name] = record
    require(COPY_CONTRACT['interpreter'].lstrip('/') in COPY_CONTRACT['command_paths'],
            'stage0 interpreter is absent from the command closure')
    return tools, payloads, roots, records


def qualify_copy_domain(core, main, baseline_main):
    contract = COPY_CONTRACT
    copy_roots, api_roots = set(contract['copy_roots']), set(contract['api_roots'])
    require(copy_roots and not copy_roots.intersection(api_roots),
            'copy and API roots must be explicit disjoint sets')
    for name in copy_roots | api_roots:
        require(canonical(core, name) == name and '/' not in name,
                'copy root is not one canonical top-level name')
    destination = canonical(core, contract['new_root_path'].lstrip('/'))
    require('/' not in destination and destination not in copy_roots | api_roots,
            'new tmpfs destination overlaps the copy domain')
    actual_top = {name for name in main.entries if name != '.' and '/' not in name}
    require(actual_top == copy_roots | api_roots and destination not in main.entries,
            'archive top-level tree differs from the reviewed stage0 copy contract')
    records = []
    for name in sorted(actual_top):
        entry = main.entries[name]
        require(entry['uid'] == entry['gid'] == 0, 'copy-domain root ownership changed: ' + name)
        if name in api_roots:
            require(entry['kind'] == 'directory', 'API root is not a directory: ' + name)
        elif name not in ('init', 'init.systemd', 'init.tmpfs', 'init.tmpfs-wait'):
            old = baseline_main.entries.get(name)
            require(old is not None and entry['kind'] == old['kind'] and
                    entry['mode'] == old['mode'] and entry.get('target') == old.get('target'),
                    'original copy-root type/mode/target changed: ' + name)
        records.append({**core.member_record(entry), 'mode': entry['mode'],
                        'target': entry.get('target')})
    groups = {}
    for name, entry in main.entries.items():
        if name == '.':
            continue
        top = name.split('/', 1)[0]
        if top in copy_roots:
            require(entry['kind'] in ('directory', 'regular', 'symlink'),
                    'unexpected special node in copied ordinary payload tree: ' + name)
        if entry['kind'] == 'regular' and entry['nlink'] > 1:
            groups.setdefault(entry['inode_key'], []).append(name)
    for names in groups.values():
        domains = {name.split('/', 1)[0] in copy_roots for name in names}
        require(len(domains) == 1, 'hardlink group crosses copied payload and excluded API roots')
    return {'contract': contract, 'top_level_members': records,
            'archive_copy_domain_complete': True,
            'regular_hardlink_groups_checked': len(groups),
            'no_hardlink_group_crosses_api_exclusion': True,
            'copy_execution_tested': False, 'mount_move_tested': False,
            'old_root_cleanup_tested': False,
            'scope': 'fixed script bytes and archive coverage only; actual tmpfs/cleanup evidence requires VM'}


def verify(image, fw_manifest, expected_cache, expected_libraries, early_policy_manifest,
           *, legacy_verifier, baseline_image, source_root, init_bootstrap, early_tools_manifest):
    result = {'schema_version': 1, 'passed': False, 'stage': 'fixed-inputs',
              'scope': 'explicit tmpfs-handoff, V4 VM audit observation and single seven-permission policy payload; ARM64 archive qualification only',
              'parent_verifier_sha256': PARENT_SHA,
              'extracted': False, 'image_executed': False, 'ldconfig_executed': False,
              'proot_executed': False, 'kernel_policy_load_tested': False,
              'firmware_loaded': False, 'physical_hardware_tested': False}
    try:
        core = load_legacy(Path(legacy_verifier))
        source_root = Path(source_root)
        require(source_root == SOURCE_ROOT and not source_root.is_symlink() and source_root.is_dir(),
                'this profile requires the fixed original Fedora source root')
        old_raw = core.read_regular(Path(baseline_image), core.MAX_ARCHIVE)
        require(len(old_raw) == BASELINE_SIZE and digest(old_raw) == BASELINE_SHA,
                'the original qualified initramfs is required')
        del old_raw
        baseline = core.verify(Path(baseline_image), Path(fw_manifest))
        require(baseline['passed'], 'the unmodified old checker did not accept its original image')
        result['baseline'] = {'image': baseline['image'], 'legacy_verifier_sha256': LEGACY_SHA,
                              'original_verification_passed': True,
                              'original_cache_sha256': baseline['ld_so_cache']['sha256']}
        baseline_elfs = {item['path']: item for item in baseline['runtime_elfs']['files']}
        old_libraries = {}
        for item in baseline['ld_so_cache']['entries']:
            elf = baseline_elfs[item['resolved_path']]
            require(item['soname'] not in old_libraries, 'duplicate baseline soname')
            old_libraries[item['soname']] = {
                key: item[key] for key in ('soname', 'cache_path', 'resolved_path', 'sha256')}
            old_libraries[item['soname']]['size'] = elf['size']
        available = {**old_libraries}
        for soname, item in EXTRA_LIBRARY_CATALOG.items():
            require(soname not in available or available[soname] == item,
                    'extra-library catalog conflicts with the qualified baseline')
            available[soname] = item
        result['stage'] = 'fixed-bootstrap-and-dependency-closure'
        tools, handoff_payloads, tool_dependencies, tool_sources = qualify_handoff_sources(
            core, source_root, early_tools_manifest, baseline_elfs)
        require(BOOTSTRAP_SIZE is not None and BOOTSTRAP_SHA is not None,
                'the reviewed ELF bootstrap has not yet been pinned for this profile')
        require(init_bootstrap['size'] == BOOTSTRAP_SIZE and init_bootstrap['sha256'] == BOOTSTRAP_SHA and
                init_bootstrap['mode'] == 0o755, 'bootstrap is not the explicitly approved ELF')
        bootstrap_source, unused = ordinary_bytes(Path(init_bootstrap['source_path']), 4 * 1024**2)
        require(len(bootstrap_source) == BOOTSTRAP_SIZE and digest(bootstrap_source) == BOOTSTRAP_SHA,
                'bootstrap source file differs from its approved bytes')
        dependencies = {'init': dynamic_dependencies(bootstrap_source), **tool_dependencies}
        require(not dependencies['init']['rpath'] and not dependencies['init']['runpath'],
                'bootstrap has an unqualified dynamic search-path override')
        # The fixed bootstrap opens libselinux dynamically; libselinux's
        # version adaptation opens libsepol. DT_NEEDED cannot find either edge.
        queue = ['libselinux.so.1', 'libsepol.so.2']
        for item in dependencies.values():
            queue.extend(item['needed'])
        needed = set()
        while queue:
            soname = queue.pop()
            if soname in needed:
                continue
            require(soname in available, 'dependency lacks an explicitly qualified source mapping: ' + soname)
            item = available[soname]
            record, data = source_payload(core, source_root, item['resolved_path'])
            require(record['resolved_path'] == item['resolved_path'] and
                    record['size'] == item['size'] and record['sha256'] == item['sha256'],
                    'dependency source differs from its fixed identity: ' + soname)
            dependency = dynamic_dependencies(data)
            require(dependency['soname'] == soname and not dependency['rpath'] and not dependency['runpath'],
                    'dependency SONAME/search-path differs from this profile: ' + soname)
            dependencies[item['resolved_path']] = dependency
            needed.add(soname)
            queue.extend(dependency['needed'])
        expected_map = {**old_libraries, **{name: available[name] for name in needed}}
        supplied = {}
        require(isinstance(expected_libraries, list), 'expected_libraries must be an explicit list')
        for item in expected_libraries:
            require(set(item) == {'soname', 'cache_path', 'resolved_path', 'size', 'sha256'} and
                    item['soname'] not in supplied, 'invalid or duplicate expected-library record')
            supplied[item['soname']] = item
        require(supplied == expected_map,
                'expected cache libraries are not exactly old-baseline union qualified bootstrap closure')
        for soname, item in expected_map.items():
            record, unused = source_payload(core, source_root, item['resolved_path'])
            require(record['resolved_path'] == item['resolved_path'] and record['size'] == item['size'] and
                    record['sha256'] == item['sha256'], 'baseline source library changed: ' + soname)
        result['dependency_closure'] = {'old_cache_entries': len(old_libraries),
            'new_cache_entries': len(expected_map), 'added_sonames': sorted(set(expected_map) - set(old_libraries)),
            'explicit_dlopen_edges': ['init -> libselinux.so.1', 'libselinux.so.1 -> libsepol.so.2'],
            'tool_roots': ['init', *tool_dependencies], 'needed_libraries': sorted(needed), 'elf_records': dependencies,
            'all_expected_libraries': list(expected_map.values())}
        result['handoff_source_qualification'] = tool_sources
        result['stage'] = 'archive-boundaries'
        main, parsed = parse_image(core, Path(image))
        result.update(parsed)
        result['limits'] = {'archive_bytes': core.MAX_ARCHIVE, 'expanded_bytes': core.MAX_EXPANDED}
        result['stage'] = 'tmpfs-copy-domain'
        baseline_main, unused = parse_image(core, Path(baseline_image))
        result['tmpfs_handoff'] = qualify_copy_domain(core, main, baseline_main)
        del baseline_main
        result['stage'] = 'firmware-payloads'
        manifest_raw = core.read_regular(Path(fw_manifest), 1024**2)
        require(digest(manifest_raw) == core.FW_MANIFEST_SHA256, 'fixed canonical firmware manifest required')
        manifest = json.loads(manifest_raw)
        require(manifest['firmware_file_count'] == len(manifest['files']) == 69, 'unexpected firmware manifest count')
        firmware, names = [], set()
        for item in manifest['files']:
            original = canonical(core, item['destination'])
            require(original.startswith('lib/firmware/'), 'firmware prefix escaped')
            path = 'usr/' + original
            require(path not in names, 'duplicate firmware name')
            names.add(path)
            entry = main.regular(path)
            require(entry['path'] == path and entry['size'] == item['size_bytes'] and
                    entry['sha256'] == item['sha256'], 'archive firmware payload mismatch: ' + path)
            firmware.append(core.member_record(entry))
        actual = {path for path, entry in main.entries.items()
                  if path.startswith('usr/lib/firmware/') and entry['kind'] != 'directory'}
        require(actual == names, 'archive firmware set is not exactly the qualified 69 files')
        result['firmware'] = {'files_verified': 69, 'manifest_sha256': core.FW_MANIFEST_SHA256,
                              'payload_bytes': sum(item['size'] for item in firmware), 'files': firmware}
        result['stage'] = 'early-policy-source-manifest'
        policy_files = manifest_records(core, early_policy_manifest)
        context_root = source_root / 'etc/selinux/targeted/contexts'
        required = {'etc/selinux/config', 'etc/selinux/targeted/policy/policy.35'}
        for parent, dirs, files in os.walk(context_root, followlinks=False):
            require(len(required) <= 512, 'contexts source tree exceeds explicit bound')
            for name in dirs:
                require(not (Path(parent) / name).is_symlink(), 'unexpected contexts directory symlink')
            for name in files:
                path = Path(parent) / name
                require(not path.is_symlink() and path.is_file(), 'contexts source is not ordinary')
                required.add(path.relative_to(source_root).as_posix())
        require('etc/selinux/targeted/contexts/files/file_contexts' in required and
                set(policy_files) == required, 'policy manifest does not exactly cover the fixed contexts tree')
        policy_records = []
        for path, item in policy_files.items():
            original, original_data = source_payload(core, source_root, path)
            if path == 'etc/selinux/targeted/policy/policy.35':
                require(original['resolved_path'] == path and
                        original['size'] == ORIGINAL_POLICY_SIZE and original['sha256'] == ORIGINAL_POLICY_SHA,
                        'immutable original policy source changed')
                data, unused = ordinary_bytes(CANDIDATE_POLICY_SOURCE, 16 * 1024**2)
                require(len(data) == POLICY_SIZE and digest(data) == POLICY_SHA,
                        'single qualified candidate policy differs')
                record = {'path': path, 'resolved_path': path, 'size': len(data), 'sha256': digest(data)}
                result['single_policy_replacement'] = {
                    'archive_path': path, 'original_source': original,
                    'candidate_source': str(CANDIDATE_POLICY_SOURCE),
                    'candidate': record, 'only_policy_payload_replaced': True,
                    'derived_from_tmpfs_checker_sha256': DERIVED_FROM_TMPFS_CHECKER_SHA,
                    'original_source_written': False, 'semantic_comparison_scope':
                        'separate source build/semantic qualification, not inferred by this archive parser'}
            else:
                record, data = original, original_data
            require(record['resolved_path'] == path and record['size'] == item['size'] and
                    record['sha256'] == item['sha256'], 'policy source identity mismatch: ' + path)
            entry = main.regular(path)
            require(entry['path'] == path and entry['size'] == item['size'] and
                    entry['sha256'] == item['sha256'], 'archive policy member mismatch: ' + path)
            if path == 'etc/selinux/config':
                require(record['sha256'] == CONFIG_SHA, 'fixed Fedora SELinux config required')
            if path.endswith('/policy/policy.35'):
                require(record['size'] == POLICY_SIZE and record['sha256'] == POLICY_SHA and
                        struct.unpack_from('<II', data) == (0xf97cff8c, 8) and data[8:16] == b'SE Linux' and
                        struct.unpack_from('<I', data, 16)[0] == 35, 'fixed separately qualified version 35 candidate policy required')
            policy_records.append(core.member_record(entry))
        archive_policy = {path for path, entry in main.entries.items()
                          if path.startswith('etc/selinux/') and entry['kind'] != 'directory'}
        require(archive_policy == required, 'unexpected or missing /etc/selinux archive payload')
        result['early_policy'] = {'files_verified': len(policy_records), 'files': policy_records,
                                  'source_root': str(source_root), 'policy_version': 35,
                                  'unchanged_contexts_and_config': True,
                                  'only_changed_relative_payload': 'etc/selinux/targeted/policy/policy.35'}
        result['stage'] = 'bootstrap-and-original-startup-members'
        init = main.entries.get('init')
        require(init is not None and init['kind'] == 'regular' and init['path'] == 'init' and
                init['size'] == BOOTSTRAP_SIZE and init['sha256'] == BOOTSTRAP_SHA and
                stat.S_IMODE(init['mode']) == 0o755 and init['nlink'] == 1,
                '/init is not the unique fixed bootstrap')
        init_elf = core.arm64_elf(main, 'init', require_executable=True)
        require(dynamic_dependencies(bytes(main.payload(init))) == dependencies['init'],
                'archive bootstrap dependencies differ from the qualified source artifact')
        old_init = main.entries.get('init.systemd')
        require(old_init is not None and old_init['kind'] == 'symlink' and
                main.resolve('init.systemd')['path'] == 'usr/lib/systemd/systemd',
                '/init.systemd does not preserve a real systemd symlink')
        systemd = core.arm64_elf(main, 'init.systemd', require_executable=True)
        shell = core.arm64_elf(main, '/usr/bin/sh', require_executable=True)
        for name, entry in [('systemd', systemd), ('hook_shell', shell)]:
            require(entry['sha256'] == baseline['critical_members'][name]['sha256'] and
                    entry['size'] == baseline['critical_members'][name]['size'],
                    'original startup ELF changed: ' + name)
        hook = main.regular(core.HOOK)
        require(hook['sha256'] == core.HOOK_SHA256 and hook['mode'] & 0o111 and
                bytes(main.payload(hook)).split(b'\n', 1)[0] == b'#!/usr/bin/sh',
                'original dracut SELinux hook changed')
        handoff_records = []
        for name, fixed in HANDOFF_CATALOG.items():
            entry = main.entries.get(name)
            require(entry is not None and entry['kind'] == 'regular' and entry['path'] == name and
                    entry['size'] == fixed['size'] and entry['sha256'] == fixed['sha256'] and
                    stat.S_IMODE(entry['mode']) == fixed['mode'] and entry['nlink'] == 1 and
                    entry['uid'] == entry['gid'] == 0, 'archive handoff member changed: ' + name)
            require(bytes(main.payload(entry)) == handoff_payloads[name],
                    'archive handoff bytes differ from the qualified source: ' + name)
            if fixed['kind'] == 'elf':
                core.arm64_elf(main, name, require_executable=True)
                require(dynamic_dependencies(bytes(main.payload(entry))) == tool_dependencies[name],
                        'archive handoff ELF closure changed: ' + name)
            handoff_records.append({**core.member_record(entry), 'mode': stat.S_IMODE(entry['mode'])})
        for name in COPY_CONTRACT['command_paths']:
            entry = core.arm64_elf(main, name, require_executable=True)
            fixed = tool_sources[name]
            require(entry['size'] == fixed['size'] and entry['sha256'] == fixed['sha256'],
                    'copy-command archive payload changed: ' + name)
        result['critical_members'] = {'init_bootstrap': init_elf,
            'saved_init': {**core.member_record(old_init), 'target': old_init['target']},
            'systemd': systemd, 'hook_shell': shell, 'selinux_hook': core.member_record(hook),
            'early_external_tools': handoff_records}
        result['stage'] = 'qualified-cache-mapping'
        actual_map, cache = cache_entries(core, main, expected_cache)
        require(actual_map == expected_map, 'new cache mappings differ from independently derived source closure')
        cache['all_mappings_match_fixed_sources'] = True
        result['ld_so_cache'] = cache
        result['stage'] = 'all-runtime-elfs'
        elfs = []
        for path, entry in main.entries.items():
            if entry['kind'] == 'regular' and not path.startswith('usr/lib/firmware/'):
                if bytes(main.payload(entry)[:4]) == b'\x7fELF':
                    elfs.append(core.arm64_elf(main, path))
        baseline_userspace = {path: (item['size'], item['sha256']) for path, item in baseline_elfs.items()
                              if not path.startswith('usr/lib/modules/')}
        expected_userspace = {**baseline_userspace}
        expected_userspace['init'] = (BOOTSTRAP_SIZE, BOOTSTRAP_SHA)
        for item in expected_map.values():
            expected_userspace[item['resolved_path']] = (item['size'], item['sha256'])
        for name, fixed in HANDOFF_CATALOG.items():
            if fixed['kind'] == 'elf':
                expected_userspace[name] = (fixed['size'], fixed['sha256'])
        actual_userspace = {item['path']: (item['size'], item['sha256']) for item in elfs
                            if not item['path'].startswith('usr/lib/modules/')}
        require(actual_userspace == expected_userspace,
                'userspace ELF set/payload changed beyond qualified tools and dependency closure')
        result['runtime_elfs'] = {'count': len(elfs), 'all_elf64_little_endian_aarch64': True,
            'unchanged_or_qualified_userspace_payloads': True, 'files': elfs,
            'module_payload_identity_scope': 'ARM64 archive checks only; kernel/module manifest inspector remains separate'}
        result['stage'] = 'complete'
        result['passed'] = True
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--firmware-manifest', type=Path, required=True)
    parser.add_argument('--profile-inputs', type=Path, required=True)
    parser.add_argument('--legacy-verifier', type=Path, required=True)
    parser.add_argument('--baseline-image', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, default=SOURCE_ROOT)
    args = parser.parse_args()
    data, unused = ordinary_bytes(args.profile_inputs, 1024**2)
    profile = json.loads(data)
    outcome = verify(args.image, args.firmware_manifest, profile['expected_cache'],
                     profile['expected_libraries'], profile['early_policy_manifest'],
                     legacy_verifier=args.legacy_verifier, baseline_image=args.baseline_image,
                     source_root=args.source_root, init_bootstrap=profile['init_bootstrap'],
                     early_tools_manifest=profile['early_tools_manifest'])
    outcome['profile_inputs'] = {'path': str(args.profile_inputs), 'bytes': len(data), 'sha256': digest(data)}
    print(json.dumps(outcome, indent=2, sort_keys=True), flush=True)
    raise SystemExit(0 if outcome['passed'] else 1)
