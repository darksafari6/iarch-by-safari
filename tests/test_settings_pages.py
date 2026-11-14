#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Tests for what the fifteen pages contain, as data.

A page in this application is a **plan** and a **rendering**. Only the rendering
needs GTK, so only the rendering is untestable in a sandbox with no display -- and
``docs/UNVERIFIED.md`` SET-02 says exactly that. Everything a plan can be checked
for is checked here, which is why the plan is required to be complete:

* a row names a setting that exists in ``data/settings.default.json``, or a service
  function that exists in this package, and never an invented one;
* a dropdown's choices come from a record or from a function that resolves;
* a number row carries the bounds it is rendered with, so a page cannot offer a
  value the generator behind it would refuse;
* every settings path is owned by a page, which is how "every visual switch in the
  product is reachable" becomes a build failure rather than a promise;
* nothing in the interface names an upstream project, which is Part 4's other
  acceptance clause, and the About page's legal sections are the one exception.

The upstream-name scan reads the plan rather than the source, and that distinction
is the whole test. A source scan would find the word in an import, in a record's
file name and in a comment explaining why a key belongs to somebody else -- all of
which are correct and none of which a person ever sees. What a person sees is the
title, the subtitle, the choice labels, the confirmation text and the banners, so
that is what gets scanned.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))
sys.path.insert(0, str(ROOT / "tools"))

from iarch_settings import pages as registry  # noqa: E402
from iarch_settings.pages import appearance, plan as plan_module  # noqa: E402
from iarch_settings.services import MODULES as SERVICE_MODULES  # noqa: E402

import naming_audit  # noqa: E402

SETTINGS = json.loads((ROOT / "data" / "settings.default.json").read_text(encoding="utf-8"))
SCHEMA = json.loads((ROOT / "data" / "schemas" / "settings.schema.json").read_text(
    encoding="utf-8"))

CONTEXT = plan_module.default_context()
PLANS: Dict[str, Any] = {page_id: registry.build(page_id, CONTEXT)
                         for page_id in registry.PAGE_IDS}

#: Names an upstream project. The four in the naming audit's own token list, plus the
#: shell's name on its own, because a person does not see ``noctalia-shell`` -- they
#: would see the word the project is known by.
UPSTREAM_TOKENS = tuple(naming_audit.TOKENS) + ("noctalia",)


def all_rows() -> Iterable[Tuple[str, Any]]:
    """Every row on every page, including the ones in a title bar."""
    for page_id, built in PLANS.items():
        for row in built.walk():
            yield page_id, row
        for row in built.header_actions:
            yield page_id, row


def visible_text() -> Iterable[Tuple[str, str, str]]:
    """Every string a person can read, labelled by page and by where it appears.

    Deliberately not the source: an import, a record's file name and a comment that
    explains why a key belongs to somebody else all contain these words, and all
    three are correct.
    """
    for page_id, built in PLANS.items():
        yield page_id, "the page title", built.title
        yield page_id, "the page description", built.description or ""
        for keyword in built.keywords:
            yield page_id, "a page keyword", str(keyword)
        for banner in built.banners:
            yield page_id, "a banner", banner.text
        for group in built.groups:
            yield page_id, "a group title", group.title
            yield page_id, "a group description", group.description or ""
            for row in group.rows:
                yield from _row_text(page_id, row)
        for row in built.header_actions:
            yield from _row_text(page_id, row, where="a title-bar row")


def _row_text(page_id: str, row: Any, where: str = "a row") -> Iterable[Tuple[str, str, str]]:
    yield page_id, f"{where} title", row.title
    yield page_id, f"{where} subtitle", row.subtitle or ""
    yield page_id, f"{where} confirmation", row.confirm or ""
    yield page_id, f"{where} confirmation body", row.confirm_body or ""
    yield page_id, f"{where} placeholder", row.placeholder or ""
    for choice in row.choices or ():
        yield page_id, f"{where} choice", str(choice[1] if isinstance(choice, tuple)
                                                else choice)


