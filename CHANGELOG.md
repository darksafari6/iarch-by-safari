# Changelog

Notable changes to iArch by Safari, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the
six-part plan in [`docs/ROADMAP.md`](docs/ROADMAP.md) rather than semantic
versioning, because nothing here is a library anyone links against.

## Unreleased — the keyboard map, and the record that owns it

This is Part 5 of the roadmap: shortcuts as data. Before it, the keyboard map
lived in a hand-written `.config/hypr/keybind.lua` and every report about it —
the documentation, the Settings page — was a second copy that could drift. The
direction is now reversed: one record is the source, and the Lua the compositor
reads, the documentation and the Settings page are all rendered from it.

### Added

- **`data/keybinds.default.json`, version 2** — 80 entries, 77 of them enabled,
  each an `{id, mods, key, action, description, category, enabled, locked}` with
  ids of the form `category.subject`. An override in
  `~/.config/iarch/keybinds.json` carries only the fields it changes, keyed by
  id, so a rebind does not have to restate an action. Validated against
  `data/schemas/keybinds.schema.json`.
- **`data/design/keybinds.json`** — the keyboard surface of the pinned
  compositor, read out of Hyprland v0.57.2's own source rather than transcribed:
  the `hl.bind` signature and its option names, the dispatcher tree with an
  arity per leaf, the bind-option exclusions, and what the compositor does by
  itself when a Lua config fails (`recovery.emergency_mode`).
- **`data/design/noctalia-ipc.json`** — 41 verbs the shell answers on, each with
  its argument shape and the upstream line it was read from, verified against
  noctalia v5.4.1. Verbs this project deliberately does not send are recorded
  with the reason, so "not used" is a decision on the record rather than an
  omission.
- **`data/reference/xkb-keysyms-1.7.0.txt`** — 2 577 keysym names from the
  pinned xkbcommon. Every key a bind may name is checked against it, which is
  how `BackSpace` (capital S) and `period` (not `.`) stop being runtime
  surprises.
- **`iarch/cli/iarch_keybinds.py`** — `generate`, `list`, `check`, `docs`,
  `reset` and a top-level `--check` for CI. `check` is the gate the render runs
  behind: it refuses a key that is not a keysym, a modifier the compositor does
  not know, two binds on one combination, a dispatcher outside the verified
  tree, a noctalia verb outside the record, an exec with no argv, a duplicate
  id, and an override that tried to delete a locked binding.
- **`tools/migrate_keybinds_v2.py`** and **`tools/render_shortcuts.py`** — the
  one-off v1→v2 migration, and the renderer behind `docs/SHORTCUTS.md`.
- **The Shortcuts page** (`iarch/settings-app/iarch_settings/pages/shortcuts.py`)
  now reads the record, so it shows the map that ships rather than a copy of it.
- **A golden fixture pair** (`tests/fixtures/keybinds.golden.{json,lua}`) pins
  the exact Lua a fixed record must produce, so a change to how a command is
  quoted or a description escaped is a diff a person accepts on purpose instead
  of a silent edit to a file the session reads.

- **The mutating subcommands** — `set`, `add`, `disable`, `enable`, `export` and
  `import`, beside the `reset` the recovery combo already needed. Each is one
  change with the same four steps in the same order: validate the map the change
  would produce, confirm where it discards more than was named, back up both
  files, then write both through a temporary file renamed into place — restoring
  both if a write fails halfway, because "validate first" cannot cover a full
  disk. The exit status is the contract: **0** done, **1** refused, cancelled or
  failed to write, **2** bad input. A confirmation with no terminal to answer it
  exits 2 rather than assuming yes, and a batch validates and lands as one change
  so there is no half-disabled map. Input is canonicalised to the pinned spelling
  rather than accepted as typed, so one key cannot end up written two ways.
- **`iarch/cli/iarch_cheatsheet.py`** — the overlay behind `Super+H`, which the
  record had bound to a command that did not exist. It merges the record with your
  override through the same function that renders the compositor's Lua, so it
  cannot show a map the session does not have; groups rows by the record's own
  categories, with reserved and disabled keys held in their own group at the end
  rather than dropped; filters on every term at once, where a single character has
  to be a *key* rather than a letter inside a description, because `super t` has to
  answer with one row and not most of the map; and paints from the shipped
  `midnight-glass` preset, refusing a colour role the preset does not define rather
  than inventing a hex value, so it is the same dark glass and the same neon blue as
  the session it floats over. Fired from a bind it has no terminal, so it decides
  where to draw and says why: the terminal it already has, else the first installed
  of the six the compositor's own emergency mode probes for, in its order, else
  `notify-send`, else stderr and a non-zero exit. In a terminal it waits — `q`
  closes, anything else is read as a new filter and redrawn. `--json` gives the same
  overlay as data. 48 tests cover the model, the grouping, the filter, the palette,
  both renderings and every fallback branch, injected rather than hoped for.
