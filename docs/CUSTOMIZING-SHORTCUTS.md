# Customizing shortcuts

How to change a key on this desktop, what the checker will refuse and why, and how
to get back to the map that ships when a change goes wrong.

Nothing here is a hope. Every rule below is enforced by
`iarch/cli/iarch_keybinds.py` and tested in `tests/test_iarch_keybinds.py`; what
could not be verified on the machine this was written on is listed at the end and
in [UNVERIFIED.md](UNVERIFIED.md) rather than described as though it worked.

## The model: one record, three renderings

The keyboard map is data. `data/keybinds.default.json` holds one entry per bind
and is the only place a bind is declared. Three things are rendered from it:

| Rendering | File | Command |
| --- | --- | --- |
| The Lua the compositor reads | `.config/hypr/generated/keybinds.lua` | `iarch-keybinds generate --write` |
| The documentation | `docs/SHORTCUTS.md` | `python3 tools/render_shortcuts.py --write` |
| The Settings page | `iarch/settings-app/iarch_settings/pages/shortcuts.py` | reads the record at draw time |

Until Part 5 the direction was the other way round: the Lua was hand-written and a
tool extracted the record out of it. That is why the Shortcuts page was read-only
and why the documentation could drift — a report about a file cannot be edited,
because the next extract overwrites the edit.

**Do not hand-edit the generated Lua.** It opens with a header saying so, and the
next render replaces the file and the edit with it.

## Where your changes live

The shipped record is not yours to edit — an update replaces it. Your differences
go in a second file:

```
~/.config/iarch/keybinds.json
```

Set `IARCH_CONFIG_DIR` to put it somewhere else. The two are merged by `id`, and
an override carries **only the fields it changes**, so everything you did not
mention keeps coming from the shipped record:

```json
{
  "bindings": [
    { "id": "applications.terminal", "key": "Return", "mods": ["SUPER", "SHIFT"] }
  ]
}
```

That moves the terminal from `Super+Return` to `Super+Shift+Return` and leaves its
action, description and category alone. The shape is a **list** of partial
bindings, each carrying its own `id` — not a mapping keyed by id.

A binding whose id is not in the shipped record is one you added, and is appended.
Adding one means supplying every required field: `id`, `mods`, `key`, `action`,
`description`, `category`, `enabled`, `locked`.

A broken override file does not break the session. It is reported and the
defaults are used, which is deliberate: the failure mode this system has to
survive is its own worst output.

## Making a change

The Shortcuts page in Settings shows the map and **does not yet offer to change
it** — the recorder and action picker that would put the collision check in front
of you are later work. The CLI does it today:

```sh
iarch-keybinds list                              # what is bound, by category
iarch-keybinds set <id> --mods SUPER --key G     # rebind one entry
iarch-keybinds add custom.x --mods SUPER --key F13 \
    --description "Scratch pad" --category Custom --exec "~/.local/bin/pad.sh"
iarch-keybinds disable <id> [<id> …]             # turn off, keeping any rebind
iarch-keybinds enable <id> [<id> …]              # turn back on
iarch-keybinds export [--all] > mine.json        # your differences, to move them
iarch-keybinds import mine.json [--replace]      # and back again
iarch-keybinds reset --all                       # drop every difference
iarch-keybinds check                             # every problem, with severities
```

`iarch-keybinds` is the name once `scripts/iarch-link-cli.sh` has run — that
script writes `~/.local/bin/iarch-keybinds` and tells you if that directory is
not on your `PATH`. From a checkout without it, spell any of the above
`python3 iarch/cli/iarch_keybinds.py …`; it is the same code path either way.
Every command also takes `--config-home DIR` to work against another home, which
is what the tests use.

Then reload the compositor config for the change to take effect.

### What each of them does before it writes

One change, four steps, always in this order — and the order is the safety:

