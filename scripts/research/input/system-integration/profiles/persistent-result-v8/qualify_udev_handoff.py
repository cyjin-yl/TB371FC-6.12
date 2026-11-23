#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Independent read-only post-boot qualification, derived before v8 production.

Counts cover successful stores/inserts, not automatically the original queue.
Reject every explicit storage/restore failure path in the matched v262.1
source. No count lines means no positive count proof, not an empty queue.
The already executed VM recipe and its result are never rewritten.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import stat

WORK = Path('/work/fedora-input-system-v8')
SOURCE_SHA = '49ece39cdd38f83c7112dc94df2cb8ba0e6a570bd42939b31c98bce64392ed4e'
FAILURE_PREFIXES = (
    'Failed to create new device monitor instance:',
    'Failed to get address of device monitor socket:',
    'Failed to save event to socket storage, ignoring:',
    'Failed to push event serialization fd to service manager:',
    'Received multiple event storage socket (',
    'Failed to verify type of event storage socket (',
    'Received invalid event storage socket (',
    'Failed to initialize event storage:',
    'Failed to set trusted sender for event storage:',
    'Failed to wait for event from event storage:',
    'Failed to receive device from event storage, ignoring:',
    'Failed to insert device into event queue, ignoring:',
    "Failed to store deserialized fd 'event-serialization'",
)


def read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        first = os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or not 0 < first.st_size <= limit:
            raise ValueError('ordinary bounded evidence required: ' + str(path))
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            raw = stream.read(limit + 1)
        last = os.fstat(fd)
        key = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if key(first) != key(last) or len(raw) != first.st_size:
            raise ValueError('evidence changed while being read')
        return raw
    finally:
        os.close(fd)


def identity(raw):
    return {'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default='vm-verify-01')
    args = parser.parse_args()
    if not re.fullmatch(r'vm-verify-[0-9]{2}', args.run):
        parser.error('fixed verification run name required')
    if WORK.is_symlink() or not WORK.is_dir():
        raise ValueError('independent v8 prefix required')
    result_path = WORK / args.run / 'result.json'
    raw_result = read(result_path, 1024 * 1024)
    result = json.loads(raw_result)
    raw = read(result_path.parent / 'serial.log', 8 * 1024 * 1024)
    if (identity(raw)['sha256'] != result.get('serial_log_sha256') or
            len(raw) != result.get('serial_log_bytes')):
        raise ValueError('full raw log no longer matches the original controller result')
    lines = raw.decode(errors='replace').splitlines()
    failures = {prefix: [{'line': i + 1, 'text': line} for i, line in enumerate(lines) if prefix in line]
                for prefix in FAILURE_PREFIXES}
    delimiters = [i for i, line in enumerate(lines) if 'Deserializing state' in line]
    root_lines = lines[delimiters[-1]:] if delimiters else []
    serialized = [int(m[1]) for line in lines if (m := re.search(r'\bSerialized ([0-9]+) events\.', line))]
    restored = [int(m[1]) for line in root_lines if (m := re.search(r'\bDeserialized ([0-9]+) events\.', line))]
    accepted = [line for line in root_lines if re.search(
        r'systemd-udevd\.service: Added fd [0-9]+ \(event-serialization\) to fd store\.', line)]
    positive_serialized = [n for n in serialized if n > 0]
    positive_restored = [n for n in restored if n > 0]
    conditional_counts = not positive_serialized or (bool(accepted) and positive_serialized == positive_restored)
    host_pass = (result.get('phase') == 'verify' and result.get('passed') is True and
                 result.get('qemu_exit_code') == 0 and result.get('board_dtb_used') is False and
                 result.get('physical_hardware_tested') is False)
    passed = bool(host_pass and not any(failures.values()) and conditional_counts)
    report = {'schema_version': 1, 'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'scope': 'read-only qualification of this generic VM full raw serial', 'passed': passed,
              'source_file': 'matched Fedora systemd v262.1 src/udev/udev-manager.c',
              'source_sha256': SOURCE_SHA, 'qualifier': identity(Path(__file__).read_bytes()),
              'original_controller_result': identity(raw_result), 'original_vm_passed': host_pass,
              'full_serial': identity(raw), 'run': args.run, 'failure_prefix_matches': failures,
              'no_observed_storage_or_restore_failure': not any(failures.values()),
              'root_state_deserialization_delimiter_lines': [n + 1 for n in delimiters],
              'serialized_counts': serialized, 'root_restored_counts': restored,
              'root_accepted_fd_lines': accepted, 'conditional_count_gate_passed': conditional_counts,
              'positive_count_proof_observed': bool(positive_serialized and accepted and
                                                   positive_serialized == positive_restored),
              'debug_count_absence_means_empty_queue': False,
              'entire_original_queue_independently_inventoried': False,
              'counts_scope': 'successful device_monitor_send and event_queue_insert operations only',
              'physical_tablet_tested': False, 'vm_result_or_log_modified': False}
    output = WORK / ('udev-handoff-qualification-' + args.run + '.json')
    with output.open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'passed': passed, 'report': str(output), **identity(output.read_bytes())}, sort_keys=True))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
