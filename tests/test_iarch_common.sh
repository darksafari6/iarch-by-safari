#!/usr/bin/env bash
# Tests for lib/iarch-common.sh. Runs against temporary directories only:
# nothing here touches ~/.config, a package manager or a session.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf -- "$tmp"' EXIT

failures=0
check() {
    local label=$1 expected=$2 actual=$3
    if [[ "$expected" == "$actual" ]]; then
        printf 'ok   - %s\n' "$label"
    else
        printf 'FAIL - %s: expected %q, got %q\n' "$label" "$expected" "$actual" >&2
        failures=$((failures + 1))
    fi
}
check_exists() {
    if [[ -e $2 || -L $2 ]]; then printf 'ok   - %s\n' "$1"
    else printf 'FAIL - %s: missing %s\n' "$1" "$2" >&2; failures=$((failures + 1)); fi
}
check_absent() {
    if [[ ! -e $2 && ! -L $2 ]]; then printf 'ok   - %s\n' "$1"
    else printf 'FAIL - %s: unexpected %s\n' "$1" "$2" >&2; failures=$((failures + 1)); fi
}
check_rc() {
    local label=$1 expected=$2 actual=$3
    if [[ "$expected" == "$actual" ]]; then printf 'ok   - %s\n' "$label"
    else printf 'FAIL - %s: expected exit %s, got %s\n' "$label" "$expected" "$actual" >&2
    failures=$((failures + 1)); fi
}

export NO_COLOR=1
# shellcheck source=/dev/null
. "$repo/lib/iarch-common.sh"

# --- loading is idempotent and the product name comes from the file --------
check 'repo_root resolves' "$repo" "$(iarch::repo_root)"
iarch::load_product
check 'product name loaded' 'iArch by Safari' "$IARCH_PRODUCT_NAME"
iarch::load_product
check 'second load is a no-op' 'iArch by Safari' "$IARCH_PRODUCT_NAME"
check 'second sourcing of the library is a no-op' '1' "$IARCH_COMMON_LOADED"

# --- stamps and collision-free backup paths -------------------------------
if [[ $(iarch::stamp) =~ ^[0-9]{8}-[0-9]{6}$ ]]; then
    printf 'ok   - stamp format\n'
else
    printf 'FAIL - stamp format: %s\n' "$(iarch::stamp)" >&2
    failures=$((failures + 1))
fi

occupied="$tmp/occupied"
printf 'x\n' >"$occupied"
unique=$(iarch::unique_path "$occupied")
check 'unique_path skips an occupied name' "$occupied.1" "$unique"
printf 'x\n' >"$occupied.1"
check 'unique_path keeps counting' "$occupied.2" "$(iarch::unique_path "$occupied")"
check 'unique_path returns a free path unchanged' "$tmp/free" "$(iarch::unique_path "$tmp/free")"

# --- backup ---------------------------------------------------------------
work="$tmp/backup"; mkdir -p -- "$work"
if out=$(iarch::backup "$work/missing"); then
    check 'backup of a missing path prints nothing' '' "$out"
else
    printf 'FAIL - backup of a missing path returned nonzero\n' >&2; failures=$((failures + 1))
fi

printf 'original\n' >"$work/config"
backup=$(iarch::backup "$work/config")
check_exists 'backup file created' "$backup"
check_absent 'original moved away' "$work/config"
check 'backup content preserved' 'original' "$(cat "$backup")"
if [[ $(basename -- "$backup") =~ ^config\.bak\.[0-9]{8}-[0-9]{6}$ ]]; then
    printf 'ok   - backup suffix is timestamped\n'
else
    printf 'FAIL - backup suffix: %s\n' "$(basename -- "$backup")" >&2
    failures=$((failures + 1))
fi

