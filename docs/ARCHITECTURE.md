# Architecture and repository layout

iArch by Safari is a Hyprland desktop session for Arch Linux and Fedora: dotfiles,
installers, runtime helpers and the tooling that keeps them honest. This document is
the map. Read it before changing anything.

- Naming and credit policy: [BRANDING.md](BRANDING.md)
- Claims that are not proven yet: [UNVERIFIED.md](UNVERIFIED.md)
- What is being built next: [ROADMAP.md](ROADMAP.md)
- Glass profile behaviour and recovery: [glass-experience.md](glass-experience.md)

## Repository layout

```
.
├── README.md                 Entry point for users: install, customize, uninstall.
├── InstallNotes.md           Long-form install and troubleshooting notes.
├── LICENSE.txt               GPL-3.0 license for this repository. Never edit or remove.
├── THIRD_PARTY_NOTICES.md    Generated. Third-party credit; edit branding/notices.json instead.
│
├── .config/                  The session payload (see "Two payloads" below).
│   ├── hypr/                 Compositor configuration: *.lua is current, *.conf is legacy v4.
│   ├── noctalia/             Shell configuration: config.toml + palettes/ (v5), settings.json + plugins/ (v4).
│   ├── fastfetch/            System information layout and artwork.
│   ├── kitty/                Terminal configuration and generated color/profile includes.
│   ├── fish/                 Interactive shell configuration, including the greeting.
│   ├── gtk-3.0/, gtk-4.0/    GTK theme and icon preferences.
│   ├── starship.toml         Prompt configuration.
│   └── minimalinux/          Frozen legacy v4 customization center (Python/GTK 3).
│
├── branding/                 Product identity, machine-readable.
│   ├── product.env           The only definition of the product name, ids and runtime paths.
│   └── notices.json          The only definition of third-party credit.
│
├── profiles/                 Effect presets applied on top of the shipped shell profile.
│   └── performance.toml      Overlay: same keys, lower cost. See "Performance contract".
│
├── lib/                      Shell libraries sourced by the installers.
│   ├── iarch-common.sh       Logging, timestamped backups, safe install, user resolution.
│   ├── managed-files.sh      Classifies an installed system file before touching it.
│   ├── package-audit.sh      Records which packages an install added. Never removes any.
│   └── stage-v5-config.sh    Builds the v5-only payload in a caller-owned empty directory.
│
├── tools/                    Python helpers. Stdlib only; no desktop is started by tests.
│   ├── iarch_brand.py        Reads branding/product.env; validates naming consistency.
│   ├── notices.py            Renders and checks THIRD_PARTY_NOTICES.md.
│   ├── branding_lint.py      Fails when the everyday UI shows an upstream or previous name.
│   ├── profile_preset.py     Applies or reverts an effect preset, backup first.
│   ├── preflight.py          Read-only host checks before an install.
│   ├── diagnose.py           Read-only session diagnostics (legacy v4 session).
│   ├── recover_session.py    Lists and restores session backups (legacy v4 session).
│   ├── glass_preset.py       Experimental glass preset for the legacy v4 session.
│   └── v5_profile.py         Stages the shell profile or restores an explicit backup.
│
├── scripts/                  Runtime helpers a user runs inside the session.
│   ├── iarch-healthcheck.sh  Read-only diagnostics; changes nothing.
│   └── iarch-control-center.sh  Allowlisted IPC shortcuts for the shell.
│
├── session/                  Wayland session launchers and menu entries for the legacy v4 session.
├── pipewire/                 Optional virtual-surround convolver profile and HRIR assets.
├── assets/screenshots/       Images used by README and docs.
├── legacy/                   Reference code that is not a supported entry point.
├── docs/                     This directory.
├── tests/                    Shell and Python tests. See "Testing map".
├── trailer/                  Release video asset, not referenced by the session.
│
├── install.sh                Arch installer: system-wide, root, fresh install.
├── fedora_install.sh         Fedora installer: system-wide, root, fresh install.
├── uninstall.sh              Restores timestamped backups; never deletes an active config.
├── install-v4-session.sh     Installs the isolated legacy session for one user.
└── uninstall-v4-session.sh   Removes only the managed launchers of that session.
```

## Two payloads

The repository carries two mutually incompatible configuration sets. Mixing them is the
single easiest way to break a session, so every installer stages exactly one.

| | Current session (v5) | Legacy isolated session (v4) |
| --- | --- | --- |
| Compositor config | `.config/hypr/*.lua` (Lua API) | `.config/hypr/*.conf` (Hyprlang) |
| Shell config | `.config/noctalia/config.toml` + `palettes/*.json` | `.config/noctalia/settings.json` + `plugins/` |
| IPC used by keybinds | `noctalia msg ...` | `qs -c noctalia-shell ipc call ...` |
| Deployed by | `install.sh`, `fedora_install.sh` via `lib/stage-v5-config.sh` | `install-v4-session.sh` (copies `.config` wholesale) |
| Config root | `~/.config` | `~/.config/minimalinux` (its own `XDG_CONFIG_HOME`) |
| Status | Supported | Frozen. Kept working, not developed further |

`lib/stage-v5-config.sh` is the boundary: it copies an explicit allowlist of v5 paths and
fails if one is missing, so a v4 file can never reach a v5 install. `tests/test_v5_staging.py`
proves the exclusion in both directions.

### Frozen legacy identifiers

The legacy session keeps the identifiers other programs match on, even though they carry the
previous product name:

