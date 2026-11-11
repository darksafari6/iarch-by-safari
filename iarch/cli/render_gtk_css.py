#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the GTK 4 and GTK 3 glass overlays from the design tokens.

Both sheets are rendered from the same tokens, presets and intensities as the
compositor and shell renderers, and both are checked against
``data/design/gtk.json`` before anything is written. That check is the reason
this renderer exists as a program rather than as two CSS files in the payload:

* GTK warns about a property it does not know and keeps loading, so a typo
  ships as a widget that quietly keeps the theme default;
* a selector that matches no node or no class is kept and never applies, so the
  sheet looks applied while doing nothing;
* GTK CSS has no ``!important`` at either version -- the word does not appear in
  ``gtkcssprovider.c`` -- so an overlay cannot force its way past the theme. It
  wins on cascade order, because ``~/.config/gtk-4.0/gtk.css`` is parsed after
  the theme, and a rule that has to beat libadwaita must match or exceed its
  specificity.

GTK 4 and GTK 3 are not the same language. ``backdrop-filter``, ``filter``,
``transform``, ``line-height`` and ``@media`` exist only in GTK 4;
``@binding-set`` only in GTK 3; ``:focus-visible`` only in GTK 4, where GTK 3
has ``:focus``, ``:prelight`` and ``:insensitive``. The two templates therefore
differ, and each is validated against its own version's surface, so a GTK 4-only
property cannot leak into the GTK 3 sheet.

Exit codes follow the other renderers: 0 on success, 1 when the repository or
the host is out of step, 2 on a usage or data error.
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
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402

TOKENS_PATH = ROOT / "data" / "design" / "tokens.json"
SURFACE_PATH = ROOT / "data" / "design" / "gtk.json"
PRESET_DIR = ROOT / "data" / "design" / "presets"
TEMPLATE_DIR = ROOT / "iarch" / "lib" / "templates"

DEFAULT_PRESET = "midnight-glass"
VERSIONS = ("4", "3")
REPO_CONFIG = ROOT / ".config"

# Values with no token equivalent, each with the reason it is what it is. A
# number that does vary with the design -- an opacity, a radius, a duration --
# comes from tokens.json instead, never from here.
SHAPE = OrderedDict(
    # GTK's own default header bar height; a taller bar would push the client
    # area down without adding anything the design asks for.
    headerbar_min_height=46,
    # The top highlight is a 1px hairline, so the gradient stops after one
    # pixel and reads as a lit edge rather than a wash.
    highlight_stop=1,
    # A pressed button sinks by 2%. Only GTK 4 can do this at all: transform is
    # not a GTK 3 property, so the GTK 3 sheet uses a darker fill instead.
    press_scale=0.98,
    # Disabled controls keep their shape and lose contrast, so the layout does
    # not move when a control becomes unavailable.
    disabled_opacity=0.45,
    disabled_accent_alpha=0.30,
    placeholder_opacity=0.60,
    dim_opacity=0.65,
    # Fills that sit on top of a translucent surface have to stay translucent
    # themselves, or the glass reads as a hole punched in it.
    selection_alpha=0.32,
    tab_selected_alpha=0.22,
    banner_alpha=0.28,
    fill_alpha=0.85,
    indicator_checked_alpha=0.90,
    switch_checked_alpha=0.90,
    slider_hover_alpha=0.18,
    scrollbar_alpha=0.28,
    scrollbar_hover_alpha=0.45,
    scrollbar_overlay_alpha=0.18,
    scrollbar_min=6,
    scale_trough=4,
    progress_min=6,
    # The accent glow is a shadow with no offset, so it reads as light coming
    # from the control rather than as a second shadow under it.
    glow_px=12,
    glow_alpha=0.28,
    glow_hover_px=18,
    glow_hover_alpha=0.38,
    popover_extra_blur=4,
    popover_lift=0.10,
    dialog_lift=0.06,
    backdrop_falloff=0.50,
    low_shadow_falloff=0.35,
    # A checked indicator and a focused control both draw their ring inside the
    # control, so the ring never changes the layout.
    circular_min=26,
)


class GtkError(RuntimeError):
    """A render was refused, or the data it needs is not usable."""


# --------------------------------------------------------------- loading


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GtkError(f"cannot read {label(path)}: {exc}") from exc


def load_tokens() -> Dict[str, Any]:
    return load_json(TOKENS_PATH)


def load_surface() -> Dict[str, Any]:
    return load_json(SURFACE_PATH)


