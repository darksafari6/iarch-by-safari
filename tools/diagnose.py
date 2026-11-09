#!/usr/bin/env python3
"""Read-only minimaLinux diagnostics; never changes services or drivers."""
import argparse
import grp
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import preflight


def check_command(*args, timeout=12):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
        return result.returncode, (result.stdout + result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, str(exc)


def inspect(root, state_home):
    checks = []
    def add(level, text):
        checks.append((level, text))
    for name in ('Hyprland', 'hyprctl', 'qs', 'kitty', 'fish'):
        found = shutil.which(name)
        add('OK' if found else 'WARN', f'{name}: {found or "not found"}')
    config = root / 'hypr/hyprland.conf'
    if not config.is_file():
        add('WARN', f'Hyprland configuration missing: {config}')
    else:
        for line in config.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^\s*source\s*=\s*(\S+)', line)
            if not match:
                continue
            value = match.group(1).replace('$HOME', str(Path.home()))
            path = Path(os.path.expanduser(value))
            if not path.is_file():
                add('WARN', f'Hyprland source not found: {path}')
        executable = shutil.which('Hyprland')
        if executable and os.environ.get('XDG_RUNTIME_DIR'):
            status, help_text = check_command(executable, '--help')
            if status == 0 and '--verify-config' in help_text:
                status, output = check_command(executable, '--verify-config', '--config', str(config), timeout=20)
                add('OK' if status == 0 else 'WARN', 'Hyprland --verify-config: ' + ('passed' if status == 0 else f'failed or could not run: {output[:700]}'))
            else:
                add('SKIP', 'Hyprland does not advertise --verify-config; syntax not validated.')
        else:
            add('SKIP', 'Hyprland syntax not validated: binary or XDG_RUNTIME_DIR unavailable.')
    shell = root / 'quickshell/noctalia-shell/shell.qml'
    add('OK' if shell.is_file() else 'WARN', 'Noctalia v4 shell source: ' + ('present' if shell.is_file() else f'missing ({shell})'))
    if shutil.which('pgrep'):
        status, _ = check_command('pgrep', '-u', str(os.getuid()), '-x', 'quickshell')
        add('OK' if status == 0 else 'SKIP', 'Quickshell process: ' + ('found' if status == 0 else 'not detected (may not be running or process name differs)'))
    else:
        add('SKIP', 'Quickshell process check: pgrep unavailable.')
    settings_path = root / 'noctalia/settings.json'
    try:
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
        if not isinstance(settings, dict):
            raise ValueError('not an object')
        ddc = settings.get('brightness', {}).get('enableDdcSupport', False)
        scheme = settings.get('colorSchemes', {}).get('predefinedScheme')
        add('OK', 'Noctalia settings: readable JSON')
        if scheme:
            names = {'Tokyo Night': 'Tokyo-Night', 'Noctalia (default)': 'Noctalia-default', 'Rose Pine': 'Rosepine'}
            key = names.get(scheme, scheme)
            if '/' not in key and key not in ('.', '..'):
                bundled = root / 'quickshell/noctalia-shell/Assets/ColorScheme' / key / (key + '.json')
                if not bundled.is_file():
                    add('WARN', f'Bundled Noctalia scheme not found: {scheme}; it may be a custom scheme.')
        if ddc:
            add('OK' if shutil.which('ddcutil') else 'WARN', 'DDC/CI enabled; ddcutil ' + ('found' if shutil.which('ddcutil') else 'missing'))
            groups = [grp.getgrgid(g).gr_name for g in os.getgroups() if g is not None]
            add('OK' if 'i2c' in groups else 'WARN', 'DDC i2c group: ' + ('present' if 'i2c' in groups else 'not detected'))
            add('OK' if list(Path('/dev').glob('i2c-*')) else 'WARN', 'DDC I2C devices: ' + ('present' if list(Path('/dev').glob('i2c-*')) else 'not detected'))
            add('SKIP', 'Monitors were not probed; check DDC/CI in the monitor OSD and test manually.')
        else:
            add('SKIP', 'DDC/CI is not enabled in session settings.')
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
        add('WARN', f'Noctalia settings could not be checked: {exc}')
    if shutil.which('systemctl'):
        for scope, service in [('--user', 'pipewire.service'), ('--user', 'wireplumber.service'), ('--system', 'bluetooth.service')]:
            status, output = check_command('systemctl', scope, 'is-active', service)
            level = 'OK' if status == 0 else ('WARN' if output in ('inactive', 'failed') else 'SKIP')
            add(level, f'{service}: {output or "status unavailable"}')
    else:
        add('SKIP', 'systemctl unavailable; audio and Bluetooth status not checked.')
    logs = sorted((state_home / 'minimalinux/logs').glob('install.*.log'))
    if logs:
        log = max(logs, key=lambda p: p.stat().st_mtime)
        try:
            content = log.read_text(encoding='utf-8', errors='replace')
            finished = 'SUCCESS session configuration' in content
            add('OK' if finished else 'WARN', f'Latest install log: {log} ({"complete" if finished else "no success marker; review for interruption or failure"})')
        except OSError as exc:
            add('WARN', f'Cannot read install log: {exc}')
    else:
        add('SKIP', 'No installer log found (older installs may predate logging).')
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repair', action='store_true', help='Show repair availability; no changes are made')
    parser.add_argument('--no-network', action='store_true', help='Skip the connectivity probe')
    args = parser.parse_args()
    if args.repair:
        print('No automated repairs are implemented yet. Nothing was changed; consult InstallNotes.md for manual recovery.')
        return 1
    print('minimaLinux diagnostics — read-only (Hyprland may write its own runtime log)')
    report = preflight.collect(network=not args.no_network)
    print('OS:', report['os'], '| GPU:', report['graphics_status'], '| Network:', report['network'])
    if report['nvidia']:
        print('NVIDIA driver:', report['nvidia_driver'], '— verify driver setup manually; no driver changes are made.')
    root = Path.home() / '.config/minimalinux'
    state = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state')))
    try:
        checks = inspect(root, state)
    except OSError as exc:
        print('[WARN] Diagnostics could not read a required path:', exc, file=sys.stderr)
        return 1
    for level, text in checks:
        print(f'[{level}] {text}')
    print('No services were restarted and no configuration was changed.')
    return 1 if any(level == 'WARN' for level, _ in checks) else 0

if __name__ == '__main__':
    sys.exit(main())
