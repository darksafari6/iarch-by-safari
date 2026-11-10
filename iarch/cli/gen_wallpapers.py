#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render the abstract wallpapers the generated presets ship with.

Each preset whose ``wallpaper.kind`` is ``generated`` describes a gradient in its
own JSON: a style, two to six colour stops, a seed, a grain and a vignette
strength. This renders that description to a 3840x2160 WebP under
``assets/wallpapers/generated/``, inside a size budget. The render is seeded
end to end, so the same preset JSON produces the same file with the same Pillow
and libwebp, and a maintainer can confirm the committed WebP came from the JSON
next to it.

Presets whose wallpaper is ``bundled`` (Crimson Plasma and Tokyo Night Glass,
which reuse the two images this repository already shipped) are never rendered
and never touched; ``--check`` only confirms the file they point at exists.

Rendering happens at a low resolution and is upscaled bicubically, because every
style here is a smooth field: computing 8.3 million pixels in Python would take
minutes and produce nothing visually different. Grain is added afterwards at full
resolution, mean-zero, so it does not lift the blacks.

Requires Pillow. Nothing here shells out, and no ``shell=True`` is used anywhere
in this repository.

Usage:
    python3 iarch/cli/gen_wallpapers.py                 # render every generated preset
    python3 iarch/cli/gen_wallpapers.py --preset aurora  # one preset
    python3 iarch/cli/gen_wallpapers.py --check          # verify what ships
    python3 iarch/cli/gen_wallpapers.py --dry-run        # report without writing
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
PRESET_DIR = ROOT / "data" / "design" / "presets"
GENERATED_DIR = ROOT / "assets" / "wallpapers" / "generated"

# Rendered small and upscaled: the fields are smooth, so the detail is not there
# to lose. 4x on each axis reaches the 4K target exactly, and at this resolution
# the interpolation lattice no longer shows as soft rectangles.
LOW_RES = (960, 540)
TARGET = (3840, 2160)
SIZE_BUDGET_BYTES = 600 * 1024
DEFAULT_QUALITY = 86

STYLES = ("mesh", "aurora", "radial", "diagonal", "plasma")


class WallpaperError(RuntimeError):
    """Raised when a preset cannot be rendered or the shipped art is wrong."""


def parse_hex(value: str, where: str) -> Tuple[int, int, int]:
    text = value.strip()
    if not text.startswith("#") or len(text) != 7:
        raise WallpaperError(f"{where}: {value!r} is not a #rrggbb colour")
    try:
        return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
    except ValueError as exc:
        raise WallpaperError(f"{where}: {value!r} has non-hex digits") from exc


def ramp(stops: Sequence[Tuple[int, int, int]], position: float) -> Tuple[int, int, int]:
    """Piecewise-linear interpolation across the stop list at ``position`` 0..1."""
    if not stops:
        raise WallpaperError("a gradient needs at least one stop")
    if len(stops) == 1:
        return stops[0]
    scaled = max(0.0, min(1.0, position)) * (len(stops) - 1)
    index = int(scaled)
    if index >= len(stops) - 1:
        return stops[-1]
    fraction = scaled - index
    left, right = stops[index], stops[index + 1]
    return tuple(round(a + (b - a) * fraction) for a, b in zip(left, right))  # type: ignore[return-value]


def smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def value_noise(width: int, height: int, rng: random.Random,
                cells_x: int, cells_y: int) -> List[float]:
    """Bilinearly interpolated lattice noise, one value in 0..1 per pixel."""
    lattice = [[rng.random() for _ in range(cells_x + 1)] for _ in range(cells_y + 1)]
    out: List[float] = []
    for y in range(height):
        fy = y / max(1, height - 1) * cells_y
        y0 = int(fy)
        y1 = min(y0 + 1, cells_y)
        ty = smoothstep(fy - y0)
        row_top, row_bottom = lattice[y0], lattice[y1]
        for x in range(width):
            fx = x / max(1, width - 1) * cells_x
            x0 = int(fx)
            x1 = min(x0 + 1, cells_x)
            tx = smoothstep(fx - x0)
            top = row_top[x0] * (1.0 - tx) + row_top[x1] * tx
            bottom = row_bottom[x0] * (1.0 - tx) + row_bottom[x1] * tx
            out.append(top * (1.0 - ty) + bottom * ty)
    return out


