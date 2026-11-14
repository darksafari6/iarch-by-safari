#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the settings document: migration, merge order, backups and quarantine.

``data/schemas/settings.schema.json:25`` makes one promise in so many words: *version 2 is
what this project writes; version 1 is accepted as input*, and the migration that upgrades
one "lives in … config_store.py as migrate_v1_to_v2, and tests/test_settings_config_store.py
proves a version 1 document comes out of it as a version 2 document that validates." That
sentence is the reason this file exists, and the strongest form of it is the one that runs
the validator rather than eyeballing the keys -- so the migration's output is validated
against the schema itself, and the test says so out loud when the validator is not
installed rather than passing quietly.

Why version 1 has to be accepted at all: a ``settings.json`` written before the settings
application existed has no ``glass``, ``fonts``, ``startup`` or ``app`` section, and
``load`` merges the defaults *underneath* it, so refusing a version 1 document would refuse
every existing install. The migration's rules are ordered, and the order is the semantics:

1. anything the document already says is kept -- a migration that discards a user's choice
   is not a migration;
2. ``theme.intensity`` is derived from the coarse ``effects`` map when there is none;
3. ``effects.animations: false`` becomes ``animation.preset: "off"``, because that is the
   one mechanism the motion half already has for "no animation" and a second would leave
   the two able to disagree;
4. ``effects.shadows: false`` becomes the leaf override ``decoration:shadow:enabled``,
   because no intensity expresses it;
5. the remaining sections are filled from the defaults;
6. ``version`` becomes 2 and the coarse switches are re-derived, so the two descriptions of
   one intention agree in the file that is actually written.

Three further properties are load-bearing and easy to lose. The merge order -- defaults
under the user file -- means a mode or a page the user chose survives a defaults change.
A backup's file name cannot be inverted, because a path separator becomes an underscore, so
``restore`` recognises a backup by its prefix and refuses anything outside the backup
directory. And a document that will not parse is quarantined with a reason rather than
replaced, because the alternative is a settings application that deletes what it cannot
read.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch.lib import configstore as shared_store  # noqa: E402
from iarch_settings.services import config_store  # noqa: E402

SCHEMA_PATH = ROOT / "data" / "schemas" / "settings.schema.json"
DEFAULTS = json.loads((ROOT / "data" / "settings.default.json").read_text(encoding="utf-8"))

# A version 1 document of the shape this project actually shipped -- the one the Part 3
# installer wrote, whose `animation.speed` was a multiplier and whose `effects` carried four
# booleans. The shape matters: a fixture invented for the test would measure the fixture
# rather than the migration, and would migrate cleanly whatever the real document did.
V1_DOCUMENT: Dict[str, Any] = {
    "_copyright": "Copyright (C) 2026 Safari — GPL-3.0-or-later",
    "version": 1,
    "preset": "glass",
    "effects": {"blur": True, "transparency": True, "animations": True, "shadows": True},
    "theme": {"colour_preset": "midnight-glass", "colour_mode": "dark", "accent": ""},
    "animation": {"preset": "smooth", "speed": 1.0, "reduce_motion": False,
                  "event_overrides": {}},
    "modes": {"game": {"active": False}, "focus": {"active": False}},
    "notes": "written by an installer that predates the settings application",
}

try:  # pragma: no cover - depends on what is installed
    import jsonschema  # noqa: F401

    HAVE_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAVE_JSONSCHEMA = False


def fresh_store(document: Optional[Dict[str, Any]] = None) -> Any:
    """A ``Store`` pointed at a temporary config dir, with the document already on disk."""
    tmp = tempfile.TemporaryDirectory()
    env = {"IARCH_CONFIG_DIR": tmp.name}
    if document is not None:
        path = config_store.user_path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    store = config_store.Store(root=ROOT, env=env)
    return store, tmp


