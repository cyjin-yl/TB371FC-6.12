#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Retain the completed v6 tmpfs-policy failure without changing any result."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re


def identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary closed evidence file required: ' + str(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'size': path.stat().st_size, 'sha256': digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    work = args.work
    if str(work) != '/work/fedora-input-system-v6' or work.is_symlink():
        parser.error('explicit independent project system prefix required')
    profile = json.loads((work / 'system-profile.json').read_text())
    release = profile['kernel_release']
    if not re.fullmatch(r'6\.12\.114-tb371fc-research4-system', release):
        raise ValueError('unexpected candidate release')
    results = {path.parent.name: json.loads(path.read_text())
               for path in sorted(work.glob('vm-*-??/result.json'))}
    failures = [name for name, result in results.items() if name.startswith('vm-verify-') and
                result.get('passed') is False and result.get('qemu_exit_code') is not None]
    if not failures:
        raise ValueError('a completed failed verification VM is required')
    latest = sorted(failures)[-1]
    if any(name > latest and name.startswith('vm-verify-') for name in results):
        raise ValueError('refusing to describe an earlier failure as the latest outcome')
    jobs = {path.name: json.loads(path.read_text()) for path in sorted((work / 'jobs').glob('*.json'))}
    vm_records = {}
    for name, result in results.items():
        vm_records[name] = {'result': result, 'metadata': identity(work / name / 'result.json'),
                           'serial': identity(work / name / 'serial.log')}
    metadata = {}
    for name in ('baseline-copy.json', 'stage01-prewrite-check.json', 'kernel-transfer.json',
                 'runtime.json', 'system-profile.json', 'configured.json', 'initramfs.json',
                 'initramfs-archive-verification.json', 'image.before-boot.json',
                 'maintenance-initramfs.json', 'maintenance-initramfs-verification.json',
                 'baseline-copy-qualification.json',
                 'early-policy-profile-inputs.json', 'initrd-proof-payloads.json',
                 'udev-handoff-qualification-vm-verify-01.json'):
        path = work / name
        if path.is_file():
            metadata[name] = identity(path)
    images = [work / 'fedora45-research4c-tmpfs-early-selinux.ext4']
    if len(images) != 1:
        raise ValueError('exactly one candidate image expected')
    report = {
        'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'generic_vm_verification_failed', 'overall_passed': False,
        'scope': 'host_build and isolated generic ARM64 virtual machine',
        'work': str(work), 'kernel_release': release, 'profile': profile,
        'latest_verification_run': latest, 'vm_runs': vm_records, 'phase_jobs': jobs,
        'retained_metadata': metadata,
        'failed_image_after_owned_qemu_exit': {'path': str(images[0]), **identity(images[0]),
                                              'clean_poweroff_claimed': False,
                                              'filesystem_repaired': False},
        'partial_progress_is_complete_acceptance': False,
        'physical_tablet_booted': False, 'physical_tablet_modified': False,
        'tablet_hardware_tested': False, 'all_hardware_accepted': False,
        'source_recipe': identity(Path(__file__)),
        'actual_execution_recipe_manifest': identity(Path('/work/fedora-input-system-recipe-r4-v4/recipe-manifest.json')),
        'maintenance_initramfs': json.loads((work / 'maintenance-initramfs.json').read_text()),
        'production_initramfs': json.loads((work / 'initramfs.json').read_text()),
        'native_early_policy_load_observed': any('TB371FC_EARLY_SELINUX_V1 POLICY_LOADED enforcing=1' in line
            for line in (work / latest / 'serial.log').read_text().splitlines()),
        'tmpfs_migration_and_initrd_domain_lines': [line for line in (work / latest / 'serial.log').read_text().splitlines()
            if 'TB371FC_TMPFS_STAGE' in line or 'TB371FC_R4C_INITRD_DOMAINS ' in line],
        'native_helper_and_security_failure_lines': [line for line in (work / latest / 'serial.log').read_text().splitlines()
            if 'TB371FC_EARLY_SELINUX_V1 ' in line or 'avc:' in line or 'Could not set context' in line],
        'limits': [
            'Partial progress reports only the named checks reached before failure.',
            'The completed failed VM is retained; no gate, image or log is overwritten.',
            'Every gate must execute again for any later candidate; partial initrd domains are not full-system success.',
            'The new root is ordinary tmpfs before policy load; this alone does not qualify every mounted API filesystem label.',
            'QEMU uses generic virt DT. The packaged Lenovo DT and firmware are not hardware tests.',
            'The compiled MODULE_SIG_FORCE setting and the explicit VM module.sig_enforce argument are distinct.',
        ],
    }
    output = work / 'fedora-input-system-attempt.json'
    with output.open('x') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'latest_run': latest, 'report': identity(output)}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
