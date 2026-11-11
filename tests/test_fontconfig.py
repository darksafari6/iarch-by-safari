#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the fontconfig renderer, ``iarch/cli/gen_fontconfig.py``.

fontconfig hides its mistakes the way the other engines do: it warns about an
element or attribute it does not know and keeps loading, and a family that
matches no installed font is simply never selected. So these tests assert against
the configuration DTD recorded in ``data/design/fontconfig.json`` rather than a
frozen snapshot of the XML:

* every element and attribute the file uses is one the DTD declares, with a value
  inside its enumeration;
* every family it prefers is one the design tokens name -- nothing is invented,
  and the generic families (sans-serif, monospace) are targets, not faces;
* the user-interface face leads ``sans-serif``, the terminal face leads
  ``monospace``, and the token's fallback chain follows both in order, so a glyph
  the primary face lacks still resolves;
* ``serif`` is left alone, because the tokens name no serif face;
* the file is well-formed XML whose first line is an XML comment, not the ``#``
  a kitty ``.conf`` uses;
* a refused render writes nothing, and a failed write restores every byte.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.cli import gen_fontconfig as fc  # noqa: E402
from iarch.lib import configstore  # noqa: E402

TOKENS = fc.load_tokens()
SURFACE = fc.load_surface()
FONT = TOKENS["font"]


def document() -> str:
    return fc.build_document(TOKENS, SURFACE)


def rendered() -> str:
    return fc.rendered_text(fc.REPO_CONF, document())


def families_under(tag: str) -> List[str]:
    """Every <family> text inside the first <prefer> of the alias for ``tag``."""
    root = ET.fromstring(rendered())
    for alias in root.findall("alias"):
        generic = alias.find("family")
        if generic is not None and generic.text == tag:
            prefer = alias.find("prefer")
            return [f.text for f in prefer.findall("family")]
    return []


# --------------------------------------------------------------- the surface


class SurfaceIsTheFontconfigDtd(unittest.TestCase):
    def test_the_vocabulary_is_sized_like_the_dtd(self):
        self.assertGreaterEqual(len(SURFACE["elements"]), 40)
        for element in ("fontconfig", "alias", "family", "prefer", "match", "test", "edit"):
            self.assertIn(element, SURFACE["elements"])

    def test_the_surface_is_pinned_to_a_version_and_a_commit(self):
        verified = SURFACE["verified_against"]
        self.assertRegex(verified["version"], r"^\d+\.\d+\.\d+$")
        self.assertRegex(verified["commit"], r"^[0-9a-f]{40}$")
        self.assertIn("fonts.dtd", SURFACE["source"])

    def test_every_emitted_element_is_declared(self):
        for element in SURFACE["emitted_elements"]:
            self.assertIn(element, SURFACE["elements"])

    def test_the_alias_attribute_enumeration_is_recorded(self):
        binding = SURFACE["elements"]["alias"]["attributes"]["binding"]
        self.assertEqual(["weak", "strong", "same"], binding["values"])

    def test_diagnostics_explain_why_a_typo_is_not_enough(self):
        self.assertIn("unknown element", SURFACE["diagnostics"]["unknown_element"])
        self.assertIn("never selected", SURFACE["diagnostics"]["uninstalled_family"])

    def test_the_mapping_says_what_fills_each_generic(self):
        self.assertIn("ui", SURFACE["mapping"]["sans-serif"])
        self.assertIn("mono", SURFACE["mapping"]["monospace"])
        self.assertIn("no serif", SURFACE["mapping"]["serif"])


# --------------------------------------------------------------- the vocabulary


