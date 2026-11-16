#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Zen mode: hide everything the shell draws over the session, and bring it all back.
#
# Usage: scripts/iarch-zen.sh {on,off,toggle,status}
#
# Zen mode is not a new mechanism and it invents no state of its own: it is the shell's
# three hide verbs sent together, and the three show verbs sent together. All six are
# commands of noctalia v5.4.1's own IPC table (src/cli/schema_msg.h, every one of them
# taking no argument at all):
#
#   bar-hide  (:358)  "Hide one or all bars and release their layout gaps"
#   bar-show  (:375)  "Show one or all bars"
#   dock-hide (:512)  "Hide the dock (persists override)"
#   dock-show (:514)  "Show the dock (persists override)"
#   desktop-widgets-hide (:479) and desktop-widgets-show (:489), both "runtime only; does
#   not change the saved setting"
#
# Sending the three together is the whole of the feature, and it is why this is a script
# rather than a binding: one bind carries one action, and a zen mode that hid the bar but
# left the dock and the desktop widgets is not zen. `bar-hide` releasing the layout gaps
# matters too -- a hidden bar that still reserves its strip leaves a band of nothing at the
# top of every window, which is the opposite of the point.
#
# The one thing this script does keep is which way it last went, and it says so rather than
# pretending to know. None of the six verbs reports the state it left behind, and the
# shell's own dump (`status`, :790, "Print current state as JSON") is not a read this
# repository has verified field by field, so `toggle` remembers `on` or `off` in a one-word
# file under the state directory configstore.state_dir() names -- $IARCH_STATE_DIR when
# that is set and absolute, else ~/.local/state/iarch. With no file yet, `toggle` assumes
# the session is showing its chrome, because that is the state the shipped configuration
# renders, and hides it. `on` and `off` need no memory at all: they send the three verbs
# that match the word, so a remembered state that has drifted is corrected by either.
#
# A drift it cannot correct: `dock-hide` persists its override and `desktop-widgets-hide`
# does not, so after a shell restart the dock stays hidden and the widgets come back. That
# is the two verbs' own documented difference, not a bug here, and `off` puts both back.
#
# Exit status: 0 when the shell answered every verb it was sent, 1 when one refused, 2 on a
# usage error, 127 when noctalia is missing.
#
# What has not happened: nothing has disappeared. There is no shell and no display here, so
# the six verbs are read out of the command table and the behaviour is unobserved.
# docs/UNVERIFIED.md carries that as KB-08.
set -euo pipefail

usage() {
    printf 'Usage: %s {on,off,toggle,status}\n' "$0" >&2
}

# The state directory configstore.state_dir() names, resolved the way
# .config/hypr/keybind.lua resolves its own paths: an override that is set and absolute
# wins, and anything else degrades to the default under $HOME rather than failing.
state_file() {
    local override=${IARCH_STATE_DIR:-}
    if [ -n "$override" ] && [ "${override#/}" != "$override" ]; then
        printf '%s\n' "$override/zen"
        return 0
    fi
    printf '%s\n' "${HOME:-/tmp}/.local/state/iarch/zen"
}

remembered() {
    local target word=""
    target=$(state_file)
    if [ -f "$target" ]; then
        word=$(head -n1 -- "$target" 2>/dev/null || true)
    fi
    case "$word" in
        on | off) printf '%s\n' "$word" ;;
        *) printf '%s\n' 'unknown' ;;
    esac
}

remember() {
    local target=$1
    mkdir -p -- "$(dirname -- "$target")"
    printf '%s\n' "$2" >"$target"
}

# Send every verb named, and report the ones the shell refused instead of stopping at the
# first: a zen mode that hid the bar and then gave up on the dock is worse than one that
# hid both and said the widgets refused.
send_all() {
    local wanted=$1 verb failed=0
    shift
    for verb in "$@"; do
        if noctalia msg "$verb" >&2; then
            printf '  %s answered\n' "$verb" >&2
        else
            printf 'Error: the shell refused `%s`.\n' "$verb" >&2
            failed=1
        fi
    done
    if [ "$failed" -eq 0 ]; then
        remember "$(state_file)" "$wanted"
        printf 'zen %s\n' "$wanted" >&2
    else
        printf 'zen %s was only partly applied; the remembered state was left alone.\n' \
            "$wanted" >&2
    fi
    return "$failed"
}

zen_on() {
    send_all on bar-hide dock-hide desktop-widgets-hide
}

zen_off() {
    send_all off bar-show dock-show desktop-widgets-show
}

if ! command -v noctalia >/dev/null 2>&1; then
    printf 'Error: noctalia is not on PATH, so there is no shell chrome to hide.\n' >&2
    exit 127
fi

case "${1:-}" in
    on)  zen_on ;;
    off) zen_off ;;
    toggle)
        now=$(remembered)
        if [ "$now" = "unknown" ]; then
            printf 'Nothing is remembered about zen mode and none of the six verbs reports a\n' >&2
            printf 'state, so this assumes the chrome the shipped configuration renders is\n' >&2
            printf 'showing, and hides it.\n' >&2
            now="off"
        fi
        if [ "$now" = "on" ]; then zen_off; else zen_on; fi
        ;;
    status)
        now=$(remembered)
        printf 'zen: %s\n' "$now"
        printf 'That is what this script last did, not what the shell is drawing: none of the\n' >&2
        printf 'six verbs reports its state. `%s on` or `%s off` is definite either way.\n' \
            "$0" "$0" >&2
        ;;
    *)
        usage
        exit 2
        ;;
esac