- **`scripts/iarch-keybinds.sh` and `scripts/iarch-link-cli.sh`** — the name the
  recovery bind, the record and the documentation had all been using already. The
  first is a thin launcher that execs the CLI so the exit status passes through
  untouched; the second writes `~/.local/bin/iarch-keybinds` as a generated
  wrapper that names its checkout absolutely. It is idempotent, refuses to touch
  a file it did not write unless `--force` (and backs that file up when it does),
  refuses to run as root, creates the directory, says when it is not on `PATH`,
  and fails loudly with the command to re-run when the checkout is gone.
  `tests/test_cli_launchers.py` runs both for real, then runs `iarch-keybinds
  check` *by name* through the wrapper, and asserts that every name
  `.config/hypr/keybind.lua` probes for with `command -v` is a name the linker
  provides — so the bind and the linker cannot drift apart.

### Changed

- **The Lua is generated, not written.** `.config/hypr/generated/keybinds.lua`
  holds 76 binds and opens with a do-not-edit header naming the command that
  regenerates it. `.config/hypr/keybind.lua` no longer binds anything except the
  recovery combo, and `.config/hypr/hyprland.lua` requires the generated file
  *before* it.
- **`tools/extract_keybinds.py` is gone.** It read the record out of the Lua,
  which is the direction this part reverses; leaving it in place would leave two
  tools claiming to be the source.
- **Super+Shift+E opens the session menu** rather than ending the session.
  `hl.dsp.exit` takes no arguments and runs the moment the key goes down, and
  noctalia's `session logout` does the same, so neither goes on a key: the bind
  is `panel-toggle session`, and `session` is a builtin panel id in noctalia
  v5.4.1 (`src/launcher/panel_catalog.cpp`), which means the shell draws the
  confirmation. `lock` and `suspend` stay bindable because both are undoable.
- **The modifier layers are enforced, not documented and hoped for.** `Super` is
  the primary layer, `Super+Shift` the secondary one, the `Ctrl+Alt` family is
  recovery and system, and `Super+Alt` is kept empty on purpose so a later bind
  has somewhere to go without taking a key from anything. A plain `Ctrl+letter`
  is still refused — and its remedy no longer suggests `Ctrl+Alt`, which the
  layer rule reserves, because a checker that recommends its own next refusal
  sends people in a circle.
- **Seven bindings are locked** by role: close window, lock, exit, open
  terminal, open settings, cheat sheet, power menu. Locked is keyed by id, not
  by key, so a later re-layout of the map cannot quietly drop one. A locked
  binding can be rebound but not deleted, and an override that tries is refused.
- **`Ctrl+Alt+BackSpace` is reserved and never bound.** It is the X11
  kill-server combination; holding the key in the record disabled is what stops
  a future edit taking it.
- **The two mouse-wheel binds are verified, and were verified by being wrong.**
  `Super+mouse_up` and `Super+mouse_down` were carried from the v1 map as an open
  question because neither is a keysym nor a `mouse:N` code. Source settled it:
  the compositor accepts them as *events* (`src/keybinds/Key.cpp:8-10`) and
  dispatches a wheel delta under exactly that name
  (`src/keybinds/Manager.cpp:312-335`), so they bind without ever reaching the
  resolver. The rejection row in `data/design/keybinds.json` was deleted rather
  than annotated and the mechanism recorded as a fifth key form; `check` reports
  two warnings instead of four, and the two limits that came with the finding are
  recorded as well — the names are compared exactly, and only a scroll wheel
  produces them, so a touchpad scroll never fires these binds.
- **`docs/UNVERIFIED.md` now carries a verification log for the keyboard map**,
  listing every upstream file and line range the record cites, at which ref each
  was read, and stating plainly that nothing in the pass was observed on a running
  compositor — there is no Hyprland, no `hyprctl`, no display and no package tool
  here. KB-04 is closed; KB-01, KB-02, KB-03 and KB-05 remain, because each needs
  an observation rather than a reading, and TP-10 still owns the live half of all
  of it.

### Fixed

