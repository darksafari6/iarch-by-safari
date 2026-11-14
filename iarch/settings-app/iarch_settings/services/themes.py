# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The look of the session: presets, intensities, motion and the accent colour.

This module is the settings application's side of the two command line tools that
already own this state. It **does not reimplement either**: applying a theme means
calling ``iarch/cli/theme.py apply``, which owns the contrast gate, the eleven
render targets, the atomic writes, the backup rotation and the
reload-then-verify-or-roll-back sequence, and changing motion means calling
``iarch/cli/iarch_anim.py``. A page that rendered a stylesheet itself would be a
second implementation of a decision the tools already make, and the two would
drift the first time a preset changed.

What this module adds is reading: which presets exist, which intensities exist,
what a preset's colours are so the Appearance page can draw a thumbnail, and which
accent roles a contrast warning applies to.

**There is no ``iarch-theme preview`` subcommand**, and this module does not
pretend there is one. ``theme.py`` has exactly two: ``apply`` and ``current``
(``iarch/cli/theme.py:606`` and ``:626``). A preset thumbnail is therefore drawn
from the preset's own palette in ``data/design/presets/<id>.json`` -- the same
colours ``apply`` would render -- rather than captured from a compositor this
sandbox does not have. :func:`thumbnail` returns the colours and :func:`swatches`
says which of them a tile shows.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import paths
from . import runner

THEME_TOOL = "theme"
ANIM_TOOL = "iarch_anim"
FONTCONFIG_TOOL = "gen_fontconfig"
CONTRAST_TOOL = "contrast_check"

#: The palette keys a preset thumbnail shows, in the order it shows them. Every
#: one of them is a key data/design/presets/*.json already carries, so a tile is
#: drawn from the colours `iarch-theme apply` would render rather than from a
#: second opinion of what the preset looks like.
THUMBNAIL_KEYS = ("background", "surface", "surface_variant", "on_surface",
                  "outline", "shadow")

#: The accent roles, which is what the accent picker offers and what the contrast
#: warning is computed against.
ACCENT_ROLES = ("primary", "secondary", "success", "warning", "danger")

#: Motion presets, as the files under data/design/animations/ that define them.
#: `off` is the one that means "no animation", and it is the mechanism
#: `effects.animations` is derived from -- not a second switch beside it.
MOTION_PRESETS = ("smooth", "snappy", "bouncy", "minimal", "off")


class ThemesError(RuntimeError):
    """A preset, an intensity or a tool answer that cannot be used."""


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ThemesError(f"{path}: {exc}") from exc


# ------------------------------------------------------------------ the tokens


