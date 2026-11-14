#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the Hyprland half of the glass design system into Lua.

Reads ``data/design/tokens.json`` plus one colour preset and writes
``~/.config/hypr/generated/glass.lua``: the ``decoration`` and ``general`` blocks
for the chosen intensity, a layer rule per Noctalia surface and a window rule per
application class group. ``themes/theme.lua`` loads it through a ``pcall``, so a
session that has never run ``iarch-theme`` still starts -- it just starts with
the static values.

Two things make this file safer than a hand-written one:

* it refuses to emit a config leaf that ``data/design/tokens.json`` does not list
  under ``hyprland.leaves``. That list was read out of Hyprland v0.57.2, so an
  invented key fails here, in CI, rather than in the user's session;
* every number it emits is checked against the min/max Hyprland itself enforces,
  taken from the same source. Design tokens may exceed those bounds on purpose
  -- ``radius.pill`` is 999 by CSS convention -- and are clamped with a warning
  in the rendered header, never silently.

Colours are emitted as ``rgba(r, g, b, a)`` with a floating-point alpha and
gradients as ``{ colors = {...}, angle = <degrees> }``: the two forms
``ParserUtils::parseColor`` and ``CLuaConfigGradient::parse`` accept.

Usage:
    python3 iarch/cli/gen_glass_lua.py                      # write to the user config dir
    python3 iarch/cli/gen_glass_lua.py --preset aurora --intensity crystal
    python3 iarch/cli/gen_glass_lua.py --print              # stdout, write nothing
    python3 iarch/cli/gen_glass_lua.py --write-repo-default # refresh .config/hypr/generated/
    python3 iarch/cli/gen_glass_lua.py --check              # repo default matches a fresh render
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
PRESET_DIR = ROOT / "data" / "design" / "presets"
REPO_DEFAULT = ROOT / ".config" / "hypr" / "generated" / "glass.lua"
MODULE_NAME = "generated.glass"

DEFAULT_PRESET = "midnight-glass"


class GlassError(RuntimeError):
    """Raised when the tokens, a preset or a rendered value cannot be trusted."""


# ---------------------------------------------------------------- inputs


def load_tokens() -> Dict[str, Any]:
    try:
        return json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GlassError(f"{TOKENS_PATH}: {exc}") from exc


def load_preset(tokens: Dict[str, Any], preset_id: Optional[str]) -> Dict[str, Any]:
    wanted = preset_id or DEFAULT_PRESET
    path = PRESET_DIR / f"{wanted}.json"
    if not path.is_file():
        raise GlassError(f"no preset {wanted!r} in {PRESET_DIR}")
    try:
        preset = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GlassError(f"{path}: {exc}") from exc
    if preset.get("id") != wanted:
        raise GlassError(f"{path} declares id {preset.get('id')!r}, expected {wanted!r}")
    return preset


def resolve_intensity(tokens: Dict[str, Any], intensity: Optional[str]) -> str:
    name = intensity or tokens.get("default_intensity", "frosted")
    if name not in tokens["intensities"]:
        raise GlassError(f"unknown intensity {name!r}; tokens define "
                         f"{', '.join(sorted(tokens['intensities']))}")
    return name


# ---------------------------------------------------------------- colour and numbers


def parse_hex(value: str, where: str) -> Tuple[int, int, int]:
    text = value.strip()
    if not text.startswith("#") or len(text) != 7:
        raise GlassError(f"{where}: {value!r} is not a #rrggbb colour")
    try:
        return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
    except ValueError as exc:
        raise GlassError(f"{where}: {value!r} has non-hex digits") from exc


def rgba(hex_color: str, alpha: float, where: str) -> str:
    """Hyprland's rgba() form: three bytes and a floating-point alpha."""
    if not 0.0 <= alpha <= 1.0:
        raise GlassError(f"{where}: alpha {alpha} outside 0..1")
    red, green, blue = parse_hex(hex_color, where)
    return f"rgba({red}, {green}, {blue}, {round(alpha, 3)})"


