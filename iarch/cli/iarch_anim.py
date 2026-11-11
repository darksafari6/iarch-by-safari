#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iarch-anim — choose how the desktop moves, and prove the compositor took it.

Every animation this project drives is switchable. Five presets live in
``data/design/animations/`` — smooth, snappy, bouncy, minimal and off — each
declaring its own named curves and its own per-event durations, curves and styles,
and ``gen_animations_lua`` renders one of them to
``~/.config/hypr/generated/animations.lua``, which ``animations.lua`` requires
through a ``pcall`` after the static ``animations/default.lua``. On top of the
preset sit three modifiers a person controls: a global speed multiplier, a
reduce-motion switch, and per-event overrides.

The contract, which docs/ARCHITECTURE.md and iarch/lib/renderers.py state:

* read user state through ``iarch.lib.configstore`` and write only the generated
  file — never a hand-written config, and never the static baseline it overrides;
* validate before writing: the render refuses an unknown leaf, a style that leaf
  does not accept, an unregistered curve, a bezier component outside ``[-1, 2]``,
  a spring value at or below 0.5, or a duration outside ``(0, 10000]`` ms, all of
  which Hyprland would answer with a config error that stops the session;
* back the previous file up, write atomically, then ask the compositor to reload
  and ask it what it thinks — and if the reload produced a config error that was
  not there before, put the old bytes back and reload again, so a bad choice costs
  a flicker and not a session;
* skip the write when the rendered bytes already match what is on disk, so
  re-selecting the same preset neither rewrites nor rotates a backup;
* never start a desktop: a missing ``hyprctl`` or ``luac`` is a warning that says
  the change is unverified, not a failure;
* exit 0 on success, 1 when a gate refuses or the compositor rejected the result,
  2 on a usage or data error.

``--json`` prints one object and nothing else, for the Part 4 settings app and the
Part 5 overlay: the state that was applied, the resolved per-event plan the render
was built from, what was written, what was skipped, which reload commands ran, and
what verification could and could not be done.

Usage:
    python3 iarch/cli/iarch_anim.py list
    python3 iarch/cli/iarch_anim.py set PRESET
    python3 iarch/cli/iarch_anim.py speed MULTIPLIER        # 0.5-2.0, clamped; above 1 is faster
    python3 iarch/cli/iarch_anim.py toggle EVENT
    python3 iarch/cli/iarch_anim.py reduce-motion on|off
    python3 iarch/cli/iarch_anim.py current [--live]

Every subcommand takes ``--config-home DIR`` (default ``~/.config``, where
hyprland.lua actually reads the file), ``--no-reload``, ``--dry-run`` and
``--json``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)
from iarch.cli import gen_animations_lua as anim  # noqa: E402  (repo-root import by design)

EXIT_OK = 0
EXIT_REFUSED = 1  # a gate refused, or the compositor rejected the result and it was rolled back
EXIT_USAGE = 2    # bad arguments, unknown preset or event, render or data error

# Verified against the release this repo targets, so neither needs a TODO(verify):
#   hyprctl reload        — Hyprland v0.57.2, src/ipc/s1/Commands.cpp:2113
#                           legacyCommand("reload", COMMAND_MATCH_PREFIX, reloadRequest),
#                           and docs/hyprctl.1.rst: "Force a reload of the config file."
#   hyprctl configerrors  — src/ipc/s1/Commands.cpp:2104 legacyCommand("configerrors",
#                           COMMAND_MATCH_EXACT, configErrorsRequest), described in
#                           hyprctl/src/Strings.hpp as "Lists all current config parsing
#                           errors". It is not in docs/hyprctl.1.rst, which is why the
#                           handler registration is cited as well as the man page.
#                           configErrorsRequest returns Config::mgr()->getErrors() split on
#                           newlines, and with -j a JSON array, so an empty array is a
#                           config the compositor parsed cleanly.
#   hyprctl animations    — src/ipc/s1/Commands.cpp:2098, "Gets the current config'd info
#                           about animations and beziers": per node it reports name,
#                           overridden, bezier, enabled, speed and style, which is how
#                           --live proves a preset reached the session rather than only
#                           the file.
HYPRCTL = "hyprctl"
RELOAD_COMMAND: Tuple[str, ...] = (HYPRCTL, "reload")
CONFIGERRORS_COMMAND: Tuple[str, ...] = (HYPRCTL, "configerrors")
ANIMATIONS_COMMAND: Tuple[str, ...] = (HYPRCTL, "-j", "animations")
HYPRCTL_TIMEOUT_SECONDS = 30

