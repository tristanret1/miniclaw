#!/bin/bash
# Deploy miniclaw to EC2 via SSM
# Usage:
#   Full deploy:   ./scripts/deploy.sh --pat <GITHUB_PAT>
#   Update only:   ./scripts/deploy.sh --pat <GITHUB_PAT> --update
#   Push secrets:  ./scripts/deploy.sh --pat <GITHUB_PAT> --update --secrets
#
# PAT can also be set via GITHUB_PAT env var.
# --update:  pull latest code, install deps, restart service (skip system setup & secrets)
# --secrets: also push .env and .credentials.json (works with --update or full deploy)

set -euo pipefail

export AWS_PAGER=""
PROFILE="sen"
INSTANCE_ID="i-041a7fb83cf05fe63"
REPO_OWNER="shou2077"
REPO_NAME="miniclaw"
APP_DIR="/home/ubuntu/miniclaw"
SERVICE_NAME="miniclaw"

# Defaults
UPDATE_ONLY=false
PUSH_SECRETS=false
GITHUB_PAT="${GITHUB_PAT:-}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pat)     GITHUB_PAT="$2"; shift 2 ;;
        --update)  UPDATE_ONLY=true; shift ;;
        --secrets) PUSH_SECRETS=true; shift ;;
        *)         echo "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$GITHUB_PAT" ]]; then
    echo "Error: GitHub PAT required. Use --pat <token> or set GITHUB_PAT env var."
    exit 1
fi

REPO_URL="https://${GITHUB_PAT}@github.com/${REPO_OWNER}/${REPO_NAME}.git"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

push_secrets() {
    log "Writing secrets to instance..."
    local env_b64 cred_b64
    env_b64=$(base64 < "$SCRIPT_DIR/.env")
    cred_b64=$(base64 < "$SCRIPT_DIR/.credentials.json")
    run_remote "\"echo '$env_b64' | base64 -d > $APP_DIR/.env && chmod 600 $APP_DIR/.env && chown ubuntu:ubuntu $APP_DIR/.env && echo env-ok\""
    run_remote "\"echo '$cred_b64' | base64 -d > $APP_DIR/.credentials.json && chmod 600 $APP_DIR/.credentials.json && chown ubuntu:ubuntu $APP_DIR/.credentials.json && echo cred-ok\""
}

run_remote() {
    local cmd_id
    cmd_id=$(aws ssm send-command \
        --profile "$PROFILE" \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters "commands=[$1]" \
        --timeout-seconds 120 \
        --output text \
        --query "Command.CommandId" 2>&1)

    sleep 2
    # Poll until done
    for i in {1..30}; do
        local status
        status=$(aws ssm get-command-invocation \
            --profile "$PROFILE" \
            --instance-id "$INSTANCE_ID" \
            --command-id "$cmd_id" \
            --query "Status" --output text 2>&1)

        if [[ "$status" == "Success" ]]; then
            aws ssm get-command-invocation \
                --profile "$PROFILE" \
                --instance-id "$INSTANCE_ID" \
                --command-id "$cmd_id" \
                --query "StandardOutputContent" --output text 2>&1
            return 0
        elif [[ "$status" == "Failed" ]]; then
            warn "Command failed!"
            aws ssm get-command-invocation \
                --profile "$PROFILE" \
                --instance-id "$INSTANCE_ID" \
                --command-id "$cmd_id" \
                --query "{stdout:StandardOutputContent,stderr:StandardErrorContent}" --output json 2>&1
            return 1
        fi
        sleep 2
    done
    warn "Command timed out"
    return 1
}

if [[ "$UPDATE_ONLY" == true ]]; then
    # --- Update mode: pull + deps + restart ---
    log "Updating git credentials..."
    run_remote "\"sudo -u ubuntu bash -c 'cd $APP_DIR && git config credential.helper store && echo https://${GITHUB_PAT}@github.com > /home/ubuntu/.git-credentials && chmod 600 /home/ubuntu/.git-credentials && echo cred-ok'\""

    log "Pulling latest code..."
    run_remote "\"sudo -u ubuntu bash -c 'cd $APP_DIR && git pull --rebase'\""

    log "Installing Python packages..."
    run_remote "\"sudo -u ubuntu bash -c 'cd $APP_DIR && source venv/bin/activate && pip install -q -r requirements.txt'\""

    if [[ "$PUSH_SECRETS" == true ]]; then
        push_secrets
    fi

    log "Restarting service..."
    run_remote "\"systemctl restart $SERVICE_NAME && echo service-restarted\""

    sleep 3
    log "Verifying..."
    run_remote "\"systemctl status $SERVICE_NAME --no-pager -l | head -20\""

    log "Update complete!"
    exit 0
fi

# --- Full deploy ---

# Step 1: Install system deps
log "Setting up instance..."
run_remote "\"apt-get update -qq && apt-get install -y -qq python3-pip python3-venv git > /dev/null 2>&1 && echo deps-ok\""

# Step 2: Clone or pull (HTTPS + PAT)
log "Deploying code..."
run_remote "\"sudo -u ubuntu bash -c 'if [ -d $APP_DIR ]; then cd $APP_DIR && git remote set-url origin $REPO_URL && git pull --rebase; else git clone $REPO_URL $APP_DIR; fi'\""

# Step 3: Configure git credential to avoid PAT leaking in remote URL long-term
log "Configuring git credentials..."
run_remote "\"sudo -u ubuntu bash -c 'cd $APP_DIR && git remote set-url origin https://github.com/${REPO_OWNER}/${REPO_NAME}.git && git config credential.helper store && echo https://${GITHUB_PAT}@github.com > /home/ubuntu/.git-credentials && chmod 600 /home/ubuntu/.git-credentials'\""

# Step 4: Install Python deps
log "Installing Python packages..."
run_remote "\"sudo -u ubuntu bash -c 'cd $APP_DIR && python3 -m venv venv && source venv/bin/activate && pip install -q -r requirements.txt'\""

# Step 5: Write secrets to instance
push_secrets

# Step 7: Create systemd service
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

# Step 8: Verify
log "Verifying..."
sleep 3
run_remote "\"systemctl status $SERVICE_NAME --no-pager -l | head -20\""

log "Deploy complete!"
