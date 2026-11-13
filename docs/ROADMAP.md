# Roadmap — the glass session in six parts

The destination: a fully glass, fully animated, deeply customizable desktop session — a glass
settings app, a glass control center, animated notifications, hover/open/close animations, premium
fonts and icons, a complete shortcut system behind `Super+H`, a Contact/Portfolio page, and an
installer that is safe to run twice.

Each part is specified by its own work order. This file records the intended sequence, what has
landed, and how each part is accepted. Parts 4 to 7 are provisional until their work order arrives;
when it does, this file is updated in the same commit.

The sequence below is not the one this file first guessed. Part 3's work order turned out to be the
deep-glass and session-surfaces work rather than the shortcut system, and the parts after it moved to
match: the settings app is Part 4, the in-session overlays Part 5, installer safety Part 6 and the
shortcut system Part 7. Those are the numbers the code already cites -- `iarch/settings-app/README.md`
reserves itself for Part 4, `iarch/README.md` schedules the rest of `iarch-doctor` for Part 5,
`docs/UNVERIFIED.md` defers DDC brightness to Part 6, and `data/keybinds.default.json` reserves
`Super+H` for Part 7 -- so a reader who follows a citation out of a source file lands on the part that
file meant.

Global rules that apply to every part:

- No invented configuration keys, IPC commands or CLI flags. Verify against the upstream release
  this repository targets, or record the claim in [UNVERIFIED.md](UNVERIFIED.md) with `TODO(verify)`
  in the code.
- Safety first: back up before overwriting, idempotent scripts, no recursive `chown` of a config
  tree, no silent package removal, no `curl | bash`, no `--noconfirm` for an unreviewed AUR package.
- Every visual effect is switchable and a Performance preset always exists.
- Credit lives only in `THIRD_PARTY_NOTICES.md` and Settings → About → Open-source licenses; the
  everyday UI says iArch by Safari.
- Small commits, each proven by `bash -n`, `python3 -m unittest discover -s tests` and the lint.

## Part 1 — Foundation, cleanup, branding, structure ✅ landed

**Goal:** make the next five parts safe and mechanical to build on.

| Deliverable | Where | Proof |
| --- | --- | --- |
| Product naming defined once | `branding/product.env`, `tools/iarch_brand.py` | `tests/test_branding.py` |
| Third-party credit generated, not hand-written | `branding/notices.json`, `tools/notices.py`, `THIRD_PARTY_NOTICES.md` | `python3 tools/notices.py --check` |
| Naming policy enforced mechanically | `tools/branding_lint.py` | `tests/test_branding_lint.py` |
| Everyday UI rebranded | shell profile, palette `iarch-midnight`, keybind descriptions, terminal greeting, session menu entries, window titles, `scripts/iarch-*.sh` | `python3 tools/branding_lint.py` → 0 findings |
| Unverified claims registered | `docs/UNVERIFIED.md` | referenced by `notices.json` and validated |
| Repository map, payload separation, safety and performance contracts | `docs/ARCHITECTURE.md` | `tests/test_payload_map.py`, `tests/test_architecture_docs.py` |
| Naming and credit policy written down | `docs/BRANDING.md` | linked from README |
| Shared safe shell helpers | `lib/iarch-common.sh` | `tests/test_iarch_common.sh` |
| Performance preset that cannot invent keys | `profiles/performance.toml`, `tools/profile_preset.py` | `tests/test_profile_preset.py` |
| Root cleaned, historical docs marked | `legacy/`, `assets/screenshots/`, banners | `tests/test_payload_map.py` |
| One place owns user state: defaults in `data/`, settings in `~/.config/iarch/`, atomic generated writes, five backups | `iarch/lib/configstore.py`, `data/*.default.json` | `tests/test_config_store.py` |
| Keyboard map is data, not prose | `data/keybinds.default.json`, `tools/extract_keybinds.py` | `tests/test_keybinds_data.py`, `--check` in CI |
| Glass design tokens recorded with their source | `data/design/glass.tokens.json` | `data/schemas/design-tokens.schema.json` |
| Credit rendered twice from one source, no license guessed | `branding/notices.json`, `tools/notices.py`, `THIRD_PARTY_NOTICES.md`, `data/licenses.json` | `tests/test_licenses_data.py` |
| Copyright header defined once and applied to new files | `branding/product.env`, `docs/BRANDING.md` | `tests/test_copyright_headers.py` |
| Shortcut table generated from the session, never typed | `tools/render_shortcuts.py`, `docs/SHORTCUTS.md` | `tests/test_shortcuts_doc.py` |
| Previous names survive only where a reason is recorded | `tools/naming_audit.py` | `tests/test_naming_audit.py` |
| Every data file validated against a schema | `data/schemas/` | `tests/test_data_files.py` |
| No broken reference in a script or a document | `tests/test_repo_paths.py` | itself |
| README under 250 lines, in a fixed order, claiming only what exists | `README.md` | `tests/test_readme_structure.py` |
| Governance written down | `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` | linked from README |
| CI renamed and extended: non-root guard, JSON Schema, TOML, gitlink and clean-tree checks | `.github/workflows/iarch-checks.yml` | workflow run |

