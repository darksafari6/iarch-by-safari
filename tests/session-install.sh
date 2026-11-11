#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export HOME="$tmp/home"
export MOCK_ROOT="$tmp/system"
mkdir -p "$HOME/.config/hypr" "$HOME/.config/noctalia" "$tmp/bin" "$MOCK_ROOT"
printf 'original hypr\n' > "$HOME/.config/hypr/hyprland.conf"
printf 'original noctalia\n' > "$HOME/.config/noctalia/settings.json"
mkdir -p "$HOME/.config/gtk-3.0" "$HOME/.config/fish"
printf 'original gtk\n' > "$HOME/.config/gtk-3.0/settings.ini"
printf 'original fish\n' > "$HOME/.config/fish/config.fish"
cat > "$tmp/bin/sudo" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  install) mkdir -p "$MOCK_ROOT$(dirname "$4")"; cp "$3" "$MOCK_ROOT$4" ;;
  rm) rm -f "$MOCK_ROOT${3}" ;;
  *) echo "Unexpected sudo command: $*" >&2; exit 1 ;;
esac
MOCK
cat > "$tmp/bin/git" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[[ $1 == -c && $3 == clone ]]
target=${@: -1}
mkdir -p "$target/.git"
touch "$target/shell.qml"
MOCK
printf '#!/bin/sh\nexit 0\n' > "$tmp/bin/curl"
cat > "$tmp/bin/Hyprland" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "$XDG_CONFIG_HOME" "$@" > "$MOCK_ROOT/launched"
MOCK
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"

bash -n "$repo/legacy/install-v4-session.sh" "$repo/legacy/uninstall-v4-session.sh" "$repo/legacy/session/minimalinux-session"
"$repo/legacy/install-v4-session.sh" --help >/dev/null
if "$repo/legacy/install-v4-session.sh" --unknown >/dev/null 2>&1; then echo 'Unknown argument accepted' >&2; exit 1; fi
printf 'n\n' | "$repo/legacy/install-v4-session.sh" --skip-packages >/dev/null
[[ ! -e "$HOME/.config/minimalinux" ]]
printf 'y\n' | (cd / && "$repo/legacy/install-v4-session.sh" --skip-packages) >/dev/null
[[ $(cat "$HOME/.config/hypr/hyprland.conf") == 'original hypr' ]]
[[ $(cat "$HOME/.config/noctalia/settings.json") == 'original noctalia' ]]
[[ $(cat "$HOME/.config/gtk-3.0/settings.ini") == 'original gtk' ]]
[[ $(cat "$HOME/.config/fish/config.fish") == 'original fish' ]]
[[ -x "$HOME/.config/minimalinux/hypr/Scripts/browser-launcher.sh" ]]
python3 - "$HOME/.config/minimalinux" <<'PYTEST'
import configparser, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
gtk = configparser.ConfigParser()
gtk.read(root / 'gtk-3.0/settings.ini')
assert gtk['Settings']['gtk-theme-name'] == 'adw-gtk3-dark'
assert gtk['Settings']['gtk-icon-theme-name'] == 'Papirus-Dark'
assert gtk['Settings']['gtk-cursor-theme-name'] == 'Bibata-Modern-Classic'
settings = json.loads((root / 'noctalia/settings.json').read_text())
assert settings['settingsVersion'] == 49
assert settings['colorSchemes']['predefinedScheme'] == 'Tokyo Night'
assert settings['appLauncher']['terminalCommand'] == 'kitty -e'
assert settings['appLauncher']['iconMode'] == 'native'
assert 'JetBrainsMono Nerd Font Mono' in (root / 'kitty/kitty.conf').read_text()
assert 'fish_autosuggestion_enabled 1' in (root / 'fish/config.fish').read_text()
PYTEST
if command -v fish >/dev/null; then
    fish --no-config --no-execute "$HOME/.config/minimalinux/fish/config.fish"
fi
[[ -f "$HOME/.config/minimalinux/quickshell/noctalia-shell/shell.qml" ]]
[[ ! -e "$HOME/.config/minimalinux/quickshell/noctalia-shell/.git" ]]
# shellcheck disable=SC2016  # the literal $HOME path is what must appear in the file
grep -Fq '$HOME/.config/minimalinux/hypr/monitors.conf' "$HOME/.config/minimalinux/hypr/hyprland.conf"
# shellcheck disable=SC2088  # the literal tilde path is what must appear in the file
grep -Fq '~/.config/minimalinux/hypr/keybinds.conf' "$HOME/.config/minimalinux/noctalia/plugins/hyprland-keybinds/manifest.json"
grep -Fq 'Name=iArch by Safari (isolated session)' "$MOCK_ROOT/usr/share/wayland-sessions/minimalinux.desktop"
grep -Fq 'Name=iArch by Safari Customize' "$MOCK_ROOT/usr/share/applications/minimalinux-customize.desktop"
[[ -f "$HOME/.config/minimalinux/minimalinux/center.py" ]]
grep -Fq -- '--welcome-once' "$HOME/.config/minimalinux/hypr/startup.conf"
bash "$MOCK_ROOT/usr/local/bin/minimalinux-session"
grep -Fxq "$HOME/.config/minimalinux" "$MOCK_ROOT/launched"
grep -Fxq "$HOME/.config/minimalinux/hypr/hyprland.conf" "$MOCK_ROOT/launched"
printf 'custom config\n' > "$HOME/.config/minimalinux/custom"
printf 'y\n' | "$repo/legacy/install-v4-session.sh" --skip-packages >/dev/null
backups=("$HOME"/.config/minimalinux.backup.*)
[[ ${#backups[@]} == 1 && $(cat "${backups[0]}/custom") == 'custom config' ]]
printf 'n\n' | "$repo/legacy/uninstall-v4-session.sh" >/dev/null
[[ -f "$HOME/.config/minimalinux/hypr/hyprland.conf" ]]
printf 'y\n' | "$repo/legacy/uninstall-v4-session.sh" >/dev/null
[[ -f "$HOME/.config/minimalinux/hypr/hyprland.conf" ]]
[[ -f "$HOME/.config/hypr/hyprland.conf" ]]
rm -rf "$HOME/.config/minimalinux"
if bash "$MOCK_ROOT/usr/local/bin/minimalinux-session" >/dev/null 2>&1; then echo 'Missing config accepted' >&2; exit 1; fi
echo 'Session installer tests passed.'
