# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Which settings path does what, in one table.

A row on a page says ``setting="theme.intensity"``. Something has to know that
turning that into reality means running ``iarch-theme apply``, that the tool writes
the key back itself, that the derived coarse switches have to be recomputed, and
that a compositor reload is what makes any of it visible. That knowledge is this
module, and it lives here rather than in the pages for one reason: a page that
knew how to change the machine would be a second place the rules live, and the
rules are the part that has to be testable.

**Who writes the key.** The split that decides everything below:

===========================================  ======================================
path                                         written by
===========================================  ======================================
``theme.colour_preset``, ``theme.intensity`` ``iarch-theme apply`` writes them back
``animation.*``                              ``iarch-anim`` owns the whole section
``modes.game.active``, ``modes.focus.active`` ``iarch-gamemode`` / ``iarch-focus``
``preset``, ``effects.*``                    derived, never set: see :func:`derived`
``fonts.*``                                  this project, through
                                             :mod:`~iarch_settings.services.gtk_settings`
``display.monitors``                         this project, then ``gen_monitors_lua``
``glass.leaves``, ``glass.per_app_opacity``  this project, then the compositor
``startup.autostart``                        this project, then
                                             :func:`~iarch_settings.services.autostart.project`
``theme.colour_mode``, ``app.*``             this project
``theme.accent``                             nobody: see :data:`UNPROJECTED`
===========================================  ======================================

For the first three rows the change this module builds carries **no settings
write**, because a second writer of one key is how a file ends up saying two
things: the tool writes the key, and the window re-reads the store when the report
says the change succeeded. For the rest, the change carries the dotted paths and
:mod:`~iarch_settings.services.apply` writes them before any command runs, so a
command that reads ``settings.json`` sees the new state.

Nothing here starts a process. Every command is a ``(label, callable)`` pair handed
to :class:`~iarch_settings.services.apply.Change`, which is the only thing that runs
them and the only thing that rolls back when one fails -- so a test can build any
change in this table and assert on its argv without a compositor, a shell or a
display in the room.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import paths
from . import (apply, autostart, config_store, gtk_settings, hypr, noctalia, runner,
               themes)

ANIM_TOOL = "iarch_anim"
GAMEMODE_TOOL = "iarch_gamemode"
FOCUS_TOOL = "iarch_focus"
MONITORS_TOOL = "gen_monitors_lua"
GLASS_TOOL = "gen_glass_lua"
FONTCONFIG_TOOL = "gen_fontconfig"

#: The keys this project refuses to offer, each with the reason and the thing that
#: would have to exist for the refusal to end.
#:
#: ``theme.accent`` is in ``data/schemas/settings.schema.json``, which says the
#: contrast gate is run again before anything is written when it is set. The gate
#: exists (``iarch/cli/contrast_check.py --preset``) and so does the check; what does
#: not exist is a renderer that takes the override. ``render_gtk_css.build_context``
#: reads the accent out of the preset's own palette, ``theme.py apply`` has no flag
#: for one, and every preset in ``data/design/presets/`` ships an accent that has
#: already passed the gate. So writing the key would store a value nothing reads, and
#: a switch that changes nothing on screen is worse than no switch: the Appearance
#: page shows the value and this sentence instead, and docs/UNVERIFIED.md SET-09
#: records what is missing.
UNPROJECTED: Dict[str, str] = {
    "theme.accent":
        "no renderer reads an accent override: the sheets take the accent from the "
        "colour preset's own palette, which has already passed the contrast gate",
}

#: The paths that are computed from other paths rather than set, with the path that
#: drives each. ``config_store.derive_coarse`` is the function that computes them and
#: ``docs/SETTINGS-APP.md`` is where the derivation is written down for a person;
#: this table is the one a test walks, so "the coarse switches are derived" is a claim
#: the build checks rather than one the documentation asserts.
DERIVED_FROM: Dict[str, str] = {
    "preset": "theme.intensity",
    "effects.blur": "theme.intensity",
    "effects.transparency": "theme.intensity",
    "effects.animations": "animation.preset",
    "effects.shadows": "theme.intensity",
}

#: The document's own metadata: not switches, and not derived from one either.
METADATA = ("_copyright", "version", "notes")

_ACCENT = re.compile(r"^#[0-9a-fA-F]{6}$")

#: The coarse switch's two values, which ``config_store.derive_coarse`` computes and
#: nothing sets. Listed so a page can show them without repeating the strings.
PRESET_VALUES = (("glass", "Glass"), ("performance", "Performance"))

SPEED_BOUNDS = (0.5, 2.0)
"""``animation.speed``'s bounds: tokens.json:motion.animation.speed_multiplier."""


class ControlError(RuntimeError):
    """A change this module will not build. The message is the reason."""


# --------------------------------------------------------------------- routes


