#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read a single local statistics sample; no polling, subprocesses or network."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import shell_data  # noqa: E402


def sample(proc=Path('/proc'), thermal=Path('/sys/class/thermal'), disk=Path('/')):
    result = {'cpu': None, 'memory': None, 'disk': None, 'temperature': None, 'errors': {}}
    for key, path, parser in (('cpu', proc / 'stat', shell_data.cpu_counters),
                              ('memory', proc / 'meminfo', shell_data.memory_usage)):
        try:
            result[key] = parser(path.read_text(encoding='ascii'))
        except (OSError, ValueError) as exc:
            result['errors'][key] = str(exc)
    try:
        info = os.statvfs(disk)
        total = info.f_blocks * info.f_frsize
        free = info.f_bavail * info.f_frsize
        result['disk'] = {'total': total, 'used': total - free}
    except OSError as exc:
        result['errors']['disk'] = str(exc)
    try:
        for path in sorted(thermal.glob('thermal_zone*/temp')):
            try:
                temperature = int(path.read_text(encoding='ascii').strip()) / 1000
                if -50 <= temperature <= 200:
                    result['temperature'] = temperature
                    break
            except (OSError, ValueError):
                continue
        if result['temperature'] is None:
            result['errors']['temperature'] = 'no readable thermal zone'
    except OSError as exc:
        result['errors']['temperature'] = str(exc)
    return result


def main():
    print(json.dumps(sample(), separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
