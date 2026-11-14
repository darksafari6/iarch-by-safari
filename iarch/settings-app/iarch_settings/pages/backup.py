# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The Backup & Restore page: what a change takes with it, and how to put it back.

Every change this application makes goes through one pipeline, and the pipeline's second
step is a restore point for every file the change will touch. That is not a courtesy: step
seven restores all of them if any step failed, and a change that could not be undone would
be a change this application had no business offering -- a monitor rule that leaves a display
unreadable, a theme render that writes eleven files, a font change that writes two.

So this page is mostly an explanation with one control on it. The explanation is the seven
steps in the order they run, because the order is the safety: validate before writing, back
up before writing, and verify after reloading. The control is a restore, and it is a
dropdown plus a confirmation rather than a button per backup, because a plan row carries one
value and a restore is a decision about which one.

Backups are rotated five per file, by :mod:`iarch.lib.configstore`, with a sortable
timestamp, a nanosecond and a pid in the name so two backups taken inside the same clock
second still sort correctly and cannot collide. Five is a limit worth stating on the page:
a person who assumes every change kept a copy forever will assume wrongly, and the sixth
change back is the one that is gone.

:func:`iarch_settings.services.config_store.restore` refuses four things before it writes
anything, and each refusal is a sentence this page can show: the path has to be a file inside
the backup directory, its name has to carry this settings file's prefix, it has to parse as
JSON with a version this application reads, and the file it replaces is copied aside first so
that restoring the wrong backup is itself reversible. The prefix rule exists because a backup
name is a *flattened* path and flattening cannot be inverted -- an underscore that was a
directory separator and an underscore that was in a name are the same character afterwards --
so the destination is computed and never parsed out of a file name.

What this page does not offer is a restore of anything but this project's own settings file.
The generated payloads -- the compositor's Lua, the GTK sheets, the Kvantum theme, the
shell's config.toml -- are backed up by the same pipeline and restored by the same step
seven, but they are all *rendered*: putting an old one back without re-rendering would leave
a file that disagrees with the settings that produced it, and the honest recovery is to
re-apply the theme. That is what the row says.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .. import paths
from ..services import apply, config_store, runner
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "backup"


# --------------------------------------------------------------------- readers


def backups() -> List[Any]:
    """This settings file's backups, newest first."""
    return config_store.backups()


def backup_choices() -> List[Tuple[str, str]]:
    """The backups a person may choose from, newest first.

    The value is the file name and the label is the same name with the flattened path prefix
    stripped, because the prefix is this file's own path with the separators replaced and it
    is the part of the name that carries no information a person needs twice.
    """
    prefix = config_store.backup_prefix()
    choices: List[Tuple[str, str]] = []
    for path in backups():
        label = path.name[len(prefix):] if path.name.startswith(prefix) else path.name
        choices.append((path.name, label))
    return choices


def backup_count_text() -> Optional[str]:
    """How many restore points there are, and what the limit is."""
    found = backups()
    if not found:
        return None
    return (f"{len(found)} restore point{'s' if len(found) != 1 else ''}, newest first; "
            f"the shared library keeps {config_store.BACKUP_LIMIT} per file and removes the "
            f"oldest when a sixth is taken")


def no_backup_text() -> str:
    """Why there is nothing to restore yet."""
    return ("no change has been applied from this machine yet, so there is no restore point: "
            "the pipeline takes one for every file a change will touch, and only a file that "
            "already existed has something to restore")


def directory_text() -> str:
    """Where the backups live."""
    return str(paths.backup_dir())


def steps_text() -> str:
    """The seven steps, in the order they run, as one answer."""
    return "\n".join(f"{index}. {name.replace('_', ' ')}"
                     for index, name in enumerate(apply.STEPS, start=1))


def steps_why_text() -> str:
    """Why the order is the safety, rather than a list of names."""
    return ("validate before writing, back up before writing, and verify after reloading: "
            "the order is what makes a failure recoverable, since a step that ran before the "
            "backup could not be undone and a verify that ran before the reload would be "
            "reading the state the change had not reached yet")


