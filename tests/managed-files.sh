#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
source "$repo/lib/managed-files.sh"
source_file="$tmp/source"
target="$tmp/target"
printf '# Managed by minimaLinux session installer\noriginal\n' > "$source_file"
[[ $(managed_file_state "$source_file" "$target") == absent ]]
printf 'unrelated user content\n' > "$target"
[[ $(managed_file_state "$source_file" "$target") == unmanaged ]]
[[ $(cat "$target") == 'unrelated user content' ]]
cp "$source_file" "$target"
[[ $(managed_file_state "$source_file" "$target") == identical ]]
printf 'user edit\n' >> "$target"
[[ $(managed_file_state "$source_file" "$target") == modified ]]
[[ $(tail -1 "$target") == 'user edit' ]]
rm "$target"
ln -s "$source_file" "$target"
[[ $(managed_file_state "$source_file" "$target") == symlink ]]
[[ -L $target ]]
[[ $(managed_file_state "$tmp/missing" "$target") == missing-source ]]
echo 'Managed file classification tests passed.'
