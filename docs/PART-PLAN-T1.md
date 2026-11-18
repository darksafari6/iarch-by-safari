# Part T1 plan — strategy, engine decision, theme pack format, repository layout

This is the plan for the first part of the dynamic-themes work: the seven-part
schedule in `docs/THEMES-MILESTONES.md` starts here. It records
what was read before a line was written, what was decided, what will be built and
how each piece will be proven. The report that answers it is
`docs/PART-REPORT-T1.md`.

Numbering: `T1` is *themes* part 1. The repository already has a six-part glass
plan in [ROADMAP.md](ROADMAP.md) whose parts are numbered without a prefix, so the
`T` keeps the two schedules apart in file names, commit messages and test names.

## A. What was read first

| Read | What it settled |
| --- | --- |
| `README.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` | The user-state rules every new writer has to obey: read through `iarch/lib/configstore.py`, write only generated files, atomic writes, five-backup rotation, never write inside the repository at runtime |
| `docs/THEMES.md`, `data/themes/ids.json`, `data/themes/schema.json`, `data/themes/greenhouse.json` | The Classic catalogue is closed at six ids, each one a *flat* `data/themes/<id>.json` validated by `data/themes/schema.json` with `additionalProperties: false` |
| `iarch/cli/theme.py`, `iarch/cli/session_theme.py` | `iarch-theme` already dispatches `list`, `current` and `apply <session id>` to `session_theme`, which owns the snapshot/restore/action machinery (`_snapshot`, `_restore`, `_build_actions`, `_apply_actions`, `_write_choice`) and the per-surface renderers. That machinery is what the dynamic pipeline reuses rather than reinvents |
| `iarch/cli/iarch_anim.py:445-560` | The house pattern for a verified, rolling-back change: baseline `hyprctl configerrors` → atomic write → `hyprctl reload` → read errors again → count only *new* lines → restore the snapshot and reload again → `RefusedError` with the offending lines in the message. Citations for `reload` and `configerrors` are already established there against Hyprland v0.57.2 |
| `data/design/startup.json` (`exec_once`) | The Classic engine is started by the command `noctalia`; the same record's provenance note says the legacy v4 line started the shell "through quickshell's own binary and a `-c` flag" |
| `tests/test_data_files.py`, `.github/workflows/iarch-checks.yml` step "Validate every JSON file in data/" | `PAIRS` is written twice and compared by AST evaluation. Rule 4 of that step fails a schema no document uses, and rule 3 fails a document no schema covers — so a new pack family needs a committed reference pack, not only a schema |
| `tests/test_part3_acceptance.py` | Every `data/design/*.json` needs `verified_against` matching `v?\d+\.\d+` or `fetched YYYY-MM-DD`, plus a `source`; every `iarch/cli/*.py` or `tools/*.py` containing the literal `"--check"` must be run as `python <tool> --check` in the workflow |
| `tests/test_copyright_headers.py`, `tests/test_repo_paths.py`, `tools/naming_audit.py`, `tools/branding_lint.py` | New source files join a hand-maintained tuple; every `data/**/*.json` carries `_copyright`; markdown links must resolve; `noctalia-shell` is a banned token everywhere except the allowlist; `Noctalia` and `Quickshell` are banned on *product-level* display surfaces but allowed on identity-level ones (`scripts/*.sh`) |

## B. Research, and what it proved

Quickshell was read out of its own source tree through the GitHub API
(`quickshell-mirror/quickshell`, branch `master`, tag `v0.3.2`, LGPL-3.0, homepage
`quickshell.org`, upstream `git.outfoxxed.me/quickshell/quickshell`). The files read
are named beside each finding so a reader can check the same lines.

