#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the lock screen and the idle fallback from the glass design tokens.

Writes two files, both under ``~/.config/hypr/``:

* ``hyprlock.conf`` -- the session-lock surface: a blurred capture of the desktop
  as the background, a frosted card, the password field inside it, a clock above
  and the user's name below. Its blur numbers are the intensity's own
  (``blur_passes``, ``blur_size``, ``noise``, ``contrast``, ``brightness``,
  ``vibrancy`` are Hyprland's ``decoration:blur`` leaves, and hyprlock's manual
  says its blur options are taken from Hyprland), so the lock screen frosts by
  exactly the same recipe as the rest of the session.
* ``hypridle.conf`` -- shipped **unlaunched**. It declares no listeners, so it
  only supplies the two commands a session with no shell still needs: lock on a
  D-Bus lock event, and lock before sleep.

The second file is the interesting one, because the obvious thing to do is wrong.
Hyprland's idle daemon and the shell's own idle system both watch
``ext_idle_notifier_v1``, so running both means two processes racing to lock, dim
and suspend the same session. Noctalia v5.4.1 already owns that surface
(``[idle.behavior.*]`` in ``data/design/noctalia.json``), so this project
configures idle *there* and ships hypridle as a fallback that is not started.
``docs/glass-experience.md`` gives the one line that starts it, for a session
where the shell is not running.

hyprlock is forgiving in the way Noctalia is: an unknown variable is a warning
and the lock screen still appears, so a typo silently ships a setting that does
nothing. Every variable this renderer may emit is recorded in
``data/design/hyprlock.json`` with its documented type, default and enumeration,
and ``validate()`` refuses a render that leaves that record -- including an
animation name outside hyprlock's own tree, which would quietly not animate.

Usage:
    python3 iarch/cli/render_hyprlock.py                      # write into ~/.config/hypr
    python3 iarch/cli/render_hyprlock.py --preset aurora --intensity crystal
    python3 iarch/cli/render_hyprlock.py --print              # hyprlock.conf to stdout
    python3 iarch/cli/render_hyprlock.py --write-repo-default  # refresh .config/hypr
    python3 iarch/cli/render_hyprlock.py --check              # shipped files match a render
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)
from iarch.cli import render_noctalia  # noqa: E402  (shares the token/preset loaders)

SURFACE_PATH = ROOT / "data" / "design" / "hyprlock.json"
ANIMATION_DIR = ROOT / "data" / "design" / "animations"
REPO_LOCK = ROOT / ".config" / "hypr" / "hyprlock.conf"
REPO_IDLE = ROOT / ".config" / "hypr" / "hypridle.conf"

DEFAULT_PRESET = render_noctalia.DEFAULT_PRESET

HyprlockError = render_noctalia.NoctaliaError
load_json = render_noctalia.load_json
load_tokens = render_noctalia.load_tokens
load_preset = render_noctalia.load_preset
resolve_intensity = render_noctalia.resolve_intensity
label = render_noctalia.label

# Geometry the tokens do not decide. A lock screen is one composition, so its
# proportions live here with their reasons rather than in a token file that would
# only ever be read by this renderer.
#
#   card        the frosted panel the password field sits on
#   field       hyprlock's own documented default size, 400x90, kept because the
#               dots are laid out inside it and 400 px is wide enough for a long
#               password to stay readable as dots
#   clock       spacing.xxl below the top edge, at type.sizes.xxl
#   user        spacing.xxl below the field's bottom edge
#   hint        spacing.lg below the user's name, at type.sizes.sm
CARD_WIDTH = 460
CARD_HEIGHT = 170
CARD_OFFSET_Y = 24
FIELD_WIDTH = 400
FIELD_HEIGHT = 90
FIELD_OFFSET_Y = -16
CLOCK_OFFSET_Y = 96
USER_OFFSET_Y = 72
HINT_OFFSET_Y = 104

# hypridle's three commands. `pidof noctalia ||` is the same shape as the lock_cmd
# the hypridle manual's own example uses (`pidof hyprlock || hyprlock`): prefer
# the lock surface that is already running, and only start a second one when it
# is not. Nothing here is a shell function of the user's input, so there is no
# string to escape, and hypridle runs each one through `/bin/sh -c`
# (hypridle src/core/Hypridle.cpp:286-289, identical at v0.1.8 and on main),
# which is what makes the `||` and the quoting below work at all.
IDLE_LOCK_CMD = "pidof noctalia || hyprlock"
IDLE_BEFORE_SLEEP_CMD = "loginctl lock-session"
# Not the hypridle manual's `hyprctl dispatch dpms on`, and the reason is in the
# compositor rather than in the daemon. Hyprland v0.57.2 answers `dispatch X` by
# evaluating `return hl.dispatch(X)` when the config provider is Lua
# (src/ipc/s1/Commands.cpp:1332-1350), and this session's config is Lua, so
# `dpms on` would be handed to the Lua compiler as `hl.dispatch(dpms on)` and
# come back a syntax error. hl.dsp.dpms is the dispatcher that exists
# (src/config/lua/bindings/LuaBindingsDispatchers.cpp:1380) and its action words
# are enable/on, disable/off and toggle, with anything else silently toggling
# (LuaBindingsInternal.cpp:317-325) -- which is why the word is spelled out here
# rather than left to a default. `hyprctl keyword` is not an alternative: no
# keyword command is registered at v0.57.2, and the manual itself says it will
# not work with a Lua config provider (docs/hyprctl.1.rst:36-40).
IDLE_AFTER_SLEEP_CMD = "hyprctl dispatch \"hl.dsp.dpms({ action = 'enable' })\""