def fractal_noise(width: int, height: int, rng: random.Random, octaves: int = 3) -> List[float]:
    """Sum of value-noise octaves, normalised back into 0..1."""
    total = [0.0] * (width * height)
    weight_sum = 0.0
    cells = 4
    for octave in range(octaves):
        weight = 0.5 ** octave
        layer = value_noise(width, height, rng, cells, max(2, int(cells * height / width)))
        for index, value in enumerate(layer):
            total[index] += value * weight
        weight_sum += weight
        cells *= 2
    return [value / weight_sum for value in total]


def field(style: str, width: int, height: int, rng: random.Random) -> List[float]:
    """Scalar field in 0..1 per pixel for every style except ``mesh``."""
    out: List[float] = []
    if style == "radial":
        cx, cy = rng.uniform(0.3, 0.7), rng.uniform(0.3, 0.7)
        reach = math.hypot(max(cx, 1 - cx), max(cy, 1 - cy))
        for y in range(height):
            v = y / height
            for x in range(width):
                u = x / width
                distance = math.hypot(u - cx, (v - cy) * 0.62) / reach
                out.append(max(0.0, min(1.0, 1.0 - distance)))
    elif style == "diagonal":
        angle = rng.uniform(0.35, 0.65) * math.pi
        warp_amp, warp_freq = rng.uniform(0.04, 0.09), rng.uniform(1.5, 3.0)
        dx, dy = math.cos(angle), math.sin(angle)
        span = abs(dx) + abs(dy)
        for y in range(height):
            v = y / height
            for x in range(width):
                u = x / width
                base = (u * dx + v * dy) / span
                warp = warp_amp * math.sin((u + v) * warp_freq * math.pi * 2)
                out.append(max(0.0, min(1.0, base * 0.5 + 0.25 + warp)))
    elif style == "aurora":
        # Vertical drapes hanging from the upper third, each slanting a little.
        # Sinusoidal bands read as corduroy and as closed ribbons; Gaussian rays
        # in the horizontal axis with a vertical falloff are the shape people
        # actually recognise as an aurora.
        rays = [(rng.uniform(0.05, 0.95), rng.uniform(0.03, 0.09),
                 rng.uniform(0, math.tau), rng.uniform(-0.22, 0.22),
                 rng.uniform(0.5, 1.0))
                for _ in range(6)]
        crest = rng.uniform(0.20, 0.34)
        out = []
        for y in range(height):
            v = y / height
            # A broad falloff, not a narrow one: curtains hang from the crest
            # down most of the frame, which is what makes them curtains.
            vertical = math.exp(-((v - crest) ** 2) / 0.42)
            for x in range(width):
                u = x / width
                value = 0.08 + 0.10 * (1.0 - v)
                for cx, ray_width, phase, slant, strength in rays:
                    xu = u + slant * (v - crest)
                    drape = math.exp(-(((xu - cx) + 0.5) % 1.0 - 0.5) ** 2 / (2 * ray_width ** 2))
                    shimmer = 0.65 + 0.35 * math.sin(u * math.tau * 0.8 + phase + v * 1.7)
                    value += strength * drape * vertical * shimmer * 0.55
                out.append(max(0.0, min(1.0, value)))
    elif style == "plasma":
        out = fractal_noise(width, height, rng, octaves=4)
    else:
        raise WallpaperError(f"unknown style {style!r}; expected one of {', '.join(STYLES)}")
    return out


def luminance_texture(values: Sequence[float], width: int, height: int,
                      rng: random.Random) -> List[float]:
    """Bend the field by a large-scale noise, so a gradient has depth.

    A pure two-stop gradient renders as a flat wash: technically a wallpaper,
    visually a mistake. Two octaves of value noise, applied at ten percent, give
    the surface the uneven light a real photograph of frosted glass has.
    """
    noise = fractal_noise(width, height, rng, octaves=3)
    return [max(0.0, min(1.0, value * (0.94 + 0.12 * sample)))
            for value, sample in zip(values, noise)]


