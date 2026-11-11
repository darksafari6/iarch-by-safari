"""Prove which files the v5 Hyprland session loads, and that the payload is closed.

Two independent facts are asserted from the repository itself:

1. the load graph -- every ``require()`` reachable from ``hyprland.lua`` resolves
   to a file that exists, reaches every Lua file that ships, and the scripts the
   keybindings exec exist too;
2. the payload -- the tree ``lib/stage-v5-config.sh`` builds equals an explicit
   list, and nothing the legacy v4 session owns can appear in it.

Keeping the list explicit is the point: adding a file to ``.config`` without
teaching the staging script about it, or dropping one it still copies, fails
here instead of silently changing what gets installed.
"""
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from iarch.lib import configstore  # noqa: E402  (repo-root import)
HYPR = ROOT / '.config/hypr'
LEGACY_CONFIG = ROOT / 'legacy/config'
STAGE_SCRIPT = ROOT / 'lib/stage-v5-config.sh'

# Everything the v5 installer deploys, relative to the staged root.
EXPECTED_PAYLOAD = {
    'fastfetch/config.jsonc',
    'fastfetch/logo/agk_clan.icon',
    'fastfetch/logo/aisaka.icon',
    'fastfetch/logo/geass.icon',
    'fastfetch/logo/hyprland.icon',
    'fastfetch/logo/loli.icon',
    'fastfetch/logo/pochita.icon',
    'fastfetch/logo/ryuzaki.icon',
    'fish/config.fish',
    'fontconfig/fonts.conf',
    'hypr/Scripts/browser-launcher.sh',
    'hypr/Scripts/workspace.sh',
    'hypr/animations.lua',
    'hypr/animations/default.lua',
    'hypr/generated/animations.lua',
    'hypr/generated/glass.lua',
    # hyprlock and hypridle are not Hyprland: each is its own binary that searches
    # for a fixed filename under $XDG_CONFIG_HOME/hypr/. They live beside the Lua
    # payload because that is the only place those two daemons look, not because
    # Hyprland reads them -- see the allowlist in the hyprlang test below.
    'hypr/hypridle.conf',
    'hypr/hyprlock.conf',
    'hypr/hyprland.lua',
    'hypr/inputs.lua',
    'hypr/keybind.lua',
    'hypr/monitors.lua',
    'hypr/startup.lua',
    'hypr/themes/theme.lua',
    'hypr/windowrules.lua',
    'kitty/kitty.conf',
    'kitty/minima-colors.conf',
    'kitty/minima-profile.conf',
    'gtk-3.0/gtk.css',
    'gtk-4.0/gtk.css',
    'Kvantum/kvantum.kvconfig',
    'Kvantum/iarch/iarch.kvconfig',
    'noctalia/config.toml',
    # One palette per colour preset: iarch-theme apply <preset> points
    # theme.custom_palette at that preset's palette, so all of them ship.
    'noctalia/palettes/iarch-aurora.json',
    'noctalia/palettes/iarch-crimson-plasma.json',
    'noctalia/palettes/iarch-frosted-light.json',
    'noctalia/palettes/iarch-midnight.json',
    'noctalia/palettes/iarch-mono-ice.json',
    'noctalia/palettes/iarch-tokyo-night.json',
    'starship.toml',
}


def module_paths(module: str):
    """Resolve a Lua module name the way the package.path in hyprland.lua does."""
    relative = module.replace('.', '/')
    return (HYPR / f'{relative}.lua', HYPR / relative / 'init.lua')


def required_modules(text: str):
    return re.findall(r'require\(\s*[\'"]([^\'"]+)[\'"]\s*\)', text)


def load_graph(entry: Path):
    """Walk require() from entry and return (reached files, unresolved names)."""
    reached, unresolved, pending = set(), set(), [entry]
    while pending:
        current = pending.pop()
        reached.add(current)
        for module in required_modules(current.read_text(encoding='utf-8')):
            for candidate in module_paths(module):
                if candidate.is_file():
                    if candidate not in reached:
                        pending.append(candidate)
                    break
            else:
                unresolved.add(module)
    return reached, unresolved