- the path `~/.config/minimalinux` and the launcher names `minimalinux-session`, `minimalinux-customize`;
- the marker line `# Managed by minimaLinux session installer` that `lib/managed-files.sh` uses to
  decide whether a system file is safe to replace or remove;
- the generated include names `kitty/minima-colors.conf` and `kitty/minima-profile.conf`;
- comments written into generated configuration files.

Renaming any of these would orphan already-installed systems: the marker would stop matching,
so the installer and the uninstaller would refuse to manage their own files. What a person reads
on screen (session menu entries, window titles, labels, CLI output) is rebranded; what a program
matches on is not. `tools/branding_lint.py` encodes that line.

## Runtime map

```
display manager (greetd) ──> Hyprland ──> .config/hypr/hyprland.lua
                                              ├── monitors.lua   displays and scaling
                                              ├── startup.lua    environment, autostart, shell launch
                                              ├── inputs.lua     keyboard and pointer
                                              ├── keybind.lua    every shortcut, each with a description
                                              ├── windowrules.lua  per-application rules
                                              ├── animations.lua  animation and bezier curves
                                              └── themes/theme.lua  accent colors
                                                        │
                                                        └──> shell process (bar, dock, launcher,
                                                             Control Center, notifications, Settings,
                                                             lock screen) driven by `noctalia msg ...`
                                                                      │
                          scripts/iarch-control-center.sh ────────────┘  allowlisted IPC shortcuts
                          scripts/iarch-healthcheck.sh ─── read-only probe of shell, compositor, audio
```

Keybind descriptions in `keybind.lua` are the data source for the shortcut overlay planned in
[ROADMAP.md](ROADMAP.md). Keep them short, accurate and free of upstream names; the lint checks
all three.

## Safety contract

Rules every script in this repository is held to. Deviations that exist today are listed in
[UNVERIFIED.md](UNVERIFIED.md) with an `INS-` id and are scheduled work, not accepted behaviour.

1. **Back up before overwriting**, with a timestamped suffix (`.bak.<timestamp>`), and verify the
   backup destination is free before moving anything. `lib/iarch-common.sh` implements this once.
2. **Idempotent by default.** Running a script twice must not duplicate work or destroy the first
   run's result. Skipping an unchanged file is a success, not a no-op to hide.
3. **Never `chown -R` a whole config tree.** Ownership changes are limited to paths this repository
   actually deployed.
4. **Never remove packages silently.** Removals are listed, explained and explicitly approved, and
   additions are recorded by `lib/package-audit.sh`.
5. **Never `curl | bash`.** Every script is read from the checkout the user inspected.
6. **Never pass `--noconfirm` for an unreviewed AUR package.**
7. **Refuse ambiguous targets.** Symlinks, files whose content differs from the shipped source, and
   unmanaged paths are reported and left alone rather than overwritten.
8. **Fail closed and say where the backup is.** A partial operation must tell the user what changed
   and how to get back.

## Performance contract

Every visual effect must be switchable, and a lower-cost preset must always exist.

- The shipped profile (`.config/noctalia/config.toml`) is the default "glass" look.
- `profiles/performance.toml` is an overlay that changes **values only**, never keys:
  `tools/profile_preset.py` rejects any overlay path that does not already exist in the base
  profile, which is what makes inventing configuration keys impossible.
- Applying a preset backs up first, validates, and can be reverted.
- No preset may claim a measured gain until it has one; see `PERF-01` in [UNVERIFIED.md](UNVERIFIED.md).

## Testing map

| Command | Proves |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | All Python-level logic: naming, notices, lint, staging, presets, installer CLI, recovery, diagnostics |
| `./tests/session-install.sh` | The legacy session installer against a mocked filesystem and mocked sudo |
| `./tests/managed-files.sh` | System-file classification (absent, identical, symlink, unmanaged, modified) |
| `./tests/package-audit.sh` | Package-addition recording, with no removal path |
| `python3 tools/notices.py --check` | The notices file matches its source |
| `python3 tools/iarch_brand.py --check` | Product naming is consistent and referenced files exist |
| `python3 tools/branding_lint.py` | Everyday-UI surfaces carry no previous product or upstream shell name |
| `bash -n <script>` | Shell syntax of every script |
| `shellcheck <script>` | Shell quality, where shellcheck is installed |

What no test here proves: a real Arch or Fedora install, a live Hyprland session, GPU behaviour,
audio hardware, package availability, or how the shell actually renders. Those need a machine and
are tracked in [UNVERIFIED.md](UNVERIFIED.md). Tests use temporary directories and mocks; they
never touch `~/.config`, never call a package manager and never start a session.

## Documentation set

| Document | Status |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Current. This file |
| [BRANDING.md](BRANDING.md) | Current. Naming and credit policy |
| [ROADMAP.md](ROADMAP.md) | Current. The six-part glass plan |
| [UNVERIFIED.md](UNVERIFIED.md) | Current. Open verification items |
| [glass-experience.md](glass-experience.md) | Current. Glass profile and recovery |
| [V4-SESSION.md](V4-SESSION.md), [V4-INSTALL-NOTES.md](V4-INSTALL-NOTES.md) | Historical. Legacy isolated session |
| [GLASS-UI.md](GLASS-UI.md) | Historical. Legacy v4 glass preset audit |
| [AUDIT.md](AUDIT.md), [STATUS-2.0.md](STATUS-2.0.md) | Historical. Repository and installer audit |
| [V5-PORT-STATUS.md](V5-PORT-STATUS.md) | Historical. Port status between the two payloads |

Historical documents are kept because they record why the current safety rules exist. They are
marked with a banner and are not instructions for today's session.