def checked(tokens: Dict[str, Any], leaf: str, value: Any, warnings: List[str]) -> Any:
    """Assert the leaf exists in the verified surface and the value fits its type.

    Two upstream facts make this more than a range check. An unknown key is a
    *config error* for Hyprland's Lua walker -- it reports "unknown config key"
    rather than ignoring it -- so an invented leaf would break the session. And
    ``CLuaConfigInt::parse`` accepts only ``lua_isinteger`` (plus booleans and
    known enum string keys), so a leaf declared ``MS<Int>`` must be fed a JSON
    integer: writing ``10.0`` would fail in the user's session with a type error
    that looks nothing like the real cause.
    """
    hypr = tokens["hyprland"]
    if leaf not in hypr["leaves"]:
        raise GlassError(f"{leaf} is not in hyprland.leaves; the generator must not "
                         f"emit config Hyprland does not know")
    if leaf in hypr.get("integer_leaves", []) and isinstance(value, float):
        if value.is_integer():
            value = int(value)
        else:
            raise GlassError(f"{leaf} = {value} is a fraction, but Hyprland declares "
                             f"it an integer; the Lua config parser rejects floats here")
    bounds = hypr["ranges"].get(leaf)
    if bounds and value is not None and isinstance(value, (int, float)) and not isinstance(value, bool):
        low, high = bounds
        if not low <= value <= high:
            raise GlassError(f"{leaf} = {value} is outside Hyprland's own range "
                             f"[{low}, {high}]")
    return value


def clamped_radius(tokens: Dict[str, Any], role: str, warnings: List[str]) -> int:
    """The radius step for a role, clamped to what decoration:rounding accepts."""
    radius = tokens["radius"]
    value = radius[radius[role]]
    low, high = tokens["hyprland"]["ranges"]["decoration:rounding"]
    if value > high:
        warnings.append(f"radius.{radius[role]} = {value} clamped to {high} for "
                        f"decoration:rounding (pill is a CSS convention, not a "
                        f"compositor value)")
        return int(high)
    if value < low:
        warnings.append(f"radius.{radius[role]} = {value} clamped to {low}")
        return int(low)
    return int(value)


# ---------------------------------------------------------------- lua emission


def lua_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = repr(float(value))
    return text if any(ch in text for ch in ".eE") else f"{text}.0"


def lua_value(value: Any, indent: int) -> str:
    pad = "    " * indent
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return lua_number(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, list):
        inner = ", ".join(lua_value(item, indent) for item in value)
        return f"{{ {inner} }}"
    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = []
        for key, item in value.items():
            lines.append(f"{pad}    {key} = {lua_value(item, indent + 1)},")
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"
    raise GlassError(f"cannot render {value!r} as Lua")


def emit_call(function: str, table: Dict[str, Any]) -> str:
    return f"{function}({lua_value(table, 0)})"


# ---------------------------------------------------------------- the render


def decoration_block(tokens: Dict[str, Any], intensity_name: str,
                     warnings: List[str]) -> Dict[str, Any]:
    intensity = tokens["intensities"][intensity_name]
    blur, glass, shadow, window = (intensity["blur"], intensity["glass"],
                                   intensity["shadow"], intensity["window"])
    # checked() returns the value it validated, coerced to an int where Hyprland
    # declares one. Every numeric leaf is assigned from that return value: taking
    # the token directly instead would let a JSON 10.0 reach the Lua and fail in
    # the session with a type error that points nowhere near its cause.
    size = checked(tokens, "decoration:blur:size", blur["size"], warnings)
    passes = checked(tokens, "decoration:blur:passes", blur["passes"], warnings)
    noise = checked(tokens, "decoration:blur:noise", blur["noise"], warnings)
    contrast = checked(tokens, "decoration:blur:contrast", blur["contrast"], warnings)
    brightness = checked(tokens, "decoration:blur:brightness", blur["brightness"], warnings)
    vibrancy = checked(tokens, "decoration:blur:vibrancy", blur["vibrancy"], warnings)
    if blur["variant"] not in tokens["hyprland"]["blur_variants"]:
        raise GlassError(f"blur variant {blur['variant']!r} is not one Hyprland knows")
    if blur["variant"] in tokens["hyprland"]["animated_blur_variants"]:
        warnings.append(f"blur variant {blur['variant']} animates every frame; "
                        f"it is expensive and belongs to a deliberate choice")
    shadow_range = checked(tokens, "decoration:shadow:range", shadow["range"], warnings)
    render_power = checked(tokens, "decoration:shadow:render_power",
                           shadow["render_power"], warnings)
    shadow_scale = checked(tokens, "decoration:shadow:scale", shadow["scale"], warnings)
    dim_strength = checked(tokens, "decoration:dim_strength", window["dim_strength"], warnings)
    active_opacity = checked(tokens, "decoration:active_opacity",
                             window["active_opacity"], warnings)
    inactive_opacity = checked(tokens, "decoration:inactive_opacity",
                               window["inactive_opacity"], warnings)
    fullscreen_opacity = checked(tokens, "decoration:fullscreen_opacity",
                                 window["fullscreen_opacity"], warnings)

    return {
        "rounding": clamped_radius(tokens, "window", warnings),
        "rounding_power": checked(tokens, "decoration:rounding_power",
                                  tokens["radius"]["power"], warnings),
        "active_opacity": active_opacity,
        "inactive_opacity": inactive_opacity,
        "fullscreen_opacity": fullscreen_opacity,
        "dim_inactive": window["dim_inactive"],
        "dim_strength": dim_strength,
        "dim_modal": checked(tokens, "decoration:dim_modal", True, warnings),
        "blur": {
            "enabled": blur["enabled"],
            "variant": blur["variant"],
            "size": size,
            "passes": passes,
            "noise": noise,
            "contrast": contrast,
            "brightness": brightness,
            "vibrancy": vibrancy,
            "xray": blur["xray"],
            "ignore_opacity": blur["ignore_opacity"],
            "new_optimizations": blur["new_optimizations"],
            "popups": blur["popups"],
            "special": blur["special"],
        },
        "shadow": {
            "enabled": shadow["enabled"],
            "range": shadow_range,
            "render_power": render_power,
            "color": rgba(shadow["color"], glass["shadow_alpha"], "shadow.color"),
            "color_inactive": rgba(shadow["color_inactive"],
                                   glass["shadow_alpha"] * 0.7, "shadow.color_inactive"),
            "offset": [int(shadow["offset"][0]), int(shadow["offset"][1])],
            "scale": shadow_scale,
            "sharp": shadow["sharp"],
        },
    }