# --------------------------------------------------------------- colours


def rgb(hex_color: str) -> Tuple[int, int, int]:
    """``#rrggbb`` to its three channels, refusing anything else."""
    text = hex_color.strip()
    if len(text) != 7 or not text.startswith("#"):
        raise HyprlockError(f"palette colour is not #rrggbb: {hex_color!r}")
    try:
        return tuple(int(text[i:i + 2], 16) for i in (1, 3, 5))  # type: ignore[return-value]
    except ValueError as exc:
        raise HyprlockError(f"palette colour is not #rrggbb: {hex_color!r}") from exc


def rgba(hex_color: str, alpha: float) -> str:
    """The one colour spelling hyprlock's manual uses everywhere.

    Hyprland's own configs also accept 8-digit hex, and the two projects share a
    colour parser, but hyprlock documents ``rgb()``/``rgba()`` and never hex --
    so this converts rather than relying on an undocumented form on the one
    surface where a mistake means an unreadable password field.
    """
    red, green, blue = rgb(hex_color)
    if not 0.0 <= alpha <= 1.0:
        raise HyprlockError(f"alpha is outside 0-1: {alpha!r}")
    return f"rgba({red}, {green}, {blue}, {round(alpha, 2):g})"


def opaque(hex_color: str) -> str:
    red, green, blue = rgb(hex_color)
    return f"rgba({red}, {green}, {blue}, 1.0)"


# --------------------------------------------------------------- motion


def load_preset_animation(preset_name: str) -> Dict[str, Any]:
    path = ANIMATION_DIR / f"{preset_name}.json"
    if not path.is_file():
        raise HyprlockError(f"no animation preset {preset_name!r} in {label(ANIMATION_DIR)}")
    return load_json(path)


def fade_seconds(motion: Dict[str, Any], events: Dict[str, Any], name: str) -> float:
    """A hyprlock animation duration, in seconds, from the preset's own leaf.

    Hyprland's animation tree has ``fadeIn`` and ``fadeOut`` leaves, and so does
    hyprlock's -- the same two names, the same meaning. So the lock screen fades
    at the duration the preset already chose for them (120 ms for smooth, 90 ms
    for minimal, absent for off) instead of a number invented here.

    The tokens' ``speed_multiplier`` is deliberately *not* applied. It scales
    Hyprland's own animations through the generated animation tree, and hyprlock
    has no multiplier to scale: applying it to one duration and not the others
    would make the lock screen disagree with the session it locks.
    """
    event = events.get(name)
    if not isinstance(event, dict) or not event.get("enabled"):
        raise HyprlockError(f"animation preset {motion['preset']!r} has no enabled {name}")
    duration = event.get("duration_ms")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise HyprlockError(f"animation preset {motion['preset']!r} gives {name} no duration")
    return round(float(duration) / 1000.0, 3)


def bezier_line(name: str, curve: Dict[str, Any]) -> str:
    """``bezier = name, x1, y1, x2, y2`` -- or a refusal.

    A spring curve has no four-point bezier form, so naming one here would emit
    a line hyprlock parses and then draws wrongly. The presets that carry a
    spring use it for window motion, never for a fade, so this is a guard rather
    than a limitation anyone will hit.
    """
    if curve.get("type") != "bezier":
        raise HyprlockError(f"curve {name!r} is {curve.get('type')!r}; hyprlock's bezier "
                            "keyword takes four numbers, so a spring cannot be expressed")
    points = curve.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise HyprlockError(f"curve {name!r} does not carry two control points")
    flat = [coordinate for point in points for coordinate in point]
    if len(flat) != 4:
        raise HyprlockError(f"curve {name!r} does not carry four numbers")
    return "bezier = " + ", ".join([name] + [f"{float(value):g}" for value in flat])


# --------------------------------------------------------------- the document