def index_text() -> Iterable[Tuple[str, str, str]]:
    """The parts of a search result a person actually reads.

    A search entry's ``text`` field is what gets *matched*, and it is built from the
    keywords as well as the titles. Keywords are index terms and are never drawn, so
    the shell's own name belongs in them -- that is how somebody who knows the name
    finds its keys. What must stay clean is the two fields a result list shows: the
    page's label and the row's title.
    """
    for page_id, built in PLANS.items():
        spec = registry.page(page_id)
        yield page_id, "the sidebar label a result is grouped under", spec.label
        for entry in built.search_entries(CONTEXT):
            yield page_id, "a search result's row name", str(entry.get("row") or "")
            yield page_id, "a search result's group name", str(entry.get("group") or "")


def schema_node(dotted: str) -> Optional[Dict[str, Any]]:
    """The schema's own node for a dotted settings path, or ``None``."""
    node: Any = SCHEMA
    for part in dotted.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get("properties", {}).get(part)
        if node is None:
            return None
    return node if isinstance(node, dict) else None


class TestEveryPageBuilds(unittest.TestCase):
    """The plan is data, so building it is safe on any machine."""

    def test_the_registry_has_fifteen_pages_in_sidebar_order(self):
        self.assertEqual(15, len(registry.PAGES))
        self.assertEqual(15, len(registry.PAGE_IDS))
        self.assertEqual(len(set(registry.PAGE_IDS)), len(registry.PAGE_IDS))
        self.assertEqual("home", registry.PAGE_IDS[0], "the sidebar opens on Home")
        self.assertEqual("about", registry.PAGE_IDS[-1], "and ends on About")
        self.assertEqual(registry.DEFAULT_PAGE, registry.PAGE_IDS[0])

    def test_every_page_module_is_distinct_and_is_the_spec_module(self):
        self.assertEqual(15, len(set(registry.MODULES)))
        for spec in registry.PAGES:
            with self.subTest(page=spec.id):
                self.assertEqual(spec.module, spec.id,
                                 "a page whose module is not its own id is a page two "
                                 "registry entries could share")

    def test_every_page_builds_with_no_problem(self):
        for page_id, built in PLANS.items():
            with self.subTest(page=page_id):
                self.assertEqual([], built.problems(CONTEXT))

    def test_an_unknown_page_id_falls_back_rather_than_raising(self):
        """``app.last_page`` is a value from a file a person can edit."""
        self.assertEqual("home", registry.resolve("no-such-page").id)
        self.assertEqual("home", registry.resolve("").id)
        for page_id in registry.PAGE_IDS:
            with self.subTest(page=page_id):
                self.assertEqual(page_id, registry.resolve(page_id).id)

    def test_no_page_is_empty_and_no_group_is_empty(self):
        for page_id, built in PLANS.items():
            with self.subTest(page=page_id):
                self.assertTrue(built.groups, "a page with no group draws nothing")
                for group in built.groups:
                    self.assertTrue(group.rows or any(
                        row.rows_source or row.rows for row in group.rows),
                        f"group {group.title!r} on {page_id} has no row in it")