License data was verified against upstream on 2026-11-09; the verification method is recorded in
`THIRD_PARTY_NOTICES.md` and the open items in [UNVERIFIED.md](UNVERIFIED.md).

**Explicitly not done in Part 1:** no installer behaviour was changed. `install.sh` still runs
`pacman -S --noconfirm`, `pacman -Syu --noconfirm` and `yay -S --noconfirm` for an AUR greeter
package, and still switches the display manager. Those are `INS-01` to `INS-03` and belong to
Part 6, where they can be changed with tests around them.

## Part 2 — Glass surfaces and motion ✅ landed

**Goal:** the compositor-side glass: blur, borders, rounding, shadows and the open/close/hover
animation set, all switchable.

| Deliverable | Where | Proof |
| --- | --- | --- |
| Design tokens bounded by the compositor's own limits, and colour presets that cannot ship below WCAG | `data/design/tokens.json`, `data/design/presets/*.json` | `data/schemas/tokens.schema.json`, `tests/test_design_tokens.py`, `iarch/cli/contrast_check.py` |
| Seeded 4K WebP wallpapers the generated presets own, inside a 600 KB budget; two presets keep bundled art | `assets/wallpapers/generated/*.webp`, `iarch/cli/gen_wallpapers.py` | `tests/test_wallpapers.py`, `--check` in CI |
| Hyprland decoration, layer and window rules for the shell surfaces — blur, borders, rounding, shadows, per-surface opacity — from the tokens | `.config/hypr/generated/glass.lua`, `iarch/cli/gen_glass_lua.py` | `tests/test_glass_lua.py`, `tests/test_payload_map.py`, `--check` in CI |
| The shell `config.toml` and one palette per preset, refused past the upstream schema | `.config/noctalia/config.toml`, `.config/noctalia/palettes/*.json`, `iarch/cli/render_noctalia.py` | `tests/test_noctalia.py`, `--check` in CI |
| The GTK 4 and GTK 3 glass overlays, refused past what each version parses | `.config/gtk-4.0/gtk.css`, `.config/gtk-3.0/gtk.css`, `iarch/cli/render_gtk_css.py` | `tests/test_gtk_css.py`, `--check --repo` in CI |
| The Qt/Kvantum glass theme, refused past the keys `ThemeConfig.cpp` reads | `.config/Kvantum/`, `iarch/cli/render_kvantum.py` | `tests/test_kvantum.py`, `--check` in CI |
| The fontconfig that applies the font tokens, refused past the config DTD | `.config/fontconfig/fonts.conf`, `iarch/cli/gen_fontconfig.py` | `tests/test_fontconfig.py`, `--check` in CI |
| The animation set from the motion tokens, with a real Performance off switch | `.config/hypr/generated/animations.lua`, `iarch/cli/gen_animations_lua.py` | `tests/test_animations_lua.py`, `--check` in CI |
| One command applies a preset across every surface: contrast gate first, all-or-nothing write, verified reload | `iarch/cli/theme.py` (`iarch-theme`) | `tests/test_theme.py`, dry-run smoke in CI |

