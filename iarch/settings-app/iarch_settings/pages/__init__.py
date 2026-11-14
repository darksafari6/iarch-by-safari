# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The fifteen pages, in the order the sidebar lists them.

The list is the interface's table of contents, and it is written down here rather
than discovered by walking a directory for three reasons:

* the order is a decision, and a directory listing has no opinion about order;
* every icon name comes from ``data/design/adwaita.json``, whose ``icons.names``
  maps each name to the page it belongs to -- and it does so as ``"<label> page"``,
  so a test can check this registry against the record instead of trusting either;
* ``data/settings.default.json`` remembers ``app.last_page`` by id, and an id that
  is not in this registry is a value the window cannot honour.

Nothing in here imports GTK. A page's *definition* is readable on a machine with no
display, no typelib and no PyGObject, which is what makes the definitions testable
-- docs/UNVERIFIED.md SET-02 records that building them is not.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class PageRegistryError(RuntimeError):
    """A page id, label or icon this registry does not know."""


class PageSpec:
    """One sidebar entry.

    ``label`` is the English source string; the renderer passes it through
    :func:`iarch_settings.i18n._` so the catalogue, not this file, decides what a
    person sees. ``keywords`` are the words the search index carries beside the
    label, and they are English too, because the index is built from the
    definitions and translated when it is rendered.
    """

    __slots__ = ("id", "label", "icon", "module", "description", "keywords")

    def __init__(self, page_id: str, label: str, icon: str, module: str,
                 description: str, keywords: Tuple[str, ...] = ()) -> None:
        self.id = page_id
        self.label = label
        self.icon = icon
        self.module = module
        self.description = description
        self.keywords = tuple(keywords)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PageSpec({self.id!r}, {self.label!r})"

    def as_dict(self) -> dict:
        """The stable shape the search index and the About page read."""
        return {
            "id": self.id,
            "label": self.label,
            "icon": self.icon,
            "module": self.module,
            "description": self.description,
            "keywords": list(self.keywords),
        }


#: The pages, in sidebar order. The ids are what ``app.last_page`` stores and what
#: the search results link to.
PAGES: Tuple[PageSpec, ...] = (
    PageSpec(
        "home", "Home", "user-home-symbolic", "home",
        "What this machine is running right now, and the switches worth reaching "
        "quickly.",
        ("system", "session", "overview", "do not disturb", "lock", "screenshot")),
    PageSpec(
        "appearance", "Appearance", "preferences-desktop-appearance-symbolic",
        "appearance",
        "The colour preset, the light and dark mode, the glass intensity and the "
        "wallpaper.",
        ("theme", "preset", "palette", "dark", "light", "intensity", "wallpaper",
         "accent", "contrast")),
    PageSpec(
        "glass", "Glass", "view-conceal-symbolic", "glass",
        "Blur, shadows, corner radius and the transparency of each kind of window.",
        ("blur", "shadow", "radius", "opacity", "transparency", "kawase", "acrylic",
         "dim", "window rules")),
    PageSpec(
        "animations", "Animations", "media-playback-start-symbolic", "animations",
        "Motion presets, durations and the one switch that removes animation.",
        ("motion", "animation", "duration", "reduce motion", "easing", "curve",
         "transition")),
    PageSpec(
        "fonts", "Fonts & Icons", "preferences-desktop-font-symbolic", "fonts",
        "The four font roles, hinting, the icon theme and the cursor.",
        ("font", "typeface", "hinting", "antialias", "subpixel", "icon theme",
         "cursor", "size", "urdu", "arabic")),
    PageSpec(
        "bar", "Bar, Dock & Panels", "sidebar-show-symbolic", "bar",
        "What the shell's bar, dock and panels show. Read from the shell, never "
        "copied into this project's settings.",
        ("bar", "dock", "panel", "shell", "workspace", "buttons", "size",
         "position")),
    PageSpec(
        "display", "Display", "preferences-desktop-display-symbolic", "display",
        "Monitors, resolutions, scale, rotation and arrangement.",
        ("monitor", "screen", "resolution", "scale", "refresh", "transform",
         "position", "output", "mirroring")),
    PageSpec(
        "sound", "Sound, Network & Bluetooth", "network-wireless-symbolic", "sound",
        "Volume, the network and bluetooth status, and the shell's own managers for "
        "each.",
        ("volume", "audio", "wifi", "network", "bluetooth", "osd", "mixer")),
    PageSpec(
        "shortcuts", "Shortcuts", "preferences-desktop-keyboard-shortcuts-symbolic",
        "shortcuts",
        "The session's keybinds, read from the sheet that defines them, and the "
        "recorder that finds a binding by pressing it.",
        ("keybind", "shortcut", "keys", "binding", "recorder", "super")),
    PageSpec(
        "startup", "Startup & Default apps", "preferences-desktop-apps-symbolic",
        "startup",
        "What starts at login, and which program opens a link, a folder, a text file "
        "and a mail.",
        ("autostart", "login", "startup", "default application", "browser", "file "
         "manager", "editor", "mail", "mime")),
    PageSpec(
        "power", "Power & Idle", "gnome-power-manager-symbolic", "power",
        "Battery, the power profile, idle timeouts, night light and the screen.",
        ("power", "battery", "idle", "timeout", "night light", "brightness",
         "sleep", "suspend", "profile", "caffeine")),
    PageSpec(
        "features", "Features", "application-x-addon-symbolic", "features",
        "The two modes this project adds -- game mode and focus -- and what each one "
        "changes.",
        ("game mode", "focus", "mode", "performance", "distraction", "sibling")),
    PageSpec(
        "backup", "Backup & Restore", "document-save-symbolic", "backup",
        "The restore points every write leaves behind, and the settings file they "
        "come from.",
        ("backup", "restore", "rollback", "history", "export", "import", "reset")),
    PageSpec(
        "contact", "Contact", "user-info-symbolic", "contact",
        "How to reach the person who made this, and the portfolio.",
        ("contact", "portfolio", "email", "website", "social", "creator", "copy")),
    PageSpec(
        "about", "About", "dialog-information-symbolic", "about",
        "What this is, what it is built from, and the open-source licenses.",
        ("about", "version", "license", "credits", "notices", "debug", "diagnostics",
         "unverified")),
)

