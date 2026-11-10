#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""WCAG contrast gate for the glass presets.

Every colour preset in ``data/design/presets/`` is checked before it can be
applied: text roles must reach 4.5:1 against the surfaces they are drawn on,
and non-text UI boundaries (outlines, disabled text) must reach 3:1. The ratios
are the WCAG 2.1 ones -- relative luminance from linearised sRGB, contrast as
(L1 + 0.05) / (L2 + 0.05) -- so a number printed here is the number a screen
reader user or an auditor would compute.

Usage:
    python3 iarch/cli/contrast_check.py                 # every preset
    python3 iarch/cli/contrast_check.py --preset aurora  # one preset
    python3 iarch/cli/contrast_check.py --json           # machine readable
    python3 iarch/cli/contrast_check.py --min 7.0        # stricter gate
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
PRESET_DIR = ROOT / "data" / "design" / "presets"

# WCAG 2.1, 1.4.3 Contrast (Minimum) for text, 1.4.11 for non-text UI.
MIN_TEXT_RATIO = 4.5
MIN_UI_RATIO = 3.0
# Colours that are measured and printed but never gated. Two kinds of colour
# belong here, and both are deliberate design decisions rather than gaps:
#   * a decorative hairline (outline_variant). WCAG 1.4.11 covers the boundary
#     "needed to identify" a component; the glass highlight is not that
#     boundary, the focus ring is, and the ring is gated at 3:1.
#   * ANSI colour 0 and 8, the black / bright-black pair. Terminals use them for
#     dimmed comments on purpose, so a low ratio there is the intent.
INFO_RATIO = 1.0


class ContrastError(RuntimeError):
    """Raised when a colour cannot be interpreted or a preset is incomplete."""


class Pair(NamedTuple):
    """One foreground/background combination and the ratio it must reach."""

    label: str
    foreground: str
    background: str
    minimum: float
    kind: str  # "text", "ui" (gated) or "info" (measured, never gated)


class Result(NamedTuple):
    label: str
    foreground: str
    background: str
    ratio: float
    minimum: float
    kind: str

    @property
    def passed(self) -> bool:
        return self.ratio >= self.minimum


def parse_hex(value: str, where: str = "colour") -> Tuple[int, int, int]:
    """Read ``#rgb``, ``#rrggbb`` or ``#rrggbbaa`` into 8-bit channels.

    Alpha is dropped on purpose: contrast is measured against the composited
    surface, and the presets store composited colours.
    """
    if not isinstance(value, str):
        raise ContrastError(f"{where}: expected a string, got {type(value).__name__}")
    text = value.strip()
    if not text.startswith("#"):
        raise ContrastError(f"{where}: {value!r} is not a #-prefixed hex colour")
    body = text[1:]
    if len(body) == 3:
        body = "".join(ch * 2 for ch in body)
    if len(body) not in (6, 8):
        raise ContrastError(f"{where}: {value!r} is not 3, 6 or 8 hex digits")
    try:
        red = int(body[0:2], 16)
        green = int(body[2:4], 16)
        blue = int(body[4:6], 16)
    except ValueError as exc:
        raise ContrastError(f"{where}: {value!r} has non-hex digits") from exc
    return red, green, blue


