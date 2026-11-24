#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a fresh research4 dracut archive and ordinary ext4 image file."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from system_common import IMAGE, LABEL, PROFILE, QEMU, ROOT, WORK, check, copy_new, preserve_write, profile, run_guest, save, sha

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / 'verify_initramfs.py'
VALIDATOR_SHA = '263866a1943cd43116e69cb0a8b1081d6ccd1cc93ef98866a4b3eacc00bac58a'
POLICY_SOURCE = Path('/work/selinux-standard-services-20261123/build-01/candidate/etc/selinux/targeted/policy/policy.35')
POLICY_SHA = '727cd98e5b9e13deb9999dedd17fcd95f73c01aa1541c97e9bda127df02a6502'
ORIGINAL_POLICY_SHA = '928dd639a610e600318f48db67e5724e85b93ae21a473199ac91e960775a5430'


def install_policy_candidate():
    """Archive the copied old payload, then replace only this candidate's policy."""
    destination = ROOT / 'etc/selinux/targeted/policy/policy.35'
    backup = ROOT / 'usr/share/tb371fc/research1-policy-archive/policy.35'
    pending = destination.with_name('policy.35.tb371fc-r4e-pending')
    check(destination, ORIGINAL_POLICY_SHA, 3835432)
    original_mode = destination.stat().st_mode & 0o7777
    check(POLICY_SOURCE, POLICY_SHA, 3835456)
    copy_new(destination, backup)
    copy_new(POLICY_SOURCE, pending)
    pending.chmod(original_mode)
    pending.replace(destination)
    check(backup, ORIGINAL_POLICY_SHA, 3835432)
    check(destination, POLICY_SHA, 3835456)
    save('policy-replacement.json', {'only_replaced_path': 'etc/selinux/targeted/policy/policy.35',
        'original_sha256': ORIGINAL_POLICY_SHA, 'original_preserved_in_candidate': str(backup),
        'candidate_sha256': POLICY_SHA, 'candidate_source': str(POLICY_SOURCE),
        'source_original_written': False, 'old_profiles_written': False})


def configure():
    if (WORK / 'configured.json').exists():
        raise ValueError('this independent tree is already configured')
    data = profile()
    preserve_write('etc/fstab', '# Separate research4 image; no owner tablet partition map.\n'
                   f'LABEL={LABEL} / ext4 defaults 0 1\n')
    preserve_write('etc/hostname', 'tb371fc-research4-vm\n')
    preserve_write('etc/machine-id', '')
    copy_new(HERE / 'guest_verify_system.py', ROOT / 'usr/libexec/tb371fc-r4e-vm-verify.py')
    copy_new(HERE / 'guest_transient_worker.py', ROOT / 'usr/libexec/tb371fc-r4e-worker.py')
    copy_new(HERE / 'transient_protocol.py', ROOT / 'usr/libexec/tb371fc_transient_protocol.py')
    copy_new(HERE / 'probe_fd_route_v2.py', ROOT / 'usr/libexec/tb371fc_fd_route.py')
    copy_new(HERE / 'guest_result_file.py', ROOT / 'usr/libexec/tb371fc_result_file.py')
    install_policy_candidate()
    proof_directory = ROOT / 'var/lib/tb371fc-r4e-proof'
    proof_directory.mkdir(mode=0o700)
    preserve_write('etc/systemd/system/tb371fc-r4e-validation.service', '''[Unit]
Description=Verify the independent research4 Fedora management-domain contract
After=multi-user.target
ConditionKernelCommandLine=tb371fc.r4e-phase

[Service]
Type=oneshot
SELinuxContext=system_u:system_r:sysadm_t:s0
ExecStart=/usr/bin/python3 /usr/libexec/tb371fc-r4e-vm-verify.py
StandardOutput=journal+console
StandardError=journal+console
Environment=LC_ALL=C
TasksMax=128
TimeoutStartSec=600
''')
    preserve_write('etc/systemd/system/tb371fc-r4e-validation.target', '''[Unit]
Description=Isolated research4 ARM64 system validation
Requires=multi-user.target tb371fc-r4e-validation.service
After=multi-user.target tb371fc-r4e-validation.service
AllowIsolate=yes
''')
    # The prior generic dracut policy is preserved and replaced in this copy.
    preserve_write('etc/dracut.conf.d/90-tb371fc-research.conf', '''hostonly="no"
hostonly_cmdline="no"
hostonly_default_device="no"
compress="gzip"
add_dracutmodules+=" systemd systemd-initrd rootfs-block kernel-modules selinux "
omit_dracutmodules+=" network-manager network-legacy nfs iscsi "
''')
    run_guest(['/usr/bin/systemd-analyze', 'verify', 'tb371fc-r4e-validation.service', 'tb371fc-r4e-validation.target'])
    save('configured.json', {'profile_sha256': sha(PROFILE),
                             'guest_verifier_sha256': sha(HERE / 'guest_verify_system.py'),
                             'validation_target_is_default': False, 'root_label': LABEL,
                             'kernel_release': data['kernel_release'], 'tablet_partition_mapping': None})
    print('FEDORA_R4E_CONFIGURED', flush=True)


def initrd():
    from early_initramfs import build
    build()


def image():
    data = profile()
    manifest = json.loads((WORK / 'initramfs.json').read_text())
    check(ROOT / 'boot' / f"initramfs-{data['kernel_release']}.img", manifest['sha256'], manifest['size_bytes'])
    if not manifest['archive_verified'] or shutil.disk_usage(WORK).free < 5 * 1024**3:
        raise ValueError('verified initramfs and 5 GiB free space required')
    with IMAGE.open('xb') as stream:
        stream.truncate(4 * 1024**3)
    if IMAGE.is_symlink() or not IMAGE.is_file():
        raise ValueError('new image is not an ordinary file')
    subprocess.run(['/usr/sbin/mkfs.ext4', '-F', '-L', LABEL, '-E',
                    'lazy_itable_init=0,lazy_journal_init=0', '-d', str(ROOT), str(IMAGE)],
                   check=True, timeout=600)
    subprocess.run(['/usr/sbin/e2fsck', '-fn', str(IMAGE)], check=True, timeout=120)
    save('image.before-boot.json', {'path': str(IMAGE), 'size_bytes': IMAGE.stat().st_size,
                                  'sha256': sha(IMAGE), 'filesystem': 'ext4', 'label': LABEL,
                                  'physical_block_device_used': False})
    print('FEDORA_R4E_IMAGE_CREATED', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('configure', 'initrd', 'image'))
    arguments = parser.parse_args()
    {'configure': configure, 'initrd': initrd, 'image': image}[arguments.phase]()
