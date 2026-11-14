# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Appearance page: the look, and only the look.

Four things live here and each has exactly one writer:

* **the colour preset** -- a tile in a grid, because a palette is something you look
  at rather than read. The list is the files in ``data/design/presets/``, so a preset
  added to that directory appears here without a code change, which is what the
  settings schema means by "the list stays open";
* **the glass intensity** -- a dropdown of the four the tokens define, with the
  token's own label and description, because the difference between *Frosted* and
  *Crystal* is a blur recipe and a set of opacities and not an adjective;
* **the light and dark mode** -- one value with two projections, the shell's
  ``theme-mode-set`` verb and GTK's ``gtk-application-prefer-dark-theme``, written
  together by :mod:`iarch_settings.services.control` so they cannot drift;
* **the wallpaper** -- read from the shell and *not* offered, because the shell owns
  it end to end and a second writer of a wallpaper is a second opinion about the
  desktop.

Changing the preset or the intensity runs ``iarch-theme apply``, which renders eleven
generated files and writes both keys back into ``settings.json`` itself. That is why
the rows name a setting and not an action: the file is written by the tool, and the
window re-reads the store when the report says the change succeeded.

The accent override is *shown* here and cannot be set, and the row says why in the
words :data:`iarch_settings.services.control.UNPROJECTED` records: no renderer reads
one. A switch that changes nothing on screen is worse than a row that explains
itself.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..services import config_store, control, noctalia, runner, themes
from . import page as registry_page
from . import shellkeys
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "appearance"

#: The shell's own appearance keys that belong on the Features page instead, because the
#: clipboard and telemetry are features and corner radii are not. The two pages share one
#: container, so each names the keys it wants and neither can draw a switch the other drew.
SHELL_ELSEWHERE = ("clipboard_enabled", "clipboard_confirm_clear_history",
                   "telemetry_enabled")

SHELL_BUCKETS = (
    ("Corners, borders and shadows", ("corner_radius", "button_borders", "input_borders",
                                      "popup_borders", "card_borders", "show_close_buttons",
                                      "popup_shadows")),
    ("Type and time", ("font_family", "time_format", "date_format")),
    ("The shell's own window", ("settings_", "app_icon_colorize")),
)

SHELL_ICONS = {
    "Corners, borders and shadows": "preferences-desktop-appearance-symbolic",
    "Type and time": "preferences-desktop-font-symbolic",
    "The shell's own window": "preferences-desktop-appearance-symbolic",
}

_SHELL_ROWS, _SHELL_NAMES = shellkeys.build(
    "shell", PAGE_ID, buckets=SHELL_BUCKETS, skip=SHELL_ELSEWHERE, icons=SHELL_ICONS,
    fallback_icon="preferences-desktop-appearance-symbolic")

# The generator's readers, setters and validators become this module's attributes, because a
# plan resolves a row's names against the modules it is allowed to resolve into.
globals().update(_SHELL_NAMES)


def _slug(text: str) -> str:
    """An identifier-safe version of a table path, for a generated reader's name."""
    return "".join(character if character.isalnum() else "_"
                   for character in str(text).lower()).strip("_") or "table"


def _table_reader(path: str) -> Any:
    """Build the reader one named-but-not-drawn table's row shows."""

    def read() -> str:
        try:
            leaves = [other for other in noctalia.known_paths() if other.startswith(path + ".")]
        except noctalia.NoctaliaError:
            leaves = []
        return (f"a table of {len(leaves)} keys the shell owns, changed in its own settings "
                f"window rather than here")

    read.__name__ = f"shell_table_{_slug(path)}"
    read.__doc__ = f"What ``{path}`` is, and where it is changed."
    return read


