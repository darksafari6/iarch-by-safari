# Contributing

Thank you for looking at this. It is one person's desktop session published as
free software, so the rules below exist to keep changes reviewable rather than to
keep people out.

## Before you change anything

Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). It maps the repository, and
it explains the two mutually incompatible configuration payloads (`.config/` for
the current session, `legacy/config/` for the frozen v4 session). Mixing them is
the easiest way to break someone's desktop.

Then check [`docs/UNVERIFIED.md`](docs/UNVERIFIED.md). Every claim this project
cannot yet prove has an id there. If your change makes one of those claims real,
say so in the pull request and update the row — answered rows are kept, not
deleted, because the reasoning is part of the record.

## Running the checks

Everything runs as a normal user. Python 3.11 or newer, standard library only.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'   # all unit tests
./tests/session-install.sh                             # legacy installer, mocked filesystem
./tests/managed-files.sh                               # system-file classification
./tests/package-audit.sh                               # package-addition recording
./tests/test_iarch_common.sh                           # shared shell helpers
./tests/test_uninstall.sh                              # rollback behaviour
python3 tools/notices.py --check                       # credit files match their source
python3 tools/iarch_brand.py --check                   # product naming is consistent
python3 tools/branding_lint.py                         # no upstream name in the everyday UI
python3 tools/extract_keybinds.py --check              # keybind data matches keybind.lua
bash -n install.sh fedora_install.sh uninstall.sh      # shell syntax
shellcheck --severity=warning -- $(git ls-files '*.sh') # shell quality
```

The last two are what CI runs, plus JSON and TOML validation. `shellcheck` is not
a standard-library tool; the exceptions it is allowed are listed with their
reasons in [`.shellcheckrc`](.shellcheckrc).

**Run the tests as your own user, not as root.** Seven installer-CLI tests and
`tests/session-install.sh` are designed to fail under root: the legacy session
installer refuses to run as root, and the tests prove that refusal. A failure
there as root is the correct behaviour, not a bug.

## Rules that are enforced mechanically

| Rule | Enforced by |
| :--- | :--- |
| The repository ships defaults in `data/`; a user never edits repo files after install | `iarch/lib/configstore.py`, `tests/test_config_store.py` |
| Generated files start with the GENERATED header, are written atomically, and keep five backups | `iarch/lib/configstore.py`, `tests/test_config_store.py` |
| The keyboard map is data extracted from `keybind.lua`, never typed by hand | `tools/extract_keybinds.py --check`, `tests/test_keybinds_data.py` |
| Third-party credit is rendered, not hand-written, and no license is guessed | `tools/notices.py --check`, `tests/test_licenses_data.py` |
| New files carry the copyright header defined in `branding/product.env`; vendored code under `legacy/` keeps its own | `tests/test_copyright_headers.py` |
| An effect preset may only lower values of keys the base profile already has | `tools/profile_preset.py`, `tests/test_profile_preset.py` |
| The everyday UI never shows an upstream or previous product name | `tools/branding_lint.py`, `tests/test_branding_lint.py` |
| The v5 payload and the legacy payload never overlap | `tests/test_payload_map.py` |
| `docs/BASELINE.md` stays at or under 80 lines; `README.md` stays under 250 | checked by hand and in review; count with `wc -l` |

## Rules that need a human

**Do not rename frozen identifiers.** Other programs match on them, and renaming
orphans installed systems. Specifically: `~/.config/minimalinux` and the
`minimalinux-session` / `minimalinux-customize` launcher names, the marker line
`# Managed by minimaLinux session installer`, and the generated kitty include
names `minima-colors.conf` and `minima-profile.conf`. What a person reads on
screen is branded; what a program matches on is not.
[`docs/BRANDING.md`](docs/BRANDING.md) explains the line, and
`tools/branding_lint.py` encodes it.

**Do not add binaries or media to the repository without saying why.** Images go
in `assets/` as WebP at quality 85 with a 3840 px width ceiling; keep the
lossless source in `assets/wallpapers/originals/` only when it is worth the
megabytes, and record the command that produced the rendition next to it. Audio
and video do not belong here at all: the release trailer is a YouTube link.

**Do not change installer behaviour in a drive-by fix.** Package installation,
repository edits, service enabling and the display-manager switch are listed in
[`SECURITY.md`](SECURITY.md) with the `INS-` ids they are tracked under. Changing
one of them is legitimate work, but it needs its own pull request with a test
around it.

**Keep commits small and each one green.** A commit that leaves the tests failing
cannot be bisected, and bisecting is how a broken session gets diagnosed.

## Pull requests

1. Branch from `main`. One logical change per pull request.
2. Add or update the test that proves it. If it cannot be tested here — real
   hardware, a live session, a package that only exists on one distribution —
   register it in `docs/UNVERIFIED.md` with an id instead of claiming it works.
3. Update the documents your change makes stale: `docs/ARCHITECTURE.md` for
   layout, `CHANGELOG.md` for behaviour, `README.md` only if a user would notice.
4. Say what you ran and what it printed. "Tests pass" without the command is not
   a review artifact.

Issues are welcome too, especially "this does not work on my machine, here is the
output". Hardware differences are the main source of unverified claims in this
project, and a report closes one.

## License of your contribution

Contributions are licensed under the same GPL-3.0-or-later terms as the rest of
the repository; see [`LICENSE.txt`](LICENSE.txt). New files start with the header
in `branding/product.env`. Do not submit code you do not have the right to
publish, and do not paste upstream configuration into this repository without
checking its license and recording it in
[`branding/notices.json`](branding/notices.json).