1. **Validate the map the change would produce**: the shipped defaults plus your
   differences with this edit applied. If it has an error or a conflict, every
   problem is printed and the command exits **1** having changed nothing. There
   is nothing to undo, which is the whole point of validating first.
2. **Confirm**, but only where the change discards more than you named —
   `reset --all` and `import --replace`. A targeted `reset <id>` keeps a backup
   and does not ask. The prompt refuses to guess: with no terminal to read an
   answer from it exits **2** rather than assuming yes, and `--yes` is how a
   caller that has read what the command does says so. That is what the recovery
   bind passes, because it fires while the session may be broken and a prompt on
   a screen that is not drawing is worse than no prompt.
3. **Back up both files** — your override and the session's generated Lua — into
   `~/.local/state/iarch/backups/`.
4. **Write both**, each through a temporary file in its own directory that is
   renamed into place, so a reader never sees a half-written map. If a write
   fails halfway — a full disk, a read-only mount — both files are put back from
   the backups and the command exits **1** saying so.

So: **0** is done, **1** is refused, cancelled or failed to write, **2** is bad
input. A batch (`disable a b c`) is one change, so it validates as one and lands
whole or not at all; there is no half-disabled batch.

Two refusals worth knowing about before you hit them. An id is
`category.subject`, in lower case, so `add custom` is refused and `add custom.x`
is not. And a key is checked against the keysym list this repository pins: a
character is refused with the word to use instead (`.` → `period`), a spelling
the list has in another case is snapped to the pinned one (`Backspace` →
`BackSpace`, because the compositor resolves key names case-insensitively and one
key should not end up written two ways), and a dispatcher leaf is expanded to the
path the record stores (`window.close` → `hl.dsp.window.close`) or refused with a
suggestion if the tree has nothing close.

## The layers

A modifier layer is a budget. Spending it on the wrong thing is what makes a
desktop feel arbitrary, so each one has a job and the checker enforces it:

| Layer | What it is for | Enforcement |
| --- | --- | --- |
| `Super` | The primary layer: the things you reach for constantly | — |
| `Super+Shift` | The secondary layer: the counterpart of a primary bind | — |
| `Super+Ctrl` | The session's own state: workspace navigation on the arrows, the two modes and appearance on letters, and the remedy for a plain `Ctrl+letter` | — |
| `Ctrl+Alt` | **Recovery and system only** | error for anything else |
| `Super+Ctrl+Alt` | **Recovery and system only** | warning; nothing is bound there |
| `Super+Alt` | **Deliberately empty** | error for anything at all |

`Super+Alt` being empty is not an oversight. An empty layer is somewhere a later
bind can go without taking a key away from anything else, which is worth more
than filling it now.

`Ctrl+Alt` is an error rather than a warning because the recovery combo lives on
exactly that layer, and a collision there is a safety net that does not fire when
it is needed. `Super+Ctrl+Alt` is a warning rather than an error because the two
binds that predated the rule both worked, and refusing a working bind is not the
same thing as reporting one. Those two — moving a window to the next and previous
workspace, carried over from the v1 map — were reported on every run instead of
being quietly exempted, and they have now moved to `Super+Ctrl+N` and
`Super+Ctrl+P`: the layer this checker offers when it refuses a plain
`Ctrl+letter`, and the layer that already owns workspace navigation on the
arrows. The shipped map reports nothing at all, so a warning from it means
something reached for the recovery layer again.

A plain `Ctrl+letter` is refused outright: a global `Ctrl+C` or `Ctrl+S` takes
that key from every application at once. The message offers `Super+Ctrl` and
`Super+Shift`. It used to offer `Ctrl+Alt` too, which the layer rule reserves — a
checker that recommends its own next refusal sends you in a circle. `--i-know`
downgrades the refusal to a warning and is the only way past it.

## Nothing destructive without a confirmation

A key that ends a session is a key that ends it by accident: a mistyped
combination, a child, a cat. So the checker refuses to bind an action that runs
the moment the key goes down, in every spelling it can be written:

