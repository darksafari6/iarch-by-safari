# Decisions

Every decision that changes the shape of this project is written here once, with
the alternatives it rejected and what it costs. A decision is not a plan: the
schedule lives in [ROADMAP.md](ROADMAP.md) and
`docs/THEMES-MILESTONES.md`, and the claims that are still
unproven live in [UNVERIFIED.md](UNVERIFIED.md).

Ids are `D-<part>-<number>`. `D-T1-*` are the decisions of the dynamic-themes
part 1; the plan that produced them is [PART-PLAN-T1.md](PART-PLAN-T1.md).

---

## D-T1-01 — two shell engines, exactly one running at a time

**Context.** The session's bar, launcher, control center, notifications, wallpaper
and lock behaviour are all one upstream shell process, started by the `noctalia`
line of `.config/hypr/startup.lua` (recorded in `data/design/startup.json`,
`exec_once`). The dynamic-themes work needs a shell whose every colour, radius,
font and duration comes from a theme pack at runtime.

**Decision.** This project ships a second QML engine of its own — engine id
`dynamic`, name "iArch Shell" — beside the existing one, engine id `classic`, name
"Classic". Exactly one of the two may run: `iarch-shell-switch` stops one before it
starts the other, and `iarch-doctor shell` reports a violation rather than guessing
which one won. `classic` remains the default engine, and remains what the installer
configures, until `dynamic` passes the QA gate of milestone M5.

**Rejected.**
- *Fork or patch the existing shell.* Its release is pinned at v5.4.1 and every key
  this project writes is verified against that pin (`data/design/noctalia.json`);
  a fork would make each of those citations a claim about code this project has to
  keep correct itself, forever.
- *Both at once, one hidden.* Two layer-shell surfaces, two notification servers and
  two lock clients on one compositor is a session whose behaviour depends on which
  process answered a bus name first. That is not a state a person can diagnose.
- *Replace Classic immediately.* Every shortcut, mode switch, doctor probe and
  installer step in this repository is verified against the pinned release. Making
  the new engine the default before it has passed the same QA would break work that
  is proven today.

**Costs.** Two engines to keep working, one switch command that has to be
trustworthy, and a QA gate that has to be honest about which engine it ran on.

## D-T1-02 — the second engine is built on Quickshell

**Context.** A shell needs layer-shell surfaces, a notification server, compositor
IPC, audio and media state, and a lock client.

**Decision.** Build "iArch Shell" on Quickshell. Read out of its own source tree
(`quickshell-mirror/quickshell`, `master`, tag `v0.3.2`, LGPL-3.0):

- configurations are discovered as `<xdg config dir>/quickshell/<name>/shell.qml`,
  run with `quickshell --config <name>`, with `--daemonize`, and with
  `--no-duplicate` to refuse a second instance of the same configuration
  (`src/launch/parsecommand.cpp`);
- `quickshell list --json`, `quickshell kill` and `quickshell log` give an outside
  process a way to see and stop an instance (`src/launch/parsecommand.cpp`);
- `quickshell ipc call <target> <function> [args…]` reaches an `IpcHandler` in QML
  (`src/launch/parsecommand.cpp`, `src/io/ipchandler.hpp`), which is how a theme
  apply asks a running shell to hot-swap;
- `PanelWindow` (`src/window/panelinterface.hpp`), `NotificationServer`
  (`src/services/notifications/qml.hpp`), the `Hyprland` singleton including
  `usingLua` and `dispatch()` (`src/wayland/hyprland/ipc/qml.hpp`), and PipeWire,
  MPRIS, UPower, polkit and status-notifier services are its own modules;
- its crash handler will not restart a shell that crashed within 10 seconds of
  launch (`src/launch/main.cpp`), which is the same window this project uses to
  decide a start failed.

**Rejected.**
- *Write a shell on raw Wayland protocols.* Layer shell, session lock, a
  notification daemon and compositor IPC would all become this project's code to
  verify and maintain.
- *A GTK or web shell.* Neither gives layer-shell panels with per-monitor
  exclusivity, and both would leave the glass look this repository's tokens define
  as an approximation.
