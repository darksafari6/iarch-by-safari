#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the Hyprland animation set from the motion design tokens.

Reads the ``motion`` block of ``data/design/tokens.json`` plus the per-intensity
``motion.enabled`` switch, and writes ``~/.config/hypr/generated/animations.lua``:
the named curves (four beziers and one spring) and one ``hl.animation`` call per
compositor leaf the design system owns -- the window open/close/move set, the
workspace switch, the shell layer surfaces, the fade and the focus border.
``animations.lua`` loads it through a ``pcall`` after the static
``animations/default.lua``, so a session that has never run ``iarch-theme`` still
animates -- it just animates with the static baseline, and whatever is required
last wins.

Two things make this safer than the hand-written file it overrides:

* every leaf, curve and style is checked against ``data/design/animations.json``,
  the animation API read out of Hyprland v0.57.2. An invented leaf, a style that
  leaf does not accept, or a curve shape the binding rejects fails here, in CI,
  rather than as a config error in the user's session;
* every ``speed`` is derived from a token duration by the one formula Hyprland
  actually uses -- ``duration_ms = 100 * speed``, from hyprutils
  ``AnimatedVariable::getPercent`` -- so a number is never picked by hand. The
  binding additionally requires ``speed`` in ``(0, 100]``, and the spring values
  must each be strictly greater than 0.5; both are enforced before anything is
  written.

The Performance intensity sets ``motion.enabled = false``. The generator then
emits only ``hl.config({ animations = { enabled = false } })``: Hyprland's
AnimationManager warps every animated variable straight to its final value
(``warp = !*PANIMENABLED || !PAV->enabled()``), so no bezier or spring is stepped
per frame. That is how the Performance preset measurably lowers compositor work;
docs/UNVERIFIED.md PERF-01 records that the frame-time saving itself was not
measured on real hardware.

Usage:
    python3 iarch/cli/gen_animations_lua.py                      # write to the user config dir
    python3 iarch/cli/gen_animations_lua.py --intensity performance
    python3 iarch/cli/gen_animations_lua.py --print              # stdout, write nothing
    python3 iarch/cli/gen_animations_lua.py --write-repo-default # refresh .config/hypr/generated/
    python3 iarch/cli/gen_animations_lua.py --check              # repo default matches a fresh render
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
SURFACE_PATH = ROOT / "data" / "design" / "animations.json"
REPO_DEFAULT = ROOT / ".config" / "hypr" / "generated" / "animations.lua"
MODULE_NAME = "generated.animations"

# Curve names are prefixed so they cannot collide with the static default.lua's
# wind/winIn/winOut/liner or with Hyprland's built-in "default"/"linear".
CURVE_PREFIX = "iarch-"
SPRING_CURVE = CURVE_PREFIX + "spring"

# The four motion.easing entries, in the order they are registered.
EASING_ORDER = ("standard", "emphasized", "decelerate", "accelerate")

# The design-system-owned animation leaves: (leaf, curve, duration token, style).
# ``curve`` is either ("bezier", <easing name>) or ("spring",). ``style`` is None
# for a leaf Hyprland gives no styles (fade, border). Every entry is validated
# against data/design/animations.json before it is emitted, so a leaf that does
# not exist, or a style that leaf does not accept, is refused here rather than
# breaking the session. The purely decorative angle sweeps (borderangle and
# friends) are deliberately left to the static default.lua: they are continuous
# and have no token duration, so they are not part of the open/close/hover set.
LEAF_PLAN: Tuple[Tuple[str, Tuple[str, ...], str, Optional[str]], ...] = (
    ("windows", ("bezier", "standard"), "normal_ms", "slide"),
    ("windowsIn", ("spring",), "normal_ms", "slide"),
    ("windowsOut", ("bezier", "accelerate"), "fast_ms", "slide"),
    ("windowsMove", ("bezier", "standard"), "normal_ms", "slide"),
    ("workspaces", ("bezier", "emphasized"), "slow_ms", "slide"),
    ("specialWorkspace", ("bezier", "emphasized"), "slow_ms", "slide"),
    ("layers", ("bezier", "decelerate"), "normal_ms", "fade"),
    ("layersIn", ("bezier", "decelerate"), "normal_ms", "fade"),
    ("layersOut", ("bezier", "accelerate"), "fast_ms", "fade"),
    ("fade", ("bezier", "standard"), "fast_ms", None),
    ("border", ("bezier", "standard"), "fast_ms", None),
)


class AnimationError(RuntimeError):
    """Raised when the tokens, the surface or a rendered value cannot be trusted."""


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


