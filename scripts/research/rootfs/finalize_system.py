#!/usr/bin/env python3
"""Freeze the actual Fedora integration result without altering its inputs."""
import datetime
import json
from pathlib import Path
import re
import subprocess

from fedora_system import ROOT, WORK, run_guest, save, sha, RPM_FORMAT
from assemble_image import IMAGE, INITRD

JOBS = (
    'fedora-system-prepare-01', 'fedora-system-query-01', 'fedora-system-query-02',
    'fedora-system-install-01', 'fedora-runtime-stage-01', 'fedora-system-configure-01',
    'fedora-system-initrd-01', 'fedora-system-initrd-02', 'fedora-initrd-cache-01',
    'fedora-system-image-01', 'fedora-vm-label-01', 'fedora-system-image-02',
    'fedora-vm-label-02', 'fedora-vm-enforcing-01',
)


def identity(path):
    return {'path': str(path), 'size_bytes': path.stat().st_size, 'sha256': sha(path)}


def main():
    before = (WORK / 'packages.after.tsv').read_text().splitlines()
    now = run_guest(['/usr/bin/rpm', '-qa', '--qf', RPM_FORMAT], capture=True).stdout.splitlines()
    if sorted(before) != sorted(now) or len(now) != 367:
        raise ValueError('installed Fedora package identities changed')
    label = json.loads((WORK / 'vm-label-02/result.json').read_text())
    verify = json.loads((WORK / 'vm-verify-01/result.json').read_text())
    if not label['passed'] or not verify['passed'] or not verify['guest_gates_match']:
        raise ValueError('complete clean-archive labeling/enforcing boot required')
    check = subprocess.run(['/usr/sbin/e2fsck', '-fn', str(IMAGE)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with (WORK / 'filesystem-after-boot.txt').open('x') as stream:
        stream.write(check.stdout)
    jobs = {}
    for name in JOBS:
        meta = Path('/work') / (name + '.json')
        log = Path('/work') / (name + '.log')
        jobs[name] = {'result': json.loads(meta.read_text()),
                      'result_sha256': sha(meta), 'log_sha256': sha(log),
                      'log_bytes': log.stat().st_size}
    runtime = json.loads((WORK / 'runtime.json').read_text())
    runtime.pop('runtime_files')
    text = (WORK / 'vm-verify-01/serial.log').read_text(errors='replace')
    observations = {
        'autofs4_module_warning_count': text.count("Failed to find module 'autofs4'"),
        'pids_max_no_data_warning_count': text.count('Failed to read pids.max'),
        'bpf_lsm_not_supported_count': text.count('BPF LSM not supported'),
        'virtual_gpio_deferred_probe_count': text.count('gpio-keys: failed to get gpio'),
        'selinux_avc_denial_count': len(re.findall(r'\bavc:\s+denied\b', text)),
        'kernel_panic_count': text.count('Kernel panic - not syncing'),
        'invalid_initramfs_count': text.count('rootfs image is not initramfs'),
    }
    artifact_names = ['seed.json', 'package-pins.json', 'packages.before.tsv', 'packages.after.tsv',
                      'runtime.json', 'configured.json', 'initramfs.json',
                      'initramfs-inventory.json', 'archive-order-correction.json',
                      'initrd-01-cancellation.json', 'guest-verifier-revision2.json',
                      'guest-verifier-revision3.json', 'image.before-boot.json',
                      'filesystem-after-boot.txt']
    record = {
        'schema_version': 1,
        'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scope': 'actual generic ARM64 full-system boot of a separately assembled Fedora root; not owner tablet execution',
        'status': 'generic_systemd_enforcing_boot_pass',
        'container': 'tb371fc-build-20261123 in doesvm CT102',
        'kernel_release': runtime['kernel_release'], 'package_count': len(now),
        'package_pins': json.loads((WORK / 'package-pins.json').read_text()),
        'installed_package_identities_reread_match': True,
        'runtime': runtime,
        'initramfs': json.loads((WORK / 'initramfs.json').read_text()),
        'tested_rootfs_after_clean_poweroff': identity(IMAGE),
        'filesystem_after_boot_check_exit': check.returncode,
        'label_vm': label, 'enforcing_vm': verify,
        'jobs': jobs,
        'retained_metadata': {name: identity(WORK / name) for name in artifact_names},
        'final_recipe_files': {p.name: identity(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'observed_warnings': observations,
        'normal_root_configuration': {'selinux': 'enforcing', 'type': 'targeted',
                                      'validation_target_is_default': False,
                                      'automatic_tablet_kexec': False},
        'historical_failures_and_corrections': [
            'DNF5 query format lacked an explicit newline; strict parsing failed before package installation; corrected query preserved separately.',
            'First dracut run lacked descriptor links for shell process substitution; its owned process tree was stopped and its log retained.',
            'Second dracut produced an archive but nested PRoot ldconfig could not make the target cache; retained tree was repaired using Fedora static AArch64 ldconfig outside PRoot.',
            'First native repack buffered the early CPIO prefix until after gzip; the first VM could label the filesystem but reported invalid initramfs magic. This image is retained and is not the accepted candidate.',
            'Corrected prefix order was checked against the original exact early/main archives, a new ext4 image was built, and both labeling and enforcing boots were repeated successfully.',
        ],
        'physical_tablet_modified': False, 'physical_tablet_booted': False,
        'gpu_acceleration_tested': False, 'native_panel_tested': False,
        'independent_bit_identical_rebuild_proven': False,
        'all_hardware_accepted': False,
        'limits': [
            'QEMU virt uses its generated DT and a virtual block device; the Lenovo board DT is packaged only, not executed.',
            'This fixed research1 profile retains disabled native display/touch. The separately signed research2 display/input combination needs its own image integration and hardware validation.',
            'Package identities and artifact hashes are fixed and retained, but complete independent offline or byte-identical recreation is not established.',
            'Virtual boot does not validate firmware authentication, board selection, a physical GPU, sensors, display, input, charging, radio, video codec or suspend.',
            'autofs4, BPF-LSM, pids.max and virtual GPIO warnings remain recorded; zero failed units is not a claim that every optional kernel feature is configured.',
            'The image label describes this new test filesystem, not the owner SD-card partition layout or a demonstrated tablet boot path.',
        ],
    }
    save('fedora-system-integration.json', record)
    print(json.dumps({'status': record['status'], 'package_count': len(now),
                      'rootfs_after_boot': record['tested_rootfs_after_clean_poweroff'],
                      'warnings': observations,
                      'report': identity(WORK / 'fedora-system-integration.json')}, indent=2))


if __name__ == '__main__':
    main()
