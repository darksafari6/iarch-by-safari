# Read-only package inventory for the installer. No package removal is performed.
PACKAGE_AUDIT_STARTED=false
PACKAGE_AUDIT_BEFORE=''
PACKAGE_AUDIT_AFTER=''
PACKAGE_AUDIT_ADDED=''

package_audit_begin() {
    local base=$1
    PACKAGE_AUDIT_BEFORE="$base.packages-before"
    PACKAGE_AUDIT_AFTER="$base.packages-after"
    PACKAGE_AUDIT_ADDED="$base.packages-added"
    if ! (umask 077; pacman -Qq | LC_ALL=C sort > "$PACKAGE_AUDIT_BEFORE"); then
        printf 'Cannot read the package database before installation.\n' >&2
        return 1
    fi
    PACKAGE_AUDIT_STARTED=true
}

package_audit_finish() {
    if ! $PACKAGE_AUDIT_STARTED; then return 0; fi
    PACKAGE_AUDIT_STARTED=false
    if ! (umask 077; pacman -Qq | LC_ALL=C sort > "$PACKAGE_AUDIT_AFTER"); then
        printf 'Warning: cannot read the package database after installation; package changes are unknown.\n' >&2
        return 1
    fi
    if ! (umask 077; comm -13 "$PACKAGE_AUDIT_BEFORE" "$PACKAGE_AUDIT_AFTER" > "$PACKAGE_AUDIT_ADDED"); then
        printf 'Warning: could not calculate package additions.\n' >&2
        return 1
    fi
    printf 'Package additions recorded in %s (review manually; nothing will be removed).\n' "$PACKAGE_AUDIT_ADDED"
}
