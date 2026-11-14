# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Sound, Network & Bluetooth page: the shell's keys, and no second surface.

Everything here belongs to the shell. Its audio configuration is seven keys in its own
``config.toml``, its network and bluetooth state is two verbs, and its volume surface is a
panel it already draws -- so this page reads and writes through the shell's IPC and stores
no copy, which is what ``data/settings.default.json``'s own note promises: sections another
program owns are deliberately absent from this project's settings file.

The rows are generated from ``data/design/noctalia.json`` by
:mod:`iarch_settings.pages.shellkeys`, the same generator the Bar, Dock & Panels and the
Power & Idle pages use, so the rule that decides what a declared type becomes -- a boolean
is a switch, a key with an enum is a dropdown, a float with a range is a scale -- is one
rule in one place rather than three pages' worth of opinions.

Two things this page deliberately does not draw:

* **A volume slider.** ``volume-osd`` shows the shell's own volume surface, and the record
  says that is what this page uses it for: "instead of drawing a second one". Two volume
  surfaces on one desktop are two places to look and one of them is stale, so the row here
  opens the shell's and the seven keys below configure the sounds themselves.
* **The notification keys.** The shell declares twenty-four of them, and notification
  behaviour -- geometry, urgency, dismissal, history -- is Part 5 of this project. The row
  that says so offers the shell's own window rather than pretending the keys are absent
  because nobody thought of them.

The network and bluetooth rows read their state from ``wifi-status`` and
``bluetooth-status`` rather than from a remembered value, and each toggle is one of the
zero-argument verbs :data:`iarch_settings.services.noctalia.PAGE_VERBS` exists for. A panel
is opened at a context only where the record says this project sends one -- audio and
network -- because ``panel-open`` takes any id and a context the shell does not have is a
panel that does not open.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..services import noctalia, runner
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row
from . import shellkeys

PAGE_ID = "sound"

CONTAINER = "audio"

#: The shell's audio keys in two groups: the ones that decide whether a sound plays at all,
#: and the two that decide what it sounds like. Prefixes, so a key the record adds next
#: release lands in the right group instead of in a catch-all nobody reads.
BUCKETS = (
    ("Which sounds play", ("enable_",)),
    ("How they sound", ("sound_",)),
)

ICONS = {
    "Which sounds play": "audio-volume-high-symbolic",
    "How they sound": "audio-volume-high-symbolic",
}

_ROWS, _NAMES = shellkeys.build(CONTAINER, PAGE_ID, buckets=BUCKETS, icons=ICONS)

# The generator's readers, setters and validators become this module's attributes, because
# a plan resolves a row's names against the modules it is allowed to resolve into and a
# page's rows have to name functions that exist in a module the resolver can reach.
globals().update(_NAMES)


# --------------------------------------------------------------------- readers


def wifi_text() -> Optional[str]:
    """What ``wifi-status`` answers, or ``None`` when nothing could be asked."""
    value, verdict = noctalia.wifi_status()
    return str(value) if verdict == runner.OK and value is not None else None


def bluetooth_text() -> Optional[str]:
    """What ``bluetooth-status`` answers, or ``None`` when nothing could be asked."""
    value, verdict = noctalia.bluetooth_status()
    return str(value) if verdict == runner.OK and value is not None else None


def shell_text() -> str:
    """Whether the shell's binary is on PATH, in the service's own sentence."""
    return noctalia.available()


def no_slider_text() -> str:
    """Why there is no volume slider on this page."""
    return ("the shell draws its own volume surface; this page opens it rather than "
            "drawing a second one that would be stale the moment the keys changed it")


#: The shell's notification keys, named here and written by Part 5.
#:
#: A key no page mentions is unreachable, which is what Part 4's acceptance forbids. But
#: notifications are Part 5's subject, and drawing twenty-four switches on the Sound page
#: would be a page that owns keys it has not verified. So they are named with the shape the
#: record gives each one, and the row says which part writes them.
NOTIFICATION_WHY = (
    "notifications are Part 5: the keys are named here so that nothing the shell declares is "
    "unreachable, and none of them is a control on this page because this page has not "
    "verified what a change to one does")

_NOTIFICATION_ROWS, _NOTIFICATION_NAMES = shellkeys.named_rows(
    "notification", PAGE_ID, why=NOTIFICATION_WHY)

#: ``notification.filter`` is a section of its own in the record rather than a table under
#: ``notification``, so it needs its own pass: a container prefix is how the record is
#: organised, and a page that named only the top-level one would leave twelve keys
#: unreachable.
_FILTER_ROWS, _FILTER_NAMES = shellkeys.named_rows(
    "notification.filter", PAGE_ID, why=NOTIFICATION_WHY)
globals().update(_NOTIFICATION_NAMES)
globals().update(_FILTER_NAMES)


def notification_why() -> str:
    """Why the notification keys are named here and written by another part."""
    return NOTIFICATION_WHY


def notification_keys_text() -> str:
    """How many notification keys the shell declares, and whose they are."""
    try:
        table = noctalia.key_specs()
    except noctalia.NoctaliaError:
        return "the shell's notification keys are its own"
    count = len([path for path in table if path.startswith("notification.")])
    return (f"the shell declares {count} notification keys, and notification behaviour is "
            f"Part 5 of this project: geometry, urgency, dismissal and history are not "
            f"sound settings and this page does not pretend to own them")


def key_count_text() -> str:
    """How many of the shell's audio keys this page writes."""
    return (f"{len(shellkeys.keys_of(CONTAINER))} audio keys, read and written through the "
            f"shell's IPC and stored nowhere else")


# ------------------------------------------------------------------- actions


