#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Retain the closed R4F successful attempt without changing its evidence.

This collector only accepts the complete original pipeline's success. It does
not repair an image, rescore a failed controller or execute a guest program.
The source image checksum comes from the already completed finalizer; no extra
whole-image hash is claimed here. Exported policy bytes remain private.
"""
import datetime
import hashlib
import io
import json
import lzma
import os
from pathlib import Path
import stat
import tarfile

WORK = Path('/work/fedora-input-system-v9')
RECIPE = Path('/work/fedora-input-system-recipe-r4-v7')
OUTPUT = Path('/work/fedora-r4f-closed-image-evidence-v1')
RECIPE_SHA = '927fd0755f54f303adac25daa8342bfe4615d0d42ff9a07361d29226f7cdf947'
PROFILE_NAME = 'research4-display-input-fedora45-v9-persistent-result'
PHASES = ('stage', 'configure', 'initramfs', 'image', 'vm-label', 'vm-verify',
          'post-qualify', 'finalize')


def identity(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def serial(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or not 0 < first.st_size <= limit:
            raise ValueError('ordinary bounded source required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        last = os.fstat(fd)
        key = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size,
                            item.st_mtime_ns, item.st_ctime_ns)
        if key(first) != key(last) or len(raw) != first.st_size:
            raise ValueError('source changed during read: ' + str(path))
        return raw
    finally:
        os.close(fd)


def main():
    if WORK.is_symlink() or not WORK.is_dir() or RECIPE.is_symlink() or not RECIPE.is_dir():
        raise ValueError('fixed ordinary completed work and recipe required')
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh evidence destination required')
    manifest_raw = read(RECIPE / 'recipe-manifest.json', 16384)
    if identity(manifest_raw)['sha256'] != RECIPE_SHA:
        raise ValueError('exact R4F execution sources required')
    manifest = json.loads(manifest_raw)
    if len(manifest) != 20:
        raise ValueError('complete twenty-file recipe required')
    for name, expected in manifest.items():
        if '/' in name or name in ('.', '..'):
            raise ValueError('noncanonical recipe member')
        if identity(read(RECIPE / name, 256 * 1024)) != expected:
            raise ValueError('executed source changed: ' + name)
    pipeline_raw = read(WORK / 'pipeline.exit.json', 65536)
    pipeline = json.loads(pipeline_raw)
    if (pipeline.get('exit_code') != 0 or pipeline.get('error') or
            pipeline.get('cancelled_signal') is not None or
            pipeline.get('recipe_manifest_sha256') != RECIPE_SHA):
        raise ValueError('original complete pipeline did not succeed')
    jobs = {}
    for phase in PHASES:
        raw = read(WORK / 'jobs' / (phase + '-01.json'), 65536)
        item = json.loads(raw)
        if item.get('exit_code') != 0 or item.get('error') or item.get('cancelled_signal') is not None:
            raise ValueError('required original phase did not succeed: ' + phase)
        command = item.get('command')
        if not isinstance(command, list) or len(command) < 2:
            raise ValueError('phase command missing')
        source = Path(command[1])
        if source.parent != RECIPE or source.name not in manifest or item.get('recipe_sha256') != manifest[source.name]['sha256']:
            raise ValueError('phase source identity differs: ' + phase)
        jobs[phase] = {'record': identity(raw), 'result': item}

    profile_raw = read(WORK / 'system-profile.json', 65536)
    profile = json.loads(profile_raw)
    profile_sha = identity(profile_raw)['sha256']
    if profile.get('profile') != PROFILE_NAME or profile.get('root_label') != 'tb371fc-r4f-f45':
        raise ValueError('independent R4F profile required')
    report_raw = read(WORK / 'fedora-input-system-integration.json', 8 * 1024**2)
    report = json.loads(report_raw)
    if (report.get('status') != 'generic_vm_system_verified' or report.get('profile') != profile or
            report.get('physical_tablet_booted') is not False or report.get('all_hardware_accepted') is not False or
            report.get('post_boot_filesystem_check_exit_code') != 0):
        raise ValueError('original finalizer report scope/result differs')

    files = {
        'fedora-r4f-persistent-result.json': report_raw,
        'fedora-r4f-persistent-result-pipeline.json': pipeline_raw,
    }
    for phase, key in (('label', 'label_vm'), ('verify', 'enforcing_vm')):
        directory = WORK / ('vm-' + phase + '-01')
        raw = read(directory / 'result.json', 2 * 1024**2)
        controller = json.loads(raw)
        serial_raw = read(directory / 'serial.log', 8 * 1024**2)
        if (controller.get('passed') is not True or controller.get('qemu_exit_code') != 0 or
                controller.get('termination_reason') is not None or
                controller.get('profile_sha256') != profile_sha or
                identity(serial_raw) != {'size': controller.get('serial_log_bytes'),
                                         'sha256': controller.get('serial_log_sha256')} or
                report[key]['result'] != controller or report[key]['metadata'] != identity(raw) or
                report[key]['serial'] != identity(serial_raw)):
            raise ValueError('closed controller/raw/finalizer identity differs: ' + phase)
        files['fedora-r4f-persistent-result-' + phase + '.json'] = raw
        files['fedora-r4f-persistent-result-' + phase + '.log'] = serial_raw
        if phase == 'verify':
            guest_raw = read(directory / 'guest-result.json', 4 * 1024**2)
            receipt = controller.get('persistent_result_metadata', {}).get('receipt', {})
            envelope = json.loads(guest_raw)
            if (controller.get('persistent_result_qualified') is not True or
                    controller.get('guest_gates_match') is not True or
                    controller.get('guest_file_status') != 'pass' or
                    identity(guest_raw) != {key: receipt.get(key) for key in ('size', 'sha256')} or
                    envelope.get('result') != controller.get('guest_result') or
                    envelope.get('profile_sha256') != profile_sha or
                    envelope.get('boot_id') != receipt.get('boot_id')):
                raise ValueError('complete same-boot result identity differs')
            files['fedora-r4f-persistent-result-guest.json'] = guest_raw

    extras = {
        'fedora-r4f-persistent-result-udev-handoff.json': 'udev-handoff-qualification-vm-verify-01.json',
        'fedora-r4f-persistent-result-policy-retention.json': 'actual-policy-export.json',
        'fedora-r4f-persistent-result-packages.tsv': 'packages.verified.tsv',
        'fedora-r4f-persistent-result-filesystem.log': 'filesystem.after-boot.txt',
    }
    for public, original in extras.items():
        raw = read(WORK / original, 256 * 1024)
        if report['retained_metadata'].get(original) != identity(raw):
            raise ValueError('finalizer-retained input changed: ' + original)
        files[public] = raw
    policy_metadata = json.loads(files['fedora-r4f-persistent-result-policy-retention.json'])
    if policy_metadata.get('passed') is not True or policy_metadata.get('image_opened_for_write') is not False:
        raise ValueError('original private policy retention failed')
    for name, item in policy_metadata['files'].items():
        if name not in ('loaded-policy.33', 'loaded-policy-export.json'):
            raise ValueError('unexpected private retention member')
        original = WORK / 'actual-policy-export' / name
        raw = read(original, 32 * 1024**2 if name.endswith('.33') else 8192)
        if identity(raw) != {key: item[key] for key in ('size', 'sha256')}:
            raise ValueError('private retained actual-policy identity changed')
        # Deliberately do not add either private member to the public packet.

    collection = {
        'schema_version': 1, 'collected_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'closed original successful generic-VM evidence retention',
        'collector': identity(Path(__file__).read_bytes()),
        'work': str(WORK), 'recipe_manifest_sha256': RECIPE_SHA,
        'profile_sha256': profile_sha, 'completed_phase_jobs': jobs,
        'original_pipeline_exit_code': 0, 'original_controllers_passed': True,
        'image_sha256_is_from_completed_original_finalizer': True,
        'image_rehashed_by_collector': False, 'image_mounted': False,
        'image_repaired': False, 'guest_executed_by_collector': False,
        'exported_policy_bytes_in_public_packet': False,
        'original_sources_results_logs_modified': False, 'physical_tablet_tested': False,
        'files': {name: identity(raw) for name, raw in sorted(files.items())},
    }
    files['fedora-r4f-evidence-collection.json'] = serial(collection)
    OUTPUT.mkdir(mode=0o755)
    for name, raw in sorted(files.items()):
        with (OUTPUT / name).open('xb') as stream:
            stream.write(raw)
        (OUTPUT / name).chmod(0o644)
    packet_manifest = {name: identity(raw) for name, raw in sorted(files.items())}
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(files.items()):
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.mtime = len(raw), 0o644, 0
            member.uid = member.gid = 0
            archive.addfile(member, io.BytesIO(raw))
    packet = lzma.compress(payload.getvalue(), format=lzma.FORMAT_XZ, preset=6)
    with (OUTPUT / 'public-evidence.tar.xz').open('xb') as stream:
        stream.write(packet)
    packet_record = {'schema_version': 1, 'packet': identity(packet),
                     'members': packet_manifest, 'image_or_policy_payload_included': False}
    with (OUTPUT / 'packet.json').open('xb') as stream:
        stream.write(serial(packet_record))
    print(json.dumps({'output': str(OUTPUT), 'packet': identity(packet),
                      'member_count': len(files), 'collection': identity(files['fedora-r4f-evidence-collection.json'])}, sort_keys=True))


if __name__ == '__main__':
    main()
