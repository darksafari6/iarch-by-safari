# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Power & Idle page: what the shell does when nobody is there.

Two systems and one profile. The power profile is UPower's, set through the shell; idle and
the lock screen are the shell's own, driven by the Wayland ``ext_idle_notifier_v1`` protocol
and respecting D-Bus -- which is how a browser holds idle off during playback -- and Wayland
idle inhibitors. Neither is in this project's settings file, so every row reads and writes
through the shell's IPC and stores no copy.

The idle half explains a decision Part 3 made and left in the repository: ``.config/hypr/
hypridle.conf`` ships **unlaunched**. The record's own note gives the reason -- when the
shell's resolved config defines no behaviour at all it seeds built-in Lock and Monitor-off
behaviours, both disabled -- so a second idle daemon watching the same protocol would race
this one to lock, dim and suspend. The banner says that on the page, because a configuration
file that is present and never started looks like a bug from the outside and is a decision
from the inside.

Two of the lock screen's keys are security settings rather than appearance, and the record
says so: ``grace_period_seconds`` and ``allow_empty_password``. They are drawn with the same
generator as the appearance keys because they are the same kind of thing to the shell, and
flagged separately here because they are not the same kind of thing to a person.

The profile row cannot show the profile in force. ``power-set`` and ``power-cycle`` are the
only two power verbs the record carries, and neither reads anything back, so there is no
answer to "what is it now?" that this page could give honestly. The row offers the three
profiles the verb's own description names -- performance, balanced, power-saver -- and a
state row beside it says plainly that UPower decides and nothing here reports the result. A
dropdown that showed a remembered value would be showing a value this project made up.

The four array keys -- the shell's idle ``behavior`` and ``behavior_order``, and the lock
screen's ``transition`` sequence and per-monitor list -- are shown and not written, for the
reason :func:`iarch_settings.pages.shellkeys.array_keys` gives: an array is a list editor,
and ``lockscreen.transition`` is the sharpest case, because the record declares an enum for
its *items* and not for the key, so a dropdown built from that enum would offer one
transition where the shell takes an ordered sequence of them.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..services import noctalia, runner, system
from . import page as registry_page
from . import shellkeys
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "power"

#: The profiles the verb's own description names. The record is explicit that the argument
#: has no closed choice list -- the shell passes it to UPower and UPower decides -- so this
#: is a product decision about what to offer, not a claim about what is accepted, and the
#: setter refuses anything else rather than sending a spelling nobody verified.
PROFILES: Tuple[Tuple[str, str], ...] = (
    ("power-saver", "Power saver"),
    ("balanced", "Balanced"),
    ("performance", "Performance"),
)

IDLE_BUCKETS = (("Before it acts", ("pre_action_",)),)
LOCK_BUCKETS = (
    ("When it locks", ("enabled", "lock_before_suspend", "grace_period", "fingerprint",
                       "allow_empty_password")),
    ("How it looks", ("blurred_desktop", "transition_duration", "edge_smoothness",
                      "blur_intensity", "tint_intensity", "wallpaper")),
)
ICONS = {
    "Before it acts": "preferences-desktop-screensaver-symbolic",
    "When it locks": "system-lock-screen-symbolic",
    "How it looks": "preferences-desktop-appearance-symbolic",
}

_IDLE_ROWS, _IDLE_NAMES = shellkeys.build(
    "idle", PAGE_ID, buckets=IDLE_BUCKETS, skip=shellkeys.array_keys("idle"),
    icons=ICONS, fallback_icon="preferences-desktop-screensaver-symbolic")
_LOCK_ROWS, _LOCK_NAMES = shellkeys.build(
    "lockscreen", PAGE_ID, buckets=LOCK_BUCKETS, skip=shellkeys.array_keys("lockscreen"),
    icons=ICONS, fallback_icon="system-lock-screen-symbolic")

