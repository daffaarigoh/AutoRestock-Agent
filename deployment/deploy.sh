#!/bin/bash

echo "🚀 Starting AutoRestock-Agent Deployment Process..."

# 1. Ensure we are in the repository folder
if [ ! -f "api/main.py" ]; then
    echo "❌ Error: Please run this script from the root of the AutoRestock-Agent directory."
    exit 1
fi

# 2. Pull latest code from Git
echo "⬇️ Pulling latest code..."
git pull origin main

# 3. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating python virtual environment..."
    python3 -m venv .venv
fi

# 4. Install dependencies including gunicorn for production
echo "📥 Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt
pip install gunicorn  # Recommended for production deployments

# 5. Prepare and Install Systemd Service
echo "⚙️ Configuring Systemd Service..."
# Replace placeholders with actual username and directory path dynamically
sed -e "s|{{USER}}|$USER|g" -e "s|{{PWD}}|$PWD|g" deployment/autorestock.service > /tmp/autorestock.service
sudo mv /tmp/autorestock.service /etc/systemd/system/autorestock.service

# 6. Enable and Restart the Service
echo "🔄 Reloading and restarting service..."
sudo systemctl daemon-reload
sudo systemctl enable autorestock
sudo systemctl restart autorestock

echo "✅ Deployment completed successfully!"
echo "🌐 Your app should now be running on port 8050."
echo "📜 Recent logs:"
sudo systemctl status autorestock --no-pager
