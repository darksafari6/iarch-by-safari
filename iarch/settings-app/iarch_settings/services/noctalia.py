# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The shell's IPC, and the record of which verbs this project may send.

The shell that draws the bar, the dock, the launcher and the notifications has a
command line of its own: ``noctalia msg <verb> [argument...]``. The settings
application sends those verbs rather than editing the shell's ``config.toml``,
because a value written to a file the shell has already loaded is a value the
shell does not know about until it is told, and telling it is the verb's job.

Two rules make this safe, and both are enforced here rather than left to a page:

* **A verb has to be in ``data/design/noctalia-ipc.json``.** That record was read
  out of ``src/cli/schema_msg.h`` at a pinned release, entry by entry, because
  grepping quoted strings out of the same header yields 204 names and most of them
  are positional-argument names or choice values rather than commands --
  ``monitor-selector`` is exactly that, and sending it would be refused only at
  runtime, on somebody's desktop. :func:`send` refuses an unrecorded verb, an
  argument count the record does not allow, and a value outside a recorded choice
  list, all before a process is started.
* **A reply is read, not trusted.** ``ok`` can mean a no-op: caffeine answers
  ``ok`` when it was already in the state asked for
  (``src/idle/idle_inhibitor.cpp:175-212``). And a missing binary is unverified,
  which is neither a pass nor a failure -- the same line ``iarch/lib/modes.py``
  draws for the compositor.

Nothing here stores a copy of a shell setting. The bar, the dock, the audio, the
idle and the wallpaper keys belong to the shell, so they are read and written
through it and ``~/.config/iarch/settings.json`` never holds a second value that
could disagree with the first.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import paths
from . import runner

#: The record's own invocation, so a message can quote it exactly.
INVOCATION = "noctalia msg <verb> [argument...]"

ERROR_PREFIX = "error:"

#: Verbs recorded but deliberately never sent. A page that reaches for one of
#: these gets a refusal that says why, rather than a capability the product does
#: not have.
NOT_USED = ("greeter-sync", "effects-profile-set")

#: The session actions this project will send. The record lists seven; a panel
#: that can log out, reboot or power off is one mis-click from lost work, and the
#: shell's own session menu already draws those with the confirmation it owns.
SESSION_ACTIONS = ("lock", "suspend", "lock-and-suspend")

#: The panel ids this project opens, taken from the record's own examples.
PANEL_LAUNCHER = "launcher"
PANEL_CONTROL_CENTER = "control-center"


class NoctaliaError(RuntimeError):
    """A verb, an argument or a value the record does not allow."""


# ------------------------------------------------------------------ the record


def record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/noctalia-ipc.json``, parsed."""
    try:
        return json.loads(paths.design_file("noctalia-ipc.json", root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoctaliaError(f"the shell IPC record cannot be read: {exc}") from exc


def verbs(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Every recorded verb, by name."""
    return {entry["verb"]: entry for entry in record(root)["verbs"]}


def verb_names(root: Optional[Path] = None) -> List[str]:
    """The recorded verb names, sorted. This is the closed list a test checks against."""
    return sorted(verbs(root))


def not_commands(root: Optional[Path] = None) -> List[str]:
    """Names that look like verbs and are not, so a test can assert none is sent."""
    names: List[str] = []
    for entry in record(root)["not_commands"]:
        names.extend(part.strip() for part in entry["spelling"].split(","))
    return [name for name in names if name]


# ------------------------------------------------------------------ arguments


def toml_value(value: Any) -> str:
    """A Python value as the TOML literal ``config-set`` expects.

    The record is explicit that the second argument is TOML, and the header's own
    example quotes a string (``'light'``), so an unquoted one is not a string the
    shell can parse. Booleans are TOML's ``true``/``false``, numbers are printed
    the way TOML reads them, a list becomes an array, and anything else is refused
    rather than stringified into something the shell would silently misread.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(float(value))
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        escaped = "".join(ch if ch >= " " and ch != "\x7f" else f"\\u{ord(ch):04x}"
                          for ch in escaped)
        return f'"{escaped}"'
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    raise NoctaliaError(f"{value!r} is not a value TOML can hold, so config-set cannot send it")


def check_arguments(entry: Mapping[str, Any], args: Sequence[str]) -> List[str]:
    """Every way ``args`` disagrees with the record's declaration of this verb."""
    declared = entry.get("arguments", [])
    required = [item for item in declared if item.get("required")]
    problems: List[str] = []
    verb = entry["verb"]

    if len(args) < len(required):
        names = ", ".join(item["name"] for item in required)
        problems.append(f"{verb} needs {len(required)} argument{'s' if len(required) != 1 else ''}"
                        f" ({names}) and got {len(args)}")
    if len(args) > len(declared):
        problems.append(f"{verb} takes at most {len(declared)} argument"
                        f"{'s' if len(declared) != 1 else ''} and got {len(args)}")

    for index, (argument, value) in enumerate(zip(declared, args)):
        choices = argument.get("choices")
        if choices and value not in choices:
            problems.append(f"{verb} argument {argument['name']} is {value!r}, which is not "
                            f"one of {', '.join(choices)}")
    return problems


