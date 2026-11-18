#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Public launcher for iarch-shell-switch.
#
# Purpose: run the engine switch CLI from a linked command name, so a shortcut, a
#          terminal or the settings application all reach the same code.
# Inputs:  every argument it is given, unchanged; the checkout it was linked from.
# Outputs: the CLI's own report and exit status (0 switched, 1 refused or rolled
#          back, 2 usage), 70 when the CLI is missing, 127 when python3 is not.
# Dependencies: bash, python3, iarch/cli/iarch_shell_switch.py in the same checkout.
set -euo pipefail
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/iarch_shell_switch.py"
if [[ ! -f "$cli" ]]; then
    printf "Error: %s is missing; re-link iArch commands from the repository checkout.\n" "$cli" >&2
    exit 70
fi
if ! command -v python3 >/dev/null 2>&1; then
    printf "Error: python3 is not on PATH.\n" >&2
    exit 127
fi
exec python3 "$cli" "$@"
