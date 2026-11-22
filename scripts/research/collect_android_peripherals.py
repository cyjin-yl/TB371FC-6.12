#!/usr/bin/env python3
"""Bounded Android camera/sensor/audio identities; never starts a stream.

Reads only whitelisted static sysfs/DT/ALSA identity files. The two fixed
dumpsys commands are filtered in memory; raw output/client state is never
printed, hashed or saved. No device node, debugfs, event stream, register,
calibration, power control or tracing interface is accessed.
"""
from __future__ import annotations

import base64
import datetime
import glob
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
import time

DT_ROOT = Path('/sys/firmware/devicetree/base')
DT_NAMES = re.compile(r'camera|cam[-_,]|sensor|tfa|codec|wcd|sound|audio|bmi|qmc|hall|ltr|stk|tcs', re.I)
DT_STRINGS = ('compatible', 'status', 'name', 'label', 'model', 'qcom,model',
              'qcom,sensor-name', 'sensor-name', 'qcom,eeprom-name',
              'qcom,actuator-name', 'qcom,csiphy-name')
DT_NUMBERS = ('cell-index', 'qcom,camera-id', 'qcom,sensor-id', 'reg')
CAMERA_TAGS = {'android.sensor.info.pixelArraySize', 'android.sensor.info.activeArraySize',
               'android.sensor.orientation', 'android.lens.facing',
               'android.control.aeAvailableTargetFpsRanges'}


def bounded(path, maximum=4096):
    def expired(signum, frame):
        raise TimeoutError('bounded static file read')
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, 0.5)
    try:
        with Path(path).open('rb') as stream:
            data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError('oversize static file')
        return data
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def strings(data):
    return [x.decode('utf-8', 'strict') for x in data.rstrip(b'\0\n').split(b'\0') if x]


def safe_text(path, maximum=4096):
    try:
        return bounded(path, maximum).decode('utf-8', 'strict').strip()
    except (OSError, UnicodeError, ValueError, TimeoutError) as exc:
        return {'unavailable': type(exc).__name__}


def binding(path):
    item = {'path': str(path), 'name': safe_text(path / 'name', 512)}
    for relative in ('driver', 'of_node', 'device/driver', 'device/of_node'):
        link = path / relative
        if link.is_symlink():
            item[relative] = str(link.resolve())
    for relative in ('of_node/compatible', 'device/of_node/compatible'):
        try:
            item[relative] = strings(bounded(path / relative, 2048))
        except (OSError, UnicodeError, ValueError, TimeoutError):
            pass
    return item