# Two backups in the same second must not collide.
printf 'first\n' >"$work/same"; first=$(iarch::backup "$work/same" 20260101-000000)
printf 'second\n' >"$work/same"; second=$(iarch::backup "$work/same" 20260101-000000)
check 'same-second backups differ' 'false' "$([[ $first == "$second" ]] && echo true || echo false)"
check 'first backup still holds its content' 'first' "$(cat "$first")"
check 'second backup holds its own content' 'second' "$(cat "$second")"

# latest_backup picks the newest by stamp.
printf 'a\n' >"$work/target"
iarch::backup "$work/target" 20260101-000000 >/dev/null
printf 'b\n' >"$work/target"
iarch::backup "$work/target" 20260202-000000 >/dev/null
check 'latest_backup finds the newest' "$work/target.bak.20260202-000000" "$(iarch::latest_backup "$work/target")"
check 'latest_backup is empty without backups' '' "$(iarch::latest_backup "$work/nothing")"

# --- install_file ---------------------------------------------------------
inst="$tmp/install"; mkdir -p -- "$inst/source"
printf 'new\n' >"$inst/source/file"

rc=0; iarch::install_file "$inst/source/missing" "$inst/target" >/dev/null 2>&1 || rc=$?
check_rc 'missing source is refused' 1 "$rc"
check_absent 'refused install created nothing' "$inst/target"

ln -s "$inst/source/file" "$inst/link"
rc=0; iarch::install_file "$inst/source/file" "$inst/link" >/dev/null 2>&1 || rc=$?
check_rc 'symlink target is refused' 1 "$rc"
check_exists 'refused symlink is intact' "$inst/link"

iarch::install_file "$inst/source/file" "$inst/target" >/dev/null
check 'file installed' 'new' "$(cat "$inst/target")"
check 'installed mode' '644' "$(stat -c '%a' "$inst/target")"
check_absent 'first install made no backup' "$inst/target.bak.$(iarch::stamp)"

before=$(find "$inst" -name 'target.bak.*' | wc -l)
out=$(iarch::install_file "$inst/source/file" "$inst/target")
after=$(find "$inst" -name 'target.bak.*' | wc -l)
check 'second identical install reports unchanged' 'unchanged' \
    "$(printf '%s' "$out" | grep -o 'unchanged' | head -1)"
check 'idempotent install creates no backup' "$before" "$after"

printf 'changed\n' >"$inst/source/file"
iarch::install_file "$inst/source/file" "$inst/target" 0600 >/dev/null
check 'changed source is installed' 'changed' "$(cat "$inst/target")"
check 'changed install sets the requested mode' '600' "$(stat -c '%a' "$inst/target")"
check 'previous content was backed up' '1' "$(find "$inst" -name 'target.bak.*' | wc -l)"
check 'backup holds the previous content' 'new' "$(cat "$(find "$inst" -name 'target.bak.*' | head -1)")"

# --- install_tree ---------------------------------------------------------
tree_src="$tmp/tree/source"; mkdir -p -- "$tree_src/nested"
printf 'one\n' >"$tree_src/a"; printf 'two\n' >"$tree_src/nested/b"
mkdir -p -- "$tmp/tree/target/nested"; printf 'old\n' >"$tmp/tree/target/a"

iarch::install_tree "$tree_src" "$tmp/tree/target" >/dev/null
check 'tree installed' 'one' "$(cat "$tmp/tree/target/a")"
check 'nested file installed' 'two' "$(cat "$tmp/tree/target/nested/b")"
check_absent 'stale file from the old tree is gone' "$tmp/tree/target/old"
check 'old tree preserved as a backup' 'old' "$(cat "$(find "$tmp/tree" -path '*target.bak.*/a')")"

ln -s "$tree_src" "$tmp/tree/symlinked"
rc=0; iarch::install_tree "$tree_src" "$tmp/tree/symlinked" >/dev/null 2>&1 || rc=$?
check_rc 'tree install refuses a symlink target' 1 "$rc"
check 'refused symlink target still points at the source' "$tree_src" "$(readlink "$tmp/tree/symlinked")"

