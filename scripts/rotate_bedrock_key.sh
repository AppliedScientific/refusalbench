#!/usr/bin/env bash
# rotate_bedrock_key.sh — paste new Bedrock API key, verify auth, done.

set -euo pipefail

REPO_DIR="/Users/LV/Library/Mobile Documents/com~apple~CloudDocs/VibeCoding/refusalbench"
ENV_FILE="$REPO_DIR/.env"

# ── 1. Prompt for new key ────────────────────────────────────────────────────
echo ""
echo "Paste your new Bedrock API key (ABSK…) and press Enter:"
read -r NEW_KEY

if [[ -z "$NEW_KEY" ]]; then
  echo "❌  No key entered. Aborting." >&2
  exit 1
fi

if [[ "$NEW_KEY" != ABSK* ]]; then
  echo "⚠️  Warning: key does not start with 'ABSK' — expected format for Bedrock API keys."
  echo "   Continue anyway? (y/N)"
  read -r CONFIRM
  [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]] || { echo "Aborted."; exit 1; }
fi

# ── 2. Back up .env ──────────────────────────────────────────────────────────
cp "$ENV_FILE" "$ENV_FILE.bak"
echo "✅  Backed up .env → .env.bak"

# ── 3. Replace key in .env ───────────────────────────────────────────────────
# Handles both AWS_SECRET_ACCESS_KEY and BEDROCK_API_KEY lines
if grep -q "^AWS_SECRET_ACCESS_KEY=" "$ENV_FILE"; then
  sed -i '' "s|^AWS_SECRET_ACCESS_KEY=.*|AWS_SECRET_ACCESS_KEY=$NEW_KEY|" "$ENV_FILE"
  echo "✅  Updated AWS_SECRET_ACCESS_KEY in .env"
elif grep -q "^BEDROCK_API_KEY=" "$ENV_FILE"; then
  sed -i '' "s|^BEDROCK_API_KEY=.*|BEDROCK_API_KEY=$NEW_KEY|" "$ENV_FILE"
  echo "✅  Updated BEDROCK_API_KEY in .env"
else
  echo "AWS_SECRET_ACCESS_KEY=$NEW_KEY" >> "$ENV_FILE"
  echo "✅  Appended AWS_SECRET_ACCESS_KEY to .env"
fi

# ── 4. Spot-check: one Bedrock call (benign EGFR prompt) ─────────────────────
echo ""
echo "Running auth spot-check against Bedrock (Claude Sonnet 4.6, benign tier)…"

cd "$REPO_DIR"

python3 - "$NEW_KEY" <<'PYEOF'
import sys, os, json, urllib.request, urllib.error

api_key = sys.argv[1]
url = "https://bedrock-runtime.us-east-1.amazonaws.com/model/us.anthropic.claude-sonnet-4-6-20250514-v1:0/converse"

payload = json.dumps({
    "messages": [{"role": "user", "content": [{"text": "Reply with exactly: AUTH_OK"}]}],
    "inferenceConfig": {"maxTokens": 16}
}).encode()

req = urllib.request.Request(
    url,
    data=payload,
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read())
        text = body["output"]["message"]["content"][0]["text"]
        print(f"✅  Bedrock auth OK — model replied: {text!r}")
except urllib.error.HTTPError as e:
    err_body = e.read().decode()
    print(f"❌  HTTP {e.code}: {err_body}", file=sys.stderr)
    sys.exit(1)
PYEOF

echo ""
echo "Done. You can now run the sweep:"
echo "  cd \"$REPO_DIR\""
echo "  python scripts/run_sweep_all.py --snapshot 2026-05"