| Finding | Where it was read |
| --- | --- |
| A configuration is `<xdg config dir>/quickshell/<name>/shell.qml`; `qs` runs `default`, `-c/--config <name>` runs a named one, `-p/--path` runs any file or folder. Environment equivalents: `QS_CONFIG_NAME`, `QS_CONFIG_PATH` | `src/launch/parsecommand.cpp` (`addConfigSelection`, and its own examples), `src/launch/command.cpp` (`locateNamedConfig`) |
| `-n/--no-duplicate` exits immediately if another instance of the same configuration is already running | `src/launch/parsecommand.cpp` |
| `-d/--daemonize` detaches from the controlling terminal | `src/launch/parsecommand.cpp` |
| `list [-a/--all] [-j/--json] [--show-dead]`, `kill`, `log [-t N] [-f]` are subcommands, each with `-i/--id` (a unique substring is enough) and `--pid` instance selection | `src/launch/parsecommand.cpp` |
| IPC from outside is `quickshell ipc {show, call <target> <function> [args…], wait <target> <signal>, listen <target> <signal>, prop get <target> <property>}`; `msg` is the deprecated spelling of `ipc call` | `src/launch/parsecommand.cpp`, `src/ipc/ipccommand.hpp` |
| Its own crash handler refuses to restart when the crash happened within 10 s of launch, "to avoid a crash loop" | `src/launch/main.cpp` (`checkCrashRelaunch`) |
| QML modules: `Quickshell` (core, including `PanelWindow` with `anchors`, `margins`, `exclusiveZone`, `exclusionMode`, `aboveWindows`, `focusable`), `Quickshell.Io` (`Socket`, `Process`, `FileView`, `JsonAdapter`, `IpcHandler`, `DataStream`), `Quickshell.Services.Notifications` | `src/core/module.md`, `src/io/module.md`, `src/services/notifications/module.md`, `src/window/panelinterface.hpp` |
| The notification server is the QML type `NotificationServer`; it advertises capabilities rather than assuming them (`bodySupported`, `bodyMarkupSupported`, `persistenceSupported`, …), re-registers when the bus name is released, and `Notification` objects "must be acquired from a NotificationServer" | `src/services/notifications/qml.hpp`, `src/services/notifications/server.hpp`, `src/services/notifications/notification.hpp` |
| A `Hyprland` QML singleton exists, with `usingLua`, `requestSocketPath`, `eventSocketPath`, `focusedMonitor`, `focusedWorkspace`, `activeToplevel`, `monitors`, `workspaces`, `toplevels`, `dispatch(request)`, `monitorFor(screen)` and `refresh*()` | `src/wayland/hyprland/ipc/qml.hpp` |
| Build facts a packager needs: Qt ≥ 6.6, private Qt headers for `qt6declarative` (and `qt6wayland` before Qt 6.10), must be rebuilt for each Qt release, `-DDISTRIBUTOR=…` for distro builds | `BUILD.md` |

What could **not** be verified from here, and is therefore a `TODO(verify)` in code
and a row in [UNVERIFIED.md](UNVERIFIED.md) under the new `ENG-` prefix:

- the package name and repository that ships Quickshell on Arch and on Fedora —
  `archlinux.org` and `aur.archlinux.org` are not reachable from this environment
  (`ENG-01`);
- that `quickshell --config iarch --daemonize` leaves an instance `list --json`
  reports, and that `ipc call` reaches an `IpcHandler` in this repository's
  `shell.qml` — the CLI was read, never run; there is no Qt, no Quickshell and no
  compositor in this sandbox (`ENG-02`, `ENG-03`);
- how fast the Classic engine releases `org.freedesktop.Notifications` after it is
  stopped, which is what decides whether one notification server is running at a
  time (`ENG-04`).

## C. Decisions

Recorded in full, with the alternatives each one rejected, in
[DECISIONS.md](DECISIONS.md) as `D-T1-01` … `D-T1-12`. In one line each:

1. **D-T1-01** — two engines, one at a time: `classic` (the shell this session
   already runs) and `dynamic` (a second QML engine, named "iArch Shell" to the
   user). `classic` stays the default until `dynamic` passes QA.
2. **D-T1-02** — the second engine is Quickshell, because it is the toolkit the
   first engine is already built on, it is LGPL-3.0, and the layer-shell,
   notification-server, Hyprland-IPC and PipeWire surfaces Part 3 and Part 4 need
   are its own modules rather than code this project would have to write.
3. **D-T1-03** — pack `engine` is `"ishell"` (the value the format specifies) and
   the runtime engine id is `dynamic`; one table maps the two and a test holds them
   together.
