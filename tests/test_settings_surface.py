#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for the surface the settings application is allowed to use.

``data/design/adwaita.json`` is a closed record: a widget, a style class, a named
colour, a CSS property, a pseudo-class, an icon name or an API call that is not
listed there is not used. This test is what makes "closed" mean something, because
GTK cannot be imported in this repository's CI -- there is no display and no
libadwaita in the sandbox -- so a widget that does not exist would not fail here,
it would fail on somebody's desktop.

Both directions are checked, and the second is the one that catches the quiet
failure:

* **Code to record.** Every icon name, style class and toolkit identifier the
  package's source names has to be in the record, and every icon a page plan
  carries has to be one the record verified against adwaita-icon-theme 48.1.
* **Record to code.** Every ``iarch-*`` class the record lists has to be defined by
  ``style/glass.css``, and every class that stylesheet defines has to be listed in
  the record. A stylesheet that defines a class no page uses is a style nobody can
  reach; a page that uses a class no stylesheet defines is a row that renders
  unstyled and looks like a bug in the toolkit.

The CSS is read with its comments and at-rules stripped first, and that is not
cosmetic: an unstripped scan finds ``:radius`` and ``@media`` in the prose that
explains the sheet, and a test that fails on a comment teaches everybody to ignore
it.

Two things this test asserts are findings rather than bookkeeping. The About
dialog's ``add_other_app`` is recorded as rejected because it needs libadwaita 1.7
while the record's floor is 1.6, and ``@media`` is recorded as rejected because
GTK's own property document puts CSS media queries at 4.20 while the floor here is
4.10 -- so the reduce-motion lever in ``glass.css`` is a style class the window
adds, which works on every supported release.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

from iarch_settings import pages as registry  # noqa: E402
from iarch_settings.pages import plan as plan_module  # noqa: E402
from iarch_settings.services import contacts, noctalia  # noqa: E402

RECORD = json.loads((ROOT / "data" / "design" / "adwaita.json").read_text(encoding="utf-8"))
GLASS_CSS = ROOT / "iarch" / "settings-app" / "iarch_settings" / "style" / "glass.css"
PACKAGE = ROOT / "iarch" / "settings-app" / "iarch_settings"

ICONS: Dict[str, str] = RECORD["icons"]["names"]
STYLE_CLASSES: List[str] = RECORD["style_classes"]["names"]
WIDGETS: List[str] = [entry["name"] for entry in RECORD["widgets"]]
API: List[Dict[str, Any]] = RECORD["api"]
REJECTED: List[Dict[str, Any]] = RECORD["rejected"]
PORTABILITY: List[Dict[str, Any]] = RECORD["portability"]
NAMED_COLOURS: List[str] = RECORD["named_colors"]["names"]
CSS_PROPERTIES: List[str] = RECORD["css_properties"]["names"]
PSEUDO_CLASSES: List[str] = RECORD["pseudo_classes"]["names"]

#: The classes this project invented, as opposed to libadwaita's own.
IARCH_CLASSES = [name for name in STYLE_CLASSES if name.startswith("iarch-")]

#: An at-rule keyword is not a named colour, and the difference is one character.
AT_RULES = ("media", "supports", "import", "define-color", "keyframes", "charset")

CONTEXT = plan_module.default_context()
PLANS: Dict[str, Any] = {page_id: registry.build(page_id, CONTEXT)
                         for page_id in registry.PAGE_IDS}


def source_files() -> List[Path]:
    """Every Python file in the package, so a name in any of them is checked."""
    return sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts)


def plan_rows() -> Iterable[Tuple[str, Any]]:
    """Every row on every page, labelled with the page it is on."""
    for page_id, built in PLANS.items():
        for row in built.walk():
            yield page_id, row


def css_text() -> str:
    """The stylesheet with its comments removed.

    A comment in this file explains what a property is for and quotes several, so a
    scan that reads comments finds names the sheet does not use.
    """
    return re.sub(r"/\*.*?\*/", "", GLASS_CSS.read_text(encoding="utf-8"), flags=re.S)


def css_rules() -> str:
    """The stylesheet with comments *and* at-rules removed.

    ``@media`` and ``@define-color`` are rules about rules; scanning them as though
    they were colour references is how a test ends up asserting that ``media`` is a
    colour libadwaita defines.
    """
    text = css_text()
    # The lookahead is the whole trick: `@media` is followed by a space and is an at-rule,
    # while `@card_bg_color` is followed by an underscore and is a colour. Without it the
    # substitution stops at the underscore and turns a colour into " _bg_color".
    return re.sub(r"@[a-z-]+(?![a-z0-9_-])", " ", text)


