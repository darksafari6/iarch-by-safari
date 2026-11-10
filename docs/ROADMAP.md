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
| CI renamed and extended | `.github/workflows/iarch-checks.yml` | workflow run |

License data was verified against upstream on 2026-11-09; the verification method is recorded in
`THIRD_PARTY_NOTICES.md` and the open items in [UNVERIFIED.md](UNVERIFIED.md).

**Explicitly not done in Part 1:** no installer behaviour was changed. `install.sh` still runs
`pacman -S --noconfirm`, `pacman -Syu --noconfirm` and `yay -S --noconfirm` for an AUR greeter
package, and still switches the display manager. Those are `INS-01` to `INS-03` and belong to
Part 6, where they can be changed with tests around them.

## Part 2 — Glass surfaces and motion

**Goal:** the compositor-side glass: blur, borders, rounding, shadows and the open/close/hover
animation set, all switchable.

Planned scope: Hyprland window and layer rules for shell surfaces, animation curves and durations
in `.config/hypr/animations.lua`, per-surface opacity, and a Performance preset that reduces or
disables each effect. Acceptance: every effect has a named switch; the Performance preset measurably
lowers work (record the measurement or leave `PERF-01` open); no effect is applied to a surface
whose rule could not be verified against the compositor release in use.

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
