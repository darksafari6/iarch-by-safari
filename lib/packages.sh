# shellcheck shell=bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Decide what actually needs installing, so a run on a machine that is already
# up to date opens no transaction at all.
#
# The authority on a transaction stays with the package manager. pacman(8) says
# of --needed: "Do not reinstall the targets that are already up-to-date"
# (UPGRADE OPTIONS (APPLY TO -S AND -U), https://man.archlinux.org/man/pacman.8).
# yay accepts the same flag and its own manual uses it -- yay(8) EXAMPLES:
# `pacman -Qmq | grep -Ee '-(cvs|svn|git|hg|bzr|darcs)$' | yay -S --needed -`
# (https://github.com/Jguer/yay/blob/next/doc/yay.8).
#
# What this file adds is the part a flag cannot do: say what is about to happen.
# An installer that hands pacman eighty-seven package names cannot tell the
# person watching which of them were already current, and on a machine where all
# of them are it still opens a transaction and re-downloads nothing for a long
# time. So the state of every target is read out of the local database first,
# the plan is printed, and a transaction is opened only when the plan is not
# empty. --needed is still passed, because the local database can change between
# the two reads and pacman remains the one that decides.
#
# Repository targets are aged with two read-only queries and nothing else:
#   missing   `pacman -Qq NAME` finds nothing in the local database
#   outdated  installed, and `pacman -Quq` lists it -- the sync database is
#             refreshed once per run first, because pacman(8) notes that -Qu
#             "works best if the sync database is refreshed using -Sy"
#   current   installed and not listed by `pacman -Quq`
#
# An AUR target cannot be aged the same way. Its version is whatever the
# PKGBUILD in the AUR builds right now, which only yay can tell, and yay finds
# out by fetching the AUR. So AUR targets are classified missing|installed here
# and always handed to yay with --needed, leaving the currency judgement to the
# tool that has the data instead of guessing at it in a shell script.
#
# Nothing in this file removes a package, edits a database, or writes outside
# the two functions named install.
PACKAGES_SYNC_DB_REFRESHED=false
PACKAGES_OUTDATED_CACHE=''
PACKAGES_MISSING=()
PACKAGES_OUTDATED=()
PACKAGES_CURRENT=()
PACKAGES_INSTALLED=()

# Refresh the sync databases once per run. `pacman -Qu` only reports what those
# databases know about, so without this an outdated package reads as current.
packages_refresh_sync_db() {
    if $PACKAGES_SYNC_DB_REFRESHED; then return 0; fi
    if ! pacman -Sy >&2; then
        printf 'Cannot refresh the package databases; installed packages will be\n' >&2
        printf 'reported as current even when an update is available.\n' >&2
        return 1
    fi
    PACKAGES_SYNC_DB_REFRESHED=true
    PACKAGES_OUTDATED_CACHE=''
}

# The names pacman considers out of date, one per line, cached per run.
# `pacman -Qu` exits non-zero when nothing needs upgrading, which is an answer
# and not a failure, so its status is deliberately not propagated.
packages_outdated_names() {
    if [[ -z $PACKAGES_OUTDATED_CACHE ]]; then
        PACKAGES_OUTDATED_CACHE=$(pacman -Quq 2>/dev/null || true)
    fi
    if [[ -n $PACKAGES_OUTDATED_CACHE ]]; then
        printf '%s\n' "$PACKAGES_OUTDATED_CACHE"
    fi
}

# package_state NAME -> missing|outdated|current
package_state() {
    local name=$1
    if ! pacman -Qq "$name" >/dev/null 2>&1; then
        printf 'missing\n'
        return 0
    fi
    if packages_outdated_names | grep -Fxq -- "$name"; then
        printf 'outdated\n'
    else
        printf 'current\n'
    fi
}

# installed_state NAME -> missing|installed
# The AUR half of the same question, without an age: is it in the local
# database at all?
installed_state() {
    if pacman -Qq "$1" >/dev/null 2>&1; then
        printf 'installed\n'
    else
        printf 'missing\n'
    fi
}

# packages_classify NAME... fills the four arrays. Read-only.
packages_classify() {
    local name state
    PACKAGES_MISSING=()
    PACKAGES_OUTDATED=()
    PACKAGES_CURRENT=()
    PACKAGES_INSTALLED=()
    packages_refresh_sync_db || return 1
    for name in "$@"; do
        state=$(package_state "$name") || return 1
        case $state in
            missing)  PACKAGES_MISSING+=("$name") ;;
            outdated) PACKAGES_OUTDATED+=("$name") ;;
            current)  PACKAGES_CURRENT+=("$name") ;;
            *)
                printf 'Read an impossible package state %s for %s.\n' "$state" "$name" >&2
                return 1
                ;;
        esac
        if [[ $state != missing ]]; then PACKAGES_INSTALLED+=("$name"); fi
    done
}

