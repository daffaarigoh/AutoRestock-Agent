#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "🚀 Starting AutoRestock-Agent Deployment Process..."

# 1. Ensure we are in the repository folder
if [ ! -f "api/main.py" ]; then
    echo "❌ Error: Please run this script from the root of the AutoRestock-Agent directory."
    exit 1
fi

# 2. Pull latest code from Git
echo "⬇️ Pulling latest code..."
if ! git diff --quiet -- . ':(exclude)data/**' || ! git diff --cached --quiet -- . ':(exclude)data/**'; then
    echo "❌ Deployment aborted: local code changes must be committed or backed up first."
    exit 1
fi
if [ -n "$(git ls-files --others --exclude-standard)" ]; then
    echo "❌ Deployment aborted: untracked files are present."
    exit 1
fi
git fetch origin main
git merge --ff-only origin/main

# 3. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating python virtual environment..."
    python3 -m venv .venv
fi

# 4. Install dependencies including gunicorn for production
echo "📥 Installing dependencies..."
source .venv/bin/activate
python -m pip install -r requirements.txt

# 5. Service Lifecycle Management (Target: AutoRestock-Agent-Dap port 8060)
SERVICE_NAME="autorestock-dap"

if [ "${ENABLE_SYSTEMD_INSTALL:-false}" = "true" ]; then
    echo "⚙️ Configuring Systemd Service ($SERVICE_NAME)..."
    service_file="$(mktemp)"
    trap 'rm -f "$service_file"' EXIT
    sed -e "s|{{USER}}|$USER|g" -e "s|{{PWD}}|$PWD|g" deployment/autorestock-dap.service > "$service_file"
    sudo install -m 0644 "$service_file" "/etc/systemd/system/${SERVICE_NAME}.service"
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl restart "$SERVICE_NAME"
    echo "✅ Systemd service $SERVICE_NAME restarted successfully!"
    sudo systemctl status "$SERVICE_NAME" --no-pager
else
    echo "🔄 Managing local process on port 8060 via PID tracker (retaining server boundary)..."
    PID_FILE="uvicorn-8060.pid"
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            echo "Stopping previous process $OLD_PID..."
            kill "$OLD_PID" 2>/dev/null || true
            sleep 2
        fi
        rm -f "$PID_FILE"
    fi
    echo "Starting AutoRestock-Agent-Dap on port 8060 (workers=1)..."
    nohup .venv/bin/python -m uvicorn api.main:app --host 0.0.0.0 --port 8060 --workers 1 > storage/logs/app-8060.log 2>&1 &
    NEW_PID=$!
    echo "$NEW_PID" > "$PID_FILE"
    echo "✅ Started process $NEW_PID recorded in $PID_FILE."
fi

echo "✅ Deployment completed successfully!"
echo "🌐 Your app should now be running on port 8060."

