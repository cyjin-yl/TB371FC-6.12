#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""One bounded synthetic ext4 qualification of the new result reader.

No QEMU, mount, PRoot, kernel policy load or previous candidate is used.
Only a new 8 MiB image under the required private test prefix is written.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from read_vm_result import extract, GUEST_PATH

WORK = Path('/work/r4e-result-transport-qualification-v1')


def main():
    if Path(__file__).resolve().parent != WORK or WORK.is_symlink():
        raise ValueError('fixed independent qualification prefix required')
    work = WORK / 'synthetic-01'
    work.mkdir(mode=0o700)
    image = work / 'synthetic.ext4'
    with image.open('xb') as stream:
        stream.truncate(8 * 1024**2)
    commands = []

    def command(args):
        result = subprocess.run(args, capture_output=True, timeout=30)
        commands.append({'argv': args, 'exit_code': result.returncode,
                         'stdout': result.stdout.decode(errors='replace'),
                         'stderr': result.stderr.decode(errors='replace')})
        if result.returncode:
            raise RuntimeError('synthetic fixture construction failed')
        return result

    command(['/usr/sbin/mke2fs', '-q', '-F', '-t', 'ext4', str(image)])
    profile = 'a' * 64
    boot = '00000000-0000-0000-0000-000000000001'
    envelope = {
        'schema_version': 1, 'phase': 'verify', 'status': 'pass', 'boot_id': boot,
        'profile_sha256': profile, 'guest_path': GUEST_PATH,
        'writer_context': 'system_u:system_r:sysadm_t:s0', 'writer_pid': 2,
        'file_metadata': {'uid': 0, 'gid': 0, 'mode': 0o600, 'nlink': 1,
                          'inode_selinux_context': 'system_u:object_r:var_lib_t:s0'},
        'host_full_log_qualification_pending': True, 'complete_system_accepted': False,
        'physical_hardware_tested': False, 'result': {'synthetic_fixture_only': True},
        'progress': [{'stage': 'synthetic', 'details': {'text': 'full newline\nJSON kept in file'}}],
        'failure': None,
    }
    payload = (json.dumps(envelope, sort_keys=True, separators=(',', ':')) + '\n').encode()
    source = work / 'payload.json'
    source.write_bytes(payload)
    source.chmod(0o600)
    instructions = work / 'debugfs.commands'
    instructions.write_text('\n'.join([
        'mkdir /var', 'mkdir /var/lib', 'mkdir /var/lib/tb371fc-r4e-proof',
        'set_inode_field /var/lib/tb371fc-r4e-proof mode 040700',
        'write ' + str(source) + ' ' + GUEST_PATH,
    ]) + '\n')
    command(['/usr/sbin/debugfs', '-w', '-f', str(instructions), str(image)])
    digest = hashlib.sha256(payload).hexdigest()
    receipt = ('TB371FC_R4E_VM_FILE status=pass boot_id=' + boot + ' profile_sha256=' + profile +
               ' sha256=' + digest + ' bytes=' + str(len(payload)) + ' END')
    serial = ('[ 1.1] unrelated kernel console line\r\n' + receipt + '\r\n').encode()
    positive = work / 'positive'
    positive.mkdir(mode=0o700)
    identity_before = hashlib.sha256(image.read_bytes()).hexdigest()
    value = extract(image, positive, serial, profile)
    identity_after = hashlib.sha256(image.read_bytes()).hexdigest()
    if not value['qualified'] or value['envelope'] != envelope or identity_before != identity_after:
        raise RuntimeError('actual ext4 positive read did not preserve exact file/image bytes')
    cases = {'exact_closed_ext4_file': {'passed': True,
                'source_image_sha256_before_and_after': identity_before,
                'receipt': value['receipt'], 'guest_inode': value['guest_inode']}}

    def rejected(name, candidate_image, candidate_serial):
        destination = work / name
        destination.mkdir(mode=0o700)
        try:
            extract(candidate_image, destination, candidate_serial, profile)
        except (ValueError, RuntimeError, FileNotFoundError) as error:
            cases[name] = {'passed': True, 'rejected': True,
                           'error_type': type(error).__name__, 'message': str(error)}
        else:
            raise RuntimeError('invalid transport case was accepted: ' + name)

    rejected('duplicate_receipt', image, serial + serial)
    rejected('interleaved_receipt', image, serial.replace(b' END', b' [ 9.0] audit interruption END'))
    rejected('wrong_file_digest', image, serial.replace(digest.encode(), b'b' * 64))
    rejected('wrong_boot_in_receipt', image, serial.replace(boot.encode(), b'00000000-0000-0000-0000-000000000002'))
    symlink_image = work / 'symlink.ext4'
    shutil.copyfile(image, symlink_image)
    command(['/usr/sbin/debugfs', '-w', '-R', 'rm ' + GUEST_PATH, str(symlink_image)])
    command(['/usr/sbin/debugfs', '-w', '-R', 'symlink ' + GUEST_PATH + ' /outside-result.json', str(symlink_image)])
    actual_link = command(['/usr/sbin/debugfs', '-R', 'stat ' + GUEST_PATH, str(symlink_image)])
    if b'Type: symlink' not in actual_link.stdout:
        raise RuntimeError('synthetic path-boundary fixture did not create a symlink')
    rejected('symlink_guest_member', symlink_image, serial)
    report = {'schema_version': 1, 'scope': 'synthetic offline ext4 transport only',
              'passed': all(item['passed'] for item in cases.values()), 'cases': cases,
              'commands': commands, 'source': {name: {'size': (WORK / name).stat().st_size,
                  'sha256': hashlib.sha256((WORK / name).read_bytes()).hexdigest()}
                  for name in ('read_vm_result.py', Path(__file__).name)},
              'vm_started': False, 'image_mounted': False, 'old_candidate_modified': False,
              'kernel_policy_loaded_or_written': False, 'physical_hardware_tested': False,
              'limits': ['Synthetic evidence-file qualification is not a VM/system gate pass.',
                         'Guest writer syscall/domain/runtime qualification still requires the new VM.']}
    target = work / 'result.json'
    with target.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'passed': report['passed'], 'cases': len(cases),
                      'report_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                      'report_size': target.stat().st_size}, sort_keys=True))


if __name__ == '__main__':
    main()
