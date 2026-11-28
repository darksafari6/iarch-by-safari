# Themes architecture: two engines, one at a time

This document is the decision the dynamic-themes work starts from. It says what the
two shell engines are, why the second one exists, what the two share, what they do
not, and what has to be true before either one is allowed to be the default. The
schedule is in `docs/THEMES-MILESTONES.md`, the pack format is in
`docs/THEMES-ASSETS.md` and in `data/schemas/theme-pack.schema.json`,
and the reasoning behind each choice — with the alternatives it rejected — is in
[DECISIONS.md](DECISIONS.md) as `D-T1-01` to `D-T1-12`.

The six themes that ship today are documented in [THEMES.md](THEMES.md). Nothing in
this document changes them.

## The two engines

| | Classic | iArch Shell |
| --- | --- | --- |
| Engine id | `classic` | `dynamic` |
| Pack `engine` value | `classic` | `ishell` |
| Catalogue group | `classic` | `dynamic` |
| Status today | shipped, verified end to end | skeleton; the shell itself is milestone M1 |
| Process name | `noctalia` | `quickshell` |
| Reads its configuration from | `~/.config/noctalia/` | `~/.config/quickshell/iarch/shell.qml` |
| Started by | the `noctalia` entry of `.config/hypr/startup.lua` | `iarch-shell-switch to dynamic`, and after M5 the same startup module |
| Provides a notification server | yes | yes |
| Provides the lock screen | yes | not until M2 |
| Default on a fresh install | **yes** | no |

Both engines are named for what they are in this product — "Classic" and "iArch
Shell" — everywhere a person reads: the switch command, the doctor report, the
settings toggle and the Welcome card. The upstream projects' own names appear in
this document, in the installer's dependency list and in the credit pages, which is
what `tools/branding_lint.py` enforces and what [BRANDING.md](BRANDING.md) states.

Engine ids, user-facing names, binaries, launch commands and the `ishell`↔`dynamic`
map live in exactly one place: `iarch/cli/theme_engine.py`. Nothing else in the
repository is allowed to translate between a pack's `engine` value and a running
engine, and a test holds the map total over both catalogues.

## Why a second engine at all

The session's appearance is written into files another program reads: a palette
JSON, a `config.toml`, a Hyprland include, GTK and Kvantum sheets, a Kitty include.
That is how the six Classic themes work today, and it works — `iarch-theme apply`
renders every one of those surfaces atomically and rolls back on a compositor
rejection. What it cannot do is change *shape*: the geometry of a bar, the corner
radius of a card, which surfaces blur, how a workspace transition is composed, what
a notification looks like while it arrives. Those are not configuration keys in the
pinned release; `data/design/noctalia.json` records the verified key set and, beside
it, what this project deliberately does not emit because no verified key exists.

So the dynamic themes need a shell whose every colour, radius, font, spacing step
and duration is read from a pack at runtime. Writing that shell means writing a
layer-shell client, a notification daemon, a lock client, compositor IPC and audio
state — and then maintaining all of it against every compositor release. Building it
on an existing toolkit means writing the shell and nothing else.

## What the second engine is built on

Quickshell, read out of its own source tree (`quickshell-mirror/quickshell`,
branch `master`, tag `v0.3.2`, LGPL-3.0, upstream `git.outfoxxed.me`). Every claim
below names the file it was read from; none of it is assumed.

