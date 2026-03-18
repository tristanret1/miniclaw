#!/bin/bash
# Deploy miniclaw to EC2 via SSM
# Usage: ./scripts/deploy.sh

set -euo pipefail

PROFILE="sen"
INSTANCE_ID="i-041a7fb83cf05fe63"
REPO="git@github.com:shou2077/miniclaw.git"
APP_DIR="/home/ubuntu/miniclaw"
SERVICE_NAME="miniclaw"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }

run_remote() {
    local cmd="$1"
    local cmd_id
    local status
    local i

    [[ -z "$PROFILE" ]] && { echo "PROFILE is empty" >&2; return 1; }
    [[ -z "$INSTANCE_ID" ]] && { echo "INSTANCE_ID is empty" >&2; return 1; }
    [[ -z "$cmd" ]] && { echo "Command is empty" >&2; return 1; }

    printf 'Running remote command: %q\n' "$cmd"

    if ! cmd_id=$(aws ssm send-command \
        --profile "$PROFILE" \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters commands="$cmd" \
        --timeout-seconds 120 \
        --output text \
        --query "Command.CommandId"); then
        echo "Failed to send command" >&2
        return 1
    fi

    echo "Command ID: $cmd_id"
    echo "Running command..."

    sleep 2

    for i in {1..70}; do
        if ! status=$(aws ssm get-command-invocation \
            --profile "$PROFILE" \
            --instance-id "$INSTANCE_ID" \
            --command-id "$cmd_id" \
            --query "Status" \
            --output text 2>/dev/null); then
            sleep 2
            continue
        fi

        case "$status" in
            Success)
                aws ssm get-command-invocation \
                    --profile "$PROFILE" \
                    --instance-id "$INSTANCE_ID" \
                    --command-id "$cmd_id" \
                    --query "StandardOutputContent" \
                    --output text
                return 0
                ;;
            Failed|TimedOut|Cancelled|Cancelling)
                echo "Command ended with status: $status" >&2
                aws ssm get-command-invocation \
                    --profile "$PROFILE" \
                    --instance-id "$INSTANCE_ID" \
                    --command-id "$cmd_id" \
                    --query "{stdout:StandardOutputContent,stderr:StandardErrorContent}" \
                    --output json
                return 1
                ;;
            Pending|InProgress|Delayed)
                ;;
            *)
                echo "Unknown status: $status" >&2
                ;;
        esac

        sleep 2
    done

    echo "Command polling timed out" >&2
    return 1
}

# Step 1: Install deps + clone/pull repo
log "Setting up instance..."
run_remote "\"apt-get update -qq && apt-get install -y -qq python3-pip python3-venv git > /dev/null 2>&1 && echo deps-ok\""

# Step 2: Clone or pull
log "Deploying code..."
run_remote "\"sudo -u ubuntu bash -c 'if [ -d $APP_DIR ]; then cd $APP_DIR && git pull --rebase; else git clone $REPO $APP_DIR; fi'\""

# Step 3: Install Python deps
log "Installing Python packages..."
run_remote "\"sudo -u ubuntu bash -c 'cd $APP_DIR && python3 -m venv venv && source venv/bin/activate && pip install -q -r requirements.txt'\""

# Step 4: Upload .env and .credentials.json via SSM parameter store
log "Uploading secrets..."
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

aws ssm put-parameter --profile "$PROFILE" \
    --name "/miniclaw/env" \
    --type SecureString \
    --value "$(cat "$SCRIPT_DIR/.env")" \
    --overwrite > /dev/null 2>&1

aws ssm put-parameter --profile "$PROFILE" \
    --name "/miniclaw/credentials" \
    --type SecureString \
    --value "$(cat "$SCRIPT_DIR/.credentials.json")" \
    --overwrite > /dev/null 2>&1

# Step 5: Pull secrets onto instance
log "Writing secrets to instance..."
run_remote "\"aws ssm get-parameter --name /miniclaw/env --with-decryption --query Parameter.Value --output text > $APP_DIR/.env && chmod 600 $APP_DIR/.env && chown ubuntu:ubuntu $APP_DIR/.env\""
run_remote "\"aws ssm get-parameter --name /miniclaw/credentials --with-decryption --query Parameter.Value --output text > $APP_DIR/.credentials.json && chmod 600 $APP_DIR/.credentials.json && chown ubuntu:ubuntu $APP_DIR/.credentials.json\""

# Step 6: Create systemd service
log "Setting up systemd service..."
run_remote "\"cat > /etc/systemd/system/${SERVICE_NAME}.service << 'UNIT'
[Unit]
Description=MiniClaw Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable $SERVICE_NAME && systemctl restart $SERVICE_NAME && echo service-started\""

# Step 7: Verify
log "Verifying..."
sleep 3
run_remote "\"systemctl status $SERVICE_NAME --no-pager -l | head -20\""

log "Deploy complete!"
