#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""iarch-gamemode — one switch that drops compositor effects for latency.

Game mode is not a fifth intensity and not a sixth motion preset. It is the two
that already exist, applied together, remembered, and put back:

* ``theme.intensity`` goes to the intensity ``data/design/tokens.json`` names
  under ``modes.game.intensity`` -- ``performance``, which turns window blur off,
  inner glow off, inactive dimming off, every fill opaque and the shell's own
  ``[shell.animation]`` off;
* ``animation.preset`` goes to the preset *that intensity is already paired
  with*, read through ``gen_animations_lua.preset_for_intensity`` rather than
  repeated in the tokens, so the pairing cannot drift the way two copies of it
  would. For ``performance`` that is ``off``, which sets Hyprland's master
  animation switch (``animations:enabled``, recorded in
  ``data/design/animations.json`` under ``master_switch``) and warps every
  animated variable straight to its final value.

Everything else follows from those two, because ``iarch-theme`` renders eleven
targets from the intensity: the Hyprland glass and animation payloads, both GTK
sheets, the Kvantum theme, fontconfig, the shell's ``config.toml`` and palette,
and both lock-screen fallbacks. Game mode composes the two tools that own them
instead of reimplementing either, so the contrast gate, the atomic writes, the
backup rotation and the reload-then-verify-or-roll-back sequence all stay where
they already are, and a mode cannot drift away from what running those two
commands by hand would do.

What this tool deliberately does not do:

* **It does not override reduce-motion.** ``animation.reduce_motion`` forces the
  ``minimal`` preset and caps every duration, and it wins over a preset choice
  (``iarch_anim._effective_preset``). A person who set it made an accessibility
  choice, so game mode reports that the motion half resolved to ``minimal``
  instead of ``off`` rather than silently switching the setting off.
* **It does not touch the Part 1 coarse switches.** ``preset`` and ``effects`` in
  settings.json predate the design system and no renderer reads them yet;
  reconciling them with ``theme.intensity`` is Part 5 settings-app work, and
  writing them here would record a change nothing honours.
* **It invents no compositor keyword.** There is no ``hyprctl keyword`` on this
  compositor: nothing registers one at Hyprland v0.57.2 (only a plugin may,
  ``src/plugins/PluginAPI.cpp:357``), an unregistered request answers
  ``unknown request`` (``src/ipc/s1/S1.cpp:107``) and hyprctl still exits 0
  because that reply does not start with ``error:``
  (``hyprctl/src/main.cpp:283-288``). Game mode changes the rendered files and
  asks for one reload, which is the mechanism that works.

Verification compares rather than assumes. After the apply, four leaves are read
back from the compositor with ``hyprctl getoption <leaf> -j`` and compared with
what the tokens say the applied intensity and preset should produce:
``decoration:blur:enabled``, ``decoration:glow:enabled`` and
``decoration:dim_inactive`` from ``tokens.intensities.<name>``, and
``animations:enabled`` from the effective preset's master switch. ``hyprctl
reload`` is synchronous -- the handler calls ``Config::mgr()->reload()`` before
replying ``ok`` (``src/ipc/s1/Commands.cpp:1352-1370``) -- so a value read after
it is the value the session now runs. No ``hyprctl`` and no session means the
question could not be asked, which is reported as *unverified* and never as a
pass or a failure.

Game mode is persistent, unlike ``iarch-focus``: it rewrites generated files, so
it survives a reload, a relogin and a reboot, and ``iarch-gamemode off`` is what
ends it. Turning it off restores the intensity, the colour preset and the
animation preset that were recorded when it was turned on. Speed, reduce-motion
and per-event overrides are never modified, so they come back on their own.

Usage:
    python3 iarch/cli/iarch_gamemode.py status
    python3 iarch/cli/iarch_gamemode.py on
    python3 iarch/cli/iarch_gamemode.py off
    python3 iarch/cli/iarch_gamemode.py toggle