class TestTheVersionsTheProjectAccepts(unittest.TestCase):
    """Version 2 is written, version 1 is accepted as input, and nothing else."""

    def test_the_accepted_versions_are_one_and_two(self):
        self.assertEqual((1, 2), config_store.ACCEPTED_VERSIONS)
        self.assertEqual(2, config_store.CURRENT_VERSION)
        self.assertIn(config_store.CURRENT_VERSION, config_store.ACCEPTED_VERSIONS,
                      "the version this project writes is not one it accepts, so a document "
                      "it wrote could not be read back")

    def test_the_shipped_defaults_are_already_version_two(self):
        self.assertEqual(2, DEFAULTS["version"])

    def test_the_schema_accepts_both_versions(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual([1, 2], schema["properties"]["version"]["enum"])


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema is not installed")
class TestAV1DocumentMigratesToAValidatingV2Document(unittest.TestCase):
    """The promise at settings.schema.json:25, checked by running the validator."""

    def test_the_migration_output_validates_against_the_schema(self):
        import jsonschema

        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        migrated = config_store.migrate_v1_to_v2(V1_DOCUMENT, DEFAULTS)
        errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(migrated),
                        key=lambda error: str(error.path))
        self.assertEqual([], [f"{'/'.join(str(part) for part in error.path)}: "
                              f"{error.message}" for error in errors],
                         "a version 1 document came out of the migration as something the "
                         "schema refuses, so load() would quarantine a file the project "
                         "itself upgraded")

    def test_the_version_is_two_afterwards(self):
        self.assertEqual(2, config_store.migrate_v1_to_v2(V1_DOCUMENT, DEFAULTS)["version"])

    def test_the_migration_is_pure_and_writes_nothing(self):
        before = json.dumps(V1_DOCUMENT, sort_keys=True)
        config_store.migrate_v1_to_v2(V1_DOCUMENT, DEFAULTS)
        self.assertEqual(before, json.dumps(V1_DOCUMENT, sort_keys=True),
                         "the migration edited its input, so a caller cannot show the person "
                         "what they had before it changed")

    def test_every_section_version_two_needs_is_present(self):
        migrated = config_store.migrate_v1_to_v2(V1_DOCUMENT, DEFAULTS)
        for section in ("glass", "fonts", "startup", "app", "modes", "theme", "animation"):
            with self.subTest(section=section):
                self.assertIn(section, migrated,
                              f"{section} is a version 2 section the migration did not add, "
                              f"and a v1 install has no such section to begin with")


