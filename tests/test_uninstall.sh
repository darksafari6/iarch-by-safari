#!/usr/bin/env bash
# Tests for uninstall.sh. Runs against a temporary HOME only: the real
# ~/.config, packages and services are never touched.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT

failures=0
check() {
    if [[ "$2" == "$3" ]]; then printf 'ok   - %s\n' "$1"
    else printf 'FAIL - %s: expected %q, got %q\n' "$1" "$2" "$3" >&2; failures=$((failures + 1)); fi
}
check_exists() {
    if [[ -e $2 || -L $2 ]]; then printf 'ok   - %s\n' "$1"
    else printf 'FAIL - %s: missing %s\n' "$1" "$2" >&2; failures=$((failures + 1)); fi
}
check_absent() {
    if [[ ! -e $2 && ! -L $2 ]]; then printf 'ok   - %s\n' "$1"
    else printf 'FAIL - %s: unexpected %s\n' "$1" "$2" >&2; failures=$((failures + 1)); fi
}
check_grep() {
    if printf '%s' "$3" | grep -qF -- "$2"; then printf 'ok   - %s\n' "$1"
    else printf 'FAIL - %s: %q not in output\n' "$1" "$2" >&2; failures=$((failures + 1)); fi
}

# A home with one backed-up target, one target without a backup and one file.
make_home() {
    local home=$1
    mkdir -p -- "$home/.config/hypr" "$home/.config/noctalia" "$home/.config/kitty" \
        "$home/.config/hypr.bak.20260101-000000"
    printf 'deployed hypr\n' >"$home/.config/hypr/hyprland.lua"
    printf 'user hypr\n' >"$home/.config/hypr.bak.20260101-000000/hyprland.lua"
    printf 'deployed shell\n' >"$home/.config/noctalia/config.toml"
    printf 'user kitty\n' >"$home/.config/kitty/kitty.conf"
    printf 'deployed prompt\n' >"$home/.config/starship.toml"
}

