# Keyboard shortcuts

<!-- GENERATED FILE - do not edit by hand.
     Source: data/keybinds.default.json (the source iarch-keybinds renders the session from)
     Regenerate: python3 tools/render_shortcuts.py --write
     Verify: python3 tools/render_shortcuts.py --check -->

77 shortcuts, generated from `data/keybinds.default.json`, which `iarch-keybinds` renders into `.config/hypr/generated/keybinds.lua`. The record is the source and the Lua is generated, so if this table and your session disagree, one of them is stale: run `python3 tools/render_shortcuts.py --write` for this file, or `iarch-keybinds generate --write` for the session.

`SUPER` is the Super key — the Windows key on most keyboards, Command on an Apple one. A bind marked *(mouse)* is a button or a scroll, and *(locked)* media keys keep working while the screen is locked.

## Contents

- [Applications](#applications)
- [Window Management](#window-management)
- [Window Navigation & Layout](#window-navigation-layout)
- [Screenshots](#screenshots)
- [Workspace Switching](#workspace-switching)
- [Workspace Navigation](#workspace-navigation)
- [Move Window Across Workspaces](#move-window-across-workspaces)
- [Mouse Workspace Navigation](#mouse-workspace-navigation)
- [Mouse Window Management](#mouse-window-management)
- [Media](#media)
- [System](#system)
- [Planned](#planned)

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
| `SUPER + CTRL + ALT + right` | Move to next workspace — compositor action `window.move` |
| `SUPER + CTRL + ALT + left` | Move to previous workspace — compositor action `window.move` |

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
| `XF86AudioRaiseVolume` | Volume up — runs `pamixer -i 5` *(locked)* |
| `XF86AudioLowerVolume` | Volume down — runs `pamixer -d 5` *(locked)* |

## System

| Keys | What it does |
| :--- | :--- |
| `SUPER + H` | Shortcut overlay — runs `iarch-cheatsheet` |
| `SUPER + SHIFT + E` | Open the session menu (logout, reboot, shutdown) — sends the shell `panel-toggle session` |
| `CTRL + ALT + BackSpace` | Reserved: the X11 kill-server combo, deliberately never bound *(not bound yet)* |
| `CTRL + ALT + R` | Recovery: re-apply the default keyboard map — runs `iarch-keybinds reset --all --yes` |

## Planned

Declared in the record but not bound, so nothing happens when you press them. They are reserved so the keys are not reassigned by accident; the shortcut overlay `SUPER + H` opens is scheduled in [docs/ROADMAP.md](ROADMAP.md).

| Keys | What it does |
| :--- | :--- |
| `SUPER + SHIFT + H` | Refresh the shortcut overlay (Part 7) *(not bound yet)* |
| `SUPER + K` | Hyprland key panel (Part 7) *(not bound yet)* |

## Changing a shortcut

Edit `~/.config/iarch/keybinds.json`, not the repository. It holds only your differences — a rebind is the id and the new key and nothing else — and `iarch-keybinds generate` renders it merged over `data/keybinds.default.json`, stamps the result as generated, backs the previous copy up, and validates the whole map before it writes any of it. The bindings that run today are the ones in `.config/hypr/generated/keybinds.lua`, and this table documents them.

<!-- Copyright (C) 2026 Safari — GPL-3.0-or-later -->