def render_document(tokens: Dict[str, Any], preset: Dict[str, Any], intensity_name: str,
                    surface: Dict[str, Any]) -> Dict[str, Any]:
    """The whole lock screen as data: ``general``/``auth``/``animations`` plus widgets."""
    intensity = tokens["intensities"][intensity_name]
    palette = preset["palette"]
    blur, glass, shadow = intensity["blur"], intensity["glass"], intensity["shadow"]
    motion = intensity["motion"]
    radius, spacing = tokens["radius"], tokens["spacing"]
    font = tokens["font"]
    sizes = font["sizes"]

    animation_preset = load_preset_animation(motion["preset"])
    events = animation_preset["events"]
    curves = animation_preset["curves"]

    doc: Dict[str, Any] = OrderedDict()

    # general ------------------------------------------------------------
    # compositor_fade follows the same switch the rest of the session follows, so
    # a Performance session gets a lock screen that appears and disappears
    # instantly instead of one that still fades while nothing else moves. The
    # manual says hyprlock falls back to its own client-side fade when the
    # compositor does not advertise hyprland_surface_manager_v1, which makes this
    # safe to ask for unconditionally.
    doc["general"] = OrderedDict([
        ("compositor_fade", bool(motion["enabled"])),
        ("fail_timeout", 2000),
        ("hide_cursor", True),
        ("text_trim", True),
    ])

    # auth ---------------------------------------------------------------
    # PAM only. pam:module stays at hyprlock's own default: naming a module
    # would mean asserting that /etc/pam.d/hyprlock exists on the reader's
    # system, and the manual says hyprlock falls back to "su" when it does not.
    doc["auth"] = OrderedDict([("pam:enabled", True)])

    # animations ---------------------------------------------------------
    animations: Dict[str, Any] = OrderedDict([("enabled", bool(motion["enabled"]))])
    lines: List[str] = []
    if motion["enabled"]:
        wanted: List[Tuple[str, str]] = []
        for leaf in ("fadeIn", "fadeOut"):
            event = events.get(leaf)
            if not isinstance(event, dict) or not event.get("enabled"):
                raise HyprlockError(f"animation preset {motion['preset']!r} has no enabled "
                                    f"{leaf}, so there is no honest duration to give hyprlock")
            curve_name = event.get("curve")
            if curve_name not in curves:
                raise HyprlockError(f"animation preset {motion['preset']!r} points {leaf} at "
                                    f"curve {curve_name!r}, which it does not define")
            if curve_name not in [line.split(", ")[0].split(" = ")[1] for line in lines]:
                lines.append(bezier_line(curve_name, curves[curve_name]))
            wanted.append((leaf, curve_name))
        for leaf, curve_name in wanted:
            lines.append(f"animation = {leaf}, 1, {fade_seconds(motion, events, leaf):g}, "
                         f"{curve_name}")
    animations["lines"] = lines
    doc["animations"] = animations

    # background ---------------------------------------------------------
    # path = screenshot captures the desktop when the lock starts and blurs it,
    # which is the whole glass idea: the palette behind the field is the user's
    # own wallpaper, not a colour this project picked. The manual is explicit
    # that a screenshot is a static capture, and that a *live* blurred backdrop
    # needs Hyprland's misc:session_lock_xray and misc:session_lock_blur -- both
    # real v0.57.2 leaves, neither enabled here, because keeping every workspace
    # rendering underneath a lock screen costs compositor work on every idle
    # machine for a difference only a moving window would reveal.
    #
    # color is the fallback the manual describes ("if path is empty or missing,
    # it will use color"), so it is the palette's background at full opacity:
    # readable, and honest about being a fallback rather than a tint that may or
    # may not composite over the capture.
    blurred = bool(blur["enabled"]) and int(blur["passes"]) > 0
    background = OrderedDict([
        ("monitor", ""),
        # With no blur there is no reason to capture the desktop at all: an
        # unblurred screenshot puts a password field over sharp, high-contrast
        # content -- the one background that makes text hardest to read. So the
        # Performance intensity fills with the palette's background instead, and
        # the capture is what the other three get.
        ("path", "screenshot" if blurred else ""),
        ("color", opaque(palette["background"])),
        ("blur_passes", int(blur["passes"])),
        ("blur_size", int(blur["size"])),
        ("noise", float(blur["noise"])),
        ("contrast", float(blur["contrast"])),
        ("brightness", float(blur["brightness"])),
        ("vibrancy", float(blur["vibrancy"])),
        ("zindex", -1),
    ])
    doc["background"] = [background]
    doc["_background_blurred"] = blurred

    # shape: the frosted card --------------------------------------------
    # Only background blurs in hyprlock, so a "frosted card" is a translucent
    # surface colour over an already-blurred capture -- the same trick the
    # shell's own panels use, minus a second blur pass it cannot do.
    card = OrderedDict([
        ("monitor", ""),
        ("size", f"{CARD_WIDTH}, {CARD_HEIGHT}"),
        ("color", rgba(palette["surface"], float(glass["tint_alpha"]))),
        ("rounding", int(radius[radius["panel"]])),
        ("border_size", int(tokens["layout"]["border_size"])),
        ("border_color", rgba(palette["outline_variant"], float(glass["border_alpha"]))),
        ("position", f"0, {CARD_OFFSET_Y}"),
        ("halign", "center"),
        ("valign", "center"),
        ("zindex", 1),
    ])
    if shadow["enabled"]:
        # shadow_boost *multiplies* the shadow's opacity, so the alpha lives here
        # and the colour stays opaque. Putting it in both would square it:
        # rgba(...,0.36) at a boost of 0.36 is a 0.13 shadow, which is not the
        # glass alpha the tokens asked for.
        card["shadow_passes"] = 2
        card["shadow_size"] = 6
        card["shadow_color"] = opaque(palette["shadow"])
        card["shadow_boost"] = round(float(glass["shadow_alpha"]), 2)
    doc["shape"] = [card]

    # input-field --------------------------------------------------------
    # The field's three state colours are the palette's own semantic accents --
    # warning while PAM is being asked, danger when it says no, primary when
    # Caps Lock is on -- which is the same mapping the shell's notification
    # border uses (critical to ColorRole::Error). Nothing is invented: hyprlock
    # documents check_color, fail_color and capslock_color as gradients, and a
    # gradient accepts one colour.
    doc["input-field"] = [OrderedDict([
        ("monitor", ""),
        ("size", f"{FIELD_WIDTH}, {FIELD_HEIGHT}"),
        ("outline_thickness", int(tokens["layout"]["border_size"])),
        ("outer_color", rgba(palette["outline_variant"], float(glass["border_alpha"]))),
        ("inner_color", rgba(palette["surface_variant"], float(glass["tint_alpha_strong"]))),
        ("font_color", opaque(palette["on_surface"])),
        ("font_family", font["ui"]),
        ("rounding", int(radius[radius["input"]])),
        ("dots_size", 0.25),
        ("dots_spacing", 0.15),
        ("dots_center", True),
        # Visible while empty: a lock screen that hides its own field until you
        # start typing gives no affordance at all on a machine with no keyboard
        # backlight.
        ("fade_on_empty", False),
        ("fade_timeout", 2000),
        ("placeholder_text", "<i>Type your password</i>"),
        ("check_color", opaque(palette["accent"]["warning"])),
        ("check_text", "Checking…"),
        ("fail_color", opaque(palette["accent"]["danger"])),
        ("fail_text", "<i>$FAIL <b>($ATTEMPTS)</b></i>"),
        ("capslock_color", opaque(palette["accent"]["primary"])),
        ("position", f"0, {FIELD_OFFSET_Y}"),
        ("halign", "center"),
        ("valign", "center"),
        ("zindex", 2),
    ])]

    # labels -------------------------------------------------------------
    # $TIME and $DESC are hyprlock's own substitutions, so no shell command runs
    # to draw this screen. The manual's cmd[update:N] form would spawn a process
    # on a timer inside the lock surface and hangs the AsyncResourceGatherer if
    # the command never exits; a clock that costs nothing is worth more than one
    # that proves a shell works.
    clock_shadow = bool(shadow["enabled"])
    doc["label"] = [
        OrderedDict([
            ("monitor", ""),
            ("text", "$TIME"),
            ("color", opaque(palette["on_background"])),
            ("font_size", int(sizes["xxl"])),
            ("font_family", font["ui"]),
            ("position", f"0, {CLOCK_OFFSET_Y}"),
            ("halign", "center"),
            ("valign", "top"),
            ("zindex", 3),
            # A shadow behind the clock only: it sits on the unblurred part of
            # the capture, where a light wallpaper would otherwise wash it out.
            ("shadow_passes", 2 if clock_shadow else 0),
            ("shadow_size", 4),
            ("shadow_color", opaque(palette["shadow"])),
            ("shadow_boost", round(float(glass["shadow_alpha"]), 2)),
        ]),
        OrderedDict([
            ("monitor", ""),
            ("text", "$DESC"),
            ("color", opaque(palette["on_surface_variant"])),
            ("font_size", int(sizes["lg"])),
            ("font_family", font["ui"]),
            ("position", f"0, {USER_OFFSET_Y + CARD_OFFSET_Y}"),
            ("halign", "center"),
            ("valign", "center"),
            ("zindex", 3),
        ]),
        OrderedDict([
            ("monitor", ""),
            ("text", "Enter to unlock · Esc clears the field"),
            ("color", rgba(palette["on_surface_variant"], 0.7)),
            ("font_size", int(sizes["sm"])),
            ("font_family", font["ui"]),
            ("position", f"0, {HINT_OFFSET_Y + CARD_OFFSET_Y}"),
            ("halign", "center"),
            ("valign", "center"),
            ("zindex", 3),
        ]),
    ]
    return doc


