#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# Three cycles: animation preset, blur strength, theme mode.
#
# All three have a key. `theme` is what data/keybinds.default.json binds as
# appearance.theme-mode on SUPER + CTRL + T, `blur` as appearance.glass on SUPER + SHIFT + G
# and `animation` as appearance.animation on SUPER + CTRL + A: three cells the A to Z table
# in data/design/keybinds.json allocates to them. They are here because the two CLIs they
# drive -- iarch-anim and iarch-theme -- each own a list of presets and neither offers a
# "next" of its own, so a cycle is the thing that was missing, and a launcher that only did
# the one cycle a key asks for would leave the other two reachable only by typing a preset
# name. Two of the three were unbound when this script was written, and this header said a
# second key for one action was a second place to keep in sync; the fourth pass of that
# table filled every cell it had left and took both. What makes the argument wrong rather
# than merely lost is that neither cycle keeps a list: each reads the state from the CLI
# that owns it and writes it back there, so a key and a terminal stepping the same cycle
# agree without either one remembering where the other got to. The cost of the blur half is
# still the one this header named -- an intensity carries rounding, shadow, opacity and the
# dim values with it -- and there is no blur-only leaf to step instead.
#
# Usage: scripts/iarch-cycle.sh {animation,blur,theme}
#
# A cycle is a read, a step and a write, and each of the three reads its own state from
# the thing that owns it rather than keeping a list here:
#
#   * `animation` asks `iarch-anim list --json` for the presets in their own order and
#     for the one that is active (iarch/cli/iarch_anim.py cmd_list, which builds the list
#     with anim.preset_names and marks the active one from state), steps to the next name
#     and wraps, then hands that name to `iarch-anim set`. The order is the CLI's, so a
#     preset added to data/design/animations/ is in the cycle the moment it exists.
#   * `blur` steps the glass *intensity*, because the intensity is the only switch this
#     repository has that changes blur: data/design/tokens.json records the four
#     (crystal, frosted, soft, performance) and the leaves they set include
#     decoration:blur:popups and decoration:blur:special. It is honest about the cost --
#     an intensity also carries rounding, shadow, opacity and the dim values, so cycling
#     blur cycles the whole glass profile with it, and there is no blur-only leaf to
#     cycle instead. The step goes to `iarch-theme apply --intensity`, which renders
#     every surface, writes the setting and asks for one reload, so nothing here has to
#     remember a value.
#   * `theme` asks the shell what mode it is in with `theme-mode-get`, steps
#     dark -> light -> auto -> dark, and sends `theme-mode-set` with the one it landed on.
#     The three words are the recorded choices of the verb (noctalia v5.4.1,
#     src/cli/schema_msg.h, data/design/noctalia-ipc.json). It deliberately does not send
#     `theme-mode-toggle`, for the reason that verb's own record gives: a toggle cannot
#     say which mode it landed on and it drops auto, which is the mode most people run.
#     It then writes the same choice into iArch's settings, because
#     iarch/cli/render_noctalia.py renders theme.mode from them -- a mode changed only in
#     the running shell is put back by the next `iarch-theme apply`, and a key that is
#     silently reverted is a key nobody can trust.
#
# Exit status: 0 when the cycle landed, 1 when the tool or the shell refused, 2 on a
# usage error, 127 when a program this needs is missing.
#
# What has not happened: no cycle has been watched. There is no compositor, no shell and
# no display here, so the reads and writes are exercised against the CLIs' own code and
# the verbs' own record and not against a session. docs/UNVERIFIED.md carries that as
# KB-08.
set -euo pipefail

here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname -- "$here")"

usage() {
    printf 'Usage: %s {animation,blur,theme}\n' "$0" >&2
}

need() {
    if ! command -v "$1" >/dev/null 2>&1; then
        printf 'Error: %s is not on PATH, so this cycle has nothing to step.\n' "$1" >&2
        exit 127
    fi
}

# The repository's own Python, found the way scripts/iarch-settings.sh finds it: the
# package is not installed, it is in the checkout, so PYTHONPATH is how it is reached and
# an existing PYTHONPATH is kept rather than dropped.
py() {
    PYTHONPATH="$root${PYTHONPATH:+:$PYTHONPATH}" python3 "$@"
}

