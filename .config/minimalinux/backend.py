"""Session-scoped customization helpers. No graphical dependencies."""
import configparser
from contextlib import contextmanager
from datetime import datetime
import stat
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path.home() / '.config' / 'minimalinux'
THEMES = {
    'Tokyo Night': {'scheme': 'Tokyo Night', 'dark': True, 'accent': '7aa2f7', 'secondary': 'bb9af7', 'bg': '1a1b26', 'fg': 'c0caf5'},
    'Catppuccin': {'scheme': 'Catppuccin', 'dark': True, 'accent': '89b4fa', 'secondary': 'cba6f7', 'bg': '1e1e2e', 'fg': 'cdd6f4'},
    'Nord': {'scheme': 'Nord', 'dark': True, 'accent': '88c0d0', 'secondary': 'b48ead', 'bg': '2e3440', 'fg': 'eceff4'},
    'Dracula': {'scheme': 'Dracula', 'dark': True, 'accent': 'bd93f9', 'secondary': 'ff79c6', 'bg': '282a36', 'fg': 'f8f8f2'},
    'Light': {'scheme': 'Noctalia (default)', 'dark': False, 'accent': '4b5eaa', 'secondary': '7455a3', 'bg': 'f2f2fa', 'fg': '24243a'},
}
ICONS = {'Papirus Dark': 'Papirus-Dark', 'Papirus Light': 'Papirus', 'Adwaita': 'Adwaita'}
OPTIONAL_APPS = {'Firefox browser': 'firefox', 'Audio controls': 'pavucontrol', 'Image viewer': 'loupe', 'Text editor': 'mousepad'}


