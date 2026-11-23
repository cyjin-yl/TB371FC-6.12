#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the fixed pre-policy cleanup waiter as a regular AArch64 ELF.

Run only in the qualified project builder, using a fresh /work subdirectory.
This recipe does not execute the ELF, mount anything, or edit a rootfs.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time

RELATIVE = Path('scripts/research/selinux/tmpfs-root')
SOURCE_SHA = '32fbddd979e02c310ed28e3571d32a32f9733c8a07bed772aa9c64baf4483b33'
STAGE0_SHA = '15905f3993604e6f600a17b556354c2bece12bd5a00256c24cf7838482bb7d7d'
COMPILER = Path('/usr/bin/aarch64-linux-gnu-gcc')
COMPILER_SHA = 'fb743ca27a77466c91da66047eec879a615993feaabd860aaf3750e7b222b131'
PACKAGES = {
    'binutils-aarch64-linux-gnu': '2.44-3',
    'gcc-14-aarch64-linux-gnu': '14.2.0-19cross1',
    'libc6-dev-arm64-cross': '2.41-11cross1',
}
FROZEN_NATIVE_INIT_SHA = 'e53cf4073a7df64f4234ace503329a6fadd5f1688ef7e3be5f33c01e4d510e0d'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ordinary(path, expected=None, maximum=256 * 1024):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('ordinary bounded input required: ' + str(path))
    raw = path.read_bytes()
    if expected is not None and hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('fixed input differs: ' + str(path))
    return raw