class TestRowsNameRealThings(unittest.TestCase):
    """A plan cannot smuggle behaviour past the checks, so the checks are the test."""

    def test_every_named_function_resolves(self):
        for page_id, row in all_rows():
            for field, name in (("action", row.action), ("source", row.source),
                                ("choices_source", row.choices_source),
                                ("rows_source", row.rows_source),
                                ("tiles_source", row.tiles_source),
                                ("uri_source", row.uri_source),
                                ("validator", row.validator),
                                ("sensitive_when", row.sensitive_when),
                                ("visible_when", row.visible_when)):
                if not name:
                    continue
                with self.subTest(page=page_id, row=row.title, field=field):
                    self.assertIsNotNone(CONTEXT.resolve(name),
                                         f"{name} is not a function this application has")

    def test_a_named_function_is_only_in_a_list_the_package_wrote_down(self):
        """Resolution is restricted, so a name that could resolve anywhere is uncheckable."""
        allowed_modules = (set(SERVICE_MODULES) | set(registry.MODULES)
                           | set(plan_module.PACKAGE_MODULES))
        pattern = re.compile(r"^([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$")
        for page_id, row in all_rows():
            for name in (row.action, row.source, row.choices_source, row.rows_source,
                         row.tiles_source, row.uri_source, row.validator,
                         row.sensitive_when, row.visible_when):
                if not name:
                    continue
                match = pattern.match(name)
                with self.subTest(page=page_id, row=row.title, name=name):
                    self.assertIsNotNone(match, f"{name} is not module.function")
                    self.assertIn(match.group(1), allowed_modules,
                                  f"{name} reaches into a module the package does not "
                                  f"allow a plan to name")

    def test_every_banner_condition_and_action_resolves(self):
        for page_id, built in PLANS.items():
            for banner in built.banners:
                for name in (banner.when, banner.action):
                    if not name:
                        continue
                    with self.subTest(page=page_id, name=name):
                        self.assertIsNotNone(CONTEXT.resolve(name))

    def test_a_number_row_carries_the_bounds_it_is_drawn_with(self):
        for page_id, row in all_rows():
            if row.kind not in ("spin", "scale"):
                continue
            with self.subTest(page=page_id, row=row.title):
                self.assertIsNotNone(row.minimum, "a spin or scale with no minimum cannot "
                                                  "be drawn, and inventing one would put a "
                                                  "stop on the widget the record does not "
                                                  "have")
                self.assertIsNotNone(row.maximum)
                self.assertLess(row.minimum, row.maximum)

    def test_a_dropdown_has_choices_or_a_source_that_resolves(self):
        for page_id, row in all_rows():
            if row.kind != "combo":
                continue
            with self.subTest(page=page_id, row=row.title):
                choices = row.choices_list(CONTEXT)
                self.assertTrue(choices, "a dropdown with nothing behind it is a control "
                                         "that lies")
                for identifier, label in choices:
                    self.assertTrue(str(identifier).strip(), f"{row.title} has an empty id")
                    self.assertTrue(str(label).strip(), f"{row.title} has an empty label")
                self.assertEqual(len({identifier for identifier, _ in choices}),
                                 len(choices), f"{row.title} offers one value twice")

    def test_a_setting_path_is_one_the_document_has(self):
        offered = set(plan_module.settings_paths())
        dynamic = {path for path, _kind, _record in plan_module.DYNAMIC_CONTAINERS}
        for page_id, row in all_rows():
            if not row.setting:
                continue
            with self.subTest(page=page_id, row=row.title):
                top = row.setting
                self.assertTrue(top in offered or any(top.startswith(prefix + ".")
                                                      for prefix in dynamic),
                                f"{row.setting} is not in data/settings.default.json and is "
                                f"not under a container whose keys come from a record")

    def test_a_risky_row_asks_before_it_acts(self):
        for page_id, row in all_rows():
            if not row.risky:
                continue
            with self.subTest(page=page_id, row=row.title):
                self.assertTrue(row.confirm, "a row marked risky with no confirmation is a "
                                             "row that can destroy something on one click")
                self.assertGreater(len(row.confirm_body.split()), 6,
                                   "a confirmation body has to say what is about to happen")