def shell_table_rows() -> List[Row]:
    """One row per table under the shell's own appearance keys.

    Named rather than drawn, and the reason is scope rather than effort: the launcher, the
    panels, the session menu and the window switcher are the shell's own surfaces with sixty
    leaves between them, and a page that drew all of them would be a second copy of the
    shell's settings window -- one that could not keep up with it. What this page owes a
    person is the knowledge that they exist, what they are, and where they are changed.
    """
    rows: List[Row] = []
    for path in shellkeys.table_keys("shell"):
        rows.append(Row(
            "state", path, source=f"appearance.shell_table_{_slug(path)}",
            icon="preferences-desktop-appearance-symbolic",
            subtitle="Recorded in data/design/noctalia.json, and not drawn here",
            keywords=(path, shellkeys.key_name(path), "table", "shell", "not drawn")))
    if not rows:
        rows.append(Row(
            "state", "No shell table left undrawn", source="appearance.shell_key_count_text",
            icon="object-select-symbolic",
            subtitle="Every key under the shell's own appearance section is a row above",
            keywords=("shell", "tables", "none")))
    return rows


for _path in shellkeys.table_keys("shell"):
    globals()[f"shell_table_{_slug(_path)}"] = _table_reader(_path)
del _path


#: The shell's own theme and wallpaper keys, named here rather than written here.
#:
#: Part 4's acceptance is that every visual switch in the product is reachable, and a key no
#: page mentions is not reachable. But reachability is not ownership: this project writes the
#: shell's colour mode through ``theme.mode`` and its wallpaper through the shell's own
#: picker, so the remaining keys are named with the shape the record gives them and the
#: reason they are not a control on this page.
THEME_WHY = (
    "this project writes the shell's colour mode from theme.colour_mode and leaves the rest "
    "of the shell's palette alone: a palette is chosen by the colour preset, so a row per "
    "palette key would be a second place to disagree with it")
WALLPAPER_WHY = (
    "the wallpaper is the shell's own: this page reads the current one and opens the shell's "
    "picker, because a directory of images and a per-monitor assignment are a file chooser "
    "and a list editor, not a switch")

_THEME_ROWS, _THEME_NAMES = shellkeys.named_rows("theme", PAGE_ID, why=THEME_WHY)
_WALLPAPER_ROWS, _WALLPAPER_NAMES = shellkeys.named_rows("wallpaper", PAGE_ID,
                                                        why=WALLPAPER_WHY)
globals().update(_THEME_NAMES)
globals().update(_WALLPAPER_NAMES)


def shell_theme_why() -> str:
    """Why the shell's palette keys are named and not drawn."""
    return THEME_WHY


def shell_wallpaper_why() -> str:
    """Why the shell's wallpaper keys are named and not drawn."""
    return WALLPAPER_WHY


def shell_key_count_text() -> str:
    """How many of the shell's own keys this page writes."""
    total = len(shellkeys.keys_of("shell"))
    return (f"{total - len(SHELL_ELSEWHERE)} of the shell's {total} own keys are here; the "
            f"{len(SHELL_ELSEWHERE)} about the clipboard and telemetry are on the Features "
            f"page")

#: The three values ``theme.colour_mode`` accepts, straight out of
#: ``data/schemas/settings.schema.json``. Written here rather than read from the
#: schema because the schema is a *check* and this is an *offer*: a mode added to the
#: enum without a label here would be a value the file accepts and the page cannot
#: show, which is the failure the coverage test in ``tests/test_settings_pages.py``
#: exists to catch.
COLOUR_MODES: Tuple[Tuple[str, str], ...] = (
    ("light", "Light"),
    ("dark", "Dark"),
    ("auto", "Follow the desktop"),
)


# --------------------------------------------------------------------- readers


def document() -> Dict[str, Any]:
    try:
        return config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return {}


def preset_tiles() -> List[Dict[str, Any]]:
    """One tile per colour preset that has a file, in a stable order.

    The tile carries what ``themes.thumbnail`` reads out of the preset itself -- the
    colours, the accent roles, the mode and the words -- so a tile cannot show a
    swatch the preset does not define, and a preset whose file is broken is skipped
    rather than drawn empty.
    """
    tiles: List[Dict[str, Any]] = []
    for preset_id in themes.preset_ids():
        try:
            data = themes.thumbnail(preset_id)
        except themes.ThemesError:
            continue
        tiles.append({
            "id": preset_id,
            "label": str(data.get("name") or preset_id.replace("-", " ").title()),
            "description": str(data.get("description") or ""),
            "mode": str(data.get("mode") or ""),
            "colours": dict(data.get("colours") or {}),
            "accent": dict(data.get("accent") or {}),
            "swatches": [list(pair) for pair in themes.swatches(preset_id)],
        })
    return tiles


