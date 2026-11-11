# iarch/ — the product's own code

Everything this project authors lives under this directory, named with the
`iarch` prefix (see `docs/BRANDING.md`, "Identifiers for new components").

| Path | Purpose | Status |
| :--- | :--- | :--- |
| `lib/configstore.py` | The single source of truth for user state: defaults merge, atomic writes, GENERATED headers, five-backup rotation | shipped, tested |
| `lib/renderers.py` | The generator contract, plus `is_generated` | shipped, tested |
| `cli/contrast_check.py` | WCAG gate over every preset's palette | shipped, tested |
| `cli/gen_wallpapers.py` | Seeded 4K WebP renders of the generated presets | shipped, tested |
| `cli/gen_glass_lua.py` | Hyprland decoration, layer and window rules from the tokens | shipped, tested |
| `cli/gen_animations_lua.py` | Hyprland curves and animation leaves from the motion tokens, validated against the animation tree | shipped, tested |
| `cli/render_noctalia.py` | Shell `config.toml` and one palette per preset, checked against the upstream schema | shipped, tested |
| `cli/render_gtk_css.py` | The GTK 4 and GTK 3 glass overlays, from `lib/templates/*.css.j2` | shipped, tested |
| `cli/render_kvantum.py` | The Qt/Kvantum glass theme, validated against the keys `ThemeConfig.cpp` reads | shipped, tested |
| `cli/gen_fontconfig.py` | The fontconfig file applying the font tokens, validated against the config DTD | shipped, tested |
| `cli/theme.py` | `iarch-theme`: applies one preset across every surface at once — contrast gate first, all-or-nothing render, verified reload | shipped, tested |
| `cli/iarch_anim.py` | `iarch-anim`: switches the motion preset, speed, reduce-motion and per-event overrides, verifies against the compositor and rolls back a rejection | shipped, tested |
| `cli/iarch_doctor.py` | `iarch-doctor`: asks a running session whether the settings took — notification probes and Do Not Disturb today, the rest of the session in Part 5 | shipped, tested |
| `lib/templates/` | Jinja2 templates the renderers fill from the tokens | shipped, tested |
| `cli/` | `iarch-keybinds`, and the rest of `iarch-doctor` | Part 5 |
| `settings-app/` | GTK4 + libadwaita settings application | Part 4 |

User state lives in `~/.config/iarch/`; the repository ships defaults in
`data/`. See `docs/ARCHITECTURE.md`, "User state and the single source of
truth".
