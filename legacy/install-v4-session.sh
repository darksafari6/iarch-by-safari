#!/usr/bin/env bash
# DEPRECATED legacy installer (v4 session). Kept for existing installs; use ./install.sh.
# Install the iArch by Safari isolated session alongside an existing desktop, not over it.
#
# This script lives in legacy/ because it deploys the v4 payload: the Hyprlang
# .conf files and the v4 Noctalia settings.json under legacy/config/, plus the
# session launchers under legacy/session/. It still shares the repository-wide
# helpers in lib/ and tools/, so it resolves those from the parent directory.
set -Eeuo pipefail

usage() {
    cat <<'HELP'
Usage: ./legacy/install-v4-session.sh [OPTIONS]

Install the iArch by Safari isolated Wayland session for the current user.

  -v, --verbose        Show commands and detailed progress (no shell tracing).
  --skip-packages      Only deploy the session; dependencies must already exist.
  --no-network-check   Skip the preflight connectivity probe (source download still needs network).
  --theme THEME        Initial theme: tokyo, catppuccin, nord, dracula, or light.
  --apps LIST          Optional packages: firefox,audio,images,editor (comma-separated).
  --no-welcome         Do not automatically open the welcome screen on login.
  --glass              Opt in to the experimental Noctalia v4 glass preset.
  -y, --yes            Accept the installer review and use defaults for unset options.
                       sudo, pacman and the AUR helper may still prompt separately.
  -h, --help           Show this help.

Without options, a terminal guides you through the available choices. With
piped input, defaults are used and the review still requires confirmation.
The Noctalia v4 source is downloaded even with --skip-packages.
Run as your normal user, not with sudo.
HELP
}

die() {
    if [[ -n ${log_path:-} ]]; then
        log_line "FAILED $*"
        if ${registration_started:-false}; then
            printf 'Some managed launchers may already be installed; inspect the log and use legacy/uninstall-v4-session.sh if needed.\n' >&2
        fi
    fi
    printf '\nError: %s\n' "$*" >&2
    exit 1
}
verbose=false skip_packages=false skip_explicit=false yes=false welcome=true glass=false
chosen_theme=tokyo theme_explicit=false apps_explicit=false apps_value='' network_check=true
while (($#)); do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        -v|--verbose) verbose=true ;;
        --skip-packages) skip_packages=true; skip_explicit=true ;;
        --no-welcome) welcome=false ;;
        --glass) glass=true ;;
        --no-network-check) network_check=false ;;
        -y|--yes) yes=true ;;
        --theme|--apps)
            option=$1
            (($# >= 2)) || die "Missing value for $option."
            [[ -n $2 && $2 != --* ]] || die "Missing value for $option."
            if [[ $option == --theme ]]; then chosen_theme=$2; theme_explicit=true
            else apps_value=$2; apps_explicit=true; fi
            shift ;;
        *) printf 'Unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done
case "$chosen_theme" in tokyo|catppuccin|nord|dracula|light) ;; *) die "Unknown theme '$chosen_theme'; see --help." ;; esac
if (( EUID == 0 )); then die 'Run ./legacy/install-v4-session.sh as your normal user, not as root or with sudo.'; fi

# Colors are decorative only. Piped output, dumb terminals and NO_COLOR stay plain.
bold='' dim='' cyan='' purple='' green='' reset=''
if [[ -t 1 && ${TERM:-dumb} != dumb && ! ${NO_COLOR+x} ]]; then
    bold=$'\033[1m'; dim=$'\033[2m'; cyan=$'\033[36m'; purple=$'\033[35m'; green=$'\033[32m'; reset=$'\033[0m'
