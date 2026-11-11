#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the Qt/Kvantum half of the glass design system.

Writes two files from ``data/design/tokens.json`` and a colour preset:

* ``~/.config/Kvantum/kvantum.kvconfig`` -- the pointer that tells Kvantum which
  theme to load (a single top-level ``theme=`` key);
* ``~/.config/Kvantum/iarch/iarch.kvconfig`` -- the theme itself: a ``[%General]``
  section carrying the compositor and translucency decisions, and a
  ``[GeneralColors]`` section carrying all 28 colours Kvantum reads, each mapped
  from a role in the preset's palette.

Kvantum is a Qt style chosen in qt6ct, not with ``QT_STYLE_OVERRIDE`` (qt6ct asks
the user to remove that variable). This project ships an INI-only theme: Kvantum
compiles in a default SVG, so a ``.kvconfig`` with no art of its own still
resolves every element, and the file only recolours and re-tunes it.

Everything the theme may say is verified against Kvantum V1.1.9 and recorded in
``data/design/kvantum.json``: the exact set of keys ``ThemeConfig.cpp`` reads,
each key's type, the integer bounds and enum values the documentation states.
That matters because Kvantum is *forgiving*: QSettings parses an unknown key and
``ThemeConfig.cpp`` simply never asks for it, and an out-of-range integer is
clamped and continues. A typo therefore does not fail -- it silently ships a
setting that does nothing, or a value the engine quietly changed. This renderer
treats both as errors and refuses to write.

Two decisions come from running under Hyprland rather than KDE, and are recorded
in the surface file's ``compositor`` block:

