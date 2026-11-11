# Copyright (C) 2026 Safari — GPL-3.0-or-later
"""No broken references: every path a script or document names must exist."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Directories that only ever mean "inside this repository" when a script names
# them without a leading $HOME, ~ or /.
REPO_DIRS = ("lib", "tools", "scripts", "branding", "data", "docs", "assets",
             "profiles", "pipewire", "legacy", ".config", "tests", "iarch")

INSTALLERS = ("install.sh", "fedora_install.sh", "uninstall.sh",
              "legacy/install-v4-session.sh", "legacy/uninstall-v4-session.sh",
              "legacy/legacy-install.sh")

# Repo-relative reference: not preceded by a path character, so runtime paths
# like $HOME/.config/hypr and /etc/pacman.conf are never mistaken for ours.
REPO_PATH = re.compile(
    rf"(?<![\w$/~.+-])((?:{'|'.join(re.escape(d) for d in REPO_DIRS)})(?:/[A-Za-z0-9._/*-]+)?)"
)
# The same reference reached through the installer's own root variable.
# The installers reach almost every repository path through one of these:
# SCRIPT_DIR and REPO_DIR in install.sh and fedora_install.sh, repo_dir in
# uninstall.sh. Matching them is what gives this check its coverage.
ROOT_VARIABLES = ("REPO_ROOT", "REPO_DIR", "SCRIPT_DIR", "repo_dir", "ROOT")
ROOTED_PATH = re.compile(
    rf"\$(?:\{{)?(?:{'|'.join(ROOT_VARIABLES)})\}}?/"
    rf"((?:{'|'.join(re.escape(d) for d in REPO_DIRS)})(?:/[A-Za-z0-9._/*-]+)?)"
)


def tracked(suffix: str = "") -> list[str]:
    """Tracked paths relative to the repository root, NUL-separated so that
    non-ASCII filenames are not quoted by git."""
    out = subprocess.run(["git", "ls-files", "-z", f"*{suffix}"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [line for line in out.split("\0") if line]


def clean(token: str) -> str:
    return token.rstrip(".,;:)]}'\"")


class InstallerPaths(unittest.TestCase):
    """Every repository path an installer names has to be there on a fresh clone."""

    def references(self, script: Path) -> set[str]:
        text = script.read_text(encoding="utf-8", errors="replace")
        found = {clean(m.group(1)) for m in REPO_PATH.finditer(text)}
        found |= {clean(m.group(1)) for m in ROOTED_PATH.finditer(text)}
        return found

    def test_every_referenced_path_exists(self):
        checked = 0
        all_references: set[str] = set()
        for name in INSTALLERS:
            script = ROOT / name
            with self.subTest(script=name):
                self.assertTrue(script.is_file(), f"installer is missing: {name}")
            references = self.references(script)
            all_references |= references
            for token in sorted(references):
                # A runtime destination the installer creates on the target
                # machine is not a repository file; those are always absolute or
                # variable-prefixed and the regex above already excluded them.
                with self.subTest(script=name, path=token):
                    if "*" in token:
                        matches = list(ROOT.glob(token))
                        self.assertTrue(matches, f"{name} globs something absent: {token}")
                    else:
                        self.assertTrue((ROOT / token).exists(), f"{name} names a missing path: {token}")
                    checked += 1
        # Named rather than counted: these are the references whose absence
        # would break an install on a fresh clone.
        for required in ("lib/stage-v5-config.sh", "lib/iarch-common.sh",
                         "branding/product.env", ".config", ".config/hypr"):
            with self.subTest(reference=required):
                self.assertIn(required, all_references,
                              "the installers no longer name this path; is the extraction stale?")
                self.assertTrue((ROOT / required).exists())
        self.assertGreater(checked, 12, "the reference extraction found almost nothing")

    def test_the_v5_payload_the_installers_deploy_is_complete(self):
        for name in ("install.sh", "fedora_install.sh"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(installer=name):
                self.assertIn("lib/stage-v5-config.sh", text)
                self.assertTrue((ROOT / "lib" / "stage-v5-config.sh").is_file())

    def test_branding_env_is_sourced_from_a_path_that_exists(self):
        for name in ("install.sh", "fedora_install.sh"):
            text = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(installer=name):
                self.assertIn("branding/product.env", text)
                self.assertTrue((ROOT / "branding" / "product.env").is_file())


class DocumentLinks(unittest.TestCase):
    """Markdown links and images resolve, including the historical documents."""

    def targets(self, document: Path) -> list[str]:
        text = document.read_text(encoding="utf-8", errors="replace")
        found = re.findall(r"\]\(([^)\s]+)\)", text)
        found += re.findall(r'<img[^>]+src="([^"]+)"', text)
        return [t for t in found
                if not t.startswith(("http://", "https://", "mailto:", "#", "//"))]

    def test_every_relative_link_resolves(self):
        documents = [ROOT / name for name in tracked(".md")]
        self.assertTrue(documents)
        checked = 0
        for document in documents:
            for target in self.targets(document):
                path = target.split("#", 1)[0]
                if not path:
                    continue
                resolved = (ROOT / path.lstrip("/")) if path.startswith("/") else (document.parent / path)
                with self.subTest(document=document.relative_to(ROOT).as_posix(), link=target):
                    self.assertTrue(resolved.exists(), f"broken link: {target}")
                    checked += 1
        self.assertGreater(checked, 40, "link extraction found almost nothing")

    def test_readme_images_exist_and_are_small_enough_to_ship(self):
        readme = ROOT / "README.md"
        for target in self.targets(readme):
            path = (readme.parent / target.split("#", 1)[0])
            if path.suffix in {".png", ".webp", ".jpg"}:
                with self.subTest(image=target):
                    self.assertTrue(path.is_file())
                    self.assertLess(path.stat().st_size, 1_500_000,
                                    f"{target} is too large to display from a clone; "
                                    "render a WebP at quality 85 instead")


class RepositoryShape(unittest.TestCase):
    def test_no_submodule_or_gitlink(self):
        """A missing .config/kitty/kitty-themes submodule used to be a hazard."""
        tree = subprocess.run(["git", "ls-tree", "-r", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, check=True).stdout
        gitlinks = [line.split("\t", 1)[1] for line in tree.splitlines()
                    if line.split()[0] == "160000"]
        self.assertEqual([], gitlinks, "a gitlink makes a plain clone incomplete")
        self.assertFalse((ROOT / ".gitmodules").exists())
        self.assertFalse((ROOT / ".config" / "kitty" / "kitty-themes").exists())

    def test_generated_files_are_tracked_so_a_fresh_clone_has_them(self):
        """CI checks they are up to date; here, that they are committed at all."""
        tracked_files = set(tracked())
        for generated in ("THIRD_PARTY_NOTICES.md", "data/licenses.json",
                          "data/keybinds.default.json", "docs/SHORTCUTS.md"):
            with self.subTest(path=generated):
                self.assertIn(generated, tracked_files,
                              "a generated file must be committed, not built at clone time")
                self.assertTrue((ROOT / generated).is_file())

    def test_the_workflow_the_badge_names_is_the_workflow_that_exists(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        badge = re.search(r"actions/workflow/status/[^/]+/[^/]+/([\w.-]+\.yml)", readme)
        self.assertIsNotNone(badge, "README lost its CI badge")
        self.assertTrue((ROOT / ".github" / "workflows" / badge.group(1)).is_file(),
                        f"badge points at a workflow that does not exist: {badge.group(1)}")
        workflows = list((ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(1, len(workflows), "exactly one workflow keeps the badge unambiguous")


if __name__ == "__main__":
    unittest.main()
