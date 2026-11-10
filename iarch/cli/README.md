# iarch/cli — command line tools

Generators that are shipped and tested today. Each one reads the design tokens or
a preset, renders a configuration file, and can verify what it previously wrote:

| Command | Renders | Checks |
| :--- | :--- | :--- |
| `python3 iarch/cli/contrast_check.py` | nothing — it gates | that every preset clears 4.5:1 for text and 3:1 for non-text UI |
| `python3 iarch/cli/gen_wallpapers.py` | `assets/wallpapers/generated/*.webp` | that the shipped art is 4K, WebP, inside 600 KB and rendered by some preset |
| `python3 iarch/cli/gen_glass_lua.py` | `~/.config/hypr/generated/glass.lua` | that the committed default matches a fresh render of the tokens |
| `python3 iarch/cli/gen_animations_lua.py` | `~/.config/hypr/generated/animations.lua` | that the committed default matches a fresh render of the motion tokens |
| `python3 iarch/cli/render_noctalia.py` | `~/.config/noctalia/config.toml` and its palette | that the committed shell config and all six palettes match a fresh render |
| `python3 iarch/cli/render_gtk_css.py` | `~/.config/gtk-4.0/gtk.css` and `~/.config/gtk-3.0/gtk.css` | that the committed sheets match a fresh render of the tokens |
| `python3 iarch/cli/render_kvantum.py` | `~/.config/Kvantum/kvantum.kvconfig` and `~/.config/Kvantum/iarch/iarch.kvconfig` | that the committed theme matches a fresh render of the tokens |
| `python3 iarch/cli/gen_fontconfig.py` | `~/.config/fontconfig/fonts.conf` | that the committed file matches a fresh render of the tokens |
| `python3 iarch/cli/theme.py apply [PRESET]` | all of the above at once, under the live `~/.config`, from one preset and intensity | the contrast gate before it writes, then skips any file whose rendered bytes already match |
| `python3 iarch/cli/theme.py current` | nothing — it reports | which preset and intensity an `apply` would use, and where it would write |

Every command exits 0 on success, 1 when the repository or the host is out of
step — for `iarch-theme`, a preset the contrast gate refuses — and 2 on a usage
or data error. None of them starts a desktop or edits a file it did not generate.
The per-surface generators never shell out; `iarch-theme` imports their render
functions and shells out only to ask the running compositor and shell to reload,
guarded so a missing binary is a warning rather than a failure.

Six of them also refuse to write what the upstream project would not read.
`gen_glass_lua.py` checks every key against the Hyprland config leaves, which
error out on an unknown key. `gen_animations_lua.py` checks every leaf, curve and
style against `data/design/animations.json`, the animation tree read out of the
same release, because Hyprland refuses the whole config on an unknown leaf, an
unregistered curve or a style that leaf does not accept — and it derives every
`speed` as `duration_ms / 100` rather than picking a number by hand.
`render_noctalia.py` checks against
`data/design/noctalia.json`, extracted from the shell's own schema at a recorded
release, because that side is forgiving in the wrong direction: an unknown
setting only warns and is ignored, and an out-of-range number is clamped with a
warning, so a mistake there ships as a design that silently does not match the
tokens. `render_gtk_css.py` does the same against `data/design/gtk.json`, which
keeps the GTK 4 and GTK 3 surfaces apart because they are not the same language:
`backdrop-filter`, `filter`, `transform` and `@media` exist only in GTK 4, and
`transition-property` is checked against the properties GTK actually declares
animatable, since a shorthand there interpolates nothing. `render_kvantum.py` does
the same against `data/design/kvantum.json`, every key `ThemeConfig.cpp` reads at a
recorded release, because Kvantum is forgiving the same way: QSettings parses an
unknown key and the engine ignores it, and an integer outside its bound is clamped.
`gen_fontconfig.py` does the same against `data/design/fontconfig.json`, the
configuration DTD, because fontconfig warns about an element it does not know and
keeps loading, and a family no installed font provides is silently skipped.
A render that does not
validate is refused before anything is written, and a write that fails part way
through puts every file back byte for byte. `iarch-theme apply` runs all six
renderers and the contrast gate before it writes anything, so one command is
refused if any single surface — or the palette's contrast — would be, and its
write across the nine files is all-or-nothing the same way. See
`docs/GTK-NOTES.md`, `docs/KVANTUM-NOTES.md` and `docs/FONTS.md`.

The commands still to come are `iarch-keybinds`, `iarch-anim` and `iarch-doctor`.
Each one reads user state through `iarch.lib.configstore` and writes only
generated files, under the contract in `iarch/lib/renderers.py`.

Nothing here may be renamed to an older product name; the conventions live in
`branding/product.env`.