class TestTheMigrationKeepsWhatThePersonChose(unittest.TestCase):
    """Rule 1, and the three rules that follow from the coarse switches."""

    def test_a_choice_already_in_the_document_survives(self):
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["theme"]["accent"] = "#ff7043"
        document["animation"]["speed"] = 0.5
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertEqual("#ff7043", migrated["theme"]["accent"])
        self.assertEqual(0.5, migrated["animation"]["speed"])
        self.assertEqual("midnight-glass", migrated["theme"]["colour_preset"],
                         "a preset the person chose was replaced by the default")

    def test_animations_off_becomes_the_one_mechanism_that_means_off(self):
        """A v1 document with no preset of its own: the coarse switch is all it has."""
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["effects"]["animations"] = False
        document["animation"].pop("preset", None)
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertEqual("off", migrated["animation"]["preset"],
                         "effects.animations: false did not become animation.preset 'off', "
                         "so 'no animation' now has two mechanisms that can disagree")

    def test_a_preset_and_a_coarse_switch_that_disagree_end_up_agreeing(self):
        """`animation.preset` owns `effects.animations`; the derived value was the stale one."""
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["effects"]["animations"] = False
        document["animation"]["preset"] = "smooth"
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertEqual("smooth", migrated["animation"]["preset"],
                         "the migration discarded a preset the document already stated")
        self.assertIs(True, migrated["effects"]["animations"],
                      "the migrated file describes one intention two ways and the two "
                      "disagree, which is the state the re-derivation exists to end")

    def test_a_preset_already_chosen_is_not_overwritten_by_the_coarse_switch(self):
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["effects"]["animations"] = False
        document["animation"]["preset"] = "snappy"
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertEqual("snappy", migrated["animation"]["preset"],
                         "the migration discarded a preset the document already stated")

    def test_shadows_off_becomes_a_leaf_override_because_no_intensity_expresses_it(self):
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["effects"]["shadows"] = False
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        leaves = migrated["glass"]["leaves"]
        self.assertIn(config_store.SHADOW_LEAF, leaves)
        self.assertIs(False, leaves[config_store.SHADOW_LEAF])
        self.assertEqual("decoration:shadow:enabled", config_store.SHADOW_LEAF)

    def test_an_existing_leaf_override_wins_over_the_coarse_switch(self):
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["effects"]["shadows"] = False
        document["glass"] = {"leaves": {"decoration:shadow:enabled": True}}
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertIs(True, migrated["glass"]["leaves"]["decoration:shadow:enabled"])

    def test_per_app_opacity_starts_empty_because_an_empty_list_is_the_intensity_itself(self):
        migrated = config_store.migrate_v1_to_v2(V1_DOCUMENT, DEFAULTS)
        self.assertEqual([], migrated["glass"]["per_app_opacity"])
        self.assertEqual({}, migrated["glass"]["leaves"],
                         "an empty leaves object means the intensity's own values, which "
                         "is what a fresh install has, and the migration invented one")

    def test_an_intensity_is_derived_when_the_document_has_none(self):
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["theme"].pop("intensity", None)
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertTrue(str(migrated["theme"]["intensity"]).strip(),
                        "no intensity was derived, so the theme section is incomplete")

    def test_the_coarse_switches_are_re_derived_so_both_descriptions_agree(self):
        migrated = config_store.migrate_v1_to_v2(V1_DOCUMENT, DEFAULTS)
        again = config_store.derive_coarse(migrated, ROOT)
        self.assertEqual(json.dumps(migrated["effects"], sort_keys=True),
                         json.dumps(again["effects"], sort_keys=True),
                         "the file that is written describes one intention two ways and the "
                         "two disagree")