- **A deployed session was missing a file it requires.**
  `hypr/generated/keybinds.lua` was absent from both the path list in
  `lib/stage-v5-config.sh` and `EXPECTED_PAYLOAD` in `tests/test_payload_map.py`
  — two literal lists that agreed with each other while the installed session
  failed to load a module `hyprland.lua` requires. Added to both, and the
  payload test now derives one side from the load graph so the two cannot agree
  in the same wrong way again.
- **`user_override_path()` asked for `"keybinds.json"`** from a helper that
  appends `.json`, so overrides were written to `keybinds.json.json` and never
  read back. It now passes the bare stem.
- **The conflict check compared key strings exactly**, so `validate()` reported a
  clean map for `SUPER + t` beside `SUPER + T` — two handlers on one key, and
  which runs depends on registration order. The compositor resolves key names with
  `XKB_KEYSYM_CASE_INSENSITIVE` (`src/keybinds/Key.cpp:40`), a fact this
  repository's own record already stated at `key_forms.forms[3]` and the checker
  contradicted. Comparison is case-folded now, and the message says why a spelling
  difference is not a second key. A dead `if key in seen: pass` sitting above it
  went with the fix.
- **`validate()` claimed a check it did not have.** Two docstrings said it refused
  "a locked binding an override tried to delete"; no such branch existed. Locked
  and disabled at once is an error now, added after confirming that no shipped
  entry would newly fail it.
- **Bad input was accepted in three places.** An id with no separator (`custom`,
  where ids are `category.subject`); a keysym in a case the pinned list does not
  contain (`Backspace`, which the compositor resolves but the documentation would
  then show two ways); and a dispatcher leaf with nothing checking it against the
  verified tree. Each is now refused or canonicalised, with the pinned spelling or
  a near-miss suggestion in the message — and each refusal is drift-checked by
  reintroducing the defect and proving a test notices.

### Known gaps

- **The recovery combo is bound, and what it calls now exists — but the bind has
  not fired.** `Ctrl+Alt+R` is hand-written in `.config/hypr/keybind.lua`
  deliberately, because a bind whose job is to repair a broken keyboard map
  cannot live in the file that might be broken, and the compositor's safe-`require`
  (`ConfigManager.cpp:522-527`, `:328-360`) catches a generated file that loads
  and then errors, so the static one still registers. `scripts/iarch-link-cli.sh`
  now puts `iarch-keybinds` on `PATH` and that is tested end to end, so the
  remaining gap is installation rather than code: no installer has been run on a
  machine, and a session started by a display manager does not read a shell
  profile, so whether its `PATH` reaches `~/.local/bin` is unobserved. Until it
  does the bind opens a terminal and says on stderr which command to run. The
  record carries this as an `unverified` note rather than implying a working key,
  and the installer task owns the session `PATH`.
- **`UI-02`, narrowed: the overlay draws in a terminal, not in glass.**
  `Super+H` now runs something real — see Added — but the layer-shell glass
  surface with a search box you type into is still Part 7. The vendored overlay
  plugin cannot be ported (v4 QML against noctalia v5.4.1, which needs
  `plugin.toml` plus a `.luau` entry point), and the settings application cannot
  host it either: a `PagePlan` row deliberately cannot carry behaviour, so a row
  that filtered as you typed is not expressible in it. Nothing was observed on a
  session, because there is no compositor here.
- **Two bindings in the recovery layer are debt.** `Super+Ctrl+Alt+left` and
  `+right` move a window across workspaces, which is not a system action; every
  sensible destination key is already taken, so `check` reports them as warnings
  on every run instead of an invisible exception, and they move with the next
  laying-out of the default map.
- **The Shortcuts page still will not edit the map.** The CLI can, and the page
  reads the same record, but there is no recorder, no action picker and no switch,
  so the collision check is not yet in front of the person making the change.
- **No live reload-and-rollback against a running compositor.** The validation
  before a write and the rollback after a failed one are real and tested; asking
  a running compositor to accept a map, and undoing it if the session does not
  survive, needs a compositor, and this machine does not have one.
## Unreleased — the settings application

This is Part 4 of the roadmap: the glass settings window, the About page's
open-source licences, and the Contact page. No compositor-side value changed, so
nothing a person sees on the desktop moved; what moved is that every switch
Parts 1 to 3 introduced now has an interface, and that the interface is data.

### Added

- **`iarch/settings-app/`**, a GTK 4 + libadwaita application under the id
  `dev.safari.iarch.settings`: 42 Python modules in five layers — `pages/`
  describes, `services/` answers, `widgets/` draws, `style/` styles, and the
  package root holds the paths, the version, the toolkit probe and the
  translation install.
