#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Retain this VM's ordinary exported policy from its closed ext4 image.

Only debugfs's read-only dump command is used. No filesystem is mounted and no
kernel policy API is called. The guest-exported size/hash/version and complete
metadata must match the independently read image members before qualification.
"""
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess

from system_common import IMAGE, WORK, save


def retain_policy_export(controller):
    if not (controller.get('passed') is True and controller.get('qemu_exit_code') == 0 and
            controller.get('termination_reason') is None and controller.get('phase') == 'verify'):
        raise ValueError('the same owned production VM must have ended cleanly and passed')
    expected = controller['guest_result']['actual_loaded_policy_export']
    if not (expected.get('guest_path') == '/var/lib/tb371fc-r4e-proof/loaded-policy.33' and
            expected.get('version') == 33 and expected.get('mode') == 0o600 and
            type(expected.get('size')) is int and 1024 < expected['size'] <= 32 * 1024**2 and
            expected.get('sha256') == controller['guest_result']['loaded_policy_sha256'] and
            expected.get('boot_id') == controller['guest_result']['initrd_process_domains']['boot_id'] and
            expected.get('kernel_policy_written') is False):
        raise ValueError('actual same-boot ordinary policy export contract differs')
    if IMAGE.is_symlink() or not IMAGE.is_file():
        raise ValueError('ordinary private candidate image required')
    output = WORK / 'actual-policy-export'
    output.mkdir(mode=0o700)
    files = {}
    for name, limit in (('loaded-policy.33', 32 * 1024**2), ('loaded-policy-export.json', 8192)):
        destination = output / name
        if destination.exists() or destination.is_symlink():
            raise ValueError('fresh policy export destination required')
        source = '/var/lib/tb371fc-r4e-proof/' + name
        command = ['/usr/sbin/debugfs', '-R', 'dump -p ' + source + ' ' + str(destination), str(IMAGE)]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode or len(result.stdout) + len(result.stderr) > 16384:
            raise RuntimeError('bounded read-only image member extraction failed: ' + name)
        info = destination.lstat()
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError('ordinary bounded exported image member required: ' + name)
        raw = destination.read_bytes()
        files[name] = {'guest_path': source, 'host_path': str(destination), 'size': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest(), 'mode': stat.S_IMODE(info.st_mode),
                       'read_only_debugfs_exit_code': result.returncode}
        if name == 'loaded-policy.33':
            if not (len(raw) == expected['size'] and files[name]['sha256'] == expected['sha256'] and
                    struct.unpack_from('<II', raw) == (0xf97cff8c, 8) and raw[8:16] == b'SE Linux' and
                    struct.unpack_from('<I', raw, 16)[0] == 33 and
                    stat.S_IMODE(info.st_mode) == 0o600):
                raise ValueError('image policy bytes differ from the actual same-boot query input')
        elif json.loads(raw) != expected:
            raise ValueError('ordinary export metadata differs from the raw same-boot result')
    record = {'schema_version': 1, 'passed': True, 'image': str(IMAGE),
              'same_boot_export_record': expected, 'files': files,
              'loaded_policy_hash_predetermined': False, 'image_mounted': False,
              'image_opened_for_write': False, 'kernel_policy_loaded_or_written': False,
              'scope': 'read-only retention of a passed VM export; no extra VM or policy operation'}
    save('actual-policy-export.json', record)
    return record