# luac -p parses without executing, which is the cheapest real proof the render is
# Lua. It is optional: a session, a chroot and CI may all lack it, and the
# generator's own structural check plus tests/test_animations_lua.py (which runs
# luac and luaparser when the host has them) cover the same ground.
LUAC_CANDIDATES: Tuple[str, ...] = ("luac", "luac5.4", "luac5.3", "luac5.1")
LUAC_TIMEOUT_SECONDS = 30

SETTINGS_NAME = "settings"
RELATIVE_TARGET = Path("hypr") / "generated" / "animations.lua"


class AnimCliError(RuntimeError):
    """A usage or data problem: unknown preset or event, unreadable settings."""


class RefusedError(RuntimeError):
    """A gate refused the change, or the compositor rejected it and it was undone."""


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


_JSON_MODE = False


def _say(message: str) -> None:
    """A line of prose for a person — suppressed entirely under ``--json``.

    ``--json`` promises one object on stdout and nothing else, because Parts 4 and
    5 parse it; prose interleaved with it would be a parse error for them. Warnings
    still go to stderr, which is where a caller that only reads stdout will not
    trip over them and a person watching a terminal still sees them.
    """
    if _JSON_MODE:
        return
    # Flushed, because warnings go to stderr and the two are read together: an
    # unbuffered stdout would let a warning appear above the line it belongs to.
    print(message, flush=True)


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _config_home(raw: str) -> Path:
    home = Path(raw).expanduser()
    if not home.is_absolute():
        raise AnimCliError(f"--config-home must be an absolute path: {raw!r}")
    return home


def _target(config_home: Path) -> Path:
    return config_home / RELATIVE_TARGET


# ---------------------------------------------------------------- user state


def _user_animation(env: Optional[Dict[str, str]]) -> Dict[str, Any]:
    """The ``animation.*`` the user actually wrote, ignoring repository defaults.

    Reading the raw file rather than ``configstore.load`` keeps a value the person
    never chose distinguishable from one they did, which is what lets ``current``
    say "(repository default)" and what lets a no-op re-apply skip the write.
    """
    path = configstore.user_path(SETTINGS_NAME, env)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnimCliError(f"{display(path)} cannot be read as JSON: {exc}") from exc
    block = data.get("animation") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return {}
    return block


