#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Run the iArch by Safari keyboard-map CLI.
#
# Usage: scripts/iarch-keybinds.sh [subcommand] [options]
#        scripts/iarch-keybinds.sh check
#        scripts/iarch-keybinds.sh reset --all --yes
#
# This is the launcher that gives the CLI a name. `iarch-keybinds` is what the recovery
# bind in .config/hypr/keybind.lua looks for on PATH, what data/keybinds.default.json
# names in the recovery entry's command, and what the documentation tells a person to
# type -- but the repository has no console_scripts entry for it, because the CLI is one
# file that finds its own package (iarch/cli/iarch_keybinds.py puts the repository root
# on sys.path itself, which is why there is no PYTHONPATH juggling here). So the name is
# a wrapper, and this is the wrapper.
#
# It is thin and it execs, for one reason: the exit status has to pass through untouched.
# 0 is a clean map, 1 is a refusal or a failed write, 2 is bad input. The recovery bind,
# the installer and CI all read that status, and a wrapper that swallowed it would turn a
# refused change into a silent success -- which is the one failure mode this CLI exists
# to prevent.
#
# scripts/iarch-link-cli.sh is what puts this file on PATH under the name above.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/iarch_keybinds.py"

if [ ! -f "$cli" ]; then
    printf 'Error: %s is missing, so this launcher is not in the repository it came from.\n' \
        "$cli" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so the keyboard-map CLI cannot run.\n' >&2
    exit 127
fi

exec python3 "$cli" "$@"
