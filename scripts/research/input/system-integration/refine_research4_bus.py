#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Add bounded system-bus diagnostics to a fresh copy of the fixed R4 recipe.

The actual R3 templates and initial R4 derivation remain reproducible and
unchanged. The patch adds two real broker round trips and a --wait/--pipe
baseline, and emits failure diagnostics before the terminal host marker.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

BASE_MANIFEST_SHA = 'c532046cfb8458c8ee6a8ab545e95118f53b913c74b8e9882fce13aaf8a6f9c1'
PATCH_SHA = 'eec79e767b2bce6d86d96b38846ffdae9788efa7cae2dac4f94f1100baabf990'
OUTPUT = Path('/work/fedora-input-system-recipe-r4-v2')
NAMES = {'assemble_system.py', 'boot_system_vm.py', 'copy_baseline.py',
         'copy_local_baseline.py', 'finalize_system.py', 'guest_pids_probe.py',
         'guest_verify_system.py', 'run_pipeline.py', 'stage_system.py',
         'system_common.py', 'transfer_kernel.py', 'verify_initramfs.py'}
CHANGED = {
    'boot_system_vm.py': {'size': 12418, 'sha256': '36c857d202059420724004244f6fb20e154336c8a3de1ea7b689b74028fb9af3'},
    'guest_verify_system.py': {'size': 24852, 'sha256': '6ac07365728d57ea185e4ebbd87c8261d6fff21a10627f6885cf1bad5f66ff07'},
}


def raw_regular(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary source file required: ' + str(path))
    return path.read_bytes()


def identity(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--patch', type=Path, required=True)
    args = parser.parse_args()
    if args.base.is_symlink() or not args.base.is_dir():
        raise ValueError('ordinary fixed recipe directory required')
    manifest_raw = raw_regular(args.base / 'recipe-manifest.json')
    if hashlib.sha256(manifest_raw).hexdigest() != BASE_MANIFEST_SHA:
        raise ValueError('base recipe identity changed')
    manifest = json.loads(manifest_raw)
    if set(manifest) != NAMES:
        raise ValueError('base recipe inventory changed')
    source = {}
    for name in sorted(NAMES):
        raw = raw_regular(args.base / name)
        if identity(raw) != manifest[name]:
            raise ValueError('base source changed: ' + name)
        source[name] = raw
    patch_raw = raw_regular(args.patch)
    if hashlib.sha256(patch_raw).hexdigest() != PATCH_SHA:
        raise ValueError('exact reviewed diagnostic patch required')
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh independent R4 recipe prefix required')
    OUTPUT.mkdir()
    for name, raw in source.items():
        with (OUTPUT / name).open('xb') as stream:
            stream.write(raw)
    result = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(OUTPUT),
                             '--input', str(args.patch.resolve())],
                            capture_output=True, text=True, timeout=10)
    with (OUTPUT / 'patch-result.json').open('x') as stream:
        json.dump({'exit_code': result.returncode, 'stdout': result.stdout,
                   'stderr': result.stderr}, stream, indent=2, sort_keys=True)
        stream.write('\n')
    if result.returncode:
        raise ValueError('diagnostic patch did not apply exactly')
    output_manifest = {}
    for name in sorted(NAMES):
        raw = raw_regular(OUTPUT / name)
        expected = CHANGED.get(name, manifest[name])
        if identity(raw) != expected:
            raise ValueError('unexpected resulting source: ' + name)
        compile(raw, name, 'exec')
        output_manifest[name] = expected
    with (OUTPUT / 'recipe-manifest.json').open('x') as stream:
        json.dump(output_manifest, stream, sort_keys=True, indent=2)
        stream.write('\n')
    report = {'schema_version': 1, 'base_recipe_directory': str(args.base),
              'base_recipe_manifest_sha256': BASE_MANIFEST_SHA,
              'patch': identity(patch_raw), 'generator': identity(Path(__file__).read_bytes()),
              'output_directory': str(OUTPUT), 'files': output_manifest,
              'old_sources_modified': False, 'kernel_or_system_tested': False,
              'selinux_enforcement_weakened': False, 'private_socket_bypass_added': False,
              'failure_diagnostics_precede_terminal_failure_marker': True}
    with (OUTPUT / 'derivation.json').open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(OUTPUT),
                      'recipe_manifest': identity((OUTPUT / 'recipe-manifest.json').read_bytes()),
                      'derivation': identity((OUTPUT / 'derivation.json').read_bytes())}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