# -------------------------------------------------------------- config paths


def design_record(root: Optional[Path] = None) -> Dict[str, Any]:
    """``data/design/noctalia.json``, parsed: the shell's own configuration keys."""
    try:
        return json.loads(paths.design_file("noctalia.json", root).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NoctaliaError(f"the shell configuration record cannot be read: {exc}") from exc


def key_specs(root: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """Every shell configuration key the record declares, by dotted config path.

    A section name in the record is already a dotted prefix -- ``theme``, ``dock``,
    ``bar.default`` -- and ``bar.default`` is the bar whose own ``name`` key is
    ``default``, which is why the bar's keys are three words deep while the dock's
    are two. Nothing here invents a path: every key comes out of the record, so a
    key added to the record is a key a page can offer, and a key the record does
    not carry cannot be sent.
    """
    sections = design_record(root).get("sections") or {}
    specs: Dict[str, Dict[str, Any]] = {}
    for name, section in sections.items():
        if not isinstance(section, dict):
            continue
        keys = section.get("keys")
        if not isinstance(keys, dict):
            continue
        for key, spec in keys.items():
            specs[f"{name}.{key}"] = dict(spec) if isinstance(spec, dict) else {}
    return specs


def known_paths(root: Optional[Path] = None) -> List[str]:
    """The recorded config paths, sorted. The closed list a test checks against."""
    return sorted(key_specs(root))


def check_path(path: str, root: Optional[Path] = None) -> List[str]:
    """Why ``path`` is not a key the record declares, or an empty list.

    The shell answers an unknown path with ``warning: unknown setting`` and then
    ignores it, so a typo would come back looking like a value. Refusing it here
    means the sentence a person reads names the record, not the shell's warning.
    """
    specs = key_specs(root)
    if path in specs:
        return []
    section = path.rsplit(".", 1)[0]
    siblings = sorted(other.rsplit(".", 1)[1] for other in specs
                      if other.rsplit(".", 1)[0] == section)
    hint = (f" the {section} keys are {', '.join(siblings)}" if siblings else
            f" the sections are {', '.join(sorted({key.rsplit('.', 1)[0] for key in specs}))}")
    return [f"{path!r} is not a shell configuration key in data/design/noctalia.json, so it "
            f"is not sent;{hint}"]


def check_value(path: str, value: Any, root: Optional[Path] = None) -> List[str]:
    """Why ``value`` cannot be written to ``path``, or an empty list.

    Two of the shell's own behaviours are the reason this exists: an out-of-range
    number is **clamped and continues**, and a bad type is an error that leaves the
    old value in place. A clamp is the worse of the two, because the reply says the
    set worked and the value that arrived is not the one asked for, so both are
    refused here -- which is what the record's own ``diagnostics.consequence``
    demands of anything this project sends.
    """
    specs = key_specs(root)
    spec = specs.get(path)
    if spec is None:
        return check_path(path, root)
    kind = spec.get("type")
    problems: List[str] = []

    if kind == "bool" and not isinstance(value, bool):
        problems.append(f"{path} is a boolean, and {value!r} is not one")
    elif kind in ("integer", "float"):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"{path} is a number, and {value!r} is not one")
        else:
            bounds = spec.get("range") or []
            if len(bounds) >= 2:
                low, high = float(bounds[0]), float(bounds[1])
                if not low <= float(value) <= high:
                    problems.append(
                        f"{value!r} is outside the range {path} accepts, {low:g} to {high:g}: the "
                        f"shell would clamp it and report success, so it is not sent")
                elif kind == "integer" and float(value) != int(value):
                    problems.append(f"{path} is an integer key, and {value!r} has a fraction")
    elif kind == "string" and not isinstance(value, str):
        problems.append(f"{path} is a string, and {value!r} is not one")

    choices = spec.get("enum")
    if isinstance(choices, list) and isinstance(value, str) and value not in choices:
        problems.append(f"{value!r} is not one of the values {path} accepts: "
                        f"{', '.join(str(choice) for choice in choices)}")
    return problems


# ------------------------------------------------------------------ sending


def send(verb: str, *args: Any, root: Optional[Path] = None,
         timeout: float = runner.DEFAULT_TIMEOUT) -> runner.Outcome:
    """Send one recorded verb and classify the reply.

    Refuses, before starting a process: a verb the record does not carry, a verb
    the record carries but this project refuses to send, an argument count the
    record does not allow, and a value outside a recorded choice list. A refusal
    is an :data:`runner.FAILED` outcome whose reason says which rule was broken,
    so a page shows a sentence rather than a stack trace.

    Every argument becomes one argv element. There is no shell anywhere in this
    path, so a wallpaper path with a space in it, or a brightness value that came
    out of a text field, cannot become two arguments or a command.
    """
    table = verbs(root)
    if verb in NOT_USED:
        refusal = next((entry for entry in record(root)["not_used"]
                        if entry["verb"].startswith(verb)), None)
        why = refusal["why"] if refusal else "this project refuses to send it"
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", verb], runner.FAILED,
                              reason=f"{verb} is recorded but not used: {why}")
    entry = table.get(verb)
    if entry is None:
        known = ", ".join(verb_names(root))
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", verb], runner.FAILED,
                              reason=f"{verb!r} is not in data/design/noctalia-ipc.json, so it "
                                     f"is not sent; the recorded verbs are {known}")

    rendered = [str(arg) for arg in args]
    if verb == "session" and rendered and rendered[0] not in SESSION_ACTIONS:
        # A product-level refusal, enforced here rather than only in session() so
        # that no caller can reach the four actions by going round the helper: the
        # record carries them because the shell has them, and this project does not.
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", verb, *rendered], runner.FAILED,
                              reason=f"session {rendered[0]!r} is not one of "
                                     f"{', '.join(SESSION_ACTIONS)}: a panel that can end a "
                                     "session, reboot or power off the machine is one mis-click "
                                     "from lost work, and the shell's own session menu already "
                                     "draws those actions with the confirmation the shell owns")
    problems = check_arguments(entry, rendered)
    if problems:
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", verb, *rendered], runner.FAILED,
                              reason="; ".join(problems))
    return runner.run(runner.NOCTALIA_BIN, ["msg", verb, *rendered], timeout=timeout)