class EveryEmittedElementIsInTheDtd(unittest.TestCase):
    def test_the_rendered_file_validates(self):
        self.assertEqual([], fc.validate(rendered(), TOKENS, SURFACE))

    def test_every_element_used_is_declared(self):
        root = ET.fromstring(rendered())
        for node in root.iter():
            self.assertIn(node.tag, SURFACE["elements"])

    def test_the_alias_uses_a_valid_binding(self):
        root = ET.fromstring(rendered())
        for alias in root.findall("alias"):
            self.assertIn(alias.get("binding"), ["weak", "strong", "same"])

    def test_an_unknown_element_is_refused(self):
        bad = rendered().replace("<prefer>", "<favourite>", 1).replace("</prefer>", "</favourite>", 1)
        self.assertTrue(any("not an element" in p for p in fc.validate(bad, TOKENS, SURFACE)))

    def test_an_unknown_attribute_is_refused(self):
        bad = rendered().replace('<alias binding="strong">', '<alias binding="strong" flavour="mint">', 1)
        self.assertTrue(any("no attribute" in p for p in fc.validate(bad, TOKENS, SURFACE)))

    def test_a_bad_enumerated_value_is_refused(self):
        bad = rendered().replace('binding="strong"', 'binding="tight"', 1)
        self.assertTrue(any("not one of" in p for p in fc.validate(bad, TOKENS, SURFACE)))

    def test_malformed_xml_is_refused(self):
        self.assertTrue(any("not well-formed" in p
                            for p in fc.validate("<fontconfig><alias>", TOKENS, SURFACE)))

    def test_a_wrong_root_is_refused(self):
        self.assertTrue(any("not <fontconfig>" in p
                            for p in fc.validate("<fonts><alias></alias></fonts>", TOKENS, SURFACE)))


# --------------------------------------------------------------- the families


class FamiliesComeFromTheTokens(unittest.TestCase):
    def test_an_invented_family_is_refused(self):
        bad = rendered().replace("<family>Inter</family>", "<family>Comic Sans</family>", 1)
        self.assertTrue(any("not a family the tokens name" in p
                            for p in fc.validate(bad, TOKENS, SURFACE)))

    def test_the_ui_face_leads_sans_serif(self):
        self.assertEqual(FONT["ui"], families_under("sans-serif")[0])

    def test_the_terminal_face_leads_monospace(self):
        self.assertEqual(FONT["mono"], families_under("monospace")[0])

    def test_the_fallback_chain_follows_both_in_token_order(self):
        chain = [entry["family"] for entry in FONT["fallback"]]
        self.assertEqual([FONT["ui"], *chain], families_under("sans-serif"))
        self.assertEqual([FONT["mono"], *chain], families_under("monospace"))

    def test_the_script_and_emoji_fallbacks_are_all_present(self):
        sans = families_under("sans-serif")
        for needed in ("Noto Sans CJK SC", "Noto Naskh Arabic", "Noto Nastaliq Urdu",
                       "Noto Color Emoji", "DejaVu Sans"):
            with self.subTest(family=needed):
                self.assertIn(needed, sans)

    def test_serif_is_left_to_the_system(self):
        root = ET.fromstring(rendered())
        generics = [a.find("family").text for a in root.findall("alias")]
        self.assertEqual(["sans-serif", "monospace"], generics)
        self.assertNotIn("serif", generics)

    def test_only_generic_families_are_alias_targets(self):
        root = ET.fromstring(rendered())
        for alias in root.findall("alias"):
            self.assertIn(alias.find("family").text, fc.GENERICS)

    def test_no_family_is_repeated_within_one_alias(self):
        for generic in ("sans-serif", "monospace"):
            fams = families_under(generic)
            self.assertEqual(len(fams), len(set(fams)), generic)


# --------------------------------------------------------------- the XML itself


class TheFileIsXmlFontconfigReads(unittest.TestCase):
    def test_the_header_is_an_xml_comment_not_a_hash(self):
        self.assertTrue(configstore.header_for(fc.REPO_CONF).startswith("<!--"))
        self.assertTrue(configstore.is_header_line(configstore.header_for(fc.REPO_CONF)))

    def test_a_kitty_conf_still_uses_a_hash(self):
        # The fontconfig header is keyed on the filename, so it must not change
        # the "#" every other .conf in the payload uses.
        kitty = ROOT / ".config" / "kitty" / "kitty.conf"
        self.assertTrue(configstore.header_for(kitty).startswith("# "))

    def test_there_is_no_xml_declaration_because_a_comment_leads(self):
        self.assertFalse(rendered().lstrip().startswith("<?xml"))

    def test_there_is_no_doctype_fontconfig_never_reads(self):
        self.assertNotIn("<!DOCTYPE", rendered())

    def test_the_file_is_well_formed(self):
        self.assertEqual("fontconfig", ET.fromstring(rendered()).tag)

    def test_no_line_starts_with_a_hash(self):
        for line in rendered().splitlines():
            self.assertFalse(line.lstrip().startswith("#"), line)


# --------------------------------------------------------------- writing


