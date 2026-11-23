#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Qualify a new copy of the prepared R4F root after its first image timeout.

No guest program is executed. The old prepared root, archives, failed image,
recipe and records remain inputs. Native cp preserves ACLs/xattrs/ownership;
canonical tar streams and a before/after source metadata inventory qualify the
copy. Reflink is requested opportunistically, never claimed to have succeeded.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess

SOURCE = Path('/work/fedora-input-system-v9')
SOURCE_ROOT = SOURCE / 'rootfs'
RECIPE = Path('/work/fedora-input-system-recipe-r4-v7')
WORK = Path('/work/fedora-input-system-v9-recovery-01')
ROOT = WORK / 'rootfs'
FAILED = Path('/work/fedora-r4f-image-failure-evidence-v1/fedora-r4f-image-failed.json')
FAILED_SHA = '79390c4bf78de7f806cbc26109faf8df870fea3d7cce5b3ffb3db7e99b5806e9'
RECIPE_SHA = '927fd0755f54f303adac25daa8342bfe4615d0d42ff9a07361d29226f7cdf947'
PACKAGES_SHA = '6daee65e1e3b07e7aee764b2ec4bc75cac2864f47fa7372b709097782a20bdaa'
RELEASE = '6.12.114-tb371fc-research4-system'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def identity(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('ordinary input required: ' + str(path))
    return {'size': info.st_size, 'sha256': sha(path)}


def save(name, value):
    with (WORK / name).open('x') as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write('\n')


def guard():
    for path in (SOURCE, SOURCE_ROOT, RECIPE, SOURCE / 'kernel-inputs'):
        if path.is_symlink() or not path.is_dir():
            raise ValueError('ordinary source directory required: ' + str(path))
    if identity(FAILED)['sha256'] != FAILED_SHA:
        raise ValueError('the exact already-retained failure is required')
    failed = json.loads(FAILED.read_bytes())
    if (failed.get('status') != 'host_image_creation_failed_before_any_vm' or
            failed.get('vm_runs') != 0 or failed['pipeline']['exit_code'] != 1):
        raise ValueError('wrong predecessor failure scope')
    manifest_path = RECIPE / 'recipe-manifest.json'
    if identity(manifest_path)['sha256'] != RECIPE_SHA:
        raise ValueError('original executed recipe changed')
    manifest = json.loads(manifest_path.read_bytes())
    if len(manifest) != 20:
        raise ValueError('twenty executed sources required')
    for name, item in manifest.items():
        if '/' in name or name in ('.', '..') or identity(RECIPE / name) != item:
            raise ValueError('original executed source changed: ' + name)
    for name, item in failed['qualified_predecessor_inputs'].items():
        if '/' in name or identity(SOURCE / name) != item['identity']:
            raise ValueError('prepared input metadata changed: ' + name)
    retained = failed['retained_files']
    for name, public in (('pipeline.exit.json', 'fedora-r4f-image-failed-pipeline.json'),
                         ('jobs/image-01.json', 'fedora-r4f-image-failed-image.json')):
        if identity(SOURCE / name) != retained[public]:
            raise ValueError('predecessor failure changed')
    if identity(SOURCE / 'baseline-records/packages.after.tsv')['sha256'] != PACKAGES_SHA:
        raise ValueError('original Fedora package identities changed')
    return failed


def source_inventory():
    """Detect source writes without treating read-atime changes as mutations."""
    digest, count = hashlib.sha256(), 0
    device = SOURCE_ROOT.lstat().st_dev
    pending = [SOURCE_ROOT]
    while pending:
        path = pending.pop()
        info = path.lstat()
        if info.st_dev != device:
            raise ValueError('unexpected mount within source tree: ' + str(path))
        name = '.' if path == SOURCE_ROOT else path.relative_to(SOURCE_ROOT).as_posix()
        row = [name, info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
               info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns,
               os.readlink(path) if stat.S_ISLNK(info.st_mode) else None]
        digest.update((json.dumps(row, separators=(',', ':'), ensure_ascii=True) + '\n').encode())
        count += 1
        if count > 500000:
            raise ValueError('source inventory bound exceeded')
        if stat.S_ISDIR(info.st_mode):
            pending.extend(sorted(path.iterdir(), key=lambda x: x.name, reverse=True))
    return {'entries': count, 'sha256': digest.hexdigest(), 'atime_included': False}


def canonical(tree, label):
    command = ['timeout', '--signal=TERM', '--kill-after=10s', '1200s', 'tar',
               '--sort=name', '--format=posix',
               '--pax-option=exthdr.name=%d/PaxHeaders/%f,delete=atime,delete=ctime',
               '--numeric-owner', '--acls', '--selinux', '--xattrs', '--xattrs-include=*',
               '-cf', '-', '-C', str(tree), '.']
    digest, size = hashlib.sha256(), 0
    path = WORK / (label + '.stderr')
    with path.open('xb') as log:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log)
        try:
            while block := child.stdout.read(1024**2):
                digest.update(block)
                size += len(block)
            code = child.wait(timeout=20)
            if code:
                raise RuntimeError('canonical stream failed: ' + label + ': ' + str(code))
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.stdout.close()
    if path.stat().st_size:
        raise RuntimeError('canonical stream emitted warnings: ' + label)
    return {'size': size, 'sha256': digest.hexdigest(), 'exit_code': code}


