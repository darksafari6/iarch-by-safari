#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the Hyprland animation set from a motion preset.

Part 2 rendered one animation set out of the motion tokens: four easings, a
spring, and eleven leaves chosen by a plan written in this file. Part 3 moves the
plan into data so a person can switch it. ``data/design/animations/`` holds one
JSON per preset — smooth, snappy, bouncy, minimal, off — and each declares its
own named curves and its own per-event durations, curves and styles. This module
renders one of them to ``~/.config/hypr/generated/animations.lua``, which
``animations.lua`` loads through a ``pcall`` after the static
``animations/default.lua``, so a session that has never run anything still
animates with the static baseline and whatever is required last wins.

Three things make this safer than editing a config by hand:

* every leaf, curve and style is checked against ``data/design/animations.json``,
  the animation API read out of Hyprland v0.57.2. An invented leaf, a style that
  leaf does not accept, a curve an event names but the preset does not declare, a
  bezier component outside ``[-1, 2]``, a spring value at or below 0.5 or a speed
  outside ``(0, 100]`` fails here, in CI and at render time, rather than as a
  config error in the user's session. The numeric bounds are read out of the
  surface file rather than hardcoded a second time, so there is one record of
  what the pinned release enforces;
* every ``speed`` is derived from a duration by the one formula Hyprland
  actually uses — ``duration_ms = 100 * speed``, from hyprutils
  ``AnimatedVariable::getPercent`` — so a number is never picked by hand. The
  global multiplier ``iarch-anim speed`` sets divides the duration (greater than
  1 is faster, the direction ``render_noctalia.py`` already uses for
  ``shell.animation``) and the result is re-checked against the same bounds;
* a disabled event is emitted as an explicit ``enabled = false`` rather than left
  out. A leaf that is absent keeps whatever its parent in Hyprland's animation
  tree does — ``windowsIn`` inherits ``windows``, ``specialWorkspace`` inherits
  ``workspaces``, ``fadeIn`` inherits ``fade`` — so omitting an entry would not
  turn anything off. ``hl.animation`` returns early on ``enabled = false``, so a
  disabled event carries no speed, curve or style.

The ``off`` preset and the Performance intensity set the master switch instead:
``hl.config({ animations = { enabled = false } })`` makes Hyprland's
AnimationManager warp every animated variable straight to its final value
(``warp = !*PANIMENABLED || !PAV->enabled()``), so no bezier or spring is stepped
per frame and the render emits no curve and no leaf at all. That is how the
Performance preset measurably lowers compositor work; docs/UNVERIFIED.md PERF-01
records that the frame-time saving itself was not measured on real hardware.

Reduce-motion is not a sixth preset. It renders the preset
``tokens.motion.animation.reduce_motion.preset`` names — minimal, which keeps the
opacity fades and turns off everything that moves — with every duration capped at
``max_duration_ms``, so the result is the same whatever was selected before. This
module refuses to render reduce-motion from any other preset, which is what keeps
the guarantee true for every caller rather than only for the careful one.

Usage:
    python3 iarch/cli/gen_animations_lua.py                      # write to the user config dir
    python3 iarch/cli/gen_animations_lua.py --preset bouncy
    python3 iarch/cli/gen_animations_lua.py --intensity performance
    python3 iarch/cli/gen_animations_lua.py --speed 1.5 --reduce-motion
    python3 iarch/cli/gen_animations_lua.py --print              # stdout, write nothing
    python3 iarch/cli/gen_animations_lua.py --write-repo-default # refresh .config/hypr/generated/
    python3 iarch/cli/gen_animations_lua.py --check              # repo default matches a fresh render

``iarch-anim`` imports these functions rather than shelling out to them, the way
``iarch-theme`` drives every other renderer in this directory.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
SURFACE_PATH = ROOT / "data" / "design" / "animations.json"
PRESET_DIR = ROOT / "data" / "design" / "animations"
REPO_DEFAULT = ROOT / ".config" / "hypr" / "generated" / "animations.lua"
MODULE_NAME = "generated.animations"

# Curve names are prefixed so they cannot collide with the static default.lua's
# wind/winIn/winOut/liner or with Hyprland's built-in "default"/"linear".
CURVE_PREFIX = "iarch-"


class AnimationError(RuntimeError):
    """Raised when the tokens, a preset, the surface or a rendered value cannot be trusted."""


# ---------------------------------------------------------------- inputs


def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnimationError(f"{path}: {exc}") from exc


def load_tokens() -> Dict[str, Any]:
    return load_json(TOKENS_PATH)


def load_surface() -> Dict[str, Any]:
    return load_json(SURFACE_PATH)


