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
| `cli/render_noctalia.py` | Shell `config.toml` and one palette per preset, checked against the upstream schema | shipped, tested |
| `cli/render_gtk_css.py` | The GTK 4 and GTK 3 glass overlays, from `lib/templates/*.css.j2` | shipped, tested |
| `cli/render_kvantum.py` | The Qt/Kvantum glass theme, validated against the keys `ThemeConfig.cpp` reads | shipped, tested |
| `lib/templates/` | Jinja2 templates the renderers fill from the tokens | shipped, tested |
| `cli/` | `iarch-theme`, `iarch-keybinds`, `iarch-anim`, `iarch-doctor`; the Noctalia, GTK, Qt and terminal renderers | Parts 2 and 5 |
| `settings-app/` | GTK4 + libadwaita settings application | Part 4 |

User state lives in `~/.config/iarch/`; the repository ships defaults in
`data/`. See `docs/ARCHITECTURE.md`, "User state and the single source of
truth".
