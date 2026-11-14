<!-- Copyright (C) 2026 Safari — GPL-3.0-or-later -->

# The design system

One file holds the numbers: `data/design/tokens.json`. Everything that draws — the session
sheets, the compositor rules, the lock screen, the settings window — resolves a role in that
file rather than choosing a value, and every resolution is checked by a test.

That is the whole system. The rest of this document is what falls out of it.

## Why a token file and not a theme

A theme is a set of values somebody picked. A token file is a set of values with a reason
attached, and the reason is what stops the next person from picking a different one. The
test suite compares each rendered artifact against the token it claims to resolve, so a
number that appears in a stylesheet, a Lua rule or a Python file without a token behind it
is a failure rather than a style choice.

The consequence is narrow and deliberate: changing how glass looks is editing one file and
re-rendering. Changing how glass looks *in one place* is not possible, because no place
holds a number of its own.

## Roles, not sizes

A radius is never used directly. `tokens.json:radius` holds both the scale and the roles
that point into it:

| Scale | | Roles | |
| :--- | :--- | :--- | :--- |
| `xs` | 8 | `window` | → `md` |
| `sm` | 12 | `panel` | → `lg` |
| `md` | 16 | `card` | → `md` |
| `lg` | 24 | `button`, `input` | → `sm` |
| `pill` | 999 | `tooltip` | → `xs` |
| `check` | 6 | | |

`pill` is 999 rather than a computed half-height because a radius larger than half the
element's height is clamped by everything that renders one, so 999 means "as round as this
shape can be" at any size without a second rule for small pills and large ones.

The same indirection is in `spacing` (`xs` 4, `sm` 8, `md` 12, `lg` 16, `xl` 24, `xxl` 32),
in `motion` (`fast_ms` 120, `normal_ms` 220, `slow_ms` 380, with four named bezier easings),
in `layout` (`gaps_in` 6, `gaps_out` 12, `float_gaps` 8, `border_size` 1) and in `font`
(Inter for the interface, Inter Display for headings, JetBrainsMono Nerd Font for code, six
sizes from 11 to 28, four weights, a line height of 1.45, and a fallback chain that names a
family per script rather than one generic family for every script).

The settings window reads these too. The gap between a sidebar row's icon and its label is
`spacing.sm`, read out of the token file at build time by
`iarch_settings/widgets/window.py:sidebar_spacing()` — a Python file is not exempt from the
rule that applies to the stylesheet.

## Intensity is the only place translucency is decided

`tokens.json:intensities` holds four bundles — `crystal`, `frosted`, `soft` and
`performance` — and `default_intensity` names `frosted`. Each bundle carries the
compositor's blur parameters, its shadow parameters, and a `glass` block of five alphas:

| | `frosted` | what it is for |
| :--- | :--- | :--- |
| `tint_alpha` | 0.34 | a surface that carries no text of its own |
| `tint_alpha_strong` | 0.48 | a surface that has to carry a heading over whatever is behind it |
| `border_alpha` | 0.18 | the hairline that separates two translucent surfaces |
| `highlight_alpha` | 0.1 | the tint that means "this is the chosen one" |
| `shadow_alpha` | 0.36 | a shadow that is not the compositor's |

Changing intensity is the only supported way to change how translucent the session is, and
it changes every surface at once. That is why the settings window's Glass page offers
eleven leaf overrides *on top of* an intensity rather than eleven independent controls: a
leaf row shows the value the current intensity produces, and writing to it puts an override
in `~/.config/iarch/settings.json` above that value. The row and the write are two different
questions, and answering both from the settings file would hide the intensity's own value
behind an override nobody has set.

`window_opacity` is separate and is not an intensity: it is what the compositor's own window
rules apply per application class, from 0.82 for a terminal to 1.0 for a browser and a video,
with `iarch_app` at 0.88. `app_classes.iarch_app` is the list of anchored window classes
that get it, and it includes `^dev\.safari\.iarch\.settings$` — the settings window's own
application id, so the window that changes these values is itself subject to them.

A window rule can carry `opacity` and it cannot carry `blur`: the compositor's rule effects
have `no_blur` and no positive `blur`, so the blur behind a window comes from the intensity's
`decoration:blur` and from `blur:ignore_opacity`, which is what lets it show through a 0.88
alpha. `SET-01` in [UNVERIFIED.md](UNVERIFIED.md) records that nobody has looked at the two
meeting.

## The seven classes