- **The plan, which is the whole interface.** `pages/plan.py` defines `Row`,
  `Group`, `Banner`, `Tile`, `Context` and `PagePlan`; fifteen page modules
  build 495 rows between them. A row carries names — `setting`, `action`,
  `source`, `choices_source`, `rows_source`, `sensitive_when`, `visible_when`,
  `uri_source`, `validator` — and `Row.__slots__` has no `callback`, no `widget`
  and no `handler`, so a plan cannot smuggle behaviour past the checks that read
  it. Nothing in a plan is translated: the catalogue is installed over the
  rendered tree, which keeps a plan readable without one.
- **One renderer** (`widgets/__init__.py`) turns a plan into a widget tree and
  refuses a plan it cannot draw: fourteen toolkit widgets, ten row kinds, and a
  `messages` list that says what it declined and why. A name a plan puts in a
  `*_source` field has to be a zero-argument callable; `Renderer.maybe()` does
  not catch `TypeError`, so a signature mismatch is a build failure rather than
  a silently empty row.
- **The toolkit contract** in `data/design/adwaita.json`: 46 widgets and 58 api
  entries, each read out of GTK 4.10.0's and libadwaita 1.7.12's own headers,
  with `minimum_versions`, a `portability` block recording the two spellings
  that change shape above the floor (`Gtk.CssProvider.load_from_data` changes
  arity at 4.12, and per-widget `Gtk.StyleContext.add_provider` is deprecated at
  4.10 where the display-wide call is not), and a `rejected` block recording
  what was refused and why — CSS media queries arrive only at GTK 4.20, so a
  `prefers-reduced-motion` query at the 4.10 floor would be a block the parser
  skips without failing, and a person who asked for less motion would get every
  fade. `tests/test_settings_surface.py` reads the package's AST and fails on
  any `Gtk.X` or `Adw.X` the record does not verify.
- **The window** (`widgets/window.py`): a toast overlay around a navigation
  split view, a sidebar of fifteen toggle buttons chained with `set_group` and
  moved with the `toggled` signal (the `toggled()` *method* is deprecated at
  4.10), all fifteen pages built once and switched with
  `Adw.NavigationView.replace` so the back stack stays one deep, 1100×720 with a
  760×560 minimum, and `style/glass.css` added display-wide at
  `Gtk.StyleContext.PRIORITY_APPLICATION` — 600, below the 800 a person's own
  `~/.config/gtk-4.0/gtk.css` is loaded at, so this application loses to a
  stylesheet somebody wrote by hand.
- **Reduce motion as a style class.** `iarch-reduce-motion` is added to the
  window when either `animation.reduce_motion` or the session's
  `gtk-enable-animations` says so, and the sheet's transitions are written
  against `.iarch-reduce-motion` rather than inside a media query.
- **Fourteen services** that answer from the machine or refuse in a sentence:
  `config_store` (statuses `DEFAULTS`, `LOADED`, `MIGRATED`, `QUARANTINED`, with
  a document that fails validation quarantined rather than overwritten),
  `defaults`, `apply`, `autostart`, `contacts`, `control`, `gtk_settings`,
  `hypr`, `licenses`, `links`, `noctalia`, `runner`, `system` and `themes`.
- **About → Open-source licenses**, rendered from `data/licenses.json` — the
  same record `THIRD_PARTY_NOTICES.md` is rendered from, by the same generator,
  so the two cannot disagree. Twenty-nine legal sections: one per recorded
  component plus this product's own licence. The mapping to `Gtk.License` is
  recorded rather than guessed, and `ISC`, `MIT-CMU` and `OFL-1.1` are shown as
  `CUSTOM` with their own text because none of the enum's eighteen members means
  any of them. Seventy-four open claims are listed with the reason each is open.
- **Contact and Portfolio** from `data/contacts.default.json`, opening through
  one allowlisted call (`services/links.py`), with the portfolio URL asserted
  equal where the page and the service each state it.
- **Packaging for the one component that is a package**:
  `iarch/settings-app/pyproject.toml` (name `iarch-settings`, version copied
  from the root `VERSION`, `dependencies = []` because PyGObject is not
  installable from an index, `style/*.css` shipped as package data since
  `paths.style_file()` loads it out of the installed package and a wheel without
  it would draw unstyled and report nothing — GTK's CSS parse errors are never
  fatal), `scripts/iarch-settings.sh`, and
  `dev.safari.iarch.settings.desktop`. Four ways to start the window, all ending
  at the same `main`.