# The generator's readers, setters and validators become this module's attributes, because a
# plan resolves a row's names against the modules it is allowed to resolve into.
globals().update(_IDLE_NAMES)
globals().update(_LOCK_NAMES)


# --------------------------------------------------------------------- readers


def profile_read_text() -> str:
    """Why the profile row shows nothing: the record carries no read verb."""
    return ("power-set and power-cycle are the only power verbs the shell's IPC has, and "
            "neither reads anything back, so this page cannot say which profile is in "
            "force -- only which one was last asked for, and it does not store that")


def set_profile(profile: Any) -> runner.Outcome:
    """Write the power profile, refusing a spelling this project does not offer."""
    text = str(profile or "").strip()
    offered = [value for value, _label in PROFILES]
    if text not in offered:
        return runner.Outcome([runner.NOCTALIA_BIN, "msg", "power-set", text],
                              runner.FAILED,
                              reason=f"{text!r} is not one of the profiles this page "
                                     f"offers: {', '.join(offered)}")
    return noctalia.power_profile(text)


def has_battery() -> bool:
    """Whether this machine publishes a battery at all.

    The row is conditional on this rather than always drawn, because a desktop with no
    battery and a laptop at zero percent are opposite statements and only one of them is
    true: :func:`iarch_settings.services.system.batteries` returns an empty list for the
    first, and showing 0% for it would be showing a number that does not exist.
    """
    return bool(system.batteries())


def battery_text() -> Optional[str]:
    """The first battery's charge and status, or ``None`` when there is none."""
    found = system.primary_battery()
    if not found:
        return None
    percent = found.get("percent")
    status = str(found.get("status") or "unknown")
    if percent is None:
        return f"{found.get('name')}: {status}, and no capacity is published"
    return f"{found.get('name')}: {percent}% and {status.lower()}"


def ac_text() -> str:
    """Whether the machine is on mains power, and what it means when that is unknown."""
    on_ac = system.power_on_ac()
    if on_ac is None:
        return ("this machine publishes no AC supply, which is what a desktop and a "
                "container both look like -- it is not the same as running on battery")
    return "on mains power" if on_ac else "on battery"


def uptime_text() -> Optional[str]:
    """How long the session has been up, which is what an idle timeout counts against."""
    seconds = system.uptime_seconds()
    return system.format_uptime(seconds) if seconds is not None else None


def shell_text() -> str:
    """Whether the shell's binary is on PATH, in the service's own sentence."""
    return noctalia.available()


def hypridle_text() -> str:
    """Why the shipped idle configuration is never started."""
    return (".config/hypr/hypridle.conf ships unlaunched: the shell owns "
            "ext_idle_notifier_v1 and seeds its own Lock and Monitor-off behaviours when "
            "its config defines none, so a second daemon watching the same protocol would "
            "race this one to lock, dim and suspend")


def _array_reader(path: str, subject: str) -> Any:
    """A reader that describes one array key instead of printing it."""

    def read() -> Optional[str]:
        value, verdict, _reason = noctalia.read(path)
        if verdict != runner.OK:
            return None
        if isinstance(value, list):
            if not value:
                return f"{subject}: the shell has none, so it seeds its own defaults"
            return f"{subject}: {len(value)} entr{'y' if len(value) == 1 else 'ies'}"
        return f"{subject}: {value}"

    read.__name__ = path.replace(".", "_") + "_text"
    read.__doc__ = f"A sentence describing ``{path}``, which this page shows and does not write."
    return read


#: The four array keys, each with the words its row should use.
ARRAY_SUBJECTS: Dict[str, str] = {
    "idle.behavior": "idle behaviours",
    "idle.behavior_order": "the order they run in",
    "lockscreen.transition": "lock-screen transitions",
    "lockscreen.monitors": "per-monitor lock-screen settings",
}

for _path, _subject in ARRAY_SUBJECTS.items():
    globals()[_path.replace(".", "_") + "_text"] = _array_reader(_path, _subject)
