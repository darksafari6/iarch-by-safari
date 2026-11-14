# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Glass page: one leaf at a time, on top of an intensity.

The intensity is the decision and it lives on Appearance; this page is the exceptions.
An override says "this leaf, this value, on top of whatever the intensity decided",
and clearing it returns to the intensity exactly -- which is why every row here writes
into ``glass.leaves`` rather than into a second copy of the intensity, and why the
derived coarse switches are recomputed by the same change
(:func:`iarch_settings.services.control.derived`).

Two honest limits are built into the page rather than hidden by it:

* **A leaf override is session state.** It is applied to the running compositor with
  ``hyprctl`` and remembered in ``settings.json``, but the compositor's own config
  still holds the intensity's value, so a config reload -- or a login that does not
  start this application -- gets the intensity's value back. The banner below says so
  in those words, because the alternative is a slider that appears to persist and
  does not.
* **A per-window opacity rule is not session state.** It is rendered into
  ``.config/hypr/generated/glass.lua`` and the compositor is asked to re-parse, so it
  survives a relogin the way a leaf override does not. The two kinds of row look
  alike and behave differently, and the difference is written on each group.

What a row shows is the *effective* value: the override when there is one, otherwise
what the compositor answers for that leaf, otherwise nothing -- ``None``, which the
renderer draws as *unverified* rather than as a number it made up.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from ..services import config_store, hypr, themes
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "glass"

#: The leaves this page offers as overrides, each with the row kind that suits it and
#: the words a person reads. The names are ``data/design/tokens.json``'s own
#: ``hyprland.leaves`` spellings and the bounds are its ``hyprland.ranges``, so a leaf
#: that does not exist or a bound that does not match is caught by
#: :meth:`iarch_settings.pages.plan.Row.problems` against the record rather than by a
#: compositor config error at login.
LEAF_ROWS = (
    # (leaf, kind, title, subtitle)
    ("decoration:blur:enabled", "switch", "Blur",
     "The whole blur recipe; with it off, the other blur rows change nothing"),
    ("decoration:blur:size", "scale", "Blur radius",
     "How far the blur reaches, in the compositor's own units"),
    ("decoration:blur:passes", "scale", "Blur passes",
     "How many times the compositor blurs; more passes are smoother and cost more"),
    ("decoration:blur:vibrancy", "scale", "Blur vibrancy",
     "How much colour the blurred surface keeps"),
    ("decoration:shadow:enabled", "switch", "Shadows",
     "The drop shadow under a window"),
    ("decoration:shadow:range", "scale", "Shadow range",
     "How far the shadow reaches from the window"),
    ("decoration:rounding", "spin", "Corner radius",
     "The window corner radius, in pixels"),
    ("decoration:active_opacity", "scale", "Focused window opacity",
     "How see-through the window with focus is"),
    ("decoration:inactive_opacity", "scale", "Unfocused window opacity",
     "How see-through every other window is"),
    ("decoration:dim_inactive", "switch", "Dim unfocused windows",
     "Darken a window that loses focus, rather than only making it see-through"),
    ("decoration:dim_strength", "scale", "Dim strength",
     "How much darker an unfocused window becomes"),
)


def _slug(leaf: str) -> str:
    return leaf.replace(":", "_")


def document() -> Dict[str, Any]:
    try:
        return config_store.document()
    except (config_store.ConfigStoreError, OSError):
        return {}


def overrides() -> Dict[str, Any]:
    """``glass.leaves`` as it stands, or an empty dict."""
    leaves = (document().get("glass") or {}).get("leaves")
    return dict(leaves) if isinstance(leaves, dict) else {}


def _effective_reader(leaf: str) -> Callable[[], Any]:
    """Build the zero-argument reader one leaf's row shows.

    A row names a function and the renderer calls it with nothing, so a reader per
    leaf is the only shape that works; building them from one factory keeps the eleven
    readers from being eleven chances to get the order of the fallbacks wrong. The
    order is the meaning of the row: **your override, then what the compositor
    answers, then nothing.**
    """

    def read() -> Any:
        if leaf in overrides():
            return overrides()[leaf]
        value, _why = hypr.get_option(leaf)
        return value

    read.__name__ = f"effective_{_slug(leaf)}"
    read.__doc__ = f"The effective value of ``{leaf}``: the override, else the session."
    return read