Every subcommand takes ``--config-home DIR`` (default ``~/.config``, where
hyprland.lua actually reads the generated files), ``--no-reload``, ``--dry-run``
and ``--json``. ``off`` also takes ``--forget``, which clears a record it cannot
honour instead of applying it.

Exit codes: 0 on success, 1 when a gate refused or the session rejected the
result and it was rolled back, 2 on a usage or data error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore, modes  # noqa: E402  (repo-root import by design)
from iarch.cli import gen_animations_lua as anim  # noqa: E402
from iarch.cli import iarch_anim as anim_cli  # noqa: E402
from iarch.cli import theme as theme_cli  # noqa: E402

MODE = "game"
TOOL = "iarch-gamemode"

EXIT_OK = modes.EXIT_OK
EXIT_REFUSED = modes.EXIT_REFUSED
EXIT_USAGE = modes.EXIT_USAGE

# The leaves a game-mode session is checked against. The three decoration leaves
# are in tokens.hyprland.leaves, which is the list that makes a Hyprland keyword
# emittable at all; the master switch is recorded in data/design/animations.json
# under master_switch.leaf. tests/test_gamemode.py asserts all four are recorded,
# so a check can never be built on a leaf this project has not verified exists.
CHECK_LEAVES: Tuple[str, ...] = (
    "decoration:blur:enabled",
    "decoration:glow:enabled",
    "decoration:dim_inactive",
)
MASTER_LEAF = "animations:enabled"

# The shell re-reads its own config.toml separately from the compositor: iarch-theme
# reloads both, iarch-anim only the compositor, and game mode suppresses the theme's
# reload so the desktop is not asked to redraw twice. This is the half that is left.
SHELL_RELOAD: Tuple[str, ...] = ("noctalia", "msg", "config-reload")


class GameModeError(RuntimeError):
    """A usage or data problem: nothing was changed."""


# ---------------------------------------------------------------- small helpers


def _config_home(raw: str) -> Path:
    home = Path(raw).expanduser()
    if not home.is_absolute():
        raise GameModeError(f"--config-home must be an absolute path: {raw!r}")
    return home


