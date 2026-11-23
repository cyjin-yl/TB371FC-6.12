#!/usr/bin/env python3
"""Read only this owner's fixed KGSL identity/DT properties; no GPU controls."""
import datetime
import json
from pathlib import Path

base = Path('/sys/firmware/devicetree/base/soc/qcom,kgsl-3d0@3d00000')
record = {'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'scope': 'stock Android declared GPU identity only; no MMIO/register read or mainline execution',
          'kernel_release': Path('/proc/sys/kernel/osrelease').read_text().strip(),
          'gpu_model': Path('/sys/class/kgsl/kgsl-3d0/gpu_model').read_text().strip(),
          'properties': {}}
for name in ('compatible', 'qcom,chipid', 'status'):
    path = base / name
    try:
        value = path.read_bytes()
    except FileNotFoundError:
        record['properties'][str(path)] = {'absent': True}
        continue
    if len(value) > 1024:
        raise ValueError('unexpectedly large identity property')
    entry = {'size_bytes': len(value), 'hex': value.hex()}
    if name == 'qcom,chipid':
        if len(value) != 4:
            raise ValueError('expected one big-endian chip-id cell')
        entry['chip_id_hex'] = f'0x{int.from_bytes(value, "big"):08x}'
    else:
        entry['strings'] = value.rstrip(b'\0').decode('ascii').split('\0')
    record['properties'][str(path)] = entry
print(json.dumps(record, indent=2, sort_keys=True))