fi
log_path=''
PACKAGE_AUDIT_STARTED=false
log_line() { if [[ -n $log_path ]]; then printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >> "$log_path"; fi; }
heading() { printf '\n%s%s%s\n' "$bold$cyan" "$1" "$reset"; log_line "PHASE $1"; }
info() { printf '  %s\n' "$*"; log_line "INFO $*"; }
warn() { printf '  %s%s%s\n' "$bold" "$*" "$reset"; log_line "WARN $*"; }
detail() { if $verbose; then printf '  %s[verbose]%s %s\n' "$dim" "$reset" "$*"; fi; }
run() {
    if $verbose; then
        printf '  %s[command]%s' "$dim" "$reset"
        printf ' %q' "$@"
        printf '\n'
    fi
    local command_text status
    printf -v command_text '%q ' "$@"
    log_line "RUN $command_text"
    if "$@"; then
        log_line "OK $command_text"
    else
        status=$?
        log_line "FAIL exit=$status $command_text"
        printf 'Failed command (exit %s): %s\n' "$status" "$command_text" >&2
        return "$status"
    fi
}
read_choice() {
    local answer
    if ! IFS= read -r -p "$1" answer; then
        die 'Input ended before the installation was confirmed. No further changes were made.'
    fi
    REPLY=$answer
}
registration_started=false
on_error() {
    local status=$1 operation=${2:-unknown}
    log_line "FAILED exit=$status operation=$operation"
    printf 'Failed operation: %s\n' "$operation" >&2
    if $PACKAGE_AUDIT_STARTED; then
        if package_audit_finish; then log_line "Package additions: $PACKAGE_AUDIT_ADDED"; else log_line 'WARNING package additions unavailable'; fi
    fi
    printf '\nInstallation stopped (exit %s). Review the error above; rerun after fixing it.\n' "$status" >&2
    if $registration_started; then
        printf 'Some managed system launchers may already have been installed; rerun or use legacy/uninstall-v4-session.sh.\n' >&2
    fi
    printf 'Packages already installed are not automatically rolled back.\n' >&2
}
trap 'on_error $? "$BASH_COMMAND"' ERR
trap 'log_line "INTERRUPTED"; if $PACKAGE_AUDIT_STARTED; then package_audit_finish || log_line "WARNING package additions unavailable"; fi; printf "\nInstallation interrupted. Packages and registered files may require manual review.\n" >&2; exit 130' INT

# This script sits in legacy/, but lib/ and tools/ are at the repository root.
legacy_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
repo=$(dirname -- "$legacy_dir")
config="$HOME/.config/minimalinux"
launcher=/usr/local/bin/minimalinux-session
desktop=/usr/share/wayland-sessions/minimalinux.desktop
center_launcher=/usr/local/bin/minimalinux-customize
center_desktop=/usr/share/applications/minimalinux-customize.desktop

printf '\n%s%s  i A R C H   b y   S A F A R I%s\n' "$bold" "$purple" "$reset"
printf '  %sA little space of your own.%s\n' "$dim" "$reset"
printf '  ------------------------------------------------------------\n'
warn 'Legacy v4 session installer. The supported path is ./install.sh.'
info 'A separate Hyprland session for your existing Arch desktop.'
info 'Your current desktop configuration and login session stay in place.'

# Menus are only displayed when input is a terminal. Flags override their menu.
if [[ -t 0 ]] && ! $yes; then
    heading '01  /  Installation mode'
    if ! $skip_explicit; then
        printf '  1) Complete setup    Install required packages and the session [default]\n'
        printf '  2) Session only     Skip packages; install dependencies yourself\n'
        printf '  3) Cancel\n'
        while :; do
            read_choice '  Select [1-3]: '
            case "$REPLY" in ''|1) break ;; 2) skip_packages=true; break ;; 3) echo 'Cancelled.'; exit 0 ;; *) info 'Choose 1, 2, or 3.' ;; esac
        done
    else
        info 'Session-only mode selected with --skip-packages.'
    fi
    heading '02  /  Make it yours'
    if ! $theme_explicit; then
        printf '  1) Tokyo Night [default]   2) Catppuccin\n  3) Dracula                 4) Light\n  5) Nord\n'
        while :; do
            read_choice '  Choose an initial theme [1-5]: '
            case "$REPLY" in ''|1) chosen_theme=tokyo; break ;; 2) chosen_theme=catppuccin; break ;; 3) chosen_theme=dracula; break ;; 4) chosen_theme=light; break ;; 5) chosen_theme=nord; break ;; *) info 'Choose 1, 2, 3, 4, or 5.' ;; esac
        done
    else
        info "Theme selected with --theme: $chosen_theme"
    fi
    if ! $skip_packages && ! $apps_explicit; then
        printf '\n  Optional apps (space- or comma-separated; Enter skips):\n'
        printf '  1) Firefox browser   2) Audio controls\n  3) Image viewer      4) Text editor\n'
        while :; do
            read_choice '  Select [1-4]: '
            selection=${REPLY//,/ }
            apps_value=''; invalid=false
            read -r -a selections <<< "$selection"
            for item in "${selections[@]}"; do
                case "$item" in
                    1) apps_value+=firefox, ;; 2) apps_value+=audio, ;;
                    3) apps_value+=images, ;; 4) apps_value+=editor, ;;
                    *) invalid=true ;;
                esac
            done
            if ! $invalid; then apps_value=${apps_value%,}; break; fi
            info 'Use only 1, 2, 3, and 4.'
        done
    fi
    if $welcome; then
        while :; do
            read_choice '  Show welcome screen on first login? [Y/n]: '
            case "$REPLY" in ''|y|Y|yes|YES) break ;; n|N|no|NO) welcome=false; break ;; *) info 'Please answer y or n.' ;; esac
        done
    else
        info 'Welcome screen disabled with --no-welcome.'
    fi
