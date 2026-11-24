#!/usr/bin/env python3
"""Retain one fixed, offline ARM libsepol candidate query and its exit status."""
import datetime
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import time


BASE = Path('/work/selinux-socket-probe-20261123')
ROOT = Path('/work/fedora-input-system-v3/rootfs')
POLICY = (3835456, 'fe71750b659e71969145d89d08153196f21b46e6d66c6f28e09f8b11e739e53e')
LIBRARY = (802880, '46dbfe1a088868cb3af78d5050dd0cae5b0dcc3a14f9afc583a5ea968d50693b')
QUERY = (11794, '34e2b4a250bceca14d30a56b84437a45b9d57bf3ebf5c8d4cba152a0a2206e8d')
QEMU = (16661520, '73cc2584f119f9e74c85c0a8549dbb6fd104ae3897a06a7500797f9e5b4d0943')
PYTHON = (68968, 'a12cb0a1160abfbc59d3336fb3713562977fd862b9a3eafc2553c89b887a8d15')


def identity(data):
    return {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def fixed(path, expected):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('ordinary input required: ' + str(path))
    data = path.read_bytes()
    after = path.lstat()
    fields = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if fields(before) != fields(after) or (len(data), hashlib.sha256(data).hexdigest()) != expected:
        raise ValueError('fixed input differs: ' + str(path))
    return data


def main():
    work = BASE / 'query-01'
    work.mkdir(mode=0o700)
    inputs = {
        'policy': (BASE / 'compare-01/candidate-converted-v33.policy', POLICY),
        'library': (BASE / 'build-01/tool-root/usr/lib64/libsepol.so.2', LIBRARY),
        'query': (BASE / 'query-recipe-v1/query_candidate.py', QUERY),
    }
    record = {'scope': 'one direct-QEMU userspace candidate query; no VM, PRoot or kernel-policy load',
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'kernel_export_identity_asserted': False, 'inputs': {}}
    started = time.monotonic()
    record['started_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        for name, (source, expected) in inputs.items():
            data = fixed(source, expected)
            target = work / {'policy': 'policy.33', 'library': 'libsepol.so.2', 'query': 'query_candidate.py'}[name]
            with target.open('xb') as stream:
                stream.write(data)
            target.chmod(0o600)
            record['inputs'][name] = {'path': str(source), 'copy': str(target), **identity(data)}
        qemu = Path('/usr/bin/qemu-aarch64')
        python = ROOT / 'usr/bin/python3'
        # Resolve this fixed guest symlink only for the ordinary-file identity
        # check. Its qualified relative target is inside this existing root.
        if python.is_symlink():
            resolved = python.resolve(strict=True)
            if not resolved.is_relative_to(ROOT):
                raise ValueError('fixed Python symlink escapes the qualified root')
        else:
            resolved = python
        record['qemu'] = {'path': str(qemu), **identity(fixed(qemu, QEMU))}
        record['python'] = {'path': str(python), 'ordinary_target': str(resolved),
                            **identity(fixed(resolved, PYTHON))}
        command = [str(qemu), '-L', str(ROOT), str(python), '-I', '-B',
                   str(work / 'query_candidate.py'), '--policy', str(work / 'policy.33'),
                   '--library', str(work / 'libsepol.so.2'), '--policy-size', str(POLICY[0]),
                   '--policy-sha256', POLICY[1]]
        record['command'] = command
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        record['exit_code'] = result.returncode
        for name, data in [('stdout.json', result.stdout), ('stderr.log', result.stderr)]:
            with (work / name).open('xb') as stream:
                stream.write(data)
            record[name] = identity(data)
        parsed = json.loads(result.stdout)
        record['query_completed'] = parsed.get('completed') is True
        record['all_candidate_contracts_satisfied'] = parsed.get('all_candidate_contracts_satisfied') is True
        record['query_count'] = parsed.get('query_count')
        record['allowed_count'] = parsed.get('allowed_count')
        record['denied_count'] = parsed.get('denied_count')
        record['inputs_unchanged'] = all(fixed(path, expected) is not None for path, expected in inputs.values())
        if (result.returncode or not record['query_completed'] or
                not record['all_candidate_contracts_satisfied'] or result.stderr):
            raise ValueError('candidate query did not satisfy its exact contracts')
    except Exception as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
    record['elapsed_seconds'] = time.monotonic() - started
    record['finished_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (work / 'execution.json').open('x') as stream:
        json.dump(record, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if 'error' not in record else 1


if __name__ == '__main__':
    raise SystemExit(main())