**Acceptance**, proven mechanically by `tests/test_part2_acceptance.py`:

- *Every effect has a named switch.* Blur, transparency, animations and shadows are the four
  `settings.effects` booleans; `settings.preset` is the coarse glass/performance master; and
  `settings.theme.intensity` selects crystal, frosted, soft or performance, the step every renderer
  consumes. The settings enum and the tokens' intensities are asserted to be the same set, so a
  switch can never name something the renderers lack.
- *The Performance preset lowers work.* The `performance` intensity sets `motion.enabled = false`, so
  the rendered `animations.lua` emits only Hyprland's master `animations:enabled = false` — zero
  animation leaves and zero curves, against frosted's eleven and five. The reduction is provable by
  inspection and asserted; the frame-timing, blur-cost and input-latency *measurement* on real
  hardware is still `PERF-01`, left open.
- *No effect on an unverifiable surface.* Every renderer validates its output against a
  `data/design/*.json` surface read out of the pinned upstream release (`verified_against`, `source`)
  and refuses a key, leaf, curve or property that release does not have. What no sandbox could
  observe — a live Hyprland or Noctalia session — is `TP-10`, `SES-02` and `UI-05`, and the
  icon-theme runtime gap is `TP-19`, all in [UNVERIFIED.md](UNVERIFIED.md).

**Explicitly not done in Part 2:** the settings application that reconciles the coarse
`preset`/`effects` switches with `theme.intensity` is Part 4; the cursor is applied statically by
`themes/theme.lua` (a verified no-op, every preset shipping the same one) and the icon theme is
reported, not applied (`TP-19`); and no installer behaviour changed (`INS-01` to `INS-06`, Part 6).

## Part 3 — Deep glass: motion, session surfaces, lock, login and the two modes ✅ landed

**Goal:** everything the session does that is not a decoration -- how it moves, how it notifies, how it
locks, how it logs in, and the two switches that trade glass for performance and for focus -- built on
surfaces read out of a pinned upstream release rather than out of documentation that may be ahead of it.