def css_classes_defined() -> Set[str]:
    """The class names ``glass.css`` defines, read out of its selectors."""
    return set(re.findall(r"\.([A-Za-z][A-Za-z0-9_-]*)", css_rules()))


def css_properties_used() -> Set[str]:
    """The property names ``glass.css`` declares."""
    found: Set[str] = set()
    for line in css_rules().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("@") or "{" in stripped or "}" in stripped:
            continue
        match = re.match(r"^(-?[a-z][a-z0-9-]*)\s*:", stripped)
        if match:
            found.add(match.group(1))
    return found


def css_pseudo_classes_used() -> Set[str]:
    """The pseudo-classes ``glass.css`` matches on."""
    return set(re.findall(r":([a-z][a-z-]+)", css_rules()))


def named_colours_used() -> Set[str]:
    """The ``@name`` colour references in the sheet, with the at-rules taken out."""
    return {match.group(1) for match in re.finditer(r"@([a-z][a-z0-9_]*)(?![a-z0-9_-])",
                                                    css_rules())}


def toolkit_names_in_source() -> Set[str]:
    """Every ``Gtk.Something`` and ``Adw.Something`` the package's source names.

    Read out of the syntax tree rather than with a regular expression, because a
    regex would also match the same words inside a docstring explaining what a
    widget is -- and a docstring may name a widget this code deliberately does not
    use, which is what the record's ``rejected`` block is for.
    """
    found: Set[str] = set()
    namespaces = ("Gtk", "Adw", "Gio", "GLib", "Gdk", "Pango", "Graphene")
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            value = node.value
            if isinstance(value, ast.Name) and value.id in namespaces:
                found.add(f"{value.id}.{node.attr}")
    return found


def rejected_spelling(fragment: str) -> Optional[Dict[str, Any]]:
    """The record's rejection entry whose spelling mentions ``fragment``."""
    for entry in REJECTED:
        if fragment in str(entry.get("spelling") or ""):
            return entry
    return None


class TestTheRecordItself(unittest.TestCase):
    """The record has to be usable as a closed list before it can close anything."""

    def test_every_widget_and_api_entry_carries_the_ref_it_was_read_from(self):
        for key in ("widgets", "api"):
            with self.subTest(block=key):
                for entry in RECORD[key]:
                    self.assertTrue(str(entry.get("evidence") or "").strip(),
                                    f"{key} entry {entry} has no evidence line")

    def test_the_surface_blocks_carry_evidence_as_a_block(self):
        for key in ("style_classes", "named_colors", "css_properties", "pseudo_classes",
                    "icons"):
            with self.subTest(block=key):
                self.assertTrue(str(RECORD[key].get("evidence") or "").strip(),
                                f"{key} has no evidence line")

    def test_minimum_versions_say_why_they_are_the_floor(self):
        for name, block in RECORD["minimum_versions"].items():
            with self.subTest(component=name):
                self.assertTrue(str(block.get("why") or "").strip(),
                                f"{name} has a version and no reason for it")

    def test_the_introspection_namespaces_carry_a_version_and_evidence(self):
        for entry in RECORD["introspection"]:
            with self.subTest(namespace=entry["namespace"]):
                self.assertTrue(str(entry.get("version") or "").strip())
                self.assertTrue(str(entry.get("evidence") or "").strip())

    def test_every_rejection_says_what_rejects_it(self):
        self.assertTrue(REJECTED, "the record claims nothing was rejected, which would mean "
                                  "every call in a header was usable on the floor")
        for entry in REJECTED:
            with self.subTest(spelling=entry.get("spelling")):
                self.assertTrue(str(entry.get("why") or "").strip(),
                                "a rejection with no reason is a guess")
                self.assertTrue(str(entry.get("evidence") or "").strip())

    def test_every_portability_entry_names_what_this_project_uses_instead(self):
        for entry in PORTABILITY:
            with self.subTest(call=entry.get("call")):
                self.assertTrue(str(entry.get("this_project_uses") or "").strip(),
                                "a known-bad signature with no replacement is a warning "
                                "nobody can act on")

    def test_add_other_app_is_rejected_for_the_version_marker_that_needs_it(self):
        entry = rejected_spelling("add_other_app")
        self.assertIsNotNone(entry, "add_other_app is ADW_AVAILABLE_IN_1_7 while every other "
                                    "call in that header is ADW_AVAILABLE_IN_1_5")
        self.assertIn("1_7", json.dumps(entry), "the reason has to name the version marker")
        self.assertIn("adw-about-dialog.h:176", str(entry["evidence"]))

    def test_the_legal_section_call_takes_four_arguments_in_the_recorded_order(self):
        entry = next(item for item in API
                     if item["call"] == "adw_about_dialog_add_legal_section")
        python = str(entry["python"])
        for argument in ("title", "copyright", "license_type", "license"):
            self.assertIn(argument, python)
        # copyright before license_type: an earlier draft of this record had them the other
        # way round, and a swap there is a dialog that shows a licence as a copyright line.
        self.assertLess(python.index("copyright"), python.index("license_type"),
                        "the recorded argument order does not match the header")
        self.assertIn("adw-about-dialog.h:170", str(entry["evidence"]))

    def test_the_media_query_rejection_names_the_version_that_introduced_it(self):
        """GTK's own table puts media queries at 4.20 and this record's floor is 4.10."""
        entry = rejected_spelling("@media")
        self.assertIsNotNone(entry, "glass.css cannot use @media: GTK's published property "
                                    "document puts CSS Media Queries at 'Since GTK 4.20' and "
                                    "the floor argued in minimum_versions.gtk is 4.10")
        self.assertIn("4.20", str(entry["why"]))
        self.assertIn("css-properties.md", str(entry["evidence"]))
        self.assertEqual("4.10", RECORD["minimum_versions"]["gtk"]["version"],
                         "the rejection is only true while the floor is below 4.20")

    def test_the_stylesheet_does_not_use_the_rejected_at_rule(self):
        text = GLASS_CSS.read_text(encoding="utf-8")
        self.assertNotIn("@media", css_rules(),
                         "the sheet uses an at-rule the record rejects for this GTK floor")
        self.assertIn("iarch-reduce-motion", text,
                      "the reduce-motion lever has to be the class the window adds, since "
                      "the media query is the one that does not work on the floor")