def reply_text(outcome: runner.Outcome) -> str:
    """The shell's one-line reply, stripped, or an empty string."""
    return (outcome.stdout or "").strip()


def refused(outcome: runner.Outcome) -> bool:
    """True when the shell answered with an error rather than doing the thing.

    Read out of the reply text and not out of the exit code: a handler prints one
    line and exits non-zero when it refuses, but an unreachable socket is also a
    non-zero exit, and the two need different sentences.
    """
    text = reply_text(outcome).lower()
    return text.startswith(ERROR_PREFIX) or "error" in text or "unavailable" in text


def answered(outcome: runner.Outcome) -> Optional[str]:
    """The reply when the shell answered at all, else ``None``."""
    if not outcome.ran:
        return None
    text = reply_text(outcome)
    return text or None


def available() -> str:
    """A one-line description of what can and cannot be asked of the shell."""
    if runner.which(runner.NOCTALIA_BIN) is None:
        return ("the shell binary is not on PATH, so no verb can be sent and every value "
                "below is unverified rather than off")
    return "the shell binary is on PATH; a verb that is refused says so in the row"


# ------------------------------------------------------------------ the verbs


def theme_mode() -> Tuple[Optional[str], str]:
    """``dark``, ``light`` or ``auto``, as ``(value, verdict)``."""
    outcome = send("theme-mode-get")
    text = answered(outcome)
    if text is None:
        return None, outcome.verdict
    lowered = text.lower()
    for known in ("dark", "light", "auto"):
        if known in lowered:
            return known, runner.OK
    return None, runner.FAILED


def set_theme_mode(mode: str) -> runner.Outcome:
    """One of the three recorded spellings; the record's choice list enforces it."""
    return send("theme-mode-set", mode)


def dnd_status() -> Tuple[Optional[bool], str]:
    """Do Not Disturb, as ``(value, verdict)``.

    The handler prints exactly ``on`` or ``off``
    (``src/app/application_ipc.cpp:158-159``), so anything else is a refusal or a
    shell too old for the verb, and both are reported rather than read as off.
    """
    outcome = send("notification-dnd-status")
    text = answered(outcome)
    if text is None:
        return None, outcome.verdict
    lowered = text.lower()
    if lowered == "on":
        return True, runner.OK
    if lowered == "off":
        return False, runner.OK
    return None, runner.FAILED