| Deliverable | Where | Proof |
| --- | --- | --- |
| The compositor's animation surface recorded, and five motion presets a person can switch | `data/design/animations.json`, `data/design/animations/{smooth,snappy,bouncy,minimal,off}.json` | `data/schemas/animations.schema.json`, `data/schemas/animations_preset.schema.json`, `tests/test_animation_presets.py` |
| One command switches the preset, verifies the reload against the compositor's own error list, and rolls the file back when the reload reports anything new | `iarch/cli/iarch_anim.py` | `tests/test_iarch_anim.py` |
| Motion QA that can be run on a real machine, and the document that says what it still cannot check | `iarch/cli/qa_motion.sh`, `docs/MOTION.md` | `bash -n`, MOT-01 to MOT-05 |
| The notification surface recorded, and a doctor that asks a running session instead of assuming one | `data/design/noctalia.json` (`sections.notification`, `sections.notification.filter`), `iarch/cli/iarch_doctor.py` | `tests/test_iarch_doctor.py`, NOT-01 to NOT-05 |
| The control-centre and session surfaces recorded, with an IPC wrapper that only sends commands from a fixed allowlist | `data/design/noctalia.json` (`sections.control_center`), `scripts/iarch-control-center.sh` | `tests/test_noctalia.py`, SES-02 |
| The launcher and the Alt+Tab window switcher recorded — including the two providers that do not exist upstream and are therefore not faked | `data/design/noctalia.json` (`sections.shell.keys.launcher`, `.window_switcher`) | `tests/test_noctalia.py`, UI-04 to UI-08 |
| Both lock screens and the idle fallback, rendered from one set of tokens, with the security-relevant keys emitted explicitly at their restrictive values | `.config/hypr/hyprlock.conf`, `.config/hypr/hypridle.conf`, `iarch/cli/render_hyprlock.py`, `data/design/hyprlock.json` | `tests/test_hyprlock.py`, LOCK-01 to LOCK-05 |
| The login screen recorded — and deliberately not rendered, because a greeter file this repository cannot verify is a login screen nobody can log into | `data/design/greeter.json`, `data/schemas/greeter.schema.json`, both installers | `tests/test_greeter.py`, GRE-01 to GRE-05 |
| Game mode and focus mode: compose values that already exist, then read the session back and restore what this run found | `iarch/lib/modes.py`, `iarch/cli/iarch_gamemode.py`, `iarch/cli/iarch_focus.py`, `data/design/tokens.json` (`modes`) | `tests/test_gamemode.py`, `tests/test_focus.py`, MODE-01 to MODE-04 |
| The startup module rendered from a record of what it may run, with both installers' `sed` anchors asserted in the render | `data/design/startup.json`, `iarch/cli/gen_startup_lua.py`, `.config/hypr/startup.lua` | `tests/test_startup_lua.py`, START-01 and START-02 |
| The wallpaper surface recorded, including the one animation in the session that neither motion switch reaches | `data/design/noctalia.json` (`sections.wallpaper`), `iarch/cli/render_noctalia.py` | `tests/test_noctalia.py`, WAL-01 and WAL-02 |

**Acceptance**, proven mechanically by `tests/test_part3_acceptance.py`:

- *Every emitted key exists in the pinned release's surface record.* Hyprland v0.57.2 for the
  compositor's leaves, animation tree, Lua bindings and lock screen; Noctalia v5.4.1 for the shell's
  settings; noctalia-greeter v1.7.0 for the login screen, pinned to a tag because its `main` already
  carries keys the tag does not. Where upstream publishes no tagged manual — hyprlock — the record cites
  the wiki's `main` with the date it was fetched, and LOCK-04 says what that costs. A key upstream
  declares but whose reader discards is recorded `write_only` and never emitted; a key this project
  refuses on principle is recorded `withheld`, so the validator says "withheld on purpose, and here is
  why" instead of claiming upstream has no such setting.
- *Generated files are committed and CI-checked.* Eleven text payloads carry a GENERATED header naming
  the record they came from, the six palettes carry the same sentence as their `_generated` key, and
  every tool that can check itself is checked in `.github/workflows/iarch-checks.yml`,
  and both mode switches get a dry-run smoke line there, so a payload cannot drift from the record that
  justifies it without a workflow failing.
- *A missing binary is unverified, never a failure and never a pass.* Run any report subcommand with
  nothing on `PATH` and it exits 0 with the verdict `unverified`, every check carrying `actual: null`
  and the name of the binary that was not there; `iarch-doctor` answers `unknown` rather than guessing.
  A session that was asked and disagreed exits 1 and leaves the files and the record alone, because
  rolling back would put the disk in a third state.
- *Documentation states what a surface cannot do as plainly as what it can.* Every limitation is a row
  in [UNVERIFIED.md](UNVERIFIED.md) with the evidence that does exist and the claim it blocks, and the
  documents that a reader would otherwise take the wrong way from say so where they are: `docs/MOTION.md`
  names the switch the wallpaper crossfade ignores, `docs/WALLPAPERS.md` no longer sends anybody to a
  directory the shell does not scan, `SECURITY.md` says a startup command's failure is silent by
  construction, and `README.md` says plainly that the two modes are commands with no key bound and no
  measured saving.