- **`docs/SETTINGS-APP.md`** — the five layers, the four rules as mechanisms,
  the four starting points, and what is not proven — and **`docs/DESIGN-SYSTEM.md`**
  — tokens as the only source, roles rather than sizes, the four intensities and
  their five glass alphas, `window_opacity` versus intensity, the seven `iarch-`
  classes, and the four things the stylesheet deliberately does not contain.
  Both are linked from `docs/ARCHITECTURE.md`'s documentation set and from
  `README.md`.
- **`tests/test_part4_acceptance.py`** (31 tests) and
  **`tests/test_settings_packaging.py`** (29 tests).

### Changed

- The coarse version-1 switches are reconciled rather than offered twice.
  `config_store.migrate_v1_to_v2` derives `theme.intensity` from `effects.blur`,
  `effects.transparency` and `effects.shadows` (all three on becomes `frosted`),
  turns `effects.animations: false` into `animation.preset: "off"` because that
  is the one mechanism the motion half already has for "no animation", and then
  derives the coarse pair back from the sections that own them. The derivation
  runs in one direction only, because two switches that can disagree are a bug
  that shows up as "the interface says frosted and the session is rendering
  performance": `preset` follows `theme.intensity`, `effects.blur` and
  `effects.shadows` follow the intensity's own tables *and* the leaf overrides in
  `glass.leaves`, `effects.animations` follows `animation.preset`, and
  `effects.transparency` is always true because no version-2 intensity is opaque.
  `derive_coarse` runs on every load and every save, so the pair cannot go stale.
  The interface therefore offers the intensity and the preset, not the four
  booleans behind them.
- `data/design/adwaita.json` gained six widgets and six api entries, including
  `adw_navigation_view_add` and `adw_navigation_view_replace`, verified against
  libadwaita 1.7.12's `src/adw-navigation-view.h` — where `AdwNavigationPage` is
  also declared, there being no `adw-navigation-page.h` at that release.
- `style/glass.css`'s header no longer claims the application's stylesheet wins.
  It said `APPLICATION` priority overrides a user stylesheet; the priority
  constants in `gtk/gtkstyleprovider.h` at 4.10.0 say 600 against `USER`'s 800,
  so it loses, and the comment now says that.

### Known gaps

- **The sidebar's search field is absent.** The index behind it exists —
  `PagePlan.search_entries()` carries one entry per row, 495 of them — and
  `app.focus-search` is bound to `Control+f`, but no widget draws the field, so
  the accelerator currently focuses nothing.
- **`SET-02` is the claim that costs the most:** a *misused* API — a property
  given the wrong type, a signal connected with the wrong signature — is caught
  only by running the window, and the window has never been run. No toolkit, no
  typelib and no display server exists on the machine this part was built on, so
  everything proven about the interface is proven about the plan and the record,
  not about pixels.
- **`SET-10`:** neither `install.sh` nor `fedora_install.sh` copies the desktop
  entry into `~/.local/share/applications`, `update-desktop-database` has never
  been run over it, no icon exists under the application id, and the console
  script has never been installed by a package manager. Two tests fail the
  moment an installer starts copying the entry or an icon appears, so the claim
  cannot go stale in silence.
- The sidebar's width is libadwaita's default, because no token exists for it.

## Unreleased — deep glass: motion, session surfaces, lock, login and the two modes

This is Part 3 of the roadmap: everything the session does that is not a
decoration — how it moves, how it notifies, how it locks, how it logs in, and
the two switches that trade glass for performance and for focus.

### Added

- **The compositor's animation surface**, recorded in `data/design/animations.json`
  and five motion presets a person can switch — `smooth`, `snappy`, `bouncy`,
  `minimal`, `off` — each its own file under `data/design/animations/`, each
  validated against a schema of its own.
- **`iarch/cli/iarch_anim.py`**, one command that switches the preset, verifies
  the reload against the compositor's own error list, and rolls the file back
  when the reload reports anything new.
- **Motion QA that can be run on a real machine** — `iarch/cli/qa_motion.sh` and
  `docs/MOTION.md`, which names the switch the wallpaper crossfade ignores.
- **The notification, control-centre, session, launcher and window-switcher
  surfaces**, recorded in `data/design/noctalia.json`, including the two
  providers that do not exist upstream and are therefore not faked; and
  `scripts/iarch-control-center.sh`, an IPC wrapper that only sends commands
  from a fixed allowlist.
