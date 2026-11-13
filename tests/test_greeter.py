#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the login screen record, ``data/design/greeter.json``.

Nothing in this repository generates a login-screen file, and these tests are the
reason that is a decision rather than a gap. The greeter's declarative config is a
root-owned file at ``/var/lib/noctalia-greeter/greeter.toml`` that wins over Sync
for every key it sets, its parser only ever warns, and almost everything worth
putting in it -- a connector name, an account name, a cursor theme directory, a
keyboard layout -- is a fact about one machine. So the record exists to evidence
three absences and one contract:

* no ``greeter.toml`` ships, and the payload does not configure the greeter;
* ``[shell.greeter_sync]`` and ``[shell] polkit_agent`` are withheld, with the
  renderer refusing both and naming the reason rather than claiming upstream has
  no such setting;
* the sixteen colours Sync sends are producible from every palette this
  repository ships, in both modes, because an incomplete palette makes the
  helper refuse the sync outright;
* the greetd block both installers write is upstream's own block, and the one
  line that had drifted -- the state directory's mode -- now matches too.

The record also carries four places where the greeter's documentation disagrees
with its code. Those are asserted against the values the code honours, because a
record that repeated the manual would be wrong in four places and would look
right in all of them.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
import unittest
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import render_noctalia as noctalia  # noqa: E402

RECORD_PATH = ROOT / "data" / "design" / "greeter.json"
RECORD = json.loads(RECORD_PATH.read_text(encoding="utf-8"))
SHELL_SURFACE = json.loads(noctalia.SURFACE_PATH.read_text(encoding="utf-8"))
TOKENS = noctalia.load_tokens()
CONFIG = tomllib.loads((ROOT / ".config" / "noctalia" / "config.toml").read_text(encoding="utf-8"))
PALETTES = sorted((ROOT / ".config" / "noctalia" / "palettes").glob("*.json"))
INSTALLERS = ("install.sh", "fedora_install.sh")

# isKnownTopLevelKey, src/greeter/greeter_config_io.cpp:45-55 at v1.7.0. Spelled
# out here rather than read from the record: the point of the test is that the
# record and the parser agree, and a second copy is what makes that a comparison.
TOP_LEVEL_TABLES = {"session", "user", "appearance", "output", "cursor",
                    "keyboard", "auth", "idle", "clock"}

# requiredPaletteKeys(), src/greeter/appearance_sync.h:44-52 at v1.7.0, in
# declaration order. A staged sync.toml whose palette is missing one of these is
# refused by the helper, so this list is a hard requirement and not a convention.
REQUIRED_PALETTE_KEYS = [
    "primary", "on_primary", "secondary", "on_secondary", "tertiary", "on_tertiary",
    "error", "on_error", "surface", "on_surface", "surface_variant", "on_surface_variant",
    "outline", "shadow", "hover", "on_hover",
]

# Easing, src/render/animation/animation.h:7-13 at v1.7.0.
EASINGS = ["Linear", "EaseInCubic", "EaseOutCubic", "EaseInOutCubic", "EaseOutBack"]

FUNCTION = re.compile(r"^setup_noctalia_greeter\(\) \{$", re.MULTILINE)
CITATION = re.compile(r"(?<![\w./-])((?:[\w.-]+/)*[\w.-]+\.(?:sh|lua|toml|json|py|mdx|md|desktop))")
LOCAL_PREFIXES = ("install.sh", "fedora_install.sh", "lib/", "tools/", "tests/", "data/",
                  ".config/", "iarch/", "legacy/", "profiles/")
HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_repo_local(candidate: str) -> bool:
    """Whether a cited path is this repository's rather than upstream's.

    Two prefixes are ambiguous and need a rule of their own: the greeter has a
    ``docs/`` and a ``scripts/`` too, and its user documentation all lives under
    ``docs/user/`` while its setup helpers are ``scripts/*.sh``. Everything this
    repository cites under those two trees is either a document at the top of
    ``docs/`` or a script beginning ``iarch-``, so the ambiguity is resolvable
    without guessing.
    """
    if candidate.startswith(LOCAL_PREFIXES):
        return True
    if candidate.startswith("docs/"):
        return not candidate.startswith(("docs/user/", "docs/developer/", "docs/plugin/"))
    if candidate.startswith("scripts/"):
        return candidate.startswith("scripts/iarch-")
    return False