**Explicitly not done in Part 3:** no key binds either mode — `Super+H` and the overlay behind it are
Part 7, and until then both modes are commands you run (`python3 iarch/cli/iarch_gamemode.py toggle`).
There is still no settings GUI, which is Part 4, so the coarse `preset` and `effects` switches in
`data/settings.default.json` are read by no renderer and Part 4 has to reconcile them. No greeter file
is emitted. `.config/hypr/hypridle.conf` ships unlaunched, because the shell owns
`ext_idle_notifier_v1` and a second daemon would race it. No installer behaviour changed beyond the
greeter staging, so INS-01 to INS-06 are still Part 6. And nothing in this part was observed on a live
session: the frame-timing and latency measurement is still PERF-01, and MODE-01 to MODE-04, START-01
and START-02, WAL-01 and WAL-02 are the specific claims that a sandbox could not reach.

## Part 4 — Settings app, About page and Contact/Portfolio

**Goal:** the glass settings application: every switch introduced in Parts 1 to 3 reachable from it,
About → Open-source licenses rendered from the same JSON as `THIRD_PARTY_NOTICES.md`, and the
Contact/Portfolio page.

Provisional scope, and the reason it is provisional is that its work order has not arrived: a GTK4 +
libadwaita application (`dev.safari.iarch`, reserved in `iarch/settings-app/README.md`) that edits
`~/.config/iarch/settings.json`, calls the generators in `iarch/cli/`, reconciles the coarse
`preset`/`effects` switches with `theme.intensity`, renders the licenses page from
`data/licenses.json` and the contact page from `data/contacts.default.json`. Acceptance will have to
include: nothing in the settings UI names an upstream project; every visual switch in the product is
reachable; and the About page and `THIRD_PARTY_NOTICES.md` come from one source.

## Part 5 — Notifications, control center and the in-session overlays

**Goal:** animated notification cards, a glass control center, and the in-session overlays the CLIs
already report into — `iarch-keybinds`, and the rest of `iarch-doctor`.

Provisional scope: notification geometry, urgency styles, dismiss and history animation, control-center
panel styling, the overlays `iarch/cli/iarch_anim.py` and `iarch/cli/iarch_doctor.py` reserve, and the
allowlisted IPC shortcuts in `scripts/iarch-control-center.sh`. Acceptance will have to include: no
second notification daemon; and DND, replacement and history behaviour either verified on a live session
or still open in [UNVERIFIED.md](UNVERIFIED.md) as NOT-01 to NOT-05 are today.

## Part 6 — Installer safety and release readiness

**Goal:** an installer that is safe to run twice and honest about what it changed.

Provisional scope: adopt `lib/iarch-common.sh` across `install.sh` and `fedora_install.sh`, replace
blanket `--noconfirm` use with reviewed confirmation (`INS-01`), narrow ownership changes
(`INS-02`), make the display-manager switch reversible and logged (`INS-03`), record every system
change in a manifest, and finish fonts and icon theming (`TP-19`). Acceptance will have to include: a
second run changes nothing; a failed run reports exactly what it touched and where the backups are;
`tools/preflight.py` runs before any privileged step; and every `INS-` item is either closed with
evidence or still listed.

## Part 7 — Shortcut system

**Goal:** `Super+H` shows every shortcut, searchable, in glass.

Provisional scope: a single source of shortcut truth derived from the `description` fields already in
`.config/hypr/keybind.lua` and mirrored into `data/keybinds.default.json`, a renderer for the overlay,
and the three keys `docs/SHORTCUTS.md` already reserves so they are not reassigned by accident —
`Super+H`, `Super+Shift+H` and `Super+K`. Acceptance will have to include: the overlay lists every bind
that has a description; a bind without a description fails a test; the overlay opens and closes with
animation; and the surface is chosen from a verified API rather than a guessed one (`UI-02`).