class TestIconsAgainstTheRecord(unittest.TestCase):
    """An icon name is a filename in a theme this project does not ship."""

    def test_every_icon_a_page_plan_carries_is_verified(self):
        for page_id, row in plan_rows():
            if not row.icon:
                continue
            with self.subTest(page=page_id, row=row.title):
                self.assertIn(row.icon, ICONS,
                              f"{row.icon} is not in data/design/adwaita.json, so it would "
                              f"render as a missing-image symbol on a desktop")

    def test_every_sidebar_icon_is_verified_and_names_its_own_page(self):
        for spec in registry.PAGES:
            with self.subTest(page=spec.id):
                self.assertIn(spec.icon, ICONS)
                self.assertEqual(ICONS[spec.icon], f"{spec.label} page",
                                 "the record maps each page icon to a sentence naming the "
                                 "page, so a renamed page and a stale record disagree here")

    def test_every_banner_icon_is_verified(self):
        for page_id, built in PLANS.items():
            for banner in built.banners:
                if not banner.icon:
                    continue
                with self.subTest(page=page_id):
                    self.assertIn(banner.icon, ICONS)

    def test_the_contact_records_icons_are_verified_too(self):
        """``data/contacts.default.json`` carries icon names, and they are drawn."""
        data, problems = contacts.load()
        self.assertEqual([], problems)
        seen = 0
        for row in data.get("rows") or []:
            icon = str(row.get("icon") or "")
            if not icon:
                continue
            seen += 1
            with self.subTest(kind=row.get("kind")):
                self.assertIn(icon, ICONS)
        self.assertGreater(seen, 0, "the contact record carries no icon at all")

    def test_icon_sentence_reads_the_records_copy_not_the_registrys(self):
        for spec in registry.PAGES:
            with self.subTest(page=spec.id):
                self.assertEqual(registry.icon_sentence(spec.id), f"{spec.label} page")


