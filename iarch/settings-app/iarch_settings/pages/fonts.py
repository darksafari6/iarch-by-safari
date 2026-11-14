# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Fonts & Icons page: nine keys, two files, and two keys it refuses.

Every row here maps to one GtkSettings property recorded in
``data/design/gtk-settings.json``, and the projection is
``~/.config/gtk-4.0/settings.ini`` plus the five keys GTK 3 also reads in
``~/.config/gtk-3.0/settings.ini``. Neither file gets a GENERATED header, because
both are the user's own: a person may have set a font before this project existed and
the writer keeps every key it does not own.

Three rules from the record shape the page:

* **An empty value means "do not write the key".** A font nobody chose must not be
  pinned, because pinning one stops the session's own font change from reaching GTK
  applications. So ``fonts.ui_family`` empty and ``fonts.size_pt`` zero are not
  defaults, they are absences, and each row says so.
* **An unrecognised spelling is ignored, not refused.** GTK compares
  ``gtk-xft-hintstyle`` and ``gtk-xft-rgba`` with ``strcmp`` and silently keeps its
  own value when the string is not one it knows, so those two are dropdowns and never
  free text: a typo in a dropdown is impossible, and a typo in an entry would look
  like it had been applied.
* **Two keys are recorded and deliberately not written.** ``gtk-theme-name`` belongs
  to the renderer that applies the whole look, and ``gtk-enable-animations`` would
  give reduce-motion a second mechanism that can disagree with the first. Both appear
  on this page as rows that say what they are and why they are not offered, because a
  person who has read GTK documentation will look for them here.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..services import config_store, gtk_settings, runner, themes
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "fonts"

#: The settings keys this page offers, in the order the rows appear. Written here so a
#: test can assert the set is exactly the writable keys minus the two halves of
#: ``gtk-font-name``, which are ``fonts.ui_family`` and ``fonts.size_pt``.
OFFERED = ("ui_family", "size_pt", "antialias", "hinting", "hint_style", "subpixel",
           "icon_theme", "cursor_theme", "cursor_size")


# --------------------------------------------------------------------- readers


def document() -> Dict[str, Any]:
    try:
        return config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return {}


def fonts() -> Dict[str, Any]:
    block = document().get("fonts")
    return dict(block) if isinstance(block, dict) else {}


def hint_style_choices() -> List[Tuple[str, str]]:
    """The four spellings GTK compares with strcmp, out of the record."""
    values = gtk_settings.accepted_values("gtk-xft-hintstyle") or []
    labels = {"hintnone": "None", "hintslight": "Slight", "hintmedium": "Medium",
              "hintfull": "Full"}
    return [(value, labels.get(value, value.replace("hint", "").title()))
            for value in values]


def subpixel_choices() -> List[Tuple[str, str]]:
    """The four subpixel orders, out of the record."""
    values = gtk_settings.accepted_values("gtk-xft-rgba") or []
    labels = {"rgb": "Horizontal, red first", "bgr": "Horizontal, blue first",
              "vrgb": "Vertical, red first", "vbgr": "Vertical, blue first"}
    return [(value, labels.get(value, value.upper())) for value in values]


def size_bounds() -> Tuple[int, int]:
    """``gtk-cursor-theme-size``'s own range, which the spin row is rendered with."""
    return gtk_settings.key_range("gtk-cursor-theme-size") or (0, 128)


def token_font_text() -> str:
    """What the design system itself uses, so a blank row is not a mystery."""
    font = themes.font_tokens()
    family = font.get("ui") or font.get("family") or {}
    if isinstance(family, dict):
        family = family.get("family") or family.get("name") or ""
    return (f"the design system's own interface font is {family or 'Inter'}, and an "
            f"empty row leaves it in place")


def gtk4_text() -> Optional[str]:
    """What ``~/.config/gtk-4.0/settings.ini`` holds right now."""
    found = (gtk_settings.read().get("gtk4") or {})
    if not found:
        return None
    return "; ".join(f"{key}={value}" for key, value in sorted(found.items()))


def gtk3_text() -> Optional[str]:
    """What ``~/.config/gtk-3.0/settings.ini`` holds right now."""
    found = (gtk_settings.read().get("gtk3") or {})
    if not found:
        return None
    return "; ".join(f"{key}={value}" for key, value in sorted(found.items()))


def files_text() -> str:
    """Whether the two files exist yet, in the writer's own words."""
    return gtk_settings.available()


