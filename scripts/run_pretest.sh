#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

ENV_FILE="$REPO/.env"

# If key not already saved, ask for it and save it
if ! grep -q "^AWS_SECRET_ACCESS_KEY=." "$ENV_FILE" 2>/dev/null; then
    echo "Paste your AWS secret key and press Enter:"
    read -r key
    printf "AWS_SECRET_ACCESS_KEY=%s\nAWS_REGION=us-east-1\n" "$key" > "$ENV_FILE"
    echo "Key saved."
fi

set -o allexport
source "$ENV_FILE"
set +o allexport

source "$REPO/.venv/bin/activate"
exec python scripts/pretest_opus47.py
