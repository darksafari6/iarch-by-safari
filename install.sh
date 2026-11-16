#!/bin/bash

export LC_MESSAGES=C
export LANG=C

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

# Product identity: single source of truth (see docs/BRANDING.md, Rule 1).
# Sourcing keeps installers and branding/product.env from drifting apart; the
# fallback only fires when a checkout is missing its branding file.
if [ -f "$SCRIPT_DIR/branding/product.env" ]; then
    # shellcheck source=branding/product.env
    . "$SCRIPT_DIR/branding/product.env"
fi
IARCH_PRODUCT_NAME=${IARCH_PRODUCT_NAME:-iArch by Safari}
IARCH_PRODUCT_TAGLINE=${IARCH_PRODUCT_TAGLINE:-Glass Hyprland desktop session for Arch Linux and Fedora}

print_product_banner() {
    echo ""
    echo "  ${IARCH_PRODUCT_NAME}"
    echo "  ${IARCH_PRODUCT_TAGLINE}"
    echo "  ------------------------------------------------------------"
}

append_unique_package() {
    local -n package_list="$1"
    local package="$2"
    local existing_package

    for existing_package in "${package_list[@]}"; do
        if [ "$existing_package" = "$package" ]; then
            return 0
        fi
    done

    package_list+=("$package")
}

# Ensure running as root before collecting interactive input.
if [[ $EUID -ne 0 ]]; then
    echo "This script must be run as root." >&2
    exit 1
fi

if [ ! -f /etc/pacman.conf ]; then
    echo "File [/etc/pacman.conf] not found!"
    exit 1
fi

# --- Configuration ---
# echilon, tonekneeo, xnyte
# Get the actual user running the script (not root)
if [ -n "$SUDO_USER" ] && [ "$SUDO_USER" != "root" ]; then
    ACTUAL_USER="$SUDO_USER"
else
    ACTUAL_USER=$(logname 2>/dev/null)
fi

if [ -z "$ACTUAL_USER" ] || [ "$ACTUAL_USER" = "root" ]; then
    echo "ERROR: Could not determine a non-root target user. Run this script with sudo from your normal user account."
    exit 1
fi

ACTUAL_USER_HOME=$(getent passwd "$ACTUAL_USER" | cut -d: -f6)
if [ -z "$ACTUAL_USER_HOME" ] || [ ! -d "$ACTUAL_USER_HOME" ]; then
    echo "ERROR: Could not determine home directory for user '$ACTUAL_USER'."
    exit 1
fi

REPO_DIR="$SCRIPT_DIR"
CONFIG_DIR="$ACTUAL_USER_HOME/.config"
DDCUTIL_ENABLED=0

# Every package transaction below goes through this library. It reads the state
# of each target out of the local database, prints the plan, and hands pacman
# --needed, so a machine that is already up to date installs nothing and says so
# instead of opening a transaction for eighty-seven names it already has.
if [ ! -f "$REPO_DIR/lib/packages.sh" ]; then
    echo "ERROR: lib/packages.sh is missing; this checkout is incomplete." >&2
    exit 1
fi
# shellcheck source=lib/packages.sh
. "$REPO_DIR/lib/packages.sh"

# Validate repo directory
if [ ! -d "$REPO_DIR/.config" ]; then
    echo "ERROR: Script must be run from the repository root directory."
    exit 1
fi

if [ ! -d "$REPO_DIR/.config/hypr" ]; then
    echo "ERROR: Could not find the Hyprland config directory inside your repository at '$REPO_DIR/.config/hypr'."
    exit 1
fi

# --- Pre-flight confirmation ---
print_product_banner
echo "This script installs the ${IARCH_PRODUCT_NAME} dotfiles for Hyprland and enables the Chaotic AUR repository. Use only with a fresh install of Hyprland (vanilla Arch Linux). Use at your own risk."
while true; do
    read -r -p "Install ${IARCH_PRODUCT_NAME} now? (y/n): " proceed
    case "$proceed" in
        y|Y|yes|YES)
            echo "Great! Proceeding with the ${IARCH_PRODUCT_NAME} installation..."
            break
            ;;
        n|N|no|NO)
            echo "Fair enough, Have a nice day."
            exit 0
            ;;
        *)
            echo "Please answer 'y' or 'n'."
            ;;
    esac
done

INSTALL_NVIDIA_OPTIONAL=0
while true; do
    echo ""
    read -r -p "Are you using an Nvidia GPU? (y/n): " nvidia_choice
    case "$nvidia_choice" in
        y|Y|yes|YES)
            INSTALL_NVIDIA_OPTIONAL=1
            echo "Nvidia-specific Hyprland options will be enabled."
            break
            ;;
        n|N|no|NO)
            INSTALL_NVIDIA_OPTIONAL=0
            echo "Skipping Nvidia-specific Hyprland options."
            break
            ;;
        *)
            echo "Please answer 'y' or 'n'."
            ;;
    esac
done

DEFAULT_INSTALL=0
while true; do
    echo ""
    read -r -p "Would you like to use the default installation options? (y/n): " default_install_choice
    case "$default_install_choice" in
        y|Y|yes|YES)
            DEFAULT_INSTALL=1
            echo "Using default installation options."
            break
            ;;
        n|N|no|NO)
            echo "Continuing with custom installation options."
            break
            ;;
        *)
            echo "Please answer 'y' or 'n'."
            ;;
    esac
done

# --- Printer support selection ---
INSTALL_PRINTER_SUPPORT=0
if [ "$DEFAULT_INSTALL" -eq 1 ]; then
    echo "Default selection: skipping printer support."
else
while true; do
    echo ""
    read -r -p "Do you want printer support? (y/n): " printer_choice
    case "$printer_choice" in
        y|Y|yes|YES)
            INSTALL_PRINTER_SUPPORT=1
            echo "Printer support packages will be installed after gaming packages."
            break
            ;;
        n|N|no|NO)
            INSTALL_PRINTER_SUPPORT=0
            echo "Skipping printer support installation."
            break
            ;;
        *)
            echo "Please answer 'y' or 'n'."
            ;;
    esac
done
fi

# --- Gaming package selection ---
GAMING_SELECTED_PACKAGES=()
if [ "$DEFAULT_INSTALL" -eq 1 ]; then
    GAMING_SELECTED_PACKAGES=(
        steam mangohud protonplus wine winetricks protontricks lutris
        heroic-games-launcher-bin prismlauncher
    )
    echo "Default gaming packages selected: ${GAMING_SELECTED_PACKAGES[*]}"
else
while true; do
    echo ""
    echo "Gaming Packages (select one or more):"
    echo "  1. steam"
    echo "  2. mangohud (standalone no gui)"
    echo "  3. protonplus"
    echo "  4. wine"
    echo "  5. winetricks"
    echo "  6. protontricks"
    echo "  7. lutris"
    echo "  8. heroic-games-launcher-bin"
    echo "  9. prismlauncher"
    echo " 10. goverlay"
    echo " 11. mangojuice"
    echo "  a. Install all gaming packages"
    echo "  0. Skip gaming package installation"
    echo ""
    read -r -p "Enter your choices (comma or space separated, e.g., 1,2,5 or 1 2 5, or a for all): " gaming_choices

    if [ "$gaming_choices" = "0" ] || [ -z "$gaming_choices" ]; then
        echo "Skipping gaming package installation."
        GAMING_SELECTED_PACKAGES=()
        break
    fi

    if [[ "$gaming_choices" =~ ^[aA]$ ]]; then
        gaming_choices="1 2 3 4 5 6 7 8 9 10 11"
    fi

    gaming_choices=$(echo "$gaming_choices" | tr ',' ' ')
    GAMING_SELECTED_PACKAGES=()
    invalid_choice=false

    for choice in $gaming_choices; do
        case "$choice" in
            1) append_unique_package GAMING_SELECTED_PACKAGES steam ;;
            2) append_unique_package GAMING_SELECTED_PACKAGES mangohud ;;
            3) append_unique_package GAMING_SELECTED_PACKAGES protonplus ;;
            4) append_unique_package GAMING_SELECTED_PACKAGES wine ;;
            5) append_unique_package GAMING_SELECTED_PACKAGES winetricks ;;
            6) append_unique_package GAMING_SELECTED_PACKAGES protontricks ;;
            7) append_unique_package GAMING_SELECTED_PACKAGES lutris ;;
            8) append_unique_package GAMING_SELECTED_PACKAGES heroic-games-launcher-bin ;;
            9) append_unique_package GAMING_SELECTED_PACKAGES prismlauncher ;;
            10) append_unique_package GAMING_SELECTED_PACKAGES goverlay ;;
            11) append_unique_package GAMING_SELECTED_PACKAGES mangojuice ;;
            *)
                echo "Invalid choice: $choice"
                invalid_choice=true
                ;;
        esac
    done

    if [ "$invalid_choice" = false ]; then
        echo "Selected gaming packages: ${GAMING_SELECTED_PACKAGES[*]}"
        break
    fi

    echo "Please try again with valid choices."
done
fi

