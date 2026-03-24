#!/bin/bash
# Deploy miniclaw to EC2 via SSM
# Usage: ./scripts/deploy.sh [OPTIONS]
#
# Options:
#   --profile NAME       AWS profile name (default: sen)
#   --instance-id ID     EC2 instance ID (default: i-041a7fb83cf05fe63)
#   --repo URL           Git repository URL (default: git@github.com:shou2077/miniclaw.git)
#   --app-dir PATH       Application directory on instance (default: /home/ubuntu/miniclaw)
#   --service NAME       systemd service name (default: miniclaw)
#   --dry-run            Preview actions without executing
#   --help               Show this help message
#
# Configuration priority (highest to lowest):
#   1. CLI arguments
#   2. Environment variables
#   3. Config file (deploy.config)
#   4. Hardcoded defaults

set -euo pipefail
export AWS_PAGER=""

# ============================================
# DEFAULT VALUES
# ============================================
DEFAULT_PROFILE="sen"
DEFAULT_INSTANCE_ID="i-041a7fb83cf05fe63"
DEFAULT_REPO="https://github.com/shou2077/miniclaw.git"
DEFAULT_APP_DIR="/home/ubuntu/miniclaw"
DEFAULT_SERVICE_NAME="miniclaw"

# ============================================
# COLORS
# ============================================
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# ============================================
# LOGGING FUNCTIONS
# ============================================
log() { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# ============================================
# CONFIGURATION VARIABLES
# ============================================
PROFILE=""
INSTANCE_ID=""
REPO=""
APP_DIR=""
SERVICE_NAME=""
GITHUB_PAT=""
DRY_RUN=false

# ============================================
# CONFIG FILE PARSER
# ============================================
read_config_value() {
    local config_file="$1" key="$2"
    grep -E "^${key}=" "$config_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || echo ""
}

parse_config_file() {
    local config_file="$1"

    if [[ ! -f "$config_file" ]]; then
        return 0
    fi

    [[ -z "$PROFILE" ]] && PROFILE=$(read_config_value "$config_file" "AWS_PROFILE") || true
    [[ -z "$INSTANCE_ID" ]] && INSTANCE_ID=$(read_config_value "$config_file" "INSTANCE_ID") || true
    [[ -z "$REPO" ]] && REPO=$(read_config_value "$config_file" "REPO_URL") || true
    [[ -z "$APP_DIR" ]] && APP_DIR=$(read_config_value "$config_file" "APP_DIR") || true
    [[ -z "$SERVICE_NAME" ]] && SERVICE_NAME=$(read_config_value "$config_file" "SERVICE_NAME") || true
    [[ -z "$GITHUB_PAT" ]] && GITHUB_PAT=$(read_config_value "$config_file" "GITHUB_PAT") || true
}

# ============================================
# ENVIRONMENT VARIABLE PARSER
# ============================================
parse_env_vars() {
    # Read from environment variables (different names to avoid self-reference)
    [[ -z "$PROFILE" ]] && PROFILE="${DEPLOY_AWS_PROFILE:-${AWS_PROFILE:-}}" || true
    [[ -z "$INSTANCE_ID" ]] && INSTANCE_ID="${DEPLOY_INSTANCE_ID:-}" || true
    [[ -z "$REPO" ]] && REPO="${DEPLOY_REPO_URL:-}" || true
    [[ -z "$APP_DIR" ]] && APP_DIR="${DEPLOY_APP_DIR:-}" || true
    [[ -z "$SERVICE_NAME" ]] && SERVICE_NAME="${DEPLOY_SERVICE_NAME:-}" || true
}

# ============================================
# CLI ARGUMENT PARSER
# ============================================
parse_cli_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --profile)
                PROFILE="$2"
                shift 2
                ;;
            --instance-id)
                INSTANCE_ID="$2"
                shift 2
                ;;
            --repo)
                REPO="$2"
                shift 2
                ;;
            --app-dir)
                APP_DIR="$2"
                shift 2
                ;;
            --service)
                SERVICE_NAME="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# ============================================