def _animation_block(tokens: Dict[str, Any]) -> Dict[str, Any]:
    """``tokens.motion.animation``, the block Part 3 added."""
    motion = tokens.get("motion")
    if not isinstance(motion, dict):
        raise AnimationError("tokens.json has no motion block")
    block = motion.get("animation")
    if not isinstance(block, dict):
        raise AnimationError("tokens.json motion has no animation block; it names the presets, "
                             "the multiplier bounds and what reduce-motion resolves to")
    for key in ("default_preset", "presets", "speed_multiplier", "reduce_motion"):
        if key not in block:
            raise AnimationError(f"tokens.motion.animation is missing {key!r}")
    return block


def preset_names(tokens: Dict[str, Any]) -> Tuple[str, ...]:
    """The presets the tokens name, each checked to exist on disk.

    The list is closed -- it is what ``iarch-anim`` accepts and what the settings
    schema allows -- but a name with no file behind it, or a file with no name
    here, is a broken install rather than a user error, so both are refused here
    with the directory that was looked in.
    """
    block = _animation_block(tokens)
    names = block["presets"]
    if not isinstance(names, list) or not names:
        raise AnimationError("tokens.motion.animation.presets must be a non-empty list")
    for name in names:
        if not isinstance(name, str) or not name:
            raise AnimationError(f"tokens.motion.animation.presets contains {name!r}")
        if not (PRESET_DIR / f"{name}.json").is_file():
            raise AnimationError(f"preset {name!r} is named by the tokens but "
                                 f"{label(PRESET_DIR / (name + '.json'))} does not exist")
    default = block["default_preset"]
    if default not in names:
        raise AnimationError(f"tokens.motion.animation.default_preset {default!r} is not one of "
                             f"the presets it names ({', '.join(names)})")
    return tuple(names)


def default_preset(tokens: Dict[str, Any]) -> str:
    return str(_animation_block(tokens)["default_preset"])


def load_preset(name: str) -> Dict[str, Any]:
    """One preset document, checked to be the preset it claims to be."""
    if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
        raise AnimationError(f"{name!r} is not a preset name")
    path = PRESET_DIR / f"{name}.json"
    if not path.is_file():
        known = sorted(p.stem for p in PRESET_DIR.glob("*.json"))
        raise AnimationError(f"unknown preset {name!r}; {label(PRESET_DIR)} holds "
                             f"{', '.join(known) or 'nothing'}")
    preset = load_json(path)
    if preset.get("name") != name:
        raise AnimationError(f"{label(path)} declares name {preset.get('name')!r}, not {name!r}")
    for key in ("label", "master", "curves", "events"):
        if key not in preset:
            raise AnimationError(f"preset {name!r} is missing {key!r}")
    if not isinstance(preset["curves"], dict) or not isinstance(preset["events"], dict):
        raise AnimationError(f"preset {name!r}: curves and events must both be objects")
    return preset


def resolve_intensity(tokens: Dict[str, Any], intensity: Optional[str]) -> str:
    name = intensity or tokens.get("default_intensity", "frosted")
    if name not in tokens["intensities"]:
        raise AnimationError(f"unknown intensity {name!r}; tokens define "
                             f"{', '.join(sorted(tokens['intensities']))}")
    return name


def preset_for_intensity(tokens: Dict[str, Any], intensity_name: str) -> str:
    """The motion preset an intensity renders from, with the two switches agreed.

    ``motion.enabled`` is Part 2's master switch and ``motion.preset`` is Part 3's
    preset name; they say the same thing two ways, so they are required to say it
    consistently. The schema cannot compare two keys of one object, which is why
    the check lives here and in tests/test_animation_presets.py.
    """
    intensity = tokens["intensities"].get(intensity_name)
    if not isinstance(intensity, dict):
        raise AnimationError(f"unknown intensity {intensity_name!r}")
    motion = intensity.get("motion")
    if not isinstance(motion, dict) or "enabled" not in motion:
        raise AnimationError(f"intensity {intensity_name!r} has no motion.enabled switch")
    preset = motion.get("preset")
    if not isinstance(preset, str) or not preset:
        raise AnimationError(f"intensity {intensity_name!r} has no motion.preset; it must name "
                             f"one of {', '.join(preset_names(tokens))}")
    if preset not in preset_names(tokens):
        raise AnimationError(f"intensity {intensity_name!r} names preset {preset!r}, which the "
                             f"tokens do not list")
    enabled = bool(motion["enabled"])
    off = preset == "off"
    if enabled and off:
        raise AnimationError(f"intensity {intensity_name!r} enables motion but names the 'off' "
                             f"preset; the master switch and the preset must agree")
    if not enabled and not off:
        raise AnimationError(f"intensity {intensity_name!r} disables motion but names the "
                             f"{preset!r} preset; only 'off' pairs with enabled=false")
    return preset


def reduce_motion_preset(tokens: Dict[str, Any]) -> str:
    return str(_animation_block(tokens)["reduce_motion"]["preset"])


def reduce_motion_cap_ms(tokens: Dict[str, Any]) -> int:
    return int(_animation_block(tokens)["reduce_motion"]["max_duration_ms"])