fi

# Convert user selections to a fixed allowlist, without evaluating input.
optional_packages=()
if [[ -n $apps_value ]]; then
    [[ $apps_value != ,* && $apps_value != *, && $apps_value != *,,* ]] || die 'Invalid --apps list; see --help.'
    IFS=',' read -r -a app_names <<< "$apps_value"
    for name in "${app_names[@]}"; do
        case "$name" in firefox) pkg=firefox ;; audio) pkg=pavucontrol ;; images) pkg=loupe ;; editor) pkg=mousepad ;; *) die "Unknown optional app '$name'; see --help." ;; esac
        found=false
        for existing in "${optional_packages[@]}"; do [[ $existing == "$pkg" ]] && found=true; done
        if ! $found; then optional_packages+=("$pkg"); fi
    done
fi
if $skip_packages && ((${#optional_packages[@]})); then die 'Optional apps cannot be installed with --skip-packages.'; fi
case "$chosen_theme" in tokyo) theme_name='Tokyo Night' ;; catppuccin) theme_name=Catppuccin ;; nord) theme_name=Nord ;; dracula) theme_name=Dracula ;; light) theme_name=Light ;; esac

heading '03  /  Hardware report'
command -v python3 >/dev/null || die 'python3 is required for the read-only hardware preflight.'
preflight_args=()
if ! $network_check; then preflight_args+=(--no-network); fi
if ! $skip_packages; then preflight_args+=(--require-arch); fi
python3 "$repo/tools/preflight.py" "${preflight_args[@]}" || die 'Complete setup is supported only on vanilla Arch Linux; see the report above.'

heading '04  /  Review your setup'
if $skip_packages; then info 'Mode: session only (packages are not checked or installed)'
else info 'Mode: complete (Arch packages + noctalia-qs from your AUR helper)'; fi
info "Theme: $theme_name"
if $glass; then info 'Experimental glass preset: enabled (notification sound stays off)'; else info 'Experimental glass preset: disabled'; fi
if ((${#optional_packages[@]})); then info "Optional packages: ${optional_packages[*]}"; else info 'Optional packages: none'; fi
if $welcome; then info 'First-login welcome screen: enabled'; else info 'First-login welcome screen: disabled'; fi
info "Session configuration: $config"
info 'Existing iArch by Safari session configuration will be backed up on reinstall.'
info 'The system-wide session entries need sudo; Noctalia v4 is downloaded from GitHub.'
if ! $yes; then
    read_choice '  Continue with this setup? [y/N]: '
    case "$REPLY" in y|Y|yes|YES) ;; *) echo 'Cancelled.'; exit 0 ;; esac
fi

heading '05  /  Safety checks'
if ! $skip_packages; then
    [[ -f /etc/arch-release ]] && command -v pacman >/dev/null || die 'Complete setup requires Arch Linux and pacman.'
    helper=''
    for candidate in yay paru; do
        if command -v "$candidate" >/dev/null; then helper=$candidate; break; fi
    done
    [[ -n $helper ]] || die 'Install an AUR helper (yay or paru), then run this script again.'
    detail "AUR helper: $helper"
fi
for tool in git sudo; do command -v "$tool" >/dev/null || die "Required command not found: $tool"; done
[[ -d "$repo/.config" ]] || die 'Repository dotfiles directory is missing.'
[[ -d "$legacy_dir/config" ]] || die 'Legacy dotfiles directory is missing: legacy/config.'
if [[ -e "$HOME/.config" || -L "$HOME/.config" ]]; then
    [[ -d "$HOME/.config" && -w "$HOME/.config" ]] || die 'Your ~/.config directory is not writable.'
else
    [[ -d "$HOME" && -w "$HOME" ]] || die 'Your home directory is not writable.'
fi
if [[ $chosen_theme != tokyo ]]; then
    command -v python3 >/dev/null || die 'python3 is required to apply the selected theme.'
fi
# Preserve modified or unmanaged system files; identical managed entries need no rewrite.
source "$repo/lib/managed-files.sh"
system_paths=("$launcher" "$desktop" "$center_launcher" "$center_desktop")
system_sources=("$legacy_dir/session/minimalinux-session" "$legacy_dir/session/minimalinux.desktop"
                "$legacy_dir/session/minimalinux-customize" "$legacy_dir/session/minimalinux-customize.desktop")
system_modes=(755 644 755 644)
for i in "${!system_paths[@]}"; do
    path=${system_paths[$i]}
    source_file=${system_sources[$i]}
    file_state=$(managed_file_state "$source_file" "$path")
    case $file_state in
        absent|identical) ;;
        missing-source) die "Required launcher source is missing: $source_file" ;;
        symlink) die "Refusing to overwrite a symlink: $path" ;;
        unmanaged) die "Refusing to overwrite an unmanaged file: $path" ;;
        modified) die "Managed file has changed: $path. Back it up and resolve it manually before reinstalling." ;;
        *) die "Unexpected launcher state for: $path" ;;
    esac
