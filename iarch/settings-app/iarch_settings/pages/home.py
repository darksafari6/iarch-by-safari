# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Home page: what this machine is running, and the switches worth reaching.

Home is the page the window opens on, so it has two jobs and they pull in different
directions. It has to answer "what is my desktop doing right now" without a person
having to know which of the other fourteen pages owns the question, and it has to
stay short enough that the answer is visible without scrolling. The split that
resolves that: **Home reads everything and writes almost nothing.** The state rows
are reads -- the machine, the session, the derived coarse switches -- and the only
writes are the two mode switches and the shell's own Do Not Disturb flag, because
those three are the ones a person reaches for without wanting to find the page.

Everything deeper lives on its own page, and nothing here duplicates a control: the
intensity is *shown* here and *changed* on Appearance, because two switches for one
value is how a file ends up saying two things.

The functions below are the read-only, zero-argument helpers a plan row may name
(:data:`iarch_settings.pages.plan.PLAN_HELPERS`). Each one unwraps a service answer
into something drawable and returns ``None`` when the question could not be asked,
which is what the renderer shows as *unverified* rather than as "off".
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..services import config_store, control, hypr, noctalia, runner, system, themes
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "home"


# --------------------------------------------------------------------- readers


def snapshot() -> Dict[str, Any]:
    """One read of the machine, so a page of state rows is not eight reads."""
    try:
        return system.snapshot()
    except (system.SystemError, OSError):
        return {}


def hostname() -> Optional[str]:
    value = snapshot().get("hostname")
    return str(value) if value else None


def distribution() -> Optional[str]:
    distro = snapshot().get("distro") or {}
    name = distro.get("name") or distro.get("id")
    return str(name) if name else None


def kernel_text() -> Optional[str]:
    kernel = snapshot().get("kernel") or {}
    release = kernel.get("release")
    if not release:
        return None
    machine = kernel.get("machine")
    return f"{release} ({machine})" if machine else str(release)


def session_text() -> Optional[str]:
    """The session, or ``None`` when this process is not inside one.

    A sandbox, a container and a login shell over ssh all answer ``None`` here, and
    the row then says the session could not be identified rather than reporting a
    desktop that is not there.
    """
    session = snapshot().get("session") or {}
    parts = [session.get("desktop") or session.get("session_desktop"),
             session.get("type"), session.get("compositor")]
    found = [str(part) for part in parts if part]
    return " · ".join(dict.fromkeys(found)) if found else None


def uptime_text() -> Optional[str]:
    value = snapshot().get("uptime")
    return str(value) if value else None


def memory_text() -> Optional[str]:
    memory = snapshot().get("memory") or {}
    used, total = memory.get("used_kib"), memory.get("total_kib")
    if not used or not total:
        return None
    return f"{system.format_kib(used)} of {system.format_kib(total)}"


def processor_text() -> Optional[str]:
    data = snapshot()
    count = data.get("cpu_count")
    percent = data.get("cpu_percent")
    if not count:
        return None
    if percent is None:
        return f"{count} threads"
    return f"{count} threads · {percent:.0f}% busy"


def battery_text() -> Optional[str]:
    """The primary battery, or ``None`` on a machine that has none.

    ``None`` is not "no battery" and not "unknown" at the same time on purpose: the
    row is left out of the page entirely when there is no battery, because a desktop
    that reports a battery row saying *unverified* is a desktop that has been
    installed on a machine with no battery in it.
    """
    battery = snapshot().get("battery")
    if not battery:
        return None
    percent = battery.get("percent")
    state = battery.get("state") or ("charging" if snapshot().get("on_ac") else "on battery")
    if percent is None:
        return str(state)
    return f"{percent:.0f}% · {state}"


def has_battery() -> bool:
    """Whether the battery row belongs on the page at all."""
    return bool(snapshot().get("battery"))


def settings_document() -> Dict[str, Any]:
    """The merged settings document, read for display only."""
    try:
        return config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return {}


def theme_text() -> Optional[str]:
    """``Midnight glass at Frosted``: the two halves of the look, in one line."""
    document = settings_document()
    theme = document.get("theme") or {}
    preset = str(theme.get("colour_preset") or "")
    intensity = str(theme.get("intensity") or "")
    if not preset and not intensity:
        return None
    try:
        return f"{preset.replace('-', ' ')} at {themes.intensity_label(intensity)}"
    except themes.ThemesError:
        return f"{preset} at {intensity}"