def multiplier_bounds(tokens: Dict[str, Any]) -> Tuple[float, float, float]:
    """(min, max, default) for the global speed multiplier."""
    bounds = _animation_block(tokens)["speed_multiplier"]
    if not isinstance(bounds, dict):
        raise AnimationError("tokens.motion.animation.speed_multiplier must be an object")
    try:
        low, high = float(bounds["min"]), float(bounds["max"])
        default = float(bounds.get("default", 1.0))
    except (KeyError, TypeError, ValueError) as exc:
        raise AnimationError(f"tokens.motion.animation.speed_multiplier is incomplete: {exc}") from exc
    if low <= 0 or high < low or not (low <= default <= high):
        raise AnimationError(f"speed_multiplier bounds {low}..{high} (default {default}) are not "
                             f"a usable range")
    return low, high, default


def clamp_multiplier(tokens: Dict[str, Any], value: Any) -> Tuple[float, bool]:
    """Clamp a requested multiplier into the token bounds; return (value, clamped).

    ``iarch-anim speed`` is specified to clamp rather than refuse, so asking for
    10 gets the fastest setting the design system allows and says so, instead of
    leaving a person staring at an error for a slider they dragged too far.
    """
    low, high, _default = multiplier_bounds(tokens)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnimationError(f"speed multiplier {value!r} is not a number")
    requested = float(value)
    if requested != requested:  # NaN
        raise AnimationError("speed multiplier is not a number")
    clamped = min(max(requested, low), high)
    return round(clamped, 4), clamped != requested


# ---------------------------------------------------------------- lua emission


def lua_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = repr(float(value))
    return text if any(ch in text for ch in ".eE") else f"{text}.0"


def lua_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def lua_inline_table(pairs: Sequence[Tuple[str, str]]) -> str:
    """A one-line ``{ k = v, ... }`` from already-rendered value strings."""
    return "{ " + ", ".join(f"{k} = {v}" for k, v in pairs) + " }"


def curve_name(local: str) -> str:
    """A preset-local curve name as it is registered in the session."""
    return CURVE_PREFIX + local


# ---------------------------------------------------------------- validation


def speed_for(surface: Dict[str, Any], duration_ms: Any, where: str) -> float:
    """Turn a duration in milliseconds into a Hyprland ``speed``.

    Hyprland's ``speed`` is a duration in centiseconds despite the name: from
    hyprutils ``AnimatedVariable::getPercent`` the animation finishes when
    ``(elapsed_ms / 100) / speed`` reaches 1, i.e. after ``100 * speed``
    milliseconds. So ``speed = duration_ms / 100``. The binding rejects
    ``speed <= 0`` and parses it with ``CLuaConfigFloat(0, 0, 100)``, which
    returns ``PARSE_ERROR_OUT_OF_RANGE`` rather than clamping, so a usable
    duration is in ``(0, 10000]`` ms; both bounds come from the recorded surface.
    """
    formula = surface["speed_formula"]
    if isinstance(duration_ms, bool) or not isinstance(duration_ms, (int, float)):
        raise AnimationError(f"{where}: duration {duration_ms!r} is not a number")
    speed = round(float(duration_ms) / 100.0, 4)
    low, high = formula["speed_min_exclusive"], formula["speed_max"]
    if speed <= low:
        raise AnimationError(f"{where}: duration {duration_ms}ms gives speed {speed}, "
                             f"which must be greater than {low}")
    if speed > high:
        raise AnimationError(f"{where}: duration {duration_ms}ms gives speed {speed}, "
                             f"above the binding maximum {high}")
    return speed


def effective_duration_ms(base_ms: Any, multiplier: float, where: str,
                          cap_ms: Optional[int] = None) -> int:
    """The duration a preset event actually gets, in whole milliseconds.

    The multiplier divides: 2.0 means twice as fast, so half as long, which is
    the direction ``render_noctalia.py`` already uses for ``shell.animation``.
    ``cap_ms`` is the reduce-motion ceiling and is applied after the multiplier,
    so a capped render stays capped at every multiplier. The result is rounded to
    a whole millisecond before it becomes a speed, which keeps the generated file
    readable (1.07 rather than 1.0667) and cannot lose the animation: the
    shortest duration any preset declares is 90 ms and the largest multiplier is
    2.0, so the floor of 1 ms is never reached -- but a hand-edited preset could
    reach it, and a 0 ms animation would be refused by the binding anyway, so it
    is refused here with the arithmetic shown.
    """
    if isinstance(base_ms, bool) or not isinstance(base_ms, (int, float)):
        raise AnimationError(f"{where}: duration_ms {base_ms!r} is not a number")
    if base_ms <= 0:
        raise AnimationError(f"{where}: duration_ms {base_ms} must be positive")
    if multiplier <= 0:
        raise AnimationError(f"{where}: multiplier {multiplier} must be positive")
    value = float(base_ms) / float(multiplier)
    if cap_ms is not None:
        value = min(value, float(cap_ms))
    ms = int(round(value))
    if ms < 1:
        raise AnimationError(f"{where}: {base_ms} ms at multiplier {multiplier}"
                             + (f" capped at {cap_ms} ms" if cap_ms is not None else "")
                             + f" rounds to {ms} ms, below the 1 ms floor")
    return ms


