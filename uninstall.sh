#!/usr/bin/env bash

# iArch by Safari configuration rollback.
#
# This script never deletes an active user configuration. If a timestamped
# backup exists, it moves the active file aside and restores the latest backup.
# If no backup exists, the active configuration is preserved.
#
# Switches honoured through lib/iarch-common.sh:
#   IARCH_ASSUME_YES=1  skip the confirmation prompt
#   IARCH_DRY_RUN=1     report what would be restored and change nothing
#   IARCH_VERBOSE=1     show each step
#
# Installed packages, display-manager settings and other system-level changes
# are not reverted here; see docs/ARCHITECTURE.md.

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

echo
if [ "$failed" -eq 0 ]; then
    echo "Configuration rollback finished. Review any [KEEP] messages."
else
    echo "Rollback had one or more errors. Review the messages above." >&2
fi
echo "The cloned repository was not removed; delete it manually after confirming recovery."
echo "Installed packages, display-manager settings, and system-level changes are not automatically reverted."
exit "$failed"