- **`iarch/cli/iarch_doctor.py`** asks a running session instead of assuming one,
  and answers `unknown` rather than guessing.
- **Both lock screens and the idle fallback** — `.config/hypr/hyprlock.conf`,
  `.config/hypr/hypridle.conf`, rendered by `iarch/cli/render_hyprlock.py` from
  `data/design/hyprlock.json`, with the security-relevant keys emitted
  explicitly at their restrictive values.
- **The login screen recorded and deliberately not rendered**
  (`data/design/greeter.json`): a greeter file this repository cannot verify is
  a login screen nobody can log into.
- **Game mode and focus mode** — `iarch/lib/modes.py`, `iarch/cli/iarch_gamemode.py`,
  `iarch/cli/iarch_focus.py` — which compose values that already exist, then read
  the session back and restore what this run found.
- **The startup module rendered from a record of what it may run**
  (`data/design/startup.json`, `iarch/cli/gen_startup_lua.py`), with both
  installers' `sed` anchors asserted in the render.

### Changed

- Every emitted key now has to exist in the pinned release's surface record:
  Hyprland v0.57.2, Noctalia v5.4.1, noctalia-greeter v1.7.0 — pinned to a tag
  because its `main` already carries keys the tag does not. A key upstream
  declares but whose reader discards is recorded `write_only` and never emitted;
  a key this project refuses on principle is recorded `withheld`, so the
  validator says "withheld on purpose, and here is why" instead of claiming
  upstream has no such setting.
- Eleven text payloads and six palettes now carry a GENERATED stamp naming the
  record they came from, and every tool that can check itself is checked in
  `.github/workflows/iarch-checks.yml`, so a payload cannot drift from the
  record that justifies it without a workflow failing.
- `docs/WALLPAPERS.md` no longer sends anybody to a directory the shell does not
  scan; `SECURITY.md` says a startup command's failure is silent by construction;
  `README.md` says plainly that the two modes are commands with no key bound and
  no measured saving.

### Known gaps

- No key binds either mode. `Super+H` and the overlay behind it are Part 7, and
  until then both modes are commands you run.
- There was still no settings GUI, so the coarse `preset` and `effects` switches
  in `data/settings.default.json` were read by no renderer — Part 4 reconciles
  them, and did.
- No greeter file is emitted. `.config/hypr/hypridle.conf` ships unlaunched,
  because the shell owns `ext_idle_notifier_v1` and a second daemon would race it.
- Nothing in this part was observed on a live session: the frame-timing and
  latency measurement is still `PERF-01`, and `MODE-01` to `MODE-04`, `START-01`
  and `START-02`, `WAL-01` and `WAL-02` are the specific claims a sandbox could
  not reach.

## Unreleased — glass surfaces and motion

This is Part 2 of the roadmap: the compositor-side glass — blur, borders,
rounding, shadows and the open/close/hover animation set, all switchable.

### Added

- **Design tokens bounded by the compositor's own limits**
  (`data/design/tokens.json`), and colour presets that cannot ship below WCAG
  contrast (`data/design/presets/*.json`, `iarch/cli/contrast_check.py`).
- **Seeded 4K WebP wallpapers** the generated presets own, inside a 600 KB
  budget; two presets keep bundled art (`iarch/cli/gen_wallpapers.py`).
- **Hyprland decoration, layer and window rules for the shell surfaces** —
  blur, borders, rounding, shadows, per-surface opacity — rendered from the
  tokens into `.config/hypr/generated/glass.lua`.
- **The shell `config.toml` and one palette per preset**, refused past the
  upstream schema (`.config/noctalia/`, `iarch/cli/render_noctalia.py`).
- **The GTK 4 and GTK 3 glass overlays**, refused past what each version parses
  (`.config/gtk-4.0/gtk.css`, `.config/gtk-3.0/gtk.css`, `iarch/cli/render_gtk_css.py`).
- **The Qt/Kvantum glass theme**, refused past the keys `ThemeConfig.cpp` reads
  (`.config/Kvantum/`, `iarch/cli/render_kvantum.py`).
- **The fontconfig that applies the font tokens**, refused past the config DTD
  (`.config/fontconfig/fonts.conf`, `iarch/cli/gen_fontconfig.py`).
- **The animation set from the motion tokens**, with a real Performance off
  switch (`.config/hypr/generated/animations.lua`).
- **`iarch/cli/theme.py`** (`iarch-theme`): one command applies a preset across
  every surface — contrast gate first, all-or-nothing write, verified reload.

### Changed

