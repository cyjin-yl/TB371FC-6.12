#!/usr/bin/env python3
"""Configure the new test tree, make a native dracut initrd, and an image file.

All paths are fixed under the newly created integration work directory. The
filesystem tool receives a newly and exclusively created ordinary file, never
a block device. No mount, loop device, binfmt registration or host bootloader
is used. Each phase is separate so failures remain observable and recoverable.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from fedora_system import ROOT, WORK, run_guest, save, sha
from stage_runtime import RELEASE, copy_new

HERE = Path(__file__).resolve().parent
IMAGE = WORK / 'fedora45-research1.ext4'
INITRD = ROOT / 'boot' / f'initramfs-{RELEASE}.img'


def preserve_write(relative, text):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        backup = path.with_name(path.name + '.before-tb371fc-integration')
        if backup.exists() or backup.is_symlink():
            raise ValueError('configuration backup already exists')
        path.rename(backup)
    with path.open('x') as stream:
        stream.write(text)


def configure():
    if (WORK / 'configured.json').exists():
        raise ValueError('configuration already completed')
    json.loads((WORK / 'runtime.json').read_text())
    preserve_write('etc/fstab', '# Dedicated new image; not an owner tablet partition map.\nLABEL=tb371fc-f45 / ext4 defaults 0 1\n')
    preserve_write('etc/hostname', 'tb371fc-research-vm\n')
    preserve_write('etc/machine-id', '')
    copy_new(HERE / 'guest_verify.py', ROOT / 'usr/libexec/tb371fc-vm-verify.py')
    preserve_write('etc/systemd/system/tb371fc-validation.service', '''[Unit]
Description=Verify the isolated TB371FC Fedora system image
After=multi-user.target
ConditionKernelCommandLine=tb371fc.vm-phase

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/libexec/tb371fc-vm-verify.py
StandardOutput=journal+console
StandardError=journal+console
TimeoutStartSec=600
''')
    preserve_write('etc/systemd/system/tb371fc-validation.target', '''[Unit]
Description=Isolated ARM64 root filesystem validation
Requires=multi-user.target tb371fc-validation.service
After=multi-user.target tb371fc-validation.service
AllowIsolate=yes
''')
    # The validation unit is entered only by the explicit VM kernel command
    # line; ordinary boot keeps the normal distribution target and security.
    preserve_write('etc/dracut.conf.d/90-tb371fc-research.conf', '''hostonly="no"
hostonly_cmdline="no"
hostonly_default_device="no"
compress="gzip"
add_dracutmodules+=" systemd systemd-initrd rootfs-block kernel-modules selinux "
omit_dracutmodules+=" network-manager network-legacy nfs iscsi "
''')
    run_guest(['/usr/bin/systemd-analyze', 'verify', 'tb371fc-validation.service', 'tb371fc-validation.target'])
    save('configured.json', {'guest_verifier_sha256': sha(HERE / 'guest_verify.py'),
                             'validation_target_is_default': False,
                             'label': 'tb371fc-f45', 'tablet_partition_mapping': None})
    print('FEDORA_SYSTEM_CONFIGURED', flush=True)


def initrd():
    if INITRD.exists() or INITRD.is_symlink():
        raise ValueError('initramfs output already exists')
    # OCI roots contain only the /dev nodes bound by the execution wrapper.
    # Shell process substitution needs these ordinary Linux descriptor links.
    for name, target in {'fd': '/proc/self/fd', 'stdin': '/proc/self/fd/0',
                         'stdout': '/proc/self/fd/1', 'stderr': '/proc/self/fd/2'}.items():
        path = ROOT / 'dev' / name
        if path.is_symlink():
            if path.readlink().as_posix() != target:
                raise ValueError('unexpected device descriptor alias')
        elif path.exists():
            raise ValueError('descriptor alias collides with an existing file')
        else:
            path.symlink_to(target)
    run_guest(['/usr/bin/dracut', '--no-hostonly', '--no-hostonly-cmdline',
               '--no-hostonly-default-device', '--fstab', '--kver', RELEASE,
               '--keep', '--modules', 'systemd systemd-initrd rootfs-block kernel-modules selinux',
               '--gzip', '--include', '/usr/lib/firmware', '/usr/lib/firmware',
               '/boot/' + INITRD.name])
    run_guest(['/usr/bin/lsinitrd', '/boot/' + INITRD.name])
    save('initramfs.json', {'kernel_release': RELEASE, 'path': str(INITRD),
                           'size_bytes': INITRD.stat().st_size, 'sha256': sha(INITRD),
                           'build_environment': 'ARM64 Fedora dracut under qualified PRoot/QEMU',
                           'hostonly': False, 'explicit_firmware_tree_included': True})
    print('FEDORA_INITRAMFS_CREATED', flush=True)


def image():
    if not INITRD.is_file() or not (WORK / 'initramfs.json').is_file():
        raise ValueError('verified initramfs is required first')
    if shutil.disk_usage(WORK).free < 5 * 1024**3:
        raise ValueError('insufficient free space for a separate 4 GiB image')
    with IMAGE.open('xb') as stream:
        stream.truncate(4 * 1024**3)
    if not IMAGE.is_file() or IMAGE.is_symlink() or IMAGE.stat().st_size != 4 * 1024**3:
        raise ValueError('new image is not the expected ordinary file')
    subprocess.run(['/usr/sbin/mkfs.ext4', '-F', '-L', 'tb371fc-f45',
                    '-E', 'lazy_itable_init=0,lazy_journal_init=0',
                    '-d', str(ROOT), str(IMAGE)], check=True)
    subprocess.run(['/usr/sbin/e2fsck', '-fn', str(IMAGE)], check=True)
    save('image.before-boot.json', {'path': str(IMAGE), 'size_bytes': IMAGE.stat().st_size,
                                  'sha256': sha(IMAGE), 'filesystem': 'ext4',
                                  'label': 'tb371fc-f45', 'physical_block_device_used': False})
    print('FEDORA_SYSTEM_IMAGE_CREATED', flush=True)


def repair_initrd():
    """Complete ldconfig outside PRoot, retaining the original image and tree."""
    original = json.loads((WORK / 'initramfs.json').read_text())
    if sha(INITRD) != original['sha256']:
        raise ValueError('original initramfs changed')
    candidates = list((ROOT / 'var/tmp').glob('dracut.*/initramfs'))
    if len(candidates) != 1:
        raise ValueError('exactly one retained dracut tree required')
    tree = candidates[0]
    if not (tree / 'usr/lib/systemd/systemd').is_file():
        raise ValueError('retained tree lacks target systemd')
    cache = tree / 'etc/ld.so.cache'
    if cache.exists() or cache.is_symlink():
        raise ValueError('this repair is only for the missing-cache case')
    # Fedora's ldconfig is a static AArch64 PIE, so QEMU can run it directly.
    # Avoid the nested PRoot chroot translation that caused the observed error;
    # -X leaves existing library links intact and only writes the target cache.
    subprocess.run(['/usr/bin/qemu-aarch64-static', str(ROOT / 'usr/sbin/ldconfig'),
                    '-X', '-r', str(tree)], check=True)
    if not cache.is_file() or cache.stat().st_size < 1024:
        raise ValueError('a real target ld.so.cache was not created')
    listing = subprocess.run(['/usr/bin/qemu-aarch64-static', str(ROOT / 'usr/sbin/ldconfig'),
                              '-p', '-C', str(cache)], check=True, capture_output=True, text=True).stdout
    if 'libc.so.6' not in listing or 'libselinux.so.1' not in listing or 'AArch64' not in listing:
        raise ValueError('target cache lacks expected AArch64 libraries')
    (WORK / 'initramfs-target-ldconfig.txt').write_text(listing)
    firmware = json.loads((ROOT / 'usr/share/tb371fc/stock-firmware-manifest.json').read_text())
    for entry in firmware['files']:
        path = tree / ('usr/' + entry['destination'])
        if not path.is_file() or sha(path) != entry['sha256']:
            raise ValueError('initramfs firmware differs: ' + entry['destination'])
    inventories = {}
    archives = {}
    for name, directory in [('early', tree.parent / 'earlycpio'), ('main', tree)]:
        names = ['.'] + ['./' + str(p.relative_to(directory)) for p in sorted(directory.rglob('*'))]
        archive = WORK / ('initramfs-' + name + '.cpio')
        with archive.open('xb') as output:
            subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '--owner', '0:0', '--quiet'],
                           cwd=directory, input=('\0'.join(names) + '\0').encode(), stdout=output, check=True)
        inventories[name] = names
        archives[name] = archive
    required = ['init', 'usr/lib/systemd/systemd', 'etc/ld.so.cache',
                'var/lib/dracut/hooks/pre-pivot/50-selinux-loadpolicy.sh']
    if any('./' + name not in inventories['main'] for name in required):
        raise ValueError('critical initramfs entry missing')
    replacement = WORK / 'initramfs-with-target-cache.img'
    with replacement.open('xb') as output:
        with archives['early'].open('rb') as stream:
            shutil.copyfileobj(stream, output)
        # The child writes through the shared file descriptor, bypassing the
        # Python buffer. Flush the early cpio prefix before starting gzip.
        output.flush()
        subprocess.run(['gzip', '-n', '-c', str(archives['main'])], stdout=output, check=True)
    original_path = WORK / 'initramfs.from-proot.img'
    INITRD.rename(original_path)
    copy_new(replacement, INITRD)
    (WORK / 'initramfs.json').rename(WORK / 'initramfs.from-proot.json')
    save('initramfs.json', {**original, 'sha256': sha(INITRD), 'size_bytes': INITRD.stat().st_size,
                           'original_sha256': original['sha256'],
                           'target_cache_sha256': sha(cache),
                           'target_cache_created_by': 'Fedora static AArch64 ldconfig 2.44 through QEMU, outside PRoot',
                           'repacked_with': 'native GNU cpio newc and gzip -n; early archive preserved',
                           'critical_entries_verified': required,
                           'firmware_hashes_verified': len(firmware['files']),
                           'archive_entry_counts': {name: len(entries) for name, entries in inventories.items()}})
    save('initramfs-inventory.json', inventories)
    # Retain generated build trees outside the distributable root filesystem.
    # This is a move, with no deletion or compatibility link back into the root.
    retained = WORK / 'retained-dracut-trees'
    retained.mkdir()
    tree.parent.rename(retained / tree.parent.name)
    print('FEDORA_INITRAMFS_TARGET_CACHE_REPAIRED', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('configure', 'initrd', 'repair-initrd', 'image'))
    args = parser.parse_args()
    {'configure': configure, 'initrd': initrd, 'repair-initrd': repair_initrd, 'image': image}[args.phase]()
