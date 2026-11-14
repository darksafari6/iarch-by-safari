<!-- Copyright (C) 2026 Safari — GPL-3.0-or-later -->

# The settings application

`iarch/settings-app/` is a GTK 4 window with fifteen pages, and it is the only part of this
repository that draws an interface. Everything else renders a file the session reads.

It is built in five layers, and each one is only allowed to know about the layer under it:

```
data/design/*.json     what the machine and the toolkit actually accept   (records)
        ↓
iarch_settings/services/   the only modules that touch the machine        (14)
        ↓
iarch_settings/pages/      what a page shows, as data                      (15 + plan)
        ↓
iarch_settings/widgets/    how a row becomes a widget                      (renderer, window, app)
        ↓
scripts/iarch-settings.sh  how a person starts it
```

A record is a claim about something outside this repository, with the line it was read
from. A service is the only code allowed to run a command, open a socket or write a file
this project does not own. A page is a list of rows and nothing else. The renderer turns a
row into a widget and a row's `action` string into a call. The window owns the toolkit.

## The rules, and what each one is for

**A page never touches the machine.** `pages/plan.py` defines `Row` with no callback field
and no widget field, so a plan cannot smuggle behaviour past a check: it can only carry
names. A name resolves through `Context.resolve()`, which accepts a module only if it is
listed in `services.MODULES`, `pages.MODULES` or `PACKAGE_MODULES` — four modules that
read and never act. That list is the mechanism, not a convention; a row that pointed at
`os.system` would raise before it drew anything.

**A plan is data a test reads.** All fifteen pages are built at import time by
`tests/test_settings_surface.py` and `tests/test_settings_pages.py`, which together check
495 rows for the properties that make a row honest: a `link` row has an address, a `state`
row reads something, a `spin` or `scale` row has bounds, a `combo` row has choices, an icon
name is one the record carries, and every settings path a row names is one of the 34 that
exist. A page that could only be checked by running it would be a page nobody checks.

**One mechanism per intention.** Where two ways to do a thing exist, this application uses
one and says why it refused the other. The refusals are on screen, not in a comment: the
Fonts page names `gtk-theme-name` and `gtk-enable-animations` and explains that the theme
is applied by `iarch-theme` and that reduce motion is `animation.reduce_motion`, so a
second writer would be a second source of truth. The Startup page names
`X-GNOME-Autostart-enabled` — a key the session's own generator has never heard of, so a
switch built on it would appear to work and change nothing. The Display page names the
seventeen monitor fields it will not write, each with the reason.

**Not answering is not answering no.** Every reader distinguishes three states, and the
third is the one that matters: `ok`, `failed`, and `unverified` for a binary that is not
installed, a compositor that is not running, a file that cannot be read. A row that drew
`None` as "off" would show a person a switch that is not off. `services/runner.py` keeps
`exit_code` separate from `verdict` because an unregistered compositor subcommand exits 0
and a shell verb that answers `ok` can still have done nothing, so neither an exit code nor
a reply string is a verdict on its own.

**The stylesheet chooses no number.** `style/glass.css` defines seven classes, all prefixed
`iarch-`, and every radius, alpha, duration, easing, padding and border width in it resolves
to a token in `data/design/tokens.json`. `tests/test_settings_glass.py` checks each one
against the token, so the sheet cannot drift into being the second place the design
system's numbers live. It contains no colour literal either — every colour is a named colour
libadwaita defines, so the sheet follows the colour preset and the light and dark mode
without being re-rendered.

## Starting it

```
scripts/iarch-settings.sh              # the window
scripts/iarch-settings.sh --describe   # the version and which typelib is missing
python3 -m iarch_settings              # the same program, without the wrapper
iarch-settings                         # the console script pyproject.toml declares
```

All four end at `iarch_settings.widgets.app.main`, and it returns an exit status rather than
raising. On a machine with no usable toolkit it prints one sentence naming the missing
typelib and the package that provides it on each of the two distributions this project
installs on — `python-gobject` on Arch, `python3-gobject` on Fedora — and exits 1, because
"cannot import gi" is not something a person can act on.

The package is not installed to be run; `PYTHONPATH` is how the launcher finds it.
`iarch/settings-app/pyproject.toml` exists for the one component a person starts by name,
and declares no dependency: PyGObject is the distribution's own binding, built against its
own GTK 4 and libadwaita, and a wheel of it would be a binding for a toolkit version this
project did not choose.

## What it is built against

`data/design/adwaita.json` is the toolkit contract, and it is checked rather than trusted.
`tests/test_settings_surface.py` reads every `Gtk.*` and `Adw.*` attribute access out of the
package's syntax trees and fails if the record does not carry it — 46 widget entries and 58
API entries, each with the header and line it was read from at a pinned ref (GTK 4.10.0,
libadwaita 1.7.12). The floor is GTK 4.10 because that is where `GtkFileDialog` appears, and
libadwaita 1.6 because that is where `AdwBanner` appears; nothing here needs 1.7 even though
1.7.12 is the ref the API was read from.

The record also carries a `rejected` block, which is the part that stops the next reader
re-litigating a decision. CSS media queries are refused because GTK's own property table
puts them at "Since GTK 4.20" and an `@media` block on 4.10 to 4.18 is a parse error that
`gtkcssprovider.c` documents as never fatal — so the sheet would still load, the block would
still do nothing, and a person who asked their desktop for less motion would get every fade
this window has. Custom properties are refused for the same kind of reason: `--prop` and
`var()` are 4.16, so `@define-color` is the portable spelling. Reduce motion here is a class
the window adds, from two readings that stay separate: `animation.reduce_motion` in this
project's own settings file, and the desktop's `gtk-enable-animations` out of the person's
`settings.ini`.

## What is not proven

Ten items, `SET-01` to `SET-10` in [UNVERIFIED.md](UNVERIFIED.md). The short version: no
sandbox has a display, a compositor, a browser, a shell binary or a battery, so nothing here
has been *looked at*. What has been checked is that every name is one an upstream header
carries at the pinned ref, that every number resolves to a token, that every refusal is a
sentence a person can read, and that a machine missing a binary says "unverified" rather
than "off". What has not been checked is that the window is translucent, that the motion is
smooth, that the portfolio button opens a browser, that a restore is visible without a
reopen, and that the desktop entry reaches a menu.

`SET-02` is the one that matters most: a *misused* API — a property set with the wrong type,
a signal connected with the wrong signature — is only caught by running it, and it has never
been run.