def run(command, timeout=30):
    value = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if len(value.stdout.encode()) + len(value.stderr.encode()) > 1024 * 1024:
        raise ValueError('tool output exceeds its bound')
    if value.returncode != 0:
        raise ValueError('tool failed: ' + repr(command) + ': ' + value.stderr[-4000:])
    return value.stdout


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def inspect(elf):
    raw = ordinary(elf, maximum=1024 * 1024)
    if len(raw) < 64 or raw[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('expected ELF64 little-endian version 1')
    kind, machine = struct.unpack_from('<HH', raw, 16)
    if kind != 3 or machine != 183:
        raise ValueError('expected AArch64 PIE')
    readelf = '/usr/bin/aarch64-linux-gnu-readelf'
    program = run([readelf, '--wide', '--program-headers', str(elf)])
    dynamic = run([readelf, '--wide', '--dynamic', str(elf)])
    versions = run([readelf, '--wide', '--version-info', str(elf)])
    interpreters = re.findall(r'Requesting program interpreter: ([^\]]+)', program)
    needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', dynamic)
    if interpreters != ['/lib/ld-linux-aarch64.so.1']:
        raise ValueError('unexpected ELF interpreter')
    if len(needed) != len(set(needed)) or not needed or not set(needed) <= {
            'libc.so.6', 'ld-linux-aarch64.so.1'} or 'libc.so.6' not in needed:
        raise ValueError('unexpected runtime library edge')
    if '(RPATH)' in dynamic or '(RUNPATH)' in dynamic:
        raise ValueError('unexpected ELF search-path override')
    return {
        'path': str(elf), 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
        'mode': oct(elf.stat().st_mode & 0o7777), 'elf_class': 64, 'elf_data': 'little',
        'machine': machine, 'type': 'ET_DYN', 'interpreter': interpreters[0],
        'needed': needed, 'rpath': None, 'runpath': None,
        'glibc_versions': sorted(set(re.findall(r'\bGLIBC_[0-9.]+\b', versions))),
        'program_headers': program, 'dynamic_section': dynamic,
        'version_requirements': versions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    if args.repo.is_symlink() or not args.repo.is_dir():
        parser.error('ordinary explicit source checkout/overlay required')
    work = args.work
    if (not work.is_absolute() or '..' in work.parts or
            '/work' not in [str(p) for p in work.parents]):
        parser.error('work must be a fresh absolute subdirectory of /work')
    if work.exists() or work.is_symlink():
        parser.error('refusing an existing work prefix')
    parent = work.parent
    while parent != Path('/'):
        if parent.is_symlink():
            parser.error('work ancestors cannot be symlinks')
        parent = parent.parent
    source = ordinary(args.repo / RELATIVE / 'wait_and_exec.c', SOURCE_SHA)
    stage0 = ordinary(args.repo / RELATIVE / 'stage0.sh', STAGE0_SHA)
    if b'\r' in source or b'\r' in stage0:
        parser.error('fixed source must retain LF bytes')
    compiler = COMPILER.resolve(strict=True)
    ordinary(compiler, COMPILER_SHA, 16 * 1024**2)
    package_text = run(['/usr/bin/dpkg-query', '-W', '-f=${Package}\t${Version}\n', *PACKAGES])
    packages = dict(line.split('\t', 1) for line in package_text.splitlines())
    if packages != PACKAGES:
        parser.error('qualified cross-toolchain package versions differ')

    work.mkdir(parents=True)
    source_dir = work / 'source'
    source_dir.mkdir()
    for name, raw, mode in (('wait_and_exec.c', source, 0o644), ('stage0.sh', stage0, 0o755)):
        path = source_dir / name
        with path.open('xb') as stream:
            stream.write(raw)
        path.chmod(mode)
    elf = work / 'init.tmpfs-wait'
    command = [
        str(COMPILER), '-std=gnu11', '-O2', '-g0', '-D_FORTIFY_SOURCE=3',
        '-fPIE', '-fstack-protector-strong', '-fno-ident',
        '-Wall', '-Wextra', '-Werror', str(source_dir / 'wait_and_exec.c'),
        '-pie', '-Wl,--build-id=sha1,-z,relro,-z,now,--no-undefined', '-o', str(elf),
    ]
    environment = os.environ.copy()
    environment.update(LC_ALL='C', SOURCE_DATE_EPOCH='1795392000')
    record = {
        'schema_version': 1,
        'scope': 'isolated AArch64 pre-policy cleanup-waiter construction and ELF inspection only',
        'started_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'passed': False, 'runtime_pid1_tested': False, 'mount_operation_performed': False,
        'policy_load_attempted': False, 'physical_hardware_tested': False,
        'recipe_sha256': digest(Path(__file__)),
        'source_sha256': SOURCE_SHA, 'stage0_sha256': STAGE0_SHA,
        'unchanged_next_init_sha256': FROZEN_NATIVE_INIT_SHA,
        'compiler': {'invoked_path': str(COMPILER), 'resolved_path': str(compiler),
                     'sha256': COMPILER_SHA,
                     'version': run([str(COMPILER), '--version']).splitlines()[0]},
        'toolchain_packages': packages, 'command': command,
        'explicit_environment': {'LC_ALL': 'C', 'SOURCE_DATE_EPOCH': '1795392000'},
    }
    started = time.monotonic()
    try:
        value = subprocess.run(command, capture_output=True, env=environment, timeout=60)
        record.update(compile_exit_code=value.returncode,
                      compile_elapsed_seconds=time.monotonic() - started,
                      compiler_stdout=value.stdout.decode(errors='replace'),
                      compiler_stderr=value.stderr.decode(errors='replace'))
        if value.returncode != 0:
            raise ValueError('compiler failed; diagnostics retained')
        elf.chmod(0o755)
        record['elf'] = inspect(elf)
        record['stage0'] = {'source_path': str(source_dir / 'stage0.sh'),
                            'size': len(stage0), 'sha256': STAGE0_SHA, 'mode': '0o755'}
        record['passed'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        record['elapsed_seconds'] = time.monotonic() - started
        save(work / 'build-result.json', record)
    print(json.dumps(record, indent=2, sort_keys=True), flush=True)
    raise SystemExit(0 if record['passed'] else 1)


if __name__ == '__main__':
    main()