def glow_block(tokens: Dict[str, Any], preset: Dict[str, Any],
               intensity_name: str, warnings: List[str]) -> Dict[str, Any]:
    """The inner glow Hyprland draws on a focused window: ``decoration:glow:*``.

    This is the compositor half of the focus cue. The other half is the fade it
    arrives with, which Hyprland drives through the ``fadeGlow`` animation leaf
    (``src/render/decorations/CHyprInnerGlowDecoration.cpp`` calls
    ``initializeAnimations(..., "fadeGlow", "glowangle")`` and then
    ``onWindowFocus()``), so the glow inherits whatever duration and curve the
    active motion preset gives ``fade`` and needs no leaf of its own. That is
    also why an intensity that turns motion off turns the glow off too: with
    every animated variable warped, the glow would snap on instead of fading in,
    which reads as a flash rather than a cue.

    The colour is an accent role, not a hex constant, so the glow belongs to the
    same palette decision as the active border it sits next to.
    """
    glow = tokens["intensities"][intensity_name]["glow"]
    role = glow["role"]
    accent = preset["palette"]["accent"]
    if role not in accent:
        raise GlassError(f"glow references accent role {role!r}, which the preset "
                         f"does not define")
    for leaf in ("decoration:glow:enabled", "decoration:glow:range",
                 "decoration:glow:render_power", "decoration:glow:color",
                 "decoration:glow:color_inactive"):
        if leaf not in tokens["hyprland"]["leaves"]:
            raise GlassError(f"{leaf} is not in hyprland.leaves; the generator must "
                             f"not emit config Hyprland does not know")
    return {
        "enabled": glow["enabled"],
        "range": checked(tokens, "decoration:glow:range", glow["range"], warnings),
        "render_power": checked(tokens, "decoration:glow:render_power",
                                glow["render_power"], warnings),
        "color": rgba(accent[role], glow["alpha"], f"{intensity_name}.glow.alpha"),
        "color_inactive": rgba(accent[role], glow["alpha_inactive"],
                               f"{intensity_name}.glow.alpha_inactive"),
    }


