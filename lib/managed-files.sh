# Classify an installed system file without changing it.
# Usage: managed_file_state SOURCE TARGET -> absent|identical|symlink|unmanaged|modified|missing-source
managed_file_state() {
    local source=$1 target=$2
    if [[ ! -f $source ]]; then printf 'missing-source\n'
    elif [[ -L $target ]]; then printf 'symlink\n'
    elif [[ ! -e $target ]]; then printf 'absent\n'
    elif ! grep -q '^# Managed by minimaLinux session installer$' "$target"; then printf 'unmanaged\n'
    elif cmp -s -- "$source" "$target"; then printf 'identical\n'
    else printf 'modified\n'
    fi
}
