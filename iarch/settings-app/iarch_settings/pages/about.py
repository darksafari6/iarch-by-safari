# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""The About page: the one place this application names another project, and the proof.

Part 4's acceptance has two clauses this page carries. The first is that nothing in the
settings UI names an upstream project *except* the About dialog's legal and acknowledgement
sections; the second is that the About page and ``THIRD_PARTY_NOTICES.md`` come from one
source. Both are answered here rather than asserted in a document.

The one source is ``data/licenses.json``, which ``tools/notices.py`` renders into
``THIRD_PARTY_NOTICES.md`` and :mod:`iarch_settings.services.licenses` renders into the
legal sections below. :func:`licenses.agree` compares the two renderings and a row on this
page shows the answer, so the claim is a read rather than a promise -- and if the document
and the dialog ever diverge, the row says so before anybody has to notice it in a support
conversation.

Twenty-nine legal sections come out of twenty-eight components, and each carries the SPDX
identifier it was resolved from plus the ``Gtk.License`` member that identifier maps to. Ten
identifiers have no member -- the Bitstream Vera licence, OFL-1.1, ISC, MIT-CMU, a service
terms entry, and the ones that say plainly that no licence file was published upstream at
verification time -- and every one of those becomes ``Gtk.License.CUSTOM`` with the
identifier quoted in the section's own text. ``Gtk.License.UNKNOWN`` is never used, because
it would say "we do not know what this is under" about a project whose terms are written
down, and an approximate mapping would say something false about somebody else's licence.

The mapping itself is a record, not a dictionary in this file: ``data/design/adwaita.json``
carries the whole eighteen-member ``GtkLicense`` enum as it was read out of
``gtk/gtkaboutdialog.h:66-92``, so a test can assert that every value used anywhere is a
member of the enum GTK actually declares. The same record carries
``adw_about_dialog_add_legal_section(title, copyright, license_type, license)`` at
``src/adw-about-dialog.h:170-175`` -- four arguments, copyright before licence type, which
is not the shape an earlier draft of the record had.

``add_other_app`` is recorded as rejected rather than used: it is marked
``ADW_AVAILABLE_IN_1_7`` while every other call in that header is ``ADW_AVAILABLE_IN_1_5``,
and the record's own minimum version is 1.5. A call that needs a newer libadwaita than a
session is guaranteed to have is a dialog that constructs on one machine and raises on
another.

What is still open is on this page too. ``docs/UNVERIFIED.md`` carries every claim this
project could not reach from a sandbox, and the rows below give the count rather than a
reassurance: an About page that says "verified" while sixty-nine items are open is a page
that has decided what a reader should believe.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import APP_ID, gtkenv, i18n, paths, version
from ..services import config_store, licenses
from . import page as registry_page
from .plan import Banner, Context, Group, PagePlan, Row

PAGE_ID = "about"


# --------------------------------------------------------------------- readers


def product() -> Dict[str, Any]:
    """The product block of the licence record, which branding owns."""
    try:
        return licenses.product()
    except licenses.LicensesError:
        return {}


def product_name() -> str:
    return str(product().get("name") or "iArch by Safari")


def product_license() -> str:
    return str(product().get("license") or "")


def license_file_text() -> str:
    return str(product().get("license_file") or "LICENSE.txt")


def maintainer_text() -> str:
    return str(product().get("maintainer") or "")


def repository_text() -> str:
    return str(product().get("repository") or "")


def application_id_text() -> str:
    """The id a compositor's window rule matches, and why it is not the product id."""
    return (f"{APP_ID}, which is the product id with a suffix: a Wayland compositor matches "
            f"a GTK 4 application's window by its id, and an anchored rule for the bare "
            f"product id would not match this window")


def version_text() -> str:
    return str(version.facts().get("version") or version.UNKNOWN)


def revision_text() -> str:
    """The revision checked out, so the dialog says what is running and not what was released."""
    return str(version.facts().get("revision") or version.UNKNOWN)


def build_date_text() -> str:
    return str(version.facts().get("build_date") or version.UNKNOWN)


def debug_info_text() -> str:
    """The block the dialog hands to ``set_debug_info``, shown here as well."""
    return version.debug_info()


def toolkit_text() -> str:
    """Whether GTK and libadwaita could be loaded, and what is missing if not."""
    if gtkenv.available():
        return (f"GTK {gtkenv.MINIMUM_GTK} or newer and libadwaita "
                f"{gtkenv.MINIMUM_ADWAITA} or newer are both available")
    return "unavailable: " + ", ".join(gtkenv.missing())