class Route:
    """One settings path prefix and what changing it means.

    ``owner`` says who writes the key: ``"tool"`` for a command that writes
    settings.json itself, ``"project"`` for a key this application writes. ``risky``
    marks the change that needs the countdown dialog, because it can make the dialog
    itself unreadable -- a monitor's scale or resolution, and nothing else in the
    product qualifies.
    """

    __slots__ = ("prefix", "owner", "label", "handler", "risky", "reload_session",
                 "verify_configerrors", "page", "note")

    def __init__(self, prefix: str, owner: str, label: str, handler: str, *,
                 risky: bool = False, reload_session: bool = True,
                 verify_configerrors: bool = True, page: str = "", note: str = "") -> None:
        self.prefix = prefix
        self.owner = owner
        self.label = label
        self.handler = handler
        self.risky = risky
        self.reload_session = reload_session
        self.verify_configerrors = verify_configerrors
        self.page = page
        self.note = note

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Route({self.prefix!r}, owner={self.owner!r})"


#: Longest prefix first, so ``animation.event_overrides`` is matched by its own row
#: and not by the ``animation`` one above it.
ROUTES: Tuple[Route, ...] = (
    Route("theme.colour_preset", "tool", "Colour preset", "theme",
          page="appearance",
          note="iarch-theme apply renders every surface and writes the key back"),
    Route("theme.intensity", "tool", "Glass intensity", "theme", page="appearance",
          note="the intensity decides the blur, the shadow and every surface opacity"),
    Route("theme.colour_mode", "project", "Light or dark", "colour_mode",
          page="appearance", reload_session=False, verify_configerrors=False,
          note="one value, two projections: the shell's theme-mode-set verb and "
               "gtk-application-prefer-dark-theme, written together so they cannot drift"),
    Route("theme.accent", "none", "Accent override", "unprojected", page="appearance",
          note=UNPROJECTED["theme.accent"]),
    Route("animation.event_overrides", "tool", "One animation event", "animation_event",
          page="animations",
          note="iarch-anim toggle flips the override and writes the section itself"),
    Route("animation.preset", "tool", "Motion preset", "animation_preset",
          page="animations"),
    Route("animation.speed", "tool", "Motion speed", "animation_speed",
          page="animations",
          note="above 1 is faster, because the multiplier divides every duration"),
    Route("animation.reduce_motion", "tool", "Reduce motion", "animation_reduce",
          page="animations",
          note="renders the minimal preset with every duration capped; it does not "
               "remove animation from the session, so the coarse effects.animations "
               "switch stays on"),
    Route("fonts", "project", "Fonts and icons", "fonts", page="fonts",
          reload_session=False, verify_configerrors=False,
          note="projected into both settings.ini files and into fontconfig; no "
               "compositor reload is involved, so a compositor is not asked about it"),
    Route("display.monitors", "project", "Monitor arrangement", "monitors",
          page="display", risky=True,
          note="the one change that can make its own confirmation dialog unreadable, "
               "which is why it gets the countdown and a revert"),
    Route("glass.leaves", "project", "One compositor effect", "glass_leaf",
          page="glass", reload_session=False,
          note="applied to the running compositor with hyprctl and remembered here; "
               "the compositor's own config still holds the intensity's value, so a "
               "config reload or a login that does not start this application gets "
               "the intensity's value back"),
    Route("glass.per_app_opacity", "project", "Per-window opacity", "per_app_opacity",
          page="glass",
          note="rendered into the compositor's glass module and then reloaded, so it "
               "survives a relogin the way a leaf override does not"),
    Route("modes.game.active", "tool", "Game mode", "mode", page="features",
          note="iarch-gamemode saves the intensity and motion preset it replaced, so "
               "turning it off restores them rather than guessing"),
    Route("modes.focus.active", "tool", "Focus mode", "mode", page="features",
          note="iarch-focus restores the Do Not Disturb flag and the dim it saved; "
               "those are runtime state, so its status command compares the record "
               "with what the shell and the compositor answer now"),
    Route("startup.autostart", "project", "Startup entries", "autostart",
          page="startup", reload_session=False, verify_configerrors=False,
          note="projected into ~/.config/autostart/ as one .desktop file per entry; "
               "the session's generator reads them at the next login, so nothing is "
               "reloaded now"),
    Route("effects", "derived", "Effects", "unprojected", page="home",
          note="derived, never set: config_store.derive_coarse computes all four from "
               "theme.intensity, glass.leaves and animation.preset, so the switch that "
               "changes effects.blur is the one that changes the intensity or the blur "
               "leaf. A second writer here would be two opinions in one file, which is "
               "exactly what the reconciliation Part 4 was asked for exists to prevent"),
    Route("preset", "derived", "Master preset", "unprojected", page="home",
          note="derived, never set: it follows theme.intensity, which is the switch "
               "that changes it"),
    Route("_copyright", "metadata", "The file's copyright line", "unprojected",
          note="document metadata, not a setting"),
    Route("version", "metadata", "The document's version", "unprojected",
          note="document metadata: config_store migrates a version 1 document to "
               "version 2 and writes this key itself"),
    Route("notes", "metadata", "The document's own note", "unprojected",
          note="document metadata, kept so that a person who opens the file in a text "
               "editor reads what the sections mean"),
    Route("app", "project", "This window", "window", page="", reload_session=False,
          verify_configerrors=False,
          note="the window's own size and the page it opens on; no surface outside "
               "this application is involved"),
)


