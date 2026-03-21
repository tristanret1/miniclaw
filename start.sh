#!/usr/bin/env bash
set -euo pipefail

PORT="${SMS_WEBHOOK_PORT:-8080}"

cleanup() {
    echo "Shutting down..."
    kill $CF_PID 2>/dev/null || true
    kill $BOT_PID 2>/dev/null || true
    wait 2>/dev/null
}
trap cleanup EXIT INT TERM

# Start cloudflared tunnel in background
cloudflared tunnel --url "http://localhost:$PORT" &
CF_PID=$!

# Wait for cloudflared to print the URL, then update .env
sleep 3
CF_URL=$(curl -s http://localhost:$((PORT + 1))/quicktunnel 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['hostname'])" 2>/dev/null || true)

if [ -n "$CF_URL" ]; then
    FULL_URL="https://$CF_URL/sms"
    echo "Tunnel URL: $FULL_URL"

    # Update SMS_WEBHOOK_URL in .env
    if grep -q "^SMS_WEBHOOK_URL=" .env 2>/dev/null; then
        sed -i '' "s|^SMS_WEBHOOK_URL=.*|SMS_WEBHOOK_URL=$FULL_URL|" .env
    else
        echo "SMS_WEBHOOK_URL=$FULL_URL" >> .env
    fi
    echo "Updated .env with SMS_WEBHOOK_URL=$FULL_URL"
    echo "Remember to update Twilio Console webhook to: $FULL_URL"
else
    echo "Warning: could not detect tunnel URL, check cloudflared output above"
fi

# Start bot
python main.py &
BOT_PID=$!

wait $BOT_PID
