#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only qualification of the explicit early-SELinux initramfs profile.

The frozen old verifier and its original image are mandatory trust anchors.
Only its immutable newc/path/ELF parsing components are reused for the new
profile; no fake /init resolution or weakened old-cache check is installed.
This program never extracts, runs ldconfig, starts PRoot, loads policy, or
executes an archive. The actual producer separately records target ldconfig.
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
import zlib

LEGACY_SIZE = 20506
LEGACY_SHA = '263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a'
BASELINE_SIZE = 30649939
BASELINE_SHA = '2741ed3f3b5814b40dd303f4666b6f629c55ad11fd057a6e99f9f6be5e01c543'
SOURCE_ROOT = Path('/work/fedora-system-integration-v1/rootfs')
CONFIG_SHA = '80134a263d874d1687a43513a09b6cc8fdc2998e623c1c1670cb5769a85ce942'
POLICY_SIZE = 3835432
POLICY_SHA = '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430'
# Exact build-01 artifact; a changed bootstrap requires a new explicit pin.
# This identity is not a claim that PID1 execution has passed in the VM.
# A caller's arbitrary executable cannot qualify itself by reporting a hash.
BOOTSTRAP_SIZE = 72048
BOOTSTRAP_SHA = 'e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d'
EXTRA_LIBRARY_CATALOG = {
    'libsepol.so.2': {
        'soname': 'libsepol.so.2', 'cache_path': '/lib64/libsepol.so.2',
        'resolved_path': 'usr/lib64/libsepol.so.2', 'size': 802880,
        'sha256': '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b',
    },
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def ordinary_bytes(path, maximum, allow_empty=False):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and
                (0 if allow_empty else 1) <= before.st_size <= maximum,
                'not an ordinary bounded input: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(identity(before) == identity(after) and len(data) == before.st_size,
                'input changed during read: ' + str(path))
        return data, before
    finally:
        os.close(fd)


def load_legacy(path):
    data, unused = ordinary_bytes(path, LEGACY_SIZE)
    require(len(data) == LEGACY_SIZE and digest(data) == LEGACY_SHA,
            'the immutable original verifier is required')
    module = types.ModuleType('fixed_old_initramfs_verifier')
    module.__file__ = str(path)
    exec(compile(data, str(path), 'exec'), module.__dict__)
    return module


def canonical(core, value):
    require(isinstance(value, str) and core.safe_name(value) == value and value != '.',
            'expected a canonical relative source/member path')
    return value


def source_payload(core, source_root, name):
    """Resolve guest symlinks within this one source root, never host / paths."""
    parts = canonical(core, name).split('/')
    for unused in range(40):
        for i in range(len(parts)):
            path = source_root.joinpath(*parts[:i + 1])
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                parts = core.link_destination(parts[:i], os.readlink(path)) + parts[i + 1:]
                break
            require(i == len(parts) - 1 or stat.S_ISDIR(info.st_mode),
                    'source path crosses a non-directory')
        else:
            resolved = '/'.join(parts)
            data, info = ordinary_bytes(source_root / resolved, 64 * 1024**2, allow_empty=True)
            return {'path': name, 'resolved_path': resolved, 'size': len(data),
                    'sha256': digest(data), 'mode': stat.S_IMODE(info.st_mode)}, data
    raise ValueError('source symlink loop or excessive depth')


