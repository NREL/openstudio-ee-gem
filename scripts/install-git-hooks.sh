#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Configuring git hooks path to .githooks in ${repo_root}"
git -C "${repo_root}" config core.hooksPath .githooks

echo "Done. Verify with: git -C \"${repo_root}\" config --get core.hooksPath"