# --- Bluetooth package selection ---
INSTALL_BLUETOOTH_PACKAGES=0
if [ "$DEFAULT_INSTALL" -eq 1 ]; then
    INSTALL_BLUETOOTH_PACKAGES=1
    echo "Default selection: installing Bluetooth packages."
else
while true; do
    echo ""
    read -r -p "Do you want to install Bluetooth packages and enable the Bluetooth service? (y/n): " bluetooth_choice
    case "$bluetooth_choice" in
        y|Y|yes|YES)
            INSTALL_BLUETOOTH_PACKAGES=1
            echo "Bluetooth packages will be installed and service will be enabled."
            break
            ;;
        n|N|no|NO)
            INSTALL_BLUETOOTH_PACKAGES=0
            echo "Skipping Bluetooth package installation and service."
            break
            ;;
        *)
            echo "Please answer 'y' or 'n'."
            ;;
    esac
done
fi

# --- Audio mode selection ---
AUDIO_MODE="easyeffects"
if [ "$DEFAULT_INSTALL" -eq 1 ]; then
    echo "Default selection: using EasyEffects setup."
else
while true; do
    echo ""
    echo "Audio setup option:"
    echo "  0. Skip EasyEffects and Dolby setup"
    echo "  1. EasyEffects (default)"
    echo "  2. Dolby Atmos support"
    read -r -p "Choose audio option (0-2): " audio_choice
    case "$audio_choice" in
        0)
            AUDIO_MODE="none"
            echo "Skipping EasyEffects and Dolby setup."
            break
            ;;
        1|"")
            AUDIO_MODE="easyeffects"
            echo "Using EasyEffects setup."
            break
            ;;
        2)
            AUDIO_MODE="dolby"
            echo "Dolby Atmos profile will be applied after installation."
            break
            ;;
        *)
            echo "Please enter 0, 1 or 2."
            ;;
    esac
done
fi

# --- Audio/Video player selection ---
AUDIO_VIDEO_PACKAGES=()
INSTALL_VLC_PLUGINS_ALL=0
if [ "$DEFAULT_INSTALL" -eq 1 ]; then
    AUDIO_VIDEO_PACKAGES=(mpv)
    echo "Default audio/video player selected: mpv"
else
while true; do
    echo ""
    echo "Audio/Video Players (select one or more):"
    echo "  1. mpv (lightweight video player)"
    echo "  2. vlc (versatile media player)"
    echo "  3. dragon (simple KDE video player)"
    echo "  4. haruna (modern KDE video player)"
    echo "  5. deadbeef (modular audio player)"
    echo "  6. rhythmbox (GNOME music player)"
    echo "  7. elisa (lightweight KDE music player)"
    echo "  a. Install all audio/video players"
    echo "  0. Skip audio/video player installation"
    echo ""
    read -r -p "Enter your choices (comma or space separated, e.g., 1,2,5 or 1 2 5, or a for all): " av_choices
    
    if [ "$av_choices" = "0" ] || [ -z "$av_choices" ]; then
        echo "Skipping audio/video player installation."
        break
    fi

    if [[ "$av_choices" =~ ^[aA]$ ]]; then
        av_choices="1 2 3 4 5 6 7"
    fi
    
    # Convert input to array, handling both comma and space separation
    av_choices=$(echo "$av_choices" | tr ',' ' ')
    
    invalid_choice=false
    for choice in $av_choices; do
        case "$choice" in
            1) append_unique_package AUDIO_VIDEO_PACKAGES mpv ;;
            2) append_unique_package AUDIO_VIDEO_PACKAGES vlc ;;
            3) append_unique_package AUDIO_VIDEO_PACKAGES dragon ;;
            4) append_unique_package AUDIO_VIDEO_PACKAGES haruna ;;
            5) append_unique_package AUDIO_VIDEO_PACKAGES deadbeef ;;
            6) append_unique_package AUDIO_VIDEO_PACKAGES rhythmbox ;;
            7) append_unique_package AUDIO_VIDEO_PACKAGES elisa ;;
            *)
                echo "Invalid choice: $choice"
                invalid_choice=true
                ;;
        esac
    done
    
    if [ "$invalid_choice" = false ]; then
        if [ ${#AUDIO_VIDEO_PACKAGES[@]} -gt 0 ]; then
            echo "Selected packages: ${AUDIO_VIDEO_PACKAGES[*]}"

            for pkg in "${AUDIO_VIDEO_PACKAGES[@]}"; do
                if [ "$pkg" = "vlc" ]; then
                    while true; do
                        echo ""
                        read -r -p "Do you want to install vlc-plugins-all? If you choose no, you will need to install VLC plugins manually later. (y/n): " vlc_plugins_choice
                        case "$vlc_plugins_choice" in
                            y|Y|yes|YES)
                                INSTALL_VLC_PLUGINS_ALL=1
                                echo "vlc-plugins-all will be installed alongside VLC."
                                break
                                ;;
                            n|N|no|NO)
                                INSTALL_VLC_PLUGINS_ALL=0
                                echo "Skipping vlc-plugins-all. You can install VLC plugins manually later."
                                break
                                ;;
                            *)
                                echo "Please answer 'y' or 'n'."
                                ;;
                        esac
                    done
                    break
                fi
            done
        fi
        break
    fi
    
    echo "Please try again with valid choices."
    AUDIO_VIDEO_PACKAGES=()
done
fi

#: Two of the names below are here because a key binds them, and a bind that calls a
#: program nothing installs is a key that does nothing. The failure is quiet by design of
#: the compositor: it spawns one string through /bin/sh -c, so the only report is a
#: "command not found" in a log nobody is reading.
#:
#:   wireplumber    extra, 0.5.19-1, MIT, verified against the Arch package search JSON
#:                  API on 2026-11-09. It provides `wpctl`, which is what
#:                  scripts/iarch-audio.sh drives for the two volume steps and the two
#:                  mutes, and it conflicts pipewire-media-session while providing
#:                  pipewire-session-manager -- so it is the session manager and not an
#:                  extra one. pipewire itself arrives as a dependency rather than being
#:                  named here: scripts/iarch-healthcheck.sh already asks whether the
#:                  pipewire, pipewire-pulse and wireplumber user units are active, and
#:                  naming pipewire-pulse in this array would put the installer into
#:                  pulseaudio's conflict on a machine that still has it, for a socket
#:                  this session was already expected to have.
#:   brightnessctl  extra, 0.5.1-3, MIT, verified the same way on the same day, and it
#:                  needs no privilege on this distribution: Arch's own PKGBUILD builds it
#:                  with `make ENABLE_SYSTEMD=1`, which is the build whose non-root `set`
#:                  falls back to logind's Session.SetBrightness instead of asking for
#:                  root, so there is no setuid bit to grant and no `video` group to add
#:                  (the one group this installer grants is `i2c`, for DDC).
#:
#: The two XF86 volume keys used to call `pamixer`, which no step of this installer ever
#: installed and which no package array named; that is TP-11 in docs/UNVERIFIED.md, and
#: the keys now call wpctl through scripts/iarch-audio.sh instead.
# Define the list of packages to install using pacman
PACKAGES=(
    # Core Components
    greetd                    # Login manager daemon for Noctalia Greeter
    polkit-gnome              # PolicyKit authentication agent
    gnome-keyring             # Credential storage  
    hyprlock                  # Locks screen, obviously. 
    hypridle                  # Turns off screen after set time
    pavucontrol               # PulseAudio/PipeWire volume control
    wireplumber               # PipeWire session manager; provides wpctl
    brightnessctl             # sysfs backlight control for the brightness keys
    playerctl                 # Media player controller
    wlsunset                  # Nightlight for quickshell
    fish                      # Shell
    fastfetch                 # System Info Display
    satty                     # Screenshot annotation tool
    grim                      # Screenshot utility for wayland
    slurp                     # Screenshot selector for region
    hyprshot                  # Screenshot selector region - this is a standalone app
    gedit                     # Gnome Advanced Text Editor
    nwg-look                  # Look and feel configuration
    nwg-displays              # Configure Monitors 
    kitty-shell-integration   # Kitty terminal shell integration
    kitty-terminfo            # Terminfo for Kitty
    xdg-desktop-portal-gtk    # GTK implementation of xdg-desktop-portal
    xdg-user-dirs             # Manage user directories
    thunar                    # File Manager  
    thunar-media-tags-plugin  # Media tags plugin for Thunar
    thunar-shares-plugin      # Shares plugin for Thunar
    thunar-vcs-plugin         # VCS integration plugin for Thunar
    thunar-volman             # Volume management plugin for Thunar
    thunar-archive-plugin     # Archive plugin for Thunar
    update-grub               # Update GRUB bootloader
    gcolor3                   # Color picker
    gnome-calculator          # Math n stuff...
    tumbler                   # Thumbnailer
    hyprland-protocols        # Protocols for Hyprland
    power-profiles-daemon     # Power profile management
    file-roller               # Archive manager
    starship                  # Shell prompt
    unrar                     # RAR archive support
    unzip                     # ZIP archive support
    7zip                      # 7z archive support
    cava                      # Audio visualizer
    flatpak                   # Application sandbox and package manager
    gnome-disk-utility        # Disk Management
    libopenraw                # Lib for Tumbler
    libgsf                    # Lib for Tumbler
    poppler-glib              # Lib for Tumbler
    ffmpegthumbnailer         # Lib for Tumbler 
    freetype2                 # Lib for Tumbler
    libgepub                  # Lib for Tumbler
    gvfs                      # Needed for Thunar to see drives
    gvfs-afc                  # Apple Device Support
    gvfs-mtp                  # Android/MTP Device Support
    gvfs-smb                  # SMB Support 
    ntfs-3g                   # NTFS filesystem support
    dosfstools                # DOS filesystem utilities
    exfatprogs                # exFAT filesystem support
    yay                       # AUR Helper
    base-devel                # Build package
    clang                     # Build package
    cmake                     # Cross-platform build system
    go                        # Go programming language compiler
    rust                      # Rust programming language compiler
    pkgconf                   # Package config system
    meson                     # Modern build system
    ninja                     # Small build system focused on speed
    matugen                   # Color Generation
    adw-gtk-theme             # Libadwaita theme
    loupe                     # Image viewer
    cpupower                  # CPU frequency scaling utilities
    upower                    # Power management service
    gpu-screen-recorder       # Screen Recorder
    qt6-base                  # Qt6 base libraries and tools
    qt6ct                     # Qt Settings
    noto-fonts-emoji          # Fonts
    ttf-dejavu                # Fonts
    ttf-symbola               # Fonts
    gst-plugins-good          # Gstreamer Plugins 
    gst-plugins-ugly          # Gstreamer Plugins
    gst-libav                 # Gstreamer Plugins
    qt6-websockets            # Websocket
    os-prober                 # Os prober for Grub
    stb                       # Build Package for Noctalia V5
    imagemagick               # Image display
    noctalia                  # Noctalia
)

