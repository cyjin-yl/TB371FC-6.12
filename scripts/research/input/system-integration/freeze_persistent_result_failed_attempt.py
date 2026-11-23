#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Retain R4E's closed, failed run without rescoring its original controller.

The guest behavior and ordinary result transport succeeded; one full-log AVC
still failed the run. This distinct post-run tool may retain that failed run's
already-exported policy. The executed passed-only retention helper is unchanged.
Only read-only debugfs, ordinary-file reads, hashing, and new evidence outputs
are used: no mount, replay, repair, VM, or kernel-policy operation.
"""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tarfile

WORK = Path('/work/fedora-input-system-v8')
RECIPE = Path('/work/fedora-input-system-recipe-r4-v6')
IMAGE = WORK / 'fedora45-research4e-persistent-result.ext4'
OUTPUT = Path('/work/fedora-r4e-closed-image-evidence-v1')
RECIPE_SHA = 'c453d67a35b466be76924eceb7f3af96bfd15ed313ee5cba11963a9de91fcb94'
READER_SHA = '71df5f32894a0f8b232173378786c39f39aca567af801dc3c5e035b04577dc25'
FIXED = {
    'vm-verify-01/serial.log': (1395418, 'a88df1ce7489884a0c228a4a2a0320c4dc2c2f425b2a769b88c1f170823f3534'),
    'vm-verify-01/result.json': (676766, 'ac6db6cac9ad5d375e1b054ac3c70c8bef877b994b28662488f368888412f478'),
    'vm-verify-01/guest-result.json': (413706, '3e48c9a429cad37d8baabf3fed31fe9abefdbaedfb065a484faf445bb6c2fa11'),
    'pipeline.exit.json': (894, 'a29888e4f4bc7d067474f90f33a3696eb8503d85e55a7edc1f989bb43d89d9be'),
}
PUBLIC_STEM = 'fedora-r4e-persistent-result-failed'


def key(value):
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def ordinary(path, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError('ordinary bounded evidence required: ' + str(path))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        if key(before) != key(os.fstat(descriptor)) or len(raw) != before.st_size:
            raise ValueError('evidence changed during read: ' + str(path))
        return raw
    finally:
        os.close(descriptor)


def identity(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError('ordinary evidence required: ' + str(path))
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if key(before) != key(os.fstat(descriptor)):
            raise ValueError('evidence changed during hashing: ' + str(path))
        return {'size': before.st_size, 'sha256': digest}
    finally:
        os.close(descriptor)


def write_json(path, value):
    raw = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def load_reader():
    path = RECIPE / 'read_vm_result.py'
    if identity(path)['sha256'] != READER_SHA:
        raise ValueError('fixed executed reader source differs')
    specification = importlib.util.spec_from_file_location('closed_r4e_result_reader', path)
    module = importlib.util.module_from_spec(specification)
    sys.dont_write_bytecode = True
    specification.loader.exec_module(module)
    return module


def retain_policy(reader, expected, receipt):
    if not (expected.get('guest_path') == '/var/lib/tb371fc-r4e-proof/loaded-policy.33' and
            expected.get('version') == 33 and expected.get('mode') == 0o600 and
            expected.get('boot_id') == receipt['boot_id'] and
            expected.get('size') == 3835444 and
            expected.get('sha256') == '9d7aa2b3d3c64e8c24dbff83e8850036b8e15cec63aaa1521bbea555f42b2342' and
            expected.get('kernel_policy_written') is False):
        raise ValueError('actual same-boot export identity differs from this failed run')
    descriptor = os.open(IMAGE, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    commands, files, parents = [], {}, {}
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != 4294967296:
            raise ValueError('fixed ordinary closed VM image required')
        source = '/proc/self/fd/' + str(descriptor)

        def debugfs(request):
            value = subprocess.run(['/usr/sbin/debugfs', '-R', request, source],
                                   capture_output=True, timeout=30, pass_fds=(descriptor,),
                                   env={**os.environ, 'LC_ALL': 'C'})
            if value.returncode or len(value.stdout) + len(value.stderr) > 32768:
                raise RuntimeError('bounded read-only debugfs request failed')
            item = {'request': request, 'exit_code': value.returncode,
                    'stdout': value.stdout.decode(errors='replace'),
                    'stderr': value.stderr.decode(errors='replace')}
            commands.append(item)
            return item['stdout']

        for name in ('/var', '/var/lib', '/var/lib/tb371fc-r4e-proof'):
            metadata = reader.metadata_from_stat(debugfs('stat ' + name))
            if not (metadata['type'] == 'directory' and metadata['uid'] == metadata['gid'] == 0):
                raise ValueError('guest export path crosses a non-directory or unexpected owner')
            if name.endswith('-proof') and metadata['mode'] != 0o700:
                raise ValueError('guest export directory must have mode 0700')
            parents[name] = metadata
        for name, limit in (('loaded-policy.33', 16 * 1024**2), ('loaded-policy-export.json', 8192)):
            guest_path = '/var/lib/tb371fc-r4e-proof/' + name
            destination = OUTPUT / name
            inode = reader.metadata_from_stat(debugfs('stat ' + guest_path))
            if not (inode['type'] == 'regular' and inode['uid'] == inode['gid'] == 0 and
                    inode['mode'] == 0o600 and inode['nlink'] == 1 and 0 < inode['size'] <= limit):
                raise ValueError('guest export member is not an ordinary private bounded file')
            if destination.exists() or destination.is_symlink():
                raise FileExistsError('new extraction destination required')
            # All paths are fixed profile constants, never supplied by guest JSON.
            debugfs('dump -p ' + guest_path + ' ' + str(destination))
            raw = ordinary(destination, limit)
            actual = destination.lstat()
            if not (actual.st_uid == actual.st_gid == 0 and stat.S_IMODE(actual.st_mode) == 0o600 and
                    actual.st_nlink == 1 and len(raw) == inode['size']):
                raise ValueError('retained member metadata differs from the actual guest inode')
            files[name] = {'path': str(destination), 'guest_path': guest_path,
                           **identity(destination), 'guest_inode': inode}
            if name == 'loaded-policy.33':
                if not (len(raw) == expected['size'] and files[name]['sha256'] == expected['sha256'] and
                        struct.unpack_from('<II', raw) == (0xf97cff8c, 8) and raw[8:16] == b'SE Linux' and
                        struct.unpack_from('<I', raw, 16)[0] == 33):
                    raise ValueError('actual exported policy bytes/header differ')
            elif json.loads(raw) != expected:
                raise ValueError('actual image export metadata differs from the complete guest result')
        if key(before) != key(os.fstat(descriptor)):
            raise ValueError('source image metadata changed during read-only extraction')
    finally:
        os.close(descriptor)
    return {'schema_version': 1, 'retention_completed': True, 'source_run_overall_passed': False,
            'source_run_normal_qemu_exit': True, 'source_run_guest_result_transport_qualified': True,
            'same_boot_export_record': expected, 'files': files, 'parent_inodes': parents,
            'read_only_debugfs_requests': commands, 'source_image_metadata_unchanged': True,
            'image_opened_for_write': False, 'image_mounted': False,
            'filesystem_replayed_or_repaired': False, 'kernel_policy_loaded_or_written': False,
            'extra_vm_started': False, 'failure_reclassified_as_pass': False,
            'scope': 'ordinary same-boot export from the already closed failed R4E image'}


def main():
    if WORK.is_symlink() or RECIPE.is_symlink() or not WORK.is_dir() or not RECIPE.is_dir():
        raise ValueError('fixed ordinary independent work and recipe required')
    manifest = identity(RECIPE / 'recipe-manifest.json')
    if manifest['sha256'] != RECIPE_SHA:
        raise ValueError('immutable executed recipe manifest differs')
    recipe_files = json.loads(ordinary(RECIPE / 'recipe-manifest.json', 16384))
    if len(recipe_files) != 20:
        raise ValueError('the actual complete 20-file recipe is required')
    for name, expected in recipe_files.items():
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', name) or identity(RECIPE / name) != expected:
            raise ValueError('actual executed recipe file differs: ' + name)
    fixed_raw = {}
    for name, (size, digest) in FIXED.items():
        raw = ordinary(WORK / name, 8 * 1024**2)
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError('closed original evidence differs: ' + name)
        fixed_raw[name] = raw
    controller = json.loads(fixed_raw['vm-verify-01/result.json'])
    envelope = json.loads(fixed_raw['vm-verify-01/guest-result.json'])
    pipeline = json.loads(fixed_raw['pipeline.exit.json'])
    serial = fixed_raw['vm-verify-01/serial.log']
    if not (pipeline.get('exit_code') == 1 and controller.get('passed') is False and
            controller.get('qemu_exit_code') == 0 and controller.get('termination_reason') is None and
            controller.get('phase') == 'verify' and controller.get('guest_gates_match') is True and
            controller.get('persistent_result_qualified') is True and controller.get('parse_error') is None and
            controller.get('serial_log_sha256') == FIXED['vm-verify-01/serial.log'][1] and
            controller.get('serial_log_bytes') == len(serial)):
        raise ValueError('closed failed overall / qualified guest-result scope differs')
    warnings = controller['observed_warning_counts']
    if warnings.get('selinux_avc_denial_count') != 1 or any(value != 0 for name, value in warnings.items()
                                                          if name != 'selinux_avc_denial_count'):
        raise ValueError('fixed actual full-log failure/loss counts differ')
    guest = controller['guest_result']
    if not (envelope.get('status') == 'pass' and envelope.get('result') == guest and
            envelope.get('failure') is None and envelope.get('complete_system_accepted') is False and
            envelope.get('host_full_log_qualification_pending') is True):
        raise ValueError('original complete guest result must remain distinct from overall qualification')
    reader = load_reader()
    receipt = reader.receipt_from_serial(serial, guest['profile_sha256'])
    if not (receipt['sha256'] == FIXED['vm-verify-01/guest-result.json'][1] and
            receipt['size'] == FIXED['vm-verify-01/guest-result.json'][0] and
            receipt['boot_id'] == envelope['boot_id'] == guest['initrd_process_domains']['boot_id']):
        raise ValueError('original complete result and raw receipt differ')
    if (WORK / 'actual-policy-export.json').exists() or any((WORK / 'jobs').glob('post-qualify-*.json')) or \
            any((WORK / 'jobs').glob('finalize-*.json')):
        raise ValueError('the original stopped pipeline unexpectedly ran a later phase')
    OUTPUT.mkdir(mode=0o700)
    retention = retain_policy(reader, guest['actual_loaded_policy_export'], receipt)
    write_json(OUTPUT / 'retention.json', retention)
    print(json.dumps({'stage': 'actual_policy_retained', 'record': identity(OUTPUT / 'retention.json'),
                      'policy': retention['files']['loaded-policy.33']}, sort_keys=True), flush=True)

    lines = serial.decode(errors='replace').splitlines()
    direct_avcs = [{'line_number': index + 1, 'line': line,
                    'context': lines[max(0, index - 4):index + 7]}
                   for index, line in enumerate(lines)
                   if re.match(r'^\[\s*[0-9.]+\]\s+audit: type=1400 ', line)
                   and 'avc:' in line and 'denied' in line]
    if len(direct_avcs) != 1:
        raise ValueError('the direct original kernel AVC count differs')
    attachment = 'bpf-restrict-fs: LSM BPF program attached'
    metadata = {}
    for name in ('baseline-copy.json', 'baseline-copy-qualification.json', 'kernel-transfer.json',
                 'runtime.json', 'system-profile.json', 'configured.json', 'policy-replacement.json',
                 'initramfs.json', 'initramfs-archive-verification.json', 'image.before-boot.json',
                 'maintenance-initramfs.json', 'maintenance-initramfs-verification.json',
                 'early-policy-profile-inputs.json', 'initrd-proof-payloads.json',
                 'pipeline-command.json', 'pipeline.exit.json'):
        path = WORK / name
        if path.is_file():
            metadata[name] = {'identity': identity(path), 'record': json.loads(ordinary(path, 2 * 1024**2))}
    controller_summary = {name: value for name, value in controller.items()
                          if name not in ('guest_result', 'persistent_result', 'persistent_result_transport')}
    guest_summary = {name: value for name, value in guest.items() if name != 'transient_policy_contracts'}
    route_summary = {name: {key: value for key, value in route.items()
                           if key not in ('queries', 'contexts', 'return_codes', 'descriptor_inputs')}
                     for name, route in guest['transient_policy_contracts'].items()}
    image_after = identity(IMAGE)
    report = {
        'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'status': 'generic_vm_verification_failed', 'overall_passed': False,
        'guest_behavioral_checks_passed': True, 'ordinary_result_transport_qualified': True,
        'evidence_class': 'host_build', 'scope': 'generic ARM64 VM without physical device passthrough',
        'work': str(WORK), 'pipeline': pipeline,
        'phase_jobs': {path.stem: json.loads(ordinary(path, 65536)) for path in sorted((WORK / 'jobs').glob('*.json'))},
        'original_controller_result_rewritten': False, 'original_full_log_failure_preserved': True,
        'controller_summary': controller_summary, 'complete_guest_summary': guest_summary,
        'live_policy_contracts_summary': route_summary,
        'live_policy_contract_query_count_per_route': 82,
        'offline_candidate_query_count_is_separate': 86,
        'result_receipt': receipt, 'direct_original_kernel_avcs': direct_avcs,
        'all_original_warning_counts': warnings,
        'bpf_attachment_observation': {'source_marker': attachment,
            'full_raw_occurrence_count': sum(attachment in line for line in lines),
            'lines': [line for line in lines if attachment in line],
            'source_contract': 'docs/research/2026-11-23/systemd-bpf-runtime-contract.md'},
        'actual_bpf_behavior_executed': True,
        'post_qualification_phase_executed': False, 'finalize_phase_executed': False,
        'separate_udev_handoff_qualification_executed': False,
        'actual_loaded_policy_retention': retention,
        'closed_image_after_normal_qemu_exit': {'path': str(IMAGE), **image_after,
            'qemu_exit_code': 0, 'termination_reason': None, 'filesystem_replayed_or_repaired': False,
            'postboot_filesystem_check_executed': False},
        'actual_execution_recipe': {'path': str(RECIPE), 'manifest': manifest, 'files': recipe_files},
        'retained_metadata': metadata, 'freezer_source': identity(Path(__file__)),
        'physical_tablet_booted': False, 'tablet_hardware_tested': False, 'all_hardware_accepted': False,
        'limits': [
            'The guest pass envelope precedes independent full-log qualification; overall remains failed.',
            'The visible journalctl socket-create denial remains a failure even though --sync exited 0.',
            'Zero observed audit-loss markers does not assert that every possible unobservable event is disproven.',
            'No positive udev queue counts means no count-based empty-queue or whole-queue preservation claim.',
            'The stopped post-qualify/finalize phases are not backfilled as executed.',
            'The generic-VM-only production initramfs rejects a physical tablet; it is not an owner boot artifact.',
        ],
    }
    report_path = OUTPUT / (PUBLIC_STEM + '.json')
    write_json(report_path, report)
    members = {
        report_path.name: report_path,
        PUBLIC_STEM + '-verify.json': WORK / 'vm-verify-01/result.json',
        PUBLIC_STEM + '-verify.log': WORK / 'vm-verify-01/serial.log',
        PUBLIC_STEM + '-guest.json': WORK / 'vm-verify-01/guest-result.json',
        PUBLIC_STEM + '-label.json': WORK / 'vm-label-01/result.json',
        PUBLIC_STEM + '-label.log': WORK / 'vm-label-01/serial.log',
        PUBLIC_STEM + '-pipeline.json': WORK / 'pipeline.exit.json',
        PUBLIC_STEM + '-policy-retention.json': OUTPUT / 'retention.json',
    }
    entries = {name: identity(path) for name, path in members.items()}
    packet_path = OUTPUT / 'public-evidence.tar.gz'
    with packet_path.open('xb') as destination:
        with tarfile.open(fileobj=destination, mode='w:gz', compresslevel=9) as archive:
            for name, path in members.items():
                archive.add(path, arcname=name, recursive=False)
    for name, path in members.items():
        if identity(path) != entries[name]:
            raise ValueError('public evidence changed while packaging: ' + name)
    packet = {'path': str(packet_path), **identity(packet_path), 'members': entries,
              'private_policy_binary_included': False, 'source_image_metadata_unchanged_during_retention': True}
    write_json(OUTPUT / 'public-evidence-manifest.json', packet)
    print(json.dumps({'stage': 'failed_attempt_frozen', 'overall_passed': False,
                      'report': identity(report_path), 'packet': packet,
                      'actual_policy_retention': identity(OUTPUT / 'retention.json')}, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
