# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Animations page: how the desktop moves.

Motion is its own section of the settings file and its own page, because a theme is a
look and this is how that look moves: a person can be on frosted glass and bouncy
motion, or on the Performance intensity -- which pairs with the ``off`` preset --
without either choice overwriting the other.

Everything here is written by ``iarch-anim``, not by this application. The tool owns
``animation.preset``, ``animation.speed``, ``animation.reduce_motion`` and
``animation.event_overrides``, it renders the compositor's animation tree from them,
and it writes the section back itself -- so the rows name settings and the change
carries no settings write of its own
(:data:`iarch_settings.services.control.ROUTES`). The one thing this project writes is
the derived ``effects.animations``, which follows the preset.

Three facts from the compositor's own source shape the page, and each is stated where
a person can read it rather than only in a record:

* **Above 1 is faster.** The multiplier divides every duration, so 1.5 is not "more
  animation" and the row says which way it goes.
* **``duration_ms = 100 * speed``.** The animation finishes when
  ``(elapsed_ms / 100) / speed`` reaches 1, which is why the speed row can say what a
  number means in milliseconds instead of leaving it abstract.
* **Reduce motion is not "no animation".** It renders the minimal preset with every
  duration capped, and the compositor's master switch stays on -- so the coarse
  ``effects.animations`` switch stays true, and the row says so rather than letting a
  person conclude that animation has been removed from the session.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import paths
from ..services import config_store, themes
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "animations"

RECORD = "animations.json"
PRESET_DIR = ("data", "design", "animations")


# --------------------------------------------------------------------- readers


def document() -> Dict[str, Any]:
    try:
        return config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return {}


def animation() -> Dict[str, Any]:
    block = document().get("animation")
    return dict(block) if isinstance(block, dict) else {}