def variables(node: Dict[str, Any], path: str = "") -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Yield every recorded key as (dotted path, spec), descending into tables."""
    for name, spec in node.items():
        here = f"{path}.{name}" if path else name
        yield here, spec
        if isinstance(spec, dict) and isinstance(spec.get("keys"), dict):
            yield from variables(spec["keys"], here)


def all_variables() -> Iterator[Tuple[str, Dict[str, Any]]]:
    # Prefixed with the table name, because three tables have a key called
    # "default" and an unprefixed path would collapse them into one.
    for name, section in RECORD["greeter_toml"]["sections"].items():
        yield from variables(section["keys"], name)
    yield from variables(RECORD["greetd_config"]["tables"]["terminal"]["keys"], "terminal")
    yield from variables(RECORD["greetd_config"]["tables"]["default_session"]["keys"],
                         "default_session")
    yield from variables(RECORD["main_only_keys"]["keys"])


def installer(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def function_body(text: str) -> str:
    """The whole ``setup_noctalia_greeter()`` definition, braces included."""
    start = FUNCTION.search(text)
    assert start is not None, "setup_noctalia_greeter() is not defined"
    lines = text[start.start():].splitlines()
    for index, line in enumerate(lines[1:], start=1):
        if line == "}":
            return "\n".join(lines[:index + 1])
    raise AssertionError("setup_noctalia_greeter() is never closed")


def greetd_block(text: str) -> Dict[str, Dict[str, str]]:
    """Parse the greetd config.toml the installer writes, out of its heredoc."""
    body = function_body(text)
    start = body.index('cat > "$greetd_config_file" <<EOF')
    lines = body[start:].splitlines()[1:]
    tables: Dict[str, Dict[str, str]] = {}
    current: Dict[str, str] = {}
    for line in lines:
        if line == "EOF":
            break
        if line.startswith("[") and line.endswith("]"):
            current = {}
            tables[line[1:-1]] = current
        elif line.strip():
            key, _, value = line.partition("=")
            current[key.strip()] = value.strip()
    return tables


def normalize_braces(lines: List[str]) -> List[str]:
    """``${name}`` and ``$name`` are the same string to a shell."""
    return [re.sub(r"\$\{(\w+)\}", r"$\1", line) for line in lines]


def walk_strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from walk_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from walk_strings(value)


class TheRecordDescribesTheParser(unittest.TestCase):
    """Every key, type, default, enumeration and range the record claims."""

    def test_two_releases_are_pinned_with_a_fetch_date(self):
        # Two projects are involved -- the greeter and the shell that syncs to it
        # -- so one version would leave half the record unpinned.
        self.assertIn("v1.7.0", RECORD["verified_against"])
        self.assertIn("v5.4.1", RECORD["shell_verified_against"])
        for field in ("verified_against", "shell_verified_against"):
            self.assertRegex(RECORD[field], r"fetched \d{4}-\d{2}-\d{2}")

    def test_the_recorded_tables_are_the_nine_the_parser_knows(self):
        self.assertEqual(TOP_LEVEL_TABLES, set(RECORD["greeter_toml"]["sections"]))

    def test_every_key_has_a_type_and_a_default_of_that_type(self):
        expected = {"bool": bool, "int": int, "float": (int, float), "string": str,
                    "color": (str, type(None)), "table": type(None), "map": type(None)}
        seen = 0
        for path, spec in all_variables():
            with self.subTest(key=path):
                self.assertIn(spec["type"], expected)
                default = spec["default"]
                if default is not None or spec["type"] in ("color", "table", "map"):
                    self.assertIsInstance(default, expected[spec["type"]])
                seen += 1
        self.assertGreaterEqual(seen, 40, "the record lost most of its keys")

    def test_booleans_really_are_booleans(self):
        # A bool recorded as the string "false" would pass a type check written
        # loosely, and isinstance(True, int) is the classic way to lose an int.
        for path, spec in all_variables():
            if spec["type"] == "bool" and spec["default"] is not None:
                with self.subTest(key=path):
                    self.assertIsInstance(spec["default"], bool)
            if spec["type"] == "int" and isinstance(spec["default"], int):
                with self.subTest(key=path):
                    self.assertNotIsInstance(spec["default"], bool)

    def test_every_enumeration_says_whether_the_greeter_enforces_it(self):
        # Three of the recorded enumerations are documentation only: the greeter
        # matches those values by equality and silently falls through to a
        # default. A reader has to be able to tell which is which.
        enumerated = [(path, spec) for path, spec in all_variables() if "enum" in spec]
        self.assertGreaterEqual(len(enumerated), 6)
        for path, spec in enumerated:
            with self.subTest(key=path):
                self.assertIn("validat", spec["enum_note"].lower(),
                              "the note does not say whether the value is checked")
                self.assertEqual(len(spec["enum"]), len(set(spec["enum"])))

    def test_every_range_is_traceable_to_the_code_that_enforces_it(self):
        pattern = re.compile(r"\.(cpp|c|h|md|mdx|toml)(:|$|[ ,)])")
        ranged = [(path, spec) for path, spec in all_variables() if "range" in spec]
        self.assertGreaterEqual(len(ranged), 6)
        for path, spec in ranged:
            with self.subTest(key=path):
                low, high = spec["range"]
                self.assertLessEqual(low, high)
                self.assertIn("source", spec, "a range with no citation is a guess")
                self.assertRegex(spec["source"], pattern)
                # The note explains the range; it does not restate the key.
                self.assertNotEqual(spec.get("note"), spec["range_note"])
                self.assertGreater(len(spec["range_note"]), 40)
                if spec["default"] is not None:
                    self.assertLessEqual(low, spec["default"])
                    self.assertGreaterEqual(high, spec["default"])

    def test_every_recorded_key_says_what_it_is(self):
        # A record whose purpose is documentation is not allowed a bare key, and
        # the two that started out without one were exactly the two a reader
        # would most want explained: whether the clock is on, and how big the
        # cursor is when nothing asks.
        bare = [path for path, spec in all_variables() if not spec.get("note")]
        self.assertEqual([], bare)

    def test_citations_name_a_file_and_not_only_a_document(self):
        pattern = re.compile(r"\.(cpp|h|c|md|mdx|sh|toml|in|build|json|lua|desktop)(:|$|[ ,)])")
        checked = 0
        for path, spec in all_variables():
            if "source" in spec:
                with self.subTest(key=path):
                    self.assertRegex(spec["source"], pattern)
                checked += 1
        self.assertGreaterEqual(checked, 25)

    def test_citations_of_files_in_this_repository_resolve(self):
        # Upstream paths cannot be checked offline, but a citation of install.sh
        # or of a payload file can be, and a stale one is how a record rots.
        missing, checked = set(), set()
        for text in walk_strings(RECORD):
            for candidate in CITATION.findall(text):
                if is_repo_local(candidate):
                    checked.add(candidate)
                    if not (ROOT / candidate).exists():
                        missing.add(candidate)
        self.assertEqual(set(), missing, "the record cites repository files that do not exist")
        # A rule that matched nothing would pass just as quietly.
        self.assertGreaterEqual(len(checked), 8)

    def test_the_state_directory_is_recorded_with_its_mode_and_owner(self):
        state = RECORD["state_directory"]
        self.assertEqual("/var/lib/noctalia-greeter", state["path"])
        self.assertEqual("0750", state["mode"])
        self.assertEqual("0644", state["file_mode"])
        self.assertIn("kSyncedDirMode", state["mode_constant"])
        self.assertIn("NOCTALIA_GREETER_STATE_DIR", state["env_override"]["name"])
        for name in ("greeter.toml", "sync.toml"):
            self.assertIn(name, state["files"])


class TheDocDisagreementsAreRecorded(unittest.TestCase):
    """Four places where the greeter's own documentation is wrong at v1.7.0.

    Each entry says what the documents claim, what the code does, and what
    follows from believing the documents. The recorded default or range has to be
    the one the code honours, which is the only way the entry can be checked
    against the rest of the record instead of floating free of it.
    """

    def setUp(self):
        self.entries = {entry["id"]: entry for entry in RECORD["doc_disagreements"]}
        self.keys = {path: spec for path, spec in all_variables()}

    def test_the_four_ids_are_unique_and_present(self):
        self.assertEqual({"numlock", "output_scale", "idle_default", "position_validation"},
                         set(self.entries))
        self.assertEqual(len(RECORD["doc_disagreements"]), len(self.entries))

    def test_numlock_defaults_to_off_despite_two_documents_saying_on(self):
        entry = self.entries["numlock"]
        self.assertFalse(entry["recorded_default"])
        self.assertFalse(self.keys["keyboard.numlock"]["default"])
        self.assertTrue(self.keys["keyboard.numlock"]["doc_disagreement"])
        self.assertIn("explicitly requested", entry["code_does"])

    def test_the_session_turns_numlock_on_and_the_login_screen_does_not(self):
        # The consequence, checked against the file it names rather than restated.
        inputs = (ROOT / ".config" / "hypr" / "inputs.lua").read_text(encoding="utf-8")
        self.assertIn("numlock_by_default = true", inputs)
        self.assertIn("numlock_by_default = true", self.entries["numlock"]["consequence"])

    def test_output_scale_records_the_range_the_compositor_honours(self):
        entry = self.entries["output_scale"]
        self.assertEqual([1.0, 3.4028235e+38], entry["recorded_range"])
        self.assertEqual(entry["recorded_range"], self.keys["output.scale"]["range"])
        self.assertIn("1.0", entry["code_does"])

    def test_idle_defaults_to_disabled_not_to_the_examples_300(self):
        entry = self.entries["idle_default"]
        self.assertEqual(0, entry["recorded_default"])
        self.assertEqual(0, self.keys["idle.timeout"]["default"])
        self.assertEqual([0, 86400], self.keys["idle.timeout"]["range"])
        self.assertIn("300", entry["docs_say"])

    def test_only_the_clock_position_is_validated(self):
        self.assertIn("clock.position", self.entries["position_validation"]["code_does"])
        self.assertIn("validat", self.keys["clock.position"]["enum_note"].lower())
        for key in ("appearance.power_buttons_position", "appearance.scheme_selector_position"):
            with self.subTest(key=key):
                self.assertNotIn("doc_disagreement", self.keys[key])
                self.assertIn("never validated", self.keys[key]["enum_note"])

    def test_the_keys_v170_does_not_have_are_kept_out_of_the_surface(self):
        # main adds two clock font sizes. They are recorded, but as main-only, so
        # that nothing here treats them as part of the pinned release.
        main_only = RECORD["main_only_keys"]["keys"]
        self.assertEqual({"clock.time_font_size", "clock.date_font_size"}, set(main_only))
        clock_keys = set(RECORD["greeter_toml"]["sections"]["clock"]["keys"])
        self.assertEqual({"enabled", "position", "time_format", "date_format"}, clock_keys)
        self.assertIn("unrecognized key", RECORD["main_only_keys"]["note"])


class TheInstallersWriteWhatUpstreamWrites(unittest.TestCase):
    """The greetd block, the greeter account, and the one line that had drifted."""

    def setUp(self):
        self.bodies = {name: function_body(installer(name)) for name in INSTALLERS}

    def test_both_installers_define_the_function(self):
        for name in INSTALLERS:
            with self.subTest(installer=name):
                self.assertEqual(1, len(FUNCTION.findall(installer(name))))

    def test_the_two_copies_are_byte_identical(self):
        # Two installers carrying the same function is a drift risk, so the drift
        # is asserted away rather than hoped away.
        self.assertEqual(self.bodies["install.sh"], self.bodies["fedora_install.sh"])

    def test_the_recorded_line_range_is_the_function(self):
        for name in INSTALLERS:
            citation = RECORD["installer"]["functions"][name]
            start, end = (int(value) for value in
                          re.search(rf"{re.escape(name)}:(\d+)-(\d+)", citation).groups())
            lines = installer(name).splitlines()
            with self.subTest(installer=name):
                self.assertEqual("setup_noctalia_greeter() {", lines[start - 1])
                self.assertEqual("}", lines[end - 1])

    def test_the_greetd_block_has_the_recorded_tables_and_keys(self):
        recorded = RECORD["greetd_config"]["tables"]
        for name in INSTALLERS:
            written = greetd_block(installer(name))
            with self.subTest(installer=name):
                self.assertEqual(set(recorded), set(written))
                for table in recorded:
                    self.assertEqual(set(recorded[table]["keys"]), set(written[table]))

    def test_the_greetd_block_is_upstreams_own_template(self):
        template = normalize_braces(RECORD["greetd_config"]["upstream_template"])
        for name in INSTALLERS:
            body = self.bodies[name]
            start = body.index('cat > "$greetd_config_file" <<EOF')
            written = body[start:].splitlines()[1:]
            written = written[:written.index("EOF")]
            with self.subTest(installer=name):
                self.assertEqual(template, normalize_braces(written))

    def test_the_terminal_is_vt_one(self):
        self.assertEqual("1", greetd_block(installer("install.sh"))["terminal"]["vt"])

    def test_the_session_binary_falls_back_to_the_recorded_default(self):
        default = RECORD["greetd_config"]["tables"]["default_session"]["keys"]["command"]["default"]
        for name in INSTALLERS:
            with self.subTest(installer=name):
                self.assertIn(f'session_bin="{default}"', self.bodies[name])
                self.assertIn("command -v noctalia-greeter-session", self.bodies[name])

    def test_the_greeter_account_falls_back_to_the_recorded_default(self):
        default = RECORD["greetd_config"]["tables"]["default_session"]["keys"]["user"]["default"]
        for name in INSTALLERS:
            with self.subTest(installer=name):
                self.assertIn(f'greeter_user="{default}"', self.bodies[name])

    def test_the_account_is_created_as_a_system_account_with_no_shell(self):
        for name in INSTALLERS:
            with self.subTest(installer=name):
                self.assertIn("useradd -r -s /usr/bin/nologin -d /var/lib/noctalia-greeter",
                              self.bodies[name])

    def test_the_state_directory_is_tightened_to_the_recorded_mode(self):
        mode = RECORD["state_directory"]["mode"]
        for name in INSTALLERS:
            with self.subTest(installer=name):
                self.assertIn(f"chmod {mode} /var/lib/noctalia-greeter", self.bodies[name])

    def test_the_mode_is_set_before_the_directory_is_handed_over(self):
        for name in INSTALLERS:
            body = self.bodies[name]
            with self.subTest(installer=name):
                self.assertLess(body.index("chmod 0750 /var/lib/noctalia-greeter"),
                                body.index('chown -R "$greeter_user:$greeter_user"'))

    def test_the_two_upstream_paths_to_the_same_mode_agree(self):
        # The code tightens the directory to 0750 and the packaged tmpfiles
        # drop-in says the same thing in a different format. Recording one
        # without the other would leave the fix looking like an invention.
        state = RECORD["state_directory"]
        line = state["tmpfiles_dropin"]["line"]
        self.assertIn(state["mode"], line)
        self.assertIn(state["path"], line)
        self.assertIn("greeter", line)
        self.assertIn("S_IRWXU", state["mode_constant"])
        self.assertIn("0750", RECORD["installer"]["drift_found"]["fix"])

    def test_the_drift_entry_describes_the_fix_that_is_in_the_tree(self):
        drift = RECORD["installer"]["drift_found"]
        self.assertIn("0755", drift["what"])
        self.assertIn("chmod 0750", drift["fix"])
        self.assertIn("tests/test_greeter.py", drift["fix"])

    def test_pam_is_delegated_to_the_packaged_script(self):
        path = RECORD["pam"]["setup_greetd_pam"]["path"]
        for name in INSTALLERS:
            body = self.bodies[name]
            with self.subTest(installer=name):
                self.assertIn(f"if [ -x {path} ]", body)
                self.assertIn(f"bash {path}", body)
                # Reimplementing the PAM patch here would mean writing
                # /etc/pam.d/greetd from a shell script in this repository.
                self.assertNotIn("/etc/pam.d", body)

    def test_a_missing_pam_script_warns_instead_of_aborting(self):
        for name in INSTALLERS:
            body = self.bodies[name]
            with self.subTest(installer=name):
                self.assertIn("setup_greetd_pam.sh was not found", body)
                self.assertIn("greetd PAM setup failed", body)
                self.assertNotIn("exit 1", body)

    def test_the_greetd_config_is_backed_up_before_it_is_replaced(self):
        for name in INSTALLERS:
            with self.subTest(installer=name):
                self.assertIn('cp -a "$greetd_config_file" "$greetd_config_file.bak.',
                              self.bodies[name])


class ThePaletteContractHolds(unittest.TestCase):
    """Sixteen colours, all of them, from every palette this repository ships.

    The greeter's palette has to be complete or the Synced scheme is not selected
    at all, and the privileged helper refuses a staged sync.toml whose palette is
    incomplete. So a palette file missing one role does not degrade the login
    screen -- it breaks the sync, on the machine, with the reason visible only in
    the helper's output.
    """

    def setUp(self):
        self.contract = RECORD["palette_contract"]
        self.mapping = self.contract["mapping"]

    def test_the_contract_names_the_sixteen_keys_the_greeter_requires(self):
        self.assertEqual(REQUIRED_PALETTE_KEYS, list(self.mapping))

    def test_the_contract_targets_are_the_palette_fields_the_shell_record_declares(self):
        # Two records, written against two different releases, naming the same
        # sixteen colours in the same order.
        self.assertEqual(SHELL_SURFACE["palette"]["fields"], list(self.mapping.values()))

    def test_the_mapping_is_one_to_one(self):
        self.assertEqual(len(set(self.mapping.values())), len(self.mapping))

    def test_every_shipped_palette_can_produce_a_complete_sync(self):
        self.assertGreaterEqual(len(PALETTES), 4)
        for path in PALETTES:
            palette = json.loads(path.read_text(encoding="utf-8"))
            for mode in SHELL_SURFACE["palette"]["modes"]:
                block = palette[mode]
                for greeter_key, palette_key in self.mapping.items():
                    with self.subTest(palette=path.name, mode=mode, key=greeter_key):
                        self.assertIn(palette_key, block)
                        self.assertRegex(block[palette_key], HEX_COLOR)

    def test_the_two_renamed_roles_are_the_non_obvious_ones(self):
        # surface_variant and outline come back round: the palette file's names,
        # through runtime roles the shell no longer calls that, to the greeter's
        # older names for them.
        self.assertEqual("mSurfaceVariant", self.mapping["surface_variant"])
        self.assertEqual("mOutline", self.mapping["outline"])
        for role in ("surface_container", "outline_variant"):
            with self.subTest(role=role):
                self.assertIn(role, self.contract["round_trip_note"])

    def test_the_terminal_palette_is_not_part_of_the_contract(self):
        self.assertNotIn("terminal", self.mapping.values())
        self.assertIn("terminal", self.contract["dropped_keys_note"])
        for path in PALETTES:
            with self.subTest(palette=path.name):
                self.assertIn("terminal", json.loads(path.read_text(encoding="utf-8"))["dark"])

    def test_the_corner_radius_the_login_screen_inherits_is_a_derived_number(self):
        # Sync copies [shell] corner_radius_scale, so the greeter's radius scale
        # is this repository's own derived value and has to sit inside the range
        # the greeter honours.
        shipped = CONFIG["shell"]["corner_radius_scale"]
        self.assertEqual(noctalia.corner_radius_scale(TOKENS), shipped)
        low, high = RECORD["greeter_toml"]["sections"]["appearance"]["keys"][
            "corner_radius_scale"]["range"]
        self.assertLessEqual(low, shipped)
        self.assertGreaterEqual(high, shipped)
        self.assertIn("corner_radius_scale", RECORD["motion"]["corner_radius_note"])


class NothingIsShippedForTheLoginScreen(unittest.TestCase):
    """The absence, asserted -- and the renderer's refusal, which enforces it."""

    def setUp(self):
        self.doc = noctalia.render_config(TOKENS, noctalia.load_preset(noctalia.DEFAULT_PRESET),
                                          TOKENS["default_intensity"])

    def test_no_greeter_toml_is_committed(self):
        self.assertEqual([], [p.relative_to(ROOT).as_posix()
                              for p in ROOT.rglob("greeter.toml") if ".git" not in p.parts])

    def test_no_payload_file_configures_the_greeter(self):
        hits = []
        for path in sorted((ROOT / ".config").rglob("*")):
            if path.is_file() and path.suffix in (".lua", ".toml", ".conf", ".json", ".css"):
                text = path.read_text(encoding="utf-8", errors="replace")
                if "/var/lib/noctalia-greeter" in text or "greeter.toml" in text:
                    hits.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], hits)

    def test_the_staging_list_ships_nothing_greeter_related(self):
        staged = (ROOT / "lib" / "stage-v5-config.sh").read_text(encoding="utf-8")
        self.assertNotIn("greeter", staged)

    def test_the_payload_leaves_auto_sync_at_its_default(self):
        self.assertNotIn("greeter_sync", CONFIG["shell"])
        self.assertFalse(RECORD["sync"]["auto_sync"]["default"])
        self.assertIn("auto_sync", RECORD["sync"]["auto_sync"]["key"])

    def test_the_payload_leaves_the_polkit_agent_to_the_session(self):
        self.assertNotIn("polkit_agent", CONFIG["shell"])
        self.assertFalse(RECORD["not_shipped"]["shell_polkit_agent"]["default"])
        startup = (ROOT / ".config" / "hypr" / "startup.lua").read_text(encoding="utf-8")
        self.assertIn("polkit-gnome-authentication-agent-1", startup)
        self.assertIn("startup.lua", RECORD["not_shipped"]["shell_polkit_agent"]["why"])

    def test_the_renderer_refuses_a_withheld_key_and_says_why(self):
        for key, table in (("greeter_sync", {"auto_sync": True}), ("polkit_agent", True)):
            mutated = json.loads(json.dumps(self.doc))
            mutated["shell"][key] = table
            problems = noctalia.validate(mutated, SHELL_SURFACE)
            with self.subTest(key=key):
                self.assertEqual(1, len(problems))
                self.assertIn(f"shell.{key}", problems[0])
                self.assertIn("withholds it on purpose", problems[0])
                # The dishonest version of this message claimed upstream had no
                # such setting, which for these two keys is false.
                self.assertNotIn("has no such setting", problems[0])

    def test_the_withheld_entries_point_at_entries_that_exist(self):
        withheld = SHELL_SURFACE["sections"]["shell"]["withheld"]
        self.assertEqual({"polkit_agent", "greeter_sync"}, set(withheld))
        for key, entry in withheld.items():
            with self.subTest(key=key):
                self.assertEqual("data/design/greeter.json", entry["recorded_in"])
                node: Any = RECORD
                for part in entry["where"].split("."):
                    self.assertIn(part, node, f"{entry['where']} does not resolve")
                    node = node[part]
                # The pointer has to land on the entry about this setting, and
                # both texts have to give a reason long enough to stand alone.
                self.assertIn(key, json.dumps(node))
                self.assertGreater(len(entry["reason"]), 100)
                self.assertRegex(entry["source"], r"\.(cpp|h)(:|$|[ ,)])")

    def test_an_absent_key_still_reports_the_upstream_behaviour(self):
        mutated = json.loads(json.dumps(self.doc))
        mutated["shell"]["nonsense"] = 1
        problems = noctalia.validate(mutated, SHELL_SURFACE)
        self.assertEqual(1, len(problems))
        self.assertIn("has no such setting", problems[0])
        self.assertIn("unknown setting", problems[0])

    def test_each_omission_carries_a_reason_and_not_a_phrase(self):
        for key, entry in RECORD["not_shipped"].items():
            if key == "note":
                continue
            with self.subTest(omission=key):
                self.assertGreater(len(entry["why"]), 200,
                                   "the reason has to survive being read on its own")

    def test_the_record_says_what_the_surface_cannot_do(self):
        joined = " ".join(RECORD["not_in_greeter"]).lower()
        for absent in ("motion", "blur", "radius", "password", "idle"):
            with self.subTest(absent=absent):
                self.assertIn(absent, joined)


