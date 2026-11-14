# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Features page: the two modes, and what this project honestly cannot claim.

A mode is a named bundle of switches that already exist. That sentence is
``data/design/tokens.json``'s own note about ``modes``, and it is the reason this page has
two switches and a lot of explanation: a mode invents no leaf, no value outside a range
recorded elsewhere, and no second source of truth for anything the intensities already
decide. Game mode is one intensity change plus the animation preset that intensity is
already paired with -- the pairing lives in ``intensities.performance.motion``, not in the
mode, so it cannot drift the way two copies would. Focus mode dims every window that is not
the focused one, at the compositor's own default strength rather than a number invented
here.

Both switches are on this page and on Home, and both are the same setting written through
the same route, so they cannot disagree: ``modes.game.active`` and ``modes.focus.active``
are owned by ``iarch-gamemode`` and ``iarch-focus``, which render the change, write the
settings back themselves and read the compositor back afterwards. What a mode *adds* is the
round trip: it saves the intensity and the whole animation block first, so turning it off
puts both back.

Three things this page says plainly rather than leaving to a reader to discover:

* **No key is bound to either mode.** ``Super+H`` and the overlay behind it are Part 7, so
  until then both modes are commands you run, and this window is the only surface that
  offers them.
* **No saving has been measured.** The frame-time and latency claim is still open in
  ``docs/UNVERIFIED.md`` as MODE-01 to MODE-04, because nothing in a sandbox can measure a
  live session. A switch that says "improves performance" without a measurement behind it
  is advertising, so the row says what the mode changes and the banner says what nobody has
  measured.
* **Game mode changes the intensity and never the colour preset.** A mode that moved the
  look would be a mode that undoes a choice made on the Appearance page.

The rest of the page is the shell's: Do Not Disturb, caffeine and night light are verbs, and
the two screenshot buttons trigger the shell's own capture rather than shipping a second
one. Night light is the *schedule*, and the record notes that forcing the filter on
regardless of the clock is a different verb this page does not offer -- so offering the
schedule cannot imply it also forces. Three of the shell's own keys are here rather than on
Appearance, because the clipboard and telemetry are features and corner radii are not.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..services import noctalia, runner, themes
from . import page as registry_page
from . import shellkeys
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "features"

#: The shell's own keys that belong on this page rather than on Appearance. The two pages
#: share one container, so each names the keys it wants and neither can draw a switch the
#: other already drew.
PRIVACY_KEYS = ("clipboard_enabled", "clipboard_confirm_clear_history", "telemetry_enabled")

PRIVACY_BUCKETS = (("Privacy and the clipboard", ("clipboard", "telemetry")),)

_ROWS, _NAMES = shellkeys.build(
    "shell", PAGE_ID, only=PRIVACY_KEYS, buckets=PRIVACY_BUCKETS,
    icons={"Privacy and the clipboard": "view-conceal-symbolic"})

# The generator's readers, setters and validators become this module's attributes, because a
# plan resolves a row's names against the modules it is allowed to resolve into.
globals().update(_NAMES)


# --------------------------------------------------------------------- readers


def modes() -> Dict[str, Any]:
    """The ``modes`` block of the design tokens, which is what a mode means."""
    block = themes.tokens().get("modes")
    return dict(block) if isinstance(block, dict) else {}


def mode(name: str) -> Dict[str, Any]:
    block = modes().get(name)
    return dict(block) if isinstance(block, dict) else {}


def game_mode_text() -> str:
    """What Game mode changes, in the record's own words."""
    intensity = mode("game").get("intensity", "performance")
    return (f"one intensity change -- {intensity} -- plus the animation preset that "
            f"intensity is already paired with, which is off. It saves the intensity and "
            f"the whole animation block first, so turning it off puts both back")


def focus_mode_text() -> str:
    """What Focus mode changes, in the record's own words."""
    spec = mode("focus")
    strength = spec.get("dim_strength", 0.5)
    leaves = ", ".join(str(leaf) for leaf in spec.get("leaves") or ())
    return (f"dims every window that is not the focused one, at {strength} -- the "
            f"compositor's own default strength, not a number invented here. The two leaves "
            f"it sets are {leaves}")


def no_keybind_text() -> str:
    """Why neither mode has a shortcut."""
    return ("no key is bound to either mode: Super+H and the overlay behind it are Part 7, "
            "so until then both are commands you run and this window is the only surface "
            "that offers them")


def no_measurement_text() -> str:
    """What has not been measured, and where that is written down."""
    return ("no frame-time or latency saving has been measured on a live session: the claim "
            "is open in docs/UNVERIFIED.md as MODE-01 to MODE-04, so this page says what a "
            "mode changes and not what it buys")


def preset_untouched_text() -> str:
    """The one thing Game mode deliberately does not do."""
    return ("Game mode changes the intensity and never the colour preset: a mode that moved "
            "the look would undo a choice made on the Appearance page")


def dnd_state() -> Optional[bool]:
    """Do Not Disturb, read from the shell rather than remembered.

    ``None`` when the shell could not be asked, which is a different answer from "off" and
    is drawn as an unknown switch rather than as a switch that says off.
    """
    value, _verdict = noctalia.dnd_status()
    return value