# aur_classify NAME... fills missing|installed for AUR targets.
aur_classify() {
    local name state
    PACKAGES_MISSING=()
    PACKAGES_INSTALLED=()
    for name in "$@"; do
        state=$(installed_state "$name") || return 1
        case $state in
            missing)   PACKAGES_MISSING+=("$name") ;;
            installed) PACKAGES_INSTALLED+=("$name") ;;
            *)
                printf 'Read an impossible AUR state %s for %s.\n' "$state" "$name" >&2
                return 1
                ;;
        esac
    done
}

# packages_invalidate_cache forgets what the databases said. Call it after
# anything that changes them -- a full upgrade, a repository being added --
# because a plan computed from the previous answer would name packages as
# outdated that the upgrade has already brought current.
packages_invalidate_cache() {
    PACKAGES_SYNC_DB_REFRESHED=false
    PACKAGES_OUTDATED_CACHE=''
}

# packages_needed_count -> how many targets a transaction would have to touch.
packages_needed_count() {
    printf '%d\n' "$(( ${#PACKAGES_MISSING[@]} + ${#PACKAGES_OUTDATED[@]} ))"
}

# packages_report LABEL prints the plan in plain text, one fact per line, on
# stderr. This file has no colours and no cursor control, so the same lines are
# readable in a log, over ssh without a tty, and in a test; stderr is where the
# installer's own notes go, which leaves stdout to pacman's progress output and
# keeps a caller's `$( ... )` from swallowing the transaction it just started.
packages_report() {
    local label=$1
    printf '  %s: %d to install, %d to update, %d already current\n' \
        "$label" "${#PACKAGES_MISSING[@]}" "${#PACKAGES_OUTDATED[@]}" "${#PACKAGES_CURRENT[@]}" >&2
    if ((${#PACKAGES_MISSING[@]})); then
        printf '  install: %s\n' "${PACKAGES_MISSING[*]}" >&2
    fi
    if ((${#PACKAGES_OUTDATED[@]})); then
        printf '  update: %s\n' "${PACKAGES_OUTDATED[*]}" >&2
    fi
}

# aur_report LABEL prints the same plan for AUR targets, which have no age.
aur_report() {
    local label=$1
    printf '  %s: %d to install, %d already installed\n' \
        "$label" "${#PACKAGES_MISSING[@]}" "${#PACKAGES_INSTALLED[@]}" >&2
    if ((${#PACKAGES_MISSING[@]})); then
        printf '  install: %s\n' "${PACKAGES_MISSING[*]}" >&2
    fi
}

# _packages_pacman_install CONFIRM runs the transaction the plan asked for.
# CONFIRM=1 adds --noconfirm; the one list that stays interactive is the gaming
# list, which the installer has always left to pacman's own review prompt.
_packages_pacman_install() {
    local confirm=$1
    local flags=(--needed)
    if [[ $confirm -eq 1 ]]; then flags=(--noconfirm --needed); fi
    # No `--` before the targets, and that is not an oversight. pacman's own
    # argument parser cannot be read from here -- pacman lives on
    # gitlab.archlinux.org and the GitHub mirror 404s -- so this file only uses
    # syntax pacman(8) documents. The targets are names out of this
    # repository's own arrays, never text a person typed, so none can begin with
    # a hyphen and be read as an option.
    pacman -S "${flags[@]}" "${PACKAGES_MISSING[@]}" "${PACKAGES_OUTDATED[@]}"
}

# packages_install LABEL NAME... installs only what is not already current.
# Returns 0 when there was nothing to do, which is the common case on a machine
# this installer has already been run on.
packages_install() {
    local label=$1
    shift
    packages_classify "$@" || return 1
    packages_report "$label"
    if [[ $(packages_needed_count) -eq 0 ]]; then
        return 0
    fi
    _packages_pacman_install 1
}

# packages_install_review LABEL NAME... is the same decision without
# --noconfirm, so pacman still shows its own summary and waits for a person.
packages_install_review() {
    local label=$1
    shift
    packages_classify "$@" || return 1
    packages_report "$label"
    if [[ $(packages_needed_count) -eq 0 ]]; then
        return 0
    fi
    _packages_pacman_install 0
}

# packages_aur_install LABEL RUN_AS NAME... installs AUR targets through yay as
# an unprivileged user. yay is handed --needed for the same reason pacman is,
# and --answerclean/--answerdiff (yay(8):258, :264) so a package that has never
# been built here cannot stall on a prompt nobody is reading.
packages_aur_install() {
    local label=$1 run_as=$2
    shift 2
    aur_classify "$@" || return 1
    aur_report "$label"
    if ((${#PACKAGES_MISSING[@]} == 0)); then
        return 0
    fi
    sudo -u "$run_as" yay -S --noconfirm --needed \
        --answerclean None --answerdiff None "${PACKAGES_MISSING[@]}"
}
