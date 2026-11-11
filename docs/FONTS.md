# Fonts, cursor and icon themes

How the desktop's typefaces, pointer theme and icon theme flow from the design
tokens, and what applies each of them.

## Fonts

`iarch/cli/gen_fontconfig.py` renders `~/.config/fontconfig/fonts.conf` from the
`font` block of `data/design/tokens.json`. fontconfig is read by GTK, Qt, Kitty
and most other toolkits regardless of desktop, so this is the
distribution-agnostic way to apply the font tokens: it needs no `settings.ini`,
no gsettings key and no portal, and it behaves the same on Arch and Fedora.

The tokens name upstream *family* names, not package names. The rendered file
fills two generic families and leaves the third alone:

| Generic family | Prefers, in order |
| :--- | :--- |
| `sans-serif` | the UI face (`Inter`), then the whole fallback chain |
| `monospace` | the terminal face (`JetBrainsMono Nerd Font`), then the whole fallback chain |
| `serif` | *left to the system default* — the tokens name no serif face, and inventing one would ship a family the design system never chose |

The fallback chain is the token's `font.fallback` list, in order: `Noto Sans`
(generic sans), `Noto Sans CJK SC` (Han, Hiragana, Katakana, Hangul),
`Noto Naskh Arabic` (Arabic), `Noto Nastaliq Urdu` (Urdu Nastaliq),
`Noto Color Emoji` (emoji) and `DejaVu Sans` (last-resort coverage). Appending
the same chain to both generic families means a glyph the primary face lacks —
a Han character, an Arabic ligature, an emoji — still resolves instead of
falling through to whatever the system default happens to be.

`Inter Display` (`font.ui_display`) needs no generic alias: a heading that asks
for it by name resolves directly if the face is installed.

### Why this is a renderer and not a hand-written fonts.conf

fontconfig hides its mistakes the way the other engines do. It parses a config
with a SAX handler that warns about an element or attribute it does not know and
keeps loading, and a family that matches no installed font is simply never
selected — it falls through to the next preference with no error. A typo
therefore does not fail; it silently drops a rule or degrades to a system
default. So the file is rendered and gated: `gen_fontconfig.py` refuses to write
an element, attribute or enumerated value that is not in
`data/design/fontconfig.json`, or a family the tokens do not name.

The surface is the fontconfig configuration DTD (`fonts.dtd`) at the pinned
mirror commit, with every element, its content model and its attribute
enumerations. fontconfig's DTD is a long-stable interface — every element this
project emits (`fontconfig`, `alias`, `family`, `prefer`) has been unchanged
since well before the pinned 2.13.1 — so the surface pins the mirror commit
rather than a release tag (the upstream mirror carries no tags).

The rendered file has no XML declaration and no DOCTYPE. A leading comment would
stop an `<?xml?>` being the declaration, so there is none, and fontconfig never
loads an external DTD, so the DOCTYPE would be decoration it does not read. The
GENERATED header is an XML comment (`<!-- … -->`), not the `#` a Kitty `.conf`
uses; `configstore` keys that on the `fonts.conf` filename so no other `.conf` in
the payload is affected.

## Cursor theme

The pointer theme is `Bibata-Modern-Classic` at size 24, from each preset's
`cursor` block. `.config/hypr/themes/theme.lua` exports it to every toolkit that
reads a cursor theme from the environment:

```lua
"HYPRCURSOR_THEME,Bibata-Modern-Classic",  -- Hyprland's own cursor
"XCURSOR_THEME,Bibata-Modern-Classic",      -- XWayland and GTK
"QT_CURSOR_THEME,Bibata-Modern-Classic",    -- Qt
```

`theme.lua` holds these as the static export, and every preset in
`data/design/presets/` ships the same `Bibata-Modern-Classic` at 24, so applying
a preset leaves the cursor where it is: `iarch-theme apply` re-renders the
generated config, verifies the chosen preset still names the cursor `theme.lua`
exports, and a `hyprctl reload` re-runs `theme.lua`, which re-exports it (whether
a live session re-applies that export is TP-10). `iarch-theme` does not switch a
*differing* cursor at runtime — there is no verified call for it — so a future
preset that names another cursor would update the static export in `theme.lua`
rather than rely on a runtime switch. Bibata **is** installed on Arch
(`bibata-cursor-theme`, `install.sh:424`); the Fedora package is added but its
name is unverified (`docs/UNVERIFIED.md`, TP-18). An earlier revision of TP-13
wrongly said no installer provided Bibata; that is corrected.

## Icon theme

The icon theme is `Papirus-Dark`, from each preset's `icons` block, which also
lists the alternatives a user can switch to (`icons.available[]`: Papirus dark
and light, Yaru) with their licences and upstreams. `papirus-icon-theme` and
`papirus-folders` are installed on Arch; the Fedora package is added but
unverified (TP-18).

Unlike the cursor theme, the icon theme has no environment variable: GTK reads it
from the `gtk-icon-theme-name` setting (gsettings or a `settings.ini`) and Qt
from its own icon-theme setting. The v5 payload deliberately ships no
`settings.ini` — the legacy v4 one named a v4-only theme, and
`tests/test_v5_staging.py` asserts it stays out — and no other mechanism is
verified against the toolkit releases in use: the `-gtk-icon-theme` in
`data/design/gtk.json` is a CSS property, not the `gtk-icon-theme-name` setting,
and `data/design/kvantum.json` verifies that qt6ct writes the style only. So
`iarch-theme` reports the preset's icon theme and does not set it; the gap is
recorded as TP-19 in `docs/UNVERIFIED.md`.

## Installer packages

fontconfig selects a family only if an installed font provides it, and skips it
silently if not, so the installer has to supply the faces. The two installers
differ in how safely they can carry an unverified package name:

* **Fedora** — `install_dnf_packages` checks each name with `dnf list --available`
  and skips any it cannot find, printing "Skipping unavailable packages". A wrong
  name is therefore harmless, so the assumed Fedora names are added to
  `fedora_install.sh` and verified at install time.
* **Arch** — `install.sh` runs one `pacman -S --noconfirm "${PACKAGES[@]}"` and
  aborts the whole install if any single name is unknown. A wrong name is fatal,
  so the assumed Arch names are recorded in TP-18 rather than added, until
  confirmed against a real Arch system.

The unverified names, and the reason for the asymmetry, are in
`docs/UNVERIFIED.md` (TP-13 for the Nerd Font, TP-18 for the rest).

## Regenerating

```sh
python3 iarch/cli/gen_fontconfig.py --print              # fonts.conf to stdout
python3 iarch/cli/gen_fontconfig.py --write-repo-default # refresh the shipped payload
python3 iarch/cli/gen_fontconfig.py --check              # payload matches a fresh render
```

The rendered file ships at `.config/fontconfig/fonts.conf`, is staged into the v5
payload, and is checked in CI with `--check`. Every render is validated against
`data/design/fontconfig.json` before anything is written, and a write that fails
part way through puts the file back byte for byte.
