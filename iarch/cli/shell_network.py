#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Read a cached network sample without scanning or contacting the internet."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from iarch.lib import shell_data  # noqa: E402

# NetworkManager 1.50.0 man/nmcli.xml: terse escaping and --rescan no.
WIFI_COMMAND = ('nmcli', '--terse', '--escape', 'yes', '--fields',
                'IN-USE,SSID,SIGNAL', 'device', 'wifi', 'list', '--rescan', 'no')


def sample(proc=Path('/proc/net/dev'), run=subprocess.run):
    result = {'timestamp': time.monotonic(), 'interfaces': {}, 'networks': [],
              'available': False, 'error': None}
    try:
        result['interfaces'] = shell_data.network_counters(proc.read_text(encoding='ascii'))
    except (OSError, ValueError) as exc:
        result['error'] = f'network counters: {exc}'
    try:
        environment = dict(os.environ, LC_ALL='C')
        answer = run(WIFI_COMMAND, capture_output=True, text=True, timeout=4, env=environment, check=False)
        if answer.returncode:
            result['error'] = (result['error'] + '; ' if result['error'] else '') + 'network manager unavailable'
        else:
            result['networks'] = shell_data.wifi_networks(answer.stdout)
            result['available'] = True
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        result['error'] = (result['error'] + '; ' if result['error'] else '') + f'network manager: {exc}'
    return result


def main():
    print(json.dumps(sample(), ensure_ascii=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
