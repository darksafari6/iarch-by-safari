#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# The audio keys: two volume steps, two mutes and the output switch, all through wpctl.
#
# Usage: scripts/iarch-audio.sh {up,down,mute,mic-mute,sink-next}
#
# Why wpctl
# ---------
# `data/keybinds.default.json` used to bind the two XF86 volume keys to `pamixer -i 5`
# and `pamixer -d 5`, and no step of install.sh installs pamixer: the name appears
# nowhere in the package arrays, so on a machine this repository built the keys were
# dead and the only thing that said so was a shell's "command not found". wpctl is the
# control CLI of WirePlumber, the PipeWire session manager this session already expects
# -- scripts/iarch-healthcheck.sh asks whether `wireplumber.service` is active and warns
# when it is not -- and install.sh now installs the package that provides it.
#
# Every spelling below is read out of wpctl's own manual rather than remembered
# (wpctl(1), https://man.archlinux.org/man/wpctl.1, WirePlumber 0.5.19 as Arch packages
# it):
#
#   * `set-volume ID VOL[%][-|+] [-p|--pid] [-l LIMIT|--limit LIMIT]`, where `VOL%+`
#     increases by a percentage and `VOL%-` decreases by one, and `-l LIMIT` limits the
#     final volume to below a floating-point value in which 1.0 is 100%. The limit is
#     why a held key cannot walk the volume into amplification: the manual's own NOTES
#     say values may exceed 1.0 to amplify, so an unlimited step repeated by the
#     compositor's `repeating` flag would keep going past 100%.
#   * `set-mute ID 1|0|toggle`, with the manual's example being exactly
#     `wpctl set-mute @DEFAULT_SINK@ toggle`.
#   * `@DEFAULT_AUDIO_SINK@` and `@DEFAULT_AUDIO_SOURCE@` from SPECIAL IDENTIFIERS: the
#     current default playback device and the current default capture device, resolved
#     at runtime to node ids, which is what lets one key work on whichever device is
#     default instead of on an id that changes every boot.
#   * `list audio sinks`, whose output is tab-separated object ID, name, media
#     type/object type and a `*` marker on the current default, and `set-default ID`,
#     which makes a sink the default for new streams and is remembered across restarts
#     in WirePlumber's own `default-nodes` state file. `sink-next` is those two and
#     nothing else: read the list, find the star, hand the following id to set-default.
#
# The exit codes are the manual's EXIT STATUS section, and they are passed through
# rather than flattened: 0 is success, 1 a general error, 2 "could not connect to
# PipeWire" and 3 a command-specific error such as an object that was not found. A
# caller that cannot tell "no sound server" from "no such device" cannot say anything
# useful, so this script adds a sentence for 2 and 3 and keeps the number.
#
# What has not happened: none of it has been run against a PipeWire session. There is no
# audio device, no WirePlumber and no wpctl in the sandbox this was written in, so the
# flags are a reading of the manual and the behaviour is unobserved. docs/UNVERIFIED.md
# carries that as KB-07.
set -euo pipefail

STEP='5%'
LIMIT='1.0'
SINK='@DEFAULT_AUDIO_SINK@'
SOURCE='@DEFAULT_AUDIO_SOURCE@'

usage() {
    printf 'Usage: %s {up,down,mute,mic-mute,sink-next}\n' "$0" >&2
}

# One place that turns wpctl's own exit status into a sentence, because the codes are
# documented and a key press has no terminal to explain them in.
run_wpctl() {
    local status=0
    wpctl "$@" || status=$?
    case "$status" in
        0) ;;
        2) printf 'Error: wpctl could not connect to PipeWire (exit 2), so nothing was changed.\n' >&2 ;;
        3) printf 'Error: wpctl found no such node (exit 3) for: %s\n' "$*" >&2 ;;
        *) printf 'Error: wpctl refused `%s` (exit %d).\n' "$*" "$status" >&2 ;;
    esac
    return "$status"
}

# The default sink's id and the ids around it, out of `wpctl list audio sinks`. The
# manual says the marker is a `*` in its own tab-separated field, so the star is looked
# for field by field rather than anywhere in the line: a sink whose *name* contains an
# asterisk would otherwise look like the default.
sink_rows() {
    wpctl list audio sinks | awk -F'\t' '
        {
            id = $1
            gsub(/[^0-9]/, "", id)
            if (id == "") next
            star = 0
            for (field = 2; field <= NF; field++) {
                if ($field ~ /\*/) star = 1
            }
            print id, star
        }'
}

sink_next() {
    local rows=() ids=() stars=() index current=-1 next listing status=0
    listing=$(sink_rows) || status=$?
    if [ "$status" -ne 0 ]; then
        printf 'Error: wpctl could not list the audio sinks (exit %d), so there is nothing to switch to.\n' \
            "$status" >&2
        return "$status"
    fi
    mapfile -t rows <<<"$listing"
    for row in "${rows[@]}"; do
        [ -n "$row" ] || continue
        ids+=("${row%% *}")
        stars+=("${row##* }")
    done
    if [ "${#ids[@]}" -eq 0 ]; then
        printf 'Error: wpctl lists no audio sink at all, so there is no output to switch to.\n' >&2
        return 3
    fi
    if [ "${#ids[@]}" -eq 1 ]; then
        printf 'There is one audio sink (node %s), so there is nothing to switch to.\n' "${ids[0]}" >&2
        return 0
    fi
    for index in "${!ids[@]}"; do
        if [ "${stars[$index]}" = "1" ] && [ "$current" -lt 0 ]; then
            current="$index"
        fi
    done
    # No star means WirePlumber has no default to move on from, so the switch starts at
    # the first sink and says that it guessed.
    if [ "$current" -lt 0 ]; then
        printf 'Warning: no sink is marked as the default, so switching from the first one listed.\n' >&2
        current=0
    fi
    next=$(( (current + 1) % ${#ids[@]} ))
    printf 'Default audio sink: node %s -> node %s\n' "${ids[$current]}" "${ids[$next]}" >&2
    run_wpctl set-default "${ids[$next]}"
}

if ! command -v wpctl >/dev/null 2>&1; then
    printf 'Error: wpctl is not on PATH, so there is no audio to control. It is provided by the\n' >&2
    printf 'wireplumber package, which install.sh installs; see docs/UNVERIFIED.md KB-07.\n' >&2
    exit 127
fi

case "${1:-}" in
    up)        run_wpctl set-volume "$SINK" "${STEP}+" -l "$LIMIT" ;;
    down)      run_wpctl set-volume "$SINK" "${STEP}-" -l "$LIMIT" ;;
    mute)      run_wpctl set-mute "$SINK" toggle ;;
    mic-mute)  run_wpctl set-mute "$SOURCE" toggle ;;
    sink-next) sink_next ;;
    *)
        usage
        exit 2
        ;;
esac
