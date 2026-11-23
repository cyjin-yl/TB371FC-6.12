#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive a separate R4 system recipe from the exact retained R3 templates.

This changes only the candidate's explicit scope/identifiers and adds the
source-confirmed ARM64 ftrace configuration requirements. It does not alter an
R3 source, image, module, log or failed result. All gates still execute on R4.
"""
import argparse
import hashlib
import json
from pathlib import Path

TEMPLATES = {
    "assemble_system.py": {
        "sha256": "e37b22e8d8d3b7337f85c0616e5e8ed0f63888a4dfe0d9701b00cad15c5b1598",
        "size": 8975
    },
    "boot_system_vm.py": {
        "sha256": "a2c7414833c83575ebffcac98e69ca7754fe15a87337c675000a9bd039603fbf",
        "size": 11836
    },
    "copy_baseline.py": {
        "sha256": "21e2d3b9887a52ed9fce96366eb71930fd9f5bcdfed901145cfc3a84ebd54ea0",
        "size": 8973
    },
    "copy_local_baseline.py": {
        "sha256": "e47bb6f6f59af80bd1fc1014e3d83db1537371f641ec7997dae7bacc7ffbbf6b",
        "size": 7265
    },
    "finalize_system.py": {
        "sha256": "4d20f1993d43a29ec9ba8b0cee7295d08391c0f8bd0ffc94d64d8a55fc418c06",
        "size": 6562
    },
    "guest_pids_probe.py": {
        "sha256": "61bfe7f65b421034a977e1ff9c6f471f48bcf496a2bb76b073fb6b217ef21dbe",
        "size": 2495
    },
    "guest_verify_system.py": {
        "sha256": "f11609dced375260877413e8dd18666f64a3ee6dbc166d3a7ea81226aa699660",
        "size": 16845
    },
    "run_pipeline.py": {
        "sha256": "0d54280b239a05a336cfbc01124fc84901fb1d8db6543a7dd249f2b3c2d38067",
        "size": 4256
    },
    "stage_system.py": {
        "sha256": "2a822ce860b728e54e0b7ce1d72995ddbcb845c5fd77d1569171acce69f1a18b",
        "size": 11839
    },
    "system_common.py": {
        "sha256": "c3c4b815d04a6080f8bce1f7ab444cd3743bfd760cfc456178d509ff4c1e6ecd",
        "size": 3584
    },
    "transfer_kernel.py": {
        "sha256": "4af6d802836ea97b0c0698c83e51d9f1e0424891fcee77b6c7f8f71b17ba6fa1",
        "size": 6794
    },
    "verify_initramfs.py": {
        "sha256": "263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a",
        "size": 20506
    }
}
TEMPLATE_MANIFEST_SHA = 'dcd451b8d7bc50033f5f7dcbd4fa671af968f27df5f4fef4580de4c0ba7fb1b0'
OUTPUT = Path('/work/fedora-input-system-recipe-r4-v1')
CHANGES = (
    ('research3-display-input-fedora45-v2', 'research4-display-input-fedora45-v3'),
    ('/work/fedora-input-system-v2', '/work/fedora-input-system-v3'),
    ('research3', 'research4'),
    ('tb371fc-r3', 'tb371fc-r4'),
    ('tb371fc.r3-', 'tb371fc.r4-'),
    ('TB371FC_R3', 'TB371FC_R4'),
    ('r3-kernel-', 'r4-kernel-'),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--templates', type=Path, required=True)
    parser.add_argument('--validator', type=Path)
    args = parser.parse_args()
    manifest_bytes = (json.dumps(TEMPLATES, sort_keys=True, indent=2) + '\n').encode()
    if hashlib.sha256(manifest_bytes).hexdigest() != TEMPLATE_MANIFEST_SHA:
        raise ValueError('template manifest definition changed')
    source = {}
    for name, identity in TEMPLATES.items():
        path = args.templates / name
        if name == 'verify_initramfs.py' and args.validator is not None:
            path = args.validator
        if path.is_symlink() or not path.is_file():
            raise ValueError('ordinary fixed template required: ' + name)
        raw = path.read_bytes()
        if len(raw) != identity['size'] or hashlib.sha256(raw).hexdigest() != identity['sha256']:
            raise ValueError('template content changed: ' + name)
        source[name] = raw.decode()
    derived = {}
    transformations = {}
    for name, original in source.items():
        body = original
        counts = {}
        # The tar-pump and archive verifier retain their original exact bytes.
        if name not in ('copy_baseline.py', 'verify_initramfs.py'):
            for old, new in CHANGES:
                count = body.count(old)
                if count:
                    counts[old] = {'replacement': new, 'count': count}
                    body = body.replace(old, new)
            if name == 'stage_system.py':
                anchor = "'CONFIG_MODULE_SIG_SHA512=y', 'CONFIG_SECURITY_SELINUX=y'}"
                replacement = ("'CONFIG_MODULE_SIG_SHA512=y', 'CONFIG_SECURITY_SELINUX=y', "
                               "'CONFIG_FUNCTION_TRACER=y', 'CONFIG_DYNAMIC_FTRACE=y', "
                               "'CONFIG_DYNAMIC_FTRACE_WITH_ARGS=y', "
                               "'CONFIG_DYNAMIC_FTRACE_WITH_CALL_OPS=y', "
                               "'CONFIG_DYNAMIC_FTRACE_WITH_DIRECT_CALLS=y', "
                               "'CONFIG_FTRACE_MCOUNT_RECORD=y', "
                               "'CONFIG_FTRACE_MCOUNT_USE_PATCHABLE_FUNCTION_ENTRY=y'}")
                if body.count(anchor) != 1:
                    raise ValueError('precise resolved-config guard anchor changed')
                body = body.replace(anchor, replacement)
                counts['required_config_addition'] = ['FUNCTION_TRACER', 'DYNAMIC_FTRACE',
                    'DYNAMIC_FTRACE_WITH_ARGS', 'DYNAMIC_FTRACE_WITH_CALL_OPS',
                    'DYNAMIC_FTRACE_WITH_DIRECT_CALLS', 'FTRACE_MCOUNT_RECORD',
                    'FTRACE_MCOUNT_USE_PATCHABLE_FUNCTION_ENTRY']
        compile(body, name, 'exec')
        derived[name] = body.encode()
        transformations[name] = counts
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh independent R4 recipe prefix required')
    OUTPUT.mkdir()
    manifest = {}
    for name, raw in derived.items():
        with (OUTPUT / name).open('xb') as stream:
            stream.write(raw)
        manifest[name] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    with (OUTPUT / 'recipe-manifest.json').open('x') as stream:
        json.dump(manifest, stream, sort_keys=True, indent=2)
        stream.write('\n')
    report = {'schema_version': 1, 'source_template_manifest_sha256': TEMPLATE_MANIFEST_SHA,
              'source_template_directory': str(args.templates), 'output_directory': str(OUTPUT),
              'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'transformations': transformations, 'files': manifest,
              'old_r3_files_modified': False, 'r3_results_reused_as_r4_passes': False,
              'r4_kernel_or_system_tested': False}
    with (OUTPUT / 'derivation.json').open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(OUTPUT),
                      'recipe_manifest_sha256': hashlib.sha256((OUTPUT / 'recipe-manifest.json').read_bytes()).hexdigest(),
                      'derivation_sha256': hashlib.sha256((OUTPUT / 'derivation.json').read_bytes()).hexdigest()},
                     sort_keys=True), flush=True)


if __name__ == '__main__':
    main()

