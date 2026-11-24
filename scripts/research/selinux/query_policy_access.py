#!/usr/bin/python3
"""Query fixed Fedora policy AVs in libsepol memory, never in the kernel.

Run with the qualified Fedora ARM64 Python/libsepol under PRoot/QEMU. This
bounded diagnostic reads the frozen policy, converts a temporary copy to
version 33, and queries the library's private policydb through public APIs.
It does not import libselinux, write a policy, query live process state, or
change SELinux configuration. An AV result is not a syscall failure diagnosis.
"""
import sys

sys.dont_write_bytecode = True

import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import stat

COMPATIBILITY_BYTES = 7054
COMPATIBILITY_SHA256 = '6c3c9d4e75c9da1d30c977ae7d99be4dcb57ebb0bb68d247e9ec12a3d870bf6d'
SOURCE_COMMIT = '2233a23a4d4f1bf29054037babec13f30d038e65'
SOURCE_CONTEXTS = (
    'system_u:system_r:system_dbusd_t:s0',
    'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023',
)
DOMAIN_CANDIDATES = ('unconfined_service_t', 'init_t', 'initrc_t')
PERMISSIONS = (
    ('fd', 'use'),
    ('fifo_file', 'read'),
    ('fifo_file', 'write'),
    ('fifo_file', 'append'),
    ('fifo_file', 'getattr'),
    ('fifo_file', 'ioctl'),
)
REASONS = {1: 'type_enforcement', 2: 'constraint', 4: 'role', 8: 'type_bounds'}


class AVDecision(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in
                ('allowed', 'decided', 'auditallow', 'auditdeny', 'seqno')]