def check_leaf_exists(surface: Dict[str, Any], leaf: str) -> None:
    """Is this a leaf the pinned release has at all? Checked for every event.

    A typo in a disabled event is still a typo: ``hl.animation`` would answer
    "no such animation leaf" whether or not the event is enabled, so the name is
    verified before anything else about it is looked at.
    """
    if leaf not in surface["leaves"]:
        raise AnimationError(f"{leaf} is not an animation leaf Hyprland {surface['verified_against']} "
                             f"knows; the generator must not emit it")


def check_leaf(surface: Dict[str, Any], leaf: str, style: Optional[str]) -> None:
    """Leaf existence plus the style rules, for an event that will be enabled.

    The style check is only meaningful for an enabled event: ``hl.animation``
    returns early on ``enabled = false`` and never reaches
    ``styleValidInConfigVar``, so a disabled event carries no style and demanding
    one would make "this leaf does nothing" unrepresentable.

    Requiring a name where the leaf accepts styles is this project's choice rather
    than Hyprland's -- the binding treats ``style`` as optional -- and Part 2 made
    it, so an animation set always says which of slide/gnome/gnomed/popin it means
    instead of leaving it to whatever the release defaults to.
    """
    check_leaf_exists(surface, leaf)
    allowed = surface["leaves"][leaf]["styles"]
    if style is None:
        if allowed:
            raise AnimationError(f"{leaf} accepts styles {allowed}; the preset must name one, "
                                 f"not omit it")
    elif style not in allowed:
        raise AnimationError(f"{leaf} does not accept style {style!r}; Hyprland allows "
                             f"{allowed or 'no styles'} for it")


def check_bezier(surface: Dict[str, Any], name: str, curve: Dict[str, Any]) -> None:
    """A bezier the binding will register: two points, four components, all in range."""
    if curve.get("type") != "bezier":
        raise AnimationError(f"curve {name!r} is not a bezier curve")
    points = curve.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise AnimationError(f"curve {name!r}: hl.curve needs exactly 2 bezier points, "
                             f"got {points!r}")
    limits = surface["curve_types"]["bezier"]
    low, high = limits["component_min"], limits["component_max"]
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or not all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in point)):
            raise AnimationError(f"curve {name!r}: point {point!r} is not a pair of numbers")
        for component in point:
            # CLuaConfigFloat(0, -1, 2) returns PARSE_ERROR_OUT_OF_RANGE instead of
            # clamping, so this is a session-stopping error, not a correction.
            if component < low or component > high:
                raise AnimationError(f"curve {name!r}: bezier component {component} is outside "
                                     f"[{low}, {high}], the range hl.curve parses each component "
                                     f"against; out of range is a config error, not a clamp")


def check_spring(surface: Dict[str, Any], name: str, spring: Dict[str, Any]) -> None:
    floor = surface["curve_types"]["spring"]["value_min_exclusive"]
    for key in ("stiffness", "damping", "mass"):
        value = spring.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AnimationError(f"curve {name!r}: spring {key!r} is not a number")
        # The binding calls Internal::configError when the value is <= 0.5F, so the
        # usable bound is strictly greater than the floor it records.
        if value <= floor:
            raise AnimationError(f"curve {name!r}: spring {key} = {value} must be strictly "
                                 f"greater than {floor}; hl.curve rejects it")


# ---------------------------------------------------------------- the render