def render_base(style: str, stops: Sequence[Tuple[int, int, int]],
                width: int, height: int, rng: random.Random) -> "Image.Image":  # noqa: F821
    """The low-resolution gradient, before grain, vignette and upscaling."""
    from PIL import Image  # imported lazily so --help works without Pillow

    if style == "mesh":
        # A mesh gradient is a weighted blend of coloured centres, not a scalar
        # field pushed through a ramp: that is what makes the blobs read as
        # separate lights rather than as stripes.
        centres = [(rng.uniform(0.05, 0.95), rng.uniform(0.05, 0.95),
                    rng.uniform(0.55, 1.15), colour) for colour in stops]
        pixels = []
        for y in range(height):
            v = y / height
            for x in range(width):
                u = x / width
                weights = []
                for cx, cy, tightness, _ in centres:
                    distance = math.hypot(u - cx, (v - cy) * 0.62)
                    sigma = 0.26 * tightness
                    weights.append(tightness * math.exp(-(distance ** 2) / (2 * sigma ** 2)))
                total = sum(weights) or 1.0
                blended = [0.0, 0.0, 0.0]
                for weight, (_, _, _, colour) in zip(weights, centres):
                    share = weight / total
                    for channel in range(3):
                        blended[channel] += colour[channel] * share
                pixels.append(tuple(int(round(c)) for c in blended))
        image = Image.new("RGB", (width, height))
        image.putdata(pixels)
        return image

    values = field(style, width, height, rng)
    values = luminance_texture(values, width, height, rng)
    image = Image.new("RGB", (width, height))
    image.putdata([ramp(stops, value) for value in values])
    return image


def apply_vignette(image: "Image.Image", strength: float) -> "Image.Image":  # noqa: F821
    """Darken the corners by ``strength`` (0 = none, 1 = fully black corners)."""
    from PIL import Image, ImageChops

    if strength <= 0:
        return image
    width, height = image.size
    mask: List[int] = []
    for y in range(height):
        v = (y / max(1, height - 1)) * 2.0 - 1.0
        for x in range(width):
            u = (x / max(1, width - 1)) * 2.0 - 1.0
            distance = math.hypot(u, v) / math.sqrt(2.0)
            # Six tenths of the strength at the very corner, never all of it: a
            # vignette that reaches black turns the wallpaper into a photo taken
            # in a dark room.
            factor = 1.0 - 0.6 * strength * smoothstep(max(0.0, min(1.0, distance)))
            mask.append(int(round(255 * factor)))
    layer = Image.new("L", (width, height))
    layer.putdata(mask)
    return ImageChops.multiply(image, layer.convert("RGB"))


def apply_grain(image: "Image.Image", amount: float, seed: int) -> "Image.Image":  # noqa: F821
    """Add mean-zero film grain at full resolution.

    Blending a grey noise image would raise the black floor by the blend amount,
    so the noise is split into a positive and a negative channel and each is
    added and subtracted separately.

    The noise is drawn from a seeded generator rather than from
    ``Image.effect_noise``, whose random source cannot be seeded: an unseeded
    grain would make every render differ by a few bytes, and then neither a test
    nor a maintainer could confirm that the WebP in the repository really came
    from the preset JSON next to it. Half resolution is enough -- grain this
    fine is invisible once upscaled -- and keeps the draw count sane.
    """
    from PIL import Image, ImageChops

    if amount <= 0:
        return image
    rng = random.Random(seed ^ 0x5EED)
    half_width, half_height = image.size[0] // 2, image.size[1] // 2
    samples = [min(255, max(0, 128 + int(rng.gauss(0.0, 64.0))))
               for _ in range(half_width * half_height)]
    noise = Image.new("L", (half_width, half_height))
    noise.putdata(samples)
    noise = noise.resize(image.size, Image.Resampling.BILINEAR)
    positive = noise.point(lambda v: int(max(0, v - 128) * amount)).convert("RGB")
    negative = noise.point(lambda v: int(max(0, 128 - v) * amount)).convert("RGB")
    return ImageChops.subtract(ImageChops.add(image, positive), negative)


