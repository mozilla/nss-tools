#!/bin/bash
# Vendor a mercurial tag into the tree.

set -e

declare -A sources=( \
    [nss]=https://hg.mozilla.org/projects/nss \
    [nspr]=https://hg.mozilla.org/projects/nspr \
    )
declare -A destinations=( \
    [nss]=security/nss \
    [nspr]=nsprpub \
    )
declare -A depfiles=( \
    [nss]=coreconf/coreconf.dep \
    [nspr]=config/prdepend.h \
    )

root="$(hg root 2>/dev/null || true)"
cmd=hg
if [[ -z "$root" ]]; then
    cmd=git
    root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
fi
[[ -n "$root" ]] || ! echo "Unable to find repository root and type." 1>&2

is_clean() {
    [[ "$cmd" == "hg" ]] && [[ -z "$(hg status -mardu)" ]]
    [[ "$cmd" == "git" ]] && [[ -z "$(git status --porcelain)" ]]
}

is_clean || ! echo "Unmodified files in repository." 1>&2

usage() {
    echo "Usage: $0 <nss|nspr> <tag> [source]"
    return 2
}

[[ $# -ge 2 ]] || usage

project="${1,,*}"
tag="$2"
source="${3:-${sources[$project]}}"
[[ -n "$source" ]] || \
    ! echo "Unable to determine source for $project."
[[ -n "${destinations[$project]}" ]] || \
    ! echo "Unable to determine destination for $project."
dest="$root/${destinations[$project]}"
depfile="${depfiles[$project]}"

log() {
    echo "run: $@"
    "$@"
}

# If set, use $depfile to tell the gecko build that NSS has changed.
# We do that by alternating between a blank line and the end and not.
if [[ -n "$depfile" ]]; then
    depfile="$dest/$depfile"
    lastline="$(tail -1 "$depfile" 2>/dev/null)"
fi

# Remove the old, replace with the new.
log rm -rf "$dest"
log hg clone -r "$tag" "$source" "$dest"
for remove in .hg .hgignore .hgtags; do
    log rm -rf "$dest/$remove"
done

# Update the metadata files.
echo "Write '$tag' to TAG-INFO"
echo "$tag" > "$dest/TAG-INFO"
if [[ -n "$depfile" ]]; then
    if [[ -n "$lastline" ]]; then
        echo "Adding blank line to $depfile"
        echo >> "$depfile"
    else 
        [[ -n "$(tail -1 "$depfile")" ]] || \
            ! echo "Source for $depfile has a blank line."
    fi
else
    echo "Skipping dependency file update."
fi

# Make a commit with the changes.
log "$cmd" add "$dest"
comment="Bug ${BUG:-XXXXXXX} - Update ${project^^*} to $tag, UPGRADE_${project^^*}_RELEASE, r=me"
log "$cmd" commit -m "$comment" "$dest"