- Every effect now has a named switch: blur, transparency, animations and
  shadows are the four `settings.effects` booleans, `settings.preset` is the
  coarse master, and `settings.theme.intensity` selects crystal, frosted, soft
  or performance — the step every renderer consumes. The settings enum and the
  tokens' intensities are asserted to be the same set, so a switch can never
  name something the renderers lack.
- The Performance preset lowers work in a way that is provable by inspection:
  the `performance` intensity sets `motion.enabled = false`, so the rendered
  `animations.lua` emits only Hyprland's master `animations:enabled = false` —
  zero animation leaves and zero curves, against frosted's eleven and five.
- Every renderer validates its output against a `data/design/*.json` surface read
  out of the pinned upstream release, and refuses a key, leaf, curve or property
  that release does not have.

### Known gaps

- The frame-timing, blur-cost and input-latency *measurement* on real hardware is
  still `PERF-01`; what Part 2 proves is the reduction in emitted work, not a
  measured saving.
- What no sandbox could observe — a live Hyprland or Noctalia session — is
  `TP-10`, `SES-02` and `UI-05`, and the icon-theme runtime gap is `TP-19`.
- The settings application that reconciles the coarse `preset`/`effects` switches
  with `theme.intensity` was Part 4; the cursor is applied statically by
  `themes/theme.lua` (a verified no-op, every preset shipping the same one) and
  the icon theme is reported, not applied.

## Unreleased — iArch Glass foundation

This is Part 1 of the roadmap: no change to how the desktop behaves, and every
change to how the repository is organised, named, credited and checked.

### Added

- **`iarch/`**, the directory for the product's own code, with
  `iarch/lib/configstore.py` as the single owner of user state: repository
  defaults merge under the user's file, writes are atomic
  (temp → validate → rename), generated output is stamped
  `-- GENERATED BY iArch. DO NOT EDIT. Change settings in iArch Settings.`, and
  the last five generations are kept in `~/.local/state/iarch/backups/`.
  `iarch/cli/` and `iarch/settings-app/` are reserved for Parts 2, 4 and 5 with
  a README each stating what lands there.
- **`data/`**, the defaults a user never edits after install:
  `settings.default.json`, `keybinds.default.json`, `contacts.default.json`,
  `design/glass.tokens.json` and a JSON Schema for each, plus the generated
  `licenses.json` that the settings app's About page will read.
- **`tools/extract_keybinds.py`** parses every `hl.bind()` out of
  `.config/hypr/keybind.lua`, expands the workspace loop the way Lua does, and
  renders `data/keybinds.default.json`. `--check` proves the two still agree, so
  the shortcut table can never drift from the session that implements it.
- **`profiles/performance.toml` and `tools/profile_preset.py`**, the performance
  contract `docs/ARCHITECTURE.md` described but the repository had not built: an
  overlay that may only change values of keys the base profile already has,
  refuses invented keys and type changes before writing, backs up first, and
  reverts byte-for-byte.
- **`assets/branding/`**: original logo artwork drawn for this repository, in
  colour and monochrome SVG.
- **`branding/product.env`** as the only definition of the product name, ids,
  runtime paths, license expression and copyright header, with
  `tools/iarch_brand.py --check` and `tools/branding_lint.py` enforcing it.
- **`THIRD_PARTY_NOTICES.md`**, rendered from `branding/notices.json` by
  `tools/notices.py`, covering 25 components: the compositor, shell, terminal,
  prompt, system-information and screenshot tools; the typefaces, cursor theme
  and icon themes; the vendored plugin and derived colour values; the audio and
  artwork assets whose rights are not established; the third-party repositories
  and services the installers use; and the earlier GitLab publication this
  repository grew out of. Every license was read from the upstream project, and
  the ones that could not be reached say `TODO(verify)` and point at an id in
  `docs/UNVERIFIED.md` instead of guessing.
- **`CONTRIBUTING.md`, `SECURITY.md`** and this file. `SECURITY.md` lists every
  privileged operation the installers perform, with the `INS-` and `TP-` ids they
  are tracked under, and what they deliberately do not do.
- **`docs/`**: `ARCHITECTURE.md` (repository map, the two payloads, runtime map,
  user-state rules with a diagram, safety and performance contracts, testing
  map), `BASELINE.md`, `BRANDING.md`, `ROADMAP.md`, `UNVERIFIED.md`,
  `glass-experience.md`.
- **CI** (`.github/workflows/`): bash syntax on every tracked script,
  `shellcheck --severity=warning` with its exceptions documented in
  `.shellcheckrc`, the five shell test suites, the Python unit tests, JSON and
  TOML validation, and the payload-separation and branding checks.
