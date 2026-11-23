#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Retain the original R4F host-image timeout, without reading its image payload.

This is a failure collector, not an image repair, a retry, or a VM verifier.
The original twenty-file recipe, four completed phase records, and both
qualified initramfs records are retained byte for byte in a new directory.
"""
from __future__ import annotations

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
OUTPUT = Path('/work/fedora-r4f-image-failure-evidence-v1')
IMAGE = WORK / 'fedora45-research4f-persistent-result.ext4'
RECIPE_SHA = '927fd0755f54f303adac25daa8342bfe4615d0d42ff9a07361d29226f7cdf947'
PHASES = ('stage', 'configure', 'initramfs', 'image')
RECORDS = ('baseline-copy.json', 'baseline-copy-qualification.json', 'kernel-transfer.json',
           'runtime.json', 'system-profile.json', 'configured.json', 'policy-replacement.json',
           'initramfs.json', 'initramfs-archive-verification.json',
           'maintenance-initramfs.json', 'maintenance-initramfs-verification.json',
           'early-policy-profile-inputs.json', 'initrd-proof-payloads.json')
ARCHIVES = {
    'initramfs.json': (32532312, '8533dcc827613d332d4869167351d50acf4694c27b52dcc6cf144ef7268503f6'),
    'maintenance-initramfs.json': (30709930, '721af9be1c6c23b5b6dc1778c48c447eb197d1a7ec0a8d7f83a0e113815e33dd'),
}


def identity(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def serial(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def read(path, limit, allow_empty=False):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit or
                before.st_size < (0 if allow_empty else 1)):
            raise ValueError('ordinary bounded evidence required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(fd)
        key = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size,
                            item.st_mtime_ns, item.st_ctime_ns)
        if key(before) != key(after) or len(raw) != before.st_size:
            raise ValueError('evidence changed during read: ' + str(path))
        return raw
    finally:
        os.close(fd)


def main():
    for directory in (WORK, RECIPE, WORK / 'jobs'):
        if directory.is_symlink() or not directory.is_dir():
            raise ValueError('ordinary fixed source directory required')
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh failure-evidence destination required')
    manifest_raw = read(RECIPE / 'recipe-manifest.json', 16384)
    if identity(manifest_raw)['sha256'] != RECIPE_SHA:
        raise ValueError('original R4F execution recipe differs')
    manifest = json.loads(manifest_raw)
    if len(manifest) != 20:
        raise ValueError('all original execution sources required')
    for name, item in manifest.items():
        if '/' in name or name in ('.', '..'):
            raise ValueError('noncanonical source member')
        if identity(read(RECIPE / name, 256 * 1024)) != item:
            raise ValueError('original source changed: ' + name)

    files = {'fedora-r4f-image-failed-recipe.json': manifest_raw}
    pipeline_raw = read(WORK / 'pipeline.exit.json', 65536)
    pipeline = json.loads(pipeline_raw)
    if (pipeline.get('exit_code') != 1 or pipeline.get('error') or
            pipeline.get('cancelled_signal') is not None or
            pipeline.get('recipe_manifest_sha256') != RECIPE_SHA):
        raise ValueError('the original unmodified failed pipeline is required')
    files['fedora-r4f-image-failed-pipeline.json'] = pipeline_raw
    files['fedora-r4f-image-failed-pipeline.log'] = read(WORK / 'pipeline.log', 256 * 1024)
    files['fedora-r4f-image-failed-command.json'] = read(WORK / 'pipeline-command.json', 65536)
    jobs = {}
    for phase in PHASES:
        raw = read(WORK / 'jobs' / (phase + '-01.json'), 65536)
        record = json.loads(raw)
        wanted = 1 if phase == 'image' else 0
        if (record.get('exit_code') != wanted or record.get('error') or
                record.get('cancelled_signal') is not None or
                record.get('name') != phase + '-01'):
            raise ValueError('original phase outcome differs: ' + phase)
        command = record.get('command', [])
        if len(command) < 2:
            raise ValueError('phase command is absent')
        source = Path(command[1])
        if (source.parent != RECIPE or source.name not in manifest or
                record.get('recipe_sha256') != manifest[source.name]['sha256']):
            raise ValueError('phase source identity differs: ' + phase)
        log = read(WORK / 'jobs' / (phase + '-01.log'), 2 * 1024**2, allow_empty=True)
        files['fedora-r4f-image-failed-' + phase + '.json'] = raw
        files['fedora-r4f-image-failed-' + phase + '.log'] = log
        jobs[phase] = {'record': identity(raw), 'log': identity(log), 'result': record}
    image_log = files['fedora-r4f-image-failed-image.log']
    if (b'subprocess.TimeoutExpired:' not in image_log or
            b'timed out after 600 seconds' not in image_log or
            str(IMAGE).encode() not in image_log or
            b'/usr/sbin/mkfs.ext4' not in image_log):
        raise ValueError('the actual 600-second mkfs timeout is absent')
    later = ('image.before-boot.json', 'fedora-input-system-integration.json',
             'vm-label-01', 'vm-verify-01', 'jobs/vm-label-01.json',
             'jobs/vm-verify-01.json', 'jobs/post-qualify-01.json', 'jobs/finalize-01.json')
    if any((WORK / name).exists() or (WORK / name).is_symlink() for name in later):
        raise ValueError('unexpected later-phase evidence; refuse this fixed pre-VM collector')
    metadata = {}
    for name in RECORDS:
        raw = read(WORK / name, 4 * 1024**2)
        metadata[name] = {'identity': identity(raw), 'record': json.loads(raw)}
        files['fedora-r4f-image-failed-input-' + name] = raw
    for name, (size, digest) in ARCHIVES.items():
        item = metadata[name]['record']
        if (item.get('archive_verified') is not True or item.get('size_bytes') != size or
                item.get('sha256') != digest):
            raise ValueError('previously qualified archive metadata differs: ' + name)
    partial = IMAGE.lstat()
    if not stat.S_ISREG(partial.st_mode) or partial.st_size != 4 * 1024**3:
        raise ValueError('the retained partial ordinary image differs')
    record = {
        'schema_version': 1,
        'captured_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'host_image_creation_failed_before_any_vm',
        'evidence_class': 'host_build', 'work': str(WORK), 'container': 'tb371fc-build-20261123',
        'recipe_manifest': identity(manifest_raw),
        'collector': identity(read(Path(__file__), 65536)),
        'pipeline': pipeline, 'phase_results': jobs,
        'failure': {'operation': 'mkfs.ext4 -d prepared_root', 'configured_timeout_seconds': 600,
                    'exception': 'subprocess.TimeoutExpired',
                    'no_kernel_or_guest_boot_failure_was_observed': True,
                    'concurrent_hdd_io_is_context_not_a_proven_exclusive_cause': True},
        'qualified_predecessor_inputs': metadata,
        'retained_partial_image': {'path': str(IMAGE), 'size': partial.st_size,
                                  'allocated_bytes': partial.st_blocks * 512,
                                  'mode': oct(stat.S_IMODE(partial.st_mode)),
                                  'mtime_ns': partial.st_mtime_ns, 'ctime_ns': partial.st_ctime_ns,
                                  'sha256': None, 'payload_opened_by_collector': False,
                                  'qualified_complete_filesystem': False},
        'vm_runs': 0, 'generic_vm_passed': False, 'physical_tablet_booted': False,
        'actual_loaded_policy_available': False, 'all_hardware_accepted': False,
        'image_mounted_or_repaired': False, 'original_evidence_modified': False,
        'archive_payload_rehashed_by_collector': False,
        'source_image_policy_firmware_payloads_in_public_packet': False,
        'subsequent_recovery_is_a_separate_attempt': True,
        'absent_later_phase_paths': list(later),
        'retained_files': {name: identity(raw) for name, raw in sorted(files.items())},
    }
    files['fedora-r4f-image-failed.json'] = serial(record)
    OUTPUT.mkdir(mode=0o755)
    for name, raw in sorted(files.items()):
        with (OUTPUT / name).open('xb') as stream:
            stream.write(raw)
        (OUTPUT / name).chmod(0o644)
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
                     'members': {name: identity(raw) for name, raw in sorted(files.items())}}
    with (OUTPUT / 'packet.json').open('xb') as stream:
        stream.write(serial(packet_record))
    print(json.dumps({'output': str(OUTPUT), 'packet': identity(packet),
                      'member_count': len(files), 'report': identity(files['fedora-r4f-image-failed.json'])}, sort_keys=True))


if __name__ == '__main__':
    main()
