#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Freeze evidence only after the owned label and Enforcing VM both pass."""
import datetime
import json
from pathlib import Path
import subprocess

from system_common import IMAGE, INPUTS, PROFILE, ROOT, WORK, profile, run_guest, save, sha
from retain_policy_export import retain_policy_export


def identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary retained evidence required: ' + str(path))
    return {'size': path.stat().st_size, 'sha256': sha(path)}


def main():
    data = profile()
    runs = {}
    for phase in ('label', 'verify'):
        candidates = []
        for path in sorted(WORK.glob('vm-' + phase + '-[0-9][0-9]/result.json')):
            result = json.loads(path.read_text())
            if result.get('passed') and result.get('profile_sha256') == sha(PROFILE):
                candidates.append((path, result))
        if not candidates:
            raise ValueError('required successful VM phase missing: ' + phase)
        path, result = candidates[-1]
        if not result.get('qemu_exit_code') == 0:
            raise ValueError('VM did not exit cleanly')
        runs[phase] = {'run_name': path.parent.name, 'result': result, 'metadata': identity(path),
                       'serial': identity(path.parent / 'serial.log')}
    check = subprocess.run(['/usr/sbin/e2fsck', '-fn', str(IMAGE)], capture_output=True, text=True, timeout=120)
    with (WORK / 'filesystem.after-boot.txt').open('x') as stream:
        stream.write(check.stdout + check.stderr)
    if check.returncode != 0:
        raise ValueError('new VM image did not pass post-boot filesystem check')
    actual_policy = retain_policy_export(runs['verify']['result'])
    controller = runs['verify']['result']
    result_file = WORK / runs['verify']['run_name'] / 'guest-result.json'
    file_identity = identity(result_file)
    receipt = controller.get('persistent_result_metadata', {}).get('receipt', {})
    if (controller.get('persistent_result_qualified') is not True or
            controller.get('guest_file_status') != 'pass' or
            file_identity != {key: receipt.get(key) for key in ('size', 'sha256')}):
        raise ValueError('same-boot complete ordinary result was not retained exactly')
    envelope = json.loads(result_file.read_bytes())
    if (envelope.get('result') != controller.get('guest_result') or
            envelope.get('boot_id') != receipt.get('boot_id') or
            envelope.get('profile_sha256') != sha(PROFILE)):
        raise ValueError('retained full result no longer matches the evaluated envelope')
    actual_packages = run_guest(['/usr/bin/rpm', '-qa', '--qf', '%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\n'],
                                capture=True).stdout
    before = (WORK / 'baseline-records/packages.after.tsv').read_text()
    if sorted(actual_packages.splitlines()) != sorted(before.splitlines()):
        raise ValueError('qualified Fedora package identities changed')
    with (WORK / 'packages.verified.tsv').open('x') as stream:
        stream.write(actual_packages)
    qualification_name = 'udev-handoff-qualification-' + runs['verify']['run_name'] + '.json'
    queue_qualification = json.loads((WORK / qualification_name).read_text())
    if (queue_qualification.get('passed') is not True or
            queue_qualification.get('original_controller_result') != runs['verify']['metadata'] or
            queue_qualification.get('full_serial') != runs['verify']['serial']):
        raise ValueError('full-log event-storage/restore post-qualification is required')
    runtime = json.loads((WORK / 'runtime.json').read_text())
    for name, expected in runtime['runtime_files'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('offline system runtime changed: ' + name)
    runtime_summary = {key: value for key, value in runtime.items() if key != 'runtime_files'}
    kernel = json.loads((INPUTS / 'artifacts/research4-system-build.json').read_text())
    required = ('baseline-copy.json', 'kernel-transfer.json', 'runtime.json', 'system-profile.json',
                'configured.json', 'initramfs.json', 'initramfs-archive-verification.json',
                'maintenance-initramfs.json', 'maintenance-initramfs-verification.json',
                'baseline-copy-qualification.json', qualification_name,
                'early-policy-profile-inputs.json', 'initrd-proof-payloads.json',
                'image.before-boot.json', 'packages.verified.tsv', 'filesystem.after-boot.txt',
                'policy-replacement.json', 'actual-policy-export.json')
    retained = {name: identity(WORK / name) for name in required}
    jobs = {path.stem: json.loads(path.read_text()) for path in sorted((WORK / 'jobs').glob('*.json'))}
    record = {
        'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'generic_vm_system_verified', 'scope': 'host_build with isolated generic ARM64 virtual machine',
        'work': str(WORK), 'container': 'tb371fc-build-20261123',
        'kernel_release': data['kernel_release'], 'profile': data,
        'source_fedora_baseline_report_sha256': '66ac854b2bc938aed147afe0355b57fcbba856c874e9d82cec4cad663b1c87d9',
        'baseline_copy': json.loads((WORK / 'baseline-copy.json').read_text()),
        'kernel_transfer': json.loads((WORK / 'kernel-transfer.json').read_text()),
        'kernel_build_report': identity(INPUTS / 'artifacts/research4-system-build.json'),
        'kernel_and_module_inspection_passed': kernel['passed'],
        'runtime': runtime_summary, 'package_count': len(actual_packages.splitlines()),
        'installed_package_identities_reread_match': True,
        'label_vm': runs['label'], 'enforcing_vm': runs['verify'],
        'udev_handoff_postqualification': queue_qualification,
        'post_boot_filesystem_check_exit_code': check.returncode,
        'tested_image_after_clean_poweroff': {'path': str(IMAGE), **identity(IMAGE)},
        'initramfs': json.loads((WORK / 'initramfs.json').read_text()),
        'maintenance_initramfs': json.loads((WORK / 'maintenance-initramfs.json').read_text()),
        'early_policy_archive_verification': json.loads((WORK / 'initramfs-archive-verification.json').read_text()),
        'source_policy_replacement': json.loads((WORK / 'policy-replacement.json').read_text()),
        'same_boot_actual_exported_policy_retained': actual_policy,
        'same_boot_complete_result_file_retained': {'path': str(result_file), **file_identity,
            'boot_id': receipt['boot_id'], 'profile_sha256': receipt['profile_sha256'],
            'read_only_closed_image_extraction': True},
        'service_context_scope': 'strict existing sysadm_t for this controlled management validator and workers; unconfined_service_t FIFO restriction remains',
        'prior_r4_failed_vm_preserved': '/work/fedora-input-system-v3/vm-verify-01',
        'prior_early_relabel_failed_vm_preserved': '/work/fedora-input-system-v5/vm-verify-01',
        'prior_tmpfs_reload_and_pid1_fd_failed_vm_preserved': '/work/fedora-input-system-v6/vm-verify-01',
        'prior_pl061_fixture_varlink_and_framing_failed_vm_preserved': '/work/fedora-input-system-v7/vm-verify-01',
        'source_copy_race_preserved': '/work/fedora-input-system-v4/baseline-copy.json',
        'baseline_payload_comparison_sha256': '4fbba68f55e17ad2e170cc7c769829a516f3642f018776644c8bd7f5f8d530b5',
        'retained_metadata': retained,
        'recipe_files': {p.name: identity(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'completed_phase_jobs_before_finalizer': jobs,
        'normal_root_configuration': {'selinux': 'enforcing', 'policy': 'targeted',
                                      'validation_target_is_default': False,
                                      'automatic_tablet_kexec': False},
        'production_initramfs_scope': 'V3 requires explicit audit observation opt-in and actual linux,dummy-virt; this generic-VM qualification artifact is not a qualified tablet boot initramfs',
        'original_fedora_tree_written_by_this_profile': False,
        'old_research1_files_deleted_by_this_profile': False,
        'physical_tablet_booted': False, 'physical_tablet_modified': False,
        'tablet_input_tested': False, 'native_panel_tested': False, 'gpu_acceleration_tested': False,
        'all_hardware_accepted': False,
        'limits': [
            'The QEMU machine uses its generated generic virt DT, never the packaged Lenovo board DT.',
            'The packaged joint DT enables native display, touch and keyboard; it is not a physical probe or usability result.',
            'Current research DT retains qcom,adreno-smmu and dma-coherent; physical per-process initialization/isolation is untested.',
            'PCIe/WLAN, TFA amplifiers, Venus and other unresolved owner peripherals are not made complete by this system VM.',
            'Owner firmware bytes are staged and checked, not authenticated or exercised on tablet hardware.',
            'The old research1 runtime remains in this separate copy and its generic metadata is archived; active release is explicit.',
            'A real tablet entry/boot path, display/input timing, pen charging and Android parity remain separate unpassed gates.',
            'The earlier SSD copy failed to preserve POSIX ACLs and is retained; only the matching HDD copy is used.',
            'Input hashes and build recipes are fixed; an independent bit-identical rebuild of the complete distribution is not proven.',
            'Before this profile, PRoot query bindings changed three source directory mtimes; the failed copy remains failed, and the new quiescent copy was qualified independently.',
            'The controlled verifier and its owned workers use strict existing sysadm_t; this does not qualify every production daemon domain.',
            'The restrictions on unconfined_service_t FIFO transfer and init_t reading policy remain independently checked.',
            'V3 changes only this generic VM printk rate interval to 0 under explicit opt-in; audit queue loss is unchanged and any observed audit loss or suppression fails the run.',
            'Read-only debugfs does not replay the filesystem journal; unavailable post-failure evidence remains a failed transport contract.',
        ],
    }
    save('fedora-input-system-integration.json', record)
    print(json.dumps({'status': record['status'], 'module_count': runtime['module_count'],
                      'firmware_file_count': runtime['firmware_file_count'], 'package_count': record['package_count'],
                      'report': identity(WORK / 'fedora-input-system-integration.json')}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
