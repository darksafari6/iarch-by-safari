# Kvantum notes

The Qt half of the glass design system is a [Kvantum](https://github.com/tsujan/Kvantum)
theme, rendered from the same tokens, presets and intensities as the compositor,
the shell and the GTK overlays. `iarch/cli/render_kvantum.py` writes two files:

* `~/.config/Kvantum/kvantum.kvconfig` — the pointer, a single top-level `theme=`
  key that tells Kvantum which theme to load;
* `~/.config/Kvantum/iarch/iarch.kvconfig` — the theme: a `[%General]` section
  with the compositor and translucency decisions, and a `[GeneralColors]` section
  with all 28 colours Kvantum reads, each mapped from a role in the preset's
  palette.

Both ship in the repository under `.config/Kvantum/`, are staged into the v5
payload, and are checked in CI with `render_kvantum.py --check`.

## Why this is a renderer and not two INI files

Kvantum hides its mistakes the same way GTK and Noctalia do. It reads a theme
with `QSettings`, which parses generic INI: a key `ThemeConfig.cpp` never asks
for is read and then ignored, with no warning, and an integer outside its
documented bound is clamped and continues. A hand-written theme can therefore
look complete and be half-applied — a misspelled `reduce_window_opacity` does
nothing, a `menu_blur_radius=40` is silently cut to 10 — and nothing tells the
user. So the theme is rendered and gated: `render_kvantum.py` refuses to write a
key that is not in `data/design/kvantum.json`, an integer outside its recorded
bound, or an enum value outside its set.

## What was verified, and against what

Kvantum is pinned to the release tag **V1.1.9**, not `master`, so a key cannot be
emitted that the installed release does not read.

| Recorded in `data/design/kvantum.json` | Source |
| :--- | :--- |
| 89 `[%General]` keys, 28 `[GeneralColors]` keys, 23 `[Hacks]` keys | every `getValue(KSL("Group"),KSL("key"))` call site in `Kvantum/style/themeconfig/ThemeConfig.cpp` |
| each key's type (bool, int, string, colour, enum) and integer bounds | the type and range column of `Kvantum/doc/Theme-Config` |
| `dialog_button_layout` enum 0–5 and its meanings | `Kvantum/doc/Theme-Config` |
| the 28 colour keys and their order | `ThemeConfig.cpp`'s `getColorSpec` |
| the Qt style names are `kvantum` and `kvantum-dark` | `Kvantum/style/kvantum.json` |
| an INI-only theme still resolves element art | `Kvantum/style/themeconfig/defaulttheme.qrc` (a compiled-in default SVG) |
| the pointer reads `theme` as a top-level key, and `[Applications]` for per-app overrides | `Kvantum/style/Kvantum.cpp` |

The `[%General]` sizing keys the theme writes — `menu_separator_height=10`,
`scroll_width=12`, `slider_width=8`, `check_size=13`, `layout_margin=4` — are
Kvantum's own verified defaults, so the theme does not silently resize widgets
away from what the default theme ships. `layout_spacing` is lifted from its
default of 2 to 4 (still inside the 2–16 bound) so widgets in a translucent
window are not packed edge to edge.

## Running under Hyprland, not KDE

Two decisions come from the compositor this desktop actually uses, and both are
recorded in the surface file's `compositor` block so they are not mistaken for
omissions:

| Key | Written | Why |
| :--- | :--- | :--- |
| `blurring`, `popup_blurring` | `false` | Kvantum's screen blur needs the KDE blur effect and a supporting GPU. Hyprland provides neither, so the frosted look is a translucent interior plus the compositor blur in `.config/hypr/generated/glass.lua`. |
| `shadowless_popup` | `true` | Hyprland already shadows popups through `decoration:shadow`. A second Kvantum shadow would double the one the compositor draws — the same split that puts the GTK 4 drop shadow in `glass.lua` rather than the stylesheet. |
| `menu_shadow_depth`, `tooltip_shadow_depth` | `0` | They go to zero with `shadowless_popup`. |
| `composite` | `true` | Wayland is always composited, so translucent menus and tooltips are available; what varies is how translucent each surface is. |
| `menu_blur_radius`, `tooltip_blur_radius` | `2` | These are **not** screen blur: they round the corners of a translucent popup when compositing, to avoid artifacts. The documentation recommends 2. |

Translucency is driven entirely by `reduce_window_opacity` and
`reduce_menu_opacity`, derived from the intensity's `qt` opacities in
`data/design/tokens.json`: a surface the tokens want kept at 88% fill becomes a
12% reduction (`round((1 − 0.88) × 100)`), clamped to the documented 0–90 bound.
`translucent_windows` follows the reduction, so the Performance intensity — where
every `qt` opacity is 1.0 — writes `reduce_window_opacity=0`,
`reduce_menu_opacity=0` and `translucent_windows=false`, and the theme is fully
opaque. The documentation states window translucency needs either a translucent
SVG element or a nonzero `reduce_window_opacity`; this theme is INI-only, so it
uses the latter.

## INI-only: no SVG

This project ships no custom SVG. Kvantum compiles in a default theme image
(`defaulttheme.qrc`), so a `.kvconfig` with no art of its own still resolves
every element; the file only recolours it through `[GeneralColors]` and re-tunes
it through `[%General]`. Rounded corners and the blur behind a window come from
the compositor, exactly as they do for the GTK 3 overlay, rather than from
per-widget SVG art.

## Activation

Kvantum is a Qt **style**, chosen in qt6ct (or Kvantum Manager), which writes the
choice into `~/.config/qt6ct/qt6ct.conf`. It is deliberately **not** activated
with `QT_STYLE_OVERRIDE`: qt6ct detects that variable and asks the user to remove
it. `startup.lua` already sets `QT_QPA_PLATFORMTHEME=qt6ct`, so the platform
theme is qt6ct and the style is whatever qt6ct is told to use — set it to
`kvantum` once and every Qt 6 application picks up this theme. Kvantum must be
installed for the style to exist (see `docs/UNVERIFIED.md`, TP-17, for the
distribution package names).

## Regenerating

```sh
python3 iarch/cli/render_kvantum.py --print                 # the theme, to stdout
python3 iarch/cli/render_kvantum.py --preset aurora --intensity crystal
python3 iarch/cli/render_kvantum.py --write-repo-default    # refresh the shipped payload
python3 iarch/cli/render_kvantum.py --check                 # payload matches a fresh render
```

`iarch-theme apply <preset>` re-renders the theme in place; the pointer keeps
naming `iarch`, so only `iarch.kvconfig` changes. Every render is validated
against `data/design/kvantum.json` before anything is written, and a write that
fails part way through puts every file back byte for byte.
