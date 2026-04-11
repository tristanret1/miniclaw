#!/usr/bin/env bash
set -euo pipefail

PIDS=()

cleanup() {
    echo "Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# ── SMS tunnel ───────────────────────────────────────────────────────────────
PORT="${SMS_WEBHOOK_PORT:-8080}"

if command -v ngrok &>/dev/null; then
    ngrok http "$PORT" --log=stdout --log-level=warn &
    PIDS+=($!)
    sleep 3
    TUNNEL_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
        | python3 -c "import sys,json; ts=json.load(sys.stdin)['tunnels']; print(next(t['public_url'] for t in ts if t['public_url'].startswith('https')))" 2>/dev/null || true)

    if [ -n "$TUNNEL_URL" ]; then
        FULL_URL="${TUNNEL_URL}/sms"
        echo "SMS tunnel: $FULL_URL"

        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|^SMS_WEBHOOK_URL=.*|SMS_WEBHOOK_URL=$FULL_URL|" .env 2>/dev/null || echo "SMS_WEBHOOK_URL=$FULL_URL" >> .env
        else
            sed -i "s|^SMS_WEBHOOK_URL=.*|SMS_WEBHOOK_URL=$FULL_URL|" .env 2>/dev/null || echo "SMS_WEBHOOK_URL=$FULL_URL" >> .env
        fi
    else
        echo "Warning: ngrok started but could not detect tunnel URL"
    fi
else
    echo "Warning: ngrok not found — no SMS tunnel"
fi

# ── Start bot ────────────────────────────────────────────────────────────────
PYTHON="python"
[ -x "venv/bin/python" ] && PYTHON="venv/bin/python"

$PYTHON main.py &
PIDS+=($!)

wait "${PIDS[-1]}"