| What it provides | Where it was read |
| --- | --- |
| Configurations are discovered as `<xdg config dir>/quickshell/<name>/shell.qml`, run with `--config <name>`, `--path <file or dir>`, or the `QS_CONFIG_NAME`/`QS_CONFIG_PATH` environment | `src/launch/parsecommand.cpp` (`addConfigSelection`), `src/launch/command.cpp` (`locateNamedConfig`) |
| `--no-duplicate` exits immediately when another instance of the same configuration is running — the engine's own enforcement of one shell at a time | `src/launch/parsecommand.cpp` |
| `--daemonize` detaches from the controlling terminal, so a shell started by a command line survives it | `src/launch/parsecommand.cpp` |
| `list [--json] [--all] [--show-dead]`, `kill`, `log [-t N] [-f]`, with `-i/--id` (a unique substring is enough) and `--pid` instance selection | `src/launch/parsecommand.cpp` |
| IPC from outside: `ipc show`, `ipc call <target> <function> [arguments…]`, `ipc wait`, `ipc listen`, `ipc prop get`; `msg` is the deprecated spelling of `ipc call` | `src/launch/parsecommand.cpp`, `src/ipc/ipccommand.hpp` |
| Its crash handler restarts the shell, but refuses when the crash came within 10 seconds of launch — "Not restarting to avoid a crash loop" | `src/launch/main.cpp` (`checkCrashRelaunch`) |
| QML modules: `Quickshell` (core, including `PanelWindow` with `anchors`, `margins`, `exclusiveZone`, `exclusionMode`, `aboveWindows`, `focusable`), `Quickshell.Io` (`Socket`, `Process`, `FileView`, `JsonAdapter`, `IpcHandler`, `DataStream`), `Quickshell.Services.Notifications` | `src/core/module.md`, `src/io/module.md`, `src/window/panelinterface.hpp`, `src/services/notifications/module.md` |
| The notification server is the QML type `NotificationServer`; it advertises capabilities (`bodySupported`, `bodyMarkupSupported`, `persistenceSupported`, …) instead of assuming them, re-registers when the bus name is released, and `Notification` objects must be acquired from it | `src/services/notifications/qml.hpp`, `src/services/notifications/server.hpp`, `src/services/notifications/notification.hpp` |
| A `Hyprland` singleton with `usingLua`, `requestSocketPath`, `eventSocketPath`, `focusedMonitor`, `focusedWorkspace`, `activeToplevel`, `monitors`, `workspaces`, `toplevels`, `dispatch(request)` and `monitorFor(screen)` | `src/wayland/hyprland/ipc/qml.hpp` |
| Services already written: MPRIS, PipeWire, UPower, polkit, status notifier, greetd, PAM | `src/services/` |
| Packaging facts: Qt ≥ 6.6, private Qt headers for `qt6declarative` (and `qt6wayland` before Qt 6.10), a rebuild per Qt release, `-DDISTRIBUTOR=` for distro builds, optional jemalloc and a crash handler | `BUILD.md` |

Two of these decide the design rather than merely enabling it. `--no-duplicate`
means a second iArch Shell instance cannot start behind the first one's back, and
the 10-second crash-loop window is the same budget this project gives a switch to
prove the engine came up: a shell that cannot start in ten seconds is one its own
toolkit would not retry either.

What is **not** verified, and is therefore a `TODO(verify)` in the code and an `ENG-`
row in [UNVERIFIED.md](UNVERIFIED.md): the package that ships this toolkit on Arch
and on Fedora (`ENG-01`, neither package index was reachable from the environment
this was written in), that `--daemonize` leaves an instance `list --json` reports
(`ENG-02`), that `ipc call` reaches an `IpcHandler` in this repository's `shell.qml`
(`ENG-03`), how quickly the Classic engine releases the notification bus name when
it is stopped (`ENG-04`), the two session-bus lookups that name the notification
server's owner (`ENG-05`), and the absence of a verified graceful-exit command for
the Classic engine (`ENG-06`).

## Exactly one shell, and exactly one notification server

Two shells on one compositor means two layer-shell surfaces, two lock clients and
two processes that both want `org.freedesktop.Notifications`. Whichever wins the bus
name is whichever asked first, and a desktop whose behaviour depends on a race is a
desktop nobody can diagnose. So:

- `iarch-shell-switch` stops one engine before it starts the other, and refuses to
  act at all when it finds two running — it will not guess which one to keep;
- `iarch-doctor shell` reports both engines, which one the record selects, which
  process owns the notification bus name, and any *other* notification daemon in the
  process table (the read-only probe `notify-test` already used);
- the dynamic engine is started with `--no-duplicate`, so a second instance of it
  cannot be started by accident;