- `hl.dsp.exit` — the compositor's own dispatcher, which takes no arguments
- noctalia `session logout`, `reboot`, `reboot-uefi`, `shutdown`
- the `noctalia msg session …` argv form the older map used
- `systemctl poweroff|reboot|halt`, `loginctl terminate-session`,
  `hyprctl dispatch exit`, and `shutdown`/`poweroff`/`reboot`/`halt` by any path

What goes on the key instead is the **menu**, because the menu is the
confirmation. `Super+Shift+E` is `panel-toggle session`: `session` is a builtin
panel id in noctalia v5.4.1, so the shell draws logout, reboot and shutdown
behind a click. `lock` and `suspend` stay bindable directly, because both are
undoable — you log back in, or you wake the machine.

## Locked bindings

Seven bindings are locked **by role**: close window, lock, exit, open terminal,
open settings, cheat sheet, power menu. A locked binding can be rebound but not
deleted, and an override that tries to delete one is refused.

The reason is that a session with no way to close a window, or no way back into
the keyboard map, is a session that needs a reboot — and "needs a reboot" is the
one outcome a shortcut system must never produce. Locked is keyed by `id` rather
than by key, so re-laying out the map cannot quietly drop one.

This `locked` is not the compositor's `locked` bind option, which means "keep
working while the screen is locked" and lives under `flags` on the media keys.
Two things with the same name doing different jobs is exactly the confusion the
separate fields exist to prevent.

## Getting back to the map that ships

```sh
iarch-keybinds reset --all        # drop every difference
iarch-keybinds reset <id> …       # drop named ones only
```

`reset --all` **asks first**, because it discards more than you named: every
difference you ever saved, not the one you were thinking about. `--yes` is how a
caller that has read what it does answers in advance, and with no terminal to ask
— a script, a bind, CI — the command exits **2** rather than assuming an answer.
A targeted `reset <id>` does not ask; it drops what you named and keeps a backup.

`reset` backs your override up into `~/.local/state/iarch/backups/` before it
touches anything, validates the map the reset would produce, and only then
writes. The safety is the ordering rather than an undo: a reset that would
produce a map the compositor refuses reports it and changes nothing. The rollback
is not a flag, because a recovery command whose safety can be switched off is a
trap.

It writes the **session** copy of the generated file
(`~/.config/hypr/generated/keybinds.lua`), not the repository artifact. The two
are different files: `lib/stage-v5-config.sh` copies the payload into place, so
fixing the repository copy would leave the compositor reading the map that broke.

### The recovery combo

`Ctrl+Alt+R` runs that reset. It is hand-written in `.config/hypr/keybind.lua`
rather than rendered, and that is the whole point: **a bind whose job is to
repair a broken keyboard map cannot live in the file that might be broken.**

It works because of how the compositor loads modules. `require` is replaced with
a wrapper that catches a module which loads and then errors — the error goes into
the config-error list and an empty table is returned, so the requiring file
continues (Hyprland v0.57.2 `src/config/lua/ConfigManager.cpp:522-527` and
`:328-360`). `hyprland.lua` requires `generated.keybinds` *before* `keybind`, so
the generated file can fail at runtime and the recovery bind still registers.

The one case that does not reach it is the generated file being **missing**,
because that path re-raises and aborts `hyprland.lua`. That case is already
covered, and better, by the compositor itself: with at least one config error and
an empty bind registry it trips emergency mode, which registers `Super+Q` for a
terminal, `Super+R` for a launcher and `Super+M` to exit
(`src/config/lua/Emergency.hpp:4-46`, recorded in
`data/design/keybinds.json → recovery.emergency_mode`). A total failure gets
upstream's net and a partial failure gets this one.

