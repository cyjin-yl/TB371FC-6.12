#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Read allowlisted Android kernel/entry prerequisites without testing entry.

No modules are loaded, no kexec syscall is made, and no disk identity, content,
credentials, raw command line or arbitrary debugfs/sysfs interface is read.
"""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path

CONFIG_KEYS = {
    'CONFIG_ARM64', 'CONFIG_KEXEC', 'CONFIG_KEXEC_FILE', 'CONFIG_KEXEC_CORE',
    'CONFIG_CRASH_DUMP', 'CONFIG_PROC_VMCORE', 'CONFIG_RELOCATABLE',
    'CONFIG_RANDOMIZE_BASE', 'CONFIG_MODULES', 'CONFIG_MODULE_UNLOAD',
    'CONFIG_MODVERSIONS', 'CONFIG_MODULE_SIG', 'CONFIG_MODULE_SIG_FORCE',
    'CONFIG_IKCONFIG', 'CONFIG_IKCONFIG_PROC', 'CONFIG_SECURITY_SELINUX',
    'CONFIG_USB_CONFIGFS', 'CONFIG_USB_CONFIGFS_ACM', 'CONFIG_USB_CONFIGFS_F_FS',
    'CONFIG_USB_CONFIGFS_NCM', 'CONFIG_PSTORE', 'CONFIG_PSTORE_RAM',
}
SCALAR_PATHS = (
    '/sys/kernel/kexec_loaded', '/sys/kernel/kexec_crash_loaded',
    '/proc/sys/kernel/kexec_load_disabled', '/proc/sys/kernel/modules_disabled',
)


def collect():
    result = {'schema_version': 1,
              'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'passive entry prerequisites, not boot/restore validation',
              'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'kernel_release': os.uname().release, 'kernel_config': {},
              'entry_scalars': {}, 'mmc_block_nodes': [],
              'module_load_performed': False, 'kexec_load_performed': False,
              'physical_mainline_boot_tested': False}
    try:
        with Path('/proc/config.gz').open('rb') as source:
            compressed = source.read(1024**2 + 1)
        if len(compressed) > 1024**2:
            raise ValueError('compressed config exceeds bound')
        # GzipFile permits an explicit decompressed-size bound.
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as source:
            config = source.read(2 * 1024**2 + 1)
        if len(config) > 2 * 1024**2:
            raise ValueError('decompressed config exceeds bound')
        values = {}
        for line in config.decode('ascii').splitlines():
            key, separator, value = line.partition('=')
            if separator and key in CONFIG_KEYS:
                values[key] = value
            elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
                key = line[2:-11]
                if key in CONFIG_KEYS:
                    values[key] = 'n'
        result['kernel_config'] = {'compressed_sha256': hashlib.sha256(compressed).hexdigest(),
                                   'decompressed_sha256': hashlib.sha256(config).hexdigest(),
                                   'values': {key: values.get(key, 'not_present_in_config')
                                              for key in sorted(CONFIG_KEYS)}}
    except (OSError, ValueError, EOFError) as error:
        result['kernel_config'] = {'unavailable': type(error).__name__}
    for name in SCALAR_PATHS:
        try:
            with Path(name).open('rb') as source:
                value = source.read(65)
            if value.strip() not in (b'0', b'1'):
                raise ValueError('not a boolean scalar')
            result['entry_scalars'][name] = int(value.strip())
        except (OSError, ValueError) as error:
            result['entry_scalars'][name] = {'unavailable': type(error).__name__}
    try:
        import re
        result['mmc_block_nodes'] = sorted(path.name for path in Path('/sys/class/block').iterdir()
                                          if re.fullmatch(r'mmcblk[0-9]+(?:p[0-9]+)?', path.name))
    except OSError as error:
        result['mmc_block_nodes'] = {'unavailable': type(error).__name__}
    return result


if __name__ == '__main__':
    print(json.dumps(collect(), indent=2, sort_keys=True))
