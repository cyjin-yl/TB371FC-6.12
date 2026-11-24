#!/usr/bin/env python3
"""Bounded, explicit ARM Nix builder inside the existing disposable CT102 container.

PRoot supplies mixed native/AArch64 execution only for this process tree. Nix's
foreign-platform, sandbox and build-user overrides are per invocation. Nothing
registers binfmt, contacts a daemon, switches a system or changes host settings.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import time

WORK = Path('/work/nixos-system-v1')
PROOT = Path('/work/fedora-proot-src/src/proot')
HOST_LIBS = '/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu'
QEMU = Path('/usr/bin/qemu-aarch64-static')
FLAKE = Path('/work/nixos-flake')
BASH = Path('/nix/store/xkz38nlafxlb2jry727hg5l64iln9c05-bash-5.3p9')
HELLO = Path('/nix/store/67xf635fy5p8pryn15rwfc5iz63gk0kx-hello-2.12.3')
SYSTEM = '/nix/store/9qpn9nzy4xmcrfv6jc5liymr8mnzwdpg-nixos-system-tb371fc-research-26.05.20261121.94c3211.drv'
EXPECTED = '/nix/store/j1g4ih1ajpffx2vhp5z0iyns13h59c4a-nixos-system-tb371fc-research-26.05.20261121.94c3211'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    with (WORK / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def command(arguments, *, emulate=False, deadline=180):
    env = dict(os.environ, NIX_REMOTE='local')
    argv = list(arguments)
    if emulate:
        env['LD_LIBRARY_PATH'] = HOST_LIBS
        argv = [str(PROOT), '-r', '/', '-q', str(QEMU), '-w', str(WORK), *argv]
    started = time.monotonic()
    number = 1
    while (WORK / f'command-{number:02d}.stdout.log').exists():
        number += 1
    out_path = WORK / f'command-{number:02d}.stdout.log'
    err_path = WORK / f'command-{number:02d}.stderr.log'
    with out_path.open('x') as out, err_path.open('x') as err:
        process = subprocess.Popen(argv, stdout=out, stderr=err,
                                   text=True, env=env, start_new_session=True)
        print('NIX_COMMAND_STARTED', process.pid, str(out_path), str(err_path), flush=True)
        timed_out = False
        try:
            process.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
    return {'command': argv, 'emulation_enabled': emulate,
            'exit_code': process.returncode, 'timed_out': timed_out,
            'elapsed_seconds': time.monotonic() - started,
            'stdout_path': str(out_path), 'stderr_path': str(err_path),
            'stdout': out_path.read_text(), 'stderr': err_path.read_text()}


def nix(arguments):
    return ['nix', '--extra-experimental-features', 'nix-command flakes',
            '--store', 'local', '--option', 'sandbox', 'false',
            '--option', 'build-users-group', '',
            '--option', 'extra-platforms', 'aarch64-linux',
            '--option', 'require-sigs', 'true',
            '--option', 'cores', '2', '--option', 'max-jobs', '1',
            '--option', 'max-silent-time', '180', '--option', 'timeout', '600',
            *arguments]


def require(record):
    if record['exit_code'] != 0 or record['timed_out']:
        print(json.dumps(record, indent=2), flush=True)
        raise SystemExit('recorded command failed; preserved its evidence')


def probe():
    if WORK.exists() or WORK.is_symlink():
        raise SystemExit('new work directory must not already exist')
    if shutil.disk_usage('/work').free < 8 * 1024 ** 3:
        raise SystemExit('less than 8 GiB free')
    WORK.mkdir()
    records = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'scope': 'explicit userspace foreign builder; no system boot or tablet test',
               'binfmt_registration_changed': False, 'global_nix_settings_changed': False,
               'tablet_accessed': False, 'recipe_sha256': digest(__file__), 'tools': {}}
    for path in (PROOT, QEMU, BASH / 'bin/bash', HELLO / 'bin/hello'):
        raw = path.read_bytes()[:64]
        records['tools'][str(path)] = {'sha256': digest(path), 'size_bytes': path.stat().st_size,
                                      'elf_machine': struct.unpack('<H', raw[18:20])[0]}
    if any(records['tools'][str(p)]['elf_machine'] != 183
           for p in (BASH / 'bin/bash', HELLO / 'bin/hello')):
        raise SystemExit('target commands are not AArch64 ELF')
    native = command(['nix', '--extra-experimental-features', 'nix-command flakes',
                      '--store', 'local', 'config', 'show', '--json'])
    records['default_configuration'] = native
    save('configuration.before.json', native)
    require(native)
    mixed = command(['/usr/bin/python3', '-c',
                     'import subprocess; print("NATIVE_PYTHON_STARTED", flush=True); '
                     'subprocess.run(["' + str(BASH / 'bin/bash') + '", "-eu", "-c", '
                     '"' + str(HELLO / 'bin/hello') + '; printf ARM_BASH_EXECUTED"], check=True)'],
                    emulate=True)
    records['mixed_execution'] = mixed
    save('mixed-execution.json', mixed)
    require(mixed)
    if 'Hello, world!\nARM_BASH_EXECUTED' not in mixed['stdout']:
        raise SystemExit('missing actual nested ARM execution output')
    expression = '''let
      bash = builtins.storePath "''' + str(BASH) + '''";
      hello = builtins.storePath "''' + str(HELLO) + '''";
    in builtins.derivation {
      name = "tb371fc-explicit-arm-builder-v1";
      system = "aarch64-linux";
      builder = "${bash}/bin/bash";
      args = [ "-eu" "-c" ''
        ${hello}/bin/hello > "$out"
        printf '\\nARM_DERIVATION_EXECUTED\\n' >> "$out"
      '' ];
    }
'''
    (WORK / 'probe.nix').write_text(expression)
    built = command(nix(['build', '--impure', '--no-link', '--print-out-paths',
                         '--keep-failed', '--file', str(WORK / 'probe.nix')]), emulate=True)
    records['derivation_build'] = built
    save('derivation-probe-command.json', built)
    require(built)
    output = Path(built['stdout'].strip())
    if output.parent != Path('/nix/store') or not output.is_file():
        raise SystemExit('unexpected probe output')
    expected = 'Hello, world!\n\nARM_DERIVATION_EXECUTED\n'
    if output.read_text() != expected:
        raise SystemExit('unexpected foreign derivation bytes')
    records['derivation_output'] = {'path': str(output), 'sha256': digest(output), 'contents': expected}
    records['probe_passed'] = True
    save('probe.json', records)
    print('NIX_ACTUAL_ARM_DERIVATION_PASSED', str(output), flush=True)


def plan():
    if not json.loads((WORK / 'probe.json').read_text()).get('probe_passed'):
        raise SystemExit('successful actual ARM derivation required')
    result = command(nix(['build', '--no-link', '--dry-run', SYSTEM + '^*']), emulate=True, deadline=300)
    save('system-plan.json', result)
    require(result)
    print(result['stderr'], result['stdout'], flush=True)


def build():
    plan_record = json.loads((WORK / 'system-plan.json').read_text())
    require(plan_record)
    result = command(nix(['build', '--no-link', '--print-out-paths', '--keep-failed',
                          SYSTEM + '^*']), emulate=True, deadline=1800)
    save('system-build.json', result)
    print(result['stderr'], result['stdout'], flush=True)
    require(result)
    if result['stdout'].strip() != EXPECTED or not Path(EXPECTED).is_dir():
        raise SystemExit('unexpected system output')
    retention = command(['nix-store', '--store', 'local', '--add-root',
                         str(WORK / 'system-result'), '--indirect', '--realise', EXPECTED])
    save('retention.json', retention)
    require(retention)
    print('NIXOS_FULL_SYSTEM_CLOSURE_BUILT', EXPECTED, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('probe', 'plan', 'build'))
    args = parser.parse_args()
    globals()[args.action]()