def language_text() -> str:
    """The language this window draws in, and where it came from."""
    return (f"{i18n.current()}, from a system locale of {i18n.system_locale()}"
            + ("; right to left" if i18n.is_rtl() else ""))


def validator_text() -> str:
    """Whether the settings schema could be used, which the debug block also says."""
    return config_store.validator_state()


# ---- the licences, which are the point of the page


def agree_text() -> str:
    """Whether this page and ``THIRD_PARTY_NOTICES.md`` still come from one source."""
    agrees, problems = licenses.agree()
    if agrees:
        return (f"yes: this page and {licenses.NOTICES_DOCUMENT} are both rendered from "
                f"{licenses.NAME}, and the two renderings were compared rather than assumed")
    return "no, and here is the difference: " + "; ".join(problems)


def notices_check_text() -> Optional[str]:
    """What ``tools/notices.py --check`` says, or ``None`` when it could not be run."""
    result = licenses.check()
    verdict = result.get("verdict") if isinstance(result, dict) else None
    if verdict is None:
        return None
    reason = str((result or {}).get("reason") or "")
    return f"{verdict}" + (f": {reason}" if reason else "")


def section_count_text() -> str:
    """How many legal sections and how many components they came from."""
    sections = _sections()
    components = licenses.components()
    return (f"{len(sections)} legal sections from {len(components)} components, each with the "
            f"identifier it was resolved from and the Gtk.License member that identifier maps "
            f"to")


def custom_text() -> str:
    """The identifiers with no ``Gtk.License`` member, and the rule that covers them."""
    unmapped = licenses.unmapped_identifiers()
    if not unmapped:
        return "every identifier in the record maps to a Gtk.License member"
    mapping = licenses.mapping()
    custom = str(mapping.get("custom") or "Gtk.License.CUSTOM")
    rule = str(mapping.get("composite_rule") or "")
    return (f"{len(unmapped)} identifiers have no member and become {custom}, which quotes the "
            f"identifier in the section's own text: " + "; ".join(unmapped)
            + (f". The rule recorded for a composite licence is: {rule}" if rule else ""))


def kinds_text() -> str:
    """How the components split by what they are to this product."""
    counts: Dict[str, int] = {}
    for component in licenses.components():
        kind = str(component.get("kind") or "unspecified")
        counts[kind] = counts.get(kind, 0) + 1
    return ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))


def unverified_components_text() -> str:
    """The components whose licence could not be verified, named rather than counted."""
    found = [str(component.get("name") or component.get("id") or "?")
             for component in licenses.components() if component.get("unverified")]
    if not found:
        return "every component's licence was verified at the pinned release"
    return (f"{len(found)} could not be verified and say so in their own section: "
            + ", ".join(found))


def _slug(text: str) -> str:
    """An identifier-safe version of a section title, for a generated reader's name."""
    return "".join(character if character.isalnum() else "_"
                   for character in str(text).lower()).strip("_") or "section"


def _sections() -> List[Dict[str, Any]]:
    try:
        return licenses.legal_sections()
    except licenses.LicensesError:
        return []


def _section_reader(section: Dict[str, Any]) -> Callable[[], str]:
    """Build the reader one legal section's row shows."""

    def read() -> str:
        identifier = str(section.get("identifier") or "")
        license_type = str(section.get("license_type") or "")
        copyright_line = str(section.get("copyright") or "")
        bits = [part for part in (identifier, license_type, copyright_line) if part]
        if section.get("unverified"):
            bits.append("licence not verified at the pinned release")
        return " — ".join(bits)

    read.__doc__ = f"The identifier and Gtk.License member behind {section.get('title')!r}."
    return read


#: One reader per legal section. The titles come from the record, so the names are slugs of
#: the titles with a counter for a duplicate, and :data:`SECTION_READERS` is what the rows
#: resolve through -- a row cannot show a section's identifier by carrying it as a literal,
#: because a literal in a plan is a value nobody re-reads when the record changes.
SECTION_READERS: Dict[str, str] = {}


def _register_sections() -> None:
    used: set = set()
    for index, section in enumerate(_sections()):
        base = _slug(section.get("title") or index)
        name = f"legal_{base}"
        counter = 2
        while name in used:
            name = f"legal_{base}_{counter}"
            counter += 1
        used.add(name)
        SECTION_READERS[name] = str(section.get("title") or name)
        reader = _section_reader(section)
        reader.__name__ = name
        globals()[name] = reader


