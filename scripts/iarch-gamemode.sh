#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Run the iArch by Safari game mode switch, which is what Super+Ctrl+G calls.
#
# Usage: scripts/iarch-gamemode.sh {status,on,toggle,off}
#            [--config-home DIR] [--no-reload] [--dry-run] [--json] [--forget]
#
# `data/keybinds.default.json` binds `SUPER + CTRL + G` to the command `iarch-gamemode`,
# and a bind that names a program nothing provides is a key that does nothing. This is the
# launcher that makes the name real, and scripts/iarch-link-cli.sh is what puts it on PATH
# under that name.
#
# This is the one launcher a key calls whose command writes files: game mode re-renders the
# glass, animation and GTK payloads at the performance intensity, rotates the backups it
# replaces and then asks for one reload. That is why the exit status has to reach the caller
# untouched -- a wrapper that swallowed a failure here would leave a session half-rendered
# and reporting success -- and why the switch itself verifies the reload or rolls back.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/iarch_gamemode.py"

if [ ! -f "$cli" ]; then
    printf 'Error: %s is missing, so this launcher is not in the repository it came from.\n' \
        "$cli" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so game mode cannot be switched.\n' >&2
    exit 127
fi

exec python3 "$cli" "$@"