def load_preset(preset_id: str) -> Dict[str, Any]:
    path = PRESET_DIR / f"{preset_id}.json"
    if not path.is_file():
        known = ", ".join(sorted(p.stem for p in PRESET_DIR.glob("*.json")))
        raise GtkError(f"unknown preset {preset_id!r}; data/design/presets holds {known}")
    return load_json(path)


def resolve_intensity(tokens: Dict[str, Any], preset: Dict[str, Any],
                      wanted: Optional[str]) -> str:
    name = wanted or preset.get("default_intensity") or tokens["default_intensity"]
    if name not in tokens["intensities"]:
        raise GtkError(f"unknown intensity {name!r}; tokens define "
                       f"{', '.join(sorted(tokens['intensities']))}")
    return name


def label(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


# --------------------------------------------------------------- the context


def require(mapping: Dict[str, Any], path: Tuple[str, ...], where: str) -> Any:
    node: Any = mapping
    for key in path:
        if not isinstance(node, dict) or key not in node:
            raise GtkError(f"{where} has no {'.'.join(str(k) for k in path)}")
        node = node[key]
    return node


def bezier(easing: Dict[str, Any], name: str) -> str:
    """A token easing as the cubic-bezier() CSS function."""
    entry = require(easing, (name,), "tokens.motion.easing")
    if entry.get("type") != "bezier":
        raise GtkError(f"tokens.motion.easing.{name} is {entry.get('type')!r}, not a bezier")
    points = entry["points"]
    if len(points) != 2 or any(len(p) != 2 for p in points):
        raise GtkError(f"tokens.motion.easing.{name} must carry two control points")
    for value in (x for point in points for x in point):
        if not 0.0 <= float(value) <= 1.0:
            raise GtkError(f"cubic-bezier handles run 0-1; {name} has {value}")
    return "cubic-bezier(" + ", ".join(f"{float(x):g}" for point in points for x in point) + ")"


def transition_groups(version: str) -> Dict[str, str]:
    """The transition-property values this sheet may use.

    Only properties declared GTK_STYLE_PROPERTY_ANIMATED can be interpolated,
    and a shorthand is never one of them: ``border-color`` expands to four
    longhands at parse time and carries no animated flag of its own, so
    transitioning it does nothing at all. Each group below is checked against
    the version's animated list by :func:`validate_sheet`.
    """
    border = ("border-top-color, border-right-color, "
              "border-bottom-color, border-left-color")
    press = "background-color, box-shadow" + (", transform" if version == "4" else "")
    return OrderedDict(
        fill="background-color",
        fill_border=f"background-color, {border}",
        border=border,
        press=press,
        ring="outline-color, outline-width",
        entry=f"background-color, {border}, outline-color, outline-width",
        indicator=f"background-color, {border}",
        tab=f"background-color, {border}, color",
    )


def build_context(tokens: Dict[str, Any], preset: Dict[str, Any],
                  surface: Dict[str, Any], intensity_name: str,
                  version: str = "4") -> Dict[str, Any]:
    intensity = require(tokens, ("intensities", intensity_name), "tokens.json")
    glass = require(intensity, ("glass",), intensity_name)
    blur = require(intensity, ("blur",), intensity_name)
    shadow = require(intensity, ("shadow",), intensity_name)
    gtk_alpha = require(intensity, ("gtk",), intensity_name)

    radius = tokens["radius"]
    spacing = tokens["spacing"]
    motion = tokens["motion"]
    font = tokens["font"]
    layout = tokens["layout"]
    palette = require(preset, ("palette",), preset["id"])
    accent = require(palette, ("accent",), f"{preset['id']}.palette")
    on_accent = require(palette, ("on_accent",), f"{preset['id']}.palette")

    if "check" not in radius:
        raise GtkError("tokens.radius has no check role; a check box would need "
                       "a radius this renderer chose for itself")

    # An integral width renders as 1px, not 1.0px: both parse, but the sheet is
    # read by people diffing a preset change, and 1.0px is noise in that diff.
    width = float(layout["border_size"])
    border = int(width) if width.is_integer() else width
    border_alpha = float(glass["border_alpha"])
    shadow_alpha = float(glass["shadow_alpha"])
    blur_px = int(blur["size"]) if blur["enabled"] else 0

    def size(role: str) -> int:
        value = radius[role]
        if isinstance(value, str):  # a role naming another role: panel -> lg -> 24
            value = radius[value]
        return int(value)

    # radius.pill is 999, which is larger than any GTK corner wants and would
    # look wrong on a control that is not actually a pill; half the control's
    # own height is what makes an end fully round, and these controls are small.
    pill_clamped = min(int(radius["pill"]), SHAPE["circular_min"])

    colours = OrderedDict(
        background=palette["background"],
        surface=palette["surface"],
        surface_variant=palette["surface_variant"],
        on_surface=palette["on_surface"],
        on_surface_variant=palette["on_surface_variant"],
        outline_variant=palette["outline_variant"],
        shadow=palette["shadow"],
        text_disabled=palette["text_disabled"],
        accent=accent["primary"],
        secondary=accent["secondary"],
        success=accent["success"],
        warning=accent["warning"],
        danger=accent["danger"],
        on_accent=on_accent["primary"],
    )

    shape = OrderedDict(
        y=int(shadow["offset"][1]),
        blur=int(shadow["range"]),
        alpha=shadow_alpha,
        backdrop_alpha=round(shadow_alpha * SHAPE["backdrop_falloff"], 3),
        low_alpha=round(shadow_alpha * SHAPE["low_shadow_falloff"], 3),
        popover_alpha=round(min(1.0, shadow_alpha + SHAPE["popover_lift"]), 3),
        popover_blur=int(shadow["range"]) + SHAPE["popover_extra_blur"],
        dialog_alpha=round(min(1.0, shadow_alpha + SHAPE["dialog_lift"]), 3),
        dialog_blur=int(shadow["range"]),
        strong_border_alpha=round(min(1.0, border_alpha * 2), 3),
        backdrop_border_alpha=round(border_alpha * 0.6, 3),
        margin=int(layout["gaps_out"]),
        headerbar_min_height=SHAPE["headerbar_min_height"],
        headerbar_highlight_stop=SHAPE["highlight_stop"],
        button_highlight_stop=SHAPE["highlight_stop"],
        title_weight=int(font["weights"]["semibold"]),
        subtitle_size=int(font["sizes"]["sm"]),
        press_scale=SHAPE["press_scale"],
        indicator_min=int(font["sizes"]["lg"]),
        scale_slider=int(spacing["lg"]) + 2,
        circular_min=SHAPE["circular_min"],
        **{k: v for k, v in SHAPE.items()
           if k in ("disabled_opacity", "disabled_accent_alpha", "placeholder_opacity",
                    "dim_opacity", "selection_alpha", "tab_selected_alpha", "banner_alpha",
                    "fill_alpha", "indicator_checked_alpha", "switch_checked_alpha",
                    "slider_hover_alpha", "scrollbar_alpha", "scrollbar_hover_alpha",
                    "scrollbar_overlay_alpha", "scrollbar_min", "scale_trough",
                    "progress_min", "glow_px", "glow_alpha", "glow_hover_px",
                    "glow_hover_alpha")},
    )

    return {
        "product": tokens["name"],
        "preset": preset["id"],
        "intensity": intensity_name,
        "verified": surface["verified_against"],
        "c": colours,
        "r": OrderedDict(
            window=size("window"), card=size("card"), button=size("button"),
            input=size("input"), tooltip=size("tooltip"), check=int(radius["check"]),
            pill_clamped=pill_clamped,
        ),
        "o": gtk_alpha,
        "g": OrderedDict(
            tint_alpha=float(glass["tint_alpha"]),
            tint_alpha_strong=float(glass["tint_alpha_strong"]),
            border_alpha=border_alpha,
            highlight_alpha=float(glass["highlight_alpha"]),
            shadow_alpha=shadow_alpha,
            strong_border_alpha=shape["strong_border_alpha"],
            backdrop_border_alpha=shape["backdrop_border_alpha"],
        ),
        "sh": shape,
        "sp": OrderedDict(
            button_y=int(spacing["xs"]), button_x=int(spacing["md"]),
            pill_y=int(spacing["xs"]), pill_x=int(spacing["lg"]),
            circular=int(spacing["xs"]),
            entry_y=int(spacing["xs"]), entry_x=int(spacing["sm"]),
            row_y=int(spacing["xs"]) + 2, row_x=int(spacing["md"]),
            tab=int(spacing["xs"]), tab_y=int(spacing["xs"]), tab_x=int(spacing["sm"]),
            menu_y=int(spacing["xs"]), menu_x=int(spacing["md"]),
            tooltip_y=int(spacing["xs"]), tooltip_x=int(spacing["sm"]),
            toast=int(spacing["sm"]), toast_y=int(spacing["xs"]),
            toast_x=int(spacing["md"]),
            scrollbar=int(spacing["xs"]),
        ),
        "m": OrderedDict(
            fast=int(motion["fast_ms"]), normal=int(motion["normal_ms"]),
            slow=int(motion["slow_ms"]),
            standard=bezier(motion["easing"], "standard"),
            emphasized=bezier(motion["easing"], "emphasized"),
            decelerate=bezier(motion["easing"], "decelerate"),
            accelerate=bezier(motion["easing"], "accelerate"),
        ),
        "t": transition_groups(version),
        "gtk_version": version,
        "border": border,
        "blur_enabled": bool(blur["enabled"]),
        "blur_px": blur_px,
        "blur_popover_px": blur_px + SHAPE["popover_extra_blur"],
    }


# --------------------------------------------------------------- rendering


def render_sheet(version: str, context: Dict[str, Any]) -> str:
    """Render one template. Jinja2 is the template language the .j2 files use."""
    try:
        import jinja2  # noqa: PLC0415  (imported here so --help works without it)
    except ImportError as exc:
        raise GtkError(
            "Jinja2 is required to render the GTK sheets and is not installed. "
            "On Arch it is python-jinja, on Fedora python3-jinja2 "
            "(docs/UNVERIFIED.md TP-16)."
        ) from exc
    if version not in VERSIONS:
        raise GtkError(f"unknown GTK major version {version!r}; this renders {' and '.join(VERSIONS)}")
    path = TEMPLATE_DIR / f"gtk{version}.css.j2"
    if not path.is_file():
        raise GtkError(f"missing template {label(path)}")
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=jinja2.StrictUndefined,   # a missing context key is a bug, not an empty string
        keep_trailing_newline=True,
        autoescape=False,                   # this is CSS, not markup
        trim_blocks=False,
        lstrip_blocks=False,
    )
    try:
        template = env.get_template(path.name)
        text = template.render(**context)
    except jinja2.TemplateError as exc:
        raise GtkError(f"{label(path)} failed to render: {exc}") from exc
    return text.rstrip("\n")


