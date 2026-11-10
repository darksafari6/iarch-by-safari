# iarch/cli — command line tools

Generators that are shipped and tested today. Each one reads the design tokens or
a preset, renders a configuration file, and can verify what it previously wrote:

| Command | Renders | Checks |
| :--- | :--- | :--- |
| `python3 iarch/cli/contrast_check.py` | nothing — it gates | that every preset clears 4.5:1 for text and 3:1 for non-text UI |
| `python3 iarch/cli/gen_wallpapers.py` | `assets/wallpapers/generated/*.webp` | that the shipped art is 4K, WebP, inside 600 KB and rendered by some preset |
| `python3 iarch/cli/gen_glass_lua.py` | `~/.config/hypr/generated/glass.lua` | that the committed default matches a fresh render of the tokens |

Every generator exits 0 on success, 1 when the repository or the host is out of
step, and 2 on a usage or data error, and none of them starts a desktop, edits a
file it did not generate, or shells out.

The commands still to come are `iarch-theme`, `iarch-keybinds`, `iarch-anim` and
`iarch-doctor`. Each one reads user state through `iarch.lib.configstore` and
writes only generated files, under the contract in `iarch/lib/renderers.py`.

Nothing here may be renamed to an older product name; the conventions live in
`branding/product.env`.