def general_block(tokens: Dict[str, Any], preset: Dict[str, Any],
                  warnings: List[str]) -> Dict[str, Any]:
    layout = tokens["layout"]
    gaps_in = checked(tokens, "general:gaps_in", layout["gaps_in"], warnings)
    gaps_out = checked(tokens, "general:gaps_out", layout["gaps_out"], warnings)
    float_gaps = checked(tokens, "general:float_gaps", layout["float_gaps"], warnings)
    border_size = checked(tokens, "general:border_size", layout["border_size"], warnings)

    accent = preset["palette"]["accent"]
    border = layout["border"]
    for leaf in ("general:col.active_border", "general:col.inactive_border"):
        checked(tokens, leaf, None, warnings)
    active = border["active"]
    for role in (active["from_role"], active["to_role"]):
        if role not in accent:
            raise GlassError(f"border gradient references accent role {role!r}, "
                             f"which the preset does not define")
    return {
        "gaps_in": gaps_in,
        "gaps_out": gaps_out,
        "float_gaps": float_gaps,
        "border_size": border_size,
        "resize_on_border": layout["resize_on_border"],
        "col": {
            "active_border": {
                "colors": [
                    rgba(accent[active["from_role"]], active["from_alpha"],
                         "layout.border.active.from"),
                    rgba(accent[active["to_role"]], active["to_alpha"],
                         "layout.border.active.to"),
                ],
                "angle": border["angle_deg"],
            },
            "inactive_border": rgba(border["inactive"]["color"],
                                    border["inactive"]["alpha"],
                                    "layout.border.inactive"),
        },
    }


SURFACE_METADATA = {"id", "namespace", "description"}
SURFACE_EFFECTS = {"blur", "ignore_alpha", "xray", "blur_popups", "dim_around",
                   "order", "above_lock", "no_screen_share", "no_anim", "animation"}


def layer_rules(tokens: Dict[str, Any], intensity_name: str) -> List[str]:
    """One hl.layer_rule per Noctalia surface, blur following the intensity."""
    blur_on = tokens["intensities"][intensity_name]["blur"]["enabled"]
    calls = []
    for entry in tokens["surfaces"]["entries"]:
        unexpected = set(entry) - SURFACE_METADATA - SURFACE_EFFECTS
        if unexpected:
            raise GlassError(f"surface {entry.get('id', '?')} declares keys that are "
                             f"neither metadata nor a layer rule effect: "
                             f"{', '.join(sorted(unexpected))}")
        effects = {
            "blur": bool(entry["blur"]) and blur_on,
            "ignore_alpha": entry["ignore_alpha"],
            "xray": entry["xray"],
        }
        for optional in ("blur_popups", "dim_around", "order", "above_lock",
                         "no_screen_share", "no_anim", "animation"):
            if optional in entry:
                effects[optional] = entry[optional]
        unknown = set(effects) - set(tokens["hyprland"]["layer_rule_effects"])
        if unknown:
            raise GlassError(f"layer rule for {entry['id']} uses effects Hyprland "
                             f"does not know: {', '.join(sorted(unknown))}")
        calls.append(emit_call("hl.layer_rule", {
            "name": f"iarch-glass-{entry['id']}",
            "match": {"namespace": entry["namespace"]},
            **effects,
        }))
    return calls


#: What a per-app opacity entry from settings.json may look like. The same rule
#: data/schemas/settings.schema.json states, enforced here as well because this
#: generator can be handed any file and a pattern that reaches the compositor's rule
#: engine unanchored matches windows nobody meant.
OPACITY_CLASS = re.compile(r"^[^^$]+$")


def check_overrides(entries: Sequence[Mapping[str, Any]]) -> List[str]:
    """Every way a ``glass.per_app_opacity`` list is unusable, as sentences."""
    problems: List[str] = []
    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        where = f"glass.per_app_opacity[{index}]"
        if not isinstance(entry, Mapping):
            problems.append(f"{where} is not an object")
            continue
        unexpected = set(entry) - {"class", "opacity"}
        if unexpected:
            problems.append(f"{where} declares {', '.join(sorted(unexpected))}, which is "
                            f"neither a class nor an opacity")
        pattern = entry.get("class")
        if not isinstance(pattern, str) or not OPACITY_CLASS.match(pattern):
            problems.append(f"{where} needs a window class with at least one character "
                            f"and no ^ or $ in it: this generator anchors the pattern")
        elif pattern in seen:
            problems.append(f"{where} names {pattern}, which entry {seen[pattern]} already "
                            f"gave an opacity; two rules for one class is a rule that "
                            f"depends on the order they were written in")
        else:
            seen[pattern] = index
        value = entry.get("opacity")
        if not isinstance(value, (int, float)) or isinstance(value, bool) \
                or not 0.0 <= float(value) <= 1.0:
            problems.append(f"{where} needs an opacity between 0.0 and 1.0, and "
                            f"{value!r} is not one")
    return problems