def render_idle_document(surface: Dict[str, Any]) -> Dict[str, Any]:
    """The unlaunched hypridle fallback: two commands and no timers."""
    return OrderedDict([
        ("general", OrderedDict([
            ("lock_cmd", IDLE_LOCK_CMD),
            ("before_sleep_cmd", IDLE_BEFORE_SLEEP_CMD),
            ("after_sleep_cmd", IDLE_AFTER_SLEEP_CMD),
        ])),
    ])


# --------------------------------------------------------------- validation


def _blocks(surface: Dict[str, Any]) -> Dict[str, Any]:
    """Every recorded block, widgets and sections together, keyed by how it is spelled.

    The three shared groups (positioning, shadowable, clickable) have no block of
    their own in the file, so they are keyed by their recorded name, which no
    widget can collide with. They still have to be reachable here: ``halign`` and
    ``valign`` carry an enumerated vocabulary, and a check that only looked at a
    widget's own keys would let ``halign = middle`` through to a session where
    hyprlock warns and then centres the widget anyway.
    """
    blocks: Dict[str, Any] = {}
    for group in ("sections", "widgets"):
        for name, block in surface[group].items():
            table = block.get("table")
            key = table.split(" {")[0].strip() if table else name
            blocks[key] = block
    return blocks


def _check_value(path: str, spec: Dict[str, Any], value: Any, problems: List[str]) -> None:
    kind = spec["type"]
    if kind == "bool":
        if not isinstance(value, bool):
            problems.append(f"{path}: {value!r} is not a bool")
    elif kind == "int":
        # bool is an int in Python, and `shadow_passes = true` is exactly the
        # mistake a type check that forgets this would wave through.
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{path}: {value!r} is not an int")
    elif kind == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{path}: {value!r} is not a float")
    elif kind in ("string", "color", "gradient", "layoutxy"):
        if not isinstance(value, str):
            problems.append(f"{path}: {value!r} is not a {kind}")
        elif kind in ("color", "gradient") and value:
            # A gradient is one or more colours plus an optional angle, so the
            # check is on the first colour only -- enough to catch a palette hex
            # that never went through rgba().
            first = value.split()[0].rstrip("deg")
            if not (first.startswith("rgb(") or first.startswith("rgba(")):
                problems.append(f"{path}: {value!r} is not an rgb()/rgba() colour")
    else:  # pragma: no cover - the schema fixes the vocabulary
        problems.append(f"{path}: the surface records an unknown type {kind!r}")

    # The enumeration and the range are checked for *every* type, not only for
    # numbers. Most of hyprlock's enumerated variables are strings -- halign,
    # valign, screencopy_mode's cousins -- and a check nested inside the numeric
    # branch would let `halign = middle` through to a session where hyprlock
    # warns and then centres the widget anyway. That is the silent failure this
    # gate exists to prevent.
    if "enum" in spec and value not in spec["enum"]:
        problems.append(f"{path}: {value!r} is not one of "
                        f"{', '.join(str(item) for item in spec['enum'])}")
    if "range" in spec and isinstance(value, (int, float)) and not isinstance(value, bool):
        low, high = spec["range"]
        if not low <= value <= high:
            problems.append(f"{path}: {value} is outside the documented range {low}-{high}")