done
info 'Checks passed.'
detail "Repository: $repo"
detail "Legacy payload: $legacy_dir"
# Create a private user-readable log only after confirmation and safety checks.
state_home=${XDG_STATE_HOME:-$HOME/.local/state}
[[ $state_home == /* ]] || die 'XDG_STATE_HOME must be an absolute path.'
log_dir="$state_home/minimalinux/logs"
(umask 077; mkdir -p -- "$log_dir")
log_path=$(umask 077; mktemp "$log_dir/install.$(date +%Y%m%d-%H%M%S).XXXXXXXX.log")
log_line "START user=${USER:-unknown} mode=$(if $skip_packages; then echo session-only; else echo complete; fi) theme=$theme_name"
info "Installation log: $log_path"
info 'The log records operations and status, not package-manager output or passwords.'


heading '06  /  Packages'
if ! $skip_packages; then
    core_packages=(hyprland hypridle hyprlock kitty fish fastfetch starship
        thunar polkit-gnome gnome-keyring xdg-desktop-portal-hyprland
        xdg-desktop-portal-gtk jq libnotify grim slurp hyprshot satty playerctl
        pamixer wlsunset qt6ct brightnessctl imagemagick python git
        adw-gtk-theme papirus-icon-theme bibata-cursor-theme nwg-look
        noto-fonts noto-fonts-emoji ttf-jetbrains-mono-nerd fzf zoxide eza python-gobject gtk3)
    # Capture package state without changing it; never remove packages automatically.
    source "$repo/lib/package-audit.sh"
    package_audit_begin "$log_path" || die 'Could not capture the pre-install package inventory.'
    log_line "Package baseline: $PACKAGE_AUDIT_BEFORE"
    info 'Installing Arch packages. Review pacman prompts before confirming.'
    run sudo pacman -S --needed "${core_packages[@]}" "${optional_packages[@]}"
    info 'Installing the Noctalia Quickshell runtime with your AUR helper.'
    run "$helper" -S --needed noctalia-qs
    if package_audit_finish; then log_line "Package additions: $PACKAGE_AUDIT_ADDED"; else log_line 'WARNING package additions unavailable'; info 'Warning: package additions could not be recorded.'; fi
else
    info 'Skipped. You are responsible for installing the dependencies.'
fi

heading '07  /  Prepare session'
mkdir -p "$HOME/.config"
stage=$(mktemp -d "$HOME/.config/.minimalinux-install.XXXXXX")
trap 'if [[ -n ${stage:-} && -d $stage ]]; then rm -rf -- "$stage"; fi' EXIT
detail "Staging directory: $stage"
run cp -a "$repo/.config/." "$stage/"
run cp -a "$legacy_dir/config/." "$stage/"
mkdir -p "$stage/quickshell"
info 'Downloading the compatible Noctalia v4.4.0 source...'
clone_args=(clone --depth 1 --branch v4.4.0)
if ! $verbose; then clone_args+=(--quiet); fi
run git -c advice.detachedHead=false "${clone_args[@]}" https://github.com/noctalia-dev/noctalia-shell.git "$stage/quickshell/noctalia-shell"
[[ -f "$stage/quickshell/noctalia-shell/shell.qml" ]] || die 'Noctalia source did not contain shell.qml; nothing was deployed.'
if $glass; then
    # Refuse unknown v4/v5 source layouts rather than applying settings blindly.
    noctalia_commit=$(git -C "$stage/quickshell/noctalia-shell" rev-parse HEAD)
    [[ $noctalia_commit == 55e9b3735d78aef8fdab49d3d3d7d31d81628b49 ]] || die 'Glass preset requires the audited Noctalia v4.4.0 source commit.'
    info 'Applying the experimental v4 glass preset to the staging tree...'
    run python3 "$repo/tools/glass_preset.py" "$stage"
fi
rm -rf -- "$stage/quickshell/noctalia-shell/.git"
# Keep the original dotfiles inside the isolated session tree.
for path in "$stage/hypr/hyprland.conf" "$stage/hypr/animations.conf" "$stage/hypr/keybinds.conf"; do
    sed -i 's|\$HOME/\.config/hypr|$HOME/.config/minimalinux/hypr|g; s|~/\.config/hypr|~/.config/minimalinux/hypr|g' "$path"
done
for path in "$stage/noctalia/plugins/hyprland-keybinds/Main.qml" \
            "$stage/noctalia/plugins/hyprland-keybinds/DesktopWidget.qml" \
            "$stage/noctalia/plugins/hyprland-keybinds/manifest.json" \
            "$stage/noctalia/plugins/hyprland-keybinds/settings.json"; do
    sed -i 's|~/\.config/hypr|~/.config/minimalinux/hypr|g' "$path"
done
if ! $welcome; then
    sed -i '/^exec-once = .*center\.py.*--welcome-once/s/^/# /' "$stage/hypr/startup.conf"
fi
if [[ $chosen_theme != tokyo ]]; then
    info "Applying the $theme_name preset..."
    # Use the same preset definitions as the customization center, but write only
    # to the staging directory and never signal the currently running desktop.
    run python3 - "$stage" "$theme_name" <<'PY'
import importlib.util
from pathlib import Path
import sys
root, name = Path(sys.argv[1]), sys.argv[2]
spec = importlib.util.spec_from_file_location('minimalinux_backend', root / 'minimalinux/backend.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
backend.ROOT = root
backend.theme(name, 'Papirus' if name == 'Light' else 'Papirus-Dark', 'Noto Sans 10')
backend.settings_update({'wallpaper': {'solidColor': '#' + backend.THEMES[name]['bg']}})
PY
fi
chmod +x "$stage/hypr/Scripts/browser-launcher.sh"
touch "$stage/.managed-by-minimalinux"

heading '08  /  Register & install'
info 'Registering the session and customization center (sudo required)...'
registration_started=true
for i in "${!system_paths[@]}"; do
    file_state=$(managed_file_state "${system_sources[$i]}" "${system_paths[$i]}")
    case $file_state in
        identical) detail "Keeping unchanged system file: ${system_paths[$i]}" ;;
        absent) run sudo install -Dm"${system_modes[$i]}" "${system_sources[$i]}" "${system_paths[$i]}" ;;
        *) die "System file changed during installation ($file_state): ${system_paths[$i]}. Review the log and any partial registration." ;;
    esac
done
if [[ -e $config || -L $config ]]; then
    backup=$(mktemp -d "$HOME/.config/minimalinux.backup.$(date +%Y%m%d-%H%M%S).XXXXXXXX")
    rmdir "$backup"
    run mv -- "$config" "$backup"
    info "Previous session configuration backed up to $backup"
    log_line "BACKUP original=$config saved=$backup"
fi
if ! mv -- "$stage" "$config"; then
    printf 'Could not install the staged configuration.\n' >&2
    if [[ -n ${backup:-} && ! -e $config && ! -L $config ]]; then
        mv -- "$backup" "$config" && printf 'Restored the previous configuration.\n' >&2
    fi
    exit 1
fi
stage=''
trap - EXIT

log_line 'SUCCESS session configuration and launchers installed; no packages were removed'
printf '\n%s%s  All set!%s\n' "$bold" "$green" "$reset"
info 'Log out, then select iArch by Safari (isolated session) in your display manager session menu.'
info 'Super+Return: terminal   Super+K: customize   Super+Shift+M: log out'
info 'Monitor settings: ~/.config/minimalinux/hypr/monitors.conf'
