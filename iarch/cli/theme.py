#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iarch-theme — apply one glass design preset across every surface at once.

This is the capstone the per-surface generators in this directory build toward.
``gen_glass_lua``, ``gen_animations_lua``, ``render_gtk_css``,
``render_kvantum``, ``gen_fontconfig`` and ``render_noctalia`` each know how to
render one surface from the design tokens and a colour preset. ``iarch-theme``
imports those render functions — it never shells out to them — and drives them
all from a single choice, so a person changes the whole desktop's palette and
intensity in one step and every surface agrees.

The contract, which docs/ARCHITECTURE.md and iarch/lib/renderers.py state:

* read user state through ``iarch.lib.configstore`` and write only generated
  files, through ``configstore.write_generated`` — never a file this project did
  not generate;
* gate on contrast first: a preset whose colours fail the WCAG floor that
  ``contrast_check`` measures is refused before anything is written (exit 1);
* render every surface, then write — if a surface fails to render or a write
  fails part way, every file already touched is put back byte for byte, so the
  desktop is never left half-themed;
* skip a file whose rendered bytes already match what is on disk, so re-applying
  the same theme neither rewrites nor re-backs-up anything;
* ask the compositor and the shell to reload with the commands verified against
  the releases this repo targets, guarded so a missing binary is a warning and
  not a failure;
* never start a desktop, and exit 0 on success, 1 when a gate refuses, 2 on a
  usage or data error.

Two things a theme nominally covers are handled with care rather than applied
blind, because the runtime mechanism could not be verified:

* The cursor. ``themes/theme.lua`` already exports the cursor through ``hl.env``
  when the session starts, and every preset in data/design/presets ships the
  same Bibata-Modern-Classic at 24px, so a reload re-exports exactly what the
  chosen preset names — applying a preset is a no-op for the cursor. iarch-theme
  verifies that agreement and, if a future preset ever names a different cursor,
  says so rather than inventing a runtime switch there is no verified call for.
* The icon theme. TODO(verify) TP-19 in docs/UNVERIFIED.md: no runtime mechanism
  to set the icon theme is verified against the toolkit releases in use — the
  ``-gtk-icon-theme`` in data/design/gtk.json is a CSS property, not the
  settings.ini key, that file is deliberately not shipped, and qt6ct is verified
  to write the style only. So iarch-theme reports the preset's icon theme and
  does not try to set it.

Usage:
    python3 iarch/cli/theme.py apply [PRESET] [--intensity NAME]
                                     [--config-home DIR] [--no-reload] [--dry-run]
    python3 iarch/cli/theme.py current [--config-home DIR]

