# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""A line citation is a claim, and this file checks the claim.

`install.sh` is a 2,200-line script that the design records, `SECURITY.md`,
`.shellcheckrc` and two docstrings cite by line number, because a line number is the only way to
point at one `sed` expression inside a function that does six things. The price
is that every restructure moves the target and the citation quietly starts
pointing at something else -- not at nothing, which a reader would notice, but
at whatever line now happens to be there.

That is not a hypothetical, and it has happened here twice. Restructuring
`install.sh` into numbered steps left twenty-one citations pointing at the wrong
lines, and two of them were only caught because a test happened to assert the
anchor text: the greeter record's function range and the startup record's `sed`
anchor. The other nineteen were found by reading every citation against the
file. Then the installer-safety pass inserted an argument parser, a prompt
helper and a report step near the top of the same file and moved all
twenty-nine of its citations at once; seven lines added to the failure summary
lower down moved fifty-one more. Both remaps diffed the two revisions of the
file and read the line each citation landed on, which is the only method that
does not assume the rest of the file stood still -- and both times a shorthand
number turned out to be wrong, because a bare ":1740" or ":1037" is exactly the
form this table cannot attribute to a file. The greeter record's Arch shorthand
had been stale since the step restructure, and its fedora one named a
core-package error path instead of the call.

A third drift was found the same way and had never been visible: `.shellcheckrc`
indexes its exceptions by line, and both of its installer numbers were already
wrong before this pass -- one named a comment about the cursor-theme package
instead of the `SC2034` silence, the other named a closing brace. Nothing caught
it because the file has no suffix and no directory this test scanned, so a
faithful remap carried a wrong number to a new wrong line. It is scanned now.

So this file does that reading on every run:

* every `install.sh:NNN` and `fedora_install.sh:NNN` citation in the repository
  has to land inside its file, which catches a citation left behind by a
  deletion;
* every citation in a design record and in `SECURITY.md` has to land on a line
  that still contains the token the citation is about, which catches the
  restructure case;
* and the expectation table has to cover every citation those files contain, so
  a new citation cannot arrive unchecked. That last rule is what keeps the
  table from rotting into a list of the citations somebody once cared about.

Docstrings and prose are deliberately not in the table: they carry no
machine-checked claim, and `docs/UNVERIFIED.md` cites a line to say what is
*not* known there. The two source docstrings that cite the `sed` anchor are
checked by `tests/test_startup_lua.py`, which asserts the anchor itself.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent

#: The files whose citations are claims about code rather than prose.
CITED_SOURCES = ("install.sh", "fedora_install.sh")

#: Where citations are read from. Design records are machine-read and
#: SECURITY.md is the document a person consults before running a privileged
#: script, so a wrong line number there sends them to the wrong operation.
#: `.shellcheckrc` is here because it is an index of exceptions by line, and
#: because it was the one citing file nobody scanned: no suffix in
#: SCANNED_SUFFIXES and no directory in SCANNED_ROOTS, so both of its numbers
#: had drifted before this test could see them.
SCANNED_ROOTS = ("data", "docs", "iarch", "tests", "tools")
SCANNED_FILES = ("README.md", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md",
                 ".shellcheckrc")
SCANNED_SUFFIXES = (".json", ".md", ".py", ".sh")

