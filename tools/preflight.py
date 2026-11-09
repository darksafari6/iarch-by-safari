#!/usr/bin/env python3
"""Read-only hardware and environment report for minimaLinux."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def command(*args, timeout=5):
    if not shutil.which(args[0]):
        return None
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def read(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return ''


def os_info():
    result = {}
    for line in read('/etc/os-release').splitlines():
        key, sep, value = line.partition('=')
        if sep and key in ('ID', 'ID_LIKE', 'PRETTY_NAME'):
            result[key] = value.strip().strip('"\'')
    return result


def collect(network=True):
    info = os_info()
    cpu = command('lscpu') or read('/proc/cpuinfo')
    cpu_line = next((line.split(':', 1)[1].strip() for line in cpu.splitlines()
                     if line.startswith(('Model name:', 'model name\t:', 'Hardware\t:')) and ':' in line), 'Unknown')
    memory = next((line.split(':', 1)[1].strip() for line in read('/proc/meminfo').splitlines()
                   if line.startswith('MemTotal:')), 'Unknown')
    try:
        disk_free = shutil.disk_usage(Path.home()).free
    except OSError:
        disk_free = None
    try:
        root_free = shutil.disk_usage('/').free
    except OSError:
        root_free = None
    pci = command('lspci', '-nn')
    gpus = [line.strip() for line in pci.splitlines()
            if any(x in line.lower() for x in ('vga compatible controller', '3d controller', 'display controller'))] if pci else []
    chassis = read('/sys/class/dmi/id/chassis_type')
    portable = chassis in {'8', '9', '10', '11', '12', '14', '18', '21', '30', '31', '32'}
    try:
        battery = any(read(p / 'type').lower() == 'battery' for p in Path('/sys/class/power_supply').iterdir())
    except OSError:
        battery = False
    machine = 'Laptop/portable (detected)' if portable or battery else ('Desktop (DMI reported)' if chassis in {'3', '4', '5', '6', '7', '15', '16'} else 'Unknown')
    nvidia = any('nvidia' in line.lower() or '[10de:' in line.lower() for line in gpus)
    nvidia_smi = command('nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader') if nvidia else None
    pacman_exists = bool(shutil.which('pacman'))
    pacman_db = command('pacman', '-Qq', timeout=10) if pacman_exists else None
    network_status = 'Not checked'
    if network:
        if shutil.which('curl'):
            network_status = 'GitHub reachable' if command('curl', '-fsSI', '--connect-timeout', '2', '--max-time', '4', 'https://github.com', timeout=5) is not None else 'GitHub check failed (network, DNS, proxy or policy)'
        else:
            network_status = 'Unknown (curl not installed)'
    return {
        'os': info.get('PRETTY_NAME', 'Unknown'), 'os_id': info.get('ID', 'unknown'),
        'official_arch': info.get('ID') == 'arch' and Path('/etc/arch-release').is_file(),
        'architecture': platform.machine(), 'cpu': cpu_line, 'memory': memory,
        'home_free_bytes': disk_free, 'root_free_bytes': root_free, 'device': machine, 'graphics': gpus,
        'graphics_status': 'Detected' if gpus else ('No graphics controller found' if pci else 'Unknown (lspci missing or failed)'),
        'nvidia': nvidia, 'nvidia_driver': nvidia_smi or ('Not detected by nvidia-smi' if nvidia else 'Not applicable / unknown'),
        'nvidia_module_loaded': Path('/sys/module/nvidia').is_dir() if nvidia else False,
        'nvidia_packages': [p for p in ('nvidia', 'nvidia-open', 'nvidia-dkms', 'nvidia-open-dkms') if pacman_db and p in pacman_db.splitlines()] if nvidia else [],
        'display_session': os.environ.get('XDG_SESSION_TYPE', 'Unknown'),
        'desktop': os.environ.get('XDG_CURRENT_DESKTOP', 'Unknown'),
        'hyprland_command': shutil.which('Hyprland') or 'Not found',
        'pacman': ('Local package database readable' if pacman_db is not None else 'Missing or local database query failed'),
        'pacman_lock': Path('/var/lib/pacman/db.lck').exists(),
        'sudo': 'Available' if shutil.which('sudo') else 'Not found',
        'network': network_status,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Output machine-readable JSON')
    parser.add_argument('--no-network', action='store_true', help='Skip the outbound connectivity check')
    parser.add_argument('--require-arch', action='store_true', help='Exit nonzero unless this is vanilla Arch Linux')
    args = parser.parse_args()
    report = collect(network=not args.no_network)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print('Hardware & compatibility (read-only)')
        for label, key in [('OS', 'os'), ('Architecture', 'architecture'), ('CPU', 'cpu'), ('RAM', 'memory'),
                           ('Device type', 'device'), ('Display session', 'display_session'), ('Desktop', 'desktop'),
                           ('Hyprland', 'hyprland_command'), ('Pacman', 'pacman'), ('Sudo', 'sudo'), ('Network', 'network')]:
            print(f'  {label}: {report[key]}')
        free = report['home_free_bytes']
        print('  Home free space:', f'{free / (1024 ** 3):.1f} GiB' if free is not None else 'Unknown')
        root_free = report['root_free_bytes']
        print('  Root free space:', f'{root_free / (1024 ** 3):.1f} GiB' if root_free is not None else 'Unknown')
        print('  Graphics:', report['graphics_status'])
        for gpu in report['graphics']:
            print('    ' + gpu)
        if report['nvidia']:
            print('  NVIDIA driver:', report['nvidia_driver'])
            print('  NVIDIA kernel module:', 'loaded' if report['nvidia_module_loaded'] else 'not detected')
            print('  NVIDIA driver packages:', ', '.join(report['nvidia_packages']) or 'not detected (or pacman unavailable)')
            print('  NVIDIA: verify the driver and Hyprland guidance manually; no driver will be changed.')
        if report['pacman_lock']:
            print('  Warning: pacman lock exists; check for active package operations. Do not delete it automatically.')
        if not report['official_arch']:
            print('  Warning: this is not verified as vanilla Arch Linux. Derivatives are not supported.')
    return 1 if args.require_arch and not report['official_arch'] else 0


if __name__ == '__main__':
    sys.exit(main())
