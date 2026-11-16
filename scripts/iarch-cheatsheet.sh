#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Run the iArch by Safari shortcut overlay, which is what Super+H calls.
#
# Usage: scripts/iarch-cheatsheet.sh [--query TERMS] [--text] [--json] [--plan]
#
# `data/keybinds.default.json` binds `SUPER + H` to the command `iarch-cheatsheet`, and
# a bind that names a program nothing provides is a key that does nothing. This is the
# launcher that makes the name real, and scripts/iarch-link-cli.sh is what puts it on
# PATH under that name.
#
# Thin and exec'ing, for the same reason as scripts/iarch-keybinds.sh: the exit status
# has to reach the caller untouched. The overlay exits non-zero when it could not appear
# anywhere -- no terminal, no notification daemon -- and a wrapper that swallowed that
# would turn a dead key into a silent one.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/iarch_cheatsheet.py"

if [ ! -f "$cli" ]; then
    printf 'Error: %s is missing, so this launcher is not in the repository it came from.\n' \
        "$cli" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so the shortcut overlay cannot run.\n' >&2
    exit 127
fi

exec python3 "$cli" "$@"
