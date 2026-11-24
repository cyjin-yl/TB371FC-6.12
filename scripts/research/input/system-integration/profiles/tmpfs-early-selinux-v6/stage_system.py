#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Consume a frozen research4 public runtime bundle into the new Fedora tree.

Old research1 runtime files remain in this independently copied tree. Only its
generic metadata names are moved to an explicit archive before new metadata
is added. No firmware selection or kernel module is inferred from a filename.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from system_common import INPUTS, LABEL, PROFILE, ROOT, WORK, check, copy_new, relative, run_guest, save, sha

FW_SHA = '4feb4264605198fc56114fb8b8044ffcd51f662107270a857f59fdaf2e8bcf7c'
REQUIRED_ARTIFACTS = ('Image', 'board.dtb', 'kernel.config', 'Module.symvers',
                      'modules.SHA256SUMS', 'source-manifest.json', 'signing-cert.der', 'kernel.btf')
MODULE_METADATA = ('modules.builtin', 'modules.builtin.modinfo', 'modules.order')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-sha256', required=True)
    parser.add_argument('--bundle-sha256', required=True)
    args = parser.parse_args()
    if not all(re.fullmatch('[0-9a-f]{64}', s) for s in (args.report_sha256, args.bundle_sha256)):
        parser.error('explicit SHA-256 identities required')
    if PROFILE.exists() or (WORK / 'runtime.json').exists():
        raise ValueError('new profile must not already be staged')
    copied = json.loads((WORK / 'baseline-copy.json').read_text())
    if not copied['complete']:
        raise ValueError('baseline copy did not pass')
    check(INPUTS / 'bundle.json', args.bundle_sha256)
    bundle = json.loads((INPUTS / 'bundle.json').read_text())
    report_path = INPUTS / 'artifacts/research4-system-build.json'
    check(report_path, args.report_sha256)
    report = json.loads(report_path.read_text())
    release = report['kernel_release']
    if not report['passed'] or not re.fullmatch(r'6\.12\.114-tb371fc-research4-system', release):
        raise ValueError('qualified independent research4 build required')
    for name, identity in bundle['files'].items():
        check(INPUTS / relative(name), identity['sha256'], identity['size'])
    actual_files = set()
    for path in INPUTS.rglob('*'):
        if path.is_symlink():
            raise ValueError('no runtime bundle symlinks permitted')
        if path.is_file():
            actual_files.add(path.relative_to(INPUTS).as_posix())
    if actual_files != set(bundle['files']) | {'bundle.json'}:
        raise ValueError('undeclared runtime input files')
    for name in REQUIRED_ARTIFACTS:
        identity = report['files'][name]
        check(INPUTS / 'artifacts' / name, identity['sha256'], identity['size'])
    for name in MODULE_METADATA:
        identity = report['module_metadata'][name]
        if identity['artifact_name'] != name or identity['installed_path'] != f'lib/modules/{release}/{name}':
            raise ValueError('unexpected installed module metadata mapping')
        check(INPUTS / 'artifacts' / name, identity['sha256'], identity['size'])
    modules = report['modules']
    if not modules or len(modules) != report['module_count']:
        raise ValueError('module count does not match the inspector')
    if not (report['module_inventory']['installed_order_matches_build'] and
            report['module_inventory']['installed_module_set_matches_build']):
        raise ValueError('build and installed module inventories differ')
    expected_modules = {}
    for entry in modules:
        name = relative(entry['path']).as_posix()
        if not name.startswith('lib/modules/' + release + '/kernel/') or not name.endswith('.ko'):
            raise ValueError('unexpected kernel module path')
        if name in expected_modules:
            raise ValueError('duplicate kernel module')
        if not (entry['all_imported_crcs_match'] and entry['cms_verified']):
            raise ValueError('module ABI/signature inspection failed')
        if entry['vermagic'].split()[0] != release:
            raise ValueError('module release mismatch')
        check(INPUTS / 'modules' / name, entry['sha256'], entry['size'])
        expected_modules[name] = entry['sha256']
    actual_modules = {p.relative_to(INPUTS / 'modules').as_posix()
                      for p in (INPUTS / 'modules').rglob('*.ko')}
    if actual_modules != set(expected_modules):
        raise ValueError('unlisted/missing module in runtime bundle')
    parsed = {}
    for line in (INPUTS / 'artifacts/modules.SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        if name in parsed:
            raise ValueError('duplicate SHA inventory entry')
        parsed[name] = digest
    if parsed != expected_modules:
        raise ValueError('module SHA inventory does not match the build report')
    config = (INPUTS / 'artifacts/kernel.config').read_text().splitlines()
    required_config = {'CONFIG_CGROUP_PIDS=y', 'CONFIG_AUTOFS_FS=m', 'CONFIG_GPIO_PL061=y',
                       'CONFIG_FTRACE=y', 'CONFIG_KPROBES=y', 'CONFIG_KPROBE_EVENTS=y',
                       'CONFIG_BPF_EVENTS=y', 'CONFIG_BPF_LSM=y', 'CONFIG_DEBUG_INFO_BTF=y',
                       'CONFIG_MODULE_SIG=y', 'CONFIG_MODULE_SIG_ALL=y',
                       'CONFIG_MODULE_SIG_SHA512=y', 'CONFIG_SECURITY_SELINUX=y', 'CONFIG_FUNCTION_TRACER=y', 'CONFIG_DYNAMIC_FTRACE=y', 'CONFIG_DYNAMIC_FTRACE_WITH_ARGS=y', 'CONFIG_DYNAMIC_FTRACE_WITH_CALL_OPS=y', 'CONFIG_DYNAMIC_FTRACE_WITH_DIRECT_CALLS=y', 'CONFIG_FTRACE_MCOUNT_RECORD=y', 'CONFIG_FTRACE_MCOUNT_USE_PATCHABLE_FUNCTION_ENTRY=y'}
    if not required_config.issubset(set(config)):
        raise ValueError('required resolved research4 configuration is incomplete')
    certificate = INPUTS / 'artifacts/signing-cert.der'
    if certificate.read_bytes() not in (INPUTS / 'artifacts/Image').read_bytes():
        raise ValueError('public module signing certificate is absent from this Image')
    btf = report['kernel_btf']
    check(INPUTS / 'artifacts/kernel.btf', btf['sha256'], btf['size'])
    if not btf['exact_bytes_present_in_image']:
        raise ValueError('kernel BTF identity was not checked against Image')

    firmware_path = ROOT / 'usr/share/tb371fc/stock-firmware-manifest.json'
    check(firmware_path, FW_SHA)
    firmware = json.loads(firmware_path.read_text())
    runtime_files = {}
    for entry in firmware['files']:
        name = 'usr/' + relative(entry['destination']).as_posix()
        check(ROOT / name, entry['sha256'], entry['size_bytes'])
        runtime_files[name] = entry['sha256']
    if len(firmware['files']) != firmware['firmware_file_count']:
        raise ValueError('firmware manifest count mismatch')
    declared = {relative(e['destination']).as_posix() for e in firmware['files']}
    actual = {'lib/firmware/' + p.relative_to(ROOT / 'usr/lib/firmware').as_posix()
              for p in (ROOT / 'usr/lib/firmware').rglob('*') if p.is_file()}
    if actual != declared:
        raise ValueError('existing firmware tree differs from the frozen owner staging')
    destination_modules = ROOT / 'usr/lib/modules' / release
    if destination_modules.exists() or destination_modules.is_symlink():
        raise ValueError('new module release directory already exists')
    # All guarded inputs have been read before changing the new copy.
    for name, digest in expected_modules.items():
        destination = 'usr/' + name
        copy_new(INPUTS / 'modules' / name, ROOT / destination)
        runtime_files[destination] = digest
    for name in MODULE_METADATA:
        src = INPUTS / 'artifacts' / name
        copy_new(src, destination_modules / name)
        runtime_files[f'usr/lib/modules/{release}/{name}'] = sha(src)
    archive = ROOT / 'usr/share/tb371fc/archive/research1'
    archive.mkdir(parents=True)
    moved = []
    for name in ('kernel-build.json', 'kernel-source-manifest.json', 'modules.SHA256SUMS', 'runtime.json'):
        src = ROOT / 'usr/share/tb371fc' / name
        if src.is_symlink() or not src.is_file():
            raise ValueError('old metadata must be preserved as an ordinary file')
        digest = sha(src)
        src.rename(archive / name)
        moved.append({'from': 'usr/share/tb371fc/' + name,
                      'to': 'usr/share/tb371fc/archive/research1/' + name, 'sha256': digest})
    targets = {'Image': f'boot/Image-{release}',
               'board.dtb': f'boot/dtb-{release}/qcom/sm8250-lenovo-tb371fc-display-input.dtb',
               'kernel.config': f'boot/config-{release}',
               'source-manifest.json': 'usr/share/tb371fc/kernel-source-manifest.json',
               'modules.SHA256SUMS': 'usr/share/tb371fc/modules.SHA256SUMS',
               'signing-cert.der': 'usr/share/tb371fc/signing-cert.der',
               'kernel.btf': 'usr/share/tb371fc/kernel.btf',
               'research4-system-build.json': 'usr/share/tb371fc/kernel-build.json'}
    for name, target in targets.items():
        copy_new(INPUTS / 'artifacts' / name, ROOT / target)
        runtime_files[target] = sha(INPUTS / 'artifacts' / name)
    runtime_files['usr/share/tb371fc/stock-firmware-manifest.json'] = FW_SHA
    run_guest(['/usr/sbin/depmod', '-a', release])
    # The actual signed module supplies the expected identity for the guest's
    # autoload check; its hash and CMS verification are already pinned above.
    autofs = next((n for n in expected_modules if n.endswith('/autofs4.ko')), None)
    if autofs is None:
        raise ValueError('built autofs4 module missing')
    autofs_identity = {}
    for field in ('signer', 'sig_key', 'sig_hashalgo'):
        value = subprocess.run(['modinfo', '-F', field, str(INPUTS / 'modules' / autofs)],
                               check=True, capture_output=True, text=True).stdout.strip()
        if not value:
            raise ValueError('autofs4 signature metadata is incomplete')
        autofs_identity[field] = value
    runtime = {'schema_version': 1, 'kernel_release': release,
               'kernel_report_sha256': args.report_sha256, 'bundle_sha256': args.bundle_sha256,
               'module_count': len(expected_modules), 'firmware_file_count': len(firmware['files']),
               'runtime_files': runtime_files, 'firmware_manifest_sha256': FW_SHA,
               'old_runtime_metadata_preserved': moved, 'physical_tablet_tested': False,
               'firmware_authenticated_or_loaded_on_tablet': False}
    save('runtime.json', runtime)
    copy_new(WORK / 'runtime.json', ROOT / 'usr/share/tb371fc/runtime.json')
    profile = {'schema_version': 1, 'profile': 'research4-display-input-fedora45-v6-tmpfs-early-selinux',
               'kernel_release': release, 'root_label': LABEL,
               'module_count': len(expected_modules), 'firmware_file_count': len(firmware['files']),
               'runtime_manifest_sha256': sha(WORK / 'runtime.json'),
               'kernel_image_sha256': sha(INPUTS / 'artifacts/Image'),
               'board_dtb_sha256': sha(INPUTS / 'artifacts/board.dtb'),
               'kernel_btf_sha256': btf['sha256'], 'kernel_btf_size': btf['size'],
               'public_signing_certificate_sha256': sha(certificate),
               'autofs_module_signature': autofs_identity, 'validation_tasks_max': 128,
               'validation_selinux_context': 'system_u:system_r:initrc_t:s0',
               'early_selinux_required': True,
               'initramfs_root_type_required': 'tmpfs',
               'kernel_rdinit_required': '/init.tmpfs',
               'baseline_qualification_sha256': sha(WORK / 'baseline-copy-qualification.json'),
               'journal_acl_check': copied['journal_acl_check'],
               'configured_module_sig_force': 'CONFIG_MODULE_SIG_FORCE=y' in config,
               'vm_module_signature_enforcement_required': True,
               'module_enforcement_scope': 'module.sig_enforce=1 in this owned VM; compiled FORCE setting is unchanged',
               'scope': 'generic ARM64 VM; packaged Lenovo DT is not used by QEMU'}
    save('system-profile.json', profile)
    copy_new(WORK / 'system-profile.json', PROFILE)
    print(json.dumps({'runtime_staged': True, 'release': release,
                      'module_count': len(expected_modules), 'firmware_file_count': len(firmware['files']),
                      'profile_sha256': sha(PROFILE)}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
