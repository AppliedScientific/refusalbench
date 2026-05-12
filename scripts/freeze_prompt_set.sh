#!/usr/bin/env bash
# freeze_prompt_set.sh — mark benchmark/prompts/v<version>/ as immutable before a sweep.
#
# Usage: bash scripts/freeze_prompt_set.sh [version]
# Default version: 1.0
#
# This creates a .frozen marker file and tags the git commit.
# CI enforces that benchmark/prompts/v1.0/ is never modified after this tag.

set -euo pipefail

VERSION="${1:-1.0}"
PROMPTS_DIR="benchmark/prompts/v${VERSION}"
FROZEN_MARKER="${PROMPTS_DIR}/.frozen"
GIT_TAG="prompts-v${VERSION}-frozen"

if [ ! -d "${PROMPTS_DIR}" ]; then
  echo "ERROR: ${PROMPTS_DIR} does not exist." >&2
  exit 1
fi

if [ -f "${FROZEN_MARKER}" ]; then
  echo "Already frozen: ${FROZEN_MARKER} exists."
  exit 0
fi

# Validate before freezing
python scripts/validate_prompts.py "${VERSION}"

# Create marker
touch "${FROZEN_MARKER}"
git add "${FROZEN_MARKER}"
git commit -m "freeze: mark benchmark/prompts/v${VERSION}/ immutable before sweep"
git tag "${GIT_TAG}"

echo "Frozen: ${PROMPTS_DIR}"
echo "Git tag created: ${GIT_TAG}"
echo "Run 'git push --tags' to push the tag."