#: Icon and cursor themes, installed by their own step and through yay. Two
#: reasons, neither of which a package list can show on its own:
#:
#:   * Not one of these is a session dependency. A theme a mirror does not carry
#:     leaves the desktop on its fallback theme; that is a cosmetic gap, not a
#:     broken install. They were in the fatal core array above, where a single
#:     missing name aborted everything that came after it.
#:   * Two of the names are not in Arch's own repositories at all. Checked against
#:     the package search JSON API on 2026-11-09, `bibata-cursor-theme` and
#:     `papirus-folders` both return zero results, so pacman can only ever find
#:     them in a third-party repository. yay searches the repositories and the
#:     AUR in one pass (yay(8): -N/--repo, -a/--aur), which is why this step uses
#:     it even for the packages that are not from the AUR.
ICON_PACKAGES=(
    papirus-icon-theme        # extra, 20260801-1, GPL-3.0 (verified 2026-11-09)
    yaru-icon-theme           # an alternative the presets offer
    humanity-icon-theme       # an alternative the presets offer
)

#: The cursor theme the presets name, as a package whose existence and licence
#: were read out of the AUR's own RPC interface on 2026-11-09: version 2.0.7-1,
#: GPL-3.0-or-later, and it both Provides and Conflicts `bibata-cursor-theme`.
#: That last pair is why the step below checks for either name before installing:
#: a machine that built the source package already has the cursor theme, and
#: handing it the binary one would be a conflict, not an upgrade.
CURSOR_PACKAGE='bibata-cursor-theme-bin'

#: Colour-matched folder icons for Papirus. Not in Arch's repositories, and the
#: repository that does carry it could not be confirmed from here, so it is
#: fetched on its own: TP-20 in docs/UNVERIFIED.md, and one unverifiable name
#: must not take the verified ones down with it.
FOLDER_ICONS_PACKAGE='papirus-folders'

# Audio stack is selected at runtime.
if [ "$AUDIO_MODE" = "easyeffects" ]; then
    PACKAGES+=(
        easyeffects               # Audio Effects
        lsp-plugins-lv2           # Easyeffects Plugins
        calf                      # Easyeffects Plugins
    )
fi

OPTIONALPKG=(
    upscayl-desktop-git       # Upscaler for images on the fly
    video-downloader          # Download videos on your system, avoid sketchy websites! Yipee!
    mission-center            # Task Manager, Sleek
    obsidian                  # Markdown Text Editor
    obs-studio-stable         # OBS Streaming Software
    visual-studio-code-bin    # Visual Studio Code editor
)

# Descriptions for optional packages
declare -A OPTIONALPKG_DESC=(
    [upscayl-desktop-git]="Image upscaler (desktop GUI)"
    [video-downloader]="Download videos locally from various sources"
    [mission-center]="Sleek task manager / system monitor"
    [obsidian]="Markdown text editor"
    [obs-studio-stable]="OBS streaming and recording software"
    [visual-studio-code-bin]="Visual Studio Code editor"
)

SELECTED_OPTIONAL_PACKAGES=()
BROWSER_CHOICE=6

# --- Color Functions ---
disable_colors() {
    unset ALL_OFF BOLD BLUE GREEN RED YELLOW CYAN MAGENTA
}

enable_colors() {
    if tput setaf 0 &>/dev/null; then
        ALL_OFF="$(tput sgr0)"
        BOLD="$(tput bold)"
        RED="${BOLD}$(tput setaf 1)"
        GREEN="${BOLD}$(tput setaf 2)"
        YELLOW="${BOLD}$(tput setaf 3)"
        BLUE="${BOLD}$(tput setaf 4)"
        MAGENTA="${BOLD}$(tput setaf 5)"
        CYAN="${BOLD}$(tput setaf 6)"
    else
        ALL_OFF="\e[0m"
        BOLD="\e[1m"
        RED="${BOLD}\e[31m"
        GREEN="${BOLD}\e[32m"
        YELLOW="${BOLD}\e[33m"
        BLUE="${BOLD}\e[34m"
        MAGENTA="${BOLD}\e[35m"
        CYAN="${BOLD}\e[36m"
    fi
    # shellcheck disable=SC2034  # palette entries are defined together; not all are used
    readonly ALL_OFF BOLD BLUE GREEN RED YELLOW CYAN MAGENTA
}

if [[ -t 2 ]]; then
    enable_colors
else
    disable_colors
fi

# --- Chaotic-AUR Functions ---
print_header() {
    echo ""
    printf "${CYAN}${BOLD}   Chaotic-AUR Repository Setup${ALL_OFF}\n"
    printf "${YELLOW}${BOLD}   'The Fast Lane!'${ALL_OFF}\n"
    echo ""
}

msg() {
    printf "${GREEN}▶${ALL_OFF}${BOLD} ${1}${ALL_OFF}\n" >&2
}

info() {
    printf "${YELLOW}  •${ALL_OFF} ${1}${ALL_OFF}\n" >&2
}

error() {
    printf "${RED}  ✗${ALL_OFF} ${1}${ALL_OFF}\n" >&2
}

# --- Wizard scaffolding ---
# An installer is a sequence of steps a person watches, and the two ways it
# fails them are silence and ambiguity: nothing on screen for a minute, and then
# no way to tell afterwards what ran, what was skipped and what broke. So every
# step is numbered against a total that is written down here, announces itself
# before it starts, and ends with exactly one verdict. A step with nothing to do
# is skipped *out loud*, because a skipped step and a step that never ran look
# identical on a screen that says nothing.
#
# None of these functions puts a variable in a printf format string. A package
# name, a path or a person's choice can contain a percent sign, and in a format
# string that is a formatting error rather than text.
#
# This script exports LANG=C, so ${#var} counts bytes there, not columns: the
# banner builds its rule by replacing spaces in a padded field instead of
# measuring a string of box-drawing characters. The lines it pads are ASCII for
# the same reason.
#
# STEP_TOTAL is a literal, and tests/test_installer_wizard.py counts the
# step_begin calls in this file and refuses to let the two disagree.
STEP_TOTAL=24
STEP_NUMBER=0
STEP_TITLE=''
STEP_VERDICT='ok'
STEP_REASON=''
STEP_OK_COUNT=0
STEP_SKIP_COUNT=0
STEP_FAILED_STEPS=()

step_begin() {
    STEP_NUMBER=$((STEP_NUMBER + 1))
    STEP_TITLE="$1"
    STEP_VERDICT='ok'
    STEP_REASON=''
    printf '\n%s[%2d/%d]%s %s%s%s\n' \
        "$CYAN" "$STEP_NUMBER" "$STEP_TOTAL" "$ALL_OFF" "$BOLD" "$STEP_TITLE" "$ALL_OFF" >&2
}

# step_skip REASON and step_fail REASON record a verdict; finish_step prints it.
# A step function calls one of them and returns, so numbering stays in one place.
step_skip() {
    STEP_VERDICT='skip'
    STEP_REASON="${1-nothing to do}"
}

step_fail() {
    STEP_VERDICT='fail'
    STEP_REASON="${1-failed}"
}

step_note() {
    printf '%s   •%s %s\n' "$BLUE" "$ALL_OFF" "$1" >&2
}