- **Tests**: from none to 119 unit tests plus five shell suites, covering naming,
  credit, the payload map, keybind data, the config store, the performance
  preset, installer CLI, staging, recovery and diagnostics.

### Changed

- **Renamed from the earlier product names to iArch by Safari** on every surface
  a person reads: README, installers' output, session menu entries, window
  titles, terminal greeting, system-information header, palette name
  (`iarch-midnight`) and the runtime helper scripts (`iarch-healthcheck.sh`,
  `iarch-control-center.sh`). Identifiers other programs match on are
  deliberately left alone — see below.
- **Moved the frozen v4 payload into `legacy/`**: both deprecated installers, the
  Wayland session launchers, the Hyprlang `.conf` configuration, the v4 Noctalia
  settings and QML plugin, the GTK 3/4 settings and the frozen customization
  centre, plus the historical documents. `.config/` now holds exactly the 26
  files the current session deploys, and `tests/test_payload_map.py` proves the
  two payloads do not overlap in either direction.
- **Rewrote the root of the repository**: documentation, artwork and media out of
  the top level, and the exec bit set on the entry points the docs tell people to
  run, so `sudo ./install.sh` works on a fresh clone.
- **`docs/ARCHITECTURE.md`** gained "User state and the single source of truth"
  and a diagram of Settings app → config store → generators → generated files →
  Hyprland and Noctalia reload.
- **`IARCH_LICENSE_ID`** is now the SPDX expression `GPL-3.0-or-later`, matching
  the copyright header new files carry and the "any later version" option the
  GPL-3.0 text in `LICENSE.txt` offers.
- **`README.md`** states the lineage once, in the credits section, and links the
  release trailer instead of embedding it.

### Removed

- **`trailer/trailer.mp4`** (10 MB). The video tour is on YouTube and linked from
  the README; a release video is not something a configuration repository needs
  to carry in every clone.
- **Dead code in `.config/hypr/Scripts/workspace.sh`** (94 → 77 lines), including
  an unreachable branch and a duplicated lock-file check. The dispatch strings
  were verified against Hyprland's `Commands.cpp`, which wraps them in
  `hl.dispatch`, so they stay exactly as they are.
- **The `.png` showcase images from `assets/screenshots/`**, moved to
  `assets/wallpapers/originals/` and replaced in README and the docs by WebP
  renditions at quality 85 — 7.37 MB → 0.21 MB and 1.19 MB → 0.09 MB, with the
  alpha channel preserved losslessly.
- **The README's claim to be "maintained as a standalone GitHub repository, not
  as a fork"**, which the history does not support: this repository is the
  continuing work of the earlier GitLab dotfiles under a new name, and it now
  says so once, in the credits section. The CI workflow that carried the earlier
  product name was renamed and extended, not removed.

### Fixed

- Shellcheck findings at warning severity in `install.sh`, `fedora_install.sh`,
  `legacy/legacy-install.sh`, `lib/*` and `tests/package-audit.sh`; the gate is
  now zero errors and zero warnings across all 19 tracked shell scripts and both
  session launchers.
- Stale paths and links left behind by the move into `legacy/`, in four test
  files, `tools/branding_lint.py`, `branding/notices.json`, six documents and the
  CI workflow.
- A stale comment in `lib/stage-v5-config.sh` that still pointed at the v4
  payload's old location.
- Registered, rather than papered over: `install.sh` and `fedora_install.sh`
  request `JetBrainsMono Nerd Font Mono` and `Bibata-Modern-Classic`; no package
  provides the Nerd Font (`TP-13`), though Bibata is installed on Arch and its
  Fedora name is unverified (`TP-18`); `hypridle` is installed but never
  started by `startup.lua`; the DDC brightness branch edits a `settings.json`
  that the v5 session never deploys (`INS-06`); and `themes/theme.conf` and
  `themes/theme.lua` disagree on gaps, rounding and inactive opacity.

### Known gaps

`docs/UNVERIFIED.md` holds the current list with an id per row. The short
version: nothing here has been validated by a real install on a real machine in
this pass — no live Hyprland session, no `noctalia config validate`, no measured
effect of the performance preset, and the Fedora installer has been checked for
syntax only. `install.sh` still runs `pacman -S --noconfirm`, still edits
`/etc/pacman.conf`, still imports the Chaotic-AUR key and still switches the
display manager; that hardening is Part 6, where it can be changed with tests
around it.
