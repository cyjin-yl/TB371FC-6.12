#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Rebind one completed R7 build/root construction to a paused model handoff.

The operator supplies the SHA-256 of a reviewed, versioned receipt contract.
No R7 output hash is guessed from R5/R6. This rehashes ordinary input bytes and
cross-checks recorded offline evidence; it does not rerun signing commands,
load modules, establish runtime enforcement, or grant native readiness.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from boot_formats import parse_arm64_image
from derive_second_stage_dtb import check_delta
from qualify_boot_bundle import BundleReader, canonical_path, fingerprint
from second_stage_inputs import (checked_path, read_file, require,
                                 unique_object, validate_identity)

INPUT_PROFILE = 'r7-rpmh-v1'
CONTRACT_SCHEMA = 'tb371fc-r7-second-stage-input-contract-v1'
ROOTFS_PHASE = 'constructed-unbooted-prelabel-v1'
GENERIC_VM_PHASE = 'generic-vm-verified-v1'
GENERIC_VM_WRAPPER_SHA = '5deaaa2619979af919b8047ee0410fe40f96257267c7acb5c2d2187626c27750'
GENERIC_VM_DRIVER_SHA = '4d1f59691bb4faccdcdbd791ae2120a89e56f7712fd63270f0a2204662842736'
GENERIC_VM_TOOLS = {
    '/usr/bin/qemu-system-aarch64': {'bytes': 34073536, 'sha256': '2e7fe3008a900980493a85e606036793fd162153edac0228477579988c53e1f5'},
    '/usr/sbin/debugfs': {'bytes': 255824, 'sha256': 'deb37b9515718738f369dfe0546a50a74fdd7d5837046adac272ef6a3381ccee'},
}
RELEASE = '6.12.114-tb371fc-research7-rpmh-clock'
LABEL = 'tb371fc-r7-f45'
SYSTEM_PROFILE = 'research7-rpmh-clock-fedora45-derived-v9'
PREFIX = 'modules/lib/modules/' + RELEASE + '/'
ROOTFS_BYTES = 4 * 1024**3
BUILD_RECIPE_SHA = '509aa9cb8f3b43292ae6708622066bec1d22eb92330d6dfb090a286534c2b5d6'
CONSTRUCTOR_SHA = 'f556256e8764b7c6060b05ffe5e7350046055d87e1393ed2acd9ef4c00126042'
SIGNATURE_VERIFIER_SHA = '8e7fb179b500bf13cfadd3843fdb3104a5740005f1cd394f2be8112732ee0082'
ABI_VERIFIER_SHA = '8e207831577a1537eec3e7a6d6f1ee0eeb0bd610db44c48f3736bf6af28734b9'
# Sorted module-relative paths, one ASCII path per line including final newline;
# derived from the frozen R6 receipt f37fbe20624e7f49... that the R7 builder uses.
MODULE_PATHS_SHA = '1c7cf3eaba0f882b5cf2124de70662955d8a0161a6fca15802dae77b3c2c00eb'
CONFIG = {'bytes': 223386, 'sha256': '84747cefce945deaf0134e52c3b1a8a2bf771f3082853d6903be59ab6d5a92a4'}
NATIVE_DTB = {'bytes': 126877, 'sha256': 'af80b06f38b73ea42cb669a2897721ba7ecc5a99a8aa3d6d9c1e9ba132597730'}
STAGE2_DTB = {'bytes': 126893, 'sha256': '7092d992582a2f49b65e8eb1a4209fede3b41ccbbacb3abc28d29b649b33423c'}
POLICY_SHA = 'ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798'
BOOTSTRAP_SHA = '0bc3f0fbb814ece1133b16e36c6b3c402fbf5456d366fb99f4fe2783c87c1d14'
METADATA = {'modules.builtin', 'modules.builtin.modinfo', 'modules.order'}
ARTIFACTS = {'Image', 'board.dtb', 'kernel.config', 'kernel.release', 'System.map',
             'Module.symvers', 'signing-cert.der', 'kernel.btf'} | METADATA
KERNEL_RECEIPTS = {'build-result.json', 'module-signatures.json',
                   'module-abi.json', 'source-inventory.json'}
CONSTRUCTION_FILES = {'r7-construction-result.json', 'r7-module-contract.json',
                      'r7-runtime-stage.json', 'runtime.json', 'system-profile.json',
                      'root-module-report.json', 'r7-initrd-modules.json',
                      'recipe/derivation.json'}
GENERIC_VM_FILES = {'r7-generic-vm-result.json', 'vm-label-01/result.json',
    'vm-label-01/command.json', 'vm-label-01/serial.log', 'vm-verify-01/result.json',
    'vm-verify-01/command.json', 'vm-verify-01/serial.log', 'vm-verify-01/guest-result.json',
    'r7-generic-vm/label.driver.log', 'r7-generic-vm/verify.driver.log',
    'r7-generic-vm/reparse-label/inspection.json', 'r7-generic-vm/reparse-verify/inspection.json',
    'r7-generic-vm/reparse-verify/guest-result.json'}
LAUNCH_KEYS = {'kernel', 'dtb', 'initrd', 'config', 'certificate', 'rootfs'}
RAW_KEYS = {'kernel', 'dtb', 'initrd', 'config', 'certificate'}
LAUNCH_LIMITS = {'kernel': 128 * 1024**2, 'dtb': 2 * 1024**2, 'initrd': 256 * 1024**2,
                 'config': 1024**2, 'certificate': 1024**2, 'rootfs': 4 * 1024**3}
SUPPLIERS = {'kernel/drivers/regulator/qcom-rpmh-regulator.ko',
             'kernel/drivers/interconnect/qcom/qnoc-sm8250.ko',
             'kernel/drivers/interconnect/qcom/icc-rpmh.ko',
             'kernel/drivers/interconnect/qcom/icc-bcm-voter.ko',
             'kernel/drivers/interconnect/qcom/interconnect_qcom.ko'}