#: citation -> a token the cited lines must still contain.
#:
#: Written by reading the cited line, not by adding an offset to the old number:
#: an offset assumes nothing else moved, which is the mistake that produced the
#: drift this file exists to catch.
#:
#: A citation written as shorthand -- the greeter record says "called at :2074"
#: on the strength of the "install.sh:" earlier in its sentence -- is not in this
#: table, because a bare ":2074" cannot be attributed to a file without parsing
#: the prose around it. The full citation beside it is checked instead, and that
#: shorthand was stale for one whole restructure before anybody read it. The
#: record's other shorthand points into `fedora_install.sh`, whose lines this
#: pass did not move, and it named an error path rather than the call.
EXPECTATIONS: Dict[Tuple[str, str], str] = {
    # --- data/design/greeter.json: the login screen's installer half ---
    ("install.sh", "2070"): "noctalia-greeter-git",
    ("install.sh", "1683-1732"): "setup_noctalia_greeter() {",
    ("install.sh", "1715-1722"): "default_session",
    ("install.sh", "1690-1692"): "command -v",
    ("install.sh", "1694-1697"): "useradd",
    ("install.sh", "1700-1707"): "chmod 0750",
    ("install.sh", "1724-1731"): "setup_greetd_pam",
    ("install.sh", "2080-2084"): "greetd",
    ("install.sh", "2080"): "systemctl disable sddm",
    ("install.sh", "2081-2084"): "systemctl enable greetd",
    ("install.sh", "2035-2061"): "systemctl is-enabled",
    ("fedora_install.sh", "558-607"): "setup_noctalia_greeter() {",
    ("fedora_install.sh", "590-597"): "default_session",
    ("fedora_install.sh", "576-582"): "chmod 0750",
    ("fedora_install.sh", "599-606"): "setup_greetd_pam",
    # --- data/design/startup.json: what the compositor runs at startup ---
    ("install.sh", "1406-1408"): "enable_nvidia_optional",
    ("install.sh", "729"): "qt6ct",
    ("install.sh", "659"): "gnome-keyring",
    ("install.sh", "779-781"): "easyeffects",
    ("fedora_install.sh", "858-860"): "enable_nvidia_optional",
    ("fedora_install.sh", "847"): "polkit",
    ("fedora_install.sh", "836-854"): "polkit",
    # --- data/design/xdg-defaults.json: the file-manager association ---
    ("install.sh", "1568"): "xdg-mime default thunar",
    ("fedora_install.sh", "910"): "xdg-mime default thunar",
    ("fedora_install.sh", "1115"): "inode/directory",
    # --- SECURITY.md: the operations it warns about, by line ---
    ("install.sh", "1841"): "pacman -Syu --noconfirm",
    ("install.sh", "1127"): "pacman -Rns --noconfirm",
    ("install.sh", "1044"): "chaotic-keyring",
    ("install.sh", "1049"): "chaotic-mirrorlist",
    ("install.sh", "2063-2085"): "noctalia-greeter-git",
    ("install.sh", "1182"): "cups",
    ("install.sh", "1198"): "bluetooth",
    ("install.sh", "1707"): "chown",
    ("fedora_install.sh", "582"): "chown",
    ("fedora_install.sh", "523-542"): "systemctl",
    ("fedora_install.sh", "92-104"): "copr",
    # --- .shellcheckrc: the index of exceptions, by the line each one is on ---
    ("install.sh", "832"): "disable=SC2034",
    ("fedora_install.sh", "471"): "disable=SC2034",
}

CITATION = re.compile(r"(?<![\w-])(fedora_install|install)\.sh:(\d+)(?:-(\d+))?")


def sources() -> Dict[str, List[str]]:
    return {name: (ROOT / name).read_text(encoding="utf-8").splitlines()
            for name in CITED_SOURCES}


def scanned_files() -> List[Path]:
    found = {ROOT / name for name in SCANNED_FILES if (ROOT / name).is_file()}
    for root in SCANNED_ROOTS:
        for path in (ROOT / root).rglob("*"):
            if path.suffix in SCANNED_SUFFIXES and path.is_file():
                found.add(path)
    # A record may cite a line in a document that no longer exists; skipping a
    # missing file would hide that, so the set is asserted complete instead.
    return sorted(found)


def citations() -> List[Tuple[str, int, str, str]]:
    """Every citation in the scanned files: (where, line, source, range)."""
    out = []
    for path in scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), 1):
            for match in CITATION.finditer(line):
                cite = match.group(2)
                if match.group(3):
                    cite += "-" + match.group(3)
                out.append((str(path.relative_to(ROOT)), number,
                            match.group(1) + ".sh", cite))
    return out


def window(lines: List[str], cite: str) -> str:
    start, _, end = cite.partition("-")
    return "\n".join(lines[int(start) - 1:int(end or start)])


