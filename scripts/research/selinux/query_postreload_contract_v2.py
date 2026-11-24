#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""V2 offline AV query for the independent map-and-self-transition candidate.

Derived from frozen c2e9f490f44202130271fec12626573d7608be39ca7d04c9ee1bc7d60acbe8aa;
the original map-only source and 53-row result remain unchanged.

Only the exact candidate35 file is accepted. It is converted to version33 in
process memory and queried with the fixed AArch64 libsepol public ABI. The
result is not an observation of loaded kernel policy or actual device labels.
No libselinux call, kernel load, boolean update, PRoot, subprocess or mount is
performed. ABI source: SELinux Project commit
2233a23a4d4f1bf29054037babec13f30d038e65.
"""

import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import platform
import stat
import struct
import sys


STOCK = (3835432, 'e1a63e7e6a97122f207b2df5a28d863fb29852530aa59c0c8d3dd8eefba36269')
CONVERTED_SIZE = 3835420
LIBRARY = (802880, '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b')
INIT = 'system_u:system_r:init_t:s0'


class AVDecision(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in
                ('allowed', 'decided', 'auditallow', 'auditdeny', 'seqno')]


def identity(data):
    return len(data), hashlib.sha256(data).hexdigest()


def fixed_file(path, permitted):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 32 * 1024**2:
        raise ValueError('bounded ordinary input file required: ' + str(path))
    data = path.read_bytes()
    if identity(data) not in permitted:
        raise ValueError('input is not a fixed qualified file: ' + str(path))
    return data


def context(type_name):
    return 'system_u:system_r:' + type_name + ':s0'


def object_context(type_name):
    return 'system_u:object_r:' + type_name + ':s0'


def query_rows():
    rows = []

    def add(group, source, target, cls, names):
        rows.extend((group, source, target, cls, name) for name in names)

    add('init_same_domain_setcon', INIT, INIT, 'process', ('setcurrent', 'dyntransition'))
    add('device_source', INIT, object_context('device_t'), 'chr_file', ('getattr', 'relabelfrom'))
    for target in ('null_device_t', 'kmsg_device_t'):
        add('device_target', INIT, object_context(target), 'chr_file', ('getattr', 'relabelto'))
        add('device_associate', object_context(target), object_context('device_t'), 'filesystem', ('associate',))
    for source in ('tmpfs_t', 'syslogd_tmpfs_t'):
        add('run_source_directory', INIT, object_context(source), 'dir', ('getattr', 'search', 'relabelfrom'))
        add('run_source_file', INIT, object_context(source), 'file', ('getattr', 'relabelfrom'))
    for target in ('var_run_t', 'syslogd_var_run_t', 'tmpfs_t'):
        add('run_target_directory', INIT, object_context(target), 'dir', ('getattr', 'search', 'relabelto'))
        add('run_associate', object_context(target), object_context('tmpfs_t'), 'filesystem', ('associate',))
    add('journal_target_file', INIT, object_context('syslogd_var_run_t'), 'file', ('getattr', 'relabelto'))
    logger = context('syslogd_t')
    add('journal_file_access', logger, object_context('syslogd_var_run_t'), 'file',
        ('create', 'open', 'read', 'write', 'append', 'getattr', 'map'))
    add('journal_directory_access', logger, object_context('syslogd_var_run_t'), 'dir',
        ('search', 'add_name', 'write', 'open', 'read', 'getattr'))
    add('old_journal_label_diagnostic', logger, object_context('syslogd_tmpfs_t'), 'file', ('map',))
    add('candidate_policy_file', INIT, object_context('semanage_store_t'), 'file', ('read', 'open', 'getattr', 'map'))
    add('candidate_policy_load', INIT, object_context('security_t'), 'security', ('load_policy',))
    add('manager_export_denial_control', INIT, object_context('security_t'), 'security', ('read_policy',))
    return rows


def probe(policy_bytes, library_path):
    out = {
        'schema_version': 1,
        'scope': 'offline candidate AV contracts; no runtime execution proof',
        'completed': False,
        'kernel_policy_loaded_or_written': False,
        'booleans_changed': False,
        'proot_used': False,
        'sids_are_process_private': True,
        'policy_semantic_equivalence_to_other_hash_asserted': False,
        'actual_runtime_enforcement_proven_by_query': False,
        'input_policy': dict(zip(('size', 'sha256'), identity(policy_bytes))),
        'library': {'path': str(library_path), 'size': LIBRARY[0], 'sha256': LIBRARY[1]},
        'return_codes': {},
        'contexts': {},
        'queries': [],
    }
    libc = None
    lib = None
    db = c.c_void_p()
    serialized = c.c_void_p()
    memory_file = None
    try:
        if (platform.machine() != 'aarch64' or c.sizeof(c.c_void_p) != 8 or
                c.sizeof(AVDecision) != 20):
            raise ValueError('qualified AArch64 ABI required')
        supplied = identity(policy_bytes)
        if supplied != STOCK:
            raise ValueError('exact independently qualified candidate35 policy required')
        if (struct.unpack_from('<II', policy_bytes) != (0xf97cff8c, 8) or
                policy_bytes[8:16] != b'SE Linux'):
            raise ValueError('unexpected binary policy header')
        version = struct.unpack_from('<I', policy_bytes, 16)[0]
        if version != 35:
            raise ValueError('policy version does not match its identity')
        library_bytes = fixed_file(library_path, (LIBRARY,))
        if (library_bytes[:6] != b'\x7fELF\x02\x01' or
                int.from_bytes(library_bytes[18:20], 'little') != 183):
            raise ValueError('fixed libsepol must be ELF64 AArch64')
        lib = c.CDLL(str(library_path))
        signatures = {
            'sepol_policydb_create': ([c.POINTER(c.c_void_p)], c.c_int),
            'sepol_policydb_free': ([c.c_void_p], None),
            'sepol_policydb_from_image': ([c.c_void_p, c.c_void_p, c.c_size_t, c.c_void_p], c.c_int),
            'sepol_policydb_set_vers': ([c.c_void_p, c.c_uint], c.c_int),
            'sepol_policydb_to_image': ([c.c_void_p, c.c_void_p, c.POINTER(c.c_void_p),
                                       c.POINTER(c.c_size_t)], c.c_int),
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
        libc.fmemopen.argtypes, libc.fmemopen.restype = [c.c_void_p, c.c_size_t, c.c_char_p], c.c_void_p
        libc.fclose.argtypes, libc.fclose.restype = [c.c_void_p], c.c_int
        libc.free.argtypes, libc.free.restype = [c.c_void_p], None

        def zero(name, value):
            out['return_codes'][name] = value
            if value != 0:
                raise ValueError(name + ' returned ' + str(value))

        input_buffer = c.create_string_buffer(policy_bytes, len(policy_bytes))
        if supplied == STOCK:
            out['policy_provenance'] = 'independent fixed map-and-self-transition candidate35 converted to33 in userspace; offline only'
            out['policy_version_converted'] = True
            zero('policydb_create', lib.sepol_policydb_create(c.byref(db)))
            zero('policydb_from_image', lib.sepol_policydb_from_image(None, input_buffer, len(policy_bytes), db))
            zero('policydb_set_vers33', lib.sepol_policydb_set_vers(db, 33))
            size = c.c_size_t()
            zero('policydb_to_image', lib.sepol_policydb_to_image(None, db, c.byref(serialized), c.byref(size)))
            if not serialized or size.value != CONVERTED_SIZE:
                raise ValueError('converted policy has unexpected allocation or size')
            queried = c.string_at(serialized, size.value)
            if (len(queried) != CONVERTED_SIZE or struct.unpack_from('<I', queried, 16)[0] != 33):
                raise ValueError('converted candidate has an unexpected length or version')
        out['queried_policy'] = dict(zip(('size', 'sha256'), identity(queried)))
        buffer = c.create_string_buffer(queried, len(queried))
        c.set_errno(0)
        memory_file = libc.fmemopen(buffer, len(queried), b'rb')
        if not memory_file:
            raise OSError(c.get_errno(), 'fmemopen failed')
        zero('private_policydb_from_file', lib.sepol_set_policydb_from_file(memory_file))
        closed = libc.fclose(memory_file)
        memory_file = None
        zero('fclose', closed)

        # sepol_context_to_sid validates the supplied user/role/type/MLS tuple.
        # A private SID is not a live kernel SID or proof of a process transition.
        sids = {}

        def sid(value):
            if value not in sids:
                encoded = value.encode('ascii')
                answer = c.c_uint32()
                ret = lib.sepol_context_to_sid(encoded, len(encoded), c.byref(answer))
                out['contexts'][value] = {'return_code': ret, 'accepted_by_policy': ret == 0,
                                          'private_sid': answer.value if ret == 0 else None}
                if ret != 0:
                    raise ValueError('context is not valid in this policy: ' + value)
                sids[value] = answer.value
            return sids[value]

        rows = query_rows()
        for group, source, target, class_name, permission_name in rows:
            class_id, permission = c.c_uint16(), c.c_uint32()
            zero('class:' + class_name,
                 lib.sepol_string_to_security_class(class_name.encode(), c.byref(class_id)))
            zero('permission:' + class_name + ':' + permission_name,
                 lib.sepol_string_to_av_perm(class_id, permission_name.encode(), c.byref(permission)))
            if not permission.value or permission.value & (permission.value - 1):
                raise ValueError('permission lookup is not a single bit')
            decision, reason = AVDecision(), c.c_uint()
            ret = lib.sepol_compute_av_reason(sid(source), sid(target), class_id, permission,
                                              c.byref(decision), c.byref(reason))
            out['queries'].append({
                'group': group, 'source_context': source, 'target_context': target,
                'class': class_name, 'permission': permission_name,
                'return_code': ret,
                'permission_allowed': bool(decision.allowed & permission.value) if ret == 0 else None,
                'denial_audit_mask_includes_permission': bool(decision.auditdeny & permission.value) if ret == 0 else None,
                'reason_mask': reason.value, 'requested_mask': permission.value,
                'raw_decision': {field: getattr(decision, field) for field, _ in AVDecision._fields_},
            })
            if ret != 0:
                raise ValueError('AV computation error is not a permission denial')

        out['required_denials'] = [row for row in out['queries']
            if row['group'] not in ('old_journal_label_diagnostic', 'manager_export_denial_control') and not row['permission_allowed']]
        out['diagnostic_rows'] = [row for row in out['queries']
            if row['group'] in ('old_journal_label_diagnostic', 'manager_export_denial_control')]
        out['retained_controls_denied'] = len(out['diagnostic_rows']) == 2 and all(
            row['permission_allowed'] is False for row in out['diagnostic_rows'])
        out['all_queried_required_permissions_allowed'] = not out['required_denials']
        out['candidate_permission_contract_complete'] = (
            out['all_queried_required_permissions_allowed'] and out['retained_controls_denied'])
        out['query_count'] = len(out['queries'])
        out['expected_query_count'] = len(rows)
        if fixed_file(library_path, (LIBRARY,)) != library_bytes:
            raise ValueError('library changed during query')
        out['completed'] = len(out['queries']) == len(rows)
    except Exception as error:
        out['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if libc is not None and memory_file:
            libc.fclose(memory_file)
        if libc is not None and serialized:
            libc.free(serialized)
        if lib is not None and db:
            lib.sepol_policydb_free(db)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = fixed_file(args.policy, (STOCK,))
        result = probe(data, args.library)
    except Exception as error:
        result = {'completed': False, 'error': {'type': type(error).__name__, 'message': str(error)}}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('completed') is True else 1


if __name__ == '__main__':
    sys.exit(main())