def diff_text() -> Optional[str]:
    """Where the two files disagree, which is the one thing worth warning about.

    GTK 4 reads nine keys and GTK 3 reads five, so a difference in the other four is
    expected and is not reported: only a key both versions read can be a real
    disagreement, and that is what this says.
    """
    differences = gtk_settings.diff()
    if not differences:
        return None
    return "; ".join(str(item) for item in differences)


#: One reader per refused key, because a state row's *value* has to be about the row's
#: own subject and a reader is zero-argument: a row cannot ask for the reason for one
#: particular key. Each returns the record's own sentence, so what a person reads is
#: what ``data/design/gtk-settings.json`` says rather than a paraphrase of it, and a
#: key added to the record without a reader here is a row
#: :func:`refused_rows` leaves out -- which the surface test notices, because it
#: asserts the two sets agree.
def theme_name_refusal() -> str:
    """Why ``gtk-theme-name`` is recorded and not written."""
    return str(gtk_settings.refused_keys().get("gtk-theme-name") or "")


def enable_animations_refusal() -> str:
    """Why ``gtk-enable-animations`` is recorded and not written."""
    return str(gtk_settings.refused_keys().get("gtk-enable-animations") or "")


REFUSAL_READERS = {"gtk-theme-name": "fonts.theme_name_refusal",
                   "gtk-enable-animations": "fonts.enable_animations_refusal"}


def refused_rows() -> List[Row]:
    """The keys this project records and does not write, as rows.

    Built from the record rather than typed out, so the list cannot drift from the
    record's own. A key the record refuses and this function has no reader for is
    reported in the row's own title rather than silently dropped: a refusal nobody can
    read is a refusal nobody can argue with.
    """
    rows: List[Row] = []
    for key, reason in sorted(gtk_settings.refused_keys().items()):
        source = REFUSAL_READERS.get(key)
        if source is None:
            rows.append(Row(
                "state", f"{key} (refused, and this page has no reader for the reason)",
                source="fonts.files_text", icon="dialog-warning-symbolic",
                subtitle=str(reason), keywords=(key, "refused", "not written")))
            continue
        rows.append(Row(
            "state", key, source=source, icon="dialog-warning-symbolic",
            subtitle="Recorded in data/design/gtk-settings.json and deliberately not "
                     "written; the value is the reason",
            keywords=(key, "refused", "not written", "gtk")))
    return rows