class TestStyleClassesBothWays(unittest.TestCase):
    """The seven ``iarch-*`` classes are this project's, so both sides must agree."""

    def test_every_iarch_class_the_record_lists_is_defined_by_the_stylesheet(self):
        defined = css_classes_defined()
        for name in IARCH_CLASSES:
            with self.subTest(style_class=name):
                self.assertIn(name, defined,
                              f"{name} is listed in the record but glass.css does not define "
                              f"it, so a page that asks for it renders unstyled")

    def test_every_iarch_class_the_stylesheet_defines_is_listed_in_the_record(self):
        listed = set(STYLE_CLASSES)
        defined = [name for name in css_classes_defined() if name.startswith("iarch-")]
        self.assertTrue(defined, "glass.css defines no iarch-* class at all")
        for name in sorted(defined):
            with self.subTest(style_class=name):
                self.assertIn(name, listed,
                              f"glass.css defines {name} and the record does not list it, so "
                              f"the record is not the closed list it claims to be")

    def test_the_stylesheet_uses_only_properties_gtk_parses(self):
        used = css_properties_used()
        self.assertIn("transition-duration", used, "the scan found no property at all")
        for name in sorted(used):
            with self.subTest(property=name):
                self.assertIn(name, CSS_PROPERTIES,
                              f"{name} is not in the recorded property table, so GTK would "
                              f"warn and drop it")

    def test_transition_delay_is_recorded_because_two_sheets_use_it(self):
        self.assertIn("transition-delay", CSS_PROPERTIES,
                      "GTK's published table lists transition-delay beside the other three "
                      "transition longhands, and glass.css uses it")

    def test_the_stylesheet_uses_only_recorded_pseudo_classes(self):
        allowed = set(PSEUDO_CLASSES)
        for name in sorted(css_pseudo_classes_used()):
            with self.subTest(pseudo_class=name):
                self.assertIn(name, allowed,
                              f":{name} is not in the recorded pseudo-class table, so the "
                              f"selector would never match")

    def test_the_stylesheet_uses_only_recorded_named_colours(self):
        used = named_colours_used()
        self.assertIn("card_bg_color", used, "the scan found no named colour at all")
        allowed = set(NAMED_COLOURS)
        for name in sorted(used):
            with self.subTest(named_colour=name):
                self.assertIn(name, allowed,
                              f"@{name} is not a colour libadwaita defines, so the value "
                              f"would be unresolved and the declaration dropped")

    def test_the_stylesheet_contains_no_colour_literal(self):
        """Every colour is a named one, so the sheet follows the preset and the mode."""
        body = css_rules()
        for match in re.finditer(r"#[0-9a-fA-F]{3,8}\b", body):
            self.fail(f"glass.css carries the colour literal {match.group(0)}: a literal "
                      f"cannot follow a colour preset or a light/dark switch")
        for match in re.finditer(r"\brgba?\(", body):
            self.fail(f"glass.css carries {match.group(0)}: an rgba() literal is a colour "
                      f"this sheet chose for itself")

    def test_a_page_style_class_is_a_recorded_class(self):
        listed = set(STYLE_CLASSES)
        for page_id, built in PLANS.items():
            for name in built.styles:
                with self.subTest(page=page_id, where="page"):
                    self.assertIn(name, listed)
            for row in built.walk():
                for name in row.style_classes:
                    with self.subTest(page=page_id, row=row.title):
                        self.assertIn(name, listed)


class TestToolkitNamesInCode(unittest.TestCase):
    """A widget the code names has to be one the record read out of a header."""

    def test_every_toolkit_name_in_the_package_is_recorded(self):
        widgets = set(WIDGETS)
        api_python = {str(entry["python"]).split("(")[0] for entry in API}
        for name in sorted(toolkit_names_in_source()):
            namespace, attribute = name.split(".", 1)
            with self.subTest(name=name):
                known = (name in widgets or name in api_python
                         or any(entry["call"].endswith("_" + _snake(attribute))
                                for entry in API)
                         or namespace in ("Gio", "GLib", "Gdk", "Pango", "Graphene"))
                self.assertTrue(known,
                                f"{name} is named in the package's source and is not in "
                                f"data/design/adwaita.json")

    def test_the_record_lists_the_widgets_a_preferences_window_is_built_from(self):
        for name in ("Adw.Application", "Adw.NavigationPage", "Adw.PreferencesGroup",
                     "Adw.ActionRow", "Adw.SwitchRow", "Adw.ComboRow", "Adw.SpinRow",
                     "Adw.EntryRow", "Adw.ExpanderRow", "Adw.Banner", "Adw.AboutDialog",
                     "Adw.ToastOverlay", "Gtk.FlowBox", "Gtk.CssProvider"):
            with self.subTest(widget=name):
                self.assertIn(name, WIDGETS,
                              f"{name} is what this window is built from and the record does "
                              f"not list it")


def _snake(name: str) -> str:
    """``AddLegalSection`` as ``add_legal_section``, for matching a C call name."""
    out = []
    for index, character in enumerate(name):
        if character.isupper() and index:
            out.append("_")
        out.append(character.lower())
    return "".join(out)


