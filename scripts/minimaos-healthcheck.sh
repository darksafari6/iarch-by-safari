#!/usr/bin/env bash
# Read-only diagnostics for the minimaOS Noctalia/Hyprland profile.
# This script never installs packages, edits config, or changes services.
set -o pipefail

CONFIG_DIR="$HOME/.config/noctalia"
FAILED=0

ok()   { printf '[ OK ] %s\n' "$1"; }
warn() { printf '[WARN] %s\n' "$1"; }
fail() { printf '[FAIL] %s\n' "$1"; FAILED=1; }

printf '\nminimaOS desktop health check\n'
printf '%s\n' '=============================='

if [ "$(id -u)" -eq 0 ]; then
    warn "Run this as your normal desktop user, not through sudo."
fi

if command -v noctalia >/dev/null 2>&1; then
    ok "Noctalia executable found: $(command -v noctalia)"
    if [ -f "$CONFIG_DIR/config.toml" ]; then
        ok "Profile config exists: $CONFIG_DIR/config.toml"
        printf '\nValidating the active Noctalia configuration...\n'
        if noctalia config validate; then
            ok "Noctalia configuration validator passed."
        else
            fail "Noctalia configuration validator reported a problem."
        fi
    else
        warn "No $CONFIG_DIR/config.toml found; defaults or another config root may be active."
    fi
else
    fail "Noctalia command not found. The profile requires Noctalia v5+."
fi

if command -v hyprctl >/dev/null 2>&1; then
    ok "hyprctl executable found."
    if [ -n "$(printenv HYPRLAND_INSTANCE_SIGNATURE 2>/dev/null)" ]; then
        if hyprctl version >/dev/null 2>&1; then
            ok "Hyprland control socket is responding."
        else
            warn "Hyprland is not responding through the current session socket."
        fi
    else
        warn "No active Hyprland session detected; session-only checks were skipped."
    fi
else
    warn "hyprctl not found; this profile is designed for a Hyprland session."
fi

if command -v systemctl >/dev/null 2>&1; then
    if systemctl --user is-active pipewire.service >/dev/null 2>&1 || systemctl --user is-active pipewire-pulse.service >/dev/null 2>&1; then
        ok "A user PipeWire audio service is active."
    else
        warn "PipeWire user service is not active; sound controls may be unavailable."
    fi
    if systemctl --user is-active wireplumber.service >/dev/null 2>&1; then
        ok "WirePlumber user service is active."
    else
        warn "WirePlumber is not active or is not installed."
    fi
else
    warn "systemctl unavailable; service checks were skipped."
fi

printf '\nNotes:\n'
printf '%s\n' '- Network, Bluetooth, brightness, and battery controls depend on real hardware and services.'
printf '%s\n' '- This check does not toggle radios, restart services, or change system files.'
printf '%s\n' '- See docs/minimaOS-Glass-Experience.md for recovery and setup instructions.'

if [ "$FAILED" -ne 0 ]; then
    exit 1
fi
exit 0
