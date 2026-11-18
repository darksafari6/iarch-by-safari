#!/usr/bin/env bash

# iArch by Safari configuration rollback.
#
# Two halves, because they are two different kinds of undo. The first restores
# configuration and never deletes one: if a timestamped backup exists, the active
# file is moved aside and the backup put back in its place; if no backup exists,
# the active configuration is preserved and the run says so. The second reads the
# manifest install.sh writes -- ~/.local/state/iarch/install-manifest.txt, one
# absolute path per line, every file the installer created outside the repository
# -- and removes exactly those paths. Nothing else is touched, and a directory in
# the manifest is reported rather than deleted, because a tree is a claim about
# files this script never enumerated.
#
# Switches honoured through lib/iarch-common.sh:
#   IARCH_ASSUME_YES=1  skip both confirmation prompts
#   IARCH_DRY_RUN=1     report what would be restored and removed, change nothing
#   IARCH_VERBOSE=1     show each step
#
# Installed packages and system services are not reverted here, and the display
# manager is not switched back: re-enabling a unit needs root, and a script that
# asked for it in the same breath as "restore my configuration" would be asking
# for more than the person agreed to. What this script does instead is read the
# state install.sh recorded before it switched, and print the commands that put
# it back with the unit names filled in (INS-03). See docs/ARCHITECTURE.md.

set -u

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=lib/iarch-common.sh
if ! . "$repo_dir/lib/iarch-common.sh"; then
    echo "Could not load $repo_dir/lib/iarch-common.sh" >&2
    exit 1
fi
iarch::load_product || exit 1

CONFIG_DIR="$HOME/.config"
STAMP="$(iarch::stamp)"
TARGETS=(
    "hypr"
    "noctalia"
    "kitty"
    "fish"
    "fastfetch"
    "starship.toml"
    "pipewire"
)

restore_target() {
    local target="$1"
    local active="$CONFIG_DIR/$target"
    local backup preserved

    backup="$(iarch::latest_backup "$active")"

    if [ -z "$backup" ]; then
        iarch::info "[KEEP] no timestamped backup for $target; preserving the current path."
        return 0
    fi

    if iarch::path_exists "$active"; then
        preserved="$(iarch::unique_path "$CONFIG_DIR/$target.iarch-preserved.$STAMP")"
        if iarch::dry_run; then
            iarch::info "[DRY] would move $active aside as $(basename -- "$preserved")"
            iarch::info "[DRY] would restore $target from $(basename -- "$backup")"
            return 0
        fi
        if ! mv -- "$active" "$preserved"; then
            iarch::error "[FAIL] could not preserve the current $active; not restoring $backup."
            return 1
        fi
        iarch::info "[KEEP] current configuration moved to $(basename -- "$preserved")"
    elif iarch::dry_run; then
        iarch::info "[DRY] would restore $target from $(basename -- "$backup")"
        return 0
    fi

    if mv -- "$backup" "$active"; then
        iarch::info "[RESTORED] $target from $(basename -- "$backup")"
    else
        iarch::error "[FAIL] could not restore $backup."
        return 1
    fi
}

MANIFEST="$HOME/.local/state/iarch/install-manifest.txt"
DISPLAY_MANAGER_STATE="$HOME/.local/state/iarch/display-manager-before.txt"