def _check_repeated(path: str, line: Any, repeated: Dict[str, Any],
                    known: Dict[str, Any]) -> List[str]:
    """Check one ``keyword = a, b, c`` line against the recorded keyword list."""
    problems: List[str] = []
    if not isinstance(line, str) or " = " not in line:
        return [f"{path}: {line!r} is not a `keyword = value` line"]
    keyword, _, rest = line.partition(" = ")
    if keyword not in repeated:
        return [f"{path}: {keyword!r} is not a keyword this block takes "
                f"({', '.join(sorted(repeated))})"]
    # Every repeated keyword in hyprlock is a comma-separated list, and the parts
    # have documented meanings, so each is checked by position against the same
    # type the manual gives the keyword.
    parts = [part.strip() for part in rest.split(",")]
    if keyword == "bezier":
        if len(parts) != 5:
            problems.append(f"{path}: a bezier is NAME, X1, Y1, X2, Y2, got {len(parts)} "
                            "parts")
        for index, part in enumerate(parts[1:], start=1):
            try:
                float(part)
            except ValueError:
                problems.append(f"{path}: bezier component {index} is {part!r}, not a number")
    elif keyword == "animation":
        if len(parts) != 4:
            problems.append(f"{path}: an animation is NAME, ENABLED, SECONDS, BEZIER, got "
                            f"{len(parts)} parts")
    return problems