def dt_inventory():
    records = []
    visited = 0
    complete = True
    for directory, children, files in os.walk(DT_ROOT, followlinks=False):
        children.sort()
        visited += 1
        if visited > 12000 or len(records) >= 96:
            complete = False
            break
        path = Path(directory)
        try:
            compat = strings(bounded(path / 'compatible', 2048)) if 'compatible' in files else []
        except (OSError, UnicodeError, ValueError, TimeoutError):
            compat = []
        # Identity-bearing device declarations only. Unbound pinctrl/thermal
        # labels otherwise exhaust the bound before later camera nodes.
        if not compat or not DT_NAMES.search(path.name + ' ' + ' '.join(compat)):
            continue
        item = {'path': '/' + str(path.relative_to(DT_ROOT)), 'properties': {}}
        for name in DT_STRINGS + DT_NUMBERS:
            if name not in files:
                continue
            try:
                data = bounded(path / name, 2048)
                if name in DT_STRINGS:
                    item['properties'][name] = strings(data)
                elif len(data) % 4 == 0:
                    item['properties'][name] = list(struct.unpack('>' + 'I' * (len(data) // 4), data))
            except (OSError, UnicodeError, ValueError, TimeoutError) as exc:
                item['properties'][name] = {'unavailable': type(exc).__name__}
        records.append(item)
    return {'nodes': records, 'visited_node_count': visited,
            'complete_within_limits': complete,
            'meaning': 'DT declarations/candidates; not proof of fitted or bound hardware'}


def service_output(service):
    """Fixed read-only services; bounded capture with guaranteed child reaping."""
    if service not in ('sensorservice', 'media.camera'):
        raise ValueError('service not allowed')
    command = ['/system/bin/dumpsys', '-t', '5', service]
    data = bytearray()
    status = {'command': command, 'raw_output_retained': False}
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    try:
        deadline = time.monotonic() + 7
        fd = proc.stdout.fileno()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                status['unavailable'] = 'timeout'
                break
            ready, _, _ = select.select([fd], [], [], min(remaining, 0.2))
            if not ready:
                continue
            block = os.read(fd, 16384)
            if not block:
                break
            if len(data) + len(block) > 1024 * 1024:
                status['unavailable'] = 'output_limit'
                break
            data.extend(block)
    finally:
        try:
            proc.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=1)
        proc.stdout.close()
        status['returncode'] = proc.returncode
    if status.get('unavailable') or proc.returncode:
        return '', status
    return data.decode('utf-8', 'replace'), status


def sensor_static(text):
    records = []
    in_list = False
    current = None
    for line in text.splitlines():
        if re.match(r'^\s*Sensor List\s*(?:\([^)]*\))?\s*:', line, re.I):
            in_list = True
            continue
        if not in_list:
            continue
        match = re.match(r'^\s*(0x[0-9a-fA-F]+|\d+)\)\s*([^|]{1,160})\|\s*([^|]{1,160})\|\s*ver:\s*(\d+)\s*\|\s*type:\s*([^|]{1,160})\|', line)
        if match:
            current = {'handle': match[1], 'name': match[2].strip(), 'vendor': match[3].strip(),
                       'version': int(match[4]), 'type': match[5].strip()}
            records.append(current)
            if len(records) >= 96:
                break
            continue
        if re.search(r'Active sensors|active connections|Recent Sensor|Fusion States|Sensor Event Connection|SocketBuffer', line, re.I):
            break
        if current:
            for key in ('minRate', 'maxRate', 'maxRange', 'resolution', 'power', 'minDelay', 'maxDelay'):
                found = re.search(r'\b' + key + r'\s*=\s*([-+0-9.eE]+)(Hz|ms|us|s|mA)?', line)
                if found:
                    current[key] = {'value': found[1], 'unit': found[2]}
    return {'sensors': records, 'static_list_recognized': in_list,
            'meaning': 'Android HAL logical descriptors; fusion/virtual/uncalibrated types are not additional physical chips'}


def camera_static(text):
    result = {'counts': {}, 'devices': []}
    current = None
    pending = None
    for line in text.splitlines():
        match = re.fullmatch(r'\s*Number of (camera devices|normal camera devices|public camera devices):\s*(\d+)\s*', line)
        if match:
            result['counts'][match[1]] = int(match[2])
        if line.lstrip().startswith('=='):
            current = None
            pending = None
            match = re.search(r'Camera HAL device device@([0-9.]+)/[A-Za-z0-9_-]+/(\d+).*static information', line)
            if match:
                current = {'camera_id': match[2], 'hal_api_version': match[1], 'characteristics': {}}
                result['devices'].append(current)
            continue
        if current is None:
            continue
        match = re.fullmatch(r'\s*Facing:\s*(Front|Back|External)\s*', line, re.I)
        if match:
            current['facing'] = match[1].lower()
        match = re.fullmatch(r'\s*Orientation:\s*(\d+)\s*', line)
        if match:
            current['orientation_degrees'] = int(match[1])
        match = re.match(r'^\s*(android\.[A-Za-z0-9_.]+)\s+\((?:0x)?[0-9a-fA-F]+\):\s*(\w+)\[(\d+)\]', line)
        if match:
            pending = match[1] if match[1] in CAMERA_TAGS else None
            if pending:
                current['characteristics'][pending] = {'type': match[2], 'declared_count': int(match[3]), 'values': []}
            continue
        if pending:
            match = re.fullmatch(r'\s*\[\s*([A-Z0-9_.+\-\s]+)\s*\]\s*', line)
            if match:
                values = current['characteristics'][pending]['values']
                values.extend(match[1].split()[:max(0, 64 - len(values))])
    result['meaning'] = 'Service static enumeration only; no stream, frame, client, application or dynamic event data retained'
    return result


def capture():
    result = {'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'collector_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'scope': 'Passive Android camera/sensor/audio identities and a small static capability subset',
              'physical_streams_started': False, 'raw_service_logs_retained': False,
              'kernel_release': safe_text('/proc/sys/kernel/osrelease', 512)}
    result['i2c_clients'] = [binding(p) for p in sorted(Path('/sys/bus/i2c/devices').glob('*'))
                             if re.fullmatch(r'\d+-[0-9a-fA-F]{4}', p.name)][:64]
    result['video_class'] = [binding(p) for p in sorted(Path('/sys/class/video4linux').glob('*'))][:48]
    result['iio_devices'] = [binding(Path(p)) for p in sorted(glob.glob('/sys/bus/iio/devices/iio:device*'))][:32]
    result['sensor_class'] = []
    for directory in ('/sys/class/sensors', '/sys/class/sensor'):
        for p in sorted(Path(directory).glob('*'))[:32]:
            item = binding(p)
            for name in ('vendor', 'type', 'version', 'max_range', 'resolution', 'max_delay', 'min_delay'):
                if (p / name).is_file():
                    item[name] = safe_text(p / name, 512)
            result['sensor_class'].append(item)
    result['alsa'] = {name: safe_text('/proc/asound/' + name, 24576) for name in ('cards', 'pcm')}
    result['alsa']['card_ids'] = {str(p): safe_text(p, 512) for p in sorted(Path('/proc/asound').glob('card[0-9]*/id'))[:16]}
    result['device_tree'] = dt_inventory()
    for name, parser, key in (('sensorservice', sensor_static, 'sensor_service'),
                              ('media.camera', camera_static, 'camera_service')):
        try:
            raw, status = service_output(name)
            result[key] = {'collection': status, **parser(raw)}
            del raw
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            result[key] = {'unavailable': type(exc).__name__, 'raw_output_retained': False}
    return result


if __name__ == '__main__':
    # Only the sanitized JSON is serialized, compressed and hashed.
    data = (json.dumps(capture(), sort_keys=True, separators=(',', ':')) + '\n').encode()
    print(json.dumps({'encoding': 'gzip+base64', 'size': len(data),
                      'sha256': hashlib.sha256(data).hexdigest(),
                      'data': base64.b64encode(gzip.compress(data, mtime=0)).decode()}))