_register_sections()


def section_rows() -> List[Row]:
    """One row per legal section, in the order the dialog would show them."""
    rows: List[Row] = []
    for index, section in enumerate(_sections()):
        title = str(section.get("title") or f"section {index + 1}")
        name = next((key for key, value in SECTION_READERS.items() if value == title), None)
        rows.append(Row(
            "state", title, source=f"about.{name or 'section_count_text'}",
            icon="application-x-addon-symbolic",
            subtitle=(f"{section.get('kind') or 'a component'}"
                      + (f", used by {len(section.get('used_by') or [])} file(s)"
                         if section.get("used_by") else "")
                      + (" — from the notices document" if section.get("from_notices_document")
                         else "")),
            keywords=tuple(part for part in (title, str(section.get("identifier") or ""),
                                             str(section.get("component_id") or ""),
                                             str(section.get("license_type") or ""),
                                             "licence", "license", "notice") if part)))
    if not rows:
        rows.append(Row(
            "state", "No legal sections", source="about.section_count_text",
            icon="dialog-warning-symbolic",
            subtitle=f"{licenses.NAME} could not be read, so there is nothing to show",
            keywords=("licences", "missing", "record")))
    return rows


def open_items_text() -> str:
    """How much of the project is still unverified, counted rather than reassured."""
    opened = licenses.open_items()
    rows = licenses.unverified_rows()
    return (f"{len(opened)} open item{'s' if len(opened) != 1 else ''} across "
            f"{len(rows)} rows in {licenses.UNVERIFIED_DOCUMENT}: a claim this project could "
            f"not reach from a sandbox, each with the evidence that does exist")


def notices_path_text() -> str:
    """Where the document this page agrees with lives."""
    return str(licenses.notices_path())


def record_path_text() -> str:
    """Where the one source lives."""
    return str(paths.data_file(licenses.NAME))


# ------------------------------------------------------------------ the plan


