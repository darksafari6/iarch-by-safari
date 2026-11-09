# Unverified items

Every claim this repository makes about a feature must be either verified or listed here.
An item stays in this file until someone proves it on a real system and records how.
Code that depends on an unverified item carries a `TODO(verify)` comment pointing at its id.

Nothing in this file is a bug report or a wishlist. It is the boundary between
"checked" and "assumed".

Verification log for third-party license data: **2026-11-09**, upstream repository metadata and
`LICENSE`/`COPYING` files read through the GitHub REST API. Tooling: `tools/notices.py --check`.

## How to close an item

1. Reproduce it on the target system (Arch or Fedora, real Hyprland session).
2. Record the command, the version and the observed result in the *Evidence* column.
3. Remove the `TODO(verify)` marker from the code that referenced the id.
4. Delete the row here in the same commit.

## Third-party credit and assets

| Id | Item | Why it is unverified | Blocking |
| --- | --- | --- | --- |
| TP-01 | Copyright holder and year for the vendored `hyprland-keybinds` Noctalia plugin | `manifest.json` declares `"license": "MIT"` and `"author": "tonekneeo"` but states no copyright year, and no `LICENSE` file is vendored next to the code | Publishing a release |
| TP-02 | Whether Noctalia v5.4.1 loads the vendored `hyprland-keybinds` plugin | Its manifest declares `minNoctaliaVersion 4.1.2` and its widgets use the v4 plugin API. `.config/noctalia/plugins.json` separately enables `keybind-cheatsheet` and `screen-recorder` from the upstream registry, which are different plugin ids | Shipping the plugin as part of the session |
| TP-03 | Redistribution rights for the HeSuVi HRIR assets in `pipewire/hrir/` (624 WAV files, ~32 MB) | Several file names refer to commercial vendor surround products; no license or provenance record ships with them | Publishing a release or a mirror |
| TP-04 | Authorship and rights for `.config/fastfetch/logo/*.icon` | Seven artwork files with no attribution record | Publishing a release |
| TP-05 | Chaotic-AUR terms, keyring trust and package provenance | `install.sh` imports the signing key, edits `/etc/pacman.conf` and installs prebuilt AUR packages; the operator's terms and the individual builds were not reviewed | Running `install.sh` on a machine you care about |
| TP-06 | License of the `noctalia-dev/noctalia-plugins` registry | The upstream repository published no top-level `LICENSE` file at verification time; each plugin carries its own manifest license | Redistributing anything fetched from that registry |
| TP-07 | Exact upstream revision of the PipeWire filter-chain example that `pipewire/pipewire.conf.d/sink-virtual-surround-7.1-hesuvi.conf` was derived from | The file follows the upstream virtual-surround example but records no revision | Precise attribution |
| TP-08 | Exact upstream revision and variant of the Tokyo Night color values | Values are adapted into `.config/kitty/minima-colors.conf`; the source revision is not recorded | Precise attribution |
| TP-09 | Live behavior of the Noctalia v5 profile | **Partly verified:** all 137 leaf keys of `.config/noctalia/config.toml` appear in the upstream v5.4.1 schema sources (`src/config/schema/config_schema.cpp`, `src/config/config_types.h`), and `custom_palette` is documented as the stem of a JSON file in `palettes/`. **Not verified:** rendered appearance, GUI-managed override precedence in `~/.local/state/noctalia/settings.toml` on a real machine, and the output of `noctalia config validate` | Claiming the glass profile works |
| TP-10 | Hyprland Lua configuration API used by `.config/hypr/*.lua` | The `hl.*` calls were not checked against a pinned Hyprland release in this pass, and no `Hyprland --verify-config` or live-session run was available | Claiming the session config loads |
| TP-11 | Availability and names of the session helper packages on Arch and Fedora | `hyprshot`, `grim`, `slurp`, `wl-clip-persist`, `pamixer`, `playerctl`, `polkit-gnome`, `gnome-keyring`, `easyeffects`, `ddcutil` are called by keybinds and startup but were not resolved per distribution in this pass | Running the session on a fresh install |
| TP-12 | Licensing and availability of `ttf-ms-fonts` and other AUR appearance packages | Offered by `install.sh`; redistribution terms differ from official repository packages | Offering them in the installer |

## Session, UI and installer behavior

| Id | Item | Why it is unverified | Blocking |
| --- | --- | --- | --- |
| UI-01 | How Noctalia Settings labels a custom palette | The palette file is named from `IARCH_PALETTE_ID`; upstream documents the file-stem lookup but does not document whether the picker prettifies the stem, so the on-screen label for `iarch-midnight` was not observed | Naming the palette in documentation |
| UI-02 | Shortcut overlay surface for the v5 session | The legacy v4 customization center binds `Super+H` to a GTK window; the v5 equivalent is planned for a later part and no supported API has been selected yet | Binding `Super+H` on v5 |
| PERF-01 | Measured effect of the Performance overlay | `profiles/performance.toml` only lowers values of keys that already exist in the shipped profile; frame timing, blur cost and input latency were not measured on real hardware | Claiming a performance gain |
| INS-01 | Safety of `install.sh` package operations | It runs `pacman -S --noconfirm`, `pacman -Syu --noconfirm`, `yay -S --noconfirm noctalia-greeter-git` and, after an interactive approval, `pacman -Rns --noconfirm`. That conflicts with the safety contract in `docs/ARCHITECTURE.md`; the safer flow is scheduled work, not a claim made today | Recommending `install.sh` unattended |
| INS-02 | Recursive ownership changes in `deploy_configs` | `chown -R` is restricted to the deployed paths (`fastfetch fish hypr kitty noctalia starship.toml`) rather than all of `~/.config`, but the effect on pre-existing user files inside those paths was not observed on a live system | Installing over an existing desktop |
| INS-03 | Display-manager switch performed by `install.sh` | It installs `noctalia-greeter-git` from the AUR, writes `/etc/greetd/config.toml`, disables `sddm` and enables `greetd`; none of that was validated on a booting machine | Fresh-install documentation |
| INS-04 | Behavior of `noctalia config validate` across versions | Documented for v5.4.1 upstream; the exit codes and messages of the installed build were not observed | Automated validation in scripts |
| INS-05 | Activation of the PipeWire virtual-surround profile | The convolver references `~/.config/pipewire/hrir/atmos.wav`, which is not the path the installer deploys the HRIR assets to, and no audio device was available for a test | Documenting surround sound as working |
