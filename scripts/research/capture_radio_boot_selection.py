#!/usr/bin/env python3
"""Bounded read of radio-selection tokens in the current Android kernel log.

Never clear the log, change verbosity, restart a radio, or expose raw lines,
SSID/BSSID/MAC values, unrelated process names or packet data. Missing tokens
only mean the current retained buffer did not provide this evidence.
"""
import datetime
import json
import re
import subprocess

LIMIT = 2 * 1024 * 1024
record = {
    'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'scope': 'current Android kernel-buffer radio-selection tokens only',
    'read_only': True, 'radio_restarted': False, 'log_cleared': False,
    'raw_log_published': False, 'selection_proven': False,
}
try:
    result = subprocess.run(['/system/bin/dmesg', '-s', str(LIMIT)],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=8)
except subprocess.TimeoutExpired:
    record['status'] = 'bounded_read_timed_out'
else:
    record['exit_code'] = result.returncode
    record['captured_bytes'] = len(result.stdout)
    if result.returncode:
        record['status'] = 'reader_failed_no_raw_diagnostics_published'
    elif len(result.stdout) > LIMIT:
        record['status'] = 'reader_exceeded_publication_bound_no_tokens_accepted'
    else:
        names, identifiers = set(), set()
        for line in result.stdout.decode('utf-8', errors='replace').splitlines():
            if not re.search(r'(?i)\b(cnss|cnss2|wlan|qcacld|ath11k|qmi)\b', line):
                continue
            names.update(re.findall(r'\b(?:bdwlan(?:[._-][A-Za-z0-9_.-]{1,48})?|board-2\.bin|amss20\.bin)\b', line))
            identifiers.update(re.findall(r'(?i)\b(?:qmi[-_ ]?)?(?:board|bdf)[-_ ]?id\s*[:=]\s*(?:0x[0-9a-f]{1,8}|[0-9]{1,10})\b', line))
        record['filename_tokens'] = sorted(names)[:32]
        record['board_id_tokens'] = sorted(identifiers)[:32]
        record['token_bound_exceeded'] = len(names) > 32 or len(identifiers) > 32
        record['status'] = 'tokens_observed_need_source_context' if names or identifiers else 'no_selection_tokens_in_retained_buffer'
record['limit'] = ('This is not a full boot trace and does not establish a WLAN board choice, '
                   'Bluetooth ROM revision, authentication, or Linux radio operation.')
print(json.dumps(record, indent=2, sort_keys=True))