Those three keys are also this map's, and that is not a collision: emergency mode
only trips when the bind registry is *empty*, which is the state in which this map
is not loaded at all. `Super+R` runs the run prompt when the map is up and the
compositor's own `hyprland-run` when it is not — and `hyprland-run` is a name this
project neither ships nor installs, so the emergency launcher is the one key of the
three that may not exist (`KB-05`).

`iarch-keybinds check` reads the static file back and proves the record and the
implementation agree about the key and the command. Two files describing one bind
is exactly the shape that drifts, and both files being individually valid is not
evidence they describe the same thing.

**The recovery combo is bound, and the command it calls now exists.**
`scripts/iarch-link-cli.sh` writes `~/.local/bin/iarch-keybinds`, and
`tests/test_cli_launchers.py` runs that name end to end. What has not happened is
the bind *firing*: `install.sh` runs that script and writes
`~/.config/environment.d/iarch-cli-path.conf` because a display manager starts a
session without reading your shell profile, but no installer has been run on a
machine and no compositor exists here, so whether the session actually inherits
that `PATH` is unobserved (INS-07). Until
it does, the bind opens a terminal and says on stderr which command to run rather
than failing silently. The record carries this as an `unverified` note, and
`docs/UNVERIFIED.md` keeps it open as KB-01.

## Keys that are held but not bound

`Ctrl+Alt+BackSpace` is reserved and disabled. It is the X11 kill-server
combination; holding the key in the record is what stops a future edit taking it,
and a reserved entry is present so nothing reassigns the key by accident.

Reserved entries render to nothing — they are absent from the generated file
rather than commented out, because a commented-out bind in a generated file is a
bind a person hand-edits and then loses on the next render.

## What is not built yet

- **The overlay is a terminal drawing, not a glass window.** `Super+H` runs
  `iarch-cheatsheet`, which merges the record with your override, groups it by
  category, filters on every term you give it and paints with the shipped
  `midnight-glass` palette. With no terminal attached — the bind's case — it opens
  one of the terminals the compositor's own emergency mode probes for, then falls
  back to `notify-send`, then to stderr, so the key never fails silently. What is
  not built is the layer-shell glass surface with a box you type into: a plan row
  in the settings application cannot carry behaviour by design, so that needs a
  page module of its own. This is `UI-02`.
- **The Settings page still will not edit the map.** `set`, `add`, `disable`,
  `enable`, `export`, `import` and `reset` are all here and all tested, but they
  are a CLI: the Shortcuts page reads the same record and offers no recorder, no
  action picker and no switch, so the collision check is not yet in front of the
  person making the change. That page is the reason the CLI validates first and
  confirms explicitly — the interface inherits those guarantees rather than
  reimplementing them.
- **No live reload-and-rollback against a running compositor.** The validation
  and the rollback on a failed write are real; asking a running compositor to
  accept a map and undoing it if the session does not survive needs a compositor,
  and the machine this was written on does not have one.
- **The mouse-wheel binds work on a wheel and not on a touchpad.**
  `Super+mouse_up` and `Super+mouse_down` are neither a keysym nor a `mouse:N`
  code, and they still bind: the compositor accepts them as *events*
  (`src/keybinds/Key.cpp:8-10`) and turns a scroll-wheel delta into one
  (`src/keybinds/Manager.cpp:312-335`). That path runs only for
  `WL_POINTER_AXIS_SOURCE_WHEEL`, so a two-finger touchpad scroll changes nothing,
  and the four names are compared exactly — `MOUSE_DOWN` is not the same event.
  Verified from source and never observed on a session, so `docs/UNVERIFIED.md`
  keeps the live half under TP-10.
- **The two mode keys have never been pressed.** `Super+Ctrl+F` and `Super+Ctrl+G`
  run `iarch-focus toggle` and `iarch-gamemode toggle` through launchers that
  `scripts/iarch-link-cli.sh` puts on `PATH`, and both CLIs are tested here —
  focus mode against a stand-in shell, game mode against a temporary config root
  — but no compositor and no display exist on the machine this was written on, so
  what has been proved is the logic and not the key. That is `KB-06`, and it sits
  inside the gap `INS-07` leaves for every bind that names an `iarch-*` command:
  whether a session greetd started has `~/.local/bin` on its `PATH` at all.

