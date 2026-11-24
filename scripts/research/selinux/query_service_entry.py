#!/usr/bin/python3
"""Bounded service-entry AV follow-up using the fixed offline query engine.

This probe reuses the exact qualified conversion and process-private policydb
from query_policy_access.py. It does not execute a service or load a kernel
policy. File entrypoint permission does not establish an automatic transition.
"""
import sys

sys.dont_write_bytecode = True

import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import stat

ENGINE = Path('/analysis/query_policy_access.py')
ENGINE_BYTES = 12847
ENGINE_SHA256 = '43f81b1334aeac1691529a699a6b8dad923ada9b5f16e38b2c45643ead9736d3'
BASE_RESULT_SHA256 = 'f556fbb650713298b380e7d05e7677b49c683abc6d6dd42af4d1d61b92f096a3'
COMPATIBILITY = Path('/analysis/verify_selinux_compatibility.py')


def check():
    result = {
        'schema_version': 1,
        'scope': 'offline service-entry access vectors; not an execution test',
        'query_completed': False,
        'kernel_policy_load_attempted': False,
        'live_selinux_configuration_changed': False,
        'rootfs_written_by_probe': False,
        'hardware_tested': False,
        'entrypoint_implies_transition': False,
        'engine_sha256': ENGINE_SHA256,
        'return_codes': {},
        'queries': [],
    }
    try:
        fd = os.open(ENGINE, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != ENGINE_BYTES:
                raise ValueError('unexpected fixed query engine')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                code = stream.read(ENGINE_BYTES + 1)
        finally:
            os.close(fd)
        if hashlib.sha256(code).hexdigest() != ENGINE_SHA256:
            raise ValueError('query engine hash mismatch')
        engine = {'__name__': '__fixed_av_query__', '__file__': str(ENGINE)}
        exec(compile(code, str(ENGINE), 'exec'), engine)
        base = engine['query'](COMPATIBILITY)
        encoded = (json.dumps(base, indent=2, sort_keys=True) + '\n').encode()
        base_hash = hashlib.sha256(encoded).hexdigest()
        result['base_query'] = {
            'query_completed': base['query_completed'],
            'query_count': base.get('query_count'),
            'permission_denial_count': base.get('permission_denial_count'),
            'serialized_result_sha256': base_hash,
        }
        if not base['query_completed'] or base_hash != BASE_RESULT_SHA256:
            raise ValueError('base query differs from the fixed first observation')
        # The engine freed its conversion wrapper/buffer. libsepol's service
        # policydb remains in this process, as specified in services.c:136-155.
        fixed = engine['fixed_compatibility_helper'](COMPATIBILITY)
        lib = c.CDLL(str(fixed['LIBRARY']))
        Decision = engine['AVDecision']
        signatures = {
            'sepol_context_to_sid': ([c.c_char_p, c.c_size_t, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_string_to_security_class': ([c.c_char_p, c.POINTER(c.c_uint16)], c.c_int),
            'sepol_string_to_av_perm': ([c.c_uint16, c.c_char_p, c.POINTER(c.c_uint32)], c.c_int),
            'sepol_compute_av_reason': ([c.c_uint32, c.c_uint32, c.c_uint16, c.c_uint32,
                                         c.POINTER(Decision), c.POINTER(c.c_uint)], c.c_int),
        }
        for name, (args, ret) in signatures.items():
            fn = getattr(lib, name)
            fn.argtypes, fn.restype = args, ret
        result['sepol_transition_sid_exported'] = hasattr(lib, 'sepol_transition_sid')
        result['automatic_transition_computed'] = False

        def zero(name, ret):
            result['return_codes'][name] = ret
            if ret != 0:
                raise ValueError(name + ' failed')

        def sid(context):
            value = c.c_uint32()
            data = context.encode('ascii')
            zero('context:' + context, lib.sepol_context_to_sid(data, len(data), c.byref(value)))
            return value.value

        candidates = [
            ('system_u:system_r:init_t:s0', 'system_u:system_r:init_t:s0',
             'process', 'setexec'),
            ('system_u:system_r:init_t:s0', 'system_u:system_r:initrc_t:s0',
             'process', 'transition'),
        ]
        for file_type in ('bin_t', 'shell_exec_t'):
            for perm in ('entrypoint', 'execute', 'read', 'open', 'getattr'):
                candidates.append(('system_u:system_r:initrc_t:s0',
                                   'system_u:object_r:' + file_type + ':s0', 'file', perm))
        for source, target, class_name, perm in candidates:
            class_id, bit = c.c_uint16(), c.c_uint32()
            zero('class:' + class_name, lib.sepol_string_to_security_class(
                class_name.encode(), c.byref(class_id)))
            zero('permission:' + class_name + ':' + perm, lib.sepol_string_to_av_perm(
                class_id, perm.encode(), c.byref(bit)))
            if not bit.value or bit.value & (bit.value - 1):
                raise ValueError('permission is not a single AV bit')
            av, reason = Decision(), c.c_uint()
            ret = lib.sepol_compute_av_reason(sid(source), sid(target), class_id, bit,
                                              c.byref(av), c.byref(reason))
            result['queries'].append({
                'source_context': source, 'target_context': target,
                'class': class_name, 'class_id': class_id.value, 'permission': perm,
                'requested_mask': '0x%08x' % bit.value, 'return_code': ret,
                'permission_allowed': bool(av.allowed & bit.value) if ret == 0 else None,
                'denial_audit_mask_includes_permission': bool(av.auditdeny & bit.value) if ret == 0 else None,
                'raw_decision': {name: '0x%08x' % getattr(av, name) for name, _ in Decision._fields_},
                'reason_mask': reason.value,
                'reasons': [label for mask, label in engine['REASONS'].items() if reason.value & mask],
            })
            if ret != 0:
                raise ValueError('AV computation failed')
        fixed['read_pinned'](fixed['POLICY'], fixed['POLICY_BYTES'], fixed['POLICY_SHA256'])
        fixed['read_pinned'](fixed['LIBRARY'], fixed['LIBRARY_BYTES'], fixed['LIBRARY_SHA256'])
        result['inputs_unchanged_after_query'] = True
        result['query_count'] = len(result['queries'])
        result['permission_denial_count'] = sum(not item['permission_allowed'] for item in result['queries'])
        result['query_completed'] = len(result['queries']) == 12
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    return result


if __name__ == '__main__':
    outcome = check()
    print(json.dumps(outcome, sort_keys=True, indent=2), flush=True)
    raise SystemExit(0 if outcome['query_completed'] else 1)
