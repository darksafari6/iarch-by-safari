#!/usr/bin/env bash
# DEPRECATED legacy uninstaller (v4 session). Kept for existing installs; use ./uninstall.sh.
# Removes only the system-wide launchers installed by legacy/install-v4-session.sh.
set -euo pipefail

if (( EUID == 0 )); then
    echo 'Run ./legacy/uninstall-v4-session.sh as the user who installed the session, not with sudo.' >&2
    exit 1
fi
config="$HOME/.config/minimalinux"
launcher=/usr/local/bin/minimalinux-session
# This script sits in legacy/, but lib/ is at the repository root.
legacy_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo=$(dirname -- "$legacy_dir")
desktop=/usr/share/wayland-sessions/minimalinux.desktop
center_launcher=/usr/local/bin/minimalinux-customize
center_desktop=/usr/share/applications/minimalinux-customize.desktop

echo 'This removes the system-wide iArch by Safari session and customization launchers for ALL users.'
echo "Your current session configuration ($config) will be kept."
echo 'Other desktop configs, backups and packages will not be removed.'
read -r -p 'Continue? [y/N] ' answer
case "$answer" in y|Y|yes|YES) ;; *) echo 'Cancelled.'; exit 0 ;; esac
source "$repo/lib/managed-files.sh"
system_paths=("$desktop" "$launcher" "$center_desktop" "$center_launcher")
system_sources=("$legacy_dir/session/minimalinux.desktop" "$legacy_dir/session/minimalinux-session"
                "$legacy_dir/session/minimalinux-customize.desktop" "$legacy_dir/session/minimalinux-customize")
warning=false
for i in "${!system_paths[@]}"; do
    path=${system_paths[$i]}
    file_state=$(managed_file_state "${system_sources[$i]}" "$path")
    case $file_state in
        absent) ;;
        identical) sudo rm -- "$path"; echo "Removed $path" ;;
        *) echo "Not removing $file_state file: $path" >&2; warning=true ;;
    esac
done
if $warning; then
    echo 'Some files were retained. Inspect them manually; source versions may differ.' >&2
    exit 1
fi
echo 'Done. You can manually remove ~/.config/minimalinux and its backups if no longer needed.'