def record() -> Dict[str, Any]:
    try:
        return json.loads(paths.design_file(RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def preset_record(preset: str) -> Dict[str, Any]:
    """One preset's own file, which is where its events and durations live."""
    path = paths.repo_root().joinpath(*PRESET_DIR) / f"{preset}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def preset_events(preset: str) -> List[str]:
    events = preset_record(preset).get("events")
    return list(events) if isinstance(events, dict) else []


def every_event() -> List[str]:
    """Every event any preset declares, in a stable order.

    The union rather than the active preset's own list, because the readers below are
    module attributes and a module attribute cannot depend on which preset happens to
    be active when the page is drawn. A row is only *offered* for an event the active
    preset declares; the readers simply exist for all of them.
    """
    found: List[str] = []
    for preset in themes.motion_presets():
        for event in preset_events(preset):
            if event not in found:
                found.append(event)
    return sorted(found)


def preset_choices() -> List[Tuple[str, str]]:
    """The presets that have a file, as ``(id, label)`` pairs."""
    return [(name, str(preset_record(name).get("label") or name.replace("_", " ").title()))
            for name in themes.motion_presets()]


def preset_description() -> Optional[str]:
    """What the active preset is for, in its own words."""
    preset = str(animation().get("preset") or "")
    return str(preset_record(preset).get("description") or "") or None


def preset_label() -> Optional[str]:
    preset = str(animation().get("preset") or "")
    return str(preset_record(preset).get("label") or preset) or None


def speed_formula_text() -> str:
    """``duration_ms = 100 * speed``, with the source that says so."""
    formula = record().get("speed_formula") or {}
    return str(formula.get("equation") or "duration_ms = 100 * speed")


def duration_text() -> Optional[str]:
    """What the current multiplier means in milliseconds, for the speed row."""
    speed = animation().get("speed")
    if not speed:
        return None
    return f"a unit of animation lasts {100 * float(speed):.0f} ms at {float(speed):g}×"


def reduce_motion_text() -> str:
    """What reduce motion resolves to, from the tokens rather than from an adjective."""
    tokens = themes.tokens()
    block = ((tokens.get("motion") or {}).get("animation") or {}).get("reduce_motion") or {}
    preset = block.get("preset", "minimal")
    cap = block.get("max_duration_ms", 90)
    return (f"renders the {preset} preset with every duration capped at {cap} ms; the "
            f"compositor's own animation switch stays on, so this reduces motion "
            f"rather than removing it")


def master_switch_text() -> str:
    """The compositor's kill-switch, which this page does not offer."""
    block = record().get("master_switch") or {}
    leaf = block.get("leaf", "animations:enabled")
    return (f"{leaf} is the compositor's own kill-switch, and the Performance "
            f"intensity is what sets it false -- not this page")


def state_text() -> Optional[str]:
    """What ``iarch-anim current`` says, first line.

    A read that runs the tool rather than the settings file, because the question this
    row answers is what the compositor was actually told. No tool and no session gives
    ``None``, and the row then says the state could not be asked.
    """
    outcome = themes.run_anim("current")
    if outcome.verdict == "unverified":
        return None
    lines = [line.strip() for line in (outcome.stdout or outcome.stderr).splitlines()
             if line.strip()]
    return lines[0] if lines else None


def overrides_in_force() -> str:
    """How many per-event overrides are on top of the preset."""
    overrides = animation().get("event_overrides") or {}
    count = len(overrides) if isinstance(overrides, dict) else 0
    if not count:
        return "no per-event overrides: every event follows the preset"
    return f"{count} override{'s' if count != 1 else ''} on top of the preset"


def _event_reader(event: str) -> Callable[[], Optional[bool]]:
    """Build the reader one event's switch shows: the override, else the preset."""

    def read() -> Optional[bool]:
        overrides = animation().get("event_overrides")
        if isinstance(overrides, dict) and event in overrides:
            return bool(overrides[event])
        declared = (preset_record(str(animation().get("preset") or "")).get("events") or {})
        entry = declared.get(event)
        return bool(entry.get("enabled")) if isinstance(entry, dict) else None

    read.__name__ = f"effective_{event}"
    read.__doc__ = f"Whether ``{event}`` animates: the override, else the preset's own."
    return read


# One reader per event any preset declares. Built in a loop because the set comes from
# the preset files and a hand-written list of twenty names would be a list that drifts
# the first time a preset adds an event; each is still a real module attribute, which
# is what a plan row resolves.
for _event in every_event():
    globals()[f"effective_{_event}"] = _event_reader(_event)
del _event

EVENT_READERS: Dict[str, Callable[[], Optional[bool]]] = {
    event: globals()[f"effective_{event}"] for event in every_event()
}


def event_rows() -> List[Row]:
    """One switch per event the *active* preset declares.

    An event the preset does not declare is not offered: ``iarch-anim toggle`` refuses
    one, and a switch that cannot be used is worse than a switch that is not there.
    """
    preset = str(animation().get("preset") or "")
    rows: List[Row] = []
    for event in preset_events(preset):
        declared = (preset_record(preset).get("events") or {}).get(event) or {}
        rows.append(Row(
            "switch", event,
            setting=f"animation.event_overrides.{event}",
            source=f"animations.effective_{event}",
            icon="media-playback-start-symbolic",
            subtitle=(f"the {preset} preset animates this over "
                      f"{declared.get('duration_ms', '?')} ms with its "
                      f"{declared.get('curve', '?')} curve"
                      if declared else "the preset declares this event"),
            keywords=(event, "animation", "event", "override", "motion")))
    if not rows:
        rows.append(Row(
            "state", "No events to override", source="animations.preset_label",
            icon="dialog-information-symbolic",
            subtitle="The active preset declares no events, or its file could not be "
                     "read, so there is nothing to turn on or off on top of it",
            keywords=("events", "overrides", "preset")))
    return rows


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Animations page, as data."""
    spec = registry_page(PAGE_ID)
    tokens = themes.tokens()
    multiplier = (((tokens.get("motion") or {}).get("animation") or {})
                  .get("speed_multiplier") or {})

    preset = Group(
        "Motion",
        Row("combo", "Preset", setting="animation.preset",
            choices_source="animations.preset_choices",
            icon="media-playback-start-symbolic",
            subtitle="Every duration, curve and style at once; the one named off "
                     "removes animation from the session",
            keywords=("motion", "animation", "preset", "smooth", "snappy", "bouncy",
                      "minimal", "off")),
        Row("state", "What it means", icon="dialog-information-symbolic",
            source="animations.preset_description", keywords=("preset", "description")),
        Row("scale", "Speed", setting="animation.speed",
            minimum=float(multiplier.get("min", 0.5)),
            maximum=float(multiplier.get("max", 2.0)), step=0.05, unit="×",
            icon="media-playback-start-symbolic",
            subtitle="Above 1 is FASTER, because the multiplier divides every "
                     "duration: " + speed_formula_text(),
            keywords=("speed", "multiplier", "duration", "fast", "slow", "rate")),
        Row("state", "What the multiplier does", icon="dialog-information-symbolic",
            source="animations.duration_text", keywords=("duration", "milliseconds", "speed")),
        Row("switch", "Reduce motion", setting="animation.reduce_motion",
            # The icon theme record has no accessibility icon in it, and a name the
            # record does not verify is a name the renderer would draw as a missing
            # image: data/design/adwaita.json is the list, and this page stays inside
            # it rather than reaching for the obvious name.
            icon="media-playback-start-symbolic",
            subtitle="Fades only, every duration capped. It reduces motion; it does "
                     "not remove it",
            keywords=("reduce motion", "accessibility", "vestibular", "fades", "calm")),
        Row("state", "What reduce motion resolves to", icon="dialog-information-symbolic",
            source="animations.reduce_motion_text", keywords=("reduce motion", "cap", "minimal")),
        description="The preset decides every duration; the speed scales them all; "
                    "reduce motion replaces the preset's motion with fades and caps "
                    "them.",
        style_classes=("iarch-glass-card",),
    )

    events = Group(
        "Per-event overrides",
        Row("expander", "One event at a time", rows_source="animations.event_rows",
            icon="media-playback-start-symbolic",
            subtitle="On top of whatever the preset declares, so a preset can stay and "
                     "one animation can go",
            keywords=("event", "override", "windows", "workspaces", "fade", "border",
                      "layers")),
        Row("state", "Overrides in force", icon="edit-clear-symbolic",
            source="animations.overrides_in_force", keywords=("override", "count")),
        description="Only the events the active preset declares are offered: the tool "
                    "refuses an override for an event the preset does not have, and a "
                    "switch that cannot be used is worse than no switch.",
    )

    session = Group(
        "What the compositor was told",
        Row("state", "Current state", icon="view-refresh-symbolic",
            source="animations.state_text",
            subtitle="iarch-anim current: the state, the resolved plan and the file it "
                     "rendered",
            keywords=("state", "current", "compositor", "iarch-anim")),
        Row("state", "The master switch", icon="dialog-warning-symbolic",
            source="animations.master_switch_text",
            subtitle="Recorded so that this page cannot appear to own it",
            keywords=("master", "animations:enabled", "kill switch", "performance")),
        description="Motion is rendered into the compositor's own animation tree and "
                    "reloaded; this is the read-back that says it arrived.",
    )

    return PagePlan(
        PAGE_ID, spec.label, preset, events, session,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card", "iarch-glass-preview"),
        banners=(
            Banner("The whole section is written by iarch-anim, not by this window: "
                   "the tool renders the compositor's animation tree and writes the "
                   "settings back itself.",
                   kind="info", icon="dialog-information-symbolic"),
        ),
        header_actions=(
            Row("state", "The motion preset in force", icon="media-playback-start-symbolic",
                source="animations.preset_label", keywords=("preset", "motion")),
        ),
    )
