#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the Noctalia half of the glass design system.

Writes two kinds of file from ``data/design/tokens.json`` and a colour preset:

* ``~/.config/noctalia/config.toml`` -- bar, dock, panels, notifications and the
  settings window, with the geometry and translucency the tokens define;
* ``~/.config/noctalia/palettes/iarch-<preset>.json`` -- the 16 ``m``-prefixed
  colours Noctalia reads, plus its optional terminal block, taken from the
  preset's palette and terminal colours.

Everything the shell needs to know is verified against Noctalia v5.4.1 and
recorded in ``data/design/noctalia.json``: which keys exist, which are enums and
what their values are, which carry a numeric range, and which take a colour role
rather than a number. That matters more here than anywhere else in the design
system, because Noctalia is *forgiving*: an unknown key is a warning and an
out-of-range number is clamped and continues. A typo therefore does not fail --
it silently ships a setting that does nothing, or a value the shell quietly
changed. This renderer treats both as errors and refuses to write.

Product choices that no token can decide -- which widgets sit in the bar, where
panels open, whether the launcher tracks usage -- live in ``PROFILE`` below with
their reasons, so the render is reproducible from the repository alone.

Usage:
    python3 iarch/cli/render_noctalia.py                     # write into the user config dir
    python3 iarch/cli/render_noctalia.py --preset aurora --intensity crystal
    python3 iarch/cli/render_noctalia.py --print             # config.toml to stdout
    python3 iarch/cli/render_noctalia.py --write-repo-default  # refresh the shipped payload
    python3 iarch/cli/render_noctalia.py --check             # shipped payload matches a render
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import tomllib
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
SURFACE_PATH = ROOT / "data" / "design" / "noctalia.json"
PRESET_DIR = ROOT / "data" / "design" / "presets"
REPO_CONFIG = ROOT / ".config" / "noctalia" / "config.toml"
REPO_PALETTES = ROOT / ".config" / "noctalia" / "palettes"

DEFAULT_PRESET = "midnight-glass"

# Motion baseline the animation speed is measured against: Noctalia's speed is a
# multiplier (0.1-4.0), so 1.0 means "our normal duration", and a token that
# asked for faster motion scales it up.
MOTION_BASELINE_MS = 220


class NoctaliaError(RuntimeError):
    """Raised when a render would write something Noctalia does not accept."""


# --------------------------------------------------------------- product choices
#
# Values no design token can supply. Each one is a decision about what the shell
# shows, not about how it looks, so it lives here rather than in tokens.json.

