#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only AV computation on bytes exported by this VM's SELinux kernel.

The caller supplies bytes it just read from /sys/fs/selinux/policy after its
owned-VM guards. There is no version conversion, libselinux call, policy load,
boolean update or kernel write. Public libsepol APIs populate only this Python
process's private policydb/sidtab. SIDs in the result are not kernel SID values.

ABI source: SELinux Project commit 2233a23a4d4f1bf29054037babec13f30d038e65,
libsepol/include/sepol/policydb/services.h and flask_types.h. The fixed offline
engine in scripts/research/selinux/query_policy_access.py uses the same ABI.
"""
import ctypes as c
import hashlib
from pathlib import Path
import platform
import struct

LIBRARY = Path('/usr/lib64/libsepol.so.2')
LIBRARY_SIZE = 802880
LIBRARY_SHA = '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b'


class AVDecision(c.Structure):
    _fields_ = [(name, c.c_uint32) for name in
                ('allowed', 'decided', 'auditallow', 'auditdeny', 'seqno')]


def probe(policy, broker_context, validator_context):
    outcome = {'schema_version': 1, 'scope': 'userspace AV computation on actual exported VM policy bytes',
               'kernel_policy_written_or_loaded': False, 'booleans_changed': False,
               'policy_version_converted': False, 'query_completed': False,
               'sids_are_process_private': True, 'queries': [], 'return_codes': {},
               'input_policy': {'size': len(policy), 'sha256': hashlib.sha256(policy).hexdigest()},
               'library': {'path': str(LIBRARY), 'size': LIBRARY_SIZE, 'sha256': LIBRARY_SHA}}
    libc = None
    memory_file = None
    try:
        if platform.machine() != 'aarch64' or c.sizeof(c.c_void_p) != 8 or c.sizeof(AVDecision) != 20:
            raise ValueError('qualified native ARM64 public ABI required')
        if not 1024 < len(policy) <= 32 * 1024**2:
            raise ValueError('exported policy length outside bound')
        if (struct.unpack_from('<II', policy) != (0xf97cff8c, 8) or
                policy[8:16] != b'SE Linux' or struct.unpack_from('<I', policy, 16)[0] != 33):
            raise ValueError('actual kernel-exported version 33 policy required')
        if broker_context not in ('system_u:system_r:system_dbusd_t:s0',
                                  'system_u:system_r:system_dbusd_t:s0-s0:c0.c1023'):
            raise ValueError('unexpected actual broker process context')
        if validator_context != 'system_u:system_r:initrc_t:s0':
            raise ValueError('the explicit verification service domain was not entered')
        if LIBRARY.is_symlink() or not LIBRARY.is_file():
            raise ValueError('ordinary fixed libsepol binary required')
        library = LIBRARY.read_bytes()
        if len(library) != LIBRARY_SIZE or hashlib.sha256(library).hexdigest() != LIBRARY_SHA:
            raise ValueError('libsepol differs from the frozen Fedora package')
        if library[:6] != b'\x7fELF\x02\x01' or int.from_bytes(library[18:20], 'little') != 183:
            raise ValueError('libsepol is not ELF64 AArch64')
        lib = c.CDLL(str(LIBRARY))
        signatures = {
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

        def zero(name, value):
            outcome['return_codes'][name] = value
            if value != 0:
                raise ValueError(name + ' returned ' + str(value))

        # Keep this buffer alive until sepol_set_policydb_from_file returns and
        # fclose completes. libsepol owns its parsed database after that call.
        buffer = c.create_string_buffer(policy, len(policy))
        c.set_errno(0)
        memory_file = libc.fmemopen(buffer, len(policy), b'rb')
        if not memory_file:
            raise OSError(c.get_errno(), 'fmemopen failed')
        zero('userspace_policydb_from_exported_bytes', lib.sepol_set_policydb_from_file(memory_file))
        closed = libc.fclose(memory_file)
        memory_file = None
        zero('fclose', closed)
        sids = {}

        def sid(context):
            if context not in sids:
                value = c.c_uint32()
                encoded = context.encode('ascii')
                zero('context:' + context, lib.sepol_context_to_sid(encoded, len(encoded), c.byref(value)))
                sids[context] = value.value
            return sids[context]

        candidates = []
        for target in (validator_context, 'system_u:system_r:unconfined_service_t:s0'):
            candidates.append((broker_context, target, 'fd', 'use'))
            candidates.extend((broker_context, target, 'fifo_file', name)
                              for name in ('read', 'write', 'append', 'getattr', 'ioctl'))
        candidates.extend((
            (broker_context, 'system_u:system_r:kernel_t:s0', 'fd', 'use'),
            ('system_u:system_r:init_t:s0', validator_context, 'process', 'transition'),
            ('system_u:system_r:init_t:s0', 'system_u:system_r:init_t:s0', 'process', 'setexec'),
        ))
        for source, target, class_name, name in candidates:
            class_id, permission = c.c_uint16(), c.c_uint32()
            zero('class:' + class_name, lib.sepol_string_to_security_class(class_name.encode(), c.byref(class_id)))
            zero('permission:' + class_name + ':' + name,
                 lib.sepol_string_to_av_perm(class_id, name.encode(), c.byref(permission)))
            if not permission.value or permission.value & (permission.value - 1):
                raise ValueError('permission lookup is not a single bit')
            decision, reason = AVDecision(), c.c_uint()
            ret = lib.sepol_compute_av_reason(sid(source), sid(target), class_id, permission,
                                              c.byref(decision), c.byref(reason))
            entry = {'source_context': source, 'target_context': target, 'class': class_name,
                     'permission': name, 'return_code': ret,
                     'permission_allowed': bool(decision.allowed & permission.value) if ret == 0 else None,
                     'denial_audit_mask_includes_permission': bool(decision.auditdeny & permission.value) if ret == 0 else None,
                     'reason_mask': reason.value, 'requested_mask': permission.value,
                     'raw_decision': {field: getattr(decision, field) for field, _ in AVDecision._fields_}}
            outcome['queries'].append(entry)
            if ret != 0:
                raise ValueError('AV API failure is not a permission denial result')
        if hashlib.sha256(LIBRARY.read_bytes()).hexdigest() != LIBRARY_SHA:
            raise ValueError('fixed library changed while querying')
        outcome['query_count'] = len(outcome['queries'])
        outcome['query_completed'] = len(outcome['queries']) == 15
        outcome['actual_service_fd_and_fifo_allowed'] = all(
            item['permission_allowed'] for item in outcome['queries']
            if item['source_context'] == broker_context and item['target_context'] == validator_context)
        previous = [item for item in outcome['queries'] if item['class'] == 'fifo_file' and
                    item['target_context'] == 'system_u:system_r:unconfined_service_t:s0']
        outcome['unconfined_service_fifo_restriction_retained'] = (len(previous) == 5 and
            all(item['permission_allowed'] is False for item in previous))
        outcome['actual_runtime_syscall_enforcement_proven_by_this_query'] = False
    except Exception as error:
        outcome['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if libc is not None and memory_file:
            libc.fclose(memory_file)
    return outcome