def intensity_choices() -> List[Tuple[str, str]]:
    """The four intensities as ``(id, label)`` pairs, in the tokens' own order."""
    return [(name, themes.intensity_label(name)) for name in themes.intensity_ids()]


def intensity_description() -> Optional[str]:
    """The description of the intensity in use, for the row's subtitle."""
    intensity = str((document().get("theme") or {}).get("intensity") or "")
    return themes.intensity_description(intensity) if intensity else None


def accent_value() -> Optional[str]:
    """The accent override in the file, or ``None`` when the preset's own is in use."""
    value = str((document().get("theme") or {}).get("accent") or "")
    return value or None


def accent_is_set() -> bool:
    """The banner condition: a value in the file that nothing reads."""
    return accent_value() is not None


def accent_text() -> str:
    """What the accent row says, which is the refusal rather than a colour."""
    value = accent_value()
    if value is None:
        return "following the colour preset's own accent role"
    return f"{value} is in the file, and {control.refusal_for('theme.accent')}"


def contrast_text() -> Optional[str]:
    """The contrast gate's verdict for the preset in use, in one line.

    The gate is what ``iarch-theme apply`` refuses on, so a warning here and a refusal
    there cannot disagree: they are the same program's answer about the same palette.
    """
    preset = str((document().get("theme") or {}).get("colour_preset") or "")
    if not preset:
        return None
    outcome = themes.contrast_report(preset)
    if outcome.verdict != runner.OK:
        return f"the contrast gate could not be run: {outcome.reason}"
    lines = [line.strip() for line in outcome.stdout.splitlines() if line.strip()]
    return lines[0] if lines else "the contrast gate answered nothing"


def wallpaper_text() -> Optional[str]:
    """The wallpaper the shell reports, or ``None`` when it does not answer."""
    value, _why = noctalia.wallpaper()
    return value


def shell_missing() -> bool:
    return runner.which(runner.NOCTALIA_BIN) is None


