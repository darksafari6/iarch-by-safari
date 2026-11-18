# Keyboard shortcuts

<!-- GENERATED FILE - do not edit by hand.
     Source: data/keybinds.default.json (the source iarch-keybinds renders the session from)
             and data/design/keybinds.json -> alphabet (the A to Z allocation)
     Regenerate: python3 tools/render_shortcuts.py --write
     Verify: python3 tools/render_shortcuts.py --check -->

127 shortcuts, generated from `data/keybinds.default.json`, which `iarch-keybinds` renders into `.config/hypr/generated/keybinds.lua`. The record is the source and the Lua is generated, so if this table and your session disagree, one of them is stale: run `python3 tools/render_shortcuts.py --write` for this file, or `iarch-keybinds generate --write` for the session.

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
| `SUPER + SHIFT + C` | Open the calendar panel — runs `iarch-control-center calendar` |
| `SUPER + SHIFT + M` | Open the media panel — runs `iarch-control-center media` |
| `SUPER + SHIFT + O` | Open the monitor panel — runs `iarch-control-center monitor` |
| `SUPER + SHIFT + S` | Open the screen time panel — runs `iarch-control-center screen-time` |
| `SUPER + SHIFT + Y` | Clear the clipboard history (asks first) — runs `iarch-clipboard clear` |
| `SUPER + CTRL + H` | Open the control centre's home tab — runs `iarch-control-center home` |
| `SUPER + CTRL + Y` | Show the last clipboard entry — runs `iarch-clipboard show` |

## Window Management

| Keys | What it does |
| :--- | :--- |
| `SUPER + Q` | Close window — compositor action `window.close` |
| `SUPER + W` | Toggle floating — compositor action `window.float` |
| `SUPER + F` | Toggle fullscreen — compositor action `window.fullscreen` |
| `SUPER + SHIFT + F` | Fullscreen, keeping the bar — compositor action `window.fullscreen_state` |
| `SUPER + SHIFT + Q` | Force close the focused window — compositor action `window.kill` |
| `SUPER + CTRL + U` | Raise the focused window — compositor action `window.bring_to_top` |

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
| `SUPER + SHIFT + J` | Cycle focus to the next window — compositor action `window.cycle_next` |

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
| `SUPER + CTRL + J` | Open or close the special workspace — compositor action `workspace.toggle_special` |

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
| `SUPER + SHIFT + D` | Hide or show the dock — sends the shell `dock-toggle` |
| `SUPER + SHIFT + L` | Edit the lock screen's widgets — sends the shell `lockscreen-widgets-toggle-edit` |
| `SUPER + SHIFT + R` | Give the bar's strip back to the screen — sends the shell `bar-reserve-toggle` |
| `SUPER + SHIFT + T` | Re-apply the theme templates — sends the shell `templates-apply` |
| `SUPER + SHIFT + Z` | Hide or show the desktop widgets — sends the shell `desktop-widgets-toggle` |
| `SUPER + CTRL + E` | Edit the desktop widgets — sends the shell `desktop-widgets-toggle-edit` |
| `SUPER + SHIFT + G` | Cycle the glass intensity — runs `iarch-cycle blur` |
| `SUPER + CTRL + A` | Cycle the animation preset — runs `iarch-cycle animation` |

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
| `SUPER + SHIFT + V` | Show the volume without changing it — sends the shell `volume-osd` *(locked)* |
| `SUPER + CTRL + V` | Show the microphone level — sends the shell `mic-volume-osd` *(locked)* |

## Brightness

| Keys | What it does |
| :--- | :--- |
| `XF86MonBrightnessUp` | Brightness up — runs `iarch-brightness up` *(locked repeating)* |
| `XF86MonBrightnessDown` | Brightness down — runs `iarch-brightness down` *(locked repeating)* |
| `SUPER + SHIFT + K` | Turn the keyboard backlight on or off — sends the shell `keyboard-backlight-toggle` |
| `XF86KbdBrightnessUp` | Keyboard backlight up — sends the shell `keyboard-backlight-up` *(locked repeating)* |
| `XF86KbdBrightnessDown` | Keyboard backlight down — sends the shell `keyboard-backlight-down` *(locked repeating)* |

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
| `SUPER + SHIFT + U` | Re-render every surface, then reload — runs `iarch-reload config` |
| `SUPER + SHIFT + X` | Release a stuck input capture — compositor action `release_input_capture` |
| `SUPER + CTRL + I` | Act on the newest notification — sends the shell `notification-invoke-latest` |
| `SUPER + CTRL + Q` | Close the open panel — sends the shell `panel-close` |
| `SUPER + CTRL + X` | Reload the renderer — compositor action `force_renderer_reload` |
| `SUPER + CTRL + Z` | Lock and suspend — sends the shell `session lock-and-suspend` |

