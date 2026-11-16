#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Turn the gaps between windows off and on again, without a reload and without a file.
#
# Usage: scripts/iarch-gaps.sh {on,off,toggle,status}
#
# The mechanism is the compositor's own configuration API and the same one
# iarch/cli/iarch_focus.py uses for its dim: `hyprctl eval 'hl.config({ ... })'`. That
# idiom is recorded with its citations in that file's module docstring -- hl.config walks
# the table into dotted keys, refuses a key it does not know with `unknown config key`,
# refuses a value the leaf's parser rejects, and on success schedules exactly the refresh
# that leaf declares (Hyprland v0.57.2, src/config/lua/bindings/
# LuaBindingsConfigRules.cpp:943-991). A failure comes back as a reply starting with
# `error:` *and* exit 7, which is what makes it checkable rather than fire-and-forget, and
# both are checked here.
#
# The three leaves are `general:gaps_in`, `general:gaps_out` and `general:float_gaps`,
# all three of them listed among the keys this project renders in data/design/tokens.json
# (`hyprland` leaf list) and documented there as MS<CssGap>, which take an integer or a
# table of top/right/bottom/left -- and a float such as 10.0 is a config error rather than
# a rounded integer, so the values are emitted as integers and never as decimals.
#
# The values are not invented here: `on` is the layout the tokens already ship
# (data/design/tokens.json -> layout: gaps_in 6, gaps_out 12, float_gaps 8, and the
# intensities do not override them), and `off` is zero for all three. Reading them out of
# the tokens is what keeps this from becoming a second source of truth for a number the
# renderer already owns.
#
# Two honest limits:
#
#   * `hl.config` writes and does not read. The only compositor reads this repository has
#     verified are `hyprctl configerrors` and `hyprctl -j animations`
#     (iarch/cli/iarch_anim.py), and neither reports a config leaf, so `toggle` cannot ask
#     the compositor what the gaps are. It remembers what it last did in a one-word file
#     under the state directory configstore.state_dir() names -- $IARCH_STATE_DIR when that
#     is set and absolute, else ~/.local/state/iarch -- and `status` prints that word and
#     says it is remembered. With no file yet, `toggle` assumes the gaps are on, because
#     the session the tokens render has them on, and turns them off.
#   * The change is runtime state and dies with the next reload: `hyprctl reload`,
#     `iarch-theme apply` or a relogin re-renders theme.lua and puts the tokens' gaps
#     back. That is the same caveat iarch-focus documents for its dim, and the remembered
#     word is not corrected when it happens, so `status` can be wrong after a reload.
#
# Exit status: 0 when the compositor answered `ok`, 1 when it refused, 2 on a usage error,
# 127 when hyprctl or python3 is missing.
#
# What has not happened: no gap has closed. There is no compositor here, so the leaf names
# and the value forms are read out of the tokens and the eval idiom out of iarch_focus.py,
# and the behaviour is unobserved. docs/UNVERIFIED.md carries that as KB-08.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"

usage() {
    printf 'Usage: %s {on,off,toggle,status}\n' "$0" >&2
}

# The state directory configstore.state_dir() names, resolved the same way
# .config/hypr/keybind.lua resolves its own paths: an override that is set and absolute
# wins, and anything else degrades to the default under $HOME rather than failing.
state_file() {
    local override=${IARCH_STATE_DIR:-}
    if [ -n "$override" ] && [ "${override#/}" != "$override" ]; then
        printf '%s\n' "$override/gaps"
        return 0
    fi
    printf '%s\n' "${HOME:-/tmp}/.local/state/iarch/gaps"
}

# The three gap values for a wanted state, as `gaps_in gaps_out float_gaps`, read out of
# the tokens so this file carries no number of its own.
gap_values() {
    local wanted=$1
    python3 - "$root" "$wanted" <<'PY'
import json
import sys
from pathlib import Path

root, wanted = Path(sys.argv[1]), sys.argv[2]
tokens = json.loads((root / "data" / "design" / "tokens.json").read_text(encoding="utf-8"))
layout = tokens.get("layout") or {}
if wanted == "off":
    values = (0, 0, 0)
else:
    values = tuple(int(layout[key]) for key in ("gaps_in", "gaps_out", "float_gaps"))
# Integers on purpose: these leaves are MS<CssGap>, and the tokens record that a float is
# a config error rather than a rounded integer.
print(" ".join(str(value) for value in values))
PY
}

apply_state() {
    local wanted=$1 values gaps_in gaps_out float_gaps lua reply status=0 target
    values=$(gap_values "$wanted") || {
        printf 'Error: the gap values in data/design/tokens.json could not be read.\n' >&2
        return 1
    }
    read -r gaps_in gaps_out float_gaps <<<"$values"
    lua="hl.config({ general = { gaps_in = ${gaps_in}, gaps_out = ${gaps_out}, float_gaps = ${float_gaps} } })"
    reply=$(hyprctl eval "$lua" 2>&1) || status=$?
    if [ "$status" -ne 0 ] || [ "${reply#error:}" != "$reply" ]; then
        printf 'Error: the compositor refused `%s`: %s\n' "$lua" "${reply:-no reply}" >&2
        return 1
    fi
    target=$(state_file)
    mkdir -p -- "$(dirname -- "$target")"
    printf '%s\n' "$wanted" >"$target"
    printf 'gaps %s (gaps_in %s, gaps_out %s, float_gaps %s); compositor answered %s\n' \
        "$wanted" "$gaps_in" "$gaps_out" "$float_gaps" "${reply:-ok}" >&2
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

if ! command -v hyprctl >/dev/null 2>&1; then
    printf 'Error: hyprctl is not on PATH, so there is no compositor to ask.\n' >&2
    exit 127
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so the token values cannot be read.\n' >&2
    exit 127
fi

case "${1:-}" in
    on)  apply_state on ;;
    off) apply_state off ;;
    toggle)
        now=$(remembered)
        if [ "$now" = "unknown" ]; then
            printf 'Nothing is remembered about the gaps, and the compositor cannot be asked,\n' >&2
            printf 'so this assumes the session the tokens render -- gaps on -- and turns them off.\n' >&2
            now="on"
        fi
        if [ "$now" = "on" ]; then apply_state off; else apply_state on; fi
        ;;
    status)
        now=$(remembered)
        printf 'gaps: %s\n' "$now"
        if [ "$now" = "unknown" ]; then
            printf 'That is a remembered word and not a reading: hl.config writes and cannot\n' >&2
            printf 'read a leaf back, so run `%s on` or `%s off` to make it definite.\n' "$0" "$0" >&2
        fi
        ;;
    *)
        usage
        exit 2
        ;;
esac
