# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Where this application reads from and writes to.

Three roots matter, and keeping them apart is what stops the application from
writing into the checkout it was started from:

* the **repository root**, which holds ``data/`` (defaults, schemas, licenses,
  the design records) and ``iarch/cli/`` (the generators this app calls);
* the **user config root**, ``~/.config/iarch/``, owned by
  :mod:`iarch.lib.configstore` and honouring ``IARCH_CONFIG_DIR``;
* the **user state root**, ``~/.local/state/iarch/``, where the backups the
  restore page lists already live.

Like every other tool in this repository, this one is run from a checkout --
``python3 -m iarch_settings`` or the ``iarch-settings`` launcher beside it -- and
is not installed as a system binary yet. That is Part 6's work, so a checkout
that cannot be found is an error that says so rather than a silent fallback to
somebody's home directory.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Optional

PACKAGE_DIR = Path(__file__).resolve().parent
APP_DIR = PACKAGE_DIR.parent
"""``iarch/settings-app/``: the application's own root, holding pyproject.toml."""

_MARKER = Path("branding") / "product.env"
"""The file that only exists at a repository root, used to find one."""


class PathError(RuntimeError):
    """A root the application needs could not be resolved."""


def repo_root(env: Optional[Mapping[str, str]] = None) -> Path:
    """The repository checkout this application was started from.

    ``IARCH_REPO_ROOT`` wins, because a test harness points the application at a
    temporary checkout and a packager will point it at an installed copy of
    ``data/``. Otherwise the marker file is walked for upwards from this module,
    which is how ``iarch/cli/theme.py`` and ``tools/iarch_brand.py`` find it too.
    """
    env = os.environ if env is None else env
    override = env.get("IARCH_REPO_ROOT")
    if override:
        root = Path(override)
        if not root.is_absolute():
            raise PathError(f"IARCH_REPO_ROOT must be absolute: {override!r}")
        if not (root / _MARKER).is_file():
            raise PathError(
                f"IARCH_REPO_ROOT={override} is not a repository checkout: "
                f"{root / _MARKER} is missing")
        return root
    for candidate in [PACKAGE_DIR, *PACKAGE_DIR.parents]:
        if (candidate / _MARKER).is_file():
            return candidate
    raise PathError(
        "Cannot find the iArch by Safari checkout this application was started "
        f"from: no {_MARKER} at or above {PACKAGE_DIR}. Run it from a checkout, "
        "or set IARCH_REPO_ROOT. Installing the application outside a checkout is "
        "Part 6 of the roadmap and is not wired yet.")


def add_repo_to_path(root: Optional[Path] = None) -> Path:
    """Make ``iarch.lib`` and ``tools`` importable, and return the root used.

    The application calls the repository's generators in-process -- the same way
    ``iarch/cli/iarch_gamemode.py`` calls its siblings -- so the checkout has to
    be importable. Inserted at the front, because a system-installed copy of this
    package must not shadow the checkout that is actually being edited.
    """
    resolved = root or repo_root()
    for entry in (str(resolved), str(resolved / "tools"), str(APP_DIR)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return resolved


def data_file(name: str, root: Optional[Path] = None) -> Path:
    """A read-only repository data file: ``data_file("licenses.json")``."""
    path = (root or repo_root()) / "data" / name
    if not path.is_file():
        raise PathError(f"Repository data file is missing: {path}")
    return path


def design_file(name: str, root: Optional[Path] = None) -> Path:
    """A read-only design record: ``design_file("adwaita.json")``."""
    return data_file(f"design/{name}", root)


def schema_file(name: str, root: Optional[Path] = None) -> Path:
    """A JSON Schema under ``data/schemas/``."""
    return data_file(f"schemas/{name}", root)


def app_data_file(name: str) -> Path:
    """A file shipped inside the application itself, not in ``data/``."""
    path = APP_DIR / "data" / name
    if not path.is_file():
        raise PathError(f"Application data file is missing: {path}")
    return path


def style_file(name: str = "glass.css") -> Path:
    """The application's own CSS, which extends the Part 2 sheets."""
    path = PACKAGE_DIR / "style" / name
    if not path.is_file():
        raise PathError(f"Application stylesheet is missing: {path}")
    return path


def cli_module_path(tool: str) -> Path:
    """The path of one of the repository's command line tools."""
    path = repo_root() / "iarch" / "cli" / f"{tool}.py"
    if not path.is_file():
        raise PathError(f"Repository tool is missing: {path}")
    return path


def config_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """``~/.config/iarch/``, delegated so tests use one override for both.

    Each of these three adds the checkout to ``sys.path`` itself rather than asking
    the caller to: they are read by :func:`iarch_settings.version.debug_info`, which
    runs while the About dialog is being built, and a path helper that raises
    ``ModuleNotFoundError`` from inside a dialog is a much worse failure than the
    import it was trying to reach. :func:`add_repo_to_path` is idempotent and cheap.
    """
    add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415 - imported late: it needs the path

    return configstore.config_dir(env)


def state_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """``~/.local/state/iarch/``."""
    add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415

    return configstore.state_dir(env)


def backup_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """``~/.local/state/iarch/backups/``, which the restore page lists."""
    add_repo_to_path()
    from iarch.lib import configstore  # noqa: PLC0415

    return configstore.backup_dir(env)