# Eleven module-level readers, one per row above. The names are what the plan resolves.
effective_decoration_blur_enabled = _effective_reader("decoration:blur:enabled")
effective_decoration_blur_size = _effective_reader("decoration:blur:size")
effective_decoration_blur_passes = _effective_reader("decoration:blur:passes")
effective_decoration_blur_vibrancy = _effective_reader("decoration:blur:vibrancy")
effective_decoration_shadow_enabled = _effective_reader("decoration:shadow:enabled")
effective_decoration_shadow_range = _effective_reader("decoration:shadow:range")
effective_decoration_rounding = _effective_reader("decoration:rounding")
effective_decoration_active_opacity = _effective_reader("decoration:active_opacity")
effective_decoration_inactive_opacity = _effective_reader("decoration:inactive_opacity")
effective_decoration_dim_inactive = _effective_reader("decoration:dim_inactive")
effective_decoration_dim_strength = _effective_reader("decoration:dim_strength")

#: Which reader belongs to which leaf, so the plan below cannot pair a row with the
#: wrong one and so a test can assert that every row in :data:`LEAF_ROWS` has a reader.
READERS: Dict[str, Callable[[], Any]] = {
    leaf: globals()[f"effective_{_slug(leaf)}"] for leaf, _kind, _title, _sub in LEAF_ROWS
}


def leaf_row(leaf: str, kind: str, title: str, subtitle: str) -> Row:
    """One override row, with its bounds read out of the tokens rather than typed."""
    bounds = themes.slider_bounds(leaf) or (0.0, 1.0)
    integer = themes.is_integer_leaf(leaf)
    common: Dict[str, Any] = {
        "setting": f"glass.leaves.{leaf}",
        "source": f"glass.effective_{_slug(leaf)}",
        "subtitle": subtitle,
        "keywords": tuple(part for part in leaf.replace(":", " ").replace("_", " ").split()),
    }
    if kind == "switch":
        return Row("switch", title, **common)
    if kind == "spin":
        return Row("spin", title, minimum=bounds[0], maximum=bounds[1], step=1.0,
                   unit="px", **common)
    return Row("scale", title, minimum=bounds[0], maximum=bounds[1],
               step=1.0 if integer else 0.01, **common)


def leaf_rows() -> List[Row]:
    """Every override row, built from :data:`LEAF_ROWS` and the tokens."""
    return [leaf_row(leaf, kind, title, subtitle)
            for leaf, kind, title, subtitle in LEAF_ROWS]


def override_count() -> str:
    """How many overrides are in force, for the group's own summary row."""
    count = len(overrides())
    if not count:
        return "no overrides: every value below is the intensity's own"
    return f"{count} override{'s' if count != 1 else ''} on top of the intensity"


def compositor_missing() -> bool:
    """The banner condition: no compositor means nothing can be applied live."""
    return not hypr.in_session()


def config_errors_text() -> Optional[str]:
    """What the compositor says about its own configuration, or ``None``."""
    errors, why = hypr.config_errors()
    if errors is None:
        return None if not why else why
    return ", ".join(errors) if errors else "the compositor parsed its configuration cleanly"


def opacity_entries() -> List[Dict[str, Any]]:
    """``glass.per_app_opacity`` as a list of dicts, or an empty list."""
    entries = (document().get("glass") or {}).get("per_app_opacity")
    return [dict(entry) for entry in entries if isinstance(entry, dict)] if entries else []


def opacity_rows() -> List[Row]:
    """One pair of rows per per-window rule that already exists.

    Adding and removing a rule is the window's job, not the plan's: it needs a dialog
    and a class name typed into it, and a plan row cannot carry either. What the plan
    can express -- and does -- is every rule that is already in the file, editable in
    place, with the same bounds the generator enforces. The rules are emitted after
    the token groups and before the fullscreen rule, so a person's own choice beats a
    group default and a fullscreen window stays opaque whatever it says here.
    """
    rows: List[Row] = []
    for index, entry in enumerate(opacity_entries()):
        rows.append(Row(
            "entry", f"Window class {index + 1}",
            setting=f"glass.per_app_opacity.{index}.class",
            value=str(entry.get("class") or ""),
            icon="view-conceal-symbolic",
            subtitle="A plain class name or a simple regex body; the generator anchors "
                     "it, so no ^ or $ here",
            placeholder="firefox",
            keywords=("window", "class", "rule", "opacity", "app")))
        rows.append(Row(
            "scale", f"Opacity for {entry.get('class') or index + 1}",
            setting=f"glass.per_app_opacity.{index}.opacity",
            value=float(entry.get("opacity") or 1.0),
            minimum=0.0, maximum=1.0, step=0.01,
            subtitle="1.0 is fully opaque, which is what a browser or a video player "
                     "should stay",
            keywords=("opacity", "transparency", "window", "class")))
    if not rows:
        rows.append(Row(
            "state", "No per-window rules",
            source="glass.opacity_summary",
            subtitle="Add one with the button in this page's title bar; the classes "
                     "this project already groups are in the tokens, and a rule here "
                     "outranks them",
            icon="list-add-symbolic",
            keywords=("opacity", "window", "class", "rule")))
    return rows


