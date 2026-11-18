#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# The two clipboard keys: clear the history behind a question, and show the last entry.
#
# Usage: scripts/iarch-clipboard.sh {clear,show}
#
# Why this is a script and not two binds
# --------------------------------------
# The shell has three clipboard verbs and a key can only use two of them. `clipboard-copy`
# takes text (src/cli/schema_msg.h:435 and kMsgClipboardCopyPositionals), so a bind would
# have to carry the text it copies and would copy the same thing forever; it is recorded in
# data/design/noctalia-ipc.json and deliberately not sent. `clipboard-clear` (:433) takes
# nothing and erases the history the panel behind SUPER + Y keeps, which is the one verb in
# that record a key press can lose something with. `clipboard-text` (:437) prints, and a
# bind has no stdout to print to -- a key that ran it would look exactly like a key that
# does nothing.
#
# So the two that a key can want both need a step in between, and this is that step:
#
#   * `clear` puts the shell's own picker in front of the erase and sends `clipboard-clear`
#     only on an answer the picker returned. That is the same shape
#     iarch/cli/iarch_keybinds.py's confirmation rule enforces for a session ending -- bind
#     the menu, not the action -- applied to a smaller loss. The rule itself does not reach
#     this verb, because `destructive_reason` is about a session or a machine ending and a
#     clipboard is neither, and a rule that only covers the big losses would leave this one
#     to whoever noticed it first.
#   * `show` reads the most recent entry and hands it to `notification-show` (:653-660), so
#     the answer lands somewhere a key press can put it: a card the shell draws. It is the
#     cheap way to see the last thing copied without opening the panel and hunting in it.
#
# The picker is the shell's own, for the reason scripts/iarch-run.sh gives at length:
# `noctalia dmenu` reads newline-separated candidates from stdin, asks the running shell to
# present them in the launcher, prints the selected line to stdout and exits 0, and a cancel
# (Esc, panel closed) prints nothing and exits 1 (src/launcher/dmenu_cli.h). It reaches the
# shell over a dedicated Unix socket at
# $XDG_RUNTIME_DIR/noctalia-dmenu-$WAYLAND_DISPLAY.sock
# (src/launcher/dmenu_socket_path.cpp:8-19) which the shell binds at startup and simply
# leaves unbound when it could not be created -- "dmenu stays unavailable; the shell is
# otherwise unaffected" (src/launcher/dmenu_ipc.h:13-17). `clear` looks for that socket
# before it asks anything and says which of the two variables is missing when it is not
# there, because that is the whole of the failure and the person pressing the key is the
# only one who can fix it. `show` does not need the socket: it sends two `msg` verbs, which
# go over the main IPC.
#
# One line, and only one
# ----------------------
# The main IPC is synchronous and line-capped, one connection per invocation, which is why
# `show` sends the first line of what `clipboard-text` printed and says when it dropped the
# rest. A multi-line entry is common -- a copied command, a paragraph -- and a card that
# swallowed it whole would be a card the shell may not have been able to parse. Truncating
# to a line is the honest half of that: the card shows the beginning of what was copied and
# the stderr line says there was more.
#
# Exit status: 0 when the answer landed (including the answer "no, keep it"), 1 when the
# picker was cancelled or the shell refused a verb, 2 on a usage error, and 127 when
# noctalia is missing or its dmenu socket is not there. The 127 is the code the other
# launchers this repository ships use for a program that is not installed, and matching it
# matters because a keybind's exit status is the only report a person gets: 1 says something
# was asked and said no, 127 says nothing was there to ask.
#
# What has not happened: neither half has been run against a shell. There is no compositor,
# no shell and no display here, so no picker was ever drawn, no history was ever cleared and
# no card was ever read. Every spelling below was read out of noctalia v5.4.1's own source
# and recorded in data/design/noctalia-ipc.json, which is what `iarch-keybinds check`
# validates a noctalia action against. docs/UNVERIFIED.md carries the gap as KB-13.
set -euo pipefail

usage() {
    printf 'Usage: %s {clear,show}\n' "$0" >&2
    printf '  clear  empty the clipboard history, after the shell picker asks\n' >&2
    printf '  show   report the most recent clipboard entry as a notification\n' >&2
}