class TestTheOfferedSurfaceIsTheRecordedSurface(unittest.TestCase):
    """Counts a record and a page must not drift apart on."""

    def test_the_settings_document_offers_exactly_the_paths_a_page_can_own(self):
        found = plan_module.settings_paths()
        self.assertEqual(34, len(found),
                         "the settings document and the plan's walk of it disagree about how "
                         "many paths exist, which means a section was added to one and not "
                         "the other")
        self.assertEqual(len(set(found)), len(found), "a path is offered twice")

    def test_the_fonts_page_offers_exactly_the_writable_gtk_keys(self):
        from iarch_settings.pages import fonts
        from iarch_settings.services import gtk_settings

        self.assertEqual(9, len(fonts.OFFERED),
                         "data/design/gtk-settings.json records nine keys this project "
                         "writes, and the Fonts & Icons page offers a different number")
        # The two lists are not the same vocabulary and are not the same length, and both
        # facts are the point: `ui_family` and `size_pt` are the two halves of the single
        # `gtk-font-name` string, so neither maps to a key on its own, and
        # `gtk-application-prefer-dark-theme` is writable but comes from `theme.colour_mode`
        # rather than from a fonts setting at all.
        halves = set(gtk_settings.FONT_NAME_SETTINGS)
        one_to_one = [setting for setting in fonts.OFFERED if setting not in halves]
        self.assertEqual(sorted(gtk_settings.KEY_BY_SETTING), sorted(one_to_one),
                         "every offered fonts setting maps to exactly one GtkSettings key, "
                         "except the two halves of gtk-font-name")
        expected = sorted(set(gtk_settings.KEY_BY_SETTING.values())
                          | {"gtk-font-name", gtk_settings.DARK_KEY})
        self.assertEqual(expected, sorted(gtk_settings.writable_keys()),
                         "the writable list is the seven one-to-one keys, the font-name key "
                         "the two halves build, and the dark-theme key the colour mode "
                         "writes")
        self.assertEqual(2, len(halves & set(fonts.OFFERED)))

    def test_the_bar_page_offers_the_recorded_shell_keys_and_no_more(self):
        from iarch_settings.pages import bar

        self.assertEqual(53, len(bar.OFFERED),
                         "the shell's bar and dock keys are 49 this page writes and 4 it "
                         "shows without writing")
        self.assertEqual(4, len(bar.READ_ONLY))
        self.assertEqual(49, len([path for path in bar.OFFERED
                                  if path not in bar.READ_ONLY]),
                         "OFFERED is everything the page draws, so the writable count is the "
                         "total minus the read-only ones")
        for path, reason in bar.READ_ONLY.items():
            with self.subTest(key=path):
                self.assertGreater(len(reason.split()), 6,
                                   "a read-only key needs a reason a person can read")

    def test_every_shell_key_the_record_declares_is_reachable(self):
        """Part 4's acceptance: every visual switch in the product is reachable."""
        named: Set[str] = set()
        for _page_id, row in plan_rows():
            named.update(row.keywords)
        tables = set(noctalia.table_paths())
        under_a_named_table = {path for path in noctalia.known_paths()
                               if any(path.startswith(table + ".") for table in tables)}
        missing = sorted(set(noctalia.known_paths()) - named - under_a_named_table)
        self.assertEqual([], missing,
                         "the shell declares a key that no page writes, no page shows and no "
                         "page names: a value only a text editor can change")

    def test_a_table_is_named_by_a_page_and_is_not_a_leaf_key(self):
        """A table is pointed at, not drawn, and the pointing has to exist."""
        named: Set[str] = set()
        for _page_id, row in plan_rows():
            named.update(row.keywords)
        known = set(noctalia.known_paths())
        for path in noctalia.table_paths():
            with self.subTest(table=path):
                self.assertNotIn(path, known, "a table is not a leaf key, so config_set "
                                              "would have nothing to write to it")
                container = path.split(".")[0]
                self.assertTrue(any(keyword.startswith(container) for keyword in named),
                                f"no page names the container {path} belongs to")

    def test_no_page_names_a_shell_key_the_record_does_not_declare(self):
        known = set(noctalia.known_paths())
        for page_id, row in plan_rows():
            for keyword in row.keywords:
                if "." not in keyword:
                    continue
                container = keyword.split(".")[0]
                if container not in ("shell", "bar", "dock", "audio", "idle", "lockscreen",
                                     "theme", "wallpaper", "notification", "control_center"):
                    continue
                with self.subTest(page=page_id, row=row.title, keyword=keyword):
                    self.assertTrue(keyword in known or keyword in noctalia.table_paths(),
                                    f"{keyword} looks like a shell config path and the record "
                                    f"does not declare it")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
