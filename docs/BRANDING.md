# Branding and credit policy

This is the rule set for names. It exists because the session is built on other people's
excellent software, and because a desktop that shows three different product names looks
unfinished.

## The product

| | |
| --- | --- |
| Product name | **iArch by Safari** |
| Short form | iArch |
| Identifier (paths, file stems) | `iarch` |
| Maintainer | Safari |
| License | GPL-3.0-only, text in [`LICENSE.txt`](../LICENSE.txt) |

These values are defined once, in [`branding/product.env`](../branding/product.env). Shell scripts
source that file; Python reads it through [`tools/iarch_brand.py`](../tools/iarch_brand.py). Do not
hardcode the product name in a new file — read it.

## Rule 1 — the everyday UI says iArch by Safari

Everywhere a person looks while using the desktop, the product is iArch by Safari:

bar · launcher · dock · Control Center · notifications · lock screen · greeter and session menu ·
system information output (fastfetch) · terminal greeting · settings pages · keybind descriptions ·
window titles of our own tools · output of `scripts/*.sh`

Upstream project names and previous product names (`minimaOS`, `minimaLinux`, `minimaDots`) do not
appear on those surfaces. `python3 tools/branding_lint.py` enforces this and is part of CI. It
extracts **display strings only**, so a command such as `noctalia msg panel-toggle launcher` or a
path such as `~/.config/minimalinux` is not a violation, while a label reading
"Open minimaOS Control Center" is.

Two levels apply:

- **product** — previous product names *and* the upstream shell name are banned. Used where the
  product speaks for itself: keybind descriptions, terminal greeting, system-information labels,
  session menu entries, window titles.
- **identity** — only previous product names are banned. Used where naming a probed executable is
  factual and useful, such as diagnostics reporting that the shell binary is missing.

Run `python3 tools/branding_lint.py --surfaces` to see exactly which files are scanned, which are
not, and why.

## Rule 2 — credit lives in exactly two places

1. [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)
2. Settings → About → Open-source licenses (in progress; see [ROADMAP.md](ROADMAP.md))

Both are rendered from [`branding/notices.json`](../branding/notices.json), so they cannot disagree.
Nothing else in the product carries third-party credit — not the bar, not the launcher, not the
lock screen, not the system information output.

This removes names from the UI, never from the record:

- `LICENSE.txt` stays exactly as it is.
- Copyright and license headers inside files stay.
- License files that ship with third-party code stay.
- The vendored plugin keeps its `manifest.json` author and license fields.
- The installer keeps its contributor line.

`tests/test_branding.py` fails if any of those disappear.

### Adding third-party credit

1. Add a component to `branding/notices.json`: name, kind, purpose, upstream, license, copyright,
   and the repository paths that use it.
2. If the license or the rights are not established, write `TODO(verify)` and add an id to
   [UNVERIFIED.md](UNVERIFIED.md). Never guess a license; an invented SPDX id is worse than an open
   question. `tools/notices.py` rejects a `TODO(verify)` license with no verification id, and
   rejects a `used_by` path that does not exist.
3. Run `python3 tools/notices.py --write` and commit the regenerated file.

## Rule 3 — documentation and code stay accurate

Technical documentation (`README.md`, `InstallNotes.md`, `docs/**`), installer code and developer
tooling name upstream projects where that is the accurate thing to say: you cannot explain a shell
configuration format without naming the shell. Rule 1 covers what the user sees in the session, not
what a maintainer reads in a file.

## Rule 4 — never invent a key, an API or a capability

Configuration keys, IPC commands and CLI flags must be verified against the upstream release the
repository targets. If something cannot be verified, the code carries `TODO(verify)` and the claim
is recorded in [UNVERIFIED.md](UNVERIFIED.md). A feature that the platform does not support is not
faked, not stubbed with a dead control, and not described as working.

## Identifiers for new components

Everything this project authors from here on uses the `iarch` prefix, and the
values live in `branding/product.env` so tools and docs cannot drift apart:

| Kind | Convention | Example |
| :--- | :--- | :--- |
| Binary or service | `iarch-<purpose>` | `iarch-settings`, `iarch-theme`, `iarch-keybinds`, `iarch-doctor` |
| User configuration | `~/.config/iarch/` | never inside another program's directory |
| Desktop application id | reverse-DNS of the owner domain | `dev.safari.iarch` |
| Shell functions and env switches | `iarch::` / `IARCH_` | `iarch::backup`, `IARCH_DRY_RUN` |
| Palette and profile ids | `iarch-<name>` | `iarch-midnight`, `profiles/performance.toml` |

A convention becomes a path only when the component ships; until then it is a
name reserved in `branding/product.env`, and no code may hardcode it twice.

## Frozen identifiers

Some identifiers keep a previous name because programs match on them. Renaming them would orphan
already-installed systems. The full list and the reasoning are in
[ARCHITECTURE.md](ARCHITECTURE.md#frozen-legacy-identifiers). In short: paths, launcher names, the
managed-file marker line, generated include names and comments inside generated files stay as they
are; anything rendered on screen changes.

## Checklist for a new UI string

1. Read the name from `branding/product.env` instead of typing it.
2. Keep the string short enough for the surface it lands on.
3. Describe the action, not the implementation ("Open Control Center", not "Call panel-toggle").
4. Run `python3 tools/branding_lint.py`.
5. If the string credits someone, stop — that belongs in `branding/notices.json` instead.
## Copyright headers

New files in this repository start with the header defined once in
`branding/product.env` as `IARCH_COPYRIGHT_HEADER`:

```
Copyright (C) 2026 Safari — GPL-3.0-or-later
```

- Shell, Python and TOML files carry it as a comment on the first line after any shebang.
- JSON has no comments, so `data/**/*.json` carries it as the `_copyright` key.
- Files that already existed keep whatever header they have; vendored upstream code under
  `legacy/` keeps its own copyright untouched, and `tests/test_copyright_headers.py` fails if
  this repository's header is ever stamped into `legacy/`.
- `IARCH_LICENSE_ID` is the SPDX expression `GPL-3.0-or-later`. `LICENSE.txt` carries the GNU
  GPL version 3 text, whose "any later version" option is what the header relies on. Prose for
  people ("licensed under GPL-3.0") is fine; machine-readable fields use the SPDX expression.

Third-party credit is generated, not written by hand: edit `branding/notices.json`, then run
`python3 tools/notices.py --write`. That renders both `THIRD_PARTY_NOTICES.md` for people and
`data/licenses.json` for the settings app's About page, so the two can never drift. A license
that could not be read from a reachable upstream is written as `TODO(verify)` and must point at
an id in [UNVERIFIED.md](UNVERIFIED.md); guessing is refused by `tools/notices.py --check`.