def family_count_text() -> Optional[str]:
    """How many families the system has, or ``None`` when fontconfig cannot be asked.

    One read, for one row, so that an entry row asking for a family name is not the
    only place on the page that says whether the machine can answer the question.
    """
    if runner.which("fc-list") is None:
        return None
    outcome = runner.run("fc-list", [":", "family"], timeout=runner.DEFAULT_TIMEOUT)
    if outcome.verdict != runner.OK:
        return None
    families = {line.split(",")[0].strip() for line in outcome.stdout.splitlines()
                if line.strip()}
    return f"fontconfig lists {len(families)} families on this machine"


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Fonts & Icons page, as data."""
    spec = registry_page(PAGE_ID)
    minimum, maximum = size_bounds()

    face = Group(
        "The interface font",
        Row("entry", "Family", setting="fonts.ui_family", icon="preferences-desktop-font-symbolic",
            placeholder="Inter",
            subtitle="Empty leaves the design system's own family in place, and a "
                     "family the system does not have is ignored by GTK rather than "
                     "refused",
            keywords=("font", "family", "typeface", "ui", "text", "interface")),
        Row("spin", "Size", setting="fonts.size_pt", minimum=0.0, maximum=72.0,
            step=0.5, unit="pt", icon="preferences-desktop-font-symbolic",
            subtitle="0 means do not write the key at all, which leaves the system "
                     "default in place",
            keywords=("size", "point", "pt", "scale", "big", "small", "font")),
        Row("state", "The design system's own", icon="dialog-information-symbolic",
            source="fonts.token_font_text", keywords=("default", "token", "inter")),
        Row("state", "Families on this machine", icon="preferences-system-symbolic",
            source="fonts.family_count_text",
            subtitle="Asked of fontconfig once, so the row above is not the only place "
                     "that knows",
            keywords=("fc-list", "fontconfig", "families", "installed")),
        description="The family and the size are the two halves of one GtkSettings "
                    "key, gtk-font-name, which is a single string of the form "
                    "\"Family Size\".",
        style_classes=("iarch-glass-card",),
    )

    rendering = Group(
        "Rendering",
        Row("switch", "Antialias", setting="fonts.antialias",
            icon="preferences-desktop-font-symbolic",
            subtitle="gtk-xft-antialias; the key's third value, -1, is the system "
                     "default and is what not writing it means",
            keywords=("antialias", "smooth", "edges", "xft")),
        Row("switch", "Hinting", setting="fonts.hinting",
            icon="preferences-desktop-font-symbolic", subtitle="gtk-xft-hinting",
            keywords=("hinting", "snap", "grid", "xft")),
        Row("combo", "Hint style", setting="fonts.hint_style",
            choices_source="fonts.hint_style_choices",
            icon="preferences-desktop-font-symbolic",
            subtitle="A dropdown and not an entry: GTK ignores a spelling it does not "
                     "know instead of refusing it, so a typo here would look applied",
            keywords=("hint", "style", "slight", "medium", "full", "none")),
        Row("combo", "Subpixel order", setting="fonts.subpixel",
            choices_source="fonts.subpixel_choices",
            icon="preferences-desktop-font-symbolic",
            subtitle="gtk-xft-rgba, and ignored rather than refused if the spelling is "
                     "not one GTK knows",
            keywords=("subpixel", "rgba", "bgr", "lcd", "order")),
        description="Four keys GTK reads through Xft, all of them forgiving in the "
                    "worst way: an unrecognised value is silently ignored, so each "
                    "one is a closed list here.",
    )

    themes_group = Group(
        "Icons and cursor",
        Row("entry", "Icon theme", setting="fonts.icon_theme",
            icon="folder-pictures-symbolic", placeholder="Adwaita",
            subtitle="gtk-icon-theme-name. Empty means do not write the key; the icon "
                     "theme this project ships and verifies against is Adwaita",
            keywords=("icon", "theme", "symbolic", "adwaita")),
        Row("entry", "Cursor theme", setting="fonts.cursor_theme",
            icon="input-keyboard-symbolic", placeholder="Bibata-Modern-Classic",
            subtitle="gtk-cursor-theme-name. Every colour preset ships the same "
                     "cursor, so applying a preset does not move it",
            keywords=("cursor", "pointer", "theme", "bibata", "mouse")),
        Row("spin", "Cursor size", setting="fonts.cursor_size",
            minimum=float(minimum), maximum=float(maximum), step=1.0, unit="px",
            icon="input-keyboard-symbolic",
            subtitle=f"The key's own range is {minimum} to {maximum}; 0 is the key's "
                     f"system default and also means do not write it",
            keywords=("cursor", "size", "pointer", "px", "big")),
        description="Three keys both GTK versions read, projected into both "
                    "settings.ini files.",
    )

    files = Group(
        "The two files",
        Row("state", "What exists", icon="document-save-symbolic",
            source="fonts.files_text",
            subtitle="Neither file gets a GENERATED header: both are the user's own, "
                     "and every key this project does not write is kept",
            keywords=("settings.ini", "gtk-4.0", "gtk-3.0", "files")),
        Row("state", "GTK 4 now holds", icon="accessories-text-editor-symbolic",
            source="fonts.gtk4_text", keywords=("gtk4", "settings.ini", "keys")),
        Row("state", "GTK 3 now holds", icon="accessories-text-editor-symbolic",
            source="fonts.gtk3_text", keywords=("gtk3", "settings.ini", "keys")),
        Row("state", "Where the two disagree", icon="dialog-warning-symbolic",
            source="fonts.diff_text",
            subtitle="Only a key both versions read can be a real disagreement",
            keywords=("diff", "disagree", "gtk3", "gtk4")),
        Row("expander", "Recorded and deliberately not written",
            rows=tuple(refused_rows()), icon="dialog-warning-symbolic",
            subtitle="Two keys the record lists and this project refuses, each with "
                     "the reason the record gives",
            keywords=("refused", "gtk-theme-name", "gtk-enable-animations", "not written")),
        description="What is on disk after a change, read back rather than assumed.",
    )

    return PagePlan(
        PAGE_ID, spec.label, face, rendering, themes_group, files,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("A font change is written to both settings.ini files and then "
                   "fontconfig is re-rendered: GTK's keys alone do not reach "
                   "applications that ask fontconfig directly.",
                   kind="info", icon="dialog-information-symbolic"),
        ),
        header_actions=(
            Row("state", "Keys this page writes", icon="accessories-text-editor-symbolic",
                source="fonts.writable_text",
                keywords=("keys", "writable", "gtk")),
        ),
    )


def writable_text() -> str:
    """How many of the recorded keys this page writes, for the title bar."""
    keys = gtk_settings.writable_keys()
    return f"{len(keys)} GtkSettings keys, of which {len(gtk_settings.gtk3_keys())} " \
           f"are also written for GTK 3"