# --- dry run changes nothing ---------------------------------------------
dry="$tmp/dry"; mkdir -p -- "$dry"
printf 'keep\n' >"$dry/config"
IARCH_DRY_RUN=1 iarch::install_file "$inst/source/file" "$dry/config" >/dev/null
check 'dry run left the target alone' 'keep' "$(cat "$dry/config")"
check_absent 'dry run made no backup' "$(find "$dry" -name 'config.bak.*' | head -1)"
IARCH_DRY_RUN=1 iarch::backup "$dry/config" >/dev/null
check 'dry run backup did not move the file' 'keep' "$(cat "$dry/config")"

# --- confirmation ---------------------------------------------------------
rc=0; IARCH_ASSUME_YES=1 iarch::confirm 'proceed?' >/dev/null || rc=$?
check_rc 'IARCH_ASSUME_YES answers yes' 0 "$rc"
rc=0; printf 'n\n' | iarch::confirm 'proceed?' >/dev/null || rc=$?
check_rc 'no answers nonzero' 1 "$rc"
rc=0; printf 'yes\n' | iarch::confirm 'proceed?' >/dev/null || rc=$?
check_rc 'yes answers zero' 0 "$rc"
rc=0; iarch::confirm 'proceed?' </dev/null >/dev/null || rc=$?
check_rc 'closed stdin answers nonzero' 1 "$rc"

# --- users and privileges -------------------------------------------------
if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
    rc=0; iarch::refuse_root >/dev/null 2>&1 || rc=$?
    check_rc 'refuse_root rejects root' 1 "$rc"
    rc=0; iarch::require_root >/dev/null 2>&1 || rc=$?
    check_rc 'require_root accepts root' 0 "$rc"
else
    rc=0; iarch::refuse_root >/dev/null 2>&1 || rc=$?
    check_rc 'refuse_root accepts a normal user' 0 "$rc"
    rc=0; iarch::require_root >/dev/null 2>&1 || rc=$?
    check_rc 'require_root rejects a normal user' 1 "$rc"
fi
resolved=$(SUDO_USER=root iarch::target_user 2>/dev/null || true)
check 'target_user never returns root' 'false' "$([[ $resolved == root ]] && echo true || echo false)"
check 'target_user honours SUDO_USER' 'someone' "$(SUDO_USER=someone iarch::target_user)"

# --- change record --------------------------------------------------------
manifest="$tmp/state/manifest.tsv"
iarch::manifest_record "$manifest" backup "$tmp/tree/target" 'moved aside'
iarch::manifest_record "$manifest" install "$tmp/tree/target" 'from source tree'
check 'manifest has one line per action' '2' "$(wc -l <"$manifest")"
check 'manifest records the action' 'backup' "$(cut -f2 "$manifest" | head -1)"
check 'manifest records the detail' 'moved aside' "$(cut -f4 "$manifest" | head -1)"
check 'manifest is private' '600' "$(stat -c '%a' "$manifest")"
rc=0; iarch::manifest_record "$manifest" backup >/dev/null 2>&1 || rc=$?
check_rc 'manifest refuses an incomplete record' 2 "$rc"

# --- logging goes to the right stream ------------------------------------
check 'info writes to stdout' 'hello' "$(iarch::info 'hello' 2>/dev/null | grep -o 'hello')"
check 'warn writes to stderr' 'careful' "$(iarch::warn 'careful' 2>&1 >/dev/null | grep -o 'careful')"
check 'error writes to stderr' 'broken' "$(iarch::error 'broken' 2>&1 >/dev/null | grep -o 'broken')"
check 'detail is silent by default' '' "$(iarch::detail 'hidden' 2>/dev/null)"
check 'detail prints when verbose' 'shown' "$(IARCH_VERBOSE=1 iarch::detail 'shown' 2>/dev/null | grep -o 'shown')"

printf '\n'
if [[ $failures -eq 0 ]]; then
    printf 'Shared library tests passed.\n'
    exit 0
fi
printf '%s test(s) failed.\n' "$failures" >&2
exit 1
