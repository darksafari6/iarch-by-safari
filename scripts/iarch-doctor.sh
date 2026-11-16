#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Run the iArch by Safari diagnostics CLI. No key calls it, and the header below says why.
#
# Usage: scripts/iarch-doctor.sh {notify-test,dnd} [...]
#        scripts/iarch-doctor.sh dnd {on,off,toggle,status} [--json]
#
# The CLI has always been here -- iarch/cli/iarch_doctor.py, with a `dnd` subcommand that
# reads and sets Do Not Disturb through the shell's own verbs and a `notify-test` that
# sends one notification to prove the path -- but it had no name on PATH, and the docs use
# that name: `iarch-doctor` appears in iarch/cli/README.md and in docs/ARCHITECTURE.md,
# docs/MOTION.md, docs/ROADMAP.md and docs/UNVERIFIED.md as a command to type or as the
# place a later half of the doctor is scheduled. scripts/iarch-link-cli.sh is
# what puts it on PATH under that name, and tests/test_cli_launchers.py fails when a
# script in scripts/ is not linked, so the name and the file cannot drift apart.
#
# No key binds it, and that is a decision rather than an omission. data/design/keybinds.json
# reserves both cells a Do Not Disturb switch would land on -- SUPER + CTRL + D and, by the
# same argument, the layer's C for caffeine -- because iarch-focus on reads the flag with
# notification-dnd-status, saves what it read and puts it back on off, so a key that flipped
# the flag underneath a running focus session would break the restore and leave the session
# silent after focus mode ended. Focus mode is SUPER + CTRL + F and it owns both switches.
# So this launcher exists for a terminal and for the docs, not for a bind.
#
# Thin and exec'ing, for the same reason as scripts/iarch-focus.sh: the exit status has to
# reach the caller untouched. `dnd` exits non-zero when the shell refused the change or
# could not be asked at all, and a wrapper that swallowed that would report a quiet
# session that is still interruptible.
#
# Exit status: whatever iarch/cli/iarch_doctor.py exits with, untouched -- 0 when the
# subcommand ran, non-zero when the shell refused or could not be reached -- plus 70 when
# this launcher is not inside the repository it came from and 127 when python3 is missing.
# `notify-test` is the one subcommand that exits 0 with nothing working, and it says so in
# its own report rather than in its status: a machine with no notification daemon is a
# finding to print, not a failure of the command that printed it.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"
cli="$root/iarch/cli/iarch_doctor.py"

if [ ! -f "$cli" ]; then
    printf 'Error: %s is missing, so this launcher is not in the repository it came from.\n' \
        "$cli" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so the diagnostics CLI cannot run.\n' >&2
    exit 127
fi

exec python3 "$cli" "$@"