``PRESET`` is a colour preset id from data/design/presets (default: the
``theme.colour_preset`` in the user's settings, else ``midnight-glass``).
``--intensity`` is crystal, frosted, soft or performance (default: the user's
``theme.intensity``, else the preset's own ``default_intensity``).
``--config-home`` is the live config root the surfaces are written under
(default ``~/.config``, where hyprland.lua, GTK, Kvantum, fontconfig and
Noctalia actually read them); tests point it at a temporary directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)
from iarch.cli import (  # noqa: E402  (repo-root import by design)
    contrast_check,
    gen_animations_lua,
    gen_fontconfig,
    gen_glass_lua,
    render_gtk_css,
    render_kvantum,
    render_noctalia,
)

DEFAULT_PRESET = "midnight-glass"
PRESET_DIR = contrast_check.PRESET_DIR
THEME_LUA = ROOT / ".config" / "hypr" / "themes" / "theme.lua"

EXIT_OK = 0
EXIT_REFUSED = 1  # a safety gate (contrast) refused the change
EXIT_USAGE = 2    # bad arguments, unknown preset/intensity, render or environment error

# The cursor themes/theme.lua exports statically through hl.env. Every preset
# ships these same values today, so applying a preset does not move the cursor;
# iarch-theme only checks the chosen preset still agrees with the static export.
_CURSOR_THEME_KEY = "XCURSOR_THEME"
_CURSOR_SIZE_KEY = "XCURSOR_SIZE"

# Verified against the releases this repo targets, so neither needs a
# TODO(verify) (see docs/UNVERIFIED.md):
#   hyprctl reload             — Hyprland v0.57.2, docs/hyprctl.1.rst: "Force a
#                                reload of the config file."
#   noctalia msg config-reload — Noctalia v5.4.1, src/cli/schema_msg.h:472, the
#                                configReload subcommand under `msg`.
# Both are guarded by shutil.which and run non-fatally: a desktop without them
# on PATH (a chroot, CI, a fresh install before the session runs) is a warning.
RELOAD_COMMANDS: Tuple[Tuple[str, ...], ...] = (
    ("hyprctl", "reload"),
    ("noctalia", "msg", "config-reload"),
)
RELOAD_TIMEOUT_SECONDS = 30

# A render or data failure from any surface is a usage/data error (exit 2), the
# same class of failure the individual generators report.
RENDER_ERRORS = (
    contrast_check.ContrastError,
    gen_glass_lua.GlassError,
    gen_animations_lua.AnimationError,
    render_gtk_css.GtkError,
    render_kvantum.KvantumError,
    gen_fontconfig.FontconfigError,
    render_noctalia.NoctaliaError,
)


class ThemeError(RuntimeError):
    """A usage or data problem: unknown preset, bad path, unreadable settings."""


class RefusedError(RuntimeError):
    """A safety gate refused to apply the theme; nothing was written."""


# ---------------------------------------------------------------- small helpers


def label(path: Path) -> str:
    """A path for a message: repository-relative when it is inside the repo."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def display(path: Path) -> str:
    """A path for a message: collapsed under ``~`` when it is in the home dir."""
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def _say(message: str) -> None:
    print(message)


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


# ---------------------------------------------------------------- user settings


def _user_theme(env: Optional[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
    """The ``theme.*`` the user actually wrote, ignoring repository defaults.

    Reading the raw user file rather than ``configstore.load`` keeps the two
    fallbacks distinct: a colour preset the user never chose falls back to
    ``midnight-glass``, but an intensity the user never chose falls back to the
    *preset's own* ``default_intensity`` rather than to the repository default,
    so a preset that ships ``crystal`` is applied at ``crystal`` until the
    person says otherwise.
    """
    path = configstore.user_path("settings", env)
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    theme = data.get("theme") if isinstance(data, dict) else None
    if not isinstance(theme, dict):
        return None, None
    colour = theme.get("colour_preset")
    intensity = theme.get("intensity")
    return (
        colour if isinstance(colour, str) and colour else None,
        intensity if isinstance(intensity, str) and intensity else None,
    )


def _resolve(colour_arg: Optional[str], intensity_arg: Optional[str],
             env: Optional[Dict[str, str]]) -> Tuple[Dict[str, Any], Dict[str, Any], str, str]:
    """Settle the effective tokens, preset, colour id and intensity name.

    Order: the command line, then what the user recorded in settings, then the
    preset's own default, then the tokens' default. An unknown preset or
    intensity is a usage error (exit 2) that names the valid choices.
    """
    tokens = gen_glass_lua.load_tokens()
    user_colour, user_intensity = _user_theme(env)
    colour = colour_arg or user_colour or DEFAULT_PRESET

    if not (PRESET_DIR / f"{colour}.json").is_file():
        known = ", ".join(sorted(p.stem for p in PRESET_DIR.glob("*.json")))
        raise ThemeError(f"unknown colour preset {colour!r}; data/design/presets holds: {known}")
    preset = gen_glass_lua.load_preset(tokens, colour)  # also checks the id matches

    intensity = (intensity_arg or user_intensity
                 or preset.get("default_intensity") or tokens.get("default_intensity", "frosted"))
    if intensity not in tokens["intensities"]:
        known = ", ".join(sorted(tokens["intensities"]))
        raise ThemeError(f"unknown intensity {intensity!r}; the tokens define: {known}")
    return tokens, preset, colour, intensity


# ---------------------------------------------------------------- safety gates


def _contrast_gate(colour: str, preset: Dict[str, Any]) -> Tuple[int, float]:
    """Refuse a preset that fails the WCAG floor; report the gate when it passes.

    This runs before anything is rendered or written, so a preset that cannot be
    applied accessibly never touches the desktop. Pairs contrast_check marks
    ``info`` (a decorative hairline, the terminal's dim colours) are measured but
    never gated, exactly as contrast_check itself treats them.
    """
    results = contrast_check.evaluate(preset)
    failed = [r for r in results if r.kind != "info" and not r.passed]
    if failed:
        detail = "; ".join(f"{r.label} {r.ratio:.2f}:1 < {r.minimum:.1f}" for r in failed)
        raise RefusedError(
            f"contrast gate refused {colour!r} — "
            f"{len(failed)} pair(s) below the WCAG floor: {detail}")
    gated = sum(1 for r in results if r.kind != "info")
    lowest = min((r.ratio for r in results if r.kind != "info"), default=0.0)
    return gated, lowest


def _cursor_in_theme_lua() -> Tuple[Optional[str], Optional[int]]:
    """The cursor themes/theme.lua exports statically, read from the committed file."""
    try:
        text = THEME_LUA.read_text(encoding="utf-8")
    except OSError:
        return None, None
    theme = re.search(rf'"{_CURSOR_THEME_KEY},([^"]+)"', text)
    size = re.search(rf'"{_CURSOR_SIZE_KEY},(\d+)"', text)
    return (theme.group(1) if theme else None, int(size.group(1)) if size else None)


def _report_cursor(preset: Dict[str, Any]) -> None:
    """Confirm the preset's cursor is the one theme.lua re-exports on reload."""
    cursor = preset.get("cursor") or {}
    want_theme, want_size = cursor.get("theme"), cursor.get("size")
    static_theme, static_size = _cursor_in_theme_lua()
    if static_theme is None or static_size is None:
        _warn(f"could not read the static cursor from {label(THEME_LUA)}; skipped the cursor check")
        return
    if (want_theme, want_size) == (static_theme, static_size):
        _say(f"cursor: {static_theme} {static_size}px — themes/theme.lua exports it through "
             "hl.env, so the reload re-applies it (unchanged)")
        return
    # A future preset could name a different cursor. There is no verified call to
    # change XCURSOR_THEME/HYPRCURSOR_THEME on a running session, so iarch-theme
    # does not invent one; it says the session cursor stays the static export.
    _warn(f"preset cursor {want_theme} {want_size}px differs from the static "
          f"{static_theme} {static_size}px in themes/theme.lua; iarch-theme does not switch the "
          f"cursor at runtime, so the session cursor stays {static_theme} {static_size}px")


def _report_icon(preset: Dict[str, Any]) -> None:
    """Report the preset's icon theme without applying it (no verified mechanism)."""
    theme = (preset.get("icons") or {}).get("theme")
    if not theme:
        return
    # TODO(verify) TP-19: setting the icon theme at runtime is not verified
    # against the toolkit releases in use, so this reports and does not apply.
    _say(f"icon theme: {theme} — reported, not applied (no verified runtime mechanism; "
         "TODO(verify) TP-19 in docs/UNVERIFIED.md)")


# ---------------------------------------------------------------- the render plan


def _rendered(path: Path, body: str) -> str:
    """Exactly the bytes ``configstore.write_generated`` will put on disk."""
    if path.suffix == ".json":
        data = json.loads(body)
        return json.dumps({"_generated": configstore.GENERATED_HEADER, **data},
                          indent=2, ensure_ascii=False) + "\n"
    return f"{configstore.header_for(path)}\n{body}\n"


def _plan(tokens: Dict[str, Any], preset: Dict[str, Any], intensity: str,
          config_home: Path) -> List[Tuple[Path, str, str]]:
    """Render every surface under ``config_home``; return (path, body, rendered).

    The Hyprland files go where hyprland.lua reads them (``$HOME/.config/hypr``),
    and each toolkit's files go where that toolkit reads them, so the render
    reaches the live session rather than iarch's own config dir. Nothing here
    writes: it only produces bytes, so a failure in any one surface leaves the
    desktop untouched.
    """
    targets: List[Tuple[Path, str, str]] = []

    def add(path: Path, body: str) -> None:
        targets.append((path, body, _rendered(path, body)))

    # Hyprland: the glass decoration/general block and the animation tree, both
    # required last by theme.lua / animations.lua through a pcall.
    add(config_home / "hypr" / "generated" / "glass.lua",
        gen_glass_lua.build(tokens, preset, intensity))
    add(config_home / "hypr" / "generated" / "animations.lua",
        gen_animations_lua.build(tokens, gen_animations_lua.load_surface(), intensity))

    # GTK 4 and GTK 3, each under its own gtk-<v>.0 directory.
    gtk_surface = render_gtk_css.load_surface()
    for version in render_gtk_css.VERSIONS:
        path, body = render_gtk_css.targets_for(
            version, tokens, preset, gtk_surface, intensity, config_home / f"gtk-{version}.0")
        add(path, body)

    # Kvantum: the pointer file and the theme it names.
    targets.extend(
        (p, b, _rendered(p, b)) for p, b in render_kvantum.targets_for(
            tokens, render_kvantum.load_surface(), preset, intensity, config_home / "Kvantum"))

    # fontconfig: global, so it takes no preset or intensity.
    targets.extend(
        (p, b, _rendered(p, b)) for p, b in gen_fontconfig.targets_for(
            tokens, gen_fontconfig.load_surface(), config_home / "fontconfig"))

    # Noctalia: the shell config and the palette it selects.
    targets.extend(
        (p, b, _rendered(p, b)) for p, b in render_noctalia.user_targets(
            tokens, render_noctalia.load_surface(), preset, intensity, config_home / "noctalia"))

    return targets


def _on_disk_equals(path: Path, rendered: str) -> bool:
    """True when ``path`` already holds exactly ``rendered``."""
    try:
        return path.is_file() and path.read_text(encoding="utf-8") == rendered
    except (OSError, UnicodeDecodeError):
        return False


def _write_all(writes: Sequence[Tuple[Path, str]], env: Optional[Dict[str, str]]) -> List[Path]:
    """Write every target, or put them all back byte for byte if any write fails."""
    snapshot: Dict[Path, Optional[bytes]] = {
        path: (path.read_bytes() if path.is_file() else None) for path, _ in writes}
    try:
        for path, body in writes:
            configstore.write_generated(path, body, env)
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
    return [path for path, _ in writes]


# ---------------------------------------------------------------- reload + settings


def _reload(env: Optional[Dict[str, str]], dry_run: bool, no_reload: bool) -> None:
    """Ask the compositor and the shell to re-read their config, non-fatally."""
    if no_reload:
        _say("reload: skipped (--no-reload)")
        return
    if dry_run:
        _say("reload: skipped (dry run)")
        return
    for command in RELOAD_COMMANDS:
        printable = " ".join(command)
        if shutil.which(command[0]) is None:
            _warn(f"{command[0]} not found on PATH; skipped `{printable}` "
                  "(is the session running?)")
            continue
        try:
            subprocess.run(command, check=False, timeout=RELOAD_TIMEOUT_SECONDS,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            _warn(f"reload: `{printable}` failed: {exc}")
        else:
            _say(f"reload: ran `{printable}`")


def _persist(colour: str, intensity: str, env: Optional[Dict[str, str]]) -> Tuple[Path, bool]:
    """Record the applied theme in the user's settings; return (path, changed).

    ``configstore.load`` returns the repository defaults with the user's file
    merged on top, so saving that document back keeps every key the user already
    had and fills in the rest, and the file it writes always validates against
    data/schemas/settings.schema.json. Only ``theme`` is changed here; the coarse
    Part-1 ``preset`` and ``effects`` switches are left as they are, and
    reconciling the two is Part 4 settings-app work.

    Re-applying the theme that is already recorded is a no-op: it neither rewrites
    the file nor rotates a backup, matching how the generated files are skipped
    when their bytes already match.
    """
    path = configstore.user_path("settings", env)
    user_colour, user_intensity = _user_theme(env)
    if path.is_file() and user_colour == colour and user_intensity == intensity:
        return path, False
    settings = configstore.load("settings", ROOT, env)
    settings["theme"] = {"colour_preset": colour, "intensity": intensity}
    return configstore.save("settings", settings, env), True


# ---------------------------------------------------------------- subcommands


def _config_home(raw: str) -> Path:
    home = Path(raw).expanduser()
    if not home.is_absolute():
        raise ThemeError(f"--config-home must be an absolute path: {raw!r}")
    return home


def cmd_apply(args: argparse.Namespace, env: Dict[str, str]) -> int:
    config_home = _config_home(args.config_home)
    tokens, preset, colour, intensity = _resolve(args.preset, args.intensity, env)

    _say(f"iArch by Safari — apply {colour!r} at {intensity!r} intensity")
    gated, lowest = _contrast_gate(colour, preset)
    _say(f"contrast gate: {gated} gated pair(s), lowest {lowest:.2f}:1 — pass")

    targets = _plan(tokens, preset, intensity, config_home)
    _report_cursor(preset)
    _report_icon(preset)

    writes: List[Tuple[Path, str]] = []
    skips: List[Path] = []
    for path, body, rendered in targets:
        if _on_disk_equals(path, rendered):
            skips.append(path)
        else:
            writes.append((path, body))

    if args.dry_run:
        for path, _ in writes:
            _say(f"  would write  {display(path)}")
        for path in skips:
            _say(f"  unchanged    {display(path)}")
        _say(f"[dry-run] {len(writes)} file(s) to write, {len(skips)} unchanged; "
             "no settings change, no reload")
        return EXIT_OK

    for path, _ in writes:
        _say(f"  write        {display(path)}")
    for path in skips:
        _say(f"  unchanged    {display(path)}")
    written = _write_all(writes, env)

    settings_path, changed = _persist(colour, intensity, env)
    verb = "recorded" if changed else "already recorded"
    _say(f"settings: {verb} theme.colour_preset={colour}, theme.intensity={intensity} "
         f"in {display(settings_path)}")

    _reload(env, dry_run=False, no_reload=args.no_reload)
    _say(f"applied {colour!r} at {intensity!r}: wrote {len(written)}, unchanged {len(skips)}")
    return EXIT_OK


def cmd_current(args: argparse.Namespace, env: Dict[str, str]) -> int:
    config_home = _config_home(args.config_home)
    _tokens, preset, colour, intensity = _resolve(None, None, env)
    user_colour, user_intensity = _user_theme(env)

    _say("iArch by Safari — current theme")
    _say(f"  colour preset: {colour}" + ("" if user_colour else "   (repository default)"))
    _say(f"  intensity:     {intensity}" + ("" if user_intensity else "   (preset default)"))
    _say(f"  config home:   {display(config_home)}")
    cursor = preset.get("cursor") or {}
    _say(f"  cursor:        {cursor.get('theme')} {cursor.get('size')}px "
         "(static in themes/theme.lua, re-applied on reload)")
    icons = preset.get("icons") or {}
    _say(f"  icon theme:    {icons.get('theme')} (reported, not applied — TODO(verify) TP-19)")
    _say(f"  settings file: {display(configstore.user_path('settings', env))}")
    return EXIT_OK


# ---------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iarch-theme", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    default_home = str(Path.home() / ".config")

    apply_p = sub.add_parser("apply", help="render and apply a preset across every surface")
    apply_p.add_argument("preset", nargs="?",
                         help=f"colour preset id (default: settings theme.colour_preset, "
                              f"else {DEFAULT_PRESET})")
    apply_p.add_argument("--intensity",
                         help="crystal, frosted, soft or performance (default: settings "
                              "theme.intensity, else the preset's own default_intensity)")
    apply_p.add_argument("--config-home", default=default_home,
                         help=f"live config root to write under (default {default_home})")
    apply_p.add_argument("--no-reload", action="store_true",
                         help="write the files but do not ask the compositor or shell to reload")
    apply_p.add_argument("--dry-run", action="store_true",
                         help="render and report only; write nothing, change no settings, "
                              "reload nothing")
    apply_p.set_defaults(func=cmd_apply)

    current_p = sub.add_parser("current", help="show the theme that apply would use")
    current_p.add_argument("--config-home", default=default_home,
                           help=f"live config root (default {default_home})")
    current_p.set_defaults(func=cmd_current)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ
    try:
        return args.func(args, env)
    except RefusedError as exc:
        print(f"iarch-theme: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (ThemeError, configstore.ConfigError, OSError) + RENDER_ERRORS as exc:
        print(f"iarch-theme: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