def set_dnd(state: bool) -> runner.Outcome:
    """Turn Do Not Disturb on or off. ``on``/``off`` are the recorded spellings."""
    return send("notification-dnd-set", "on" if state else "off")


def read(path: str, root: Optional[Path] = None) -> Tuple[Optional[Any], str, str]:
    """Read one shell configuration key, as ``(value, verdict, reason)``.

    The three-part answer is what a page needs, because "could not be asked" and
    "the shell said no" and "the value is empty" are three different sentences on
    a screen, and a two-part answer collapses the first two into the same ``None``.

    The path is checked against ``data/design/noctalia.json`` before it is sent, so
    a typo is refused here rather than answered with the shell's unknown-setting
    warning -- which a reader would otherwise have to parse out of a reply that
    looks like a value.
    """
    problems = check_path(path, root)
    if problems:
        return None, runner.FAILED, "; ".join(problems)
    outcome = send("config-get", path)
    text = answered(outcome)
    if text is None:
        return None, outcome.verdict, (outcome.reason or reply_text(outcome)
                                       or "the shell did not answer")
    try:
        return json.loads(text), runner.OK, ""
    except json.JSONDecodeError:
        # A bare word or a number is a legitimate reply for a scalar key.
        return text, runner.OK, ""


def config_get(path: str, root: Optional[Path] = None) -> Tuple[Optional[Any], str]:
    """Read one shell configuration key by its dotted path: ``(value, verdict)``."""
    value, verdict, _reason = read(path, root)
    return value, verdict


def config_set(path: str, value: Any, root: Optional[Path] = None) -> runner.Outcome:
    """Write one shell configuration key. The value is encoded as TOML.

    Both the path and the value are checked against the record first, for the reason
    :func:`check_value` gives: the shell clamps an out-of-range number and reports
    success, and a reply that says the change worked is not a change that arrived.
    """
    problems = check_path(path, root) or check_value(path, value, root)
    if problems:
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", "config-set", path],
                              runner.FAILED, reason="; ".join(problems))
    try:
        rendered = toml_value(value)
    except NoctaliaError as exc:
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", "config-set", path],
                              runner.FAILED, reason=str(exc))
    return send("config-set", path, rendered)


def reload() -> runner.Outcome:
    """Ask the shell to re-read its own configuration."""
    return send("config-reload")


def wallpaper(connector: Optional[str] = None) -> Tuple[Optional[str], str]:
    """The wallpaper path, for one output or for all of them."""
    outcome = send("wallpaper-get", connector) if connector else send("wallpaper-get")
    return answered(outcome), outcome.verdict


def set_wallpaper(path: str, connector: Optional[str] = None) -> runner.Outcome:
    """Set the wallpaper from a local path.

    A path, not a URI: the picker hands over a local file, so no scheme parsing is
    involved, and the path travels as one argv element however many spaces it has.
    """
    if not path or not isinstance(path, str):
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", "wallpaper-set"], runner.FAILED,
                              reason="a wallpaper path must be a non-empty string")
    argv = [connector, path] if connector else [path]
    return send("wallpaper-set", *argv)


def wifi_status() -> Tuple[Optional[str], str]:
    outcome = send("wifi-status")
    return answered(outcome), outcome.verdict


def bluetooth_status() -> Tuple[Optional[str], str]:
    outcome = send("bluetooth-status")
    return answered(outcome), outcome.verdict


def toggle(kind: str) -> runner.Outcome:
    """``wifi``, ``bluetooth`` or ``network``: the recorded toggle verbs."""
    table = {"wifi": "wifi-toggle", "bluetooth": "bluetooth-toggle",
             "network": "network-toggle"}
    verb = table.get(kind)
    if verb is None:
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", kind], runner.FAILED,
                              reason=f"{kind!r} has no toggle verb in the record")
    return send(verb)


# ------------------------------------------------------------------ page verbs
#
# Zero-argument spellings of the calls above, one per button a page draws. They exist
# because a plan row names a function and the renderer calls it with nothing: a row
# cannot carry arguments, and a row that had to would be a row that could smuggle a
# value past the plan's checks. Each of these is one recorded verb with its argument
# already decided, so the set of things a button can do to the shell is exactly the
# set written here -- and a test can enumerate it.


def lock_now() -> runner.Outcome:
    """Lock the session now. One of the three session actions this project offers."""
    return session("lock")


def suspend_now() -> runner.Outcome:
    """Suspend the session now."""
    return session("suspend")


def screen_off() -> runner.Outcome:
    """Turn the panel off without touching the idle timer."""
    return screen("off")


