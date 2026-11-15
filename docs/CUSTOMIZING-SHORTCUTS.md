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
of you are later work. Today a change is two steps:

```sh
# 1. see what is bound, and what a change would collide with
python3 iarch/cli/iarch_keybinds.py list
python3 iarch/cli/iarch_keybinds.py check

# 2. write the difference into ~/.config/iarch/keybinds.json, then render
python3 iarch/cli/iarch_keybinds.py generate --write
```

`generate --write` validates the whole map before it writes any of it, so a
change that would produce a bind the compositor cannot resolve is refused rather
than half-applied. Then reload the compositor config for the change to take
effect.

`iarch-keybinds` is not on `PATH` yet — no entry point and no installer wiring
exists — which is why the commands above are spelled `python3 iarch/cli/...`.

## The layers

A modifier layer is a budget. Spending it on the wrong thing is what makes a
desktop feel arbitrary, so each one has a job and the checker enforces it:

| Layer | What it is for | Enforcement |
| --- | --- | --- |
| `Super` | The primary layer: the things you reach for constantly | — |
| `Super+Shift` | The secondary layer: the counterpart of a primary bind | — |
| `Super+Ctrl` | Workspace navigation, and the remedy for a plain `Ctrl+letter` | — |
| `Ctrl+Alt` | **Recovery and system only** | error for anything else |
| `Super+Ctrl+Alt` | **Recovery and system only** | warning; two v1 binds are debt |
| `Super+Alt` | **Deliberately empty** | error for anything at all |

`Super+Alt` being empty is not an oversight. An empty layer is somewhere a later
bind can go without taking a key away from anything else, which is worth more
than filling it now.

`Ctrl+Alt` is an error rather than a warning because the recovery combo lives on
exactly that layer, and a collision there is a safety net that does not fire when
it is needed. The two `Super+Ctrl+Alt` binds that predate the rule — moving a
window to the next and previous workspace — are reported on every run instead of
being quietly exempted, because an invisible exception rots.

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
python3 iarch/cli/iarch_keybinds.py reset --all      # drop every difference
python3 iarch/cli/iarch_keybinds.py reset <id> …     # drop named ones only
```

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

`iarch-keybinds check` reads the static file back and proves the record and the
implementation agree about the key and the command. Two files describing one bind
is exactly the shape that drifts, and both files being individually valid is not
evidence they describe the same thing.

**The recovery combo is bound but cannot yet run.** `iarch-keybinds` is not on
`PATH`, so until the installer puts it in `~/.local/bin` the bind opens a
terminal and says why on stderr instead of failing silently. The record carries
this as an `unverified` note.

## Keys that are held but not bound

`Ctrl+Alt+BackSpace` is reserved and disabled. It is the X11 kill-server
combination; holding the key in the record is what stops a future edit taking it,
and a reserved entry is present so nothing reassigns the key by accident.

Reserved entries render to nothing — they are absent from the generated file
rather than commented out, because a commented-out bind in a generated file is a
bind a person hand-edits and then loses on the next render.

## What is not built yet

- **`iarch-cheatsheet` does not exist.** `Super+H` is bound to it and locked, so
  the key is real and the overlay behind it is not. This is `UI-02`.
- **The mutating subcommands are absent** — `set`, `add`, `disable`, `import`,
  `export`. `reset` exists because the recovery combo calls it and a safety net
  that depends on unwritten code is not a safety net.
- **No live reload-and-rollback against a running compositor.** The validation
  and the rollback on a failed write are real; asking a running compositor to
  accept a map and undoing it if the session does not survive needs a compositor,
  and the machine this was written on does not have one.
- **Two mouse-wheel binds are carried unverified.** `Super+mouse_up` and
  `Super+mouse_down` come from the older map and are neither a keysym nor a
  `mouse:N` code, so the compositor may answer `key not found`. `check` warns on
  both rather than passing them silently.

## Reading the map

```sh
python3 iarch/cli/iarch_keybinds.py list                # grouped by category
python3 iarch/cli/iarch_keybinds.py list --json         # what an overlay would read
python3 iarch/cli/iarch_keybinds.py list --category System
python3 iarch/cli/iarch_keybinds.py check               # every problem, with severities
python3 iarch/cli/iarch_keybinds.py --check             # CI: are the renderings current?
```

`check` exits non-zero on an error or a conflict and zero on warnings, so a
healthy map with known debt does not look broken — but the warnings are still
printed, because a warning nobody sees is a warning nobody can act on.

The full table of what is bound is [SHORTCUTS.md](SHORTCUTS.md), which is
generated from the same record and cannot disagree with your session unless one
of them is stale.