def tokens(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/tokens.json``, the design system's own source."""
    return _json(paths.design_file("tokens.json", root))


def intensities(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """The four intensities, by id, each with its label and description."""
    return tokens(root)["intensities"]


def intensity_ids(root: Optional[Path] = None) -> List[str]:
    """The intensity ids in the order the tokens declare them."""
    return list(intensities(root))


def default_intensity(root: Optional[Path] = None) -> str:
    return str(tokens(root)["default_intensity"])


def intensity_label(intensity: str, root: Optional[Path] = None) -> str:
    table = intensities(root).get(intensity)
    if table is None:
        return intensity
    return str(table.get("label", intensity))


def intensity_description(intensity: str, root: Optional[Path] = None) -> str:
    table = intensities(root).get(intensity) or {}
    return str(table.get("description", ""))


def glass_leaves(root: Optional[Path] = None) -> Tuple[List[str], Dict[str, List[float]],
                                                       List[str]]:
    """The compositor's leaf names, their bounds and which ones are whole numbers.

    This is the Glass page's authority: a slider's range comes from here, so a
    value the compositor's own parser would refuse cannot be offered. Returned as
    ``(names, ranges, integer_names)`` straight out of ``tokens.json -> hyprland``.
    """
    hyprland = tokens(root)["hyprland"]
    return (list(hyprland["leaves"]),
            {key: [float(low), float(high)] for key, (low, high) in hyprland["ranges"].items()},
            list(hyprland["integer_leaves"]))


def slider_bounds(leaf: str, root: Optional[Path] = None) -> Optional[Tuple[float, float]]:
    """A leaf's ``(minimum, maximum)``, or ``None`` when the tokens bound nothing."""
    _, ranges, _ = glass_leaves(root)
    bounds = ranges.get(leaf)
    return (bounds[0], bounds[1]) if bounds else None


def is_integer_leaf(leaf: str, root: Optional[Path] = None) -> bool:
    _, _, integers = glass_leaves(root)
    return leaf in integers


def font_tokens(root: Optional[Path] = None) -> Dict[str, Any]:
    """The design system's own fonts, which the Fonts page shows as the defaults."""
    return tokens(root)["font"]


# ------------------------------------------------------------------ the presets


def preset_dir(root: Optional[Path] = None) -> Path:
    path = (root or paths.repo_root()) / "data" / "design" / "presets"
    if not path.is_dir():
        raise ThemesError(f"no colour presets at {path}")
    return path


def preset_ids(root: Optional[Path] = None) -> List[str]:
    """Every preset id, from the filenames, sorted.

    Read off the directory rather than off a list, so a preset added to
    ``data/design/presets/`` appears in the picker without a code change -- which
    is what the settings schema means by "the list stays open".
    """
    return sorted(path.stem for path in preset_dir(root).glob("*.json"))


def preset(preset_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    path = preset_dir(root) / f"{preset_id}.json"
    if not path.is_file():
        raise ThemesError(f"there is no colour preset named {preset_id!r}; the ones that "
                          f"exist are {', '.join(preset_ids(root))}")
    return _json(path)


def palette(preset_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """One preset's palette block."""
    document = preset(preset_id, root)
    palette_block = document.get("palette")
    if not isinstance(palette_block, dict):
        raise ThemesError(f"{preset_id} has no palette block")
    return palette_block


def thumbnail(preset_id: str, root: Optional[Path] = None) -> Dict[str, Any]:
    """What a preset tile draws: the colours, the mode and the words.

    Nothing here is captured from a running session and nothing calls a
    subcommand that does not exist. A tile is the preset's own background, surface,
    surface variant, text, outline and shadow, its accent roles, its name, its mode
    and its default intensity -- the same values ``iarch-theme apply`` renders from,
    so a tile cannot disagree with the result of clicking it.
    """
    document = preset(preset_id, root)
    colours = palette(preset_id, root)
    accent = colours.get("accent") or {}
    return {
        "id": preset_id,
        "name": str(document.get("name", preset_id)),
        "description": str(document.get("description", "")),
        "mode": str(document.get("mode", "dark")),
        "default_intensity": str(document.get("default_intensity",
                                              default_intensity(root))),
        "colours": {key: colours.get(key) for key in THUMBNAIL_KEYS},
        "accent": {role: accent.get(role) for role in ACCENT_ROLES},
    }


def swatches(preset_id: str, root: Optional[Path] = None) -> List[Tuple[str, str]]:
    """The ``(label, colour)`` pairs a tile paints, skipping a colour the preset lacks."""
    data = thumbnail(preset_id, root)
    pairs = [(key.replace("_", " "), value) for key, value in data["colours"].items()
             if isinstance(value, str) and value.startswith("#")]
    pairs += [(f"accent {role}", value) for role, value in data["accent"].items()
              if isinstance(value, str) and value.startswith("#")]
    return pairs


def accent_roles(preset_id: str, root: Optional[Path] = None) -> Dict[str, Optional[str]]:
    """The five accent colours a preset defines, for the accent picker."""
    colours = palette(preset_id, root).get("accent") or {}
    return {role: colours.get(role) for role in ACCENT_ROLES}


# ------------------------------------------------------------------ motion


def motion_presets(root: Optional[Path] = None) -> List[str]:
    """The motion presets that actually have a file, in a stable order.

    Intersected with the recorded list so a stray file in the directory cannot add
    a preset the schema does not allow, and ordered by :data:`MOTION_PRESETS` so
    the picker does not reshuffle when a file is added.
    """
    directory = (root or paths.repo_root()) / "data" / "design" / "animations"
    present = {path.stem for path in directory.glob("*.json")} if directory.is_dir() else set()
    return [name for name in MOTION_PRESETS if name in present]


def motion_record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/animations.json``: the compositor's animation API surface."""
    return _json(paths.design_file("animations.json", root))


# ------------------------------------------------------------------ calling out


def theme_argv(preset_id: str, intensity: Optional[str] = None, *,
               reduce_motion: str = "auto", config_home: Optional[Path] = None,
               dry_run: bool = False, no_reload: bool = False) -> List[str]:
    """The ``theme.py apply`` argument list, built rather than string-formatted.

    Kept as its own function so a test can assert on the exact argv without
    starting a process, and so a page cannot forget ``--config-home`` -- which is
    the mistake that writes into ``~/.config/iarch/theme`` while the session reads
    ``~/.config``.
    """
    argv = ["apply", preset_id]
    if intensity:
        argv += ["--intensity", intensity]
    argv += ["--reduce-motion", reduce_motion]
    if config_home:
        argv += ["--config-home", str(config_home)]
    if no_reload:
        argv.append("--no-reload")
    if dry_run:
        argv.append("--dry-run")
    return argv


def apply_theme(preset_id: str, intensity: Optional[str] = None, *,
                reduce_motion: str = "auto", config_home: Optional[Path] = None,
                dry_run: bool = False, no_reload: bool = False) -> runner.Outcome:
    """Run ``iarch-theme apply`` and classify the result.

    The tool's own exit codes are the verdict: 0 rendered and verified, 1 a gate
    refused (which is a *decision*, not a crash -- the contrast gate refusing an
    unreadable accent is the tool working), 2 the arguments were wrong. A refusal
    is reported as :data:`runner.FAILED` with the tool's own sentence attached, so
    the toast says why rather than only that.
    """
    argv = theme_argv(preset_id, intensity, reduce_motion=reduce_motion,
                      config_home=config_home, dry_run=dry_run, no_reload=no_reload)
    return runner.python_tool(paths.cli_module_path(THEME_TOOL), argv)


def current_theme(config_home: Optional[Path] = None) -> runner.Outcome:
    """``iarch-theme current``: what apply would use, without applying anything."""
    argv = ["current"] + (["--config-home", str(config_home)] if config_home else [])
    return runner.python_tool(paths.cli_module_path(THEME_TOOL), argv)


def anim_argv(subcommand: str, *args: str, config_home: Optional[Path] = None,
              no_reload: bool = False, dry_run: bool = False, as_json: bool = False,
              live: bool = False) -> List[str]:
    """An ``iarch-anim`` argument list.

    Every subcommand of that tool takes ``--config-home``, ``--no-reload``,
    ``--dry-run`` and ``--json``; only ``current`` takes ``--live``, which is the
    flag that also asks the compositor what it is animating with now. Passing it
    anywhere else would be an exit 2 from argparse, so it is a parameter here and
    not something a page appends.
    """
    argv = [subcommand, *args]
    if config_home:
        argv += ["--config-home", str(config_home)]
    if no_reload:
        argv.append("--no-reload")
    if dry_run:
        argv.append("--dry-run")
    if as_json:
        argv.append("--json")
    if live and subcommand == "current":
        argv.append("--live")
    return argv


def run_anim(subcommand: str, *args: str, config_home: Optional[Path] = None,
             no_reload: bool = False, dry_run: bool = False, as_json: bool = False,
             live: bool = False) -> runner.Outcome:
    """Run one ``iarch-anim`` subcommand and classify its exit code."""
    argv = anim_argv(subcommand, *args, config_home=config_home, no_reload=no_reload,
                     dry_run=dry_run, as_json=as_json, live=live)
    return runner.python_tool(paths.cli_module_path(ANIM_TOOL), argv)


def contrast_report(preset_id: Optional[str] = None, minimum: Optional[float] = None,
                    as_json: bool = False) -> runner.Outcome:
    """Run the contrast gate, which is what an accent warning is made of.

    ``--preset`` is the tool's own flag for one preset
    (``iarch/cli/contrast_check.py --help``); there is no positional form, and
    passing one would be an exit 2. The accent picker warns before it applies, and
    the warning is this gate's verdict rather than a rule invented in the
    interface -- the gate is the thing ``iarch-theme apply`` refuses on, so a
    warning here and a refusal there cannot disagree.
    """
    argv: List[str] = []
    if preset_id:
        argv += ["--preset", preset_id]
    if minimum is not None:
        argv += ["--min", str(minimum)]
    if as_json:
        argv.append("--json")
    return runner.python_tool(paths.cli_module_path(CONTRAST_TOOL), argv)


def fontconfig_argv(output_dir: Optional[Path] = None, to_stdout: bool = False,
                    write_repo_default: bool = False, check: bool = False) -> List[str]:
    """A ``gen_fontconfig`` argument list.

    That tool writes into ``--output-dir``, not ``--config-home``, and it has no
    ``--dry-run``: ``--print`` is the render-nothing form. Both facts come from its
    own ``--help``, and guessing either would be an exit 2 at the worst moment --
    after a font change had already been written to settings.ini.
    """
    argv: List[str] = []
    if output_dir:
        argv += ["--output-dir", str(output_dir)]
    if to_stdout:
        argv.append("--print")
    if write_repo_default:
        argv.append("--write-repo-default")
    if check:
        argv.append("--check")
    return argv


def generate_fontconfig(output_dir: Optional[Path] = None,
                        to_stdout: bool = False) -> runner.Outcome:
    """Re-render fonts.conf after a font choice changes."""
    return runner.python_tool(paths.cli_module_path(FONTCONFIG_TOOL),
                              fontconfig_argv(output_dir, to_stdout))


def tool_outcomes() -> Dict[str, str]:
    """Which of this project's own tools can be run, for a status row.

    These are Python files in the checkout rather than installed binaries -- Part 6
    installs them -- so "present" means the file exists and the interpreter does,
    which is a different question from "on PATH".
    """
    found: Dict[str, str] = {}
    for tool in (THEME_TOOL, ANIM_TOOL, FONTCONFIG_TOOL, CONTRAST_TOOL,
                 "gen_monitors_lua", "gen_glass_lua", "iarch_doctor",
                 "iarch_gamemode", "iarch_focus"):
        try:
            found[tool] = str(paths.cli_module_path(tool))
        except paths.PathError:
            found[tool] = ""
    return found
