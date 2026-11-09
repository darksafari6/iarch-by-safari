#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin"
cat > "$tmp/bin/pacman" <<'MOCK'
#!/usr/bin/env bash
set -euo pipefail
[[ "$1" == -Qq ]]
cat "$MOCK_PACKAGES"
MOCK
chmod +x "$tmp/bin/pacman"
export PATH="$tmp/bin:$PATH" MOCK_PACKAGES="$tmp/packages"
# shellcheck source=../lib/package-audit.sh
source "$repo/lib/package-audit.sh"
printf 'fish\nkitty\n' > "$MOCK_PACKAGES"
package_audit_begin "$tmp/log"
printf 'fish\nkitty\nhyprland\n' > "$MOCK_PACKAGES"
package_audit_finish
[[ $(cat "$tmp/log.packages-added") == hyprland ]]
[[ $(stat -c %a "$tmp/log.packages-added") == 600 ]]
printf 'Package audit tests passed.\n'
