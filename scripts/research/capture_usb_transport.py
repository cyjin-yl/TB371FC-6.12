#!/usr/bin/env python3
"""Bounded USB transport metadata; never reads serials or changes a USB role."""
import argparse
import datetime
import json
from pathlib import Path
import re


def attribute(path, limit=128):
    try:
        with path.open('rb') as stream:
            data = stream.read(limit + 1)
    except FileNotFoundError:
        return {'present': False}
    except PermissionError:
        return {'present': True, 'readable': False}
    except OSError as error:
        return {'present': path.exists(), 'readable': False, 'errno': error.errno}
    if len(data) > limit:
        return {'present': True, 'readable': True, 'over_bound': True}
    return {'present': True, 'readable': True, 'value': data.decode('ascii', errors='replace').strip()}


def entries(parent, limit=64):
    if not parent.is_dir():
        return []
    found = sorted(parent.iterdir())
    if len(found) > limit:
        raise RuntimeError('too many entries under fixed parent: ' + str(parent))
    return found


def host():
    result = []
    for path in entries(Path('/sys/bus/usb/devices'), 128):
        if ':' in path.name or not re.fullmatch(r'(?:usb)?[0-9]+(?:[-.][0-9]+)*', path.name):
            continue
        if not (path / 'idVendor').is_file() or not (path / 'idProduct').is_file():
            continue
        result.append({'sysfs_name': path.name, 'attributes': {
            key: attribute(path / key)
            for key in ('idVendor', 'idProduct', 'bDeviceClass', 'bConfigurationValue', 'speed')
        }})
    candidates = [row['sysfs_name'] for row in result
                  if row['attributes']['idVendor'].get('value') in ('17ef', '18d1', '05c6')]
    return {'usb_device_count': len(result), 'usb_devices': result,
            'lenovo_google_qualcomm_vendor_candidates': candidates,
            'candidate_meaning': 'vendor IDs only; neither a tablet identity nor a fastboot/recovery test',
            'physical_tablet_identity_verified': False,
            'scope_limit': 'this host inventory at this instant only; no claim about other hosts'}


def android():
    udcs = []
    for path in entries(Path('/sys/class/udc')):
        udcs.append({'sysfs_name': path.name, 'attributes': {
            key: attribute(path / key) for key in ('state', 'current_speed', 'maximum_speed')
        }})
    gadgets = []
    for parent in (Path('/config/usb_gadget'), Path('/sys/kernel/config/usb_gadget')):
        for path in entries(parent):
            if path.is_dir():
                gadgets.append({'path': str(path), 'attributes': {
                    key: attribute(path / key) for key in ('idVendor', 'idProduct', 'UDC')
                }})
    ports = []
    for path in entries(Path('/sys/class/typec')):
        if re.fullmatch(r'port[0-9]+', path.name):
            ports.append({'sysfs_name': path.name, 'attributes': {
                key: attribute(path / key) for key in ('data_role', 'power_role', 'port_type')
            }})
    return {'udc': udcs, 'gadget_identifiers': gadgets, 'typec': ports,
            'fastboot_observed': False, 'recovery_transport_verified': False,
            'scope_limit': 'live Android cached/sysfs state; no bootloader or recovery transition'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scope', choices=('host', 'android'))
    args = parser.parse_args()
    value = {'schema_version': 1,
             'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'scope': args.scope, 'serials_read': False, 'role_or_configuration_changed': False,
             'reboot_or_bootloader_command_issued': False,
             'capture': globals()[args.scope]()}
    print(json.dumps(value, indent=2, sort_keys=True))
