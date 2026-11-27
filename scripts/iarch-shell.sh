#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Isolated preview launcher; the unfinished session shell remains guarded.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
if [[ $# == 1 && "$1" == start ]]; then
    # The switch performs one-engine preflight and still refuses the skeleton.
    export IARCH_SHELL_ROOT="$root"
    exec "$root/scripts/iarch-shell-switch.sh" to dynamic
fi
if [[ $# -ge 1 && "$1" == setup ]]; then
    shift
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Error: python3 is not installed.\n' >&2
        exit 127
    fi
    exec python3 "$root/iarch/cli/shell_setup.py" "$@"
fi
if [[ $# -ge 1 && "$1" == autostart ]]; then
    shift
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Error: python3 is not installed.\n' >&2
        exit 127
    fi
    exec python3 "$root/iarch/cli/shell_autostart.py" "$@"
fi
if [[ $# -ge 1 && "$1" == fix-legacy-icons ]]; then
    shift
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Error: python3 is not installed.\n' >&2
        exit 127
    fi
    exec python3 "$root/iarch/cli/shell_legacy_icons.py" "$@"
fi
if [[ $# -ge 1 && "$1" == quality ]]; then
    shift
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Error: python3 is not installed.\n' >&2
        exit 127
    fi
    exec python3 "$root/iarch/cli/shell_quality.py" "$@"
fi
if [[ $# -ge 1 && "$1" == perf ]]; then
    shift
    if ! command -v python3 >/dev/null 2>&1; then
        printf 'Error: python3 is not installed.\n' >&2
        exit 127
    fi
    exec python3 "$root/iarch/cli/iarch_shell_perf.py" "$@"
fi
if [[ $# != 1 || ( "$1" != gallery && "$1" != preview ) ]]; then
    printf 'Usage: iarch-shell start | setup | gallery | preview | quality [level] | fix-legacy-icons [--write] | perf [--json] | autostart [--write]\nThe session shell is not ready yet.\n' >&2
    exit 2
fi
if ! command -v quickshell >/dev/null 2>&1; then
    printf 'Error: the shell toolkit is not installed.\n' >&2
    exit 127
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not installed.\n' >&2
    exit 127
fi
export IARCH_SHELL_ROOT="$root"
if [[ "$1" == preview ]]; then
    # Explicit developer preview: no switch, no notification server, no reserved
    # compositor space. The QML entry enforces those restrictions as well.
    unset IARCH_ENABLE_NOTIFICATIONS
    exec quickshell --path "$root/iarch/shell/PreviewShell.qml" --no-duplicate
fi
exec quickshell --path "$root/iarch/shell/GalleryShell.qml" --no-duplicate