def resolve_intensity(tokens: Dict[str, Any], intensity: Optional[str]) -> str:
    name = intensity or tokens.get("default_intensity", "frosted")
    if name not in tokens["intensities"]:
        raise AnimationError(f"unknown intensity {name!r}; tokens define "
                             f"{', '.join(sorted(tokens['intensities']))}")
    return name


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


# ---------------------------------------------------------------- validation


def speed_for(surface: Dict[str, Any], duration_ms: Any, where: str) -> float:
    """Turn a token duration in milliseconds into a Hyprland ``speed``.

    Hyprland's ``speed`` is a duration in centiseconds despite the name: from
    hyprutils ``AnimatedVariable::getPercent`` the animation finishes when
    ``(elapsed_ms / 100) / speed`` reaches 1, i.e. after ``100 * speed``
    milliseconds. So ``speed = duration_ms / 100``. The binding rejects
    ``speed <= 0`` and clamps to ``[0, 100]``, so a usable duration is in
    ``(0, 10000]`` ms; both bounds are checked against the recorded surface.
    """
    formula = surface["speed_formula"]
    if not isinstance(duration_ms, (int, float)) or isinstance(duration_ms, bool):
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


def check_leaf(surface: Dict[str, Any], leaf: str, style: Optional[str]) -> None:
    leaves = surface["leaves"]
    if leaf not in leaves:
        raise AnimationError(f"{leaf} is not an animation leaf Hyprland {surface['verified_against']} "
                             f"knows; the generator must not emit it")
    allowed = leaves[leaf]["styles"]
    if style is None:
        if allowed:
            raise AnimationError(f"{leaf} accepts styles {allowed}; the plan must name one, "
                                 f"not omit it")
    elif style not in allowed:
        raise AnimationError(f"{leaf} does not accept style {style!r}; Hyprland allows "
                             f"{allowed or 'no styles'} for it")


def check_bezier(surface: Dict[str, Any], name: str, curve: Dict[str, Any]) -> None:
    if curve.get("type") != "bezier":
        raise AnimationError(f"easing {name!r} is not a bezier curve")
    points = curve.get("points")
    if not isinstance(points, list) or len(points) != 2:
        raise AnimationError(f"easing {name!r}: hl.curve needs exactly 2 bezier points, "
                             f"got {points!r}")
    for point in points:
        if (not isinstance(point, list) or len(point) != 2
                or not all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in point)):
            raise AnimationError(f"easing {name!r}: point {point!r} is not a pair of numbers")


def check_spring(surface: Dict[str, Any], spring: Dict[str, Any]) -> None:
    for key in ("stiffness", "damping", "mass"):
        value = spring.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise AnimationError(f"spring {key!r} is not a number")
        # The binding rejects <= 0.5 with a config error, so the usable bound is
        # strictly greater than 0.5 (the tokens schema allows >= 0.5; this is the
        # tighter, session-true check).
        if value <= 0.5:
            raise AnimationError(f"spring {key} = {value} must be strictly greater than 0.5; "
                                 f"hl.curve rejects it")


# ---------------------------------------------------------------- the render