def render_curves(preset: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """Register every curve the preset declares, in the order it declares them.

    Order matters twice over: ``hl.animation`` looks a name up with
    ``bezierExists``/``springExists`` and errors on a miss, so every curve has to
    be registered before the events that name it, and a preset that declares an
    overshoot bezier and a spring gets both, whichever its events use.
    """
    calls: List[str] = []
    for name, curve in (preset.get("curves") or {}).items():
        if not isinstance(name, str) or not name:
            raise AnimationError(f"preset {preset.get('name')!r}: curve name {name!r} is not usable")
        if not isinstance(curve, dict):
            raise AnimationError(f"preset {preset.get('name')!r}: curve {name!r} is not an object")
        kind = curve.get("type")
        if kind == "bezier":
            check_bezier(surface, name, curve)
            points = " ".join(
                "{" + ", ".join(lua_number(c) for c in pt) + "}," for pt in curve["points"]
            )
            table = lua_inline_table([
                ("type", lua_string("bezier")),
                ("points", "{ " + points.rstrip(",") + " }"),
            ])
        elif kind == "spring":
            check_spring(surface, name, curve)
            table = lua_inline_table([
                ("type", lua_string("spring")),
                ("stiffness", lua_number(curve["stiffness"])),
                ("damping", lua_number(curve["damping"])),
                ("mass", lua_number(curve["mass"])),
            ])
        else:
            raise AnimationError(f"preset {preset.get('name')!r}: curve {name!r} has type "
                                 f"{kind!r}; hl.curve accepts 'bezier' or 'spring'")
        calls.append(f"hl.curve({lua_string(curve_name(name))}, {table})")
    return calls


def _effective_enabled(leaf: str, event: Dict[str, Any], overrides: Mapping[str, bool],
                       reduce_motion: bool, warnings: List[str]) -> bool:
    """What an event ends up doing, after the user's per-event override.

    An override is an explicit choice and normally wins in both directions, so a
    person can switch the looping border sweep off in smooth or back on in
    minimal. Reduce-motion is the one case where it does not: an override that
    would add motion back is ignored and reported, because an accessibility
    setting that a stale toggle could silently defeat is not an accessibility
    setting. Overrides that remove motion are always honoured.
    """
    preset_enabled = bool(event["enabled"])
    if leaf not in overrides:
        return preset_enabled
    wanted = bool(overrides[leaf])
    if reduce_motion and wanted and not preset_enabled:
        warnings.append(f"{leaf}: your override asks for motion that reduce-motion removes, "
                        f"so it stays off")
        return False
    return wanted


def plan_events(preset: Dict[str, Any], surface: Dict[str, Any], *,
                multiplier: float = 1.0, cap_ms: Optional[int] = None,
                overrides: Optional[Mapping[str, bool]] = None,
                reduce_motion: bool = False) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Resolve every event to the numbers that will be emitted; return (plan, warnings).

    One plan, two readers: ``render_events`` turns it into Lua and ``iarch-anim``
    reports it (and puts it in ``--json`` for the Part 4 settings app and the Part
    5 overlay). Keeping the decisions here means the report cannot drift from the
    render -- a caller never has to re-derive what the multiplier, the cap or an
    override did, and every refusal happens before a single line is emitted.

    Each entry carries the leaf, whether it animates, the duration in whole
    milliseconds after the multiplier and the cap, the ``speed`` that duration
    becomes, the registered curve name and its kind, and the style if the leaf
    takes one. A disabled entry carries only the leaf and ``enabled = False``,
    because that is all ``hl.animation`` reads on its early return.
    """
    overrides = dict(overrides or {})
    events = preset.get("events") or {}
    declared = set(events)
    for leaf in sorted(set(overrides) - declared):
        raise AnimationError(f"event {leaf!r} is not one this preset declares; "
                             f"{preset.get('name')!r} sets {', '.join(sorted(declared)) or 'nothing'}")

    warnings: List[str] = []
    curves = preset.get("curves") or {}
    plan: List[Dict[str, Any]] = []
    for leaf, event in events.items():
        if not isinstance(event, dict) or "enabled" not in event:
            raise AnimationError(f"preset {preset.get('name')!r}: event {leaf!r} has no "
                                 f"'enabled' key")
        check_leaf_exists(surface, leaf)
        preset_enabled = bool(event["enabled"])
        enabled = _effective_enabled(leaf, event, overrides, reduce_motion, warnings)
        if enabled and not preset_enabled:
            # Only an override can get here, and only for an event the preset
            # itself declares off -- which by the rule below carries no duration,
            # curve or style, so there is nothing to turn it on with.
            raise AnimationError(f"preset {preset.get('name')!r} declares {leaf!r} off and gives "
                                 f"it no duration, curve or style, so an override cannot turn it "
                                 f"on; switch to a preset that animates {leaf}")
        if not enabled:
            if not preset_enabled:
                # The preset declares this event off, so the data it carries would
                # be dead. An override turning a live event off is different: the
                # preset's duration and curve stay in the file, ready for the next
                # toggle back, and are simply not emitted.
                dead = sorted(key for key in ("duration_ms", "curve", "style") if key in event)
                if dead:
                    raise AnimationError(f"preset {preset.get('name')!r}: event {leaf!r} is "
                                         f"disabled but still carries {', '.join(dead)}, which "
                                         f"hl.animation never reads; a disabled event says only "
                                         f"that it is off")
            plan.append({"leaf": leaf, "enabled": False})
            continue
        check_leaf(surface, leaf, event.get("style"))

        local = event.get("curve")
        if not isinstance(local, str) or local not in curves:
            raise AnimationError(f"preset {preset.get('name')!r}: event {leaf!r} names curve "
                                 f"{local!r}, which the preset does not declare; Hyprland would "
                                 f"reject it as an unregistered curve")
        duration = event.get("duration_ms")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise AnimationError(f"preset {preset.get('name')!r}: event {leaf!r} is enabled but "
                                 f"carries no duration_ms")
        where = f"{preset.get('name')}.{leaf}"
        ms = effective_duration_ms(duration, multiplier, where, cap_ms=cap_ms)
        speed = speed_for(surface, ms, where)
        # bezier and spring are mutually exclusive in hl.animation: it checks the
        # bezier field first and the spring field second, and uses exactly one.
        kind = curves[local].get("type")
        if kind not in ("bezier", "spring"):
            raise AnimationError(f"preset {preset.get('name')!r}: curve {local!r} has type "
                                 f"{kind!r}, which hl.animation cannot use")
        plan.append({
            "leaf": leaf,
            "enabled": True,
            "duration_ms": ms,
            "speed": speed,
            "curve": curve_name(local),
            "kind": kind,
            "style": event.get("style"),
            # A spring curve ignores speed: getCurveStep advances it by wall-clock
            # DT through advanceSpring and never reads internalSpeed. The value is
            # emitted because the binding still requires one above 0.
            "duration_is_inert": kind == "spring",
        })
    return plan, warnings


def render_events(preset: Dict[str, Any], surface: Dict[str, Any], *,
                  multiplier: float = 1.0, cap_ms: Optional[int] = None,
                  overrides: Optional[Mapping[str, bool]] = None,
                  reduce_motion: bool = False) -> Tuple[List[str], List[str]]:
    """One ``hl.animation`` call per event the preset declares; return (calls, warnings)."""
    plan, warnings = plan_events(preset, surface, multiplier=multiplier, cap_ms=cap_ms,
                                 overrides=overrides, reduce_motion=reduce_motion)
    calls: List[str] = []
    for entry in plan:
        leaf = entry["leaf"]
        if not entry["enabled"]:
            # hl.animation returns early on enabled = false, after
            # setConfigForNode(leaf, false, 1, "default"), so no speed, curve or
            # style is read -- and emitting one would suggest it matters.
            calls.append("hl.animation(" + lua_inline_table([
                ("leaf", lua_string(leaf)),
                ("enabled", lua_number(False)),
            ]) + ")")
            continue
        pairs: List[Tuple[str, str]] = [
            ("leaf", lua_string(leaf)),
            ("enabled", lua_number(True)),
            ("speed", lua_number(entry["speed"])),
            (entry["kind"], lua_string(entry["curve"])),
        ]
        if entry["style"] is not None:
            pairs.append(("style", lua_string(entry["style"])))
        calls.append(f"hl.animation({lua_inline_table(pairs)})")
    return calls, warnings


def resolve_modifiers(tokens: Dict[str, Any], preset_name: str, multiplier: Any = 1.0,
                      reduce_motion: bool = False) -> Tuple[float, Optional[int], List[str]]:
    """Settle the multiplier and the reduce-motion cap; return (factor, cap_ms, warnings).

    One resolver, so the rules cannot differ between what is rendered and what is
    reported: the multiplier is clamped to the token bounds (and says so), and
    reduce-motion is refused for any preset but the one the tokens force, then
    caps every duration after the multiplier so slowing down cannot push a fade
    back over the ceiling.
    """
    warnings: List[str] = []
    factor, clamped = clamp_multiplier(tokens, multiplier)
    if clamped:
        low, high, _default = multiplier_bounds(tokens)
        warnings.append(f"speed multiplier {multiplier} is outside {low}..{high}; "
                        f"rendered at {factor}")
    cap_ms: Optional[int] = None
    if reduce_motion:
        forced = reduce_motion_preset(tokens)
        if preset_name != forced:
            raise AnimationError(f"reduce-motion renders the {forced!r} preset, not "
                                 f"{preset_name!r}; tokens.motion.animation.reduce_motion.preset "
                                 f"is what makes reduce-motion mean the same thing every time")
        cap_ms = reduce_motion_cap_ms(tokens)
        warnings.append(f"reduce-motion: rendering {forced!r} with every duration capped at "
                        f"{cap_ms} ms")
    return factor, cap_ms, warnings


def render_preset(tokens: Dict[str, Any], surface: Dict[str, Any], preset: Dict[str, Any], *,
                  multiplier: Any = 1.0, reduce_motion: bool = False,
                  overrides: Optional[Mapping[str, bool]] = None,
                  intensity_name: Optional[str] = None) -> Tuple[str, List[str]]:
    """Return (lua source without the generated header, warnings) for one preset."""
    name = preset.get("name")
    if not isinstance(name, str) or not name:
        raise AnimationError("a preset must carry its own name")

    factor, cap_ms, warnings = resolve_modifiers(tokens, name, multiplier, reduce_motion)

    master_on = bool(preset.get("master"))
    master = ("hl.config({\n"
              "    animations = {\n"
              f"        enabled = {lua_number(master_on)},\n"
              "    },\n"
              "})")
    if not master_on:
        warnings.append(f"preset {name}: animations disabled; Hyprland warps every animated "
                        f"variable to its final value (no per-frame curve work)")
        return master + "\n", warnings

    events, event_warnings = render_events(
        preset, surface, multiplier=factor, cap_ms=cap_ms,
        overrides=overrides, reduce_motion=reduce_motion)
    warnings.extend(event_warnings)
    parts = [master, "", *render_curves(preset, surface), "", *events]
    return "\n".join(parts) + "\n", warnings


def header_note(preset: Dict[str, Any], surface: Dict[str, Any], warnings: List[str], *,
                intensity_name: Optional[str] = None, multiplier: float = 1.0,
                reduce_motion: bool = False, overrides: Optional[Mapping[str, bool]] = None) -> str:
    name = preset.get("name")
    origin = f"data/design/animations/{name}.json"
    if intensity_name:
        origin += f" (intensity={intensity_name})"
    lines = [
        f"-- Source: {origin}, data/design/animations.json",
        f"-- Verified against Hyprland {surface['verified_against']}; speed = duration_ms / 100 "
        f"(hyprutils AnimatedVariable getPercent).",
        f"-- Preset {name!r} at speed multiplier {multiplier}"
        + (" with reduce-motion" if reduce_motion else "")
        + (f", {len(overrides)} event override(s)" if overrides else "") + ".",
        "-- Switch it with iarch-anim: set PRESET | speed 0.5-2.0 | toggle EVENT | "
        "reduce-motion on|off | current.",
    ]
    for warning in warnings:
        lines.append(f"-- warning: {warning}")
    return "\n".join(lines) + "\n"


def build_preset(tokens: Dict[str, Any], surface: Dict[str, Any], preset: Dict[str, Any], *,
                 multiplier: Any = 1.0, reduce_motion: bool = False,
                 overrides: Optional[Mapping[str, bool]] = None,
                 intensity_name: Optional[str] = None) -> str:
    """The generated file's body plus header for one preset."""
    body, warnings = render_preset(tokens, surface, preset, multiplier=multiplier,
                                   reduce_motion=reduce_motion, overrides=overrides,
                                   intensity_name=intensity_name)
    problems = sanity_check_lua(body)
    if problems:
        raise AnimationError("rendered Lua failed its structural check: " + "; ".join(problems))
    factor, _clamped = clamp_multiplier(tokens, multiplier)
    return header_note(preset, surface, warnings, intensity_name=intensity_name,
                       multiplier=factor, reduce_motion=reduce_motion,
                       overrides=overrides) + body


def preset_for_render(tokens: Dict[str, Any], intensity_name: str,
                      reduce_motion: bool = False) -> str:
    """The preset a whole-session render uses.

    Under reduce-motion it is the preset the tokens force, not the one the
    intensity is paired with. ``resolve_modifiers`` refuses that pair outright,
    and rightly: a reduce-motion render of some other preset would be a different
    effect on every intensity, which is the one thing the switch must not be. The
    intensity still decides whether motion happens at all, because an intensity
    paired with ``off`` has a master switch that reduces everything to a warp
    anyway.
    """
    if reduce_motion:
        return reduce_motion_preset(tokens)
    return preset_for_intensity(tokens, intensity_name)


def render(tokens: Dict[str, Any], surface: Dict[str, Any],
           intensity_name: str, reduce_motion: bool = False) -> Tuple[str, List[str]]:
    """The Part 2 entry point: render the preset an intensity names.

    ``iarch-theme`` calls this, so applying a theme renders the motion preset that
    intensity is paired with at multiplier 1.0 and with no per-event overrides --
    the theme owns intensity and colour, and the animation state a person set with
    ``iarch-anim`` lives in their settings and is rendered by that tool.

    Reduce-motion is the one piece of that state this honours, because it is an
    accessibility switch rather than a style preference: a person who asked the
    desktop for less motion has to keep it across a colour change, and the GTK
    sheets ``iarch-theme`` renders beside this file are zeroed by the same switch.
    Applying a theme that quietly restored 380ms workspace slides on one side
    while freezing every transition on the other would be worse than either
    behaviour alone. Everything else -- the chosen preset, the speed multiplier
    and the per-event toggles -- stays ``iarch-anim``'s to render, and
    ``iarch-theme`` warns when what it is about to write differs.
    """
    preset_name = preset_for_render(tokens, intensity_name, reduce_motion)
    return render_preset(tokens, surface, load_preset(preset_name),
                         reduce_motion=reduce_motion, intensity_name=intensity_name)


def build(tokens: Dict[str, Any], surface: Dict[str, Any], intensity_name: str,
          reduce_motion: bool = False) -> str:
    preset_name = preset_for_render(tokens, intensity_name, reduce_motion)
    return build_preset(tokens, surface, load_preset(preset_name),
                        reduce_motion=reduce_motion, intensity_name=intensity_name)


def sanity_check_lua(text: str) -> List[str]:
    """Structural checks a missing Lua interpreter cannot do for us.

    Not a parser: it proves the brackets balance and every string terminates,
    which is where a table emitter actually goes wrong. A trailing comma before a
    closing brace is *legal* Lua, and this deliberately does not flag it.
    tests/test_animations_lua.py additionally runs ``luac -p`` when a Lua binary
    exists on the host.
    """
    problems: List[str] = []
    depth = {"(": 0, "{": 0, "[": 0}
    closing = {")": "(", "}": "{", "]": "["}
    in_string = False
    escaped = False
    for index, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in depth:
            depth[char] += 1
        elif char in closing:
            depth[closing[char]] -= 1
            if depth[closing[char]] < 0:
                problems.append(f"unbalanced {char} at offset {index}")
                break
    if in_string:
        problems.append("an unterminated string literal")
    for opener, count in depth.items():
        if count != 0:
            problems.append(f"{count} unclosed {opener}")
    return problems


# ---------------------------------------------------------------- entry points


def label(path: Path) -> str:
    """A path for a message: repository-relative when it is inside the repository."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def target_path(env: Optional[Dict[str, str]] = None) -> Path:
    return configstore.config_dir(env) / "hypr" / "generated" / "animations.lua"


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated will put on disk for ``body``.

    Kept as one expression so --check cannot drift from the write path: the two
    must disagree only when the source changed, never because one of them forgot a
    header or a newline.
    """
    return f"{configstore.header_for(path)}\n{body}\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gen-animations-lua",
                                     description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--intensity",
                        help="render the preset this intensity is paired with "
                             "(default: the tokens' own default_intensity)")
    source.add_argument("--preset",
                        help="render this preset directly: "
                             "smooth, snappy, bouncy, minimal or off")
    parser.add_argument("--speed", type=float, default=None,
                        help="global multiplier, clamped to the token bounds; "
                             "greater than 1 is faster")
    parser.add_argument("--reduce-motion", action="store_true",
                        help="render the reduce-motion preset with every duration capped")
    parser.add_argument("--disable-event", action="append", default=[], metavar="EVENT",
                        help="emit this event as enabled = false (repeatable)")
    parser.add_argument("--enable-event", action="append", default=[], metavar="EVENT",
                        help="emit this event as enabled = true even if the preset disables it "
                             "(repeatable)")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the render to stdout instead of a file")
    parser.add_argument("--write-repo-default", action="store_true",
                        help=f"refresh {label(REPO_DEFAULT)}")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed default matches a fresh render")
    parser.add_argument("--output", type=Path,
                        help="explicit destination (overrides the config dir)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    overrides: Dict[str, bool] = {}
    for leaf in args.disable_event:
        overrides[leaf] = False
    for leaf in args.enable_event:
        if leaf in overrides:
            print(f"animations-lua: --enable-event {leaf} contradicts --disable-event {leaf}",
                  file=sys.stderr)
            return 2
        overrides[leaf] = True

    try:
        tokens = load_tokens()
        surface = load_surface()
        multiplier = multiplier_bounds(tokens)[2] if args.speed is None else args.speed
        if args.preset:
            preset = load_preset(args.preset)
            intensity: Optional[str] = None
        else:
            intensity = resolve_intensity(tokens, args.intensity)
            preset = load_preset(preset_for_intensity(tokens, intensity))
        source = build_preset(tokens, surface, preset, multiplier=multiplier,
                              reduce_motion=args.reduce_motion, overrides=overrides,
                              intensity_name=intensity)
    except AnimationError as exc:
        print(f"animations-lua: {exc}", file=sys.stderr)
        return 2

    source = source.rstrip("\n")

    if args.to_stdout:
        sys.stdout.write(source + "\n")
        return 0

    if args.check:
        if not REPO_DEFAULT.is_file():
            print(f"animations-lua: {label(REPO_DEFAULT)} is missing", file=sys.stderr)
            return 1
        current = REPO_DEFAULT.read_text(encoding="utf-8")
        expected = rendered_text(REPO_DEFAULT, source)
        if current != expected:
            print("animations-lua: the committed default does not match a fresh render of "
                  f"{preset.get('name')!r}"
                  + (f" at intensity {intensity}" if intensity else "")
                  + "; run --write-repo-default", file=sys.stderr)
            return 1
        print(f"animations-lua: {label(REPO_DEFAULT)} matches a fresh render")
        return 0

    destination = args.output or (REPO_DEFAULT if args.write_repo_default else target_path())
    try:
        written = configstore.write_generated(destination, source)
    except (OSError, configstore.ConfigError) as exc:
        print(f"animations-lua: {exc}", file=sys.stderr)
        return 1
    print(f"animations-lua: wrote {written} (preset {preset.get('name')}"
          + (f", intensity {intensity}" if intensity else "") + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