def settings_path_text() -> str:
    """The file this page restores."""
    return str(config_store.user_path())


def defaults_text() -> str:
    """The defaults that sit under the user's file."""
    return str(config_store.defaults_path())


def store_status_text() -> str:
    """How the settings file loaded: the user's, the defaults, migrated or quarantined."""
    try:
        store = config_store.Store()
        store.load()
    except (config_store.ConfigStoreError, OSError) as exc:
        return f"the settings file could not be loaded: {exc}"
    return (f"{store.status}: " + {
        config_store.LOADED: "your file, merged over the repository defaults",
        config_store.MIGRATED: "a version 1 file was migrated to version 2 on the way in",
        config_store.DEFAULTS: "no file of yours yet, so the repository defaults are what "
                               "every page shows",
        config_store.QUARANTINED: "your file did not parse, so it was moved aside as "
                                  ".broken.<timestamp> and the defaults were loaded -- the "
                                  "broken copy is never deleted, because it is the only "
                                  "evidence of what was there",
    }.get(store.status, "an unrecognised load status"))


def validator_text() -> str:
    """Whether the schema could be used to check the document."""
    return config_store.validator_state()


def mode_text() -> str:
    """Why the settings file is owner-only."""
    return (f"written with mode {config_store.SETTINGS_MODE:o}: it is not secret, but "
            f"startup.autostart holds commands the session will run at login, and a file "
            f"another local user could edit is a file another local user could put a command "
            f"in")


def payloads_text() -> str:
    """Why the generated files are not restorable from here."""
    return ("the compositor's Lua, the GTK sheets, the Kvantum theme and the shell's "
            "config.toml are backed up by the same pipeline and restored by the same failing "
            "step, but they are all rendered: putting an old one back without re-rendering "
            "would leave a file that disagrees with the settings that produced it, so the "
            "recovery is to re-apply the theme rather than to restore a payload")


def header_text() -> str:
    """Which generated files carry the header that says do not edit them."""
    return ("a generated body carries a header line for "
            + ", ".join(apply.HEADER_REQUIRED_SUFFIXES)
            + "; the two settings.ini files and the autostart entries do not, because those "
              "are the user's own and every key this project does not write is kept")


# ------------------------------------------------------------------- the action


def restore_choice(name: Any) -> Tuple[bool, str]:
    """Put the chosen backup back over the settings file.

    A dropdown's action rather than a button's, because a plan row carries one value and the
    value here is which backup. The answer is the service's own sentence, so the toast says
    what was refused and why rather than that something went wrong.
    """
    text = str(name or "").strip()
    if not text:
        return False, "no backup was chosen, so nothing was restored"
    directory = paths.backup_dir()
    return config_store.restore(directory / text)


def restore_count_text() -> str:
    """How many backups there are to choose from, for the restore row's subtitle."""
    found = backups()
    if not found:
        return no_backup_text()
    return (f"{len(found)} to choose from; restoring one copies the current file aside first, "
            f"so the restore is itself reversible")


# ------------------------------------------------------------------ the plan


def restore_row() -> Row:
    """Either the restore control or the reason there is not one.

    Decided at draw time rather than shipped as a dropdown that may be empty, and the reason
    is the same one the Default apps page gives: a dropdown with nothing behind it is a
    control that lies. With no backup on this machine the honest row is a sentence saying so,
    and with one the honest row is the list of them.
    """
    if backups():
        return Row("combo", "Put a backup back", choices_source="backup.backup_choices",
                   action="backup.restore_choice", icon="document-save-as-symbolic",
                   risky=True, confirm="Restore this backup over your settings?",
                   confirm_body="The file you have now is copied aside first, so this can be "
                                "undone. Every page reads the restored document, and the look "
                                "of the session does not change until a theme is applied "
                                "again.",
                   subtitle="The newest first. A backup that does not parse, or that is not a "
                            "version this application reads, is refused rather than restored",
                   keywords=("restore", "backup", "undo", "revert", "settings"))
    return Row("state", "Nothing to restore yet", source="backup.no_backup_text",
               icon="document-save-as-symbolic",
               subtitle="A restore point appears the first time a change is applied from this "
                        "machine",
               keywords=("restore", "backup", "none", "empty", "undo"))