class TestTheMergeOrderPutsTheDefaultsUnderneath(unittest.TestCase):
    """Defaults under the user file, so a defaults change cannot undo a choice."""

    def setUp(self):
        self.store, self._tmp = fresh_store()
        self.addCleanup(self._tmp.cleanup)

    def test_the_user_path_comes_from_the_environment_and_is_a_property(self):
        self.assertIsInstance(self.store.user_path, Path)
        self.assertIsInstance(self.store.defaults_path, Path)
        self.assertTrue(str(self.store.user_path).endswith("settings.json"))

    def test_a_value_the_user_file_states_wins_over_the_default(self):
        document = json.loads(json.dumps(DEFAULTS))
        document["theme"]["accent"] = "#00ff88"
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        store.load()
        self.assertEqual("#00ff88", store.get("theme.accent"))

    def test_a_section_the_user_file_lacks_comes_from_the_defaults(self):
        document = json.loads(json.dumps(DEFAULTS))
        document["theme"]["accent"] = "#123456"
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        loaded = store.load()
        self.assertEqual("#123456", loaded["theme"]["accent"])
        self.assertIn("glass", loaded, "a section missing from the user file was not filled "
                                       "in from the defaults")

    def test_the_mode_and_page_state_come_from_the_raw_user_file(self):
        """The application's own state must not be invented by the defaults."""
        document = json.loads(json.dumps(DEFAULTS))
        document["app"]["last_page"] = "backup"
        document["app"]["window_width"] = 1280
        document["modes"]["game"]["active"] = True
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        store.load()
        path = config_store.user_path({"IARCH_CONFIG_DIR": str(tmp.name)})
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("backup", raw["app"]["last_page"])
        self.assertEqual("backup", store.get("app.last_page"))
        self.assertEqual(1280, store.get("app.window_width"))
        self.assertIs(True, store.get("modes.game.active"))
        self.assertNotEqual(DEFAULTS["app"]["window_width"], store.get("app.window_width"),
                            "the window the person resized was reset by the defaults")

    def test_a_last_page_naming_no_page_is_kept_and_handled_by_the_window(self):
        """The schema leaves last_page a free string on purpose."""
        document = json.loads(json.dumps(DEFAULTS))
        document["app"]["last_page"] = "a-page-that-was-renamed"
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        store.load()
        self.assertEqual("a-page-that-was-renamed", store.get("app.last_page"),
                         "an unknown page id was dropped or rewritten, so the schema would "
                         "have to be edited every time a page is added")
        from iarch_settings import pages
        self.assertFalse(pages.has_page(store.get("app.last_page")),
                         "the id is meant to be unknown for this test")
        self.assertTrue(pages.has_page(pages.DEFAULT_PAGE),
                        "the window's fallback page is not in the registry")

    def test_the_defaults_are_read_from_the_repository_and_not_copied_into_the_user_file(self):
        document = json.loads(json.dumps(DEFAULTS))
        document["app"]["last_page"] = "glass"
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        self.assertEqual(config_store.defaults_path(root=ROOT), store.defaults_path)
        store.load()
        raw = json.loads(config_store.user_path({"IARCH_CONFIG_DIR": str(tmp.name)})
                         .read_text(encoding="utf-8"))
        self.assertEqual(document, raw,
                         "reading the document rewrote the user's file, which is how a "
                         "defaults change becomes a choice the person never made")
        self.assertEqual("glass", store.get("app.last_page"))

    def test_the_required_sections_are_three_and_a_document_without_them_is_completed(self):
        """Missing is filled from the defaults; unknown is quarantined. Two different answers."""
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(["version", "preset", "effects"], schema["required"],
                         "the coarse pair is still read by the installers and by the "
                         "doctor, so a document without it cannot be honoured")
        document = {"version": 2, "app": {"last_page": "home"}}
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        loaded = store.load()
        self.assertEqual(config_store.LOADED, store.status,
                         "a document missing a required section was refused rather than "
                         "completed from the defaults, which is the whole reason the "
                         "defaults are merged underneath")
        self.assertEqual("home", loaded["app"]["last_page"],
                         "the page the person's file named was replaced while the rest of "
                         "the document was being completed")
        self.assertIn("preset", loaded)
        self.assertIn("effects", loaded)
        self.assertEqual(document, json.loads(config_store.user_path(
            {"IARCH_CONFIG_DIR": str(tmp.name)}).read_text(encoding="utf-8")),
            "completing the document rewrote the file, so a defaults change would become a "
            "choice the person never made")

    def test_a_property_the_schema_does_not_allow_is_quarantined(self):
        """`additionalProperties: false` is what catches a key nobody reads."""
        document = json.loads(json.dumps(DEFAULTS))
        document["app"]["mode"] = "performance"
        store, tmp = fresh_store(document)
        self.addCleanup(tmp.cleanup)
        store.load()
        self.assertEqual(config_store.QUARANTINED, store.status,
                         "a property the schema does not allow was loaded, so a settings "
                         "file can accumulate keys nothing reads and the page would show a "
                         "switch that changes one of them")
        self.assertTrue(store.problems)
        self.assertIn("app", " ".join(store.problems))

    def test_a_dotted_get_and_set_reach_a_nested_value(self):
        store, tmp = fresh_store(json.loads(json.dumps(DEFAULTS)))
        self.addCleanup(tmp.cleanup)
        store.load()
        store.set("theme.accent", "#abcdef", save=False)
        self.assertEqual("#abcdef", store.get("theme.accent"))
        self.assertIsNone(store.get("theme.nonsense"))
        self.assertEqual("fallback", store.get("theme.nonsense", "fallback"))


