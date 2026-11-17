# Session themes

iArch's six session themes are complete data packs. The data pack is the only
place a per-theme value is defined; the files under `~/.config` are projections
written by the theme renderer.

## The six packs

| ID | Name | Character |
| --- | --- | --- |
| `greenhouse` | Greenhouse | Warm copper over dark wood; slow, soft slide |
| `amber-bloom` | Amber Bloom | Gold on near-black; fast motion and a small pop bounce |
| `neon-rain` | Neon Rain | Violet and electric pink; medium slide and fade |
| `forest-night` | Forest Night | Quiet green on charcoal; short fade and no workspace slide |
| `violet-glass` | Violet Glass | Translucent violet glass; long blur and fade |
| `crimson-silk` | Crimson Silk | Coral-red glass and folder gold; slow pop-in and fade |

The closed ID list and repository default are in `data/themes/ids.json`.
The default is `forest-night`; that default is used only when no user choice
exists.

## Source files and schema

- `data/themes/schema.json` is the JSON Schema contract. It rejects unknown
  keys, out-of-range values, malformed colors and paths that do not match the
  theme ID.
- `data/themes/<id>.json` owns the theme's metadata, wallpaper and notification
  sound paths, Hyprland decoration, motion, Noctalia palette and layout hints,
  GTK and Kvantum accent, Kitty palette, Starship palette name and overview
  style/geometry hints.
- `~/.config/iarch/theme.json` is the user's selection and has exactly this
  shape: `{"id":"<id>"}`. It is not copied into generated files as a default.
- `tools/render_theme.py` renders the saved selection. It does not change the
  selection and does not reload a running session.

Validate a pack after editing it:

```bash
python3 -m json.tool data/themes/greenhouse.json >/dev/null
python3 -m json.tool data/themes/schema.json >/dev/null
python3 -m unittest tests.test_session_themes
```

When `jsonschema` is installed, the renderer validates the pack against
`data/themes/schema.json` before it writes anything. Its structural and path
checks still run without that optional Python package.

## Commands

```bash
iarch-theme list
iarch-theme current
iarch-theme apply greenhouse
iarch-theme apply amber-bloom
iarch-theme apply neon-rain
iarch-theme apply forest-night
iarch-theme apply violet-glass
iarch-theme apply crimson-silk

# Render the saved choice without reloading a running session:
python3 tools/render_theme.py
```

`apply` writes `~/.config/iarch/theme.json`, renders the selected pack and
then asks the running components to reload. The saved ID is not written back
to repository defaults and a later installer render reads, rather than resets,
the saved choice.

## Generated targets

| Target | What the renderer writes |
| --- | --- |
| `hypr/generated/theme.lua` | Border colors/size, rounding, gaps, shadow, blur, inactive opacity and dim; named bezier curve and window/workspace/fade/border/layer animation leaves |
| `noctalia/palettes/iarch-active.json` | A custom palette in the same dark/light and terminal shape as the shipped `iarch-*.json` palettes |
| `noctalia/config.toml` | Selects `iarch-active`; updates only existing theme, bar, dock, Control Center, notification, shell-animation and audio keys |
| `kitty/theme.conf` | Foreground, background, cursor, selection and all sixteen ANSI colors |
| `starship.toml` | Selects the named palette and replaces only the marked iArch palette block |
| `gtk-3.0/gtk.css`, `gtk-4.0/gtk.css` | Replaces only the marked iArch accent block; the existing generated glass sheets stay intact |
| `Kvantum/iarch/iarch.kvconfig` | Updates supported `[GeneralColors]` color values in the existing theme |
| `iarch/sounds/active-notify.ogg` | A symlink to the selected pack's notification sound, when that asset exists |

The Hyprland loader requires `generated.theme` after the existing glass fallback.
The Kitty include is last in `kitty.conf`, so the active theme colors win over
the base terminal include.

Reload order is compositor (`hyprctl reload`), Noctalia (`noctalia msg
config-reload`), wallpaper (`noctalia msg wallpaper-set` when the selected file
exists), and Kitty remote `set-colors` only when `KITTY_LISTEN_ON` identifies
a socket. When the Noctalia config-reload IPC cannot be reached, the renderer
may restart the Noctalia shell process only; it never restarts Hyprland or the
desktop session. It does not run `pw-play`.

## Modes and unsupported surfaces

Game mode remains an overlay: while `modes.game.active` is recorded, rendering
keeps the selected pack but disables its compositor blur/shadow and motion.
When game mode is turned off, the active `theme.json` selection is rendered
again. Focus mode keeps its dim and Do Not Disturb state across a theme reload;
if a theme changes during focus mode, focus-off's saved dim restore point is
updated to the newly selected theme.

The `overview.style`, `overview.rounding`, `overview.gap` and
`overview.dim_inactive` values are validated and carried into the generated
Hyprland file as explicit tokens. The pinned Noctalia/Hyprland configuration
does not expose a verified bento/tiles/pills overview styling interface for
these values, so they are not presented as an active overview implementation.
No second window manager or shell widget is created to imitate one.

The six pack files reserve these original asset paths:

- `assets/wallpapers/themes/<id>.webp`
- `assets/sounds/<id>/notify.ogg` (and an optional `urgent.ogg`)

Those binary assets are not part of this renderer change. Until a selected file
exists, the renderer warns and leaves the current wallpaper/sound link alone;
it does not reuse screenshot artwork or synthesize an uncredited asset. No
notification audio is played by `iarch-theme apply`.

## Editing rules

1. Edit `data/themes/<id>.json`, not generated CSS, Lua, TOML, Kitty or Kvantum
   files.
2. Keep the ID list at exactly the six entries above.
3. Keep values inside the schema and use only Noctalia keys/widgets recorded in
   `data/design/noctalia.json`.
4. Re-render with `python3 tools/render_theme.py` after changing the currently
   selected pack. Apply a different pack with `iarch-theme apply <id>`.
5. Do not change `theme.json` during a renderer-only operation.