- a violation is a sentence with the pids in it, not a boolean.

These are safeguards, not a system-wide guarantee: independent processes can
start outside the switch, and a notification server can acquire the D-Bus name
later. Live handoff and ownership enforcement remain UNTESTED-LIVE; the dynamic
session entry stays guarded until that and other readiness gaps are resolved.
Manual rollback stops and rechecks the other engine before starting the previous
one, and refuses to start it if the other engine cannot be proved stopped.

## Switching: the ten-second contract

`iarch-shell-switch to <engine>` is the only command that changes the running
engine. Its steps, in `iarch/cli/shell_switch.py`, are:

1. **Preflight.** Refuse before touching anything when the target's binary is not
   installed or, for the dynamic engine, when `~/.config/quickshell/iarch/shell.qml`
   does not exist. Finding that out after stopping a working shell is how a session
   ends up with none.
2. **Snapshot.** Write `~/.local/state/iarch/shell-switch.json` — the previous
   engine, its pids, the previous record and the budget — before anything is
   stopped. This is what `rollback` restores, and it is written first because a
   rollback that has to reconstruct the past is a rollback that guesses.
3. **Stop.** Ask the engine to exit through its own verified command when it has
   one (the dynamic engine's `kill`), then signal the pids the process table named,
   with a grace period before anything stronger. Nothing is started until the old
   engine is gone.
4. **Start.** Spawn the target detached, in its own session, with its standard
   streams closed, so it outlives the command that started it.
5. **Prove it is up.** Poll inside the budget — ten seconds by default. A process in
   the table is the weak proof; an engine that lists its own instances
   (`list --json`) is the strong one, and the report says which of the two it got.
6. **Roll back on any failure.** Stop the half-started engine, start the previous
   one again, prove *it* is up, restore the record, and say what failed, why, and
   what the session is running now. The exit status is 1, never 0.
7. **Record.** Only now write `~/.local/state/iarch/engine.json`. A legacy
   `~/.config/iarch/shell-engine.json` is read only until the new record exists;
   it is not deleted or overwritten by migration.

Exit statuses: 0 when the session runs the engine that was asked for, 1 when the
switch was refused or rolled back, 2 on a usage or data error. `--dry-run` prints
the plan and changes nothing; `--json` prints the whole report, which is what a test
or the settings application reads.

`iarch-shell-switch rollback` restores the snapshotted engine by hand and stops the
other one — the recovery path for a person who does not want to work out which
engine is which.

## What the two engines share

Sharing is the point: a theme that has to be authored twice is a theme that will be
authored once. Everything below is written once and consumed by both engines.

| Shared | Where it lives | How the dynamic engine reaches it |
| --- | --- | --- |
| The palette generators and the contrast gate | `iarch/cli/contrast_check.py`, `iarch/cli/render_noctalia.py`, `iarch/lib/renderers.py` | The pack's `palette.json` is the input; the gate runs before anything is written, exactly as it does today |
| The Hyprland include a theme renders | `hypr/generated/theme.lua`, written by `iarch/cli/session_theme.py` | The same generated file, from the pack's `hypr.json` section; the compositor does not know or care which shell is running |
| GTK, Qt/Kvantum, Kitty, Starship, fontconfig, cursor and icon rendering | `render_gtk_css.py`, `render_kvantum.py`, `render_kitty_theme`, `render_starship_config`, `gen_fontconfig.py` | Unchanged: these are toolkit surfaces, not shell surfaces, and a pack renders them through the same functions |
| Shortcuts and the shortcut overlay | `data/keybinds.default.json`, `iarch/cli/iarch_keybinds.py`, `iarch-cheatsheet` | The keyboard map is the compositor's, so both engines inherit it; the overlay reads the same record |
| Backup, restore and atomic writes | `iarch/lib/configstore.py` (five-backup rotation, `atomic_write`, GENERATED headers) | Every file the dynamic pipeline writes goes through it, which is what makes its rollback byte-exact |
| The mode switches | `iarch/lib/modes.py`, `iarch-gamemode`, `iarch-focus` | A mode is a bundle of switches that already exist; the dynamic engine reads the same records and its own motion tokens |
| The theme selection record | `~/.config/iarch/theme.json` | One record, extended with `engine` and `overrides` (`D-T1-09`), read by both |
| Diagnostics | `iarch-doctor` | The `shell` check reports either engine; `notify-test` and `dnd` stay Classic-specific until M5 |

## What they do not share

| Not shared | Why |
| --- | --- |
| The shell's own surfaces — bar, dock, launcher, control center, notifications, OSD, lock | This is the work of Parts 2 to 4: the dynamic engine draws them from pack tokens rather than from a pinned release's configuration keys |
| The palette *file format* the Classic shell reads | `~/.config/noctalia/palettes/iarch-active.json` is written for one program's schema. The dynamic engine reads `palette.json` from the pack directly and never needs that projection |
| The shell's IPC verbs | Classic is driven by the 66 verbs recorded in `data/design/noctalia-ipc.json`; the dynamic engine is driven by an `IpcHandler` target this project defines (`iarch.theme`, function `apply`) |
| Lock, idle and the greeter | Verified against the pinned Classic release and `hyprlock`; the dynamic engine's lock surface arrives at M2 and inherits the same records, not the same code |
| The Classic engine's own configuration schema | Nothing in the dynamic engine writes a key it has not verified for the engine it targets, which is the rule `data/design/noctalia.json` already enforces for Classic |

## Why Classic stays the default

Everything this repository claims about a working session — the installer's 26
steps, the shortcut map, the two mode switches, the doctor's notification probes,
the greeter, the Kvantum and GTK sheets — is verified against the pinned Classic
release. The dynamic engine starts as a skeleton with a layout and a set of enforced
rules (`D-T1-11`), and becomes the default only when the M5 QA gate has been run on
a real session and recorded. Until then:

- the installer currently leaves Classic as the default; installing both engines
  and their dependencies is planned for M5, not yet implemented;
- the planned Welcome tour card and Settings → Appearance toggle (M5) will call
  `iarch-shell-switch` rather than starting a process themselves; neither is a
  completed Dynamic-engine opt-in flow yet;
- a switch that fails leaves the session running the engine it was running, and says
  so in one sentence;
- `docs/themes/STATUS.md`, generated from `data/design/themes.json`, is the only
  place that says how far the dynamic work has got, so a claim about it cannot drift
  from the record.

## Where the code lives

| Path | Responsibility |
| --- | --- |
| `iarch/cli/theme_engine.py` | The engine catalogue as data, and the read-only probes over it |
| `iarch/cli/engine_state.py` | The two records, and the one report of what the session says about itself |
| `iarch/cli/engine_steps.py` | The three actions a switch is made of: stop, start, prove |
| `iarch/cli/shell_switch.py` | The sequence, its preflight and its rollback |
| `iarch/cli/iarch_shell_switch.py` | The `iarch-shell-switch` command line |
| `iarch/lib/runner.py` | One way to run a command: argument lists, timeouts, "could not be asked" |
| `iarch/lib/processes.py` | The process table, spawning detached, and a guarded terminate |
| `iarch/lib/compositor.py` | `hyprctl reload`, `configerrors`, and the "only new lines count" comparison |
| `iarch/lib/dbus_probe.py` | Who owns a session-bus name, and which pid is behind it |
| `iarch/shell/` | The dynamic engine's QML: entry point, runtime, services, components, surfaces |
| `scripts/iarch-shell-switch.sh` | The public launcher, linked by `scripts/iarch-link-cli.sh` |

Every one of those modules keeps to the repository's rules: one responsibility, no
more than 300 lines, a header comment naming purpose, inputs, outputs and
dependencies, and an injectable runner so the logic is testable with no compositor,
no shell and no display in the room.

Dynamic theme rollback checks the saved post-apply file fingerprints and current
selection before restoring; changed files or stale checkpoints are refused. Pack
archive import also bounds decompressed tar bytes before parsing extended metadata.