class TestAFileIsWrittenAtomicallyAndNeverThroughALink(unittest.TestCase):
    """``save`` goes through ``iarch.lib.configstore.atomic_write``, which refuses a symlink."""

    def setUp(self):
        self.store, self._tmp = fresh_store(json.loads(json.dumps(DEFAULTS)))
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_saving_writes_valid_json_with_the_owner_only_mode(self):
        self.store.load()
        path = self.store.save({"theme.accent": "#010203"})
        self.assertTrue(path.is_file())
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual("#010203", document["theme"]["accent"])
        self.assertEqual(0o600, path.stat().st_mode & 0o777,
                         f"{oct(path.stat().st_mode & 0o777)} is not owner-only, and this "
                         f"file holds every choice the person made")
        self.assertEqual(config_store.SETTINGS_MODE, 0o600)

    def test_a_symlink_in_place_of_the_settings_file_is_refused(self):
        victim = self.tmp / "victim.json"
        victim.write_text("{}", encoding="utf-8")
        link = self.tmp / "settings.json"
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(victim)
        with self.assertRaises(shared_store.ConfigError):
            shared_store.atomic_write(link, "{}")
        self.assertEqual("{}", victim.read_text(encoding="utf-8"),
                         "the write followed the link, so anything that can plant a symlink "
                         "in the config directory can write any file the user can")

    def test_saving_through_a_symlinked_settings_file_is_refused_too(self):
        """Loaded first, then the file is swapped for a link: the order a person hits it in."""
        victim = self.tmp / "victim.json"
        victim.write_text("{}", encoding="utf-8")
        self.store.load()
        link = config_store.user_path({"IARCH_CONFIG_DIR": str(self.tmp)})
        link.unlink()
        link.symlink_to(victim)
        with self.assertRaises(shared_store.ConfigError) as caught:
            self.store.save({})
        self.assertIn("symlink", str(caught.exception).lower(),
                      f"the refusal does not say what was wrong: {caught.exception}")
        self.assertEqual("{}", victim.read_text(encoding="utf-8"),
                         "the write followed the link into a file the person never named")


class TestBackupsAreRecognisedByPrefixAndNotByInvertingAName(unittest.TestCase):
    """A path separator becomes an underscore, so the file name cannot be read back."""

    def test_the_backup_prefix_comes_from_the_environment(self):
        prefix = config_store.backup_prefix({"IARCH_CONFIG_DIR": "/tmp/one"})
        self.assertTrue(prefix)
        self.assertNotEqual(prefix, config_store.backup_prefix({"IARCH_CONFIG_DIR":
                                                                "/tmp/two"}),
                            "two config directories share a backup prefix, so a restore in "
                            "one could pick up a backup made by the other")

    def test_the_backup_suffix_and_limit_are_recorded_once(self):
        self.assertEqual(".bak", config_store.BACKUP_SUFFIX)
        self.assertEqual(5, config_store.BACKUP_LIMIT)

    def test_backups_are_listed_newest_first_and_only_from_the_backup_directory(self):
        store, tmp = fresh_store(json.loads(json.dumps(DEFAULTS)))
        self.addCleanup(tmp.cleanup)
        env = {"IARCH_CONFIG_DIR": tmp.name}
        first = config_store.backups(env)
        self.assertIsInstance(first, list)
        for path in first:
            with self.subTest(backup=str(path)):
                self.assertTrue(str(path).startswith(config_store.backup_prefix(env)),
                                "a file that is not a backup was listed as one")

    def test_a_path_outside_the_backup_directory_is_refused_by_restore(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "elsewhere.json"
            outside.write_text("{}", encoding="utf-8")
            ok, reason = config_store.restore(outside, {"IARCH_CONFIG_DIR": tmp})
            self.assertFalse(ok)
            self.assertTrue(reason.strip(), "a refusal with no reason is a shrug")

    def test_a_backup_name_that_is_not_a_backup_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"IARCH_CONFIG_DIR": tmp}
            odd = Path(tmp) / f"{config_store.backup_prefix(env)}../../etc/passwd.bak"
            ok, reason = config_store.restore(odd, env)
            self.assertFalse(ok, "a traversal in a backup name reached a file outside the "
                                 "backup directory")
            self.assertTrue(reason.strip())

    def test_a_restore_reports_what_it_did_in_a_sentence(self):
        store, tmp = fresh_store(json.loads(json.dumps(DEFAULTS)))
        self.addCleanup(tmp.cleanup)
        env = {"IARCH_CONFIG_DIR": tmp.name}
        store.load()
        store.save({"theme.accent": "#aaaaaa"})
        store.save({"theme.accent": "#bbbbbb"})
        found = config_store.backups(env)
        if not found:
            self.skipTest("no backup was made, so there is nothing to restore")
        ok, reason = config_store.restore(found[0], env)
        self.assertTrue(ok, reason)
        self.assertIn(str(found[0].name), reason,
                      "the sentence does not name the backup that was restored, so a person "
                      "cannot tell which of five it was")