4. **D-T1-04** — dynamic packs are directories: `data/themes/<id>/{theme,palette,
   layout,motion,sounds,hypr,apps}.json`. The Classic six keep their flat
   `data/themes/<id>.json` files unchanged.
5. **D-T1-05** — one committed reference pack, `data/themes/dynamic-reference/`,
   exists because CI rule 4 refuses a schema no document uses; it is `status:
   "reference"` in `data/design/themes.json`, so `list` and `apply` never offer it.
6. **D-T1-06** — seven pack schemas plus `design-themes.schema.json`, all
   draft-07, all `additionalProperties: false`, every colour reachable only from
   `palette.json`, every size a named token.
7. **D-T1-07** — export is a `tar.gz` of the pack directory, capped at 2 MB,
   refusing executables, absolute paths, symlinks and anything outside the pack.
8. **D-T1-08** — the apply pipeline mirrors `iarch_anim.py`: validate → snapshot →
   render → write the active record → signal the shell → reload the compositor →
   compare `configerrors` → restore and reload again on any failure. Shared
   compositor helpers move to `iarch/lib/compositor.py`; `iarch_anim.py` keeps its
   own verified copy in this part.
9. **D-T1-09** — `~/.config/iarch/theme.json` gains `engine` and `overrides`
   beside `id`, and `~/.config/iarch/theme-overrides.json` carries per-token
   overrides under `schema_version: 1` with a migration from a bare `{"id": …}`.
10. **D-T1-10** — `data/design/themes.json` is the catalogue of record for both
    groups, with a `status` and a `source_screenshot` per pack; `docs/themes/
    STATUS.md` is generated from it by `iarch/cli/gen_theme_status.py --check`.
11. **D-T1-11** — `iarch/shell/` ships as a skeleton in this part: an entry point
    under 150 lines, pure-QtQuick runtime files that `qmllint` and an offscreen
    test can read, impure services isolated in `services/`, and a README in every
    folder. Part 2 fills it.
12. **D-T1-12** — `iarch-sounds` and `assets/sounds/*` content are **not** built
    here: the folder and its README ship, the CLI is scheduled at M4, and this
    part says so rather than shipping an empty command.

## D. What gets built, task by task

Line budgets are the repository rule: 300 lines maximum per file, one
responsibility, a header comment naming purpose, inputs, outputs and
dependencies, and a README in every folder.

### TASK 1 — engine decision and `iarch-shell-switch`

| File | Role | Budget |
| --- | --- | --- |
| `docs/THEMES-ARCHITECTURE.md` | The decision: why a second engine, what is shared with Classic, what is not, one shell and one notification server at a time, the 10-second rollback contract, why Classic stays the default | ~260 |
| `iarch/cli/theme_engine.py` | The engine catalogue as data: ids, user-facing names, binaries, launch and stop commands, config roots, notification-server ownership, and the `ishell`↔`dynamic` map. Also the read-only probes (which engines are running, who owns the bus name) | 300 |
| `iarch/lib/compositor.py` | `hyprctl reload` / `configerrors` behind an injectable runner, plus the "only new lines count" comparison | 200 |
| `iarch/cli/iarch_shell_switch.py` | `iarch-shell-switch status|to <engine>|rollback`: snapshot → stop → start → verify within the timeout → roll back, reporting every step | 300 |
| `scripts/iarch-shell-switch.sh` | Launcher, same shape as `scripts/iarch-theme.sh` | 40 |
| `scripts/iarch-link-cli.sh` | One `COMMANDS` entry added | +1 |
| `iarch/cli/iarch_doctor.py` | A `shell` subcommand that reports running engines and the notification-server owner | +40 |
| `tests/test_theme_engine.py`, `tests/test_shell_switch.py` | Catalogue invariants; switch with fake processes and a fake runner: success, stop-failure, start-timeout rollback, already-active, missing binary | ~600 |

### TASK 2 — the theme pack format

