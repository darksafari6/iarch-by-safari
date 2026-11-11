#!/usr/bin/env bash
# Manual QA walk-through for the iArch by Safari motion system.
#
# Read-only unless asked: by default this checks what a shell can check and
# prints what only a person can see, with the expected result beside each step.
# Nothing here installs a package, edits a file or changes a service.
#
#   ./iarch/cli/qa_motion.sh                  check what is checkable, list the rest
#   ./iarch/cli/qa_motion.sh --walk           pause at each visual step for y/n
#   ./iarch/cli/qa_motion.sh --apply-switches also run the preset round-trip
#   IARCH_VERBOSE=1 ./iarch/cli/qa_motion.sh  show the commands being run
#
# A check that needs a running session, a Lua compiler or a display is reported as
# SKIP rather than FAIL: the absence of a binary means the result is unverified,
# not that the result is wrong. The same rule the CLIs follow.
#
# The expected results below are the ones docs/MOTION.md documents. If a step here
# and a sentence there disagree, one of them is wrong and both should be fixed.
set -uo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
# shellcheck source=/dev/null
. "$repo/lib/iarch-common.sh" || exit 1

PY=$(command -v python3 || true)
CONFIG_HOME=${CONFIG_HOME:-$HOME/.config}
ANIMATIONS_LUA="$CONFIG_HOME/hypr/generated/animations.lua"
GLASS_LUA="$CONFIG_HOME/hypr/generated/glass.lua"

PASSED=0
FAILED=0
SKIPPED=0
PENDING=0
WALK=0
APPLY_SWITCHES=0

pass()   { printf '%s[ OK ]%s %s\n' "$IARCH_C_GREEN" "$IARCH_C_RESET" "$*"; PASSED=$((PASSED + 1)); }
skip()   { printf '%s[SKIP]%s %s\n' "$IARCH_C_DIM" "$IARCH_C_RESET" "$*"; SKIPPED=$((SKIPPED + 1)); }
fail()   { printf '%s[FAIL]%s %s\n' "$IARCH_C_RED" "$IARCH_C_RESET" "$*" >&2; FAILED=$((FAILED + 1)); }

# A visual step. In --walk mode it waits for an answer; otherwise it is printed as
# something still to be looked at, because a script cannot see a window arrive.
manual() {
    local step=$1 expect=$2 answer
    printf '%s[LOOK]%s %s\n' "$IARCH_C_YELLOW" "$IARCH_C_RESET" "$step"
    printf '       expected: %s\n' "$expect"
    if [[ $WALK == 1 ]]; then
        printf '       did you see that? [y/n] '
        read -r answer || answer=''
        case ${answer,,} in
            y | yes) pass "confirmed: $step" ;;
            *)       fail "not seen: $step" ;;
        esac
    else
        PENDING=$((PENDING + 1))
    fi
}

# Run a check whose result is the exit status of a command.
expect_ok() {
    local label=$1
    shift
    iarch::detail "running: $*"
    if "$@" >/dev/null 2>&1; then
        pass "$label"
    else
        fail "$label (command: $*)"
    fi
}

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case $1 in
        --walk) WALK=1 ;;
        --apply-switches) APPLY_SWITCHES=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            printf 'unknown argument: %s\n\n' "$1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

# Every check below runs through python3, because the renderers and the test
# suites are Python. Without it the whole first half is unverified rather than
# failed: reporting FAIL for a missing interpreter would tell a person their
# motion system is broken when all that is broken is this script's toolchain.
if [[ -z $PY ]]; then
    skip "python3 is not installed; nothing below it can be checked"
    iarch::warn "install python3 and rerun; the visual steps below still apply"
else
    iarch::heading "Repository state: does what is committed still match its source?"
    expect_ok "the committed animations.lua matches a fresh render" \
        "$PY" "$repo/iarch/cli/gen_animations_lua.py" --check
    expect_ok "the committed glass.lua matches a fresh render" \
        "$PY" "$repo/iarch/cli/gen_glass_lua.py" --check
    expect_ok "the committed GTK sheets match a fresh render" \
        "$PY" "$repo/iarch/cli/render_gtk_css.py" --check --repo

    iarch::heading "Design data: are the presets inside what Hyprland accepts?"
    expect_ok "every preset validates against its schema" \
        "$PY" -m unittest -q tests.test_animation_presets
    expect_ok "the generator refuses an impossible preset" \
        "$PY" -m unittest -q tests.test_animations_lua
fi

