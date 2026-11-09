#!/usr/bin/env python3
"""Single source of truth for iArch by Safari product naming.

The values live in ``branding/product.env`` so that shell scripts and Python
tools cannot drift apart. Nothing here invents names: every value is read from
that file.

Usage as a library::

    from iarch_brand import product, repo_root
    product()["IARCH_PRODUCT_NAME"]   # -> "iArch by Safari"

Usage as a script (prints the resolved values, exits nonzero if invalid)::

    python3 tools/iarch_brand.py --print
    python3 tools/iarch_brand.py --check
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict

REQUIRED_KEYS = (
    "IARCH_PRODUCT_NAME",
    "IARCH_PRODUCT_SHORT",
    "IARCH_PRODUCT_ID",
    "IARCH_MAINTAINER",
    "IARCH_REPO_URL",
    "IARCH_LICENSE_ID",
    "IARCH_LICENSE_FILE",
    "IARCH_NOTICES_SOURCE",
    "IARCH_NOTICES_FILE",
    "IARCH_PALETTE_ID",
    "IARCH_PALETTE_NAME",
    "IARCH_PROFILE_DEFAULT",
    "IARCH_PROFILE_PERFORMANCE",
    "IARCH_PROFILE_DIR",
    "IARCH_SHELL_CONFIG_DIR",
    "IARCH_HYPRLAND_ENTRY",
)

_ASSIGNMENT = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"\s*(?:#.*)?$')
_REPO_ROOT = Path(__file__).resolve().parent.parent


def repo_root() -> Path:
    """Absolute path of the repository checkout."""
    return _REPO_ROOT


def product_env_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "branding" / "product.env"


def parse_env(text: str) -> Dict[str, str]:
    """Parse the ``KEY="value"`` lines of product.env.

    Comments and blank lines are ignored. Unquoted values are rejected so that
    a malformed edit fails loudly instead of silently changing the product name.
    """
    values: Dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ASSIGNMENT.match(raw)
        if not match:
            raise ValueError(f"product.env line {lineno} is not KEY=\"value\": {raw!r}")
        key, value = match.group(1), match.group(2)
        if key in values:
            raise ValueError(f"product.env line {lineno} redefines {key}")
        values[key] = value
    return values


def product(root: Path | None = None) -> Dict[str, str]:
    """Return the product naming table."""
    return parse_env(product_env_path(root).read_text(encoding="utf-8"))


def check(root: Path | None = None) -> list[str]:
    """Return a list of human-readable problems; empty means healthy."""
    problems: list[str] = []
    path = product_env_path(root)
    if not path.is_file():
        return [f"missing {path}"]
    try:
        values = parse_env(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [str(exc)]

    for key in REQUIRED_KEYS:
        if not values.get(key):
            problems.append(f"{key} is missing or empty")

    ids = {
        "IARCH_PRODUCT_ID": values.get("IARCH_PRODUCT_ID", ""),
        "IARCH_PALETTE_ID": values.get("IARCH_PALETTE_ID", ""),
    }
    for key, value in ids.items():
        if value and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
            problems.append(f"{key} must be lowercase and path-safe, got {value!r}")

    root_path = root or repo_root()
    license_file = values.get("IARCH_LICENSE_FILE", "")
    if license_file and not (root_path / license_file).is_file():
        problems.append(f"{license_file} referenced by IARCH_LICENSE_FILE does not exist")
    notices_source = values.get("IARCH_NOTICES_SOURCE", "")
    if notices_source and not (root_path / notices_source).is_file():
        problems.append(f"{notices_source} referenced by IARCH_NOTICES_SOURCE does not exist")
    palette_id = values.get("IARCH_PALETTE_ID", "")
    shell_dir = values.get("IARCH_SHELL_CONFIG_DIR", "")
    if palette_id and shell_dir:
        palette = root_path / ".config" / shell_dir / "palettes" / f"{palette_id}.json"
        if not palette.is_file():
            problems.append(f"palette file for IARCH_PALETTE_ID does not exist: {palette}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--print", action="store_true", help="print resolved values")
    group.add_argument("--check", action="store_true", help="validate product.env and referenced files")
    args = parser.parse_args(argv)

    if args.check:
        problems = check()
        if problems:
            for problem in problems:
                print(f"branding: {problem}", file=sys.stderr)
            return 1
        print("branding: product.env is consistent")
        return 0

    values = product()
    for key in sorted(values):
        print(f"{key}={values[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