| File | Role | Budget |
| --- | --- | --- |
| `data/schemas/theme-pack.schema.json` | The manifest: `schema_version` 1, `id`, `name`, `description`, `engine`, `mode`, `fonts`, `shape`, `surfaceStyle`, `accentStrategy`, `variants`, `capabilities`, `credits`, `_copyright` | 300 |
| `data/schemas/theme-pack-{palette,layout,motion,sounds,hypr,apps}.schema.json` | One schema per file of the pack | 120 each |
| `data/themes/dynamic-reference/*.json` | The reference pack: the smallest thing that is a whole pack | 7 files |
| `iarch/cli/theme_pack_validate.py` | Per-file schema validation plus the structural rules: unknown keys, absolute paths, symlinks, executables, size caps, colours that are not palette references, sizes that are not tokens | 300 |
| `tests/test_theme_pack_schema.py` | Every schema is draft-07 and well formed; the reference pack validates; each rule rejects a pack that breaks it | ~400 |

### TASK 3 — repository layout

`iarch/shell/{shell.qml,runtime/,services/,components/,surfaces/,tests/}`,
`assets/sounds/`, `docs/themes/`, and a README in every folder named above.
`iarch/README.md` and `iarch/cli/README.md` gain the new rows.
`tests/test_shell_layout.py` holds the shape: folder set, README length and
sections, per-file line budgets, header comments, no `Quickshell` import outside
`shell.qml` and `services/`, no hex colour outside the token file.

### TASK 4 — `iarch-theme` grows the pack verbs

| File | Role | Budget |
| --- | --- | --- |
| `iarch/cli/theme_packs.py` | Discovery and loading of both groups, `list --json` payload | 260 |
| `iarch/cli/theme_pack_apply.py` | The dynamic apply pipeline of D-T1-08 | 300 |
| `iarch/cli/theme_pack_archive.py` | `export` / `import` with the caps and refusals of D-T1-07 | 240 |
| `iarch/cli/theme_pack_cli.py` | argparse for `list --json`, `apply`, `validate`, `export`, `import`, `preview`, `rollback` | 260 |
| `iarch/cli/theme.py` | Delegation only: pack verbs and `list --json` route to `theme_pack_cli`; existing routes are untouched | +25 |
| `tests/test_theme_packs.py`, `tests/test_theme_pack_apply.py`, `tests/test_theme_pack_archive.py` | Success, validator-failure rollback, shell-signal-failure rollback, compositor-error rollback, export/import round trip, oversized and hostile archives | ~900 |

### TASK 5 — records and the catalogue of record

`iarch/cli/theme_records.py` (active record, overrides, migration),
`data/design/themes.json` + `data/schemas/design-themes.schema.json`,
`data/theme-overrides.default.json` + `data/schemas/theme-overrides.schema.json`
(the shipped default is what keeps a schema for a *user* file exercised by the
`data/` validation step), `iarch/cli/gen_theme_status.py` (`--check`, wired into
the workflow), `docs/themes/STATUS.md` (generated), `tests/test_theme_records.py`,
`tests/test_theme_catalogue.py` (the drift test).

### TASK 6 and TASK 7 — assets policy and milestones

`docs/THEMES-ASSETS.md` and `docs/THEMES-MILESTONES.md`, plus the pointer rows in
`docs/THEMES.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md` and `README.md`'s
documentation table.

### TASK 8 — the test set

Every test above, plus `tests/test_part_t1_acceptance.py`, which asserts the part's
own acceptance checklist rather than trusting it: the three documents exist and
agree with each other and with the code, the schemas accept the reference pack and
reject each bad one, `list --json` carries both groups, `apply` rolls back, the
doctor check reports one shell and one notification server, and the status record
has not drifted from the generated document.

## E. Gates that must pass before the report is written

```bash
python3 -m unittest discover -s tests -p 'test_*.py'      # whole suite
bash -n <every .sh> && shellcheck --severity=warning <every .sh>
./tests/session-install.sh ./tests/managed-files.sh ./tests/package-audit.sh \
  ./tests/test_packages.sh ./tests/test_iarch_common.sh ./tests/test_uninstall.sh
python3 tools/notices.py --check && python3 tools/iarch_brand.py --check
python3 tools/branding_lint.py && python3 tools/naming_audit.py --check
python3 iarch/cli/gen_theme_status.py --check             # new
# plus every `--check` the workflow already runs
```

`CHANGELOG.md` gains one entry and `VERSION` is bumped once, at the end.