- *Extend the existing shell's own configuration surface.* Its verified key set
  (`data/design/noctalia.json`, including what it deliberately withholds) does not
  expose per-surface geometry, motion or shape tokens; that is the gap the whole
  dynamic-themes plan exists to close.

**Costs.** A new runtime dependency (package availability on Arch and Fedora is
`ENG-01`), Qt ≥ 6.6 with private headers, and an LGPL-3.0 component this project
uses unmodified through its own QML — recorded in
`docs/THEMES-ASSETS.md` and, when the installer depends on it, in
`branding/notices.json`.

## D-T1-03 — `engine: "ishell"` in a pack, `dynamic` at runtime

**Context.** The pack format names the renderer a pack targets; the switch command
and the state records name the running engine. Two vocabularies for one idea is a
bug waiting to be typed.

**Decision.** The pack field keeps the value the format specifies, `"ishell"`. The
runtime engine id is `dynamic`. Exactly one table — `PACK_ENGINE_TO_ENGINE` in
`iarch/cli/theme_engine.py` — maps between them, and a test asserts the map is
total over both catalogues. Nothing else in the repository is allowed to translate
between the two words.

**Rejected.** *Rename one to match the other.* The pack value is part of a
published format version, and the runtime id is what a state file, a doctor report
and a settings toggle say; either rename would put a migration in front of a
format that has not shipped yet.

## D-T1-04 — dynamic packs are directories, Classic packs stay flat

**Decision.** A dynamic pack is `data/themes/<id>/` containing `theme.json`,
`palette.json`, `layout.json`, `motion.json`, `sounds.json`, `hypr.json`,
`apps.json`, plus `wallpapers/` and `preview/`. The six Classic packs keep their
existing flat `data/themes/<id>.json` files and their existing
`data/themes/schema.json` unchanged, so `iarch-theme apply greenhouse`, the
installer render and every current test keep working byte for byte.

**Rejected.**
- *One flat file per dynamic pack.* A pack carries a palette, geometry, motion,
  sound and per-application sections; one file would be several thousand lines and
  impossible to review one section at a time, which is how the six packs will be
  built in Part 5.
- *Convert the Classic six to directories now.* Nothing gains from it in this part,
  and it would touch six validated files, two installers and a dozen tests for a
  format the Classic renderer does not read.

## D-T1-05 — one committed reference pack

**Context.** CI validates `data/` twice over: rule 3 fails a document no schema
covers, rule 4 fails a schema no document uses (`.github/workflows/iarch-checks.yml`,
step "Validate every JSON file in data/ against its schema", and the same rules in
`tests/test_data_files.py`). Seven new pack schemas with no committed pack would
fail rule 4 on the first run.

**Decision.** Ship `data/themes/dynamic-reference/`: the smallest complete pack,
used by the schema tests as the known-good input and by the validator tests as the
base they mutate. It is recorded in `data/design/themes.json` with
`status: "reference"`, and `iarch-theme list` and `apply` never offer it.

**Rejected.** *A test fixture outside `data/`.* It would keep CI green by leaving
the schemas unexercised by the step that exists to exercise them.

## D-T1-06 — seven schemas, closed, palette-only colours, token-only sizes

**Decision.** `data/schemas/theme-pack.schema.json` for the manifest and one schema
per remaining file (`theme-pack-palette`, `-layout`, `-motion`, `-sounds`, `-hypr`,
`-apps`), all draft-07, all with `additionalProperties: false`, all requiring
`_copyright` like every other document in `data/`. A pack file may not carry a
colour literal: colours are `palette.json` roles referenced by name, and the
validator rejects a `#` literal anywhere else. Sizes are named tokens from
`layout.json`'s scale, never bare numbers in a component.

**Rejected.** *One schema for the whole pack.* A pack is reviewed and edited one
file at a time; one schema would make every error message point at the pack instead
of the file, and `schema_version` would have to change for a motion-only edit.

## D-T1-07 — export is a capped `tar.gz`, import refuses everything hostile

**Decision.** `iarch-theme export <id> <file>` writes a gzip-compressed tar of the
pack directory, and refuses to produce one larger than 2 MB. `iarch-theme import
<file>` refuses an archive over 2 MB compressed or 8 MB unpacked, a member with an
absolute path, a `..` component, a symlink or hard link, an executable mode bit, a
file the pack format does not name, or a pack that fails validation — and it
imports into a new directory, never over an existing pack, without `--force`.

