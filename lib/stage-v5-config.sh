#!/usr/bin/env bash
# Build only the v5/Lua config payload in a caller-owned empty directory.
# The v4 payload lives under legacy/config/ and must never reach this payload.
set -euo pipefail
[[ $# == 2 ]] || { echo 'Usage: stage-v5-config.sh SOURCE DESTINATION' >&2; exit 2; }
src=$1 dest=$2
[[ -d $src && -d $dest && ! -L $dest ]] || { echo 'Missing source or unsafe staging directory' >&2; exit 1; }
[[ -z $(ls -A -- "$dest") ]] || { echo 'Destination must be empty' >&2; exit 1; }
for path in fastfetch fish fontconfig/fonts.conf gtk-3.0/gtk.css gtk-4.0/gtk.css Kvantum/kvantum.kvconfig Kvantum/iarch/iarch.kvconfig kitty starship.toml hypr/Scripts hypr/animations.lua hypr/animations/default.lua hypr/generated/animations.lua hypr/generated/glass.lua hypr/hyprland.lua hypr/inputs.lua hypr/keybind.lua hypr/monitors.lua hypr/startup.lua hypr/themes/theme.lua hypr/windowrules.lua noctalia/config.toml noctalia/palettes; do
    [[ -e "$src/$path" && ! -L "$src/$path" ]] || { echo "Missing or symlinked v5 source: $path" >&2; exit 1; }
    mkdir -p -- "$dest/$(dirname -- "$path")"
    cp -a -- "$src/$path" "$dest/$path"
done
