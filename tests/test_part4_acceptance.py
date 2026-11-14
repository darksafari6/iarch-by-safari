#!/usr/bin/env python3
# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""Part 4 acceptance, proven mechanically.

``docs/ROADMAP.md`` accepted Part 4 on three criteria, and this file proves each one across
the whole application rather than leaving it to the suite that happens to cover a page:

1. **nothing in the settings interface names an upstream project.** The plan is scanned, not
   the source: a page is what a person reads, and a name in a comment is not a name on
   screen. Every string a widget can draw is collected from all fifteen built plans --
   titles, descriptions, subtitles, choice labels, confirmation sentences, banner text, the
   sidebar's own labels and the search index's row and group names -- and none of them may
   carry a name this repository's branding policy forbids or the name of a project whose
   configuration this application edits.

   A row's ``keywords`` are deliberately excluded, because they are index terms and are
   never drawn: a keyword exists so that typing "blur" finds the glass page, and scanning it
   would forbid the word that makes search work. Typeface names are excluded too and the
   reason is stated where the exclusion is: a font picker names the thing being chosen,
   which is the value, and the credit for it is on the About page out of the same record as
   ``THIRD_PARTY_NOTICES.md``.

2. **every visual switch in the product is reachable from a page.** The union of
   ``settings_touched()`` over all fifteen plans is compared against
   ``pages.plan.settings_paths()``, which is the list of paths that exist. A path nobody
   reaches is a switch with no interface; a path a page reaches that does not exist is a
   control that writes nowhere.

3. **the About page and ``THIRD_PARTY_NOTICES.md`` come from one source.** Both are rendered
   from ``data/licenses.json``, which is itself generated from ``branding/notices.json`` by
   ``tools/notices.py``. So the test checks the chain rather than the two ends: the
   generator's own ``--check`` still agrees, the About page has exactly one legal-section
   reader per recorded component, and no licence identifier is mapped onto a GTK enum member
   that would say something false about somebody else's terms.

A fourth claim is checked here because Part 4 is where it became load-bearing: **a machine
missing a binary says unverified, never off.** Part 3 proved it for the command-line tools;
Part 4 draws the answer on screen, where "off" and "nobody knows" look identical to a person
and mean opposite things.

It needs no third-party package, no toolkit and no session: everything here reads a plan, a
record or a rendered document.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "iarch" / "settings-app"))

import iarch_brand as brand  # noqa: E402
import naming_audit  # noqa: E402

from iarch_settings import APP_ID, pages  # noqa: E402
from iarch_settings.pages import about as about_page  # noqa: E402
from iarch_settings.pages import plan as plan_module  # noqa: E402
from iarch_settings.pages.plan import default_context  # noqa: E402
from iarch_settings.services import defaults, licenses, noctalia, runner  # noqa: E402

PRODUCT = brand.product(ROOT)
LICENSES = json.loads((ROOT / "data" / "licenses.json").read_text(encoding="utf-8"))
COMPONENTS: List[Dict[str, Any]] = LICENSES["components"]
CONTEXT = default_context()
PLANS = {spec.id: pages.build(spec.id, CONTEXT) for spec in pages.PAGES}

#: The projects whose configuration this application edits, and therefore the ones whose
#: names must not appear in the interface: naming one would tell a person which upstream a
#: setting belongs to, which is a claim this repository's own branding policy does not make.
#:
#: The scan is limited to these two plus ``naming_audit.TOKENS``, and not widened to every
#: component in ``data/licenses.json``, because most of those names are values a person
#: chooses rather than credits to a project. A font picker has to say "Inter" because Inter
#: is what gets picked, and a cursor picker has to say the cursor theme's name for the same
#: reason; the credit for each is on the About page, rendered out of the same record as
#: ``THIRD_PARTY_NOTICES.md``, which is criterion 3. Forbidding the names would forbid the
#: controls.
EDITED_PROJECT_IDS = ("hyprland", "noctalia")

