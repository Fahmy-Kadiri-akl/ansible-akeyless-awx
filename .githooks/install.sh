#!/usr/bin/env bash
# Install the repo-versioned hooks by pointing git's core.hooksPath at
# .githooks/. Run from the repo root, or any subdirectory.

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git config core.hooksPath .githooks
chmod +x .githooks/pre-commit .githooks/commit-msg

echo "Installed: core.hooksPath = .githooks"
echo "Hooks armed: pre-commit, commit-msg"
echo
echo "To bypass for a single commit (use sparingly): git commit --no-verify"
echo "To uninstall:                                  git config --unset core.hooksPath"