iarch::heading "Live files: is what the session will read the shape it should be?"
if [[ -f $ANIMATIONS_LUA ]]; then
    pass "found $ANIMATIONS_LUA"
    if command -v luac >/dev/null 2>&1; then
        expect_ok "animations.lua parses as Lua" luac -p "$ANIMATIONS_LUA"
    else
        skip "luac is not installed; animations.lua was not parsed"
    fi
    if grep -q 'iarch-' "$ANIMATIONS_LUA"; then
        pass "animations.lua registers iArch's own curves"
    else
        fail "animations.lua registers no iarch- curve; it is not a render of a preset"
    fi
else
    skip "$ANIMATIONS_LUA is not there yet; run iarch-theme apply or iarch-anim set"
fi

if [[ -f $GLASS_LUA ]]; then
    if grep -q 'glow = {' "$GLASS_LUA"; then
        pass "glass.lua carries the focus glow block"
    else
        fail "glass.lua has no glow block; the focus cue would be the border alone"
    fi
else
    skip "$GLASS_LUA is not there yet; run iarch-theme apply"
fi

# Every transition a GTK widget wears must answer inside 120-180ms, or be 0ms
# because the user asked for less motion. A duration outside both is a regression.
for version in 4.0 3.0; do
    sheet="$CONFIG_HOME/gtk-$version/gtk.css"
    if [[ ! -f $sheet ]]; then
        skip "gtk-$version/gtk.css is not there yet; run iarch-theme apply"
        continue
    fi
    if [[ -n $PY ]]; then
        # `if out=$(...)` rather than assigning and then testing $?: a helper call
        # between the two would silently overwrite the status being tested.
        if out=$("$PY" - "$sheet" <<'PYCHECK'
import re
import sys

values = [int(v) for v in re.findall(r"transition-duration:\s*(\d+)ms",
                                     open(sys.argv[1], encoding="utf-8").read())]
bad = sorted({v for v in values if v != 0 and not 120 <= v <= 180})
print(f"{len(values)} transition(s); outside the band: {bad if bad else 'none'}")
sys.exit(1 if bad or not values else 0)
PYCHECK
        ); then
            pass "gtk-$version: $out"
        else
            fail "gtk-$version: $out"
        fi
    else
        skip "python3 is not installed; the gtk-$version durations were not measured"
    fi
done