def window_rules(tokens: Dict[str, Any], intensity_name: str,
                 overrides: Optional[Sequence[Mapping[str, Any]]] = None) -> List[str]:
    """Opacity per class group, then the user's own, then fullscreen last so it wins.

    ``overrides`` is ``glass.per_app_opacity`` out of settings.json. Those rules are
    emitted after the token groups and before the fullscreen rule, so a person's own
    choice beats the group default for that class and a fullscreen window is still
    opaque whatever it is: the ordering is the whole semantics of the list, and it is
    why the fullscreen rule stays last rather than being sorted with the rest.
    """
    opacity = tokens["window_opacity"]
    allowed = set(tokens["hyprland"]["window_rule_effects"])
    calls = []

    def guarded(rule_name: str, effects: Dict[str, Any]) -> str:
        """Refuse any effect Hyprland does not know, the same way layer rules do.

        An unknown effect key is a config error for the rule engine, and it would
        only surface in the user's session, so it is caught here instead.
        """
        unknown = set(effects) - allowed - {"name", "match"}
        if unknown:
            raise GlassError(f"window rule {rule_name} uses effects Hyprland does not "
                             f"know: {', '.join(sorted(unknown))}")
        return emit_call("hl.window_rule", effects)

    for group, patterns in tokens["app_classes"].items():
        if group == "_note":
            continue
        value = opacity[group]
        for pattern in patterns:
            rule: Dict[str, Any] = {"match": {"class": pattern}, "opacity": value}
            if group == "opaque_always":
                # Launchers and games keep their own compositing: no blur, no
                # translucency, and no dimming of a game that loses focus.
                rule["no_blur"] = True
                rule["no_dim"] = True
            calls.append(guarded(pattern, rule))
    for entry in overrides or ():
        pattern = str(entry["class"])
        calls.append(guarded(pattern, {
            # Anchored here and not in the settings file: data/schemas/settings.schema.json
            # forbids a ^ or a $ in the value so that the anchoring lives in exactly one
            # place, and this is it.
            "match": {"class": f"^{pattern}$"},
            "opacity": float(entry["opacity"]),
        }))
    # Registered last, so it overrides every group opacity above for any window
    # that is actually fullscreen -- a game, a video, a presentation.
    calls.append(guarded("iarch-glass-fullscreen", {
        "name": "iarch-glass-fullscreen",
        "match": {"fullscreen": True},
        "opacity": opacity["fullscreen_override"],
        "no_blur": True,
        "no_dim": True,
    }))
    return calls


def render(tokens: Dict[str, Any], preset: Dict[str, Any], intensity_name: str,
           overrides: Optional[Sequence[Mapping[str, Any]]] = None
           ) -> Tuple[str, List[str]]:
    """Return (lua source without the generated header, warnings)."""
    warnings: List[str] = []
    decoration = decoration_block(tokens, intensity_name, warnings)
    # The glow is the only decoration whose colour comes from the palette rather
    # than from the intensity, so it is built separately and merged in.
    decoration["glow"] = glow_block(tokens, preset, intensity_name, warnings)
    calls = [
        emit_call("hl.config", {
            "general": general_block(tokens, preset, warnings),
            "decoration": decoration,
        }),
    ]
    calls.extend(layer_rules(tokens, intensity_name))
    calls.extend(window_rules(tokens, intensity_name, overrides))
    body = "\n\n".join(calls) + "\n"
    return body, warnings


def header_note(tokens: Dict[str, Any], preset: Dict[str, Any], intensity_name: str,
                warnings: List[str]) -> str:
    lines = [
        f"-- Source: data/design/tokens.json intensity={intensity_name}, "
        f"preset=data/design/presets/{preset['id']}.json",
        f"-- Verified against Hyprland {tokens['hyprland']['verified_against']}; "
        f"edit the tokens or the preset, then run iarch-theme apply.",
    ]
    if not tokens["surfaces"]["verified"]:
        lines.append("-- Layer namespaces are the documented expectation, not an "
                     "observation: docs/UNVERIFIED.md SES-02.")
        lines.append("-- Run `iarch-doctor layers` inside the session and correct "
                     "tokens.surfaces if they differ.")
    for warning in warnings:
        lines.append(f"-- warning: {warning}")
    return "\n".join(lines) + "\n"


def sanity_check_lua(text: str) -> List[str]:
    """Structural checks a missing Lua interpreter cannot do for us.

    Not a parser: it proves the brackets balance and every string terminates,
    which is where a table emitter actually goes wrong. A trailing comma before
    a closing brace is *legal* Lua and the emitter always emits one, so this
    deliberately does not flag it. tests/test_glass_lua.py additionally runs
    ``luac -p`` when a Lua binary exists on the host.
    """
    problems = []
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


