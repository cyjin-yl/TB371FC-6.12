#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Independent fixed six-permission candidate AV qualification. Reuses the exact 54 postreload and 32 Varlink rows, with group namespaces, in one userspace policy parse. Fixed candidate35 is converted to the independently expected33 bytes; no kernel policy load, boolean write, PRoot, subprocess, mount, service or VM operation is implemented. Exit zero requires all named contract and retained-denial gates.
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


STOCK = (3835456, '727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502')
CONVERTED_SIZE = 3835444
CONVERTED_SHA = '9b39b5a59771bf3f7ac1119979ac09ca7c579fd5504b57f2970008b6ee200afe'
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


def postreload_rows():
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


def varlink_rows():
    rows = []

    def add(group, source, target, cls, names):
        rows.extend((group, source, target, cls, name) for name in names)

    registry = object_context('systemd_varlink_registry_t')
    add('registry_create', INIT, registry, 'lnk_file', ('create',))
    add('registry_idempotent_link_check', INIT, registry, 'lnk_file', ('getattr', 'read'))
    add('registry_remove_on_stop', INIT, registry, 'lnk_file', ('unlink',))
    add('registry_directory_lifecycle', INIT, registry, 'dir', ('search', 'write', 'add_name', 'remove_name'))
    add('registry_parent_traversal', INIT, object_context('systemd_varlink_t'), 'dir', ('search',))
    add('registry_directory_setup_diagnostic', INIT, registry, 'dir', ('create', 'getattr', 'setattr'))
    client = context('journalctl_t')
    journal = object_context('syslogd_var_run_t')
    add('journal_socket_path', client, journal, 'sock_file', ('write',))
    add('journal_server_connection', client, context('syslogd_t'), 'unix_stream_socket', ('connectto',))
    add('journal_client_socket', client, client, 'unix_stream_socket', ('create', 'connect', 'read', 'write'))
    add('journal_client_socket_diagnostic', client, client, 'unix_stream_socket', ('getattr', 'getopt', 'setopt', 'shutdown'))
    for label in ('var_run_t', 'init_var_run_t', 'syslogd_var_run_t'):
        add('journal_parent_traversal', client, object_context(label), 'dir', ('search',))
    add('journal_socket_metadata_diagnostic', client, journal, 'sock_file', ('getattr',))
    add('expected_denial_control', INIT, object_context('security_t'), 'security', ('read_policy',))
    add('expected_denial_control', context('syslogd_t'), object_context('syslogd_tmpfs_t'), 'file', ('map',))
    add('expected_denial_control', 'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023',
        context('unconfined_service_t'), 'fifo_file', ('write',))
    add('prior_required_permission', INIT, INIT, 'process', ('setcurrent', 'dyntransition'))
    add('prior_required_permission', INIT, object_context('semanage_store_t'), 'file', ('map',))
    return rows

def query_rows():
    post, var = postreload_rows(), varlink_rows()
    if len(post) != 54 or len(var) != 32:
        raise ValueError('frozen matrix sizes changed')
    return [(prefix + '/' + group, source, target, cls, permission)
            for prefix, rows in [('postreload', post), ('varlink', var)]
            for group, source, target, cls, permission in rows]



def probe(policy_bytes, library_path):
    out = {
        'schema_version': 2,
        'scope': 'offline fixed six-permission candidate; one combined 54+32 query; no runtime execution proof',
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
            out['policy_provenance'] = 'independent fixed standard-services candidate35 converted to33 in userspace; offline only'
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
        if identity(queried) != (CONVERTED_SIZE, CONVERTED_SHA):
            raise ValueError('converted policy differs from independently qualified fresh33 identity')
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

        post_rows = [row for row in out['queries'] if row['group'].startswith('postreload/')]
        var_rows = [row for row in out['queries'] if row['group'].startswith('varlink/')]
        post_control_groups = {'postreload/old_journal_label_diagnostic',
                               'postreload/manager_export_denial_control'}
        post_controls = [row for row in post_rows if row['group'] in post_control_groups]
        post_required = [row for row in post_rows if row['group'] not in post_control_groups]
        var_controls = [row for row in var_rows if row['group'] == 'varlink/expected_denial_control']
        var_diagnostics = [row for row in var_rows if row['group'].endswith('_diagnostic')]
        var_required = [row for row in var_rows
                        if row['group'] != 'varlink/expected_denial_control'
                        and not row['group'].endswith('_diagnostic')]
        new_groups = {'varlink/registry_remove_on_stop', 'varlink/journal_socket_path',
                      'varlink/journal_server_connection'}
        newly_allowed = [row for row in var_rows if row['group'] in new_groups]
        getattr_control = [row for row in var_rows
                           if row['group'] == 'varlink/journal_socket_metadata_diagnostic']
        out['required_denials'] = [row for row in post_required + var_required
                                  if row['permission_allowed'] is not True]
        out['diagnostic_rows'] = var_diagnostics
        out['retained_denial_rows'] = post_controls + var_controls
        out['postreload_required_allowed'] = len(post_required) == 52 and all(
            row['permission_allowed'] is True for row in post_required)
        out['postreload_two_controls_denied'] = len(post_controls) == 2 and all(
            row['permission_allowed'] is False for row in post_controls)
        out['varlink_required_allowed'] = len(var_required) == 21 and all(
            row['permission_allowed'] is True for row in var_required)
        out['varlink_three_controls_denied'] = len(var_controls) == 3 and all(
            row['permission_allowed'] is False for row in var_controls)
        out['new_three_permissions_allowed'] = len(newly_allowed) == 3 and all(
            row['permission_allowed'] is True for row in newly_allowed)
        out['target_socket_getattr_remains_denied'] = len(getattr_control) == 1 and (
            getattr_control[0]['permission_allowed'] is False)
        out['all_queried_required_permissions_allowed'] = not out['required_denials']
        out['postreload_contract_complete'] = (out['postreload_required_allowed'] and
                                               out['postreload_two_controls_denied'])
        out['varlink_contract_complete'] = (out['varlink_required_allowed'] and
                                            out['varlink_three_controls_denied'] and
                                            out['new_three_permissions_allowed'] and
                                            out['target_socket_getattr_remains_denied'])
        out['candidate_permission_contract_complete'] = (
            out['postreload_contract_complete'] and out['varlink_contract_complete'])
        out['query_count'] = len(out['queries'])
        out['expected_query_count'] = 86
        out['matrix_counts'] = {'postreload': len(post_rows), 'varlink': len(var_rows)}
        out['unique_av_tuple_count'] = len({(row['source_context'], row['target_context'],
                                           row['class'], row['permission'])
                                          for row in out['queries']})
        out['allowed_count'] = sum(row['permission_allowed'] is True for row in out['queries'])
        out['denied_count'] = sum(row['permission_allowed'] is False for row in out['queries'])
        out['original_matrix_rows_preserved'] = True
        out['duplicate_tuples_between_matrices_retained'] = True
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
    return 0 if (result.get('completed') is True and
                 result.get('candidate_permission_contract_complete') is True) else 1


if __name__ == '__main__':
    sys.exit(main())
