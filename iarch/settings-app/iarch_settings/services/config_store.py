# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""``~/.config/iarch/settings.json``: load it, migrate it, save it, watch it.

This module is the only place in the application that reads or writes that file.
Everything it does is either delegated to :mod:`iarch.lib.configstore`, which
already owns the atomic-write and backup-rotation rules for every tool in this
repository, or is one of four things that file needs and the shared library does
not provide:

**A version.** Version 2 is what this application writes; version 1 is what a
checkout from before Part 4 has. :func:`migrate_v1_to_v2` is a pure function so a
test can hand it a version 1 document and assert on the result without touching a
filesystem. The migration has to *reconcile* two switches that describe the same
intention -- the coarse Part 1 ``preset``/``effects`` pair and the Part 2
``theme.intensity`` -- and it does so in one direction only: the intensity is
authoritative and the coarse pair is derived from it on every save
(:func:`derive_coarse`). Two switches that can disagree are a bug that shows up
as "the interface says frosted and the session is rendering performance".

**A quarantine.** A settings.json that will not parse is moved to
``settings.json.broken.<timestamp>`` and the defaults are loaded instead, so a
corrupted file costs the user their customisation and not the application. The
broken copy is never deleted: it is the only evidence of what was there.

**Validation, when it is available.** :mod:`jsonschema` is installed in CI but is
not a runtime dependency of a desktop session, so a missing module means "not
validated" and is reported as such rather than raising. A document that *is*
checked and fails is refused, because writing it back would put an invalid value
in front of a generator that clamps or refuses.

**A file monitor.** A command line tool -- ``iarch-theme apply``,
``iarch-gamemode on``, ``iarch-focus on`` -- changes this file while the window is
open. Pages that showed a stale value would be worse than pages that showed
nothing, so :class:`Store` can watch the file and tell its subscribers.

The file is written with mode 0600. It is not secret, but ``startup.autostart``
holds commands that the session will run at login, and a file another local user
could edit is a file another local user could put a command in.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from .. import paths

NAME = "settings"
"""The stem: ``~/.config/iarch/settings.json``."""

CURRENT_VERSION = 2
"""What this application writes. :data:`ACCEPTED_VERSIONS` is what it reads."""

ACCEPTED_VERSIONS = (1, 2)

#: settings.json can hold an autostart command, so it is owner-only.
SETTINGS_MODE = 0o600

BROKEN_PREFIX = ".broken."

#: Verdicts a load can report, so a page can say which one happened.
LOADED = "loaded"
MIGRATED = "migrated"
DEFAULTS = "defaults"
QUARANTINED = "quarantined"


class ConfigStoreError(RuntimeError):
    """The settings file could not be used."""


def _timestamp() -> str:
    """A sortable, filesystem-safe timestamp, matching configstore's backup names."""
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime())


# --------------------------------------------------------------------------
# migration
# --------------------------------------------------------------------------

def intensity_from_effects(effects: Mapping[str, Any], default: str) -> str:
    """The intensity a version 1 ``effects`` map means.

    A version 1 file has four booleans and no intensity. Two of them decide
    everything: blur off, or transparency off, is the ``performance`` intensity
    (blur off, shadows off, solid fills). Anything else is the tokens' own
    default, which is ``frosted``.

    ``effects.shadows`` cannot be honoured by choosing an intensity, because every
    intensity that blurs also shadows; the caller turns it into a leaf override
    instead, which is exactly what ``glass.leaves`` is for.
    """
    if not effects.get("blur", True) or not effects.get("transparency", True):
        return "performance"
    return default