PROFILE: Dict[str, Any] = OrderedDict(
    theme_sync_color_scheme=True,
    theme_pure_black_dark=False,
    # Borders on inputs, cards and popups but not on every button: a 1px light
    # edge is what makes a translucent surface readable, and button borders on
    # top of pill fills turn the shell into wireframe.
    button_borders=False,
    input_borders=True,
    popup_borders=True,
    card_borders=True,
    show_close_buttons=True,
    # Left empty on purpose: fontconfig resolves sans-serif to the design
    # system's interface face, so the shell follows the font stack instead of
    # pinning a family name here.
    font_family="",
    time_format="{:%H:%M}",
    date_format="%a, %x",
    settings_show_advanced=False,
    settings_expand_all_groups=False,
    app_icon_colorize=False,
    clipboard_enabled=True,
    clipboard_confirm_clear_history=True,
    shadow_direction="down",
    panel_borders=True,
    panel_list_item_background=False,
    floating_layer="overlay",
    placements=OrderedDict(
        launcher="floating", clipboard="floating", control_center="floating",
        wallpaper="floating", session="floating", polkit="floating",
    ),
    positions=OrderedDict(
        launcher="center", clipboard="center", control_center="top_right",
        wallpaper="center", session="center", polkit="center",
    ),
    open_near_click_control_center=True,
    launcher=OrderedDict(
        layout="full", width=760, search_position="bottom", default_view="recent",
        categories=True, show_navigation_labels=True, show_settings_button=True,
        show_session_button=True, show_icons=True, track_usage=True, sort_by_usage=True,
    ),
    bar_order=["default"],
    bar_position="top",
    bar=OrderedDict(
        enabled=True, auto_hide=False, reserve_space=True, thickness=40,
        contact_shadow=False, margin_ends=14, margin_edge=8, padding=12,
        widget_spacing=8, scale=1.0, font_scale=1.0, capsule=True,
        capsule_border_width=1,
        start=["launcher", "workspaces"],
        center=["clock"],
        end=["media", "tray", "network", "bluetooth", "volume", "brightness",
             "battery", "notifications", "control-center", "session"],
    ),
    dock=OrderedDict(
        enabled=True, position="bottom", active_monitor_only=False, icon_size=44,
        main_axis_padding=18, cross_axis_padding=10, item_spacing=8, layer="top",
        margin_ends=0, margin_edge=12, show_running=True, auto_hide=False,
        reserve_space=False, active_scale=1.05, inactive_scale=0.90,
        # Magnification is the one piece of motion the dock owns, and it is cheap:
        # a scale on hover, no blur and no framebuffer pass.
        magnification=True, magnification_scale=1.18,
    ),
    control_center=OrderedDict(sidebar="full", width=700),
    notification=OrderedDict(
        enable_daemon=True, show_app_name=True, show_actions=True,
        position="top_right", layer="top", scale=1.0, width=380,
        offset_x=18, offset_y=12, collapse_on_dismiss=True,
        keep_dismissed_in_history=True, max_visible=4, history_retention_hours=168,
    ),
    audio=OrderedDict(
        enable_sounds=True,
        # Notification sounds off: the shell should not speak for applications
        # that already make their own noise.
        enable_notification_sounds=False,
        enable_volume_sounds=True, enable_power_sounds=True,
        enable_screenshot_sounds=True, sound_volume=0.38, sound_theme="freedesktop",
    ),
)

# Colour roles, not hex values, so every edge follows the active palette.
BORDER_ROLE = "outline_variant"
FILL_ROLE = "surface_container"

SECTION_COMMENTS: Dict[str, str] = {
    "theme": "Palette selection. source = custom points at palettes/<custom_palette>.json.",
    "shell": "Shell-wide appearance. Radii, borders and translucency come from the tokens.",
    "shell.animation": "Speed is motion.normal_ms measured against a 220 ms baseline.",
    "shell.shadow": "Panel shadow: the intensity's shadow alpha, or nothing when shadows are off.",
    "shell.panel": "Floating panels: launcher, control centre, session, polkit, wallpaper picker.",
    "shell.launcher": "Launcher layout and content.",
    "bar": "Bars live at the config root: order names them, [bar.<name>] configures each.",
    "dock": "Dock geometry and magnification.",
    "control_center": "Control centre layout.",
    "notification": "Notification toasts.",
    "audio": "Shell sounds. Notification sounds are off by design.",
}


# --------------------------------------------------------------- inputs


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoctaliaError(f"{label(path)}: {exc}") from exc


def load_tokens() -> Dict[str, Any]:
    return load_json(TOKENS_PATH)


def load_surface() -> Dict[str, Any]:
    return load_json(SURFACE_PATH)


def load_preset(preset_id: str) -> Dict[str, Any]:
    path = PRESET_DIR / f"{preset_id}.json"
    if not path.is_file():
        raise NoctaliaError(f"no preset {preset_id!r} in {label(PRESET_DIR)}")
    preset = load_json(path)
    if preset.get("id") != preset_id:
        raise NoctaliaError(f"{label(path)} declares id {preset.get('id')!r}, "
                            f"expected {preset_id!r}")
    return preset


def resolve_intensity(tokens: Dict[str, Any], preset: Dict[str, Any],
                      wanted: Optional[str]) -> str:
    name = wanted or preset.get("default_intensity") or tokens["default_intensity"]
    if name not in tokens["intensities"]:
        raise NoctaliaError(f"unknown intensity {name!r}; tokens define "
                            f"{', '.join(sorted(tokens['intensities']))}")
    return name


