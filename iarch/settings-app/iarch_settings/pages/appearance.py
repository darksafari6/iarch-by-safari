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
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "appearance"

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

    return PagePlan(
        PAGE_ID, spec.label, colour, glass, wallpaper,
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
