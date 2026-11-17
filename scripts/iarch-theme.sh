#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Public launcher for the existing iarch-theme CLI.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/theme.py"
if [[ ! -f "$cli" ]]; then
    printf "Error: %s is missing; re-link iArch commands from the repository checkout.\n" "$cli" >&2
    exit 70
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf "Error: python3 is not on PATH.\n" >&2
    exit 127
fi
exec python3 "$cli" "$@"
