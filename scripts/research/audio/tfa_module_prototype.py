#!/usr/bin/env python3
"""Compile the existing TFA98xx source in a separate, non-root build prefix.

This prototype is never installed, signed, loaded or given an amplifier. The
historical MTP guards are preserved as source changes, not a proof that every
possible hardware write is blocked. The qualified R4 runtime remains unchanged.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import stat
import subprocess

WORK = Path('/work/tfa-module-prototype-v1')
JOBS = Path('/work/tfa-module-prototype-jobs-v1')
BASE = Path('/work/research4-system')
SOURCE_REL = Path('source-input/linux-6.12.114-input-integration')
RELEASE = '6.12.114-tb371fc-research4-system'
PATCH = Path('/src/mainline-port/patches/0003-wip-ASoC-codecs-add-support-for-TFA98xx-based-on-dow.patch')
GUARD = Path('/src/scripts/r160-sound/tfa98xx-mtp-guard.py')
PINS = {
    PATCH: '9d5ca9bf17c37601f17f0ea5271fe81b3f68fb2187a438a4244a76aba74745b7',
    GUARD: '57b07505a43b1f28d74b76737faa9846bb4f2463b8b97a398f003992f105484c',
    BASE / 'kernel-out/.config': '0236496603f168aacc5586eac7e199ca8f840b5d0c9b5ed111da64e9d28ec275',
    BASE / 'kernel-out/Module.symvers': '68c10e8b5e63761282cbc6005affd059d8037fce5ac434f80285a6f9aac2f9e0',
    BASE / 'artifacts/Image': '8ab38b022f7504869443f2469878cd55656b08fb6c56946122710144fc1cc8fb',
    BASE / 'artifacts/modules.SHA256SUMS': '9ef1c87254c5422b61c0c365d088b8374a4c323c99da9bda1578170eaa443f03',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(name, value):
    with (WORK / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def pins():
    result = {}
    for path, expected in PINS.items():
        actual = sha(path)
        if actual != expected:
            raise ValueError('fixed source/build input changed: ' + str(path))
        result[str(path)] = {'sha256': actual, 'size': path.stat().st_size}
    return result


def prepare():
    original = pins()
    if WORK.exists() or WORK.is_symlink() or shutil.disk_usage('/work').free < 8 * 1024**3:
        raise ValueError('fresh prefix and 8 GiB free required')
    WORK.mkdir()
    unpack = WORK / 'patch-source'
    unpack.mkdir()
    subprocess.run(['git', 'init', '-q', str(unpack)], check=True)
    applied = subprocess.run(['git', 'apply', '--include=sound/soc/codecs/tfa98xx-downstream/*', str(PATCH)],
                             cwd=unpack, check=True, capture_output=True, text=True)
    imported = unpack / 'sound/soc/codecs/tfa98xx-downstream'
    files = sorted(p for p in imported.iterdir() if p.is_file())
    if len(files) != 35 or any(p.is_symlink() for p in files):
        raise ValueError('unexpected imported TFA source set')
    before = {p.name: sha(p) for p in files}
    module = WORK / 'module'
    shutil.copytree(imported, module)
    replaced = []
    for path in sorted(module.glob('*.c')):
        data = path.read_text()
        count = data.count('snd_soc_component_to_dapm(')
        if count:
            replaced.append({'file': path.name, 'occurrences': count})
            path.write_text(data.replace('snd_soc_component_to_dapm(', 'snd_soc_component_get_dapm('))
    if sum(row['occurrences'] for row in replaced) != 1:
        raise ValueError('the pinned 7.1-to-6.12 API substitution differs')
    guarded = subprocess.run(['python3', str(GUARD), str(module)], check=True, capture_output=True, text=True)
    (module / 'Kbuild').write_text('obj-m += snd-soc-tfa98xx.o\n'
        'snd-soc-tfa98xx-objs := tfa98xx.o tfa_container.o tfa_dsp.o tfa_init.o\n')
    # A separate source/development-output copy avoids changing the qualified
    # kernel. No certs directory or signing private key is copied from its out.
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE / SOURCE_REL), str(WORK / 'kernel-source')], check=True)
    subprocess.run(['cp', '-a', '--reflink=auto', str(BASE / 'target-sysroot'), str(WORK / 'target-sysroot')], check=True)
    output = WORK / 'kernel-out'
    output.mkdir()
    members = ('.config', 'Makefile', 'Module.symvers', 'System.map', 'vmlinux', 'include', 'scripts', 'tools')
    for name in members:
        path = BASE / 'kernel-out' / name
        if not path.exists():
            raise ValueError('missing prepared development input: ' + name)
        subprocess.run(['cp', '-a', '--reflink=auto', str(path), str(output / name)], check=True)
    for root in (module, WORK / 'kernel-source', output, WORK / 'target-sysroot'):
        for path in (root, *root.rglob('*')):
            if path.is_symlink():
                continue
            mode = stat.S_IMODE(path.stat().st_mode)
            os.chown(path, 1000, 1000)
            os.chmod(path, 0o755 if path.is_dir() or mode & 0o111 else 0o644)
    if sha(output / '.config') != PINS[BASE / 'kernel-out/.config'] or sha(output / 'Module.symvers') != PINS[BASE / 'kernel-out/Module.symvers']:
        raise ValueError('copied ABI inputs differ')
    after = {p.name: sha(p) for p in sorted(module.iterdir()) if p.is_file()}
    save('prepared.json', {'source_inputs': original, 'source_before': before, 'source_after': after,
        'api_substitution': replaced, 'guard_stdout': guarded.stdout, 'patch_stdout': applied.stdout,
        'patch_stderr': applied.stderr, 'output_members_copied': members,
        'warning_suppression_added': False, 'private_signing_key_copied': False,
        'kernel_runtime_installed_or_modified': False, 'physical_hardware_accessed': False})
    pins()
    print('TFA_PROTOTYPE_PREPARED', flush=True)


def drop_identity():
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)


def build():
    prepared = json.loads((WORK / 'prepared.json').read_text())
    for name, value in prepared['source_after'].items():
        if sha(WORK / 'module' / name) != value:
            raise ValueError('prototype source changed')
    pins()
    argv = ['make', '-C', str(WORK / 'kernel-source'), 'O=' + str(WORK / 'kernel-out'),
            'ARCH=arm64', 'LLVM=1', 'CC=clang --sysroot=' + str(WORK / 'target-sysroot'),
            'M=' + str(WORK / 'module'), '-j2', 'modules']
    env = dict(os.environ, PATH='/usr/lib/llvm-19/bin:/usr/bin:/bin', LC_ALL='C', TZ='UTC',
               KBUILD_BUILD_USER='tb371fc-research', KBUILD_BUILD_HOST='isolated-builder',
               KBUILD_BUILD_VERSION='1', KBUILD_BUILD_TIMESTAMP='2026-11-23 00:00:00 +0000',
               SOURCE_DATE_EPOCH='1795392000')
    save('build-invocation.json', {'command': argv, 'uid': 1000, 'gid': 1000,
                                  'supplementary_groups': [], 'timeout_seconds': 600})
    process = subprocess.Popen(argv, env=env, preexec_fn=drop_identity, start_new_session=True)
    timed_out = False
    try:
        process.wait(timeout=600)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
    pins()
    save('build-result.json', {'exit_code': process.returncode, 'timed_out': timed_out,
                               'qualified_r4_inputs_still_match': True})
    raise SystemExit(124 if timed_out else process.returncode)


def inspect():
    if json.loads((WORK / 'build-result.json').read_text())['exit_code'] != 0:
        raise ValueError('successful compilation required')
    pins()
    path = WORK / 'module/snd-soc-tfa98xx.ko'
    header = path.read_bytes()[:64]
    if header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 183:
        raise ValueError('prototype module is not AArch64 ELF64')
    metadata = {key: subprocess.check_output(['/usr/sbin/modinfo', '-F', key, str(path)], text=True).strip()
                for key in ('vermagic', 'depends', 'alias', 'parm', 'signer', 'firmware')}
    if not metadata['vermagic'].startswith(RELEASE + ' ') or 'nxp,tfa9894' not in metadata['alias'] or metadata['signer']:
        raise ValueError('unexpected module identity or signed prototype')
    expected = {line.split()[1]: int(line.split()[0], 16)
                for line in (BASE / 'kernel-out/Module.symvers').read_text().splitlines()}
    versions = subprocess.check_output(['/usr/sbin/modprobe', '--show-modversions', str(path)], text=True)
    imported = []
    for line in versions.splitlines():
        crc, name = line.split()
        if int(crc, 16) != expected.get(name):
            raise ValueError('imported CRC differs: ' + name)
        imported.append({'symbol': name, 'crc': crc})
    if not imported or sha(WORK / 'kernel-out/.config') != PINS[BASE / 'kernel-out/.config']:
        raise ValueError('missing CRC evidence or changed build configuration')
    sections = subprocess.check_output(['/usr/lib/llvm-19/bin/llvm-readelf', '-SW', str(path)], text=True)
    jobs = {}
    for phase in ('prepare', 'build'):
        record = JOBS / ('tfa-prototype-' + phase + '-01.json')
        log = record.with_suffix('.log')
        data = json.loads(record.read_text())
        if data['exit_code'] != 0:
            raise ValueError('unsuccessful prerequisite: ' + phase)
        jobs[phase] = {**data, 'metadata_sha256': sha(record), 'log_sha256': sha(log),
                       'log_size': log.stat().st_size}
    report = {'schema_version': 1, 'evidence_class': 'host_build',
        'recipe_sha256': sha(__file__), 'jobs': jobs,
        'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'kernel_release': RELEASE, 'prepared': json.loads((WORK / 'prepared.json').read_text()),
        'module': {'path': str(path), 'sha256': sha(path), 'size': path.stat().st_size,
                   'elf_machine': 183, 'metadata': metadata, 'btf_section_present': ' .BTF ' in sections},
        'imported_crcs': imported, 'all_imported_crcs_match': True,
        'compiled_configuration_sha256': sha(WORK / 'kernel-out/.config'),
        'qualified_r4_inputs_after': pins(), 'module_signed': False, 'module_installed': False,
        'module_loaded': False, 'firmware_given_to_driver': False, 'device_tree_changed': False,
        'physical_audio_tested': False, 'complete_mtp_write_prevention_proven': False,
        'limits': ['The historical three MTP guards are retained; their completeness and every raw-register/container path are not established.',
                   'An unsigned out-of-tree prototype is not part of the 84 signed modules or the Fedora runtime.',
                   'No QS/YC per-amplifier assignment, firmware acceptance, calibration, DAI/TDM routing or playback has been tested.']}
    save('tfa-module-prototype.json', report)
    print(json.dumps({'compiled': True, 'module_sha256': sha(path), 'imported_crcs': len(imported),
                      'btf': report['module']['btf_section_present'], 'physical_audio_tested': False}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('prepare', 'build', 'inspect'))
    globals()[parser.parse_args().phase]()
