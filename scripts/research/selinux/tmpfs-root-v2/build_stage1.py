#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Derive/build a new cleanup waiter for one explicitly pinned V3 /init.

This independent recipe imports only the hash-pinned original tool/ELF helpers.
It never invokes the old build entry point or edits its source. The derived C
changes only its marker, target byte length, and the explanatory header comment.
The C waiter still checks shape/size only: complete V3 and waiter ELF hashes
must be pinned by the independent archive/runtime profile. This recipe does
not execute either ELF, mount, load a policy, edit a rootfs, or start a VM.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
BASE_RELATIVE = Path('scripts/research/selinux/tmpfs-root')
BASE_SOURCE_SHA = '32fbddd979e02c310ed28e3571d32a32f9733c8a07bed772aa9c64baf4483b33'
BASE_RECIPE_SHA = '5c6985c93942a7987acb5fa3e0822567c3c76348c5a34d280f370dcf3f62e294'
STAGE0_SHA = '15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d'
WORK_PARENT = Path('/work/tmpfs-waiter-v2-20261123')
ORIGINAL_TARGET_SIZE = 72048


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def ordinary(path, expected=None, maximum=1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= maximum:
            raise ValueError('bounded ordinary input required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(maximum + 1)
        after = os.fstat(fd)
        key = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
                         s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if key(before) != key(after) or len(raw) != before.st_size or len(raw) > maximum:
            raise ValueError('input changed while read: ' + str(path))
    finally:
        os.close(fd)
    if expected is not None and digest(raw) != expected:
        raise ValueError('fixed input hash differs: ' + str(path))
    return raw, {'size': len(raw), 'sha256': digest(raw),
                 'mode': oct(stat.S_IMODE(before.st_mode)),
                 'uid': before.st_uid, 'gid': before.st_gid}


def derive_source(original, target_size):
    if digest(original) != BASE_SOURCE_SHA or not 64 <= target_size <= 1024 * 1024:
        raise ValueError('original source or explicit target size differs')
    changes = [
        (b'// then execute the unchanged e53cf... native SELinux /init.\n',
         b'// then execute the separately pinned V3 native SELinux /init.\n'
         b'// This waiter validates shape and byte length, not a content hash.\n'
         b'// The independent archive/profile must pin both complete ELF hashes.\n'),
        (b'#define MARKER "TB371FC_TMPFS_STAGE1_V1"',
         b'#define MARKER "TB371FC_TMPFS_STAGE1_V2"'),
        (b'#define HELPER_SIZE 72048',
         ('#define HELPER_SIZE ' + str(target_size)).encode('ascii')),
    ]
    derived = original
    for old, new in changes:
        if derived.count(old) != 1:
            raise ValueError('non-unique original derivation anchor')
        derived = derived.replace(old, new, 1)
    restored = derived
    for old, new in reversed(changes):
        if restored.count(new) != 1:
            raise ValueError('non-unique reverse derivation anchor')
        restored = restored.replace(new, old, 1)
    if restored != original:
        raise ValueError('derived waiter changed beyond the three approved substitutions')
    return derived, changes


def fresh_work(path):
    if (not path.is_absolute() or '..' in path.parts or WORK_PARENT not in path.parents or
            path.exists() or path.is_symlink()):
        raise ValueError('fresh explicit child of ' + str(WORK_PARENT) + ' required')
    if any(p.is_symlink() for p in path.parents):
        raise ValueError('work ancestors cannot be symlinks')
    path.mkdir(parents=True, mode=0o700)


def write_new(path, raw, mode):
    with path.open('xb') as stream:
        stream.write(raw)
    path.chmod(mode)


def build(args):
    if (not args.repo.is_absolute() or args.repo.is_symlink() or not args.repo.is_dir() or
            not args.v3_init.is_absolute() or
            not re.fullmatch(r'[0-9a-f]{64}', args.v3_sha256) or
            not 64 <= args.v3_size <= 1024 * 1024):
        raise ValueError('explicit source root and fixed V3 path/size/SHA are required')
    source_path = args.repo / BASE_RELATIVE / 'wait_and_exec.c'
    recipe_path = args.repo / BASE_RELATIVE / 'build_stage1.py'
    stage0_path = args.repo / BASE_RELATIVE / 'stage0.sh'
    original, _ = ordinary(source_path, BASE_SOURCE_SHA)
    original_recipe, _ = ordinary(recipe_path, BASE_RECIPE_SHA)
    stage0, _ = ordinary(stage0_path, STAGE0_SHA)
    target, target_identity = ordinary(args.v3_init, args.v3_sha256)
    if (len(target) != args.v3_size or target_identity['mode'] != '0o755' or
            target_identity['uid'] != 0 or target_identity['gid'] != 0 or
            b'TB371FC_EARLY_SELINUX_V3' not in target):
        raise ValueError('explicit V3 ELF size/mode/owner/marker differs')
    if b'\r' in original or b'\r' in stage0:
        raise ValueError('frozen sources must retain LF bytes')
    derived, changes = derive_source(original, args.v3_size)
    spec = importlib.util.spec_from_file_location('tb371fc_original_waiter_build', recipe_path)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    # The imported source is pinned above. Call its read-only helpers only;
    # never mutate its constants or invoke its source-specific main().
    compiler = base.COMPILER.resolve(strict=True)
    ordinary(compiler, base.COMPILER_SHA, 16 * 1024**2)
    package_text = base.run(['/usr/bin/dpkg-query', '-W', '-f=${Package}\t${Version}\n', *base.PACKAGES])
    packages = dict(line.split('\t', 1) for line in package_text.splitlines())
    if packages != base.PACKAGES:
        raise ValueError('qualified cross-toolchain package versions differ')
    target_elf = base.inspect(args.v3_init)
    if target_elf['size'] != args.v3_size or target_elf['sha256'] != args.v3_sha256:
        raise ValueError('V3 target changed before ELF qualification')
    fresh_work(args.work)
    source_dir = args.work / 'source'
    source_dir.mkdir(mode=0o700)
    write_new(source_dir / 'wait_and_exec.c', derived, 0o644)
    write_new(source_dir / 'stage0.sh', stage0, 0o755)
    output = args.work / 'init.tmpfs-wait'
    argv = [str(base.COMPILER), '-std=gnu11', '-O2', '-g0', '-D_FORTIFY_SOURCE=3',
            '-fPIE', '-fstack-protector-strong', '-fno-ident',
            '-Wall', '-Wextra', '-Werror', str(source_dir / 'wait_and_exec.c'),
            '-pie', '-Wl,--build-id=sha1,-z,relro,-z,now,--no-undefined', '-o', str(output)]
    environment = dict(os.environ, LC_ALL='C', SOURCE_DATE_EPOCH='1795392000')
    record = {
        'schema_version': 1,
        'scope': 'independent V2 cleanup-waiter construction and ELF inspection only',
        'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'passed': False, 'runtime_pid1_tested': False, 'mount_operation_performed': False,
        'policy_load_attempted': False, 'rootfs_modified': False, 'physical_hardware_tested': False,
        'recipe_sha256': digest(Path(__file__).read_bytes()),
        'original_source_sha256': BASE_SOURCE_SHA, 'original_recipe_sha256': digest(original_recipe),
        'derived_source_sha256': digest(derived), 'stage0_sha256': STAGE0_SHA,
        'approved_source_changes': [{'old': a.decode(), 'new': b.decode()} for a, b in changes],
        'exact_original_bytes_restored_by_reversing_approved_substitutions': True,
        'target_init': {'path': str(args.v3_init), **target_identity, 'elf': target_elf},
        'runtime_contract': {'fixed_next_path': '/init', 'shape_size_check': args.v3_size,
            'waiter_checks_target_content_hash': False, 'archive_must_pin_both_full_elf_hashes': True,
            'cleanup_child_fd_pid1_root_empty_and_other_shape_checks_unchanged': True,
            'new_marker': 'TB371FC_TMPFS_STAGE1_V2', 'old_target_size': ORIGINAL_TARGET_SIZE,
            'target_size_changed_from_original': args.v3_size != ORIGINAL_TARGET_SIZE},
        'compiler': {'invoked_path': str(base.COMPILER), 'resolved_path': str(compiler),
            'sha256': base.COMPILER_SHA, 'version': base.run([str(base.COMPILER), '--version']).splitlines()[0]},
        'toolchain_packages': packages, 'command': argv,
        'explicit_environment': {'LC_ALL': 'C', 'SOURCE_DATE_EPOCH': '1795392000'},
    }
    started = time.monotonic()
    try:
        result = subprocess.run(argv, capture_output=True, env=environment, timeout=60)
        record.update(compile_exit_code=result.returncode, compile_seconds=time.monotonic() - started)
        write_new(args.work / 'compiler.stdout', result.stdout, 0o600)
        write_new(args.work / 'compiler.stderr', result.stderr, 0o600)
        if result.returncode:
            raise ValueError('compiler failed; original diagnostics retained')
        output.chmod(0o755)
        record['elf'] = base.inspect(output)
        record['stage0'] = {'source_path': str(source_dir / 'stage0.sh'),
                            'size': len(stage0), 'sha256': STAGE0_SHA, 'mode': '0o755'}
        ordinary(source_path, BASE_SOURCE_SHA)
        ordinary(recipe_path, BASE_RECIPE_SHA)
        ordinary(stage0_path, STAGE0_SHA)
        final_target, final_target_identity = ordinary(args.v3_init, args.v3_sha256)
        if final_target != target or final_target_identity != target_identity:
            raise ValueError('target V3 ELF changed during waiter construction')
        record['inputs_unchanged_after_build'] = True
        record['passed'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        record['elapsed_seconds'] = time.monotonic() - started
        write_new(args.work / 'build-result.json',
                  (json.dumps(record, indent=2, sort_keys=True) + '\n').encode(), 0o600)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--v3-init', required=True, type=Path)
    parser.add_argument('--v3-size', required=True, type=int)
    parser.add_argument('--v3-sha256', required=True)
    outcome = build(parser.parse_args())
    print(json.dumps(outcome, indent=2, sort_keys=True), flush=True)
    raise SystemExit(0 if outcome['passed'] else 1)