def load_overrides(path: Path) -> List[Dict[str, Any]]:
    """``glass.per_app_opacity`` out of a settings document, checked.

    Raises rather than skipping: an entry this generator cannot anchor is an entry
    that would become a window rule matching something else, and a refusal that names
    the line is the only outcome that does not silently change a window nobody asked
    about.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GlassError(f"{path} could not be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise GlassError(f"{path} is not valid JSON ({exc.msg} at line {exc.lineno})") from exc
    entries = ((document.get("glass") or {}).get("per_app_opacity") or []) \
        if isinstance(document, Mapping) else []
    if not isinstance(entries, list):
        raise GlassError("glass.per_app_opacity is not a list")
    problems = check_overrides(entries)
    if problems:
        raise GlassError("; ".join(problems))
    return [dict(entry) for entry in entries]


def build(tokens: Dict[str, Any], preset: Dict[str, Any], intensity_name: str,
          overrides: Optional[Sequence[Mapping[str, Any]]] = None) -> str:
    body, warnings = render(tokens, preset, intensity_name, overrides)
    problems = sanity_check_lua(body)
    if problems:
        raise GlassError("rendered Lua failed its structural check: "
                         + "; ".join(problems))
    return header_note(tokens, preset, intensity_name, warnings) + body


# ---------------------------------------------------------------- entry points


def label(path: Path) -> str:
    """A path for a message: repository-relative when it is inside the repository."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def target_path(env: Optional[Dict[str, str]] = None) -> Path:
    return configstore.config_dir(env) / "hypr" / "generated" / "glass.lua"


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated will put on disk for ``body``.

    Kept as one expression so --check cannot drift from the write path: the two
    must disagree only when the source changed, never because one of them
    forgot a header or a newline.
    """
    return f"{configstore.header_for(path)}\n{body}\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help=f"preset id (default {DEFAULT_PRESET})")
    parser.add_argument("--intensity",
                        help="crystal, frosted, soft or performance (default: the preset's own)")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the render to stdout instead of a file")
    parser.add_argument("--write-repo-default", action="store_true",
                        help=f"refresh {label(REPO_DEFAULT)}")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed default matches a fresh render")
    parser.add_argument("--output", type=Path,
                        help="explicit destination (overrides the config dir)")
    parser.add_argument("--settings", type=Path,
                        help="a settings.json to read glass.per_app_opacity from; "
                             "ignored by --check and --write-repo-default, because the "
                             "committed default has to be reproducible from the records "
                             "alone and not from whoever is running the command")
    args = parser.parse_args(argv)

    # The repository default is one file rendered from two records, so a person's own
    # per-app opacities cannot be part of it: --check would then fail on every machine
    # that had set one, and the failure would say nothing about the source.
    wanted = bool(args.settings) and not (args.check or args.write_repo_default)
    try:
        tokens = load_tokens()
        preset = load_preset(tokens, args.preset)
        intensity = resolve_intensity(tokens, args.intensity or preset.get("default_intensity"))
        overrides = load_overrides(args.settings) if wanted else None
        source = build(tokens, preset, intensity, overrides)
    except GlassError as exc:
        print(f"glass-lua: {exc}", file=sys.stderr)
        return 2

    source = source.rstrip("\n")

    if args.to_stdout:
        sys.stdout.write(source + "\n")
        return 0

    if args.check:
        if not REPO_DEFAULT.is_file():
            print(f"glass-lua: {label(REPO_DEFAULT)} is missing", file=sys.stderr)
            return 1
        current = REPO_DEFAULT.read_text(encoding="utf-8")
        expected = rendered_text(REPO_DEFAULT, source)
        if current != expected:
            print("glass-lua: the committed default does not match a fresh render of "
                  f"{DEFAULT_PRESET}; run --write-repo-default", file=sys.stderr)
            return 1
        print(f"glass-lua: {label(REPO_DEFAULT)} matches a fresh render")
        return 0

    destination = args.output or (REPO_DEFAULT if args.write_repo_default
                                  else target_path())
    try:
        written = configstore.write_generated(destination, source)
    except (OSError, configstore.ConfigError) as exc:
        print(f"glass-lua: {exc}", file=sys.stderr)
        return 1
    extra = f", {len(overrides)} per-app rule(s)" if wanted and overrides else ""
    print(f"glass-lua: wrote {written} (preset {preset['id']}, intensity {intensity}{extra})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