cycle_animation() {
    local report next
    report=$(py "$root/iarch/cli/iarch_anim.py" list --json) || {
        printf 'Error: iarch-anim could not report its presets, so there is nothing to cycle.\n' >&2
        return 1
    }
    next=$(printf '%s\n' "$report" | py -c '
import json, sys

report = json.load(sys.stdin)
names = [preset["name"] for preset in report.get("presets") or [] if preset.get("name")]
current = (report.get("state") or {}).get("preset")
if not names:
    raise SystemExit("iarch-anim reported no presets")
if current in names:
    print(names[(names.index(current) + 1) % len(names)])
else:
    print(names[0])
') || {
        printf 'Error: the preset list iarch-anim reported could not be stepped.\n' >&2
        return 1
    }
    printf 'Animation preset: %s\n' "$next" >&2
    py "$root/iarch/cli/iarch_anim.py" set "$next"
}

cycle_blur() {
    local current next
    current=$(py -c '
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

settings = configstore.load("settings", root)
print((settings.get("theme") or {}).get("intensity") or "")
' "$root")
    next=$(py -c '
import json, sys
from pathlib import Path

root = Path(sys.argv[1])
tokens = json.loads((root / "data" / "design" / "tokens.json").read_text(encoding="utf-8"))
names = list((tokens.get("intensities") or {}).keys())
if not names:
    raise SystemExit("data/design/tokens.json records no intensities")
current = sys.argv[2]
if current in names:
    print(names[(names.index(current) + 1) % len(names)])
else:
    print(names[0])
' "$root" "$current") || {
        printf 'Error: the intensities in data/design/tokens.json could not be stepped.\n' >&2
        return 1
    }
    printf 'Glass intensity (blur strength): %s -> %s\n' "${current:-unset}" "$next" >&2
    py "$root/iarch/cli/theme.py" apply --intensity "$next"
}

cycle_theme() {
    need noctalia
    py -c '
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

# The order is the choice list the verb itself declares -- dark, light, auto --
# recorded in data/design/noctalia-ipc.json from noctalia v5.4.1
# src/cli/schema_msg.h.
ORDER = ("dark", "light", "auto")


def send(*argv):
    import subprocess

    done = subprocess.run(["noctalia", "msg", *argv], capture_output=True, text=True, check=False)
    return done.returncode, (done.stdout or "").strip(), (done.stderr or "").strip()

settings = configstore.load("settings", root)
theme = settings.get("theme") or {}
stored = str(theme.get("colour_mode") or "").strip().lower()

status, out, err = send("theme-mode-get")
live = out.strip().lower() if status == 0 else ""
current = live if live in ORDER else (stored if stored in ORDER else "")
if not current:
    print("The shell answered neither a mode this script knows nor is a mode stored in "
          "settings, so the cycle starts at dark.", file=sys.stderr)
    current = ORDER[0]
nxt = ORDER[(ORDER.index(current) + 1) % len(ORDER)]

status, out, err = send("theme-mode-set", nxt)
if status != 0:
    print(f"Error: the shell refused theme-mode-set {nxt}: {err or out or 'no reply'}",
          file=sys.stderr)
    raise SystemExit(1)

# Written as well as sent, because iarch/cli/render_noctalia.py renders theme.mode from
# these settings: a mode only the running shell knows is put back by the next render.
theme["colour_mode"] = nxt
settings["theme"] = theme
configstore.save("settings", settings)
print(f"Theme mode: {current} -> {nxt} (sent to the shell and written to settings)",
      file=sys.stderr)
' "$root"
}

if [ ! -d "$root/iarch/cli" ]; then
    printf 'Error: %s has no iarch/cli, so this script is not in the repository it came from.\n' \
        "$root" >&2
    exit 70
fi

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Error: python3 is not on PATH, so no cycle can read the state it steps.\n' >&2
    exit 127
fi

case "${1:-}" in
    animation) cycle_animation ;;
    blur)      cycle_blur ;;
    theme)     cycle_theme ;;
    *)
        usage
        exit 2
        ;;
esac
