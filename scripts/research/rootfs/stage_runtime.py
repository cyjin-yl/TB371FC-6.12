#!/usr/bin/env python3
"""Install verified research1 runtime files into the separate Fedora tree.

The firmware contract was audited on research2-display. Before reusing its
canonical tree, compare every audited loader source and DT firmware-name
property with research1. This does not equate the two boards' enabled devices.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess

from fedora_system import ROOT, WORK, run_guest, save, sha

ART = Path('/work/artifacts')
SOURCE = Path('/work/linux-6.12.114-research1')
FIRMWARE = Path('/work/stock-fw-stage-v1/canonical-elf')
CONTRACT = Path('/src/docs/research/2026-11-23/evidence/firmware-kernel-contract.json')
KERNEL_REPORT_SHA = '7ad22ac18bbd83859ff0535bcbcbe98ad76d9acfb548558e21442d55064655ee'
CONTRACT_SHA = '26ab16aa3e71f2317e736aa0877572616fb13c64f29ff5ea3381278bc931644a'
FW_MANIFEST_SHA = '4feb4264605198fc56114fb8b8044ffcd51f662107270a857f59fdaf2e8bcf7c'
RELEASE = '6.12.114-tb371fc-research1'


def check(path, expected, size=None):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary input file required: ' + str(path))
    if sha(path) != expected or (size is not None and path.stat().st_size != size):
        raise ValueError('input hash/size mismatch: ' + str(path))


def safe_relative(value):
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or str(p) != value:
        raise ValueError('noncanonical relative path: ' + value)
    return p


def copy_new(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError('refusing to replace staged runtime file: ' + str(destination))
    if source.is_symlink() or not source.is_file():
        raise ValueError('ordinary source required: ' + str(source))
    shutil.copy2(source, destination)
    check(destination, sha(source), source.stat().st_size)


def main():
    if not ROOT.is_dir() or ROOT.is_symlink() or (WORK / 'runtime.json').exists():
        raise ValueError('new, prepared Fedora runtime required')
    check(ART / 'kernel-build.json', KERNEL_REPORT_SHA)
    check(CONTRACT, CONTRACT_SHA)
    check(FIRMWARE / 'stock-firmware-manifest.json', FW_MANIFEST_SHA)
    kernel = json.loads((ART / 'kernel-build.json').read_text())
    contract = json.loads(CONTRACT.read_text())
    firmware = json.loads((FIRMWARE / 'stock-firmware-manifest.json').read_text())
    if kernel['kernel_release'] != RELEASE or kernel['module_count'] != 83:
        raise ValueError('unexpected qualified kernel identity')
    for name, entry in kernel['files'].items():
        check(ART / safe_relative(name), entry['sha256'], entry['size'])
    source_checks = {}
    for name, entry in contract['source_files'].items():
        check(SOURCE / safe_relative(name), entry['sha256'], entry['size'])
        source_checks[name] = entry['sha256']
    dt_checks = []
    for node, properties in contract['dt_nodes'].items():
        # Absence of a plain firmware-name is also significant: adding it could
        # override the catalog/ROM/GPIO-selected paths in the audited contract.
        names = {'firmware-name'} | {key for key in properties if key.endswith('firmware-name')}
        for name in sorted(names):
            result = subprocess.run(['fdtget', '-t', 's', str(ART / 'board.dtb'), node, name],
                                    capture_output=True, text=True)
            actual = result.stdout.strip().split() if result.returncode == 0 else None
            expected = properties.get(name)
            if actual != expected:
                raise ValueError(f'DT firmware selection differs: {node} {name}: {actual} != {expected}')
            # A missing node is not equivalent to an absent property.
            if result.returncode and 'FDT_ERR_NOTFOUND' not in result.stderr:
                raise ValueError('unrecognized fdtget failure: ' + result.stderr)
            subprocess.run(['fdtget', '-p', str(ART / 'board.dtb'), node],
                           check=True, stdout=subprocess.DEVNULL)
            dt_checks.append({'node': node, 'property': name, 'value': actual})

    modules_root = Path('/work/modules/lib/modules') / RELEASE
    module_expected = {}
    for line in (ART / 'modules.SHA256SUMS').read_text().splitlines():
        digest, name = line.split('  ', 1)
        relative = safe_relative(name)
        if not str(relative).startswith(f'lib/modules/{RELEASE}/kernel/'):
            raise ValueError('unexpected module inventory prefix')
        check(Path('/work/modules') / relative, digest)
        module_expected[str(relative)] = digest
    actual = {str(p.relative_to('/work/modules')) for p in modules_root.rglob('*.ko')}
    if len(module_expected) != 83 or actual != set(module_expected):
        raise ValueError('module inventory differs from the frozen kernel')
    if firmware['firmware_file_count'] != 69 or len(firmware['files']) != 69:
        raise ValueError('unexpected canonical firmware inventory')
    for entry in firmware['files']:
        relative = safe_relative(entry['destination'])
        if not str(relative).startswith('lib/firmware/'):
            raise ValueError('firmware path escaped the canonical root')
        check(FIRMWARE / relative, entry['sha256'], entry['size_bytes'])
    fw_actual = {str(p.relative_to(FIRMWARE)) for p in (FIRMWARE / 'lib/firmware').rglob('*') if p.is_file()}
    if fw_actual != {entry['destination'] for entry in firmware['files']}:
        raise ValueError('undeclared canonical firmware files')

    # All input checks precede writes. Keep source/build links out of a runtime
    # image: they expose a builder path and are not loadable kernel modules.
    module_destination = ROOT / 'usr/lib/modules' / RELEASE
    if module_destination.exists() or module_destination.is_symlink():
        raise ValueError('module destination already exists')
    omitted = []
    for source in sorted(modules_root.rglob('*')):
        rel = source.relative_to(modules_root)
        if source.is_symlink():
            if rel.as_posix() not in ('build', 'source'):
                raise ValueError('unexpected symlink in runtime modules')
            omitted.append(rel.as_posix())
        elif source.is_file():
            copy_new(source, module_destination / rel)
    runtime_files = {}
    for rel, digest in module_expected.items():
        runtime_files['usr/' + rel] = digest
    for entry in firmware['files']:
        destination = 'usr/' + entry['destination']
        copy_new(FIRMWARE / entry['destination'], ROOT / destination)
        runtime_files[destination] = entry['sha256']
    for name, destination in {
        'Image': f'boot/Image-{RELEASE}',
        'board.dtb': f'boot/dtb-{RELEASE}/qcom/sm8250-lenovo-tb371fc.dtb',
        'kernel.config': f'boot/config-{RELEASE}',
        'kernel-build.json': 'usr/share/tb371fc/kernel-build.json',
        'source-manifest.json': 'usr/share/tb371fc/kernel-source-manifest.json',
        'modules.SHA256SUMS': 'usr/share/tb371fc/modules.SHA256SUMS',
    }.items():
        copy_new(ART / name, ROOT / destination)
        runtime_files[destination] = sha(ART / name)
    copy_new(FIRMWARE / 'stock-firmware-manifest.json', ROOT / 'usr/share/tb371fc/stock-firmware-manifest.json')
    runtime_files['usr/share/tb371fc/stock-firmware-manifest.json'] = FW_MANIFEST_SHA
    run_guest(['/usr/sbin/depmod', '-a', RELEASE])
    record = {
        'kernel_release': RELEASE,
        'kernel_report_sha256': KERNEL_REPORT_SHA,
        'firmware_contract_sha256': CONTRACT_SHA,
        'firmware_manifest_sha256': FW_MANIFEST_SHA,
        'cross_profile_loader_source_hashes': source_checks,
        'cross_profile_dt_firmware_properties': dt_checks,
        'cross_profile_comparison_scope': 'loader bytes and firmware-name properties only; enabled devices and display behavior differ',
        'module_count': 83, 'firmware_file_count': 69,
        'omitted_nonruntime_module_links': omitted,
        'runtime_files': runtime_files,
        'hardware_tested': False,
        'firmware_authenticated_or_loaded_on_tablet': False,
    }
    save('runtime.json', record)
    copy_new(WORK / 'runtime.json', ROOT / 'usr/share/tb371fc/runtime.json')
    print('FEDORA_RUNTIME_STAGED 83 modules 69 firmware files', flush=True)


if __name__ == '__main__':
    main()
