#!/usr/bin/env python3
"""Read-only hardware and environment report for iArch by Safari.

Nothing here changes anything: every probe is a read of /proc, /sys, a file under
/etc, or a command that only reports (`lscpu`, `lspci`, `nvidia-smi`, `pacman -Qq`,
`curl -I`). That is what makes it safe to run before the installer's first
privileged step, and what `install.sh` does with it.

Three outputs, one report:

* no flag       the same facts as prose, for a person deciding whether to install;
* `--json`      the report as JSON, which is what the installer writes to
                `~/.local/state/iarch/preflight.json` and records in its manifest;
* `--blockers`  one `BLOCKER:` or `WARN:` line per finding, and exit 1 if any
                blocker. `--from-report PATH` reads a JSON report already written
                instead of collecting a second one, so the decision and the file a
                person can read afterwards are the same facts.

A blocker is a fact that makes the run certain to fail rather than a judgement
about whether it should: this is not vanilla Arch Linux (every package array and
the AUR are Arch-only), another package transaction holds
`/var/lib/pacman/db.lck`, or pacman is not there at all. Everything else is a
warning, including the outbound probe, because what it reaches is GitHub while
what the first step needs is `keyserver.ubuntu.com` and `cdn-mirror.chaotic.cx`
-- a machine behind an allowlist can fail one and serve the other, and refusing
it would be a guess dressed as a decision. For the same reason there is no
free-space floor: a threshold nobody measured is a number that cries wolf, and
the report prints both free spaces for a person to judge.
"""
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


#: The two package sources the first privileged step fetches, named in the
#: warning rather than implied: `setup_chaotic_aur` receives a key from
#: keyserver.ubuntu.com and installs two packages by URL from cdn-mirror.chaotic.cx.
FIRST_STEP_NEEDS = ("keyserver.ubuntu.com", "cdn-mirror.chaotic.cx")


def findings(report):
    """(kind, text) for everything in a report an installer should act on.

    ``kind`` is BLOCKER or WARN. The split is deliberately narrow: a blocker is a
    fact that makes the run certain to fail, and a warning is anything that needs
    a judgement this tool does not have the evidence to make.
    """
    out = []
    if not report.get('official_arch'):
        out.append(('BLOCKER',
                    f"{report.get('os', 'this system')} is not verified as vanilla Arch Linux "
                    "(ID=arch plus /etc/arch-release); every package array this installer "
                    "reads and the AUR it builds from are Arch-only"))
    if report.get('pacman_lock'):
        out.append(('BLOCKER',
                    "/var/lib/pacman/db.lck exists, so another package transaction is "
                    "running or one ended badly; every pacman call in this run would fail "
                    "against it, and deleting the lock is not this tool's decision"))
    if str(report.get('pacman', '')).startswith('Missing'):
        out.append(('BLOCKER',
                    "pacman is not installed, so there is no package manager for this "
                    "installer to plan against"))
    elif 'failed' in str(report.get('pacman', '')).lower():
        out.append(('WARN',
                    "the local package database could not be read, so every plan "
                    "lib/packages.sh prints would be computed from nothing"))
    network = str(report.get('network', ''))
    if network.startswith('GitHub check failed'):
        out.append(('WARN',
                    "the outbound probe could not reach https://github.com, and the first "
                    "privileged step fetches a key from " + FIRST_STEP_NEEDS[0] + " and two "
                    "packages from " + FIRST_STEP_NEEDS[1] + "; a machine behind an "
                    "allowlist can fail this probe and still serve both"))
    elif network.startswith('Unknown'):
        out.append(('WARN',
                    "curl is not installed, so the outbound probe did not run and the "
                    "first privileged step's two sources were not reached for it"))
    if report.get('nvidia') and not report.get('nvidia_module_loaded'):
        out.append(('WARN',
                    "an NVIDIA controller is present and no nvidia kernel module is "
                    "loaded; this installer changes no driver, so the session needs one "
                    "before Hyprland will draw"))
    if report.get('sudo') == 'Not found':
        out.append(('WARN',
                    "sudo is not installed, and the installer drops privileges with "
                    "`sudo -u` for every file it writes as the session's own user"))
    if report.get('hyprland_command') == 'Not found':
        out.append(('WARN',
                    "Hyprland is not on PATH yet, which is expected before the core "
                    "packages install and worth knowing if this is a second run"))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', action='store_true', help='Output machine-readable JSON')
    parser.add_argument('--no-network', action='store_true', help='Skip the outbound connectivity check')
    parser.add_argument('--require-arch', action='store_true', help='Exit nonzero unless this is vanilla Arch Linux')
    parser.add_argument('--blockers', action='store_true',
                        help='Print one BLOCKER or WARN line per finding and exit 1 on a blocker')
    parser.add_argument('--from-report', metavar='PATH',
                        help='Read a JSON report already written instead of collecting one')
    args = parser.parse_args(argv)
    if args.from_report:
        try:
            report = json.loads(Path(args.from_report).read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            print(f'preflight: could not read {args.from_report}: {exc}', file=sys.stderr)
            return 2
    else:
        report = collect(network=not args.no_network)
    if args.blockers:
        found = findings(report)
        for kind, text in found:
            print(f'{kind}: {text}')
        if not found:
            print('BLOCKER: none, and no warning either')
        blocked = any(kind == 'BLOCKER' for kind, _ in found)
        if args.json:
            print(json.dumps({'report': report,
                              'findings': [{'kind': k, 'text': x} for k, x in found],
                              'blocked': blocked}, indent=2))
        return 1 if blocked else 0
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
