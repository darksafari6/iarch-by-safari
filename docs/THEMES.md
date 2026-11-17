# Session themes

Part 2 ships six colour presets on the existing `iarch-theme apply` path. Part 1 was the contract only.

`iarch/cli/theme.py` already re-renders Hyprland glass, the Noctalia palette, GTK 3, GTK 4, Kvantum and kitty colours from one preset, then reloads. These six are presets in `data/design/presets/`. They are not a second command.

## Apply

```bash
python3 iarch/cli/theme.py apply greenhouse
python3 iarch/cli/theme.py apply amber-bloom
python3 iarch/cli/theme.py apply neon-rain
python3 iarch/cli/theme.py apply forest-night
python3 iarch/cli/theme.py apply violet-glass
python3 iarch/cli/theme.py apply crimson-silk
```

The saved choice is still the settings key `theme.colour_preset`, which `iarch-theme apply` already reads. `data/themes/ids.json` names the six ids. It does not replace that key.

## What one apply changes today

From the preset, the same generators the other six presets already use:

- Noctalia palette: bar, dock, Control Center, notification cards, lock screen colours
- GTK 3 and GTK 4 accent, and the Kvantum accent
- Kitty colours, written from `terminal.colors` (background, foreground, cursor, selection, color0–15)
- Wallpaper path recorded on the preset (a wallpaper this repository already generated)
- Hyprland blur, rounding and opacity for the intensity that preset names (`frosted`, `crystal` or `soft`)

Contrast is gated at the same floors as the older presets, including the test margin (text at least 4.6:1, UI at least 3.4:1).

## What a preset cannot change yet

`data/schemas/preset.schema.json` sets `additionalProperties` to false. A fish prompt, a notification sound, a font family, or a Control Center layout that is not already a token is refused by the schema, so this part does not invent those fields.

Those surfaces stay on the global tokens until a later part extends the schema and the generator together:

- Fish and Starship
- Notification sound and volume
- Font family
- Per-theme bar layout, dock visibility and animation curves beyond the intensity the preset already selects

Game mode and focus mode are unchanged. They still override the active preset and restore it when they turn off.

## Files

| Path | Role |
| --- | --- |
| `data/design/presets/<id>.json` | The preset `iarch-theme apply <id>` reads |
| `.config/noctalia/palettes/iarch-<id>.json` | Generated palette, written by `render_noctalia.py --write-repo-default` |
| `data/themes/ids.json` | The closed list of six ids |

Do not edit a palette by hand. Change the preset and run `python3 iarch/cli/render_noctalia.py --write-repo-default`.
