# iarch/ — the product's own code

Everything this project authors lives under this directory, named with the
`iarch` prefix (see `docs/BRANDING.md`, "Identifiers for new components").

| Path | Purpose | Status |
| :--- | :--- | :--- |
| `lib/configstore.py` | The single source of truth for user state: defaults merge, atomic writes, GENERATED headers, five-backup rotation | shipped, tested |
| `lib/renderers.py` | Home of the generators (Hyprland Lua, Noctalia overrides, shortcut overlay) | contract shipped, renderers land in Parts 2 and 5 |
| `cli/` | `iarch-theme`, `iarch-keybinds`, `iarch-anim`, `iarch-doctor` | Parts 2 and 5 |
| `settings-app/` | GTK4 + libadwaita settings application | Part 4 |

User state lives in `~/.config/iarch/`; the repository ships defaults in
`data/`. See `docs/ARCHITECTURE.md`, "User state and the single source of
truth".
