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

# 5. Prepare and Install Systemd Service
echo "⚙️ Configuring Systemd Service..."
# Replace placeholders with actual username and directory path dynamically
service_file="$(mktemp)"
trap 'rm -f "$service_file"' EXIT
sed -e "s|{{USER}}|$USER|g" -e "s|{{PWD}}|$PWD|g" deployment/autorestock.service > "$service_file"
sudo install -m 0644 "$service_file" /etc/systemd/system/autorestock.service

# 6. Enable and Restart the Service
echo "🔄 Reloading and restarting service..."
sudo systemctl daemon-reload
sudo systemctl enable autorestock
sudo systemctl restart autorestock

echo "✅ Deployment completed successfully!"
echo "🌐 Your app should now be running on port 8060."
echo "📜 Recent logs:"
sudo systemctl status autorestock --no-pager