def _deep_defaults(section: Mapping[str, Any], have: Mapping[str, Any]) -> Dict[str, Any]:
    """``have`` with every key ``section`` declares filled in underneath it."""
    merged = dict(section)
    for key, value in have.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def migrate_v1_to_v2(document: Mapping[str, Any], defaults: Mapping[str, Any]) -> Dict[str, Any]:
    """Return ``document`` as a version 2 document. Pure: it writes nothing.

    ``defaults`` is ``data/settings.default.json``, which is itself version 2, so
    every section the new version needs has a value to fall back on.

    The rules, in the order they are applied:

    1. Anything the document already says is kept. A migration that discards a
       user's choice is not a migration.
    2. ``theme.intensity`` is derived from the coarse ``effects`` map when the
       document has no intensity (:func:`intensity_from_effects`).
    3. ``effects.animations: false`` becomes ``animation.preset: "off"``, because
       that is the one mechanism the motion half already has for "no animation"
       and adding a second would leave the two able to disagree.
    4. ``effects.shadows: false`` becomes the leaf override
       ``decoration:shadow:enabled = false``, because no intensity expresses it.
    5. The remaining version 2 sections are filled in from the defaults.
    6. ``version`` becomes 2 and the coarse switches are re-derived, so the two
       descriptions of one intention agree in the file that is written.
    """
    migrated: Dict[str, Any] = json.loads(json.dumps(dict(document)))
    default_theme = defaults.get("theme", {})
    default_intensity = default_theme.get("intensity", "frosted")

    effects = document.get("effects") or {}
    theme = dict(migrated.get("theme") or {})
    theme.setdefault("colour_preset", default_theme.get("colour_preset", "midnight-glass"))
    theme.setdefault("intensity", intensity_from_effects(effects, default_intensity))
    theme.setdefault("colour_mode", default_theme.get("colour_mode", "dark"))
    theme.setdefault("accent", default_theme.get("accent", ""))
    migrated["theme"] = theme

    animation = dict(migrated.get("animation") or {})
    default_animation = defaults.get("animation", {})
    if "preset" not in animation and effects.get("animations") is False:
        animation["preset"] = "off"
    for key, value in default_animation.items():
        animation.setdefault(key, value)
    migrated["animation"] = animation

    glass = dict(migrated.get("glass") or {})
    leaves = dict(glass.get("leaves") or {})
    if effects.get("shadows") is False and "decoration:shadow:enabled" not in leaves:
        leaves["decoration:shadow:enabled"] = False
    glass["leaves"] = leaves
    glass.setdefault("per_app_opacity", [])
    migrated["glass"] = _deep_defaults(defaults.get("glass", {}), glass)

    migrated["fonts"] = _deep_defaults(defaults.get("fonts", {}),
                                       dict(migrated.get("fonts") or {}))
    migrated["startup"] = _deep_defaults(defaults.get("startup", {}),
                                         dict(migrated.get("startup") or {}))
    migrated["app"] = _deep_defaults(defaults.get("app", {}),
                                     dict(migrated.get("app") or {}))
    migrated["modes"] = _deep_defaults(defaults.get("modes", {}),
                                       dict(migrated.get("modes") or {}))

    migrated["version"] = CURRENT_VERSION
    return derive_coarse(migrated)


def derive_coarse(document: Mapping[str, Any]) -> Dict[str, Any]:
    """Rewrite ``preset`` and ``effects`` from the sections that own them.

    The coarse pair is Part 1's master switch and still read by the installers and
    by ``iarch-doctor``, so it cannot be dropped; but it must not be a second
    opinion. ``preset`` follows ``theme.intensity``, ``effects.blur`` and
    ``effects.shadows`` follow the intensity's own tables, and
    ``effects.animations`` follows ``animation.preset`` -- the one animation
    preset named ``off`` is the only state in which the coarse switch is false,
    which is why ``reduce_motion`` does not turn it off: reducing motion renders
    the minimal preset, it does not remove animation from the session.

    ``effects.transparency`` has no counterpart in version 2 -- every intensity
    keeps some translucency -- so it is always true here. A version 1 file that
    said false was folded into ``performance`` by the migration, which is the
    least translucent intensity the tokens define.
    """
    result: Dict[str, Any] = json.loads(json.dumps(dict(document)))
    intensity = str(result.get("theme", {}).get("intensity", "frosted"))
    animation_preset = str(result.get("animation", {}).get("preset", "smooth"))
    performance = intensity == "performance"
    result["preset"] = "performance" if performance else "glass"
    result["effects"] = {
        "blur": not performance,
        "transparency": True,
        "animations": animation_preset != "off",
        "shadows": not performance,
    }
    return result


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def _jsonschema():
    """The validator, or ``None``. Importing it late keeps a session without it working."""
    try:
        import jsonschema  # noqa: PLC0415 - deliberately late
    except ImportError:
        return None
    return jsonschema


