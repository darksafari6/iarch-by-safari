# Lossless sources of the desktop showcase art

The WebP files one directory up are what README and the docs display. The PNGs
here are the lossless captures they were made from, kept so the art can be
re-rendered at another size or quality without a second screenshot session.

| Source | Rendition | Command that produced it |
| :--- | :--- | :--- |
| `desktop-red.png` (3460x1947, RGBA) | `../desktop-red.webp` (209 KB) | see below |
| `desktop-tokyo-night.png` (1920x1080, RGB) | `../desktop-tokyo-night.webp` (94 KB) | see below |

```sh
python3 -m venv /tmp/imgvenv && /tmp/imgvenv/bin/pip install pillow
/tmp/imgvenv/bin/python - <<'PY'
from PIL import Image
for name in ("desktop-red", "desktop-tokyo-night"):
    Image.open(f"assets/wallpapers/originals/{name}.png").save(
        f"assets/wallpapers/{name}.webp", "WEBP", quality=85, method=6, exact=True)
PY
```

Neither image is wider than the 3840 px ceiling, so no rescaling happens; if a
future capture is larger, resize with `Image.LANCZOS` to 3840 px wide first.
`exact=True` keeps the alpha channel of `desktop-red.png` lossless (verified:
maximum alpha difference 0, mean per-pixel colour difference under 1.2 of 255).

## Why not Git LFS

Git LFS was considered and rejected: it is not installed in the environment this
repository is maintained from, it needs a storage quota and a client on every
machine that clones, and these two files are documentation art that nothing at
runtime reads. Keeping them as plain files means a fresh clone works with no
extra tooling. If this directory grows past a few megabytes, revisit that.

Nothing in `.config/`, `install.sh` or `fedora_install.sh` deploys these images;
the session's wallpaper is chosen by the user in Noctalia settings.