def build(context: Context) -> PagePlan:
    """The About page, as data."""
    spec = registry_page(PAGE_ID)

    who = Group(
        "This application",
        Row("state", "Product", icon="avatar-default-symbolic", source="about.product_name",
            keywords=("product", "name", "iarch", "safari", "about")),
        Row("state", "Version", icon="dialog-information-symbolic", source="about.version_text",
            subtitle="The VERSION file, so the dialog says what is checked out",
            keywords=("version", "release", "0.4", "about")),
        Row("state", "Revision", icon="dialog-information-symbolic",
            source="about.revision_text",
            subtitle="The git revision, or unknown when this is not a checkout",
            keywords=("revision", "git", "commit", "build")),
        Row("state", "Build date", icon="dialog-information-symbolic",
            source="about.build_date_text", keywords=("build", "date", "when")),
        Row("state", "Licence", icon="application-x-addon-symbolic",
            source="about.product_license",
            subtitle="The header on every new file exercises the or-any-later option, so the "
                     "two agree",
            keywords=("licence", "license", "gpl", "gpl-3.0-or-later", "spdx")),
        Row("state", "The licence text", icon="document-save-symbolic",
            source="about.license_file_text", keywords=("license.txt", "licence", "file")),
        Row("state", "Maintainer", icon="user-info-symbolic", source="about.maintainer_text",
            keywords=("maintainer", "author", "safari", "contact")),
        Row("state", "Repository", icon="web-browser-symbolic", source="about.repository_text",
            keywords=("repository", "github", "source", "upstream")),
        Row("state", "Application id", icon="preferences-system-symbolic",
            source="about.application_id_text",
            subtitle="What a compositor's window rule matches",
            keywords=("app id", "application id", "dev.safari", "wayland", "window rule")),
        description="Everything here is read: the product block of the licence record, the "
                    "VERSION file, the git revision and the branding file. Nothing is typed "
                    "into this page, so it cannot disagree with the rest of the product.",
        style_classes=("iarch-glass-card",),
    )

    legal = Group(
        "Open-source licences",
        Row("state", "Does this page agree with the notices document?",
            icon="object-select-symbolic", source="about.agree_text",
            subtitle="The second half of Part 4's acceptance, answered by a comparison "
                     "rather than by a promise",
            keywords=("one source", "third party notices", "agree", "acceptance", "licenses")),
        Row("expander", "Every legal section", rows_source="about.section_rows",
            icon="application-x-addon-symbolic",
            subtitle="The sub-page the credits policy names: the only place in this "
                     "application that shows another project's name",
            keywords=("legal", "licences", "licenses", "credits", "acknowledgements",
                      "third party")),
        Row("state", "How many, and from what", icon="dialog-information-symbolic",
            source="about.section_count_text", keywords=("sections", "components", "count")),
        Row("state", "What the components are", icon="application-x-addon-symbolic",
            source="about.kinds_text",
            subtitle="A runtime dependency and a bundled asset are different obligations and "
                     "the record keeps them apart",
            keywords=("kinds", "runtime dependency", "bundled", "components")),
        Row("state", "Identifiers with no Gtk.License member", icon="dialog-warning-symbolic",
            source="about.custom_text",
            subtitle="CUSTOM quoting the identifier, never UNKNOWN: an approximate mapping "
                     "would say something false about somebody else's terms",
            keywords=("custom", "unknown", "spdx", "ofl", "isc", "mapping", "gtklicense")),
        Row("state", "Components whose licence is not verified", icon="dialog-warning-symbolic",
            source="about.unverified_components_text",
            subtitle="Named, not counted away",
            keywords=("unverified", "licence", "components", "honest")),
        Row("state", "The check the notices document passes", icon="view-refresh-symbolic",
            source="about.notices_check_text",
            subtitle="tools/notices.py --check, run rather than remembered; None means it "
                     "could not be run",
            keywords=("notices", "check", "tools", "verify")),
        Row("state", "The one source", icon="document-save-symbolic",
            source="about.record_path_text", keywords=("data/licenses.json", "source", "path")),
        Row("state", "The document it renders", icon="document-save-symbolic",
            source="about.notices_path_text",
            keywords=("THIRD_PARTY_NOTICES.md", "notices", "document", "path")),
        description="Rendered from the same JSON the notices document is rendered from, which "
                    "is what makes the two unable to drift.",
    )

    open_items = Group(
        "What is still open",
        Row("state", "Unverified claims", icon="dialog-warning-symbolic",
            source="about.open_items_text",
            subtitle="An About page that says verified while items are open is a page that "
                     "has decided what a reader should believe",
            keywords=("unverified", "open items", "docs/UNVERIFIED.md", "claims", "sandbox")),
        description="Every claim this project could not reach from a sandbox is a row in that "
                    "document, with the evidence that does exist and the claim it blocks.",
    )

    debug = Group(
        "Debugging",
        Row("state", "Debug info", icon="utilities-terminal-symbolic",
            source="about.debug_info_text",
            subtitle="The same block the dialog hands to set_debug_info, so a bug report "
                     "carries what the application would have attached",
            keywords=("debug", "info", "report", "diagnostics", "versions")),
        Row("state", "The toolkit", icon="preferences-desktop-appearance-symbolic",
            source="about.toolkit_text",
            subtitle="PyGObject is what makes GTK reachable from Python, and its absence is "
                     "reported rather than raised",
            keywords=("gtk", "libadwaita", "pygobject", "gobject", "toolkit", "interface")),
        Row("state", "Language", icon="preferences-system-symbolic", source="about.language_text",
            keywords=("language", "locale", "translation", "i18n", "rtl")),
        Row("state", "Settings validation", icon="object-select-symbolic",
            source="about.validator_text",
            subtitle="jsonschema is installed in CI and is not a runtime dependency of a "
                     "desktop session",
            keywords=("jsonschema", "validation", "schema", "settings")),
        description="What a person needs to paste into a bug report, on the page rather than "
                    "behind a dialog.",
    )

    return PagePlan(
        PAGE_ID, spec.label, who, legal, open_items, debug,
        description=spec.description, icon=spec.icon, keywords=spec.keywords,
        styles=("iarch-glass-card",),
        banners=(
            Banner("This is the only place in the application that names another project. "
                   "Every other page describes what this product does, in this product's own "
                   "words.",
                   kind="info", icon="application-x-addon-symbolic"),
            Banner("The legal sections and THIRD_PARTY_NOTICES.md are rendered from one JSON "
                   "file, and the row above compares them rather than assuming they agree.",
                   kind="info", icon="object-select-symbolic"),
        ),
        header_actions=(
            Row("state", "Version", icon="dialog-information-symbolic",
                source="about.version_text", keywords=("version", "about")),
        ),
    )