def main():
    failed = guard()
    if WORK.exists() or WORK.is_symlink():
        raise ValueError('fresh recovery prefix required')
    if shutil.disk_usage(WORK.parent).free < 10 * 1024**3:
        raise ValueError('10 GiB free space required before the independent copy')
    WORK.mkdir(mode=0o755)
    record = {'schema_version': 1, 'started_utc': now(), 'complete': False,
              'source_tree': str(SOURCE_ROOT), 'destination_tree': str(ROOT),
              'predecessor_failure': {'path': str(FAILED), **identity(FAILED)},
              'original_recipe_manifest_sha256': RECIPE_SHA,
              'copy_helper': identity(Path(__file__)),
              'copy_method': 'native cp -a --reflink=auto',
              'reflink_used': None, 'guest_program_executed': False,
              'old_partial_image_opened': False, 'old_source_written': False,
              'source_read_atime_changes_are_not_excluded': True}
    try:
        before = source_inventory()
        record['source_metadata_before'] = before
        command = ['timeout', '--signal=TERM', '--kill-after=10s', '1800s',
                   'cp', '-a', '--reflink=auto', '--', str(SOURCE_ROOT), str(ROOT)]
        record['copy_command'] = command
        with (WORK / 'prepared-copy.stderr').open('xb') as log:
            result = subprocess.run(command, stdout=log, stderr=log)
        record['copy_exit_code'] = result.returncode
        if result.returncode or (WORK / 'prepared-copy.stderr').stat().st_size:
            raise RuntimeError('prepared-root copy failed or warned; partial retained')
        record['source_canonical'] = canonical(SOURCE_ROOT, 'prepared-source-canonical')
        record['destination_canonical'] = canonical(ROOT, 'prepared-destination-canonical')
        if record['source_canonical'] != record['destination_canonical']:
            raise ValueError('prepared source/destination canonical streams differ')
        after = source_inventory()
        record['source_metadata_after'] = after
        if before != after:
            raise ValueError('source metadata changed during prepared-root qualification')
        acl = {}
        for name in ('system.posix_acl_access', 'system.posix_acl_default'):
            first = os.getxattr(SOURCE_ROOT / 'var/log/journal', name, follow_symlinks=False)
            second = os.getxattr(ROOT / 'var/log/journal', name, follow_symlinks=False)
            if not first or first != second:
                raise ValueError('journal ACL not preserved')
            acl[name] = {'size': len(first), 'sha256': hashlib.sha256(first).hexdigest(),
                         'source_destination_byte_identical': True}
        record['journal_acls'] = acl
        metadata = {}
        original_records = WORK / 'prepared-predecessor-records'
        original_records.mkdir()
        for name, item in failed['qualified_predecessor_inputs'].items():
            source, destination = SOURCE / name, WORK / name
            saved_original = original_records / name
            shutil.copy2(source, saved_original)
            if identity(saved_original) != item['identity']:
                raise ValueError('retained original metadata changed: ' + name)
            if name in ('initramfs.json', 'maintenance-initramfs.json'):
                # Only the host input location changes. Keep the complete
                # original record above, and bind the copied payload below.
                derived = json.loads(source.read_bytes())
                old_path = Path(derived['path'])
                relative_path = old_path.relative_to(SOURCE_ROOT)
                if relative_path.parts[0] != 'boot' or len(relative_path.parts) != 2:
                    raise ValueError('unexpected original archive location')
                derived['path'] = str(ROOT / relative_path)
                derived['reused_archive_original_record'] = {
                    'path': str(saved_original), **item['identity']}
                derived['original_archive_path'] = str(old_path)
                derived['archive_rebuilt_for_recovery'] = False
                save(name, derived)
            else:
                shutil.copy2(source, destination)
                if identity(destination) != item['identity']:
                    raise ValueError('reused original metadata changed: ' + name)
            metadata[name] = {'original_path': str(source), 'copied_path': str(destination),
                              'original_record': item['identity'],
                              'recovery_record': identity(destination),
                              'only_archive_host_path_rebased':
                                  name in ('initramfs.json', 'maintenance-initramfs.json')}
        (WORK / 'baseline-records').mkdir()
        package_source = SOURCE / 'baseline-records/packages.after.tsv'
        package_destination = WORK / 'baseline-records/packages.after.tsv'
        shutil.copy2(package_source, package_destination)
        if identity(package_destination)['sha256'] != PACKAGES_SHA:
            raise ValueError('copied package identities differ')
        record['reused_metadata'] = metadata
        checked = {}
        for name, suffix in (('initramfs.json', '.img'),
                             ('maintenance-initramfs.json', '-maintenance.img')):
            item = failed['qualified_predecessor_inputs'][name]['record']
            relative = 'boot/initramfs-' + RELEASE + suffix
            actual = identity(ROOT / relative)
            if actual != {'size': item['size_bytes'], 'sha256': item['sha256']}:
                raise ValueError('actual reused archive bytes differ: ' + relative)
            checked[relative] = actual
        for name, digest in (
            ('etc/selinux/targeted/policy/policy.35',
             'ff65a5f262d917891e9c3b85283052e4cb9f6f3cb17e04ab8abf971d2a693798'),
            ('usr/share/tb371fc/system-profile.json',
             failed['qualified_predecessor_inputs']['system-profile.json']['identity']['sha256'])):
            item = identity(ROOT / name)
            if item['sha256'] != digest:
                raise ValueError('prepared runtime identity differs: ' + name)
            checked[name] = item
        original_sources = json.loads((RECIPE / 'recipe-manifest.json').read_bytes())
        for source, relative in (
            ('guest_verify_system.py', 'usr/libexec/tb371fc-r4f-vm-verify.py'),
            ('guest_transient_worker.py', 'usr/libexec/tb371fc-r4f-worker.py'),
            ('transient_protocol.py', 'usr/libexec/tb371fc_transient_protocol.py'),
            ('probe_fd_route_v2.py', 'usr/libexec/tb371fc_fd_route.py'),
            ('guest_result_file.py', 'usr/libexec/tb371fc_result_file.py')):
            item = identity(ROOT / relative)
            if item != original_sources[source]:
                raise ValueError('prepared guest source differs: ' + relative)
            checked[relative] = item
        record['critical_prepared_files'] = checked
        if guard() != failed:
            raise ValueError('original predecessor guard changed')
        record['complete'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        record['finished_utc'] = now()
        save('prepared-copy.json', record)
    qualification = {'schema_version': 1, 'qualified': True,
                     'prepared_copy': identity(WORK / 'prepared-copy.json'),
                     'source_tree': str(SOURCE_ROOT), 'destination_tree': str(ROOT),
                     'canonical_source_destination_identical': True,
                     'canonical_stream': record['source_canonical'],
                     'source_metadata_stable_excluding_atime': True,
                     'journal_acl_bytes_preserved': True,
                     'actual_reused_archive_payloads_rehashed': True,
                     'original_failure_sha256': FAILED_SHA,
                     'old_image_or_root_written': False,
                     'new_image_created': False, 'vm_run': False}
    save('prepared-copy-qualification.json', qualification)
    print(json.dumps({'complete': True, 'work': str(WORK),
                      'record': identity(WORK / 'prepared-copy.json'),
                      'qualification': identity(WORK / 'prepared-copy-qualification.json')}, sort_keys=True))


if __name__ == '__main__':
    main()