class TestADocumentThatWillNotParseIsQuarantined(unittest.TestCase):
    """Deleting what cannot be read is not a recovery strategy."""

    def test_a_broken_document_is_moved_aside_with_a_reason_and_not_replaced(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = {"IARCH_CONFIG_DIR": tmp.name}
        path = config_store.user_path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{ this is not json", encoding="utf-8")
        store = config_store.Store(root=ROOT, env=env)
        loaded = store.load()
        self.assertIsInstance(loaded, dict)
        # The status is an attribute, not a key: the document a page reads must not carry
        # the store's own bookkeeping in it.
        self.assertEqual(config_store.QUARANTINED, store.status,
                         f"the load did not report that it quarantined: {store.status}")
        self.assertTrue(store.problems or store.quarantined_to,
                        "a quarantine with no recorded reason cannot be explained to the "
                        "person whose file was moved")
        self.assertEqual(sorted(DEFAULTS), sorted(loaded),
                         "a quarantined load did not fall back to the defaults, so the "
                         "application would start with no document at all")
        broken = sorted(Path(tmp.name).glob(f"*{config_store.BROKEN_PREFIX}*"))
        self.assertTrue(broken, "the broken file was deleted rather than moved aside, so the "
                                "person lost every choice in it")
        self.assertIn("not json", broken[0].read_text(encoding="utf-8"))

    def test_the_quarantine_prefix_is_recorded_once(self):
        self.assertEqual(".broken.", config_store.BROKEN_PREFIX)
        self.assertTrue(config_store.BROKEN_PREFIX.startswith("."),
                        "a quarantined file that is not hidden would be offered as a "
                        "document to load")

    def test_a_document_with_an_unknown_version_is_quarantined_too(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = {"IARCH_CONFIG_DIR": tmp.name}
        path = config_store.user_path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 99}), encoding="utf-8")
        store = config_store.Store(root=ROOT, env=env)
        store.load()
        self.assertEqual(config_store.QUARANTINED, store.status,
                         "a version this project does not accept was loaded anyway")

    def test_a_version_one_document_is_loaded_by_being_migrated_not_quarantined(self):
        """The whole point of accepting version 1: an existing install keeps working."""
        store, tmp = fresh_store(json.loads(json.dumps(V1_DOCUMENT)))
        self.addCleanup(tmp.cleanup)
        loaded = store.load()
        self.assertNotEqual(config_store.QUARANTINED, store.status,
                            "a version 1 document was quarantined, which refuses every "
                            "install that predates this application")
        self.assertEqual(config_store.MIGRATED, store.status)
        self.assertEqual(2, loaded["version"])
        if HAVE_JSONSCHEMA:
            self.assertEqual([], store.problems,
                             "the migrated document did not validate, so the very next line "
                             "of load() would quarantine the file it had just upgraded")

    def test_a_version_one_document_is_written_back_as_version_two(self):
        store, tmp = fresh_store(json.loads(json.dumps(V1_DOCUMENT)))
        self.addCleanup(tmp.cleanup)
        store.load()
        store.save({})
        written = json.loads(config_store.user_path(
            {"IARCH_CONFIG_DIR": tmp.name}).read_text(encoding="utf-8"))
        self.assertEqual(2, written["version"],
                         "the file on disk is still version 1, so the next load migrates "
                         "again and a person's repair is written over each time")

    def test_the_validator_reports_its_own_state_rather_than_pretending(self):
        state = config_store.validator_state()
        self.assertIn(state, ("validated", "unavailable"))
        self.assertEqual("validated" if HAVE_JSONSCHEMA else "unavailable", state,
                         "the About page's debug line would say the document was validated "
                         "when nothing checked it")

    def test_validation_problems_are_sentences_and_empty_for_the_shipped_defaults(self):
        if not HAVE_JSONSCHEMA:
            self.assertEqual([], config_store.validation_problems(DEFAULTS, ROOT),
                             "with no validator installed a document must report no "
                             "problems, because 'unchecked' is not 'wrong'")
            self.skipTest("jsonschema is not installed")
        self.assertEqual([], config_store.validation_problems(DEFAULTS, ROOT))
        problems = config_store.validation_problems({"version": 2, "preset": "nonsense"},
                                                    ROOT)
        self.assertTrue(problems)
        self.assertTrue(all(isinstance(problem, str) and problem.strip()
                            for problem in problems))