finish_step() {
    case "$STEP_VERDICT" in
        ok)
            STEP_OK_COUNT=$((STEP_OK_COUNT + 1))
            printf '%s   ✓%s done\n' "$GREEN" "$ALL_OFF" >&2
            ;;
        skip)
            STEP_SKIP_COUNT=$((STEP_SKIP_COUNT + 1))
            printf '%s   –%s skipped: %s\n' "$YELLOW" "$ALL_OFF" "$STEP_REASON" >&2
            ;;
        *)
            STEP_FAILED_STEPS+=("$STEP_TITLE")
            printf '%s   ✗%s failed: %s\n' "$RED" "$ALL_OFF" "$STEP_REASON" >&2
            ;;
    esac
}

wizard_banner() {
    local width=58 version rule line
    version=$(cat "$REPO_DIR/VERSION" 2>/dev/null) || version='unknown'
    printf -v rule '%*s' "$width" ''
    rule=${rule// /─}
    printf '\n%s  ╭%s╮%s\n' "$CYAN" "$rule" "$ALL_OFF" >&2
    for line in "$IARCH_PRODUCT_NAME" \
                "$IARCH_PRODUCT_TAGLINE" \
                "installer v$version / $STEP_TOTAL steps / user $ACTUAL_USER"; do
        # The format contributes one space before the padded field, so the field
        # is width-1 wide: one plus (width - 1) is the width of the rule above.
        printf '%s  │%s %-*s%s│%s\n' \
            "$CYAN" "$BOLD" "$((width - 1))" "${line:0:width - 2}" "$ALL_OFF" "$ALL_OFF" >&2
    done
    printf '%s  ╰%s╯%s\n\n' "$CYAN" "$rule" "$ALL_OFF" >&2
}

wizard_summary() {
    printf '\n%s  the run, in numbers%s\n' "$BOLD" "$ALL_OFF" >&2
    printf '   %s✓%s %d done   %s–%s %d skipped   %s✗%s %d failed\n' \
        "$GREEN" "$ALL_OFF" "$STEP_OK_COUNT" \
        "$YELLOW" "$ALL_OFF" "$STEP_SKIP_COUNT" \
        "$RED" "$ALL_OFF" "${#STEP_FAILED_STEPS[@]}" >&2
    if ((${#STEP_FAILED_STEPS[@]})); then
        local name
        printf '\n  %sThese steps did not finish:%s\n' "$RED" "$ALL_OFF" >&2
        for name in "${STEP_FAILED_STEPS[@]}"; do
            printf '    ✗ %s\n' "$name" >&2
        done
        printf '\n  Configuration already deployed stays deployed. The steps\n' >&2
        printf '  listed above are the ones to re-run once the cause is fixed.\n' >&2
        return 1
    fi
    return 0
}

check_if_chaotic_repo_was_added() {
    grep -q "chaotic-aur" /etc/pacman.conf
}

ensure_multilib_repo_enabled() {
    msg "Ensuring multilib repository is enabled.."

    local pacman_conf="/etc/pacman.conf"

    if grep -Eq '^[[:space:]]*\[multilib\][[:space:]]*$' "$pacman_conf"; then
        info "multilib is already enabled"
        return
    fi

    if grep -Eq '^[[:space:]]*#[[:space:]]*\[multilib\][[:space:]]*$' "$pacman_conf"; then
        info "Found commented multilib block, enabling it"
        sed -i '/^[[:space:]]*#[[:space:]]*\[multilib\][[:space:]]*$/,/^[[:space:]]*#[[:space:]]*Include[[:space:]]*=[[:space:]]*\/etc\/pacman\.d\/mirrorlist[[:space:]]*$/ s/^[[:space:]]*#[[:space:]]*//' "$pacman_conf"
    else
        info "multilib block not found, appending it"
        {
            echo ""
            echo "[multilib]"
            echo "Include = /etc/pacman.d/mirrorlist"
        } >> "$pacman_conf"
    fi

    msg "Done configuring multilib repository"
}

reorder_pacman_conf() {
    msg "Ensuring correct repository order in pacman.conf.."
    
    local pacman_conf="/etc/pacman.conf"
    local pacman_conf_backup
    pacman_conf_backup="/etc/pacman.conf.bak.$(date +%s)"
    
    info "Backup current config"
    cp "$pacman_conf" "$pacman_conf_backup"
    
    # Remove any existing Chaotic-AUR entries
    sed -i '/^\[chaotic-aur\]/,/^$/d' "$pacman_conf"
    
    # Add Chaotic-AUR at the end
    echo "" >> "$pacman_conf"
    echo "[chaotic-aur]" >> "$pacman_conf"
    echo "Include = /etc/pacman.d/chaotic-mirrorlist" >> "$pacman_conf"
    
    info "Chaotic-AUR positioned at the end of pacman.conf"
    msg "Done configuring repository order"
}

install_chaotic_aur() {
    msg "Installing Chaotic-AUR repository.."
    printf "${CYAN}${BOLD}  🔑 Adding Chaotic-AUR GPG key...${ALL_OFF}\n"

    info "Adding Chaotic-AUR GPG key"
    if ! pacman-key --recv-key 3056513887B78AEB --keyserver keyserver.ubuntu.com; then
        error "Failed to fetch Chaotic-AUR GPG key"
        return 1
    fi

    if ! pacman-key --lsign-key 3056513887B78AEB; then
        error "Failed to locally sign the Chaotic-AUR GPG key"
        return 1
    fi

    printf "${CYAN}${BOLD}  📦 Installing Chaotic-AUR packages...${ALL_OFF}\n"
    info "Installing Chaotic-AUR keyring and mirrorlist"
    if ! pacman -U --noconfirm 'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-keyring.pkg.tar.zst'; then
        error "Failed to install chaotic-keyring"
        return 1
    fi

    if ! pacman -U --noconfirm 'https://cdn-mirror.chaotic.cx/chaotic-aur/chaotic-mirrorlist.pkg.tar.zst'; then
        error "Failed to install chaotic-mirrorlist"
        return 1
    fi

    msg "Done installing Chaotic-AUR repository."
}

create_chaotic_mirrorlist() {
    msg "Creating Chaotic-AUR mirrorlist file.."
    
    if [[ ! -f /etc/pacman.d/chaotic-mirrorlist ]] || [[ ! -s /etc/pacman.d/chaotic-mirrorlist ]]; then
        info "Creating chaotic-mirrorlist"
        cat > /etc/pacman.d/chaotic-mirrorlist << 'EOF'
# Chaotic-AUR Mirrorlist
Server = https://cdn-mirror.chaotic.cx/chaotic-aur/$arch
Server = https://geo-mirror.chaotic.cx/chaotic-aur/$arch
EOF
    fi
    
    msg "Done creating mirrorlist file"
}

setup_chaotic_aur() {
    print_header
    msg "Setting up Chaotic-AUR repository.."

    ensure_multilib_repo_enabled
    
    if check_if_chaotic_repo_was_added; then
        info "Chaotic-AUR repo is already installed!"
        info "Skipping installation steps"
    else
        if ! install_chaotic_aur; then
            return 1
        fi
        create_chaotic_mirrorlist
    fi
    
    reorder_pacman_conf
    
    echo ""
    printf "${GREEN}${BOLD}  ✓ SUCCESS${ALL_OFF}\n"
    printf "${GREEN}  Chaotic-AUR repository setup completed successfully!${ALL_OFF}\n"
    printf "${GREEN}  Repository is now positioned at the end of pacman.conf${ALL_OFF}\n"
    echo ""
    
    msg "Refreshing pacman mirrors..."
    pacman -Syy
    
    if [ $? -ne 0 ]; then
        echo "Warning: Failed to refresh pacman mirrors."
    fi
}

# --- Main Installation Functions ---

# Keep existing applications unless the user explicitly opts in to removal.
remove_conflicting_packages() {
    local candidates=()
    local package

    for package in dolphin polkit-kde-agent vim; do
        if pacman -Q "$package" >/dev/null 2>&1; then
            candidates+=("$package")
        fi
    done

    if [ "${#candidates[@]}" -eq 0 ]; then
        echo "No optional conflicting packages are installed; nothing to remove."
        return 0
    fi

    echo "These packages may overlap with the selected defaults: ${candidates[*]}"
    echo "They will be preserved unless you explicitly approve removal."
    read -r -p "Remove these packages and their unused dependencies? (y/N): " remove_choice
    case "$remove_choice" in
        y|Y|yes|YES)
            if pacman -Rns --noconfirm -- "${candidates[@]}"; then
                echo "Requested package removal completed."
            else
                echo "Warning: package removal failed; continuing without removing them."
            fi
            ;;
        *)
            echo "Keeping all existing packages."
            ;;
    esac
}

install_gaming_packages() {
    if [ ${#GAMING_SELECTED_PACKAGES[@]} -eq 0 ]; then
        step_skip "no gaming packages selected"
        return 0
    fi

    for pkg in "${GAMING_SELECTED_PACKAGES[@]}"; do
        case "$pkg" in
            mangohud)
                append_unique_package GAMING_SELECTED_PACKAGES lib32-mangohud
                ;;
            prismlauncher)
                append_unique_package GAMING_SELECTED_PACKAGES jdk21-openjdk
                ;;
        esac
    done

    # pacman still prints its own summary and waits for a person here: this is
    # the one list the installer has always left interactive, because the choices
    # were made a minute ago in a menu and a second look is cheap.
    if ! packages_install_review "gaming packages" "${GAMING_SELECTED_PACKAGES[@]}"; then
        step_fail "some gaming packages did not install"
    fi
}

install_printer_support_packages() {
    if [ "$INSTALL_PRINTER_SUPPORT" -ne 1 ]; then
        step_skip "printer support not selected"
        return 0
    fi

    local printer_packages=(
        hspell libvoikko hunspell aspell nuspell reflector pinta lib32-libpulse ttf-ms-fonts
        cups cups-filters cups-pdf hplip gutenprint system-config-printer
        foomatic-db-gutenprint-ppds foomatic-db-nonfree-ppds foomatic-db-ppds
        foomatic-db-nonfree foomatic-db foomatic-db-engine
        python-pyqt5 python-reportlab python-pyqt6
    )
    if ! packages_install "printer support" "${printer_packages[@]}"; then
        step_fail "some printer support packages did not install"
    fi

    step_note "enabling and starting CUPS"
    if ! systemctl enable --now cups; then
        step_note "warning: the CUPS service did not start"
    fi
}

install_bluetooth_packages() {
    if [ "$INSTALL_BLUETOOTH_PACKAGES" -ne 1 ]; then
        step_skip "bluetooth not selected"
        return 0
    fi

    if ! packages_install "bluetooth" bluez bluez-utils blueman; then
        step_fail "some bluetooth packages did not install"
    fi

    step_note "enabling the bluetooth service"
    if ! systemctl enable bluetooth; then
        step_note "warning: the bluetooth service did not enable"
    fi
}

install_audio_video_packages() {
    if [ ${#AUDIO_VIDEO_PACKAGES[@]} -eq 0 ]; then
        step_skip "no audio or video players selected"
        return 0
    fi

    local selected=("${AUDIO_VIDEO_PACKAGES[@]}")
    if [ "$INSTALL_VLC_PLUGINS_ALL" -eq 1 ]; then
        selected+=(vlc-plugins-all)
    fi
    if ! packages_install "audio and video players" "${selected[@]}"; then
        step_fail "some audio or video packages did not install"
    fi
}

# Function to prompt optional package selection
prompt_optional_packages() {
    local optional_choices
    local pkg
    local desc
    local choice
    local pkg_index
    local invalid_choice
    local menu_index

    echo -e "\n--- Optional Packages Installation ---"

    if [ "$DEFAULT_INSTALL" -eq 1 ]; then
        SELECTED_OPTIONAL_PACKAGES=("${OPTIONALPKG[@]}")
        append_unique_package SELECTED_OPTIONAL_PACKAGES luajit
        echo "Default selection: installing all optional packages."
        return 0
    fi

    while true; do
        echo "Choose one or more optional packages:"
        menu_index=1
        for pkg in "${OPTIONALPKG[@]}"; do
            desc="${OPTIONALPKG_DESC[$pkg]}"
            if [ -n "$desc" ]; then
                echo "  $menu_index. $pkg ($desc)"
            else
                echo "  $menu_index. $pkg"
            fi
            menu_index=$((menu_index + 1))
        done
        echo "  0. Skip optional package installation"
        echo "  a. Install all optional packages"
        echo ""

        read -r -p "Enter your choices (comma or space separated, e.g., 1,2 or 1 2, or a for all): " optional_choices

        if [ "$optional_choices" = "0" ] || [ -z "$optional_choices" ]; then
            echo "Skipping optional package installation."
            SELECTED_OPTIONAL_PACKAGES=()
            return 0
        fi

        if [[ "$optional_choices" =~ ^[aA]$ ]]; then
            optional_choices=$(seq -s ' ' 1 "${#OPTIONALPKG[@]}")
        fi

        optional_choices=$(echo "$optional_choices" | tr ',' ' ')
        SELECTED_OPTIONAL_PACKAGES=()
        invalid_choice=false

        for choice in $optional_choices; do
            if ! [[ "$choice" =~ ^[0-9]+$ ]]; then
                echo "Invalid choice: $choice"
                invalid_choice=true
                continue
            fi

            if [ "$choice" -lt 1 ] || [ "$choice" -gt "${#OPTIONALPKG[@]}" ]; then
                echo "Invalid choice: $choice"
                invalid_choice=true
                continue
            fi

            pkg_index=$((choice - 1))
            append_unique_package SELECTED_OPTIONAL_PACKAGES "${OPTIONALPKG[$pkg_index]}"
        done

        if [ "$invalid_choice" = false ]; then
            for pkg in "${SELECTED_OPTIONAL_PACKAGES[@]}"; do
                if [ "$pkg" = "obs-studio-stable" ]; then
                    append_unique_package SELECTED_OPTIONAL_PACKAGES luajit
                    break
                fi
            done

            return 0
        fi

        echo "Please try again with valid choices."
    done
}

# Function to handle optional package installation
install_optional_packages() {
    if [ ${#SELECTED_OPTIONAL_PACKAGES[@]} -eq 0 ]; then
        step_skip "no optional packages selected"
        return 0
    fi

    if ! packages_install "optional packages" "${SELECTED_OPTIONAL_PACKAGES[@]}"; then
        step_fail "some optional packages did not install"
    fi
}

# Deploy configuration files from repo/.config to ~/.config
deploy_configs() {
    echo "Deploying configuration files..."
    
    # Build a v5-only payload: the repository also retains an isolated v4
    # session, whose Hyprlang/JSON files must not replace the v5 Lua profile.
    local staged_config
    staged_config=$(mktemp -d) || return 1
    if ! bash "$REPO_DIR/lib/stage-v5-config.sh" "$REPO_DIR/.config" "$staged_config"; then
        rm -rf -- "$staged_config"
        echo "FATAL ERROR: Unable to stage v5 configuration." >&2
        return 1
    fi
    CONFIG_SOURCE_ROOT="$staged_config"

    if ! sudo -u "$ACTUAL_USER" mkdir -p "$CONFIG_DIR"; then
        rm -rf -- "$staged_config"
        return 1
    fi

    # Check every backup destination before moving any existing config.
    BACKUP_TIMESTAMP="$(date +%Y%m%d-%H%M%S-%N).$RANDOM"
    local item name target backup
    for item in "$CONFIG_SOURCE_ROOT"/*; do
        name=$(basename "$item")
        backup="$CONFIG_DIR/$name.bak.$BACKUP_TIMESTAMP"
        if [ -e "$backup" ] || [ -L "$backup" ]; then
            echo "Backup destination already exists: $backup" >&2
            rm -rf -- "$staged_config"
            return 1
        fi
    done
    echo "Backing up existing configuration files..."
    for item in "$CONFIG_SOURCE_ROOT"/*; do
        name=$(basename "$item")
        target="$CONFIG_DIR/$name"
        backup="$CONFIG_DIR/$name.bak.$BACKUP_TIMESTAMP"
        if [ -e "$target" ] || [ -L "$target" ]; then
            echo "  -> Backing up: $name to $(basename "$backup")"
            if ! mv -- "$target" "$backup"; then
                echo "Backup failed; previously moved backups are retained under $CONFIG_DIR." >&2
                rm -rf -- "$staged_config"
                return 1
            fi
        fi
    done
    # Do not copy over paths recreated during backup.
    for item in "$CONFIG_SOURCE_ROOT"/*; do
        target="$CONFIG_DIR/$(basename "$item")"
        if [ -e "$target" ] || [ -L "$target" ]; then
            echo "Destination appeared during deployment: $target; backups retained." >&2
            rm -rf -- "$staged_config"
            return 1
        fi
    done

    # Copy all configuration files from repo/.config to ~/.config
    echo "Copying configuration files from $CONFIG_SOURCE_ROOT to $CONFIG_DIR..."
    cp -rf "$CONFIG_SOURCE_ROOT"/* "$CONFIG_DIR"/
    local copy_status=$?
    rm -rf -- "$staged_config"

    if [ "$copy_status" -eq 0 ]; then
        echo "Configuration files copied successfully!"
        
        # Fix ownership since we're running as root
        for name in fastfetch fish hypr kitty noctalia starship.toml; do
            chown -R "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR/$name" || return 1
        done

        # If ddcutil was enabled, make sure Noctalia uses DDC monitor control.
        if [ "$DDCUTIL_ENABLED" -eq 1 ] && [ -f "$CONFIG_DIR/noctalia/settings.json" ]; then
            python3 - "$CONFIG_DIR/noctalia/settings.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

brightness = data.get("brightness")
if not isinstance(brightness, dict):
    brightness = {}
    data["brightness"] = brightness

brightness["enableDdcSupport"] = True

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)
    f.write("\n")
PY
            if [ $? -eq 0 ]; then
                chown "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR/noctalia/settings.json"
                echo "Enabled Noctalia DDC support in settings.json."
            else
                echo "Warning: Could not update Noctalia DDC setting automatically."
            fi
        fi
    else
        echo "ERROR: Failed to copy configuration files." >&2
        return 1
    fi
}



update_hypr_startup_config() {
    local startup_file="$ACTUAL_USER_HOME/.config/hypr/startup.lua"

    if [ ! -f "$startup_file" ]; then
        echo "Warning: Hyprland startup file '$startup_file' not found."
        return 0
    fi

    if [ "$INSTALL_NVIDIA_OPTIONAL" -eq 1 ]; then
        if grep -qF 'local enable_nvidia_optional = false' "$startup_file"; then
            echo "Enabling Nvidia-specific Hyprland options in $startup_file..."
            sed -i 's|^local enable_nvidia_optional = false$|local enable_nvidia_optional = true|' "$startup_file"
        else
            echo "Warning: Expected Nvidia toggle line not found in '$startup_file'."
        fi
    fi
}

# Set executable permissions for scripts
set_permissions() {
    SCRIPTS_PATH="$ACTUAL_USER_HOME/.config/hypr/Scripts"
    
    if [ -d "$SCRIPTS_PATH" ]; then
        echo "Setting execution permissions for scripts..."
        find "$SCRIPTS_PATH" -type f -exec chmod +x {} \;
    else
        echo "Warning: Hyprland scripts directory '$SCRIPTS_PATH' not found."
    fi
}

# Browser selection prompt
prompt_browser_installation() {
    echo -e "\n--- Browser Installation ---"
    echo "Which browser would you like to install?"
    echo "  1. Vivaldi"
    echo "  2. Brave"
    echo "  3. Zen Browser"
    echo "  4. Firefox"
    echo "  5. LibreWolf"
    echo "  6. Skip browser installation"
    echo ""
    
    while true; do
        read -r -p "Enter your choice (1-6): " browser_choice
        case "$browser_choice" in
            1)
                BROWSER_CHOICE=1
                break
                ;;
            2)
                BROWSER_CHOICE=2
                break
                ;;
            3)
                BROWSER_CHOICE=3
                break
                ;;
            4)
                BROWSER_CHOICE=4
                break
                ;;
            5)
                BROWSER_CHOICE=5
                break
                ;;
            6)
                BROWSER_CHOICE=6
                break
                ;;
            *)
                echo "Invalid choice. Please enter a number between 1 and 6."
                ;;
        esac
    done
}

# Browser installation
install_browser() {
    local package=''
    case "$BROWSER_CHOICE" in
        1) package='vivaldi' ;;
        2) package='brave-bin' ;;
        3) package='zen-browser-bin' ;;
        4) package='firefox' ;;
        5) package='librewolf' ;;
        *)
            step_skip "no browser selected"
            return 0
            ;;
    esac
    # Five branches that each said "Installing X..." and then installed X are one
    # question: which package. Naming it once means the plan, --needed and the
    # verdict are the same whichever browser a person picked.
    if ! packages_install "browser ($package)" "$package"; then
        step_fail "$package did not install"
    fi
}

# Setup ddcutil for monitor brightness control
setup_ddcutil() {
    echo -e "\n--- Optional: ddcutil Setup ---"
    echo "ddcutil allows you to control monitor brightness via DDC/CI protocol."
    local ddcutil_response

    if [ "$DEFAULT_INSTALL" -eq 1 ]; then
        ddcutil_response="y"
        echo "Default selection: configuring ddcutil."
    else
        read -r -p "Do you want to install and configure ddcutil? (y/N): " ddcutil_response
    fi
    
    if [[ "$ddcutil_response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        # Install ddcutil
        if ! packages_install "ddcutil" ddcutil; then
            step_fail "ddcutil did not install"
            return 1
        fi

        # Install ddcutil-service (AUR, D-Bus activated)
        if command -v yay >/dev/null 2>&1; then
            if ! packages_aur_install "ddcutil-service (AUR)" "$ACTUAL_USER" ddcutil-service; then
                step_note "warning: ddcutil-service did not build; brightness still works without the D-Bus service"
            fi
        else
            step_note "warning: yay was not found; skipping ddcutil-service"
        fi
        
        # Load i2c-dev module
        modprobe i2c-dev
        if [ $? -ne 0 ]; then
            echo "Warning: Failed to load i2c-dev module."
        fi
        
        # Make i2c-dev load on boot
        if ! echo "i2c-dev" > /etc/modules-load.d/i2c-dev.conf; then
            echo "Warning: Failed to configure i2c-dev autoload."
        fi

        # Reload udev rules so ddcutil permissions are applied immediately
        udevadm control --reload-rules
        udevadm trigger
        
        # List i2c devices
        echo "Available i2c devices:"
        ls /dev/i2c-* 2>/dev/null || echo "No i2c devices found (this is normal if not yet configured)"
        
        # Add user to i2c group
        usermod -aG i2c "$ACTUAL_USER"
        if [ $? -ne 0 ]; then
            echo "Warning: Failed to add user to i2c group."
        fi

        # Quick runtime validation; service is D-Bus activated and should respond.
        if ! sudo -u "$ACTUAL_USER" ddcutil-client detect >/dev/null 2>&1; then
            echo "Warning: ddcutil D-Bus detect failed right now. This can still work after relogin/reboot."
        fi

        DDCUTIL_ENABLED=1
        
        step_note "log out and back in for the i2c group to take effect"
    else
        step_skip "ddcutil not selected"
    fi
}

# Set default file manager to Thunar
set_default_file_manager() {
    echo ""
    echo "Setting Thunar as default file manager..."
    # Ensure the user config directory exists so xdg-mime writes to the correct path.
    sudo -u "$ACTUAL_USER" mkdir -p "$ACTUAL_USER_HOME/.config"
    sudo -u "$ACTUAL_USER" xdg-mime default thunar.desktop inode/directory application/x-gnome-saved-search
    echo "Default file manager set to Thunar."
}

# Create GTK bookmarks for Thunar
create_thunar_bookmarks() {
    echo ""
    echo "Creating Thunar bookmarks..."

    local gtk_dir="$ACTUAL_USER_HOME/.config/gtk-3.0"
    local bookmarks_file="$gtk_dir/bookmarks"

    sudo -u "$ACTUAL_USER" mkdir -p "$gtk_dir"

    sudo -u "$ACTUAL_USER" tee "$bookmarks_file" >/dev/null <<EOF
file://$ACTUAL_USER_HOME/Documents
file://$ACTUAL_USER_HOME/Downloads
file://$ACTUAL_USER_HOME/Pictures
file://$ACTUAL_USER_HOME/Music
file://$ACTUAL_USER_HOME/Videos
file://$ACTUAL_USER_HOME/.config/hypr
EOF

    echo "Thunar bookmarks created at $bookmarks_file."
}

# Copy backup config files if available
copy_backup_configs() {
    echo -e "\n--- Optional: Copy Backup Configs ---"
    
    local config_source="$REPO_DIR/backup/.config"
    
    if [[ ! -d "$config_source" ]]; then
        echo "No backup folder found at $REPO_DIR/backup/.config"
        echo "Skipping backup config restoration."
        return 0
    fi
    
    echo "Found backup configs at: $config_source"
    read -r -p "Do you want to restore config files from backup? (y/N): " backup_response
    
    if [[ "$backup_response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
        echo "Copying config files from backup to $CONFIG_DIR..."
        cp -rf "$config_source"/* "$CONFIG_DIR"/
        
        if [ $? -eq 0 ]; then
            echo "Config files copied successfully!"
            
            # Fix ownership since we're running as root
            chown -R "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR"

            # Keep DDC support enabled if ddcutil setup was selected.
            if [ "$DDCUTIL_ENABLED" -eq 1 ] && [ -f "$CONFIG_DIR/noctalia/settings.json" ]; then
                python3 - "$CONFIG_DIR/noctalia/settings.json" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

brightness = data.get("brightness")
if not isinstance(brightness, dict):
    brightness = {}
    data["brightness"] = brightness

brightness["enableDdcSupport"] = True

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=4)
    f.write("\n")
PY
                if [ $? -eq 0 ]; then
                    chown "$ACTUAL_USER:$ACTUAL_USER" "$CONFIG_DIR/noctalia/settings.json"
                    echo "Re-enabled Noctalia DDC support after backup restore."
                else
                    echo "Warning: Could not re-enable Noctalia DDC support after backup restore."
                fi
            fi
            
            # If running under Hyprland, reload it to apply config changes
            if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]]; then
                echo "Detected Hyprland environment. Reloading Hyprland to apply new configs..."
                hyprctl reload 2>/dev/null || echo "Note: Could not reload Hyprland. You may need to restart it manually."
                sleep 2
            fi
        else
            echo "ERROR: Failed to copy backup config files."
        fi
    else
        echo "Skipping backup config restoration."
    fi
}

# Apply optional Dolby PipeWire profile
apply_dolby_pipewire_profile() {
    if [ "$AUDIO_MODE" != "dolby" ]; then
        return 0
    fi

    local pipewire_source="$REPO_DIR/pipewire"
    local pipewire_target="$CONFIG_DIR/pipewire"

    echo -e "\n--- Applying Dolby PipeWire Profile ---"

    if [ ! -d "$pipewire_source" ]; then
        echo "Warning: Dolby profile selected, but no '$pipewire_source' folder was found."
        return 0
    fi

    echo "Copying Dolby PipeWire config to $pipewire_target..."
    sudo -u "$ACTUAL_USER" mkdir -p "$pipewire_target"
    cp -rf "$pipewire_source"/* "$pipewire_target"/

    if [ $? -eq 0 ]; then
        chown -R "$ACTUAL_USER:$ACTUAL_USER" "$pipewire_target"
        echo "Dolby PipeWire profile applied successfully."
    else
        echo "Warning: Failed to apply Dolby PipeWire profile."
    fi
}

setup_noctalia_greeter() {
    echo -e "\n--- Noctalia Greeter Setup ---"

    local greetd_config_file="/etc/greetd/config.toml"
    local greeter_user="greeter"
    local session_bin="/usr/bin/noctalia-greeter-session"

    if command -v noctalia-greeter-session >/dev/null 2>&1; then
        session_bin=$(command -v noctalia-greeter-session)
    fi

    if ! id -u "$greeter_user" >/dev/null 2>&1; then
        echo "Creating greeter user '$greeter_user'..."
        useradd -r -s /usr/bin/nologin -d /var/lib/noctalia-greeter "$greeter_user"
    fi

    echo "Preparing greeter state directory..."
    mkdir -p /var/lib/noctalia-greeter
    # 0750 rather than the umask default of 0755. The greeter's own setup tightens
    # this directory to the greeter account (kSyncedDirMode = S_IRWXU | S_IRGRP |
    # S_IXGRP, noctalia-greeter src/greeter/greeter_preferences.cpp:29, applied at
    # :481). It holds sync.toml, greeter.toml and the synced wallpaper images: no
    # secret, but not a directory every local user should be able to list either.
    chmod 0750 /var/lib/noctalia-greeter
    chown -R "$greeter_user:$greeter_user" /var/lib/noctalia-greeter

    if [ -f "$greetd_config_file" ]; then
        cp -a "$greetd_config_file" "$greetd_config_file.bak.$(date +%s)"
    fi

    echo "Writing greetd configuration to $greetd_config_file..."
    mkdir -p /etc/greetd
    cat > "$greetd_config_file" <<EOF
[terminal]
vt = 1

[default_session]
command = "$session_bin"
user = "$greeter_user"
EOF

    if [ -x /usr/share/noctalia-greeter/setup_greetd_pam.sh ]; then
        echo "Configuring greetd PAM integration for Noctalia Greeter..."
        if ! bash /usr/share/noctalia-greeter/setup_greetd_pam.sh; then
            echo "Warning: greetd PAM setup failed."
        fi
    else
        echo "Warning: /usr/share/noctalia-greeter/setup_greetd_pam.sh was not found."
    fi
}

# --- The steps this repository's own artifacts need ---
#
# Everything above installs packages and other people's configuration. The steps
# below install *this repository*: the commands the session calls by bare name,
# the menu entry that launches the settings window, the PATH that makes both
# resolve, and the wallpapers the picker reads. Without them an install finishes
# "successfully" and the session's own shortcuts do nothing, which is what
# docs/UNVERIFIED.md records as KB-01 and SET-10.

#: Where the installer writes down every path it created outside the repository.
#: A person can read it, a future uninstall can be exact about it, and a second
#: run can tell what it already owns.
install_manifest_path() {
    printf '%s\n' "$ACTUAL_USER_HOME/.local/state/iarch/install-manifest.txt"
}

record_installed_file() {
    local path=$1 manifest
    manifest="$(install_manifest_path)"
    if ! sudo -u "$ACTUAL_USER" mkdir -p -- "$(dirname -- "$manifest")"; then
        step_note "warning: could not create $(dirname -- "$manifest"); the manifest is not being kept"
        return 1
    fi
    if [ -f "$manifest" ] && grep -Fxq -- "$path" "$manifest"; then
        return 0
    fi
    printf '%s\n' "$path" | sudo -u "$ACTUAL_USER" tee -a -- "$manifest" >/dev/null
}

install_core_packages() {
    # This step used to print a countdown and then hand pacman every name in
    # PACKAGES whether the machine had it or not. The plan the library prints is
    # more useful than a countdown: it says how many of the eighty-seven are
    # already current, and a machine that is current opens no transaction.
    if ! packages_install "core packages" "${PACKAGES[@]}"; then
        step_fail "the core packages did not install"
        return 1
    fi
}

upgrade_system() {
    # A partial upgrade is not a state this session can be tested in, and the
    # AUR builds later in the run compile against whatever is installed now.
    if ! pacman -Syu --noconfirm; then
        step_fail "the system upgrade did not complete"
        return 1
    fi
    # The upgrade just changed the answer every later plan is computed from.
    packages_invalidate_cache
}

update_user_directories() {
    # Runs before the wallpaper step on purpose: this is what writes
    # ~/.config/user-dirs.dirs, which is where that step reads the Pictures
    # directory from.
    if ! sudo -u "$ACTUAL_USER" xdg-user-dirs-update; then
        step_note "warning: user directories were not updated"
    fi
}

configure_file_manager() {
    set_default_file_manager
    create_thunar_bookmarks
}

install_icon_themes() {
    local targets=()
    if ! command -v yay >/dev/null 2>&1; then
        step_fail "yay is not installed, so the icon themes cannot be fetched"
        return 1
    fi
    if pacman -Qq bibata-cursor-theme >/dev/null 2>&1 ||
       pacman -Qq "$CURSOR_PACKAGE" >/dev/null 2>&1; then
        step_note "a Bibata cursor theme is already installed; leaving it alone"
    else
        targets+=("$CURSOR_PACKAGE")
    fi
    targets+=("${ICON_PACKAGES[@]}")
    # Deliberately not fatal: the session falls back to another theme, and an
    # install that stops here would leave a machine with no configuration at all.
    if ! packages_aur_install "icons and cursors" "$ACTUAL_USER" "${targets[@]}"; then
        step_note "warning: some icon or cursor themes did not install"
    fi
    if ! packages_aur_install "folder icons" "$ACTUAL_USER" "$FOLDER_ICONS_PACKAGE"; then
        step_note "warning: $FOLDER_ICONS_PACKAGE did not install; folder icons keep their default colour"
    fi
}

install_repo_commands() {
    # The session's keybinds call iarch-keybinds and iarch-cheatsheet by bare
    # name, the menu entry below launches iarch-settings the same way, and none
    # of those names exist on a fresh machine. The linker writes one small
    # wrapper per command into ~/.local/bin, tags each with a marker line so it
    # can tell its own files from anything else, and refuses to overwrite a file
    # it did not write.
    local linker="$REPO_DIR/scripts/iarch-link-cli.sh"
    if [ ! -f "$linker" ]; then
        step_fail "scripts/iarch-link-cli.sh is missing from this checkout"
        return 1
    fi
    if ! sudo -u "$ACTUAL_USER" bash "$linker" --force; then
        step_fail "the session commands could not be linked onto PATH"
        return 1
    fi
    record_installed_file "$ACTUAL_USER_HOME/.local/state/iarch/install-manifest.txt"
    step_note "wrappers written into $ACTUAL_USER_HOME/.local/bin"
}

install_session_path() {
    # ~/.local/bin is not on the PATH of a compositor a display manager started:
    # nothing reads a shell profile on that path. environment.d is the mechanism
    # systemd documents for a user session's environment, so one marked file goes
    # there. Whether the greeter this installer sets up hands that environment to
    # Hyprland is not something a sandbox can watch, and it is recorded as
    # INS-07 in docs/UNVERIFIED.md rather than assumed here.
    local dir="$ACTUAL_USER_HOME/.config/environment.d"
    local target="$dir/iarch-cli-path.conf"
    if ! sudo -u "$ACTUAL_USER" mkdir -p -- "$dir"; then
        step_fail "could not create $dir"
        return 1
    fi
    # A heredoc cannot be the condition of an `if !` -- bash rejects the
    # compound command -- so the two lines are printed into the pipe instead.
    # Both stay single-quoted here and are written literally, because
    # environment.d expands $HOME and $PATH when the session reads the file.
    if ! printf '# Managed by %s install.sh\nPATH=$HOME/.local/bin:$PATH\n' \
            "$IARCH_PRODUCT_NAME" |
        sudo -u "$ACTUAL_USER" tee -- "$target" >/dev/null; then
        step_fail "could not write $target"
        return 1
    fi
    record_installed_file "$target"
    step_note "$target adds ~/.local/bin to the session PATH"
}

install_menu_entry() {
    # The desktop entry is written against the specification and has always been
    # correct; what never happened is anybody copying it where a menu reads it,
    # or installing an icon under the name its Icon= key gives. SET-10 in
    # docs/UNVERIFIED.md records both halves of that.
    local app_id='dev.safari.iarch.settings'
    local entry="$REPO_DIR/iarch/settings-app/$app_id.desktop"
    local logo="$REPO_DIR/assets/branding/iarch-logo.svg"
    local apps="$ACTUAL_USER_HOME/.local/share/applications"
    local icons="$ACTUAL_USER_HOME/.local/share/icons/hicolor/scalable/apps"
    if [ ! -f "$entry" ]; then
        step_fail "the desktop entry is missing from this checkout"
        return 1
    fi
    if ! sudo -u "$ACTUAL_USER" mkdir -p -- "$apps" "$icons"; then
        step_fail "could not create the menu directories"
        return 1
    fi
    if ! cp -- "$entry" "$apps/$app_id.desktop" || ! cp -- "$logo" "$icons/$app_id.svg"; then
        step_fail "could not copy the menu entry or its icon"
        return 1
    fi
    chown "$ACTUAL_USER:$ACTUAL_USER" "$apps/$app_id.desktop" "$icons/$app_id.svg" || return 1
    record_installed_file "$apps/$app_id.desktop"
    record_installed_file "$icons/$app_id.svg"
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database "$apps" >/dev/null 2>&1 ||
            step_note "warning: update-desktop-database did not refresh $apps"
    fi
    step_note "$apps/$app_id.desktop (Exec=iarch-settings, Icon=$app_id)"
}

#: The directory the shell's wallpaper picker reads, resolved the way noctalia
#: v5.4.1 resolves it: XDG_PICTURES_DIR from ~/.config/user-dirs.dirs, else
#: $HOME/Pictures (src/util/file_utils.h:117-230; see docs/WALLPAPERS.md). The
#: session's own environment variable is not readable from a root shell, and
#: user-dirs.dirs is the file it is set from, so this reads the file.
pictures_directory() {
    local dirs="$ACTUAL_USER_HOME/.config/user-dirs.dirs" line value
    if [ -f "$dirs" ]; then
        line=$(grep -m1 '^XDG_PICTURES_DIR=' -- "$dirs" || true)
        value=${line#XDG_PICTURES_DIR=}
        value=${value%\"}
        value=${value#\"}
        value=${value/\$HOME/"$ACTUAL_USER_HOME"}
        if [ -n "$value" ]; then
            printf '%s\n' "$value"
            return 0
        fi
    fi
    printf '%s\n' "$ACTUAL_USER_HOME/Pictures"
}

deploy_wallpapers() {
    # The art is committed under assets/wallpapers and has never been copied
    # anywhere a picker looks, so a fresh install offered nothing this repository
    # shipped. It goes into a named folder rather than loose into Pictures, and
    # an identical file is left alone so a second run copies nothing.
    local pictures target source name count=0 skipped=0
    pictures="$(pictures_directory)"
    target="$pictures/Wallpapers/$IARCH_PRODUCT_NAME"
    if ! sudo -u "$ACTUAL_USER" mkdir -p -- "$target"; then
        step_fail "could not create $target"
        return 1
    fi
    for source in "$REPO_DIR"/assets/wallpapers/*.webp \
                  "$REPO_DIR"/assets/wallpapers/generated/*.webp \
                  "$REPO_DIR"/assets/wallpapers/desktop/*.webp; do
        [ -e "$source" ] || continue
        name=$(basename -- "$source")
        if [ -f "$target/$name" ] && cmp -s -- "$source" "$target/$name"; then
            skipped=$((skipped + 1))
            continue
        fi
        if ! cp -- "$source" "$target/$name"; then
            step_fail "could not copy $name into $target"
            return 1
        fi
        chown "$ACTUAL_USER:$ACTUAL_USER" "$target/$name" || return 1
        record_installed_file "$target/$name"
        count=$((count + 1))
    done
    if [ "$count" -eq 0 ] && [ "$skipped" -eq 0 ]; then
        step_skip "no wallpapers are committed under assets/wallpapers"
        return 0
    fi
    step_note "$count copied, $skipped already there: $target"
    step_note "point Noctalia Settings at that folder, or pick from it directly"
}

install_greeter() {
    # The greeter is an AUR package, so it needs yay; a machine without yay has
    # no login manager and there is nothing to log into, which makes this fatal.
    if ! command -v yay >/dev/null 2>&1; then
        step_fail "yay is not installed and the greeter only exists in the AUR"
        return 1
    fi
    if ! packages_aur_install "login manager (AUR)" "$ACTUAL_USER" noctalia-greeter-git; then
        step_fail "noctalia-greeter-git did not build"
        return 1
    fi
    if ! setup_noctalia_greeter; then
        step_fail "greetd could not be configured for the greeter"
        return 1
    fi
    step_note "disabling sddm, enabling greetd"
    systemctl disable sddm >/dev/null 2>&1 || step_note "sddm was not enabled"
    if ! systemctl enable greetd; then
        step_fail "greetd could not be enabled"
        return 1
    fi
}

# run_step TITLE COMMAND... announces one step, runs it, and prints the verdict
# the command asked for. A command that only exits non-zero gets a generic
# failure, so a step can never finish without saying how it went.
run_step() {
    local title=$1
    shift
    step_begin "$title"
    if ! "$@" && [ "$STEP_VERDICT" = 'ok' ]; then
        step_fail "$title returned a failure"
    fi
    finish_step
}

# fatal_step is run_step for a step whose failure stops the install. Without the
# repository, the core packages, the configuration payload or the login manager
# there is no session to log into, and continuing would leave a half-installed
# machine that is harder to diagnose than a stopped one.
fatal_step() {
    local title=$1
    shift
    step_begin "$title"
    if ! "$@"; then
        if [ "$STEP_VERDICT" = 'ok' ]; then
            step_fail "$title returned a failure"
        fi
        finish_step
        echo ""
        echo "ERROR: $STEP_TITLE failed; stopping the installation." >&2
        wizard_summary
        exit 1
    fi
    finish_step
}

prompt_reboot() {
    local answer
    if [ "$DEFAULT_INSTALL" -eq 1 ] || [ ! -t 0 ]; then
        printf '\nNot rebooting: no terminal to ask on. Reboot when ready and\n'
        printf 'choose %s on the login screen.\n' "$IARCH_PRODUCT_NAME"
        return 0
    fi
    while true; do
        printf '\n%sReboot now?%s [y/N] ' "$BOLD" "$ALL_OFF"
        read -r answer
        case "$answer" in
            y|Y|yes|YES)
                printf 'Rebooting...\n'
                reboot now
                return 0
                ;;
            n|N|no|NO|'')
                printf 'Not rebooting. Log out and back in, then choose %s on the login screen.\n' \
                    "$IARCH_PRODUCT_NAME"
                return 0
                ;;
            *)
                printf 'Please answer y or n.\n'
                ;;
        esac
    done
}

# --- Main Installation Flow ---
#
# One numbered pass, in the order the machine needs it: repositories before
# packages, packages before configuration, configuration before the things that
# launch it, and the login manager last because it is what makes the session
# reachable at all. Every step prints a verdict, and the summary at the end lists
# the ones that did not finish.

wizard_banner

# Choices first, so each package step can report a complete plan rather than
# discovering halfway through that it has nothing to install.
prompt_optional_packages
if [ "$DEFAULT_INSTALL" -eq 1 ]; then
    BROWSER_CHOICE=2
    step_note "default install: the browser is Brave"
else
    prompt_browser_installation
fi

fatal_step "Chaotic-AUR repository"      setup_chaotic_aur
run_step   "Conflicting packages"        remove_conflicting_packages
fatal_step "Core packages"               install_core_packages
run_step   "Gaming packages"             install_gaming_packages
run_step   "Printer support"             install_printer_support_packages
run_step   "Bluetooth"                   install_bluetooth_packages
run_step   "Audio and video players"     install_audio_video_packages
run_step   "Optional packages"           install_optional_packages
run_step   "Icons and cursors"           install_icon_themes
run_step   "User directories"            update_user_directories
fatal_step "System upgrade"              upgrade_system
run_step   "Browser"                     install_browser
run_step   "Display brightness"          setup_ddcutil
run_step   "File manager"                configure_file_manager
fatal_step "Configuration payload"       deploy_configs
run_step   "Backup configuration"        copy_backup_configs
run_step   "Nvidia startup flags"        update_hypr_startup_config
run_step   "File permissions"            set_permissions
run_step   "Dolby PipeWire profile"      apply_dolby_pipewire_profile
run_step   "Session commands on PATH"    install_repo_commands
run_step   "Session PATH"                install_session_path
run_step   "Menu entry"                  install_menu_entry
run_step   "Wallpapers"                  deploy_wallpapers
fatal_step "Login manager"               install_greeter

echo ""
echo "--------------------------------------------------------"
printf '%sAll %d steps have run.%s\n' "$BOLD" "$STEP_NUMBER" "$ALL_OFF"
echo "The manifest of files this installer created is at:"
echo "  $(install_manifest_path)"
echo "--------------------------------------------------------"

wizard_summary
install_status=$?

prompt_reboot

exit "$install_status"
