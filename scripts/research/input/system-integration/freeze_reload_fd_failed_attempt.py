#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Freeze v7's actual failure and retain its ordinary policy export read-only.

The original controller result is never repaired or rerun. Intact progress
frames are separate partial observations; malformed frames stay malformed.
No mount, VM, policy operation, filesystem replay or image write is performed.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess

WORK = Path('/work/fedora-input-system-v7')
RECIPE = Path('/work/fedora-input-system-recipe-r4-v5')
RECIPE_SHA = '0779fa0982a23fe9e30c58d17f721df8222d438b7329370fdaa918d13075879b'
SERIAL_SHA = 'cfe215d2a33dc01f8ffdf7ab5bc2d7dd2f7fafec309d06c82eb3db48bb5658aa'
IMAGE = WORK / 'fedora45-research4d-reload-fd-contract.ext4'
POLICY_OUTPUT = Path('/work/fedora-r4d-closed-image-evidence-v1')


def identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary closed evidence required: ' + str(path))
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'size': path.stat().st_size, 'sha256': value}


def ordinary(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError('ordinary bounded evidence required: ' + str(path))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        after = os.fstat(descriptor)
        key = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if key(before) != key(after) or len(raw) != before.st_size:
            raise ValueError('evidence changed while read: ' + str(path))
        return raw
    finally:
        os.close(descriptor)


def strict_frames(raw):
    records, errors = [], []
    pattern = rb'(?m)^TB371FC_R4D_VM_PROGRESS ([^\n]*)'
    for match in re.finditer(pattern, raw):
        payload = match[1].rstrip(b'\r')
        item = {'byte_offset': match.start(), 'payload_bytes': len(payload),
                'payload_sha256': hashlib.sha256(payload).hexdigest()}
        try:
            record = json.loads(payload)
            if not isinstance(record, dict) or record.get('complete_system_pass') is not False:
                raise ValueError('unexpected progress envelope')
            records.append({**item, 'record': record})
        except (ValueError, UnicodeError) as error:
            errors.append({**item, 'error': {'type': type(error).__name__, 'message': str(error)},
                'prefix_excerpt': payload[:1000].decode(errors='replace'),
                'suffix_excerpt': payload[-1000:].decode(errors='replace'),
                'excerpt_is_complete_payload': len(payload) <= 1000})
    return records, errors


def retain_export(expected):
    if not (expected.get('guest_path') == '/var/lib/tb371fc-r4d-proof/loaded-policy.33' and
            expected.get('version') == 33 and expected.get('mode') == 0o600 and
            type(expected.get('size')) is int and 1024 < expected['size'] <= 32 * 1024**2 and
            re.fullmatch('[0-9a-f]{64}', expected.get('sha256', '')) and
            expected.get('kernel_policy_written') is False):
        raise ValueError('actual strict progress frame does not contain the qualified export record')
    POLICY_OUTPUT.mkdir(mode=0o700)
    before = IMAGE.stat()
    copied = {}
    for name, bound in (('loaded-policy.33', 32 * 1024**2), ('loaded-policy-export.json', 8192)):
        source = '/var/lib/tb371fc-r4d-proof/' + name
        destination = POLICY_OUTPUT / name
        command = ['/usr/sbin/debugfs', '-R', 'dump -p ' + source + ' ' + str(destination), str(IMAGE)]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode or len(result.stdout) + len(result.stderr) > 16384:
            raise RuntimeError('read-only debugfs extraction failed: ' + name)
        raw = ordinary(destination, bound)
        info = destination.stat()
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError('ordinary export uid/mode differs from the actual guest contract')
        copied[name] = {'path': str(destination), **identity(destination),
                        'uid': info.st_uid, 'gid': info.st_gid, 'mode': stat.S_IMODE(info.st_mode),
                        'read_only_debugfs_exit_code': result.returncode}
        if name == 'loaded-policy.33':
            if not (len(raw) == expected['size'] and copied[name]['sha256'] == expected['sha256'] and
                    struct.unpack_from('<II', raw) == (0xf97cff8c, 8) and raw[8:16] == b'SE Linux' and
                    struct.unpack_from('<I', raw, 16)[0] == 33):
                raise ValueError('actual image member differs from the same-boot exported policy')
        elif json.loads(raw) != expected:
            raise ValueError('ordinary export metadata differs from the intact serial progress record')
    after = IMAGE.stat()
    key = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if key(before) != key(after):
        raise ValueError('source image metadata changed during read-only retention')
    return {'completed': True, 'files': copied, 'same_boot_guest_record': expected,
            'source_image_metadata_unchanged': True, 'image_opened_for_write': False,
            'image_mounted': False, 'filesystem_replayed_or_repaired': False,
            'kernel_policy_loaded_or_written': False, 'extra_vm_started': False,
            'source_was_failed_vm_image': True, 'failure_reclassified_as_pass': False}


def main():
    if WORK.is_symlink() or not WORK.is_dir() or IMAGE.is_symlink() or not IMAGE.is_file():
        raise ValueError('the fixed independent v7 work/image is required')
    if identity(RECIPE / 'recipe-manifest.json')['sha256'] != RECIPE_SHA:
        raise ValueError('actual immutable execution recipe differs')
    pipeline = json.loads(ordinary(WORK / 'pipeline.exit.json', 16384))
    if pipeline.get('exit_code') != 1:
        raise ValueError('the closed failed v7 pipeline is required')
    controller_path = WORK / 'vm-verify-01/result.json'
    controller = json.loads(ordinary(controller_path, 4 * 1024**2))
    if not (controller.get('passed') is False and controller.get('qemu_exit_code') is not None and
            controller.get('termination_reason') == 'guest reported failure'):
        raise ValueError('the original completed failure must remain a failure')
    raw = ordinary(WORK / 'vm-verify-01/serial.log', 8 * 1024**2)
    if (hashlib.sha256(raw).hexdigest() != SERIAL_SHA or
            controller.get('serial_log_sha256') != SERIAL_SHA or controller.get('serial_log_bytes') != len(raw)):
        raise ValueError('full raw serial no longer matches the original closed controller record')
    progress, framing_errors = strict_frames(raw)
    by_stage = {}
    for item in progress:
        by_stage.setdefault(item['record']['stage'], []).append(item['record']['details'])
    exported = by_stage.get('actual_loaded_policy_export', [])
    retention = {'completed': False}
    if len(exported) != 1:
        retention['error'] = {'message': 'exactly one intact actual policy export frame was not found'}
    else:
        try:
            retention = retain_export(exported[0])
        except Exception as error:
            retention['error'] = {'type': type(error).__name__, 'message': str(error)}
    lines = raw.decode(errors='replace').splitlines()
    attachment_marker = b'bpf-restrict-fs: LSM BPF program attached'
    attachment_hits = [
        {'byte_offset': match.start(),
         'context_excerpt': raw[max(0, match.start() - 180):match.end() + 180].decode(errors='replace')}
        for match in re.finditer(re.escape(attachment_marker), raw)]
    direct_avc = [line for line in lines if re.match(r'^\[\s*[0-9.]+\]\s+audit: type=1400 ', line)
                  and 'avc:' in line and 'denied' in line]
    metadata = {}
    for name in ('baseline-copy.json', 'baseline-copy-qualification.json', 'kernel-transfer.json',
                 'runtime.json', 'system-profile.json', 'configured.json', 'policy-replacement.json',
                 'initramfs.json', 'initramfs-archive-verification.json', 'image.before-boot.json',
                 'maintenance-initramfs.json', 'maintenance-initramfs-verification.json',
                 'early-policy-profile-inputs.json', 'initrd-proof-payloads.json',
                 'pipeline-command.json', 'pipeline.exit.json',
                 'udev-handoff-qualification-vm-verify-01.json'):
        path = WORK / name
        if path.is_file():
            metadata[name] = identity(path)
    report = {'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'generic_vm_verification_failed', 'overall_passed': False,
        'scope': 'host construction and named partial generic ARM64 VM observations only',
        'work': str(WORK), 'profile': json.loads((WORK / 'system-profile.json').read_text()),
        'pipeline': pipeline, 'phase_jobs': {p.stem: json.loads(p.read_text()) for p in sorted((WORK / 'jobs').glob('*.json'))},
        'vm_runs': {name: {'result': json.loads((WORK / name / 'result.json').read_text()),
                          'metadata': identity(WORK / name / 'result.json'),
                          'serial': identity(WORK / name / 'serial.log')}
                    for name in ('vm-label-01', 'vm-verify-01')},
        'original_controller_parse_error_retained': controller.get('parse_error'),
        'original_controller_result_rewritten': False,
        'strict_progress_frames': progress, 'malformed_progress_frames': framing_errors,
        'progress_analysis_method': 'whole original progress line JSON only; no trimming, concatenation, repair, or rescoring of controller',
        'actual_loaded_policy_retention': retention,
        'direct_kernel_avc_lines': direct_avc,
        'suppression_messages': [line for line in lines if 'callbacks suppressed' in line],
        'early_native_and_domain_lines': [line for line in lines if line.startswith('TB371FC_EARLY_SELINUX_V2 ') or
            line.startswith('TB371FC_TMPFS_STAGE') or line.startswith('TB371FC_R4D_INITRD_DOMAINS ')],
        'standard_reload_and_transition_lines': [line for line in lines if
            'Successfully switched to calculated init label ' in line or 'Successfully loaded SELinux policy in ' in line or
            'Failed to load new SELinux policy' in line or 'Failed to transition into init label ' in line],
        'pl061_serial_lines': [line for line in lines if ('PL061' in line or 'pl061' in line)
                               and not line.startswith('TB371FC_R4D_VM_PROGRESS ')],
        'actual_bpf_behavior_run': bool(by_stage.get('bpf_same_worker_baseline_attempt')),
        'bpf_attachment_observation': {
            'exact_source_marker': attachment_marker.decode(),
            'full_raw_occurrence_count': len(attachment_hits),
            'occurrences': attachment_hits,
            'marker_observed': bool(attachment_hits),
            'source_contract': 'docs/research/2026-11-23/systemd-bpf-runtime-contract.md',
            'counts_may_include_later_journal_repetition': True,
            'attachment_is_not_restricted_behavior_test': True},
        'complete_system_marker_observed': any(line.strip() == 'TB371FC_R4D_VM_SYSTEM_COMPLETE' for line in lines),
        'retained_metadata': metadata,
        'actual_execution_recipe_manifest': identity(RECIPE / 'recipe-manifest.json'),
        'freezer_source': identity(Path(__file__)),
        'failed_image_after_owned_qemu_exit': {'path': str(IMAGE), **identity(IMAGE),
            'clean_poweroff_claimed': False, 'filesystem_replayed_or_repaired': False},
        'physical_tablet_booted': False, 'tablet_hardware_tested': False, 'all_hardware_accepted': False,
        'limits': ['An intact named partial observation is not complete system acceptance.',
                   'The original controller parse error and all visible AVCs remain failures.',
                   'No malformed serial frame is repaired or used to infer a missing result.',
                   'Missing BPF behavior remains not run, regardless of source or attachment logs.',
                   'QEMU uses generic virt; no owner-tablet boot or device use occurred.']}
    output = WORK / 'fedora-input-system-attempt.json'
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'report': identity(output),
                      'intact_progress_frames': len(progress), 'malformed_frames': len(framing_errors),
                      'ordinary_actual_policy_retained': retention['completed']}, sort_keys=True))


if __name__ == '__main__':
    main()