def route_for(dotted: str) -> Optional[Route]:
    """The route that owns a settings path, or ``None`` when nothing does."""
    text = str(dotted)
    best: Optional[Route] = None
    for route in ROUTES:
        if text == route.prefix or text.startswith(f"{route.prefix}."):
            if best is None or len(route.prefix) > len(best.prefix):
                best = route
    return best


def owns(dotted: str) -> bool:
    """Whether a page may offer this path as a switch.

    ``tool`` counts as owned: the key is written by a command the change runs, which
    is this application changing it, just not with its own hand on the file. The three
    owners that do not count are ``none`` (nothing projects it), ``derived`` (another
    path decides it) and ``metadata`` (it is not a setting at all).
    """
    route = route_for(dotted)
    return route is not None and route.owner in ("project", "tool")


def refusal_for(dotted: str) -> str:
    """Why a path is not offered as a switch, or ``""`` when it is offered."""
    route = route_for(dotted)
    if route is None:
        return f"{dotted} is not a path this application changes"
    if route.owner in ("project", "tool"):
        return ""
    return route.note


def owner_of(dotted: str) -> str:
    """``tool``, ``project`` or ``none``: who writes the key."""
    route = route_for(dotted)
    return route.owner if route else "none"


def label_for(dotted: str) -> str:
    """The sentence a toast shows for a change to this path."""
    route = route_for(dotted)
    return route.label if route else str(dotted)


def derived(document: Mapping[str, Any], root: Optional[Path] = None) -> Dict[str, Any]:
    """``preset`` and ``effects`` recomputed from the sections that own them."""
    result = config_store.derive_coarse(document, root)
    return {"preset": result.get("preset"), **{f"effects.{key}": value
                                               for key, value in (result.get("effects") or {}).items()}}


# --------------------------------------------------------------- the handlers


def _theme_change(preset: str, intensity: str, reduce_motion: str,
                  config_home: Optional[Path], change: apply.Change) -> apply.Change:
    """``iarch-theme apply``: the tool writes the keys back, so the change does not."""
    change.add_command(
        f"render every surface for {preset} at {intensity}",
        lambda: themes.apply_theme(preset, intensity, reduce_motion=reduce_motion,
                                   config_home=config_home))
    return change


def _colour_mode_change(mode: str, change: apply.Change,
                        config_home: Optional[Path]) -> apply.Change:
    """One value, two projections: the shell's verb and the GTK settings key."""
    dark = mode == "dark"
    change.settings["theme.colour_mode"] = mode
    change.add_command(
        f"tell the shell the mode is {mode}",
        lambda: noctalia.set_theme_mode(mode))
    # The GTK half goes through the same writer the Fonts page uses, so both files
    # get the key, both get a backup, and neither gets a GENERATED header they should
    # not have.
    change.add_command(
        "write gtk-application-prefer-dark-theme into both settings.ini files",
        lambda: _write_gtk({"gtk-application-prefer-dark-theme":
                            gtk_settings.bool_value(dark)}, config_home))
    return change


def _write_gtk(values: Mapping[str, str], config_home: Optional[Path]) -> runner.Outcome:
    """``gtk_settings.write`` as the ``(label, callable)`` shape a change wants."""
    try:
        written = gtk_settings.write(dict(values), config_home=config_home)
    except (gtk_settings.GtkSettingsError, OSError) as exc:
        return runner.Outcome(["gtk-settings", "write"], runner.FAILED, reason=str(exc))
    return runner.Outcome(["gtk-settings", "write", str(len(values)), "keys"], runner.OK,
                          stdout="\n".join(str(path) for path in written))


def _fontconfig_change(change: apply.Change, config_home: Optional[Path]) -> apply.Change:
    """fontconfig is the second half of a font change: GTK's keys are not enough.

    That tool takes ``--output-dir`` and has no ``--config-home``
    (:func:`iarch_settings.services.themes.fontconfig_argv` records the fact from its
    own ``--help``), so the directory is spelled out here: ``<config_home>/fontconfig``
    is where the session reads ``fonts.conf``, and letting the tool default would put
    it somewhere nothing reads.
    """
    output_dir = Path(config_home) / "fontconfig" if config_home else None
    change.add_command(
        "render the fontconfig sheet",
        lambda: themes.generate_fontconfig(output_dir))
    return change