* ``blurring`` and ``popup_blurring`` need the KDE blur effect, which Hyprland
  does not provide, so both are false. The frosted look is a translucent interior
  (``reduce_window_opacity`` / ``reduce_menu_opacity``, derived from the
  intensity's ``qt`` opacities) plus the compositor blur in
  ``.config/hypr/generated/glass.lua``.
* Hyprland already shadows popups through ``decoration:shadow``, so
  ``shadowless_popup`` is true and the menu/tooltip shadow depths are 0: a second
  Kvantum shadow would double the one the compositor draws.

Usage:
    python3 iarch/cli/render_kvantum.py                     # write into the user config dir
    python3 iarch/cli/render_kvantum.py --preset aurora --intensity crystal
    python3 iarch/cli/render_kvantum.py --print             # theme .kvconfig to stdout
    python3 iarch/cli/render_kvantum.py --write-repo-default  # refresh the shipped payload
    python3 iarch/cli/render_kvantum.py --check             # shipped payload matches a render
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
SURFACE_PATH = ROOT / "data" / "design" / "kvantum.json"
PRESET_DIR = ROOT / "data" / "design" / "presets"
REPO_POINTER = ROOT / ".config" / "Kvantum" / "kvantum.kvconfig"
REPO_THEME = ROOT / ".config" / "Kvantum" / "iarch" / "iarch.kvconfig"

DEFAULT_PRESET = "midnight-glass"
THEME_NAME = "iarch"
COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")


class KvantumError(RuntimeError):
    """Raised when a render would write something Kvantum does not accept."""


# --------------------------------------------------------------- product choices
#
# Values no design token can supply: the sizing, layout and compositor keys whose
# verified defaults (or, where noted, a deliberate choice) this theme writes. The
# translucency keys are NOT here -- they are derived from the intensity below.
# Each entry is (key, value); the value's type is checked against the surface.
SHAPE: Tuple[Tuple[str, Any], ...] = (
    # Compositor cooperation. Wayland is always composited, so composite stays
    # true; what varies is how translucent each surface is (derived, below).
    ("composite", True),
    # Kvantum's own screen blur needs the KDE effect; Hyprland has no KDE blur,
    # so the frosted look is a translucent interior plus the compositor blur.
    ("blurring", False),
    ("popup_blurring", False),
    # Hyprland shadows popups through decoration:shadow, so Kvantum must not add
    # a second one; the depths go to 0 with it.
    ("shadowless_popup", True),
    ("menu_shadow_depth", 0),
    ("tooltip_shadow_depth", 0),
    # menu/tooltip_blur_radius are not screen blur: they round the corners of a
    # translucent popup when compositing, to avoid artifacts. The doc recommends 2.
    ("menu_blur_radius", 2),
    ("tooltip_blur_radius", 2),
    # Sizing at the verified defaults, so the theme does not silently resize
    # widgets away from what Kvantum's own default theme ships.
    ("menu_separator_height", 10),
    ("scroll_width", 12),
    ("slider_width", 8),
    ("check_size", 13),
    # Layout: margin at its default; spacing lifted from 2 to 4 so widgets in a
    # translucent window are not packed edge to edge (still inside the 2-16 bound).
    ("layout_margin", 4),
    ("layout_spacing", 4),
    # Follow the platform's dialog button order rather than forcing a DE's.
    ("dialog_button_layout", 0),
    # Smooth widget state transitions, matching the motion the tokens define for
    # the rest of the desktop.
    ("animate_states", True),
)

# Provenance for the theme file, written as ";" comments (Qt's INI comment char).
AUTHOR = "iArch"


# --------------------------------------------------------------- inputs


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KvantumError(f"{label(path)}: {exc}") from exc


def load_tokens() -> Dict[str, Any]:
    return load_json(TOKENS_PATH)


def load_surface() -> Dict[str, Any]:
    return load_json(SURFACE_PATH)


def load_preset(preset_id: str) -> Dict[str, Any]:
    path = PRESET_DIR / f"{preset_id}.json"
    if not path.is_file():
        raise KvantumError(f"no preset {preset_id!r} in {label(PRESET_DIR)}")
    preset = load_json(path)
    if preset.get("id") != preset_id:
        raise KvantumError(f"{label(path)} declares id {preset.get('id')!r}, "
                           f"expected {preset_id!r}")
    return preset


def resolve_intensity(tokens: Dict[str, Any], preset: Dict[str, Any],
                      wanted: Optional[str]) -> str:
    name = wanted or preset.get("default_intensity") or tokens["default_intensity"]
    if name not in tokens["intensities"]:
        raise KvantumError(f"unknown intensity {name!r}; tokens define "
                           f"{', '.join(sorted(tokens['intensities']))}")
    return name


def label(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


# --------------------------------------------------------------- colours


def palette_color(palette: Dict[str, Any], role: str) -> str:
    """Resolve a dotted palette role (``accent.primary``) to its #rrggbb value."""
    node: Any = palette
    for part in role.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KvantumError(f"palette has no role {role!r} (missing {part!r})")
        node = node[part]
    if not isinstance(node, str) or not COLOR_RE.match(node):
        raise KvantumError(f"palette role {role!r} is not a #rrggbb colour: {node!r}")
    return node


def build_colors(preset: Dict[str, Any], surface: Dict[str, Any]) -> "OrderedDict[str, str]":
    """All 28 [GeneralColors] keys, each taken from the role the surface names."""
    palette = preset["palette"]
    spec = surface["sections"]["GeneralColors"]["keys"]
    out: "OrderedDict[str, str]" = OrderedDict()
    for key in spec:  # the surface's order is the verified, stable order
        out[key] = palette_color(palette, spec[key]["palette_role"])
    return out


# --------------------------------------------------------------- the theme document


def reduce_opacity(fill: float) -> int:
    """Kvantum reduces opacity by a percentage; the tokens state the fill kept.

    ``reduce_window_opacity`` is how much of the window opacity to *remove* (0-90),
    so a surface the tokens want at 88% fill becomes a 12% reduction. Clamped to
    the documented bound; the validator checks it again against the surface.
    """
    return max(0, min(90, round((1.0 - fill) * 100)))


def build_general(tokens: Dict[str, Any], intensity_name: str) -> "OrderedDict[str, Any]":
    qt = tokens["intensities"][intensity_name]["qt"]
    general: "OrderedDict[str, Any]" = OrderedDict()
    general["author"] = AUTHOR
    general["comment"] = ("Glass theme rendered from data/design/tokens.json; "
                          "do not edit, run iarch-theme apply.")
    for key, value in SHAPE:
        general[key] = value
    # Translucency, derived from the intensity. A window the tokens want opaque
    # (Performance) gets reduce_window_opacity 0, and translucent_windows follows:
    # with no reduction and no translucent SVG element Kvantum disables it anyway,
    # so stating it explicitly keeps the file honest about what it does.
    win = reduce_opacity(qt["window"])
    general["translucent_windows"] = win > 0
    general["reduce_window_opacity"] = win
    general["reduce_menu_opacity"] = reduce_opacity(qt["menu"])
    return general


def build_theme(tokens: Dict[str, Any], preset: Dict[str, Any],
                intensity_name: str, surface: Dict[str, Any]) -> "OrderedDict[str, Any]":
    return OrderedDict([
        ("%General", build_general(tokens, intensity_name)),
        ("GeneralColors", build_colors(preset, surface)),
    ])


# --------------------------------------------------------------- validation


def validate(doc: Dict[str, Any], surface: Dict[str, Any]) -> List[str]:
    """Refuse any key, integer bound, enum value or colour Kvantum would not read."""
    problems: List[str] = []
    sections = surface["sections"]
    for section, values in doc.items():
        if section not in sections:
            problems.append(f"[{section}] is not a section Kvantum reads")
            continue
        spec = sections[section]["keys"]
        for key, value in values.items():
            if key not in spec:
                problems.append(f"[{section}] {key} is not a key ThemeConfig.cpp reads")
                continue
            key_spec = spec[key]
            kind = key_spec["type"]
            if kind == "bool":
                if not isinstance(value, bool):
                    problems.append(f"[{section}] {key} must be true/false, got {value!r}")
            elif kind in ("int", "int_or_string"):
                if isinstance(value, bool) or not isinstance(value, int):
                    problems.append(f"[{section}] {key} must be an integer, got {value!r}")
                    continue
                bounds = key_spec.get("range", {})
                if "min" in bounds and value < bounds["min"]:
                    problems.append(f"[{section}] {key}={value} is below the minimum {bounds['min']}")
                if "max" in bounds and value > bounds["max"]:
                    problems.append(f"[{section}] {key}={value} is above the maximum {bounds['max']}")
                if "enum" in key_spec and value not in key_spec["enum"]["values"]:
                    problems.append(f"[{section}] {key}={value} is not one of "
                                    f"{key_spec['enum']['values']}")
            elif kind == "color":
                if not isinstance(value, str) or not COLOR_RE.match(value):
                    problems.append(f"[{section}] {key} must be a #rrggbb colour, got {value!r}")
            elif kind == "string":
                if not isinstance(value, str):
                    problems.append(f"[{section}] {key} must be a string, got {value!r}")
            elif kind == "float":
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    problems.append(f"[{section}] {key} must be a number, got {value!r}")
            else:
                problems.append(f"[{section}] {key} has an unhandled type {kind!r} in the surface")
    return problems


# --------------------------------------------------------------- emission


def ini_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def provenance(preset: Dict[str, Any], surface: Dict[str, Any], intensity_name: str) -> str:
    return "\n".join([
        f"; Source: data/design/tokens.json intensity={intensity_name}, "
        f"preset=data/design/presets/{preset['id']}.json.",
        f"; Keys, types, integer bounds and enums verified against Kvantum "
        f"{surface['verified_against']}; see data/design/kvantum.json.",
        "; Edit the tokens, the preset or SHAPE in iarch/cli/render_kvantum.py, "
        "then run iarch-theme apply.",
    ])


def emit_theme(doc: Dict[str, Any], header: str) -> str:
    lines: List[str] = [header.rstrip("\n"), ""]
    for section, values in doc.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key}={ini_scalar(value)}")
        lines.append("")
    # No trailing newline: write_generated adds exactly one, and a body that
    # already ended in one would leave a blank line at the end of the file.
    return "\n".join(lines).rstrip("\n")


def emit_pointer(header: str) -> str:
    """The theme chooser: a single top-level ``theme=`` key, no section."""
    return "\n".join([
        header.rstrip("\n"),
        "",
        f"; Kvantum loads ~/.config/Kvantum/{THEME_NAME}/{THEME_NAME}.kvconfig.",
        f"theme={THEME_NAME}",
    ])


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
            path.parent.mkdir(parents=True, exist_ok=True)
            saved.append((path, path.read_bytes() if path.is_file() else None))
            written.append(configstore.write_generated(path, body, env))
    except BaseException:
        for path, blob in reversed(saved):
            restore(path, blob)
        raise
    return written


def targets_for(tokens: Dict[str, Any], surface: Dict[str, Any], preset: Dict[str, Any],
                intensity_name: str, root: Optional[Path] = None) -> List[Tuple[Path, str]]:
    base = root or (configstore.config_dir() / "Kvantum")
    theme = build_theme(tokens, preset, intensity_name, surface)
    problems = validate(theme, surface)
    if problems:
        raise KvantumError("rendered theme is not valid for Kvantum "
                           f"{surface['verified_against']}:\n  " + "\n  ".join(problems))
    header = provenance(preset, surface, intensity_name)
    return [
        (base / "kvantum.kvconfig", emit_pointer(header)),
        (base / THEME_NAME / f"{THEME_NAME}.kvconfig", emit_theme(theme, header)),
    ]


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated puts on disk for ``body``."""
    return f"{configstore.header_for(path)}\n{body}\n"


# --------------------------------------------------------------- CLI


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help=f"preset id (default {DEFAULT_PRESET})")
    parser.add_argument("--intensity", help="crystal, frosted, soft or performance")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the rendered theme .kvconfig to stdout")
    parser.add_argument("--write-repo-default", action="store_true",
                        help="refresh the shipped payload under .config/Kvantum/")
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
            theme = build_theme(tokens, preset, intensity, surface)
            problems = validate(theme, surface)
            if problems:
                raise KvantumError("render is not valid:\n  " + "\n  ".join(problems))
            sys.stdout.write(emit_theme(theme, provenance(preset, surface, intensity)) + "\n")
            return 0

        root = REPO_POINTER.parent if (args.write_repo_default or args.check) else args.output_dir
        targets = targets_for(tokens, surface, preset, intensity, root)
    except KvantumError as exc:
        print(f"kvantum: {exc}", file=sys.stderr)
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
                print(f"kvantum: {line}", file=sys.stderr)
            print("kvantum: run --write-repo-default", file=sys.stderr)
            return 1
        print(f"kvantum: {len(targets)} shipped file(s) match a fresh render of "
              f"Kvantum {surface['verified_against']} settings")
        return 0

    try:
        written = write_all(targets)
    except (OSError, configstore.ConfigError) as exc:
        print(f"kvantum: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"kvantum: wrote {label(path)}")
    print(f"kvantum: preset {preset['id']}, intensity {intensity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