iarch::heading "Compositor: does Hyprland agree with what was written?"
if command -v hyprctl >/dev/null 2>&1 && [[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
    errors=$(hyprctl configerrors 2>/dev/null)
    if [[ -z $errors ]]; then
        pass "hyprctl configerrors is empty"
    else
        fail "hyprctl configerrors reports: $(printf '%s' "$errors" | head -3 | tr '\n' ';')"
    fi
    live=$(hyprctl animations 2>/dev/null)
    if printf '%s' "$live" | grep -q 'iarch-'; then
        pass "the compositor is animating with iArch's curves"
    else
        fail "the compositor reports no iarch- curve; it has not loaded the render"
    fi
    manual "open and close a window" \
        "it arrives over roughly a fifth of a second and leaves faster than it arrived"
    manual "switch workspace" "the two workspaces slide past each other, not crossfade"
    manual "focus a window and look at its edge" \
        "the accent border changes and a faint glow fades in with it, rather than snapping"
else
    skip "not inside a Hyprland session (no hyprctl or no HYPRLAND_INSTANCE_SIGNATURE)"
    skip "the visual steps need a session; run this script from inside one"
fi

iarch::heading "Toolkit: does a control answer the pointer?"
manual "hover a button in a GTK application" \
    "its fill lightens within about an eighth of a second; nothing moves or scales"
manual "press and hold that button" \
    "it sinks by 2% under the pointer in GTK 4, and darkens in GTK 3, which has no transform"
manual "tab to the next control" "the focus ring fades in; it does not appear at once"

iarch::heading "Reduce motion: does the accessibility switch reach every surface?"
if [[ -n $PY ]]; then
    state=$("$PY" - "$repo" <<'PYSTATE'
import json
import os
import sys

root = sys.argv[1]
path = os.path.join(os.environ.get("IARCH_CONFIG_DIR",
                                   os.path.expanduser("~/.config/iarch")), "settings.json")
sys.path.insert(0, root)
try:
    recorded = json.load(open(path, encoding="utf-8")).get("animation", {})
except (OSError, ValueError):
    recorded = {}
print(recorded.get("preset", "unset"), recorded.get("reduce_motion", False))
PYSTATE
    )
    iarch::detail "settings.json animation: $state"
    pass "readable animation state: $state"
else
    skip "python3 is not installed; the recorded animation state was not read"
fi
manual "run 'iarch-anim reduce-motion on', then open a window" \
    "nothing slides and nothing overshoots; only short fades remain, each under 90ms"
manual "with reduce-motion still on, hover a GTK button" \
    "the fill changes at once, with no fade, because GTK renders every duration as 0ms"
manual "run 'iarch-anim reduce-motion off'" \
    "the preset you had chosen comes back, including its overshoot if it had one"

iarch::heading "Notifications: does the shell's own daemon answer, and does it move?"
# Read-only on purpose. --dry-run builds every probe and reports what the session
# says without putting one toast on screen; sending them is the person's step
# below, because a check that covers the screen unasked is one nobody runs twice.
if [[ -n $PY ]]; then
    report=$("$PY" "$repo/iarch/cli/iarch_doctor.py" notify-test --dry-run --json 2>/dev/null)
    summary=""
    if [[ -n $report ]]; then
        summary=$(printf '%s' "$report" | "$PY" -c '
import json
import sys

try:
    report = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
print(report["verdict"], report["do_not_disturb"], report["competing_daemons_searched"],
      ",".join(report["competing_daemons"]) or "-", len(report["probes"]))
' 2>/dev/null)
    fi
    if [[ -z $summary ]]; then
        fail "iarch-doctor notify-test --dry-run gave no readable report"
        notify_blocked=1
    else
        read -r verdict dnd searched others probes <<<"$summary"
        notify_blocked=0
        case $verdict in
            dry-run) pass "iarch-doctor built $probes probe(s) without sending one" ;;
            not-run)
                skip "noctalia is not installed or not answering, so no probe could be built"
                notify_blocked=1
                ;;
            blocked)
                skip "the probes are suppressed rather than broken; nothing would be visible"
                notify_blocked=1
                ;;
            *)     fail "iarch-doctor notify-test --dry-run reported: $verdict" ;;
        esac
        case $dnd in
            True)
                skip "Do Not Disturb is on: toasts are suppressed, so the steps below stay invisible"
                iarch::detail "run 'python3 iarch/cli/iarch_doctor.py dnd off' to see them"
                notify_blocked=1
                ;;
            False) pass "Do Not Disturb is off" ;;
            *)     skip "the Do Not Disturb state could not be read" ;;
        esac
        if [[ $others != "-" ]]; then
            iarch::warn "another notification daemon is running: $others"
            iarch::detail "whichever claimed the bus first keeps it; nothing was stopped"
        elif [[ $searched == True ]]; then
            pass "no other notification daemon in the process table"
        else
            skip "the process table was not searched, so no claim is made about other daemons"
        fi
    fi
    if [[ ${notify_blocked:-0} == 0 ]]; then
        manual "run 'python3 iarch/cli/iarch_doctor.py notify-test'" \
            "three cards stack in the top-right corner, each revealing over 200ms; hovering one pauses its countdown bar, and the critical one keeps a red edge until it is dismissed"
        manual "apply the performance intensity, then run notify-test again" \
            "the same cards appear without sliding, because [shell.animation] enabled = false reaches the toast animations too (docs/UNVERIFIED.md NOT-02)"
    fi
else
    skip "python3 is not installed; the notification path was not checked"
fi

if [[ $APPLY_SWITCHES == 1 ]]; then
    iarch::heading "Round-trip: does every preset apply and come back cleanly?"
    if [[ -n $PY ]]; then
        recorded_preset=$("$PY" "$repo/iarch/cli/iarch_anim.py" current --json 2>/dev/null |
            "$PY" -c 'import json,sys; print(json.load(sys.stdin)["state"]["preset"])' 2>/dev/null)
        for preset in smooth snappy bouncy minimal off; do
            expect_ok "iarch-anim set $preset" \
                "$PY" "$repo/iarch/cli/iarch_anim.py" set "$preset"
        done
        if [[ -n ${recorded_preset:-} ]]; then
            expect_ok "restored the preset you had ($recorded_preset)" \
                "$PY" "$repo/iarch/cli/iarch_anim.py" set "$recorded_preset"
        else
            skip "could not read the preset to restore; leaving the last one applied"
        fi
    else
        skip "python3 is not installed; the preset round-trip was not run"
    fi
    manual "watch the round-trip above as it happens" \
        "each switch changes how windows arrive, and 'off' makes them appear at once"
else
    iarch::detail "pass --apply-switches to run the bouncy/off round-trip and restore your preset"
fi

iarch::heading "Result"
printf 'passed %s   failed %s   skipped %s   still to look at %s\n' \
    "$PASSED" "$FAILED" "$SKIPPED" "$PENDING"
if [[ $FAILED -gt 0 ]]; then
    iarch::error "motion QA failed; docs/MOTION.md lists what each check means"
    exit 1
fi
if [[ $PENDING -gt 0 && $WALK == 0 ]]; then
    iarch::warn "$PENDING visual step(s) were printed but not confirmed; rerun with --walk"
fi
exit 0
