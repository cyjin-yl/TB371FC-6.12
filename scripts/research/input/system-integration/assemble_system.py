#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a fresh research3 dracut archive and ordinary ext4 image file."""
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


def configure():
    if (WORK / 'configured.json').exists():
        raise ValueError('this independent tree is already configured')
    data = profile()
    preserve_write('etc/fstab', '# Separate research3 image; no owner tablet partition map.\n'
                   f'LABEL={LABEL} / ext4 defaults 0 1\n')
    preserve_write('etc/hostname', 'tb371fc-research3-vm\n')
    preserve_write('etc/machine-id', '')
    copy_new(HERE / 'guest_verify_system.py', ROOT / 'usr/libexec/tb371fc-r3-vm-verify.py')
    copy_new(HERE / 'guest_pids_probe.py', ROOT / 'usr/libexec/tb371fc-r3-pids-probe.py')
    preserve_write('etc/systemd/system/tb371fc-r3-validation.service', '''[Unit]
Description=Verify the independent research3 Fedora system image
After=multi-user.target
ConditionKernelCommandLine=tb371fc.r3-phase

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/libexec/tb371fc-r3-vm-verify.py
StandardOutput=journal+console
StandardError=journal+console
Environment=LC_ALL=C
TasksMax=128
TimeoutStartSec=600
''')
    preserve_write('etc/systemd/system/tb371fc-r3-validation.target', '''[Unit]
Description=Isolated research3 ARM64 system validation
Requires=multi-user.target tb371fc-r3-validation.service
After=multi-user.target tb371fc-r3-validation.service
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
    run_guest(['/usr/bin/systemd-analyze', 'verify', 'tb371fc-r3-validation.service', 'tb371fc-r3-validation.target'])
    save('configured.json', {'profile_sha256': sha(PROFILE),
                             'guest_verifier_sha256': sha(HERE / 'guest_verify_system.py'),
                             'validation_target_is_default': False, 'root_label': LABEL,
                             'kernel_release': data['kernel_release'], 'tablet_partition_mapping': None})
    print('FEDORA_R3_CONFIGURED', flush=True)


def initrd():
    data = profile()
    release = data['kernel_release']
    output = ROOT / 'boot' / f'initramfs-{release}.img'
    if output.exists() or output.is_symlink() or (WORK / 'initramfs.json').exists():
        raise ValueError('fresh initramfs output required')
    if list((ROOT / 'var/tmp').glob('dracut.*/initramfs')):
        raise ValueError('unexpected old dracut trees in the new root')
    for name, target in {'fd': '/proc/self/fd', 'stdin': '/proc/self/fd/0',
                         'stdout': '/proc/self/fd/1', 'stderr': '/proc/self/fd/2'}.items():
        path = ROOT / 'dev' / name
        if path.is_symlink():
            if path.readlink().as_posix() != target:
                raise ValueError('unexpected descriptor alias')
        elif path.exists():
            raise ValueError('existing descriptor path is not the expected link')
        else:
            path.symlink_to(target)
    run_guest(['/usr/bin/dracut', '--no-hostonly', '--no-hostonly-cmdline',
               '--no-hostonly-default-device', '--fstab', '--kver', release,
               '--keep', '--modules', 'systemd systemd-initrd rootfs-block kernel-modules selinux',
               '--gzip', '--include', '/usr/lib/firmware', '/usr/lib/firmware',
               '/boot/' + output.name], timeout=900)
    raw_identity = {'sha256': sha(output), 'size': output.stat().st_size}
    trees = list((ROOT / 'var/tmp').glob('dracut.*/initramfs'))
    if len(trees) != 1:
        raise ValueError('exactly one retained target dracut tree required')
    tree = trees[0]
    cache = tree / 'etc/ld.so.cache'
    if cache.exists() or cache.is_symlink():
        cache.rename(WORK / 'initramfs-cache.from-proot')
    subprocess.run([str(QEMU), str(ROOT / 'usr/sbin/ldconfig'), '-X', '-r', str(tree)],
                   check=True, timeout=120)
    if not cache.is_file() or cache.stat().st_size < 1024:
        raise ValueError('real target loader cache missing')
    listing = subprocess.run([str(QEMU), str(ROOT / 'usr/sbin/ldconfig'), '-p', '-C', str(cache)],
                             check=True, capture_output=True, text=True, timeout=60).stdout
    if not all(x in listing for x in ('AArch64', 'libc.so.6', 'libselinux.so.1')):
        raise ValueError('target cache lacks critical AArch64 libraries')
    with (WORK / 'initramfs-target-ldconfig.txt').open('x') as stream:
        stream.write(listing)
    archives = {}
    counts = {}
    for name, directory in (('early', tree.parent / 'earlycpio'), ('main', tree)):
        names = ['.'] + ['./' + p.relative_to(directory).as_posix() for p in sorted(directory.rglob('*'))]
        archive = WORK / ('initramfs-' + name + '.cpio')
        with archive.open('xb') as stream:
            subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '--owner', '0:0', '--quiet'],
                           cwd=directory, input=('\0'.join(names) + '\0').encode(),
                           stdout=stream, check=True, timeout=120)
        archives[name] = archive
        counts[name] = len(names)
    replacement = WORK / 'initramfs-with-target-cache.img'
    with replacement.open('xb') as stream:
        with archives['early'].open('rb') as prefix:
            shutil.copyfileobj(prefix, stream)
        stream.flush()
        subprocess.run(['gzip', '-n', '-c', str(archives['main'])], stdout=stream, check=True, timeout=180)
    check(VALIDATOR, VALIDATOR_SHA)
    spec = importlib.util.spec_from_file_location('frozen_initramfs_validator', VALIDATOR)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validated = validator.verify(replacement, ROOT / 'usr/share/tb371fc/stock-firmware-manifest.json')
    save('initramfs-archive-verification.json', validated)
    if not validated['passed']:
        raise ValueError('actual initramfs archive validation failed')
    output.rename(WORK / 'initramfs.from-proot.img')
    copy_new(replacement, output)
    save('initramfs.json', {'kernel_release': release, 'path': str(output), 'sha256': sha(output),
                           'size_bytes': output.stat().st_size, 'original_proot_archive': raw_identity,
                           'target_cache_sha256': sha(cache), 'archive_entry_counts': counts,
                           'archive_validator_sha256': VALIDATOR_SHA,
                           'archive_verified': True, 'hostonly': False,
                           'cache_created_by': 'Fedora static AArch64 ldconfig through QEMU outside PRoot',
                           'repacked_by': 'GNU cpio newc, flushed early prefix, gzip -n',
                           'physical_hardware_tested': False})
    retained = WORK / 'retained-dracut-trees'
    retained.mkdir()
    tree.parent.rename(retained / tree.parent.name)
    print('FEDORA_R3_INITRAMFS_VERIFIED', flush=True)


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
    print('FEDORA_R3_IMAGE_CREATED', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('configure', 'initrd', 'image'))
    arguments = parser.parse_args()
    {'configure': configure, 'initrd': initrd, 'image': image}[arguments.phase]()