def _clean_overrides(raw: Any) -> Dict[str, bool]:
    """Per-event overrides as ``{leaf: bool}``, refusing anything else.

    A settings file is the one input here a person can hand-edit into any shape,
    and the leaf names are validated against the preset later, so all that is
    needed now is that the values are booleans and the keys are strings.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise AnimCliError("animation.event_overrides must be an object mapping an event "
                           f"name to true or false, got {type(raw).__name__}")
    overrides: Dict[str, bool] = {}
    for leaf, value in raw.items():
        if not isinstance(leaf, str) or not leaf:
            raise AnimCliError(f"animation.event_overrides has an unusable event name {leaf!r}")
        if not isinstance(value, bool):
            raise AnimCliError(f"animation.event_overrides[{leaf!r}] is {value!r}, not a boolean")
        overrides[leaf] = value
    return overrides


def _resolve(tokens: Dict[str, Any], env: Optional[Dict[str, str]], *,
             preset: Optional[str] = None, speed: Any = None,
             reduce_motion: Optional[bool] = None,
             overrides: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """Settle the effective state: the command line, then the user's file, then defaults.

    The multiplier is resolved here rather than stored clamped-then-reclamped: a
    request outside the token bounds is clamped, and the state that gets persisted
    is the clamped value, so ``current`` never reports a number the render did not
    use.
    """
    names = anim.preset_names(tokens)
    low, high, default_factor = anim.multiplier_bounds(tokens)
    user = _user_animation(env)

    chosen = preset if preset is not None else user.get("preset")
    if chosen is None:
        chosen = anim.default_preset(tokens)
    if chosen not in names:
        raise AnimCliError(f"unknown preset {chosen!r}; the presets are {', '.join(names)}")

    requested = speed if speed is not None else user.get("speed", default_factor)
    factor, clamped = anim.clamp_multiplier(tokens, requested)

    rm = reduce_motion if reduce_motion is not None else bool(user.get("reduce_motion", False))
    if not isinstance(rm, bool):
        raise AnimCliError(f"reduce-motion is {rm!r}, not on or off")

    merged = _clean_overrides(user.get("event_overrides"))
    if overrides:
        merged.update(overrides)

    return {
        "preset": str(chosen),
        "speed": factor,
        "reduce_motion": rm,
        "event_overrides": merged,
        "_requested_speed": requested,
        "_speed_clamped": clamped,
        "_user_chose_preset": user.get("preset") is not None and preset is None,
    }


def _effective_preset(tokens: Dict[str, Any], state: Dict[str, Any]) -> str:
    """The preset that will actually be rendered, after the reduce-motion rule."""
    if state["reduce_motion"]:
        return anim.reduce_motion_preset(tokens)
    return state["preset"]


def _persist(state: Dict[str, Any], env: Optional[Dict[str, str]]) -> Tuple[Path, bool]:
    """Record the animation state in the user's settings; return (path, changed).

    ``configstore.load`` returns the repository defaults with the user's file
    merged on top, so saving that document back keeps every key the person already
    had and fills in the rest, and the file written always validates against
    data/schemas/settings.schema.json. Only ``animation`` is touched; the Part 1
    ``effects.animations`` boolean and the Part 2 ``theme`` block are left alone,
    and reconciling the coarse switch with this one is Part 4 settings-app work.

    Re-applying the state that is already recorded is a no-op: no rewrite, no
    rotated backup, matching how the generated file is skipped when its bytes
    already match.
    """
    path = configstore.user_path(SETTINGS_NAME, env)
    payload = {
        "preset": state["preset"],
        "speed": state["speed"],
        "reduce_motion": state["reduce_motion"],
        "event_overrides": dict(sorted(state["event_overrides"].items())),
    }
    user = _user_animation(env)
    if path.is_file() and user:
        same = (user.get("preset") == payload["preset"]
                and float(user.get("speed", payload["speed"])) == payload["speed"]
                and bool(user.get("reduce_motion", False)) == payload["reduce_motion"]
                and _clean_overrides(user.get("event_overrides")) == payload["event_overrides"])
        if same:
            return path, False
    settings = configstore.load(SETTINGS_NAME, ROOT, env)
    settings["animation"] = payload
    return configstore.save(SETTINGS_NAME, settings, env), True


# ---------------------------------------------------------------- the plan


def _plan(tokens: Dict[str, Any], surface: Dict[str, Any],
          state: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Resolve the state into (the preset document, the per-event plan, warnings).

    The plan comes from ``gen_animations_lua.plan_events`` — the same resolution
    the renderer emits from — so what ``current`` and ``--json`` report cannot
    drift from what lands in the file.
    """
    name = _effective_preset(tokens, state)
    preset = anim.load_preset(name)
    factor, cap_ms, warnings = anim.resolve_modifiers(
        tokens, name, state["speed"], state["reduce_motion"])
    plan, plan_warnings = anim.plan_events(
        preset, surface, multiplier=factor, cap_ms=cap_ms,
        overrides=state["event_overrides"], reduce_motion=state["reduce_motion"])
    return preset, plan, warnings + plan_warnings


# ---------------------------------------------------------------- verification


def _luac() -> Optional[str]:
    return next((name for name in LUAC_CANDIDATES if shutil.which(name)), None)


