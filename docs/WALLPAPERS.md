# Wallpapers

Where the art comes from, who owns it, how it is regenerated, and how your own
pictures fit in.

## What ships

| Preset | File | Kind | Notes |
| :--- | :--- | :--- | :--- |
| Midnight Glass | `assets/wallpapers/generated/midnight-glass.webp` | generated | mesh gradient, seed 20260101 |
| Frosted Light | `assets/wallpapers/generated/frosted-light.webp` | generated | mesh gradient, seed 20260102 |
| Aurora | `assets/wallpapers/generated/aurora.webp` | generated | aurora drapes, seed 20260103 |
| Mono Ice | `assets/wallpapers/generated/mono-ice.webp` | generated | radial glow, seed 20260106 |
| Crimson Plasma | `assets/wallpapers/desktop-red.webp` | bundled | the red image this repository already shipped |
| Tokyo Night Glass | `assets/wallpapers/desktop-tokyo-night.webp` | bundled | the Tokyo Night image this repository already shipped |

Generated art is 3840x2160 WebP and each file is inside a 600 KB budget; in
practice they land between 25 KB and 50 KB, because a smooth field compresses
hard. The two bundled images are **never rendered and never modified** by the
generator -- `iarch/cli/gen_wallpapers.py --check` only confirms the files they
point at still exist. Their PNG originals remain under
`assets/wallpapers/originals/`, and their provenance is recorded in
`THIRD_PARTY_NOTICES.md`.

## Regenerating

```sh
python3 -m venv /tmp/imgvenv && /tmp/imgvenv/bin/pip install Pillow
/tmp/imgvenv/bin/python iarch/cli/gen_wallpapers.py            # all generated presets
/tmp/imgvenv/bin/python iarch/cli/gen_wallpapers.py --preset aurora
/tmp/imgvenv/bin/python iarch/cli/gen_wallpapers.py --check    # verify what ships
/tmp/imgvenv/bin/python iarch/cli/gen_wallpapers.py --dry-run  # report, write nothing
```

The render is seeded end to end: the gradient field comes from
`random.Random(seed)` and the grain from a second generator derived from the same
seed, so the same preset JSON produces the same file with the same Pillow and
libwebp. That is what lets `--check` be a *contract* check (present, 4K, WebP,
inside budget, nothing orphaned) rather than a byte comparison: byte-identical
output across machines would additionally depend on the libwebp build, which is
not something this repository controls. `tests/test_wallpapers.py` asserts that
two renders in one process are byte-identical, and that changing the seed is not.

If Pillow is missing the CLI exits 2 with the install hint instead of a
traceback, and the test suite skips rather than fails. Rendering is only needed
to *change* the art; a normal install uses the committed files and needs nothing.

Each preset describes its own gradient in `data/design/presets/<id>.json` under
`wallpaper.generate`: a `style` (`mesh`, `aurora`, `radial`, `diagonal`,
`plasma`), two to six `stops`, a `seed`, a `grain` amount and a `vignette`
strength. Editing those values and re-running the generator is the whole
workflow; there is no hand-edited binary in the repository.

Generated artwork is project artwork and carries the project licence,
GPL-3.0-or-later. Pillow, the imaging library the generator imports, is
MIT-CMU licensed and credited in `THIRD_PARTY_NOTICES.md`.

## Your own wallpapers

Put them in `~/Pictures/Wallpapers`. That directory is what Noctalia's wallpaper
picker reads, and the settings this design system writes point the shell at it.

The relevant Noctalia v5.4.1 keys, read from `src/config/schema/config_schema.cpp`
(`wallpaperSchema()`) and `src/config/config_types.h` at tag `v5.4.1`:

| Key | Values | Meaning |
| :--- | :--- | :--- |
| `wallpaper.enabled` | bool | whether the shell draws a wallpaper at all |
| `wallpaper.directory` | path | the folder the picker reads |
| `wallpaper.directory_light` | path | per-mode override for light mode |
| `wallpaper.directory_dark` | path | per-mode override for dark mode |
| `wallpaper.fill_mode` | `center`, `crop`, `fit`, `stretch`, `repeat`, `span` | how the image is scaled |
| `wallpaper.transition` | `diamond`, `disc`, `fade`, `golden`, `honeycomb`, `melt`, `pixel`, `stripes`, `vortex`, ... | transition effect on change |
| `wallpaper.transition_duration` | 100-30000 ms | how long that transition runs |
| `wallpaper.edge_smoothness` | 0-1 | softening of the image edge |
| `wallpaper.transition_on_startup` | bool | animate the first wallpaper |
| `wallpaper.per_monitor_directories` | bool | one folder per monitor |
| `wallpaper.monitor.<name>` | sub-table | per-monitor overrides, matched by `match` |

Two honest notes on that table. First, upstream states that `[wallpaper]` *also*
carries app-managed state -- the currently selected wallpapers, per-monitor
choices -- which the config service reads separately and which is **not** part of
the schema; do not hand-write those keys, change the selection in Noctalia
Settings instead. Second, nothing in this repository's shipped
`.config/noctalia/config.toml` sets a wallpaper path today, and
`hyprland.lua` sets `force_default_wallpaper = 0` to keep Hyprland's own
placeholder off the screen; the preset's `wallpaper.path` is therefore the file
the design system names as that preset's background, and wiring it into
`[wallpaper]` is Task 5 work with the keys above. `docs/UNVERIFIED.md` UI-03
tracks the one thing still unproven: that writing `wallpaper.directory` in
`config.toml` is honoured by an installed build rather than overridden by GUI
state (`~/.local/state/noctalia/settings.toml` wins over `config.toml`, see
UI-01's sibling behaviour).

To use your own image with a preset, copy it into `~/Pictures/Wallpapers`, then
in Noctalia Settings pick it, or edit the preset:

```json
"wallpaper": {
  "kind": "bundled",
  "path": "assets/wallpapers/generated/my-own.webp",
  "credit": "Photograph by me, taken 2026-04."
}
```

and place the file where the preset says. `kind: "generated"` is reserved for art
the generator can reproduce from `wallpaper.generate`; if your image is a
photograph or someone else's work, it is `bundled`, and the `credit` field is
where its licence and author go, so `THIRD_PARTY_NOTICES.md` stays the single
place third-party art is credited.

## Sizes and hygiene

The 600 KB budget exists because this repository spent Part 1 deleting 8.5 MB of
PNG that had been committed by accident. WebP at 4K with quality stepped down
until the file fits keeps generated art in the tens of kilobytes. If a future
style needs more detail than a smooth field, raise the budget deliberately in
`iarch/cli/gen_wallpapers.py` and say why in the commit message; do not raise it
silently.
