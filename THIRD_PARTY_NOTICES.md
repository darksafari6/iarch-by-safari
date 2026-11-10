# Third-party notices — iArch by Safari

<!-- GENERATED FILE - do not edit by hand.
     Source: branding/notices.json
     Regenerate: python3 tools/notices.py --write
     Verify: python3 tools/notices.py --check -->

Notices version 2 · updated 2026-11-10 · license information verified 2026-11-10

This repository is licensed as a whole under the GNU General Public License version 3.0; the full text is in LICENSE.txt and is not reproduced here.

iArch by Safari is an independent product. It ships configuration for third-party projects and a small amount of vendored third-party code and assets, listed below.

The product name shown in the desktop session is iArch by Safari. Upstream project names are intentionally kept out of the everyday UI; this file and the Settings page About -> Open-source licenses are the only places where third-party credit is displayed. See docs/BRANDING.md.

Packages that the installer only downloads from your distribution are licensed by that distribution. They are listed for completeness, not redistributed here.

## Product license

iArch by Safari is free software: you can redistribute it and/or modify it under the terms of the GPL-3.0-or-later license as published by the Free Software Foundation. The complete text is in [`LICENSE.txt`](LICENSE.txt) and is not reproduced here.

Maintained by Safari · https://github.com/darksafari6/iarch-by-safari

## What is listed here

- **Vendored code stored in this repository** — Third-party source code stored inside this repository.
- **Configuration and colors derived from third-party projects** — Configuration or color values in this repository derived from a third-party project.
- **Third-party software this product configures or launches** — Third-party software this configuration targets or launches; not redistributed here.
- **Artwork and audio assets stored in this repository** — Binary or artwork assets stored inside this repository.
- **Third-party services, repositories and registries** — Third-party network service, repository or registry used by the installer or the shell.
- **Where this repository came from** — Earlier publications of this same work, credited for history rather than reused as code.

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

### JetBrains Mono

Terminal typeface requested by the kitty configuration.

- **License:** OFL-1.1
- **Copyright:** Copyright 2020 The JetBrains Mono Project Authors
- **Upstream:** https://github.com/JetBrains/JetBrainsMono
- **Used by:**
  - `.config/kitty/kitty.conf`
  - `.config/kitty/minima-profile.conf`
- **Notes:** Both files request "JetBrainsMono Nerd Font Mono", the Nerd Fonts patched build of this face. License read from the upstream repository's LICENSE file on 2026-11-10.
- **Open verification items:** `TP-13` in `docs/UNVERIFIED.md`

### Nerd Fonts

Patched font build that supplies the powerline and icon glyphs kitty renders.

- **License:** OFL-1.1 (patched fonts); MIT (patcher tooling)
- **Copyright:** Copyright (c) 2014 Ryan L McIntyre
- **Upstream:** https://github.com/ryanoasis/nerd-fonts
- **Used by:**
  - `.config/kitty/kitty.conf`
- **Notes:** Upstream LICENSE states the split explicitly: patched fonts in folders carrying an OFL file are SIL Open Font License 1.1, the patcher source is MIT. Read 2026-11-10.
- **Open verification items:** `TP-13` in `docs/UNVERIFIED.md`

### DejaVu fonts

Wide-coverage fallback typeface installed by the Arch installer (ttf-dejavu).

- **License:** Bitstream Vera license; DejaVu changes are in the public domain
- **Copyright:** Fonts are (c) Bitstream; glyphs imported from Arev fonts are (c) Tavmjong Bah
- **Upstream:** https://github.com/dejavu-fonts/dejavu-fonts
- **Used by:**
  - `install.sh`
- **Notes:** License read from the first lines of the upstream LICENSE file on 2026-11-10.

### Noto Color Emoji

Emoji coverage installed by the Arch installer (noto-fonts-emoji).

- **License:** OFL-1.1
- **Copyright:** Copyright 2013 Google, Inc.
- **Upstream:** https://github.com/googlefonts/noto-emoji
- **Used by:**
  - `install.sh`
- **Notes:** License read from the upstream repository metadata on 2026-11-10.

### Bibata cursor theme

Pointer theme the session exports to Hyprland, XWayland and Qt.