def _lua_syntax_check(text: str) -> Tuple[str, Optional[str]]:
    """Parse the render with ``luac -p`` if a Lua compiler exists.

    Returns (status, detail) where status is "passed", "failed" or "missing".
    Written to a temp file rather than piped, because ``luac -p`` takes a file and
    a pipe would need a shell, and this project never runs one.
    """
    luac = _luac()
    if luac is None:
        return "missing", None
    handle = tempfile.NamedTemporaryFile("w", suffix=".lua", delete=False, encoding="utf-8")
    try:
        handle.write(text)
        handle.close()
        result = subprocess.run((luac, "-p", handle.name), check=False,
                                capture_output=True, text=True, timeout=LUAC_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as exc:
        return "failed", f"{luac} could not be run: {exc}"
    finally:
        Path(handle.name).unlink(missing_ok=True)
    if result.returncode != 0:
        return "failed", (result.stderr or result.stdout or f"{luac} exited "
                                                            f"{result.returncode}").strip()
    return "passed", None


def _hyprctl_json(command: Tuple[str, ...]) -> Optional[Any]:
    """Run a hyprctl request for JSON; None when it cannot be asked at all.

    None means "no answer", which is not the same as an empty answer: a session
    that is not running, a chroot, CI and a fresh install before the first login
    all give None, and the caller has to say the change is unverified rather than
    claim it worked.
    """
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True,
                                timeout=HYPRCTL_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _hyprctl_lines(command: Tuple[str, ...]) -> Optional[List[str]]:
    """Run a hyprctl request for its normal (non-JSON) output, as lines.

    ``configerrors`` is read this way on purpose. Its JSON form is assembled by
    hand in configErrorsRequest — a bracket, then one quoted line per error, then
    trimTrailingComma — while its normal form is exactly the error lines, which is
    the same information with no parser in between. Empty output means a config the
    compositor parsed cleanly; None means it could not be asked.
    """
    if shutil.which(command[0]) is None:
        return None
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True,
                                timeout=HYPRCTL_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _config_errors() -> Optional[List[str]]:
    """The compositor's current config parsing errors, or None if it cannot be asked."""
    return _hyprctl_lines(CONFIGERRORS_COMMAND)


def _live_animations() -> Optional[Any]:
    """What the compositor says it is actually animating with, or None."""
    return _hyprctl_json(ANIMATIONS_COMMAND)


def _reload(dry_run: bool, no_reload: bool, report: Dict[str, Any]) -> bool:
    """Ask the compositor to re-read its config. Returns whether it was asked."""
    printable = " ".join(RELOAD_COMMAND)
    if no_reload:
        report["skipped"].append(f"{printable} (--no-reload)")
        _say("reload: skipped (--no-reload)")
        return False
    if dry_run:
        report["skipped"].append(f"{printable} (dry run)")
        _say("reload: skipped (dry run)")
        return False
    if shutil.which(RELOAD_COMMAND[0]) is None:
        report["skipped"].append(f"{printable} ({RELOAD_COMMAND[0]} not on PATH)")
        _warn(f"{RELOAD_COMMAND[0]} not found on PATH; skipped `{printable}` "
              "(is the session running?)")
        return False
    try:
        subprocess.run(RELOAD_COMMAND, check=False, timeout=HYPRCTL_TIMEOUT_SECONDS,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        report["skipped"].append(f"{printable} ({exc})")
        _warn(f"reload: `{printable}` failed: {exc}")
        return False
    report["ran"].append(printable)
    _say(f"reload: ran `{printable}`")
    return True


def _restore(path: Path, snapshot: Optional[bytes]) -> bool:
    """Put the previous bytes back, or remove a file that did not exist."""
    try:
        if snapshot is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(snapshot)
        return True
    except OSError as exc:
        _warn(f"rollback: could not restore {display(path)}: {exc}")
        return False


# ---------------------------------------------------------------- the pipeline


def _apply(tokens: Dict[str, Any], surface: Dict[str, Any], state: Dict[str, Any],
           config_home: Path, env: Dict[str, str], args: argparse.Namespace,
           report: Dict[str, Any]) -> int:
    """Validate, back up, render, syntax-check, write, reload, verify, or roll back."""
    preset, plan, warnings = _plan(tokens, surface, state)
    for warning in warnings:
        _warn(warning)
    report["warnings"].extend(warnings)
    report["state"] = _public_state(state)
    report["effective"] = {
        "preset": preset.get("name"),
        "label": preset.get("label"),
        "master": bool(preset.get("master")),
        "multiplier": state["speed"],
        "reduce_motion": state["reduce_motion"],
        "duration_cap_ms": (anim.reduce_motion_cap_ms(tokens) if state["reduce_motion"] else None),
        "events": plan,
    }

    # 1. render — which is where every validation happens, before anything is touched.
    source = anim.build_preset(tokens, surface, preset, multiplier=state["speed"],
                               reduce_motion=state["reduce_motion"],
                               overrides=state["event_overrides"]).rstrip("\n")
    rendered = _rendered_bytes(_target(config_home), source)
    report["target"] = display(_target(config_home))

    # 2. parse the render if a Lua compiler is available.
    status, detail = _lua_syntax_check(rendered)
    report["verification"]["luac"] = {"status": status, "detail": detail}
    if status == "failed":
        raise RefusedError(f"the render is not valid Lua ({detail}); nothing was written")
    if status == "missing":
        _warn("no luac on PATH; the render was checked structurally but not parsed")

    path = _target(config_home)
    unchanged = _on_disk_equals(path, rendered)
    report["unchanged"] = unchanged

    if args.dry_run:
        _say(f"  {'unchanged    ' if unchanged else 'would write  '}{display(path)}")
        _say(f"[dry-run] preset {preset.get('name')!r}, {len(plan)} event(s), "
             f"{sum(1 for e in plan if e['enabled'])} animating; no settings change, no reload")
        report["dry_run"] = True
        return EXIT_OK

    snapshot = path.read_bytes() if path.is_file() else None
    report["backup"] = {
        "snapshot_taken": snapshot is not None,
        "directory": display(configstore.backup_dir(env)),
    }

    if unchanged:
        _say(f"  unchanged    {display(path)}")
    else:
        # 3. back up and write atomically: write_generated copies the previous file
        #    into the rotated backup directory and renames a temp file created in
        #    the destination directory into place, so there is never a half-written
        #    config. The in-memory snapshot below is what a rollback restores,
        #    because it does not depend on the backup rotation still holding it.
        try:
            written = configstore.write_generated(path, source, env)
        except (OSError, configstore.ConfigError) as exc:
            raise AnimCliError(f"could not write {display(path)}: {exc}") from exc
        report["written"] = display(written)
        _say(f"  write        {display(written)}")

    # 4. ask the compositor what it thought before, reload, and ask it again.
    #    The settings are deliberately not written yet: if the reload produces an
    #    error this change caused, the file goes back and the recorded state has to
    #    go with it, so a rejected change leaves neither the file nor the settings
    #    claiming it happened.
    baseline = _config_errors()
    report["verification"]["configerrors"] = {"baseline": baseline}
    reloaded = _reload(dry_run=False, no_reload=args.no_reload, report=report["reload"])

    if not reloaded:
        report["verification"]["verdict"] = "unverified"
        _warn("the compositor was not reloaded, so the new motion set is on disk but "
              "not verified in a session")
    else:
        after = _config_errors()
        report["verification"]["configerrors"]["after"] = after
        if after is None:
            report["verification"]["verdict"] = "unverified"
            _warn(f"`{' '.join(CONFIGERRORS_COMMAND)}` gave no answer; the reload ran but "
                  "the result could not be checked")
        else:
            # Errors that were already there are not this change's fault, and
            # rolling back would not remove them, so only new lines count.
            fresh = [line for line in after if line not in (baseline or [])]
            report["verification"]["configerrors"]["new"] = fresh
            if baseline:
                _warn(f"the config already had {len(baseline)} parsing error(s) before this "
                      "change; they are not iArch's and are left alone")
            if fresh:
                # 5. roll back: the previous bytes, then reload again, so the session
                #    is left running what it was running rather than a config it has
                #    just rejected.
                restored = _restore(path, snapshot)
                report["rollback"] = {"restored": restored, "reason": fresh}
                _reload(dry_run=False, no_reload=False, report=report["reload"])
                report["verification"]["configerrors"]["after_rollback"] = _config_errors()
                raise RefusedError("the compositor reported "
                                   f"{len(fresh)} new config error(s) after the reload, so "
                                   f"{display(path)} was put back and reloaded, and the "
                                   f"recorded animation state was left as it was: "
                                   + "; ".join(fresh))
            report["verification"]["verdict"] = "clean"
            _say(f"verified: `{' '.join(CONFIGERRORS_COMMAND)}` reports no new error")

    # 6. the file is staying, so record the state: a relogin, the Part 4 settings
    #    app and the Part 5 overlay all read it from here.
    settings_path, changed = _persist(state, env)
    report["settings"] = {"path": display(settings_path), "changed": changed}
    _say(f"settings: {'recorded' if changed else 'already recorded'} "
         f"animation.preset={state['preset']}, speed={state['speed']}, "
         f"reduce_motion={state['reduce_motion']} in {display(settings_path)}")
    _say(f"applied {preset.get('name')!r}: {sum(1 for e in plan if e['enabled'])} of "
         f"{len(plan)} event(s) animating")
    return EXIT_OK


def _rendered_bytes(path: Path, body: str) -> str:
    """Exactly the text ``configstore.write_generated`` will put on disk."""
    return f"{configstore.header_for(path)}\n{body}\n"


def _on_disk_equals(path: Path, rendered: str) -> bool:
    try:
        return path.is_file() and path.read_text(encoding="utf-8") == rendered
    except (OSError, UnicodeDecodeError):
        return False


def _public_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """The state without the private resolution keys."""
    return {key: value for key, value in state.items() if not key.startswith("_")}


def _new_report(command: str) -> Dict[str, Any]:
    """The ``--json`` shape, with every key present whether or not it is used.

    Parts 4 and 5 read this object, so a key that appears only on some paths is a
    bug waiting for a caller that does not guard it.
    """
    return {
        "tool": "iarch-anim",
        "command": command,
        "ok": True,
        "state": None,
        "effective": None,
        "presets": None,
        "on_disk_matches_state": None,
        "target": None,
        "written": None,
        "unchanged": False,
        "dry_run": False,
        "backup": None,
        "settings": None,
        "rollback": None,
        "warnings": [],
        "reload": {"ran": [], "skipped": []},
        "verification": {"luac": None, "configerrors": None, "verdict": "not-run"},
    }


# ---------------------------------------------------------------- subcommands


def cmd_list(args: argparse.Namespace, env: Dict[str, str]) -> int:
    tokens = anim.load_tokens()
    surface = anim.load_surface()
    state = _resolve(tokens, env)
    effective = _effective_preset(tokens, state)
    names = anim.preset_names(tokens)
    report = args.report
    report["state"] = _public_state(state)
    report["presets"] = []

    _say("iArch by Safari — animation presets")
    for name in names:
        preset = anim.load_preset(name)
        events = preset.get("events") or {}
        on = sum(1 for event in events.values() if event.get("enabled"))
        durations = sorted({event["duration_ms"] for event in events.values()
                            if event.get("enabled") and "duration_ms" in event})
        band = f"{durations[0]}-{durations[-1]} ms" if durations else "no durations"
        active = " (active)" if name == state["preset"] else ""
        forced = " (forced by reduce-motion)" if name == effective and state["reduce_motion"] else ""
        entry = {
            "name": name,
            "label": preset.get("label"),
            "description": preset.get("description"),
            "master": bool(preset.get("master")),
            "events": len(events),
            "events_animating": on,
            "duration_band_ms": durations,
            "active": name == state["preset"],
            "effective": name == effective,
        }
        report["presets"].append(entry)
        _say(f"  {name:<8} {preset.get('label')}{active}{forced}")
        _say(f"           {len(events)} events, {on} animating, {band}")
        _say(f"           {preset.get('description')}")
    report["effective_preset"] = effective
    _emit(report, args)
    return EXIT_OK


def cmd_set(args: argparse.Namespace, env: Dict[str, str]) -> int:
    tokens, surface = anim.load_tokens(), anim.load_surface()
    if args.preset not in anim.preset_names(tokens):
        raise AnimCliError(f"unknown preset {args.preset!r}; the presets are "
                           f"{', '.join(anim.preset_names(tokens))}")
    state = _resolve(tokens, env, preset=args.preset)
    report = args.report
    _say(f"iArch by Safari — animation preset {args.preset!r}")
    code = _apply(tokens, surface, state, _config_home(args.config_home), env, args, report)
    _emit(report, args)
    return code


def cmd_speed(args: argparse.Namespace, env: Dict[str, str]) -> int:
    tokens, surface = anim.load_tokens(), anim.load_surface()
    low, high, _default = anim.multiplier_bounds(tokens)
    state = _resolve(tokens, env, speed=args.multiplier)
    report = args.report
    _say(f"iArch by Safari — animation speed {args.multiplier}")
    if state["_speed_clamped"]:
        _warn(f"{args.multiplier} is outside {low}..{high}; using {state['speed']}")
    _say(f"  multiplier {state['speed']} — above 1 is faster, so every duration is divided by it")
    code = _apply(tokens, surface, state, _config_home(args.config_home), env, args, report)
    _emit(report, args)
    return code


def cmd_toggle(args: argparse.Namespace, env: Dict[str, str]) -> int:
    tokens, surface = anim.load_tokens(), anim.load_surface()
    state = _resolve(tokens, env)
    name = _effective_preset(tokens, state)
    preset = anim.load_preset(name)
    events = preset.get("events") or {}
    leaf = args.event

    if leaf not in events:
        raise AnimCliError(f"{leaf!r} is not an event the {name!r} preset declares; the events "
                           f"are {', '.join(sorted(events))}")
    if not bool(preset.get("master")):
        raise RefusedError(f"the {name!r} preset turns the master animation switch off, so every "
                           f"event is already inert; choose another preset to toggle {leaf}")

    current = bool(events[leaf]["enabled"])
    if leaf in state["event_overrides"]:
        current = bool(state["event_overrides"][leaf])
    wanted = not current
    if wanted and not bool(events[leaf]["enabled"]):
        if state["reduce_motion"]:
            raise RefusedError(f"reduce-motion is on and turns {leaf} off; "
                               f"run `iarch-anim reduce-motion off` first")
        raise RefusedError(f"the {name!r} preset declares {leaf} off and gives it no duration or "
                           f"curve, so there is nothing to turn on; choose a preset that animates "
                           f"{leaf}")

    overrides = dict(state["event_overrides"])
    if wanted == bool(events[leaf]["enabled"]):
        # Back to what the preset itself says, so the override is dropped rather
        # than left behind to outlive the reason for it.
        overrides.pop(leaf, None)
    else:
        overrides[leaf] = wanted

    state = dict(state)
    state["event_overrides"] = overrides
    report = args.report
    _say(f"iArch by Safari — toggle {leaf}: {'on' if wanted else 'off'}")
    code = _apply(tokens, surface, state, _config_home(args.config_home), env, args, report)
    _emit(report, args)
    return code


def cmd_reduce_motion(args: argparse.Namespace, env: Dict[str, str]) -> int:
    tokens, surface = anim.load_tokens(), anim.load_surface()
    wanted = args.state == "on"
    state = _resolve(tokens, env, reduce_motion=wanted)
    report = args.report
    forced = anim.reduce_motion_preset(tokens)
    cap = anim.reduce_motion_cap_ms(tokens)
    _say(f"iArch by Safari — reduce-motion {args.state}")
    if wanted:
        _say(f"  forces the {forced!r} preset (fades only, nothing slides) and caps every "
             f"duration at {cap} ms")
        if state["preset"] != forced:
            _say(f"  your selected preset stays {state['preset']!r} and comes back when "
                 f"reduce-motion is turned off")
    code = _apply(tokens, surface, state, _config_home(args.config_home), env, args, report)
    # This command owns the compositor half of the switch. The GTK sheets are the
    # other half, and iarch-theme renders them: it reads the same
    # animation.reduce_motion from settings.json and emits every transition at
    # 0ms, which is the only lever GTK 3 has, since it cannot parse an @media
    # query at all. Saying so is the difference between a switch that works and
    # one that only appears to.
    report["warnings"].append(
        "reduce-motion also governs the GTK 4 and GTK 3 sheets, which this command "
        "does not render: run `iarch-theme apply` so they follow")
    _warn(f"reduce-motion {args.state} is recorded and the compositor side is applied; "
          f"run `iarch-theme apply` so the GTK sheets follow")
    _emit(report, args)
    return code


def cmd_current(args: argparse.Namespace, env: Dict[str, str]) -> int:
    tokens, surface = anim.load_tokens(), anim.load_surface()
    state = _resolve(tokens, env)
    preset, plan, warnings = _plan(tokens, surface, state)
    name = _effective_preset(tokens, state)
    report = args.report
    report["state"] = _public_state(state)
    report["effective"] = {
        "preset": name,
        "label": preset.get("label"),
        "master": bool(preset.get("master")),
        "multiplier": state["speed"],
        "reduce_motion": state["reduce_motion"],
        "duration_cap_ms": (anim.reduce_motion_cap_ms(tokens) if state["reduce_motion"] else None),
        "events": plan,
    }
    report["warnings"].extend(warnings)
    report["target"] = display(_target(_config_home(args.config_home)))
    report["settings"] = {"path": display(configstore.user_path(SETTINGS_NAME, env))}

    user = _user_animation(env)
    _say("iArch by Safari — current animation state")
    _say(f"  preset:        {state['preset']}"
         + ("" if user.get("preset") else "   (repository default)"))
    _say(f"  rendered as:   {name} — {preset.get('label')}")
    if state["reduce_motion"]:
        _say(f"  reduce-motion: on (forces {name!r}, every duration capped at "
             f"{anim.reduce_motion_cap_ms(tokens)} ms)")
    else:
        _say("  reduce-motion: off")
    low, high, _default = anim.multiplier_bounds(tokens)
    _say(f"  speed:         {state['speed']} (clamped to {low}..{high}; above 1 is faster)")
    overrides = state["event_overrides"]
    _say(f"  overrides:     " + (", ".join(f"{k}={'on' if v else 'off'}"
                                           for k, v in sorted(overrides.items()))
                                 if overrides else "none"))
    _say(f"  master switch: {'on' if preset.get('master') else 'off'}")
    animating = [entry for entry in plan if entry["enabled"]]
    _say(f"  events:        {len(animating)} of {len(plan)} animating")
    for warning in warnings:
        _warn(warning)

    path = _target(_config_home(args.config_home))
    try:
        source = anim.build_preset(tokens, surface, preset, multiplier=state["speed"],
                                   reduce_motion=state["reduce_motion"],
                                   overrides=overrides).rstrip("\n")
        matches = _on_disk_equals(path, _rendered_bytes(path, source))
    except anim.AnimationError as exc:
        matches = False
        _warn(f"the state on record cannot be rendered: {exc}")
    report["on_disk_matches_state"] = matches
    _say(f"  {display(path)}: "
         + ("matches this state" if matches else
            "does NOT match this state — run any iarch-anim command to rewrite it"))

    if args.live:
        live = _live_animations()
        errors = _config_errors()
        report["verification"]["live"] = live
        report["verification"]["configerrors"] = {"after": errors}
        if live is None:
            _warn(f"`{' '.join(ANIMATIONS_COMMAND)}` gave no answer; is the session running?")
            report["verification"]["verdict"] = "unverified"
        else:
            _say("  live:          the compositor answered `hyprctl -j animations`")
            report["verification"]["verdict"] = (
                "clean" if errors is not None and not errors else "unverified")
            if errors:
                for line in errors:
                    _warn(f"configerrors: {line}")
    _emit(report, args)
    return EXIT_OK


# ---------------------------------------------------------------- entry point


def _emit(report: Dict[str, Any], args: argparse.Namespace) -> None:
    if getattr(args, "json", False):
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iarch-anim",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    default_home = str(Path.home() / ".config")

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config-home", default=default_home,
                        help=f"live config root to write under (default {default_home})")
        sp.add_argument("--no-reload", action="store_true",
                        help="write the file but do not ask the compositor to reload")
        sp.add_argument("--dry-run", action="store_true",
                        help="render and report only; write nothing, change no settings, "
                             "reload nothing")
        sp.add_argument("--json", action="store_true",
                        help="print one machine-readable object instead of prose")

    list_p = sub.add_parser("list", help="the presets, and which one is active")
    common(list_p)
    list_p.set_defaults(func=cmd_list)

    set_p = sub.add_parser("set", help="choose a preset")
    set_p.add_argument("preset", help="smooth, snappy, bouncy, minimal or off")
    common(set_p)
    set_p.set_defaults(func=cmd_set)

    speed_p = sub.add_parser("speed", help="set the global multiplier; above 1 is faster")
    speed_p.add_argument("multiplier", type=float, help="0.5 to 2.0; clamped, not refused")
    common(speed_p)
    speed_p.set_defaults(func=cmd_speed)

    toggle_p = sub.add_parser("toggle", help="turn one event on or off on top of the preset")
    toggle_p.add_argument("event", help="an animation leaf the active preset declares, "
                                        "e.g. windows, workspaces, borderangle")
    common(toggle_p)
    toggle_p.set_defaults(func=cmd_toggle)

    reduce_p = sub.add_parser("reduce-motion", help="force fades only, capped under 100 ms")
    reduce_p.add_argument("state", choices=("on", "off"))
    common(reduce_p)
    reduce_p.set_defaults(func=cmd_reduce_motion)

    current_p = sub.add_parser("current", help="the state, the resolved plan, and the file")
    common(current_p)
    current_p.add_argument("--live", action="store_true",
                           help="also ask the compositor what it is animating with now")
    current_p.set_defaults(func=cmd_current)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    global _JSON_MODE
    args = build_parser().parse_args(argv)
    _JSON_MODE = bool(getattr(args, "json", False))
    env = os.environ
    # One report per run, owned here and handed to the subcommand, so a refusal or
    # a usage error still prints everything learned before it -- the state that was
    # resolved, the plan it produced, what was written and what the compositor said.
    # A caller in Part 4 or Part 5 needs the rollback reason on the failure path
    # most of all, which is exactly where a fresh report would have dropped it.
    report = _new_report(getattr(args, "command", "?"))
    args.report = report
    try:
        return args.func(args, env)
    except RefusedError as exc:
        report["ok"] = False
        report["error"] = str(exc)
        report["exit"] = EXIT_REFUSED
        if getattr(args, "json", False):
            sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
        else:
            print(f"iarch-anim: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (AnimCliError, anim.AnimationError, configstore.ConfigError, OSError) as exc:
        report["ok"] = False
        report["error"] = str(exc)
        report["exit"] = EXIT_USAGE
        if getattr(args, "json", False):
            sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
        else:
            print(f"iarch-anim: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
