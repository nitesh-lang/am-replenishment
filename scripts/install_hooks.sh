#!/usr/bin/env bash
# One-command installer for the data-health audit pre-commit hook.
#
# Usage:
#   bash scripts/install_hooks.sh
#
# After install, any `git commit` that stages files under data/input/
# will auto-run scripts/data_health_audit.py and block the commit on
# FAIL. Bypass in emergencies with: git commit --no-verify

set -eu

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK_SRC="$REPO_ROOT/scripts/hooks/pre-commit"
HOOK_DST="$REPO_ROOT/.git/hooks/pre-commit"

if [ ! -f "$HOOK_SRC" ]; then
    echo "✗ Source hook missing: $HOOK_SRC"
    exit 1
fi

# Back up any existing hook before overwriting
if [ -f "$HOOK_DST" ]; then
    BACKUP="$HOOK_DST.bak.$(date +%Y%m%d_%H%M%S)"
    echo "  Existing hook found — backing up to:"
    echo "  $BACKUP"
    cp "$HOOK_DST" "$BACKUP"
fi

cp "$HOOK_SRC" "$HOOK_DST"
chmod +x "$HOOK_DST"

echo
echo "✓ Pre-commit hook installed at:"
echo "  $HOOK_DST"
echo
echo "  Next time you stage files under data/input/ and run 'git commit',"
echo "  the audit will auto-run and block the commit on FAIL."
echo
echo "  Bypass (emergencies only):  git commit --no-verify"
