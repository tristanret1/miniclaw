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

# ── Resolve gateway mode ─────────────────────────────────────────────────────
GATEWAYS="${MINICLAW_GATEWAY:-}"
GATEWAY_FLAG=""
if [ -n "$GATEWAYS" ]; then
    GATEWAY_FLAG="--gateway $GATEWAYS"
    echo "Gateway mode: $GATEWAYS"
fi

# ── SMS tunnel (only when sms gateway is active) ─────────────────────────────
needs_sms_tunnel() {
    # No gateway filter = full mode, check config
    [ -z "$GATEWAYS" ] && return 0
    # Explicit gateway list: check if sms is in it
    echo "$GATEWAYS" | grep -qw "sms"
}

if needs_sms_tunnel; then
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
        echo "Warning: SMS enabled but ngrok not found — no tunnel"
    fi
fi

# ── Start bot ────────────────────────────────────────────────────────────────
PYTHON="python"
[ -x "venv/bin/python" ] && PYTHON="venv/bin/python"

$PYTHON main.py $GATEWAY_FLAG &
PIDS+=($!)

wait "${PIDS[-1]}"
