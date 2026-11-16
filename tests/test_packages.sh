#!/usr/bin/env bash
# Copyright (C) 2026 Safari — GPL-3.0-or-later
# lib/packages.sh against a pacman and a yay that answer from files.
#
# There is no pacman, no yay and no Arch system in a CI runner or in the
# development sandbox, so the two binaries are stubbed and the questions asked
# of them are written down. What that proves is the decision this library makes
# -- which names reach a transaction, and that a machine which is already
# current reaches none -- and it is recorded in docs/UNVERIFIED.md that it has
# never been proven against the real package manager.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"

cat > "$tmp/bin/pacman" <<'MOCK'
#!/usr/bin/env bash
# A pacman that answers from two files and writes down what it was asked.
printf '%s\n' "pacman $*" >> "$MOCK_LOG"
case "$1" in
    -Sy)
        exit 0
        ;;
    -Qq)
        shift
        [[ $# == 1 ]] || { printf 'mock: -Qq takes one name\n' >&2; exit 2; }
        if grep -Fxq -- "$1" "$MOCK_INSTALLED"; then exit 0; else exit 1; fi
        ;;
    -Quq)
        cat "$MOCK_OUTDATED"
        exit 0
        ;;
    -S)
        printf '%s\n' "TRANSACTION $*" >> "$MOCK_LOG"
        exit 0
        ;;
esac
printf 'mock: unexpected operation %s\n' "$1" >&2
exit 2
MOCK

cat > "$tmp/bin/sudo" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "sudo $*" >> "$MOCK_LOG"
if [[ ${1-} == -u ]]; then shift 2; fi
exec "$@"
MOCK

cat > "$tmp/bin/yay" <<'MOCK'
#!/usr/bin/env bash
printf '%s\n' "TRANSACTION yay $*" >> "$MOCK_LOG"
exit 0
MOCK

chmod +x "$tmp/bin/pacman" "$tmp/bin/sudo" "$tmp/bin/yay"
export PATH="$tmp/bin:$PATH"
export MOCK_LOG="$tmp/log" MOCK_INSTALLED="$tmp/installed" MOCK_OUTDATED="$tmp/outdated"
printf '' > "$MOCK_LOG"; printf '' > "$MOCK_INSTALLED"; printf '' > "$MOCK_OUTDATED"

# shellcheck source=../lib/packages.sh
# shellcheck source=lib/packages.sh
source "$repo/lib/packages.sh"

failures=0
assert_eq() {  # GOT WANT WHY
    if [[ $1 != "$2" ]]; then
        printf 'FAIL %s\n  want: %s\n  got:  %s\n' "$3" "$2" "$1" >&2
        failures=$((failures + 1))
    fi
}
transactions() { grep '^TRANSACTION' "$MOCK_LOG" || true; }
reset_mocks() {
    printf '' > "$MOCK_LOG"; printf '' > "$MOCK_INSTALLED"; printf '' > "$MOCK_OUTDATED"
    packages_invalidate_cache
}

# 1. Everything current: the plan says so and no transaction is opened at all.
reset_mocks
printf 'hyprland\nfish\nkitty\n' > "$MOCK_INSTALLED"
report=$(packages_install 'core' hyprland fish kitty 2>&1)
assert_eq "$report" '  core: 0 to install, 0 to update, 3 already current' \
    'an all-current machine must be told it is all-current'
assert_eq "$(transactions)" '' 'an all-current machine must open no transaction'

# 2. Mixed: only the missing and the outdated reach pacman, in that order.
reset_mocks
printf 'hyprland\nfish\n' > "$MOCK_INSTALLED"
printf 'fish\n' > "$MOCK_OUTDATED"
packages_install 'core' hyprland fish kitty waybar > /dev/null
assert_eq "$(transactions)" 'TRANSACTION -S --noconfirm --needed kitty waybar fish' \
    'only the missing and the outdated may be passed to pacman'

# 3. Only outdated, no missing: the empty array must not become an argument.
reset_mocks
printf 'hyprland\nfish\n' > "$MOCK_INSTALLED"
printf 'hyprland\n' > "$MOCK_OUTDATED"
packages_install 'core' hyprland fish > /dev/null
assert_eq "$(transactions)" 'TRANSACTION -S --noconfirm --needed hyprland' \
    'an empty missing list must not add an empty argument'

# 4. Only missing, no outdated: the same on the other side.
reset_mocks
printf 'hyprland\n' > "$MOCK_INSTALLED"
packages_install 'core' hyprland kitty > /dev/null
assert_eq "$(transactions)" 'TRANSACTION -S --noconfirm --needed kitty' \
    'an empty outdated list must not add an empty argument'

# 5. Nothing installed at all: every target is installed, and --needed is still
#    passed, because the local database can move between the read and the write.
reset_mocks
packages_install 'core' hyprland fish > /dev/null
assert_eq "$(transactions)" 'TRANSACTION -S --noconfirm --needed hyprland fish' \
    'a fresh machine must install everything, still with --needed'

# 6. The three states are what the two queries say, and nothing else.
reset_mocks
printf 'hyprland\nfish\n' > "$MOCK_INSTALLED"
printf 'fish\n' > "$MOCK_OUTDATED"
packages_classify hyprland fish kitty > /dev/null 2>&1 || true
assert_eq "$(package_state kitty)" 'missing' 'a name absent from -Qq is missing'
assert_eq "$(package_state fish)" 'outdated' 'an installed name listed by -Qu is outdated'
assert_eq "$(package_state hyprland)" 'current' 'an installed name -Qu omits is current'

# 7. The sync database is refreshed once per run, not once per call: -Qu only
#    knows about updates the databases describe.
reset_mocks
printf 'hyprland\n' > "$MOCK_INSTALLED"
packages_classify hyprland > /dev/null
packages_classify hyprland > /dev/null
assert_eq "$(grep -c '^pacman -Sy$' "$MOCK_LOG")" '1' '-Sy must run once per installer run'

# 8. AUR targets have no age, so an installed one is left alone and a missing
#    one goes to yay as the unprivileged user, with --needed and no prompts.
reset_mocks
printf 'noctalia-greeter-git\n' > "$MOCK_INSTALLED"
packages_aur_install 'greeter' 'safari' noctalia-greeter-git > /dev/null
assert_eq "$(transactions)" '' 'an installed AUR target must not be rebuilt'
reset_mocks
out=$(packages_aur_install 'greeter' 'safari' noctalia-greeter-git ddcutil-service 2>&1)
assert_eq "$out" '  greeter: 2 to install, 0 already installed
  install: noctalia-greeter-git ddcutil-service' 'the AUR plan must name what it will fetch'
assert_eq "$(grep '^sudo' "$MOCK_LOG")" 'sudo -u safari yay -S --noconfirm --needed --answerclean None --answerdiff None noctalia-greeter-git ddcutil-service' \
    'yay must run as the unprivileged user with no prompt it cannot answer'

if ((failures)); then
    printf '%d package test(s) failed.\n' "$failures" >&2
    exit 1
fi
printf 'Package state tests passed.\n'
