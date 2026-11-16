#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# The two reload keys: the running session, and this repository's own configuration.
#
# Usage: scripts/iarch-reload.sh {session,config}
#
# `session` is the half data/keybinds.default.json binds: session.reload on SUPER + U,
# described in the record as "Reload the session: the shell's configuration and the
# compositor's", which is the cell the A to Z table in data/design/keybinds.json allocates
# to the letter U. It asks both halves of the desktop to re-read what they already have:
#
#   * `noctalia msg config-reload` makes the shell re-read config.toml. The verb is
#     recorded in data/design/noctalia-ipc.json from noctalia v5.4.1
#     src/cli/schema_msg.h:472, and iarch/cli/theme.py already sends it after a render,
#     because a set that is not reloaded is a change nothing has read yet.
#   * `hyprctl reload` makes the compositor re-require its Lua configuration, which is
#     where .config/hypr/generated/keybinds.lua and every other generated file is read
#     again. It is the same call iarch/cli/theme.py:111 makes and the same one the
#     recovery bind in .config/hypr/keybind.lua ends with.
#
# The shell is asked first and the compositor second, and both answers are reported
# rather than the first failure short-circuiting the rest: a compositor reload that
# re-requires a broken generated file is exactly the case the recovery combo exists for,
# and a script that stopped at the first refusal would leave the shell unreloaded and say
# nothing about which half failed.
#
# Exit status: 0 when both halves answered, 1 when either half refused or had to be
# skipped because its program is missing, 2 on a usage error, 70 when this script is not
# inside the repository it came from (it needs iarch/cli to render anything), and 127 when
# *neither* noctalia nor hyprctl is on PATH or python3 is missing. The 127 is the code the
# other seven launchers this pass added use for a program that is not installed, and it is
# worth matching because a keybind's exit status is the only report a person gets: 1 says
# "something was asked and said no", 127 says "nothing was there to ask". A machine with
# one half installed is a 1, and the warning names the half that was skipped.
#
# `config` has no key and it is not a reload at all in the compositor's sense: it
# re-renders every surface this repository generates from ~/.config/iarch/settings.json --
# the glass, the animations, the GTK sheets, the keybinds' own generated file through
# iarch-keybinds -- and then asks for the reloads above. That is `iarch-theme apply` with
# no preset, which keeps the colour preset and the intensity the settings already name. It
# is the second half of this script rather than a cell in the table because iArch's
# configuration is not a file the compositor reads: it is the input to the generators, so
# "reload my configuration" means "run them again", and SUPER + U already means the other
# thing. A terminal is where this one belongs, beside `iarch-theme apply` itself.
#
# What has not happened: neither reload has been watched. There is no compositor and no
# shell here, so both halves are commands this repository already calls elsewhere and the
# behaviour is unobserved. docs/UNVERIFIED.md carries that as KB-08.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"

usage() {
    printf 'Usage: %s {session,config}\n' "$0" >&2
}

py() {
    PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" python3 "$@"
}

reload_session() {
    local failed=0

    if ! command -v noctalia >/dev/null 2>&1 && ! command -v hyprctl >/dev/null 2>&1; then
        # Neither half of the desktop is installed, which is a different fact from
        # one half refusing: there was nothing to ask, so this is the code the other
        # launchers use for a missing program rather than the one for a refusal.
        printf 'Error: neither noctalia nor hyprctl is on PATH, so there is no session to reload.\n' >&2
        printf 'Neither is a package this repository installs: install.sh configures a shell and\n' >&2
        printf 'a compositor it expects to find, and scripts/iarch-healthcheck.sh is what reports\n' >&2
        printf 'whether they are there. See docs/UNVERIFIED.md KB-08.\n' >&2
        return 127
    fi

    if command -v noctalia >/dev/null 2>&1; then
        if noctalia msg config-reload; then
            printf 'shell: config-reload answered\n' >&2
        else
            printf 'Error: the shell refused config-reload.\n' >&2
            failed=1
        fi
    else
        printf 'Warning: noctalia is not on PATH, so the shell half was skipped.\n' >&2
        failed=1
    fi

    if command -v hyprctl >/dev/null 2>&1; then
        if hyprctl reload; then
            printf 'compositor: reloaded\n' >&2
        else
            printf 'Error: hyprctl reload was refused. If the session now has no keys,\n' >&2
            printf 'the recovery combination is CTRL + ALT + R.\n' >&2
            failed=1
        fi
    else
        printf 'Warning: hyprctl is not on PATH, so the compositor half was skipped.\n' >&2
        failed=1
    fi

    return "$failed"
}

if [ ! -d "$root/iarch/cli" ]; then
    printf 'Error: %s has no iarch/cli, so this script is not in the repository it came from.\n' \
        "$root" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so the generators cannot be run.\n' >&2
    exit 127
fi

case "${1:-}" in
    session) reload_session ;;
    config)  exec py "$root/iarch/cli/theme.py" apply ;;
    *)
        usage
        exit 2
        ;;
esac
