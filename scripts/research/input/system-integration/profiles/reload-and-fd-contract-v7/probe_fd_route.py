#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only AV contracts on caller-supplied, same-boot exported policy bytes.

The caller has already checked the owned VM, read /sys/fs/selinux/policy, and
created/observed three pipe endpoints. This module does not observe processes
or descriptors. In particular, worker_context is a requested premise until the
parent independently observes the held worker after READY and before GO.

No libselinux API, version conversion, policy/boolean update, subprocess or
kernel write is used. The fixed Fedora libsepol public services API parses the
input into this process's private policydb/sidtab. ABI source: SELinux Project
2233a23a4d4f1bf29054037babec13f30d038e65, services.h and flask_types.h.
"""

import ctypes as c
import hashlib
from pathlib import Path
import platform
import stat
import struct


LIBRARY = Path('/usr/lib64/libsepol.so.2')
LIBRARY_SIZE = 802880
LIBRARY_SHA = '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b'
MANAGER = 'system_u:system_r:init_t:s0'
BROKER = 'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023'
MANAGEMENT = 'system_u:system_r:sysadm_t:s0'
POLICY_FILE = 'system_u:object_r:semanage_store_t:s0'
ENTRY_FILE = 'system_u:object_r:bin_t:s0'
SECURITY = 'system_u:object_r:security_t:s0'
PREVIOUS_SERVICE = 'system_u:system_r:unconfined_service_t:s0'
FIFO_PERMISSIONS = ('read', 'write', 'append', 'getattr', 'ioctl')
ENTRY_PERMISSIONS = ('entrypoint', 'execute', 'read', 'open', 'getattr', 'map')


class AVDecision(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in
                ('allowed', 'decided', 'auditallow', 'auditdeny', 'seqno')]


def probe(policy_bytes, *, manager_context, broker_context, creator_context,
          worker_context, descriptors, policy_file_context, entry_file_context):
    """Return computed permissions, never a claim of actual worker observation."""
    result = {
        'schema_version': 1,
        'scope': 'userspace AV computation on caller-provided same-boot exported policy bytes',
        'query_completed': False,
        'all_receivers_fd_and_fifo_allowed': False,
        'service_entry_allowed': False,
        'source_policy_map_allowed': False,
        'source_policy_read_and_load_allowed': False,
        'manager_read_policy_denied': False,
        'management_read_policy_allowed': False,
        'management_policy_export_path_allowed': False,
        'unconfined_service_fifo_restriction_retained': False,
        'all_requested_contracts_satisfied': False,
        'kernel_policy_loaded_or_written': False,
        'booleans_changed': False,
        'policy_version_converted': False,
        'sids_are_process_private': True,
        'worker_context_is_requested_premise': True,
        'actual_worker_context_observed_by_probe': False,
        'actual_descriptor_provenance_observed_by_probe': False,
        'runtime_descriptor_transfer_proven_by_probe': False,
        'required_composite_gate': 'parent must observe the same held worker domain, PID identity and three forwarded descriptors before GO',
        'library': {'path': str(LIBRARY), 'size': LIBRARY_SIZE, 'sha256': LIBRARY_SHA},
        'return_codes': {}, 'contexts': {}, 'queries': [],
    }
    libc = None
    memory_file = None
    try:
        if platform.machine() != 'aarch64' or c.sizeof(c.c_void_p) != 8 or c.sizeof(AVDecision) != 20:
            raise ValueError('qualified AArch64 public ABI required')
        if type(policy_bytes) is not bytes or not 1024 < len(policy_bytes) <= 32 * 1024**2:
            raise ValueError('bounded immutable exported policy bytes required')
        result['input_policy'] = {'size': len(policy_bytes),
                                  'sha256': hashlib.sha256(policy_bytes).hexdigest()}
        if (struct.unpack_from('<II', policy_bytes) != (0xf97cff8c, 8) or
                policy_bytes[8:16] != b'SE Linux' or
                struct.unpack_from('<I', policy_bytes, 16)[0] != 33):
            raise ValueError('actual exported version33 binary policy required; no conversion is allowed')
        if (manager_context != MANAGER or broker_context != BROKER or
                creator_context != MANAGEMENT or worker_context != MANAGEMENT):
            raise ValueError('actual/requested contexts differ from the explicit v7 management contract')
        if policy_file_context != POLICY_FILE or entry_file_context != ENTRY_FILE:
            raise ValueError('actual policy or executable inode label differs from the qualified entry')
        result['process_context_inputs'] = {
            'manager': manager_context, 'broker': broker_context,
            'creator': creator_context, 'requested_worker': worker_context,
        }
        result['file_context_inputs'] = {'policy': policy_file_context, 'entry': entry_file_context}
        if not isinstance(descriptors, dict) or set(descriptors) != {'0', '1', '2'}:
            raise ValueError('exactly three observed forwarded descriptors are required')
        checked = {}
        for fd in ('0', '1', '2'):
            item = descriptors[fd]
            access_mode = 0 if fd == '0' else 1
            if (not isinstance(item, dict) or item.get('creator_context') != creator_context or
                    item.get('inode_selinux_context') != MANAGEMENT or
                    type(item.get('mode')) is not int or not stat.S_ISFIFO(item['mode']) or
                    type(item.get('access_mode')) is not int or item['access_mode'] != access_mode):
                raise ValueError('descriptor creator, inode type/label or direction differs: ' + fd)
            checked[fd] = {
                'creator_context': item['creator_context'],
                'inode_selinux_context': item['inode_selinux_context'],
                'mode': item['mode'], 'access_mode': item['access_mode'],
                'opener_provenance': 'caller observed its unchanged domain around pipe2; not independently observed by this probe',
            }
            for key in ('device', 'inode', 'flags'):
                if key in item:
                    if type(item[key]) is not int or item[key] < 0:
                        raise ValueError('invalid observed descriptor field: ' + key)
                    checked[fd][key] = item[key]
        result['descriptor_inputs'] = checked
        if LIBRARY.is_symlink() or not LIBRARY.is_file():
            raise ValueError('ordinary fixed libsepol binary required')
        library = LIBRARY.read_bytes()
        if len(library) != LIBRARY_SIZE or hashlib.sha256(library).hexdigest() != LIBRARY_SHA:
            raise ValueError('libsepol differs from the qualified Fedora package')
        if library[:6] != b'\x7fELF\x02\x01' or int.from_bytes(library[18:20], 'little') != 183:
            raise ValueError('libsepol must be ELF64 AArch64')
        lib = c.CDLL(str(LIBRARY))
        signatures = {
            'sepol_set_policydb_from_file': ([c.c_void_p], c.c_int),
            'sepol_context_to_sid': ([c.c_char_p, c.c_size_t, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_string_to_security_class': ([c.c_char_p, c.POINTER(c.c_uint16)], c.c_int),
            'sepol_string_to_av_perm': ([c.c_uint16, c.c_char_p, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_compute_av_reason': ([c.c_uint32, c.c_uint32, c.c_uint16, c.c_uint32,
                                         c.POINTER(AVDecision), c.POINTER(c.c_uint)], c.c_int),
        }
        for name, (args, restype) in signatures.items():
            function = getattr(lib, name)
            function.argtypes, function.restype = args, restype
        libc = c.CDLL('libc.so.6', use_errno=True)
        libc.fmemopen.argtypes, libc.fmemopen.restype = [c.c_void_p, c.c_size_t, c.c_char_p], c.c_void_p
        libc.fclose.argtypes, libc.fclose.restype = [c.c_void_p], c.c_int

        def zero(name, value):
            result['return_codes'][name] = value
            if value != 0:
                raise ValueError(name + ' returned ' + str(value))

        # Keep buffer alive through fclose. The services API owns its parsed
        # process-private policydb; no kernel or libselinux load API is used.
        buffer = c.create_string_buffer(policy_bytes, len(policy_bytes))
        c.set_errno(0)
        memory_file = libc.fmemopen(buffer, len(policy_bytes), b'rb')
        if not memory_file:
            raise OSError(c.get_errno(), 'fmemopen failed')
        zero('private_policydb_from_exported_bytes', lib.sepol_set_policydb_from_file(memory_file))
        closed = libc.fclose(memory_file)
        memory_file = None
        zero('fclose', closed)
        sids = {}

        def sid(value):
            if value not in sids:
                encoded = value.encode('ascii')
                answer = c.c_uint32()
                ret = lib.sepol_context_to_sid(encoded, len(encoded), c.byref(answer))
                result['contexts'][value] = {'return_code': ret,
                    'accepted_by_policy': ret == 0, 'private_sid': answer.value if ret == 0 else None}
                if ret != 0:
                    raise ValueError('context rejected by the actual supplied policy: ' + value)
                sids[value] = answer.value
            return sids[value]

        rows = []

        def add(group, source, target, class_name, permissions, *, fd=None, receiver=None):
            rows.extend({'group': group, 'source_context': source, 'target_context': target,
                         'class': class_name, 'permission': name,
                         'descriptor': fd, 'receiver': receiver} for name in permissions)

        receivers = {'broker': broker_context, 'manager': manager_context, 'requested_worker': worker_context}
        for fd, descriptor in checked.items():
            for receiver, source in receivers.items():
                add('descriptor_route', source, descriptor['creator_context'], 'fd', ('use',),
                    fd=fd, receiver=receiver)
                add('descriptor_route', source, descriptor['inode_selinux_context'],
                    'fifo_file', FIFO_PERMISSIONS, fd=fd, receiver=receiver)
        add('entry', manager_context, manager_context, 'process', ('setexec',))
        add('entry', manager_context, creator_context, 'process', ('transition',))
        add('entry', creator_context, entry_file_context, 'file', ENTRY_PERMISSIONS)
        # Requested worker and creator are deliberately the same exact context;
        # the same Python/bin_t entry contract applies once the parent observes it.
        add('source_policy_map', manager_context, policy_file_context, 'file', ('map',))
        add('source_policy_read_and_load', manager_context, policy_file_context,
            'file', ('read', 'open', 'getattr'))
        add('source_policy_read_and_load', manager_context, SECURITY, 'security', ('load_policy',))
        add('manager_policy_export', manager_context, SECURITY, 'security', ('read_policy',))
        add('management_policy_export', creator_context, SECURITY, 'security', ('read_policy',))
        add('management_policy_export_path', creator_context, SECURITY, 'file', ('open', 'read', 'getattr'))
        add('management_policy_export_path', creator_context, SECURITY, 'dir', ('search', 'getattr'))
        add('previous_service_fifo', broker_context, PREVIOUS_SERVICE, 'fifo_file', FIFO_PERMISSIONS)
        add('previous_service_fd', broker_context, PREVIOUS_SERVICE, 'fd', ('use',))

        for row in rows:
            class_id, permission = c.c_uint16(), c.c_uint32()
            zero('class:' + row['class'],
                 lib.sepol_string_to_security_class(row['class'].encode(), c.byref(class_id)))
            zero('permission:' + row['class'] + ':' + row['permission'],
                 lib.sepol_string_to_av_perm(class_id, row['permission'].encode(), c.byref(permission)))
            if not permission.value or permission.value & (permission.value - 1):
                raise ValueError('permission lookup is not a single bit')
            decision, reason = AVDecision(), c.c_uint()
            ret = lib.sepol_compute_av_reason(sid(row['source_context']), sid(row['target_context']),
                class_id, permission, c.byref(decision), c.byref(reason))
            result['queries'].append({**row,
                'return_code': ret,
                'permission_allowed': bool(decision.allowed & permission.value) if ret == 0 else None,
                'denial_audit_mask_includes_permission': bool(decision.auditdeny & permission.value) if ret == 0 else None,
                'requested_mask': permission.value, 'reason_mask': reason.value,
                'raw_decision': {field: getattr(decision, field) for field, _ in AVDecision._fields_},
            })
            if ret != 0:
                raise ValueError('AV computation error is not a permission-denial result')

        def all_decisions(group, expected_count, allowed):
            selected = [row for row in result['queries'] if row['group'] == group]
            return len(selected) == expected_count and all(row['permission_allowed'] is allowed for row in selected)

        if len(LIBRARY.read_bytes()) != LIBRARY_SIZE or hashlib.sha256(LIBRARY.read_bytes()).hexdigest() != LIBRARY_SHA:
            raise ValueError('qualified library changed during query')
        result.update(
            query_count=len(result['queries']), expected_query_count=80,
            query_completed=len(result['queries']) == len(rows) == 80,
            all_receivers_fd_and_fifo_allowed=all_decisions('descriptor_route', 54, True),
            service_entry_allowed=all_decisions('entry', 8, True),
            source_policy_map_allowed=all_decisions('source_policy_map', 1, True),
            source_policy_read_and_load_allowed=all_decisions('source_policy_read_and_load', 4, True),
            manager_read_policy_denied=all_decisions('manager_policy_export', 1, False),
            management_read_policy_allowed=all_decisions('management_policy_export', 1, True),
            management_policy_export_path_allowed=all_decisions('management_policy_export_path', 5, True),
            unconfined_service_fifo_restriction_retained=all_decisions('previous_service_fifo', 5, False),
        )
        result['all_requested_contracts_satisfied'] = all(result[key] for key in (
            'query_completed', 'all_receivers_fd_and_fifo_allowed', 'service_entry_allowed',
            'source_policy_map_allowed', 'source_policy_read_and_load_allowed',
            'manager_read_policy_denied', 'management_read_policy_allowed',
            'management_policy_export_path_allowed', 'unconfined_service_fifo_restriction_retained'))
    except Exception as error:
        result['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if libc is not None and memory_file:
            libc.fclose(memory_file)
    return result
