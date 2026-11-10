# Third-party notices — iArch by Safari

<!-- GENERATED FILE - do not edit by hand.
     Source: branding/notices.json
     Regenerate: python3 tools/notices.py --write
     Verify: python3 tools/notices.py --check -->

Notices version 1 · updated 2026-11-09 · license information verified 2026-11-09

This repository is licensed as a whole under the GNU General Public License version 3.0; the full text is in LICENSE.txt and is not reproduced here.

iArch by Safari is an independent product. It ships configuration for third-party projects and a small amount of vendored third-party code and assets, listed below.

The product name shown in the desktop session is iArch by Safari. Upstream project names are intentionally kept out of the everyday UI; this file and the Settings page About -> Open-source licenses are the only places where third-party credit is displayed. See docs/BRANDING.md.

Packages that the installer only downloads from your distribution are licensed by that distribution. They are listed for completeness, not redistributed here.

## Product license

iArch by Safari is free software: you can redistribute it and/or modify it under the terms of the GPL-3.0-only license as published by the Free Software Foundation. The complete text is in [`LICENSE.txt`](LICENSE.txt) and is not reproduced here.

Maintained by Safari · https://github.com/darksafari6/iarch-by-safari

## What is listed here

- **Vendored code stored in this repository** — Third-party source code stored inside this repository.
- **Configuration and colors derived from third-party projects** — Configuration or color values in this repository derived from a third-party project.
- **Third-party software this product configures or launches** — Third-party software this configuration targets or launches; not redistributed here.
- **Artwork and audio assets stored in this repository** — Binary or artwork assets stored inside this repository.
- **Third-party services, repositories and registries** — Third-party network service, repository or registry used by the installer or the shell.

## Vendored code stored in this repository

### Hyprland Keybinds (Noctalia plugin)

Bar widget, panel and settings page that view and edit the Hyprland keybinds file.

- **License:** MIT
- **Copyright:** Copyright (c) tonekneeo (year not stated in manifest.json)
- **Version checked:** 1.0.0
- **Used by:**
  - `legacy/config/noctalia/plugins/hyprland-keybinds/`
- **Notes:** Authored for this repository and declared MIT in its own manifest.json. It follows the Noctalia plugin API conventions but is not a copy of the upstream keybind-cheatsheet plugin, which has a different id, author, version and file set.
- **Open verification items:** `TP-01`, `TP-02` in `docs/UNVERIFIED.md`

<details>
<summary>MIT license text</summary>

Copyright (c) tonekneeo (year not stated in manifest.json)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

</details>

## Configuration and colors derived from third-party projects

### PipeWire filter-chain virtual surround configuration

Convolver sink that plays 7.1 virtual surround through stereo headphones using HRIR files.

- **License:** MIT
- **Copyright:** Copyright (c) PipeWire contributors
- **Upstream:** https://gitlab.freedesktop.org/pipewire/pipewire
- **Used by:**
  - `pipewire/pipewire.conf.d/sink-virtual-surround-7.1-hesuvi.conf`
- **Notes:** The convolver graph follows the upstream filter-chain virtual surround example. Paths and the HeSuVi 14-channel WAV layout were adapted for this repository.
- **Open verification items:** `TP-07` in `docs/UNVERIFIED.md`

<details>
<summary>MIT license text</summary>

Copyright (c) PipeWire contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

</details>

### Tokyo Night color values

Terminal and shell color scheme values.

- **License:** Apache-2.0
- **Copyright:** Copyright (c) Folke Lemaitre
- **Upstream:** https://github.com/folke/tokyonight.nvim
- **Used by:**
  - `.config/kitty/minima-colors.conf`
  - `legacy/config/noctalia/settings.json`
- **Notes:** Color values only. The Apache License 2.0 text is available in the upstream repository; no upstream source code is stored here.
- **Open verification items:** `TP-08` in `docs/UNVERIFIED.md`

## Third-party software this product configures or launches

### Noctalia

Wayland desktop shell: bar, dock, launcher, Control Center, notifications, lock screen, greeter and Settings. Launched by the session and driven with the noctalia command.

- **License:** MIT
- **Copyright:** Copyright (c) 2026 noctalia-dev
- **Version checked:** v5.4.1
- **Upstream:** https://github.com/noctalia-dev/noctalia
- **Used by:**
  - `.config/noctalia/config.toml`
  - `.config/noctalia/palettes/`
  - `.config/hypr/keybind.lua`
  - `.config/hypr/startup.lua`
  - `scripts/iarch-control-center.sh`
  - `scripts/iarch-healthcheck.sh`
  - `install.sh`
- **Notes:** Configuration keys in this repository were checked against the upstream v5.4.1 schema; see docs/UNVERIFIED.md for what still needs a live-session check.
- **Open verification items:** `TP-09` in `docs/UNVERIFIED.md`

### Hyprland

Wayland compositor. The session configuration is written in its Lua configuration API.

- **License:** BSD-3-Clause
- **Copyright:** Copyright (c) 2022-2026, vaxerski
- **Upstream:** https://github.com/hyprwm/Hyprland
- **Used by:**
  - `.config/hypr/`
- **Open verification items:** `TP-10` in `docs/UNVERIFIED.md`

### fastfetch

System information display used in the terminal.

- **License:** MIT
- **Copyright:** Copyright (c) 2021-2023 Linus Dierheimer; Copyright (c) 2022-2026 Carter Li
- **Upstream:** https://github.com/fastfetch-cli/fastfetch
- **Used by:**
  - `.config/fastfetch/config.jsonc`

### kitty

GPU accelerated terminal emulator.