def preset_text() -> Optional[str]:
    """The coarse master switch, which is derived and shown here rather than set."""
    value = settings_document().get("preset")
    return str(value).replace("_", " ") if value else None


def effects_text() -> Optional[str]:
    """The four coarse effect switches as one line, because none of them is set here."""
    effects = settings_document().get("effects") or {}
    if not effects:
        return None
    order = ("blur", "transparency", "shadows", "animations")
    return " · ".join(f"{name} {'on' if effects.get(name) else 'off'}"
                      for name in order if name in effects)


def motion_text() -> Optional[str]:
    document = settings_document()
    animation = document.get("animation") or {}
    preset = str(animation.get("preset") or "")
    if not preset:
        return None
    speed = animation.get("speed")
    text = preset.replace("_", " ")
    if speed:
        text += f" at {float(speed):g}×"
    if animation.get("reduce_motion"):
        text += ", reduced"
    return text


def compositor_text() -> str:
    """What can be asked of the compositor, in the compositor service's own words."""
    return hypr.available()


def shell_text() -> str:
    """What can be asked of the shell, in the shell service's own words."""
    return noctalia.available()


def compositor_missing() -> bool:
    """The banner condition: no compositor means every live value is unverified."""
    return not hypr.in_session() or hypr.available().startswith(("no ", "this looks"))


def shell_missing() -> bool:
    return runner.which(runner.NOCTALIA_BIN) is None


def dnd_state() -> Optional[bool]:
    """Do Not Disturb as the shell reports it, or ``None`` when it does not answer."""
    value, _why = noctalia.dnd_status()
    return value


def settings_problems() -> bool:
    """Whether the settings document needed a migration or was quarantined."""
    try:
        store = config_store.Store()
        store.load()
    except (config_store.ConfigStoreError, OSError):
        return True
    return store.status != config_store.LOADED


