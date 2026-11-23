#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive and build an independent early loader for a pinned policy candidate.

This build recipe never loads a policy, runs PID 1, changes a rootfs, or edits
frozen inputs. The derived V3 helper requires an explicit generic-VM audit
observation opt-in and the actual linux,dummy-virt compatible before changing
only the shared printk interval to zero. It verifies a fresh readback and an
unchanged burst before its first libselinux load. This does not prevent audit
queue loss. The separate archive/runtime recipe must require the exact policy,
helper, command line, observation marker, and full serial-log loss gates.

This recipe is derived from the fixed root draft 48ab7278... and original V1
recipe/source. The accompanying guard fragment is an independently pinned input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True

ORIGINAL_SOURCE_SHA = '6006a0fade3e9e8cc9201b5549cab3339961931feadb842c0f3d5863dc383726'
ORIGINAL_RECIPE_SHA = '5ed18306782a44b20c6bf022976c6dc029b0829ec5a72352575ae35440fb493d'
ORIGINAL_POLICY_SHA = '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430'
COMPILER_SHA = 'fb743ca27a77466c91da66047eec879a615993feaabd860aaf3750e7b222b131'
PARENT_DRAFT_SHA = '48ab7278723e33a63e00e9daa7eb465642cb872d36be772d31a9f1979eaf0231'
GUARD_SOURCE_SHA = 'f715d823ac20181b916afac5c4db9ae9af8226454508e2dff9bb9b8f35e035cc'
CANDIDATE_POLICY_SHA = '727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502'
CANDIDATE_POLICY_SIZE = 3835456
PACKAGES = {
    'binutils-aarch64-linux-gnu': '2.44-3',
    'gcc-14-aarch64-linux-gnu': '14.2.0-19cross1',
    'libc6-dev-arm64-cross': '2.41-11cross1',
}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def ordinary(path, *, expected=None, bound=32 * 1024**2):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size > bound:
            raise ValueError('ordinary bounded input required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(bound + 1)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        if len(raw) > bound or any(getattr(before, x) != getattr(after, x) for x in fields):
            raise ValueError('input changed during read: ' + str(path))
    finally:
        os.close(fd)
    if expected is not None and digest(raw) != expected:
        raise ValueError('pinned input differs: ' + str(path))
    return raw


def fresh_directory(path):
    if (not path.is_absolute() or '..' in path.parts or
            Path('/work') not in path.parents or path.exists() or path.is_symlink()):
        raise ValueError('fresh absolute /work subdirectory required')
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('work ancestors cannot be symlinks')
    path.mkdir(mode=0o700, parents=True)


def write_new(path, raw, mode=0o600):
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(mode)


def command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    if len(result.stdout.encode()) + len(result.stderr.encode()) > 2 * 1024**2:
        raise ValueError('bounded tool output exceeded')
    if result.returncode:
        raise ValueError('tool failed: ' + repr(argv) + ': ' + result.stderr[-4096:])
    return result.stdout



def derive_source(original, guard, policy_size):
    if (digest(original) != ORIGINAL_SOURCE_SHA or digest(guard) != GUARD_SOURCE_SHA or
            policy_size != CANDIDATE_POLICY_SIZE):
        raise ValueError('fixed V3 source/guard/policy-size inputs differ')
    replacements = [
        (b'#define MARKER "TB371FC_EARLY_SELINUX_V1"',
         b'#define MARKER "TB371FC_EARLY_SELINUX_V3"'),
        (b'st.st_size != 3835432', ('st.st_size != ' + str(policy_size)).encode()),
        (b'#include <linux/magic.h>\n', b'#include <linux/magic.h>\n#include <limits.h>\n'),
        (b'static void load_api(struct selinux_api *api)\n',
         guard + b'\nstatic void load_api(struct selinux_api *api)\n'),
        (b'                  NULL, SELINUX_MAGIC);\n        load_api(&api);\n',
         b'                  NULL, SELINUX_MAGIC);\n'
         b'        configure_vm_audit_printk_observation();\n        load_api(&api);\n'),
    ]
    source = original
    for old, new in replacements:
        if source.count(old) != 1:
            raise ValueError('source derivation anchor is not unique')
        source = source.replace(old, new, 1)
    return source, replacements


def build(args):
    if (not re.fullmatch('[0-9a-f]{64}', args.policy_sha256) or
            args.policy_sha256 != CANDIDATE_POLICY_SHA or args.policy_size != CANDIDATE_POLICY_SIZE):
        raise ValueError('the fixed six-permission V3 candidate identity is required')
    policy = ordinary(args.policy, expected=args.policy_sha256)
    if (len(policy) != args.policy_size or not 1024 < len(policy) < 32 * 1024**2 or
            struct.unpack_from('<II', policy) != (0xf97cff8c, 8) or
            policy[8:16] != b'SE Linux' or struct.unpack_from('<I', policy, 16)[0] != 35):
        raise ValueError('the exact candidate version 35 policy is required')
    if args.policy_sha256 == ORIGINAL_POLICY_SHA:
        raise ValueError('the unchanged original policy is not this candidate')
    source_path = args.repo / 'scripts/research/selinux/early_init.c'
    recipe_path = args.repo / 'scripts/research/selinux/build_early_init.py'
    original = ordinary(source_path, expected=ORIGINAL_SOURCE_SHA, bound=128 * 1024)
    original_recipe = ordinary(recipe_path, expected=ORIGINAL_RECIPE_SHA, bound=128 * 1024)
    spec = importlib.util.spec_from_file_location('tb371fc_frozen_early_build', recipe_path)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    # Import only the pinned RPM/header extraction implementation, never modify
    # the frozen recipe's SOURCE_SHA256 or call its source-specific build().
    guard_path = Path(__file__).with_name('audit_printk_guard.inc')
    guard = ordinary(guard_path, expected=GUARD_SOURCE_SHA, bound=32 * 1024)
    source, replacements = derive_source(original, guard, args.policy_size)
    compiler = Path('/usr/bin/aarch64-linux-gnu-gcc')
    ordinary(compiler.resolve(strict=True), expected=COMPILER_SHA, bound=16 * 1024**2)
    package_text = command(['/usr/bin/dpkg-query', '-W', '-f=${Package}\t${Version}\n', *PACKAGES])
    packages = dict(line.split('\t', 1) for line in package_text.splitlines())
    if packages != PACKAGES:
        raise ValueError('qualified cross-toolchain package versions differ')
    rpm = base.fetch(args.header_cache)
    fresh_directory(args.work)
    outcome = {
        'schema_version': 1,
        'scope': 'build and inspect a new early SELinux loader; no kernel policy load or VM execution',
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'completed': False, 'hardware_tested': False, 'kernel_policy_load_attempted': False,
        'rootfs_modified': False, 'frozen_sources_modified': False,
        'recipe_sha256': digest(Path(__file__).read_bytes()),
        'parent_draft_sha256': PARENT_DRAFT_SHA,
        'guard_source': {'path': str(guard_path), 'size': len(guard), 'sha256': digest(guard)},
        'runtime_observation_contract': {
            'scope': 'generic QEMU VM only; no owner-tablet setting or boot authorization',
            'required_unique_opt_in': 'rd.tb371fc.audit-printk-unlimited=1',
            'required_actual_compatible': 'linux,dummy-virt',
            'fixed_write': {'path': '/proc/sys/kernel/printk_ratelimit', 'ascii': '0\n'},
            'fresh_readback_interval': 0, 'burst_must_remain_unchanged': True,
            'audit_rate_backlog_enforcing_modified': False,
            'separate_full_serial_audit_loss_gates_required': True,
            'runtime_execution_performed_by_this_build': False,
        },
        'original_source_sha256': ORIGINAL_SOURCE_SHA,
        'original_recipe_sha256': digest(original_recipe),
        'derived_source_sha256': digest(source),
        'source_changes': [{'old': old.decode(), 'new': new.decode()} for old, new in replacements],
        'candidate_policy': {'input_path': str(args.policy), 'size': len(policy),
                             'sha256': digest(policy), 'version': 35,
                             'hash_must_also_be_checked_by_archive_and_runtime_recipe': True},
        'compiler': {'invoked_path': str(compiler), 'resolved_path': str(compiler.resolve()),
                     'sha256': COMPILER_SHA, 'version': command([str(compiler), '--version'])},
        'toolchain_packages': packages,
        'header_rpm': {'url': base.RPM_URL, 'size': len(rpm), 'sha256': digest(rpm)},
    }
    try:
        outcome['headers'] = base.extract_headers(rpm, args.work / 'headers')
        native_source = args.work / 'early_init.c'
        output = args.work / 'early-init'
        write_new(native_source, source)
        argv = [str(compiler), '-std=gnu11', '-O2', '-g0', '-D_FORTIFY_SOURCE=3',
                '-fPIE', '-fstack-protector-strong', '-fno-ident', '-Wall', '-Wextra', '-Werror',
                '-I', str(args.work / 'headers'), str(native_source), '-pie',
                '-Wl,--build-id=sha1,-z,relro,-z,now,--no-undefined', '-ldl', '-o', str(output)]
        environment = dict(os.environ, SOURCE_DATE_EPOCH='1795392000', LC_ALL='C')
        started = time.monotonic()
        process = subprocess.run(argv, capture_output=True, timeout=60, env=environment)
        outcome.update(command=argv, compile_seconds=time.monotonic() - started,
                       compile_exit_code=process.returncode,
                       explicit_environment={'SOURCE_DATE_EPOCH': '1795392000', 'LC_ALL': 'C'})
        write_new(args.work / 'compiler.stdout', process.stdout)
        write_new(args.work / 'compiler.stderr', process.stderr)
        if process.returncode:
            raise ValueError('compiler failed; original diagnostics retained')
        binary = ordinary(output, bound=1024 * 1024)
        if (binary[:7] != b'\x7fELF\x02\x01\x01' or
                struct.unpack_from('<HH', binary, 16) != (3, 183)):
            raise ValueError('output is not an AArch64 PIE ELF64')
        details = {}
        for option, name in [('-d', 'dynamic'), ('-l', 'program_headers'), ('-V', 'versions')]:
            value = command(['/usr/bin/readelf', option, str(output)])
            write_new(args.work / ('readelf-' + name + '.txt'), value.encode())
            details[name] = value
        needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', details['dynamic'])
        interpreter = re.findall(r'Requesting program interpreter: ([^\]]+)', details['program_headers'])
        if (needed != ['libc.so.6', 'ld-linux-aarch64.so.1'] or
                interpreter != ['/lib/ld-linux-aarch64.so.1'] or
                '(RPATH)' in details['dynamic'] or '(RUNPATH)' in details['dynamic']):
            raise ValueError('unexpected ELF runtime contract')
        output.chmod(0o755)
        outcome['artifact'] = {
            'path': str(output), 'size': len(binary), 'sha256': digest(binary), 'mode': '0755',
            'machine': 183, 'type': 'ET_DYN', 'needed': needed, 'interpreter': interpreter[0],
            'glibc_versions': sorted(set(re.findall(r'GLIBC_[0-9.]+', details['versions']))),
        }
        ordinary(source_path, expected=ORIGINAL_SOURCE_SHA)
        ordinary(recipe_path, expected=ORIGINAL_RECIPE_SHA)
        ordinary(guard_path, expected=GUARD_SOURCE_SHA)
        ordinary(args.policy, expected=args.policy_sha256)
        outcome['inputs_unchanged_after_build'] = True
        outcome['completed'] = True
    except Exception as error:
        outcome['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        write_new(args.work / 'build-result.json',
                  (json.dumps(outcome, sort_keys=True, indent=2) + '\n').encode())
    return outcome


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--policy', required=True, type=Path)
    parser.add_argument('--policy-sha256', required=True)
    parser.add_argument('--policy-size', required=True, type=int)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--header-cache', required=True, type=Path)
    result = build(parser.parse_args())
    print(json.dumps(result, sort_keys=True, indent=2), flush=True)
    raise SystemExit(0 if result['completed'] else 1)