## Reading the map

```sh
iarch-keybinds list                # grouped by category
iarch-keybinds list --json         # what an overlay would read
iarch-keybinds list --category System
iarch-keybinds check               # every problem, with severities
iarch-keybinds --check             # CI: are the renderings current?
```

From a checkout that has not run `scripts/iarch-link-cli.sh`, each of those is
`python3 iarch/cli/iarch_keybinds.py …` instead.

`check` exits non-zero on an error or a conflict and zero on warnings, so a map
with debt in it does not look broken — but the warnings are still printed,
because a warning nobody sees is a warning nobody can act on. The shipped map has
none: the last two were the `Super+Ctrl+Alt` binds above, and allocating the
letters found them a home.

The full table of what is bound is [SHORTCUTS.md](SHORTCUTS.md), which is
generated from the same record and cannot disagree with your session unless one
of them is stale.

## The A to Z table

A modifier layer is a budget, so every letter of the three layers a letter may
live in is allocated before anything is bound to it: 78 cells in
`data/design/keybinds.json` under `alphabet`, rendered as a grid at the end of
[SHORTCUTS.md](SHORTCUTS.md). A cell may be one of four things — a binding, a key
the record has claimed and not bound, a refusal with the mechanism that makes it
a bad idea, or empty on purpose — and after four passes over the table not one of
the 78 is empty: twenty-six letters are bound on `Super`, twenty-five bound and
one claimed on `Super+Shift`, eighteen bound and eight refused on `Super+Ctrl`.
The fourth state stays in the schema because a layer with a letter nobody has
thought about is more honest than one that pretends to be finished, and a cell
that is empty is a cell a reader can ask about. `tests/test_keybinds_alphabet.py`
checks the table against the map in both directions, so a bind added to a letter
nobody allocated fails there instead of quietly making the grid a story about the
past.

The refusals are the cells worth reading, and each one names the verb, file or
command behind it. There are eight of them, all in the `Super+Ctrl` layer, and
every one of them is a reason not to bind a key rather than a key nobody got
round to: brightness and mute belong on the media row, where the XF86 keys this
map now binds are; theme mode is written by a generator that a runtime toggle
would disagree with, so the cycle goes through `iarch-cycle theme` instead; Do
Not Disturb and caffeine belong to focus mode because it reads both back before
it changes them; the keyboard letter is the eighth and the newest, because the
layout cycle already sits on `Super+K`, the backlight toggle on `Super+Shift+K`
and two XF86 keys step the backlight, while the two verbs that would set a level
outright take a value the record marks as required; monitors off is a switch
nobody has watched come back on input; screenshots are already three `hyprshot`
binds on Print Screen; and `Super+Ctrl+R` would be a second spelling of the
recovery combo.

Two refusals this list used to carry are gone, and the reason is worth keeping
because it is how a refusal should end. `Super+R` was refused as the
compositor's own emergency launcher — emergency mode registers that key for
`hyprland-run`, which is not a binary this project ships (`KB-05`) — and it is
now the run prompt, `scripts/iarch-run.sh`, which offers everything on `PATH` to
the shell's own dmenu picker. The two cannot collide: emergency mode only trips
when the bind registry is empty, which is exactly when this map is not loaded.
`Super+K` was held for a Hyprland key panel, and the shell has no such panel —
its control centre has twelve tabs and none of them is a keyboard — so the cell
is the keyboard layout cycle instead. A placeholder that names a surface which
does not exist is worse than a bind that names a verb which does.

The table describes the shipped defaults and nothing else. Your
`~/.config/iarch/keybinds.json` may use any empty cell it likes — `check` does
not read the table, because a validator that policed your own map would be
policing the wrong file.
