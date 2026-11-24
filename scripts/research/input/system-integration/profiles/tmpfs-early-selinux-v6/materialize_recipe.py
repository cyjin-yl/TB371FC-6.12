#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Materialize the exact v6 recipe from repository-tracked source files.

Run inside the project builder with a source checkout/overlay containing this
profile. Refuse an existing destination; do not modify a previous recipe.
"""
import argparse
import hashlib
import json
from pathlib import Path

OUTPUT = Path('/work/fedora-input-system-recipe-r4-v4')
PROFILE = Path('scripts/research/input/system-integration/profiles/tmpfs-early-selinux-v6')
PARENT = Path('scripts/research/input/system-integration')
PROFILE_NAMES = ('assemble_system.py', 'boot_system_vm.py', 'early_initramfs.py',
                 'finalize_system.py', 'guest_pids_probe.py', 'guest_verify_system.py',
                 'run_pipeline.py', 'stage_system.py', 'system_common.py',
                 'qualify_udev_handoff.py', 'initrd-domain-proof.sh', 'initrd-domain-proof.service')
FIXED = {
    'verify_initramfs.py': (Path('scripts/research/rootfs/verify_initramfs.py'),
        '263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a'),
    'verify_early_policy_initramfs.py': (PARENT / 'verify_early_policy_initramfs.py',
        '58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e'),
    'probe_loaded_policy.py': (PARENT / 'probe_loaded_policy.py',
        'f861a0930cb0a9151d99b657c09f05dd7d271a2d51638b3bf0cc2626845d3487'),
    'verify_tmpfs_policy_initramfs.py': (PARENT / 'verify_tmpfs_policy_initramfs.py',
        '92f02fd33fcc5f7aaea6d1d0e06c04589af024b09e8f678f772798909c2ebb07'),
}


def identity(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def ordinary(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 256 * 1024:
        raise ValueError('ordinary bounded source required: ' + str(path))
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    args = parser.parse_args()
    root = args.repo
    if root.is_symlink() or not root.is_dir():
        raise ValueError('ordinary repository/overlay root required')
    manifest = json.loads(ordinary(root / PROFILE / 'profile-source-manifest.json'))
    if set(manifest) != set(PROFILE_NAMES):
        raise ValueError('exact v6 override source set required')
    values = {}
    for name in PROFILE_NAMES:
        raw = ordinary(root / PROFILE / name)
        if identity(raw) != manifest[name]:
            raise ValueError('v6 profile source changed: ' + name)
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        values[name] = raw
    for name, (relative, expected) in FIXED.items():
        raw = ordinary(root / relative)
        if identity(raw)['sha256'] != expected:
            raise ValueError('frozen supplemental source changed: ' + name)
        if name.endswith('.py'):
            compile(raw, name, 'exec')
        values[name] = raw
    base = ordinary(root / PROFILE / 'prior-profile-source-manifest.json')
    if hashlib.sha256(base).hexdigest() != '186af28df00e39617d9cb12030b881ca31846a228a9ed1f959da85bb75b13df7':
        raise ValueError('exact historical v5 source manifest required')
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh recipe prefix required')
    OUTPUT.mkdir()
    for name, raw in values.items():
        with (OUTPUT / name).open('xb') as stream:
            stream.write(raw)
        if name.endswith('.sh'):
            (OUTPUT / name).chmod(0o755)
    result = {name: identity(raw) for name, raw in sorted(values.items())}
    with (OUTPUT / 'recipe-manifest.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write('\n')
    provenance = {'schema_version': 1, 'source_repository': str(root),
                  'profile_source_directory': str(PROFILE),
                  'prior_v5_profile_source_manifest_sha256': hashlib.sha256(base).hexdigest(),
                  'profile_source_manifest': identity(ordinary(root / PROFILE / 'profile-source-manifest.json')),
                  'materializer': identity(Path(__file__).read_bytes()),
                  'output_directory': str(OUTPUT), 'old_recipes_modified': False,
                  'kernel_or_system_tested_by_materialization': False}
    with (OUTPUT / 'derivation.json').open('x') as stream:
        json.dump(provenance, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'output': str(OUTPUT), 'file_count': len(values),
                      'recipe_manifest': identity((OUTPUT / 'recipe-manifest.json').read_bytes())}, sort_keys=True))


if __name__ == '__main__':
    main()
