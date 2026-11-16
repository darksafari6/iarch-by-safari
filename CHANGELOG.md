# Changelog

Notable changes to iArch by Safari, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the
six-part plan in [`docs/ROADMAP.md`](docs/ROADMAP.md) rather than semantic
versioning, because nothing here is a library anyone links against.

## Unreleased — every Super+letter cell, and the eight scripts that filled them

The second slice of Part 7, and it exists because the first one left a sentence behind that
turned out to be a design error rather than a tidy outcome. The A to Z table allocated all 78
letter cells and called the empty ones *free on purpose* — a budget kept for a later bind. Read
as a plan that is defensible; read as a keyboard it is not, because a person pressing `Super+G`
and getting nothing has no way to tell a decision from an omission, and the table could not tell
them either. So every cell of the primary layer is now bound, and the cells that had no mechanism
behind them got one: eight new launchers under `scripts/`, ten verbs read back out of the shell's
own command table, and one compositor configuration call the design record already documented.

### Added

- **Sixteen bindings, and the `Super` layer is full.** `data/keybinds.default.json` went from 83
  rows to 98 and from 14 categories to 15 — `Brightness` is the new one — and all twenty-six
  letters of the primary layer are bound. Ten of the sixteen are letters that were refused or left
  empty a slice ago: `Super+G` for the gaps, `Super+J` for the window switcher, `Super+K` for the
  keyboard layout, `Super+N` to dismiss what is on screen, `Super+O` for the shell's OSD, `Super+P`
  to cycle the power profile, `Super+R` for a run prompt, `Super+U` to reload the session,
  `Super+Y` for the clipboard history and `Super+Z` for zen mode. The other six are rows the map
  had no business being without: the two mute keys, the two brightness keys, and — in the tertiary
  layer — `Super+Ctrl+T` for the theme mode and `Super+Ctrl+W` for the next wallpaper.
- **Eight launchers under `scripts/`** — `iarch-audio`, `iarch-brightness`, `iarch-cycle`,
  `iarch-doctor`, `iarch-gaps`, `iarch-reload`, `iarch-run` and `iarch-zen`. Each one exists
  because a cell needed a mechanism rather than a placeholder, and each carries its evidence in its
  header: the wpctl and brightnessctl flags are read out of those tools' own manuals and, for
  brightnessctl, out of the source that implements them; the six hide and show verbs zen sends are
  quoted from the shell's command table with the line each came from; the run prompt's contract is
  `noctalia dmenu`'s, down to the socket path and the two environment variables it needs.
  `scripts/iarch-link-cli.sh` now links fifteen names instead of seven, because a bind that execs a
  command nothing puts on `PATH` is a key that does nothing and fails quietly.
- **Ten verbs in `data/design/noctalia-ipc.json`**, which went from 41 to 51: the wallpaper cycle,
  `keyboard-layout-cycle`, `notification-clear-active`, `osd-toggle`, `power-cycle`, and the six
  bar, dock and desktop-widget verbs. All ten are read out of `src/cli/schema_msg.h` at v5.4.1 with
  the line they came from, and `iarch-keybinds check` validates a noctalia action against the
  record — so an invented verb is refused at the gate rather than at the key. The typed wrapper in
  `iarch/settings-app/iarch_settings/services/noctalia.py` carries the same fifty-one, because a
  second copy of a list agrees with itself after the first one changes.
- **Four rows in `docs/UNVERIFIED.md`** — `KB-07` for the six keys that reach a third-party binary,
  `KB-08` for the four that drive a compositor or shell switch, `KB-09` for the seven that send a
  shell verb, and `KB-10` for the run prompt. Each says what was read, what was never run, and what
  the gap blocks, and every one of the sixteen new rows carries an `unverified` note pointing at
  the row that explains it.

### Changed