def encode_webp(image: "Image.Image", destination: Path, budget: int,  # noqa: F821
                quality: int) -> Tuple[int, int]:
    """Write WebP, stepping the quality down until the file fits the budget."""
    from PIL import Image  # noqa: F401  (kept for the Resampling constant)

    destination.parent.mkdir(parents=True, exist_ok=True)
    current = quality
    while True:
        image.save(destination, "WEBP", quality=current, method=6)
        size = destination.stat().st_size
        if size <= budget or current <= 40:
            return size, current
        current -= 4


def render_preset(preset: Dict[str, object], destination: Path, budget: int,
                  quality: int) -> Dict[str, object]:
    from PIL import Image

    wallpaper = preset["wallpaper"]
    spec = wallpaper.get("generate")
    if not isinstance(spec, dict):
        raise WallpaperError(f"{preset.get('id')}: wallpaper.generate is missing")
    style = spec.get("style")
    if style not in STYLES:
        raise WallpaperError(f"{preset.get('id')}: unknown style {style!r}")
    raw_stops = spec.get("stops") or []
    if not 2 <= len(raw_stops) <= 6:
        raise WallpaperError(f"{preset.get('id')}: needs 2 to 6 stops, has {len(raw_stops)}")
    where = f"{preset.get('id')}.wallpaper.generate.stops"
    stops = [parse_hex(str(value), where) for value in raw_stops]
    seed = int(spec.get("seed", 0))
    grain = float(spec.get("grain", 0.0))
    vignette = float(spec.get("vignette", 0.0))

    rng = random.Random(seed)
    base = render_base(str(style), stops, LOW_RES[0], LOW_RES[1], rng)
    base = apply_vignette(base, vignette)
    image = base.resize(TARGET, Image.Resampling.BICUBIC)
    image = apply_grain(image, grain, seed)
    size, used_quality = encode_webp(image, destination, budget, quality)
    return {
        "preset": preset.get("id"),
        "path": destination,
        "style": style,
        "size": size,
        "quality": used_quality,
        "dimensions": TARGET,
    }


def load_presets(only: Optional[str] = None) -> List[Dict[str, object]]:
    if not PRESET_DIR.is_dir():
        raise WallpaperError(f"preset directory {PRESET_DIR} does not exist")
    presets = []
    for path in sorted(PRESET_DIR.glob("*.json")):
        try:
            preset = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WallpaperError(f"{path}: {exc}") from exc
        if only and preset.get("id") != only and path.stem != only:
            continue
        presets.append(preset)
    if only and not presets:
        raise WallpaperError(f"no preset named {only!r}")
    if not presets:
        raise WallpaperError(f"no presets in {PRESET_DIR}")
    return presets