def _run_tool(tool: str, args: Sequence[str], config_home: Optional[Path] = None,
              env: Optional[Mapping[str, str]] = None) -> runner.Outcome:
    """One of ``iarch/cli/``'s generators, aimed at the live session.

    Two things have to be true at once, and neither is the tool's default:

    * **Where it writes.** Each generator's own default destination is
      ``configstore.config_dir()`` -- ``~/.config/iarch/<tool>`` -- while the session
      reads ``~/.config/hypr/``. So the destination is always passed explicitly with
      ``--output`` (or ``--output-dir`` for fontconfig), computed by
      :func:`iarch_settings.services.apply.config_target`, rather than left to a
      default that writes somewhere nothing reads.
    * **What it reads.** ``gen_monitors_lua`` renders from ``settings.json`` through
      :mod:`iarch.lib.configstore`, which resolves the user's file from
      ``IARCH_CONFIG_DIR`` or from ``HOME``. The apply pipeline writes the document
      before the command runs, so the child is given the same two variables the
      pipeline used: a generator that read a different settings file than the one just
      written would render the previous state and report success.

    ``theme.py`` and ``iarch_anim.py`` are not reached through here: they take
    ``--config-home`` and :mod:`iarch_settings.services.themes` never forgets it.
    """
    environ = dict(os.environ if env is None else env)
    if config_home is not None:
        environ["HOME"] = str(Path(config_home).parent)
        environ["IARCH_CONFIG_DIR"] = str(Path(config_home) / "iarch")
        environ["IARCH_STATE_DIR"] = str(Path(config_home).parent / ".local" / "state" / "iarch")
    return runner.python_tool(paths.cli_module_path(tool), args, env=environ)


def _anim_json() -> Dict[str, Any]:
    """``iarch-anim current --json`` parsed, or ``{}`` when it cannot be asked."""
    import json  # noqa: PLC0415

    outcome = themes.run_anim("current", as_json=True)
    if outcome.verdict != runner.OK:
        return {}
    try:
        payload = json.loads(outcome.stdout)
    except ValueError:
        return {}
    return payload if isinstance(payload, Mapping) else {}