def settings_status() -> Optional[str]:
    """How the document got here, when the answer is not simply "loaded"."""
    try:
        store = config_store.Store()
        store.load()
    except (config_store.ConfigStoreError, OSError) as exc:
        return str(exc)
    if store.status == config_store.LOADED:
        return None
    detail = "; ".join(store.problems) if store.problems else ""
    return f"{store.status}{': ' + detail if detail else ''}"


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Home page, as data."""
    spec = registry_page(PAGE_ID)

    machine = Group(
        "This machine",
        Row("state", "Computer", icon="computer-symbolic", source="home.hostname",
            keywords=("hostname", "name", "machine")),
        Row("state", "Distribution", icon="preferences-system-symbolic",
            source="home.distribution", keywords=("distro", "arch", "fedora", "linux")),
        Row("state", "Kernel", icon="preferences-system-symbolic",
            source="home.kernel_text", keywords=("linux", "version", "machine")),
        Row("state", "Session", icon="system-users-symbolic", source="home.session_text",
            keywords=("wayland", "x11", "desktop", "compositor", "session type")),
        Row("state", "Uptime", icon="preferences-system-symbolic",
            source="home.uptime_text", keywords=("up", "boot", "time")),
        Row("state", "Memory", icon="drive-harddisk-symbolic", source="home.memory_text",
            keywords=("ram", "memory", "used")),
        Row("state", "Processor", icon="preferences-system-symbolic",
            source="home.processor_text", keywords=("cpu", "cores", "threads", "load")),
        Row("state", "Battery", icon="battery-good-symbolic", source="home.battery_text",
            visible_when="home.has_battery", keywords=("power", "charge", "ac")),
        description="Read from /proc, /sys and /etc. Nothing here is stored, so none "
                    "of it can go stale.",
        style_classes=("iarch-glass-hero",),
    )

    look = Group(
        "The look right now",
        Row("state", "Theme", icon="preferences-desktop-appearance-symbolic",
            source="home.theme_text",
            subtitle="Changed on the Appearance page",
            keywords=("preset", "intensity", "colour", "glass")),
        Row("state", "Master switch", icon="view-conceal-symbolic",
            source="home.preset_text",
            subtitle="Derived from the glass intensity, never set on its own",
            keywords=("preset", "performance", "coarse")),
        Row("state", "Effects", icon="view-conceal-symbolic", source="home.effects_text",
            subtitle="Derived from the intensity, the leaf overrides and the motion "
                     "preset",
            keywords=("blur", "shadow", "transparency", "animation", "effects")),
        Row("state", "Motion", icon="media-playback-start-symbolic",
            source="home.motion_text", subtitle="Changed on the Animations page",
            keywords=("animation", "motion", "speed", "reduce")),
        description="The coarse switches Part 1 shipped are computed from the sections "
                    "that own them, so this page shows them and does not offer them: "
                    "one value, one writer.",
    )

    modes = Group(
        "Quick switches",
        Row("switch", "Game mode", setting="modes.game.active",
            icon="applications-games-symbolic",
            subtitle="Drops compositor effects for latency, and restores what it "
                     "replaced when it is turned off",
            keywords=("game", "latency", "performance", "fps")),
        Row("switch", "Focus mode", setting="modes.focus.active",
            icon="preferences-desktop-screensaver-symbolic",
            subtitle="Do Not Disturb, caffeine and a dimmed background",
            keywords=("focus", "dnd", "quiet", "dim", "leave me alone")),
        Row("switch", "Do Not Disturb", action="noctalia.set_dnd", source="home.dnd_state",
            icon="dialog-warning-symbolic",
            subtitle="The shell's own flag, read from and written through its IPC",
            keywords=("dnd", "notifications", "quiet", "shell")),
        Row("button", "Keep the session awake", action="noctalia.caffeine",
            icon="gnome-power-manager-symbolic",
            subtitle="Toggles the shell's caffeine flag. The shell has no verb that "
                     "answers what it is set to, so this row cannot show a state",
            keywords=("caffeine", "idle", "awake", "sleep")),
        Row("button", "Night light", action="noctalia.nightlight",
            icon="night-light-symbolic",
            subtitle="Toggles the shell's own night light, which the shell owns "
                     "end to end",
            keywords=("night light", "blue light", "warm", "evening")),
        description="The three switches worth reaching without finding their page. "
                    "Each one is the same switch the page owns, not a second copy.",
    )

    session = Group(
        "The session",
        Row("button", "Lock now", action="noctalia.lock_now",
            icon="system-lock-screen-symbolic",
            subtitle="Asks the shell to lock; the lock screen itself is the one this "
                     "project renders",
            keywords=("lock", "screen", "secure", "away")),
        Row("button", "Capture a region", action="noctalia.screenshot_region",
            icon="camera-photo-symbolic",
            subtitle="The shell's own capture, so the file lands where the shell puts "
                     "its captures",
            keywords=("screenshot", "capture", "region", "image")),
        Row("button", "Open the control centre", action="noctalia.open_control_center",
            icon="open-menu-symbolic",
            subtitle="The shell's panel, not a page of this window",
            keywords=("control centre", "panel", "shell", "quick settings")),
        Row("state", "Compositor", icon="preferences-system-symbolic",
            source="home.compositor_text", keywords=("hyprland", "hyprctl", "compositor")),
        Row("state", "Shell", icon="preferences-system-symbolic", source="home.shell_text",
            keywords=("shell", "ipc", "noctalia", "bar")),
        description="What can be asked, and what cannot. A missing binary is "
                    "*unverified* rather than *off*, everywhere on this page.",
    )

    return PagePlan(
        PAGE_ID, spec.label, machine, look, modes, session,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("No compositor session was found, so every live value on this page "
                   "is unverified rather than wrong.",
                   kind="warning", icon="dialog-warning-symbolic",
                   when="home.compositor_missing"),
            Banner("The shell's binary is not on PATH, so its verbs cannot be sent and "
                   "its state cannot be read.",
                   kind="warning", icon="dialog-warning-symbolic", when="home.shell_missing"),
            Banner("The settings file needed attention before it could be read.",
                   kind="info", icon="dialog-information-symbolic",
                   when="home.settings_problems"),
        ),
        header_actions=(
            Row("state", "Settings file", icon="document-save-symbolic",
                source="home.settings_status",
                subtitle="Only shown when the document was migrated, quarantined or "
                         "could not be read",
                visible_when="home.settings_problems"),
        ),
    )
