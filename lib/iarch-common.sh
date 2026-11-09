# shellcheck shell=bash
# iArch by Safari — shared shell helpers for installers and runtime scripts.
#
# Source this file, never execute it:
#
#     repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
#     . "$repo/lib/iarch-common.sh" || exit 1
#     iarch::load_product || exit 1
#
# It implements the safety contract in docs/ARCHITECTURE.md:
#   * back up before overwriting, with a timestamped, collision-free suffix
#   * idempotent operations — an unchanged file is a reported success
#   * refuse ambiguous targets (symlinks, foreign content) instead of guessing
#   * never delete what this repository did not create
#   * fail closed, and always say where the backup went
#
# Environment switches honoured by every mutating helper:
#   IARCH_DRY_RUN=1      report what would change and change nothing
#   IARCH_ASSUME_YES=1   iarch::confirm succeeds without reading stdin
#   IARCH_VERBOSE=1      iarch::detail prints
#   NO_COLOR=1           plain output (also automatic when stdout is not a tty)
#
# The product name is never hardcoded here; it comes from branding/product.env
# through iarch::load_product.

if [[ -n ${IARCH_COMMON_LOADED:-} ]]; then
    return 0 2>/dev/null || exit 0
fi
IARCH_COMMON_LOADED=1

# --- output ---------------------------------------------------------------

_iarch_colors() {
    if [[ ${NO_COLOR:-} == 1 || ! -t 1 ]]; then
        IARCH_C_RESET='' IARCH_C_RED='' IARCH_C_GREEN='' IARCH_C_YELLOW='' IARCH_C_DIM=''
        return 0
    fi
    IARCH_C_RESET=$'\033[0m' IARCH_C_RED=$'\033[31m' IARCH_C_GREEN=$'\033[32m'
    IARCH_C_YELLOW=$'\033[33m' IARCH_C_DIM=$'\033[2m'
}
_iarch_colors

iarch::info()    { printf '%s[INFO]%s %s\n' "$IARCH_C_GREEN" "$IARCH_C_RESET" "$*"; }
iarch::warn()    { printf '%s[WARN]%s %s\n' "$IARCH_C_YELLOW" "$IARCH_C_RESET" "$*" >&2; }
iarch::error()   { printf '%s[FAIL]%s %s\n' "$IARCH_C_RED" "$IARCH_C_RESET" "$*" >&2; }
iarch::detail()  { [[ ${IARCH_VERBOSE:-0} == 1 ]] && printf '%s[....]%s %s\n' "$IARCH_C_DIM" "$IARCH_C_RESET" "$*"; return 0; }
iarch::heading() { printf '\n%s== %s ==%s\n' "$IARCH_C_DIM" "$*" "$IARCH_C_RESET"; }

# Print a message and exit nonzero. Used for conditions that must stop a run.
iarch::die() {
    iarch::error "$*"
    exit 1
}

iarch::dry_run() { [[ ${IARCH_DRY_RUN:-0} == 1 ]]; }

# --- paths and product identity -------------------------------------------

# Absolute path of the repository checkout this library was sourced from.
iarch::repo_root() {
    ( cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P )
}

# Load branding/product.env once. After this, IARCH_PRODUCT_NAME and friends
# are set. Fails instead of falling back to a hardcoded name.
iarch::load_product() {
    [[ -n ${IARCH_PRODUCT_LOADED:-} ]] && return 0
    local root env_file
    root=$(iarch::repo_root) || return 1
    env_file="$root/branding/product.env"
    if [[ ! -f $env_file ]]; then
        iarch::error "missing product naming file: $env_file"
        return 1
    fi
    # The file is KEY="value" lines only; sourcing it cannot run commands.
    # shellcheck source=/dev/null
    . "$env_file" || return 1
    IARCH_PRODUCT_LOADED=1
    if [[ -z ${IARCH_PRODUCT_NAME:-} ]]; then
        iarch::error "$env_file did not define IARCH_PRODUCT_NAME"
        return 1
    fi
    return 0
}

iarch::command_exists() { command -v "$1" >/dev/null 2>&1; }

# --- users and privileges -------------------------------------------------

# The account an installer should act for: the user behind sudo, else the
# logged-in user. Never "root".
iarch::target_user() {
    local user=${SUDO_USER:-}
    if [[ -z $user || $user == root ]]; then
        user=$(logname 2>/dev/null || true)
    fi
    if [[ -z $user || $user == root ]]; then
        return 1
    fi
    printf '%s\n' "$user"
}

iarch::target_home() {
    local user home
    user=$(iarch::target_user) || return 1
    if ! iarch::command_exists getent; then
        iarch::error "getent is unavailable; cannot resolve the home directory of $user"
        return 1
    fi
    home=$(getent passwd "$user" | cut -d: -f6)
    if [[ -z $home ]]; then
        iarch::error "no home directory recorded for user $user"
        return 1
    fi
    printf '%s\n' "$home"
}

iarch::require_root() {
    if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
        iarch::error "this step must run as root (use sudo)"
        return 1
    fi
    return 0
}

iarch::refuse_root() {
    if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
        iarch::error "run this as your desktop user, not with sudo"
        return 1
    fi
    return 0
}

# --- confirmation ---------------------------------------------------------