- **License:** GPL-3.0-only
- **Copyright:** Copyright (c) Kovid Goyal
- **Upstream:** https://github.com/kovidgoyal/kitty
- **Used by:**
  - `.config/kitty/`

### fish shell

Interactive shell used by the terminal profile.

- **License:** GPL-2.0-only
- **Copyright:** Copyright (C) 2005-2009 Axel Liljencrantz and fish-shell contributors
- **Upstream:** https://github.com/fish-shell/fish-shell
- **Used by:**
  - `.config/fish/config.fish`
- **Notes:** Upstream COPYING also covers components under other licenses; see that file for the authoritative list.

### Starship

Cross-shell prompt.

- **License:** ISC
- **Copyright:** Copyright (c) 2019-2022, Starship Contributors
- **Upstream:** https://github.com/starship/starship
- **Used by:**
  - `.config/starship.toml`
  - `legacy/config/minimalinux/starship-detailed.toml`
  - `legacy/config/minimalinux/starship-minimal.toml`

### Satty

Screenshot annotation tool bound to a keybind.

- **License:** MPL-2.0
- **Copyright:** See upstream source headers
- **Upstream:** https://github.com/gabm/Satty
- **Used by:**
  - `.config/hypr/keybind.lua`

### adw-gtk3

GTK 3 theme used to match the shell look in classic GTK applications.

- **License:** LGPL-2.1-only
- **Copyright:** See upstream source headers
- **Upstream:** https://github.com/lassekongo83/adw-gtk3
- **Used by:**
  - `legacy/config/gtk-3.0/settings.ini`
  - `install.sh`
  - `fedora_install.sh`

### Papirus icon theme

Icon theme selected by the session presets.

- **License:** GPL-3.0-only
- **Copyright:** Copyright (c) Papirus Development Team
- **Upstream:** https://github.com/PapirusDevelopmentTeam/papirus-icon-theme
- **Used by:**
  - `legacy/config/gtk-3.0/settings.ini`
  - `install.sh`

### Session helper utilities

Small tools the session calls for screenshots, clipboard, media keys, volume and policy authentication: hyprshot, grim, slurp, wl-clip-persist, pamixer, playerctl, polkit-gnome-authentication-agent-1, gnome-keyring-daemon, EasyEffects, ddcutil.

- **License:** Varies per package
- **Copyright:** See each package
- **Upstream:** Each project's own repository
- **Used by:**
  - `.config/hypr/keybind.lua`
  - `.config/hypr/startup.lua`
  - `install.sh`
- **Notes:** Installed from the distribution or AUR; each package ships its own license. Nothing from these projects is stored in this repository.
- **Open verification items:** `TP-11` in `docs/UNVERIFIED.md`

### Fonts, icon and cursor themes installed by the installer

Bibata cursor theme, Yaru and Humanity icon themes, Papirus folders, Noto emoji, DejaVu and Symbola fonts, and the Microsoft core fonts package offered on Arch.

- **License:** Varies per package
- **Copyright:** See each package
- **Upstream:** Each project's own repository
- **Used by:**
  - `install.sh`
  - `fedora_install.sh`
- **Notes:** Installed from the distribution; licenses come from the distribution package metadata. Nothing from these projects is stored in this repository.
- **Open verification items:** `TP-12` in `docs/UNVERIFIED.md`

## Artwork and audio assets stored in this repository

### HeSuVi HRIR audio assets

Impulse response WAV files selectable by the virtual surround convolver profile.

- **License:** TODO(verify)
- **Copyright:** TODO(verify)
- **Used by:**
  - `pipewire/hrir/`
- **Notes:** 624 WAV files, about 32 MB. Several names refer to commercial vendor surround products, so the redistribution rights are not established. Review before publishing a release or mirroring this repository.
- **Open verification items:** `TP-03` in `docs/UNVERIFIED.md`

### fastfetch ASCII logo files

Selectable artwork for the system information display.

- **License:** TODO(verify)
- **Copyright:** TODO(verify)
- **Used by:**
  - `.config/fastfetch/logo/`
- **Notes:** Seven .icon files of artwork derived from anime franchises. Authorship and redistribution rights are not established.
- **Open verification items:** `TP-04` in `docs/UNVERIFIED.md`

## Third-party services, repositories and registries

### Chaotic-AUR

Third-party Arch repository and keyring enabled by the Arch installer for prebuilt AUR packages.

- **License:** Service terms of the operator
- **Copyright:** Chaotic-AUR maintainers
- **Upstream:** https://aur.chaotic.cx/
- **Used by:**
  - `install.sh`
- **Notes:** The installer edits /etc/pacman.conf and imports the signing key. Review before running; the package builds come from third parties.
- **Open verification items:** `TP-05` in `docs/UNVERIFIED.md`

### Noctalia plugin registry

Remote plugin index the shell can install plugins from.

- **License:** No license file published upstream at verification time
- **Copyright:** noctalia-dev and individual plugin authors
- **Upstream:** https://github.com/noctalia-dev/noctalia-plugins
- **Used by:**
  - `legacy/config/noctalia/plugins.json`
- **Notes:** Referenced by URL only; no plugin source is downloaded into this repository by the installer. The registry publishes no top-level LICENSE file, and each plugin carries its own manifest license.
- **Open verification items:** `TP-06` in `docs/UNVERIFIED.md`

## Verification

Upstream project metadata and LICENSE/COPYING files read through the GitHub REST API on the tag or branch named in each entry.

Items that could not be verified are listed in [`docs/UNVERIFIED.md`](docs/UNVERIFIED.md). They are never presented as working features.