PAGE_IDS: Tuple[str, ...] = tuple(spec.id for spec in PAGES)
"""Every page id, in order. ``app.last_page`` must be one of these."""

_BY_ID: Dict[str, PageSpec] = {spec.id: spec for spec in PAGES}

MODULES: Tuple[str, ...] = tuple(spec.module for spec in PAGES)
"""The plan module each page is defined in, in sidebar order.

A module name equals its page id for all fifteen, and a test asserts that: the
equality is what lets :class:`iarch_settings.pages.plan.Context` resolve a
``module.function`` name against a whitelist instead of against the filesystem, so
a plan cannot point a row at a module nobody registered as a page."""

DEFAULT_PAGE = "home"
"""The page the window opens on when ``app.last_page`` is missing or unknown."""

ICONS_RECORD = "adwaita.json"
"""Where every icon name in this registry was verified."""


def page(page_id: str) -> PageSpec:
    """One page's spec. Refuses an id this registry does not have."""
    if page_id not in _BY_ID:
        raise PageRegistryError(
            f"{page_id} is not a page of this application; the pages are "
            f"{', '.join(PAGE_IDS)}")
    return _BY_ID[page_id]


def has_page(page_id: str) -> bool:
    """Whether an id names a page, without raising."""
    return page_id in _BY_ID


def resolve(page_id: str) -> PageSpec:
    """The page to open: the one asked for, or the default when it is unknown.

    ``app.last_page`` is a value from a file a person can edit, and a window that
    refused to open because of it would be a worse answer than opening on Home and
    saying nothing.
    """
    return _BY_ID.get(page_id) or _BY_ID[DEFAULT_PAGE]


def build(page_id: str, context: Any = None) -> Any:
    """One page's plan, built by its own module.

    The module is imported by name from :data:`MODULES` rather than looked up in a
    dict built at import time, so importing this package does not import fifteen
    modules and a page that fails to import fails only when it is asked for -- with
    its own name in the sentence.
    """
    import importlib  # noqa: PLC0415

    from .plan import Context, default_context  # noqa: PLC0415

    spec = page(page_id)
    module = importlib.import_module(f"{__name__}.{spec.module}")
    function = getattr(module, "build", None)
    if not callable(function):
        raise PageRegistryError(
            f"iarch_settings.pages.{spec.module} has no build(context) function, so "
            f"the {spec.label} page cannot be described")
    return function(context if context is not None else default_context())


def build_all(context: Any = None) -> Dict[str, Any]:
    """Every page's plan, keyed by id, in sidebar order."""
    from .plan import default_context  # noqa: PLC0415

    resolved = context if context is not None else default_context()
    return {page_id: build(page_id, resolved) for page_id in PAGE_IDS}


def icon_sentence(page_id: str, root: Optional[Path] = None) -> str:
    """What the icon record says a page's icon is for, e.g. ``"Home page"``.

    ``data/design/adwaita.json`` maps each page icon to a sentence of exactly that
    form, so the label in this registry and the sentence in the record are two copies
    of one decision. This function reads the record's copy, and a test asserts the
    two agree for all fifteen pages -- which is how a renamed page is caught by the
    build instead of by somebody noticing that the sidebar and the record disagree.
    """
    from .. import paths  # noqa: PLC0415  (late: a test may point paths elsewhere)

    record = json.loads(paths.design_file(ICONS_RECORD, root).read_text(encoding="utf-8"))
    names = record["icons"]["names"]
    spec = page(page_id)
    if spec.icon not in names:
        raise PageRegistryError(
            f"{spec.icon} is not an icon name in {ICONS_RECORD}, so the record cannot "
            f"say what the {spec.label} page is for")
    return str(names[spec.icon])