def open_audio_panel() -> runner.Outcome:
    """Open the shell's control centre at its audio section.

    A page-local zero-argument wrapper, because :func:`noctalia.panel` takes the panel id
    and the context and a button's action takes nothing: the id and the context are this
    page's decision, not the person's.
    """
    return noctalia.panel(noctalia.PANEL_CONTROL_CENTER, "audio")


def open_network_panel() -> runner.Outcome:
    """Open the shell's control centre at its network section."""
    return noctalia.panel(noctalia.PANEL_CONTROL_CENTER, "network")


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Sound, Network & Bluetooth page, as data."""
    spec = registry_page(PAGE_ID)

    groups: List[Group] = []
    for title, rows in _ROWS.items():
        groups.append(Group(
            title, *rows,
            description="Every key below is the shell's own, read out of the record of its "
                        "schema: the range or the choice list in each subtitle is the one "
                        "the shell enforces."
            if not groups else "",
            style_classes=("iarch-glass-card",) if not groups else (),
        ))

    groups.append(Group(
        "Volume",
        Row("button", "Open the shell's volume surface", action="noctalia.volume_osd",
            icon="audio-volume-high-symbolic",
            subtitle="volume-osd shows the shell's own volume display without changing the "
                     "volume, which is the point: one surface, and it is the shell's",
            keywords=("volume", "osd", "mixer", "slider", "loudness")),
        Row("state", "Why there is no slider here", icon="dialog-information-symbolic",
            source="sound.no_slider_text",
            subtitle="Two volume surfaces on one desktop are two places to look and one of "
                     "them is stale",
            keywords=("volume", "slider", "second surface", "why")),
        Row("button", "Open the audio panel", action="sound.open_audio_panel",
            icon="audio-volume-high-symbolic",
            subtitle="panel-open control-center audio: the shell's own panel at the section "
                     "the record says this project sends",
            keywords=("panel", "control centre", "audio", "open")),
        description="The seven keys above configure which sounds play and how loud they are; "
                    "the volume itself is the shell's surface and stays that way.",
    ))

    groups.append(Group(
        "Network and Bluetooth",
        Row("state", "Wireless", icon="network-wireless-symbolic", source="sound.wifi_text",
            subtitle="Read from wifi-status rather than remembered, so the row cannot show "
                     "a state the shell has since changed",
            keywords=("wifi", "wireless", "network", "status")),
        Row("button", "Turn wireless on or off", action="noctalia.toggle_wifi",
            icon="network-wireless-symbolic",
            subtitle="One verb, and the row above reads the answer back",
            keywords=("wifi", "toggle", "wireless", "on", "off")),
        Row("state", "Bluetooth", icon="bluetooth-symbolic", source="sound.bluetooth_text",
            subtitle="Read from bluetooth-status",
            keywords=("bluetooth", "status", "device", "pairing")),
        Row("button", "Turn Bluetooth on or off", action="noctalia.toggle_bluetooth",
            icon="bluetooth-symbolic", keywords=("bluetooth", "toggle", "on", "off")),
        Row("button", "Toggle networking altogether", action="noctalia.toggle_network",
            icon="network-wireless-symbolic",
            subtitle="The shell's own networking switch, which is neither of the two above",
            keywords=("network", "airplane", "toggle", "offline")),
        Row("button", "Open the network panel", action="sound.open_network_panel",
            icon="network-wireless-symbolic",
            subtitle="panel-open control-center network: choosing a network is the shell's "
                     "panel's job, not a list this page would have to keep fresh",
            keywords=("panel", "control centre", "network", "open")),
        Row("state", "Can the shell be asked?", icon="utilities-terminal-symbolic",
            source="sound.shell_text", keywords=("ipc", "noctalia", "available")),
        description="Three toggles and two states, all of them the shell's: this project "
                    "keeps no copy of a network state it could not keep true.",
    ))

    groups.append(Group(
        "Not elsewhere",
        Row("state", "The notification keys", icon="dialog-information-symbolic",
            source="sound.notification_keys_text",
            subtitle="Not hidden, and not this page's: the sentence is the row",
            keywords=("notification", "part 5", "shell", "keys")),
        Row("expander", "The filter rules, named too", rows=tuple(_FILTER_ROWS),
            icon="view-conceal-symbolic",
            subtitle="notification.filter is its own section in the record, so it needs its "
                     "own pass: a page that named only the top level would leave twelve keys "
                     "unreachable",
            keywords=("notification", "filter", "rules", "named", "part 5")),
        Row("expander", "Every one of them, named", rows=tuple(_NOTIFICATION_ROWS),
            icon="view-conceal-symbolic",
            subtitle="What the record says each key is, so nothing the shell declares is a "
                     "value only a text editor can change",
            keywords=("notification", "keys", "named", "part 5", "filter")),
        Row("state", "Why they are not controls here", icon="dialog-information-symbolic",
            source="sound.notification_why", keywords=("notification", "why", "part 5")),
        Row("state", "What this page writes", icon="audio-volume-high-symbolic",
            source="sound.key_count_text", keywords=("audio", "keys", "count", "ipc")),
        Row("button", "Open this in the shell's own window",
            action="noctalia.open_shell_settings", icon="go-next-symbolic",
            subtitle="The escape hatch the record describes, for a key this project has not "
                     "verified a range for",
            keywords=("shell", "settings", "open", "escape hatch")),
        description="A key the shell owns and this project has not recorded is not a key "
                    "this page guesses at.",
    ))

    return PagePlan(
        PAGE_ID, spec.label, *groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("Every write here goes to the shell over its IPC and is followed by a "
                   "config reload; nothing on this page is stored in settings.json.",
                   kind="info", icon="utilities-terminal-symbolic"),
        ),
        header_actions=(
            Row("state", "Audio keys", icon="audio-volume-high-symbolic",
                source="sound.key_count_text", keywords=("audio", "keys")),
        ),
    )