def label(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


# --------------------------------------------------------------- the config document


def corner_radius_scale(tokens: Dict[str, Any]) -> float:
    """How far the shell's own radii are scaled, to land on the panel radius.

    Noctalia multiplies its internal base radii by ``shell.corner_radius_scale``
    and does not document the base, so this asks for the token's panel radius
    against its medium radius -- the same 24 px the compositor's floating panels
    get -- and the result is tuned by eye (docs/UNVERIFIED.md UI-04).
    """
    radius = tokens["radius"]
    scale = radius[radius["panel"]] / radius["md"]
    return round(min(2.0, max(0.0, scale)), 2)


def animation_speed(tokens: Dict[str, Any]) -> float:
    speed = MOTION_BASELINE_MS / tokens["motion"]["normal_ms"]
    return round(min(4.0, max(0.1, speed)), 2)


def theme_section(preset: Dict[str, Any]) -> Dict[str, Any]:
    return OrderedDict(
        mode=preset["mode"],
        shell_mode=preset["mode"],
        source="custom",
        custom_palette=preset["noctalia"]["palette_id"],
        sync_color_scheme=PROFILE["theme_sync_color_scheme"],
        pure_black_dark=PROFILE["theme_pure_black_dark"],
    )


def shell_section(tokens: Dict[str, Any], intensity: Dict[str, Any]) -> Dict[str, Any]:
    glass, shadow, shell = intensity["glass"], intensity["shadow"], intensity["shell"]
    section = OrderedDict(
        corner_radius_scale=corner_radius_scale(tokens),
        button_borders=PROFILE["button_borders"],
        input_borders=PROFILE["input_borders"],
        popup_borders=PROFILE["popup_borders"],
        card_borders=PROFILE["card_borders"],
        show_close_buttons=PROFILE["show_close_buttons"],
        popup_shadows=bool(shadow["enabled"]),
        font_family=PROFILE["font_family"],
        time_format=PROFILE["time_format"],
        date_format=PROFILE["date_format"],
        telemetry_enabled=False,
        settings_window_translucent=bool(shell["settings_translucent"]),
        settings_show_advanced=PROFILE["settings_show_advanced"],
        settings_expand_all_groups=PROFILE["settings_expand_all_groups"],
        app_icon_colorize=PROFILE["app_icon_colorize"],
        clipboard_enabled=PROFILE["clipboard_enabled"],
        clipboard_confirm_clear_history=PROFILE["clipboard_confirm_clear_history"],
    )
    section["animation"] = OrderedDict(
        enabled=tokens["motion"]["normal_ms"] > 0,
        speed=animation_speed(tokens),
    )
    section["shadow"] = OrderedDict(
        direction=PROFILE["shadow_direction"],
        alpha=float(glass["shadow_alpha"]),
    )
    panel = OrderedDict(
        transparency_mode=shell["panel_transparency"],
        borders=PROFILE["panel_borders"],
        border_color=BORDER_ROLE,
        border_width=float(tokens["layout"]["border_size"]),
        shadow=bool(shadow["enabled"]),
        list_item_background=PROFILE["panel_list_item_background"],
        floating_layer=PROFILE["floating_layer"],
        floating_offset=tokens["layout"]["float_gaps"],
        open_near_click_control_center=PROFILE["open_near_click_control_center"],
    )
    for name, value in PROFILE["placements"].items():
        panel[f"{name}_placement"] = value
    for name, value in PROFILE["positions"].items():
        panel[f"{name}_position"] = value
    section["panel"] = panel
    section["launcher"] = OrderedDict(PROFILE["launcher"])
    return section


def bar_section(tokens: Dict[str, Any], intensity: Dict[str, Any]) -> Dict[str, Any]:
    shell, blur, shadow = intensity["shell"], intensity["blur"], intensity["shadow"]
    layout, radius = tokens["layout"], tokens["radius"]
    panel_radius = radius[radius["panel"]]
    capsule_radius = float(radius[radius["card"]])
    bar = OrderedDict(PROFILE["bar"])
    fields = OrderedDict(
        position=PROFILE["bar_position"],
        enabled=bar["enabled"],
        auto_hide=bar["auto_hide"],
        reserve_space=bar["reserve_space"],
        thickness=bar["thickness"],
        background_opacity=float(shell["bar_opacity"]),
        compositor_blur=bool(blur["enabled"]),
        border=BORDER_ROLE,
        border_width=float(layout["border_size"]),
        shadow=bool(shadow["enabled"]),
        contact_shadow=bar["contact_shadow"],
        # A bar has four corner radii and no single "radius": the plain key only
        # exists on a per-monitor override, where it would be silently ignored.
        radius_top_left=panel_radius,
        radius_top_right=panel_radius,
        radius_bottom_left=panel_radius,
        radius_bottom_right=panel_radius,
        margin_ends=bar["margin_ends"],
        margin_edge=bar["margin_edge"],
        padding=bar["padding"],
        widget_spacing=bar["widget_spacing"],
        scale=bar["scale"],
        font_scale=bar["font_scale"],
        capsule=bar["capsule"],
        capsule_fill=FILL_ROLE,
        capsule_opacity=float(shell["capsule_opacity"]),
        capsule_border=BORDER_ROLE,
        capsule_border_width=bar["capsule_border_width"],
        capsule_radius=capsule_radius,
        start=bar["start"],
        center=bar["center"],
        end=bar["end"],
    )
    return OrderedDict(order=list(PROFILE["bar_order"]), default=fields)


def dock_section(tokens: Dict[str, Any], intensity: Dict[str, Any]) -> Dict[str, Any]:
    shell, blur, shadow = intensity["shell"], intensity["blur"], intensity["shadow"]
    dock = OrderedDict(PROFILE["dock"])
    return OrderedDict(
        enabled=dock["enabled"],
        position=dock["position"],
        active_monitor_only=dock["active_monitor_only"],
        icon_size=dock["icon_size"],
        main_axis_padding=dock["main_axis_padding"],
        cross_axis_padding=dock["cross_axis_padding"],
        item_spacing=dock["item_spacing"],
        background_opacity=float(shell["dock_opacity"]),
        compositor_blur=bool(blur["enabled"]),
        border=BORDER_ROLE,
        border_width=float(tokens["layout"]["border_size"]),
        shadow=bool(shadow["enabled"]),
        radius=tokens["radius"][tokens["radius"]["panel"]],
        margin_ends=dock["margin_ends"],
        margin_edge=dock["margin_edge"],
        show_running=dock["show_running"],
        auto_hide=dock["auto_hide"],
        reserve_space=dock["reserve_space"],
        layer=dock["layer"],
        active_scale=dock["active_scale"],
        inactive_scale=dock["inactive_scale"],
        magnification=dock["magnification"],
        magnification_scale=dock["magnification_scale"],
    )


def notification_section(tokens: Dict[str, Any], intensity: Dict[str, Any]) -> Dict[str, Any]:
    notification = OrderedDict(PROFILE["notification"])
    notification["background_opacity"] = float(intensity["shell"]["notification_opacity"])
    notification["border"] = True
    notification["border_color"] = BORDER_ROLE
    notification["border_width"] = float(tokens["layout"]["border_size"])
    return notification


def render_config(tokens: Dict[str, Any], preset: Dict[str, Any],
                  intensity_name: str) -> Dict[str, Any]:
    intensity = tokens["intensities"][intensity_name]
    return OrderedDict(
        theme=theme_section(preset),
        shell=shell_section(tokens, intensity),
        bar=bar_section(tokens, intensity),
        dock=dock_section(tokens, intensity),
        control_center=OrderedDict(PROFILE["control_center"]),
        notification=notification_section(tokens, intensity),
        audio=OrderedDict(PROFILE["audio"]),
    )


# --------------------------------------------------------------- validation


def validate(doc: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """Check a rendered document against the verified Noctalia surface.

    Returns a list of problems rather than raising, so one run reports every
    mistake instead of the first.
    """
    problems: List[str] = []
    sections = surface["sections"]
    roles = set(surface["color_roles"])
    container_keys = set(surface["bar_container"]["keyed_outside_fields"])

    def check_value(path: str, spec: Dict[str, Any], value: Any) -> None:
        kind = spec.get("type")
        if kind == "bool" and not isinstance(value, bool):
            problems.append(f"{path}: {value!r} is not a boolean")
        elif kind == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            problems.append(f"{path}: {value!r} is not an integer")
        elif kind == "float" and not isinstance(value, (int, float)):
            problems.append(f"{path}: {value!r} is not a number")
        elif kind == "string" and not isinstance(value, str):
            problems.append(f"{path}: {value!r} is not a string")
        elif kind == "array" and not isinstance(value, list):
            problems.append(f"{path}: {value!r} is not an array")
        if "enum" in spec and value not in spec["enum"]:
            problems.append(f"{path}: {value!r} is not one of {spec['enum']}")
        if "range" in spec and isinstance(value, (int, float)) and not isinstance(value, bool):
            low, high = spec["range"][0], spec["range"][1]
            if not low <= value <= high:
                problems.append(f"{path}: {value} is outside [{low}, {high}] "
                                f"({spec.get('range_constant', 'range')}); Noctalia would "
                                f"clamp it and only warn")
        if spec.get("color") and isinstance(value, str):
            if value and value not in roles and not value.startswith("#"):
                problems.append(f"{path}: {value!r} is neither a colour role nor a hex colour")

    def walk(values: Dict[str, Any], spec: Dict[str, Any], path: str,
             allow_container: bool = False) -> None:
        keys = spec["keys"]
        for key, value in values.items():
            here = f"{path}.{key}" if path else key
            if key not in keys:
                if allow_container and key in container_keys:
                    continue
                problems.append(f"{here}: Noctalia {surface['verified_against']} has no such "
                                f"setting; it would warn 'unknown setting' and ignore it")
                continue
            entry = keys[key]
            if isinstance(value, dict):
                if "keys" not in entry:
                    problems.append(f"{here}: is a table but the setting is not")
                else:
                    walk(value, entry, here)
                continue
            check_value(here, entry, value)

    for name, values in doc.items():
        if name == "bar":
            order = values.get("order")
            if not isinstance(order, list) or not order:
                problems.append("bar.order: must be a non-empty array of bar names")
            for key, value in values.items():
                if key == "order":
                    continue
                if not isinstance(value, dict):
                    problems.append(f"bar.{key}: a bar must be a table")
                    continue
                if key not in order:
                    problems.append(f"bar.{key}: not listed in bar.order")
                walk(value, sections["bar.default"], f"bar.{key}", allow_container=True)
            continue
        spec = sections.get(name)
        if spec is None:
            problems.append(f"{name}: no verified schema section")
            continue
        walk(values, spec, name)

    for extra in order_only(doc):
        problems.append(extra)
    return problems


def order_only(doc: Dict[str, Any]) -> List[str]:
    """bar.order must name every bar present, and nothing else."""
    bar = doc.get("bar", {})
    names = {key for key in bar if key != "order"}
    listed = set(bar.get("order", []))
    if names - listed:
        return [f"bar.order does not name {sorted(names - listed)}"]
    if listed - names:
        return [f"bar.order names {sorted(listed - names)}, which are not defined"]
    return []


# --------------------------------------------------------------- TOML emission


def toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = repr(float(value))
        return text if any(ch in text for ch in ".eE") else f"{text}.0"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_scalar(item) for item in value) + "]"
    raise NoctaliaError(f"cannot render {value!r} as TOML")


def emit_toml(doc: Dict[str, Any], header: str) -> str:
    lines: List[str] = [header.rstrip("\n"), ""]

    def table(values: Dict[str, Any], path: str) -> None:
        comment = SECTION_COMMENTS.get(path)
        if comment:
            lines.append(f"# {comment}")
        lines.append(f"[{path}]")
        for key, value in values.items():
            if not isinstance(value, dict):
                lines.append(f"{key} = {toml_scalar(value)}")
        lines.append("")
        for key, value in values.items():
            if isinstance(value, dict):
                table(value, f"{path}.{key}")

    for name, values in doc.items():
        table(values, name)
    # No trailing newline: write_generated adds exactly one, and a body that
    # already ended in one would leave a blank line at the end of the file.
    return "\n".join(lines).rstrip("\n")


def provenance(tokens: Dict[str, Any], preset: Dict[str, Any],
               surface: Dict[str, Any], intensity_name: str) -> str:
    return "\n".join([
        f"# Source: data/design/tokens.json intensity={intensity_name}, "
        f"preset=data/design/presets/{preset['id']}.json.",
        f"# Keys, enums and ranges verified against Noctalia {surface['verified_against']}; "
        f"see data/design/noctalia.json.",
        "# Edit the tokens, the preset or PROFILE in iarch/cli/render_noctalia.py, "
        "then run iarch-theme apply.",
    ])


# --------------------------------------------------------------- palettes

# Material's tertiary slot is the palette's third accent hue; success is the
# third designed accent in every preset, and error maps to danger exactly.
PALETTE_MAP: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("mPrimary", ("accent", "primary")),
    ("mOnPrimary", ("on_accent", "primary")),
    ("mSecondary", ("accent", "secondary")),
    ("mOnSecondary", ("on_accent", "secondary")),
    ("mTertiary", ("accent", "success")),
    ("mOnTertiary", ("on_accent", "success")),
    ("mError", ("accent", "danger")),
    ("mOnError", ("on_accent", "danger")),
    ("mSurface", ("surface",)),
    ("mOnSurface", ("on_surface",)),
    ("mSurfaceVariant", ("surface_variant",)),
    ("mOnSurfaceVariant", ("on_surface_variant",)),
    ("mOutline", ("outline",)),
    ("mShadow", ("shadow",)),
    # hover has no preset colour of its own: outline_variant is the palette's
    # designed step up from surface_variant, so a highlight is a chosen colour
    # rather than a computed blend.
    ("mHover", ("outline_variant",)),
    ("mOnHover", ("on_surface",)),
)