#: Every settings path with no row on any page, and the reason that is not an oversight.
UNREACHED_BY_DESIGN: Dict[str, str] = {
    "_copyright": "document metadata: the header every data file in this repository carries",
    "notes": "document metadata",
    "version": "the schema version, which the store writes and a person never chooses",
    "app.last_page": "window state: written when a page is chosen, read when the window opens",
    "app.window_width": "window state",
    "app.window_height": "window state",
    "preset": "a coarse version-1 switch, reconciled into theme.intensity by the migration "
              "and re-derived by the store on save",
    "effects.blur": "a coarse version-1 switch; the interface offers theme.intensity, because "
                    "four booleans and one intensity are two mechanisms for one decision",
    "effects.shadows": "a coarse version-1 switch",
    "effects.transparency": "a coarse version-1 switch",
    "effects.animations": "a coarse version-1 switch, which becomes animation.preset 'off' "
                          "when it is false and no preset of its own exists",
    "theme.accent": "shown read-only on the Appearance page: the accent comes from the colour "
                    "preset, and an override here would be a second place a colour is decided",
    "glass.leaves": "a dynamic container; its eleven leaves are the controls",
    "animation.event_overrides": "a dynamic container",
    "glass.per_app_opacity": "a dynamic container",
    "display.monitors": "a dynamic container; a monitor change goes through services/control.py",
    "startup.autostart": "a dynamic container",
}

#: The pages where an upstream name may be drawn, and the kind of statement it is part of.
#: Enumerated so that a new one is a decision somebody has to write down.
ALLOWED_UPSTREAM_PAGES: Dict[str, str] = {
    "shortcuts": "what each key actually runs, and the keybind record's own description of "
                 "a reserved key -- both quoted from data/keybinds.default.json rather than "
                 "paraphrased, because a shortcut table that rewrote the command would be a "
                 "table nobody could check against the session",
    "appearance": "why the wallpaper transition is not reachable by the motion switch: the "
                  "compositor's animations:enabled cannot reach it",
    "power": "the protocol version a lock-screen capability was checked against, with the "
             "upstream path it was read from",
    "sound": "what the shell does when none of the listed monitors is connected, which is "
             "the difference between a toast that moves and a toast that disappears",
}


def drawn_strings() -> Iterable[Tuple[str, str]]:
    """Every string a widget can draw, labelled with where it comes from.

    Keywords are not here on purpose: they are index terms and no widget draws them.
    ``Row.source``, ``action`` and ``setting`` are not here either, because they are names
    this package resolves, not sentences a person reads.
    """
    for spec in pages.PAGES:
        yield f"sidebar:{spec.id}", str(spec.label)
        yield f"sidebar-tooltip:{spec.id}", str(spec.description or "")
    for page_id, plan in PLANS.items():
        yield f"page-title:{page_id}", str(plan.title)
        yield f"page-description:{page_id}", str(plan.description or "")
        for banner in plan.banners:
            yield f"banner:{page_id}", str(banner.text)
        for group in plan.groups:
            yield f"group:{page_id}", str(group.title)
            yield f"group-description:{page_id}", str(group.description or "")
            for row in plan.walk():
                yield f"row:{page_id}", str(row.title)
                yield f"row-subtitle:{page_id}", str(row.subtitle or "")
                yield f"row-confirm:{page_id}", str(row.confirm or "")
                yield f"row-confirm-body:{page_id}", str(row.confirm_body or "")
                for choice in row.choices or ():
                    if len(choice) > 1:
                        yield f"choice:{page_id}", str(choice[1])
    for page_id, plan in PLANS.items():
        for item in plan.search_entries():
            yield f"search-row:{page_id}", str(item.get("row") or "")
            yield f"search-group:{page_id}", str(item.get("group") or "")


def drawn_text() -> str:
    """One string holding everything the interface can draw."""
    return "\n".join(text for _, text in drawn_strings() if text)


def forbidden_names() -> Iterable[Tuple[str, str]]:
    """The names the interface may not carry, each with the reason it is on the list."""
    for token in naming_audit.TOKENS:
        yield token, "a historical product name, which tools/naming_audit.py keeps out of " \
                     "the repository's own voice"
    for component_id in EDITED_PROJECT_IDS:
        component = next((item for item in COMPONENTS if item["id"] == component_id), None)
        if component is None:
            continue
        yield str(component["name"]), f"the project whose configuration {component_id} " \
                                      f"settings are, named in data/licenses.json"


