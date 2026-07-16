#!/bin/bash
# ── EduBloom OCR Service — Oracle VPS Deployment ────────────────────────
# Run this ONCE on a fresh Ubuntu 22.04 Oracle ARM instance.
# Paste the whole block into Cloud Shell / SSH terminal.

set -e
echo "── Updating system ──"
sudo apt-get update -y
sudo apt-get install -y python3-pip python3-venv nginx certbot python3-certbot-nginx git ufw

echo "── Setting up firewall ──"
sudo ufw allow OpenSSH
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

echo "── Creating app directory ──"
mkdir -p ~/edubloom-ocr
cd ~/edubloom-ocr

echo "── Python virtual environment ──"
python3 -m venv venv
source venv/bin/activate

echo "── Installing dependencies (this takes 5-10 min on ARM) ──"
pip install --upgrade pip
pip install -r requirements.txt

echo "── Creating systemd service (auto-restart, auto-start on boot) ──"
sudo tee /etc/systemd/system/edubloom-ocr.service > /dev/null << 'SERVICE'
[Unit]
Description=EduBloom PaddleOCR Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/edubloom-ocr
ExecStart=/home/ubuntu/edubloom-ocr/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
SERVICE

echo "── Configuring nginx reverse proxy (port 80 -> 8000) ──"
sudo tee /etc/nginx/sites-available/edubloom-ocr > /dev/null << 'NGINX'
server {
    listen 80;
    server_name _;
    client_max_body_size 15M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 60s;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/edubloom-ocr /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "── Starting OCR service ──"
sudo systemctl daemon-reload
sudo systemctl enable edubloom-ocr
sudo systemctl start edubloom-ocr

echo ""
echo "✅ DONE. Service running on port 80."
echo "Test with: curl http://localhost/health"
echo ""
echo "⚠️  IMPORTANT: Also open port 80 in Oracle Cloud Console:"
echo "   Networking → Virtual Cloud Networks → your VCN → Security Lists"
echo "   → Add Ingress Rule → Source: 0.0.0.0/0, Port: 80"