def change_for(dotted: str, value: Any, *, store: Optional[config_store.Store] = None,
               settings: Optional[Mapping[str, Any]] = None,
               config_home: Optional[Path] = None, root: Optional[Path] = None,
               env: Optional[Mapping[str, str]] = None,
               reduce_motion: str = "auto") -> apply.Change:
    """The change a row's new value means. Raises :class:`ControlError` to refuse.

    ``settings`` is the document as it stands *after* the change, which the caller
    has usually already computed; when it is missing the store's own copy is used.
    The refusal cases are the ones where building a change would be a lie: a path
    nothing owns, a value outside the bounds the generator behind it enforces, an
    animation leaf the active preset does not declare.
    """
    route = route_for(dotted)
    if route is None:
        raise ControlError(f"{dotted} is not a path this application changes")
    if route.owner not in ("project", "tool"):
        raise ControlError(f"{dotted} cannot be set: {route.note}")

    document: Dict[str, Any] = _copy(settings if settings is not None
                                     else (store.data if store is not None else {}))
    theme = document.get("theme") or {}
    preset = str(theme.get("colour_preset") or themes.preset_ids(root)[0])
    intensity = str(theme.get("intensity") or themes.default_intensity(root))
    change = apply.Change(route.label, risky=route.risky,
                          reload_session=route.reload_session,
                          verify_configerrors=route.verify_configerrors,
                          config_home=config_home)

    if route.handler == "theme":  # noqa: PLR0912 - the two keys resolve differently
        if dotted == "theme.colour_preset":
            preset = str(value)
            if preset not in themes.preset_ids(root):
                raise ControlError(
                    f"{preset} is not a colour preset; the ones that exist are "
                    f"{', '.join(themes.preset_ids(root))}")
        else:
            intensity = str(value)
            if intensity not in themes.intensity_ids(root):
                raise ControlError(
                    f"{intensity} is not an intensity; the tokens define "
                    f"{', '.join(themes.intensity_ids(root))}")
        _theme_change(preset, intensity, reduce_motion, config_home, change)
        # The tool writes eleven generated files; the pipeline has to know them before
        # the run so that each has a restore point and each is read back afterwards.
        for target in themes.apply_targets(preset, intensity,
                                           reduce_motion=reduce_motion,
                                           config_home=config_home, env=env, root=root):
            change.add_target(target)
        # The tool writes the two theme keys back; the coarse pair is derived from
        # them and nothing else writes it, so this project does.
        projected = dict(document)
        projected.setdefault("theme", {})
        projected["theme"]["colour_preset"] = preset
        projected["theme"]["intensity"] = intensity
        change.settings.update(derived(projected, root))
        return change

    if route.handler == "colour_mode":
        if value not in ("light", "dark", "auto"):
            raise ControlError(f"{value!r} is not light, dark or auto")
        return _colour_mode_change(str(value), change, config_home)

    if route.handler == "animation_preset":
        if value not in themes.motion_presets(root):
            raise ControlError(
                f"{value} is not a motion preset; the ones with a file are "
                f"{', '.join(themes.motion_presets(root))}")
        change.add_command(f"apply the {value} motion preset",
                           lambda: themes.run_anim("set", str(value),
                                                   config_home=config_home))
        change.settings.update(derived(_with(document, "animation.preset", value), root))
        return change

    if route.handler == "animation_speed":
        try:
            multiplier = float(value)
        except (TypeError, ValueError) as exc:
            raise ControlError(f"{value!r} is not a number") from exc
        if not SPEED_BOUNDS[0] <= multiplier <= SPEED_BOUNDS[1]:
            raise ControlError(
                f"a motion multiplier is between {SPEED_BOUNDS[0]} and {SPEED_BOUNDS[1]}; "
                f"{multiplier} is not, and the tool clamps rather than refuses, so "
                f"this refusal is the only place the bounds are stated")
        change.add_command(f"set the motion multiplier to {multiplier}",
                           lambda: themes.run_anim("speed", _number(multiplier),
                                                   config_home=config_home))
        return change

    if route.handler == "animation_reduce":
        state = "on" if value else "off"
        change.add_command(f"turn reduce motion {state}",
                           lambda: themes.run_anim("reduce-motion", state,
                                                   config_home=config_home))
        return change

    if route.handler == "animation_event":
        leaf = _leaf_of(dotted, "animation.event_overrides")
        declared = _declared_events(document, root)
        if declared and leaf not in declared:
            raise ControlError(
                f"{leaf} is not an animation event the active preset declares; the "
                f"ones it declares are {', '.join(sorted(declared))}")
        wanted = bool(value)
        current = _current_override(leaf, document)
        if current == wanted:
            # Nothing to do. A toggle command run anyway would flip the override the
            # other way, and an empty change is the honest answer: the report says
            # the value is already the one asked for.
            change.add_command("nothing to do",
                               lambda: runner.Outcome(["iarch-anim", "toggle", leaf],
                                                      runner.OK,
                                                      reason=f"{leaf} is already "
                                                             f"{wanted}"))
            return change
        change.add_command(f"turn {leaf} {'on' if wanted else 'off'}",
                           lambda: themes.run_anim("toggle", leaf,
                                                   config_home=config_home))
        return change

    if route.handler == "fonts":
        problems = _font_problems(dotted, value, root)
        if problems:
            raise ControlError("; ".join(problems))
        projected = _with(document, dotted, value)
        values = gtk_settings.values_from_settings(
            projected.get("fonts") or {},
            str((projected.get("theme") or {}).get("colour_mode") or "dark"), root)
        change.settings[dotted] = value
        change.add_command("write both settings.ini files",
                           lambda: _write_gtk(values, config_home))
        _fontconfig_change(change, config_home)
        for path in gtk_settings.target_paths(config_home).values():
            change.add_target(path)
        return change

    if route.handler == "monitors":
        entries = _monitor_list(document, dotted, value)
        problems = _monitor_problems(entries, root)
        if problems:
            raise ControlError("; ".join(problems))
        change.settings["display.monitors"] = entries
        destination = _hypr_target("monitors.lua", config_home, env)
        change.add_command("render the compositor's monitor module",
                           lambda: _run_tool(MONITORS_TOOL,
                                             ["--output", str(destination)],
                                             config_home, env))
        change.add_target(destination)
        return change

    if route.handler == "glass_leaf":
        leaf = _leaf_of(dotted, "glass.leaves")
        names, ranges, integers = themes.glass_leaves(root)
        if leaf not in names:
            raise ControlError(
                f"{leaf} is not a compositor leaf the tokens name, so the compositor "
                f"would answer with a config error at the next parse")
        bounds = ranges.get(leaf)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            if leaf not in _boolean_leaves(root):
                raise ControlError(f"{leaf} takes a number, and {value!r} is not one")
        elif bounds and not bounds[0] <= float(value) <= bounds[1]:
            raise ControlError(
                f"{leaf} is between {bounds[0]} and {bounds[1]}; {value} is outside it, "
                f"and a value the compositor's parser refuses is a config error the "
                f"whole session reports at login")
        leaves = dict((document.get("glass") or {}).get("leaves") or {})
        leaves[leaf] = value
        change.settings["glass.leaves"] = leaves
        change.settings.update(derived(_with(document, "glass.leaves", leaves), root))
        change.add_command(f"set {leaf} on the running compositor",
                           lambda: hypr.eval_leaves({leaf: value}))
        return change

    if route.handler == "per_app_opacity":
        entries = _opacity_list(document, dotted, value)
        problems = _opacity_problems(entries)
        if problems:
            raise ControlError("; ".join(problems))
        change.settings["glass.per_app_opacity"] = entries
        # `user_path` is a property on the store, and the file it names is the one the
        # apply pipeline has just written: the generator is told to read exactly that
        # path rather than resolving one of its own.
        settings_path = (store.user_path if store is not None
                         else _user_settings_path(env))
        destination = _hypr_target(str(Path("generated") / "glass.lua"), config_home, env)
        change.add_command(
            "render the compositor's glass module with the per-window rules",
            lambda: _run_tool(GLASS_TOOL,
                              ["--settings", str(settings_path),
                               "--output", str(destination)], config_home, env))
        change.add_target(destination)
        return change

    if route.handler == "mode":
        mode = "game" if "game" in dotted else "focus"
        tool = GAMEMODE_TOOL if mode == "game" else FOCUS_TOOL
        wanted = bool(value)
        change.add_command(f"turn {mode} mode {'on' if wanted else 'off'}",
                           lambda: _run_tool(tool, ["on" if wanted else "off"],
                                             config_home))
        change.settings.update(derived(_with(document, f"modes.{mode}.active",
                                             wanted), root))
        return change

    if route.handler == "autostart":
        entries = _autostart_list(document, dotted, value)
        problems = autostart.projection_problems(entries, root)
        if problems:
            raise ControlError("; ".join(problems))
        change.settings["startup.autostart"] = entries
        change.add_command(
            f"project {len(entries)} startup entr{'y' if len(entries) == 1 else 'ies'}",
            lambda: autostart.project(entries, config_home=None, env=env, root=root))
        # The targets are the files this list will produce, one per entry -- not the
        # directory, which the pipeline reads back as a file, and not the files a
        # previous list produced, which the projection removes and backs up itself. A
        # rollback therefore restores exactly the entries that were there.
        target = autostart.directory(None, env)
        for entry in entries:
            change.add_target(target / autostart.entry_file_name(str(entry["name"]), root))
        return change

    if route.handler == "window":
        change.settings[dotted] = value
        return change

    raise ControlError(f"{route.handler} is a route this module does not implement")