**Rejected.** *A zip file.* `tar.gz` needs no dependency beyond the standard
library, and its member metadata (mode, type, link target) is exactly what the
refusals above have to read.

## D-T1-08 — the apply pipeline is the animation pipeline, generalised

**Decision.** A dynamic apply runs: validate the pack → snapshot every file it will
touch → render each surface → write the active record → signal the running shell
over IPC → `hyprctl reload` → read `hyprctl configerrors` and count only lines that
were not there before → on any failure restore the snapshot, reload again, and
report what was refused and why → on success play the switch sound. The compositor
half lives in `iarch/lib/compositor.py` behind an injectable runner so the whole
pipeline is testable with fakes.

`iarch/cli/iarch_anim.py` keeps its own verified copy of the same sequence in this
part: it is 924 lines of tested code whose citations and rollback wording are
asserted by `tests/test_iarch_anim.py`, and moving it under a theme-format change
would put proven behaviour at risk for no gain in this part.

**Rejected.** *Write-then-hope with a warning.* The repository rule is that a
pipeline rolls back to the previous working state and tells the user; a half-applied
theme is a desktop nobody can describe.

## D-T1-09 — the active record gains `engine` and `overrides`, with a migration

**Decision.** `~/.config/iarch/theme.json` is `{schema_version, id, engine,
overrides}`; a bare `{"id": …}` — the shape every existing install has — is read as
`schema_version: 1`, `engine: "classic"`, no overrides, and is rewritten in the new
shape the first time anything writes it. Per-token user overrides live in
`~/.config/iarch/theme-overrides.json` under `data/schemas/theme-overrides.schema.json`,
so an override can be validated, exported and thrown away without touching the
selection. The repository ships the empty-but-valid default as
`data/theme-overrides.default.json`, the way it ships
`data/settings.default.json`, which is also what keeps the schema exercised by the
`data/` validation step in CI.

**Rejected.** *A new file for the new fields.* Two records that both claim to say
which theme is active is a drift this project would have to test for forever.

## D-T1-10 — `data/design/themes.json` is the catalogue of record

**Decision.** Both groups are listed in `data/design/themes.json` with, per pack:
`id`, `name`, `group`, `engine`, `status` (`shipped`, `planned`, `reference`),
`source_screenshot` where one exists, and `verified_against`/`source` for the record
itself as every other design record carries. `docs/themes/STATUS.md` is generated
from it by `iarch/cli/gen_theme_status.py`, which offers `--check` and is run in CI,
and a test fails when the generated document and the record disagree.

**Rejected.** *Hand-write the status document.* A hand-written status page is a
second catalogue, and the two drift in the direction that matters: the page says a
theme is done.

## D-T1-11 — `iarch/shell/` ships as a skeleton with the rules already enforced

**Decision.** This part creates the layout and the rules, not the shell:
`shell.qml` under 150 lines, `runtime/` pure QtQuick (no `Quickshell` import, so
`qmllint` and an offscreen test can read it), `services/` the only place a
`Quickshell.*` import is allowed below the entry point, `components/` and
`surfaces/` empty but README'd for Parts 2–4, and `tests/` holding a QtTest file
that runs where `qmltestrunner` exists. `tests/test_shell_layout.py` enforces the
folder set, the README sections, the line budgets, the header comments, the import
rule and the no-hex-colour rule in this part, so Part 2 inherits a shape it cannot
silently break.

**Rejected.** *Wait until Part 2 to create the folders.* The layout is what the
pack format's `layout.json` and `motion.json` sections are written against; deciding
it after the packs exist means rewriting packs.

## D-T1-12 — `iarch-sounds` is scheduled, not stubbed

**Decision.** `assets/sounds/` and its README ship in this part, because the six
Classic packs already name `assets/sounds/<id>/notify.ogg` and the folder's absence
is what makes the renderer warn. The `iarch-sounds` command itself is scheduled at
M4 (Part 6), where the sounds are synthesized; this part documents that and does not
ship an empty command that reports success.

**Rejected.** *A stub CLI.* A command that exists and does nothing is worse than a
documented schedule: it reads as shipped.
