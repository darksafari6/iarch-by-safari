#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Apply or revert an effect preset over a Noctalia v5 profile, backup first.

The overlay in profiles/<name>.toml may only change values of keys that already
exist in the base profile; anything else is refused before a single byte is
written. Writes go through iarch.lib.configstore so they are atomic and the
previous file is kept in the five-backup rotation.

Usage:
    python3 tools/profile_preset.py apply performance --config PATH
    python3 tools/profile_preset.py revert --config PATH
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any, Dict, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import by design)


class PresetError(RuntimeError):
    """Raised when an overlay or target is not safe to apply."""


def overlay_paths(name: str) -> Path:
    path = ROOT / "profiles" / f"{name}.toml"
    if not path.is_file():
        raise PresetError(f"Unknown preset {name!r}; see profiles/")
    return path


def flatten(model: Dict[str, Any], prefix: Tuple[str, ...] = ()) -> Dict[Tuple[str, ...], Any]:
    flat: Dict[Tuple[str, ...], Any] = {}
    for key, value in model.items():
        path = prefix + (key,)
        if isinstance(value, dict):
            flat.update(flatten(value, path))
        else:
            flat[path] = value
    return flat


def load_overlay(name: str) -> Dict[Tuple[str, ...], Any]:
    return flatten(tomllib.loads(overlay_paths(name).read_text(encoding="utf-8")))


def validate(overlay: Dict[Tuple[str, ...], Any], base: Dict[Tuple[str, ...], Any]) -> None:
    for path, value in overlay.items():
        if path not in base:
            raise PresetError(f"overlay invents a key the base profile does not have: {'.'.join(path)}")
        if type(base[path]) is not type(value):
            raise PresetError(
                f"overlay changes the type of {'.'.join(path)}: "
                f"{type(base[path]).__name__} -> {type(value).__name__}"
            )


def toml_literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(value)


def apply_text(text: str, overlay: Dict[Tuple[str, ...], Any]) -> str:
    table: Tuple[str, ...] = ()
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            table = tuple(stripped[1:-1].split("."))
            out.append(line)
            continue
        match = None
        if not stripped.startswith("#"):
            import re

            match = re.match(r"^(\s*)([A-Za-z0-9_-]+)(\s*=\s*)(.*)$", line)
        if match:
            path = table + (match.group(2),)
            if path in overlay:
                line = f"{match.group(1)}{match.group(2)}{match.group(3)}{toml_literal(overlay[path])}"
        out.append(line)
    return "\n".join(out) + "\n"


def apply(name: str, config: Path, env=None) -> Path:
    base_model = tomllib.loads(config.read_text(encoding="utf-8"))
    overlay = load_overlay(name)
    validate(overlay, flatten(base_model))
    rendered = apply_text(config.read_text(encoding="utf-8"), overlay)
    expected = flatten(base_model) | overlay
    if flatten(tomllib.loads(rendered)) != expected:
        raise PresetError("rendered profile does not match the intended model; nothing written")
    configstore.backup_of(config, env)
    configstore.atomic_write(config, rendered, validate_json=False)
    return config


def revert(config: Path, env=None) -> Path:
    directory = configstore.backup_dir(env)
    stamp_name = str(config).strip("/").replace("/", "_")
    candidates = sorted(
        (p for p in directory.glob(f"{stamp_name}.*.bak") if p.is_file()), key=lambda p: p.name
    )
    if not candidates:
        raise PresetError(f"no backup of {config} in {directory}; nothing to revert")
    configstore.atomic_write(config, candidates[-1].read_text(encoding="utf-8"), validate_json=False)
    return candidates[-1]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    apply_cmd = sub.add_parser("apply")
    apply_cmd.add_argument("preset")
    apply_cmd.add_argument("--config", required=True, type=Path)
    revert_cmd = sub.add_parser("revert")
    revert_cmd.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "apply":
            target = apply(args.preset, args.config)
            print(f"applied {args.preset} to {target} (previous copy backed up)")
        else:
            source = revert(args.config)
            print(f"restored {args.config} from {source}")
    except (PresetError, configstore.ConfigError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
