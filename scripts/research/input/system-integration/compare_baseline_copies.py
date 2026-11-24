#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compare the retained interrupted copy with the new quiescent copy.

Both trees are private, offline Fedora build directories. No source timestamps
are reset. Regular-file payloads, hardlinks, metadata, symlinks and xattr hashes
are compared; special device nodes are statted, never opened.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat

FIRST = Path('/work/fedora-input-system-v4/rootfs')
SECOND = Path('/work/fedora-input-system-v5/rootfs')
OUTPUT = Path('/work/fedora-r4-baseline-comparison-v1')


def snapshot(root):
    if root.is_symlink() or not root.is_dir():
        raise ValueError('ordinary offline root required')
    entries, payloads, hardlinks = {}, {}, {}
    total = 0
    paths = [root] + sorted(root.rglob('*'))
    if len(paths) > 100000:
        raise ValueError('unexpected root inventory size')
    for path in paths:
        before = path.lstat()
        name = path.relative_to(root).as_posix()
        entry = {'mode': before.st_mode, 'uid': before.st_uid, 'gid': before.st_gid,
                 'mtime_ns': before.st_mtime_ns, 'rdev': before.st_rdev,
                 'xattrs': {}}
        for attribute in sorted(os.listxattr(path, follow_symlinks=False)):
            raw = os.getxattr(path, attribute, follow_symlinks=False)
            entry['xattrs'][attribute] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if stat.S_ISLNK(before.st_mode):
            entry['link_target'] = os.readlink(path)
        elif stat.S_ISREG(before.st_mode):
            key = (before.st_dev, before.st_ino)
            if key not in payloads:
                if before.st_size > 1024**3:
                    raise ValueError('unexpected regular payload size')
                with path.open('rb') as stream:
                    payloads[key] = hashlib.file_digest(stream, 'sha256').hexdigest()
                total += before.st_size
                if total > 4 * 1024**3:
                    raise ValueError('unexpected total regular payload size')
            entry['size'] = before.st_size
            entry['sha256'] = payloads[key]
            if before.st_nlink > 1:
                hardlinks.setdefault(key, []).append(name)
        after = path.lstat()
        stable = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
                                value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if stable(before) != stable(after):
            raise ValueError('entry changed while reading: ' + name)
        entries[name] = entry
    groups = sorted(sorted(names) for names in hardlinks.values() if len(names) > 1)
    # Recheck directory mtimes after all data reads; source changes are not
    # forgiven merely because a reader had already passed the changed path.
    for name, entry in entries.items():
        if stat.S_ISDIR(entry['mode']) and (root / name).lstat().st_mtime_ns != entry['mtime_ns']:
            raise ValueError('directory changed during the comparison: ' + name)
    return {'entries': entries, 'hardlink_groups': groups,
            'unique_regular_payload_bytes_hashed': total}


def main():
    if OUTPUT.exists() or OUTPUT.is_symlink():
        raise ValueError('fresh comparison output required')
    OUTPUT.mkdir()
    first, second = snapshot(FIRST), snapshot(SECOND)
    identities = {}
    for name, data in (('retained-copy.json', first), ('quiescent-copy.json', second)):
        raw = (json.dumps(data, sort_keys=True, indent=2) + '\n').encode()
        with (OUTPUT / name).open('xb') as stream:
            stream.write(raw)
        identities[name] = {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    differences = []
    for name in sorted(set(first['entries']) | set(second['entries'])):
        before, after = first['entries'].get(name), second['entries'].get(name)
        if before != after:
            fields = sorted(key for key in set(before or {}) | set(after or {})
                            if (before or {}).get(key) != (after or {}).get(key))
            differences.append({'path': name, 'different_fields': fields,
                                'retained': before, 'quiescent': after})
    record = {'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'first': str(FIRST), 'second': str(SECOND), 'manifests': identities,
              'differences': differences,
              'hardlink_groups_equal': first['hardlink_groups'] == second['hardlink_groups'],
              'source_timestamps_reset': False, 'special_devices_opened': False,
              'historical_tar_hash_reconstructed': False,
              'original_failed_copy_reclassified_as_pass': False,
              'recipe_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with (OUTPUT / 'comparison.json').open('x') as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps(record, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