# The socket the shell binds for `noctalia dmenu`, spelled the way
# src/launcher/dmenu_socket_path.cpp spells it, and checked rather than left to the command
# failing: the two environment variables it is built from are the two things a person can
# actually fix, and a socket that is absent is not an error the verb can report.
dmenu_socket() {
    local runtime=${XDG_RUNTIME_DIR:-} display=${WAYLAND_DISPLAY:-}
    if [ -z "$runtime" ]; then
        printf 'Error: XDG_RUNTIME_DIR is not set, so the shell dmenu socket has no\n' >&2
        printf 'directory to live in (src/launcher/dmenu_socket_path.cpp:8-11).\n' >&2
        return 127
    fi
    if [ -z "$display" ]; then
        printf 'Error: WAYLAND_DISPLAY is not set, so the shell dmenu socket has no name\n' >&2
        printf '(src/launcher/dmenu_socket_path.cpp:13-16). This is not a Wayland session.\n' >&2
        return 127
    fi
    printf '%s\n' "$runtime/noctalia-dmenu-$display.sock"
}

# The two candidates, one of which is the answer that erases. Wording matters here: the
# picker prints the line it was given, and this script compares the answer to the same
# literal, so the destructive choice is spelled out and is not the first line offered.
CLEAR_YES='Yes, clear the clipboard history'
CLEAR_NO='No, keep it'

clear_history() {
    local socket selection
    socket=$(dmenu_socket) || return 127
    if [ ! -S "$socket" ]; then
        printf 'Error: %s is not a socket, so the running shell is not offering its dmenu\n' \
            "$socket" >&2
        printf 'interface. It binds one at startup and leaves it unbound when it cannot\n' >&2
        printf '(src/launcher/dmenu_ipc.h:13-17), which needs a shell of v5.4.1 or newer.\n' >&2
        return 127
    fi

    if ! selection=$(printf '%s\n%s\n' "$CLEAR_NO" "$CLEAR_YES" \
                     | noctalia dmenu -p 'Clear the clipboard history?'); then
        printf 'Cancelled: the picker closed with no selection, so nothing was cleared.\n' >&2
        return 1
    fi
    if [ -z "$selection" ]; then
        printf 'Cancelled: the picker returned nothing, so nothing was cleared.\n' >&2
        return 1
    fi
    if [ "$selection" != "$CLEAR_YES" ]; then
        # An answer that is not the erasing one is an answer to keep the history. It is not
        # treated as a failure, and it is not treated as a yes either: only the literal this
        # script offered can authorise the verb.
        printf 'Keeping the clipboard history: the picker returned %s\n' "$selection" >&2
        return 0
    fi

    if ! noctalia msg clipboard-clear; then
        printf 'Error: the shell refused clipboard-clear, so the history is as it was.\n' >&2
        return 1
    fi
    printf 'Clipboard history cleared.\n' >&2
}

show_latest() {
    local text first rest
    if ! text=$(noctalia msg clipboard-text); then
        printf 'Error: the shell refused clipboard-text, so there is nothing to show.\n' >&2
        return 1
    fi
    if [ -z "$text" ]; then
        printf 'The clipboard history has no text entry to show.\n' >&2
        return 0
    fi

    first=${text%%$'\n'*}
    if [ "${#text}" -gt "${#first}" ]; then
        printf 'Note: the entry runs to more than one line (%d characters in all); the card\n' \
            "${#text}" >&2
        printf 'carries the first line, because the shell IPC is line-capped.\n' >&2
    fi

    if ! noctalia msg notification-show 'Clipboard' "$first"; then
        printf 'Error: the shell refused notification-show, so the entry was read and\n' >&2
        printf 'nowhere reported. It was not changed.\n' >&2
        return 1
    fi
}

# Usage is answered before the shell is looked for, so `--help` works on a machine that has
# neither, and a missing argument is a usage error rather than a report about noctalia.
case "${1:-}" in
    clear|show) ;;
    -h|--help)
        usage
        exit 0
        ;;
    "")
        usage
        exit 2
        ;;
    *)
        printf 'Error: unknown action: %s\n' "$1" >&2
        usage
        exit 2
        ;;
esac

if ! command -v noctalia >/dev/null 2>&1; then
    printf 'Error: noctalia is not on PATH, so there is no clipboard to ask and no picker\n' >&2
    printf 'to ask with. The shell provides both (`noctalia msg clipboard-text`,\n' >&2
    printf 'src/cli/schema_msg.h:437, and `noctalia dmenu`, src/launcher/dmenu_cli.h) and\n' >&2
    printf 'this repository installs no other; see docs/UNVERIFIED.md KB-13.\n' >&2
    exit 127
fi

case "${1:-}" in
    clear) clear_history ;;
    show)  show_latest ;;
esac