## Planned

Declared in the record but not bound, so nothing happens when you press them. They are reserved so the keys are not reassigned by accident; the shortcut overlay `SUPER + H` opens is scheduled in [docs/ROADMAP.md](ROADMAP.md).

| Keys | What it does |
| :--- | :--- |
| `SUPER + SHIFT + H` | Refresh the shortcut overlay (Part 7) *(not bound yet)* |

## The A to Z table

Every letter of all three layers a letter may live in — 78 cells — each one decided before anything was bound to it. A modifier layer is a budget, and an undecided letter is where an arbitrary bind lands later, so the allocation is written down in `data/design/keybinds.json` under `alphabet` and rendered here. `tests/test_keybinds_alphabet.py` proves the table and the map agree in both directions. It describes the shipped defaults only: your own `~/.config/iarch/keybinds.json` may use any cell it likes, including one this table refuses, because a refusal is a reason not to spend the shipped budget on a bind and not a rule about yours -- and `iarch-keybinds check` does not consult this table, because a person's map is theirs and a checker that policed it would be policing the wrong file.

`SUPER` — **primary**. What a person reaches for constantly: the applications this session installs, launched by name; the window actions in use all day (close on Q, float on W, fullscreen on F, resize mode on X, the gaps on G, the switcher on J); the surfaces that answer a question about the session itself or hand one to it (the shortcut overlay on H, the control centre on I, the clipboard history on Y, the run prompt on R, the reload on U); and the four switches that change the state of the session rather than of a window in it (the power profile on P, the keyboard layout on K, the shell's popups on O, zen on Z).

`SUPER + SHIFT` — **secondary**. The second surface for the letter beside it, and it never launches a program. Five of its rows were already the control-centre tab behind an application launcher (audio, Bluetooth, network, notifications, power) and this pass added four more of the twelve tabs the shell declares (calendar, media, monitor, screen time); the rest are the counterpart of a primary action rather than a repeat of one — force close beside close on Q, the compositor's own fullscreen state beside fullscreen on F, the compositor's cycle beside the shell's switcher on J — plus the shell's chrome switches (dock, bar reserve, desktop widgets, the lock screen's widgets, theme templates), the glass cycle this repository's own CLI owns, the reload that re-renders before it re-reads on U, and the two keys that stand between a person and something they cannot undo: the session menu on E and the question in front of clearing the clipboard on Y.

`SUPER + CTRL` — **tertiary**. The state of the session rather than a program in it: workspace navigation on the arrows (next, previous, empty) and the special workspace on J, the focused window moved between workspaces on N and P and raised in the stack on U, the two modes this project builds on F and G, appearance on L, T, A and E, the shell's own surfaces on H, Q and V, the notification a person just read on I, the last thing they copied on Y, the escape hatch for a session that is drawing wrong on X, and the one action that puts the machine to sleep on Z. It is also the layer the checker offers when it refuses a plain Ctrl+letter, because no application owns Super+Ctrl — a global Ctrl+C takes that key from every terminal and editor at once, and this one does not.

| Letter | `SUPER` | `SUPER + SHIFT` | `SUPER + CTRL` |
| :--- | :--- | :--- | :--- |
| A | Annotate screenshot | Open audio controls | Cycle the animation preset |
| B | Browser | Open Bluetooth controls | *reserved* |
| C | Code editor | Open the calendar panel | *reserved* |
| D | Toggle launcher | Hide or show the dock | *reserved* |
| E | File manager | Open the session menu (logout, reboot, shutdown) | Edit the desktop widgets |
| F | Toggle fullscreen | Fullscreen, keeping the bar | Focus mode: Do Not Disturb, caffeine and a dimmed background |
| G | Toggle the gaps between windows | Cycle the glass intensity | Game mode: drop the compositor's effects for latency |
| H | Shortcut overlay | Refresh the shortcut overlay (Part 7) *(not bound yet)* | Open the control centre's home tab |
| I | Open Control Center | Open Settings | Act on the newest notification |
| J | Jump to a window: open or close the switcher overlay | Cycle focus to the next window | Open or close the special workspace |
| K | Cycle the keyboard layout | Turn the keyboard backlight on or off | *reserved* |
| L | Lock screen | Edit the lock screen's widgets | Toggle night light |
| M | Music player | Open the media panel | *reserved* |
| N | Dismiss every active notification | Open notification center | Move to next workspace |
| O | Toggle the shell's OSD popups | Open the monitor panel | *reserved* |
| P | Cycle the power profile | Open power controls | Move to previous workspace |
| Q | Close window | Force close the focused window | Close the open panel |
| R | Run a command: pick one out of everything on PATH | Give the bar's strip back to the screen | *reserved* |
| S | Steam | Open the screen time panel | *reserved* |
| T | Toggle settings | Re-apply the theme templates | Cycle the theme mode: dark, light, auto |
| U | Reload the session: the shell's configuration and the compositor's | Re-render every surface, then reload | Raise the focused window |
| V | Video player | Show the volume without changing it | Show the microphone level |
| W | Toggle floating | Open network controls | Next wallpaper |
| X | Resize mode | Release a stuck input capture | Reload the renderer |
| Y | Open the clipboard history | Clear the clipboard history (asks first) | Show the last clipboard entry |
| Z | Zen mode: hide the bar, the dock and the desktop widgets | Hide or show the desktop widgets | Lock and suspend |

### Why a cell is not bound

*reserved* is a refusal with a mechanism behind it, and there are eight of them. An em dash would be a cell left empty on purpose, which is the fourth state the record allows and the one a reader can ask about — and after four passes over this table, not one of the 78 cells is in it. Every refusal is listed first, in letter order, then what each layer says about the letters it does not refuse.

- **`SUPER + CTRL + B`** — Brightness. The two XF86 keys are where a level belongs and this map now binds them: XF86MonBrightnessUp and XF86MonBrightnessDown run scripts/iarch-brightness.sh, which drives brightnessctl with a --min-value=1 floor so a key the compositor repeats while it is held cannot walk the backlight to black. A letter would be a third spelling of the same step, and an absolute level would need somewhere to remember the last one, which a key has and a compositor does not. brightness-set stays recorded and deliberately not sent: it takes a required value and an optional target, and naming a monitor is something the shell's own IPC cannot enumerate (data/design/noctalia-ipc.json). The keyboard's own backlight is the one brightness this map does put on a letter, at SUPER + SHIFT + K, and it is a toggle rather than a level — exactly the distinction this cell is making, and the reason the two steps beside it went to the two XF86 keys a keyboard already sends.
- **`SUPER + CTRL + C`** — Caffeine. iarch-focus on saves what caffeine was and puts it back on off, so a key that flips the idle inhibitor underneath a running focus session breaks the restore and leaves the session awake after focus mode ends. Super+Ctrl+F is the switch that owns caffeine, and the toggle is reachable without a key of its own: iarch/cli/iarch_focus.py sends caffeine-enable and caffeine-disable, and the settings application's Home page offers the same switch as a row through its noctalia.caffeine action. What is missing is not a way to reach caffeine but a way to reach it that does not forget what focus mode saved.
- **`SUPER + CTRL + D`** — Do Not Disturb, for the same reason as C: focus mode reads the flag with notification-dnd-status before it changes it and restores what it read, and a blind notification-dnd-toggle would leave the recorded state and the shell's real state disagreeing about who is allowed to interrupt. Notification silence is Super+Ctrl+F.
- **`SUPER + CTRL + K`** — Keyboard. Every keyboard action this map has is already on a key and none of them is here: SUPER + K cycles the layout with keyboard-layout-cycle, SUPER + SHIFT + K turns the backlight on and off with keyboard-backlight-toggle, and the two steps beside that toggle are on XF86KbdBrightnessUp and XF86KbdBrightnessDown, two of the keysyms data/reference/xkb-keysyms-1.7.0.txt pins (at :1352 and :1353) that this map now binds. What is left of the family cannot go on a letter at all. keyboard-backlight-set and keyboard-backlight-osd each take a required value (src/cli/schema_msg.h:545-554 and :535-544), so a key would have to carry a number, and a number a key carried would be a lie about the level the keyboard is actually at — which is the same reason brightness-osd is not bound and volume-osd and mic-volume-osd are, since those two default to the current value. The compositor's own hl.dsp.layout is not a fourth option either: it is the tiling-layout message and takes one argument, which data/design/noctalia-ipc.json says explicitly at keyboard-layout-cycle and this record used to contradict.
- **`SUPER + CTRL + M`** — Mute. The media row carries it now: XF86AudioMute and XF86AudioMicMute run scripts/iarch-audio.sh, which toggles with wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle and @DEFAULT_AUDIO_SOURCE@ toggle and so reads the mute state out of WirePlumber rather than remembering it. volume-mute stays recorded and deliberately not sent, because mute is a state of the same mixer the two volume steps change and this project changes both in one place so the switch and the level cannot drift apart (data/design/noctalia-ipc.json). A letter here would be a second mute key on a third mechanism, and the cell stays reserved so the row that exists is the only one. The microphone is not unrepresented for the omission: its level is on SUPER + CTRL + V through mic-volume-osd, which changes nothing, and its mute stays on the key a keyboard already sends.
- **`SUPER + CTRL + O`** — Monitors off. dpms-off is in the verb record and the Power & Idle page offers it as a row a person clicks, but a key is not a click: nothing here has observed a monitor come back on input, and a combination one Super key away from the rest of the map is a screen that goes black by accident. Reserved until the wake path is verified on a session.
- **`SUPER + CTRL + R`** — Recovery. Ctrl+Alt+R re-applies the default map and it is the one action that has to survive a configuration that will not load, which is why it is written by hand in .config/hypr/keybind.lua rather than generated. A second spelling of it is a second way to lose a custom map by accident, one Super key closer to the rest of the map. The two escape hatches this map does have answer different failures and neither can lose a customisation: SUPER + SHIFT + X releases an input capture a client did not give back (hl.dsp.release_input_capture) and SUPER + CTRL + X asks the compositor to rebuild what it is already drawing (hl.dsp.force_renderer_reload). Neither one rewrites the map.
- **`SUPER + CTRL + S`** — Screenshots. Print Screen already carries three hyprshot binds — window, monitor and region — and the shell's own screenshot-region and screenshot-window verbs are what the settings application's Features page triggers, so the shell's capture is already reachable and a fourth path would mean a second picker and a second answer to where the file went (data/design/noctalia-ipc.json). Reserved rather than left free because this is the first cell anybody reaches for, and what goes there should be written down before the reaching. The pass that filled the other eleven empty cells of this layer re-read the command table and left this one exactly as it found it: annotate (:344), screenshot-annotate (:721) and screenshot-fullscreen (:731) all exist at v5.4.1 and none of the three is bound, for the reason above rather than for want of a verb.
- *Every letter of `SUPER`* — This layer is full: all twenty-six cells are bound, and that is a decision with a cost worth writing down rather than a tidy outcome. A new application or a new switch now has to take a key away from one of these instead of landing in an empty cell, which is the argument the whole Super+Alt layer makes by staying empty. What made filling it defensible is that every one of the ten cells that were empty got a mechanism this repository can cite — eight launchers under scripts/, six verbs re-read out of the shell's own command table, and one compositor configuration call whose leaves data/design/tokens.json already records — and not a placeholder. A letter that could only have been filled with a guess would have stayed reserved with a reason naming the mechanism it is waiting for, the way the Super+Ctrl layer's seven refusals do.
- *Every letter of `SUPER + SHIFT`* — This layer is full: twenty-five cells bound and one declared, and the eighteen that were empty got a mechanism rather than a guess. What made filling it defensible is the test the Super layer's third pass applied — every cell names something this repository can cite, which here means seven verbs out of the shell's own command table at v5.4.1, six of them recorded for the first time in this pass; four control-centre tabs out of the twelve the shell declares; four leaves of the verified hl.dsp tree; three subcommands of scripts this repository already shipped; and one new launcher, scripts/iarch-clipboard.sh, which exists because two of the shell's three clipboard verbs need a step between the key and the verb. The cost is the one the full Super layer already carries: a new counterpart now has to take a key away from one of these instead of landing in an empty cell. A letter whose only candidate was a second spelling of a key that already exists was not filled here, and the eight refusals in the layer below say which mechanism each one names.
- *Every other letter of `SUPER + CTRL`* — No cell in this layer is free any more: twelve were empty, eleven are bound and one is reserved. Every cell that got a mechanism got one this repository can cite — five verbs out of the shell's command table at v5.4.1, four of them recorded for the first time in this pass; one control-centre tab out of the twelve the shell declares; three leaves of the verified hl.dsp tree; and two subcommands of scripts this repository already shipped — and no cell got a second key for an action the map already had, which is the rule the eight refusals below are the other half of. SUPER + CTRL + K is the one letter with no bind, and it is reserved rather than free because the keyboard's actions are all spoken for: the layout cycle, the backlight toggle and the two backlight steps are on four other keys, and the two verbs left in that family each take a required value a key cannot honestly carry. A cell that could only repeat one of those is a cell that should say so.

## Changing a shortcut

Edit `~/.config/iarch/keybinds.json`, not the repository. It holds only your differences — a rebind is the id and the new key and nothing else — and `iarch-keybinds generate` renders it merged over `data/keybinds.default.json`, stamps the result as generated, backs the previous copy up, and validates the whole map before it writes any of it. The bindings that run today are the ones in `.config/hypr/generated/keybinds.lua`, and this table documents them.

<!-- Copyright (C) 2026 Safari — GPL-3.0-or-later -->