# SHOW HELP
# ============================================
show_help() {
    cat << 'EOF'
Deploy miniclaw to EC2 via SSM

Usage: ./scripts/deploy.sh [OPTIONS]

Options:
  --profile NAME       AWS profile name (default: sen)
  --instance-id ID     EC2 instance ID (default: i-041a7fb83cf05fe63)
  --repo URL           Git repository URL (default: git@github.com:shou2077/miniclaw.git)
  --app-dir PATH       Application directory on instance (default: /home/ubuntu/miniclaw)
  --service NAME       systemd service name (default: miniclaw)
  --dry-run            Preview actions without executing
  --help               Show this help message

Configuration priority (highest to lowest):
  1. CLI arguments
  2. Environment variables
  3. Config file (deploy.config)
  4. Hardcoded defaults

Environment variables:
  AWS_PROFILE              AWS profile name (also DEPLOY_AWS_PROFILE)
  DEPLOY_INSTANCE_ID       EC2 instance ID
  DEPLOY_REPO_URL          Git repository URL
  DEPLOY_APP_DIR           Application directory on instance
  DEPLOY_SERVICE_NAME      systemd service name

Examples:
  ./scripts/deploy.sh
  ./scripts/deploy.sh --profile prod --instance-id i-1234567890abcdef0
  ./scripts/deploy.sh --dry-run
  AWS_PROFILE=prod ./scripts/deploy.sh --instance-id i-1234567890abcdef0
EOF
}

# ============================================
# APPLY DEFAULTS
# ============================================
apply_defaults() {
    [[ -z "$PROFILE" ]] && PROFILE="$DEFAULT_PROFILE" || true
    [[ -z "$INSTANCE_ID" ]] && INSTANCE_ID="$DEFAULT_INSTANCE_ID" || true
    [[ -z "$REPO" ]] && REPO="$DEFAULT_REPO" || true
    [[ -z "$APP_DIR" ]] && APP_DIR="$DEFAULT_APP_DIR" || true
    [[ -z "$SERVICE_NAME" ]] && SERVICE_NAME="$DEFAULT_SERVICE_NAME" || true
}

# ============================================
# DISPLAY CONFIGURATION
# ============================================
display_config() {
    log "Configuration:"
    echo "  AWS Profile:     $PROFILE"
    echo "  Instance ID:     $INSTANCE_ID"
    echo "  Repository:      $REPO"
    echo "  App Directory:   $APP_DIR"
    echo "  Service Name:    $SERVICE_NAME"
    echo "  Dry Run:         $DRY_RUN"
}

# ============================================
# VALIDATE CONFIGURATION
# ============================================
validate_config() {
    local errors=0
    
    if [[ -z "$PROFILE" ]]; then
        error "AWS profile is required"
        errors=$((errors + 1))
    fi
    
    if [[ -z "$INSTANCE_ID" ]]; then
        error "EC2 instance ID is required"
        errors=$((errors + 1))
    fi
    
    if [[ -z "$REPO" ]]; then
        error "Repository URL is required"
        errors=$((errors + 1))
    fi
    
    if [[ -z "$APP_DIR" ]]; then
        error "Application directory is required"
        errors=$((errors + 1))
    fi
    
    if [[ -z "$SERVICE_NAME" ]]; then
        error "Service name is required"
        errors=$((errors + 1))
    fi
    
    return $errors
}

