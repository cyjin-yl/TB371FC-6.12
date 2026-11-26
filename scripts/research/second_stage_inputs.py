#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Bind a simulated board handoff to the completed, immutable R5 Fedora inputs.

This is a versioned experiment, not a generic installer. Paths are supplied by
an operator manifest; the R5 payload identities come from published evidence.
The retained 84-module bundle is requalified, and the completed 4 GiB root is
hashed in full. No device, mount, root filesystem or original file is changed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat

from qualify_boot_bundle import BundleReader, fingerprint, qualify_kernel

REPO = Path(__file__).resolve().parents[2]
CONTRACT = REPO / 'docs/research/2026-11-23/boot-candidate-r5.json'
CONTRACT_SHA256 = 'cbd40dbd9acdf26645c11647fb29079e5c4c8f8d1a6fadafaf154d3a3e72570b'
RELEASE = '6.12.114-tb371fc-research5-services'
FIXED = {
    'kernel': (41091080, 'd80bfce0feb5f6c0cec1b0b0dd4691323720ec3f34a373c7a109001e2cf42e76'),
    'dtb': (126893, '7092d992582a2f49b65e8eb1a4209fede3b41ccbbacb3abc28d29b649b33423c'),
    'initrd': (32535823, '6f63a7048f6664d1ff4473c0ddf580412172b50f9495073a4e7af5cd23465321'),
    'config': (223395, 'a4980121abcc3e2bac47f7020e63c8c00949c53c289019c22b67808d84cd3afa'),
    'certificate': (1324, '07a54ba929080f3c5d74cb485afeca7d7acf7c920fde0b26cf003ba45fd57627'),
    'rootfs': (4294967296, 'f3d260f5e91ed6a2b67e84fd4f7b3d07b1ff2dda5c88be43d1dac242774043ad'),
}
FILE_KEYS = set(FIXED) | {'qemu'}
RAW_KEYS = {'kernel', 'dtb', 'initrd', 'config', 'certificate'}
MAX_FILE = 8 * 1024**3
REQUIRED_ARGS = {
    'rdinit': '/init.tmpfs', 'rd.tb371fc.early-selinux': '1',
    'rd.tb371fc.tmpfs-root': '1', 'enforcing': '1',
    'module.sig_enforce': '1', 'root': 'LABEL=tb371fc-r5-f45',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique_object(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def checked_path(value):
    require(isinstance(value, str) and value and ',' not in value
            and all(32 <= ord(c) < 127 for c in value),
            'path must be printable ASCII without comma')
    path = Path(value)
    require(path.is_absolute() and str(path) == value
            and '..' not in path.parts, 'path must be canonical and absolute')
    # Do not resolve a link and silently bind a different source file.
    for parent in reversed(path.parents):
        require(stat.S_ISDIR(parent.lstat().st_mode),
                'path ancestor is a link or not a directory: ' + str(parent))
    return path


def validate_identity(value, label):
    require(isinstance(value, dict) and set(value) == {'path', 'bytes', 'sha256'},
            label + ' requires exactly path, bytes and sha256')
    require(type(value['bytes']) is int and 0 < value['bytes'] <= MAX_FILE,
            label + ' has invalid byte length')
    require(isinstance(value['sha256'], str)
            and re.fullmatch(r'[0-9a-f]{64}', value['sha256']) is not None,
            label + ' has invalid SHA-256')
    return checked_path(value['path'])


def read_file(path, *, expected=None, maximum=MAX_FILE, capture=False):
    """One stable ordinary-file read; stream large roots without buffering."""
    path = checked_path(str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    digest, chunks, length = hashlib.sha256(), [], 0
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum,
                'input is not a bounded ordinary file: ' + str(path))
        if expected is not None:
            require(before.st_size == expected['bytes'],
                    'input size mismatch: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                length += len(chunk)
                require(length <= maximum, 'input grew while reading')
                digest.update(chunk)
                if capture:
                    chunks.append(chunk)
        require(fingerprint(before) == fingerprint(os.fstat(fd))
                == fingerprint(path.lstat()) and length == before.st_size,
                'input changed during read: ' + str(path))
    finally:
        os.close(fd)
    identity = {'path': str(path), 'bytes': length, 'sha256': digest.hexdigest()}
    if expected is not None:
        require(identity['sha256'] == expected['sha256'],
                'input SHA-256 mismatch: ' + str(path))
    return identity, fingerprint(before), b''.join(chunks) if capture else None


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and set(manifest) == {
        'schema_version', 'release', 'kernel_bundle', 'kernel_load_base',
        'bootargs', 'files'}, 'unexpected manifest fields')
    require(type(manifest['schema_version']) is int and manifest['schema_version'] == 1,
            'unsupported manifest schema')
    require(manifest['release'] == RELEASE, 'not the completed R5 kernel release')
    load = manifest['kernel_load_base']
    require(type(load) is int and 0x80000000 <= load < 0x280000000
            and load % 0x200000 == 0 and not 0xbbb00000 <= load < 0xc0000000,
            'invalid simulated kernel load base')
    checked_path(manifest['kernel_bundle'])
    require(isinstance(manifest['files'], dict) and set(manifest['files']) == FILE_KEYS,
            'manifest must bind all seven input files')
    for name, entry in manifest['files'].items():
        validate_identity(entry, name)
        if name in FIXED:
            require((entry['bytes'], entry['sha256']) == FIXED[name],
                    name + ' is not the frozen completed R5 input')
    require(manifest['files']['qemu']['bytes'] <= 512 * 1024**2,
            'QEMU binary exceeds bounded experiment profile')
    args = manifest['bootargs']
    require(isinstance(args, str) and 0 < len(args) <= 4096
            and all(32 <= ord(c) < 127 for c in args)
            and all(c not in args for c in '\"\''), 'unsupported boot-argument syntax')
    tokens = args.split()
    require('--' not in tokens, 'kernel arguments after -- are not accepted')
    for key, value in REQUIRED_ARGS.items():
        matches = [t for t in tokens if t.split('=', 1)[0].replace('-', '_')
                   == key.replace('-', '_')]
        require(matches == [key + '=' + value], 'missing or conflicting argument: ' + key)
    require(not any(t.split('=', 1)[0].replace('-', '_') in {
        'init', 'selinux', 'mem', 'memmap', 'efi', 'acpi', 'dtb', 'fdt'}
        for t in tokens), 'unsupported handoff override in command line')
    return manifest


def verify_inputs(manifest_path):
    manifest_path = checked_path(str(manifest_path))
    manifest_id, manifest_stamp, manifest_raw = read_file(
        manifest_path, maximum=1024 * 1024, capture=True)
    manifest = validate_manifest(json.loads(manifest_raw, object_pairs_hook=unique_object))
    contract_id, contract_stamp, contract_raw = read_file(
        CONTRACT, maximum=1024 * 1024, capture=True)
    require(contract_id['sha256'] == CONTRACT_SHA256,
            'frozen R5 contract differs from the published input')
    contract = json.loads(contract_raw, object_pairs_hook=unique_object)
    kernel_bundle = checked_path(manifest['kernel_bundle'])
    with BundleReader(kernel_bundle) as reader:
        bundle_before = reader.inventory()
    qualification = qualify_kernel(kernel_bundle, contract)
    require(qualification['status'] == 'verified',
            'R5 kernel/module bundle qualification failed: '
            + json.dumps(qualification['errors'], sort_keys=True))
    with BundleReader(kernel_bundle) as reader:
        bundle_after = reader.inventory()
    require(bundle_before == bundle_after, 'kernel bundle changed during qualification')
    paths, identities, stamps, raw = {}, {}, {}, {}
    for name, entry in manifest['files'].items():
        path = validate_identity(entry, name)
        identity, stamp, data = read_file(path, expected=entry,
                                          capture=name in RAW_KEYS)
        if name == 'qemu':
            require(os.access(path, os.X_OK), 'QEMU is not executable')
        paths[name], identities[name], stamps[str(path)] = path, identity, stamp
        if data is not None:
            raw[name] = data
    # Equal hashes bind copied launch files to the same qualified bundle.
    payloads = {e['path']: e for e in contract['kernel_files']}
    for name, artifact in [('kernel', 'image'), ('config', 'config'),
                           ('certificate', 'certificate')]:
        reference = payloads[contract['kernel']['artifacts'][artifact]]
        require(all(identities[name][k] == reference[k] for k in ('bytes', 'sha256')),
                'launch ' + name + ' differs from qualified kernel bundle')
    stamps[str(manifest_path)] = manifest_stamp
    stamps[str(CONTRACT)] = contract_stamp
    result = {
        'paths': paths, 'raw': raw, 'identities': identities,
        'release': manifest['release'], 'bootargs': manifest['bootargs'],
        'kernel_load_base': manifest['kernel_load_base'],
        'kernel_bundle_qualification': qualification,
        'evidence_bindings': {
            'manifest': manifest_id, 'kernel_contract': contract_id,
            'rootfs_source': 'completed Fedora R5 run04 post-verify image',
            'initrd_source': 'run04 production-qualified verify archive',
            'dtb_source': 'retained R5 second-stage RAM declaration candidate',
            'module_signatures_reexecuted': False,
            'physical_boot_verified': False,
        },
        '_stamps': stamps, '_kernel_bundle': kernel_bundle,
        '_bundle_inventory': bundle_after,
    }
    verify_unchanged(result)
    return result


def verify_unchanged(inputs):
    """Detect replacement/write between validation and QMP cont/exit.

    The complete input bytes were hashed at preparation. These comparisons
    use inode/mode/size/mtime/ctime and the complete bundle inventory, not a
    repeated expensive 4 GiB scan. They do not claim to defeat a privileged
    adversary able to restore filesystem metadata or alter this process.
    """
    for value, expected in inputs['_stamps'].items():
        path = checked_path(value)
        require(fingerprint(path.lstat()) == expected,
                'input changed since qualification: ' + value)
    bundle = checked_path(str(inputs['_kernel_bundle']))
    with BundleReader(bundle) as reader:
        require(reader.inventory() == inputs['_bundle_inventory'],
                'kernel/module bundle changed since qualification')