# iarch::confirm "question"  ->  0 on yes, 1 on no. Honours IARCH_ASSUME_YES.
iarch::confirm() {
    if [[ ${IARCH_ASSUME_YES:-0} == 1 ]]; then
        iarch::detail "assuming yes: $*"
        return 0
    fi
    local reply
    printf '%s [y/N]: ' "$*"
    if ! read -r reply; then
        return 1
    fi
    case $reply in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# --- timestamps, backups and safe installation ----------------------------

iarch::stamp() { date +%Y%m%d-%H%M%S; }

# Print a path that does not exist yet, adding .1, .2, ... if needed. Two runs
# in the same second must never overwrite each other's backup.
iarch::unique_path() {
    local candidate=$1 suffix=1
    while [[ -e $candidate || -L $candidate ]]; do
        candidate="$1.$suffix"
        suffix=$((suffix + 1))
    done
    printf '%s\n' "$candidate"
}

iarch::path_exists() { [[ -e $1 || -L $1 ]]; }

# Move a path aside before it is replaced. Prints the backup path when one was
# made. A missing target is a success with no output: there is nothing to
# protect. Never deletes anything.
iarch::backup() {
    local target=$1 stamp=${2:-$(iarch::stamp)} backup
    if [[ -z $target ]]; then
        iarch::error "iarch::backup needs a target path"
        return 2
    fi
    if ! iarch::path_exists "$target"; then
        iarch::detail "nothing to back up: $target"
        return 0
    fi
    backup=$(iarch::unique_path "$target.bak.$stamp") || return 1
    if iarch::dry_run; then
        iarch::detail "would back up $target to $backup"
        printf '%s\n' "$backup"
        return 0
    fi
    if ! mv -- "$target" "$backup"; then
        iarch::error "could not back up $target to $backup; refusing to continue"
        return 1
    fi
    iarch::detail "backed up $target to $backup"
    printf '%s\n' "$backup"
    return 0
}

# Latest timestamped backup for a path, or empty output when there is none.
# Sorting is lexical, which matches the %Y%m%d-%H%M%S stamp format.
iarch::latest_backup() {
    local target=$1 candidate latest=''
    for candidate in "$target".bak.*; do
        iarch::path_exists "$candidate" || continue
        if [[ -z $latest || $candidate > $latest ]]; then
            latest=$candidate
        fi
    done
    printf '%s' "$latest"
}

# Install one file: back up the target first, then copy. Idempotent — an
# identical target is reported and left alone, so a second run creates no
# backup and changes nothing. Refuses symlinks and directories as targets.
#   iarch::install_file SOURCE TARGET [MODE]
iarch::install_file() {
    local source=$1 target=${2:-} mode=${3:-0644} backup
    if [[ -z $target ]]; then
        iarch::error "iarch::install_file needs SOURCE and TARGET"
        return 2
    fi
    if [[ ! -f $source ]]; then
        iarch::error "source file is missing: $source"
        return 1
    fi
    if [[ -L $target ]]; then
        iarch::error "refusing to install over a symlink: $target"
        return 1
    fi
    if [[ -d $target ]]; then
        iarch::error "refusing to install a file over a directory: $target"
        return 1
    fi
    if [[ -e $target ]] && cmp -s -- "$source" "$target"; then
        iarch::info "unchanged: $target"
        return 0
    fi
    backup=$(iarch::backup "$target") || return 1
    if [[ -n $backup ]]; then
        iarch::info "backed up $target -> $(basename -- "$backup")"
    fi
    if iarch::dry_run; then
        iarch::info "would install $source -> $target (mode $mode)"
        return 0
    fi
    mkdir -p -- "$(dirname -- "$target")" || return 1
    if ! install -m "$mode" -- "$source" "$target"; then
        iarch::error "could not install $source to $target${backup:+; the previous file is at $backup}"
        return 1
    fi
    iarch::detail "installed $source -> $target"
    return 0
}

# Install a directory tree with the same contract: the existing target is moved
# aside as a whole, then the source tree is copied. Nothing is merged into a
# live tree and nothing is deleted.
#   iarch::install_tree SOURCE_DIR TARGET_DIR
iarch::install_tree() {
    local source=$1 target=${2:-} backup
    if [[ -z $target ]]; then
        iarch::error "iarch::install_tree needs SOURCE_DIR and TARGET_DIR"
        return 2
    fi
    if [[ ! -d $source || -L $source ]]; then
        iarch::error "source must be a real directory: $source"
        return 1
    fi
    if [[ -L $target ]]; then
        iarch::error "refusing to install over a symlink: $target"
        return 1
    fi
    if [[ -e $target && ! -d $target ]]; then
        iarch::error "refusing to replace a non-directory: $target"
        return 1
    fi
    backup=$(iarch::backup "$target") || return 1
    if [[ -n $backup ]]; then
        iarch::info "backed up $target -> $(basename -- "$backup")"
    fi
    if iarch::dry_run; then
        iarch::info "would install tree $source -> $target"
        return 0
    fi
    mkdir -p -- "$(dirname -- "$target")" || return 1
    if ! cp -a -- "$source" "$target"; then
        iarch::error "could not copy $source to $target${backup:+; the previous tree is at $backup}"
        return 1
    fi
    iarch::detail "installed tree $source -> $target"
    return 0
}

# --- change record --------------------------------------------------------

# Append one line to a manifest so an install can be reviewed or undone later.
# Tab separated: time, action, target, detail. Created with mode 0600.
#   iarch::manifest_record MANIFEST ACTION TARGET [DETAIL]
iarch::manifest_record() {
    local manifest=$1 action=${2:-} target=${3:-} detail=${4:-}
    if [[ -z $manifest || -z $action || -z $target ]]; then
        iarch::error "iarch::manifest_record needs MANIFEST ACTION TARGET"
        return 2
    fi
    if iarch::dry_run; then
        iarch::detail "would record $action $target in $manifest"
        return 0
    fi
    mkdir -p -- "$(dirname -- "$manifest")" || return 1
    (
        umask 077
        printf '%s\t%s\t%s\t%s\n' "$(date -Is 2>/dev/null || iarch::stamp)" \
            "$action" "$target" "$detail" >>"$manifest"
    ) || {
        iarch::error "could not write the change record: $manifest"
        return 1
    }
    return 0
}