class RefusesToWriteUnlessEverythingIsValid(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "IARCH_STATE_DIR": str(self.root / "state")}
        # patch.dict restores the environment exactly on stop; a hand-rolled
        # clear()+update() runs its cleanups last-in-first-out and wipes PATH for
        # every later test.
        patcher = unittest.mock.patch.dict(os.environ, self.env)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_file_that_fails_validation_is_refused_before_any_write(self):
        original = fc.validate
        fc.validate = lambda text, tokens, surface: ["<family>Invented</family> is not a token"]
        try:
            with self.assertRaises(fc.FontconfigError) as caught:
                fc.targets_for(TOKENS, SURFACE, self.root / "fontconfig")
        finally:
            fc.validate = original
        self.assertIn("not valid", str(caught.exception))
        self.assertEqual([], list((self.root / "fontconfig").rglob("*"))
                         if (self.root / "fontconfig").exists() else [])

    def test_a_failure_part_way_through_leaves_the_filesystem_as_it_was(self):
        good = self.root / "fontconfig" / "fonts.conf"
        good.parent.mkdir(parents=True)
        good.write_text("<!-- previous -->\n<fontconfig/>\n", encoding="utf-8")
        blocked = self.root / "blocked" / "fonts.conf"
        blocked.parent.mkdir(parents=True)
        os.chmod(blocked.parent, 0o500)
        self.addCleanup(os.chmod, blocked.parent, 0o700)
        with self.assertRaises(OSError):
            fc.write_all([(good, "<fontconfig/>"), (blocked, "x")], self.env)
        self.assertEqual("<!-- previous -->\n<fontconfig/>\n", good.read_text(encoding="utf-8"))
        self.assertFalse(blocked.exists())

    def test_an_existing_file_keeps_its_mode_and_gains_a_backup(self):
        target = self.root / "fonts.conf"
        target.write_text("<!-- previous -->\n<fontconfig/>\n", encoding="utf-8")
        os.chmod(target, 0o640)
        fc.write_all([(target, "<fontconfig/>")], self.env)
        self.assertEqual(0o640, target.stat().st_mode & 0o777)
        self.assertTrue([p for p in (self.root / "state" / "backups").rglob("*") if p.is_file()])


# --------------------------------------------------------------- the shipped payload


class ShippedPayload(unittest.TestCase):
    def tmp_stage(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / "stage"
        dest.mkdir()
        return dest

    def test_the_file_ships_and_validates(self):
        self.assertTrue(fc.REPO_CONF.is_file())
        text = fc.REPO_CONF.read_text(encoding="utf-8")
        self.assertTrue(text.startswith(configstore.header_for(fc.REPO_CONF)))
        self.assertEqual([], fc.validate(text, TOKENS, SURFACE))

    def test_the_shipped_file_is_a_fresh_render_of_the_tokens(self):
        self.assertEqual(rendered(), fc.REPO_CONF.read_text(encoding="utf-8"))

    def test_the_shipped_file_is_readable_and_staged(self):
        self.assertTrue(fc.REPO_CONF.stat().st_mode & 0o044)
        staged = subprocess.run(["bash", str(ROOT / "lib" / "stage-v5-config.sh"),
                                 str(ROOT / ".config"), str(self.tmp_stage())],
                                capture_output=True, text=True)
        self.assertEqual(0, staged.returncode, staged.stderr)


# --------------------------------------------------------------- the command line


class CommandLine(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(ROOT / "iarch" / "cli" / "gen_fontconfig.py"),
                               *args], capture_output=True, text=True, cwd=str(ROOT))

    def test_print_writes_the_document_to_stdout(self):
        result = self.run_cli("--print")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("<fontconfig>", result.stdout)
        self.assertIn(f"<family>{FONT['ui']}</family>", result.stdout)

    def test_check_passes_on_the_shipped_payload(self):
        result = self.run_cli("--check")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("matches a fresh render", result.stdout)

    def test_output_dir_writes_the_file_with_an_xml_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "anywhere"
            result = self.run_cli("--output-dir", str(dest))
            self.assertEqual(0, result.returncode, result.stderr)
            written = dest / "fonts.conf"
            self.assertTrue(written.is_file())
            self.assertTrue(written.read_text(encoding="utf-8").startswith("<!--"))

    def test_help_lists_every_flag(self):
        result = self.run_cli("--help")
        self.assertEqual(0, result.returncode, result.stderr)
        for flag in ("--print", "--write-repo-default", "--check", "--output-dir"):
            self.assertIn(flag, result.stdout)


if __name__ == "__main__":
    unittest.main()
