#!/usr/bin/python3
"""Bounded validation service for the explicitly marked, private QEMU image.

This program refuses to relabel or power off any system without all three
guards: the exact test command-line token, QEMU's ARM virt DT, and the newly
created test-root label. No Lenovo DT is supplied to this VM.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import traceback

LABEL = 'tb371fc-f45'
RELEASE = '6.12.114-tb371fc-research1'


def run(*args, check=True):
    p = subprocess.run(args, text=True, capture_output=True, check=check)
    return p.stdout.strip()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    words = Path('/proc/cmdline').read_text().split()
    phase = next((x.split('=', 1)[1] for x in words if x.startswith('tb371fc.vm-phase=')), '')
    if phase not in ('label', 'verify'):
        raise RuntimeError('explicit isolated VM phase is absent')
    compatible = Path('/proc/device-tree/compatible').read_bytes().rstrip(b'\0').split(b'\0')
    if b'linux,dummy-virt' not in compatible:
        raise RuntimeError('not the owned generic ARM virt machine')
    root_source = run('/usr/bin/findmnt', '-n', '-o', 'SOURCE', '/')
    root_type = run('/usr/bin/findmnt', '-n', '-o', 'FSTYPE', '/')
    if root_source != '/dev/vda' or root_type != 'ext4':
        raise RuntimeError('unexpected root mount: ' + root_source + ' ' + root_type)
    if run('/usr/sbin/blkid', '-s', 'LABEL', '-o', 'value', root_source) != LABEL:
        raise RuntimeError('root is not the dedicated validation image')
    if platform.machine() != 'aarch64' or platform.release() != RELEASE:
        raise RuntimeError('unexpected architecture/kernel')
    pid1 = os.readlink('/proc/1/exe')
    if pid1 != '/usr/lib/systemd/systemd':
        raise RuntimeError('actual PID1 is not systemd: ' + pid1)
    enforce = Path('/sys/fs/selinux/enforce')
    if not enforce.is_file():
        raise RuntimeError('SELinux control filesystem is not active')
    with Path('/sys/fs/selinux/policy').open('rb') as stream:
        loaded_policy = stream.read(32 * 1024**2 + 1)
    if not 1024 < len(loaded_policy) <= 32 * 1024**2:
        raise RuntimeError('loaded SELinux policy is missing or outside the bound')
    magic, name_length = struct.unpack_from('<II', loaded_policy)
    if magic != 0xf97cff8c or name_length != 8 or loaded_policy[8:16] != b'SE Linux':
        raise RuntimeError('loaded policy has an unexpected binary header')
    loaded_policy_version = struct.unpack_from('<I', loaded_policy, 16)[0]
    if loaded_policy_version != 33:
        raise RuntimeError('loaded policy is not the expected compatible version 33')
    if digest(Path('/etc/selinux/targeted/policy/policy.35')) != '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430':
        raise RuntimeError('Fedora source policy changed')
    if phase == 'label':
        if enforce.read_text().strip() != '0':
            raise RuntimeError('maintenance relabel requires explicit permissive boot')
        # setfiles only labels the new filesystem. Unlike cleanup-oriented
        # convenience wrappers, it does not delete files under /tmp or /var.
        subprocess.run(['/usr/sbin/setfiles', '-F', '-e', '/proc', '-e', '/sys',
                        '-e', '/dev', '-e', '/run',
                        '/etc/selinux/targeted/contexts/files/file_contexts', '/'], check=True)
        os.sync()
        print('TB371FC_VM_LABEL_COMPLETE', flush=True)
    else:
        if enforce.read_text().strip() != '1':
            raise RuntimeError('validation boot must enforce SELinux')
        record = json.loads(Path('/usr/share/tb371fc/runtime.json').read_text())
        for name, expected in record['runtime_files'].items():
            actual = digest(Path('/') / name)
            if actual != expected:
                raise RuntimeError('runtime file changed: ' + name)
        systemd_elf = Path(pid1).read_bytes()[:20]
        if systemd_elf[:6] != b'\x7fELF\x02\x01' or int.from_bytes(systemd_elf[18:20], 'little') != 183:
            raise RuntimeError('PID1 executable is not ELF64 AArch64')
        failed = run('/usr/bin/systemctl', 'list-units', '--failed', '--no-legend', '--plain')
        result = {
            'scope': 'generic ARM64 VM with no physical device passthrough',
            'kernel_release': platform.release(), 'pid1': pid1,
            'root_source': root_source, 'root_type': root_type, 'root_label': LABEL,
            'selinux': run('/usr/sbin/getenforce'),
            'kernel_supported_policy_version': Path('/sys/fs/selinux/policyvers').read_text().strip(),
            'loaded_policy_version': loaded_policy_version,
            'loaded_policy_bytes': len(loaded_policy),
            'loaded_policy_sha256': hashlib.sha256(loaded_policy).hexdigest(),
            'pid1_selinux_context': Path('/proc/1/attr/current').read_text().strip('\0\n'),
            'systemd': run('/usr/bin/systemctl', '--version').splitlines()[0],
            'multi_user_target': run('/usr/bin/systemctl', 'is-active', 'multi-user.target'),
            'udev': run('/usr/bin/systemctl', 'is-active', 'systemd-udevd.service'),
            'dbus': run('/usr/bin/systemctl', 'is-active', 'dbus.service'),
            'module_files_verified': record['module_count'],
            'firmware_files_verified': record['firmware_file_count'],
            'all_runtime_hashes_verified': True,
            'failed_units': failed.splitlines() if failed else [],
            'tablet_hardware_tested': False, 'gpu_acceleration_tested': False,
        }
        if result['pid1_selinux_context'].split(':')[2:3] != ['init_t']:
            raise RuntimeError('systemd did not enter the init_t SELinux domain')
        print('TB371FC_VM_RESULT ' + json.dumps(result, sort_keys=True), flush=True)
        if result['selinux'] != 'Enforcing' or result['failed_units']:
            raise RuntimeError('the complete validation gate did not pass')
        print('TB371FC_VM_SYSTEM_COMPLETE', flush=True)
    # Only reached after the guards and a successful phase. QEMU exits through
    # its virtual PSCI power-off; the host runner still enforces a time bound.
    subprocess.run(['/usr/bin/systemctl', '--no-block', 'poweroff'], check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('TB371FC_VM_VALIDATION_FAILED', flush=True)
        traceback.print_exc()
        sys.exit(1)
