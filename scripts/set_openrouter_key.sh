#!/bin/bash
# Usage:
#   paste as argument:  bash scripts/set_openrouter_key.sh sk-or-...
#   or prompted:        bash scripts/set_openrouter_key.sh

cd "$(dirname "$0")/.." || exit 1

if [ -n "$1" ]; then
    KEY="$1"
else
    read -rp "Paste OpenRouter API key: " KEY
fi

if [ -z "$KEY" ]; then
    echo "No key provided." >&2
    exit 1
fi

# Write or replace OPENROUTER_API_KEY in .env
if grep -q "^OPENROUTER_API_KEY=" .env; then
    sed -i '' "s|^OPENROUTER_API_KEY=.*|OPENROUTER_API_KEY=$KEY|" .env
else
    echo "OPENROUTER_API_KEY=$KEY" >> .env
fi

echo "Done — OPENROUTER_API_KEY written to .env"
