#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Render and apply the six iArch session themes from data/themes/<id>.json.

The selected id is stored only in ~/.config/iarch/theme.json. This module owns
runtime projections; theme packs remain the only place a theme value is defined.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iarch.lib import configstore, modes  # noqa: E402

THEMES_DIR = ROOT / "data" / "themes"
INDEX_PATH = THEMES_DIR / "ids.json"
SCHEMA_PATH = THEMES_DIR / "schema.json"
CONFIG_TIMEOUT = 12


class SessionThemeError(RuntimeError):
    """A theme pack, user choice or runtime projection is invalid."""


def _warn(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _display(path: Path) -> str:
    try:
        return "~/" + path.relative_to(configstore.home_dir()).as_posix()
    except ValueError:
        return str(path)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionThemeError(f"{path}: {exc}") from exc


def theme_ids() -> List[str]:
    index = _read_json(INDEX_PATH)
    themes = index.get("themes") if isinstance(index, dict) else None
    if not isinstance(themes, list):
        raise SessionThemeError(f"{INDEX_PATH}: themes must be an array")
    ids = [item.get("id") for item in themes if isinstance(item, dict)]
    expected = ["greenhouse", "amber-bloom", "neon-rain", "forest-night", "violet-glass", "crimson-silk"]
    if ids != expected:
        raise SessionThemeError(f"{INDEX_PATH}: expected exactly {', '.join(expected)} in that order")
    return ids


def default_theme_id() -> str:
    index = _read_json(INDEX_PATH)
    wanted = index.get("default") if isinstance(index, dict) else None
    if wanted not in theme_ids():
        raise SessionThemeError(f"{INDEX_PATH}: default must name one of the six theme ids")
    return wanted


def validate_pack(pack: Dict[str, Any], wanted: str, path: Path) -> None:
    if not isinstance(pack, dict) or not isinstance(pack.get("meta"), dict):
        raise SessionThemeError(f"{path}: missing meta object")
    if pack["meta"].get("id") != wanted:
        raise SessionThemeError(f"{path}: meta.id is {pack['meta'].get('id')!r}, expected {wanted!r}")
    # Use the repository schema when jsonschema is present. A small structural
    # fallback keeps the renderer usable on a minimal Python installation.
    try:
        import jsonschema  # type: ignore
    except ImportError:
        jsonschema = None
    if jsonschema is not None:
        schema = _read_json(SCHEMA_PATH)
        try:
            jsonschema.validate(instance=pack, schema=schema)
        except Exception as exc:
            raise SessionThemeError(f"{path}: schema validation failed: {exc}") from exc
    required = ("wallpaper", "hypr", "motion", "noctalia", "gtk", "terminal", "starship", "sound", "overview")
    missing = [key for key in required if key not in pack]
    if missing:
        raise SessionThemeError(f"{path}: missing required section(s): {', '.join(missing)}")
    if pack["wallpaper"] != f"assets/wallpapers/themes/{wanted}.webp":
        raise SessionThemeError(f"{path}: wallpaper must be assets/wallpapers/themes/{wanted}.webp")
    if pack["sound"].get("notify") != f"assets/sounds/{wanted}/notify.ogg":
        raise SessionThemeError(f"{path}: sound.notify must be assets/sounds/{wanted}/notify.ogg")
    if not isinstance(pack["meta"].get("dark"), bool):
        raise SessionThemeError(f"{path}: meta.dark must be a boolean")


def load_theme(theme_id: str) -> Dict[str, Any]:
    if theme_id not in theme_ids():
        raise SessionThemeError(f"unknown theme {theme_id!r}; available: {', '.join(theme_ids())}")
    path = THEMES_DIR / f"{theme_id}.json"
    pack = _read_json(path)
    validate_pack(pack, theme_id, path)
    return pack


def choice_path(env: Optional[Mapping[str, str]] = None) -> Path:
    return configstore.config_dir(env) / "theme.json"


def current_theme_id(env: Optional[Mapping[str, str]] = None) -> Tuple[str, bool]:
    path = choice_path(env)
    if not path.exists():
        return default_theme_id(), False
    choice = _read_json(path)
    wanted = choice.get("id") if isinstance(choice, dict) else None
    if not isinstance(wanted, str) or wanted not in theme_ids():
        raise SessionThemeError(f"{path}: expected {{'id': '<one of the six theme ids>'}}")
    return wanted, True


def _hex_rgba(value: str, alpha: Optional[float] = None) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?", value):
        raise SessionThemeError(f"invalid colour {value!r}")
    raw = value[1:]
    red, green, blue = (int(raw[i:i + 2], 16) for i in (0, 2, 4))
    chosen = alpha if alpha is not None else (int(raw[6:8], 16) / 255 if len(raw) == 8 else 1.0)
    return f"rgba({red}, {green}, {blue}, {chosen:.3f})"


def _n(value: Any) -> str:
    return str(round(float(value), 4))


def _animation(leaf: str, enabled: bool, ms: int, curve: str, style: Optional[str] = None) -> str:
    if not enabled or ms <= 0:
        return f'hl.animation({{ leaf = "{leaf}", enabled = false }})'
    fields = [f'leaf = "{leaf}"', "enabled = true", f"speed = {_n(ms / 100)}", f'bezier = "{curve}"']
    if style:
        fields.append(f'style = "{style}"')
    return "hl.animation({ " + ", ".join(fields) + " })"


def _mode_active(env: Mapping[str, str], name: str) -> bool:
    return bool(modes.mode_state(dict(env), name).get("active"))


def _focus_values() -> Tuple[bool, float]:
    tokens = _read_json(ROOT / "data" / "design" / "tokens.json")
    focus = tokens.get("modes", {}).get("focus", {})
    return bool(focus.get("dim_inactive", True)), float(focus.get("dim_strength", 0.5))


def _sync_focus_restore_target(pack: Dict[str, Any], env: Mapping[str, str]) -> None:
    """When a theme changes during focus mode, make focus-off restore this theme."""
    settings = configstore.load("settings", ROOT, dict(env))
    modes_block = settings.setdefault("modes", {})
    focus = modes_block.get("focus")
    if not isinstance(focus, dict) or not focus.get("active"):
        return
    previous = focus.get("previous")
    if not isinstance(previous, dict):
        previous = {}
    leaves = previous.get("leaves")
    if not isinstance(leaves, dict):
        leaves = {}
    leaves["decoration:dim_inactive"] = bool(pack["hypr"]["dim_strength"] > 0)
    leaves["decoration:dim_strength"] = float(pack["hypr"]["dim_strength"])
    previous["leaves"] = leaves
    focus["previous"] = previous
    modes_block["focus"] = focus
    settings["modes"] = modes_block
    configstore.save("settings", settings, dict(env))


def render_hypr_theme(pack: Dict[str, Any], game_mode: bool = False,
                      focus_mode: bool = False) -> str:
    meta, hypr, motion = pack["meta"], pack["hypr"], pack["motion"]
    blur = hypr["blur"]
    focus_dim, focus_strength = _focus_values()
    dim_inactive = focus_dim if focus_mode else (hypr["dim_strength"] > 0 and not game_mode)
    dim_strength = focus_strength if focus_mode else (0.0 if game_mode else hypr["dim_strength"])
    inactive_opacity = 1.0 if game_mode else hypr["inactive_opacity"]
    blur_enabled = bool(blur["enabled"]) and not game_mode
    shadow_enabled = hypr["shadow_range"] > 0 and not game_mode
    curve = motion["bezier"]["name"]
    controls = motion["bezier"]["controls"]
    x1, y1, x2, y2 = controls
    lines = [
        f"-- Theme: {meta['name']} ({meta['id']})",
        "-- Generated from data/themes/<id>.json. Do not edit this file.",
        "hl.config({",
        "    general = {",
        f"        gaps_in = {hypr['gaps_in']},",
        f"        gaps_out = {hypr['gaps_out']},",
        f"        border_size = {hypr['border_size']},",
        "        col = {",
        f'            active_border = {{ colors = {{ "{_hex_rgba(hypr["active_border"])}", "{_hex_rgba(hypr["active_border"], 0.62)}" }}, angle = 135 }},',
        f'            inactive_border = "{_hex_rgba(hypr["inactive_border"], 0.28)}",',
        "        },",
        "    },",
        "    decoration = {",
        f"        rounding = {hypr['rounding']},",
        f"        inactive_opacity = {_n(inactive_opacity)},",
        "        active_opacity = 1.0,",
        "        fullscreen_opacity = 1.0,",
        f"        dim_inactive = {str(dim_inactive).lower()},",
        f"        dim_strength = {_n(dim_strength)},",
        "        blur = {",
        f"            enabled = {str(blur_enabled).lower()},",
        f"            size = {blur['size']},",
        f"            passes = {blur['passes']},",
        f"            noise = {_n(blur['noise'])},",
        f"            contrast = {_n(blur['contrast'])},",
        "            variant = \"kawase\",",
        "            ignore_opacity = true,",
        "            new_optimizations = true,",
        "            xray = false,",
        "            special = true,",
        "        },",
        "        shadow = {",
        f"            enabled = {str(shadow_enabled).lower()},",
        f"            range = {0 if game_mode else hypr['shadow_range']},",
        "            render_power = 2,",
        f'            color = "{_hex_rgba(hypr["shadow_color"], 0.42)}",',
        f'            color_inactive = "{_hex_rgba(hypr["shadow_color"], 0.24)}",',
        "            offset = { 0, 6 },",
        "            scale = 1.0,",
        "        },",
        "    },",
        "})",
        "",
        f'hl.curve("{curve}", {{ type = "bezier", points = {{{{ {_n(x1)}, {_n(y1)} }}, {{ {_n(x2)}, {_n(y2)} }}}} }})',
    ]
    windows = motion["windows"]
    workspace = motion["workspace"]
    fade = motion["fade"]
    border = motion["border"]
    layer = motion["layer"]
    if game_mode:
        lines.append("hl.config({ animations = { enabled = false } })")
    lines.extend([
        _animation("windows", not game_mode, max(windows["open_ms"], windows["close_ms"], windows["move_ms"]), curve, windows["style"]),
        _animation("windowsIn", not game_mode, windows["open_ms"], curve, windows["style"]),
        _animation("windowsOut", not game_mode, windows["close_ms"], curve, windows["style"]),
        _animation("windowsMove", not game_mode, windows["move_ms"], curve, windows["style"]),
    ])
    workspace_style = {"horizontal": "slide", "vertical": "slidevert", "none": "fade"}[workspace["direction"]]
    lines.append(_animation("workspaces", not game_mode and workspace["direction"] != "none", workspace["duration_ms"], curve, workspace_style))
    lines.append(_animation("specialWorkspace", not game_mode and workspace["direction"] != "none", workspace["duration_ms"], curve, workspace_style))
    for leaf in ("fade", "fadeIn", "fadeOut", "fadeSwitch", "fadeShadow", "fadeDim", "fadeLayers"):
        lines.append(_animation(leaf, fade["enabled"] and not game_mode, fade["duration_ms"], curve))
    lines.append(_animation("border", border["enabled"] and not game_mode, border["duration_ms"], curve))
    lines.append(_animation("layers", not game_mode, layer["bar_ms"], curve, layer["style"]))
    lines.append(_animation("layersIn", not game_mode, layer["bar_ms"], curve, layer["style"]))
    lines.append(_animation("layersOut", not game_mode, layer["osd_ms"], curve, layer["style"]))
    # The overview token is deliberately data-only until the shipped shell has
    # a real overview styling API. It does not spawn a second window manager.
    lines.extend([
        "",
        f"-- Overview token: {pack['overview']['style']}; rounding={pack['overview']['rounding']};",
        f"-- gap={pack['overview']['gap']}; dim_inactive={str(pack['overview']['dim_inactive']).lower()}",
    ])
    return "\n".join(lines) + "\n"


def _palette_mode(pack: Dict[str, Any], light: bool = False) -> Dict[str, Any]:
    p = pack["noctalia"]["palette"]
    t = pack["terminal"]
    if light:
        surface, surface_variant, text, background = "#F7F4EF", "#EEE7DF", "#211A18", "#F7F4EF"
    else:
        surface, surface_variant, text, background = p["surface"], p["dock"], p["text"], p["background"]
    return {
        "mPrimary": p["primary"], "mOnPrimary": p["on_primary"],
        "mSecondary": p["secondary"], "mOnSecondary": p["on_secondary"],
        "mTertiary": p["dock"], "mOnTertiary": p["text"],
        "mError": p["error"], "mOnError": p["on_error"],
        "mSurface": surface, "mOnSurface": text,
        "mSurfaceVariant": surface_variant, "mOnSurfaceVariant": text,
        "mOutline": p["outline"], "mShadow": background,
        "mHover": p["notification"], "mOnHover": text,
        "terminal": {
            "background": t["background"] if not light else "#F7F4EF",
            "foreground": t["foreground"] if not light else "#211A18",
            "cursor": t["cursor"], "cursorText": t["background"],
            "selectionBg": t["selection_background"],
            "selectionFg": t["selection_foreground"],
            "normal": {
                "black": t["color0"], "red": t["color1"], "green": t["color2"], "yellow": t["color3"],
                "blue": t["color4"], "magenta": t["color5"], "cyan": t["color6"], "white": t["color7"]
            },
            "bright": {
                "black": t["color8"], "red": t["color9"], "green": t["color10"], "yellow": t["color11"],
                "blue": t["color12"], "magenta": t["color13"], "cyan": t["color14"], "white": t["color15"]
            }
        }
    }


def render_noctalia_palette(pack: Dict[str, Any]) -> str:
    return json.dumps({"dark": _palette_mode(pack), "light": _palette_mode(pack, light=True)},
                      indent=2, ensure_ascii=False) + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise SessionThemeError(f"cannot render TOML value {value!r}")


def _set_toml(text: str, section: str, key: str, value: Any) -> str:
    headers = list(re.finditer(r"(?m)^\[([^\]]+)\]\s*$", text))
    for index, header in enumerate(headers):
        if header.group(1) != section:
            continue
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        block = text[header.end():end]
        pattern = re.compile(rf"(?m)^(\s*{re.escape(key)}\s*=\s*).*$")
        updated, count = pattern.subn(lambda m: m.group(1) + _toml_value(value), block, count=1)
        if count != 1:
            raise SessionThemeError(f"Noctalia config is missing [{section}].{key}; refusing to invent a shell key")
        return text[:header.end()] + updated + text[end:]
    raise SessionThemeError(f"Noctalia config is missing [{section}] section")


def render_noctalia_config(existing: str, pack: Dict[str, Any],
                            game_mode: bool = False) -> str:
    layout = pack["noctalia"]["layout"]
    sound = pack["sound"]
    radius_scale = round(layout["corner_radius"] / 16, 2)
    motion_speed = round(max(0.1, min(4.0, 220 / max(1, pack["motion"]["layer"]["osd_ms"]))), 2)
    values = [
        ("theme", "mode", "dark" if pack["meta"]["dark"] else "light"),
        ("theme", "shell_mode", "dark" if pack["meta"]["dark"] else "light"),
        ("theme", "custom_palette", "iarch-active"),
        ("shell", "corner_radius_scale", radius_scale),
        ("shell.animation", "enabled", not game_mode),
        ("shell.animation", "speed", motion_speed),
        ("bar.default", "position", layout["bar_position"]),
        ("bar.default", "start", layout["module_order"]["start"]),
        ("bar.default", "center", layout["module_order"]["center"]),
        ("bar.default", "end", layout["module_order"]["end"]),
        ("bar.default", "background_opacity", pack["noctalia"]["surface_alpha"]),
        ("dock", "enabled", layout["dock_visible"]),
        ("dock", "background_opacity", pack["noctalia"]["surface_alpha"]),
        ("control_center", "sidebar", layout["control_center_density"]),
        ("notification", "position", layout["notification_position"]),
        ("notification", "width", layout["notification_width"]),
        ("notification", "background_opacity", pack["noctalia"]["surface_alpha"]),
        ("audio", "enable_notification_sounds", True),
        ("audio", "sound_volume", sound["volume"]),
    ]
    result = re.sub(
        r"(?m)^# Source:.*$",
        "# Source: data/themes/" + pack["meta"]["id"] + ".json; generated by tools/render_theme.py.",
        existing,
        count=1,
    )
    for section, key, value in values:
        result = _set_toml(result, section, key, value)
    return result


def render_kitty_theme(pack: Dict[str, Any]) -> str:
    t = pack["terminal"]
    rows = [
        f"foreground {t['foreground']}",
        f"background {t['background']}",
        f"cursor {t['cursor']}",
        f"selection_foreground {t['selection_foreground']}",
        f"selection_background {t['selection_background']}",
    ]
    rows.extend(f"color{i} {t[f'color{i}']}" for i in range(16))
    return "\n".join(rows) + "\n"


def render_starship_config(existing: str, pack: Dict[str, Any]) -> str:
    start, end = "# BEGIN iArch session palette", "# END iArch session palette"
    clean = re.sub(rf"(?ms)^{re.escape(start)}\n.*?^{re.escape(end)}\n?", "", existing)
    palette = pack["starship"]["palette"]
    palette_line = re.compile(r"(?m)^palette\s*=.*$")
    if palette_line.search(clean):
        clean = palette_line.sub(f"palette = {json.dumps(palette)}", clean, count=1)
    else:
        schema_line = re.search(r"(?m)^\s*['\"]?\$schema['\"]?\s*=.*$", clean)
        if schema_line:
            clean = clean[:schema_line.end()] + f"\npalette = {json.dumps(palette)}" + clean[schema_line.end():]
        else:
            clean = f"palette = {json.dumps(palette)}\n" + clean
    t = pack["terminal"]
    names = ("black", "red", "green", "yellow", "blue", "purple", "cyan", "white",
             "bright-black", "bright-red", "bright-green", "bright-yellow", "bright-blue",
             "bright-purple", "bright-cyan", "bright-white")
    entries = "\n".join(f'{name} = "{t[f"color{i}"]}"' for i, name in enumerate(names))
    block = f"\n{start}\n[palettes.{palette}]\n{entries}\n{end}\n"
    return clean.rstrip() + "\n" + block


def _css_theme_block(pack: Dict[str, Any]) -> str:
    g = pack["gtk"]
    text = pack["noctalia"]["palette"]["text"]
    outline = pack["noctalia"]["palette"]["outline"]
    return f"""/* BEGIN iArch session theme: {pack['meta']['id']} */
.suggested-action,
button.suggested-action {{
  background-color: {g['accent']};
  color: {text};
  border-color: {outline};
}}
.destructive-action,
button.destructive-action {{
  background-color: {g['destructive']};
  color: {text};
}}
window.background {{
  background-color: alpha({g['window_bg']}, 0.90);
  color: {text};
}}
headerbar,
.titlebar {{
  background-color: alpha({g['headerbar']}, 0.94);
  color: {text};
  border-bottom-color: {g['accent']};
}}
/* END iArch session theme */
"""


def render_gtk_css(existing: str, pack: Dict[str, Any]) -> str:
    block = _css_theme_block(pack)
    pattern = re.compile(r"(?ms)^/\* BEGIN iArch session theme: .*?^/\* END iArch session theme \*/\s*")
    if pattern.search(existing):
        return pattern.sub(block, existing).rstrip() + "\n"
    return existing.rstrip() + "\n\n" + block


def render_kvantum_config(existing: str, pack: Dict[str, Any]) -> str:
    p, g = pack["noctalia"]["palette"], pack["gtk"]
    replacement = {
        "alt.base.color": p["bar"], "base.color": p["surface"],
        "button.color": p["bar"], "button.text.color": p["text"],
        "highlight.color": g["accent"], "highlight.text.color": p["on_primary"],
        "inactive.alt.base.color": p["bar"], "inactive.base.color": p["surface"],
        "inactive.highlight.color": g["accent"], "inactive.highlight.text.color": p["on_primary"],
        "inactive.text.color": p["text"], "inactive.window.color": g["window_bg"],
        "inactive.window.text.color": p["text"], "link.color": p["secondary"],
        "link.visited.color": g["accent"], "shadow.color": pack["hypr"]["shadow_color"],
        "text.color": p["text"], "tooltip.base.color": p["notification"],
        "tooltip.text.color": p["text"], "window.color": g["window_bg"],
        "window.text.color": p["text"],
    }
    lines = existing.splitlines()
    in_colors = False
    changed = set()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_colors = stripped == "[GeneralColors]"
            continue
        if in_colors and "=" in line and not stripped.startswith(";"):
            key = line.split("=", 1)[0].strip()
            if key in replacement:
                lines[i] = f"{key}={replacement[key]}"
                changed.add(key)
    missing = sorted(set(replacement) - changed)
    if missing:
        raise SessionThemeError("Kvantum [GeneralColors] is missing expected colour keys: " + ", ".join(missing))
    return "\n".join(lines) + "\n"


def _with_generated_header(path: Path, body: str) -> str:
    if path.suffix == ".json":
        return json.dumps({"_generated": configstore.GENERATED_HEADER, **json.loads(body)},
                          indent=2, ensure_ascii=False) + "\n"
    return f"{configstore.header_for(path)}\n{body.rstrip()}\n"


def _strip_generated_header(text: str) -> str:
    lines = text.splitlines()
    if lines and configstore.is_header_line(lines[0]):
        return "\n".join(lines[1:]).lstrip("\n") + "\n"
    return text


def _snapshot(path: Path) -> Tuple[str, Optional[bytes], Optional[str]]:
    if path.is_symlink():
        return "symlink", None, os.readlink(path)
    if path.is_file():
        return "file", path.read_bytes(), None
    return "missing", None, None


def _restore(path: Path, snapshot: Tuple[str, Optional[bytes], Optional[str]]) -> None:
    kind, data, link = snapshot
    if kind == "missing":
        path.unlink(missing_ok=True)
    elif kind == "symlink" and link is not None:
        path.unlink(missing_ok=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(link)
    elif data is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.restore-{os.getpid()}")
        tmp.write_bytes(data)
        os.replace(tmp, path)


def _write_preserving(path: Path, text: str, env: Mapping[str, str]) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    if path.is_file() or path.is_symlink():
        configstore.backup_of(path, env)
    configstore.atomic_write(path, text, validate_json=False)


def _write_generated_if_changed(path: Path, body: str, env: Mapping[str, str]) -> bool:
    rendered = _with_generated_header(path, body)
    if path.is_file() and not path.is_symlink():
        try:
            if path.read_text(encoding="utf-8") == rendered:
                return False
        except (OSError, UnicodeDecodeError):
            pass
    configstore.write_generated(path, body, env)
    return True


def _ensure_kitty_include(path: Path, env: Mapping[str, str]) -> Optional[str]:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*include\s+theme\.conf\s*$", text):
        return text
    changed = text.rstrip() + "\n\n# iArch session theme colours\ninclude theme.conf\n"
    return changed


def _noctalia_config_path(config_home: Path) -> Path:
    return config_home / "noctalia" / "config.toml"


def _build_actions(pack: Dict[str, Any], config_home: Path,
                   env: Mapping[str, str],
                   game_mode_override: Optional[bool] = None) -> List[Tuple[str, Path, str]]:
    actions: List[Tuple[str, Path, str]] = []
    game_mode = (_mode_active(env, "game") if game_mode_override is None
                 else bool(game_mode_override))
    focus_mode = _mode_active(env, "focus")
    hypr = config_home / "hypr" / "generated" / "theme.lua"
    actions.append(("generated", hypr, render_hypr_theme(pack, game_mode, focus_mode)))

    palette = config_home / "noctalia" / "palettes" / "iarch-active.json"
    actions.append(("generated", palette, render_noctalia_palette(pack)))

    noctalia_config = _noctalia_config_path(config_home)
    if noctalia_config.is_file():
        existing = noctalia_config.read_text(encoding="utf-8")
        updated = render_noctalia_config(existing, pack, game_mode)
        actions.append(("generated-existing", noctalia_config, _strip_generated_header(updated)))
    else:
        _warn(f"{_display(noctalia_config)} is absent; palette will be generated but Noctalia selection/layout cannot be changed")

    kitty_dir = config_home / "kitty"
    actions.append(("generated", kitty_dir / "theme.conf", render_kitty_theme(pack)))
    kitty_config = kitty_dir / "kitty.conf"
    included = _ensure_kitty_include(kitty_config, env)
    if included is not None:
        actions.append(("preserving", kitty_config, included))
    else:
        _warn(f"{_display(kitty_config)} is absent; the generated theme.conf will not be included")

    starship = config_home / "starship.toml"
    if starship.is_file():
        actions.append(("preserving", starship, render_starship_config(starship.read_text(encoding="utf-8"), pack)))
    else:
        _warn(f"{_display(starship)} is absent; Starship palette was not attached")

    for version in ("3.0", "4.0"):
        css = config_home / f"gtk-{version}" / "gtk.css"
        if css.is_file():
            actions.append(("preserving", css, render_gtk_css(css.read_text(encoding="utf-8"), pack)))
        else:
            _warn(f"{_display(css)} is absent; shipped GTK glass sheet was left untouched")

    kvantum = config_home / "Kvantum" / "iarch" / "iarch.kvconfig"
    if kvantum.is_file():
        actions.append(("preserving", kvantum, render_kvantum_config(kvantum.read_text(encoding="utf-8"), pack)))
    else:
        _warn(f"{_display(kvantum)} is absent; Kvantum accent was not changed")

    return actions


def _apply_actions(actions: Sequence[Tuple[str, Path, str]], env: Mapping[str, str]) -> Tuple[List[Path], Dict[Path, Tuple[str, Optional[bytes], Optional[str]]]]:
    snapshots: Dict[Path, Tuple[str, Optional[bytes], Optional[str]]] = {}
    changed: List[Path] = []
    try:
        for kind, path, body in actions:
            snapshots.setdefault(path, _snapshot(path))
            if kind == "generated":
                if _write_generated_if_changed(path, body, env):
                    changed.append(path)
            elif kind == "generated-existing":
                _write_generated_if_changed(path, body, env)
                if snapshots[path][0] != "file" or snapshots[path][1] != path.read_bytes():
                    changed.append(path)
            elif kind == "preserving":
                before = path.read_bytes() if path.is_file() else None
                _write_preserving(path, body, env)
                after = path.read_bytes() if path.is_file() else None
                if before != after:
                    changed.append(path)
            else:
                raise SessionThemeError(f"unknown write action {kind!r}")
    except BaseException:
        for path, old in reversed(list(snapshots.items())):
            try:
                _restore(path, old)
            except OSError:
                pass
        raise
    return changed, snapshots


def _write_choice(path: Path, theme_id: str, env: Mapping[str, str]) -> Tuple[str, Optional[bytes], Optional[str]]:
    old = _snapshot(path)
    if old[0] == "file":
        try:
            if json.loads((old[1] or b"{}").decode("utf-8")).get("id") == theme_id:
                return old
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        configstore.backup_of(path, env)
    configstore.atomic_write(path, json.dumps({"id": theme_id}, indent=2) + "\n")
    return old


def _run(command: Sequence[str], *, timeout: int = CONFIG_TIMEOUT) -> bool:
    if not shutil.which(command[0]):
        _warn(f"{command[0]} is not on PATH; skipped {' '.join(command)}")
        return False
    try:
        result = subprocess.run(list(command), check=False, timeout=timeout,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        _warn(f"{' '.join(command)} failed: {exc}")
        return False
    if result.returncode != 0:
        _warn(f"{' '.join(command)} returned exit status {result.returncode}")
        return False
    print(f"reloaded: {' '.join(command)}")
    return True


def _reload_noctalia() -> bool:
    if _run(("noctalia", "msg", "config-reload")):
        return True
    # Noctalia's own launcher is the process entry point recorded in startup.lua.
    # Restart only that shell process; never restart Hyprland or the user session.
    noctalia = shutil.which("noctalia")
    pgrep = shutil.which("pgrep")
    kill = shutil.which("kill")
    if not noctalia or not pgrep:
        _warn("Noctalia IPC is unavailable and a shell-only restart could not be resolved from PATH")
        return False
    try:
        probe = subprocess.run([pgrep, "-x", "noctalia"], capture_output=True, text=True,
                               timeout=3, check=False)
        pids = [value for value in probe.stdout.split() if value.isdigit()]
        if not pids:
            _warn("No running noctalia process was found; not starting a second shell")
            return False
        for pid in pids:
            subprocess.run([kill or "kill", "-TERM", pid], check=False, timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.6)
        subprocess.Popen([noctalia], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        print("restarted: Noctalia shell only")
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        _warn(f"Noctalia shell-only restart failed: {exc}")
        return False


def _apply_sound_link(pack: Dict[str, Any], env: Mapping[str, str]) -> List[Path]:
    sound_root = configstore.config_dir(env) / "sounds"
    sound_root.mkdir(parents=True, exist_ok=True)
    linked: List[Path] = []
    for field, filename in (("notify", "active-notify.ogg"),
                            ("urgent", "active-urgent.ogg")):
        relative = pack["sound"].get(field)
        link = sound_root / filename
        if not relative:
            if link.is_symlink():
                link.unlink()
            continue
        target = ROOT / relative
        if not target.is_file():
            _warn(f"{relative} is not in the repository; leaving {_display(link)} unchanged")
            continue
        if link.exists() and not link.is_symlink():
            _warn(f"{_display(link)} is a regular file; refusing to replace it with a symlink")
            continue
        if link.is_symlink() and link.resolve() == target.resolve():
            linked.append(link)
            continue
        temporary = link.with_name(f".{link.name}.new-{os.getpid()}")
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(target.resolve())
        os.replace(temporary, link)
        linked.append(link)
    return linked


def _apply_wallpaper(pack: Dict[str, Any]) -> None:
    wallpaper = ROOT / pack["wallpaper"]
    if not wallpaper.is_file():
        _warn(f"{pack['wallpaper']} is not in the repository; wallpaper was not changed")
        return
    _run(("noctalia", "msg", "wallpaper-set", str(wallpaper.resolve())))


def render_active(config_home: Path, env: Mapping[str, str],
                  game_mode_override: Optional[bool] = None) -> List[Path]:
    theme_id, _saved = current_theme_id(env)
    pack = load_theme(theme_id)
    actions = _build_actions(pack, config_home, env, game_mode_override)
    sound_paths = [configstore.config_dir(env) / "sounds" / name
                   for name in ("active-notify.ogg", "active-urgent.ogg")]
    sound_snapshots = {path: _snapshot(path) for path in sound_paths}
    settings_path = configstore.user_path("settings", env)
    settings_snapshot = _snapshot(settings_path)
    snapshots: Dict[Path, Tuple[str, Optional[bytes], Optional[str]]] = {}
    try:
        changed, snapshots = _apply_actions(actions, env)
        _sync_focus_restore_target(pack, env)
        _apply_sound_link(pack, env)
    except BaseException:
        for path, snapshot in reversed(list(snapshots.items())):
            try:
                _restore(path, snapshot)
            except OSError:
                pass
        for path, snapshot in [*sound_snapshots.items(), (settings_path, settings_snapshot)]:
            try:
                _restore(path, snapshot)
            except OSError:
                pass
        raise
    return changed


def reload_active_surfaces(pack: Dict[str, Any], config_home: Path,
                            env: Mapping[str, str]) -> None:
    _run(("hyprctl", "reload"))
    _reload_noctalia()
    if _mode_active(env, "focus"):
        # A shell-only fallback restart does not preserve runtime DND, so restore
        # the recorded focus mode explicitly after the shell has reloaded.
        _run(("noctalia", "msg", "notification-dnd-set", "on"))
    _apply_wallpaper(pack)
    socket = os.environ.get("KITTY_LISTEN_ON")
    kitty = shutil.which("kitty")
    theme_conf = config_home / "kitty" / "theme.conf"
    if socket and kitty and theme_conf.is_file():
        _run((kitty, "@", "--to", socket, "set-colors", "--all", str(theme_conf)))
    elif socket:
        _warn("KITTY_LISTEN_ON is set but kitty or the generated theme.conf is unavailable")
    else:
        print("kitty: no KITTY_LISTEN_ON socket; existing windows were not changed")


def apply_theme(theme_id: str, config_home: Path, env: Mapping[str, str],
                no_reload: bool = False, dry_run: bool = False) -> int:
    pack = load_theme(theme_id)
    state = choice_path(env)
    actions = _build_actions(pack, config_home, env)
    if dry_run:
        print(f"iArch theme dry run: {theme_id}")
        print(f"  choice: {_display(state)}")
        for _kind, path, _body in actions:
            print(f"  render: {_display(path)}")
        print("  reload: skipped (dry run); no files changed")
        return 0

    old_choice = _write_choice(state, theme_id, env)
    sound_paths = [configstore.config_dir(env) / "sounds" / name
                   for name in ("active-notify.ogg", "active-urgent.ogg")]
    old_sounds = {path: _snapshot(path) for path in sound_paths}
    settings_path = configstore.user_path("settings", env)
    old_settings = _snapshot(settings_path)
    snapshots: Dict[Path, Tuple[str, Optional[bytes], Optional[str]]] = {}
    try:
        changed, snapshots = _apply_actions(actions, env)
        _sync_focus_restore_target(pack, env)
        # Sound is optional until each original OGG asset is included. A missing
        # sound never invalidates or changes the user's saved visual theme.
        sound_links = _apply_sound_link(pack, env)
    except BaseException:
        for path, snapshot in reversed(list(snapshots.items())):
            try:
                _restore(path, snapshot)
            except OSError:
                pass
        for path, snapshot in [*old_sounds.items(), (settings_path, old_settings),
                               (state, old_choice)]:
            try:
                _restore(path, snapshot)
            except OSError:
                pass
        raise

    print(f"theme: applied {pack['meta']['name']} ({theme_id})")
    print(f"choice: {_display(state)}")
    for path in changed:
        print(f"  wrote: {_display(path)}")
    for sound_link in sound_links:
        print(f"  sound: {_display(sound_link)}")
    if not no_reload:
        reload_active_surfaces(pack, config_home, env)
    else:
        print("reload: skipped (--no-reload)")
    print("audio: no playback command was run")
    return 0


def cmd_list(_args: argparse.Namespace, _env: Mapping[str, str]) -> int:
    for theme_id in theme_ids():
        pack = load_theme(theme_id)
        print(f"{theme_id:14} {pack['meta']['name']} — {pack['meta']['blurb']}")
    return 0


def cmd_current(_args: argparse.Namespace, env: Mapping[str, str]) -> int:
    theme_id, saved = current_theme_id(env)
    pack = load_theme(theme_id)
    status = "saved choice" if saved else "repository default"
    print(f"iArch by Safari — current theme: {pack['meta']['name']} ({theme_id}) [{status}]")
    print(f"choice file: {_display(choice_path(env))}")
    # Preserve useful read-only context for people who still use the older
    # intensity/motion settings controls. It is informational, never a source of
    # truth for the session theme pack.
    legacy = configstore.user_path("settings", env)
    legacy_choice = None
    if legacy.is_file():
        try:
            value = json.loads(legacy.read_text(encoding="utf-8"))
            legacy_choice = value.get("theme", {}) if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            legacy_choice = None
    old_colour = legacy_choice.get("colour_preset") if isinstance(legacy_choice, dict) else None
    old_intensity = legacy_choice.get("intensity") if isinstance(legacy_choice, dict) else None
    print(f"legacy compatibility: colour preset {old_colour or 'midnight-glass'}"
          + ("" if old_colour else " (repository default)")
          + f", intensity {old_intensity or 'frosted'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iarch-theme", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list the six session theme packs").set_defaults(func=cmd_list)
    current = sub.add_parser("current", help="show the active session theme")
    current.set_defaults(func=cmd_current)
    apply = sub.add_parser("apply", help="save a theme choice, render and reload the session")
    apply.add_argument("theme_id", choices=theme_ids())
    apply.add_argument("--config-home", default=os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    apply.add_argument("--no-reload", action="store_true")
    apply.add_argument("--dry-run", action="store_true")
    apply.set_defaults(func="apply")
    render = sub.add_parser("render", help="render the saved theme choice without reloading")
    render.add_argument("--config-home", default=os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    render.set_defaults(func="render")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    env = os.environ
    try:
        if args.command == "apply":
            config_home = Path(args.config_home).expanduser()
            if not config_home.is_absolute():
                raise SessionThemeError("--config-home must be an absolute path")
            return apply_theme(args.theme_id, config_home, env, args.no_reload, args.dry_run)
        if args.command == "render":
            config_home = Path(args.config_home).expanduser()
            if not config_home.is_absolute():
                raise SessionThemeError("--config-home must be an absolute path")
            paths = render_active(config_home, env)
            print(f"rendered saved theme: {len(paths)} file(s) changed")
            return 0
        return args.func(args, env)
    except (SessionThemeError, configstore.ConfigError, OSError, subprocess.SubprocessError) as exc:
        print(f"iarch-theme: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