class TestTheSettingsDocumentIsCovered(unittest.TestCase):
    """Part 4's acceptance: every visual switch in the product is reachable."""

    #: Two paths in the document are not switches and no page should offer them.
    #: ``_copyright`` is the header stamp every data file in this repository carries, and
    #: ``notes`` is free prose a person writes in their own copy. Offering either would be
    #: a control for something that is not a setting.
    NOT_A_SWITCH = ("_copyright", "notes")

    def test_every_settings_path_is_owned_by_a_page(self):
        owned: Set[str] = set()
        for _page_id, row in all_rows():
            if row.setting:
                owned.add(row.setting)
        dynamic = {path for path, _kind, _record in plan_module.DYNAMIC_CONTAINERS}
        named: Set[str] = set()
        for _page_id, row in all_rows():
            named.update(str(keyword) for keyword in row.keywords)
        missing = []
        for path in plan_module.settings_paths():
            if path in self.NOT_A_SWITCH:
                continue
            if path in owned or path in dynamic:
                continue
            if any(path.startswith(prefix + ".") for prefix in dynamic):
                continue
            if any(path == keyword or path.startswith(keyword + ".")
                   for keyword in named):
                continue
            missing.append(path)
        self.assertEqual([], missing,
                         "a settings path no page offers and no page names: a value only a "
                         "text editor can change")

    def test_the_two_paths_no_page_offers_are_the_two_that_are_not_switches(self):
        """The exclusion list has to be exactly as long as it needs to be."""
        owned: Set[str] = set()
        for _page_id, row in all_rows():
            if row.setting:
                owned.add(row.setting)
        dynamic = {path for path, _kind, _record in plan_module.DYNAMIC_CONTAINERS}
        named: Set[str] = set()
        for _page_id, row in all_rows():
            named.update(str(keyword) for keyword in row.keywords)
        unowned = []
        for path in plan_module.settings_paths():
            if path in owned or path in dynamic:
                continue
            if any(path.startswith(prefix + ".") for prefix in dynamic):
                continue
            if any(path == keyword or path.startswith(keyword + ".") for keyword in named):
                continue
            unowned.append(path)
        self.assertEqual(sorted(self.NOT_A_SWITCH), sorted(unowned),
                         "the list of paths no page owns changed, so either a switch lost "
                         "its page or the exclusion list is hiding one")

    def test_the_dynamic_containers_are_the_kind_the_schema_says(self):
        for path, kind, record in plan_module.DYNAMIC_CONTAINERS:
            with self.subTest(container=path):
                node = schema_node(path)
                self.assertIsNotNone(node, f"{path} is not in the settings schema at all")
                self.assertEqual(kind, node.get("type"),
                                 f"{path} is recorded here as {kind} and the schema says "
                                 f"{node.get('type')}")
                self.assertTrue((ROOT / record).is_file(),
                                f"{path} names {record} as the authority for its keys and "
                                f"that file does not exist")

    def test_the_dynamic_containers_really_are_empty_in_the_defaults(self):
        """The reason the table exists: a literal walk cannot enumerate these keys."""
        for path, kind, _record in plan_module.DYNAMIC_CONTAINERS:
            node: Any = SETTINGS
            for part in path.split("."):
                node = node.get(part, {}) if isinstance(node, dict) else {}
            with self.subTest(container=path):
                self.assertEqual([] if kind == "array" else {}, node,
                                 f"{path} ships non-empty, so a walk of the defaults file "
                                 f"could enumerate it and the table would be a way to skip "
                                 f"a check")

    def test_the_colour_modes_offered_cover_the_schema_enum(self):
        node = schema_node("theme.colour_mode")
        self.assertIsNotNone(node)
        enum = set(node.get("enum") or ())
        offered = {identifier for identifier, _label in appearance.COLOUR_MODES}
        self.assertEqual(enum, offered,
                         "a mode the schema accepts and the page cannot show is a value the "
                         "file allows and the interface hides")
        for identifier, label in appearance.COLOUR_MODES:
            with self.subTest(mode=identifier):
                self.assertTrue(label.strip())