def render_curves(motion: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """Register the four easing beziers and the spring under iarch- names."""
    easing = motion.get("easing", {})
    calls: List[str] = []
    for name in EASING_ORDER:
        if name not in easing:
            raise AnimationError(f"motion.easing is missing {name!r}")
        curve = easing[name]
        check_bezier(surface, name, curve)
        points = " ".join(
            "{" + ", ".join(lua_number(c) for c in pt) + "}," for pt in curve["points"]
        )
        table = lua_inline_table([
            ("type", lua_string("bezier")),
            ("points", "{ " + points.rstrip(",") + " }"),
        ])
        calls.append(f"hl.curve({lua_string(CURVE_PREFIX + name)}, {table})")
    spring = motion.get("spring")
    if not isinstance(spring, dict):
        raise AnimationError("motion.spring is missing or not an object")
    check_spring(surface, spring)
    table = lua_inline_table([
        ("type", lua_string("spring")),
        ("stiffness", lua_number(spring["stiffness"])),
        ("damping", lua_number(spring["damping"])),
        ("mass", lua_number(spring["mass"])),
    ])
    calls.append(f"hl.curve({lua_string(SPRING_CURVE)}, {table})")
    return calls


def render_leaves(motion: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """One hl.animation call per design-system-owned leaf."""
    calls: List[str] = []
    for leaf, curve, duration_token, style in LEAF_PLAN:
        check_leaf(surface, leaf, style)
        if curve[0] == "spring":
            # The spring is registered once under SPRING_CURVE; nothing to check
            # against the easing set.
            pass
        elif curve[0] == "bezier":
            if curve[1] not in EASING_ORDER:
                raise AnimationError(f"{leaf}: the plan names easing {curve[1]!r}, which "
                                     f"render_curves never registers (it emits "
                                     f"{', '.join(EASING_ORDER)}); the leaf would reference "
                                     f"a curve that does not exist")
        else:
            raise AnimationError(f"{leaf}: curve spec {curve!r} is neither bezier nor spring")
        if duration_token not in motion:
            raise AnimationError(f"motion is missing duration token {duration_token!r}")
        speed = speed_for(surface, motion[duration_token], f"{leaf}.{duration_token}")
        pairs: List[Tuple[str, str]] = [
            ("leaf", lua_string(leaf)),
            ("enabled", lua_number(True)),
            ("speed", lua_number(speed)),
        ]
        if curve[0] == "spring":
            # speed is inert for a spring curve -- getCurveStep advances it by
            # wall-clock DT through advanceSpring and never reads internalSpeed --
            # but the binding still requires speed > 0, so a real value is emitted.
            pairs.append(("spring", lua_string(SPRING_CURVE)))
        else:
            pairs.append(("bezier", lua_string(CURVE_PREFIX + curve[1])))
        if style is not None:
            pairs.append(("style", lua_string(style)))
        calls.append(f"hl.animation({lua_inline_table(pairs)})")
    return calls


def render(tokens: Dict[str, Any], surface: Dict[str, Any],
           intensity_name: str) -> Tuple[str, List[str]]:
    """Return (lua source without the generated header, warnings)."""
    warnings: List[str] = []
    intensity = tokens["intensities"][intensity_name]
    motion_switch = intensity.get("motion")
    if not isinstance(motion_switch, dict) or "enabled" not in motion_switch:
        raise AnimationError(f"intensity {intensity_name!r} has no motion.enabled switch")
    motion = tokens.get("motion")
    if not isinstance(motion, dict):
        raise AnimationError("tokens.json has no motion block")

    enabled = bool(motion_switch["enabled"])
    master = ("hl.config({\n"
              "    animations = {\n"
              f"        enabled = {lua_number(enabled)},\n"
              "    },\n"
              "})")
    if not enabled:
        warnings.append(f"intensity {intensity_name}: animations disabled; Hyprland warps "
                        f"every animated variable to its final value (no per-frame curve work)")
        return master + "\n", warnings

    parts = [master, "", *render_curves(motion, surface), "", *render_leaves(motion, surface)]
    return "\n".join(parts) + "\n", warnings


def header_note(tokens: Dict[str, Any], surface: Dict[str, Any], intensity_name: str,
                warnings: List[str]) -> str:
    lines = [
        f"-- Source: data/design/tokens.json intensity={intensity_name} (motion), "
        f"data/design/animations.json",
        f"-- Verified against Hyprland {surface['verified_against']}; speed = duration_ms / 100 "
        f"(hyprutils AnimatedVariable getPercent).",
        "-- Edit the motion tokens, then run iarch-theme apply.",
    ]
    for warning in warnings:
        lines.append(f"-- warning: {warning}")
    return "\n".join(lines) + "\n"


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


def build(tokens: Dict[str, Any], surface: Dict[str, Any], intensity_name: str) -> str:
    body, warnings = render(tokens, surface, intensity_name)
    problems = sanity_check_lua(body)
    if problems:
        raise AnimationError("rendered Lua failed its structural check: " + "; ".join(problems))
    return header_note(tokens, surface, intensity_name, warnings) + body


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


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--intensity",
                        help="crystal, frosted, soft or performance (default: the tokens' own)")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the render to stdout instead of a file")
    parser.add_argument("--write-repo-default", action="store_true",
                        help=f"refresh {label(REPO_DEFAULT)}")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed default matches a fresh render")
    parser.add_argument("--output", type=Path,
                        help="explicit destination (overrides the config dir)")
    args = parser.parse_args(argv)

    try:
        tokens = load_tokens()
        surface = load_surface()
        intensity = resolve_intensity(tokens, args.intensity)
        source = build(tokens, surface, intensity)
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
            default_intensity = tokens.get("default_intensity", "frosted")
            print("animations-lua: the committed default does not match a fresh render of "
                  f"{default_intensity}; run --write-repo-default", file=sys.stderr)
            return 1
        print(f"animations-lua: {label(REPO_DEFAULT)} matches a fresh render")
        return 0

    destination = args.output or (REPO_DEFAULT if args.write_repo_default else target_path())
    try:
        written = configstore.write_generated(destination, source)
    except (OSError, configstore.ConfigError) as exc:
        print(f"animations-lua: {exc}", file=sys.stderr)
        return 1
    print(f"animations-lua: wrote {written} (intensity {intensity})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
