#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build the fixed ARM64 early-SELinux helper in a fresh container directory.

This builds an ordinary ELF file. It never runs PID 1, loads a kernel policy,
mounts a filesystem, modifies a rootfs, or changes the host toolchain. The
Fedora libselinux development RPM is extracted as data, never installed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import time
import urllib.request

SOURCE_SHA256 = '6006a0fade3e9e8cc9201b5549cab3339961931feadb842c0f3d5863dc383726'
RPM_URL = ('https://kojipkgs.fedoraproject.org/packages/libselinux/3.11/5.fc45/'
           'aarch64/libselinux-devel-3.11-5.fc45.aarch64.rpm')
RPM_BYTES = 128120
RPM_SHA256 = '60383ef415eee73f0f2cad12e81010f6a6c2bf810dfed7b3c61f585ea772e6da'
HEADER_HASHES = {
    'avc.h': 'b8cbacb883bcfd10b5827d24da47d21f1974f4de160b787210d35471a5ebd524',
    'context.h': 'bba43da28c95e6018673550318a679e501c9e659851ed3ef106337e99bf44827',
    'get_context_list.h': 'e8d9129bf8fc5bb1cb7df250e684b8116f424a743f76e98a63db880243e73c28',
    'get_default_type.h': 'b41c8ffe702794f3e481e2b9b199ee407fe12102eb1ecab9256dc08865a7982b',
    'label.h': 'cc6c7ef62dee069d0206f045551e31e884eee1f707de7ca5af8741973313c2c1',
    'restorecon.h': '452ba2e89e89397a5388acdf4b83954e9b1b7161a11ed69a14a50304a9512bd8',
    'selinux.h': '7e306b900740bacb51f25228cde66cbed277e196ef561cc1feefbd4ddda86ae5',
}
CC = Path('/usr/bin/aarch64-linux-gnu-gcc')
READELF = Path('/usr/bin/readelf')


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError('ordinary file required: ' + str(path))
    return path.read_bytes()


def write_new(path: Path, data: bytes, mode: int = 0o600) -> None:
    with path.open('xb') as stream:
        stream.write(data)
    path.chmod(mode)


def fetch(cache: Path) -> bytes:
    cache.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = cache / RPM_URL.rsplit('/', 1)[-1]
    if path.exists() or path.is_symlink():
        data = regular(path)
    else:
        with urllib.request.urlopen(RPM_URL, timeout=30) as response:
            data = response.read(RPM_BYTES + 1)
        if len(data) != RPM_BYTES or digest(data) != RPM_SHA256:
            raise ValueError('downloaded Fedora header RPM hash/size mismatch')
        write_new(path, data)
    if len(data) != RPM_BYTES or digest(data) != RPM_SHA256:
        raise ValueError('cached Fedora header RPM hash/size mismatch')
    return data


def extract_headers(rpm: bytes, destination: Path) -> list[dict]:
    def header_end(offset: int) -> int:
        if rpm[offset:offset + 4] != b'\x8e\xad\xe8\x01':
            raise ValueError('RPM header magic/version')
        count, size = struct.unpack_from('>II', rpm, offset + 8)
        end = offset + 16 + count * 16 + size
        if end > len(rpm):
            raise ValueError('RPM header bounds')
        return end

    offset = header_end((header_end(96) + 7) & ~7)
    compressed = rpm[offset:]
    if compressed.startswith(b'\x1f\x8b'):
        payload = gzip.decompress(compressed)
    elif compressed.startswith(b'\xfd7zXZ'):
        payload = lzma.decompress(compressed)
    elif compressed.startswith(b'\x28\xb5\x2f\xfd'):
        payload = subprocess.run(['/usr/bin/zstd', '-q', '-d', '-c'],
                                 input=compressed, capture_output=True,
                                 check=True, timeout=15).stdout
    else:
        raise ValueError('unsupported fixed RPM payload compression')
    if len(payload) > 4 * 1024**2:
        raise ValueError('fixed header payload exceeds size bound')
    position = 0
    found = {}
    while True:
        header = payload[position:position + 110]
        if len(header) != 110 or header[:6] != b'070701':
            raise ValueError('CPIO header')
        fields = [int(header[6 + i * 8:14 + i * 8], 16) for i in range(13)]
        size, name_size = fields[6], fields[11]
        if name_size < 1 or position + 110 + name_size > len(payload):
            raise ValueError('CPIO name bounds')
        raw_name = payload[position + 110:position + 110 + name_size]
        if raw_name[-1:] != b'\0' or b'\0' in raw_name[:-1]:
            raise ValueError('CPIO name termination')
        name = raw_name[:-1].decode('utf-8')
        start = (position + 110 + name_size + 3) & ~3
        if start + size > len(payload):
            raise ValueError('CPIO member bounds')
        content = payload[start:start + size]
        position = (start + size + 3) & ~3
        if name == 'TRAILER!!!':
            break
        name = name.removeprefix('./')
        prefix = 'usr/include/selinux/'
        if not name.startswith(prefix) or not name.endswith('.h'):
            continue
        leaf = name[len(prefix):]
        if leaf not in HEADER_HASHES or leaf in found or not stat.S_ISREG(fields[1]):
            raise ValueError('unexpected/duplicate/nonregular fixed header')
        if digest(content) != HEADER_HASHES[leaf]:
            raise ValueError('Fedora header differs: ' + leaf)
        found[leaf] = content
    if set(found) != set(HEADER_HASHES):
        raise ValueError('incomplete fixed header set')
    target = destination / 'selinux'
    target.mkdir(mode=0o700, parents=True)
    result = []
    for name, content in sorted(found.items()):
        write_new(target / name, content)
        result.append({'path': 'selinux/' + name, 'size': len(content),
                       'sha256': digest(content)})
    return result


