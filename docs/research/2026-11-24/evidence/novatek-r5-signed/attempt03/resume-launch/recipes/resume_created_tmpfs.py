#!/usr/bin/env python3
"""Start only the exact, never-started run03 helper left by create timeout.

Preserves launcher.json/.exit and the frozen recipes. No create, exec, remove,
device access, source change, or replacement worker is performed.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys

EVIDENCE = Path('/tank/hot/tb371fc-build-20261123/r5-novatek-tmpfs-evidence-c1296-run03')
NAME = 'tb371fc-novatek-tmpfs-c1296-run03'
CONTAINER = '6d2faf7e40305934917fb5f40e64d9f9f09536db932532e8d3063b2e67c9504e'
IMAGE = 'sha256:ec92d6b34c6a7e6372d87dc9ef2fd6e8ca8125353fe7d033c676f51cf923a13b'
SPEC_SHA = 'd3ed6d154cc34be3bbcab95144b1685b664aeb5ff9deafcd8ab2595d19e74d01'
CONTRACT = {'commit': 'ff3b485190f9d589c7600da41590f221cb14ec2f',
            'tree': '42f9b5b10ac65f1ca59ba30e73ca1f5c861cb03e'}
FROZEN = {
    'launcher.json': (8883, 'b996d2a8007d83e6ccd4efdc20f701dbcdfc12be539b954b0c895534828dd396'),
    'launcher.exit': (2, '4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865'),
    'recipes/source-contract.json': (113, 'fca2adb4646740c1bd07067224f3f58d8fff5a34897a53d17b2407c81b4fdf8b'),
    'recipes/launch_tmpfs_target.py': (13536, 'ce9c5694621462da1dfb5a530238d1cde4f97149766468b300a8b4762d628e2a'),
    'recipes/run_tmpfs_target.py': (16450, '56da0aab714982e0660cb461217d7bd52e45a125e23f38c501b9824296f9f868'),
}
CONFIG_FIELDS = ('Cmd', 'Entrypoint', 'Env', 'User', 'WorkingDir', 'StopTimeout')
HOST_FIELDS = ('ReadonlyRootfs', 'NetworkMode', 'Memory', 'MemorySwap', 'PidsLimit',
               'SecurityOpt', 'Tmpfs', 'Privileged', 'CapAdd', 'CapDrop',
               'Devices', 'DeviceRequests', 'Mounts')
INPUT_CONTAINERS = {
    'tb371fc-build-20261123': ('volume', '/tank/docker/doescontainer/docker/volumes/tb371fc-build-20261123/_data'),
    'tb371fc-build-ssd-20261123': ('bind', '/tank/hot/tb371fc-build-20261123'),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def identity(path, maximum=2 * 1024**2):
    require(stat.S_ISREG(path.lstat().st_mode), 'ordinary file required: ' + str(path))
    require(path.stat().st_size <= maximum, 'unexpected file size: ' + str(path))
    data = path.read_bytes()
    require(len(data) <= maximum, 'file grew beyond bound')
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def frozen_inputs():
    result = {}
    for name, (size, sha) in FROZEN.items():
        result[name] = identity(EVIDENCE / name)
        require(result[name] == {'bytes': size, 'sha256': sha}, 'frozen input changed: ' + name)
    return result


def save(path, value, exclusive=False):
    output = path if exclusive else path.with_name(path.name + '.pending-' + str(os.getpid()))
    with output.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        os.replace(output, path)


def docker_read(argv, timeout=30):
    result = subprocess.run(['docker', *argv], stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, timeout=timeout, check=False)
    require(len(result.stdout) + len(result.stderr) <= 2 * 1024**2, 'Docker response exceeded bound')
    require(result.returncode == 0, 'Docker command failed: ' + result.stderr[:2000])
    return result.stdout


def inspect(name):
    values = json.loads(docker_read(['inspect', name]))
    require(len(values) == 1, 'one exact Docker object required')
    return values[0]


def projection(info):
    host = {key: info['HostConfig'][key] for key in HOST_FIELDS}
    host['Mounts'] = sorted(host['Mounts'], key=lambda item: item['Target'])
    return {'Id': info['Id'], 'Image': info['Image'],
            'Config': {key: info['Config'][key] for key in CONFIG_FIELDS},
            'HostConfig': host,
            'Mounts': sorted(info['Mounts'], key=lambda item: item['Destination'])}


def never_started(info):
    require(info['Id'] == CONTAINER and info.get('Name', '/' + NAME) == '/' + NAME,
            'exact original helper ID/name required')
    state = info['State']
    require(state['Status'] == 'created' and state['Running'] is False and
            state['Pid'] == 0 and state['OOMKilled'] is False and state['ExitCode'] == 0 and
            all(state[key] is False for key in ('Paused', 'Restarting', 'Dead')) and
            state['Error'] == '' and
            state['StartedAt'] == state['FinishedAt'] == '0001-01-01T00:00:00Z' and
            info.get('RestartCount', 0) == 0, 'helper has already started or is not cleanly created')


def match_created(info, original):
    never_started(info)
    selected = projection(info)
    digest = hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(digest == SPEC_SHA, 'created helper differs from the reviewed actual inspect specification')
    argv = original['create_argv']
    require(argv[:2] == ['docker', 'create'] and argv[-4:] ==
            [IMAGE, 'python3', '-B', '/recipes/run_tmpfs_target.py'], 'original create command changed')
    expected = {}
    for index, option in enumerate(argv):
        if option != '--mount':
            continue
        fields = argv[index + 1].split(',')
        parts = dict(part.split('=', 1) for part in fields if part != 'readonly')
        require(set(parts) == {'type', 'source', 'destination'} and parts['type'] == 'bind' and
                len(fields) == 3 + ('readonly' in fields), 'unsupported original mount syntax')
        target = parts['destination']
        require(target not in expected, 'duplicate original mount')
        expected[target] = (parts['type'], parts['source'], 'readonly' in fields)
    configured, actual = {}, {}
    for item in info['HostConfig']['Mounts']:
        target = item['Target']
        require(target not in configured, 'duplicate configured mount')
        configured[target] = (item['Type'], item['Source'], item.get('ReadOnly', False))
    for item in info['Mounts']:
        target = item['Destination']
        require(target not in actual and type(item['RW']) is bool, 'duplicate/invalid actual mount')
        actual[target] = (item['Type'], item['Source'], not item['RW'])
    require(len(expected) == 15 and configured == actual == expected,
            'all actual/configured binds must equal the original create arguments')
    require(expected['/recipes'] == ('bind', str(EVIDENCE / 'recipes'), True) and
            expected['/evidence'] == ('bind', str(EVIDENCE / 'results'), False) and
            expected['/usr'] == ('bind', original['source_usr'], True),
            'recipe/evidence/public tool mount changed')
    require(info['Config']['Entrypoint'] == [argv[argv.index('--entrypoint') + 1]] and
            info['Config']['Cmd'] == argv[-3:], 'entrypoint/command differs')
    hc = info['HostConfig']
    for key in ('Binds', 'VolumesFrom', 'DeviceCgroupRules', 'Links', 'PortBindings'):
        require(not hc.get(key), 'unexpected additional HostConfig setting: ' + key)
    require(not hc.get('AutoRemove') and not hc.get('OomKillDisable') and
            hc.get('PidMode', '') == '' and hc.get('UTSMode', '') == '',
            'unexpected lifecycle, OOM, or host namespace override')
    return selected


def interrupted(number, unused_frame):
    raise InterruptedError('resume controller received signal ' + str(number))


def main():
    require(os.geteuid() == 0, 'use the existing authorized root/sudo context')
    require(stat.S_ISDIR(EVIDENCE.lstat().st_mode), 'original evidence directory required')
    receipt_path = EVIDENCE / 'resume-launch.json'
    for name in ('resume-launch.json', 'resume-launch.exit', 'resume-launch.log'):
        path = EVIDENCE / name
        require(not path.exists() and not path.is_symlink(), 'retain existing resume attempt: ' + name)
    report = {'schema': 'tb371fc-created-helper-resume-v1', 'started_utc': utc(),
              'complete': False, 'container_id': CONTAINER, 'start_attempted': False,
              'physical_hardware_tested': False, 'new_container_created': False,
              'original_launcher_rewritten': False, 'outer_timeout_seconds': 3300,
              'controller': identity(Path(__file__))}
    save(receipt_path, report, exclusive=True)
    attached, exit_code = None, 1
    try:
        report['frozen_inputs_before'] = frozen_inputs()
        original = json.loads((EVIDENCE / 'launcher.json').read_text())
        require(original['schema'] == 'tb371fc-novatek-tmpfs-launch-v1' and
                original['complete'] is False and original['exit_code'] == 1 and
                (EVIDENCE / 'launcher.exit').read_bytes() == b'1\n' and
                not original.get('container_id') and 'docker_start_exit_code' not in original,
                'the original unstarted create failure is required')
        require(original['failure'] == {
            'type': 'TimeoutExpired',
            'message': "Command '" + str(original['create_argv']) + "' timed out after 60 seconds"},
            'original failure must be exactly the 60-second docker create timeout')
        contract = json.loads((EVIDENCE / 'recipes/source-contract.json').read_text())
        require(contract == CONTRACT and original['source_commit'] == CONTRACT['commit'] and
                original['source_tree'] == CONTRACT['tree'] and original['image_id'] == IMAGE and
                original['evidence_directory'] == str(EVIDENCE), 'original source contract changed')
        for path in (EVIDENCE / 'results', EVIDENCE / 'recipes'):
            require(stat.S_ISDIR(path.lstat().st_mode), 'ordinary original evidence subdirectory required')
        require(not any((EVIDENCE / 'results').iterdir()), 'worker evidence already exists; do not repeat')
        report['source_contract'] = contract
        report['original_failure'] = original['failure']
        report['input_containers'] = {}
        for name, (kind, source) in INPUT_CONTAINERS.items():
            info = inspect(name)
            require(info['State']['Running'] is True and info['Image'] == IMAGE,
                    'original input container stopped or changed image: ' + name)
            work = [item for item in info['Mounts'] if item['Destination'] == '/work']
            require(len(work) == 1 and (work[0]['Type'], work[0]['Source']) == (kind, source),
                    'original input /work mapping changed')
            if name == 'tb371fc-build-ssd-20261123':
                require(info['GraphDriver']['Data']['MergedDir'] + '/usr' == original['source_usr'],
                        'observed public /usr path changed')
            report['input_containers'][name] = {'id': info['Id'], 'image': info['Image'], 'work': work[0]}
        require(stat.S_ISDIR(Path(original['source_usr']).lstat().st_mode), 'public /usr directory missing')
        mem = next(line for line in Path('/proc/meminfo').read_text().splitlines()
                   if line.startswith('MemAvailable:')).split()
        require(mem[2] == 'kB', 'unexpected MemAvailable unit')
        report['mem_available_before_bytes'] = int(mem[1]) * 1024
        require(report['mem_available_before_bytes'] >= 10 * 1024**3, 'at least 10 GiB MemAvailable required')
        info = inspect(CONTAINER)
        report['verified_created_spec'] = match_created(info, original)
        report['state_before'] = info['State']
        require(frozen_inputs() == report['frozen_inputs_before'], 'frozen inputs changed during preflight')
        require(not any((EVIDENCE / 'results').iterdir()), 'worker evidence appeared during preflight')
        # Final fresh state/spec read, then the only start request in this controller.
        match_created(inspect(CONTAINER), original)
        report['start_attempted'] = True
        report['start_utc'] = utc()
        save(receipt_path, report)
        with (EVIDENCE / 'resume-launch.log').open('xb') as log:
            attached = subprocess.Popen(['docker', 'start', '--attach', CONTAINER],
                                        stdin=subprocess.DEVNULL, stdout=log, stderr=log)
            report['docker_start_exit_code'] = attached.wait(timeout=3300)
        final = inspect(CONTAINER)
        require(final['Id'] == CONTAINER, 'container ID changed')
        report['container_state'] = final['State']
        runner = json.loads((EVIDENCE / 'results/runner.json').read_text())
        report['worker_receipt'] = identity(EVIDENCE / 'results/runner.json')
        report['worker_summary'] = {key: runner.get(key) for key in
                                    ('complete', 'text_export_complete', 'exit_code', 'phase', 'failure')}
        require(report['docker_start_exit_code'] == 0 and final['State']['Status'] == 'exited' and
                final['State']['Running'] is False and final['State']['ExitCode'] == 0 and
                final['State']['OOMKilled'] is False and runner.get('complete') is True and
                runner.get('text_export_complete') is True and runner.get('exit_code') == 0 and
                (EVIDENCE / 'results/runner.exit').read_bytes() == b'0\n',
                'helper did not complete with persisted actual evidence')
        report['complete'], exit_code = True, 0
    except BaseException as error:
        report['failure'] = {'type': type(error).__name__, 'message': str(error)}
    finally:
        # Never stop either source container or an unvalidated/name-reused helper.
        if report['start_attempted']:
            try:
                final = inspect(CONTAINER)
                require(final['Id'] == CONTAINER, 'refuse cleanup of another container')
                if final['State']['Running']:
                    report['stop_requested'] = True
                    docker_read(['stop', '--time', '30', CONTAINER], 45)
                report['container_state'] = inspect(CONTAINER)['State']
            except BaseException as error:
                report['cleanup_error'] = str(error)
                report['complete'], exit_code = False, 1
        if attached is not None and attached.poll() is None:
            attached.terminate()
            try:
                attached.wait(timeout=10)
            except subprocess.TimeoutExpired:
                attached.kill()
                attached.wait(timeout=10)
        try:
            report['frozen_inputs_after'] = frozen_inputs()
            report['original_failure_and_recipes_unchanged'] = True
        except BaseException as error:
            report['frozen_input_error'] = str(error)
            report['complete'], exit_code = False, 1
        # If stop triggered the worker's finally, retain its resulting status too.
        worker_path = EVIDENCE / 'results/runner.json'
        if worker_path.is_file() and not worker_path.is_symlink():
            try:
                worker = json.loads(worker_path.read_text())
                report['worker_receipt'] = identity(worker_path)
                report['worker_summary'] = {key: worker.get(key) for key in
                    ('complete', 'text_export_complete', 'exit_code', 'phase', 'failure')}
            except BaseException as error:
                report['worker_readback_error'] = str(error)
                report['complete'], exit_code = False, 1
        report['finished_utc'], report['exit_code'] = utc(), exit_code
        save(receipt_path, report)
        with (EVIDENCE / 'resume-launch.exit').open('x') as stream:
            stream.write(str(exit_code) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps({'complete': report['complete'], 'exit_code': exit_code,
                          'container_id': CONTAINER, 'receipt': str(receipt_path),
                          'failure': report.get('failure')}), flush=True)
    return exit_code


if __name__ == '__main__':
    for number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(number, interrupted)
    sys.exit(main())