REQUIRED_ARGS = {'rdinit': '/init.tmpfs', 'rd.tb371fc.early-selinux': '1',
                 'rd.tb371fc.tmpfs-root': '1', 'enforcing': '1',
                 'module.sig_enforce': '1', 'root': 'LABEL=' + LABEL,
                 'tb371fc.early_pgtable': 'memblock'}


def exact(value, keys, label):
    require(isinstance(value, dict) and set(value) == set(keys), label + ' fields differ')


def content_id(value, label='payload', maximum=8 * 1024**3):
    exact(value, {'bytes', 'sha256'}, label)
    require(type(value['bytes']) is int and 0 < value['bytes'] <= maximum,
            label + ' has invalid length')
    require(isinstance(value['sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', value['sha256']) is not None,
            label + ' has invalid SHA-256')
    return value


def stripped_id(value):
    return {key: value[key] for key in ('bytes', 'sha256')}


def mode_id(value, label, *, allow_empty=False):
    exact(value, {'bytes', 'sha256', 'mode'}, label)
    require(type(value['mode']) is int and 0 <= value['mode'] <= 0o777, label + ' has invalid file mode')
    if allow_empty and type(value['bytes']) is int and value['bytes'] == 0:
        require(value['sha256'] == hashlib.sha256(b'').hexdigest(), label + ' has invalid empty-file identity')
    else:
        content_id(stripped_id(value), label)
    return value


def raw_id(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def schema_one(value, label):
    require(isinstance(value, dict) and type(value.get('schema_version')) is int
            and value['schema_version'] == 1, label + ' schema differs')


def false_fields(value, fields, label):
    require(all(value.get(key) is False for key in fields), label + ' overstates its scope')


def validate_contract(contract):
    require(isinstance(contract, dict), 'R7 contract must be an object')
    phase = contract.get('rootfs_phase')
    require(phase in (ROOTFS_PHASE, GENERIC_VM_PHASE), 'unsupported R7 root qualification phase')
    extra = {'generic_vm_files'} if phase == GENERIC_VM_PHASE else set()
    exact(contract, {'schema', 'input_profile', 'release', 'build_result',
                     'construction_files', 'launch_files', 'dtb_derivation', 'rootfs_phase'} | extra, 'R7 contract')
    require(contract['schema'] == CONTRACT_SCHEMA and contract['input_profile'] == INPUT_PROFILE
            and contract['release'] == RELEASE, 'wrong R7 contract version or release')
    require(contract['dtb_derivation'] == 'native-memory-reg-only-v1', 'unsupported R7 DT derivation')
    if phase == GENERIC_VM_PHASE:
        require(isinstance(GENERIC_VM_WRAPPER_SHA, str), 'generic VM wrapper source is not frozen')
        exact(contract['generic_vm_files'], GENERIC_VM_FILES, 'generic VM evidence inventory')
        for name, entry in contract['generic_vm_files'].items():
            content_id(entry, name, 16 * 1024**2)
    content_id(contract['build_result'], 'build receipt', 1024**2)
    exact(contract['construction_files'], CONSTRUCTION_FILES, 'construction receipt inventory')
    for name, entry in contract['construction_files'].items():
        content_id(entry, name, 16 * 1024**2)
    exact(contract['launch_files'], LAUNCH_KEYS, 'contract launch inventory')
    for name, entry in contract['launch_files'].items():
        content_id(entry, name, LAUNCH_LIMITS[name])
    require(contract['launch_files']['config'] == CONFIG, 'not the exact R7 configuration')
    require(contract['launch_files']['dtb'] == STAGE2_DTB, 'not the exact declared RAM candidate')
    require(contract['launch_files']['rootfs']['bytes'] == ROOTFS_BYTES, 'R7 root must be exactly 4 GiB')
    return contract


def validate_manifest(manifest, contract):
    exact(manifest, {'schema_version', 'input_profile', 'release', 'kernel_bundle',
                     'construction_bundle', 'kernel_load_base', 'bootargs', 'files'}, 'R7 manifest')
    schema_one(manifest, 'manifest')
    require(manifest['input_profile'] == INPUT_PROFILE and manifest['release'] == RELEASE,
            'not the explicit R7 input profile and release')
    load = manifest['kernel_load_base']
    require(type(load) is int and 0x80000000 <= load < 0x280000000 and load % 0x200000 == 0
            and not 0xbbb00000 <= load < 0xc0000000, 'invalid simulated kernel load base')
    checked_path(manifest['kernel_bundle'])
    checked_path(manifest['construction_bundle'])
    exact(manifest['files'], LAUNCH_KEYS | {'qemu'}, 'R7 launch inventory')
    for name, entry in manifest['files'].items():
        validate_identity(entry, name)
        if name != 'qemu':
            require(stripped_id(entry) == contract['launch_files'][name],
                    'launch ' + name + ' differs from pinned R7 contract')
    require(manifest['files']['qemu']['bytes'] <= 512 * 1024**2, 'QEMU exceeds bounded profile')
    args = manifest['bootargs']
    require(isinstance(args, str) and 0 < len(args) <= 4096
            and all(32 <= ord(c) < 127 for c in args) and not any(c in args for c in '\"\''),
            'unsupported boot-argument syntax')
    tokens = args.split()
    require('--' not in tokens, 'kernel arguments after -- are not accepted')
    for key, value in REQUIRED_ARGS.items():
        matches = [token for token in tokens if token.split('=', 1)[0].replace('-', '_') == key.replace('-', '_')]
        require(matches == [key + '=' + value], 'missing or conflicting R7 argument: ' + key)
    require(not any(token.split('=', 1)[0].replace('-', '_') in
                    {'init', 'selinux', 'security', 'lsm', 'mem', 'memmap', 'efi', 'acpi', 'dtb', 'fdt'} for token in tokens),
            'unsupported handoff override in command line')
    return manifest


def validate_build(build, signatures, abi):
    for value, name in ((build, 'build'), (signatures, 'signature'), (abi, 'ABI')):
        schema_one(value, name)
        require(value.get('passed') is True and type(value.get('module_count')) is int
                and value['module_count'] == 84, name + ' must qualify 84 modules')
    require(build.get('kernel_release') == abi.get('kernel_release') == RELEASE,
            'build or ABI release differs')
    require(build.get('recipe', {}).get('sha256') == BUILD_RECIPE_SHA
            and build.get('retained_inputs_reverified') is True
            and build.get('offline_modules_qualified') is True,
            'completed reviewed R7 builder required')
    false_fields(build, ('old_objects_copied', 'old_private_key_copied',
                        'runtime_signature_enforcement_verified'), 'build')
    require(type(build.get('native_hardware_passes_added')) is int
            and build['native_hardware_passes_added'] == 0, 'build native scope differs')
    for report in (signatures, abi):
        require(report.get('input_snapshot_stable') is True, 'offline snapshot was unstable')
        false_fields(report, ('runtime_signature_enforcement_verified',), 'offline qualification')
    false_fields(signatures, ('kernel_keyring_trust_verified', 'module_loadability_verified',
                             'private_key_accessed', 'certificate_chain_validation'), 'signature receipt')
    false_fields(abi, ('runtime_module_loading_verified', 'btf_semantic_type_validation'), 'ABI receipt')
    require(signatures.get('verifier_source', {}).get('sha256') == SIGNATURE_VERIFIER_SHA
            and build['inputs']['signature_verifier']['sha256'] == SIGNATURE_VERIFIER_SHA
            and build['inputs']['abi_verifier']['sha256'] == ABI_VERIFIER_SHA,
            'recorded offline verifier source differs')
    require(type(signatures.get('expected_count')) is int and signatures['expected_count'] == 84
            and signatures.get('compressed_modules_not_verified') == [], 'signature coverage differs')
    exact(build['artifacts'], ARTIFACTS, 'R7 artifact inventory')
    for name, entry in build['artifacts'].items():
        content_id(entry, name, 128 * 1024**2)
    require(build['artifacts']['kernel.config'] == CONFIG and build['artifacts']['board.dtb'] == NATIVE_DTB,
            'R7 config or native DT identity differs')
    require(build['candidate_config'] == CONFIG
            and build['new_signing_certificate'] == build['artifacts']['signing-cert.der'],
            'build configuration or new certificate binding differs')
    modules = build['modules']
    require(isinstance(modules, dict) and len(modules) == 84, 'exactly 84 built modules required')
    for name, entry in modules.items():
        canonical_path(name)
        require(name.startswith(PREFIX + 'kernel/') and name.endswith('.ko'), 'foreign or invalid R7 module path')
        content_id(entry, name, 128 * 1024**2)
    relative = sorted(name[len(PREFIX):] for name in modules)
    require(hashlib.sha256(('\n'.join(relative) + '\n').encode('ascii')).hexdigest() == MODULE_PATHS_SHA,
            'module-relative path inventory differs from qualified R6/R7')
    certificate = build['artifacts']['signing-cert.der']
    require(signatures['public_certificate'].get('format') == 'DER'
            and stripped_id(signatures['public_certificate']) == certificate
            and signatures['public_certificate']['der_sha256'] == certificate['sha256'],
            'recorded signatures use a different public certificate')
    require(len(signatures['modules']) == len(abi['modules']) == 84, 'offline module row count differs')
    signed = {'modules/' + row['path']: stripped_id(row) for row in signatures['modules']}
    imported = {PREFIX + row['path']: stripped_id(row) for row in abi['modules']}
    require(signed == imported == modules, 'offline receipts cover different module bytes')
    require(all(row.get('passed') is True and row.get('verified_content_matches') is True
                and row.get('verified_signer_der_sha256') == certificate['sha256'] for row in signatures['modules']),
            'module signature evidence did not pass')
    require(all(row.get('imported_symbol_crcs_match') is True and row.get('debug_info_stripped') is True
                and row.get('vermagic') == RELEASE + ' SMP preempt mod_unload modversions aarch64'
                for row in abi['modules']), 'module ABI evidence did not pass')
    require(abi['module_symvers'] == build['artifacts']['Module.symvers'], 'ABI export table differs')
    exact(build['module_metadata'], METADATA, 'Kbuild metadata')
    for name, entry in build['module_metadata'].items():
        exact(entry, {'built', 'installed', 'relationship'}, name)
        content_id(entry['built'], name)
        require(entry['installed'] == build['artifacts'][name], 'installed metadata differs: ' + name)
        relation = 'Kbuild kernel-prefix and .o-to-.ko transform' if name == 'modules.order' else 'byte-identical'
        require(entry['relationship'] == relation and (name == 'modules.order' or entry['built'] == entry['installed']),
                'metadata relationship differs: ' + name)
    return modules


def validate_construction(docs, ids, build, build_id, launch_files, *, rootfs_phase=ROOTFS_PHASE):
    result = docs['r7-construction-result.json']
    schema_one(result, 'construction')
    require(result.get('complete') is True and result.get('kernel_release') == RELEASE
            and result.get('retained_inputs_reverified') is True
            and type(result.get('module_count')) is int and result['module_count'] == 84
            and result.get('constructor', {}).get('sha256') == CONSTRUCTOR_SHA,
            'completed reviewed R7 construction required')
    false_fields(result, ('physical_boot_verified', 'userspace_verified',
                         'runtime_signature_enforcement_verified'), 'construction')
    require(type(result.get('owner_native_linux_passes_added')) is int
            and result['owner_native_linux_passes_added'] == 0, 'construction native scope differs')
    require(result['build_result'] == build_id and result['profile'] == ids['system-profile.json'],
            'construction build or profile differs')
    exact(result['rootfs'], {'path', 'bytes', 'sha256', 'label'}, 'constructed root')
    exact(result['initrd'], {'path', 'bytes', 'sha256'}, 'constructed initrd')
    content_id(stripped_id(result['rootfs']), 'constructed root')
    require(result['rootfs']['label'] == LABEL and result['rootfs']['bytes'] == ROOTFS_BYTES
            and stripped_id(result['initrd']) == launch_files['initrd'], 'constructed launch payload differs')
    if rootfs_phase == ROOTFS_PHASE:
        require(stripped_id(result['rootfs']) == launch_files['rootfs'], 'constructed launch payload differs')
    elif rootfs_phase == GENERIC_VM_PHASE:
        validate_generic_vm(docs, ids, launch_files)
    else:
        raise ValueError('unsupported R7 root qualification phase')
    module_contract = docs['r7-module-contract.json']
    exact(module_contract, {'schema_version', 'scope', 'kernel', 'kernel_files', 'build_result',
                            'physical_boot_verified'}, 'R7 module contract')
    schema_one(module_contract, 'module contract')
    require(module_contract['kernel'] == {'release': RELEASE, 'module_count': 84}
            and module_contract['build_result'] == build_id, 'module contract build differs')
    false_fields(module_contract, ('physical_boot_verified',), 'module contract')
    expected = {**build['modules'], **{PREFIX + name: build['artifacts'][name] for name in METADATA}}
    rows = module_contract['kernel_files']
    require(isinstance(rows, list) and len(rows) == 87, 'module contract must bind 84 modules and three metadata files')
    for row in rows:
        exact(row, {'path', 'bytes', 'sha256', 'mode'}, 'module contract row')
        require(type(row['mode']) is int and 0 <= row['mode'] <= 0o777, 'module file mode invalid')
    require({row['path']: stripped_id(row) for row in rows} == expected, 'module contract file identities differ')
    stage = docs['r7-runtime-stage.json']
    mode_id(stage['root_module_report'], 'staged root-module report')
    require(stage.get('complete') is True and stage.get('kernel_release') == RELEASE
            and stage.get('stage_source', {}).get('sha256') == CONSTRUCTOR_SHA
            and stage['build_result'] == build_id
            and stripped_id(stage['root_module_report']) == ids['root-module-report.json'],
            'runtime stage construction binding differs')
    require(type(stage.get('owner_native_linux_passes_added')) is int
            and stage['owner_native_linux_passes_added'] == 0, 'runtime stage scope differs')
    root_report = docs['root-module-report.json']['root_module_tree']
    require(root_report.get('kernel_release') == RELEASE and root_report.get('module_count_expected') == 84
            and all(root_report.get(key) is True for key in ('passed', 'input_snapshot_stable',
                'module_bytes_verified', 'kbuild_metadata_verified', 'text_dependency_graph_verified',
                'binary_indexes_recorded', 'native_depmod_provenance_not_verified')),
            'constructed root module tree did not qualify')
    false_fields(root_report, ('binary_index_semantics_verified', 'rootfs_runtime_ready',
                               'physical_hardware_tested', 'rootfs_modified', 'target_code_executed'), 'root module report')
    tree = stage['module_tree']
    require(isinstance(tree, dict) and {name for name in tree if name.endswith('.ko')} ==
            {name[len(PREFIX):] for name in build['modules']}, 'root module inventory differs')
    for name, entry in expected.items():
        require(stripped_id(tree[name[len(PREFIX):]]) == entry, 'root signed module or metadata bytes differ')
    for name, entry in tree.items():
        canonical_path(name)
        require('.ko.' not in name, 'compressed module outside qualified inventory')
        mode_id(entry, 'root tree ' + name, allow_empty=True)
    root_rows = root_report['module_files'] + root_report['kbuild_metadata']
    require(len(root_report['module_files']) == 84 and len(root_report['kbuild_metadata']) == 3
            and {PREFIX + row['path']: {key: row[key] for key in ('bytes', 'sha256', 'mode')}
                 for row in root_rows} == {row['path']: {key: row[key] for key in ('bytes', 'sha256', 'mode')}
                                           for row in rows}, 'root report modules or metadata differ')
    require(all(tree[row['path']] == {key: row[key] for key in ('bytes', 'sha256', 'mode')}
                for row in root_report['indexes']), 'root depmod index bytes differ')
    closure = result['supplier_closure']
    require(isinstance(closure, list) and closure == sorted(set(closure))
            and SUPPLIERS <= set(closure) <= {name[len(PREFIX):] for name in build['modules']}
            and stage['supplier_closure'] == closure, 'supplier dependency closure differs')
    archives = docs['r7-initrd-modules.json']
    exact(archives, {'production', 'maintenance'}, 'initrd archive receipts')
    require(archives == result['archive_module_checks'], 'construction archive evidence differs')
    for role, archive in archives.items():
        require(archive.get('passed') is True and archive.get('kernel_release') == RELEASE
                and archive.get('signed_bytes_match_qualified_build') is True
                and archive.get('text_dependency_graph_matches_root') is True
                and archive['required_supplier_closure'] == closure, role + ' archive qualification differs')
        false_fields(archive, ('binary_index_semantics_verified', 'module_loading_verified',
                               'signature_enforcement_runtime_verified'), role + ' archive')
        included = archive['modules']
        require(type(archive.get('included_module_count')) is int
                and archive['included_module_count'] == len(included)
                and set(closure) <= set(included), 'initrd supplier closure missing')
        require(all(PREFIX + name in build['modules'] and entry == build['modules'][PREFIX + name]
                    for name, entry in included.items()), 'initrd module bytes differ')
    require(archives['production']['image'] == launch_files['initrd'], 'production archive differs from launch initrd')
    profile, runtime, derivation = (docs[name] for name in
                                    ('system-profile.json', 'runtime.json', 'recipe/derivation.json'))
    for value, name in ((profile, 'system profile'), (runtime, 'runtime manifest'), (derivation, 'recipe derivation')):
        schema_one(value, name)
        require(value.get('kernel_release') == RELEASE, name + ' release differs')
    require(profile.get('profile') == derivation.get('profile') == SYSTEM_PROFILE
            and profile.get('root_label') == derivation.get('root_label') == LABEL,
            'root profile or recipe identity differs')
    for key, expected_value in {
            'module_count': 84, 'firmware_file_count': 69,
            'runtime_manifest_sha256': ids['runtime.json']['sha256'],
            'kernel_image_sha256': build['artifacts']['Image']['sha256'],
            'board_dtb_sha256': NATIVE_DTB['sha256'],
            'kernel_btf_sha256': build['artifacts']['kernel.btf']['sha256'],
            'kernel_btf_size': build['artifacts']['kernel.btf']['bytes'],
            'public_signing_certificate_sha256': build['artifacts']['signing-cert.der']['sha256'],
            'staging_receipt_sha256': ids['r7-runtime-stage.json']['sha256'],
            'source_policy_sha256': POLICY_SHA, 'early_bootstrap_sha256': BOOTSTRAP_SHA,
            'early_bootstrap_build_policy_sha256': POLICY_SHA,
            'initramfs_root_type_required': 'tmpfs', 'kernel_rdinit_required': '/init.tmpfs',
            'validation_selinux_context': 'system_u:system_r:sysadm_t:s0',
            'transient_selinux_context': 'system_u:system_r:sysadm_t:s0',
            'validation_tasks_max': 128, 'audit_printk_interval_required': 0,
            'journal_acl_check': stage['journal_acls'],
    }.items():
        require(type(profile.get(key)) is type(expected_value) and profile[key] == expected_value,
                'R7 profile binding differs: ' + key)
    require(all(profile.get(key) is True for key in ('early_selinux_required',
                'audit_printk_opt_in_required', 'vm_module_signature_enforcement_required')),
            'required R7 runtime security policy missing')
    false_fields(profile, ('configured_module_sig_force', 'actual_exported_kernel_policy_sha256_predetermined',
                           'early_bootstrap_embeds_policy_hash'), 'system profile')
    for key, name in (('transient_worker_sha256', 'guest_transient_worker.py'),
                      ('guest_result_writer_sha256', 'guest_result_file.py'),
                      ('host_result_reader_sha256', 'read_vm_result.py')):
        mode_id(derivation['derived'][name], 'derived protocol ' + name)
        require(profile[key] == derivation['derived'][name]['sha256'], 'guest/host result protocol binding differs')
    false_fields(derivation, ('frozen_recipe_written', 'runtime_acceptance_verified'), 'recipe derivation')
    false_fields(runtime, ('physical_tablet_tested', 'firmware_selection_verified'), 'runtime manifest')
    require(type(runtime.get('module_count')) is int and runtime['module_count'] == 84
            and type(runtime.get('firmware_file_count')) is int and runtime['firmware_file_count'] == 69
            and len(stage['firmware_inventory']) == 69, 'runtime module or firmware count differs')
    for name, entry in tree.items():
        require(runtime['runtime_files']['usr/lib/modules/' + RELEASE + '/' + name] == entry['sha256'],
                'runtime module tree hash differs')
    for name, entry in stage['firmware_inventory'].items():
        canonical_path(name)
        require(name.startswith('lib/firmware/'), 'firmware inventory path outside qualified tree')
        mode_id(entry, 'firmware ' + name)
        require(runtime['runtime_files']['usr/' + name] == entry['sha256'], 'runtime firmware hash differs')
    meta = 'usr/share/tb371fc/' + RELEASE + '/'
    mappings = {'Image': 'boot/Image-' + RELEASE,
                'board.dtb': 'boot/dtb-' + RELEASE + '/qcom/sm8250-lenovo-tb371fc.dtb',
                'kernel.config': 'boot/config-' + RELEASE, 'System.map': 'boot/System.map-' + RELEASE,
                **{name: meta + name for name in ('signing-cert.der', 'kernel.btf', 'Module.symvers', 'kernel.release')}}
    require(all(runtime['runtime_files'][path] == build['artifacts'][name]['sha256']
                for name, path in mappings.items()), 'runtime kernel artifact binding differs')
    require(all(runtime['runtime_files'][meta + name] == entry['sha256'] for name, entry in {
        'research7-build.json': build_id, 'source-manifest.json': build['source_inventory'],
        'module-signatures.json': build['offline_signature_result'],
        'module-abi.json': build['offline_abi_result']}.items()), 'runtime build evidence binding differs')
    return {row['path']: row['mode'] for row in rows}


def generic_command(work, phase, profile_sha):
    root = work / 'rootfs'
    args = ('console=ttyAMA0 root=LABEL=' + LABEL + ' rootfstype=ext4 rw '
        'rd.luks=0 rd.lvm=0 rd.md=0 rd.dm=0 rd.neednet=0 module.sig_enforce=1 '
        'systemd.unit=tb371fc-r4f-validation.target systemd.show_status=yes '
        'systemd.log_target=console systemd.log_level=debug selinux=1 enforcing=' +
        ('0' if phase == 'label' else '1 rd.tb371fc.early-selinux=1 rd.tb371fc.tmpfs-root=1 '
         'rdinit=/init.tmpfs rd.tb371fc.audit-printk-unlimited=1') +
        ' tb371fc.r4f-phase=' + phase + ' tb371fc.r4f-profile=' + profile_sha)
    return ['/usr/bin/qemu-system-aarch64', '-machine', 'virt', '-cpu', 'cortex-a72',
        '-smp', '2', '-m', '2048', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
        '-nic', 'none', '-no-reboot', '-kernel', str(root / 'boot' / ('Image-' + RELEASE)),
        '-initrd', str(root / 'boot' / ('initramfs-' + RELEASE + ('-maintenance' if phase == 'label' else '') + '.img')),
        '-append', args, '-drive', 'if=none,id=rootfs,format=raw,file=' + str(work / 'fedora45-research7-rpmh-clock.ext4'),
        '-device', 'virtio-blk-device,drive=rootfs']


def validate_generic_vm(docs, ids, launch_files):
    """Bind the frozen wrapper's independently reparsed generic-virt evidence.

    No VM or result extractor executes here. A separately reviewed wrapper must
    have completed its unchanged inherited acceptance gates and full disk hash
    chain. The board-model result remains distinct from this historical pass.
    """
    receipt = docs['r7-generic-vm-result.json']
    exact(receipt, {'schema', 'rootfs_phase', 'passed', 'kernel_release', 'started_utc', 'finished_utc',
        'wrapper_source', 'construction_result', 'profile', 'initial_rootfs', 'final_rootfs', 'tools',
        'source_inputs', 'phases', 'inputs_reverified', 'generic_virt_acceptance', 'board_model_verified',
        'physical_boot_verified', 'native_userspace_verified', 'owner_native_linux_passes_added', 'error'},
        'generic VM terminal receipt')
    require(receipt['schema'] == 'tb371fc-r7-generic-vm-v1' and receipt['rootfs_phase'] == GENERIC_VM_PHASE
            and receipt['kernel_release'] == RELEASE and receipt['error'] is None
            and all(receipt[key] is True for key in ('passed', 'inputs_reverified', 'generic_virt_acceptance')),
            'generic VM qualification is not complete')
    false_fields(receipt, ('board_model_verified', 'physical_boot_verified', 'native_userspace_verified'), 'generic VM')
    require(type(receipt['owner_native_linux_passes_added']) is int and receipt['owner_native_linux_passes_added'] == 0,
            'generic VM native scope differs')
    require(receipt['tools'] == GENERIC_VM_TOOLS, 'generic VM recorded tools differ')
    require(all(isinstance(receipt[key], str) and receipt[key] for key in ('started_utc', 'finished_utc')),
            'generic VM receipt is not terminal')
    content_id(receipt['wrapper_source'], 'generic VM wrapper source')
    require(isinstance(GENERIC_VM_WRAPPER_SHA, str)
            and receipt['wrapper_source']['sha256'] == GENERIC_VM_WRAPPER_SHA,
            'generic VM wrapper differs from reviewed source')
    construction = docs['r7-construction-result.json']
    require(receipt['source_inputs']['scripts/research/system-kernel/research7-rpmh-clock/build_rpmh_rootfs.py']['sha256']
            == CONSTRUCTOR_SHA, 'generic VM constructor source differs')
    require(receipt['construction_result'] == ids['r7-construction-result.json']
            and receipt['profile'] == ids['system-profile.json']
            and receipt['initial_rootfs'] == stripped_id(construction['rootfs'])
            and receipt['final_rootfs'] == launch_files['rootfs'], 'generic VM root or construction chain differs')
    work = Path(construction['rootfs']['path']).parent
    require(work.is_absolute() and work.parent == Path('/work') and work.name.startswith('fedora-r7-system-')
            and construction['rootfs']['path'] == str(work / 'fedora45-research7-rpmh-clock.ext4'),
            'generic VM work path differs from constructed image')
    require(isinstance(receipt['phases'], list) and len(receipt['phases']) == 2, 'exact label then verify phases required')
    previous = receipt['initial_rootfs']
    profile_sha = ids['system-profile.json']['sha256']
    for phase, row in zip(('label', 'verify'), receipt['phases']):
        exact(row, {'phase', 'run', 'started_utc', 'finished_utc', 'rootfs_before', 'rootfs_after',
            'result', 'command', 'serial', 'guest_result', 'reparsed_result', 'driver_source', 'driver_log',
            'exit_code', 'child_reaped', 'process_group_empty', 'all_owned_descendants_reaped',
            'orphan_descendants_found', 'acceptance_reparsed'}, 'generic VM phase')
        run = 'vm-' + phase + '-01'
        require(row['phase'] == phase and row['run'] == run and type(row['exit_code']) is int
                and row['exit_code'] == 0 and row['orphan_descendants_found'] == []
                and all(row[key] is True for key in ('child_reaped', 'process_group_empty',
                    'all_owned_descendants_reaped', 'acceptance_reparsed')), 'generic VM phase ownership or completion differs')
        require(all(isinstance(row[key], str) and row[key] for key in ('started_utc', 'finished_utc')),
                'generic VM phase is not terminal')
        content_id(row['rootfs_before'], 'phase root before')
        content_id(row['rootfs_after'], 'phase root after')
        require(row['rootfs_before'] == previous and row['rootfs_after']['bytes'] == ROOTFS_BYTES,
                'generic VM disk hash chain is discontinuous')
        previous = row['rootfs_after']
        require(row['driver_source'] == stripped_id(docs['recipe/derivation.json']['derived']['boot_system_vm.py'])
                and row['driver_source']['sha256'] == GENERIC_VM_DRIVER_SHA, 'generic VM inherited driver differs')
        for key, name in {'result': run + '/result.json', 'command': run + '/command.json',
            'serial': run + '/serial.log', 'driver_log': 'r7-generic-vm/' + phase + '.driver.log',
            'reparsed_result': 'r7-generic-vm/reparse-' + phase + '/inspection.json'}.items():
            require(row[key] == ids[name], 'generic VM retained evidence differs: ' + name)
        require(row['serial']['bytes'] <= 8 * 1024**2 and row['driver_log']['bytes'] <= 4 * 1024**2,
                'generic VM retained log bound exceeded')
        require(docs[run + '/command.json'] == generic_command(work, phase, profile_sha), 'generic VM command differs')
        result = docs[run + '/result.json']
        replay = docs['r7-generic-vm/reparse-' + phase + '/inspection.json']
        archive = docs['r7-initrd-modules.json']['maintenance' if phase == 'label' else 'production']['image']
        expected = {'schema_version': 2, 'phase': phase, 'profile_sha256': profile_sha,
            'kernel_image_sha256': launch_files['kernel']['sha256'], 'initramfs_sha256': archive['sha256'],
            'timeout_seconds': 900, 'log_limit_bytes': 8 * 1024**2, 'qemu_exit_code': 0,
            'termination_reason': None, 'passed': True, 'physical_hardware_tested': False,
            'physical_device_passthrough': False, 'network': False, 'board_dtb_used': False,
            'host_filesystem_shared': False, 'vm_module_sig_enforce_argument': 'module.sig_enforce=1',
            'compiled_module_sig_force': False, 'serial_log_sha256': row['serial']['sha256'],
            'serial_log_bytes': row['serial']['bytes'], 'systemd_debug_logging_for_this_vm_only': True,
            'initramfs_role': 'maintenance-label-only' if phase == 'label' else 'production-tmpfs-early-selinux',
            'early_selinux_argument': None if phase == 'label' else 'rd.tb371fc.early-selinux=1',
            'kernel_rdinit_argument': None if phase == 'label' else 'rdinit=/init.tmpfs',
            'audit_printk_observation_argument': None if phase == 'label' else 'rd.tb371fc.audit-printk-unlimited=1'}
        require(all(type(result.get(key)) is type(value) and result[key] == value for key, value in expected.items()),
                'generic VM inherited result binding differs')
        require(not any(key in result for key in ('error', 'parse_error', 'persistent_result_error')),
                'generic VM inherited result contains errors')
        require(all(result.get(key) == value for key, value in replay.items() if key != 'persistent_result_metadata'),
                'generic VM independent acceptance reparse differs')
        require(replay.get('expected_marker_seen') is True and type(replay.get('marker_exact_line_count')) is int
                and replay['marker_exact_line_count'] == 1, 'generic VM completion marker differs')
        false_fields(replay, ('validation_failure_seen', 'kernel_panic_seen', 'invalid_initramfs_seen'), 'generic VM reparse')
        if phase == 'label':
            require(row['guest_result'] is None, 'maintenance phase unexpectedly carries production result')
        else:
            require(row['guest_result'] == ids['vm-verify-01/guest-result.json']
                    == ids['r7-generic-vm/reparse-verify/guest-result.json'], 'production result copies differ')
            require(replay.get('guest_gates_match') is True and replay.get('persistent_result_qualified') is True
                    and replay.get('guest_file_status') == 'pass'
                    and isinstance(replay.get('observed_warning_counts'), dict) and replay['observed_warning_counts']
                    and all(type(value) is int and value == 0 for value in replay['observed_warning_counts'].values()),
                    'generic VM production acceptance gates failed')
            original, actual = result['persistent_result_metadata'], replay['persistent_result_metadata']
            keys = ('qualified', 'receipt', 'guest_inode', 'parent_inodes', 'image_opened_for_write',
                    'image_mounted', 'filesystem_replayed_or_repaired', 'source_image_metadata_unchanged')
            require(all(original[key] == actual[key] for key in keys), 'production same-boot extraction metadata differs')
            same_boot = actual['receipt']
            require(actual['qualified'] is True and actual['source_image_metadata_unchanged'] is True
                    and same_boot['status'] == 'pass' and same_boot['profile_sha256'] == profile_sha
                    and {'bytes': same_boot['size'], 'sha256': same_boot['sha256']} == row['guest_result'],
                    'production guest receipt differs from retained bytes')
            false_fields(actual, ('image_opened_for_write', 'image_mounted', 'filesystem_replayed_or_repaired'), 'result extraction')
            guest = docs['vm-verify-01/guest-result.json']
            require(guest.get('status') == 'pass' and guest.get('phase') == 'verify'
                    and guest.get('boot_id') == same_boot['boot_id'] and guest.get('profile_sha256') == profile_sha
                    and guest.get('result') == replay['guest_result'], 'production result envelope differs')
    require(previous == receipt['final_rootfs'], 'final generic VM root differs from verify phase')


def read_bundle(root, expected, capture):
    """Read a closed public bundle; no source tree, vmlinux, or private key."""
    payloads, identities = {}, {}
    with BundleReader(root) as reader:
        before = reader.inventory()
        require(set(before[0]) == set(expected), 'public bundle has missing or unexpected files')
        for name, wanted in expected.items():
            content_id(wanted, name, 128 * 1024**2)
            raw, info = reader.read(name, wanted['bytes'])
            require(fingerprint(info) == before[0][name] and raw_id(raw) == wanted,
                    'bundle file changed or differs: ' + name)
            identities[name] = {**wanted, 'mode': stat.S_IMODE(info.st_mode)}
            if name in capture:
                payloads[name] = raw
        require(reader.inventory() == before, 'bundle changed while hashing')
    return identities, payloads, before


def verify_inputs(manifest_path, contract_path, contract_sha256):
    require(isinstance(contract_sha256, str) and re.fullmatch('[0-9a-f]{64}', contract_sha256) is not None,
            'explicit reviewed R7 contract SHA-256 required')
    contract_id, contract_stamp, contract_raw = read_file(contract_path, maximum=1024**2, capture=True)
    require(contract_id['sha256'] == contract_sha256, 'R7 input contract SHA-256 differs from explicit pin')
    contract = validate_contract(json.loads(contract_raw, object_pairs_hook=unique_object))
    manifest_id, manifest_stamp, manifest_raw = read_file(manifest_path, maximum=1024**2, capture=True)
    manifest = validate_manifest(json.loads(manifest_raw, object_pairs_hook=unique_object), contract)
    kernel_root, construction_root = (checked_path(manifest[key]) for key in ('kernel_bundle', 'construction_bundle'))
    # Pin the build before using any receipt-controlled relative paths.
    build_file = kernel_root / 'build-result.json'
    build_id, build_stamp, build_raw = read_file(build_file, expected=contract['build_result'],
                                               maximum=1024**2, capture=True)
    build = json.loads(build_raw, object_pairs_hook=unique_object)
    receipts = {'build-result.json': contract['build_result'],
                'module-signatures.json': build['offline_signature_result'],
                'module-abi.json': build['offline_abi_result'], 'source-inventory.json': build['source_inventory']}
    expected = {**receipts, **{'artifacts/' + name: entry for name, entry in build['artifacts'].items()},
                **build['modules'], **{PREFIX + name: entry['installed'] for name, entry in build['module_metadata'].items()}}
    kernel_ids, kernel_raw, kernel_inventory = read_bundle(kernel_root, expected,
        {'build-result.json', 'module-signatures.json', 'module-abi.json', 'artifacts/kernel.release',
         'artifacts/board.dtb', 'artifacts/modules.order'})
    signatures = json.loads(kernel_raw['module-signatures.json'], object_pairs_hook=unique_object)
    abi = json.loads(kernel_raw['module-abi.json'], object_pairs_hook=unique_object)
    validate_build(build, signatures, abi)
    require(kernel_raw['build-result.json'] == build_raw, 'build receipt changed during qualification')
    require(kernel_raw['artifacts/kernel.release'] == (RELEASE + '\n').encode('ascii'), 'release payload differs')
    require(sorted(kernel_raw['artifacts/modules.order'].decode('ascii').splitlines()) ==
            sorted(name[len(PREFIX):] for name in build['modules']), 'installed module order differs')
    evidence_ids = {**contract['construction_files'], **contract.get('generic_vm_files', {})}
    capture_json = {name for name in evidence_ids if name.endswith('.json')}
    construction_ids, construction_raw, construction_inventory = read_bundle(construction_root, evidence_ids, capture_json)
    docs = {name: json.loads(raw, object_pairs_hook=unique_object) for name, raw in construction_raw.items()}
    modes = validate_construction(docs, evidence_ids, build, contract['build_result'], contract['launch_files'],
                                  rootfs_phase=contract['rootfs_phase'])
    require(all(kernel_ids[name]['mode'] == mode for name, mode in modes.items()), 'module bundle file mode differs')
    paths, identities, stamps, raw = {}, {}, {}, {}
    for name, entry in manifest['files'].items():
        path = validate_identity(entry, name)
        observed, stamp, data = read_file(path, expected=entry, capture=name in RAW_KEYS)
        if name == 'qemu':
            require(os.access(path, os.X_OK), 'QEMU is not executable')
        paths[name], identities[name], stamps[str(path)] = path, observed, stamp
        if data is not None:
            raw[name] = data
    for role, name in (('kernel', 'Image'), ('config', 'kernel.config'), ('certificate', 'signing-cert.der')):
        require(stripped_id(identities[role]) == build['artifacts'][name], 'launch file differs from R7 build: ' + role)
    header = parse_arm64_image(raw['kernel'])
    require(raw['certificate'] in raw['kernel'], 'new R7 certificate absent from launched Image')
    delta = check_delta(kernel_raw['artifacts/board.dtb'], raw['dtb'])
    stamps.update({str(Path(manifest_path)): manifest_stamp, str(Path(contract_path)): contract_stamp,
                   str(build_file): build_stamp})
    qualification = {'status': 'verified', 'input_profile': INPUT_PROFILE, 'module_count': 84,
        'artifact_count': 11, 'installed_metadata_count': 3, 'kernel_bundle_file_count': len(kernel_ids),
        'recorded_offline_signature_pass': True, 'recorded_offline_abi_pass': True,
        'module_bytes_match_recorded_qualification': True, 'module_signatures_reexecuted': False,
        'module_symbol_crc_commands_reexecuted': False, 'rootfs_contents_reaudited': False,
        'runtime_signature_enforcement_verified': False, 'userspace_verified': False,
        'physical_hardware_tested': False, 'arm64_header': header}
    result = {'paths': paths, 'raw': raw, 'identities': identities, 'input_profile': INPUT_PROFILE,
        'release': RELEASE, 'bootargs': manifest['bootargs'], 'kernel_load_base': manifest['kernel_load_base'],
        'kernel_bundle_qualification': qualification,
        'evidence_bindings': {'manifest': manifest_id, 'input_contract': contract_id,
            'build_result': build_id, 'construction_files': construction_ids,
            'rootfs_source': contract['rootfs_phase'],
            'generic_vm_recorded_acceptance': contract['rootfs_phase'] == GENERIC_VM_PHASE,
            'generic_vm_acceptance_reexecuted': False,
            'dtb_derivation': delta, 'full_rootfs_bytes_hashed': ROOTFS_BYTES,
            'module_signatures_reexecuted': False, 'runtime_signature_enforcement_verified': False,
            'physical_boot_verified': False},
        '_stamps': stamps, '_bundles': [(kernel_root, kernel_inventory), (construction_root, construction_inventory)]}
    verify_unchanged(result)
    return result


def verify_unchanged(inputs):
    """Recheck stable snapshots at pre-cont and exit; do not rescan 4 GiB."""
    require(inputs.get('input_profile') == INPUT_PROFILE, 'wrong input verifier dispatch')
    for value, expected in inputs['_stamps'].items():
        require(fingerprint(checked_path(value).lstat()) == expected, 'R7 input changed since qualification: ' + value)
    for root, expected in inputs['_bundles']:
        with BundleReader(checked_path(str(root))) as reader:
            require(reader.inventory() == expected, 'R7 bundle changed since qualification: ' + str(root))
