#!/usr/bin/python3
"""Read-only, in-memory compatibility check for the fixed Fedora 45 policy.

Run with the fixed Fedora ARM64 Python/libsepol, for example through the
project's PRoot/QEMU wrapper. This is not a policy loader or an installer.
It reads two explicitly pinned regular files, performs libsepol's binary
conversion entirely in memory, prints return codes and hashes, then frees the
temporary image. It never calls libselinux or a kernel SELinux interface.
"""
import sys

sys.dont_write_bytecode = True

import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import stat
import struct

POLICY = Path('/etc/selinux/targeted/policy/policy.35')
POLICY_BYTES = 3_835_432
POLICY_SHA256 = '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430'
LIBRARY = Path('/usr/lib64/libsepol.so.2')
LIBRARY_BYTES = 802_880
LIBRARY_SHA256 = '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b'
TARGET_VERSION = 33
OUTPUT_BYTES = 3_835_420
OUTPUT_SHA256 = 'aab7b7128bb8f0db2d349ac0817d806e5157b9a0b93dfe4f85ccf630354ebebe'


def read_pinned(path, expected_size, expected_hash):
    """Reject changed files, final symlinks and non-regular input nodes."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
            raise ValueError('input is not the pinned regular file: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(expected_size + 1)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size,
                                       after.st_mtime_ns, after.st_ctime_ns):
            raise ValueError('input changed while reading: ' + str(path))
    finally:
        os.close(fd)
    if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError('input hash differs from the fixed experiment: ' + str(path))
    return data


def binary_version(data):
    if len(data) < 20:
        raise ValueError('truncated binary policy')
    magic, name_len = struct.unpack_from('<II', data)
    if magic != 0xF97CFF8C or name_len != 8 or data[8:16] != b'SE Linux':
        raise ValueError('unexpected SELinux binary policy header')
    return struct.unpack_from('<I', data, 16)[0]


def check():
    result = {
        'schema_version': 1,
        'scope': 'fixed Fedora ARM64 libsepol; binary conversion in memory only',
        'policy_path': str(POLICY),
        'library_path': str(LIBRARY),
        'target_version': TARGET_VERSION,
        'output_written': False,
        'kernel_load_attempted': False,
        'live_selinux_configuration_changed': False,
        'rootfs_written_by_probe': False,
        'hardware_tested': False,
        'passed': False,
        'return_codes': {},
    }
    db = c.c_void_p()
    out = c.c_void_p()
    lib = None
    output_owned = False
    try:
        policy = read_pinned(POLICY, POLICY_BYTES, POLICY_SHA256)
        library = read_pinned(LIBRARY, LIBRARY_BYTES, LIBRARY_SHA256)
        result.update({
            'input_bytes': len(policy),
            'input_sha256': hashlib.sha256(policy).hexdigest(),
            'input_policy_version': binary_version(policy),
            'library_bytes': len(library),
            'library_sha256': hashlib.sha256(library).hexdigest(),
        })
        if result['input_policy_version'] != 35:
            raise ValueError('input is not the expected version 35 policy')
        lib = c.CDLL(str(LIBRARY))
        lib.sepol_policy_kern_vers_min.restype = c.c_int
        lib.sepol_policy_kern_vers_max.restype = c.c_int
        lib.sepol_policydb_create.argtypes = [c.POINTER(c.c_void_p)]
        lib.sepol_policydb_create.restype = c.c_int
        lib.sepol_policydb_free.argtypes = [c.c_void_p]
        lib.sepol_policydb_free.restype = None
        lib.sepol_policydb_from_image.argtypes = [c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p]
        lib.sepol_policydb_from_image.restype = c.c_int
        lib.sepol_policydb_set_vers.argtypes = [c.c_void_p, c.c_uint]
        lib.sepol_policydb_set_vers.restype = c.c_int
        lib.sepol_policydb_to_image.argtypes = [c.c_void_p, c.c_void_p,
                                               c.POINTER(c.c_void_p), c.POINTER(c.c_size_t)]
        lib.sepol_policydb_to_image.restype = c.c_int
        result['library_min_version'] = lib.sepol_policy_kern_vers_min()
        result['library_max_version'] = lib.sepol_policy_kern_vers_max()
        if not result['library_min_version'] <= TARGET_VERSION <= result['library_max_version']:
            raise ValueError('target version is outside this library range')

        def require_zero(name, value):
            result['return_codes'][name] = value
            if value != 0:
                raise ValueError(name + ' failed; policy was not loaded or written')

        require_zero('create', lib.sepol_policydb_create(c.byref(db)))
        source = c.create_string_buffer(policy)
        require_zero('from_image', lib.sepol_policydb_from_image(
            None, c.cast(source, c.c_void_p), len(policy), db))
        require_zero('set_version', lib.sepol_policydb_set_vers(db, TARGET_VERSION))
        size = c.c_size_t()
        require_zero('to_image', lib.sepol_policydb_to_image(None, db, c.byref(out), c.byref(size)))
        output_owned = True
        if not out or size.value != OUTPUT_BYTES:
            raise ValueError('converted size differs from the fixed observation')
        converted = c.string_at(out, size.value)
        result.update({
            'output_bytes': len(converted),
            'output_sha256': hashlib.sha256(converted).hexdigest(),
            'output_policy_version': binary_version(converted),
        })
        if result['output_policy_version'] != TARGET_VERSION or result['output_sha256'] != OUTPUT_SHA256:
            raise ValueError('converted bytes differ from the fixed observation')
        # Detect accidental replacement of either controlled build input during
        # the check. The probe itself has opened neither input for writing.
        read_pinned(POLICY, POLICY_BYTES, POLICY_SHA256)
        read_pinned(LIBRARY, LIBRARY_BYTES, LIBRARY_SHA256)
        result['inputs_unchanged_after_check'] = True
        result['passed'] = True
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if output_owned and out:
            libc = c.CDLL('libc.so.6')
            libc.free.argtypes = [c.c_void_p]
            libc.free.restype = None
            libc.free(out)
        if lib is not None and db:
            lib.sepol_policydb_free(db)
    return result


if __name__ == '__main__':
    outcome = check()
    print(json.dumps(outcome, indent=2, sort_keys=True), flush=True)
    raise SystemExit(0 if outcome['passed'] else 1)
