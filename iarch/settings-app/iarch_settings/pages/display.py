# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Display page: six fields written, seventeen recorded and refused.

This is the one page in the application that can leave a screen unusable, and the
record for it says so in a sentence worth repeating rather than paraphrasing: a scale
or a resolution change is applied **first** and confirmed **after**, with a countdown
and a rollback, because a confirmation dialog drawn over a session that is already
running the new mode is a dialog the person may not be able to read. So the row is
marked risky, the change carries the confirmation, and the page says what happens when
nobody answers.

What the page offers comes out of ``data/design/monitors.json``, which was read out of
the compositor's rule parser field by field at a pinned release. That record carries
23 fields and marks 17 of them ``written_by_this_project: false`` -- colour management,
HDR, luminance, VRR, mirroring and the reserved area -- so this page draws six controls
per monitor and a group that lists the rest with the reason each is refused. The reason
matters more than the list: a wrong ICC profile or a mirrored output at the wrong scale
is a display nobody can read back, and the reserved area is what the shell's own bar
and dock already cost each output, so writing it would fight the shell for the same
edge of the screen.

The spellings each field accepts are the parser's, not this page's, and two of them are
traps the record names explicitly:

* ``scale`` is a **string**. A generator emitting ``scale = 1`` unquoted is a parse
  error rather than a scale of one, and a number below 0.25 is refused and reset to 1.
* ``mode`` and ``position`` accept a closed set of words plus an open shape -- ``WxH``,
  ``WxH@RR.RRHz``, ``XxY`` -- so they are entries with validators rather than
  dropdowns: a dropdown could offer the words but not the shapes, and an entry without
  a validator would let a person type a spelling the parser answers with ``invalid
  resolution`` while keeping the old mode.

``output`` is an entry too, and its validator prefers a name this page read back from
the compositor, because the record is explicit that the page always writes a real name
it read rather than the parser's ``auto`` or a description-based selector.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .. import paths
from ..services import config_store, hypr, runner
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "display"

RECORD = "monitors.json"
SETTING = "display.monitors"

#: The mode shapes the parser accepts, from ``Parser.cpp:112-145`` as the record cites
#: it: a ``WxH`` pair, with an optional ``@RR.RRHz`` that ``hyprctl -j monitors`` also
#: prints -- so a mode copied out of the read half of the record is a mode the write
#: half accepts.
_MODE_SHAPE = re.compile(r"^\d+x\d+(@\d+(\.\d+)?Hz)?$", re.IGNORECASE)
_POSITION_SHAPE = re.compile(r"^-?\d+x-?\d+$")
_SCALE_MINIMUM = 0.25


# --------------------------------------------------------------------- readers


