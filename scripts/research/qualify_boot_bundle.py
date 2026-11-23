#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Qualify the frozen R5 kernel input bundle without modifying or booting it.

This is a deliberately versioned R5 contract, not a generic firmware installer.
Historical evidence, current payload bytes and native boot readiness are separate
results. Even a complete kernel bundle cannot satisfy the remaining root-loader,
firmware, physical entry and recovery requirements.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys

from boot_formats import parse_arm64_image, parse_fdt
from derive_boot_candidate import derive, encoded

REPO = Path(__file__).resolve().parents[2]
CANDIDATE = Path('docs/research/2026-11-23/boot-candidate-r5.json')
MAX_FILE = 128 * 1024**2
MAX_ENTRIES = 4096
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
REQUIRED_CONFIG = {
    'CONFIG_BLK_DEV_INITRD': 'y', 'CONFIG_RD_GZIP': 'y',
    'CONFIG_DEVTMPFS': 'y', 'CONFIG_DEVTMPFS_MOUNT': 'y',
    'CONFIG_EXT4_FS': 'y', 'CONFIG_EXT4_FS_SECURITY': 'y',
    'CONFIG_MMC_SDHCI_MSM': 'y', 'CONFIG_SCSI_UFS_QCOM': 'y',
    'CONFIG_PHY_QCOM_QMP_UFS': 'y', 'CONFIG_BLK_DEV_SD': 'y',
    'CONFIG_VIRTIO_BLK': 'y', 'CONFIG_VIRTIO_MMIO': 'y',
    'CONFIG_MODULE_SIG': 'y', 'CONFIG_MODULE_SIG_FORCE': 'y',
    'CONFIG_MODVERSIONS': 'y', 'CONFIG_FHANDLE': 'y',
    'CONFIG_PID_NS': 'y', 'CONFIG_USER_NS': 'y', 'CONFIG_CGROUP_PIDS': 'y',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def canonical_path(value):
    require(isinstance(value, str) and value and '\\' not in value,
            'noncanonical relative bundle path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and path.as_posix() == value
            and all(part not in ('.', '..', '') for part in path.parts)
            and all(ord(char) >= 32 and ord(char) != 127 for char in value),
            'noncanonical relative bundle path')
    return path.parts


class BundleReader:
    """Read only regular files below one directory descriptor, without links."""

    def __init__(self, root):
        self.fd = os.open(root, DIRECTORY_FLAGS)

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def read(self, relative, maximum=MAX_FILE):
        parts = canonical_path(relative)
        parent = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                child = os.open(part, DIRECTORY_FLAGS, dir_fd=parent)
                os.close(parent)
                parent = child
            fd = os.open(parts[-1], FILE_FLAGS, dir_fd=parent)
            try:
                before = os.fstat(fd)
                require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum,
                        'not a bounded ordinary file: ' + relative)
                with os.fdopen(fd, 'rb', closefd=False) as stream:
                    raw = stream.read(maximum + 1)
                after = os.fstat(fd)
                require(fingerprint(before) == fingerprint(after)
                        and len(raw) == before.st_size,
                        'file changed during read: ' + relative)
                return raw, before
            finally:
                os.close(fd)
        finally:
            os.close(parent)

    def inventory(self):
        files, directories = {}, {}
        count = 0

        def walk(fd, prefix):
            nonlocal count
            before = os.fstat(fd)
            directories[prefix] = fingerprint(before)
            with os.scandir(fd) as entries:
                names = sorted(entry.name for entry in entries)
            for name in names:
                relative = prefix + name
                canonical_path(relative)
                count += 1
                require(count <= MAX_ENTRIES, 'bundle contains too many entries')
                info = os.stat(name, dir_fd=fd, follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
                    try:
                        require(fingerprint(os.fstat(child)) == fingerprint(info),
                                'directory changed during inventory: ' + relative)
                        walk(child, relative + '/')
                    finally:
                        os.close(child)
                else:
                    require(stat.S_ISREG(info.st_mode),
                            'symlink or special file in bundle: ' + relative)
                    files[relative] = fingerprint(info)
            require(fingerprint(before) == fingerprint(os.fstat(fd)),
                    'directory changed during inventory: ' + prefix)

        walk(self.fd, '')
        return files, directories


def parse_config(raw):
    values = {}
    for line in raw.decode('ascii').splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            require(key not in values, 'duplicate configuration key: ' + key)
            values[key] = value
    return values


def qualify_kernel(root, contract):
    result = {'status': 'failed', 'files': [], 'evidence_sidecars': [], 'errors': [],
              'module_signatures_reexecuted': False,
              'module_symbol_crc_commands_reexecuted': False,
              'module_bytes_match_recorded_qualification': False,
              'physical_hardware_tested': False}
    expected = {entry['path']: entry for entry in contract['kernel_files']}
    sidecars = {entry['path']: entry for entry in contract.get('kernel_evidence_sidecars', [])}
    require(not (expected.keys() & sidecars.keys()), 'payload and sidecar paths overlap')
    allowed = {**expected, **sidecars}
    artifacts = contract['kernel']['artifacts']
    capture = set(artifacts.values()) | {'artifacts/kernel.release'}
    captured = {}
    try:
        with BundleReader(root) as reader:
            before, dirs_before = reader.inventory()
            missing = sorted(set(expected) - set(before))
            extra = sorted(set(before) - set(allowed))
            if missing:
                result['errors'].append({'code': 'missing_files', 'paths': missing})
            if extra:
                result['errors'].append({'code': 'unexpected_files', 'paths': extra})
            for relative in sorted(allowed.keys() & before.keys()):
                reference = allowed[relative]
                try:
                    raw, info = reader.read(relative, min(MAX_FILE, reference['bytes']))
                    observed = {'path': relative, 'bytes': len(raw),
                                'sha256': hashlib.sha256(raw).hexdigest(),
                                'mode': stat.S_IMODE(info.st_mode)}
                    keys = ('bytes', 'sha256', 'mode') if 'mode' in reference else ('bytes', 'sha256')
                    observed['matches'] = all(observed[key] == reference[key] for key in keys)
                    require(before[relative] == fingerprint(info),
                            'file changed after inventory: ' + relative)
                    result['files' if relative in expected else 'evidence_sidecars'].append(observed)
                    if not observed['matches']:
                        result['errors'].append({'code': 'identity_mismatch', 'path': relative})
                    elif relative in capture:
                        captured[relative] = raw
                except (OSError, ValueError) as error:
                    result['errors'].append({'code': 'file_read_failed',
                                             'path': relative, 'reason': str(error)})
            after, dirs_after = reader.inventory()
            require(before == after and dirs_before == dirs_after,
                    'bundle changed during qualification')
        # Parse only bytes whose full identities already match this fixed R5
        # contract. A marker in an unrelated first-stage image is insufficient.
        if not result['errors']:
            header = parse_arm64_image(captured[artifacts['image']])
            require(all(header[key] == value for key, value in
                        contract['kernel']['arm64_header'].items()),
                    'R5 ARM64 header differs from its recorded contract')
            dt = parse_fdt(captured[artifacts['dtb']])
            require(dt['compatible'] == contract['kernel']['compatible'],
                    'DT root compatible is not the qualified TB371FC joint profile')
            release = captured['artifacts/kernel.release'].decode('ascii')
            require(release == contract['kernel']['release'] + '\n',
                    'kernel.release differs from the candidate')
            config = parse_config(captured[artifacts['config']])
            require(all(config.get(key) == value for key, value in REQUIRED_CONFIG.items()),
                    'R5 configuration lacks a required root-loader or module capability')
            require(captured[artifacts['certificate']] in captured[artifacts['image']],
                    'public signing certificate is absent from the exact Image')
            modules = [row for row in result['files'] if row['path'].endswith('.ko')]
            require(len(modules) == contract['kernel']['module_count'],
                    'signed module set has the wrong size')
            result.update(status='verified', file_count=len(result['files']),
                          evidence_sidecar_count=len(result['evidence_sidecars']),
                          module_count=len(modules), arm64_header=header,
                          device_tree=dt, required_config=REQUIRED_CONFIG,
                          public_certificate_present_in_image=True,
                          module_bytes_match_recorded_qualification=True)
    except (OSError, ValueError, UnicodeError) as error:
        result['errors'].append({'code': 'bundle_contract_failed', 'reason': str(error)})
    return result


def read_candidate(path):
    with BundleReader(path.parent) as reader:
        raw, unused = reader.read(path.name, 1024 * 1024)
    def no_duplicates(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=no_duplicates)


def qualify(repo, candidate, kernel_root=None, rootfs_root=None):
    expected = derive(repo)
    require(encoded(candidate) == encoded(expected),
            'candidate is not the exact derivation of the frozen R5 evidence')
    result = {
        'schema_version': 1, 'kind': 'tb371fc-r5-boot-bundle-qualification',
        'candidate_id': candidate['candidate_id'],
        'observed_utc': datetime.now(timezone.utc).isoformat(),
        'evidence_consistency': {'status': 'verified',
                                 'source_count': len(candidate['evidence_sources'])},
        'kernel_payload': {'status': 'not_provided', 'physical_hardware_tested': False},
        'root_module_tree': {'status': 'not_provided', 'rootfs_runtime_ready': False},
        'native_boot_readiness': {'status': 'blocked',
                                  'requirements': candidate['boot_requirements']},
        'native_boot_attempted': False, 'owner_native_linux_passes_added': 0,
        'scope': 'Frozen R5 evidence and optional current kernel/root-module bytes only; '
                 'not a root-loader execution, physical boot, firmware-loading or recovery test.',
    }
    if kernel_root is not None:
        result['kernel_payload'] = qualify_kernel(kernel_root, candidate)
    if rootfs_root is not None:
        from boot_rootfs import inspect_root_module_tree
        result['root_module_tree'] = inspect_root_module_tree(rootfs_root, candidate)
    return result


def exit_status(result, gate):
    if result.get('status') == 'invalid':
        return 1
    if result['kernel_payload']['status'] == 'failed':
        return 1
    root = result['root_module_tree']
    if root['status'] != 'not_provided' and not root.get('passed', False):
        return 1
    if gate == 'evidence':
        return 0
    if gate == 'kernel':
        return 0 if result['kernel_payload']['status'] == 'verified' else 2
    # This first version deliberately has no implementation that qualifies the
    # missing native entry/root-loader/recovery. Presence of new files, historical
    # booleans or a generic-VM result cannot silently clear those prerequisites.
    return 2


def validate_output_destination(output, input_roots):
    """Keep reports out of inspected trees, including symlink/bind aliases."""
    if output is None:
        return
    parent = output.parent.resolve(strict=True)
    require(parent.is_dir(), 'report parent is not a directory')
    for root in input_roots:
        if root is None:
            continue
        resolved = root.resolve(strict=False)
        require(not parent.is_relative_to(resolved),
                'report must be outside every inspected input tree')
        if root.exists():
            # A bind mount can expose the same directory under another pathname.
            identity = root.stat()
            for ancestor in (parent, *parent.parents):
                observed = ancestor.stat()
                require((observed.st_dev, observed.st_ino) != (identity.st_dev, identity.st_ino),
                        'report parent aliases an inspected input tree')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=REPO)
    parser.add_argument('--candidate', type=Path,
                        help='default: the tracked boot-candidate-r5.json beneath --repo')
    parser.add_argument('--kernel-root', type=Path,
                        help='exact 106-file transferred R5 input directory')
    parser.add_argument('--rootfs-root', type=Path,
                        help='optional unpacked root; never executed or modified')
    parser.add_argument('--gate', choices=('evidence', 'kernel', 'native'), default='native',
                        help='exit 0 only for the selected offline gate; native remains blocked')
    parser.add_argument('--output', type=Path, help='create a new report; never overwrite')
    args = parser.parse_args()
    try:
        validate_output_destination(args.output, (args.kernel_root, args.rootfs_root))
    except (OSError, ValueError) as error:
        print(json.dumps({'status': 'invalid_output', 'reason': str(error)}), file=sys.stderr)
        return 1
    try:
        candidate = read_candidate(args.candidate or args.repo / CANDIDATE)
        result = qualify(args.repo, candidate, args.kernel_root, args.rootfs_root)
        code = exit_status(result, args.gate)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'schema_version': 1, 'status': 'invalid', 'reason': str(error),
                  'native_boot_attempted': False, 'owner_native_linux_passes_added': 0}
        code = 1
    result['requested_gate'] = args.gate
    result['exit_code'] = code
    raw = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        # Evidence belongs outside the immutable input bundle. Exclusive create
        # also prevents an output option from overwriting an input or old report.
        try:
            validate_output_destination(args.output, (args.kernel_root, args.rootfs_root))
            with args.output.open('x', encoding='utf-8') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except (OSError, ValueError) as error:
            print(json.dumps({'status': 'report_not_written', 'reason': str(error)}), file=sys.stderr)
            return 1
    else:
        sys.stdout.write(raw)
    return code


if __name__ == '__main__':
    sys.exit(main())