# ------------------------------------------------------------------- helpers


def _copy(document: Mapping[str, Any]) -> Dict[str, Any]:
    """A deep copy, because a projected change must not edit the caller's document.

    ``dict(document)`` is not enough and the mistake is invisible inside a single
    change: the shallow copy shares ``document["theme"]``, so writing the derived
    coarse pair into the projection writes it into the settings the *next* change
    reads, and a second row on the same page is then applied on top of a value nobody
    chose. Deep-copying through JSON is the cheap way to be sure, and the document is
    JSON by definition.
    """
    import json  # noqa: PLC0415

    return json.loads(json.dumps(dict(document)))


def _number(value: float) -> str:
    """A number as the argument list wants it: no trailing ``.0`` for a whole one."""
    return str(int(value)) if float(value).is_integer() else str(value)


def _with(document: Mapping[str, Any], dotted: str, value: Any) -> Dict[str, Any]:
    """The document with one dotted path replaced, for a derivation that has to see it."""
    result: Dict[str, Any] = _copy(document)
    parts = str(dotted).split(".")
    node = result
    for part in parts[:-1]:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):  # a list or a scalar where a section belongs
            return dict(document)
    node[parts[-1]] = value
    return result


def _leaf_of(dotted: str, container: str) -> str:
    """The key part of ``glass.leaves.decoration:blur:passes``."""
    text = str(dotted)
    if not text.startswith(f"{container}.") or text == f"{container}.":
        raise ControlError(f"{text} does not name one entry of {container}")
    return text[len(container) + 1:]