def validate(doc: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """Refuse a render the recorded surface does not describe.

    hyprlock warns about an unknown variable and keeps going, so nothing here
    would fail on the user's machine: a misspelled ``blur_passses`` is a lock
    screen with no blur and no error. This is the gate that turns that into a
    refusal before a byte is written.
    """
    problems: List[str] = []
    blocks = _blocks(surface)
    doc = {key: value for key, value in doc.items() if not key.startswith("_")}
    positioning = surface["widgets"]["positioning"]["keys"]
    shadowable = surface["widgets"]["shadowable"]["keys"]
    clickable = surface["widgets"]["clickable"]["keys"]

    for name, value in doc.items():
        if name not in blocks:
            problems.append(f"{name}: is not a block hyprlock documents")
            continue
        block = blocks[name]
        known = dict(block["keys"])
        # `repeated` holds the keywords that may appear more than once inside one
        # block (bezier, animation). The document carries them pre-rendered as
        # "lines" because a mapping cannot hold two keys with the same name, so
        # each line is parsed back into its parts and checked like any value.
        repeated = block.get("repeated", {})
        if repeated:
            known["lines"] = {"type": "string"}
        instances = value if isinstance(value, list) else [value]
        if not isinstance(value, list) and name in ("background", "shape", "input-field",
                                                    "label", "image"):
            problems.append(f"{name}: a widget block must be a list, so two of them cannot "
                            "collapse into one")
        for index, instance in enumerate(instances):
            here = name if len(instances) == 1 else f"{name}[{index}]"
            if not isinstance(instance, dict):
                problems.append(f"{here}: is not a block")
                continue
            allowed = set(known) | set(positioning) | (
                set(shadowable) if block.get("shadowable") else set()) | (
                set(clickable) if block.get("clickable") else set())
            for key, item in instance.items():
                if key not in allowed:
                    problems.append(f"{here}.{key}: hyprlock has no such variable")
                    continue
                if key == "lines" and repeated:
                    for line in item:
                        problems.extend(_check_repeated(f"{here}.lines", line, repeated,
                                                        known))
                    continue
                spec = known.get(key) or positioning.get(key) or shadowable.get(key) \
                    or clickable.get(key)
                _check_value(f"{here}.{key}", spec, item, problems)

    # Composition rules the manual states in prose rather than per variable.
    widgets = [name for name in ("background", "shape", "input-field", "label", "image")
               if name in doc]
    if "background" not in doc:
        problems.append("background: hyprlock draws nothing without a background block")
    if "input-field" not in doc:
        problems.append("input-field: a lock screen with no field cannot be unlocked")
    if not widgets:
        problems.append("the render declares no widgets at all")
    if doc.get("animations", {}).get("enabled"):
        lines = doc["animations"].get("lines", [])
        declared = {line.split(", ")[0].split(" = ")[1] for line in lines
                    if line.startswith("bezier = ")}
        tree = {name for names in surface["sections"]["animations"]["tree"].values()
                for name in names}
        for line in lines:
            if not line.startswith("animation = "):
                continue
            parts = [part.strip() for part in line[len("animation = "):].split(",")]
            if len(parts) != 4:
                problems.append(f"animations: {line!r} is not NAME, ENABLED, SECONDS, BEZIER")
                continue
            leaf, enabled, seconds, curve = parts
            if leaf not in tree:
                problems.append(f"animations: {leaf!r} is not in hyprlock's animation tree "
                                f"({', '.join(sorted(tree))}), so it would not animate")
            if enabled not in ("0", "1"):
                problems.append(f"animations: {leaf} enabled is {enabled!r}, not 0 or 1")
            try:
                if float(seconds) <= 0:
                    problems.append(f"animations: {leaf} duration must be above 0")
            except ValueError:
                problems.append(f"animations: {leaf} duration {seconds!r} is not a number")
            if curve not in declared:
                problems.append(f"animations: {leaf} names bezier {curve!r}, which the block "
                                "does not declare")
    return problems


def validate_idle(doc: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    fallback = surface["hypridle_fallback"]
    for name, instance in doc.items():
        if name != "general":
            problems.append(f"{name}: this project's hypridle fallback declares only general, "
                            "so no listener can disagree with the shell's idle timers")
            continue
        for key, value in instance.items():
            if key not in fallback["general_keys"]:
                problems.append(f"general.{key}: hypridle has no such variable")
                continue
            _check_value(f"general.{key}", fallback["general_keys"][key], value, problems)
        if "lock_cmd" not in instance:
            problems.append("general.lock_cmd: without it a D-Bus lock event does nothing")
    if "listeners" in doc:
        for listener in doc["listeners"]:
            for key in listener:
                if key not in fallback["listener_keys"]:
                    problems.append(f"listener.{key}: hypridle has no such variable")
    return problems


# --------------------------------------------------------------- emission


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def emit_conf(doc: Dict[str, Any], header: str) -> str:
    """hyprlock's INI-like form: ``block { key = value }``, one widget per block."""
    out: List[str] = [line for line in header.splitlines() if line]
    out.append("")

    def block(name: str, values: Dict[str, Any], comment: Optional[str] = None) -> None:
        if comment:
            out.extend(f"# {line}" if line else "#" for line in comment.splitlines())
        out.append(f"{name} {{")
        for key, value in values.items():
            out.append(f"    {key} = {_scalar(value)}")
        out.append("}")
        out.append("")

    for name in ("general", "auth"):
        if name in doc:
            block(name, doc[name], BLOCK_COMMENTS.get(name))

    if "animations" in doc:
        # bezier and animation are keywords that repeat inside one block, so the
        # document carries them as raw lines rather than as a mapping.
        values = OrderedDict(doc["animations"])
        lines = values.pop("lines", [])
        out.extend(f"# {line}" if line else "#" for line in ANIMATION_COMMENT.splitlines())
        out.append("animations {")
        for key, value in values.items():
            out.append(f"    {key} = {_scalar(value)}")
        out.extend(f"    {line}" for line in lines)
        out.append("}")
        out.append("")

    for name in ("background", "shape", "input-field", "label"):
        for index, instance in enumerate(doc.get(name, [])):
            comment = None
            if index == 0:
                comment = WIDGET_COMMENTS.get(name)
                if name == "background" and not doc.get("_background_blurred", True):
                    comment = BACKGROUND_FLAT_COMMENT
            block(name, instance, comment)

    text = "\n".join(out).rstrip("\n")
    return text + "\n"


def emit_idle_conf(doc: Dict[str, Any], header: str) -> str:
    out: List[str] = [line for line in header.splitlines() if line]
    out.append("")
    for line in IDLE_COMMENT.splitlines():
        out.append(f"# {line}" if line else "#")
    out.append("")
    for name, values in doc.items():
        out.append(f"{name} {{")
        for key, value in values.items():
            out.append(f"    {key} = {_scalar(value)}")
        out.append("}")
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


BLOCK_COMMENTS = {
    "general": (
        "The lock surface fades with the compositor's own blur contribution when the\n"
        "session animates at all, and hides the pointer: a cursor parked over a password\n"
        "field is a cursor in the way of the dots. fail_timeout is hyprlock's default,\n"
        "restated so the field's own fade_timeout and the UI reset cannot drift apart."
    ),
    "auth": (
        "PAM only, with hyprlock's own module. Naming one would assert that\n"
        "/etc/pam.d/<module> exists on this machine; hyprlock falls back to \"su\" when it\n"
        "does not. On Arch, pambase's pam_faillock.so already locks the account for ten\n"
        "minutes after three failed unlocks."
    ),
}
ANIMATION_COMMENT = (
    "Durations are the animation preset's own fadeIn and fadeOut leaves, converted to the\n"
    "seconds hyprlock's animation keyword takes. The tokens' speed_multiplier is not\n"
    "applied: it scales Hyprland's tree through generated/animations.lua, and hyprlock has\n"
    "no multiplier, so scaling one side would make the lock screen disagree with the\n"
    "session it locks. With motion off there are no lines at all and enabled = false."
)
BACKGROUND_FLAT_COMMENT = (
    "No capture and no blur, because this intensity turns blur off: an unblurred\n"
    "screenshot would put a password field over sharp, high-contrast content, the one\n"
    "background that makes text hardest to read. The palette's background fills the\n"
    "screen instead, and path stays empty -- the manual's own rule is that an empty or\n"
    "missing path fills with color. The blur variables are still emitted at 0 so the\n"
    "file says what it decided rather than leaving it to a default."
)
WIDGET_COMMENTS = {
    "background": (
        "The desktop, captured when the lock starts and blurred by exactly the recipe the\n"
        "intensity uses for windows and panels: these are Hyprland's decoration:blur\n"
        "leaves, and hyprlock's manual says its blur options are taken from Hyprland.\n"
        "color is the fallback the manual describes for a path that cannot be read, so it\n"
        "is the palette's background at full opacity rather than a tint. A *live* blurred\n"
        "backdrop instead of a capture needs Hyprland's misc:session_lock_xray and\n"
        "misc:session_lock_blur; both are real v0.57.2 leaves and neither is enabled here,\n"
        "because they keep every workspace rendering underneath a locked session."
    ),
    "shape": (
        "The frosted card. Only background blurs in hyprlock, so \"frosted\" here is a\n"
        "translucent surface colour over an already-blurred capture -- the shell's own\n"
        "panel recipe, minus a second blur pass it has no variable for. rounding is the\n"
        "tokens' panel radius in pixels; hyprlock has no percentage rounding and no shared\n"
        "radius scale."
    ),
    "input-field": (
        "The three state colours are the palette's semantic accents: warning while PAM is\n"
        "being asked, danger when it refuses, primary when Caps Lock is on -- the same\n"
        "mapping the shell uses for a critical notification's border. hyprlock documents\n"
        "each as a gradient, and a gradient accepts one colour."
    ),
    "label": (
        "$TIME and $DESC are hyprlock's own substitutions, so nothing on this screen runs\n"
        "a shell command. The manual's cmd[update:N] form spawns a process on a timer\n"
        "inside the lock surface and hangs the AsyncResourceGatherer if it never exits; a\n"
        "clock that costs nothing is worth more than one that proves a shell works."
    ),
}
IDLE_COMMENT = (
    "Shipped UNLAUNCHED, and that is the point.\n"
    "\n"
    "hypridle watches ext_idle_notifier_v1, and so does the shell: Noctalia v5.4.1 runs its\n"
    "own idle behaviours from [idle.behavior.*] in ~/.config/noctalia/config.toml, which\n"
    "respect D-Bus and Wayland idle inhibitors. Starting both means two processes racing to\n"
    "lock, dim and suspend the same session, and nobody can tell from the screen which one\n"
    "won. So idle is configured in the shell, and this file exists for the case where the\n"
    "shell is not running at all.\n"
    "\n"
    "It declares no listener, so it owns no timer: only the two commands a session still\n"
    "needs without a shell. lock_cmd prefers the lock surface that is already up -- the\n"
    "same `pidof x || y` shape the hypridle manual's own example uses -- and falls back to\n"
    "hyprlock, which reads the hyprlock.conf next to this file.\n"
    "\n"
    "To use it instead of the shell's idle system, add `hypridle` to the exec_once list in\n"
    ".config/hypr/startup.lua *and* disable every [idle.behavior.*] entry in config.toml.\n"
    "Doing only the first is what causes the race.\n"
    "\n"
    "after_sleep_cmd is the hypridle manual's own remedy for a display that needs a key\n"
    "press to come back after resume, in the spelling this compositor can run: Hyprland\n"
    "v0.57.2 evaluates `hyprctl dispatch X` as Lua when the config provider is Lua, so the\n"
    "manual's legacy `dpms on` form is a syntax error here and hl.dsp.dpms is the dispatcher\n"
    "that exists. docs/UNVERIFIED.md LOCK-03 records that no compositor in this project's\n"
    "reach ever ran either spelling."
)


def provenance(tokens: Dict[str, Any], preset: Dict[str, Any], surface: Dict[str, Any],
               intensity_name: str) -> str:
    return "\n".join([
        f"# Source: data/design/tokens.json intensity={intensity_name}, "
        f"preset=data/design/presets/{preset['id']}.json, "
        f"motion=data/design/animations/{tokens['intensities'][intensity_name]['motion']['preset']}.json.",
        f"# Variables, types and defaults recorded in data/design/hyprlock.json "
        f"({surface['verified_against']}).",
        "# Edit the tokens, the preset or the geometry constants in "
        "iarch/cli/render_hyprlock.py, then run iarch-theme apply.",
        "# hyprlock only warns about an unknown variable, so this file is generated and "
        "checked rather than hand-edited.",
    ])


# --------------------------------------------------------------- targets


def user_targets(tokens: Dict[str, Any], preset: Dict[str, Any], intensity_name: str,
                 root: Optional[Path] = None) -> List[Tuple[Path, str]]:
    surface = load_json(SURFACE_PATH)
    base = root or (configstore.config_dir() / "hypr")

    doc = render_document(tokens, preset, intensity_name, surface)
    problems = validate(doc, surface)
    if problems:
        raise HyprlockError("rendered hyprlock.conf is not valid for "
                            f"{surface['tool']}:\n  " + "\n  ".join(problems))

    idle = render_idle_document(surface)
    idle_problems = validate_idle(idle, surface)
    if idle_problems:
        raise HyprlockError("rendered hypridle.conf is not valid:\n  "
                            + "\n  ".join(idle_problems))

    return [
        (base / "hyprlock.conf", emit_conf(doc, provenance(tokens, preset, surface,
                                                           intensity_name))),
        (base / "hypridle.conf", emit_idle_conf(idle, IDLE_PROVENANCE)),
    ]


IDLE_PROVENANCE = "\n".join([
    "# Source: data/design/hyprlock.json (hypridle_fallback) and the hypridle manual's own",
    "# general example. No listener is declared, so this file owns no idle timer.",
])


def repo_targets(tokens: Dict[str, Any]) -> List[Tuple[Path, str]]:
    """The shipped payload: the default preset at the tokens' default intensity."""
    preset = load_preset(DEFAULT_PRESET)
    intensity = tokens["default_intensity"]
    return user_targets(tokens, preset, intensity, REPO_LOCK.parent)


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated puts on disk for ``body``."""
    return f"{configstore.header_for(path)}\n{body}\n"


def write_all(targets: Sequence[Tuple[Path, str]]) -> List[Path]:
    """Write every target, or put them all back byte for byte if any write fails."""
    snapshot: Dict[Path, Optional[bytes]] = {
        path: (path.read_bytes() if path.is_file() else None) for path, _ in targets}
    try:
        for path, body in targets:
            configstore.write_generated(path, body)
    except BaseException:
        for path, original in snapshot.items():
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_bytes(original)
            except OSError:
                pass
        raise
    return [path for path, _ in targets]


# --------------------------------------------------------------- CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help=f"preset id (default {DEFAULT_PRESET})")
    parser.add_argument("--intensity", help="crystal, frosted, soft or performance")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the rendered hyprlock.conf to stdout")
    parser.add_argument("--write-repo-default", action="store_true",
                        help="refresh the shipped files under .config/hypr/")
    parser.add_argument("--check", action="store_true",
                        help="verify the shipped files match a fresh render")
    parser.add_argument("--output-dir", type=Path,
                        help="write into this directory instead of the user config dir")
    args = parser.parse_args(argv)

    try:
        tokens = load_tokens()
        preset = load_preset(args.preset or DEFAULT_PRESET)
        intensity = resolve_intensity(tokens, preset, args.intensity)
        if args.to_stdout:
            surface = load_json(SURFACE_PATH)
            doc = render_document(tokens, preset, intensity, surface)
            problems = validate(doc, surface)
            if problems:
                raise HyprlockError("render is not valid:\n  " + "\n  ".join(problems))
            sys.stdout.write(emit_conf(doc, provenance(tokens, preset, surface, intensity)))
            return 0
        targets = (repo_targets(tokens) if args.write_repo_default or args.check
                   else user_targets(tokens, preset, intensity, args.output_dir))
    except HyprlockError as exc:
        print(f"hyprlock: {exc}", file=sys.stderr)
        return 2

    if args.check:
        drifted = []
        for path, body in targets:
            expected = rendered_text(path, body)
            if not path.is_file():
                drifted.append(f"{label(path)} is missing")
            elif path.read_text(encoding="utf-8") != expected:
                drifted.append(f"{label(path)} does not match a fresh render")
        if drifted:
            for line in drifted:
                print(f"hyprlock: {line}", file=sys.stderr)
            print("hyprlock: run --write-repo-default", file=sys.stderr)
            return 1
        print(f"hyprlock: {len(targets)} shipped file(s) match a fresh render against "
              f"{load_json(SURFACE_PATH)['verified_against']}")
        return 0

    try:
        written = write_all(targets)
    except (OSError, configstore.ConfigError) as exc:
        print(f"hyprlock: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"hyprlock: wrote {label(path)}")
    print(f"hyprlock: preset {preset['id']}, intensity {intensity}")
    print("hyprlock: hypridle.conf is written but NOT started; see the comment at its head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
