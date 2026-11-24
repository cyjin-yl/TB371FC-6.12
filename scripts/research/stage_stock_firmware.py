#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Stage this owner's pinned stock archive for the frozen research2 kernel.

Writes a new private prefix containing lib/firmware, a manifest and checksums.
No image extraction, live installation, device access or firmware loading is
performed. Unresolved WLAN board identity and TFA driver contracts stay open.
The exact source archive and both evidence documents are pinned; there is no
force switch or command-line replacement hash. Original capture files remain
unchanged. Python 3.11+ on Linux, with the two sibling helpers, is required.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import tarfile

import stage_gpu_firmware as safe_io
import stock_firmware_bundle as bundle


REPO = Path(__file__).absolute().parents[2]
CAPTURE_REFERENCE = 'docs/research/2026-11-23/evidence/stock-firmware-bundle.json'
CONTRACT_REFERENCE = 'docs/research/2026-11-23/evidence/firmware-kernel-contract.json'
CAPTURE_SHA256 = '94661a62898cd1cc7ef75bf90d713371b0bc5bb7372215c13dc7d5d34ce27c2b'
CONTRACT_SHA256 = '26ab16aa3e71f2317e736aa0877572616fb13c64f29ff5ea3381278bc931644a'
ARCHIVE_SHA256 = 'fc331d84ed585457b4183b08f799a49d9839d3114bf5ec2f281a725b87fe5f92'
ARCHIVE_BYTES = 15747897
MANIFEST_SHA256 = 'd1bf375a24a065489013567d03746900967bf8eb00455f0067b79d8350dd5ca9'
PARSER_SHA256 = '9ca9ccbdc628ff1a1b365ef4b5deb092ed8405acd1bcb79c8c0454f700bd18f1'
KERNEL_RELEASE = '6.12.114-tb371fc-research2-display'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path, limit):
    path = safe_io.safe_absolute(path)
    with safe_io.open_directory(path.parent) as parent:
        return safe_io.read_regular(parent, path.name, limit)


def pinned_json(path, expected):
    raw = read_file(path, 1024 * 1024)
    if digest(raw) != expected:
        raise ValueError('evidence differs from its fixed reviewed identity')
    return json.loads(raw)


def read_archive(path, capture):
    raw = read_file(path, bundle.MAX_ARCHIVE)
    if len(raw) != ARCHIVE_BYTES or digest(raw) != ARCHIVE_SHA256:
        raise ValueError('archive differs from the pinned owner capture')
    payloads, total = {}, 0
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        with tarfile.open(fileobj=compressed, mode='r|') as archive:
            for item in archive:
                if item.name not in bundle.SOURCES and item.name != 'manifest.json':
                    raise ValueError('unexpected archive member')
                if item.name in payloads or not item.isfile():
                    raise ValueError('duplicate or non-regular archive member')
                bound = bundle.MAX_MANIFEST if item.name == 'manifest.json' else bundle.MAX_FILE
                if not 0 < item.size <= bound:
                    raise ValueError('archive member size outside its bound')
                total += item.size
                if total > bundle.MAX_PAYLOAD + bundle.MAX_MANIFEST:
                    raise ValueError('archive payload total exceeds its bound')
                data = archive.extractfile(item).read(bound + 1)
                if len(data) != item.size:
                    raise ValueError('archive member length differs from its header')
                payloads[item.name] = data
        if len(compressed.read(1024 * 1024 + 1)) > 1024 * 1024:
            raise ValueError('excess bytes after the tar end marker')
    if set(payloads) != set(bundle.SOURCES) | {'manifest.json'}:
        raise ValueError('incomplete fixed source archive')
    manifest_raw = payloads.pop('manifest.json')
    if digest(manifest_raw) != MANIFEST_SHA256:
        raise ValueError('source manifest identity differs')
    manifest = json.loads(manifest_raw)
    observed = capture['off_device_receipt']['source_manifest']
    if manifest != observed or manifest['file_count'] != 118:
        raise ValueError('archive manifest differs from the public verified capture')
    records = {row['archive_path']: row for row in manifest['files']}
    if set(records) != set(payloads):
        raise ValueError('source manifest member set differs')
    for name, data in payloads.items():
        row = records[name]
        if (row['size_bytes'] != len(data) or row['sha256'] != digest(data)
                or row['source_path'] != '/' + name or row['group'] != bundle.SOURCES[name]):
            raise ValueError('source member differs from its captured identity: ' + name)
    return payloads, records