class TestTheCoarseSwitchesAreDerivedNotStoredTwice(unittest.TestCase):
    """Two descriptions of one intention, kept in agreement by derivation."""

    def test_the_intensity_table_comes_from_the_tokens_record(self):
        table = config_store.effects_by_intensity(ROOT)
        self.assertTrue(table)
        for intensity, effects in table.items():
            with self.subTest(intensity=intensity):
                self.assertEqual(2, len(effects),
                                 f"{intensity} maps to {effects}, and the pair is "
                                 f"(animations, shadows)")
                self.assertTrue(all(isinstance(value, bool) for value in effects))

    def test_a_blur_leaf_is_the_one_mechanism_for_blur(self):
        self.assertEqual("decoration:blur:enabled", config_store.BLUR_LEAF)

    def test_blur_or_transparency_off_is_the_performance_intensity(self):
        """Two of a version 1 file's four booleans decide everything."""
        for effects in ({"blur": False}, {"transparency": False},
                        {"blur": False, "transparency": False}):
            with self.subTest(effects=effects):
                self.assertEqual("performance",
                                 config_store.intensity_from_effects(effects, "frosted"))

    def test_effects_that_mean_nothing_in_particular_fall_back_to_the_default(self):
        for effects in ({}, {"blur": True, "transparency": True},
                        {"animations": False}, {"shadows": False}):
            with self.subTest(effects=effects):
                self.assertEqual("frosted",
                                 config_store.intensity_from_effects(effects, "frosted"),
                                 "an effects map that does not turn blur or transparency off "
                                 "is the tokens' own default, and guessing an intensity here "
                                 "would change a person's theme")

    def test_shadows_alone_cannot_choose_an_intensity_and_the_record_says_why(self):
        """Every intensity that blurs also shadows, so shadows becomes a leaf override."""
        self.assertEqual("frosted", config_store.intensity_from_effects(
            {"shadows": False}, "frosted"))
        document = json.loads(json.dumps(V1_DOCUMENT))
        document["effects"]["shadows"] = False
        migrated = config_store.migrate_v1_to_v2(document, DEFAULTS)
        self.assertIn(config_store.SHADOW_LEAF, migrated["glass"]["leaves"],
                      "shadows: false was dropped on the floor instead of becoming the leaf "
                      "override that glass.leaves exists for")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
