#!/usr/bin/env python3
"""Exercise the pinned stock stager's input/output boundaries in a build container.

Requires this owner's existing private capture and two completed staging trees.
No fixture firmware is published. All altered inputs and rejection targets are
new files in a required fresh work directory; completed prefixes are read-only
except for an intentionally rejected attempt to reuse one.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--elf-tree', type=Path, required=True)
    parser.add_argument('--mdt-tree', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    args.work.mkdir(mode=0o700)
    repo = Path(__file__).absolute().parents[2]
    stager = repo / 'scripts/research/stage_stock_firmware.py'
    capture = repo / 'docs/research/2026-11-23/evidence/stock-firmware-bundle.json'
    contract = repo / 'docs/research/2026-11-23/evidence/firmware-kernel-contract.json'
    results = []
    original_archive_sha = sha(args.archive)
    original_manifests = {str(tree): sha(tree / 'stock-firmware-manifest.json')
                          for tree in (args.elf_tree, args.mdt_tree)}

    def reject(name, match, archive=None, output=None, evidence=None, request_contract=None):
        destination = output or args.work / ('rejected-' + name)
        command = [sys.executable, '-B', str(stager), '--archive', str(archive or args.archive),
                   '--output', str(destination), '--zap-format', 'elf',
                   '--novatek-variants', 'dt-both-6', '--capture', str(evidence or capture),
                   '--contract', str(request_contract or contract)]
        ran = subprocess.run(command, capture_output=True, timeout=30)
        text = (ran.stdout + ran.stderr).decode(errors='replace')
        if len(text) > 8192:
            raise AssertionError('unexpectedly large rejection output')
        if ran.returncode == 0 or match not in text:
            raise AssertionError('wrong rejection result: ' + name + ': ' + text)
        if output != args.elf_tree and destination.exists():
            raise AssertionError('rejected operation created its package prefix')
        results.append({'name': name, 'command': command, 'exit_code': ran.returncode,
                        'expected_rejection': match, 'observed_expected_rejection': True,
                        'log_sha256': hashlib.sha256(ran.stdout + ran.stderr).hexdigest()})

    tampered = args.work / 'tampered-archive.tar.gz'
    data = bytearray(args.archive.read_bytes())
    data[-1] ^= 1
    tampered.write_bytes(data)
    reject('modified-archive', 'archive differs from the pinned owner capture', archive=tampered)
    changed_capture = args.work / 'modified-capture.json'
    changed_capture.write_bytes(capture.read_bytes() + b'\n')
    reject('changed-capture-pin', 'evidence differs from its fixed reviewed identity', evidence=changed_capture)
    changed_contract = args.work / 'modified-contract.json'
    changed_contract.write_bytes(contract.read_bytes() + b'\n')
    reject('changed-contract-pin', 'evidence differs from its fixed reviewed identity', request_contract=changed_contract)
    linked_archive = args.work / 'archive-link.tar.gz'
    linked_archive.symlink_to(args.archive)
    reject('source-file-symlink', 'regular file', archive=linked_archive)
    reject('existing-output', 'staging prefix exists', output=args.elf_tree)
    reject('parent-traversal', 'parent traversal', output=args.work / '..' / 'forbidden-escape')
    actual_parent = args.work / 'new-empty-parent'
    actual_parent.mkdir()
    linked_parent = args.work / 'parent-link'
    linked_parent.symlink_to(actual_parent, target_is_directory=True)
    reject('output-parent-symlink', 'Not a directory', output=linked_parent / 'rejected')
    if list(actual_parent.iterdir()):
        raise AssertionError('symlink rejection wrote into its target directory')

    checksum_checks = []
    for tree in (args.elf_tree, args.mdt_tree):
        command = ['sha256sum', '--check', '--quiet', 'SHA256SUMS']
        ran = subprocess.run(command, cwd=tree, capture_output=True, timeout=30)
        if ran.returncode:
            raise AssertionError('independent checksum check failed')
        if sha(tree / 'stock-firmware-manifest.json') != original_manifests[str(tree)]:
            raise AssertionError('completed manifest changed during rejection checks')
        checksum_checks.append({'tree': str(tree), 'command': command, 'exit_code': ran.returncode})
    if sha(args.archive) != original_archive_sha:
        raise AssertionError('source archive was modified')
    report = {'schema_version': 1, 'observed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'status': 'passed', 'scope': 'Offline staging boundary and checksum checks; no hardware test',
              'test_script_sha256': sha(Path(__file__)), 'stager_sha256': sha(stager),
              'negative_case_count': len(results), 'negative_cases': results,
              'independent_checksum_checks': checksum_checks,
              'original_source_and_completed_manifests_unchanged': True}
    (args.work / 'validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