def dynamic_dependencies(data):
    """Read bounded ELF64/AArch64 DT_NEEDED/SONAME; never execute an ELF."""
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01',
            'dependency source is not ELF64 little endian')
    elf_type, machine, version = struct.unpack_from('<HHI', data, 16)
    require(elf_type in (2, 3) and machine == 183 and version == 1,
            'dependency source is not an AArch64 executable/shared object')
    phoff = struct.unpack_from('<Q', data, 32)[0]
    ehsize, phsize, phcount = struct.unpack_from('<HHH', data, 52)
    require(ehsize == 64 and phsize == 56 and 0 < phcount <= 256 and
            phoff + phsize * phcount <= len(data), 'invalid dependency ELF headers')
    loads, dynamics, interpreters = [], [], []
    for i in range(phcount):
        typ, flags, off, va, pa, filesz, memsz, align = struct.unpack_from('<IIQQQQQQ', data, phoff + i * 56)
        require(off <= len(data) and filesz <= len(data) - off,
                'dependency program segment exceeds file')
        if typ == 1:
            loads.append((va, filesz, off))
        elif typ == 2:
            dynamics.append((off, filesz))
        elif typ == 3:
            raw = data[off:off + filesz]
            require(2 <= len(raw) <= 4096 and raw.endswith(b'\0') and b'\0' not in raw[:-1],
                    'invalid dependency ELF interpreter')
            interpreters.append(raw[:-1].decode('ascii'))
    require(len(dynamics) == 1 and len(interpreters) <= 1,
            'this dynamic userspace profile requires one PT_DYNAMIC')
    offset, size = dynamics[0]
    require(size % 16 == 0 and 0 < size <= 4096 * 16, 'invalid dynamic-table bounds')
    tags = {}
    terminated = False
    for i in range(size // 16):
        tag, value = struct.unpack_from('<qQ', data, offset + 16 * i)
        if tag == 0:
            terminated = True
            break
        tags.setdefault(tag, []).append(value)
    require(terminated and len(tags.get(5, [])) == len(tags.get(10, [])) == 1,
            'missing/ambiguous dynamic string table')
    address, length = tags[5][0], tags[10][0]
    require(0 < length <= 16 * 1024**2, 'unbounded dynamic string table')
    mappings = [off + address - va for va, size, off in loads
                if va <= address and address - va <= size and length <= size - (address - va)]
    require(len(mappings) == 1, 'dynamic string table is not in one file-backed PT_LOAD')
    strings = data[mappings[0]:mappings[0] + length]

    def string(pos):
        require(pos < len(strings), 'dynamic string offset outside table')
        end = strings.find(b'\0', pos)
        require(end >= pos and end - pos <= 4096, 'unterminated dynamic string')
        return strings[pos:end].decode('ascii')

    needed = [string(pos) for pos in tags.get(1, [])]
    require(len(needed) <= 128 and len(needed) == len(set(needed)) and
            all(name and '/' not in name and name not in ('.', '..') for name in needed),
            'unexpected DT_NEEDED spelling or duplication')
    require(len(tags.get(14, [])) <= 1, 'multiple DT_SONAME entries')
    return {'needed': needed, 'soname': string(tags[14][0]) if tags.get(14) else None,
            'interpreters': interpreters,
            'rpath': [string(pos) for pos in tags.get(15, [])],
            'runpath': [string(pos) for pos in tags.get(29, [])]}


def parse_image(core, image):
    raw = core.read_regular(image, core.MAX_ARCHIVE)
    require(raw[:6] == b'070701', 'image must begin with the empty early newc')
    early = core.Newc(raw[:core.EARLY_BYTES], 'early')
    require(set(early.entries) <= {'.'}, 'nonempty or changed early archive')
    require(raw[core.EARLY_BYTES:core.EARLY_BYTES + 2] == b'\x1f\x8b',
            'gzip must begin immediately at byte 512')
    compressed = memoryview(raw)[core.EARLY_BYTES:]
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    expanded = decoder.decompress(compressed, core.MAX_EXPANDED - core.EARLY_BYTES + 1)
    require(len(expanded) + core.EARLY_BYTES <= core.MAX_EXPANDED and
            not decoder.unconsumed_tail, 'expanded initramfs exceeds fixed limit')
    require(decoder.eof and not decoder.unused_data, 'truncated gzip, extra member or trailing data')
    crc, size = struct.unpack_from('<II', compressed, len(compressed) - 8)
    require(size == len(expanded) and crc == zlib.crc32(expanded), 'gzip CRC/ISIZE mismatch')
    main = core.Newc(expanded, 'main')
    return main, {'image': {'path': str(image), 'bytes': len(raw), 'sha256': digest(raw)},
                  'early': early.summary(), 'main': main.summary(),
                  'gzip': {'offset': core.EARLY_BYTES, 'bytes': len(compressed),
                           'expanded_bytes': len(expanded), 'members': 1,
                           'crc32': '%08x' % crc, 'crc_and_isize_verified': True,
                           'trailing_bytes': 0}}


def cache_entries(core, main, expected_cache):
    entry = main.regular('etc/ld.so.cache')
    require(set(expected_cache) == {'size', 'sha256'} and
            entry['size'] == expected_cache['size'] and entry['sha256'] == expected_cache['sha256'],
            'archive cache differs from target-ldconfig output identity')
    data = bytes(main.payload(entry))
    require(48 <= len(data) <= 1024**2 and data[:20] == b'glibc-ld.so.cache1.1' and
            data[28] & 3 == 2, 'not the fixed new little-endian glibc cache format')
    count, strings_size = struct.unpack_from('<II', data, 20)
    start, end = 48 + 24 * count, 48 + 24 * count + strings_size
    require(0 < count <= 256 and end <= len(data), 'invalid cache table bounds')

    def string(offset):
        require(start <= offset < end, 'cache string is outside its string table')
        final = data.find(b'\0', offset, end)
        require(final != -1 and final - offset <= 4096, 'unterminated cache string')
        return data[offset:final].decode('ascii')

    records = {}
    for i in range(count):
        flags, key, value, unused, hwcap = struct.unpack_from('<iIIIQ', data, 48 + 24 * i)
        require(flags == 0x0a03 and hwcap == 0, 'unexpected cache architecture or hwcap')
        soname, path = string(key), string(value)
        require(soname and '/' not in soname and path.startswith('/') and
                core.safe_name(path[1:]) == path[1:] and soname not in records,
                'duplicate soname or noncanonical cache path')
        elf = core.arm64_elf(main, path)
        dependency = dynamic_dependencies(bytes(main.payload(main.regular(path))))
        require(dependency['soname'] == soname, 'cache soname differs from library DT_SONAME')
        records[soname] = {'soname': soname, 'cache_path': path,
                           'resolved_path': elf['path'], 'size': elf['size'], 'sha256': elf['sha256']}
    return records, {**core.member_record(entry), 'architecture_flags': '0x0a03',
                     'entries': list(records.values()), 'all_cached_payloads_present_and_aarch64': True}


def manifest_records(core, manifest):
    require(set(manifest) == {'files'} and isinstance(manifest['files'], list) and
            len(manifest['files']) <= 512, 'unexpected bounded source manifest')
    result = {}
    for item in manifest['files']:
        path = canonical(core, item['path'])
        require(path not in result and isinstance(item['size'], int) and 0 <= item['size'] <= 64 * 1024**2,
                'duplicate/invalid manifest member')
        require(isinstance(item['sha256'], str) and len(item['sha256']) == 64 and
                all(c in '0123456789abcdef' for c in item['sha256']), 'invalid manifest SHA256')
        result[path] = item
    return result


def verify(image, fw_manifest, expected_cache, expected_libraries, early_policy_manifest,
           *, legacy_verifier, baseline_image, source_root, init_bootstrap, early_tools_manifest):
    result = {'schema_version': 1, 'passed': False, 'stage': 'fixed-inputs',
              'scope': 'explicit early-policy generic ARM64 archive qualification only',
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
        tools = manifest_records(core, early_tools_manifest)
        require(not tools, 'this fixed profile uses one in-process ELF bootstrap, no extra external tools')
        require(BOOTSTRAP_SIZE is not None and BOOTSTRAP_SHA is not None,
                'the reviewed ELF bootstrap has not yet been pinned for this profile')
        require(init_bootstrap['size'] == BOOTSTRAP_SIZE and init_bootstrap['sha256'] == BOOTSTRAP_SHA and
                init_bootstrap['mode'] == 0o755, 'bootstrap is not the explicitly approved ELF')
        bootstrap_source, unused = ordinary_bytes(Path(init_bootstrap['source_path']), 4 * 1024**2)
        require(len(bootstrap_source) == BOOTSTRAP_SIZE and digest(bootstrap_source) == BOOTSTRAP_SHA,
                'bootstrap source file differs from its approved bytes')
        dependencies = {'init': dynamic_dependencies(bootstrap_source)}
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
            'tool_roots': ['init'], 'needed_libraries': sorted(needed), 'elf_records': dependencies,
            'all_expected_libraries': list(expected_map.values())}
        result['stage'] = 'archive-boundaries'
        main, parsed = parse_image(core, Path(image))
        result.update(parsed)
        result['limits'] = {'archive_bytes': core.MAX_ARCHIVE, 'expanded_bytes': core.MAX_EXPANDED}
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
            record, data = source_payload(core, source_root, path)
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
                        struct.unpack_from('<I', data, 16)[0] == 35, 'original version 35 policy required')
            policy_records.append(core.member_record(entry))
        archive_policy = {path for path, entry in main.entries.items()
                          if path.startswith('etc/selinux/') and entry['kind'] != 'directory'}
        require(archive_policy == required, 'unexpected or missing /etc/selinux archive payload')
        result['early_policy'] = {'files_verified': len(policy_records), 'files': policy_records,
                                  'source_root': str(source_root), 'policy_version': 35}
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
        result['critical_members'] = {'init_bootstrap': init_elf,
            'saved_init': {**core.member_record(old_init), 'target': old_init['target']},
            'systemd': systemd, 'hook_shell': shell, 'selinux_hook': core.member_record(hook),
            'early_external_tools': []}
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
