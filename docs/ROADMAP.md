# Roadmap — the glass session in six parts

The destination: a fully glass, fully animated, deeply customizable desktop session — a glass
settings app, a glass control center, animated notifications, hover/open/close animations, premium
fonts and icons, a complete shortcut system behind `Super+H`, a Contact/Portfolio page, and an
installer that is safe to run twice.

Each part is specified by its own work order. This file records the intended sequence, what has
landed, and how each part is accepted. Parts 2 to 6 are provisional until their work order arrives;
when it does, this file is updated in the same commit.

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
`preset`/`effects` switches with `theme.intensity` is Part 5; the cursor is applied statically by
`themes/theme.lua` (a verified no-op, every preset shipping the same one) and the icon theme is
reported, not applied (`TP-19`); and no installer behaviour changed (`INS-01` to `INS-06`, Part 6).

## Part 3 — Shortcut system

**Goal:** `Super+H` shows every shortcut, searchable, in glass.

Planned scope: a single source of shortcut truth derived from the `description` fields already in
`.config/hypr/keybind.lua`, a renderer for the overlay, and the keybind itself. Acceptance: the
overlay lists every bind that has a description; a bind without a description fails a test; the
overlay opens and closes with animation; the surface is chosen from a verified API rather than a
guessed one (`UI-02`).

## Part 4 — Notifications and Control Center

**Goal:** animated notification cards and a glass control center.

Planned scope: notification geometry, urgency styles, dismiss and history animation, control-center
panel styling, and the allowlisted IPC shortcuts in `scripts/iarch-control-center.sh`. Acceptance:
no second notification daemon; DND, replacement and history behaviour verified on a live session or
left open in [UNVERIFIED.md](UNVERIFIED.md).

## Part 5 — Settings app, About page and Contact/Portfolio

**Goal:** the glass settings app, including About → Open-source licenses rendered from
`branding/notices.json`, plus the Contact/Portfolio page.

Planned scope: settings surfaces for every switch introduced in Parts 1 to 4, a Performance preset
selector, the About page, and the Contact/Portfolio page. Acceptance: the About page and
`THIRD_PARTY_NOTICES.md` come from the same JSON; every visual switch in the product is reachable
from settings; nothing in the settings UI names an upstream project.

## Part 6 — Installer safety and release readiness

**Goal:** an installer that is safe to run twice and honest about what it changed.

Planned scope: adopt `lib/iarch-common.sh` across `install.sh` and `fedora_install.sh`, replace
blanket `--noconfirm` use with reviewed confirmation (`INS-01`), narrow ownership changes
(`INS-02`), make the display-manager switch reversible and logged (`INS-03`), record every system
change in a manifest, and finish fonts and icon theming. Acceptance: a second run changes nothing;
a failed run reports exactly what it touched and where the backups are; `tools/preflight.py` runs
before any privileged step; every `INS-` item is either closed with evidence or still listed.
