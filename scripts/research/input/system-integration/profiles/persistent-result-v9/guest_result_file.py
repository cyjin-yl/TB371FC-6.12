#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Durably publish this isolated VM's complete evidence to one owned file.

The console carries a short receipt only. A receipt is not an acceptance
decision: the host must read the closed image, qualify the ordinary file,
and independently evaluate the original gates and complete raw console.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat

DIRECTORY = Path('/var/lib/tb371fc-r4f-proof')
FILENAME = 'system-result.json'
GUEST_PATH = str(DIRECTORY / FILENAME)
MAX_BYTES = 4 * 1024**2
CONTEXT = 'system_u:system_r:sysadm_t:s0'
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'


def publish(*, boot_id, profile_sha256, status, result, progress, failure):
    """Called only after the caller's exact VM/root/profile/Enforcing guards."""
    if (not re.fullmatch(UUID, boot_id) or
            not re.fullmatch('[0-9a-f]{64}', profile_sha256) or
            status not in ('pass', 'fail') or not isinstance(progress, list) or
            (status == 'pass' and (not isinstance(result, dict) or failure is not None)) or
            (status == 'fail' and not isinstance(failure, dict))):
        raise ValueError('invalid fixed result envelope')
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot_id:
        raise ValueError('result boot identity changed')
    if Path('/proc/self/attr/current').read_text().strip('\0\n') != CONTEXT:
        raise ValueError('result writer is not the observed management service')
    for component in (Path('/var'), Path('/var/lib'), DIRECTORY):
        info = component.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0:
            raise ValueError('ordinary root-owned result directory required')
    if stat.S_IMODE(DIRECTORY.stat().st_mode) != 0o700:
        raise ValueError('result directory must retain private mode 0700')
    parent = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    descriptor = None
    try:
        descriptor = os.open(FILENAME, os.O_RDWR | os.O_CREAT | os.O_EXCL |
                             os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent)
        metadata = os.fstat(descriptor)
        if (not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or metadata.st_gid != 0 or
                stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1):
            raise ValueError('new ordinary result file metadata differs')
        label = os.getxattr(descriptor, 'security.selinux').decode().strip('\0\n')
        envelope = {
            'schema_version': 1, 'scope': 'generic ARM64 VM evidence; no physical device use',
            'phase': 'verify', 'status': status, 'boot_id': boot_id,
            'profile_sha256': profile_sha256, 'guest_path': GUEST_PATH,
            'writer_context': CONTEXT, 'writer_pid': os.getpid(),
            'file_metadata': {'uid': metadata.st_uid, 'gid': metadata.st_gid,
                              'mode': stat.S_IMODE(metadata.st_mode), 'nlink': metadata.st_nlink,
                              'inode_selinux_context': label},
            'result': result, 'progress': progress, 'failure': failure,
            'host_full_log_qualification_pending': True, 'complete_system_accepted': False,
            'physical_hardware_tested': False,
        }
        raw = (json.dumps(envelope, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()
        if not 0 < len(raw) <= MAX_BYTES:
            raise ValueError('complete result exceeds its explicit size bound')
        remaining = memoryview(raw)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError('result file write made no progress')
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        observed = bytearray()
        while block := os.read(descriptor, min(65536, MAX_BYTES + 1 - len(observed))):
            observed.extend(block)
            if len(observed) > MAX_BYTES:
                raise ValueError('result readback exceeded its bound')
        final = os.fstat(descriptor)
        if (bytes(observed) != raw or final.st_size != len(raw) or final.st_ino != metadata.st_ino or
                final.st_dev != metadata.st_dev or final.st_nlink != 1 or
                final.st_uid != 0 or final.st_gid != 0 or stat.S_IMODE(final.st_mode) != 0o600):
            raise ValueError('ordinary result readback or metadata differs')
        os.fsync(parent)
        digest = hashlib.sha256(raw).hexdigest()
        # All fields have a closed grammar and the complete receipt stays
        # below 300 bytes. Concurrent console corruption still fails closed.
        receipt = ('TB371FC_R4F_VM_FILE status=' + status + ' boot_id=' + boot_id +
                   ' profile_sha256=' + profile_sha256 + ' sha256=' + digest +
                   ' bytes=' + str(len(raw)) + ' END')
        if len(receipt.encode('ascii')) >= 300:
            raise ValueError('result receipt exceeds its fixed small bound')
        return receipt
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)