def theme_tool_outcome() -> str:
    """Whether the renderer this page depends on can be run at all."""
    return themes.tool_outcomes().get("theme", "iarch-theme could not be asked about")


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Appearance page, as data."""
    spec = registry_page(PAGE_ID)

    colour = Group(
        "Colour",
        Row("flow", "Colour preset", setting="theme.colour_preset",
            tiles_source="appearance.preset_tiles", icon="view-grid-symbolic",
            subtitle="Every palette in data/design/presets, each one already through "
                     "the contrast gate",
            style_classes=("iarch-glass-tile",),
            keywords=("palette", "preset", "colour", "color", "theme", "swatch")),
        Row("combo", "Light or dark", setting="theme.colour_mode",
            choices=tuple(COLOUR_MODES), icon="display-brightness-symbolic",
            subtitle="One value, two projections: the shell's mode and GTK's "
                     "prefer-dark-theme key, written together",
            keywords=("dark", "light", "mode", "auto", "night", "day")),
        Row("state", "Accent", icon="preferences-desktop-appearance-symbolic",
            source="appearance.accent_text",
            subtitle="Not offered as a switch, and the reason is in the value",
            keywords=("accent", "colour", "highlight")),
        description="The preset decides every colour in the session; the mode decides "
                    "which of its two palettes is drawn.",
        style_classes=("iarch-glass-card",),
    )

    glass = Group(
        "Glass",
        Row("combo", "Intensity", setting="theme.intensity",
            choices_source="appearance.intensity_choices", icon="view-conceal-symbolic",
            subtitle="The blur recipe, the shadow and every surface opacity, chosen "
                     "together",
            keywords=("intensity", "glass", "frosted", "crystal", "soft", "performance",
                      "blur")),
        Row("state", "What the intensity means", icon="dialog-information-symbolic",
            source="appearance.intensity_description",
            keywords=("intensity", "description", "blur", "opacity")),
        Row("state", "Contrast gate", icon="dialog-warning-symbolic",
            source="appearance.contrast_text",
            subtitle="The same gate iarch-theme apply refuses on",
            keywords=("contrast", "accessibility", "wcag", "ratio", "gate")),
        description="Blur, shadows and opacity are one decision, so they are one row. "
                    "The individual leaves are overrides, and they live on the Glass "
                    "page.",
    )

    wallpaper = Group(
        "Wallpaper",
        Row("state", "Current wallpaper", icon="folder-pictures-symbolic",
            source="appearance.wallpaper_text",
            subtitle="Read from the shell, which owns it",
            keywords=("wallpaper", "background", "image", "picture")),
        Row("button", "Open the shell's own settings",
            action="noctalia.open_shell_settings", icon="go-next-symbolic",
            subtitle="The shell picks, scales and crossfades the wallpaper; this "
                     "window would only be a second place to set it",
            keywords=("wallpaper", "shell", "settings", "background")),
        description="Deliberately not a switch: a wallpaper set here and a wallpaper "
                    "set in the shell are two opinions about the same desktop.",
    )

    shell_groups = []
    for title, rows in _SHELL_ROWS.items():
        shell_groups.append(Group(
            title, *rows,
            description="The shell's own keys, read and written through its IPC: its corner "
                        "radius and borders are not this project's tokens, and its font "
                        "family is not the GTK one on the Fonts & Icons page."
            if not shell_groups else "",
        ))

    shell_groups.append(Group(
        "The shell's palette, named and not written",
        Row("expander", "Six keys", rows=tuple(_THEME_ROWS), icon="view-conceal-symbolic",
            subtitle="Named so that nothing the record declares is unreachable, and not drawn "
                     "because the colour preset already chooses a palette",
            keywords=("theme", "shell", "palette", "named", "not written")),
        Row("state", "Why they are not controls here", icon="dialog-information-symbolic",
            source="appearance.shell_theme_why", keywords=("theme", "palette", "why")),
        description=THEME_WHY,
    ))

    shell_groups.append(Group(
        "The shell's wallpaper, named and not written",
        Row("expander", "Twelve keys and one table", rows=tuple(_WALLPAPER_ROWS),
            icon="view-conceal-symbolic",
            subtitle="Named for the same reason, and the shell's own picker is the button "
                     "above",
            keywords=("wallpaper", "shell", "named", "not written", "automation")),
        Row("state", "Why they are not controls here", icon="dialog-information-symbolic",
            source="appearance.shell_wallpaper_why", keywords=("wallpaper", "why", "picker")),
        description=WALLPAPER_WHY,
    ))

    shell_groups.append(Group(
        "The shell's own surfaces",
        Row("expander", "Tables named and not drawn", rows_source="appearance.shell_table_rows",
            icon="preferences-desktop-appearance-symbolic",
            subtitle="The launcher, the panels, the session menu and the window switcher: the "
                     "shell's own settings window changes them",
            keywords=("shell", "launcher", "panel", "session", "window switcher", "tables")),
        Row("state", "How many keys this page writes", icon="preferences-desktop-appearance-symbolic",
            source="appearance.shell_key_count_text",
            keywords=("shell", "keys", "count", "appearance")),
        Row("button", "Open the shell's own settings",
            action="noctalia.open_shell_settings", icon="go-next-symbolic",
            subtitle="The escape hatch the record describes, for a key this project has not "
                     "verified a range for",
            keywords=("shell", "settings", "open", "escape hatch")),
        description="Nothing the record declares is dropped: a key this page writes is a row "
                    "above, and a table it does not draw is named here with the place that "
                    "does.",
    ))

    return PagePlan(
        PAGE_ID, spec.label, colour, glass, wallpaper, *shell_groups,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card", "iarch-glass-preview"),
        banners=(
            Banner("The shell's binary is not on PATH, so the mode cannot be sent to "
                   "it and the wallpaper cannot be read. GTK still gets the key.",
                   kind="warning", icon="dialog-warning-symbolic",
                   when="appearance.shell_missing"),
            Banner("An accent override is in the settings file, and no renderer reads "
                   "it: the sheets take the accent from the colour preset.",
                   kind="warning", icon="dialog-warning-symbolic",
                   when="appearance.accent_is_set"),
        ),
        header_actions=(
            Row("state", "The renderer", icon="preferences-system-symbolic",
                source="appearance.theme_tool_outcome",
                subtitle="iarch-theme is what applies everything on this page",
                keywords=("tool", "renderer", "iarch-theme")),
        ),
    )