# --- restore path ---------------------------------------------------------
home="$tmp/restore"; make_home "$home"
out=$(HOME="$home" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'rollback exits zero' '0' "$rc"
check 'backup content restored' 'user hypr' "$(cat "$home/.config/hypr/hyprland.lua")"
check 'deployed content preserved aside' 'deployed hypr' \
    "$(cat "$(find "$home/.config" -maxdepth 1 -name 'hypr.iarch-preserved.*' -print -quit)/hyprland.lua")"
check_absent 'consumed backup is gone' "$home/.config/hypr.bak.20260101-000000"
check 'target without a backup is untouched' 'user kitty' "$(cat "$home/.config/kitty/kitty.conf")"
check_absent 'no preserved copy for a target without a backup' \
    "$(find "$home/.config" -maxdepth 1 -name 'kitty.iarch-preserved.*' -print -quit)"
check 'starship file kept when it has no backup' 'deployed prompt' "$(cat "$home/.config/starship.toml")"
check_grep 'report says the session name' 'iArch by Safari' "$out"
check_grep 'report marks the restore' '[RESTORED] hypr' "$out"
check_grep 'report marks what it kept' '[KEEP]' "$out"
check_grep 'report does not claim package removal' 'No packages or system services will be removed.' "$out"

# The oldest backup must survive when a newer one is restored.
home2="$tmp/two-backups"; mkdir -p -- "$home2/.config"
printf 'oldest\n' >"$home2/.config/fish.bak.20250101-000000"
printf 'newest\n' >"$home2/.config/fish.bak.20260101-000000"
printf 'current\n' >"$home2/.config/fish"
HOME="$home2" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" >/dev/null 2>&1 || true
check 'newest backup wins' 'newest' "$(cat "$home2/.config/fish")"
check 'older backup is left alone' 'oldest' "$(cat "$home2/.config/fish.bak.20250101-000000")"

# --- cancellation ---------------------------------------------------------
home3="$tmp/cancel"; make_home "$home3"
out=$(printf 'n\n' | HOME="$home3" NO_COLOR=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'answering no exits zero' '0' "$rc"
check_grep 'cancellation is reported' 'Cancelled; no files were changed.' "$out"
check 'cancellation changed nothing' 'deployed hypr' "$(cat "$home3/.config/hypr/hyprland.lua")"
check_exists 'cancellation kept the backup' "$home3/.config/hypr.bak.20260101-000000"

# --- dry run --------------------------------------------------------------
home4="$tmp/dry"; make_home "$home4"
out=$(HOME="$home4" NO_COLOR=1 IARCH_ASSUME_YES=1 IARCH_DRY_RUN=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'dry run exits zero' '0' "$rc"
check_grep 'dry run says what it would do' '[DRY] would restore hypr' "$out"
check 'dry run changed nothing' 'deployed hypr' "$(cat "$home4/.config/hypr/hyprland.lua")"
check_exists 'dry run kept the backup' "$home4/.config/hypr.bak.20260101-000000"
check_absent 'dry run made no preserved copy' \
    "$(find "$home4/.config" -maxdepth 1 -name 'hypr.iarch-preserved.*' -print -quit)"

# --- empty home -----------------------------------------------------------
home5="$tmp/empty"; mkdir -p -- "$home5/.config"
out=$(HOME="$home5" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'empty config exits zero' '0' "$rc"
check_grep 'empty config keeps everything' '[KEEP] no timestamped backup for hypr' "$out"

# --- the manifest half ----------------------------------------------------
# What install.sh records: absolute paths, one per line, of files it created.
make_manifest_home() {
    local home=$1
    mkdir -p -- "$home/.config" "$home/.local/state/iarch" "$home/.local/bin" \
        "$home/.config/environment.d" "$home/Pictures/wallpapers"
    printf 'wrapper\n' >"$home/.local/bin/iarch-keybinds"
    printf 'PATH\n' >"$home/.config/environment.d/iarch-cli-path.conf"
    printf 'art\n' >"$home/Pictures/wallpapers/aurora.png"
    printf 'user own file\n' >"$home/.local/bin/not-mine"
    mkdir -p -- "$home/.local/share/iarch"
    printf 'state\n' >"$home/.local/state/iarch/preflight.json"
    {
        printf '%s\n' "$home/.local/bin/iarch-keybinds"
        printf '%s\n' "$home/.config/environment.d/iarch-cli-path.conf"
        printf '%s\n' "$home/Pictures/wallpapers/aurora.png"
        printf '%s\n' "$home/.local/share/iarch"
        printf '%s\n' "$home/.local/state/iarch/preflight.json"
        printf '%s\n' "relative/path/that-should-be-refused"
        printf '%s\n' "$home/.local/bin/already-gone"
    } >"$home/.local/state/iarch/install-manifest.txt"
}

home6="$tmp/manifest"; make_manifest_home "$home6"
out=$(HOME="$home6" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'manifest run exits zero' '0' "$rc"
check_absent 'a recorded wrapper is removed' "$home6/.local/bin/iarch-keybinds"
check_absent 'a recorded environment.d file is removed' "$home6/.config/environment.d/iarch-cli-path.conf"
check_absent 'a recorded wallpaper is removed' "$home6/Pictures/wallpapers/aurora.png"
check_absent 'a recorded state file is removed' "$home6/.local/state/iarch/preflight.json"
check_exists 'a file the manifest does not name survives' "$home6/.local/bin/not-mine"
check_exists 'a directory in the manifest survives' "$home6/.local/share/iarch"
check_exists 'the manifest itself survives' "$home6/.local/state/iarch/install-manifest.txt"
check_grep 'the run reports each removal' "[REMOVED] $home6/.local/bin/iarch-keybinds" "$out"
check_grep 'a directory is reported and not deleted' 'is a directory' "$out"
check_grep 'a relative path is refused rather than guessed at' 'not absolute' "$out"
check_grep 'the count says what was removed and what was skipped' 'Removed 4 recorded file(s); skipped 2.' "$out"

# A dry run of the same half changes nothing at all.
home7="$tmp/manifest-dry"; make_manifest_home "$home7"
out=$(HOME="$home7" NO_COLOR=1 IARCH_ASSUME_YES=1 IARCH_DRY_RUN=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'manifest dry run exits zero' '0' "$rc"
check_exists 'manifest dry run kept the wrapper' "$home7/.local/bin/iarch-keybinds"
check_grep 'manifest dry run says what it would remove' "[DRY] would remove $home7/.local/bin/iarch-keybinds" "$out"

# Answering no to the second question leaves the recorded files alone.
home8="$tmp/manifest-no"; make_manifest_home "$home8"
out=$(printf 'n\n' | HOME="$home8" NO_COLOR=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'cancelling the whole run exits zero' '0' "$rc"
check_exists 'cancelling kept every recorded file' "$home8/.local/bin/iarch-keybinds"

# No manifest at all is a report, not a guess and not a failure.
out=$(HOME="$home5" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'a home with no manifest exits zero' '0' "$rc"
check_grep 'a missing manifest is reported' 'No install manifest at' "$out"

# --- the display manager --------------------------------------------------
home9="$tmp/display-manager"; make_home "$home9"
mkdir -p -- "$home9/.local/state/iarch"
printf 'sddm\n' >"$home9/.local/state/iarch/display-manager-before.txt"
out=$(HOME="$home9" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check 'display-manager run exits zero' '0' "$rc"
check_grep 'the run names what the machine booted before' 'this machine booted: sddm' "$out"
check_grep 'the run prints the command that undoes the switch' 'sudo systemctl enable sddm' "$out"
check_grep 'the run prints the command that stops greetd' 'sudo systemctl disable greetd' "$out"
check_grep 'the run does not claim it reverted a service' 'are not automatically reverted.' "$out"

home10="$tmp/display-manager-none"; make_home "$home10"
mkdir -p -- "$home10/.local/state/iarch"
printf 'none\n' >"$home10/.local/state/iarch/display-manager-before.txt"
out=$(HOME="$home10" NO_COLOR=1 IARCH_ASSUME_YES=1 bash "$repo/uninstall.sh" 2>&1); rc=$?
check_grep 'a machine with no previous manager is told so' 'no display manager was enabled before' "$out"
check_grep 'and still gets the command that stops greetd' 'sudo systemctl disable greetd' "$out"

printf '\n'
if [[ $failures -eq 0 ]]; then
    printf 'Rollback script tests passed.\n'
    exit 0
fi
printf '%s test(s) failed.\n' "$failures" >&2
exit 1