del _path, _subject


def array_rows(container: str = "") -> List[Row]:
    """One read-only row per array key, saying what it holds and why it is not editable.

    ``container`` narrows the list to one container's keys, so the idle group and the lock
    screen group each show their own. Filtering on a keyword substring was the first
    attempt and it silently matched nothing, because a keyword is a whole string and
    ``idle.`` is not one of them -- an empty expander is exactly the failure a plan reports.
    """
    rows: List[Row] = []
    for path, subject in ARRAY_SUBJECTS.items():
        if container and not path.startswith(container + "."):
            continue
        rows.append(Row(
            "state", subject.capitalize(), source=f"power.{path.replace('.', '_')}_text",
            icon="dialog-information-symbolic",
            subtitle=f"{shellkeys.key_name(path)}: an array, so editing it means a list "
                     f"editor -- add, remove, reorder -- and this page does not ship half "
                     f"of one",
            keywords=(shellkeys.key_name(path), path, "array", "read-only", subject)))
    return rows


def security_rows_text() -> str:
    """Which of the lock screen's keys are security settings rather than appearance."""
    return ("grace_period_seconds and allow_empty_password are the two the shell's own "
            "record flags as security settings: one is how long the lock screen waits "
            "before it needs a password again, and the other decides whether an empty "
            "password is accepted at all")