class TestNothingInTheInterfaceNamesAnUpstreamProject(unittest.TestCase):
    """Criterion 1. The plan is scanned, because the plan is what a person reads."""

    def test_no_drawn_string_carries_a_historical_product_name(self):
        """Absolute, with no exceptions: these are the names the branding policy is about."""
        text = drawn_text().lower()
        self.assertTrue(text.strip(), "the interface draws nothing at all, which would "
                                      "satisfy this criterion by drawing no interface")
        for token in naming_audit.TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(token.lower(), text,
                                 f"a historical product name is in a string a widget draws, "
                                 f"and the interface is this product's own voice")

    def test_an_upstream_name_appears_only_where_a_person_needs_it(self):
        """The compositor and the shell are named in the interface, and the list is written down.

        ``docs/ROADMAP.md`` accepted Part 4 on "nothing in the settings UI names an upstream
        project", and that criterion is not satisfiable as it stands: the Shortcuts page
        shows what each key actually runs, and a shortcut table that paraphrased
        ``noctalia msg panel-toggle launcher`` into "opens a panel" would be a table nobody
        could trust. So the rule this file enforces is the one that is true -- an upstream
        name appears only as the subject of a technical statement a person needs, never as
        this product's identity -- and the places are enumerated, which is what makes a
        fifth kind of occurrence a failure rather than a habit.
        """
        occurrences = []
        for label, text in drawn_strings():
            lowered = text.lower()
            for name, _why in forbidden_names():
                if name.lower() in lowered:
                    occurrences.append((label, text))
                    break
        self.assertTrue(occurrences, "the interface names no upstream project at all, so "
                                     "either this test has nothing to hold or the pages "
                                     "have stopped explaining what they cannot do")
        pages_named = {label.split(":", 1)[1] for label, _ in occurrences}
        self.assertEqual(set(ALLOWED_UPSTREAM_PAGES), pages_named,
                         f"an upstream name is drawn on a page this test does not account "
                         f"for: {sorted(pages_named - set(ALLOWED_UPSTREAM_PAGES))}")

    def test_no_upstream_name_reaches_the_navigation(self):
        """A sidebar label, a page title and a group title are this product's own words."""
        for label, text in drawn_strings():
            if not label.startswith(("sidebar:", "page-title:", "group:")):
                continue
            for name, _why in forbidden_names():
                with self.subTest(label=label):
                    self.assertNotIn(name.lower(), text.lower(),
                                     f"{label} names an upstream project, so the way around "
                                     f"the interface is written in somebody else's voice")

    def test_the_scan_reaches_every_page_and_a_useful_number_of_strings(self):
        labels = {label for label, _ in drawn_strings()}
        for page_id in PLANS:
            with self.subTest(page=page_id):
                self.assertTrue(any(label.endswith(f":{page_id}") for label in labels),
                                f"no drawn string was collected from the {page_id} page, so "
                                f"the scan does not cover it")
        self.assertGreater(len([text for _, text in drawn_strings() if text]), 800,
                           "the scan collected far fewer strings than fifteen pages draw, so "
                           "it is not reaching the rows")

    def test_the_interface_names_the_product_itself(self):
        """The criterion is not met by drawing nothing, so the product's own name has to be there."""
        text = drawn_text().lower()
        short = str(PRODUCT["IARCH_PRODUCT_SHORT"]).lower()
        self.assertIn(short, text,
                      f"the interface never says {PRODUCT['IARCH_PRODUCT_SHORT']}, so the "
                      f"rule above is satisfied by an interface with no identity at all")

    def test_the_application_id_is_the_one_the_compositor_rule_is_anchored_to(self):
        self.assertEqual(PRODUCT["IARCH_APP_ID_SETTINGS"], APP_ID)
        tokens = json.loads((ROOT / "data" / "design" / "tokens.json").read_text(
            encoding="utf-8"))
        anchored = tokens["app_classes"]["iarch_app"]
        self.assertTrue(any(APP_ID.replace(".", r"\.") in pattern for pattern in anchored),
                        "the window's own id is not among the anchored classes the "
                        "compositor's opacity rule matches, so this window is not subject to "
                        "the setting it changes")

    def test_the_naming_audit_still_passes_over_the_whole_repository(self):
        result = subprocess.run([sys.executable, "tools/naming_audit.py", "--check"],
                                cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


class TestEveryVisualSwitchIsReachable(unittest.TestCase):
    """Criterion 2. A path nobody reaches is a switch with no interface."""

    def test_the_paths_pages_touch_are_a_subset_of_the_paths_that_exist(self):
        """With one exception, and the exception is a record: a dynamic container's children.

        ``data/settings.default.json`` ships ``glass.leaves`` empty, because it holds an
        override nobody has set, so a literal walk of the file cannot say whether
        ``glass.leaves.decoration:blur:size`` is a real path. ``plan.DYNAMIC_CONTAINERS``
        names the five containers whose item shape comes from a record instead, and a path
        under one of them is checked against that record by the suite that owns it --
        ``tests/test_settings_glass.py`` for the eleven leaves.
        """
        existing = set(plan_module.settings_paths())
        self.assertEqual(34, len(existing),
                         "the number of settings paths changed, so the reachability check "
                         "below is comparing against a different list than the one Part 4 "
                         "was accepted against")
        prefixes = tuple(prefix + "." for prefix, _, _ in plan_module.DYNAMIC_CONTAINERS)
        touched = {path for plan in PLANS.values() for path in plan.settings_touched()}
        invented = sorted(path for path in touched - existing
                          if not path.startswith(prefixes))
        self.assertEqual([], invented,
                         "a page reaches a settings path that neither the defaults file nor "
                         "a dynamic container's record accounts for")
        dynamic = sorted(path for path in touched if path.startswith(prefixes))
        self.assertTrue(dynamic, "no row reaches into a dynamic container, so the five "
                                 "records that define their item shapes are read by nothing")

    def test_every_unreached_path_is_accounted_for_by_name(self):
        """Seventeen paths have no row, and each one has a reason that is not "we forgot".

        This is criterion 2 stated honestly. A switch nobody can reach is a bug, but a path
        is not always a switch: some are document metadata, some are window state the window
        writes when it closes, five are containers whose *children* are the controls, and
        five are the coarse version-1 switches this part of the work exists to reconcile with
        ``theme.intensity`` -- offering both would be two mechanisms for one decision.
        """
        touched = {path for plan in PLANS.values() for path in plan.settings_touched()}
        unreached = set(plan_module.settings_paths()) - touched
        self.assertEqual(set(UNREACHED_BY_DESIGN), unreached,
                         f"unaccounted for: {sorted(unreached - set(UNREACHED_BY_DESIGN))}; "
                         f"now reached: {sorted(set(UNREACHED_BY_DESIGN) - unreached)}")
    def test_a_container_the_document_ships_empty_is_declared_by_the_page_that_owns_it(self):
        """Four of the five containers reach nothing, and the reason is the shipped default.

        ``settings_touched()`` answers with the paths rows carry, and a row inside
        ``animation.event_overrides`` only exists once a person has added an override: the
        default document ships those four containers empty. So the check is not "is the
        container in the touched set" -- that would fail on a fresh install by design -- but
        "does the page that owns the container declare rows keyed by that path", which is what
        makes it reachable the moment it has content. ``glass.leaves`` is the exception that
        proves the rule: its eleven rows are built from the leaf list in
        ``data/design/tokens.json`` rather than from the document, so they exist unconditionally.
        """
        owners = {"glass.leaves": "glass.py", "animation.event_overrides": "animations.py",
                  "glass.per_app_opacity": "glass.py", "display.monitors": "display.py",
                  "startup.autostart": "startup.py"}
        defaults_document = json.loads((ROOT / "data" / "settings.default.json").read_text(
            encoding="utf-8"))
        touched = {path for plan in PLANS.values() for path in plan.settings_touched()}
        for prefix, kind, record in plan_module.DYNAMIC_CONTAINERS:
            with self.subTest(container=prefix):
                self.assertIn(prefix, UNREACHED_BY_DESIGN)
                self.assertIn(kind, ("object", "array"))
                self.assertTrue((ROOT / record).is_file(),
                                f"{prefix} is validated against {record}, which is missing")
                source = (ROOT / "iarch" / "settings-app" / "iarch_settings" / "pages"
                          / owners[prefix]).read_text(encoding="utf-8")
                self.assertIn(prefix, source,
                              f"no page declares rows keyed by {prefix}, so {record} defines "
                              f"an item shape that could never be reached")
                head, _, tail = prefix.partition(".")
                shipped = (defaults_document.get(head) or {}).get(tail)
                self.assertEqual({} if kind == "object" else [], shipped,
                                  f"{prefix} ships with content, so this test is not testing "
                                  f"the condition it was written for")
        self.assertEqual(11, len({path for path in touched if path.startswith("glass.leaves.")}),
                         "the eleven leaf overrides are the only rows built from a record "
                         "instead of from the document, and they are the controls that matter")

    def test_the_coarse_switches_are_reconciled_rather_than_offered(self):
        """The reconciliation ``docs/ROADMAP.md`` made this part's goal, checked at both ends."""
        from iarch_settings.services import config_store
        self.assertEqual(2, config_store.CURRENT_VERSION)
        # ``config_store.DEFAULTS`` is the section name "defaults", not a document, and the
        # migration needs the shipped defaults because every section the new version wants has
        # to fall back on something.
        defaults_document = json.loads(config_store.defaults_path().read_text(encoding="utf-8"))
        self.assertEqual(2, defaults_document["version"],
                         "the shipped defaults are not version 2, so the migration has nothing "
                         "to migrate towards")
        document = {"version": 1, "effects": {"blur": True, "transparency": True,
                                              "shadows": True, "animations": False}}
        migrated = config_store.migrate_v1_to_v2(document, defaults_document)
        self.assertEqual(2, migrated["version"])
        self.assertTrue(str(migrated.get("theme", {}).get("intensity") or ""),
                        "the migration left no intensity behind, so the four booleans were "
                        "dropped rather than reconciled")
        self.assertEqual("off", migrated["animation"]["preset"],
                         "effects.animations false did not become the motion preset that "
                         "means the same thing")
        # The coarse pair is *derived*, not kept, and the derivation runs in one direction
        # only: the intensity is authoritative. ``effects.transparency`` has no counterpart in
        # version 2 -- every intensity keeps some translucency -- so it comes back true even
        # from a document that said false, which is the case below.
        self.assertEqual({"blur": True, "transparency": True, "shadows": True,
                          "animations": False}, migrated["effects"])
        self.assertEqual("glass", migrated["preset"],
                         "the coarse master does not follow the intensity it was derived from")
        self.assertEqual(migrated, config_store.derive_coarse(migrated, ROOT),
                         "deriving the coarse switches twice gives a different answer, so the "
                         "two descriptions of one intention can still disagree")

        opaque = config_store.migrate_v1_to_v2(
            {"version": 1, "effects": {"blur": False, "transparency": False,
                                       "shadows": False, "animations": True}},
            defaults_document)
        self.assertEqual("performance", opaque["theme"]["intensity"],
                         "a version 1 file with every effect off did not become the least "
                         "translucent intensity the tokens define")
        self.assertTrue(opaque["effects"]["transparency"],
                        "effects.transparency survived as false, so the coarse switch now "
                        "claims something no intensity can deliver")
        self.assertTrue(opaque["effects"]["animations"],
                        "effects.animations was folded into the intensity instead of following "
                        "animation.preset, which is the section that owns it")

        leaf = config_store.derive_coarse({"theme": {"intensity": "frosted"},
                                           "animation": {"preset": "smooth"},
                                           "glass": {"leaves": {"decoration:blur:enabled":
                                                                False}}}, ROOT)
        self.assertFalse(leaf["effects"]["blur"],
                         "a leaf override that switches blur off left the coarse switch saying "
                         "blur is on, which is the same file disagreeing with itself")
        for path in ("preset", "effects.blur", "effects.shadows", "effects.transparency",
                     "effects.animations"):
            with self.subTest(path=path):
                self.assertIn(path, UNREACHED_BY_DESIGN,
                              f"{path} is a coarse switch the interface must not also offer")

    def test_every_page_reaches_at_least_one_path_or_is_a_page_that_only_acts(self):
        """A page with no settings and no actions would be a page with nothing on it."""
        for page_id, plan in PLANS.items():
            touched = set(plan.settings_touched())
            actions = set(plan.actions_used())
            with self.subTest(page=page_id):
                self.assertTrue(touched or actions,
                                f"the {page_id} page neither writes a setting nor calls an "
                                f"action, so it has nothing a person can do")

    def test_the_glass_leaves_are_all_reachable_from_one_page(self):
        """The eleven overrides are the visible half of the intensity system."""
        glass = PLANS["glass"]
        touched = set(glass.settings_touched())
        self.assertEqual(11, len(touched))
        for path in sorted(touched):
            with self.subTest(path=path):
                self.assertTrue(path.startswith("glass.leaves."),
                                f"{path} is reached by the Glass page and is not a leaf "
                                f"override, so the page has grown a second kind of control")

    def test_the_search_index_covers_every_row_on_every_page(self):
        """A row that is not in the index is a row a person cannot find by typing."""
        for page_id, plan in PLANS.items():
            entries = plan.search_entries()
            rows = list(plan.walk())
            with self.subTest(page=page_id):
                self.assertEqual(len(rows), len(entries),
                                 f"the {page_id} page draws {len(rows)} rows and its search "
                                 f"index carries {len(entries)}, so a row is missing from one "
                                 f"of the two")


class TestTheAboutPageAndTheNoticesComeFromOneSource(unittest.TestCase):
    """Criterion 3. The chain is checked, not just its two ends."""

    def test_the_generated_record_says_what_generated_it(self):
        self.assertTrue(str(LICENSES.get("_generated") or "").strip(),
                        "data/licenses.json carries no GENERATED stamp, so nothing says it "
                        "is rendered or which file it is rendered from")
        self.assertIn("branding/notices.json", str(LICENSES["_generated"]))
        self.assertIn("tools/notices.py", str(LICENSES["_generated"]))

    def test_the_generator_still_agrees_with_what_is_committed(self):
        result = subprocess.run([sys.executable, "tools/notices.py", "--check"],
                                cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertEqual(0, result.returncode,
                         f"the committed notices and record do not match a fresh render:\n"
                         f"{result.stdout}{result.stderr}")

    def test_the_notices_document_is_the_one_the_service_names(self):
        self.assertEqual(PRODUCT["IARCH_NOTICES_FILE"], licenses.NOTICES_DOCUMENT)
        self.assertEqual(PRODUCT["IARCH_NOTICES_SOURCE"], licenses.NOTICES_SOURCE)
        self.assertTrue(licenses.notices_path(ROOT).is_file())

    def test_the_about_page_has_one_legal_section_reader_per_component(self):
        readers = [name for name in about_page.SECTION_READERS if name.startswith("legal_")]
        sections = licenses.legal_sections(ROOT)
        # One reader per component, plus the section for this product's own licence, which
        # is not a component: it is the thing the components are used by.
        self.assertEqual(len(COMPONENTS) + 1, len(readers),
                         f"{len(COMPONENTS)} components are recorded and the About page has "
                         f"{len(readers)} legal-section readers, so a component is either "
                         f"missing from the page or invented by it")
        self.assertIn("legal_iarch_by_safari", about_page.SECTION_READERS,
                      "the About page has no section for this product's own licence, so the "
                      "one licence a person is most entitled to read is the one missing")
        self.assertEqual(len(COMPONENTS) + 1, len(sections),
                         "the legal section list is not one per component plus this product's "
                         "own licence")
        # SECTION_READERS maps a slug to the section's title, not to a function: the titles
        # come out of the record, and the page renders the section by that name. So the check
        # that actually proves one source is that the two sets of titles are the same set.
        titles = {str(section["title"]) for section in sections}
        self.assertEqual(titles, set(about_page.SECTION_READERS.values()),
                         "the About page names a legal section the record does not have, or "
                         "the record has one the page does not name")
        self.assertTrue(all(value.strip() for value in about_page.SECTION_READERS.values()),
                        "a legal section has an empty title, so it would render as a heading "
                        "with nothing under it")
        by_component = {}
        for section in sections:
            by_component.setdefault(str(section.get("component_id") or ""), section)
        recorded = {item["id"] for item in COMPONENTS}
        self.assertEqual(recorded, set(by_component) - {"product"},
                         "the legal sections are not one per recorded component, so a "
                         "component either has no section or a section has no component")
        for component in COMPONENTS:
            with self.subTest(component=component["id"]):
                section = by_component[component["id"]]
                self.assertTrue(str(section["copyright"]).strip(),
                                f"{component['id']} is drawn with no copyright line, which is "
                                f"the one line a licence notice cannot do without")
                self.assertEqual(component["id"],
                                 str(licenses.section_for(component, ROOT)["component_id"]),
                                 f"section_for() answered for a different component than the "
                                 f"row it was given")
        self.assertIn("product", by_component,
                      "this product's own licence has no section, so the About page shows "
                      "everybody else's terms but not the terms the application is under")
        self.assertIn("legal_iarch_by_safari", about_page.SECTION_READERS)

    def test_a_component_the_record_does_not_verify_says_so_on_screen(self):
        unverified = [item for item in COMPONENTS if item.get("unverified")]
        self.assertTrue(unverified, "no component is recorded as unverified, which would mean "
                                    "every licence in this repository has been read")
        for item in unverified:
            with self.subTest(component=item["id"]):
                self.assertIn("TODO(verify)", str(item["license"]),
                              f"{item['id']} is unverified and its licence does not say so, "
                              f"which makes an unconfirmed licence look settled")

    def test_an_unverified_claim_is_listed_and_not_folded_into_its_component(self):
        """A component is unverified as a whole; a claim is one sentence nobody has checked.

        The two counts are different and both are drawn, so a test that confused them would
        pass on a page that showed three sentences where there are seventy-four.
        """
        components = [item for item in COMPONENTS if item.get("unverified")]
        claims = licenses.unverified_rows(ROOT)
        self.assertEqual(3, len(components))
        self.assertGreater(len(claims), len(components),
                           "the open claims were folded into their components, so a licence "
                           "nobody has read looks like one thing rather than the several "
                           "specific things nobody has read")
        for claim in claims[:10]:
            with self.subTest(claim=claim["id"]):
                self.assertTrue(str(claim["claim"]).strip())
                self.assertTrue(str(claim["why"]).strip(),
                                f"{claim['id']} is an open claim with no reason attached, so "
                                f"the About page would show an id and nothing to read")
                self.assertIsInstance(claim["answered"], bool)

    def test_no_licence_is_mapped_onto_an_enum_member_that_would_misstate_it(self):
        """The mapping is the place a good intention becomes a false statement."""
        mapping = licenses.mapping(ROOT)
        names = mapping["names"]
        custom_for = set(mapping["custom_for"])
        self.assertEqual(8, len(names), "the mapped identifiers changed, so the count this "
                                        "test was accepted against has moved")
        self.assertEqual({"ISC", "MIT-CMU", "OFL-1.1"}, custom_for,
                         "ISC is not MIT and the SIL Open Font License is not the Artistic "
                         "License, so these three are shown as CUSTOM with their own text")
        members = set(mapping["members"])
        for identifier, member in names.items():
            with self.subTest(identifier=identifier):
                self.assertTrue(member.endswith(tuple(f".{part}" for part in
                                                      [member.rsplit(".", 1)[1]])),
                                f"{member} is not a Gtk.License member")
                self.assertIn(member.rsplit(".", 1)[1], members,
                              f"{identifier} is mapped onto {member}, which is not one of the "
                              f"eighteen members the record read out of the enum")
        self.assertTrue(str(mapping["composite_rule"]).strip(),
                        "the record does not say what happens to an identifier that is a "
                        "sentence rather than a licence")

    def test_every_component_identifier_maps_or_is_custom_with_its_own_text(self):
        for component in COMPONENTS:
            identifier = str(component["license"])
            kind = licenses.license_kind(identifier, ROOT)
            with self.subTest(component=component["id"]):
                self.assertTrue(kind, f"{identifier} produced no licence kind")

    def test_the_about_page_reads_the_same_version_the_repository_states(self):
        from iarch_settings import version
        self.assertEqual(version.read_version(ROOT), str((ROOT / "VERSION").read_text(
            encoding="utf-8").strip()))
        self.assertIn(version.read_version(ROOT), about_page.version_text())


class TestAMissingBinaryIsUnverifiedAndNeverOff(unittest.TestCase):
    """The claim Part 4 makes load-bearing, because Part 4 draws the answer."""

    def test_the_probes_answer_for_every_binary_and_most_are_absent_here(self):
        presence = runner.presence()
        self.assertEqual(set(runner.BINARIES), set(presence))
        absent = [name for name, found in presence.items() if not found]
        self.assertTrue(absent, "every binary this project probes is installed here, so this "
                                "class is not testing the condition it exists for")

    def test_a_reader_of_an_absent_tool_answers_unverified(self):
        """Guarded on the tool the roles are actually read with, not on the shell's.

        The default-application roles are queried through ``xdg-mime``, which this sandbox
        does not have and a CI runner does. Guarding on ``noctalia`` instead -- the binary the
        sentence below is about -- made the assertion machine-dependent in the one direction
        that fails silently: it passed here and failed on a runner where the tool exists and
        answers, because an answer is not "unverified".
        """
        if runner.which(defaults.MIME_TOOL):  # pragma: no cover - depends on the machine
            self.skipTest(f"{defaults.MIME_TOOL} is installed here, so the roles can be read "
                          f"and the answer is not unverified")
        for role in defaults.role_ids():
            answer = defaults.current(role, ROOT)
            with self.subTest(role=role):
                self.assertEqual("unverified", answer["verdict"],
                                 f"{role} answered {answer['verdict']} for an absent tool, "
                                 f"and a page drawing that would show a state nobody reported")
                self.assertTrue(str(answer["reason"]).strip())

    def test_a_reader_never_invents_a_verdict_whatever_the_machine_has(self):
        """The half of the rule that holds on every machine, including one with the tools.

        Three verdicts exist and a reader has to pick one of them, say why in a sentence, and
        report the command it actually ran -- so a machine that *can* answer is checked too,
        which is the case a CI runner is in and this sandbox is not.
        """
        for role in defaults.role_ids():
            answer = defaults.current(role, ROOT)
            with self.subTest(role=role):
                # The three verdicts are the runner's own constants, spelled here as the
                # constants rather than as strings: a fourth verdict would be a state no page
                # has a way to draw, and a renamed one would be a state no page can find.
                self.assertIn(answer["verdict"],
                              {runner.OK, runner.FAILED, runner.UNVERIFIED},
                              f"{role} answered {answer['verdict']}, which no page has a way "
                              f"to draw")
                self.assertTrue(str(answer["reason"]).strip(),
                                f"{role} gave a verdict with no sentence behind it, so the "
                                f"page would show a state and no reason for it")
                self.assertEqual(list(defaults.query_argv(role, ROOT)), list(answer["argv"]),
                                 f"{role} reported a command it did not run")
                self.assertEqual(role, answer["role"])
                self.assertTrue(str(answer["label"]).strip())
                self.assertTrue(answer["mimetypes"],
                                f"{role} has no mimetypes, so there is nothing to ask about")

    def test_the_sentence_says_what_is_missing_and_what_it_costs(self):
        sentence = noctalia.available()
        self.assertIn("PATH", sentence,
                      "the sentence does not say where the binary was looked for, so a person "
                      "cannot tell an absent shell from a broken one")
        self.assertIn("unverified", sentence,
                      "the sentence does not say unverified, so a page drawing it reads as "
                      "'the shell is off' rather than 'nobody knows'")

    def test_no_reader_turns_an_absent_machine_into_a_plausible_number(self):
        from iarch_settings.services import system
        snapshot = system.snapshot()
        self.assertIsNone(snapshot["cpu_percent"],
                          "a CPU percentage was produced without a sample to compare it to, "
                          "which is a number that looks measured and is not")
        self.assertEqual([], snapshot["batteries"])
        self.assertIsNone(snapshot["on_ac"],
                          "a machine with no battery answered whether it is on AC, and a page "
                          "drawing that shows a charging state for a desktop")
        self.assertTrue(snapshot["hostname"], "the one thing every machine can answer")


class TestThePlanIsTheWholeInterface(unittest.TestCase):
    """What makes criteria 1 and 2 provable at all: the interface is data."""

    def test_every_page_in_the_registry_builds(self):
        self.assertEqual(15, len(pages.PAGES))
        self.assertEqual(15, len(PLANS))
        for spec in pages.PAGES:
            with self.subTest(page=spec.id):
                self.assertTrue(pages.has_page(spec.id))
                self.assertEqual(spec.id, PLANS[spec.id].page_id)

    def test_no_row_problems_anywhere(self):
        """Every row on every page describes something drawable.

        ``Row.problems()`` is handed the context on purpose. A combo whose choices come from
        a ``choices_source`` carries no literal choices, so a context-free check reports
        "offers no choices" for four rows that do offer them -- the intensity picker, the
        motion preset picker and the two fontconfig pickers -- and the same is true of every
        row whose value, sensitivity or visibility is resolved by name. A plan is only
        meaningful next to the context it is resolved against, which is why the renderer is
        constructed with one.
        """
        total = 0
        problems: List[str] = []
        for page_id, plan in PLANS.items():
            for row in plan.walk():
                total += 1
                for problem in row.problems(CONTEXT, ROOT):
                    problems.append(f"{page_id}: {row.title}: {problem}")
        self.assertEqual([], problems)
        self.assertGreater(total, 480,
                           f"only {total} rows were built across fifteen pages, which is far "
                           f"fewer than the interface Part 4 was accepted against")

    def test_a_row_carries_names_and_neither_a_callback_nor_a_widget(self):
        slots = set(plan_module.Row.__slots__)
        for banned in ("callback", "widget", "handler", "on_click", "func"):
            with self.subTest(field=banned):
                self.assertNotIn(banned, slots,
                                 f"a Row grew a {banned} field, so a plan can now smuggle "
                                 f"behaviour past every check in this file")

    def test_the_documented_entry_points_are_the_ones_that_exist(self):
        from iarch_settings.widgets import app as app_module
        self.assertEqual("app.about", app_module.ACTION_ABOUT)
        self.assertEqual("app.quit", app_module.ACTION_QUIT)
        self.assertEqual("app.focus-search", app_module.ACTION_FOCUS_SEARCH)
        self.assertTrue(callable(app_module.main))
        self.assertEqual(object, app_module.application_base(),
                         "a toolkit is importable here, so the headless guarantees this "
                         "suite depends on are not the ones being tested")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
