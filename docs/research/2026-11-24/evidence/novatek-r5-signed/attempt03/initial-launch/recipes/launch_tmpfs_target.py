#!/usr/bin/env python3
"""Prepare and launch one new Novatek tmpfs helper on the existing Docker host.

Review before use. This controller does not change any existing container,
storage property, original gate, source tree, or failed attempt.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import signal
import stat
import subprocess
import sys

GENERAL = 'tb371fc-build-20261123'
SSD = 'tb371fc-build-ssd-20261123'
HELPER = 'tb371fc-novatek-tmpfs-c1296-run03'
EVIDENCE_NAME = 'r5-novatek-tmpfs-evidence-c1296-run03'
OBSERVED_USR = '/tank/docker/doescontainer/docker/overlay2/af1e8d1b0b43bd828ff8759c878c17f267180be32717537b0249777b15c15390/merged/usr'
IMAGE_ID = 'sha256:ec92d6b34c6a7e6372d87dc9ef2fd6e8ca8125353fe7d033c676f51cf923a13b'
WORK_MOUNTS = {
    GENERAL: ('volume', '/tank/docker/doescontainer/docker/volumes/tb371fc-build-20261123/_data'),
    SSD: ('bind', '/tank/hot/tb371fc-build-20261123'),
}
ARCHIVE_BYTES = 1323141120
ARCHIVE_SHA = '1b3f7bd2630bd4721650dd08fd63d14fd44867cc1ee5bdf7ade8a25f28207b96'


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def run(argv, timeout=30):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=timeout, check=False)
    require(len(result.stdout) + len(result.stderr) <= 2 * 1024**2, 'controller command output bound exceeded')
    if result.returncode:
        raise RuntimeError('command failed: ' + argv[0] + ': ' + result.stderr[:2000])
    return result.stdout


def inspect(name):
    values = json.loads(run(['docker', 'inspect', name]))
    require(len(values) == 1, 'one observed Docker object required')
    return values[0]


def work_mount(info, container):
    matches = [item for item in info['Mounts'] if item['Destination'] == '/work']
    kind, expected = WORK_MOUNTS[container]
    require(len(matches) == 1 and matches[0]['Type'] == kind and matches[0]['Source'] == expected,
            'observed /work type/source changed: ' + container)
    path = Path(matches[0]['Source'])
    require(path.is_absolute() and stat.S_ISDIR(path.lstat().st_mode), 'ordinary observed host /work source required')
    return path


def source(work, container_path, kind):
    relative = PurePosixPath(container_path).relative_to('/work')
    require('..' not in relative.parts, 'invalid declared source path')
    path = work.joinpath(*relative.parts)
    mode = path.lstat().st_mode
    require((kind == 'file' and stat.S_ISREG(mode)) or (kind == 'dir' and stat.S_ISDIR(mode)),
            'missing ordinary public input: ' + container_path)
    return path


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.pending-' + str(os.getpid()))
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def interrupted(number, unused_frame):
    raise InterruptedError('launcher received signal ' + str(number))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--source-tree', required=True)
    parser.add_argument('--target-repo', default='/work/r5-novatek-source-c1296-run03')
    args = parser.parse_args()
    for value in (args.source_commit, args.source_tree):
        require(len(value) == 40 and all(c in '0123456789abcdef' for c in value),
                'full published source commit/tree SHAs required')
    require(args.target_repo.startswith('/work/r5-novatek-source-c1296-') and
            args.target_repo != '/work/r5-novatek-source-c1296-run02',
            'use a new checkout for the newly published reference-archive mode')
    require(os.geteuid() == 0, 'run on the observed Docker host as root')
    general, ssd = inspect(GENERAL), inspect(SSD)
    require(general['State']['Running'] and ssd['State']['Running'], 'both input containers must remain running')
    image = ssd['Image']
    require(image == general['Image'] == IMAGE_ID, 'original complete image identity changed')
    usr = Path(ssd['GraphDriver']['Data']['MergedDir']) / 'usr'
    require(str(usr) == OBSERVED_USR and stat.S_ISDIR(usr.lstat().st_mode), 'observed public /usr mount changed')
    general_work, ssd_work = work_mount(general, GENERAL), work_mount(ssd, SSD)
    present = run(['docker', 'container', 'ls', '--all', '--filter', 'name=^/' + HELPER + '$', '--format', '{{.ID}}'])
    require(not present.strip(), 'retain existing helper; this attempt name is already used')
    memory = {line.split(':', 1)[0]: line.split(':', 1)[1].strip()
              for line in Path('/proc/meminfo').read_text().splitlines()}
    available = int(memory['MemAvailable'].split()[0]) * 1024
    require(available >= 10 * 1024**3, 'at least 10 GiB MemAvailable is required')
    archive = source(ssd_work, '/work/r5-novatek-runtime-mirror-c1296-01/runtime.canonical.tar', 'file')
    archive_receipt = source(ssd_work, '/work/r5-novatek-runtime-mirror-c1296-01/receipt.json', 'file')
    pipeline = source(ssd_work, '/work/r5-novatek-runtime-transfer-pipeline-c1296-01.json', 'file')
    source_exit = source(general_work, '/work/r5-novatek-runtime-export-c1296-01/source.exit', 'file')
    source_stderr = source(general_work, '/work/r5-novatek-runtime-export-c1296-01/source.stderr', 'file')
    stream_record = json.loads(archive_receipt.read_text())
    pipeline_record = json.loads(pipeline.read_text())
    require(pipeline_record.get('source_exit_code') == 0 and source_exit.read_text().strip() == '0' and
            source_stderr.stat().st_size == 0, 'original producer must have finished cleanly')
    require(stream_record.get('archive_identity_verified') is True and
            stream_record.get('archive', {}).get('bytes') == ARCHIVE_BYTES and
            stream_record.get('archive', {}).get('sha256') == ARCHIVE_SHA and
            archive.stat().st_size == ARCHIVE_BYTES, 'complete pinned canonical archive required')
    # A receiver extraction failure on the SSD ACL-incompatible mount is retained;
    # it does not change the independently verified, immutable archive identity.
    binds = [
        (usr, '/usr', True),
        (archive, '/inputs/runtime.canonical.tar', True),
        (archive_receipt, '/inputs/archive-receipt.json', True),
        (pipeline, '/inputs/archive-pipeline.json', True),
        (source_exit, '/inputs/source.exit', True),
        (source_stderr, '/inputs/source.stderr', True),
        (source(ssd_work, args.target_repo, 'dir'), '/inputs/repo', True),
        (source(ssd_work, '/work/r5-novatek-signed-c1296-run02', 'dir'), '/inputs/signed-stage', True),
        (source(general_work, '/work/fedora-proot-src/src/proot', 'file'), '/work/fedora-proot-src/src/proot', True),
        (source(general_work, '/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu', 'dir'),
         '/work/fedora-host-tools/unpacked/usr/lib/x86_64-linux-gnu', True),
    ]
    for leaf in ('fedora-system-integration.json', 'runtime.json', 'vm-verify-01/result.json'):
        path = '/work/fedora-system-integration-v1/' + leaf
        binds.append((source(general_work, path, 'file'), path, True))
    evidence = ssd_work / EVIDENCE_NAME
    require(not evidence.exists() and not evidence.is_symlink(), 'new independent evidence destination required')
    require(stat.S_ISREG(args.worker.lstat().st_mode), 'ordinary reviewed worker file required')
    evidence.mkdir(mode=0o700)
    recipes, results = evidence / 'recipes', evidence / 'results'
    recipes.mkdir(mode=0o700)
    results.mkdir(mode=0o700)
    recipe_identities = {}
    for path, name in ((Path(__file__), 'launch_tmpfs_target.py'), (args.worker, 'run_tmpfs_target.py')):
        data = path.read_bytes()
        require(len(data) <= 128 * 1024, 'unexpected controller source size')
        with (recipes / name).open('xb') as stream:
            stream.write(data)
        recipe_identities[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    atomic_json(recipes / 'source-contract.json', {'commit': args.source_commit, 'tree': args.source_tree})
    binds += [(recipes, '/recipes', True), (results, '/evidence', False)]
    locale_environment = {}
    for item in general['Config'].get('Env', []):
        name, separator, value = item.partition('=')
        if separator and name in ('LANG', 'LC_ALL', 'LC_CTYPE', 'TZ'):
            require('\n' not in value and '\0' not in value, 'invalid locale environment value')
            locale_environment[name] = value
    argv = ['docker', 'create', '--name', HELPER, '--network', 'none', '--read-only',
            '--memory', '4g', '--memory-swap', '4g', '--pids-limit', '128',
            '--security-opt', 'no-new-privileges', '--stop-timeout', '30',
            '--tmpfs', '/work:rw,exec,nosuid,nodev,size=5g,mode=755',
            '--tmpfs', '/tmp:rw,exec,nosuid,nodev,size=128m,mode=1777',
            '--env', 'PYTHONDONTWRITEBYTECODE=1',
            '--entrypoint', '/usr/bin/env']
    for name, value in sorted(locale_environment.items()):
        argv += ['--env', name + '=' + value]
    for host, target, readonly in binds:
        require(',' not in str(host) and ',' not in target, 'comma in bind mount path')
        value = 'type=bind,source=' + str(host) + ',destination=' + target
        argv += ['--mount', value + (',readonly' if readonly else '')]
    argv += [image, 'python3', '-B', '/recipes/run_tmpfs_target.py']
    record = {'schema': 'tb371fc-novatek-tmpfs-launch-v1', 'started_utc': utc(), 'complete': False,
              'image_id': image, 'source_containers': [GENERAL, SSD], 'mem_available_before_bytes': available,
              'source_commit': args.source_commit, 'source_tree': args.source_tree, 'target_repo': args.target_repo,
              'source_container_locale_environment': locale_environment,
              'memory_limit_bytes': 4 * 1024**3, 'memory_and_swap_limit_bytes': 4 * 1024**3,
              'work_tmpfs_limit_bytes': 5 * 1024**3, 'tmp_tmpfs_limit_bytes': 128 * 1024**2,
              'create_argv': argv, 'recipes': recipe_identities, 'original_pipeline': pipeline_record,
              'old_artifacts_modified': False, 'global_storage_settings_changed': False,
              'source_usr': str(usr), 'evidence_directory': str(evidence), 'host_outer_timeout_seconds': 3300}
    record_path = evidence / 'launcher.json'
    atomic_json(record_path, record)
    container_id, attached = None, None
    exit_code = 1
    try:
        container_id = run(argv, 60).strip()
        require(len(container_id) == 64 and all(c in '0123456789abcdef' for c in container_id),
                'unexpected created helper ID')
        record['container_id'] = container_id
        atomic_json(record_path, record)
        with (evidence / 'container.log').open('xb') as log:
            attached = subprocess.Popen(['docker', 'start', '--attach', container_id],
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            record['docker_start_exit_code'] = attached.wait(timeout=3300)
        final = inspect(container_id)
        record['container_state'] = final['State']
        worker = json.loads((results / 'runner.json').read_text())
        require(record['docker_start_exit_code'] == 0 and final['State']['ExitCode'] == 0 and
                not final['State']['OOMKilled'] and worker.get('complete') is True and
                worker.get('text_export_complete') is True and
                (results / 'runner.exit').read_text().strip() == '0', 'helper did not complete and persist evidence')
        record['complete'] = True
        exit_code = 0
    except BaseException as error:
        record['failure'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        if container_id:
            try:
                state = inspect(container_id)['State']
                if state['Running']:
                    run(['docker', 'stop', '--time', '30', container_id], 45)
                record['container_state'] = inspect(container_id)['State']
            except BaseException as error:
                record['container_state_readback_error'] = str(error)
                record['complete'] = False
                exit_code = 1
        if attached is not None and attached.poll() is None:
            attached.terminate()
            try:
                attached.wait(timeout=10)
            except subprocess.TimeoutExpired:
                attached.kill()
                attached.wait(timeout=10)
        record['finished_utc'] = utc()
        record['exit_code'] = exit_code
        atomic_json(record_path, record)
        with (evidence / 'launcher.exit').open('x') as stream:
            stream.write(str(exit_code) + '\n')
        print(json.dumps({'complete': record['complete'], 'exit_code': exit_code,
                          'evidence_directory': str(evidence), 'container_id': container_id,
                          'failure': record.get('failure')}), flush=True)
    return exit_code


if __name__ == '__main__':
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, interrupted)
    sys.exit(main())