def plan_tree(payloads, source_records, contract, zap_format):
    if contract['kernel_release'] != KERNEL_RELEASE or zap_format not in ('elf', 'mdt'):
        raise ValueError('unsupported kernel contract or ZAP format')
    components = {entry['id']: entry for entry in contract['components']}
    package, files, layouts = {}, [], {}

    def request(component, name):
        if not any(row.get('name') == name for row in components[component]['requests']):
            raise ValueError('destination absent from the pinned request contract: ' + name)
        return 'lib/firmware/' + name

    def add(source, destination, component, reason):
        if destination in package or destination.startswith('/') or '..' in Path(destination).parts:
            raise ValueError('duplicate or unsafe package destination')
        data = payloads[source]
        package[destination] = data
        files.append({'source_path': '/' + source, 'destination': destination,
                      'size_bytes': len(data), 'sha256': digest(data),
                      'component': component, 'reason': reason})

    def add_mdt(source, destination, component):
        layout = bundle.inspect_mdt(source, payloads)
        if not layout['loader_file_set_complete']:
            raise ValueError('source MDT dependency set is incomplete: ' + component)
        if source.endswith('.elf') and (layout['split_payload_required'] or layout['required_split_files']):
            raise ValueError('selected complete ELF needs external segments; no automatic fallback')
        add(source, destination, component, 'Exact main firmware request; bytes unchanged')
        for row in layout['required_split_files']:
            target = str(Path(destination).parent / Path(row['path']).name)
            add(row['path'], target, component,
                'MDT program-header index ' + str(row['index']) + ': ' + row['reason'])
        layouts[destination] = layout

    for name in ('a650_gmu.bin', 'a650_sqe.fw'):
        add('vendor/firmware/' + name, request('a650', 'qcom/' + name), 'a650',
            'Preferred A650 catalog firmware path')
    add_mdt('vendor/firmware/a650_zap.' + zap_format,
            request('a650', 'qcom/sm8250/lenovo/tb371fc/a650_zap.mbn'), 'a650')
    for subsystem in ('adsp', 'cdsp', 'slpi'):
        add_mdt('vendor/firmware_mnt/image/' + subsystem + '.mdt',
                request(subsystem, 'qcom/sm8250/lenovo/tb371fc/' + subsystem + '.mbn'), subsystem)
    add_mdt('vendor/firmware_mnt/image/venus.mdt',
            request('venus', 'qcom/vpu-1.0/venus.mbn'), 'venus')

    # Include both exact runtime alternatives in the existing DT. No generic
    # Novatek alias, manufacturing-test payload or fixed panel override is made.
    for name in ('novatek_ts_tm_fw_6.bin', 'novatek_ts_fw_boe_6.bin'):
        add('vendor/firmware/' + name, request('novatek', 'lenovo/tb371fc/' + name),
            'novatek', 'Explicit DT Tianma/BOE revision-6 runtime alternative')

    bt_patterns = {row.get('name_pattern') for row in components['qca6390_bt']['requests']}
    if bt_patterns != {'qca/htbtfw%02x.tlv', 'qca/htnv%02x.bin'}:
        raise ValueError('Bluetooth request patterns changed')
    for rom in (0x10, 0x20):
        for pattern in ('htbtfw%02x.tlv', 'htnv%02x.bin'):
            name = pattern % rom
            add('vendor/bt_firmware/image/' + name, 'lib/firmware/qca/' + name,
                'qca6390_bt', 'Preserved ROM candidate name; active ROM selection is unverified')

    # This is the reviewed API1 path, not a fabricated firmware-2.bin container.
    for source, target in (('amss20.bin', 'amss.bin'), ('m3.bin', 'm3.bin')):
        add('vendor/firmware_mnt/image/qca6390/' + source,
            request('qca6390_wlan', 'ath11k/QCA6390/hw2.0/' + target), 'qca6390_wlan',
            'API1 executable input only; board data and protocol acceptance remain unresolved')

    # Re-parse the actually mapped names. This verifies that requested sibling
    # paths still close after an .mdt/.elf -> .mbn name and directory change.
    mapped_layouts = {}
    for name in layouts:
        layout = bundle.inspect_mdt(name, package)
        if not layout['loader_file_set_complete']:
            raise ValueError('canonical MDT sibling mapping is incomplete: ' + name)
        mapped_layouts[name] = layout
    used = {row['source_path'].lstrip('/') for row in files}
    excluded = [{'source_path': '/' + name, 'group': bundle.SOURCES[name],
                 'size_bytes': source_records[name]['size_bytes'],
                 'sha256': source_records[name]['sha256']} for name in sorted(set(payloads) - used)]
    manifest = {
        'schema_version': 1, 'status': 'staged_reviewed_paths_with_explicit_open_gates',
        'scope': 'Installable file tree for later image assembly; no live installation or hardware acceptance',
        'kernel_release': KERNEL_RELEASE, 'kernel_provenance': contract['provenance'],
        'source': {'archive_sha256': ARCHIVE_SHA256, 'archive_bytes': ARCHIVE_BYTES,
                   'source_manifest_sha256': MANIFEST_SHA256,
                   'capture_reference': CAPTURE_REFERENCE, 'capture_sha256': CAPTURE_SHA256,
                   'contract_reference': CONTRACT_REFERENCE, 'contract_sha256': CONTRACT_SHA256,
                   'stager_reference': 'scripts/research/stage_stock_firmware.py',
                   'stager_sha256': digest(Path(__file__).read_bytes()),
                   'io_helper_reference': 'scripts/research/stage_gpu_firmware.py',
                   'io_helper_sha256': digest(Path(safe_io.__file__).read_bytes()),
                   'mdt_parser_reference': 'scripts/research/stock_firmware_bundle.py',
                   'mdt_parser_sha256': PARSER_SHA256},
        'selection': {'zap_format': zap_format, 'novatek': 'dt-both-6',
                      'bluetooth': 'original-rom10-and-rom20-pairs', 'wlan': 'api1-executables-only',
                      'runtime_bluetooth_rom_verified': False,
                      'runtime_novatek_panel_gpio_verified': False,
                      'wlan_board_data_selected': False},
        'files': sorted(files, key=lambda row: row['destination']),
        'firmware_file_count': len(files), 'firmware_payload_bytes': sum(map(len, package.values())),
        'canonical_mdt_layouts': mapped_layouts,
        'component_state_in_frozen_contract': {key: entry['state'] for key, entry in components.items()},
        'excluded_captured_inputs': excluded,
        'open_gates': [
            'WLAN runtime board identity and matching board-2.bin/board.bin are not established',
            'Bluetooth runtime ROM must match one of the preserved candidates before claiming selection',
            'Novatek mainline panel-ID selection and controller firmware acceptance are untested',
            'TFA9894 has no validated driver/container-request contract; neither QS nor YC is installed',
            'PCIe, Novatek, Venus and TFA consumers remain disabled in the frozen display DT',
            'DSP/Venus reserved-memory fit, service or HFI ABI and secure authentication are untested',
            'No GPU, radio, input, audio, video or other physical Linux acceptance is implied',
        ],
        'all_staged_mdt_file_dependencies_complete': True,
        'all_hardware_firmware_contracts_satisfied': False,
        'vendor_signature_authentication_performed': False,
        'firmware_loaded': False, 'live_system_modified': False,
        'wlan_board_database_created': False, 'tfa_containers_installed': False,
    }
    package['stock-firmware-manifest.json'] = bundle.json_bytes(manifest)
    package['SHA256SUMS'] = ''.join(digest(data) + '  ' + name + '\n'
                                   for name, data in sorted(package.items())).encode()
    return manifest, package


