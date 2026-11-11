# Baseline: proven, contradictory, untested

Measured 2026-11-09 in a container as a normal user (uid 1001): no display server, no
Hyprland, no Noctalia, no pacman/dnf, no AUR helper. Every line below is what a command
printed here, not what a document claims.

## Commands and results

| Command | Result |
| --- | --- |
| `bash -n` on the 19 tracked `.sh` + the 2 shebang-less `legacy/session/*` launchers | 0 failures |
| `python3 -m unittest discover -s tests -p 'test_*.py'` | 74 tests, OK |
| the 3 pre-existing shell suites plus `test_iarch_common.sh` (54 checks) and `test_uninstall.sh` (24) | exit 0 |
| `python3 tools/notices.py --check`, `python3 tools/iarch_brand.py --check` | exit 0 |
| `python3 tools/branding_lint.py` | 0 findings |
| `shellcheck --severity=warning` (0.11.0) over those same 21 files | 0 errors, 0 warnings |
| the whole suite re-run as **root** (`sudo env PATH HOME=/root …`) | 7 test failures, 1 suite exit 1 |

The root failures (all in `tests/test_installer_cli.py`, plus `tests/session-install.sh`
exiting 1) are intended: the v4 installer refuses root.

## Proven by those commands

- Every shell script parses; five shell suites and 74 Python tests pass.
- `hyprland.lua`'s `require()` graph closes: 8 modules resolve, none missing, no
  shipped `.lua` file unreachable, and `lib/stage-v5-config.sh` deploys exactly 26
  files — asserted by `tests/test_payload_map.py`, which also proves no legacy v4
  file can enter that payload.
- Installer CLI parsing, staging, `.bak.<timestamp>` backups, recovery,
  diagnostics, customization, the glass preset and the profile helper behave as
  their tests specify — with the package manager, git and Hyprland stubbed.

## Documented but contradictory

1. `README.md` claimed a standalone repository while its badges pointed at the
   GitLab project it descends from; the credit now lives in `THIRD_PARTY_NOTICES.md`.
2. `README.md` says fresh Arch only and leave the display manager alone, while
   `install.sh` disables sddm and enables greetd, and the v4 installer changes no
   display manager at all (INS-01, INS-03).
3. `docs/V5-PORT-STATUS.md` calls the profile helper experimental and incomplete;
   the README ships that glass profile as the default.
4. `install.sh` sets `brightness.enableDdcSupport` in `noctalia/settings.json`;
   the v5 payload never deploys that file, and the v5 key is
   `[brightness] enable_ddcutil` (INS-06).
5. The vendored `hyprland-keybinds` plugin is v4 QML (`manifest.json`); v5 plugins
   are `plugin.toml` + `.luau` under `~/.local/share/noctalia/plugins/`, so it
   cannot load (TP-02, closed).
6. `install.sh` installs `hypridle` and `hyprlock`, but v5 `startup.lua` never
   starts `hypridle` — only the legacy `startup.conf` did. The v5 session has no
   idle timeout, DPMS-off or suspend; locking is `SUPER + L` (GAP-01).
7. `legacy/config/hypr/themes/theme.conf` and `.config/hypr/themes/theme.lua`
   disagree: gaps 5/10 vs 2/4, rounding 12 vs 8, inactive opacity 1.0 vs 0.90.
   The two sessions do not look alike.
8. `docs/AUDIT.md` describes a `.config/kitty/kitty-themes` gitlink; confirmed absent (`git ls-tree -r HEAD` has no mode 160000 entry, no `.gitmodules`), and `tests/test_repo_paths.py` keeps it that way.

## Untested — no evidence either way here

A real install on Arch or Fedora; package names and availability (TP-11, TP-12); a
live session (Hyprland, Noctalia, Wayland, GPU, audio, battery); `noctalia config
validate` (the tests stub the binary); the greetd/sddm switch and the reboot after
it; PipeWire convolver activation (INS-05); every Fedora path beyond `bash -n`.
Open items are tracked in `docs/UNVERIFIED.md`.

## What Hyprland actually loads (v5)

`.config/hypr/hyprland.lua` points `package.path` at `~/.config/hypr`, clears the
cached modules, then requires `monitors.lua`, `startup.lua`, `inputs.lua`,
`keybind.lua`, `windowrules.lua`, `animations.lua` (which requires
`animations/default.lua`) and `themes/theme.lua`, ending with `hl.config{…}`.
`keybind.lua` execs `Scripts/browser-launcher.sh` and `Scripts/workspace.sh` —
all 9 Lua files that ship: nothing missing, nothing extra.

Loaded by nothing: the 11 legacy Hyprlang files, relocated to `legacy/config/hypr/`
by TASK 2 of this part — `hyprland.conf` (the old entry point, sourcing the other
eight plus `themes/colors.conf`), `monitors.conf`, `startup.conf`, `inputs.conf`,
`keybinds.conf`, `windowrules.conf`, `animations.conf`, `animations/default.conf`,
`themes/theme.conf`, `themes/colors.conf`, `hypridle.conf`. Each is superseded by
its `.lua` counterpart, except `hypridle.conf` (no v5 equivalent: GAP-01) and
`themes/colors.conf` (folded into `themes/theme.lua` and the Noctalia palette).