class TheLoginScreenHasNoMotionSurface(unittest.TestCase):
    """The one surface in this stack that the motion presets cannot reach."""

    def test_no_recorded_key_is_a_motion_setting(self):
        for path, spec in all_variables():
            name = path.rsplit(".", 1)[-1]
            with self.subTest(key=path):
                for fragment in ("duration", "easing", "animation", "motion", "speed",
                                 "_ms", "transition"):
                    self.assertNotIn(fragment, name)

    def test_the_easings_are_the_compiled_in_set(self):
        self.assertEqual(EASINGS, RECORD["motion"]["easings"])
        self.assertIn("animation.h", RECORD["motion"]["easings_source"])

    def test_the_overshoot_is_recorded_as_unreachable(self):
        note = RECORD["motion"]["overshoot_note"]
        self.assertIn("EaseOutBack", note)
        self.assertIn("1.70158", note)
        for unreached in ("reduce-motion", "Performance"):
            with self.subTest(unreached=unreached):
                self.assertIn(unreached, note)

    def test_the_declared_transition_enum_has_no_reader(self):
        note = RECORD["motion"]["wallpaper_transition_note"]
        self.assertIn("WallpaperTransition", note)
        self.assertIn("config_types.h", note)
        self.assertIn("no reader", note.lower())

    def test_the_lock_screen_pins_one_effect_while_the_greeter_offers_none(self):
        # Recorded on both sides so the contrast is not implied by an absence:
        # the shell randomizes among eleven effects and this project pins one,
        # while the greeter has no effect to pin and no key to pin it with.
        transition = SHELL_SURFACE["sections"]["lockscreen"]["keys"]["transition"]
        self.assertEqual(11, len(transition["enum"]))
        self.assertIn("AT RANDOM", transition["note"])
        self.assertEqual(["fade"], CONFIG["lockscreen"]["transition"])
        self.assertIn("no motion settings at all", RECORD["not_in_greeter"][0].lower())