def run(argv: list[str], *, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, text=True, capture_output=True, check=True,
                          timeout=60, env=env)


def build(repo: Path, work: Path, cache: Path) -> dict:
    if not work.is_absolute() or work == Path('/') or work.exists() or work.is_symlink():
        raise ValueError('a fresh absolute work directory is required')
    source = regular(repo / 'scripts/research/selinux/early_init.c')
    if digest(source) != SOURCE_SHA256:
        raise ValueError('the source differs from this fixed recipe')
    rpm = fetch(cache)
    work.mkdir(mode=0o700, parents=True)
    result = {
        'schema_version': 1,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'recipe_sha256': digest(Path(__file__).read_bytes()),
        'source_sha256': digest(source),
        'header_rpm': {'url': RPM_URL, 'size': len(rpm), 'sha256': digest(rpm)},
        'hardware_tested': False, 'kernel_policy_load_attempted': False,
        'rootfs_modified': False, 'completed': False,
    }
    try:
        result['headers'] = extract_headers(rpm, work / 'headers')
        source_path, output = work / 'early_init.c', work / 'early-init'
        write_new(source_path, source)
        result['compiler'] = {
            'path': str(CC), 'resolved_path': str(CC.resolve()),
            'sha256': digest(CC.resolve().read_bytes()),
            'version': run([str(CC), '--version']).stdout,
        }
        result['toolchain_packages'] = run([
            '/usr/bin/dpkg-query', '-W', '-f=${Package}\t${Version}\n',
            'gcc-14-aarch64-linux-gnu', 'libc6-dev-arm64-cross',
            'binutils-aarch64-linux-gnu']).stdout
        command = [str(CC), '-std=gnu11', '-O2', '-g0', '-D_FORTIFY_SOURCE=3',
                   '-fPIE', '-fstack-protector-strong', '-fno-ident',
                   '-Wall', '-Wextra', '-Werror', '-I', str(work / 'headers'),
                   str(source_path), '-pie',
                   '-Wl,--build-id=sha1,-z,relro,-z,now,--no-undefined',
                   '-ldl', '-o', str(output)]
        env = dict(os.environ, SOURCE_DATE_EPOCH='1795392000', LC_ALL='C')
        started = time.monotonic()
        process = subprocess.run(command, text=True, capture_output=True,
                                 timeout=60, env=env)
        result['command'] = command
        result['compile_seconds'] = time.monotonic() - started
        result['compile_exit_code'] = process.returncode
        write_new(work / 'compiler.stdout', process.stdout.encode())
        write_new(work / 'compiler.stderr', process.stderr.encode())
        if process.returncode:
            raise ValueError('compiler failed; retained compiler.stderr has the diagnostic')
        binary = regular(output)
        if binary[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', binary, 18)[0] != 183:
            raise ValueError('output is not little-endian ARM64 ELF64')
        details = {}
        for option, name in [('-d', 'dynamic'), ('-l', 'program_headers'), ('-V', 'versions')]:
            text = run([str(READELF), option, str(output)]).stdout
            write_new(work / ('readelf-' + name + '.txt'), text.encode())
            details[name] = text
        needed = re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', details['dynamic'])
        interpreter = re.findall(r'Requesting program interpreter: ([^\]]+)',
                                 details['program_headers'])
        if (needed != ['libc.so.6', 'ld-linux-aarch64.so.1'] or
                interpreter != ['/lib/ld-linux-aarch64.so.1'] or
                '(RPATH)' in details['dynamic'] or '(RUNPATH)' in details['dynamic']):
            raise ValueError('unexpected fixed helper ELF runtime contract')
        output.chmod(0o755)
        result['artifact'] = {
            'path': str(output), 'size': len(binary), 'sha256': digest(binary),
            'mode': '0755', 'elf_machine': 183, 'needed': needed,
            'interpreter': interpreter[0],
            'glibc_versions': sorted(set(re.findall(r'GLIBC_[0-9.]+', details['versions']))),
        }
        result['explicit_dlopen_edges'] = [
            {'from': '/init', 'to': '/usr/lib64/libselinux.so.1'},
            {'from': '/usr/lib64/libselinux.so.1', 'to': 'libsepol.so.2'},
        ]
        result['completed'] = True
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        raise
    finally:
        write_new(work / 'build-result.json',
                  (json.dumps(result, sort_keys=True, indent=2) + '\n').encode())
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    outcome = build(args.repo.resolve(), args.work, args.cache)
    print(json.dumps(outcome, sort_keys=True, indent=2), flush=True)
