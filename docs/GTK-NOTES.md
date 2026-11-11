# GTK notes

How the GTK 4 and GTK 3 glass overlays are built, and what was checked against
upstream before any of it was written.

Both sheets are rendered by `iarch/cli/render_gtk_css.py` from
`iarch/lib/templates/gtk4.css.j2` and `gtk3.css.j2`, from the same tokens,
presets and intensities as the compositor and shell renderers. The committed
copies live at `.config/gtk-4.0/gtk.css` and `.config/gtk-3.0/gtk.css`, are
staged into the payload by `lib/stage-v5-config.sh`, and are checked in CI with
`render_gtk_css.py --check --repo`. At install and on `iarch-theme apply` they
are written to `~/.config/gtk-4.0/gtk.css` and `~/.config/gtk-3.0/gtk.css`, the
two files GTK itself reads as a user overlay on top of the active theme.

## Why this is a renderer and not two CSS files

GTK is forgiving in a way that hides mistakes:

* a property it does not know produces a warning and the declaration is dropped,
  so the widget keeps the theme default and the sheet still loads;
* a selector that matches no node or no class is kept and never applies, so a
  rule can be dead on arrival without any message at all;
* `transition-property` naming a property that is not declared
  `GTK_STYLE_PROPERTY_ANIMATED` interpolates nothing.

So a hand-written sheet can look complete and be half-applied, with no error
anywhere. `data/design/gtk.json` records the surface each version actually
parses, and the renderer refuses to write a sheet that uses anything outside it.
A refused render exits 2 and writes nothing; a write that fails part way through
restores every target byte for byte.

## What was verified, and against what

| Recorded in `data/design/gtk.json` | Source |
| :--- | :--- |
| 94 properties, 21 shorthands, 25 pseudo-classes, 47 animatable properties (GTK 4.24.1) | `gtk/gtkcssstylepropertyimpl.c`, `gtkcssshorthandpropertyimpl.c`, `gtkcssselector.c` |
| 85 properties, 20 shorthands, 22 pseudo-classes, 40 animatable properties (GTK 3.24.52) | the same four files at that tag |
| at-rules per version | the `@`-token scan of `gtk/gtkcssprovider.c` |
| 10 colour functions, 11 filter functions, 7 transform functions (GTK 4) | `gtkcsscolorvalue.c`, `gtkcssfiltervalue.c`, `gtkcsstransformvalue.c` |
| 165 node names, 213 style classes (GTK 4 + libadwaita 1.10.0) | `gtk/theme/Default/_common.scss`, `src/stylesheet/widgets/` |
| 101 node names, 162 style classes (GTK 3) | `gtk/theme/Adwaita/_common.scss` plus every `GTK_STYLE_CLASS_*` in `gtk/gtkstylecontext.h` |

Two gaps are recorded rather than papered over. GTK 4 removed
`gtk/gtkstylecontext.h`, so there is no exhaustive list of GTK 4 style classes
to check against; the recorded set is what the GTK 4 default theme and 14 of
libadwaita's 45 widget stylesheets actually style, which proves each class
exists but does not prove the set is complete, and a class missing from it was
not used rather than assumed invalid. And GTK 3 registers the direction
pseudo-class with its argument as a single token — `"dir(ltr)"`, `"dir(rtl)"` —
so `:dir()` is valid there even though no bare `dir` string appears in its
selector source; the GTK 3 Adwaita theme uses it 60 times.

## The two versions are not the same language

| | GTK 4.24.1 | GTK 3.24.52 |
| :--- | :--- | :--- |
| `backdrop-filter`, `filter` | yes, so a popover can blur what is behind it | **absent**; `gtkcssfiltervalue.c` does not exist at this tag |
| `transform` | yes; a pressed button sinks by 2% | absent; a pressed button gets a darker fill |
| `@media` | yes, so the sheet answers `prefers-reduced-motion` | absent, so it cannot |
| focus ring | `:focus-visible` | `:focus` |
| hover / disabled | `:hover`, `:disabled` | both, plus the older `:prelight`, `:insensitive` |
| menus | `popover`, `modelbutton` | `menu`, `menuitem`, `toolbar`, `toolbutton` |
| dialogs | `dialog`, `window.dialog` | `messagedialog` |
| window corners | `window.background`; there is no `decoration` node | `decoration` |

The GTK 3 frosted look therefore comes from a translucent `background-color`
plus the blur the compositor applies through
`.config/hypr/generated/glass.lua`, not from a filter GTK 3 cannot parse. That
is also why the Performance intensity works on both: it sets every GTK opacity
to 1.0 and `blur.enabled` to false, so the GTK 4 sheet emits no
`backdrop-filter` at all and the two sheets converge on the same opaque result.

`decoration` is worth spelling out because it looks like an omission. GTK 4's
`gtkwindow.c` sets only the `window` css name and its default theme keeps only
the `.default-decoration` class, so the GTK 4 sheet puts the corner radius and
the hairline inset shadow on `window.background` and leaves the drop shadow to
the compositor, which already owns `decoration:shadow`. Drawing a second shadow
in GTK would double it under a tiling compositor.

## No `!important`, so cascade order is the only lever

The word `important` does not appear in either `gtkcssprovider.c`. An overlay
cannot force its way past a theme; it wins because
`~/.config/gtk-4.0/gtk.css` is parsed after the theme, so a rule of equal
specificity takes precedence, and a rule that has to beat libadwaita carries at
least libadwaita's specificity. That is why several selectors here are longer
than they need to be for readability — `notebook > header > tabs > tab`,
`headerbar windowhandle .title` — and why nothing relies on `!important`.

## Base theme

The sheets are overlays, not themes: they assume a maintained base and only
change the material. `adw-gtk3` is the base for GTK 3 (already installed by
`install.sh` and credited in `branding/notices.json`), and libadwaita's own
stylesheet is the base for GTK 4 applications. Colours are emitted literally
from the preset rather than referencing `@accent_bg_color`, so a sheet follows
the preset it was rendered from and `iarch-theme apply <preset>` is what changes
it.

## Regenerating

```sh
python3 iarch/cli/render_gtk_css.py --print                 # both sheets to stdout
python3 iarch/cli/render_gtk_css.py --gtk 4 --preset aurora --intensity crystal
python3 iarch/cli/render_gtk_css.py --write-repo-default    # refresh .config/
python3 iarch/cli/render_gtk_css.py --check --repo          # CI's freshness check
```

Requires Jinja2 (`python-jinja` on Arch, `python3-jinja2` on Fedora; the package
names are unverified — `docs/UNVERIFIED.md` TP-16). Without it the renderer
exits 2 and says so, rather than failing with a traceback.

Every property, radius, opacity, duration and easing in a sheet comes from
`data/design/tokens.json` or a preset. The only numbers the renderer holds
itself are in its `SHAPE` table, each with the reason it is what it is, and they
are the ones with no token equivalent — a header bar's minimum height, the 1px
stop of a top highlight, how far a disabled control fades.

See also `docs/DESIGN-SYSTEM.md` for the tokens themselves and
`docs/UNVERIFIED.md` for what still needs a live session.
