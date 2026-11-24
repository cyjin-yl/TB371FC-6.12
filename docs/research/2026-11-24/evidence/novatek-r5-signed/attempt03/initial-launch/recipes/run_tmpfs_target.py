#!/usr/bin/env python3
"""Run the published offline Novatek gate in a new, bounded tmpfs helper.

The launcher supplies only public read-only inputs and a fresh evidence sink.
No module is loaded, no guest OS is booted, and no tablet is accessed.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import time

EVIDENCE = Path('/evidence')
PREPARATION = EVIDENCE / 'preparation'
REPO = Path('/inputs/repo')
SIGNED = Path('/inputs/signed-stage')
ARCHIVE = Path('/inputs/runtime.canonical.tar')
ROOT = Path('/work/fedora-system-integration-v1/rootfs')
WORK = Path('/work/r5-novatek-depmod-c1296-run03')
ARCHIVE_BYTES = 1323141120
ARCHIVE_SHA = '1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96'
SIGNED_REPORT_SHA = '405e92520d641dbf967630935c886ce664a013ced959926a13cdf25ca6606683'
JOURNAL_ACL_SHA = 'fc742256255ddf9fd3878c1a93c0a2f49b1f9cf2793a30b23ea9d64ea5740aff'
EXPECTED_SOURCE = {
    'scripts/research/input/signing/stage_r5_novatek.py': '12b95c75b1b2b7939b0cfbedf6e97353a67a43bb3d48748c44553a91ddee856b',
    'scripts/research/input/signing/target_r5_depmod.py': 'b1a93d57cedfb0dee57cffa7411d95b96b1f0f1f92d18b99f393fd7d38074cf9',
    'scripts/research/input/signing/runtime_archive.py': '07d2c015a1fc267a28db228e1dd43009568c112ff7216e89fda231aa95456ef0',
    'scripts/research/input/signing/stage_signed.py': 'ad270d83f89ce08d2488906b8246167227e0e352a91294042489d0a0737908df',
    'scripts/research/qualify_boot_bundle.py': '5cd0c3f649ace02c1d8f7166ebefb3c9710f7d3eb7bb9f2b034cab5122eb7210',
    'scripts/research/boot_rootfs.py': '6bcfb231179f2c2495e45d93cd4b6503c7f6408c5901ce1898533d2e8ad8a806',
    'scripts/research/rootfs/stage_r5_fedora.py': '4a4f8ea16a154b6ef2cfcb49766412c99df5d3ca3945cfc691841f3a8060fbfb',
    'scripts/research/boot_formats.py': 'b0936334329df6bab43fe47a5536c3cb4e279804163ffb880987530166c3d64e',
    'scripts/research/derive_boot_candidate.py': 'b77daada7463320e68f1a4b52679da0a03be97cf60167095002582fc250dbd1c',
    'docs/research/2026-11-23/boot-candidate-r5.json': 'cbd40dbd9acdf26645c11647fb29079e5c4c8f8d1a6fadafaf154d3a3e72570b',
}
PINS = {
    '/work/fedora-system-integration-v1/fedora-system-integration.json': '66ac854b2bc938aed147afe0355b57fcbba856c874e9d82cec4cad663b1c87d9',
    '/work/fedora-system-integration-v1/runtime.json': '10a373bfc3291aabe564c8f7af90265900763eadfe3167a7384cc4dcd596544b',
    '/work/fedora-system-integration-v1/vm-verify-01/result.json': '223f73b253a48995dd238575e64aad055e11f311c658aa03534b49c570095675',
    '/work/fedora-proot-src/src/proot': '313e45ea76e65687f543c18d873216310969ec204390e2d817bec263d7b3168f',
    '/usr/bin/qemu-aarch64': '73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943',
}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(path):
    require(stat.S_ISREG(path.lstat().st_mode), 'ordinary file required: ' + str(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'bytes': path.stat().st_size, 'sha256': digest}


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.pending-' + str(os.getpid()))
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def interrupted(number, unused_frame):
    raise InterruptedError('helper received signal ' + str(number))


def command(name, argv, timeout, env=None):
    record = {'argv': list(map(str, argv)), 'started_utc': utc(), 'timeout_seconds': timeout}
    child = None
    try:
        with (PREPARATION / (name + '.stdout')).open('xb') as out, \
             (PREPARATION / (name + '.stderr')).open('xb') as err:
            child = subprocess.Popen(record['argv'], stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err, env=env, start_new_session=True)
            record['exit_code'] = child.wait(timeout=timeout)
        require(record['exit_code'] == 0, name + ' failed: ' + str(record['exit_code']))
    except BaseException as error:
        record['failure'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=10)
            record['exit_code_after_cleanup'] = child.returncode
        record['finished_utc'] = utc()
        atomic_json(PREPARATION / (name + '.json'), record)
    return (PREPARATION / (name + '.stdout')).read_text().strip()


def mount_records():
    records = {}
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        before, after = line.split(' - ', 1)
        fields, extra = before.split(), after.split()
        records[fields[4]] = {'options': fields[5].split(','), 'filesystem': extra[0]}
    return records


def export_target_text():
    destination = EVIDENCE / 'target'
    destination.mkdir()
    files, total = [], 0
    if WORK.exists():
        for path in sorted(WORK.iterdir()):
            if not stat.S_ISREG(path.lstat().st_mode):
                continue
            require(path.suffix in ('.json', '.stdout', '.stderr'),
                    'unexpected top-level target artifact: ' + path.name)
            size = path.stat().st_size
            require(size <= 2 * 1024**2 and total + size <= 16 * 1024**2,
                    'target text export bound exceeded')
            data = path.read_bytes()
            data.decode('utf-8')
            with (destination / path.name).open('xb') as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())
            files.append({'name': path.name, **identity(destination / path.name)})
            total += size
    atomic_json(EVIDENCE / 'target-export.json', {'utc': utc(), 'complete': True,
                                                 'files': files, 'total_bytes': total})
    return files


def main():
    PREPARATION.mkdir()
    report = {'schema': 'tb371fc-novatek-tmpfs-controller-v1', 'started_utc': utc(),
              'complete': False, 'phase': 'preflight', 'physical_hardware_tested': False,
              'module_loaded': False, 'gate_source_patched_by_controller': False,
              'runtime_comparison_mode': 'reference_archive_unique_pax_order',
              'target_outer_timeout_seconds': 2400, 'target_executed': False,
              'worker_source': identity(Path(__file__))}
    report['locale_environment'] = {name: os.environ[name] for name in
                                    ('LANG', 'LC_ALL', 'LC_CTYPE', 'TZ') if name in os.environ}
    result_path = EVIDENCE / 'runner.json'
    atomic_json(result_path, report)
    exit_code = 1
    try:
        require(os.geteuid() == 0, 'numeric ownership requires root in this helper')
        mounts = mount_records()
        report['mounts'] = mounts
        for path in ('/work', '/tmp'):
            require(mounts[path]['filesystem'] == 'tmpfs' and
                    'rw' in mounts[path]['options'] and 'noexec' not in mounts[path]['options'],
                    'writable executable tmpfs required: ' + path)
        for path in ('/usr', '/inputs/repo', '/inputs/signed-stage',
                     '/inputs/runtime.canonical.tar', '/inputs/archive-receipt.json',
                     '/inputs/archive-pipeline.json', '/inputs/source.exit', '/inputs/source.stderr',
                     '/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu',
                     *[name for name in PINS if name.startswith('/work/')]):
            require(path in mounts and 'ro' in mounts[path]['options'],
                    'explicit read-only input bind required: ' + path)
        require(not ROOT.exists() and not WORK.exists(), 'fresh RAM roots required')
        report['pinned_inputs'] = {}
        for name, digest in PINS.items():
            observed = identity(Path(name))
            require(observed['sha256'] == digest, 'pinned input differs: ' + name)
            report['pinned_inputs'][name] = observed
        report['host_tools'] = {}
        for name in ('python3', 'tar', 'cp', 'openssl', 'git', 'timeout', 'sha256sum'):
            found = shutil.which(name)
            require(found is not None, 'missing host command: ' + name)
            path = Path(found).resolve(strict=True)
            require(path.is_relative_to('/usr'), 'host tool outside public /usr: ' + str(path))
            report['host_tools'][name] = {'path': str(path), **identity(path)}
        env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
        source_contract = json.loads(Path('/recipes/source-contract.json').read_text())
        require(set(source_contract) == {'commit', 'tree'} and all(
            isinstance(value, str) and len(value) == 40 and all(c in '0123456789abcdef' for c in value)
            for value in source_contract.values()), 'explicit published source commit/tree required')
        report['source_contract'] = source_contract
        git = ['git', '-c', 'safe.directory=' + str(REPO), '-c', 'core.fsmonitor=false', '-C', str(REPO)]
        report['source_head'] = command('source-head', git + ['rev-parse', 'HEAD'], 15, env)
        report['source_tree'] = command('source-tree', git + ['rev-parse', 'HEAD^{tree}'], 15, env)
        report['source_tracked_status'] = command('source-status', git + ['status', '--porcelain', '--untracked-files=no'], 30, env)
        require(report['source_head'] == source_contract['commit'] and report['source_tree'] == source_contract['tree'] and
                report['source_tracked_status'] == '', 'executed source does not match published source/tree')
        report['source_files'] = {}
        for name, digest in EXPECTED_SOURCE.items():
            observed = identity(REPO / name)
            require(observed['sha256'] == digest, 'source byte identity differs: ' + name)
            report['source_files'][name] = observed
        stage_identity = identity(SIGNED / 'r5-novatek-stage.json')
        require(stage_identity['sha256'] == SIGNED_REPORT_SHA and stage_identity['bytes'] == 22669,
                'the actual signed run02 receipt is required')
        report['signed_stage_receipt'] = stage_identity
        stream = json.loads(Path('/inputs/archive-receipt.json').read_text())
        pipeline = json.loads(Path('/inputs/archive-pipeline.json').read_text())
        require(pipeline['source_exit_code'] == 0 and
                Path('/inputs/source.exit').read_text().strip() == '0' and
                Path('/inputs/source.stderr').stat().st_size == 0,
                'completed warning-free producer with exit 0 is required')
        require(stream.get('archive_identity_verified') is True and
                stream.get('archive', {}).get('bytes') == ARCHIVE_BYTES and
                stream.get('archive', {}).get('sha256') == ARCHIVE_SHA,
                'the bounded receiver must have accepted the complete canonical archive')
        report['original_stream_proofs'] = {'pipeline': pipeline,
                                            'ssd_receiver_complete': stream.get('complete'),
                                            'ssd_receiver_phase': stream.get('phase'),
                                            'archive_receipt_identity': identity(Path('/inputs/archive-receipt.json'))}
        require(stat.S_ISREG(ARCHIVE.lstat().st_mode) and ARCHIVE.stat().st_size == ARCHIVE_BYTES,
                'ordinary archive with exact length required')
        observed = command('archive-sha256', ['sha256sum', str(ARCHIVE)], 180).split()[0]
        require(observed == ARCHIVE_SHA, 'read-only canonical archive bytes changed')
        report['archive'] = {'bytes': ARCHIVE_BYTES, 'sha256': observed}
        # Inspect metadata only. Never materialize the entire archive in Python memory.
        members, data_pages = 0, 0
        with tarfile.open(ARCHIVE, 'r:') as archive:
            for member in archive:
                members += 1
                require(members <= 200000, 'unexpected archive member count')
                if member.isfile():
                    data_pages += ((member.size + 4095) // 4096) * 4096
        estimate = 2 * data_pages + 2 * members * 4096 + 512 * 1024**2 + 12 * 1024**2
        report['memory_estimate'] = {'archive_members': members, 'one_tree_data_pages_bytes': data_pages,
                                     'two_trees_plus_conservative_metadata_and_tools_bytes': estimate,
                                     'container_memory_limit_bytes': 4 * 1024**3}
        require(estimate < 4 * 1024**3, 'conservative two-tree estimate exceeds fixed 4 GiB limit')
        report['phase'] = 'extract'
        atomic_json(result_path, report)
        ROOT.mkdir(mode=0o700)
        command('extract-runtime', ['tar', '--extract', '--file', str(ARCHIVE), '--directory', str(ROOT),
                                   '--numeric-owner', '--same-owner', '--same-permissions', '--acls',
                                   '--selinux', '--xattrs', '--xattrs-include=*', '--delay-directory-restore'], 600)
        require((PREPARATION / 'extract-runtime.stderr').stat().st_size == 0,
                'RAM extraction emitted metadata diagnostics')
        report['journal_acls'] = {}
        for name in ('system.posix_acl_access', 'system.posix_acl_default'):
            data = os.getxattr(ROOT / 'var/log/journal', name, follow_symlinks=False)
            value = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            require(value == {'bytes': 52, 'sha256': JOURNAL_ACL_SHA}, 'journal ACL differs: ' + name)
            report['journal_acls'][name] = value
        report['phase'] = 'original_target_gate'
        report['target_executed'] = True
        atomic_json(result_path, report)
        argv = [sys.executable, '-B', '-O', str(REPO / 'scripts/research/input/signing/target_r5_depmod.py'),
                '--repo', str(REPO), '--signed-stage', str(SIGNED), '--work', str(WORK),
                '--reference-runtime-archive', str(ARCHIVE)]
        command('target-gate', argv, 2400)
        target = json.loads((WORK / 'r5-novatek-target-depmod.json').read_text())
        require(target.get('complete') is True and target.get('target_depmod_verified') is True and
                target.get('module_loaded') is False and target.get('inputs_unchanged') is True,
                'original target gate did not report completion')
        report['target_result'] = identity(WORK / 'r5-novatek-target-depmod.json')
        report['complete'] = True
        report['phase'] = 'verified'
        exit_code = 0
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        try:
            report['exported_target_files'] = export_target_text()
            report['text_export_complete'] = True
        except BaseException as error:
            report['text_export_complete'] = False
            report['export_failure'] = {'type': type(error).__name__, 'message': str(error)}
            report['complete'] = False
            exit_code = 1
        report['finished_utc'] = utc()
        report['exit_code'] = exit_code
        for name in ('memory.current', 'memory.peak', 'memory.events', 'memory.max', 'memory.swap.max'):
            path = Path('/sys/fs/cgroup') / name
            if path.is_file():
                report.setdefault('cgroup_at_finish', {})[name] = path.read_text().strip()
        atomic_json(result_path, report)
        with (EVIDENCE / 'runner.exit').open('x') as stream:
            stream.write(str(exit_code) + '\n')
        print(json.dumps({'complete': report['complete'], 'exit_code': exit_code,
                          'phase': report['phase'], 'failure': report.get('failure')}), flush=True)
    return exit_code


if __name__ == '__main__':
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, interrupted)
    sys.exit(main())
