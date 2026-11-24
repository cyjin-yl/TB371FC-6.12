#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Materialize the exact v8 recipe from repository-tracked source files.

Run inside the project builder with a source checkout/overlay containing this
profile. Refuse an existing destination; do not modify a previous recipe.
"""
import argparse
import hashlib
import json
from pathlib import Path

OUTPUT = Path('/work/fedora-input-system-recipe-r4-v6')
PROFILE = Path('scripts/research/input/system-integration/profiles/persistent-result-v8')
PARENT = Path('scripts/research/input/system-integration')
PROFILE_NAMES = ('assemble_system.py', 'boot_system_vm.py', 'early_initramfs.py',
                 'finalize_system.py', 'guest_verify_system.py',
                 'run_pipeline.py', 'stage_system.py', 'system_common.py',
                 'qualify_udev_handoff.py', 'initrd-domain-proof.sh', 'initrd-domain-proof.service',
                 'guest_transient_worker.py', 'transient_protocol.py', 'probe_fd_route_v2.py',
                 'retain_policy_export.py', 'guest_result_file.py', 'read_vm_result.py',
                 'verify_runtime_policy_initramfs.py')
FIXED = {
    'verify_initramfs.py': (Path('scripts/research/rootfs/verify_initramfs.py'),
        '263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a'),
    'verify_early_policy_initramfs.py': (PARENT / 'verify_early_policy_initramfs.py',
        '58a5dba0186174c7442f73c2f8f0a2333599e6cbbcb1cf332169e5df558bfd1e'),
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
        raise ValueError('exact v8 override source set required')
    values = {}
    for name in PROFILE_NAMES:
        raw = ordinary(root / PROFILE / name)
        if identity(raw) != manifest[name]:
            raise ValueError('v8 profile source changed: ' + name)
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
    if hashlib.sha256(base).hexdigest() != '8b70be328295fa01789a34b7a8212c9424c926890889b2881002a7163d8c619f':
        raise ValueError('exact historical v7 source manifest required')
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
                  'prior_v7_profile_source_manifest_sha256': hashlib.sha256(base).hexdigest(),
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