def fixed_compatibility_helper(path):
    """Execute already qualified, hash-pinned definitions without its main."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size != COMPATIBILITY_BYTES:
            raise ValueError('unexpected compatibility helper type or length')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(COMPATIBILITY_BYTES + 1)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after):
            raise ValueError('compatibility helper changed while reading')
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != COMPATIBILITY_SHA256:
        raise ValueError('compatibility helper hash differs from frozen input')
    scope = {'__name__': '__fixed_selinux_compatibility__', '__file__': str(path)}
    exec(compile(data, str(path), 'exec'), scope)
    return scope


def query(compatibility_path):
    outcome = {
        'schema_version': 1,
        'scope': 'fixed policy AV computation in private libsepol userspace memory',
        'upstream_abi_commit': SOURCE_COMMIT,
        'compatibility_helper_sha256': COMPATIBILITY_SHA256,
        'kernel_policy_load_attempted': False,
        'live_selinux_configuration_changed': False,
        'live_booleans_read': False,
        'policy_image_written': False,
        'rootfs_written_by_probe': False,
        'hardware_tested': False,
        'cause_of_broker_reset_proven': False,
        'query_completed': False,
        'return_codes': {},
        'context_to_sid': [],
        'queries': [],
        'interpretation': {
            'sids': 'local to this libsepol process; not live kernel SIDs',
            'fd_target': 'candidate opener SID, distinct from inode security label',
            'fifo_target': 'inode context supplied explicitly; no descriptor state inferred',
            'booleans': 'serialized input policy defaults; no live state substituted',
            'auditdeny': 'audit mask is separate from allowed; dontaudit alone is not a denial',
            'enforcement': 'permission vector only; no live permissive or Enforcing decision asserted',
        },
    }
    db = c.c_void_p()
    serialized = c.c_void_p()
    memory_file = c.c_void_p()
    lib = libc = None
    try:
        fixed = fixed_compatibility_helper(compatibility_path)
        read_pinned = fixed['read_pinned']
        binary_version = fixed['binary_version']
        policy = read_pinned(fixed['POLICY'], fixed['POLICY_BYTES'], fixed['POLICY_SHA256'])
        library = read_pinned(fixed['LIBRARY'], fixed['LIBRARY_BYTES'], fixed['LIBRARY_SHA256'])
        outcome['input_policy'] = {
            'path': str(fixed['POLICY']), 'bytes': len(policy),
            'sha256': hashlib.sha256(policy).hexdigest(), 'version': binary_version(policy),
        }
        outcome['library'] = {
            'path': str(fixed['LIBRARY']), 'bytes': len(library),
            'sha256': hashlib.sha256(library).hexdigest(),
        }
        if binary_version(policy) != 35 or c.sizeof(AVDecision) != 20:
            raise ValueError('unexpected policy version or public AV ABI')
        lib = c.CDLL(str(fixed['LIBRARY']))
        signatures = {
            'sepol_policydb_create': ([c.POINTER(c.c_void_p)], c.c_int),
            'sepol_policydb_free': ([c.c_void_p], None),
            'sepol_policydb_from_image': ([c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p], c.c_int),
            'sepol_policydb_set_vers': ([c.c_void_p, c.c_uint], c.c_int),
            'sepol_policydb_to_image': ([c.c_void_p, c.c_void_p, c.POINTER(c.c_void_p), c.POINTER(c.c_size_t)], c.c_int),
            'sepol_set_policydb_from_file': ([c.c_void_p], c.c_int),
            'sepol_context_to_sid': ([c.c_char_p, c.c_size_t, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_string_to_security_class': ([c.c_char_p, c.POINTER(c.c_uint16)], c.c_int),
            'sepol_string_to_av_perm': ([c.c_uint16, c.c_char_p, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_compute_av_reason': ([c.c_uint32, c.c_uint32, c.c_uint16, c.c_uint32,
                                         c.POINTER(AVDecision), c.POINTER(c.c_uint)], c.c_int),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(lib, name)
            fn.argtypes, fn.restype = args, result
        libc = c.CDLL('libc.so.6', use_errno=True)
        libc.fmemopen.argtypes = [c.c_void_p, c.c_size_t, c.c_char_p]
        libc.fmemopen.restype = c.c_void_p
        libc.fclose.argtypes, libc.fclose.restype = [c.c_void_p], c.c_int
        libc.free.argtypes, libc.free.restype = [c.c_void_p], None

        def zero(name, value):
            outcome['return_codes'][name] = value
            if value != 0:
                raise ValueError(name + ' returned ' + str(value))

        zero('create', lib.sepol_policydb_create(c.byref(db)))
        original = c.create_string_buffer(policy)
        zero('from_image', lib.sepol_policydb_from_image(None, original, len(policy), db))
        zero('set_version_33', lib.sepol_policydb_set_vers(db, fixed['TARGET_VERSION']))
        size = c.c_size_t()
        zero('to_image', lib.sepol_policydb_to_image(None, db, c.byref(serialized), c.byref(size)))
        if not serialized or size.value != fixed['OUTPUT_BYTES']:
            raise ValueError('unexpected converted policy size')
        converted = c.string_at(serialized, size.value)
        converted_hash = hashlib.sha256(converted).hexdigest()
        if converted_hash != fixed['OUTPUT_SHA256'] or binary_version(converted) != 33:
            raise ValueError('converted policy differs from frozen compatibility result')
        outcome['converted_policy'] = {
            'bytes': len(converted), 'sha256': converted_hash, 'version': 33,
        }
        # This exported libsepol API reads a FILE into its own policydb/sidtab.
        # fmemopen supplies only the temporary memory buffer, not a disk file.
        c.set_errno(0)
        memory_file = c.c_void_p(libc.fmemopen(serialized, size.value, b'rb'))
        outcome['fmemopen'] = {'succeeded': bool(memory_file), 'errno': c.get_errno()}
        if not memory_file:
            raise ValueError('fmemopen failed')
        zero('userspace_policydb_from_memory_file', lib.sepol_set_policydb_from_file(memory_file))
        close_result = libc.fclose(memory_file)
        memory_file = c.c_void_p()
        zero('fclose_memory_file', close_result)

        sids, classes, bits = {}, {}, {}

        def sid(context):
            if context not in sids:
                value = c.c_uint32()
                encoded = context.encode('ascii')
                # Official context_from_string copies this exact byte count and
                # appends its own NUL (libsepol/src/context.c:289-297).
                ret = lib.sepol_context_to_sid(encoded, len(encoded), c.byref(value))
                outcome['context_to_sid'].append({'context': context, 'return_code': ret,
                                                  'process_local_sid': value.value})
                if ret != 0:
                    raise ValueError('context_to_sid rejected ' + context)
                sids[context] = value.value
            return sids[context]

        def permission(class_name, perm_name):
            if class_name not in classes:
                value = c.c_uint16()
                zero('class:' + class_name, lib.sepol_string_to_security_class(
                    class_name.encode('ascii'), c.byref(value)))
                classes[class_name] = value.value
            key = (class_name, perm_name)
            if key not in bits:
                value = c.c_uint32()
                zero('permission:' + class_name + ':' + perm_name, lib.sepol_string_to_av_perm(
                    classes[class_name], perm_name.encode('ascii'), c.byref(value)))
                if not value.value or value.value & (value.value - 1):
                    raise ValueError('permission lookup did not produce one AV bit')
                bits[key] = value.value
            return classes[class_name], bits[key]

        targets = []
        for domain in DOMAIN_CANDIDATES:
            for class_name, perm_name in PERMISSIONS:
                targets.append(('system_u:system_r:' + domain + ':s0', class_name, perm_name))
        targets.append(('system_u:system_r:kernel_t:s0', 'fd', 'use'))
        for perm_name in ('read', 'write', 'ioctl'):
            targets.append(('system_u:object_r:null_device_t:s0', 'chr_file', perm_name))
        for source_context in SOURCE_CONTEXTS:
            source_sid = sid(source_context)
            for target_context, class_name, perm_name in targets:
                target_sid = sid(target_context)
                class_id, requested = permission(class_name, perm_name)
                decision, reason = AVDecision(), c.c_uint()
                ret = lib.sepol_compute_av_reason(source_sid, target_sid, class_id, requested,
                                                  c.byref(decision), c.byref(reason))
                outcome['queries'].append({
                    'source_context': source_context, 'target_context': target_context,
                    'class': class_name, 'class_id': class_id, 'permission': perm_name,
                    'requested_mask': '0x%08x' % requested, 'return_code': ret,
                    'permission_allowed': bool(decision.allowed & requested) if ret == 0 else None,
                    'denial_audit_mask_includes_permission': bool(decision.auditdeny & requested) if ret == 0 else None,
                    'raw_decision': {name: '0x%08x' % getattr(decision, name)
                                     for name, _ in AVDecision._fields_},
                    'reason_mask': reason.value,
                    'reasons': [label for bit, label in REASONS.items() if reason.value & bit],
                })
                if ret != 0:
                    raise ValueError('AV computation failed; not a permission denial result')
        read_pinned(fixed['POLICY'], fixed['POLICY_BYTES'], fixed['POLICY_SHA256'])
        read_pinned(fixed['LIBRARY'], fixed['LIBRARY_BYTES'], fixed['LIBRARY_SHA256'])
        outcome['inputs_unchanged_after_query'] = True
        outcome['query_count'] = len(outcome['queries'])
        outcome['permission_denial_count'] = sum(not r['permission_allowed'] for r in outcome['queries'])
        outcome['query_completed'] = len(outcome['queries']) == 44
    except Exception as error:
        outcome['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        if libc is not None and memory_file:
            libc.fclose(memory_file)
        if libc is not None and serialized:
            libc.free(serialized)
        if lib is not None and db:
            lib.sepol_policydb_free(db)
    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compatibility-helper', type=Path,
                        default=Path('/analysis/verify_selinux_compatibility.py'))
    args = parser.parse_args()
    result = query(args.compatibility_helper)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    raise SystemExit(0 if result['query_completed'] else 1)
