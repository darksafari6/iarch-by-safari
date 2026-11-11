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

printf '\n'
if [[ $failures -eq 0 ]]; then
    printf 'Rollback script tests passed.\n'
    exit 0
fi
printf '%s test(s) failed.\n' "$failures" >&2
exit 1