def nightlight_text() -> str:
    """Why the row offers the schedule and not the forced filter."""
    return ("the schedule is what this row turns on and off; forcing the filter on whatever "
            "the clock says is a different verb, recorded so that offering the schedule "
            "cannot imply it also forces")


def capture_text() -> str:
    """Why the screenshot buttons are the shell's."""
    return ("both buttons trigger the shell's own capture rather than shipping a second one: "
            "two screenshot surfaces on a desktop are two sets of keys and one of them is "
            "stale")


def shell_text() -> str:
    """Whether the shell's binary is on PATH, in the service's own sentence."""
    return noctalia.available()


def feature_count_text() -> str:
    """How many switches this page has, for the header."""
    return ("2 modes written through their own tools, 3 shell verbs, and "
            f"{len(PRIVACY_KEYS)} of the shell's own keys")


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Features page, as data."""
    spec = registry_page(PAGE_ID)

    modes_group = Group(
        "The two modes",
        Row("switch", "Game mode", setting="modes.game.active",
            icon="applications-games-symbolic",
            subtitle="The Performance intensity and the animation preset paired with it; "
                     "turning it off puts both back",
            keywords=("game", "mode", "gaming", "performance", "intensity", "animation")),
        Row("state", "What it changes", icon="dialog-information-symbolic",
            source="features.game_mode_text", keywords=("game mode", "what", "round trip")),
        Row("switch", "Focus mode", setting="modes.focus.active",
            icon="view-conceal-symbolic",
            subtitle="Dims every window that is not the focused one, which is the half of "
                     "focusing the shell's own tiles cannot do",
            keywords=("focus", "mode", "dim", "concentration", "distraction")),
        Row("state", "What it changes", icon="dialog-information-symbolic",
            source="features.focus_mode_text", keywords=("focus mode", "dim", "strength")),
        Row("state", "No key is bound", icon="dialog-warning-symbolic",
            source="features.no_keybind_text",
            keywords=("keybind", "super+h", "part 7", "command", "shortcut")),
        Row("state", "Nothing has been measured", icon="dialog-warning-symbolic",
            source="features.no_measurement_text",
            subtitle="MODE-01 to MODE-04 in docs/UNVERIFIED.md",
            keywords=("measurement", "frame time", "latency", "unverified", "mode-01")),
        Row("state", "What Game mode does not touch", icon="object-select-symbolic",
            source="features.preset_untouched_text",
            keywords=("colour preset", "game mode", "intensity", "appearance")),
        description="A mode is a named bundle of switches that already exist: it invents no "
                    "leaf, no value outside a range recorded elsewhere, and no second source "
                    "of truth for anything the intensities already decide.",
        style_classes=("iarch-glass-card",),
    )

    quiet = Group(
        "Quiet, awake and captured",
        Row("switch", "Do Not Disturb", action="noctalia.set_dnd",
            source="features.dnd_state", icon="chat-message-new-symbolic",
            subtitle="Read from the shell, so the switch cannot show a state the shell has "
                     "since changed; an unknown answer is drawn as unknown, not as off",
            keywords=("do not disturb", "dnd", "notifications", "quiet", "shell")),
        Row("button", "Keep the session awake", action="noctalia.caffeine",
            icon="gnome-power-manager-symbolic",
            subtitle="The shell's idle inhibitor. It answers ok when it was already in the "
                     "state asked for, so ok is read as a reply and not as a change",
            keywords=("caffeine", "awake", "idle", "inhibit", "sleep")),
        Row("button", "Night light", action="noctalia.nightlight",
            icon="night-light-symbolic",
            subtitle="The schedule, not a forced filter",
            keywords=("night light", "redshift", "warm", "schedule", "evening")),
        Row("state", "Schedule and force are different", icon="dialog-information-symbolic",
            source="features.nightlight_text",
            keywords=("night light", "force", "schedule", "verb")),
        Row("button", "Capture a region", action="noctalia.screenshot_region",
            icon="camera-photo-symbolic", keywords=("screenshot", "region", "capture", "image")),
        Row("button", "Capture a window", action="noctalia.screenshot_window",
            icon="camera-photo-symbolic", keywords=("screenshot", "window", "capture", "image")),
        Row("state", "Why the capture is the shell's", icon="dialog-information-symbolic",
            source="features.capture_text", keywords=("screenshot", "second surface", "shell")),
        Row("state", "Can the shell be asked?", icon="utilities-terminal-symbolic",
            source="features.shell_text", keywords=("ipc", "noctalia", "available")),
        description="Five verbs and one switch, all of them the shell's: this project keeps "
                    "no copy of a state it could not keep true.",
    )

    groups: List[Group] = [modes_group, quiet]
    for title, rows in _ROWS.items():
        groups.append(Group(
            title, *rows,
            description="Three of the shell's own keys, here rather than on Appearance "
                        "because the clipboard and telemetry are features and corner radii "
                        "are not.",
        ))

    return PagePlan(
        PAGE_ID, spec.label, *groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("Neither mode has a key bound to it yet, and no saving has been measured "
                   "on a live session: both are open in docs/UNVERIFIED.md rather than "
                   "claimed here.",
                   kind="warning", icon="dialog-warning-symbolic"),
        ),
        header_actions=(
            Row("state", "What this page has", icon="applications-system-symbolic",
                source="features.feature_count_text", keywords=("features", "modes", "count")),
        ),
    )