def verify_output(output, expected):
    # The new prefix has a fixed small file set. Refuse links and special files
    # when independently re-reading it; never follow an unexpected directory.
    observed = set()
    for directory, dirs, names in os.walk(output, followlinks=False):
        for name in dirs:
            if not stat.S_ISDIR((Path(directory) / name).lstat().st_mode):
                raise ValueError('unexpected staged directory type')
        for name in names:
            path = Path(directory) / name
            relative = str(path.relative_to(output))
            if relative not in expected or relative in observed:
                raise ValueError('unexpected or duplicate staged file')
            raw = read_file(path, bundle.MAX_FILE)
            if digest(raw) != digest(expected[relative]) or path.lstat().st_mode & 0o777 != 0o644:
                raise ValueError('staged content or mode differs: ' + relative)
            observed.add(relative)
    if observed != set(expected):
        raise ValueError('staged file missing')
    return {'status': 'verified', 'file_count_including_metadata': len(observed),
            'independent_file_rereads_match': True, 'unexpected_files': [],
            'manifest_sha256': digest(expected['stock-firmware-manifest.json']),
            'checksums_sha256': digest(expected['SHA256SUMS'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--zap-format', choices=('elf', 'mdt'), required=True)
    parser.add_argument('--novatek-variants', choices=('dt-both-6',), required=True,
                        help='Explicitly include both revision-6 firmware names selected by this DT')
    parser.add_argument('--capture', type=Path, default=REPO / CAPTURE_REFERENCE)
    parser.add_argument('--contract', type=Path, default=REPO / CONTRACT_REFERENCE)
    args = parser.parse_args()
    output, archive = safe_io.safe_absolute(args.output), safe_io.safe_absolute(args.archive)
    if output.exists() or output.is_symlink():
        parser.error('staging prefix exists; overwriting is forbidden')
    if output.is_relative_to(archive) or archive.is_relative_to(output):
        parser.error('source and output paths overlap')
    if digest(Path(bundle.__file__).read_bytes()) != PARSER_SHA256:
        parser.error('shared MDT parser differs from its reviewed revision')
    capture = pinned_json(args.capture, CAPTURE_SHA256)
    contract = pinned_json(args.contract, CONTRACT_SHA256)
    payloads, records = read_archive(archive, capture)
    manifest, package = plan_tree(payloads, records, contract, args.zap_format)
    original_umask = os.umask(0o022)
    try:
        with safe_io.open_directory(output.parent) as parent:
            safe_io.publish_new(parent, output.name, package)
    finally:
        os.umask(original_umask)
    verification = verify_output(output, package)
    print(json.dumps({'status': manifest['status'], 'output': str(output),
                      'firmware_file_count': manifest['firmware_file_count'],
                      'firmware_payload_bytes': manifest['firmware_payload_bytes'],
                      'selection': manifest['selection'], 'verification': verification,
                      'all_hardware_firmware_contracts_satisfied': False,
                      'live_system_modified': False}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