- **The two XF86 volume keys no longer call `pamixer`.** They exec `iarch-audio up` and
  `iarch-audio down`, which drive `wpctl` — and the reason is a bug, not a preference: no step of
  either installer ever installed `pamixer`, so on a machine this repository built those two keys
  were dead and the only report was a shell's "command not found" in a log nobody reads.
  `wireplumber` and `brightnessctl` are now named in both installers' package arrays, with the Arch
  repository, version and licence recorded beside them (`extra`, `0.5.19-1` and `0.5.1-3`, both MIT,
  read out of Arch's package search JSON API on 2026-11-09) and two new entries in
  `branding/notices.json` crediting them. `TP-11` is narrower for it and says which half of it is
  still open: the Fedora spellings were mirrored, not resolved.
- **`data/schemas/keybinds.schema.json` grew the `repeating` flag** and the conditional that goes
  with it, because a held key is a different thing from a pressed one and the record had no way to
  say so. The two volume steps and the two brightness steps carry it; the two mutes deliberately do
  not, since a repeated toggle is a strobe.
- **`Super+K` stopped being a placeholder for a panel that does not exist.** The cell was reserved
  for a Hyprland key panel, and the shell's control centre has twelve tabs — home, media, audio,
  monitor, system, power, network, bluetooth, weather, calendar, notifications and screen time —
  none of which is a keyboard. The row that claimed it, `planned.hyprland-key`, is deleted rather
  than disabled, and the `Planned` category now holds exactly one row: `planned.refresh-overlay`,
  the overlay refresh that Part 7's glass window will need.
- **`docs/ROADMAP.md` Part 7 and `docs/CUSTOMIZING-SHORTCUTS.md` say what changed instead of what
  was true before it.** Both named three reserved keys and both listed `Super+R` and `Super+K`
  among the table's refusals; a true sentence left behind a change is a false one, so each now
  names the bind and keeps the reason the refusal was dropped. The emergency-mode paragraph gained
  the sentence a reader needs now that `Super+R` is also the run prompt: emergency mode only trips
  when the bind registry is empty, which is the state in which this map is not loaded at all.

### Known gaps

- **None of the sixteen has been pressed.** There is no compositor, no shell, no display, no sound
  server and no backlight where this was written, so every flag is a reading and every behaviour is
  unobserved — which is what `KB-07` to `KB-10` are for, and why each row says it in the record
  rather than leaving a reader to guess. The two scripts that cannot ask what state they left
  behind, `iarch-gaps` and `iarch-zen`, keep a one-word memory of it and say so out loud.
- **Zen mode drifts across a shell restart, by its verbs' own design.** `dock-hide` persists its
  override and `desktop-widgets-hide` does not, so a restart leaves the dock hidden and the widgets
  back. `off` puts both away; nothing here claims otherwise.
- **The gaps and the reload are runtime state.** `hl.config` writes and does not read, and a
  `hyprctl reload`, an `iarch-theme apply` or a relogin re-renders `theme.lua` and puts the tokens'
  gaps back. That is the honest reading of the cell rather than a bug in it.

## Unreleased — the A to Z shortcut table, and the layer debt it settled

This is the first slice of Part 7 of the roadmap: the keyboard map laid out as a plan rather than
grown one bind at a time. Before it, `data/keybinds.default.json` said what was bound and nothing
said what was not — a letter with no bind was indistinguishable from a letter nobody had thought
about — two bindings the v1 map had carried into the recovery layer were printed as debt on every
`iarch-keybinds check` run, and the two modes this project builds were commands with no key at
all, which is exactly what Part 3 left for this work.

### Added

- **The A to Z table** — `data/design/keybinds.json -> alphabet` allocates all 78 letter cells of
  the three layers a letter may live in (`Super`, `Super+Shift`, `Super+Ctrl`), and
  `tools/render_shortcuts.py` renders it as a grid at the end of `docs/SHORTCUTS.md`. A cell is
  one of four things: a binding, a key the record has claimed and not bound, a refusal with the
  mechanism behind it, or empty on purpose. Ten of them were refusals at this point, and each
  named a verb, a file or a command rather than a mood: brightness had no relative verb in
  noctalia v5.4.1, `theme-mode-toggle` would set a value `render_noctalia.py` generates and the
  next `iarch-theme` run would quietly revert, Do Not Disturb and caffeine belong to focus mode
  because it reads both back before it changes them, mute belongs on the media row where the
  volume steps are, `Super+R` is the compositor's own emergency launcher (`KB-05`), and
  `Super+Ctrl+R` would be a second spelling of the recovery combo. Seven of the ten are still
  refusals; the other three were wrong, and the slice below says so. The schema pins the three layers and their modifiers as
  constants, so the table cannot grow a fourth layer that the checker refuses — `Super+Alt`
  cannot be spelled in it at all.
- **`tests/test_keybinds_alphabet.py`** — seventeen tests that hold the table and the map
  together in both directions: a cell that says bound has to name a binding enabled at exactly
  those keys, a cell left empty has to have nothing bound at it, every letter binding in the map
  has to have a cell so a bind cannot land on a letter nobody allocated, every refusal has to
  cite something this repository actually has, and the three keys `docs/ROADMAP.md` reserves are
  read out of the roadmap rather than written down a second time here. The renderer refuses to
  write a table that disagrees with the map, for the same reason from the other side.
  `iarch-keybinds check` deliberately does not read the table: an override in
  `~/.config/iarch/keybinds.json` may use any empty cell it likes, and a validator that policed
  a person's own map would be policing the wrong file.
- **`scripts/iarch-focus.sh` and `scripts/iarch-gamemode.sh`** — the two thin launchers that make
  `iarch-focus` and `iarch-gamemode` real names, which `scripts/iarch-link-cli.sh` now links. A
  bind that execs a name nothing installs is a key that does nothing, and it fails quietly: the
  compositor spawns `/bin/sh -c` with one string, so the only report is a "command not found" in
  a log nobody is reading. `tests/test_cli_launchers.py` gained the check that turns the
  guarantee from one bind into all of them — every `iarch-*` command the map execs has to be a
  name the linker puts on `PATH`.
- **Three binds in the `Super+Ctrl` layer** — `Super+Ctrl+F` for focus mode, `Super+Ctrl+G` for
  game mode and `Super+Ctrl+L` for night light through the shell's own `nightlight-toggle`. Each
  carries an `unverified` note in the record and all three are `KB-06`: the launchers, the verbs
  and the CLIs' own logic are exercised here, and no key has been pressed on a session, because
  there is no compositor and no display where this was written.

### Changed

- **The `Super+Ctrl+Alt` layer debt is settled.** `move.next` and `move.previous` — moving the
  focused window to the next and the previous workspace, carried into the recovery layer by the
  v1 map — moved to `Super+Ctrl+N` and `Super+Ctrl+P`: the layer the checker itself offers when
  it refuses a plain `Ctrl+letter`, and the layer that already owns workspace navigation on the
  arrows. `iarch-keybinds check` reports nothing at all on the shipped map now, where it used to
  print those two on every run; the rule that printed them stays, and its message says where they
  went. Both rows carry a `relocated_from` field, new in `data/schemas/keybinds.schema.json`,
  because the person whose hands still reach for the old combination is the one who needs it
  written down — and an override that rebinds either row keeps working, since the id is the
  identity and the keys are not.
- **`docs/SHORTCUTS.md` has two sources and says so.** The banner names the A to Z allocation
  beside the keybind record, `--check` compares the document against both, and the prose the
  table renders keeps the record's ASCII dashes but reads as Markdown, because the document it
  lands in is not the file it was written in.
- **The documents that said the modes had no key now say what they have.** `README.md` said "no
  key is bound to it" and `docs/ROADMAP.md` Part 3 said "no key binds either mode"; both were
  true when they were written, and a true sentence left behind a change is a false one, so each
  now names the key and the row in `docs/UNVERIFIED.md` that says it has not been observed.
  `docs/CUSTOMIZING-SHORTCUTS.md` gained the table, the settled layer and the two keys that have
  never been pressed.

### Known gaps

- **Nothing in the new layer has been watched on a session.** `KB-06` is the row, and it sits
  inside `INS-07`: whether a session greetd started has `~/.local/bin` on its `PATH` at all is
  the question every bind that names an `iarch-*` command depends on, and no installer has run
  here. The game-mode key is the one to be careful with, because its action writes generated
  files and asks for a reload — a reload that arrives mid-game is a stutter nobody asked for,
  which is why the CLI carries `--no-reload` and why the row is not locked.
- **The table allocates letters and nothing else.** Arrows, digits, function keys, media keys and
  the mouse binds are governed by the layer rules in `iarch_keybinds.py` and by the reserved
  combinations in the design record, but they have no grid, so a new bind on `Super+Ctrl+up` is
  still a decision nobody has written down.
- **The map bound no mute key and no brightness keys**, and both gaps were recorded in the table's
  refusals rather than filled with a guessed flag. That was the right call at the time — a guessed
  flag is worse than a refusal — and the slice below closes both gaps by reading the flags out of
  `wpctl(1)` and `brightnessctl(1)` instead of guessing them. It also closes the larger one the
  refusals were standing in for: that a cell left empty on purpose is indistinguishable, to the
  person pressing it, from a cell nobody thought about.

## Unreleased — the installer wizard, the bar's widget vocabulary, and the desktop art

This is the first slice of Part 6 of the roadmap: an installer that is safe to run twice and
honest about what it changed. Before it, `install.sh` was one long sequence of `echo` and
`pacman -S --noconfirm` calls — it reinstalled packages a machine already had, it put three
package names that do not exist in Arch's repositories into the transaction whose failure
aborts everything, and it never installed the icon themes, the wallpapers, the menu entry or
the command wrappers the session's own configuration expects to find. It also shipped a bar
whose widget list nobody had checked against the shell that draws it.

### Added

- **`lib/packages.sh`** — the package-state layer every transaction now goes through. It
  refreshes the sync databases once per run, asks `pacman -Quq` which targets are actually out
  of date, classifies each name as missing, outdated or current, prints the plan
  (`core: 2 to install, 1 to update, 84 already current`) on stderr, and hands pacman and yay
  `--needed` — pacman(8)'s own "do not reinstall the targets that are already up-to-date". A
  machine that is already current opens no transaction at all. `tests/test_packages.sh` proves
  the classification, the single `-Sy`, the `--needed` flag and the empty-transaction case
  against a stubbed `pacman`, `yay` and `sudo`.
- **The installer wizard** — 24 numbered steps, each printing `[ 7/24] Bluetooth` and then
  `✓ done`, `– skipped: <reason>` or `✗ failed: <reason>`, a banner naming the step count and
  the manifest path, notes indented under their step, and a summary
  (`✓ 19 done   – 4 skipped   ✗ 1 failed`) that makes the script exit non-zero when anything
  failed. `tests/test_installer_wizard.py` executes the extracted banner, step runners, reboot
  prompt and main flow under a pty, asserts the step count and the flow agree, and refuses a
  named package transaction that bypasses `lib/packages.sh`.
- **Five installer steps that were missing**: *Icons and cursors* (Papirus, Yaru and Humanity
  icon themes plus the Bibata cursor through `yay`, non-fatal, and skipping a cursor theme that
  is already installed under either of its two names), *Session commands on PATH* (the five
  `iarch-*` wrappers), *Session PATH* (`~/.config/environment.d/iarch-cli-path.conf`, because a
  session a display manager starts reads no shell profile), *Menu entry* (the settings desktop
  entry, the icon its `Icon=` key names, and `update-desktop-database` when the machine has it)
  and *Wallpapers* (copies the committed art into the Pictures directory noctalia's picker
  reads, skipping files that are already identical).
- **`~/.local/state/iarch/install-manifest.txt`** — every path the installer creates outside
  the repository, one per line, so a second run knows what it owns and a person can read what
  an install did.
- **`bar_widgets` in `data/design/noctalia.json`** — the 34 widget types noctalia v5.4.1's
  `widget_factory.cpp` registers, read out of `kBuiltinWidgets`, plus six this project refuses
  to ship with the reason beside each. `render_noctalia.py` now refuses to render a bar array
  naming a widget the factory does not register — upstream logs `widget factory: unknown
  widget` and draws nothing while the config still validates, which is a silent failure — or
  one of the six refused names.
- **Six 4K desktop wallpapers** in `assets/wallpapers/desktop/`, one per gradient style the
  generator has, each rendered from a recorded seed by `gen_wallpapers.py --preset <id>` and
  each darker than `MAX_MEAN_LUMINANCE = 0.14`, measured as the mean of the ITU-R 601-2 luma
  channel. Dark is a measurement rather than an adjective because a bright desktop stops making
  glass panels read as panels. No third-party artwork: the generator is the author of all six.

### Changed

- The shipped bar's `end` array gains `clipboard` and `privacy`. `clipboard` is a registered
  panel with no keybind and no bar entry, so clipboard history could not be opened at all;
  `privacy` is the session's only indicator that a microphone or camera is in use. `taskbar`
  stays refused: `dock.show_running` already draws running windows.
- `scripts/iarch-link-cli.sh` links five commands instead of two — `iarch-keybinds`,
  `iarch-cheatsheet`, `iarch-settings`, `iarch-control-center` and `iarch-healthcheck` — which
  was every name the session configuration called at that point. The shortcut section above
  adds two more, because the keyboard map now execs them.
- Papirus dark and light are `verified: true` in all six colour presets, with the registry
  evidence in the entry's note, and `data/schemas/preset.schema.json` now says what `verified`
  certifies: that `package_arch` was read out of Arch's own registry, and nothing about
  `package_fedora`, which no environment here can check.
- `THIRD_PARTY_NOTICES.md` and `data/licenses.json` carry real versions for
  `papirus-icon-theme` (20260801-1, in `extra`) and `bibata-cursor` (2.0.7-1 in the AUR as
  `bibata-cursor-theme-bin`, which both Provides and Conflicts `bibata-cursor-theme`).

### Fixed

- `papirus-folders` and `bibata-cursor-theme` were in the fatal core package list although
  neither is in Arch's repositories — the package search JSON API returns no result for either
  — so `install.sh` aborted at *Core packages* on any machine that had only the official
  repositories, before it configured anything. Both moved to a step that warns instead (TP-20).
- The icon and cursor themes the presets name were never installed by anything, so a fresh
  install drew the cursor and icon theme the distribution happened to have.
- **Every `install.sh:NNN` citation in the repository pointed at the wrong line** after the
  restructure — in three design records (`greeter.json`, `startup.json`, `xdg-defaults.json`),
  in `SECURITY.md`, in `docs/UNVERIFIED.md`, in two source docstrings, and in the header
  `gen_startup_lua.py` renders into `.config/hypr/startup.lua`. `docs/FONTS.md` and `README.md`
  also named `bibata-cursor-theme` as the package Arch installs, which it is not. Each was
  re-pointed by reading the file rather than by adding an offset to the old number, because an
  offset assumes nothing else moved — the assumption that caused the drift. A stale line number
  does not read as a gap; it reads as a lie about code that is correct.
- That class of drift is now checked rather than repaired: `tests/test_citations.py` scans every
  citation of both installers in the repository, refuses one that points past the end of its
  file, and for every citation in a design record or in `SECURITY.md` asserts the cited lines
  still contain the token the citation is about. A new citation in a record arrives with an
  expectation or the suite fails.

### Known gaps

- `--dry-run` still does not exist, `pacman -Syu --noconfirm` still upgrades the whole system
  before the AUR builds, and the `pacman -Rns` removal path is unchanged (INS-01).
- Nothing reads the install manifest yet (INS-08), and whether a greetd-started session
  inherits the `environment.d` file that puts `~/.local/bin` on its `PATH` is unobserved
  (INS-07) — which is what KB-01 and SET-10 still turn on.
- No bar, wallpaper picker, icon theme or line of wizard output has been seen on a real
  machine: no compositor, display, package manager or terminal emulator exists in the
  environment these changes were made in (TP-19, WAL-03, INS-01).

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
