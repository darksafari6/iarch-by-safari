# Keyboard shortcuts

<!-- GENERATED FILE - do not edit by hand.
     Source: data/keybinds.default.json (extracted from .config/hypr/keybind.lua)
     Regenerate: python3 tools/render_shortcuts.py --write
     Verify: python3 tools/render_shortcuts.py --check -->

74 shortcuts, generated from `data/keybinds.default.json`, which `tools/extract_keybinds.py` reads out of `.config/hypr/keybind.lua`. If this table and your session disagree, the session is right and this file is stale: run `python3 tools/render_shortcuts.py --write`.

`SUPER` is the Super key — the Windows key on most keyboards, Command on an Apple one. Mouse bindings are listed with their button, and `locked` media keys keep working while the screen is locked.

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
- [Planned](#planned)

## Applications

| Keys | What it does |
| :--- | :--- |
| `SUPER + RETURN` | Terminal — runs `kitty` |
| `SUPER + E` | File manager — runs `thunar` |
| `SUPER + C` | Code editor — runs `code` |
| `SUPER + B` | Browser — runs `~/.config/hypr/Scripts/browser-launcher.sh` |
| `SUPER + D` | Toggle launcher — runs `noctalia msg panel-toggle launcher` |
| `SUPER + L` | Lock screen — runs `noctalia msg session lock ` |
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
| `SUPER + V` | Video player — runs `mpv --player-operation-mode=pseudo-gui --force-window=imm...` |

## Window Management

| Keys | What it does |
| :--- | :--- |
| `SUPER + Q` | Close window |
| `SUPER + W` | Toggle floating |
| `SUPER + F` | Toggle fullscreen |

## Window Navigation & Layout

| Keys | What it does |
| :--- | :--- |
| `SUPER + tab` | Next workspace on monitor |
| `SUPER + SHIFT + tab` | Previous workspace on monitor |
| `SUPER + left` | Focus left |
| `SUPER + right` | Focus right |
| `SUPER + up` | Focus up |
| `SUPER + down` | Focus down |
| `ALT + tab` | Window switcher overlay — runs `noctalia msg window-switcher hold` |
| `SUPER + SHIFT + right` | Resize window right |
| `SUPER + SHIFT + left` | Resize window left |
| `SUPER + SHIFT + up` | Resize window up |
| `SUPER + SHIFT + down` | Resize window down |
| `SUPER + SHIFT + CTRL + left` | Move or swap window left |
| `SUPER + SHIFT + CTRL + right` | Move or swap window right |
| `SUPER + SHIFT + CTRL + up` | Move or swap window up |
| `SUPER + SHIFT + CTRL + down` | Move or swap window down |

## Screenshots

| Keys | What it does |
| :--- | :--- |
| `SUPER + PRINT` | Screenshot window — runs `HYPRSHOT_DIR=~/Pictures/Screenshots hyprshot -m window` |
| `ALT + PRINT` | Screenshot monitor — runs `HYPRSHOT_DIR=~/Pictures/Screenshots hyprshot -m output` |
| `SHIFT + PRINT` | Screenshot region — runs `HYPRSHOT_DIR=~/Pictures/Screenshots hyprshot -m region` |
| `SUPER + A` | Annotate screenshot — runs `grim -g "$(slurp)" - | satty --filename - --output-filena...` |

## Workspace Switching

| Keys | What it does |
| :--- | :--- |
| `SUPER + 1` | Workspace1 |
| `SUPER + 2` | Workspace2 |
| `SUPER + 3` | Workspace3 |
| `SUPER + 4` | Workspace4 |
| `SUPER + 5` | Workspace5 |
| `SUPER + 6` | Workspace6 |
| `SUPER + 7` | Workspace7 |
| `SUPER + 8` | Workspace8 |
| `SUPER + 9` | Workspace9 |
| `SUPER + SHIFT + 1` | Move to workspace1 |
| `SUPER + SHIFT + 2` | Move to workspace2 |
| `SUPER + SHIFT + 3` | Move to workspace3 |
| `SUPER + SHIFT + 4` | Move to workspace4 |
| `SUPER + SHIFT + 5` | Move to workspace5 |
| `SUPER + SHIFT + 6` | Move to workspace6 |
| `SUPER + SHIFT + 7` | Move to workspace7 |
| `SUPER + SHIFT + 8` | Move to workspace8 |
| `SUPER + SHIFT + 9` | Move to workspace9 |
| `SUPER + 0` | Workspace 10 |
| `SUPER + SHIFT + 0` | Move to workspace 10 |

## Workspace Navigation

| Keys | What it does |
| :--- | :--- |
| `SUPER + CTRL + right` | Next workspace |
| `SUPER + CTRL + left` | Previous workspace |
| `SUPER + CTRL + down` | Open empty workspace |

## Move Window Across Workspaces

| Keys | What it does |
| :--- | :--- |
| `SUPER + CTRL + ALT + right` | Move to next workspace |
| `SUPER + CTRL + ALT + left` | Move to previous workspace |

## Mouse Workspace Navigation

| Keys | What it does |
| :--- | :--- |
| `SUPER + mouse_down` | Scroll to next workspace |
| `SUPER + mouse_up` | Scroll to previous workspace |

## Mouse Window Management

| Keys | What it does |
| :--- | :--- |
| `SUPER + mouse:272` | Drag window *(mouse)* |
| `SUPER + mouse:273` | Resize window *(mouse)* |
| `SUPER + X` | Resize mode |

## Media

| Keys | What it does |
| :--- | :--- |
| `XF86AudioPlay` | Play or pause — runs `playerctl play-pause` *(locked)* |
| `XF86AudioNext` | Next track — runs `playerctl next` *(locked)* |
| `XF86AudioPrev` | Previous track — runs `playerctl previous` *(locked)* |
| `XF86AudioRaiseVolume` | Volume up — runs `pamixer -i 5` *(locked)* |
| `XF86AudioLowerVolume` | Volume down — runs `pamixer -d 5` *(locked)* |

## Planned

Defined in the session configuration but not bound yet, so nothing happens when you press them. They are reserved for the in-session shortcut overlay, which [docs/ROADMAP.md](ROADMAP.md) schedules as Part 7. This table lists them so the keys are not reassigned by accident in the meantime.

| Keys | What it does |
| :--- | :--- |
| `SUPER + H` | Shortcut overlay (Part 7) *(not bound yet)* |
| `SUPER + SHIFT + H` | Refresh the shortcut overlay (Part 7) *(not bound yet)* |
| `SUPER + K` | Hyprland key panel (Part 7) *(not bound yet)* |

## Changing a shortcut

Edit `~/.config/iarch/keybinds.json`, not the repository. The generators described in [docs/ARCHITECTURE.md](ARCHITECTURE.md) render the session configuration from your file merged over `data/keybinds.default.json`, stamp it as generated, back the previous copy up, and reload. Until that generator ships, the binding that runs today is the one in `.config/hypr/keybind.lua` and this table documents it.

<!-- Copyright (C) 2026 Safari — GPL-3.0-or-later -->