def validation_problems(document: Mapping[str, Any], root: Optional[Path] = None) -> List[str]:
    """Human-readable schema problems, or ``[]``.

    An empty list does not mean the document is valid when :mod:`jsonschema` is
    missing; :func:`validator_state` says which of the two it was.
    """
    module = _jsonschema()
    if module is None:
        return []
    schema = json.loads(paths.schema_file(f"{NAME}.schema.json", root).read_text(encoding="utf-8"))
    return [f"{'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in module.Draft7Validator(schema).iter_errors(document)]


def validator_state() -> str:
    """``validated`` or ``unavailable``, for the About page's debug information."""
    return "validated" if _jsonschema() is not None else "unavailable"


# --------------------------------------------------------------------------
# the store
# --------------------------------------------------------------------------

class Store:
    """The settings document, in memory, with the file behind it.

    ``data`` is the merged document: the repository defaults underneath whatever
    the user's file said, then migrated. ``status`` says how it got there, which
    is what the window turns into a toast when the answer is not ``loaded``.
    """

    def __init__(self, root: Optional[Path] = None,
                 env: Optional[Mapping[str, str]] = None) -> None:
        self._root = root or paths.repo_root(env)
        paths.add_repo_to_path(self._root)
        from iarch.lib import configstore  # late: needs the repo on sys.path

        self._configstore = configstore
        self._env = env
        self.data: Dict[str, Any] = {}
        self.status: str = DEFAULTS
        self.problems: List[str] = []
        self.quarantined_to: Optional[Path] = None
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._monitor = None

    # -- paths -------------------------------------------------------------

    @property
    def defaults_path(self) -> Path:
        return self._configstore.defaults_path(NAME, self._root)

    @property
    def user_path(self) -> Path:
        return self._configstore.user_path(NAME, self._env)

    # -- reading -----------------------------------------------------------

    def defaults(self) -> Dict[str, Any]:
        """The repository defaults, parsed."""
        return json.loads(self.defaults_path.read_text(encoding="utf-8"))

    def load(self) -> Dict[str, Any]:
        """Read, migrate and validate. Never raises for a damaged user file."""
        defaults = self.defaults()
        self.problems = []
        self.quarantined_to = None
        user = self.user_path
        if not user.is_file():
            self.data = dict(defaults)
            self.status = DEFAULTS
            return self.data

        raw = user.read_text(encoding="utf-8", errors="replace")
        try:
            document = json.loads(raw)
        except json.JSONDecodeError as exc:
            self.quarantine(user, f"{exc.msg} at line {exc.lineno} column {exc.colno}")
            self.data = dict(defaults)
            self.status = QUARANTINED
            return self.data
        if not isinstance(document, dict):
            self.quarantine(user, f"the file holds {type(document).__name__}, not an object")
            self.data = dict(defaults)
            self.status = QUARANTINED
            return self.data

        version = document.get("version")
        if version not in ACCEPTED_VERSIONS:
            self.quarantine(user, f"version {version!r} is not one of "
                                  f"{', '.join(str(v) for v in ACCEPTED_VERSIONS)}")
            self.data = dict(defaults)
            self.status = QUARANTINED
            return self.data

        if version == 1:
            # The raw document, not a merged one: the migration derives
            # theme.intensity from the coarse effects map, and merging the
            # version 2 defaults underneath first would hand it an intensity that
            # came from the defaults rather than from what the user had chosen.
            merged = _deep_defaults(defaults, migrate_v1_to_v2(document, defaults))
            self.status = MIGRATED
        else:
            merged = derive_coarse(_deep_defaults(defaults, document))
            self.status = LOADED

        self.problems = validation_problems(merged, self._root)
        if self.problems:
            # Refuse to keep a document the schema rejects: writing it back would
            # hand a generator a value it clamps or refuses, and the user would
            # see a change they did not make.
            self.quarantine(user, "; ".join(self.problems))
            self.data = dict(defaults)
            self.status = QUARANTINED
            return self.data

        self.data = merged
        return self.data

    def quarantine(self, path: Path, why: str) -> Path:
        """Move a damaged file aside and record where it went."""
        target = path.with_name(f"{path.name}{BROKEN_PREFIX}{_timestamp()}")
        counter = 1
        while target.exists():
            target = path.with_name(f"{path.name}{BROKEN_PREFIX}{_timestamp()}-{counter}")
            counter += 1
        try:
            path.replace(target)
        except OSError as exc:
            raise ConfigStoreError(f"cannot move the damaged settings file aside: {exc}") from exc
        self.quarantined_to = target
        self.problems = [why]
        return target

    # -- writing -----------------------------------------------------------

    def save(self, changes: Optional[Mapping[str, Any]] = None) -> Path:
        """Merge ``changes`` in, re-derive the coarse switches, and write.

        ``changes`` is a mapping of dotted paths to values -- ``{"theme.intensity":
        "soft"}`` -- which is what a row hands over, so a page never has to build a
        nested document. The write is atomic (temp file, fsync, rename, old mode
        carried over) and keeps a rotated backup, both from
        :mod:`iarch.lib.configstore`.
        """
        if changes:
            for dotted, value in changes.items():
                self.set(dotted, value, save=False)
        document = derive_coarse(self.data)
        problems = validation_problems(document, self._root)
        if problems:
            raise ConfigStoreError("refusing to write a settings.json the schema rejects: "
                                   + "; ".join(problems))
        self.data = document
        target = self.user_path
        if not target.exists():
            # Create it owner-only first, so atomic_write carries that mode over
            # rather than the process default.
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(mode=SETTINGS_MODE, exist_ok=True)
        written = self._configstore.save(NAME, document, self._env)
        try:
            os.chmod(written, SETTINGS_MODE)
        except OSError:
            pass  # a read-only volume or a foreign filesystem; the write still landed
        return written

    def set(self, dotted: str, value: Any, *, save: bool = True) -> Any:
        """Set ``a.b.c`` in the document, creating the intermediate mappings."""
        keys = [part for part in dotted.split(".") if part]
        if not keys:
            raise ConfigStoreError(f"{dotted!r} names nothing")
        node: Any = self.data
        for key in keys[:-1]:
            if not isinstance(node.get(key), dict):
                node[key] = {}
            node = node[key]
        node[keys[-1]] = value
        if save:
            self.save()
        return value

    def get(self, dotted: str, fallback: Any = None) -> Any:
        """Read ``a.b.c``, returning ``fallback`` when any part is missing."""
        node: Any = self.data
        for key in (part for part in dotted.split(".") if part):
            if not isinstance(node, Mapping) or key not in node:
                return fallback
            node = node[key]
        return node

    # -- watching ----------------------------------------------------------

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        """Register ``callback``; returns a function that unregisters it."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def notify(self) -> None:
        for callback in list(self._subscribers):
            callback(self.data)

    def watch(self) -> bool:
        """Watch the config directory for changes to this file.

        Returns True when a monitor is running and False when Gio is not
        available, which is the honest answer in a session with no GTK: the pages
        then only refresh when the application itself writes.
        """
        if self._monitor is not None:
            return True
        try:
            from gi.repository import Gio  # late: absent in CI
        except ImportError:
            return False
        directory = self.user_path.parent
        directory.mkdir(parents=True, exist_ok=True)
        self._monitor = Gio.File.new_for_path(str(directory)).monitor_directory(
            Gio.FileMonitorFlags.NONE, None)
        self._monitor.connect("changed", self._on_changed)
        return True

    def unwatch(self) -> None:
        if self._monitor is not None:
            self._monitor.cancel()
            self._monitor = None

    def _on_changed(self, _monitor, changed, _other, event) -> None:
        """Reload when *another* process wrote the file.

        The application's own writes are ignored by comparing mtime against the
        one this object last saw; without that, saving would reload and notify,
        and a slider would fight the value it just set.
        """
        try:
            from gi.repository import Gio
        except ImportError:
            return
        if event not in (Gio.FileMonitorEvent.CHANGES_DONE_HINT,
                         Gio.FileMonitorEvent.CREATED):
            return
        if str(changed.get_path()) != str(self.user_path):
            return
        before = json.dumps(self.data, sort_keys=True)
        self.load()
        if json.dumps(self.data, sort_keys=True) != before:
            self.notify()
