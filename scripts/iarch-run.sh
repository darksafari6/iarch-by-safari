#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# A run prompt: pick a command out of everything on PATH, and run the one you picked.
#
# Usage: scripts/iarch-run.sh [--limit N]
#
# What it is made of
# ------------------
# The picker is the shell's own. `noctalia dmenu` is a stdin/stdout drop-in for dmenu at
# noctalia v5.4.1: it "reads newline-separated candidates from stdin, asks the running
# shell to present them in the launcher, and prints the selected line to stdout (exit 0)",
# and "cancel (Esc / panel closed) prints nothing and exits 1", with `-p <prompt>` an
# optional label (src/launcher/dmenu_cli.h). It reaches the shell over a dedicated Unix
# socket at $XDG_RUNTIME_DIR/noctalia-dmenu-$WAYLAND_DISPLAY.sock
# (src/launcher/dmenu_socket_path.cpp:8-19), which the shell binds at startup and which is
# simply absent when it could not be created -- "dmenu stays unavailable; the shell is
# otherwise unaffected" (src/launcher/dmenu_ipc.h:13-17). So this script looks for that
# socket before it tries anything, and says which of the two environment variables is
# missing when it is not there, because that is the whole of the failure.
#
# The candidates are every command on PATH (`compgen -c`, a bash builtin, so nothing has to
# be installed to list them), with the commands this prompt has run before offered first.
# Offering the whole of PATH is also what makes the prompt usable for a command the history
# does not have yet: the shell's launcher providers are an app list, an emoji list, a
# calculator, a window list, a wallpaper list, a session list and config-driven dmenu
# entries (src/launcher/*_provider.cpp), and not one of them runs a shell command, so there
# is no "run" mode to open with `panel-open launcher` -- the candidates have to come from
# here.
#
# What it will not do
# -------------------
# It runs only a line the picker printed, and only after the picker exited 0. Nothing typed
# is executed unless the picker returned it, and a cancel returns nothing and exits 1, which
# this script reports as a cancel rather than as a failure. Whether noctalia's dmenu echoes
# text that is not among the candidates -- real dmenu does -- was not observed here, and it
# does not matter to the safety of this script either way: an answer that is not a line it
# offered is still a line the shell's own picker returned, and the picker is the thing being
# trusted, not the typing.
#
# History is kept in the state directory configstore.state_dir() names, most recent first,
# deduplicated and capped, because a run prompt with no memory makes you type the whole of
# a long command every time. It is a plain text file of command lines and nothing reads it
# but this script.
#
# Exit status: 0 when a command was run, 1 when the picker was cancelled or the command
# failed, 2 on a usage error, 127 when there is no socket and no picker to use.
#
# What has not happened: no prompt has opened. There is no shell, no Wayland display and no
# $XDG_RUNTIME_DIR socket here, so the contract is read out of the shell's own source and
# the behaviour is unobserved. docs/UNVERIFIED.md carries that as KB-10.
set -euo pipefail

HISTORY_LIMIT=50
CANDIDATE_LIMIT=4000

usage() {
    printf 'Usage: %s [--limit N]\n' "$0" >&2
}

state_dir() {
    local override=${IARCH_STATE_DIR:-}
    if [ -n "$override" ] && [ "${override#/}" != "$override" ]; then
        printf '%s\n' "$override"
        return 0
    fi
    printf '%s\n' "${HOME:-/tmp}/.local/state/iarch"
}

history_file() {
    printf '%s\n' "$(state_dir)/run-history"
}

# The socket the shell binds for `noctalia dmenu`, spelled the way
# src/launcher/dmenu_socket_path.cpp spells it, and the reason it is checked rather than
# left to the command failing: the two environment variables it is built from are the two
# things a person can actually fix.
dmenu_socket() {
    local runtime=${XDG_RUNTIME_DIR:-} display=${WAYLAND_DISPLAY:-}
    if [ -z "$runtime" ]; then
        printf 'Error: XDG_RUNTIME_DIR is not set, so the shell'"'"'s dmenu socket has no\n' >&2
        printf 'directory to live in (src/launcher/dmenu_socket_path.cpp:8-11).\n' >&2
        return 1
    fi
    if [ -z "$display" ]; then
        printf 'Error: WAYLAND_DISPLAY is not set, so the shell'"'"'s dmenu socket has no name\n' >&2
        printf '(src/launcher/dmenu_socket_path.cpp:13-16). This is not a Wayland session.\n' >&2
        return 1
    fi
    printf '%s\n' "$runtime/noctalia-dmenu-$display.sock"
}

history_read() {
    local file
    file=$(history_file)
    if [ -f "$file" ]; then
        head -n "$HISTORY_LIMIT" -- "$file" 2>/dev/null || true
    fi
}

history_add() {
    local line=$1 file dir
    file=$(history_file)
    dir=$(dirname -- "$file")
    mkdir -p -- "$dir"
    # Most recent first, one entry per command, capped: the file is read back as the top of
    # the candidate list, so an uncapped file would eventually be the whole list.
    {
        printf '%s\n' "$line"
        history_read | grep -Fxv -- "$line" || true
    } | head -n "$HISTORY_LIMIT" >"$file.tmp"
    mv -f -- "$file.tmp" "$file"
}

candidates() {
    # History first, then every command on PATH, deduplicated in that order so a command
    # you ran last week is offered at the top rather than in the middle of the alphabet.
    {
        history_read
        compgen -c || true
    } | awk 'NF && !seen[$0]++' | head -n "$CANDIDATE_LIMIT"
}

if [ "${1:-}" = "--limit" ]; then
    if [ -z "${2:-}" ] || ! [[ ${2:-} =~ ^[0-9]+$ ]]; then
        printf 'Error: --limit needs a number of candidates.\n' >&2
        usage
        exit 2
    fi
    CANDIDATE_LIMIT=$2
elif [ "$#" -gt 0 ]; then
    usage
    exit 2
fi

if ! command -v noctalia >/dev/null 2>&1; then
    printf 'Error: noctalia is not on PATH, so there is no picker to ask. The shell provides\n' >&2
    printf 'one (`noctalia dmenu`, src/launcher/dmenu_cli.h) and this repository installs no\n' >&2
    printf 'other; see docs/UNVERIFIED.md KB-10.\n' >&2
    exit 127
fi

socket=$(dmenu_socket) || exit 127
if [ ! -S "$socket" ]; then
    printf 'Error: %s is not a socket, so the running shell is not offering its dmenu\n' "$socket" >&2
    printf 'interface. It binds one at startup and leaves it unbound when it cannot\n' >&2
    printf '(src/launcher/dmenu_ipc.h:20-23), which needs a shell of v5.4.1 or newer.\n' >&2
    exit 127
fi

selection=$(candidates | noctalia dmenu -p 'Run') || {
    printf 'Cancelled: the picker closed with no selection.\n' >&2
    exit 1
}

if [ -z "$selection" ]; then
    printf 'Cancelled: the picker returned nothing.\n' >&2
    exit 1
fi

history_add "$selection"
printf 'Running: %s\n' "$selection" >&2

# The picker's own line, run by a shell rather than exec'd directly, because a run prompt
# takes a command line and not only a program name: `git -C /tmp status` is one candidate
# and three words, and splitting it here would guess at quoting the person already did.
if ! bash -c -- "$selection"; then
    printf 'Error: `%s` exited non-zero.\n' "$selection" >&2
    exit 1
fi
