#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Produce separate maintenance and Enforcing early-policy initramfs files.

Only this new project's root is executed with PRoot. The fixed original Fedora
root is read natively for immutable policy/library payload qualification.
"""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

from system_common import QEMU, ROOT, WORK, check, copy_new, profile, run_guest, save, sha

HERE = Path(__file__).resolve().parent
LEGACY = HERE / 'verify_initramfs.py'
LEGACY_SHA = '263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a'
CHECKER = HERE / 'verify_tmpfs_policy_initramfs.py'
CHECKER_SHA = '92f02fd33fcc5f7aaea6d1d0e06c04589af024b09e8f678f772798909c2ebb07'
PARENT_CHECKER_SHA = '58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e'
SOURCE = Path('/work/fedora-system-integration-v1/rootfs')
BASELINE = SOURCE / 'boot/initramfs-6.12.114-tb371fc-research1.img'
BASELINE_SHA = '2741ed3f3b5814b40dd303f4666b6f629c55ad11fd057a6e99f9f6be5e01c543'
BOOTSTRAP = Path('/work/early-selinux-bootstrap-20261123/build-01/early-init')
BOOTSTRAP_SHA = 'e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d'
PROOF_SCRIPT_SHA = 'cbc552d75f53aae74ea55e2941aa5c573ac042550ff8688ae627ccd854440b7d'
PROOF_UNIT_SHA = 'c45c0163c610c58ab01d570ed32992c6b361a3249bf256c37be6387c6a607543'
HANDOFF = {
    'init.tmpfs': {'path': Path('/work/early-selinux-rootfs-20261123/build-01/source/stage0.sh'),
                   'size': 6039, 'sha256': '15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d'},
    'init.tmpfs-wait': {'path': Path('/work/early-selinux-rootfs-20261123/build-01/init.tmpfs-wait'),
                        'size': 71872, 'sha256': 'cc30c123b32259b1097eeb2f34cc13528d510cfc2521aac170bae23c4880a63a'},
    'usr/bin/switch_root': {'path': SOURCE / 'usr/bin/switch_root', 'size': 69104,
                            'sha256': '6b6c1803111f117b76b553a664cec1a074827d025618446319d7871f9c127f75'},
}
FW = ROOT / 'usr/share/tb371fc/stock-firmware-manifest.json'


def module(path, expected):
    check(path, expected)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary explicit source required: ' + str(path))
    return {'size': path.stat().st_size, 'sha256': sha(path)}


def install_fixed(source, destination, expected, mode=None):
    check(source, expected)
    copy_new(source, destination)
    if mode is not None:
        destination.chmod(mode)
    check(destination, expected)


def cache_and_listing(tree, role, expected):
    cache = tree / 'etc/ld.so.cache'
    if cache.exists() or cache.is_symlink():
        cache.rename(WORK / ('initramfs-' + role + '-previous-cache'))
    # The target's actual static AArch64 ldconfig, outside PRoot, resolves its
    # own -r tree; the host loader/cache is never used for these records.
    subprocess.run([str(QEMU), str(ROOT / 'usr/sbin/ldconfig'), '-X', '-r', str(tree)],
                   check=True, timeout=120)
    listing = subprocess.run([str(QEMU), str(ROOT / 'usr/sbin/ldconfig'), '-p', '-C', str(cache)],
                             check=True, capture_output=True, text=True, timeout=60).stdout
    if len(listing.encode()) > 128 * 1024:
        raise ValueError('target loader listing outside bound')
    actual = {}
    for line in listing.splitlines():
        if '=>' not in line:
            continue
        match = re.fullmatch(r'\s*(\S+)\s+\(libc6,AArch64\)\s+=>\s+(\S+)\s*', line)
        if not match or match[1] in actual:
            raise ValueError('unqualified target cache mapping: ' + line)
        actual[match[1]] = match[2]
    wanted = {item['soname']: item['cache_path'] for item in expected}
    if actual != wanted or not {'libc.so.6', 'libselinux.so.1'}.issubset(actual):
        raise ValueError('actual ARM ldconfig semantic map differs from qualified sources')
    with (WORK / ('initramfs-' + role + '-target-ldconfig.txt')).open('x') as stream:
        stream.write(listing)
    return identity(cache)


def pack(early, tree, role):
    archives, counts = {}, {}
    for name, directory in (('early', early), ('main', tree)):
        names = ['.'] + ['./' + path.relative_to(directory).as_posix()
                         for path in sorted(directory.rglob('*'))]
        archive = WORK / ('initramfs-' + role + '-' + name + '.cpio')
        with archive.open('xb') as stream:
            subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '--owner', '0:0', '--quiet'],
                           cwd=directory, input=('\0'.join(names) + '\0').encode(),
                           stdout=stream, check=True, timeout=120)
        archives[name], counts[name] = archive, len(names)
    output = WORK / ('initramfs-' + role + '-qualified.img')
    with output.open('xb') as stream:
        with archives['early'].open('rb') as prefix:
            shutil.copyfileobj(prefix, stream)
        stream.flush()
        subprocess.run(['gzip', '-n', '-c', str(archives['main'])], stdout=stream, check=True, timeout=180)
    return output, counts


def proof_payloads(checker, legacy, image):
    archive, unused = checker.parse_image(legacy, image)
    expected = {
        'usr/libexec/tb371fc-r4c-initrd-domain-proof.sh': (HERE / 'initrd-domain-proof.sh', 0o755),
        'usr/lib/systemd/system/tb371fc-r4c-initrd-domain-proof.service':
            (HERE / 'initrd-domain-proof.service', 0o644),
    }
    records = []
    for name, (source, mode) in expected.items():
        entry = archive.regular(name)
        if (entry['path'] != name or entry['size'] != source.stat().st_size or
                entry['sha256'] != sha(source) or stat.S_IMODE(entry['mode']) != mode):
            raise ValueError('actual initrd process-proof payload differs from source')
        records.append(legacy.member_record(entry))
    link = 'usr/lib/systemd/system/initrd.target.wants/tb371fc-r4c-initrd-domain-proof.service'
    entry = archive.entries.get(link)
    if (not entry or entry['kind'] != 'symlink' or
            entry['target'] != '../tb371fc-r4c-initrd-domain-proof.service' or
            archive.resolve(link)['path'] != 'usr/lib/systemd/system/tb371fc-r4c-initrd-domain-proof.service'):
        raise ValueError('actual initrd process-proof activation link is missing or changed')
    records.append({**legacy.member_record(entry), 'target': entry['target']})
    return {'passed': True, 'scope': 'archive bytes and activation only; actual process domains require VM',
            'files': records, 'runtime_domains_tested_by_this_check': False}


def build():
    if not all((CHECKER_SHA, PROOF_SCRIPT_SHA, PROOF_UNIT_SHA)):
        raise ValueError('v6 checker/proof source freeze is not yet complete')
    check(HERE / 'verify_early_policy_initramfs.py', PARENT_CHECKER_SHA)
    for item in HANDOFF.values():
        check(item['path'], item['sha256'], item['size'])
        if stat.S_IMODE(item['path'].stat().st_mode) != 0o755:
            raise ValueError('fixed executable handoff input has unexpected mode')
    data = profile()
    release = data['kernel_release']
    output = ROOT / 'boot' / f'initramfs-{release}.img'
    maintenance = ROOT / 'boot' / f'initramfs-{release}-maintenance.img'
    for path in (output, maintenance, WORK / 'initramfs.json', WORK / 'maintenance-initramfs.json'):
        if path.exists() or path.is_symlink():
            raise ValueError('fresh explicit initramfs outputs required: ' + str(path))
    if list((ROOT / 'var/tmp').glob('dracut.*/initramfs')):
        raise ValueError('unexpected old dracut trees in the new root')
    check(BASELINE, BASELINE_SHA, 30649939)
    check(BOOTSTRAP, BOOTSTRAP_SHA, 72048)
    check(HERE / 'initrd-domain-proof.sh', PROOF_SCRIPT_SHA)
    check(HERE / 'initrd-domain-proof.service', PROOF_UNIT_SHA)
    legacy = module(LEGACY, LEGACY_SHA)
    checker = module(CHECKER, CHECKER_SHA)
    original = legacy.verify(BASELINE, FW)
    if not original['passed']:
        raise ValueError('immutable old baseline failed the unmodified old verifier')
    baseline_elfs = {item['path']: item for item in original['runtime_elfs']['files']}
    old_libraries = [{key: item[key] for key in ('soname', 'cache_path', 'resolved_path', 'sha256')} |
                     {'size': baseline_elfs[item['resolved_path']]['size']}
                     for item in original['ld_so_cache']['entries']]
    expected_libraries = old_libraries + [checker.EXTRA_LIBRARY_CATALOG['libsepol.so.2']]
    if len({item['soname'] for item in expected_libraries}) != len(expected_libraries):
        raise ValueError('qualified closure unexpectedly overlaps the original cache')
    policy_names = {'etc/selinux/config', 'etc/selinux/targeted/policy/policy.35'}
    context = SOURCE / 'etc/selinux/targeted/contexts'
    for path in context.rglob('*'):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError('policy source tree contains a nonordinary entry')
        if path.is_file():
            policy_names.add(path.relative_to(SOURCE).as_posix())
    policy_manifest = {'files': []}
    for name in sorted(policy_names):
        record, unused = checker.source_payload(legacy, SOURCE, name)
        if record['resolved_path'] != name:
            raise ValueError('policy source path unexpectedly resolves elsewhere')
        policy_manifest['files'].append({key: record[key] for key in ('path', 'size', 'sha256')})
    for item in expected_libraries:
        record, unused = checker.source_payload(legacy, SOURCE, item['resolved_path'])
        if any(record[key] != item[key] for key in ('resolved_path', 'size', 'sha256')):
            raise ValueError('fixed library source differs from baseline/catalog')

    for name, target in {'fd': '/proc/self/fd', 'stdin': '/proc/self/fd/0',
                         'stdout': '/proc/self/fd/1', 'stderr': '/proc/self/fd/2'}.items():
        path = ROOT / 'dev' / name
        if path.is_symlink():
            if path.readlink().as_posix() != target:
                raise ValueError('unexpected descriptor alias')
        elif path.exists():
            raise ValueError('existing descriptor path is not the expected link')
        else:
            path.symlink_to(target)
    run_guest(['/usr/bin/dracut', '--no-hostonly', '--no-hostonly-cmdline',
               '--no-hostonly-default-device', '--fstab', '--kver', release,
               '--keep', '--modules', 'systemd systemd-initrd rootfs-block kernel-modules selinux',
               '--gzip', '--include', '/usr/lib/firmware', '/usr/lib/firmware',
               '/boot/' + output.name], timeout=900)
    raw_identity = identity(output)
    output.rename(WORK / 'initramfs.from-proot.img')
    trees = list((ROOT / 'var/tmp').glob('dracut.*/initramfs'))
    if len(trees) != 1:
        raise ValueError('exactly one retained dracut tree required')
    tree = trees[0]
    cache_and_listing(tree, 'maintenance', old_libraries)
    maintenance_archive, maintenance_counts = pack(tree.parent / 'earlycpio', tree, 'maintenance')
    validated = legacy.verify(maintenance_archive, FW)
    save('maintenance-initramfs-verification.json', validated)
    if not validated['passed']:
        raise ValueError('maintenance archive failed the unchanged original checker')
    copy_new(maintenance_archive, maintenance)
    save('maintenance-initramfs.json', {'path': str(maintenance), 'sha256': sha(maintenance),
         'size_bytes': maintenance.stat().st_size, 'kernel_release': release, 'archive_verified': True,
         'archive_validator_sha256': LEGACY_SHA, 'archive_entry_counts': maintenance_counts,
         'role': 'maintenance-label-only', 'production_early_policy': False,
         'enforcing_argument': 0, 'original_proot_archive': raw_identity, 'physical_hardware_tested': False})

    production = WORK / 'production-initramfs-tree'
    shutil.copytree(tree, production, symlinks=True)
    original_init = production / 'init'
    if not original_init.is_symlink() or (production / 'init.systemd').exists():
        raise ValueError('new production tree must retain original init symlink')
    original_init.rename(production / 'init.systemd')
    install_fixed(BOOTSTRAP, original_init, BOOTSTRAP_SHA, 0o755)
    for name, item in HANDOFF.items():
        install_fixed(item['path'], production / name, item['sha256'], 0o755)
    for item in policy_manifest['files']:
        install_fixed(SOURCE / item['path'], production / item['path'], item['sha256'])
    new_lib = checker.EXTRA_LIBRARY_CATALOG['libsepol.so.2']
    install_fixed(SOURCE / new_lib['resolved_path'], production / new_lib['resolved_path'], new_lib['sha256'])
    install_fixed(HERE / 'initrd-domain-proof.sh',
                  production / 'usr/libexec/tb371fc-r4c-initrd-domain-proof.sh', PROOF_SCRIPT_SHA, 0o755)
    install_fixed(HERE / 'initrd-domain-proof.service',
                  production / 'usr/lib/systemd/system/tb371fc-r4c-initrd-domain-proof.service', PROOF_UNIT_SHA, 0o644)
    link = production / 'usr/lib/systemd/system/initrd.target.wants/tb371fc-r4c-initrd-domain-proof.service'
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to('../tb371fc-r4c-initrd-domain-proof.service')
    expected_cache = cache_and_listing(production, 'production', expected_libraries)
    production_archive, counts = pack(tree.parent / 'earlycpio', production, 'production')
    inputs = {'expected_cache': expected_cache, 'expected_libraries': expected_libraries,
              'early_policy_manifest': policy_manifest,
              'init_bootstrap': {'size': 72048, 'sha256': BOOTSTRAP_SHA, 'mode': 0o755,
                                 'source_path': str(BOOTSTRAP)},
              'early_tools_manifest': {'files': [
                  {'path': name, 'size': item['size'], 'sha256': item['sha256'],
                   'mode': 0o755, 'source_path': str(item['path'])}
                  for name, item in sorted(HANDOFF.items())]}}
    save('early-policy-profile-inputs.json', inputs)
    validated = checker.verify(production_archive, FW, expected_cache, expected_libraries, policy_manifest,
                               legacy_verifier=LEGACY, baseline_image=BASELINE, source_root=SOURCE,
                               init_bootstrap=inputs['init_bootstrap'], early_tools_manifest=inputs['early_tools_manifest'])
    save('initramfs-archive-verification.json', validated)
    if not validated['passed']:
        raise ValueError('production archive failed the pinned early-policy checker: ' + str(validated.get('error')))
    proof = proof_payloads(checker, legacy, production_archive)
    save('initrd-proof-payloads.json', proof)
    copy_new(production_archive, output)
    save('initramfs.json', {'path': str(output), 'sha256': sha(output), 'size_bytes': output.stat().st_size,
         'kernel_release': release, 'archive_verified': True, 'archive_validator_sha256': CHECKER_SHA,
         'original_legacy_validator_sha256': LEGACY_SHA, 'qualified_baseline_image_sha256': BASELINE_SHA,
         'target_cache_sha256': expected_cache['sha256'], 'archive_entry_counts': counts,
         'role': 'production-tmpfs-early-selinux', 'enforcing_argument': 1,
         'kernel_rdinit_argument': 'rdinit=/init.tmpfs',
         'tmpfs_migration_argument': 'rd.tb371fc.tmpfs-root=1',
         'handoff_members': inputs['early_tools_manifest']['files'],
         'early_selinux_argument': 'rd.tb371fc.early-selinux=1', 'bootstrap': inputs['init_bootstrap'],
         'policy_source_manifest_sha256': sha(WORK / 'early-policy-profile-inputs.json'),
         'process_domain_proof_payloads_verified': proof['passed'],
         'cache_created_by': 'fixed Fedora static AArch64 ldconfig through QEMU outside PRoot',
         'cache_semantic_map_matches_fixed_sources': True,
         'repacked_by': 'GNU cpio newc, flushed early prefix, gzip -n',
         'hostonly': False, 'physical_hardware_tested': False})
    retained = WORK / 'retained-dracut-trees'
    retained.mkdir()
    tree.parent.rename(retained / tree.parent.name)
    print('FEDORA_R4C_MAINTENANCE_AND_PRODUCTION_INITRAMFS_VERIFIED', flush=True)
