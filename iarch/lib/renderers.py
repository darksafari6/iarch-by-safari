# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The contract every generator obeys, and helpers for checking it.

The generators themselves are the ``iarch/cli/gen_*.py`` commands -- wallpapers,
Hyprland glass rules, and the shell, terminal and toolkit renderers that follow.
They live as commands so each one can be run, diffed and ``--check``ed on its
own, and ``iarch-theme`` imports their render functions rather than shelling out.
Parts 2 and 5 add the remaining renderers (Noctalia overrides, the shortcut
overlay). Every renderer must obey the contract in docs/ARCHITECTURE.md:

* read user state only through :mod:`iarch.lib.configstore`;
* emit through :func:`iarch.lib.configstore.write_generated`, which stamps the
  GENERATED header, backs the previous file up and renames atomically;
* never edit a file that does not carry the GENERATED header.
"""
from __future__ import annotations

from pathlib import Path

from iarch.lib import configstore


def is_generated(path: Path) -> bool:
    """True when ``path`` starts with the iArch GENERATED header."""
    try:
        first = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except (OSError, IndexError):
        return False
    return first.startswith(configstore.GENERATED_HEADER) or first.startswith('{"_generated": ')