# --------------------------------------------------------------- validation


COMMENT = re.compile(r"/\*.*?\*/", re.S)
AT_RULE = re.compile(r"@([a-z-]+)")
FUNCTION = re.compile(r"(?<![a-zA-Z0-9_-])(-?[a-zA-Z][a-zA-Z0-9]*)\(")
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
FUNC_PSEUDO = re.compile(r":([a-zA-Z-]+)\(([^)]*)\)")
DECLARATION = re.compile(r"\s*([a-zA-Z-][a-zA-Z0-9_-]*)\s*:\s*(.*?)\s*(?:;|$)", re.S)
SELECTOR_PART = re.compile(r"(:{1,2}[a-zA-Z-]+|#[a-zA-Z-]+|\.[a-zA-Z_-][a-zA-Z0-9_-]*"
                           r"|\[[^\]]+\]|[a-zA-Z*][a-zA-Z0-9_-]*|[>+~,*])")


def strip_comments(text: str) -> str:
    return COMMENT.sub(" ", text)


def split_at_blocks(text: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    """Separate top-level at-rules from the rule body of the sheet.

    Only the at-rules the version's provider actually parses are accepted; an
    unknown one is reported rather than passed through.
    """
    at_rules: List[Tuple[str, str]] = []
    body = text
    for name in AT_RULE.findall(text):
        at_rules.append((name, ""))
    # @define-color declarations are statements, not blocks: drop them from the
    # body so the rule scanner does not see a selector without a brace.
    body = re.sub(r"@define-color\s+[a-zA-Z0-9_-]+\s+[^;]+;", " ", body)
    # @media / @keyframes wrap rules; keep the inner rules, remember the wrapper.
    body = re.sub(r"@(media|keyframes|supports)\b[^{]*\{", " ", body)
    return body, at_rules


def validate_sheet(text: str, surface: Dict[str, Any], version: str) -> List[str]:
    """Check a rendered sheet against what this GTK version really parses."""
    problems: List[str] = []
    spec = surface[f"gtk{version}"]
    properties = set(spec["properties"])
    shorthands = set(spec["shorthands"])
    animated = set(spec["animated_properties"])
    at_rules = set(spec["at_rules"])
    pseudos = set(spec["pseudo_classes"])
    colour_fns = set(spec["color_functions"]) | {"linear-gradient", "radial-gradient"}
    filter_fns = set(spec["filter_functions"])
    nodes = set(spec["node_names"]) | set(spec["extra_node_names"])
    transforms = set(spec.get("transform_functions", []))
    classes = set(spec["style_classes"]) | set(spec.get("libadwaita_style_classes", []))
    known = properties | shorthands

    clean = strip_comments(text)
    if "important" in clean.replace("! important", "!important"):
        problems.append("!important: GTK CSS does not support it at any version, so this "
                        "would be a parse error rather than an override")

    body, found_at = split_at_blocks(clean)
    for name, _ in found_at:
        if name not in at_rules:
            problems.append(f"@{name}: GTK {version} does not parse this at-rule "
                            f"(it accepts {', '.join(sorted(at_rules))})")

    for match in RULE.finditer(body):
        selector, declarations = match.group(1).strip(), match.group(2)
        if not selector or not declarations.strip():
            continue
        for problem in check_selector(selector, nodes, classes, pseudos, version):
            problems.append(problem)
        for problem in check_declarations(declarations, known, animated, colour_fns,
                                          filter_fns, transforms, version):
            problems.append(f"{selector.splitlines()[0].strip()}: {problem}")
    return problems


def check_selector(selector: str, nodes: set, classes: set, pseudos: set,
                   version: str) -> List[str]:
    problems: List[str] = []
    for group in selector.split(","):
        group = group.strip()
        if not group:
            continue
        for name, argument in FUNC_PSEUDO.findall(group):
            if name not in pseudos:
                problems.append(f"{group}: :{name}() is not a pseudo-class GTK {version} parses")
            elif name == "dir" and argument.strip() not in ("ltr", "rtl"):
                problems.append(f"{group}: :dir({argument.strip()}) takes only ltr or rtl")
        # the argument of a functional pseudo-class is not a node name
        text = FUNC_PSEUDO.sub(lambda m: ":" + m.group(1), group)
        for token in SELECTOR_PART.findall(text):
            if token in (">", "+", "~", ",", "*"):
                continue
            if token.startswith("["):
                problems.append(f"{group}: {token} is an attribute selector, which the GTK "
                                f"{version} selector engine does not parse")
                continue
            if token.startswith("::"):
                problems.append(f"{group}: {token} is a pseudo-element; GTK has none")
                continue
            if token.startswith(":"):
                name = token[1:]
                if name not in pseudos:
                    problems.append(f"{group}: {token} is not a pseudo-class GTK {version} "
                                    f"parses (it has {', '.join(sorted(pseudos))})")
                continue
            if token.startswith("#"):
                continue  # a widget name set by the application; always parseable
            if token.startswith("."):
                name = token[1:]
                if name not in classes:
                    problems.append(f"{group}: {token} is not a style class the GTK {version} "
                                    "theme or libadwaita uses, so no widget carries it and the "
                                    "rule silently matches nothing")
                continue
            if token not in nodes:
                problems.append(f"{group}: {token} is not a node name GTK {version} has, so the "
                                "rule silently matches nothing")
    return problems


def check_declarations(declarations: str, known: set, animated: set, colour_fns: set,
                       filter_fns: set, transforms: set, version: str) -> List[str]:
    problems: List[str] = []
    for match in DECLARATION.finditer(declarations):
        name, value = match.group(1), match.group(2).strip()
        if name not in known:
            near = sorted(n for n in known if n.startswith(name.split("-")[0]))[:4]
            problems.append(f"{name}: GTK {version} has no such property"
                            + (f"; did you mean {', '.join(near)}?" if near else ""))
            continue
        if name == "transition-property":
            for item in (part.strip() for part in value.split(",")):
                if item in ("all", "none"):
                    continue
                if item not in animated:
                    problems.append(
                        f"transition-property: {item} is not declared "
                        "GTK_STYLE_PROPERTY_ANIMATED, so it cannot be interpolated and the "
                        "transition silently does nothing")
        for function in FUNCTION.findall(value):
            if function in ("cubic-bezier",):
                continue
            if name in ("backdrop-filter", "filter"):
                if function not in filter_fns:
                    problems.append(f"{name}: {function}() is not a filter function GTK "
                                    f"{version} parses")
            elif name in ("transform", "transform-origin"):
                if function not in transforms:
                    problems.append(f"{name}: {function}() is not a transform function GTK "
                                    f"{version} parses")
            elif function not in colour_fns and function not in ("calc", "min", "max"):
                # Anything else that looks like a function call in a value is
                # either a gradient, a colour function or an invention.
                if function.endswith("gradient"):
                    continue
                problems.append(f"{name}: {function}() is not a function GTK {version} parses")
        if name in ("backdrop-filter", "filter") and version == "3":
            problems.append(f"{name}: GTK 3 has no filter support at all")
    return problems


# --------------------------------------------------------------- writing


def targets_for(version: str, tokens: Dict[str, Any], preset: Dict[str, Any],
                surface: Dict[str, Any], intensity: str,
                root: Optional[Path] = None) -> Tuple[Path, str]:
    context = build_context(tokens, preset, surface, intensity, version)
    body = render_sheet(version, context)
    problems = validate_sheet(body, surface, version)
    if problems:
        raise GtkError(f"the rendered GTK {version} sheet uses something GTK {version} does not "
                       "have, so it would warn and half-apply:\n  " + "\n  ".join(problems))
    base = root if root is not None else Path.home() / ".config" / f"gtk-{version}.0"
    return base / "gtk.css", body


def rendered_text(path: Path, body: str) -> str:
    """Exactly what configstore.write_generated puts on disk for ``body``."""
    return f"{configstore.header_for(path)}\n{body}\n"


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
    """Write every sheet, or leave the filesystem exactly as it was."""
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


def provenance(context: Dict[str, Any], surface: Dict[str, Any], versions: Sequence[str]) -> str:
    verified = surface["verified_against"]
    return "\n".join([
        f"# Preset {context['preset']}, intensity {context['intensity']}.",
        f"# Verified against GTK {verified['gtk4']} (4.x sheet) and GTK {verified['gtk3']} "
        f"(3.x sheet), libadwaita {verified['libadwaita']}.",
        f"# Sheets rendered: {', '.join(f'gtk-{v}.0/gtk.css' for v in versions)}.",
    ])


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help=f"preset id (default {DEFAULT_PRESET})")
    parser.add_argument("--intensity", help="crystal, frosted, soft or performance")
    parser.add_argument("--gtk", choices=VERSIONS + ("both",), default="both",
                        help="which sheet to render (default both)")
    parser.add_argument("--print", action="store_true", dest="to_stdout",
                        help="write the rendered sheet to stdout instead of a file")
    parser.add_argument("--output-dir", type=Path,
                        help="write gtk-4.0/ and gtk-3.0/ under this directory")
    parser.add_argument("--check", action="store_true",
                        help="verify sheets already written match a fresh render")
    parser.add_argument("--write-repo-default", action="store_true",
                        help="refresh the shipped payload under .config/gtk-{4.0,3.0}/")
    parser.add_argument("--repo", action="store_true",
                        help="with --check, verify the shipped payload rather than $HOME")
    args = parser.parse_args(argv)

    versions = VERSIONS if args.gtk == "both" else (args.gtk,)
    try:
        tokens = load_tokens()
        surface = load_surface()
        preset = load_preset(args.preset or DEFAULT_PRESET)
        intensity = resolve_intensity(tokens, preset, args.intensity)
        if args.output_dir:
            root = lambda v: args.output_dir / f"gtk-{v}.0"  # noqa: E731
        elif args.write_repo_default or (args.check and args.repo):
            root = lambda v: REPO_CONFIG / f"gtk-{v}.0"  # noqa: E731
        else:
            root = lambda v: None  # noqa: E731
        targets = [targets_for(version, tokens, preset, surface, intensity, root(version))
                   for version in versions]
    except GtkError as exc:
        print(f"gtk: {exc}", file=sys.stderr)
        return 2

    if args.to_stdout:
        for (path, body) in targets:
            header = configstore.header_for(path)
            sys.stdout.write(f"/* ==== {label(path)} ==== */\n{header}\n{body}\n\n")
        return 0

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
                print(f"gtk: {line}", file=sys.stderr)
            return 1
        print(f"gtk: {len(targets)} sheet(s) match a fresh render for GTK "
              f"{surface['verified_against']['gtk4']} and "
              f"{surface['verified_against']['gtk3']}")
        return 0

    try:
        written = write_all(targets)
    except (OSError, configstore.ConfigError) as exc:
        print(f"gtk: {exc}", file=sys.stderr)
        return 1
    for path in written:
        print(f"gtk: wrote {label(path)}")
    print(f"gtk: preset {preset['id']}, intensity {intensity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