ANSI_NORMAL = ("color0", "color1", "color2", "color3", "color4", "color5", "color6", "color7")
ANSI_BRIGHT = ("color8", "color9", "color10", "color11", "color12", "color13", "color14", "color15")
ANSI_NAMES = ("black", "red", "green", "yellow", "blue", "magenta", "cyan", "white")


def dig(palette: Dict[str, Any], path: Tuple[str, ...]) -> str:
    node: Any = palette
    for step in path:
        if not isinstance(node, dict) or step not in node:
            raise NoctaliaError(f"preset palette has no {'.'.join(path)}")
        node = node[step]
    if not isinstance(node, str):
        raise NoctaliaError(f"preset palette {'.'.join(path)} is not a colour")
    return node


def palette_mode(preset: Dict[str, Any]) -> Dict[str, Any]:
    """One mode block of a Noctalia palette: 16 colours plus the terminal set."""
    palette = preset["palette"]
    block: Dict[str, Any] = OrderedDict()
    for key, path in PALETTE_MAP:
        block[key] = dig(palette, path)

    terminal = preset.get("terminal", {}).get("colors")
    if terminal:
        for required in ("background", "foreground", "cursor", "cursor_text",
                         "selection_background", "selection_foreground",
                         *ANSI_NORMAL, *ANSI_BRIGHT):
            if required not in terminal:
                raise NoctaliaError(f"preset {preset['id']} terminal colors has no {required}")
        block["terminal"] = OrderedDict(
            background=terminal["background"],
            foreground=terminal["foreground"],
            cursor=terminal["cursor"],
            cursorText=terminal["cursor_text"],
            selectionBg=terminal["selection_background"],
            selectionFg=terminal["selection_foreground"],
            normal=OrderedDict(zip(ANSI_NAMES, (terminal[name] for name in ANSI_NORMAL))),
            bright=OrderedDict(zip(ANSI_NAMES, (terminal[name] for name in ANSI_BRIGHT))),
        )
    return block