`iarch/settings-app/iarch_settings/style/glass.css` defines exactly seven, all prefixed
`iarch-`:

| Class | What it is |
| :--- | :--- |
| `.iarch-glass-card` | the card a group of rows sits on |
| `.iarch-glass-hero` | the Home page's one pane-of-glass surface |
| `.iarch-glass-sidebar` | the pane carrying the fifteen page names |
| `.iarch-glass-tile` | one tile in a grid, with `:hover`, `:checked` and `:focus-visible` |
| `.iarch-glass-preview` | a read-only surface a page draws a sample on |
| `.iarch-highlight` | the tint that means "this matched" or "this is chosen" |
| `.iarch-reduce-motion` | not a surface: the class that removes the transitions |

Every other class in the application belongs to libadwaita and is styled by libadwaita or by
the session sheet. Restyling `card` or `boxed-list` here would change a widget the
application does not own, in a way that survives a change of intensity.

Four things the sheet deliberately does not contain, each with the reason in a comment beside
the rule that would have used it:

- **No number it chose.** Every radius, alpha, duration, easing, padding and border width
  resolves to a token, checked by `tests/test_settings_glass.py`.
- **No colour literal.** Every colour is a named colour libadwaita defines, so the sheet
  follows the colour preset and the light and dark mode without being re-rendered, and a
  person who changes accent does not have to find this file.
- **No `backdrop-filter` and no `filter`.** The blur behind the window is the compositor's.
  Blurring inside the widget would blur the application's own text instead of the desktop
  behind it, and would cost an offscreen buffer per frame.
- **No box-shadow with an offset or a blur.** Every shadow here is an inset hairline, which
  is a border drawn as a shadow, or the focus ring's 2px spread, which casts nothing. The
  drop shadow under a window is the compositor's, and a second one here would double it under
  a tiling compositor.

## Reduce motion is a class, and the reason is a version number

GTK's own published property table puts CSS Media Queries at "Since GTK 4.20". The floor this
project argues for is GTK 4.10, because that is where `GtkFileDialog` appears. On 4.10 to
4.18 an `@media` block is a parse error, and `gtkcssprovider.c` documents that parsing errors
are never fatal and parsing resumes — so the sheet would still load, the block would still do
nothing, and a person who asked their desktop for less motion would get every fade this window
has. The refusal and its evidence are in `data/design/adwaita.json:rejected`.

So the window adds `.iarch-reduce-motion` itself, from two readings that stay separate:
`animation.reduce_motion` in this project's settings file, and the desktop's
`gtk-enable-animations` out of the person's own `settings.ini`. A person who asked their
desktop for no motion gets no motion from this window whatever the settings file says. Under
that class every transition duration and delay is 0ms.

[docs/MOTION.md](MOTION.md) records the same rule for the session sheets, which is where an
`@media` query is still used and still carries that version caveat.

## Contrast is a gate, not a preference

`python3 iarch/cli/contrast_check.py` takes no arguments and gates: every preset has to clear
4.5:1 for text and 3:1 for non-text interface elements. It is the one design check that can
fail a build rather than describe a state, and it exists because translucency is a contrast
decision — a tint over an unknown background is a foreground colour nobody chose.

## The toolkit contract

`data/design/adwaita.json` is what the interface is allowed to name: 46 widget entries, 58
API entries, 51 style classes, the CSS properties GTK 4 parses, the named colours libadwaita
defines, and the pseudo-classes. Each carries the header and line it was read from at a
pinned ref, and `tests/test_settings_surface.py` reads every `Gtk.*` and `Adw.*` attribute
access out of the package's syntax trees and fails on one the record does not carry.

Two floors, both argued from the newest API in use rather than from what a distribution
happens to ship: GTK 4.10, where `GtkFileDialog` appears, and libadwaita 1.6, where
`AdwBanner` appears. The binding itself is not pinned, and `SET-06` says why.

The `portability` block is the part that saves the next reader a round trip: calls whose
spelling differs between supported releases, what the difference is, and which spelling this
project uses. `gtk_css_provider_load_from_data` takes `(data, length)` at 4.10 and `(bytes)`
at 4.12, so one spelling cannot work on both and the file spelling is the one used.
`GtkStyleContext` is deprecated per-widget but not per-display: attaching a provider to one
widget's context is in `gtk/deprecated/` and marked deprecated at 4.10, while
`gtk_style_context_add_provider_for_display` is in `gtk/gtkstyleprovider.h` and is not
deprecated at all.