def check(budget: int) -> List[str]:
    """Verify the shipped art. Returns a list of problems, empty when all is well.

    Deliberately not a byte comparison: WebP output depends on the Pillow and
    libwebp versions, so re-encoding on another machine would fail a byte check
    while the art is still correct. What is checked instead is the contract the
    task sets -- every preset resolves to a file that exists, generated art is
    4K and inside the budget, and nothing is orphaned in the output directory.
    """
    from PIL import Image

    problems: List[str] = []
    presets = load_presets()
    referenced: set[Path] = set()
    generated_expected: set[Path] = set()

    for preset in presets:
        preset_id = str(preset.get("id", "?"))
        wallpaper = preset.get("wallpaper")
        if not isinstance(wallpaper, dict):
            problems.append(f"{preset_id}: no wallpaper block")
            continue
        relative = str(wallpaper.get("path", ""))
        path = ROOT / relative
        referenced.add(path)
        kind = wallpaper.get("kind")
        if not path.is_file():
            problems.append(f"{preset_id}: {relative} does not exist")
            continue
        if kind == "bundled":
            continue
        if kind != "generated":
            problems.append(f"{preset_id}: wallpaper.kind is {kind!r}")
            continue
        generated_expected.add(path)
        if path.parent != GENERATED_DIR:
            problems.append(f"{preset_id}: generated art belongs in {GENERATED_DIR}, "
                            f"found {path.parent}")
        size = path.stat().st_size
        if size > budget:
            problems.append(f"{preset_id}: {relative} is {size / 1024:.0f} KB, "
                            f"budget is {budget / 1024:.0f} KB")
        try:
            with Image.open(path) as image:
                if image.size != TARGET:
                    problems.append(f"{preset_id}: {relative} is {image.size[0]}x{image.size[1]}, "
                                    f"expected {TARGET[0]}x{TARGET[1]}")
                if image.format != "WEBP":
                    problems.append(f"{preset_id}: {relative} is {image.format}, expected WEBP")
        except OSError as exc:
            problems.append(f"{preset_id}: {relative} cannot be opened: {exc}")

    if GENERATED_DIR.is_dir():
        for path in sorted(GENERATED_DIR.glob("*")):
            if path.is_file() and path not in generated_expected:
                label = (path.relative_to(ROOT).as_posix()
                         if path.is_relative_to(ROOT) else str(path))
                problems.append(f"orphan: {label} is rendered by no preset")
    return problems


def require_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError as exc:
        raise WallpaperError(
            "Pillow is required to render wallpapers. Install it with "
            "`pip install --user Pillow`, or the distribution package "
            "(Arch: python-pillow, Fedora: python3-pillow -- TODO(verify): the "
            "package names were not confirmed against the distribution "
            "repositories, see docs/UNVERIFIED.md TP-15). Rendering is only "
            "needed to regenerate the art; the wallpapers ship in the "
            "repository, so a normal install does not need Pillow."
        ) from exc


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preset", help="render or check a single preset id")
    parser.add_argument("--check", action="store_true",
                        help="verify the shipped wallpapers instead of rendering")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be written without writing it")
    parser.add_argument("--max-kb", type=int, default=SIZE_BUDGET_BYTES // 1024,
                        help=f"size budget per file in KB (default {SIZE_BUDGET_BYTES // 1024})")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY,
                        help=f"starting WebP quality (default {DEFAULT_QUALITY})")
    args = parser.parse_args(argv)

    budget = args.max_kb * 1024
    try:
        require_pillow()
        if args.check:
            problems = check(budget)
            for problem in problems:
                print(f"wallpapers: {problem}", file=sys.stderr)
            if problems:
                print(f"wallpapers: {len(problems)} problem(s)", file=sys.stderr)
                return 1
            print(f"wallpapers: every preset resolves to art that is present, "
                  f"4K where generated, and inside {args.max_kb} KB")
            return 0

        presets = load_presets(args.preset)
        rendered = 0
        for preset in presets:
            wallpaper = preset["wallpaper"]
            if wallpaper.get("kind") != "generated":
                print(f"{preset['id']}: wallpaper is bundled "
                      f"({wallpaper.get('path')}), not rendered")
                continue
            destination = ROOT / str(wallpaper["path"])
            if args.dry_run:
                print(f"{preset['id']}: would render {destination.relative_to(ROOT)} "
                      f"({wallpaper['generate']['style']}, "
                      f"seed {wallpaper['generate']['seed']})")
                continue
            result = render_preset(preset, destination, budget, args.quality)
            rendered += 1
            print(f"{preset['id']}: {destination.relative_to(ROOT)} "
                  f"{result['size'] / 1024:.0f} KB at q{result['quality']} "
                  f"({result['style']}, {TARGET[0]}x{TARGET[1]})")
        if not args.dry_run:
            problems = check(budget)
            for problem in problems:
                print(f"wallpapers: {problem}", file=sys.stderr)
            if problems:
                return 1
        print(f"wallpapers: {rendered} rendered" if not args.dry_run else "wallpapers: dry run")
        return 0
    except WallpaperError as exc:
        print(f"wallpapers: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