def render_palette(preset: Dict[str, Any]) -> Dict[str, Any]:
    """Both mode variants of a palette, the second taken from its counterpart.

    Noctalia uses the dark variant for both modes when light is omitted, so a
    dark-only palette would silently render dark in light mode. Rather than
    invent a light variant, each preset names the preset that supplies the mode
    it does not have.
    """
    counterpart = preset["noctalia"]["counterpart"]
    other = load_preset(counterpart["preset"])
    if other["mode"] != counterpart["mode"]:
        raise NoctaliaError(f"preset {preset['id']} names {other['id']} as its "
                            f"{counterpart['mode']} counterpart, but that preset is "
                            f"{other['mode']}")
    if other["mode"] == preset["mode"]:
        raise NoctaliaError(f"preset {preset['id']} and its counterpart share the mode "
                            f"{preset['mode']}")
    modes = {preset["mode"]: palette_mode(preset), other["mode"]: palette_mode(other)}
    return OrderedDict(dark=modes["dark"], light=modes["light"])


def validate_palette(document: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    spec = surface["palette"]
    fields, groups = spec["fields"], spec["terminal_groups"]
    for mode in spec["modes"]:
        block = document.get(mode)
        if not isinstance(block, dict):
            problems.append(f"palette has no {mode!r} variant")
            continue
        for field in fields:
            value = block.get(field)
            if not isinstance(value, str) or not value.startswith("#") or len(value) != 7:
                problems.append(f"palette {mode}.{field} must be a #rrggbb colour, got {value!r}")
        unknown = set(block) - set(fields) - {"terminal"}
        if unknown:
            problems.append(f"palette {mode} carries keys Noctalia does not read: "
                            f"{', '.join(sorted(unknown))}")
        terminal = block.get("terminal")
        if terminal is None:
            continue
        if not isinstance(terminal, dict):
            problems.append(f"palette {mode}.terminal must be a table")
            continue
        for field in spec["terminal_fields"]:
            if field not in terminal:
                problems.append(f"palette {mode}.terminal has no {field}")
        for group in groups:
            colours = terminal.get(group)
            if not isinstance(colours, dict) or set(colours) != set(spec["terminal_ansi"]):
                problems.append(f"palette {mode}.terminal.{group} must define exactly "
                                f"{spec['terminal_ansi']}")
    return problems


# --------------------------------------------------------------- writing


def restore(path: Path, blob: Optional[bytes]) -> None:
    """Put a file back the way it was, atomically, during a rollback."""
    try:
        if blob is None:
            path.unlink(missing_ok=True)
            return
        handle = tempfile.NamedTemporaryFile("wb", dir=str(path.parent),
                                             prefix=f".{path.name}.", suffix=".rollback",
                                             delete=False)
        tmp = Path(handle.name)
        try:
            with handle:
                handle.write(blob)
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    except OSError:
        pass  # the backups in ~/.local/state/iarch/backups are the second net


def write_all(targets: Sequence[Tuple[Path, str]],
              env: Optional[Dict[str, str]] = None) -> List[Path]:
    """Write every file, or leave the filesystem exactly as it was."""
    saved: List[Tuple[Path, Optional[bytes]]] = []
    written: List[Path] = []
    try:
        for path, body in targets:
            saved.append((path, path.read_bytes() if path.is_file() else None))
            written.append(configstore.write_generated(path, body, env))
    except BaseException:
        for path, blob in reversed(saved):
            restore(path, blob)
        raise
    return written


def user_targets(tokens: Dict[str, Any], surface: Dict[str, Any], preset: Dict[str, Any],
                 intensity_name: str, root: Optional[Path] = None) -> List[Tuple[Path, str]]:
    base = root or (configstore.config_dir() / "noctalia")
    config = render_config(tokens, preset, intensity_name)
    problems = validate(config, surface)
    if problems:
        raise NoctaliaError("rendered config.toml is not valid for Noctalia "
                            f"{surface['verified_against']}:\n  " + "\n  ".join(problems))
    body = emit_toml(config, provenance(tokens, preset, surface, intensity_name))
    try:
        tomllib.loads(body)
    except tomllib.TOMLDecodeError as exc:
        raise NoctaliaError(f"rendered config.toml does not parse: {exc}") from exc

    palette = render_palette(preset)
    palette_problems = validate_palette(palette, surface)
    if palette_problems:
        raise NoctaliaError("rendered palette is not valid:\n  " + "\n  ".join(palette_problems))
    return [
        (base / "config.toml", body),
        (base / "palettes" / f"{preset['noctalia']['palette_id']}.json",
         json.dumps(palette, indent=2, ensure_ascii=False) + "\n"),
    ]


def repo_targets(tokens: Dict[str, Any], surface: Dict[str, Any]) -> List[Tuple[Path, str]]:
    """The shipped payload: the default preset's config and every preset's palette."""
    targets = user_targets(tokens, surface, load_preset(DEFAULT_PRESET),
                           tokens["default_intensity"], REPO_CONFIG.parent)
    palettes = []
    for path in sorted(PRESET_DIR.glob("*.json")):
        preset = load_json(path)
        document = render_palette(preset)
        problems = validate_palette(document, surface)
        if problems:
            raise NoctaliaError(f"palette for {preset['id']} is not valid:\n  "
                                + "\n  ".join(problems))
        palettes.append((REPO_PALETTES / f"{preset['noctalia']['palette_id']}.json",
                         json.dumps(document, indent=2, ensure_ascii=False) + "\n"))
    # user_targets already produced the chosen preset's palette; keep one copy.
    seen = {path for path, _ in targets}
    return targets + [item for item in palettes if item[0] not in seen]


# --------------------------------------------------------------- CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help=f"preset id (default {DEFAULT_PRESET})")
    parser.add_argument("--intensity", help="crystal, frosted, soft or performance")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the rendered config.toml to stdout")
    parser.add_argument("--write-repo-default", action="store_true",
                        help="refresh the shipped payload under .config/noctalia/")
    parser.add_argument("--check", action="store_true",
                        help="verify the shipped payload matches a fresh render")
    parser.add_argument("--output-dir", type=Path,
                        help="write into this directory instead of the user config dir")
    args = parser.parse_args(argv)

    try:
        tokens = load_tokens()
        surface = load_surface()
        preset = load_preset(args.preset or DEFAULT_PRESET)
        intensity = resolve_intensity(tokens, preset, args.intensity)

        if args.to_stdout:
            config = render_config(tokens, preset, intensity)
            problems = validate(config, surface)
            if problems:
                raise NoctaliaError("render is not valid:\n  " + "\n  ".join(problems))
            sys.stdout.write(emit_toml(config, provenance(tokens, preset, surface, intensity)) + "\n")
            return 0

        targets = (repo_targets(tokens, surface) if args.write_repo_default or args.check
                   else user_targets(tokens, surface, preset, intensity, args.output_dir))
    except NoctaliaError as exc:
        print(f"noctalia: {exc}", file=sys.stderr)
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
                print(f"noctalia: {line}", file=sys.stderr)
            print("noctalia: run --write-repo-default", file=sys.stderr)
            return 1
        print(f"noctalia: {len(targets)} shipped file(s) match a fresh render of "
              f"Noctalia {surface['verified_against']} settings")
        return 0

    try:
        written = write_all(targets)
    except (OSError, configstore.ConfigError) as exc:
        print(f"noctalia: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"noctalia: wrote {label(path)}")
    print(f"noctalia: preset {preset['id']}, intensity {intensity}")
    return 0


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated puts on disk for ``body``."""
    if path.suffix == ".json":
        data = json.loads(body)
        return json.dumps({"_generated": configstore.GENERATED_HEADER, **data},
                          indent=2, ensure_ascii=False) + "\n"
    return f"{configstore.header_for(path)}\n{body}\n"


if __name__ == "__main__":
    sys.exit(main())