def opacity_summary() -> str:
    """The rules in one line, for the state row and for the expander's subtitle."""
    entries = opacity_entries()
    if not entries:
        return ("no per-window rules, so every window gets the opacity its group in "
                "the tokens gives it")
    return "; ".join(f"{entry.get('class')} at {float(entry.get('opacity') or 0):.2f}"
                     for entry in entries)


def intensity_text() -> Optional[str]:
    """The intensity in force, named here and changed on Appearance."""
    intensity = str((document().get("theme") or {}).get("intensity") or "")
    return themes.intensity_description(intensity) if intensity else None


def intensity_label() -> Optional[str]:
    intensity = str((document().get("theme") or {}).get("intensity") or "")
    return themes.intensity_label(intensity) if intensity else None


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The Glass page, as data."""
    spec = registry_page(PAGE_ID)

    leaves = Group(
        "Compositor effects",
        Row("state", "Intensity in force", icon="view-conceal-symbolic",
            source="glass.intensity_label",
            subtitle="Changed on the Appearance page; every value below is an "
                     "exception to it",
            keywords=("intensity", "frosted", "crystal", "soft", "performance")),
        Row("state", "Overrides", icon="edit-clear-symbolic",
            source="glass.override_count", keywords=("override", "leaves", "count")),
        Row("expander", "Blur, shadow, corners and opacity",
            rows=tuple(leaf_rows()), icon="view-conceal-symbolic",
            subtitle="One leaf at a time, with the bounds the compositor's own parser "
                     "accepts",
            keywords=("blur", "shadow", "radius", "opacity", "dim", "override", "leaf")),
        description="An override is applied to the running compositor and remembered "
                    "here. The compositor's own configuration still holds the "
                    "intensity's value, so a reload or a login without this "
                    "application returns to it.",
        style_classes=("iarch-glass-card",),
    )

    per_app = Group(
        "Per-window opacity",
        Row("expander", "Window rules this project adds", rows_source="glass.opacity_rows",
            icon="view-conceal-symbolic",
            subtitle="Rendered into the compositor's glass module and reloaded, so "
                     "these survive a relogin",
            keywords=("opacity", "window", "class", "rule", "app", "per app")),
        Row("state", "The rules in force", icon="dialog-information-symbolic",
            source="glass.opacity_summary", keywords=("opacity", "rules", "summary")),
        description="A browser or a video player should stay opaque: translucent page "
                    "content and translucent video are both unreadable, which is why "
                    "the tokens pin those groups to 1.0 and a rule here is how one "
                    "window is exempted from its group.",
    )

    session = Group(
        "What the compositor answers",
        Row("state", "Configuration errors", icon="dialog-error-symbolic",
            source="glass.config_errors_text",
            subtitle="hyprctl configerrors, asked after every change this page makes",
            keywords=("config", "errors", "hyprctl", "parse")),
        description="The check that closes the loop: a value this page wrote is only "
                    "applied if the compositor parsed the configuration it produced.",
    )

    return PagePlan(
        PAGE_ID, spec.label, leaves, per_app, session,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card", "iarch-glass-preview"),
        banners=(
            Banner("No compositor session was found. An override is still written to "
                   "the settings file, but nothing can be applied to a session and "
                   "every value below reads as unverified.",
                   kind="warning", icon="dialog-warning-symbolic",
                   when="glass.compositor_missing"),
        ),
        header_actions=(
            Row("state", "The intensity behind these values",
                icon="dialog-information-symbolic", source="glass.intensity_text",
                keywords=("intensity", "description", "blur", "shadow")),
        ),
    )
