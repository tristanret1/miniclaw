#!/usr/bin/env bash
set -euo pipefail

PORT="${SMS_WEBHOOK_PORT:-8080}"
TUNNEL_PID=""
BOT_PID=""

cleanup() {
    echo "Shutting down..."
    [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null || true
    [ -n "$BOT_PID" ] && kill "$BOT_PID" 2>/dev/null || true
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# ── Detect tunnel tool ───────────────────────────────────────────────────────
TUNNEL_URL=""

if command -v ngrok &>/dev/null; then
    # ngrok: start tunnel, query API for public URL
    ngrok http "$PORT" --log=stdout --log-level=warn &
    TUNNEL_PID=$!
    sleep 3
    TUNNEL_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null \
        | python3 -c "import sys,json; ts=json.load(sys.stdin)['tunnels']; print(next(t['public_url'] for t in ts if t['public_url'].startswith('https')))" 2>/dev/null || true)

elif command -v cloudflared &>/dev/null; then
    # cloudflared: start quick tunnel, query metrics endpoint
    cloudflared tunnel --url "http://localhost:$PORT" &
    TUNNEL_PID=$!
    sleep 3
    CF_HOST=$(curl -s "http://localhost:$((PORT + 1))/quicktunnel" 2>/dev/null \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['hostname'])" 2>/dev/null || true)
    [ -n "$CF_HOST" ] && TUNNEL_URL="https://$CF_HOST"

else
    echo "Warning: neither ngrok nor cloudflared found — no tunnel started"
fi

# ── Update .env with tunnel URL ──────────────────────────────────────────────
if [ -n "$TUNNEL_URL" ]; then
    FULL_URL="${TUNNEL_URL}/sms"
    echo "Tunnel URL: $FULL_URL"

    # sed -i behaves differently on macOS vs Linux
    if [[ "$(uname)" == "Darwin" ]]; then
        SED_INPLACE=(sed -i '')
    else
        SED_INPLACE=(sed -i)
    fi

    if grep -q "^SMS_WEBHOOK_URL=" .env 2>/dev/null; then
        "${SED_INPLACE[@]}" "s|^SMS_WEBHOOK_URL=.*|SMS_WEBHOOK_URL=$FULL_URL|" .env
    else
        echo "SMS_WEBHOOK_URL=$FULL_URL" >> .env
    fi
    echo "Updated .env with SMS_WEBHOOK_URL=$FULL_URL"
    echo "Remember to update Twilio Console webhook to: $FULL_URL"
else
    echo "Warning: could not detect tunnel URL"
fi

# ── Start bot ────────────────────────────────────────────────────────────────
# Use venv python if available (production), otherwise bare python
if [ -x "venv/bin/python" ]; then
    venv/bin/python main.py &
else
    python main.py &
fi
BOT_PID=$!

wait $BOT_PID