- **License:** GPL-3.0-only
- **Copyright:** Copyright (c) 2018 Abdurahman
- **Upstream:** https://github.com/ful1e5/Bibata_Cursor
- **Used by:**
  - `.config/hypr/themes/theme.lua`
  - `legacy/config/gtk-3.0/settings.ini`
- **Notes:** Bibata-Modern-Classic at size 24 is set through HYPRCURSOR_THEME, XCURSOR_THEME and QT_CURSOR_THEME. Neither installer installs a package that provides it; see TP-13.
- **Open verification items:** `TP-13` in `docs/UNVERIFIED.md`

### Papirus Folders

Folder colour script installed alongside the Papirus icon theme.

- **License:** MIT
- **Copyright:** Copyright (c) 2018-2024 Papirus Development Team
- **Upstream:** https://github.com/PapirusDevelopmentTeam/papirus-folders
- **Used by:**
  - `install.sh`
- **Notes:** License read from the upstream repository metadata on 2026-11-10.

### Fonts offered by the installer whose licenses were not verified

ttf-symbola and ttf-ms-fonts, installed by the printer-support step of the Arch installer.

- **License:** TODO(verify)
- **Copyright:** TODO(verify)
- **Upstream:** ttf-ms-fonts is an AUR package of Microsoft's core fonts; ttf-symbola ships the Symbola face by George Douros.
- **Used by:**
  - `install.sh`
- **Notes:** Neither license could be read from a reachable upstream: ttf-ms-fonts redistributes fonts under Microsoft's own end-user terms and is not open source, and Symbola's terms were not published in a place this repository could verify. Both are installed only when the user opts into printer support, and nothing in the session configuration requires them.
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

### Pillow (the PIL fork)

Imaging library imported by iarch/cli/gen_wallpapers.py to render the generated preset wallpapers at 3840x2160 and encode them as WebP.

- **License:** MIT-CMU
- **Copyright:** Copyright (c) 1997-2011 Secret Labs AB; Copyright (c) 1995-2011 Fredrik Lundh and contributors; Copyright (c) 2010 Jeffrey 'Alex' Clark and contributors
- **Version checked:** 13.0.0
- **Upstream:** https://github.com/python-pillow/Pillow
- **Used by:**
  - `iarch/cli/gen_wallpapers.py`
- **Notes:** Its LICENSE states Pillow is licensed under the open source MIT-CMU License; the GitHub license API reports NOASSERTION for that wording, so the licence was read from the LICENSE file directly. Not a runtime dependency of an installed session: the generated WebP files ship in the repository, and Pillow is only needed to regenerate them.
- **Open verification items:** `TP-15` in `docs/UNVERIFIED.md`

## Where this repository came from

### The original dotfiles this repository started from

Safari's personal Arch Linux dotfiles, published on GitLab before this repository, under the names minimaLinux and minimaDots.

- **License:** GPL-3.0-or-later (this repository's own earlier publication)
- **Copyright:** Copyright (C) Safari
- **Upstream:** https://gitlab.com/minimalinux/minimaDots
- **Used by:**
  - `README.md`
  - `docs/BRANDING.md`
  - `THIRD_PARTY_NOTICES.md`
- **Notes:** This repository is that same continuing work, not a fork of someone else's project: the configuration, installers and history came from it. The project path was recovered from the GitLab badge links in the first commit of this repository's history (git show b3e20fc:README.md). gitlab.com is not reachable from the environment used to verify these notices, so the license text published there was not re-read; the older names survive in this repository only as frozen runtime identifiers and in historical documents, as docs/BRANDING.md explains.
- **Open verification items:** `TP-14` in `docs/UNVERIFIED.md`

## Verification

Upstream project metadata and LICENSE/COPYING files read through the GitHub REST API on the tag or branch named in each entry: first pass 2026-11-09 (compositor, shell, terminal, prompt, system information, screenshot annotation, audio, GTK and icon theme projects), extended 2026-11-10 for the typefaces, cursor theme and Papirus Folders. Where an upstream could not be reached, the entry says TODO(verify) and points at docs/UNVERIFIED.md instead of guessing.

Items that could not be verified are listed in [`docs/UNVERIFIED.md`](docs/UNVERIFIED.md). They are never presented as working features.