class HyprlandLoadGraph(unittest.TestCase):
    def test_every_require_resolves_and_reaches_every_shipped_lua_file(self):
        entry = HYPR / 'hyprland.lua'
        self.assertTrue(entry.is_file(), 'hyprland.lua is the session entry point')
        reached, unresolved = load_graph(entry)
        self.assertEqual(set(), unresolved, 'require() targets that resolve to no file')
        shipped = {p for p in HYPR.rglob('*.lua') if p.is_file()}
        self.assertEqual(shipped, reached,
                         'Lua files that ship but are never required, or vice versa')

    def test_scripts_executed_by_keybindings_exist(self):
        keybind = (HYPR / 'keybind.lua').read_text(encoding='utf-8')
        scripts = set(re.findall(r'scrPath\s*\.\.\s*"/([^"]+)"', keybind))
        self.assertTrue(scripts, 'keybind.lua is expected to exec helper scripts')
        for script in sorted(scripts):
            path = HYPR / 'Scripts' / script
            self.assertTrue(path.is_file(), f'keybind.lua execs a missing script: {script}')

    # .conf files that are *not* Hyprlang: each belongs to a separate binary in
    # the Hypr ecosystem that searches for its own fixed filename under
    # $XDG_CONFIG_HOME/hypr/ and has no include mechanism to point elsewhere.
    # hyprlock.conf's search order is recorded in data/design/hyprlock.json
    # (search_path); hypridle.conf's is the same directory.
    ECOSYSTEM_CONF = {
        'hypridle.conf': 'hypridle, the idle daemon (ships unlaunched)',
        'hyprlock.conf': 'hyprlock, the session-lock client',
    }

    def test_no_hyprlang_file_ships_next_to_the_lua_configuration(self):
        leftovers = sorted(str(p.relative_to(HYPR)) for p in HYPR.rglob('*.conf')
                           if p.name not in self.ECOSYSTEM_CONF)
        self.assertEqual([], leftovers,
                         'Hyprlang files beside the Lua payload are not loaded by v5; '
                         'they belong under legacy/config/hypr/')

    def test_every_conf_beside_the_lua_configuration_names_its_own_daemon(self):
        # The allowlist is the point: a .conf that no daemon reads is a file that
        # looks configured and does nothing, which is the exact failure this test
        # exists to catch. So each allowed name has to be one the ecosystem really
        # searches for, and each has to be a generated file with a header saying
        # which tool renders it.
        shipped = {p.name for p in HYPR.rglob('*.conf')}
        self.assertTrue(shipped & set(self.ECOSYSTEM_CONF),
                        'the allowlist no longer matches anything shipped')
        for name in sorted(shipped & set(self.ECOSYSTEM_CONF)):
            with self.subTest(conf=name):
                first = (HYPR / name).read_text(encoding='utf-8').splitlines()[0]
                self.assertTrue(configstore.is_header_line(first),
                                f'{name} line 1 is not a GENERATED header: {first!r}')


class StagedPayload(unittest.TestCase):
    def staged_root(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        dest = Path(tmp.name) / 'stage'
        dest.mkdir()
        result = subprocess.run(['bash', str(STAGE_SCRIPT), str(ROOT / '.config'), str(dest)],
                                capture_output=True, text=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return dest

    def stage(self):
        dest = self.staged_root()
        return {str(p.relative_to(dest)) for p in dest.rglob('*') if p.is_file()}

    def test_payload_is_exactly_the_expected_file_list(self):
        staged = self.stage()
        self.assertEqual(EXPECTED_PAYLOAD, staged)

    # One relative path exists on both sides, and the v5 side must win it:
    # hypridle.conf. hypridle is a separate daemon that only ever reads
    # ~/.config/hypr/hypridle.conf, so the v4 session's hand-written copy and the
    # v5 generated one cannot both be installed -- whichever is copied last is
    # what locks the machine. The v4 copy is superseded, not shared, and the test
    # below proves the staged file is the generated one rather than the legacy
    # bytes.
    SUPERSEDED_BY_V5 = {'hypr/hypridle.conf'}

    def test_legacy_v4_files_cannot_reach_the_payload(self):
        staged = self.stage()
        self.assertTrue(LEGACY_CONFIG.is_dir(), 'legacy/config holds the v4-only payload')
        legacy = {str(p.relative_to(LEGACY_CONFIG)) for p in LEGACY_CONFIG.rglob('*') if p.is_file()}
        self.assertTrue(legacy, 'legacy/config unexpectedly holds no files')
        self.assertEqual(set(), (legacy & staged) - self.SUPERSEDED_BY_V5,
                         'a file the legacy v4 session owns was staged into the v5 payload')

    def test_a_superseded_path_stages_the_generated_file_and_not_the_legacy_bytes(self):
        staged_root = self.staged_root()
        for relative in sorted(self.SUPERSEDED_BY_V5):
            with self.subTest(path=relative):
                staged = staged_root / relative
                legacy = LEGACY_CONFIG / relative
                self.assertTrue(staged.is_file(), f'{relative} was not staged')
                self.assertTrue(legacy.is_file(), f'{relative} is no longer in legacy/config, '
                                'so it is not superseding anything')
                first = staged.read_text(encoding='utf-8').splitlines()[0]
                self.assertTrue(configstore.is_header_line(first),
                                f'{relative} staged without a GENERATED header, so the legacy '
                                f'hand-written file may have been the one copied: {first!r}')
                self.assertNotEqual(staged.read_bytes(), legacy.read_bytes(),
                                    f'{relative} staged byte-identical to the legacy v4 file')

    def test_staging_script_names_the_same_files_as_this_test(self):
        # The list inside the staging script is the deployment source of truth;
        # if it drifts from EXPECTED_PAYLOAD the two checks above can both pass
        # while the installer ships something else.
        text = STAGE_SCRIPT.read_text(encoding='utf-8')
        listed = set(re.search(r'for path in (.+?); do', text, re.S).group(1).split())
        expanded = set()
        for entry in listed:
            if (ROOT / '.config' / entry).is_dir():
                expanded |= {str(p.relative_to(ROOT / '.config'))
                             for p in (ROOT / '.config' / entry).rglob('*') if p.is_file()}
            else:
                expanded.add(entry)
        self.assertEqual(EXPECTED_PAYLOAD, expanded)


if __name__ == '__main__':
    unittest.main()
