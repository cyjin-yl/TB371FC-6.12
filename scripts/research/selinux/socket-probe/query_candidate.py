#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Qualify the new socket-probe candidate in private libsepol memory.

Derived from the retained-V8 19-row query fb51735ec147fee035c0fe091d6f3172fdef0b5c1290d0fab072457c444837ec.
The input is the separately recorded fresh version-33 serialization produced by
our complete CIL comparison, identified by explicit required size/SHA arguments.
It is not kernel-exported policy. No conversion, policy load, boolean write,
rootfs operation or VM is implemented. Exit zero requires the seven reviewed
permissions to allow and all twelve negative controls to remain denied. This
qualifies an offline candidate, not a runtime call stack or hardware behavior.
"""

import argparse
import ctypes as c
import hashlib
import json
from pathlib import Path
import platform
import re
import stat
import struct
import sys


LIBRARY = (802880, '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b')


class AVDecision(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in
                ('allowed', 'decided', 'auditallow', 'auditdeny', 'seqno')]


def identity(data):
    return len(data), hashlib.sha256(data).hexdigest()


def fixed_file(path, expected):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size != expected[0]:
        raise ValueError('exact ordinary input required: ' + str(path))
    data = path.read_bytes()
    if identity(data) != expected:
        raise ValueError('fixed input identity differs: ' + str(path))
    return data


def subject(type_name):
    return 'system_u:system_r:' + type_name + ':s0'


def object_context(type_name):
    return 'system_u:object_r:' + type_name + ':s0'


def query_rows():
    rows = []

    def add(group, source, target, klass, permissions):
        rows.extend((group, source, target, klass, permission) for permission in permissions)

    client = subject('journalctl_t')
    manager = subject('init_t')
    add('required_socket_probe_create', client, client, 'unix_dgram_socket', ('create',))
    add('socket_xattr_diagnostic', client, client, 'unix_dgram_socket', ('getattr', 'setattr'))
    add('unrelated_socket_diagnostic', client, client, 'unix_dgram_socket',
        ('connect', 'bind', 'read', 'write', 'getopt', 'setopt'))
    add('unrelated_capability_diagnostic', client, client, 'capability', ('net_admin',))
    add('prior_required', manager, manager, 'process', ('setcurrent', 'dyntransition'))
    add('prior_required', manager, object_context('semanage_store_t'), 'file', ('map',))
    add('prior_required', manager, object_context('systemd_varlink_registry_t'), 'lnk_file', ('unlink',))
    add('prior_required', client, object_context('syslogd_var_run_t'), 'sock_file', ('write',))
    add('prior_required', client, subject('syslogd_t'), 'unix_stream_socket', ('connectto',))
    add('retained_denial_control', manager, object_context('security_t'), 'security', ('read_policy',))
    add('retained_denial_control', subject('syslogd_t'), object_context('syslogd_tmpfs_t'), 'file', ('map',))
    add('retained_denial_control', 'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023',
        subject('unconfined_service_t'), 'fifo_file', ('write',))
    if len(rows) != 19 or len(set(rows)) != len(rows):
        raise ValueError('fixed unique query matrix changed')
    return rows


def probe(policy_bytes, library_path, expected_policy):
    out = {
        'schema_version': 1,
        'scope': 'offline AV qualification on an explicitly pinned fresh candidate version-33 serialization',
        'completed': False,
        'kernel_policy_loaded_or_written': False,
        'policy_version_converted': False,
        'booleans_changed': False,
        'proot_used': False,
        'vm_started': False,
        'sids_are_process_private': True,
        'runtime_call_stack_proven_by_query': False,
        'repair_performed': False,
        'kernel_export_identity_asserted': False,
        'input_policy': dict(zip(('size', 'sha256'), identity(policy_bytes))),
        'library': {'path': str(library_path), 'size': LIBRARY[0], 'sha256': LIBRARY[1]},
        'return_codes': {},
        'contexts': {},
        'queries': [],
    }
    libc = None
    memory_file = None
    try:
        if (platform.machine() != 'aarch64' or c.sizeof(c.c_void_p) != 8 or
                c.sizeof(AVDecision) != 20):
            raise ValueError('qualified AArch64 ABI required')
        if identity(policy_bytes) != expected_policy:
            raise ValueError('exact explicitly pinned candidate policy required')
        if (struct.unpack_from('<II', policy_bytes) != (0xf97cff8c, 8) or
                policy_bytes[8:16] != b'SE Linux' or
                struct.unpack_from('<I', policy_bytes, 16)[0] != 33):
            raise ValueError('unexpected binary-policy header/version')
        library_bytes = fixed_file(library_path, LIBRARY)
        if (library_bytes[:6] != b'\x7fELF\x02\x01' or
                int.from_bytes(library_bytes[18:20], 'little') != 183):
            raise ValueError('fixed libsepol must be ELF64 AArch64')
        lib = c.CDLL(str(library_path))
        signatures = {
            'sepol_set_policydb_from_file': ([c.c_void_p], c.c_int),
            'sepol_context_to_sid': ([c.c_char_p, c.c_size_t, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_string_to_security_class': ([c.c_char_p, c.POINTER(c.c_uint16)], c.c_int),
            'sepol_string_to_av_perm': ([c.c_uint16, c.c_char_p, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_compute_av_reason': ([c.c_uint32, c.c_uint32, c.c_uint16, c.c_uint32,
                                         c.POINTER(AVDecision), c.POINTER(c.c_uint)], c.c_int),
        }
        for name, (args, result) in signatures.items():
            function = getattr(lib, name)
            function.argtypes, function.restype = args, result
        libc = c.CDLL('libc.so.6', use_errno=True)
        libc.fmemopen.argtypes, libc.fmemopen.restype = [c.c_void_p, c.c_size_t, c.c_char_p], c.c_void_p
        libc.fclose.argtypes, libc.fclose.restype = [c.c_void_p], c.c_int

        def zero(name, result):
            out['return_codes'][name] = result
            if result != 0:
                raise ValueError(name + ' returned ' + str(result))

        buffer = c.create_string_buffer(policy_bytes, len(policy_bytes))
        c.set_errno(0)
        memory_file = libc.fmemopen(buffer, len(policy_bytes), b'rb')
        if not memory_file:
            raise OSError(c.get_errno(), 'fmemopen failed')
        zero('private_policydb_from_file', lib.sepol_set_policydb_from_file(memory_file))
        close_result = libc.fclose(memory_file)
        memory_file = None
        zero('fclose', close_result)

        sids = {}

        def sid(value):
            if value not in sids:
                encoded, answer = value.encode('ascii'), c.c_uint32()
                result = lib.sepol_context_to_sid(encoded, len(encoded), c.byref(answer))
                out['contexts'][value] = {'return_code': result, 'accepted_by_policy': result == 0,
                                          'private_sid': answer.value if result == 0 else None}
                if result != 0:
                    raise ValueError('context is invalid in fixed policy: ' + value)
                sids[value] = answer.value
            return sids[value]

        rows = query_rows()
        for group, source, target, klass, permission_name in rows:
            class_id, permission = c.c_uint16(), c.c_uint32()
            zero('class:' + klass,
                 lib.sepol_string_to_security_class(klass.encode(), c.byref(class_id)))
            zero('permission:' + klass + ':' + permission_name,
                 lib.sepol_string_to_av_perm(class_id, permission_name.encode(), c.byref(permission)))
            if not permission.value or permission.value & (permission.value - 1):
                raise ValueError('permission lookup must yield one bit')
            decision, reason = AVDecision(), c.c_uint()
            result = lib.sepol_compute_av_reason(sid(source), sid(target), class_id, permission,
                                                  c.byref(decision), c.byref(reason))
            out['queries'].append({
                'group': group, 'source_context': source, 'target_context': target,
                'class': klass, 'permission': permission_name, 'return_code': result,
                'permission_allowed': bool(decision.allowed & permission.value) if result == 0 else None,
                'denial_audit_mask_includes_permission': bool(decision.auditdeny & permission.value) if result == 0 else None,
                'requested_mask': permission.value, 'reason_mask': reason.value,
                'raw_decision': {field: getattr(decision, field) for field, _ in AVDecision._fields_},
            })
            if result != 0:
                raise ValueError('AV computation error is not a permission denial')

        out['query_count'] = len(out['queries'])
        out['allowed_count'] = sum(row['permission_allowed'] is True for row in out['queries'])
        out['denied_count'] = sum(row['permission_allowed'] is False for row in out['queries'])
        out['prior_required_allowed'] = all(row['permission_allowed'] is True for row in out['queries']
                                            if row['group'] == 'prior_required')
        out['controls_denied'] = all(row['permission_allowed'] is False for row in out['queries']
                                    if row['group'] == 'retained_denial_control')
        out['required_socket_create_allowed'] = all(row['permission_allowed'] is True for row in out['queries']
                                                    if row['group'] == 'required_socket_probe_create')
        out['unrequested_permissions_remain_denied'] = all(
            row['permission_allowed'] is False for row in out['queries']
            if row['group'] in ('socket_xattr_diagnostic', 'unrelated_socket_diagnostic',
                                'unrelated_capability_diagnostic'))
        out['all_candidate_contracts_satisfied'] = (
            out['prior_required_allowed'] and out['controls_denied'] and
            out['required_socket_create_allowed'] and out['unrequested_permissions_remain_denied'])
        if fixed_file(library_path, LIBRARY) != library_bytes:
            raise ValueError('library changed during query')
        out['completed'] = len(out['queries']) == 19
    except Exception as error:
        out['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if libc is not None and memory_file:
            libc.fclose(memory_file)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', type=Path, required=True)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--policy-size', type=int, required=True)
    parser.add_argument('--policy-sha256', required=True)
    args = parser.parse_args()
    if not 0 < args.policy_size < 32 * 1024**2 or not re.fullmatch('[0-9a-f]{64}', args.policy_sha256):
        parser.error('bounded policy size and exact SHA256 are required')
    expected_policy = (args.policy_size, args.policy_sha256)
    try:
        data = fixed_file(args.policy, expected_policy)
        result = probe(data, args.library, expected_policy)
    except Exception as error:
        result = {'completed': False, 'error': {'type': type(error).__name__, 'message': str(error)}}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if (result.get('completed') is True and
                 result.get('all_candidate_contracts_satisfied') is True) else 1


if __name__ == '__main__':
    sys.exit(main())
