#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Run the iArch by Safari focus mode switch, which is what Super+Ctrl+F calls.
#
# Usage: scripts/iarch-focus.sh {status,on,toggle,off} [--no-caffeine] [--dry-run] [--json]
#
# `data/keybinds.default.json` binds `SUPER + CTRL + F` to the command `iarch-focus`, and
# a bind that names a program nothing provides is a key that does nothing. This is the
# launcher that makes the name real, and scripts/iarch-link-cli.sh is what puts it on
# PATH under that name. Until the A-Z table in data/design/keybinds.json allocated the
# cell, focus mode was a command only: docs/ROADMAP.md Part 3 records "no key binds
# either mode" and left both to the shortcut system.
#
# Thin and exec'ing, for the same reason as scripts/iarch-cheatsheet.sh: the exit status
# has to reach the caller untouched. The switch exits non-zero when the shell refused one
# of the things it was asked to change and rolled the rest back, and a wrapper that
# swallowed that would report a focus session that is not focused.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/iarch_focus.py"

if [ ! -f "$cli" ]; then
    printf 'Error: %s is missing, so this launcher is not in the repository it came from.\n' \
        "$cli" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so focus mode cannot be switched.\n' >&2
    exit 127
fi

exec python3 "$cli" "$@"