def relative_luminance(rgb: Sequence[int]) -> float:
    """WCAG 2.1 relative luminance of an sRGB colour."""
    channels = []
    for value in rgb[:3]:
        scaled = value / 255.0
        channels.append(scaled / 12.92 if scaled <= 0.04045 else ((scaled + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    """Contrast ratio between two hex colours, 1.0 to 21.0."""
    lum_a = relative_luminance(parse_hex(first, "foreground"))
    lum_b = relative_luminance(parse_hex(second, "background"))
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def blend(foreground: str, background: str, alpha: float) -> str:
    """Composite ``foreground`` over ``background`` at ``alpha`` (0..1).

    Used for the translucent fills the glass design is built on: a tint at 34 %
    over the wallpaper is not the tint colour, and measuring the tint alone
    would overstate how much contrast the text really has.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ContrastError(f"blend alpha {alpha} is outside 0..1")
    top = parse_hex(foreground, "blend foreground")
    bottom = parse_hex(background, "blend background")
    mixed = tuple(round(t * alpha + b * (1.0 - alpha)) for t, b in zip(top, bottom))
    return "#{:02x}{:02x}{:02x}".format(*mixed)


def accent_roles(palette: Dict[str, object]) -> Dict[str, str]:
    """The accent colour set, validated as hex."""
    accent = palette.get("accent")
    if not isinstance(accent, dict):
        raise ContrastError("palette.accent is missing or not an object")
    out: Dict[str, str] = {}
    for role in ("primary", "secondary", "success", "warning", "danger"):
        value = accent.get(role)
        if not isinstance(value, str):
            raise ContrastError(f"palette.accent.{role} is missing")
        parse_hex(value, f"palette.accent.{role}")
        out[role] = value
    return out


def pairs_for(preset: Dict[str, object]) -> List[Pair]:
    """Every foreground/background combination this preset must satisfy.

    The list is derived from the palette roles rather than written out per
    preset, so adding a colour role to one preset cannot silently skip the
    check for the others.
    """
    palette = preset.get("palette")
    if not isinstance(palette, dict):
        raise ContrastError(f"{preset.get('id', '?')}: palette is missing")

    def colour(role: str) -> str:
        value = palette.get(role)
        if not isinstance(value, str):
            raise ContrastError(f"palette.{role} is missing")
        parse_hex(value, f"palette.{role}")
        return value

    background = colour("background")
    surface = colour("surface")
    surface_variant = colour("surface_variant")
    on_background = colour("on_background")
    on_surface = colour("on_surface")
    on_surface_variant = colour("on_surface_variant")
    outline = colour("outline")
    outline_variant = colour("outline_variant")
    text_disabled = colour("text_disabled")
    accents = accent_roles(palette)

    pairs: List[Pair] = [
        # Body text on each surface it can land on.
        Pair("body text on background", on_background, background, MIN_TEXT_RATIO, "text"),
        Pair("body text on surface", on_surface, surface, MIN_TEXT_RATIO, "text"),
        Pair("body text on surface-variant", on_surface_variant, surface_variant, MIN_TEXT_RATIO, "text"),
        # A card sits on the window background too, and a sidebar variant can
        # hold body text, so cross those as well.
        Pair("body text on surface (variant text)", on_surface_variant, surface, MIN_TEXT_RATIO, "text"),
        Pair("surface-variant text on background", on_surface_variant, background, MIN_TEXT_RATIO, "text"),
        # Accents are used as link text, as button labels on a glass fill, and
        # as the value of a focused entry: they have to be readable, not just
        # recognisable.
    ]
    for role, value in accents.items():
        pairs.append(Pair(f"accent.{role} text on background", value, background, MIN_TEXT_RATIO, "text"))
        pairs.append(Pair(f"accent.{role} text on surface", value, surface, MIN_TEXT_RATIO, "text"))

    # Text drawn *inside* an accent fill (a suggested button, a selected row).
    on_accent = palette.get("on_accent")
    if isinstance(on_accent, dict):
        for role, value in accents.items():
            label = on_accent.get(role)
            if not isinstance(label, str):
                raise ContrastError(f"palette.on_accent.{role} is missing")
            parse_hex(label, f"palette.on_accent.{role}")
            pairs.append(Pair(f"label on accent.{role} fill", label, value, MIN_TEXT_RATIO, "text"))

    # Non-text UI: focus rings, hairlines and disabled text only need 3:1, and
    # disabled text is exempt from 1.4.3 entirely -- but it still has to be
    # distinguishable from the surface, so it is measured at the UI level.
    pairs.extend([
        Pair("outline against surface", outline, surface, MIN_UI_RATIO, "ui"),
        Pair("outline against background", outline, background, MIN_UI_RATIO, "ui"),
        Pair("body text against outline (focus ring)", on_surface, outline, MIN_UI_RATIO, "ui"),
        Pair("disabled text against surface", text_disabled, surface, MIN_UI_RATIO, "ui"),
        Pair("decorative hairline against surface", outline_variant, surface, INFO_RATIO, "info"),
    ])

    # Terminal palette: the shell is read for hours, so hold it to the same bar.
    terminal = preset.get("terminal", {})
    colours = terminal.get("colors", {}) if isinstance(terminal, dict) else {}
    term_bg = colours.get("background")
    term_fg = colours.get("foreground")
    if isinstance(term_bg, str) and isinstance(term_fg, str):
        parse_hex(term_bg, "terminal.colors.background")
        parse_hex(term_fg, "terminal.colors.foreground")
        pairs.append(Pair("terminal foreground", term_fg, term_bg, MIN_TEXT_RATIO, "text"))
        for index in range(16):
            value = colours.get(f"color{index}")
            if not isinstance(value, str):
                continue
            parse_hex(value, f"terminal.colors.color{index}")
            dim = index in (0, 8)  # black and bright-black: dimmed text by design
            pairs.append(Pair(
                f"terminal ansi color{index}",
                value,
                term_bg,
                INFO_RATIO if dim else MIN_TEXT_RATIO,
                "info" if dim else "text",
            ))
    return pairs


def evaluate(preset: Dict[str, object], minimum: Optional[float] = None) -> List[Result]:
    """Measure every pair of a preset, optionally raising the floor."""
    results = []
    for pair in pairs_for(preset):
        floor = pair.minimum if minimum is None else max(pair.minimum, minimum)
        results.append(Result(
            label=pair.label,
            foreground=pair.foreground,
            background=pair.background,
            ratio=contrast_ratio(pair.foreground, pair.background),
            minimum=floor,
            kind=pair.kind,
        ))
    return results


def load_preset(path: Path) -> Dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContrastError(f"{path}: {exc}") from exc
    except OSError as exc:
        raise ContrastError(f"{path}: {exc}") from exc


def discover(directory: Path = PRESET_DIR, only: Optional[str] = None) -> List[Path]:
    if not directory.is_dir():
        raise ContrastError(f"preset directory {directory} does not exist")
    paths = sorted(p for p in directory.glob("*.json") if p.is_file())
    if only:
        paths = [p for p in paths if p.stem == only or p.name == only]
        if not paths:
            raise ContrastError(f"no preset named {only!r} in {directory}")
    if not paths:
        raise ContrastError(f"no presets found in {directory}")
    return paths


def report(results: Iterable[Result]) -> str:
    lines = []
    for result in sorted(results, key=lambda r: (r.kind == "info", r.ratio)):
        if result.kind == "info":
            mark = "info"
        else:
            mark = "ok  " if result.passed else "FAIL"
        floor = "      " if result.kind == "info" else f"min {result.minimum:.1f}"
        lines.append(
            f"  [{mark}] {result.ratio:5.2f}:1 ({floor}) "
            f"{result.label}: {result.foreground} on {result.background}"
        )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help="check a single preset id or file name")
    parser.add_argument("--directory", type=Path, default=PRESET_DIR, help="preset directory")
    parser.add_argument("--min", type=float, default=None,
                        help="raise the floor for every pair (default: 4.5 text, 3.0 UI)")
    parser.add_argument("--json", action="store_true", dest="as_json", help="emit JSON instead of a report")
    parser.add_argument("--quiet", action="store_true", help="only print failures")
    args = parser.parse_args(argv)

    payload: Dict[str, object] = {"ok": True, "presets": {}}
    failures = 0
    try:
        for path in discover(args.directory, args.preset):
            preset = load_preset(path)
            results = evaluate(preset, args.min)
            failed = [r for r in results if not r.passed]
            failures += len(failed)
            preset_id = str(preset.get("id", path.stem))
            payload["presets"][preset_id] = {
                "path": str(path.relative_to(ROOT)),
                "pairs": len(results),
                "gated": sum(1 for r in results if r.kind != "info"),
                "informational": sum(1 for r in results if r.kind == "info"),
                "failures": [r._asdict() for r in failed],
                "lowest": round(min(r.ratio for r in results), 3) if results else None,
                "lowest_gated": round(min((r.ratio for r in results if r.kind != "info"),
                                          default=0.0), 3),
            }
            if not args.as_json and (failed or not args.quiet):
                gated = sum(1 for r in results if r.kind != "info")
                print(f"{preset_id} ({path.name}): {gated} gated pairs, "
                      f"{len(failed)} below floor, "
                      f"{len(results) - gated} informational")
                print(report(results))
    except ContrastError as exc:
        print(f"contrast-check: {exc}", file=sys.stderr)
        return 2

    payload["ok"] = failures == 0
    if args.as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif failures:
        print(f"\n{failures} pair(s) below the required ratio", file=sys.stderr)
    elif args.quiet:
        print("contrast-check: all presets pass")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
