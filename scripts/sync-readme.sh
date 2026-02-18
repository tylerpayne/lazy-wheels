#!/bin/bash
# Sync package README to root README
# Replaces everything before "## Repository Structure" in root README
# with the contents of packages/lazy-wheels/README.md

set -e

ROOT_README="README.md"
PKG_README="packages/lazy-wheels/README.md"
MARKER="## Repository Structure"

if [[ ! -f "$PKG_README" ]]; then
    echo "Error: $PKG_README not found"
    exit 1
fi

if [[ ! -f "$ROOT_README" ]]; then
    echo "Error: $ROOT_README not found"
    exit 1
fi

# Extract everything from marker onwards in root README
REPO_SECTION=$(sed -n "/$MARKER/,\$p" "$ROOT_README")

if [[ -z "$REPO_SECTION" ]]; then
    echo "Error: '$MARKER' not found in $ROOT_README"
    exit 1
fi

# Combine package README + repo section
{
    cat "$PKG_README"
    echo ""
    echo "$REPO_SECTION"
} > "$ROOT_README.tmp"

mv "$ROOT_README.tmp" "$ROOT_README"

# Stage the updated root README if it changed
git add "$ROOT_README"