# Remove the files the installer recorded, and only those. Three refusals are
# built in rather than left to judgement: a path that is not absolute is not
# guessed at, a directory is reported instead of deleted, and a path that is
# already gone is a detail rather than an error -- a second run of this script is
# supposed to be boring.
remove_recorded_files() {
    local path removed=0 skipped=0
    while IFS= read -r path || [ -n "$path" ]; do
        [ -n "$path" ] || continue
        case "$path" in
            /*) ;;
            *)
                iarch::warn "[SKIP] the manifest holds a path that is not absolute: $path"
                skipped=$((skipped + 1))
                continue
                ;;
        esac
        if ! iarch::path_exists "$path"; then
            iarch::detail "[GONE] $path"
            continue
        fi
        if [ -d "$path" ] && [ ! -L "$path" ]; then
            iarch::warn "[SKIP] $path is a directory; this script removes files it can name"
            skipped=$((skipped + 1))
            continue
        fi
        if iarch::dry_run; then
            iarch::info "[DRY] would remove $path"
            continue
        fi
        if rm -f -- "$path"; then
            iarch::info "[REMOVED] $path"
            removed=$((removed + 1))
        else
            iarch::error "[FAIL] could not remove $path"
            return 1
        fi
    done < "$MANIFEST"
    if iarch::dry_run; then
        echo "Dry run: nothing was removed. The manifest itself is kept in both cases,"
        echo "because it is the record of what an install did, and removing it would"
        echo "leave a second run with nothing to read."
        return 0
    fi
    echo "Removed $removed recorded file(s); skipped $skipped."
    echo "The manifest is kept at $MANIFEST."
    return 0
}

# What the machine booted before install.sh switched it. The installer writes
# this before `systemctl disable`, because a disable leaves no trace of what it
# replaced; reading it back is the only honest way to name the units to restore.
report_display_manager() {
    local units
    iarch::heading "Display manager"
    if [ ! -f "$DISPLAY_MANAGER_STATE" ]; then
        echo "No record of a previous display manager at $DISPLAY_MANAGER_STATE,"
        echo "so either install.sh never reached that step or it ran before this"
        echo "record existed. Nothing to undo that this script can name."
        return 0
    fi
    units="$(tr '\n' ' ' < "$DISPLAY_MANAGER_STATE")"
    units="${units% }"
    if [ "$units" = "none" ] || [ -z "$units" ]; then
        echo "install.sh recorded that no display manager was enabled before it"
        echo "switched this machine to greetd. To undo the switch:"
        echo "  sudo systemctl disable greetd"
        return 0
    fi
    echo "Before install.sh switched it, this machine booted: $units"
    echo "Re-enabling a unit needs root, which this script does not ask for, so"
    echo "the commands are printed rather than run:"
    echo "  sudo systemctl disable greetd"
    for unit in $units; do
        echo "  sudo systemctl enable $unit"
    done
    return 0
}

iarch::heading "$IARCH_PRODUCT_NAME configuration rollback"
echo "No packages or system services will be removed."
echo "Active files are preserved before a backup is restored."
if ! iarch::confirm "Restore $IARCH_PRODUCT_NAME configuration backups now?"; then
    echo "Cancelled; no files were changed."
    exit 0
fi

failed=0
for target in "${TARGETS[@]}"; do
    restore_target "$target" || failed=1
done

iarch::heading "Files the installer recorded"
if [ -f "$MANIFEST" ]; then
    recorded=$(grep -c '^/' -- "$MANIFEST" 2>/dev/null || true)
    echo "$MANIFEST names ${recorded:-0} absolute path(s) install.sh created."
    echo "Only those files are candidates: directories are reported, not deleted,"
    echo "and nothing outside the manifest is touched."
    if iarch::confirm "Remove the files the install manifest records?"; then
        remove_recorded_files || failed=1
    else
        echo "Kept. The manifest stays at $MANIFEST and this half can be run again."
    fi
else
    echo "No install manifest at $MANIFEST, so there is no list of files this"
    echo "installer created. Nothing is removed on a guess; the configuration"
    echo "rollback above is the whole of what this run can answer for."
fi

report_display_manager

echo
if [ "$failed" -eq 0 ]; then
    echo "Configuration rollback finished. Review any [KEEP] messages."
else
    echo "Rollback had one or more errors. Review the messages above." >&2
fi
echo "The cloned repository was not removed; delete it manually after confirming recovery."
echo "Installed packages, display-manager settings, and system-level changes are not automatically reverted."
exit "$failed"