def key_count_text() -> str:
    """How many of the shell's power keys this page writes."""
    idle = len(shellkeys.keys_of("idle"))
    lock = len(shellkeys.keys_of("lockscreen"))
    arrays = len(ARRAY_SUBJECTS)
    return (f"{idle + lock - arrays} of the shell's {idle + lock} idle and lock-screen keys "
            f"are written here; {arrays} are arrays and are shown instead")


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Power & Idle page, as data."""
    spec = registry_page(PAGE_ID)

    groups: List[Group] = [Group(
        "Power",
        Row("combo", "Power profile", choices=list(PROFILES), action="power.set_profile",
            icon="gnome-power-manager-symbolic",
            subtitle="Sent to UPower through the shell. The record declares no closed choice "
                     "list for it, so these are the three the verb's own description names",
            keywords=("power", "profile", "upower", "performance", "balanced",
                      "power-saver", "battery")),
        Row("state", "What this row cannot show", icon="dialog-warning-symbolic",
            source="power.profile_read_text",
            subtitle="A dropdown that showed a remembered value would be showing a value "
                     "this project made up",
            keywords=("profile", "read back", "no verb", "honest")),
        Row("state", "Mains power", icon="gnome-power-manager-symbolic",
            source="power.ac_text", keywords=("ac", "mains", "battery", "plugged")),
        Row("state", "Battery", icon="battery-good-symbolic", source="power.battery_text",
            visible_when="power.has_battery",
            subtitle="Read from sysfs, not from the shell: a charge level is the kernel's "
                     "answer and the shell has no verb for it",
            keywords=("battery", "percent", "charge", "capacity", "laptop")),
        Row("state", "Uptime", icon="preferences-system-symbolic", source="power.uptime_text",
            subtitle="What an idle timeout counts against",
            keywords=("uptime", "session", "idle", "time")),
        description="The profile is UPower's and the charge level is the kernel's; this "
                    "project stores neither.",
        style_classes=("iarch-glass-card",),
    )]

    groups.append(Group(
        "Session",
        Row("button", "Lock now", action="noctalia.lock_now",
            icon="system-lock-screen-symbolic",
            subtitle="The shell's own lock, which is the one this session shows whenever the "
                     "shell is running",
            keywords=("lock", "screen", "now", "session")),
        Row("button", "Suspend now", action="noctalia.suspend_now",
            icon="gnome-power-manager-symbolic",
            subtitle="One of the two session actions this project sends; logging out, "
                     "rebooting and powering off are the shell's own menu's job, with the "
                     "confirmation it owns",
            keywords=("suspend", "sleep", "session", "power")),
        Row("button", "Turn the screen off", action="noctalia.screen_off",
            icon="display-brightness-symbolic", keywords=("screen", "off", "dpms", "blank")),
        Row("button", "Turn the screen on", action="noctalia.screen_on",
            icon="display-brightness-symbolic", keywords=("screen", "on", "dpms", "wake")),
        Row("state", "Can the shell be asked?", icon="utilities-terminal-symbolic",
            source="power.shell_text", keywords=("ipc", "noctalia", "available")),
        description="Four verbs and no confirmation of this project's own: each one is "
                    "reversible by pressing a key or moving the mouse.",
    ))

    for title, rows in _IDLE_ROWS.items():
        groups.append(Group(
            title, *rows,
            description="The shell's idle system, driven by ext_idle_notifier_v1 and "
                        "respecting D-Bus and Wayland idle inhibitors.",
        ))
    groups.append(Group(
        "Idle, shown and not written",
        Row("expander", "The shell's idle arrays", rows=tuple(array_rows("idle")),
            icon="dialog-information-symbolic",
            subtitle="An array is a list editor, and this page does not ship half of one",
            keywords=("idle", "behavior", "array", "read-only")),
        Row("state", "Why hypridle is never started", icon="dialog-warning-symbolic",
            source="power.hypridle_text",
            subtitle="A configuration file that is present and never started is a decision, "
                     "not a bug",
            keywords=("hypridle", "unlaunched", "race", "idle daemon", "ext_idle_notifier")),
        description="Two idle keys and one writable one: the fade before an action. The "
                    "behaviours themselves are the shell's to sequence.",
    ))

    for title, rows in _LOCK_ROWS.items():
        groups.append(Group(title, *rows))
    groups.append(Group(
        "The lock screen, shown and not written",
        Row("expander", "Its arrays", rows=tuple(array_rows("lockscreen")),
            icon="dialog-information-symbolic",
            subtitle="The transition sequence and the per-monitor list: both arrays, both "
                     "the shell's",
            keywords=("lockscreen", "transition", "monitors", "array", "read-only")),
        Row("state", "Two of these keys are security", icon="dialog-warning-symbolic",
            source="power.security_rows_text",
            subtitle="They are drawn like the appearance keys because they are the same kind "
                     "of thing to the shell, and flagged here because they are not the same "
                     "kind of thing to a person",
            keywords=("security", "grace period", "empty password", "lock")),
        Row("state", "Keys on this page", icon="system-lock-screen-symbolic",
            source="power.key_count_text", keywords=("keys", "count", "idle", "lockscreen")),
        Row("button", "Open this in the shell's own window",
            action="noctalia.open_shell_settings", icon="go-next-symbolic",
            subtitle="The escape hatch the record describes, for a key this project has not "
                     "verified a range for",
            keywords=("shell", "settings", "open", "escape hatch")),
        description="The shell's lock screen wins ext_session_lock_v1 whenever the shell is "
                    "running, so .config/hypr/hyprlock.conf is the fallback for a session "
                    "without it -- and the rows above are the one that is actually showing.",
    ))

    return PagePlan(
        PAGE_ID, spec.label, *groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("Nothing on this page is stored in settings.json: the profile is UPower's, "
                   "the idle and lock-screen keys are the shell's, and the charge level is "
                   "the kernel's.",
                   kind="info", icon="utilities-terminal-symbolic"),
            Banner("Two lock-screen keys are security settings rather than appearance: the "
                   "grace period before a password is needed again, and whether an empty "
                   "password is accepted at all.",
                   kind="warning", icon="dialog-warning-symbolic"),
        ),
        header_actions=(
            Row("state", "Mains power", icon="gnome-power-manager-symbolic",
                source="power.ac_text", keywords=("ac", "battery", "power")),
        ),
    )
