#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Materialize a strict R7 post-generic-VM input contract; never start QEMU.

The public bundles must already be staged as closed ordinary directories.
Supply independently reviewed SHA256 pins for the actual build, construction
and generic-VM terminal receipts. All payload identities come from those
receipts or full stable file reads. Full R7 qualification runs before a
successful preparation record is emitted. No contract is auto-activated.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re

import second_stage_r7_inputs as r7
from second_stage_inputs import checked_path, read_file, unique_object, require


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('ascii')


def save(path, value):
    with path.open('xb') as stream:
        stream.write(encoded(value))


def prepare(plan_path, out, *, build_sha256, construction_sha256, generic_vm_sha256):
    for pin in (build_sha256, construction_sha256, generic_vm_sha256):
        require(isinstance(pin, str) and re.fullmatch('[0-9a-f]{64}', pin) is not None,
                'explicit actual build, construction and generic-VM SHA256 pins required')
    plan_id, plan_stamp, raw = read_file(plan_path, maximum=1024**2, capture=True)
    plan = json.loads(raw, object_pairs_hook=unique_object)
    r7.exact(plan, {'kernel_bundle', 'construction_bundle', 'kernel_load_base', 'bootargs', 'files'}, 'R7 path plan')
    r7.exact(plan['files'], r7.LAUNCH_KEYS | {'qemu'}, 'R7 path plan launch files')
    for value in plan['files'].values():
        checked_path(value)
    kernel, evidence = (checked_path(plan[key]) for key in ('kernel_bundle', 'construction_bundle'))
    out = checked_path(str(out))
    require(not os.path.lexists(out) and not out.is_relative_to(kernel) and not out.is_relative_to(evidence),
            'new output directory outside input bundles required')
    stamps = {str(Path(plan_path)): plan_stamp}
    records, pinned_ids = {}, {}
    for key, path, pin in (
            ('build', kernel / 'build-result.json', build_sha256),
            ('construction', evidence / 'r7-construction-result.json', construction_sha256),
            ('generic_vm', evidence / 'r7-generic-vm-result.json', generic_vm_sha256)):
        identity, stamp, data = read_file(path, maximum=16 * 1024**2, capture=True)
        require(identity['sha256'] == pin, key + ' receipt differs from explicit caller pin')
        records[key] = json.loads(data, object_pairs_hook=unique_object)
        pinned_ids[key] = r7.stripped_id(identity)
        stamps[str(path)] = stamp
    build, construction, generic = (records[key] for key in ('build', 'construction', 'generic_vm'))
    ids = {}
    for name in sorted(r7.CONSTRUCTION_FILES | r7.GENERIC_VM_FILES):
        identity, stamp, unused = read_file(evidence / name, maximum=16 * 1024**2)
        ids[name], stamps[str(evidence / name)] = r7.stripped_id(identity), stamp
    require(ids['r7-construction-result.json'] == pinned_ids['construction']
            and ids['r7-generic-vm-result.json'] == pinned_ids['generic_vm'],
            'explicitly pinned terminal receipt changed during preparation')
    build_id, build_stamp, unused = read_file(kernel / 'build-result.json', maximum=1024**2)
    require(r7.stripped_id(build_id) == pinned_ids['build'], 'build receipt changed during preparation')
    stamps[str(kernel / 'build-result.json')] = build_stamp
    launch_files = {'kernel': build['artifacts']['Image'], 'config': build['artifacts']['kernel.config'],
        'certificate': build['artifacts']['signing-cert.der'], 'dtb': r7.STAGE2_DTB,
        'initrd': r7.stripped_id(construction['initrd']), 'rootfs': generic['final_rootfs']}
    contract = {'schema': r7.CONTRACT_SCHEMA, 'input_profile': r7.INPUT_PROFILE, 'release': r7.RELEASE,
        'rootfs_phase': r7.GENERIC_VM_PHASE, 'build_result': r7.stripped_id(build_id),
        'construction_files': {name: ids[name] for name in r7.CONSTRUCTION_FILES},
        'generic_vm_files': {name: ids[name] for name in r7.GENERIC_VM_FILES},
        'launch_files': launch_files, 'dtb_derivation': 'native-memory-reg-only-v1'}
    r7.validate_contract(contract)
    qemu_id, qemu_stamp, unused = read_file(Path(plan['files']['qemu']), maximum=512 * 1024**2)
    stamps[plan['files']['qemu']] = qemu_stamp
    manifest = {'schema_version': 1, 'input_profile': r7.INPUT_PROFILE, 'release': r7.RELEASE,
        'kernel_bundle': str(kernel), 'construction_bundle': str(evidence),
        'kernel_load_base': plan['kernel_load_base'], 'bootargs': plan['bootargs'],
        'files': {name: {'path': plan['files'][name], **entry} for name, entry in launch_files.items()}}
    manifest['files']['qemu'] = qemu_id
    r7.validate_manifest(manifest, contract)
    os.umask(0o077)
    out.mkdir(mode=0o700)
    contract_path, manifest_path = out / 'input-contract.json', out / 'input-manifest.json'
    save(contract_path, contract)
    save(manifest_path, manifest)
    contract_id = {'path': str(contract_path), **r7.raw_id(encoded(contract))}
    report = {'schema': 'tb371fc-r7-second-stage-preparation-v1', 'status': 'failed', 'plan': plan_id,
        'input_contract': contract_id, 'input_manifest': {'path': str(manifest_path), **r7.raw_id(encoded(manifest))},
        'contract_auto_activated': False, 'qemu_started': False, 'physical_boot_verified': False}
    try:
        prepared = r7.verify_inputs(manifest_path, contract_path, contract_id['sha256'])
        prepared['_stamps'].update(stamps)
        r7.verify_unchanged(prepared)
        report.update(status='verified', inputs_unchanged=True,
                      kernel_bundle_qualification=prepared['kernel_bundle_qualification'],
                      evidence_bindings=prepared['evidence_bindings'])
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save(out / 'qualification.json', report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--build-result-sha256', required=True)
    parser.add_argument('--construction-result-sha256', required=True)
    parser.add_argument('--generic-vm-result-sha256', required=True)
    args = parser.parse_args(argv)
    report = prepare(args.plan, args.out, build_sha256=args.build_result_sha256,
                     construction_sha256=args.construction_result_sha256,
                     generic_vm_sha256=args.generic_vm_result_sha256)
    print(json.dumps({'status': report['status'], 'input_contract': report['input_contract'],
                      'input_manifest': report['input_manifest'], 'qemu_started': False}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