# ============================================
# RUN REMOTE COMMAND
# ============================================
run_remote() {
    local cmd="$1"
    local cmd_id
    local status
    local i

    [[ -z "$PROFILE" ]] && { echo "PROFILE is empty" >&2; return 1; }
    [[ -z "$INSTANCE_ID" ]] && { echo "INSTANCE_ID is empty" >&2; return 1; }
    [[ -z "$cmd" ]] && { echo "Command is empty" >&2; return 1; }

    if [[ "$DRY_RUN" == "true" ]]; then
        log "[DRY-RUN] Would execute: $cmd"
        return 0
    fi

    printf 'Running remote command: %q\n' "$cmd"

    if ! cmd_id=$(aws ssm send-command \
        --profile "$PROFILE" \
        --instance-ids "$INSTANCE_ID" \
        --document-name "AWS-RunShellScript" \
        --parameters "{\"commands\":[$(printf '%s' "$cmd" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')]}" \
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

# ============================================
# MAIN
# ============================================
main() {
    local script_dir project_dir

    # Get script directory and project root
    script_dir="$(cd "$(dirname "$0")" && pwd)"
    project_dir="$(cd "$script_dir/.." && pwd)"
    
    # Parse CLI args first (highest priority)
    parse_cli_args "$@"

    # Parse environment variables (second priority)
    parse_env_vars

    # Parse config file (third priority)
    parse_config_file "$script_dir/deploy.config"
    
    # Apply defaults (fourth priority)
    apply_defaults
    
    # Display configuration
    display_config
    
    # Validate configuration
    if ! validate_config; then
        error "Configuration validation failed"
        exit 1
    fi
    
    if [[ "$DRY_RUN" == "true" ]]; then
        warn "Running in DRY-RUN mode - no changes will be made"
    fi
    
    # Step 1: Install deps + clone/pull repo
    log "Setting up instance..."
    run_remote "apt-get update -qq && apt-get install -y -qq python3-pip python3-venv git > /dev/null 2>&1 && echo deps-ok"

    # Step 2: Clone or pull (inject PAT into HTTPS URL for auth)
    log "Deploying code..."
    local clone_url="$REPO"
    if [[ -n "$GITHUB_PAT" && "$REPO" == https://github.com/* ]]; then
        clone_url="${REPO/https:\/\/github.com/https://${GITHUB_PAT}@github.com}"
    fi
    run_remote "sudo -u ubuntu bash -c 'if [ -d \"${APP_DIR}\" ]; then cd \"${APP_DIR}\" && git remote set-url origin \"${clone_url}\" && git pull --rebase; else git clone \"${clone_url}\" \"${APP_DIR}\"; fi'"

    # Step 3: Install Python deps
    log "Installing Python packages..."
    run_remote "sudo -u ubuntu bash -c 'cd \"${APP_DIR}\" && python3 -m venv venv && source venv/bin/activate && pip install -q -r requirements.txt'"

    # Step 4: Write secrets to instance via SSM command
    log "Writing secrets to instance..."

    local env_content creds_content
    env_content=$(cat "$project_dir/.env")
    creds_content=$(cat "$project_dir/.credentials.json")

    run_remote "cat > '${APP_DIR}/.env' << 'ENVEOF'
${env_content}
ENVEOF
chmod 600 '${APP_DIR}/.env' && chown ubuntu:ubuntu '${APP_DIR}/.env' && echo env-ok"

    run_remote "cat > '${APP_DIR}/.credentials.json' << 'CREDEOF'
${creds_content}
CREDEOF
chmod 600 '${APP_DIR}/.credentials.json' && chown ubuntu:ubuntu '${APP_DIR}/.credentials.json' && echo creds-ok"

    # Step 4b: Upload optional credential files if they exist locally
    if [[ -f "$project_dir/.codex_credentials.json" ]]; then
        log "Writing .codex_credentials.json..."
        local codex_creds_content
        codex_creds_content=$(cat "$project_dir/.codex_credentials.json")
        run_remote "cat > '${APP_DIR}/.codex_credentials.json' << 'CODEXEOF'
${codex_creds_content}
CODEXEOF
chmod 600 '${APP_DIR}/.codex_credentials.json' && chown ubuntu:ubuntu '${APP_DIR}/.codex_credentials.json' && echo codex-creds-ok"
    else
        warn "No .codex_credentials.json found locally — skipping"
    fi

    if [[ -f "$project_dir/agents.json" ]]; then
        log "Writing agents.json..."
        local agents_content
        agents_content=$(cat "$project_dir/agents.json")
        run_remote "cat > '${APP_DIR}/agents.json' << 'AGENTSEOF'
${agents_content}
AGENTSEOF
chmod 600 '${APP_DIR}/agents.json' && chown ubuntu:ubuntu '${APP_DIR}/agents.json' && echo agents-ok"
    else
        warn "No agents.json found locally — skipping"
    fi

    # Step 6: Create systemd service
    log "Setting up systemd service..."
    run_remote "cat > /etc/systemd/system/${SERVICE_NAME}.service << UNIT
[Unit]
Description=MiniClaw Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${APP_DIR}
ExecStart=${APP_DIR}/venv/bin/python main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable '${SERVICE_NAME}' && systemctl restart '${SERVICE_NAME}' && echo service-started"

    # Step 7: Verify
    log "Verifying..."
    sleep 3
    run_remote "systemctl status '${SERVICE_NAME}' --no-pager -l | head -20"

    log "Deploy complete!"
}

# Run main function
main "$@"