def _boolean_leaves(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The leaves whose value is a boolean rather than a number."""
    names, ranges, _ = themes.glass_leaves(root)
    return tuple(name for name in names if name not in ranges)


def _declared_events(document: Mapping[str, Any],
                     root: Optional[Path] = None) -> List[str]:
    """The animation events the active preset declares, or ``[]`` when unreadable.

    Read from the preset file the compositor's own generator reads, so the list a
    page offers and the list ``iarch-anim toggle`` accepts cannot disagree. An empty
    list means the question could not be answered, and the caller treats that as "do
    not refuse": a page that could not offer an event because a file was missing
    would be hiding a switch, not protecting anybody.
    """
    import json  # noqa: PLC0415

    animation = document.get("animation") or {}
    preset = str(animation.get("preset") or "smooth")
    path = (root or paths.repo_root()) / "data" / "design" / "animations" / f"{preset}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    events = payload.get("events") or payload.get("animations") or {}
    return list(events) if isinstance(events, Mapping) else []


def _current_override(leaf: str, document: Mapping[str, Any]) -> Optional[bool]:
    """What the settings file says about one event, or ``None`` when it says nothing.

    ``None`` is not ``False``: an event with no override follows the preset, and
    turning it "off" when the preset already has it off is a change that writes an
    override where none was needed. The Animations page shows that difference.
    """
    overrides = (document.get("animation") or {}).get("event_overrides") or {}
    return overrides.get(leaf) if isinstance(overrides, Mapping) else None


def _font_problems(dotted: str, value: Any, root: Optional[Path] = None) -> List[str]:
    """Whether a fonts.* value is one GTK accepts, asked of the record not of a guess."""
    setting = dotted.rpartition(".")[2]
    if setting in gtk_settings.FONT_NAME_SETTINGS:
        # The two halves of gtk-font-name: check the string they would build, which
        # is the value GTK actually parses, rather than each half on its own.
        try:
            gtk_settings.values_from_settings({setting: value}, "auto", root)
        except gtk_settings.GtkSettingsError as exc:
            return [str(exc)]
        return []
    key = gtk_settings.key_for_setting(setting)
    if not key:
        return [f"{dotted} is not a fonts key this application projects"]
    problems = gtk_settings.check_values({key: value}, root)
    if dotted.endswith("size_pt") and isinstance(value, (int, float)) and float(value) > 72.0:
        problems.append("a font size above 72pt is not a size anybody reads at")
    return problems


def _monitor_list(document: Mapping[str, Any], dotted: str, value: Any) -> List[Any]:
    """The monitor list a change would write, with one entry replaced or added."""
    entries = list((document.get("display") or {}).get("monitors") or [])
    parts = str(dotted).split(".")
    if len(parts) <= 2:
        # The whole list, which is what a "reset to the identity rule" button writes.
        return list(value or [])
    index = parts[2]
    if index == "*":
        raise ControlError(
            "a monitor row names one monitor; '*' is how a plan points at the shape "
            "of an entry, not how a change names the one to write")
    if not index.isdigit():
        raise ControlError(f"{dotted} names no monitor: {index!r} is not a position")
    count = len(entries)
    if int(index) >= count:
        if len(parts) == 3 and isinstance(value, Mapping):
            # A new monitor, added whole: the row's value is the entry itself.
            entries.append(dict(value))
            return entries
        raise ControlError(
            f"{dotted} names monitor {index}, and the list has {count}: a new monitor is "
            f"added whole rather than field by field, because the list is validated as a "
            f"list and one field of a new entry is a half entry that would be refused")
    entry = dict(entries[int(index)])
    if len(parts) == 3:
        entry = dict(value) if isinstance(value, Mapping) else entry
    else:
        entry[parts[3]] = value
    entries[int(index)] = entry
    return entries


def _monitor_problems(entries: Sequence[Any], root: Optional[Path] = None) -> List[str]:
    """Every way a monitor list is unusable, checked against the compositor's record."""
    import json  # noqa: PLC0415

    problems: List[str] = []
    if len(entries) > 16:
        problems.append(f"{len(entries)} monitors is more than the 16 the settings "
                        f"schema allows")
    outputs: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        where = f"display.monitors[{index}]"
        if not isinstance(entry, Mapping):
            problems.append(f"{where} is not an object")
            continue
        output = entry.get("output")
        if not isinstance(output, str) or not output:
            problems.append(f"{where} has no output name, and a rule without one "
                            f"matches every monitor at once")
        elif output in outputs:
            problems.append(f"{where} names {output}, which entry {outputs[output]} "
                            f"already configured")
        else:
            outputs[output] = index
        unexpected = set(entry) - set(_monitor_fields(root))
        if unexpected:
            problems.append(f"{where} declares {', '.join(sorted(unexpected))}, which "
                            f"the compositor's record does not accept")
    return problems


def _monitor_fields(root: Optional[Path] = None) -> Tuple[str, ...]:
    """The fields ``data/design/monitors.json`` says this project writes.

    The record carries 23 monitor fields and marks 17 of them
    ``written_by_this_project: false`` -- colour management, HDR, luminance,
    mirroring, VRR and the reserved area, each with the reason in
    ``refused_by_this_project``. Filtering on that flag is what stops a page offering
    a field the record refuses: without it a row for ``reserved`` would look like any
    other field and would fight the shell's own bar for the same edge of the screen.
    A field the record does not mark at all is one it writes.
    """
    import json  # noqa: PLC0415

    path = paths.design_file("monitors.json", root)
    record = json.loads(path.read_text(encoding="utf-8"))
    write = record.get("write") or {}
    fields = write.get("fields") or write.get("written_by_this_project") or []
    if isinstance(fields, Mapping):
        return tuple(fields)
    names = []
    for item in fields:
        if isinstance(item, Mapping):
            if item.get("written_by_this_project") is False:
                continue
            names.append(item.get("name"))
        else:
            names.append(str(item))
    return tuple(name for name in names if name)


def _opacity_list(document: Mapping[str, Any], dotted: str, value: Any) -> List[Any]:
    """The per-window opacity list a change would write."""
    entries = list((document.get("glass") or {}).get("per_app_opacity") or [])
    parts = str(dotted).split(".")
    if len(parts) <= 2:
        return list(value or [])
    index = parts[2]
    if index == "*":
        raise ControlError("an opacity row names one window class, not '*'")
    if not index.isdigit():
        raise ControlError(f"{dotted} names no window rule: {index!r} is not a position")
    count = len(entries)
    if int(index) >= count:
        if len(parts) == 3 and isinstance(value, Mapping):
            entries.append(dict(value))
            return entries
        raise ControlError(
            f"{dotted} names rule {index}, and the list has {count}: a new rule is added "
            f"whole rather than field by field, because a class without an opacity is a "
            f"rule gen_glass_lua.py refuses to render")
    entry = dict(entries[int(index)])
    if len(parts) == 3:
        entry = dict(value) if isinstance(value, Mapping) else entry
    else:
        entry[parts[3]] = value
    entries[int(index)] = entry
    return entries


def _opacity_problems(entries: Sequence[Any]) -> List[str]:
    """The same check the generator runs, so a refusal happens before any write."""
    import importlib  # noqa: PLC0415

    paths.add_repo_to_path()
    tool = importlib.import_module("iarch.cli.gen_glass_lua")
    return list(tool.check_overrides(entries))


def _autostart_list(document: Mapping[str, Any], dotted: str, value: Any) -> List[Any]:
    """The startup list a change would write."""
    entries = list((document.get("startup") or {}).get("autostart") or [])
    parts = str(dotted).split(".")
    if len(parts) <= 2:
        return list(value or [])
    index = parts[2]
    if index == "*":
        raise ControlError("a startup row names one entry, not '*'")
    if not index.isdigit():
        raise ControlError(f"{dotted} names no entry: {index!r} is not a position")
    count = len(entries)
    if int(index) >= count:
        if len(parts) == 3 and isinstance(value, Mapping):
            entries.append(dict(value))
            return entries
        raise ControlError(
            f"{dotted} names entry {index}, and the list has {count}: a new entry is added "
            f"whole rather than field by field, because the list is validated as a list and "
            f"a name without a command is an entry the session would never start")
    entry = dict(entries[int(index)])
    if len(parts) == 3:
        entry = dict(value) if isinstance(value, Mapping) else entry
    else:
        entry[parts[3]] = value
    entries[int(index)] = entry
    return entries


def _user_settings_path(env: Optional[Mapping[str, str]] = None) -> Path:
    """``~/.config/iarch/settings.json``: the file a generator is told to read."""
    return config_store.user_path(env)


def _hypr_target(name: str, config_home: Optional[Path],
                 env: Optional[Mapping[str, str]] = None) -> Path:
    """A file under the compositor's own directory, which the session reads."""
    if config_home is not None:
        return Path(config_home) / "hypr" / name
    return apply.config_target("hypr", *Path(name).parts)


# ------------------------------------------------------------------ describing


def describe(dotted: str, value: Any, **kwargs: Any) -> Dict[str, Any]:
    """What a change will do, as data, for the confirmation dialog and the toast.

    Building the change is the description: the dialog then cannot promise something
    the pipeline does not do, because it is reading the pipeline's own answer.
    """
    try:
        change = change_for(dotted, value, **kwargs)
    except ControlError as exc:
        return {"refused": True, "reason": str(exc), "label": label_for(dotted),
                "commands": [], "targets": [], "risky": False,
                "writes_settings": False}
    route = route_for(dotted)
    return {
        "refused": False,
        "reason": "",
        "label": change.label,
        "commands": [label for label, _call in change.commands],
        "targets": [str(target) for target in change.targets],
        "settings": dict(change.settings),
        "risky": change.risky,
        "reload_session": change.reload_session,
        "verify_configerrors": change.verify_configerrors,
        "writes_settings": bool(change.settings),
        "owner": route.owner if route else "none",
        "note": route.note if route else "",
    }


def changes_for(values: Mapping[str, Any], **kwargs: Any) -> List[apply.Change]:
    """One change per path, in the order the paths were given.

    Not one change for all of them: a page that writes a font *and* a monitor rule is
    two decisions with two different risks, and a single rollback would undo a font
    because a monitor refused. The window applies them in order and stops at the first
    refusal, which is what the toast then says.
    """
    return [change_for(dotted, value, **kwargs) for dotted, value in values.items()]


def accent_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether an accent override is a colour, for the entry row's validator.

    The syntax check is here because it is cheap and because an entry row has to
    answer while a person types; the contrast gate is not, because it is a subprocess
    and a validator that starts one per keystroke is a validator that makes the row
    unusable. The gate runs when the value is applied, and until a renderer reads the
    override at all (:data:`UNPROJECTED`) that is the whole of what it does.
    """
    text = str(value or "").strip()
    if not text:
        return True, ""
    if not _ACCENT.match(text):
        return False, "an accent override is #rrggbb, or empty to follow the preset"
    return True, ""