def screen_on() -> runner.Outcome:
    """Turn the panel back on."""
    return screen("on")


def toggle_wifi() -> runner.Outcome:
    """The shell's own wi-fi toggle."""
    return toggle("wifi")


def toggle_bluetooth() -> runner.Outcome:
    """The shell's own bluetooth toggle."""
    return toggle("bluetooth")


def toggle_network() -> runner.Outcome:
    """The shell's own network toggle, which is wired rather than wireless."""
    return toggle("network")


def screenshot_region() -> runner.Outcome:
    """Capture a region, through the shell's own capture."""
    return screenshot("region")


def screenshot_window() -> runner.Outcome:
    """Capture one window, through the shell's own capture."""
    return screenshot("window")


def open_launcher() -> runner.Outcome:
    """Open the shell's launcher panel."""
    return panel(PANEL_LAUNCHER)


def open_control_center() -> runner.Outcome:
    """Open the shell's control centre panel."""
    return panel(PANEL_CONTROL_CENTER)


#: Every page verb, so a test can assert that a button's action is one of them and
#: that none of them is a verb this project refuses.
PAGE_VERBS = ("lock_now", "suspend_now", "screen_off", "screen_on", "toggle_wifi",
              "toggle_bluetooth", "toggle_network", "screenshot_region",
              "screenshot_window", "open_launcher", "open_control_center")


def power_profile(profile: str) -> runner.Outcome:
    """Set the UPower power profile.

    The record is explicit that this argument has no closed choice list: the shell
    passes the profile to UPower and UPower decides. So this project offers the
    three the verb's own description names and reads back what UPower accepted,
    rather than assuming a fourth spelling works.
    """
    return send("power-set", profile)


def session(action: str) -> runner.Outcome:
    """Lock, suspend, or both. The other four recorded actions are refused."""
    if action not in SESSION_ACTIONS:
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", "session", action], runner.FAILED,
                              reason=f"{action!r} is not one of {', '.join(SESSION_ACTIONS)}: a "
                                     "panel that can end a session, reboot or power off is one "
                                     "mis-click from lost work, and the shell's own session menu "
                                     "already draws those")
    return send("session", action)


def screen(action: str) -> runner.Outcome:
    """``dpms-off`` or ``dpms-on``: the screen now, without touching the idle timer."""
    if action not in ("off", "on"):
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", action], runner.FAILED,
                              reason="the screen action is 'off' or 'on'")
    return send(f"dpms-{action}")


def panel(panel_id: str, context: Optional[str] = None) -> runner.Outcome:
    """Open one of the shell's own panels.

    The Sound, Network and Bluetooth rows use this instead of drawing a second
    mixer or a second device list: the panel that opens is the shell's, at the
    section asked for, which is why the recorded panel ids are the header's own
    examples.
    """
    argv = [panel_id, context] if context else [panel_id]
    return send("panel-open", *argv)


def open_shell_settings(section: Optional[str] = None) -> runner.Outcome:
    """Open the *shell's* settings window, not this one.

    The escape hatch for a key this project has not verified a range for: rather
    than store a copy of a value it cannot validate, the row hands the user to the
    surface that owns it.
    """
    return send("settings-open", section) if section else send("settings-open")


def screenshot(kind: str = "region") -> runner.Outcome:
    """Trigger the shell's own capture. ``region`` and ``window`` are recorded."""
    if kind not in ("region", "window"):
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", "screenshot"], runner.FAILED,
                              reason=f"{kind!r} is not a screenshot verb in the record")
    return send(f"screenshot-{kind}")


def caffeine(state: Optional[bool] = None) -> runner.Outcome:
    """Keep the session awake, or stop keeping it awake.

    There is no status verb, so the page cannot read this back: it sends the verb
    and reports the reply. ``ok`` can mean a no-op -- the inhibitor was already in
    that state -- which is why the reply is read rather than the exit code.
    """
    if state is None:
        return send("caffeine-toggle")
    return send("caffeine-enable" if state else "caffeine-disable")


def nightlight(state: Optional[bool] = None) -> runner.Outcome:
    """The blue-light filter.

    ``nightlight-force-toggle`` is recorded and not sent: it overrides a schedule,
    and a page that offers both a schedule and an override without saying which
    one wins is a page whose switch appears to do nothing.
    """
    if state is None:
        return send("nightlight-toggle")
    return send("nightlight-enable" if state else "nightlight-disable")


def volume_osd() -> runner.Outcome:
    """Show the shell's own volume surface, without changing the volume."""
    return send("volume-osd")