class SyncIsTheOnlyWayAppearanceArrives(unittest.TestCase):
    """What Sync carries, what it refuses to, and what it costs."""

    def setUp(self):
        self.sync = RECORD["sync"]

    def test_the_ipc_command_is_recorded_with_its_replies(self):
        self.assertEqual("noctalia msg greeter-sync", self.sync["ipc"]["command"])
        for reply in ("already in progress", "not installed", "staged"):
            with self.subTest(reply=reply):
                self.assertIn(reply, self.sync["ipc"]["note"])

    def test_the_helper_is_negotiated_with_before_anything_is_staged(self):
        self.assertEqual(["Unknown", "Legacy", "SecureSyncV1"], self.sync["helper_protocol"]["values"])
        self.assertIn("--sync <staging-directory>", self.sync["helper_protocol"]["source"])
        self.assertIn("before staging anything", self.sync["helper_protocol"]["note"])

    def test_what_is_copied_and_what_is_excluded_do_not_overlap(self):
        copies = {item.lower() for item in self.sync["copies"]}
        excludes = {item.lower() for item in self.sync["excludes"]}
        self.assertEqual(set(), copies & excludes)
        self.assertIn("the palette, as the greeter's own sixteen keys", copies)
        self.assertTrue(any("corner_radius_scale" in item for item in copies))
        self.assertTrue(any("time_format" in item for item in excludes))
        self.assertTrue(any("cursor theme" in item for item in excludes))

    def test_the_font_is_left_empty_so_the_greeter_keeps_its_own(self):
        self.assertEqual("", CONFIG["shell"]["font_family"])
        note = RECORD["greeter_toml"]["sections"]["appearance"]["keys"]["font_family"]["note"]
        self.assertIn("only when", note)
        self.assertIn("Fontconfig", note)

    def test_the_packaged_polkit_action_requires_administration(self):
        authorization = self.sync["authorization"]
        self.assertEqual("org.noctalia.greeter.sync-appearance", authorization["action_id"])
        self.assertEqual(3, authorization["defaults"].count("auth_admin"))
        self.assertIn("--sync", authorization["matches_only"])
        self.assertIn("1.3.1", authorization["legacy_action_warning"])
        self.assertIn("1.5.0", authorization["version_requirement"])

    def test_the_constrained_sync_excludes_the_session_payload_too(self):
        # The same decision from two directions: the shell payload ships no
        # session power commands, and the constrained sync would not carry them.
        note = RECORD["sync_toml"]["session_payload_note"]
        self.assertIn("deliberately excludes", note)
        self.assertNotIn("session", CONFIG["shell"].get("session", {}) and "power" or "")

    def test_the_login_screen_blanks_on_its_own_timer(self):
        idle = RECORD["greeter_toml"]["sections"]["idle"]
        self.assertIn("third idle subsystem", idle["note"])
        self.assertIn("does not reset it", idle["keys"]["timeout"]["note"])
        self.assertIn("NOCTALIA_GREETER_IDLE_TIMEOUT", idle["keys"]["timeout"]["env_override"])
        # The shell's idle behaviors are the other two, and they are configured.
        self.assertIn("lock", CONFIG["idle"]["behavior"])
        self.assertIn("screen_off", CONFIG["idle"]["behavior"])

    def test_the_keyboard_does_not_follow_the_session(self):
        keyboard = RECORD["greeter_toml"]["sections"]["keyboard"]
        self.assertIn("does not read the session compositor", keyboard["note"])
        self.assertIn("inputs.lua", keyboard["note"])
        inputs = (ROOT / ".config" / "hypr" / "inputs.lua").read_text(encoding="utf-8")
        self.assertIn('kb_layout = "us"', inputs)

    def test_the_clock_formats_are_not_synced_and_the_difference_is_recorded(self):
        clock = RECORD["greeter_toml"]["sections"]["clock"]["keys"]
        self.assertEqual(CONFIG["shell"]["time_format"], clock["time_format"]["default"])
        self.assertNotEqual(CONFIG["shell"]["date_format"], clock["date_format"]["default"])
        self.assertIn("abbreviated weekday", clock["date_format"]["note"])


if __name__ == "__main__":
    unittest.main()