def record() -> Dict[str, Any]:
    try:
        return json.loads(paths.design_file(RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_fields() -> List[Dict[str, Any]]:
    """The record's field entries, in the record's own order."""
    fields = (record().get("write") or {}).get("fields") or []
    return [item for item in fields if isinstance(item, dict)]


def field(name: str) -> Dict[str, Any]:
    for item in write_fields():
        if item.get("name") == name:
            return item
    return {}


def written_fields() -> List[str]:
    """The fields this project writes, in the record's order."""
    return [str(item["name"]) for item in write_fields()
            if item.get("written_by_this_project") is not False]


def refused_fields() -> List[str]:
    """The fields the record marks as not written by this project."""
    return [str(item["name"]) for item in write_fields()
            if item.get("written_by_this_project") is False]


def refusals() -> List[Dict[str, str]]:
    """``refused_by_this_project``: the field list and the reason, as recorded."""
    found = record().get("refused_by_this_project") or []
    return [item for item in found if isinstance(item, dict)]


def _slug(text: str) -> str:
    """An identifier-safe version of a field name, for a generated reader."""
    return "".join(character if character.isalnum() else "_" for character in str(text).lower())


def refusal_reason(name: str) -> str:
    """The recorded reason the group this field belongs to is not written."""
    for entry in refusals():
        fields = str(entry.get("field") or "")
        parts = [part.strip() for part in fields.replace(" and ", ",").split(",")]
        if name in parts or any(part.startswith(name) for part in parts):
            return str(entry.get("why") or "")
    return "recorded, and not written by this project"


def _refusal_reader(name: str) -> Callable[[], str]:
    """Build the reader one refused field's row shows: what the record says it is."""

    def read() -> str:
        spec = field(name)
        bits = [str(spec.get("type") or "value")]
        if "default" in spec:
            bits.append(f"default {spec['default']}")
        if "minimum" in spec and "maximum" in spec:
            bits.append(f"{spec['minimum']} to {spec['maximum']}")
        note = str(spec.get("note") or "")
        if note:
            bits.append(note)
        return "; ".join(bits)

    read.__name__ = f"refused_{_slug(name)}"
    read.__doc__ = f"What ``{name}`` is, from the record that refuses to write it."
    return read


def refusal_rows() -> List[Row]:
    """One row per field the record refuses, with the reason for its group.

    A row per field rather than a row per refusal, because the refusals are grouped --
    one of them covers fourteen colour and HDR fields at once -- and a person looking
    for ``icc`` should find ``icc``. The reason is the record's own sentence, repeated
    on each row of its group rather than summarised, so no row depends on another row
    being expanded to make sense.
    """
    rows: List[Row] = []
    for name in refused_fields():
        rows.append(Row(
            "state", name, source=f"display.refused_{_slug(name)}",
            icon="dialog-warning-symbolic", subtitle=refusal_reason(name),
            keywords=(name, "refused", "not written", "monitor",
                      str(field(name).get("type") or ""))))
    return rows


for _name in refused_fields():
    globals()[f"refused_{_slug(_name)}"] = _refusal_reader(_name)
del _name


def entries() -> List[Dict[str, Any]]:
    """The monitor rules in the settings document."""
    try:
        document = config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return []
    found = (document.get("display") or {}).get("monitors")
    return [item for item in found if isinstance(item, dict)] if isinstance(found, list) else []


def live_monitors() -> List[Dict[str, Any]]:
    """What the compositor reports for its enabled outputs, or an empty list."""
    if not hypr.in_session():
        return []
    found, verdict = hypr.enabled_monitors()
    return list(found) if verdict == runner.OK and found else []


def output_names() -> List[str]:
    """Every output name this page has read back, from the compositor and the settings."""
    names = [str(item.get("name") or item.get("id") or "") for item in live_monitors()]
    names += [str(item.get("output") or "") for item in entries()]
    return [name for name in dict.fromkeys(names) if name]


def modes_for(output: str) -> List[str]:
    """The DRM mode lines the compositor reports for one output.

    The read half of the record says the compositor prints modes as ``<w>x<h>@<hz>Hz``,
    which is a spelling the write half accepts, so a mode offered here is a mode that
    can be written back without anybody translating it.
    """
    for item in live_monitors():
        if str(item.get("name") or "") == output:
            found = item.get("availableModes") or item.get("available_modes") or []
            return [str(mode) for mode in found] if isinstance(found, list) else []
    return []


def monitor_rows() -> List[Row]:
    """One read-only row per output the compositor reports, right now."""
    found = live_monitors()
    if not found:
        return [Row("state", "No output could be read", icon="dialog-warning-symbolic",
                    value=hypr.available(),
                    subtitle="Outside a session there is nothing to read back, so the "
                             "rows below are the rules in settings.json and nothing "
                             "else",
                    keywords=("monitors", "hyprctl", "session", "unavailable"))]
    rows: List[Row] = []
    for item in found:
        name = str(item.get("name") or item.get("id") or "an output")
        mode = str(item.get("mode") or "")
        width = item.get("width")
        height = item.get("height")
        refresh = item.get("refreshRate") or item.get("refresh_rate")
        scale = item.get("scale")
        described = f"{width}×{height}" if width and height else mode
        if refresh:
            described += f" at {float(refresh):.2f} Hz"
        if scale:
            described += f", scale {scale}"
        rows.append(Row(
            "state", name, value=described, icon="preferences-desktop-display-symbolic",
            subtitle=str(item.get("description") or item.get("make") or
                         "the compositor's own read of this output"),
            keywords=(name, "monitor", "output", "mode", "scale", described)))
    return rows


def rule_rows() -> List[Row]:
    """The six writable fields, once per rule already in settings.json.

    Indexed rows rather than ``*`` rows, because a change has to name the entry it
    writes and ``display.monitors.*`` is how a plan describes the *shape* of an entry,
    not how a change names one: :func:`iarch_settings.services.control.change_for`
    refuses the star for exactly that reason.
    """
    found = entries()
    if not found:
        return [Row("state", "No rule yet", icon="dialog-information-symbolic",
                    value="the shipped file is the identity rule",
                    subtitle="With no entry in settings.json the generated file is the "
                             "identity rule -- output \"\", mode preferred, position "
                             "auto, scale 1 -- which changes nothing about any output",
                    keywords=("monitors", "identity", "default", "empty"))]
    rows: List[Row] = []
    for index, entry in enumerate(found):
        name = str(entry.get("output") or f"entry {index + 1}")
        rows.append(Row(
            "entry", f"{name} — output", setting=f"{SETTING}.{index}.output",
            icon="preferences-desktop-display-symbolic",
            validator="display.output_is_valid", placeholder="DP-1",
            subtitle="The name the compositor reports for this output; the parser also "
                     "takes auto and a description, and this page writes neither",
            keywords=(name, "output", "monitor", "name", "connector")))
        rows.append(Row(
            "entry", f"{name} — mode", setting=f"{SETTING}.{index}.mode",
            icon="preferences-desktop-display-symbolic",
            validator="display.mode_is_valid", placeholder="preferred",
            subtitle=accepted_sentence("mode"),
            keywords=(name, "mode", "resolution", "refresh", "hz")))
        rows.append(Row(
            "entry", f"{name} — position", setting=f"{SETTING}.{index}.position",
            icon="preferences-desktop-display-symbolic",
            validator="display.position_is_valid", placeholder="auto",
            subtitle=accepted_sentence("position"),
            keywords=(name, "position", "offset", "auto", "layout")))
        rows.append(Row(
            "entry", f"{name} — scale", setting=f"{SETTING}.{index}.scale",
            icon="preferences-desktop-display-symbolic",
            validator="display.scale_is_valid", placeholder="auto",
            subtitle=accepted_sentence("scale"),
            keywords=(name, "scale", "dpi", "fractional", "string")))
        rows.append(Row(
            "spin", f"{name} — transform", setting=f"{SETTING}.{index}.transform",
            minimum=float(field("transform").get("minimum", 0)),
            maximum=float(field("transform").get("maximum", 7)), step=1.0,
            icon="preferences-desktop-display-symbolic",
            subtitle="The wl_output_transform enumeration: 0 is normal, then the three "
                     "rotations and the four flipped forms",
            keywords=(name, "transform", "rotate", "flip", "portrait")))
        rows.append(Row(
            "switch", f"{name} — disabled", setting=f"{SETTING}.{index}.disabled",
            icon="view-conceal-symbolic",
            sensitive_when="display.can_disable",
            subtitle="Switches the output off. It cannot be switched off when it is the "
                     "only enabled one: a monitor that is off cannot show the dialog "
                     "that offers to switch it back on",
            keywords=(name, "disabled", "off", "output")))
    return rows


def accepted_sentence(name: str) -> str:
    """The record's own list of accepted spellings for one field, as one sentence."""
    spec = field(name)
    accepted = spec.get("accepted") or []
    if not accepted:
        return str(spec.get("note") or "")
    text = "; ".join(str(item) for item in accepted)
    refused = str(spec.get("refused") or "")
    return f"accepted: {text}" + (f". Refused: {refused}" if refused else "")


def entry_count_text() -> str:
    """How many rules are in the settings document, for the header."""
    found = entries()
    if not found:
        return "no monitor rule: the generated file is the identity rule"
    return (f"{len(found)} rule{'s' if len(found) != 1 else ''}: "
            + ", ".join(str(item.get("output") or "?") for item in found))


def outputs_text() -> Optional[str]:
    """The output names the compositor reports, as one line."""
    names = [str(item.get("name") or "") for item in live_monitors()]
    return ", ".join(name for name in names if name) or None


def session_text() -> str:
    """Whether the compositor can be asked at all."""
    return hypr.available()


def config_errors_text() -> Optional[str]:
    """What ``hyprctl configerrors`` says, which is the check the record requires.

    The record's own verify step is that this is empty after a reload and that the
    monitor still appears in the read, so the row shows the thing that has to be empty
    rather than a summary of whether it was.
    """
    if not hypr.in_session():
        return None
    found, verdict = hypr.config_errors()
    if verdict != runner.OK:
        return None
    return "; ".join(str(line) for line in found) if found else "empty"


def can_disable() -> bool:
    """Whether an output may be switched off at all right now.

    True when more than one output is enabled, so the switch is insensitive on a
    single-monitor machine rather than offering a change the page would then refuse:
    the record puts this in the row, and an insensitive row with its subtitle is a
    refusal a person can read before trying it.
    """
    found = live_monitors()
    if not found:
        # Nothing could be read, so nothing can be counted: leave the switch usable and
        # let the change's own validation decide, rather than refusing on a machine
        # that is simply outside a session.
        return len(entries()) > 1
    enabled = [item for item in found if not item.get("disabled")]
    return len(enabled) > 1


# ------------------------------------------------------------------ validators


def output_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether an output name is one this page can write."""
    text = str(value or "").strip()
    if not text:
        return False, "a rule needs an output name: without one it matches every monitor"
    names = output_names()
    if names and text not in names:
        return False, (f"{text!r} is not an output this session reports; the names read "
                       f"back are {', '.join(names)}")
    return True, ""


def mode_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether a mode spelling is one the compositor's parser accepts."""
    text = str(value or "").strip()
    if not text:
        return True, ""
    lowered = text.lower()
    for prefix in ("pref", "highrr"):
        if lowered.startswith(prefix):
            return True, ""
    if lowered in ("highres", "maxwidth"):
        return True, ""
    if _MODE_SHAPE.match(text):
        return True, ""
    return False, ("a mode is preferred, highres, highrr, maxwidth, WxH or WxH@RR.RRHz; "
                   "anything else is refused with invalid resolution and the rule keeps "
                   "the preferred mode")


def position_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether a position spelling is one of the eight autos, or an ``XxY`` offset."""
    text = str(value or "").strip()
    if not text:
        return True, ""
    accepted = [str(item) for item in field("position").get("accepted") or []]
    if text in accepted:
        return True, ""
    if _POSITION_SHAPE.match(text):
        return True, ""
    return False, ("a position is one of " + ", ".join(
        item for item in accepted if item != "XxY") + ", or an XxY offset")


def scale_is_valid(value: Any) -> Tuple[bool, str]:
    """Whether a scale is ``auto`` or a number of at least 0.25.

    The field's type is a *string*, so the value is kept as text and checked as a
    number: the parser refuses a non-numeric one with ``invalid scale`` and silently
    resets a number below 0.25 to 1, and both are answers this row can prevent.
    """
    text = str(value or "").strip()
    if not text or text.lower().startswith("auto"):
        return True, ""
    try:
        number = float(text)
    except ValueError:
        return False, (f"{text!r} is not a number, and scale is a string field: the "
                       f"parser refuses a non-numeric value with invalid scale")
    if number < _SCALE_MINIMUM:
        return False, (f"{number:g} is below {_SCALE_MINIMUM:g}, which the parser does "
                       f"not refuse so much as reset to 1 -- so it is not written")
    return True, ""


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Display page, as data."""
    spec = registry_page(PAGE_ID)
    safety = record().get("safety") or {}
    revert = safety.get("revert_seconds", 15)

    now = Group(
        "What the compositor reports",
        Row("expander", "Outputs, right now", rows_source="display.monitor_rows",
            icon="preferences-desktop-display-symbolic",
            subtitle="Read back with hyprctl rather than remembered, so a name offered "
                     "below is a name this session actually has",
            keywords=("monitors", "outputs", "hyprctl", "read", "modes")),
        Row("state", "Output names", icon="preferences-desktop-display-symbolic",
            source="display.outputs_text",
            subtitle="The names a rule may use; the parser also takes auto and a "
                     "description, and this page writes neither",
            keywords=("outputs", "names", "dp-1", "hdmi", "edp")),
        Row("state", "Can the compositor be asked?", icon="utilities-terminal-symbolic",
            source="display.session_text", keywords=("hyprctl", "session", "available")),
        Row("state", "Config errors", icon="dialog-warning-symbolic",
            source="display.config_errors_text",
            subtitle="Has to be empty after a reload, and the monitor has to still "
                     "appear in the read: those two are the record's own verify step",
            keywords=("configerrors", "verify", "reload", "errors")),
        description="The read half of the record: what hyprctl -j monitors answers, "
                    "including the mode lines a rule may quote back.",
        style_classes=("iarch-glass-card",),
    )

    rules = Group(
        "The rules this project writes",
        Row("expander", "One row per rule", rows_source="display.rule_rows",
            icon="preferences-desktop-display-symbolic",
            subtitle="Six fields each: output, mode, position, scale, transform and "
                     "disabled -- the six the record marks as written by this project",
            keywords=("monitors", "rules", "output", "mode", "position", "scale",
                      "transform", "disabled")),
        Row("state", "In settings.json", icon="document-save-symbolic",
            source="display.entry_count_text",
            subtitle="Rendered into .config/hypr/monitors.lua by "
                     "iarch/cli/gen_monitors_lua.py",
            keywords=("display.monitors", "settings", "monitors.lua", "generated")),
        description="Written into the compositor's own config-manager function, "
                    "hl.monitor, and an unknown field is a config error rather than "
                    "something ignored.",
    )

    refused = Group(
        "Recorded, and deliberately not written",
        Row("expander", "Every field the record refuses",
            rows=tuple(refusal_rows()), icon="dialog-warning-symbolic",
            subtitle="Colour management, HDR, luminance, VRR, mirroring and the "
                     "reserved area: each can make a display unreadable, or fight the "
                     "shell for the same edge of the screen",
            keywords=("refused", "reserved", "mirror", "hdr", "icc", "vrr", "luminance",
                      "bitdepth")),
        Row("state", "Fields this page writes", icon="object-select-symbolic",
            source="display.written_text",
            subtitle="Everything else in the record is listed above with the reason it "
                     "is not offered",
            keywords=("fields", "written", "six")),
        description="A field the record carries and this project does not write is "
                    "still a field somebody will look for, so each one is here with "
                    "the reason rather than simply absent.",
    )

    return PagePlan(
        PAGE_ID, spec.label, now, rules, refused,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner(f"A resolution or scale change is applied first and confirmed "
                   f"after, with {revert} seconds to keep it: a dialog drawn over a "
                   f"session that is already running the new mode is a dialog that may "
                   f"not be readable, so the change lands and then asks.",
                   kind="warning", icon="dialog-warning-symbolic"),
            Banner("If configerrors is not empty after the reload, or the monitor is no "
                   "longer in the read, the previous payload is restored from the "
                   "backup the pipeline took before writing.",
                   kind="info", icon="document-save-symbolic"),
        ),
        header_actions=(
            Row("state", "Monitor rules", icon="preferences-desktop-display-symbolic",
                source="display.entry_count_text", keywords=("monitors", "rules")),
        ),
    )


def written_text() -> str:
    """The six written fields as one line, for the refusal group's own summary."""
    names = written_fields()
    return (f"{len(names)} of {len(write_fields())} recorded fields are written: "
            + ", ".join(names))
