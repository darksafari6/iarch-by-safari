# Keyboard shortcuts

<!-- GENERATED FILE - do not edit by hand.
     Source: data/keybinds.default.json (the source iarch-keybinds renders the session from)
             and data/design/keybinds.json -> alphabet (the A to Z allocation)
     Regenerate: python3 tools/render_shortcuts.py --write
     Verify: python3 tools/render_shortcuts.py --check -->

96 shortcuts, generated from `data/keybinds.default.json`, which `iarch-keybinds` renders into `.config/hypr/generated/keybinds.lua`. The record is the source and the Lua is generated, so if this table and your session disagree, one of them is stale: run `python3 tools/render_shortcuts.py --write` for this file, or `iarch-keybinds generate --write` for the session.

`SUPER` is the Super key — the Windows key on most keyboards, Command on an Apple one. A bind marked *(mouse)* is a button or a scroll, and *(locked)* media keys keep working while the screen is locked.

## Contents

- [Applications](#applications)
- [Window Management](#window-management)
- [Window Navigation & Layout](#window-navigation-layout)
- [Screenshots](#screenshots)
- [Workspace Switching](#workspace-switching)
- [Workspace Navigation](#workspace-navigation)
- [Move Window Across Workspaces](#move-window-across-workspaces)
- [Modes](#modes)
- [Appearance](#appearance)
- [Mouse Workspace Navigation](#mouse-workspace-navigation)
- [Mouse Window Management](#mouse-window-management)
- [Media](#media)
- [Brightness](#brightness)
- [System](#system)
- [Planned](#planned)
- [The A to Z table](#the-a-to-z-table)

## Applications

| Keys | What it does |
| :--- | :--- |
| `SUPER + RETURN` | Terminal — runs `kitty` |
| `SUPER + E` | File manager — runs `thunar` |
| `SUPER + C` | Code editor — runs `code` |
| `SUPER + B` | Browser — runs `~/.config/hypr/Scripts/browser-launcher.sh` *(shell)* |
| `SUPER + D` | Toggle launcher — runs `noctalia msg panel-toggle launcher` |
| `SUPER + L` | Lock screen — runs `noctalia msg session lock` |
| `SUPER + T` | Toggle settings — runs `noctalia msg settings-toggle` |
| `SUPER + I` | Open Control Center — runs `noctalia msg panel-toggle control-center` |
| `SUPER + SHIFT + I` | Open Settings — runs `noctalia msg settings-toggle` |
| `SUPER + SHIFT + N` | Open notification center — runs `noctalia msg panel-toggle control-center notifications` |
| `SUPER + SHIFT + A` | Open audio controls — runs `noctalia msg panel-toggle control-center audio` |
| `SUPER + SHIFT + W` | Open network controls — runs `noctalia msg panel-toggle control-center network` |
| `SUPER + SHIFT + B` | Open Bluetooth controls — runs `noctalia msg panel-toggle control-center bluetooth` |
| `SUPER + SHIFT + P` | Open power controls — runs `noctalia msg panel-toggle control-center power` |
| `SUPER + S` | Steam — runs `steam` |
| `SUPER + M` | Music player — runs `quodlibet` |
| `SUPER + V` | Video player — runs `mpv --player-operation-mode=pseudo-gui --force-window=immediate` |
| `SUPER + R` | Run a command: pick one out of everything on PATH — runs `iarch-run` |
| `SUPER + Y` | Open the clipboard history — sends the shell `panel-toggle clipboard` |

## Window Management

| Keys | What it does |
| :--- | :--- |
| `SUPER + Q` | Close window — compositor action `window.close` |
| `SUPER + W` | Toggle floating — compositor action `window.float` |
| `SUPER + F` | Toggle fullscreen — compositor action `window.fullscreen` |

## Window Navigation & Layout

| Keys | What it does |
| :--- | :--- |
| `SUPER + tab` | Next workspace on monitor — compositor action `exec_cmd` |
| `SUPER + SHIFT + tab` | Previous workspace on monitor — compositor action `focus` |
| `SUPER + left` | Focus left — compositor action `focus` |
| `SUPER + right` | Focus right — compositor action `focus` |
| `SUPER + up` | Focus up — compositor action `focus` |
| `SUPER + down` | Focus down — compositor action `focus` |
| `ALT + tab` | Window switcher overlay — runs `noctalia msg window-switcher hold` |
| `SUPER + J` | Jump to a window: open or close the switcher overlay — sends the shell `window-switcher` |
| `SUPER + G` | Toggle the gaps between windows — runs `iarch-gaps toggle` |
| `SUPER + SHIFT + right` | Resize window right — compositor action `window.resize` |
| `SUPER + SHIFT + left` | Resize window left — compositor action `window.resize` |
| `SUPER + SHIFT + up` | Resize window up — compositor action `window.resize` |
| `SUPER + SHIFT + down` | Resize window down — compositor action `window.resize` |
| `SUPER + SHIFT + CTRL + left` | Move or swap window left — a short Lua routine |
| `SUPER + SHIFT + CTRL + right` | Move or swap window right — a short Lua routine |
| `SUPER + SHIFT + CTRL + up` | Move or swap window up — a short Lua routine |
| `SUPER + SHIFT + CTRL + down` | Move or swap window down — a short Lua routine |

## Screenshots

| Keys | What it does |
| :--- | :--- |
| `SUPER + PRINT` | Screenshot window — runs `HYPRSHOT_DIR=~/Pictures/Screenshots hyprshot -m window` *(shell)* |
| `ALT + PRINT` | Screenshot monitor — runs `HYPRSHOT_DIR=~/Pictures/Screenshots hyprshot -m output` *(shell)* |
| `SHIFT + PRINT` | Screenshot region — runs `HYPRSHOT_DIR=~/Pictures/Screenshots hyprshot -m region` *(shell)* |
| `SUPER + A` | Annotate screenshot — runs `grim -g "$(slurp)" - | satty --filename - --output-filename ~...` *(shell)* |

## Workspace Switching

| Keys | What it does |
| :--- | :--- |
| `SUPER + 1` | Workspace1 — compositor action `focus` |
| `SUPER + 2` | Workspace2 — compositor action `focus` |
| `SUPER + 3` | Workspace3 — compositor action `focus` |
| `SUPER + 4` | Workspace4 — compositor action `focus` |
| `SUPER + 5` | Workspace5 — compositor action `focus` |
| `SUPER + 6` | Workspace6 — compositor action `focus` |
| `SUPER + 7` | Workspace7 — compositor action `focus` |
| `SUPER + 8` | Workspace8 — compositor action `focus` |
| `SUPER + 9` | Workspace9 — compositor action `focus` |
| `SUPER + SHIFT + 1` | Move to workspace1 — compositor action `window.move` |
| `SUPER + SHIFT + 2` | Move to workspace2 — compositor action `window.move` |
| `SUPER + SHIFT + 3` | Move to workspace3 — compositor action `window.move` |
| `SUPER + SHIFT + 4` | Move to workspace4 — compositor action `window.move` |
| `SUPER + SHIFT + 5` | Move to workspace5 — compositor action `window.move` |
| `SUPER + SHIFT + 6` | Move to workspace6 — compositor action `window.move` |
| `SUPER + SHIFT + 7` | Move to workspace7 — compositor action `window.move` |
| `SUPER + SHIFT + 8` | Move to workspace8 — compositor action `window.move` |
| `SUPER + SHIFT + 9` | Move to workspace9 — compositor action `window.move` |
| `SUPER + 0` | Workspace 10 — compositor action `focus` |
| `SUPER + SHIFT + 0` | Move to workspace 10 — compositor action `window.move` |

## Workspace Navigation

| Keys | What it does |
| :--- | :--- |
| `SUPER + CTRL + right` | Next workspace — compositor action `focus` |
| `SUPER + CTRL + left` | Previous workspace — compositor action `focus` |
| `SUPER + CTRL + down` | Open empty workspace — compositor action `focus` |

## Move Window Across Workspaces

| Keys | What it does |
| :--- | :--- |
| `SUPER + CTRL + N` | Move to next workspace — compositor action `window.move` |
| `SUPER + CTRL + P` | Move to previous workspace — compositor action `window.move` |

## Modes

| Keys | What it does |
| :--- | :--- |
| `SUPER + CTRL + F` | Focus mode: Do Not Disturb, caffeine and a dimmed background — runs `iarch-focus toggle` |
| `SUPER + CTRL + G` | Game mode: drop the compositor's effects for latency — runs `iarch-gamemode toggle` |
| `SUPER + P` | Cycle the power profile — sends the shell `power-cycle` |
| `SUPER + Z` | Zen mode: hide the bar, the dock and the desktop widgets — runs `iarch-zen toggle` |

## Appearance

| Keys | What it does |
| :--- | :--- |
| `SUPER + CTRL + L` | Toggle night light — sends the shell `nightlight-toggle` |
| `SUPER + O` | Toggle the shell's OSD popups — sends the shell `osd-toggle` |
| `SUPER + CTRL + T` | Cycle the theme mode: dark, light, auto — runs `iarch-cycle theme` |
| `SUPER + CTRL + W` | Next wallpaper — sends the shell `wallpaper-next` |

## Mouse Workspace Navigation

| Keys | What it does |
| :--- | :--- |
| `SUPER + mouse_down` | Scroll to next workspace — compositor action `focus` |
| `SUPER + mouse_up` | Scroll to previous workspace — compositor action `focus` |

## Mouse Window Management

| Keys | What it does |
| :--- | :--- |
| `SUPER + mouse:272` | Drag window — compositor action `window.drag` *(mouse)* |
| `SUPER + mouse:273` | Resize window — compositor action `window.resize` *(mouse)* |
| `SUPER + X` | Resize mode — compositor action `window.resize` |

## Media

| Keys | What it does |
| :--- | :--- |
| `XF86AudioPlay` | Play or pause — runs `playerctl play-pause` *(locked)* |
| `XF86AudioNext` | Next track — runs `playerctl next` *(locked)* |
| `XF86AudioPrev` | Previous track — runs `playerctl previous` *(locked)* |
| `XF86AudioRaiseVolume` | Volume up — runs `iarch-audio up` *(locked repeating)* |
| `XF86AudioLowerVolume` | Volume down — runs `iarch-audio down` *(locked repeating)* |
| `XF86AudioMute` | Mute — runs `iarch-audio mute` *(locked)* |
| `XF86AudioMicMute` | Mute the microphone — runs `iarch-audio mic-mute` *(locked)* |

## Brightness

| Keys | What it does |
| :--- | :--- |
| `XF86MonBrightnessUp` | Brightness up — runs `iarch-brightness up` *(locked repeating)* |
| `XF86MonBrightnessDown` | Brightness down — runs `iarch-brightness down` *(locked repeating)* |

## System

| Keys | What it does |
| :--- | :--- |
| `SUPER + H` | Shortcut overlay — runs `iarch-cheatsheet` |
| `SUPER + K` | Cycle the keyboard layout — sends the shell `keyboard-layout-cycle` |
| `SUPER + N` | Dismiss every active notification — sends the shell `notification-clear-active` |
| `SUPER + U` | Reload the session: the shell's configuration and the compositor's — runs `iarch-reload session` |
| `SUPER + SHIFT + E` | Open the session menu (logout, reboot, shutdown) — sends the shell `panel-toggle session` |
| `CTRL + ALT + BackSpace` | Reserved: the X11 kill-server combo, deliberately never bound *(not bound yet)* |
| `CTRL + ALT + R` | Recovery: re-apply the default keyboard map — runs `iarch-keybinds reset --all --yes` |

## Planned

Declared in the record but not bound, so nothing happens when you press them. They are reserved so the keys are not reassigned by accident; the shortcut overlay `SUPER + H` opens is scheduled in [docs/ROADMAP.md](ROADMAP.md).

| Keys | What it does |
| :--- | :--- |
| `SUPER + SHIFT + H` | Refresh the shortcut overlay (Part 7) *(not bound yet)* |

## The A to Z table

Every letter of all three layers a letter may live in — 78 cells — each one decided before anything was bound to it. A modifier layer is a budget, and an undecided letter is where an arbitrary bind lands later, so the allocation is written down in `data/design/keybinds.json` under `alphabet` and rendered here. `tests/test_keybinds_alphabet.py` proves the table and the map agree in both directions. It describes the shipped defaults only: your own `~/.config/iarch/keybinds.json` may use any empty cell it likes, and `iarch-keybinds check` does not consult this table, because a person's map is theirs and a checker that policed it would be policing the wrong file.

`SUPER` — **primary**. What a person reaches for constantly: the applications this session installs, launched by name; the window actions in use all day (close on Q, float on W, fullscreen on F, resize mode on X, the gaps on G, the switcher on J); the surfaces that answer a question about the session itself or hand one to it (the shortcut overlay on H, the control centre on I, the clipboard history on Y, the run prompt on R, the reload on U); and the four switches that change the state of the session rather than of a window in it (the power profile on P, the keyboard layout on K, the shell's popups on O, zen on Z).

`SUPER + SHIFT` — **secondary**. The counterpart of a primary bind, and it never launches a program: every row here opens a control-centre context (audio, Bluetooth, network, notifications, power) or one of the session's own decisions (the settings window, the session menu that stands between a key and a logout).

`SUPER + CTRL` — **tertiary**. The state of the session rather than a program in it: workspace navigation on the arrows (next, previous, empty), moving the focused window between workspaces on N and P, the two modes this project builds on F and G, and appearance on L. It is also the layer the checker offers when it refuses a plain Ctrl+letter, because no application owns Super+Ctrl — a global Ctrl+C takes that key from every terminal and editor at once, and this one does not.

| Letter | `SUPER` | `SUPER + SHIFT` | `SUPER + CTRL` |
| :--- | :--- | :--- | :--- |
| A | Annotate screenshot | Open audio controls | — |
| B | Browser | Open Bluetooth controls | *reserved* |
| C | Code editor | — | *reserved* |
| D | Toggle launcher | — | *reserved* |
| E | File manager | Open the session menu (logout, reboot, shutdown) | — |
| F | Toggle fullscreen | — | Focus mode: Do Not Disturb, caffeine and a dimmed background |
| G | Toggle the gaps between windows | — | Game mode: drop the compositor's effects for latency |
| H | Shortcut overlay | Refresh the shortcut overlay (Part 7) *(not bound yet)* | — |
| I | Open Control Center | Open Settings | — |
| J | Jump to a window: open or close the switcher overlay | — | — |
| K | Cycle the keyboard layout | — | — |
| L | Lock screen | — | Toggle night light |
| M | Music player | — | *reserved* |
| N | Dismiss every active notification | Open notification center | Move to next workspace |
| O | Toggle the shell's OSD popups | — | *reserved* |
| P | Cycle the power profile | Open power controls | Move to previous workspace |
| Q | Close window | — | — |
| R | Run a command: pick one out of everything on PATH | — | *reserved* |
| S | Steam | — | *reserved* |
| T | Toggle settings | — | Cycle the theme mode: dark, light, auto |
| U | Reload the session: the shell's configuration and the compositor's | — | — |
| V | Video player | — | — |
| W | Toggle floating | Open network controls | Next wallpaper |
| X | Resize mode | — | — |
| Y | Open the clipboard history | — | — |
| Z | Zen mode: hide the bar, the dock and the desktop widgets | — | — |

### Why a cell is empty

*reserved* is a refusal with a mechanism behind it, and an em dash is a cell left empty on purpose. Every refusal is listed first, in letter order, then the reason each layer leaves the rest of its letters alone.

- **`SUPER + CTRL + B`** — Brightness. The two XF86 keys are where a level belongs and this map now binds them: XF86MonBrightnessUp and XF86MonBrightnessDown run scripts/iarch-brightness.sh, which drives brightnessctl with a --min-value=1 floor so a key the compositor repeats while it is held cannot walk the backlight to black. A letter would be a third spelling of the same step, and an absolute level would need somewhere to remember the last one, which a key has and a compositor does not. brightness-set stays recorded and deliberately not sent: it takes a required value and an optional target, and naming a monitor is something the shell's own IPC cannot enumerate (data/design/noctalia-ipc.json).
- **`SUPER + CTRL + C`** — Caffeine. iarch-focus on saves what caffeine was and puts it back on off, so a key that flips the idle inhibitor underneath a running focus session breaks the restore and leaves the session awake after focus mode ends. Super+Ctrl+F is the switch that owns caffeine, and caffeine-toggle is allowlisted in scripts/iarch-control-center.sh, so the toggle itself is reachable — the key is not what is missing.
- **`SUPER + CTRL + D`** — Do Not Disturb, for the same reason as C: focus mode reads the flag with notification-dnd-status before it changes it and restores what it read, and a blind notification-dnd-toggle would leave the recorded state and the shell's real state disagreeing about who is allowed to interrupt. Notification silence is Super+Ctrl+F.
- **`SUPER + CTRL + M`** — Mute. The media row carries it now: XF86AudioMute and XF86AudioMicMute run scripts/iarch-audio.sh, which toggles with wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle and @DEFAULT_AUDIO_SOURCE@ toggle and so reads the mute state out of WirePlumber rather than remembering it. volume-mute stays recorded and deliberately not sent, because mute is a state of the same mixer the two volume steps change and this project changes both in one place so the switch and the level cannot drift apart (data/design/noctalia-ipc.json). A letter here would be a second mute key on a third mechanism, and the cell stays reserved so the row that exists is the only one.
- **`SUPER + CTRL + O`** — Monitors off. dpms-off is in the verb record and the Power & Idle page offers it as a row a person clicks, but a key is not a click: nothing here has observed a monitor come back on input, and a combination one Super key away from the rest of the map is a screen that goes black by accident. Reserved until the wake path is verified on a session.
- **`SUPER + CTRL + R`** — Recovery. Ctrl+Alt+R re-applies the default map and it is the one action that has to survive a configuration that will not load, which is why it is written by hand in .config/hypr/keybind.lua rather than generated. A second spelling of it is a second way to lose a custom map by accident, one Super key closer to the rest of the map.
- **`SUPER + CTRL + S`** — Screenshots. Print Screen already carries three hyprshot binds — window, monitor and region — and the shell's own screenshot-region and screenshot-window verbs are what the settings application's Features page triggers, so the shell's capture is already reachable and a fourth path would mean a second picker and a second answer to where the file went (data/design/noctalia-ipc.json). Reserved rather than left free because this is the first cell anybody reaches for, and what goes there should be written down before the reaching.
- *Every other letter of `SUPER`* — This layer is full: all twenty-six cells are bound, and that is a decision with a cost worth writing down rather than a tidy outcome. A new application or a new switch now has to take a key away from one of these instead of landing in an empty cell, which is the argument the whole Super+Alt layer makes by staying empty. What made filling it defensible is that every one of the ten cells that were empty got a mechanism this repository can cite — eight launchers under scripts/, six verbs re-read out of the shell's own command table, and one compositor configuration call whose leaves data/design/tokens.json already records — and not a placeholder. A letter that could only have been filled with a guess would have stayed reserved with a reason naming the mechanism it is waiting for, the way the Super+Ctrl layer's seven refusals do.
- *Every other letter of `SUPER + SHIFT`* — This layer holds counterparts, and the primary letter beside it has no counterpart worth a key. Empty until one exists, which is a cheaper thing to add later than to move out of the way.
- *Every other letter of `SUPER + CTRL`* — The state it would change is already reachable, from the control centre on Super+I, the settings window on Super+T or a command in a terminal, and a second key for one action is a second place to keep in step. Empty until the cell has an action nothing else offers.

## Changing a shortcut

Edit `~/.config/iarch/keybinds.json`, not the repository. It holds only your differences — a rebind is the id and the new key and nothing else — and `iarch-keybinds generate` renders it merged over `data/keybinds.default.json`, stamps the result as generated, backs the previous copy up, and validates the whole map before it writes any of it. The bindings that run today are the ones in `.config/hypr/generated/keybinds.lua`, and this table documents them.

<!-- Copyright (C) 2026 Safari — GPL-3.0-or-later -->
