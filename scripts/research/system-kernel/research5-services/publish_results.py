#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Publish completed R5 text evidence and its exact execution sources locally."""
from pathlib import Path, PurePosixPath
import hashlib
import json

HERE = Path('/workspace/scratch/45c316069ac9')
DRAFT = HERE / 'research5-services-draft-20261123'
REPO = HERE / 'tb371fc-linux'
DOCS = REPO / 'docs/research/2026-11-23'
EVIDENCE = DOCS / 'evidence'
SOURCES = REPO / 'scripts/research/system-kernel/research5-services'
REPORT_SHA = '69d0b558c99bdfb339df8b3b9baca8bb1ee4d0cb2e46dd9b3b7fef3ab69aaad2'


def identity(raw):
    return {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def new_file(destination, raw, mode=0o644):
    assert not destination.exists() and not destination.is_symlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(raw)
    destination.chmod(mode)
    assert destination.read_bytes() == raw
    return {'path': destination.relative_to(REPO).as_posix(), **identity(raw), 'mode': mode}


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    raw_root = DRAFT / 'raw-records'
    raw_report = (raw_root / 'research5-services-build.json').read_bytes()
    assert identity(raw_report)['sha256'] == REPORT_SHA
    report = json.loads(raw_report)
    contract_raw = (DRAFT / 'services-contract.json').read_bytes()
    contract = json.loads(contract_raw)
    assert report['passed'] is True and report['configuration_changes'] == contract['exact_changes']
    assert report['module_count'] == 84 and report['module_set_changes_from_research4'] == {'added': [], 'removed': []}
    assert report['physical_hardware_tested'] is False and report['module_loaded_by_inspector'] is False
    assert not SOURCES.exists() and not (EVIDENCE / 'research5-services-records').exists()
    published_sources = []
    names = ['prepare_source.py', 'derive_recipe.py', 'run_build.py', 'run_transfer.py',
             'collect_public_records.py', 'collect_control_records.py', 'publish_results.py',
             'services-contract.json', 'recipe-derivation.json', 'recipe-derivation.patch',
             'recipe-v1/build_system.py', 'recipe-v1/inspect_system.py', 'recipe-v1/system.config',
             'recipe-v1/services-contract.json', 'transfer-v1/copy_baseline.py', 'transfer-v1/transfer_kernel.py']
    for name in names:
        source = DRAFT / name
        published_sources.append(new_file(SOURCES / name, source.read_bytes(), 0o755 if name.endswith('.py') else 0o644))
    raw_records = []
    for prefix, qualification in [('container', 'container-transport-qualification.json'),
                                  ('control', 'control-transport-qualification.json')]:
        record = json.loads((raw_root / qualification).read_bytes())
        assert record['all_raw_members_byte_verified'] is True
        for row in record['members']:
            name = row['path']
            relative = PurePosixPath(name)
            assert not relative.is_absolute() and '..' not in relative.parts and str(relative) == name
            raw = (raw_root / prefix / name).read_bytes()
            assert identity(raw) == {key: row[key] for key in ('bytes', 'sha256')}
            suffix = '' if relative.suffix in ('.json', '.log', '.tsv') else '.log' if relative.suffix in ('.stdout', '.stderr') else '.txt'
            target = EVIDENCE / 'research5-services-records' / prefix / (name + suffix)
            raw_records.append({'original_relative_path': prefix + '/' + name,
                                'raw_source_bytes_preserved': True, **new_file(target, raw)})
        new_file(EVIDENCE / 'research5-services-records' / qualification, (raw_root / qualification).read_bytes())
    assert len(raw_records) == 55
    source_inputs = []
    selected = {
        'nixos-system-boot-draft-20261123/captures/iptables-1.8.13-official-source.json': 'iptables-official-source.json',
        'nixos-system-boot-draft-20261123/sources/final/nix/store/mrgg2ppl9jh13ajns8k0l32z7207rxid-firewall-start/bin/firewall-start': 'nixos-firewall-start.sh',
        'nixos-system-boot-draft-20261123/sources/iptables-1.8.13/iptables/nft.c': 'iptables-nft.c.txt',
        'nura-system-boot-draft-20261123/kernel-source/drivers/block/zram/Kconfig': 'linux-zram-Kconfig.txt',
        'nura-system-boot-draft-20261123/kernel-source/net/netfilter/Kconfig': 'linux-netfilter-Kconfig.txt',
        'nura-system-boot-draft-20261123/kernel-source/net/netfilter/Makefile': 'linux-netfilter-Makefile.txt',
        'nura-system-boot-draft-20261123/native-inputs.json': 'nura-native-inputs.json',
        'nura-system-boot-draft-20261123/source/etc/init.d/hwclock': 'nura-hwclock.sh',
        'nura-system-boot-draft-20261123/source/etc/nftables.nft': 'nura-nftables.nft.txt',
        'nura-system-boot-draft-20261123/source/usr/bin/zramstart': 'nura-zramstart.sh',
    }
    for name, expected in contract['sources'].items():
        source = HERE / name
        raw = source.read_bytes()
        assert identity(raw) == expected, name
        if name.startswith('tb371fc-linux/'):
            source_inputs.append({'original_source': name, 'path': source.relative_to(REPO).as_posix(), **identity(raw), 'already_public': True})
        else:
            assert name in selected, name
            row = new_file(EVIDENCE / 'research5-services-source-inputs' / selected[name], raw)
            source_inputs.append({'original_source': name, **row, 'raw_source_bytes_preserved': True})
    public_report = new_file(EVIDENCE / 'research5-services-build.json', raw_report)
    build = json.loads((raw_root / 'control/host-build/build-driver-result.json').read_bytes())
    copied = json.loads((raw_root / 'control/host-transfer/driver-result.json').read_bytes())
    transfer = json.loads((raw_root / 'control/shared-transfer/transfer.json').read_bytes())
    assert build['completed'] is copied['completed'] is transfer['complete'] is True
    assert build['exit_code'] == copied['exit_code'] == 0 and transfer['files_verified'] == 106
    assert transfer['source_before'] == transfer['source_after'] == transfer['destination_readback']
    assert transfer['source_stream']['sha256'] == transfer['destination_stream']['sha256']
    assert transfer['source_stream']['bytes'] == transfer['destination_stream']['bytes'] == 66263040
    for name in ('private_signing_key_transferred', 'firmware_transferred', 'old_depmod_indexes_transferred',
                 'module_loaded', 'physical_hardware_tested'):
        assert transfer[name] is False
    verification = {
        'schema_version': 1, 'evidence_class': 'host_build', 'profile': 'research5-services',
        'scope': 'Independent full kernel build, offline signatures/ABI/DT and shared public-runtime transfer only.',
        'kernel_release': report['kernel_release'], 'kernel_report': public_report,
        'configuration_changes': report['configuration_changes'],
        'all_other_r4_semantic_config_values_preserved': True,
        'all_84_module_paths_unchanged_from_r4': True, 'module_count': 84,
        'module_imported_symbol_crc_checks': sum(row['imported_symbol_crc_count'] for row in report['modules']),
        'full_module_cms_crc_vermagic_btf_and_stripping_gates_passed': True,
        'joint_dtb_sha256': report['files']['board.dtb']['sha256'],
        'gpu_iommu': report['native_dtb']['gpu_iommu'],
        'build_phases': [{key: row[key] for key in ('start_utc', 'ended_utc', 'exit_code', 'elapsed_seconds', 'stdout', 'stderr')} |
                         {'name': name} for name, row in zip(('install', 'configure', 'build', 'inspect'), build['phases'])],
        'build_driver_seconds': build['elapsed_seconds'], 'build_completed_utc': build['ended_utc'],
        'shared_transfer_completed_utc': copied['ended_utc'], 'shared_transfer_seconds': copied['elapsed_seconds'],
        'shared_destination': transfer['destination_root'], 'shared_regular_files_verified': 106,
        'shared_stream_bytes': transfer['source_stream']['bytes'], 'shared_stream_sha256': transfer['source_stream']['sha256'],
        'shared_source_before_after_and_destination_content_mode_owner_equal': True,
        'raw_record_count': len(raw_records), 'raw_records': raw_records, 'exact_execution_sources': published_sources,
        'configuration_source_inputs': source_inputs, 'no_raw_record_rewritten': True,
        'private_key_read_or_exported': False, 'firmware_payload_published': False,
        'old_module_indexes_transferred': False, 'module_loaded_by_this_workflow': False,
        'generic_system_vm_run_performed_by_this_workflow': False, 'physical_hardware_tested': False,
        'owner_native_linux_runs': 0, 'owner_native_linux_passes': 0, 'gpu_runtime_acceleration_tested': False,
        'independent_bit_identical_rebuild_proven': False,
        'limits': [
            'The independent automatic signing key intentionally changes linked Image and module bytes.',
            'Builder package versions are captured; all tool packages are not frozen to a distribution snapshot.',
            'PL031 is the generic QEMU RTC; this does not test the physical tablet RTC.',
            'NixOS and Nura original-userland VM runs and actual services remain separate acceptance steps.',
            'The owner tablet has not booted this kernel; GPU, display, input, radios, audio, power and accessory quality remain open.',
        ],
    }
    result = new_file(EVIDENCE / 'research5-services-verification.json', json_bytes(verification))
    print(json.dumps({'report': public_report, 'verification': result, 'public_source_count': len(published_sources),
                      'configuration_source_inputs': len(source_inputs), 'raw_records': len(raw_records),
                      'module_crc_checks': verification['module_imported_symbol_crc_checks']}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