def _display(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def game_intensity(tokens: Dict[str, Any]) -> str:
    """The intensity game mode applies, out of the tokens rather than out of code."""
    return modes.tokens_modes(tokens)["game"]["intensity"]


def paired_preset(tokens: Dict[str, Any], intensity: str) -> str:
    """The motion preset an intensity is paired with, and the only one it is paired with.

    ``preset_for_intensity`` also enforces that ``motion.enabled`` and
    ``motion.preset`` agree, so a tokens edit that says "performance, but
    animating" fails here instead of shipping a game mode that animates.
    """
    return anim.preset_for_intensity(tokens, intensity)


def effective_preset(tokens: Dict[str, Any], requested: str, reduce_motion: bool) -> str:
    """The preset that will actually be rendered, after the reduce-motion rule."""
    return anim.reduce_motion_preset(tokens) if reduce_motion else requested


def master_of(preset_name: str) -> bool:
    """Whether a preset leaves Hyprland's master animation switch on."""
    return bool(anim.load_preset(preset_name).get("master"))


def expected_leaves(tokens: Dict[str, Any], intensity: str, preset_name: str) -> Dict[str, Any]:
    """What the compositor should say once ``intensity`` and ``preset_name`` are applied.

    Every value comes from a token: the three decoration leaves from the
    intensity's own blocks, the master switch from the preset document. Nothing
    here is what game mode *wants* to be true, which is the difference between a
    check and a slogan.
    """
    block = tokens["intensities"][intensity]
    expected = {
        "decoration:blur:enabled": bool(block["blur"]["enabled"]),
        "decoration:glow:enabled": bool(block["glow"]["enabled"]),
        "decoration:dim_inactive": bool(block["window"]["dim_inactive"]),
    }
    expected[MASTER_LEAF] = master_of(preset_name)
    return expected


def _resolved(env: Dict[str, str]) -> Tuple[Dict[str, Any], str, str, Dict[str, Any]]:
    """The state the two sibling tools would themselves resolve, in one read.

    ``theme._resolve`` and ``anim._resolve`` are the siblings' own order of
    precedence -- command line, then the user's settings, then the preset's
    default, then the tokens -- and a mode that resolved differently would record
    a "previous" state the tools disagree with. Returns
    ``(tokens, colour, intensity, animation_state)``.
    """
    tokens, _preset, colour, intensity = theme_cli._resolve(None, None, env)
    state = anim_cli._resolve(tokens, env)
    return tokens, colour, intensity, state


def _previous_record(tokens: Dict[str, Any], colour: str, intensity: str,
                     state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "colour_preset": colour,
        "intensity": intensity,
        "animation_preset": state["preset"],
        "reduce_motion": bool(state["reduce_motion"]),
    }


# ---------------------------------------------------------------- verification


def check_session(tokens: Dict[str, Any], intensity: str, preset_name: str,
                  report: Dict[str, Any]) -> str:
    """Ask the compositor what it runs and compare; returns the overall verdict.

    TODO(verify) MODE-01 in docs/UNVERIFIED.md: every half of this is read out of
    the pinned release and the round trip is proved against a faked compositor in
    tests/test_gamemode.py, but no session has ever been watched here, so a
    ``matches`` verdict is a comparison and not an observation.
    """
    expected = expected_leaves(tokens, intensity, preset_name)
    checks: List[Dict[str, Any]] = []
    for leaf in (*CHECK_LEAVES, MASTER_LEAF):
        want = expected[leaf]
        actual, reply = modes.getoption(leaf)
        if reply is None:
            verdict, detail = modes.UNVERIFIED, f"{modes.HYPRCTL} is not on PATH"
        elif actual is None:
            verdict = modes.UNVERIFIED
            detail = (f"the compositor answered {reply.stdout!r}" if reply.stdout
                      else f"`{' '.join(reply.command)}` gave no usable answer")
        elif modes.same_value(want, actual):
            verdict, detail = modes.MATCHES, f"{_format(actual)} as the tokens expect"
        else:
            verdict, detail = modes.DIFFERS, f"{_format(actual)}, expected {_format(want)}"
        entry = {"leaf": leaf, "expected": want, "actual": actual,
                 "verdict": verdict, "detail": detail}
        checks.append(entry)
        report["checks"].append(entry)
        if verdict == modes.MATCHES:
            modes.say(f"  verified:    {leaf} = {_format(actual)}")
        elif verdict == modes.DIFFERS:
            modes.warn(f"{leaf} is {detail}")
        else:
            modes.warn(f"{leaf} could not be read: {detail}")
    verdict = modes.overall_verdict(checks)
    report["verdict"] = verdict
    matched = sum(1 for check in checks if check["verdict"] == modes.MATCHES)
    if verdict == modes.MATCHES:
        modes.say(f"  session:       {matched} of {len(checks)} leaves match the applied state")
    elif verdict == modes.DIFFERS:
        modes.warn(f"the session does not run what was just applied: "
                   f"{matched} of {len(checks)} leaves match")
    else:
        modes.warn("the session was not asked, or did not answer, so this state is "
                   "unverified rather than confirmed")
    return verdict


def _format(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _step(report: Dict[str, Any], tool: str, argv: Sequence[str], code: int,
          out: Sequence[str], err: Sequence[str],
          parsed: Optional[Any] = None) -> Dict[str, Any]:
    """Record one sibling's run, and print its output indented under its name.

    A sibling run under ``--json`` prints a machine-readable report, which is
    kept whole in this report's ``steps`` but summarized in prose: dumping
    forty lines of JSON into a terminal because a tool asked for them would be
    the same mistake as printing prose into a JSON document.
    """
    step: Dict[str, Any] = {"tool": tool, "argv": list(argv), "exit": code,
                            "stdout": list(out), "stderr": list(err)}
    if parsed is not None:
        step["report"] = parsed
        # A sibling run with --json has just handed over the same information in a
        # usable shape, so keeping its raw lines too would double the size of this
        # report and put a JSON document inside a list of strings. The raw text is
        # kept exactly when it could not be parsed, which is when it is evidence.
        step["stdout"] = []
    report["steps"].append(step)
    modes.say(f"  {tool}:")
    if parsed is not None:
        for line in _summarize(parsed):
            modes.say(f"    {line}")
    else:
        for line in out:
            modes.say(f"    {line}")
    for line in err:
        # A sibling already prefixes its own warnings; doubling the word makes the
        # line read like a warning about a warning.
        modes.warn(f"{tool}: {line.removeprefix('warning: ').strip()}" if line.strip()
                   else f"{tool}: {line}")
    if code != EXIT_OK and parsed is not None and parsed.get("error"):
        modes.warn(f"{tool}: {parsed['error']}")
    return step


def _summarize(parsed: Dict[str, Any]) -> List[str]:
    """Three or four prose lines out of a sibling's JSON report."""
    lines: List[str] = []
    effective = parsed.get("effective") or {}
    if effective:
        events = effective.get("events") or []
        animating = sum(1 for event in events if event.get("enabled"))
        # ``name`` is not one of the keys a preset document must carry -- the
        # ``off`` preset has a label and a master switch and no name -- so the
        # label is what a person reads.
        which = effective.get("name") or effective.get("label") or "the requested preset"
        lines.append(f"preset {which!r} — {animating} of {len(events)} event(s) animating, "
                     f"master switch {'on' if effective.get('master') else 'off'}")
    if parsed.get("written"):
        lines.append(f"wrote {parsed['written']}")
    elif parsed.get("unchanged"):
        lines.append(f"unchanged {parsed.get('target', 'the generated file')}")
    verification = parsed.get("verification") or {}
    if "verdict" in verification:
        lines.append(f"verification: {verification['verdict']}")
    reload_block = parsed.get("reload") or {}
    for command in reload_block.get("ran") or []:
        lines.append(f"reload: ran `{command}`")
    for command in reload_block.get("skipped") or []:
        lines.append(f"reload: skipped `{command}`")
    if parsed.get("rollback"):
        lines.append(f"rolled back: {parsed['rollback'].get('reason')}")
    return lines


def _reload_shell(report: Dict[str, Any], no_reload: bool) -> None:
    """Ask the shell to re-read config.toml; the compositor was already reloaded."""
    printable = " ".join(SHELL_RELOAD)
    if no_reload:
        report["skipped"].append(f"{printable} (--no-reload)")
        modes.say(f"  reload: skipped `{printable}` (--no-reload)")
        return
    reply = modes.run(SHELL_RELOAD)
    if reply is None:
        report["skipped"].append(f"{printable} ({SHELL_RELOAD[0]} not on PATH)")
        modes.warn(f"{SHELL_RELOAD[0]} not found on PATH; skipped `{printable}` "
                   "(is the shell running?)")
        return
    if reply.ok:
        report["ran"].append(printable)
        modes.say(f"  reload: ran `{printable}`")
    else:
        report["skipped"].append(f"{printable} ({reply.text or f'exit {reply.returncode}'})")
        modes.warn(f"reload: `{printable}` did not answer ok: "
                   f"{reply.text or f'exit {reply.returncode}'}")


# ---------------------------------------------------------------- the round trip


def _apply_bundle(report: Dict[str, Any], tokens: Dict[str, Any], colour: str,
                  intensity: str, preset_name: str, config_home: Path,
                  env: Dict[str, str], args: argparse.Namespace,
                  rollback: Dict[str, str]) -> int:
    """Render the intensity, then the motion preset, then ask the shell to re-read.

    ``iarch-theme`` runs with ``--no-reload`` and ``iarch-anim`` without it, so the
    compositor is asked to reload exactly once and the reload that happens is the
    one ``iarch-anim`` verifies: it reads ``hyprctl configerrors`` before and after
    and puts the previous bytes back if the new ones produced an error that was not
    there before. The shell's own reload is this tool's job, because the theme's was
    suppressed and the shell reads a config.toml this apply just rewrote.

    A ``--no-reload`` given to *this* tool has to reach the motion half as well:
    ``iarch-anim set`` reloads the compositor itself, so suppressing only the
    theme's reload would still ask the session to re-parse and the flag would be a
    lie about what happened.
    """
    no_reload = bool(getattr(args, "no_reload", False))
    theme_argv = ["apply", colour, "--intensity", intensity,
                  "--config-home", str(config_home), "--no-reload"]
    code, out, err = modes.call_sibling(theme_cli.main, theme_argv, "iarch-theme")
    _step(report, "iarch-theme", theme_argv, code, out, err)
    if code != EXIT_OK:
        # Nothing else has run yet, so there is nothing to undo: the theme tool
        # either refused at its contrast gate or wrote all eleven targets and
        # rolled them all back.
        report["error"] = (f"iarch-theme refused to apply {colour!r} at {intensity!r} "
                           f"(exit {code}); no motion change was attempted")
        modes.warn(report["error"])
        return code

    anim_argv = ["set", preset_name, "--config-home", str(config_home), "--json"]
    if no_reload:
        anim_argv.append("--no-reload")
    code, out, err = modes.call_sibling(anim_cli.main, anim_argv, "iarch-anim")
    parsed = modes.parse_json_reply(out)
    _step(report, "iarch-anim", anim_argv, code, out, err, parsed)
    if code != EXIT_OK:
        # The motion half failed, so the intensity half goes back to what this run
        # found rather than to the saved restore point: those are the same thing
        # the first time game mode is switched on and different things the second,
        # and putting a desktop back where it was is the only rollback that cannot
        # surprise anybody.
        back = ["apply", rollback["colour"], "--intensity", rollback["intensity"],
                "--config-home", str(config_home)]
        if no_reload:
            back.append("--no-reload")
        restored_code, restored_out, restored_err = modes.call_sibling(
            theme_cli.main, back, "iarch-theme")
        _step(report, "iarch-theme (rollback)", back, restored_code, restored_out, restored_err)
        report["rollback"] = {"attempted": back, "exit": restored_code,
                              "restored": restored_code == EXIT_OK}
        report["error"] = (f"iarch-anim refused to apply the {preset_name!r} preset "
                           f"(exit {code}), so iarch-theme was run again to put "
                           f"{rollback['colour']!r} at {rollback['intensity']!r} back")
        modes.warn(report["error"])
        return EXIT_REFUSED

    _reload_shell(report, no_reload)
    return EXIT_OK


def cmd_on(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    tokens, colour, intensity, state = _resolved(env)
    target_intensity = game_intensity(tokens)
    requested = paired_preset(tokens, target_intensity)
    reduce_motion = bool(state["reduce_motion"])
    rendered = effective_preset(tokens, requested, reduce_motion)
    record = modes.mode_state(env, MODE)
    already = bool(record.get("active"))

    report["previous"] = _previous_record(tokens, colour, intensity, state)
    report["target"] = {"intensity": target_intensity, "animation_preset": requested,
                        "rendered_preset": rendered, "colour_preset": colour}
    report["active"] = True

    modes.say(f"iArch by Safari — game mode {'still on' if already else 'on'}")
    modes.say(f"  intensity:     {intensity} → {target_intensity}")
    if reduce_motion:
        modes.say(f"  animation:     {state['preset']} → {requested}, rendered as "
                  f"{rendered!r} because reduce-motion is on and wins")
        report["notes"].append(
            "animation.reduce_motion is on, so the motion half renders the "
            f"{rendered!r} preset with every duration capped rather than "
            f"{requested!r}; game mode does not switch an accessibility setting off")
    else:
        modes.say(f"  animation:     {state['preset']} → {requested} "
                  "(the preset this intensity is paired with)")
    if intensity == target_intensity and state["preset"] == requested and already:
        modes.say("  nothing to do: the session is already in game mode")

    if already:
        # Re-applying must not overwrite the restore point: the state read now is
        # the state game mode itself wrote, so recording it would make `off` a
        # no-op that looks like a restore.
        report["previous"] = record.get("previous") or report["previous"]
        report["notes"].append("game mode was already recorded as on, so the previous "
                               "state on record was kept rather than replaced")

    config_home = _config_home(args.config_home)
    if args.dry_run:
        report["dry_run"] = True
        modes.say(f"[dry-run] would apply {colour!r} at {target_intensity!r} with the "
                  f"{requested!r} preset, record the state above, and reload; "
                  "nothing was written")
        return EXIT_OK

    code = _apply_bundle(report, tokens, colour, target_intensity, rendered,
                         config_home, env, args,
                         {"colour": colour, "intensity": intensity})
    if code != EXIT_OK:
        report["ok"] = False
        report["applied"] = False
        report["exit"] = code
        return code

    report["applied"] = True
    if args.no_reload:
        report["notes"].append("no reload was requested, so the session was not asked "
                               "what it runs; the files on disk are the applied state")
        report["verdict"] = modes.UNVERIFIED
    else:
        check_session(tokens, target_intensity, rendered, report)

    path, changed = modes.write_mode(env, MODE, {"active": True,
                                                 "previous": report["previous"]})
    report["settings"] = {"path": _display(path), "changed": changed}
    modes.say(f"  settings: {'recorded' if changed else 'already recorded'} "
              f"modes.game in {_display(path)}")
    modes.say(f"game mode is on: {target_intensity} intensity, {rendered!r} motion. "
              "`iarch-gamemode off` puts the previous state back.")
    return modes.exit_for_verdict(
        report, "game mode is written to the files and recorded, but the session does not "
                "run it")


def cmd_off(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    tokens, colour, intensity, state = _resolved(env)
    record = modes.mode_state(env, MODE)
    previous = record.get("previous") if isinstance(record.get("previous"), dict) else None
    report["record"] = record
    report["active"] = False

    if args.forget:
        if not record:
            modes.say("iArch by Safari — game mode off")
            modes.say("  nothing recorded: modes.game is not in settings.json")
            return EXIT_OK
        path, changed = modes.write_mode(env, MODE, {"active": False})
        report["settings"] = {"path": _display(path), "changed": changed}
        report["notes"].append("--forget cleared the record without applying anything")
        modes.say("iArch by Safari — game mode record forgotten")
        modes.say(f"  settings: modes.game cleared in {_display(path)}; no file was "
                  "rendered and nothing was reloaded")
        return EXIT_OK

    if not record.get("active"):
        modes.say("iArch by Safari — game mode off")
        modes.say("  already off: modes.game is not recorded as active")
        if not args.dry_run and not args.no_reload:
            # Still worth asking what the session runs: "off" and "off but the
            # desktop disagrees" are different answers.
            check_session(tokens, intensity,
                          effective_preset(tokens, state["preset"], state["reduce_motion"]),
                          report)
        report["notes"].append("game mode was not recorded as on, so nothing was restored")
        return EXIT_OK

    if not previous or not isinstance(previous.get("intensity"), str):
        report["ok"] = False
        report["error"] = (
            "modes.game says game mode is on but records no usable previous state, so "
            "there is nothing to restore. Choose the state you want directly -- "
            "`python3 iarch/cli/theme.py apply --intensity frosted` and "
            "`python3 iarch/cli/iarch_anim.py set smooth` -- and then run "
            "`iarch-gamemode off --forget` to clear the record. This tool will not "
            "guess a theme on your behalf.")
        report["exit"] = EXIT_USAGE
        modes.warn(report["error"])
        return EXIT_USAGE

    restore_colour = previous.get("colour_preset") or colour
    restore_intensity = previous["intensity"]
    restore_preset = previous.get("animation_preset") or state["preset"]
    report["previous"] = dict(previous)
    report["target"] = {"intensity": restore_intensity, "animation_preset": restore_preset,
                        "rendered_preset": restore_preset, "colour_preset": restore_colour}

    modes.say("iArch by Safari — game mode off")
    modes.say(f"  intensity:     {intensity} → {restore_intensity}")
    modes.say(f"  animation:     {state['preset']} → {restore_preset}")
    modes.say(f"  colour:        {restore_colour}")
    modes.say("  speed, reduce-motion and per-event overrides were never changed, so "
              "they are still yours")

    if args.dry_run:
        report["dry_run"] = True
        modes.say("[dry-run] would restore the state above and reload; nothing was written")
        return EXIT_OK

    code = _apply_bundle(report, tokens, restore_colour, restore_intensity, restore_preset,
                         _config_home(args.config_home), env, args,
                         {"colour": colour, "intensity": intensity})
    if code != EXIT_OK:
        report["ok"] = False
        report["applied"] = False
        report["exit"] = code
        # The record stays: the mode is still on as far as the files are concerned,
        # and clearing it would leave no way back to the saved state.
        return code

    report["applied"] = True
    if args.no_reload:
        report["verdict"] = modes.UNVERIFIED
        report["notes"].append("no reload was requested, so the session was not asked")
    else:
        check_session(tokens, restore_intensity,
                      effective_preset(tokens, restore_preset,
                                       bool(previous.get("reduce_motion"))), report)

    path, changed = modes.write_mode(env, MODE, {"active": False})
    report["settings"] = {"path": _display(path), "changed": changed}
    modes.say(f"  settings: {'cleared' if changed else 'already cleared'} modes.game in "
              f"{_display(path)}")
    modes.say(f"game mode is off: {restore_colour!r} at {restore_intensity!r} with "
              f"{restore_preset!r} motion.")
    return modes.exit_for_verdict(
        report, "the previous state is written to the files and the record is cleared, but "
                "the session does not run it")


def cmd_toggle(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    """On when off, off when on, filling in the same report either half would."""
    active = modes.is_active(env, MODE)
    report["toggled_from"] = active
    report["command"] = f"toggle ({'off' if active else 'on'})"
    return cmd_off(args, env, report) if active else cmd_on(args, env, report)


def cmd_status(args: argparse.Namespace, env: Dict[str, str], report: Dict[str, Any]) -> int:
    """Report the record and the session, and always exit 0.

    Like ``iarch-focus status``, and like the ``current`` subcommands of its two
    siblings (theme.py:594, iarch_anim.py:827): a report that exits non-zero
    because the session disagrees cannot be told apart from one that could not
    run. Read ``report["verdict"]`` instead.
    """
    tokens, colour, intensity, state = _resolved(env)
    record = modes.mode_state(env, MODE)
    active = bool(record.get("active"))
    previous = record.get("previous") if isinstance(record.get("previous"), dict) else {}
    rendered = effective_preset(tokens, state["preset"], bool(state["reduce_motion"]))
    target_intensity = game_intensity(tokens)
    target_preset = paired_preset(tokens, target_intensity)

    report["record"] = record
    report["active"] = active
    report["previous"] = previous
    report["settings"] = {
        "path": _display(configstore.user_path(modes.SETTINGS_NAME, env)),
        "colour_preset": colour,
        "intensity": intensity,
        "animation_preset": state["preset"],
        "rendered_preset": rendered,
        "reduce_motion": bool(state["reduce_motion"]),
    }
    report["target"] = {"intensity": target_intensity, "animation_preset": target_preset}

    modes.say("iArch by Safari — game mode status")
    modes.say(f"  recorded:      {'on' if active else 'off'}")
    if active and previous:
        modes.say(f"  saved state:   {previous.get('colour_preset')} at "
                  f"{previous.get('intensity')} with {previous.get('animation_preset')} motion"
                  + (" (reduce-motion on)" if previous.get("reduce_motion") else ""))
    modes.say(f"  settings say:  {colour} at {intensity}, animation.preset="
              f"{state['preset']} rendered as {rendered!r}")

    agreement: List[Dict[str, Any]] = []
    if active:
        for what, actual, want in (("theme.intensity", intensity, target_intensity),
                                   ("animation.preset", state["preset"], target_preset)):
            entry = {"check": what, "actual": actual, "expected": want,
                     "verdict": modes.MATCHES if actual == want else modes.DIFFERS}
            agreement.append(entry)
            if entry["verdict"] == modes.DIFFERS:
                modes.warn(f"{what} is {actual!r} but game mode records {want!r}: something "
                           "re-rendered the desktop since. `iarch-gamemode on` applies it "
                           "again, `off` restores what was saved.")
    report["record_checks"] = agreement
    report["record_agreement"] = modes.overall_verdict(agreement) if agreement else None

    check_session(tokens, intensity, rendered, report)
    verdict = modes.overall_verdict([*agreement, *report["checks"]])
    report["verdict"] = verdict
    state = "on" if active else "off"
    if verdict == modes.MATCHES:
        modes.say(f"  game mode is {state} and the session agrees: {colour} at "
                  f"{intensity} with {rendered!r} motion")
    elif verdict == modes.DIFFERS:
        modes.say(f"  game mode is recorded {state} and the session disagrees")
    else:
        modes.say(f"  game mode is recorded {state}; the session did not answer for "
                  "everything above, so this is unverified rather than confirmed")
    report["exit"] = EXIT_OK
    return EXIT_OK


# ---------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=TOOL, description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    default_home = str(Path.home() / ".config")

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config-home", default=default_home,
                        help=f"live config root to write under (default {default_home})")
        sp.add_argument("--no-reload", action="store_true",
                        help="write the files but do not ask the compositor or the shell "
                             "to reload; the change is then reported as unverified")
        sp.add_argument("--dry-run", action="store_true",
                        help="report what would be applied and what is recorded now; "
                             "write nothing, change no settings, reload nothing")
        sp.add_argument("--json", action="store_true",
                        help="print one machine-readable object instead of prose")

    for name, help_text in (("status", "what is recorded, what settings say, and what "
                                       "the session runs"),
                            ("on", "apply the performance intensity and the motion preset "
                                   "it is paired with, saving the state to restore"),
                            ("toggle", "on when off, off when on")):
        sub_parser = sub.add_parser(name, help=help_text)
        common(sub_parser)
        sub_parser.set_defaults(func={"status": cmd_status, "on": cmd_on,
                                      "toggle": cmd_toggle}[name])

    off_parser = sub.add_parser("off", help="restore the intensity and motion preset that "
                                            "were saved when game mode was turned on")
    common(off_parser)
    off_parser.add_argument("--forget", action="store_true",
                            help="clear the record without applying anything, for a record "
                                 "that cannot be honoured")
    off_parser.set_defaults(func=cmd_off, forget=False)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "forget"):
        args.forget = False
    modes.set_json_mode(bool(args.json))
    env = os.environ
    report = modes.new_report(getattr(args, "command", "?"), MODE)
    report["tool"] = TOOL
    args.report = report
    try:
        code = args.func(args, env, report)
    except GameModeError as exc:
        report.update(ok=False, error=str(exc), exit=EXIT_USAGE)
        modes.emit(report)
        if not args.json:
            print(f"{TOOL}: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except (theme_cli.ThemeError, theme_cli.RefusedError, anim_cli.AnimCliError,
            anim.AnimationError, modes.ModeError, configstore.ConfigError, OSError) as exc:
        # A sibling's own error classes arrive here only when the failure happened
        # while resolving state, before any sibling was run: once a sibling runs,
        # its exit code is the answer and _apply_bundle handles the rollback.
        refused = isinstance(exc, theme_cli.RefusedError)
        report.update(ok=False, error=str(exc),
                      exit=EXIT_REFUSED if refused else EXIT_USAGE)
        modes.emit(report)
        if not args.json:
            print(f"{TOOL}: {exc}", file=sys.stderr)
        return EXIT_REFUSED if refused else EXIT_USAGE

    report["ok"] = code == EXIT_OK
    report["exit"] = code
    modes.emit(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