class TestNothingInTheInterfaceNamesAnUpstreamProject(unittest.TestCase):
    """Part 4's other acceptance clause, with the About page as the one exception."""

    def test_no_visible_string_names_an_upstream_project(self):
        hits = []
        for page_id, where, text in visible_text():
            lowered = str(text).lower()
            for token in UPSTREAM_TOKENS:
                if token in lowered:
                    hits.append(f"{page_id}: {where} names {token!r} ({text[:70]!r})")
        self.assertEqual([], hits,
                         "the settings UI names an upstream project outside the About "
                         "page's legal sections:\n" + "\n".join(hits))

    def test_nothing_a_search_result_displays_names_an_upstream_project(self):
        hits = []
        for page_id, where, text in index_text():
            lowered = str(text).lower()
            for token in UPSTREAM_TOKENS:
                if token in lowered:
                    hits.append(f"{page_id}: {where} names {token!r} ({text[:60]!r})")
        self.assertEqual([], hits,
                         "a search result shows an upstream project's name:\n"
                         + "\n".join(hits))

    def test_the_about_page_is_where_the_names_are_allowed_to_be(self):
        """The exception has to be a real section, not a loophole."""
        from iarch_settings.services import licenses

        sections = licenses.legal_sections()
        self.assertTrue(sections, "the About page has no legal section to put a name in")
        named = [section for section in sections
                 if any(token in str(section.get("title") or "").lower()
                        for token in UPSTREAM_TOKENS)]
        self.assertTrue(named, "no legal section names an upstream project, so the exception "
                               "would be allowing nothing")
        for section in sections:
            with self.subTest(section=section.get("title")):
                self.assertTrue(str(section.get("copyright") or "").strip())
                self.assertTrue(str(section.get("license") or "").strip())

    def test_the_about_page_does_not_put_an_upstream_name_in_its_own_chrome(self):
        """The exception is the legal sections, so the page's own words stay clean."""
        built = PLANS["about"]
        hits = []
        for where, text in (("the page title", built.title),
                            ("the page description", built.description or "")):
            for token in UPSTREAM_TOKENS:
                if token in str(text).lower():
                    hits.append(f"{where} names {token!r}")
        for group in built.groups:
            for token in UPSTREAM_TOKENS:
                if token in group.title.lower():
                    hits.append(f"the group title {group.title!r} names {token!r}")
        for banner in built.banners:
            for token in UPSTREAM_TOKENS:
                if token in banner.text.lower():
                    hits.append(f"a banner names {token!r}")
        self.assertEqual([], hits,
                         "the About page's own chrome names an upstream project; the "
                         "exception in the acceptance is its legal and acknowledgement "
                         "sections, not its headings:\n" + "\n".join(hits))


class TestTheSearchIndexIsBuiltFromThePlans(unittest.TestCase):
    """The index is what makes a switch findable, which is the other half of reachable."""

    def test_every_row_produces_a_search_entry(self):
        for page_id, built in PLANS.items():
            entries = built.search_entries(CONTEXT)
            rows = list(built.walk())
            with self.subTest(page=page_id):
                self.assertGreaterEqual(len(entries), len(rows),
                                        "a row that produces no search entry cannot be found")

    def test_a_search_entry_carries_the_page_the_row_and_the_text_to_match(self):
        for page_id, built in PLANS.items():
            entries = built.search_entries(CONTEXT)
            with self.subTest(page=page_id):
                self.assertTrue(entries)
                for entry in entries:
                    self.assertEqual(page_id, entry["page"])
                    self.assertTrue(str(entry.get("row") or "").strip(),
                                    "an entry with no row name cannot be shown as a result")
                    self.assertTrue(str(entry.get("text") or "").strip(),
                                    "an entry with no text cannot be matched")

    def test_the_text_to_match_carries_the_title_the_group_and_the_keywords(self):
        """A person searches by a word from the sidebar, not by a row's exact title."""
        built = PLANS["glass"]
        entries = built.search_entries(CONTEXT)
        lowered = [entry["text"].lower() for entry in entries]
        self.assertTrue(any("opacity" in text for text in lowered),
                        "the Glass page's rows do not carry 'opacity' in their search text")
        for entry in entries:
            with self.subTest(row=entry["row"]):
                self.assertIn(entry["row"].lower(), entry["text"].lower(),
                              "a row's own title is not in the text built to match it")

    def test_the_icon_sentence_and_the_registry_label_agree(self):
        for spec in registry.PAGES:
            with self.subTest(page=spec.id):
                self.assertEqual(f"{spec.label} page", registry.icon_sentence(spec.id))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