class EveryCitationPointsInsideItsFile(unittest.TestCase):
    """The cheap half: a citation past the end of the file is always wrong."""

    def test_there_are_citations_to_check(self):
        """An empty scan would pass every test below it and prove nothing."""
        found = citations()
        self.assertGreater(len(found), 20,
                           "the scan found almost nothing, so either the installer stopped "
                           "being cited by line or the scan stopped finding the files -- "
                           "both of which would make this file a decoration")

    def test_no_citation_points_past_the_end_of_its_file(self):
        lines = sources()
        for where, number, source, cite in citations():
            with self.subTest(citation=f"{where}:{number} -> {source}:{cite}"):
                start, _, end = cite.partition("-")
                self.assertLessEqual(int(end or start), len(lines[source]),
                                     f"{where}:{number} cites {source}:{cite}, which is past "
                                     f"the end of a {len(lines[source])}-line file: the "
                                     f"citation outlived the code it pointed at")
                self.assertLessEqual(int(start), int(end or start),
                                     f"{where}:{number} cites a range that runs backwards")


class EveryCheckedCitationStillSaysWhatItClaims(unittest.TestCase):
    """The half that needs a token: the line moved, and something else is there now."""

    def test_the_cited_lines_contain_the_token(self):
        lines = sources()
        for where, number, source, cite in citations():
            token = EXPECTATIONS.get((source, cite))
            if token is None:
                continue
            with self.subTest(citation=f"{where}:{number} -> {source}:{cite}"):
                text = window(lines[source], cite)
                self.assertIn(token, text,
                              f"{where}:{number} cites {source}:{cite} for {token!r}, and "
                              f"those lines no longer contain it. Either the citation moved "
                              f"with a restructure and was not re-pointed, or the code it "
                              f"described changed and the citation is now a claim about "
                              f"something else. Read the file and fix the number; do not "
                              f"add an offset to it.")

    def test_every_expectation_is_used_by_a_real_citation(self):
        """A table entry nothing cites is a check that stopped checking."""
        found = {(source, cite) for _, _, source, cite in citations()}
        for key in sorted(EXPECTATIONS):
            with self.subTest(citation=f"{key[0]}:{key[1]}"):
                self.assertIn(key, found,
                              "nothing cites this line range any more, so the expectation "
                              "is testing a citation that was removed or renumbered -- "
                              "delete it or point it at the citation that replaced it")


class TheTableCoversTheFilesThatMatter(unittest.TestCase):
    """A new citation in a record must arrive with an expectation, or it is unchecked.

    Prose is exempt on purpose. `docs/UNVERIFIED.md` cites a line to say what is
    *not* known there, `CHANGELOG.md` cites lines that no longer exist by design
    because they describe a past state, and the two docstrings that cite the
    `sed` anchor are checked by `tests/test_startup_lua.py`, which asserts the
    anchor text itself rather than a number. What is not exempt is a design
    record -- JSON another program reads -- `SECURITY.md`, which lists the
    privileged operations of a root script by line so that a person can decide
    whether to run it, or `.shellcheckrc`, which lists the findings this
    repository deliberately silences by the line each silence is on. A wrong
    number in any of the three sends a reader to the wrong operation, which is
    worse than no number, and in the third case nobody notices at all: a line
    that carries no `disable=` directive still looks like a line.
    """

    def test_every_record_and_security_citation_is_in_the_table(self):
        missing = []
        for where, number, source, cite in citations():
            checked = (where.startswith("data/") or where == "SECURITY.md"
                       or where == ".shellcheckrc")
            if checked and (source, cite) not in EXPECTATIONS:
                missing.append(f"{where}:{number} -> {source}:{cite}")
        self.assertEqual([], missing,
                         "these citations carry no expectation, so nothing notices when they "
                         "drift. Add each one to EXPECTATIONS with a token read off the line "
                         "it points at -- a token that identifies the operation, not a number "
                         "copied from the citation.")

    def test_the_table_is_not_mostly_prose_it_does_not_check(self):
        """A table nobody cites is a test that passes by being ignored."""
        found = {(source, cite) for _, _, source, cite in citations()}
        used = [key for key in EXPECTATIONS if key in found]
        self.assertGreater(len(used), 20,
                           f"only {len(used)} of {len(EXPECTATIONS)} expectations match a "
                           f"citation in the repository, so the scan and the table have "
                           f"come apart -- probably a file moved out of the scanned roots")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