def write(path, text):
    """Replace only the target file, without truncating it on an error."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f'Refusing to replace a symlink: {path}')
    old_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.minimalinux-', dir=path.parent)
    try:
        if old_mode is not None:
            os.fchmod(fd, old_mode)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def settings_update(changes):
    path = ROOT / 'noctalia/settings.json'
    # Never replace damaged or unexpected settings with defaults.
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Noctalia settings must be a JSON object')
    for section, values in changes.items():
        target = data.setdefault(section, {})
        if not isinstance(target, dict):
            raise ValueError(f'Invalid Noctalia section: {section}')
        target.update(values)
    write(path, json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def ipc(*args):
    if os.environ.get('XDG_CONFIG_HOME') != str(ROOT):
        raise RuntimeError('Open minimaLinux to control its Noctalia session.')
    if not shutil.which('qs'):
        raise RuntimeError('Noctalia is not running or qs is not installed.')
    try:
        result = subprocess.run(['qs', '-c', 'noctalia-shell', 'ipc', 'call', *args],
                                capture_output=True, text=True, timeout=8, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Noctalia did not respond.') from exc
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or 'Noctalia did not respond.')


def gtk_settings(dark, icon, font):
    if icon not in ICONS.values():
        raise ValueError('Unsupported icon theme')
    if not font or '\n' in font or '\r' in font:
        raise ValueError('Invalid font')
    for version in ('gtk-3.0', 'gtk-4.0'):
        path = ROOT / version / 'settings.ini'
        config = configparser.ConfigParser(interpolation=None)
        if path.exists():
            config.read(path, encoding='utf-8')
        if not config.has_section('Settings'):
            config.add_section('Settings')
        config.set('Settings', 'gtk-application-prefer-dark-theme', '1' if dark else '0')
        if version == 'gtk-3.0':
            config.set('Settings', 'gtk-theme-name', 'adw-gtk3-dark' if dark else 'adw-gtk3')
        config.set('Settings', 'gtk-icon-theme-name', icon)
        config.set('Settings', 'gtk-font-name', font)
        import io
        output = io.StringIO()
        config.write(output)
        write(path, output.getvalue())


@contextmanager
def backup_files(paths):
    """Back up a bounded set of session files and roll them back on failure."""
    paths = [Path(p) for p in paths]
    for path in paths:
        relative = path.relative_to(ROOT)
        cursor = ROOT
        if cursor.is_symlink():
            raise ValueError(f'Refusing to modify a symlinked session root: {cursor}')
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ValueError(f'Refusing to modify a symlink: {cursor}')
        if path.exists() and not path.is_file():
            raise ValueError(f'Expected a regular file: {path}')
    backup_root = ROOT / 'minimalinux/theme-backups'
    if (ROOT / 'minimalinux').is_symlink() or backup_root.is_symlink():
        raise ValueError('Theme backup directory must not be a symlink.')
    backup_root.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(prefix=datetime.now().strftime('%Y%m%d-%H%M%S') + '.', dir=backup_root))
    records = []
    for path in paths:
        relative = path.relative_to(ROOT)
        present = path.is_file()
        if present:
            destination = directory / 'files' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        records.append({'path': str(relative), 'present': present})
    (directory / 'manifest.json').write_text(json.dumps(records, indent=2) + '\n', encoding='utf-8')
    try:
        yield directory
    except Exception as exc:
        failures = []
        for item in records:
            target = ROOT / item['path']
            try:
                cursor = ROOT
                for part in Path(item['path']).parts:
                    cursor = cursor / part
                    if cursor.is_symlink():
                        raise ValueError('destination or parent became a symlink')
                if item['present']:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(directory / 'files' / item['path'], target)
                elif target.exists():
                    target.unlink()  # Only a file created by this failed operation.
            except (OSError, ValueError) as rollback_error:
                failures.append(f'{target}: {rollback_error}')
        if failures:
            raise RuntimeError(f'Theme change failed; manual recovery from {directory} required: {"; ".join(failures)}') from exc
        raise RuntimeError(f'Theme change failed and was rolled back; backup: {directory}: {exc}') from exc


def theme(name, icon, font):
    if name not in THEMES:
        raise ValueError('Unsupported theme')
    t = THEMES[name]
    warnings = []
    settings_path = ROOT / 'noctalia/settings.json'
    noctalia_available = settings_path.exists() or settings_path.is_symlink()
    hypr_available = (ROOT / 'hypr/hyprland.conf').is_file()
    kitty_available = (ROOT / 'kitty/kitty.conf').is_file()
    if noctalia_available:
        if settings_path.is_symlink():
            raise ValueError('Refusing to replace symlinked Noctalia settings.')
        settings = json.loads(settings_path.read_text(encoding='utf-8'))
        if not isinstance(settings, dict) or any(not isinstance(settings.get(k, {}), dict) for k in ('ui', 'colorSchemes')):
            raise ValueError('Invalid Noctalia settings; nothing was changed.')
    else:
        warnings.append('Noctalia settings missing; skipped')
    if not hypr_available:
        warnings.append('Hyprland config missing; skipped')
    if not kitty_available:
        warnings.append('Kitty config missing; skipped')
    paths = [ROOT / 'gtk-3.0/settings.ini', ROOT / 'gtk-4.0/settings.ini']
    if hypr_available:
        paths.append(ROOT / 'hypr/themes/colors.conf')
    if kitty_available:
        paths.append(ROOT / 'kitty/minima-colors.conf')
    if noctalia_available:
        paths.append(settings_path)
    with backup_files(paths):
        gtk_settings(t['dark'], icon, font)
        if hypr_available:
            write(ROOT / 'hypr/themes/colors.conf',
                  '# Generated by minimaLinux.\ngeneral {\n    col.active_border = rgba(' + t['accent'] + 'ff) rgba(' + t['secondary'] + 'ff) 45deg\n}\n')
        if kitty_available:
            kitty_colors(name)
        if noctalia_available:
            settings_update({'colorSchemes': {'predefinedScheme': t['scheme'], 'darkMode': t['dark'], 'useWallpaperColors': False},
                             'ui': {'fontDefault': re.sub(r'\s+\d+(?:\.\d+)?$', '', font)}})

    if hypr_available and os.environ.get('XDG_CONFIG_HOME') == str(ROOT) and os.environ.get('HYPRLAND_INSTANCE_SIGNATURE') and shutil.which('hyprctl'):
        if subprocess.run(['hyprctl', 'reload'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False).returncode != 0:
            warnings.append('Hyprland reload failed; reload or relog manually')
    return warnings


def kitty_colors(name):
    if name not in THEMES:
        raise ValueError('Unsupported theme')
    t = THEMES[name]
    # A small palette: ANSI colors remain readable in both light and dark modes.
    palette = [t['bg'], 'f7768e', '9ece6a', 'e0af68', t['accent'], t['secondary'], '7dcfff', t['fg'],
               '565f89', 'f7768e', '9ece6a', 'e0af68', t['accent'], t['secondary'], '7dcfff', t['fg']]
    if not t['dark']:
        palette = ['24243a', 'b42338', '3b6f28', '8f5b00', t['accent'], t['secondary'], '006b78', 'd5d5df',
                   '646477', 'b42338', '3b6f28', '8f5b00', t['accent'], t['secondary'], '006b78', 'ffffff']
    lines = [f'# {name} — generated by minimaLinux', f'foreground #{t["fg"]}', f'background #{t["bg"]}',
             f'cursor #{t["fg"]}', f'url_color #{t["accent"]}']
    lines += [f'color{i} #{color}' for i, color in enumerate(palette)]
    write(ROOT / 'kitty/minima-colors.conf', '\n'.join(lines) + '\n')


def terminal_profile(font, size, prompt):
    fonts = {'JetBrains Mono': 'JetBrainsMono Nerd Font Mono', 'Monospace': 'monospace'}
    if font not in fonts or prompt not in ('Detailed', 'Minimal') or not 8 <= float(size) <= 24:
        raise ValueError('Invalid terminal profile')
    paths = [ROOT / 'kitty/minima-profile.conf', ROOT / 'fish/conf.d/minimalinux-prompt.fish']
    with backup_files(paths):
        write(paths[0], f'# Generated by minimaLinux\nfont_family {fonts[font]}\nfont_size {float(size):g}\n')
        write(paths[1], '# Generated by minimaLinux\nset -gx STARSHIP_CONFIG "$XDG_CONFIG_HOME/minimalinux/starship-' + prompt.lower() + '.toml"\n')


def terminal_colors(name):
    with backup_files([ROOT / 'kitty/minima-colors.conf']):
        kitty_colors(name)


def desktop_settings(changes):
    with backup_files([ROOT / 'noctalia/settings.json']):
        settings_update(changes)



def shortcuts():
    pattern = re.compile(r'^\s*bind\w*\s*=\s*([^,]*),\s*([^,]*),.*?#"([^"]+)"')
    rows = []
    for line in (ROOT / 'hypr/keybinds.conf').read_text(encoding='utf-8').splitlines():
        match = pattern.match(line)
        if match:
            mod, key, label = (value.strip() for value in match.groups())
            rows.append((' + '.join(filter(None, (mod, key))), label))
    return rows


def install_optional(labels):
    if not labels or any(label not in OPTIONAL_APPS for label in labels):
        raise ValueError('Select at least one listed application')
    if not shutil.which('kitty'):
        raise RuntimeError('Kitty is not installed')
    packages = [OPTIONAL_APPS[label] for label in labels]
    # Fixed command plus an allowlisted argument array, never shell-interpolated.
    script = 'sudo pacman -S --needed "$@"; status=$?; echo; read -r -p "Press Enter to close..."; exit "$status"'
    subprocess.Popen(['kitty', '-e', 'bash', '-c', script, 'minimalinux-install', *packages], start_new_session=True)