def build(context: Context) -> PagePlan:
    """The Backup & Restore page, as data."""
    spec = registry_page(PAGE_ID)

    restore = Group(
        "Restore",
        restore_row(),
        Row("state", "How many there are", icon="document-save-symbolic",
            source="backup.restore_count_text", keywords=("backups", "count", "restore")),
        Row("state", "Restore points", icon="document-save-symbolic",
            source="backup.backup_count_text",
            subtitle="Five per file is a limit, not a promise: the sixth change back is the "
                     "one that is gone",
            keywords=("backups", "rotation", "five", "limit", "restore points")),
        Row("state", "Where they live", icon="folder-open-symbolic",
            source="backup.directory_text",
            subtitle="A sortable timestamp, a nanosecond and a pid, so two backups taken "
                     "inside one clock second still sort correctly and cannot collide",
            keywords=("backup directory", "state", "path", "timestamp")),
        description="Only this project's own settings file is restored from here, and the "
                    "refusals are checked before anything is written.",
        style_classes=("iarch-glass-card",),
    )

    pipeline = Group(
        "What a change does",
        Row("state", "The seven steps", icon="view-refresh-symbolic",
            source="backup.steps_text",
            subtitle="In the order they run, for every change on every page",
            keywords=("steps", "pipeline", "validate", "backup", "write", "commands",
                      "reload", "verify")),
        Row("state", "Why that order", icon="dialog-information-symbolic",
            source="backup.steps_why_text", keywords=("order", "safety", "why", "pipeline")),
        Row("state", "The generated payloads", icon="dialog-warning-symbolic",
            source="backup.payloads_text",
            subtitle="Backed up and restored by the same pipeline, and not offered here",
            keywords=("payloads", "generated", "lua", "gtk.css", "kvantum", "re-render")),
        Row("state", "Which files carry the header", icon="accessories-text-editor-symbolic",
            source="backup.header_text",
            subtitle="A generated file says so on its first line; a user-owned one does not",
            keywords=("header", "generated", "do not edit", "settings.ini")),
        description="A change that could not be undone would be a change this application "
                    "had no business offering.",
    )

    state = Group(
        "The file itself",
        Row("state", "Your settings", icon="document-save-symbolic",
            source="backup.settings_path_text", keywords=("settings.json", "path", "user")),
        Row("state", "The defaults under it", icon="document-save-symbolic",
            source="backup.defaults_text",
            subtitle="Merged under your file, so a key you never set still has the "
                     "repository's answer",
            keywords=("defaults", "merge", "data", "repository")),
        Row("state", "How it loaded", icon="view-refresh-symbolic",
            source="backup.store_status_text",
            keywords=("status", "loaded", "migrated", "quarantined", "defaults")),
        Row("state", "Was it validated?", icon="object-select-symbolic",
            source="backup.validator_text",
            subtitle="jsonschema is installed in CI and is not a runtime dependency of a "
                     "desktop session, so a missing module means not validated and is "
                     "reported as such rather than raising",
            keywords=("jsonschema", "validation", "schema", "unavailable")),
        Row("state", "Why it is owner-only", icon="system-lock-screen-symbolic",
            source="backup.mode_text", keywords=("0600", "mode", "permissions", "security")),
        description="What the pages read, where it comes from, and how sure this application "
                    "is of it right now.",
    )

    return PagePlan(
        PAGE_ID, spec.label, restore, pipeline, state,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("A restore replaces ~/.config/iarch/settings.json. The look of the session "
                   "does not change until a theme is applied again, because the generated "
                   "files are rendered from the settings and are not restored with them.",
                   kind="warning", icon="dialog-warning-symbolic"),
        ),
        header_actions=(
            Row("state", "How it loaded", icon="document-save-symbolic",
                source="backup.store_status_text", keywords=("status", "settings")),
        ),
    )
