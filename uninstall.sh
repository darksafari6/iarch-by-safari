#!/usr/bin/env bash

# minimaLinux configuration rollback.
# This script never deletes an active user configuration. If a timestamped
# backup exists, it moves the active file aside and restores the latest backup.
# If no backup exists, the active configuration is preserved.

set -u

CONFIG_DIR="$HOME/.config"
STAMP="$(date +%Y%m%d-%H%M%S)"
TARGETS=(
    "hypr"
    "noctalia"
    "kitty"
    "fish"
    "fastfetch"
    "starship.toml"
    "pipewire"
)

confirm_action() {
    local response
    read -r -p "Restore minimaLinux configuration backups now? (y/N): " response
    case "$response" in
        y|Y|yes|YES) return 0 ;;
        *) echo "Cancelled; no files were changed."; exit 0 ;;
    esac
}

path_exists() {
    [ -e "$1" ] || [ -L "$1" ]
}

latest_backup_for() {
    local target="$1"
    local candidate
    local latest=""

    for candidate in "$CONFIG_DIR/$target".bak.*; do
        path_exists "$candidate" || continue
        if [ -z "$latest" ] || [[ "$candidate" > "$latest" ]]; then
            latest="$candidate"
        fi
    done

    printf '%s' "$latest"
}

restore_target() {
    local target="$1"
    local active="$CONFIG_DIR/$target"
    local backup
    local preserved

    backup="$(latest_backup_for "$target")"

    if [ -z "$backup" ]; then
        echo "[KEEP] No timestamped backup for $target; preserving the current path."
        return 0
    fi

    if path_exists "$active"; then
        preserved="$CONFIG_DIR/$target.minimaLinux-preserved.$STAMP"
        if ! mv -- "$active" "$preserved"; then
            echo "[FAIL] Could not preserve current $active; not restoring $backup." >&2
            return 1
        fi
        echo "[KEEP] Current configuration moved to $preserved"
    fi

    if mv -- "$backup" "$active"; then
        echo "[RESTORED] $target from $(basename "$backup")"
    else
        echo "[FAIL] Could not restore $backup." >&2
        return 1
    fi
}

echo "======================================================"
echo " minimaLinux configuration rollback"
echo "======================================================"
echo "No packages or system services will be removed."
echo "Active files are preserved before a backup is restored."
confirm_action

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
echo "======================================================"
exit "$failed"
