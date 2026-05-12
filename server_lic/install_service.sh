#!/bin/bash
# License Server Installation Script

set -e

echo "=== License Server Installation ==="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "Please run as root (use sudo)"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/license-server"

# Generate admin token if not provided
if [ -z "$ADMIN_TOKEN" ]; then
    echo "Generating random admin token..."
    ADMIN_TOKEN=$(openssl rand -hex 32)
    echo "Generated ADMIN_TOKEN: $ADMIN_TOKEN"
    echo "IMPORTANT: Save this token! You'll need it to manage licenses."
    echo ""
fi

# Install Python dependencies
echo "Installing Python dependencies..."
apt-get update >/dev/null 2>&1
apt-get install -y python3-venv python3-pip >/dev/null 2>&1 || true

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"

# Install packages in virtual environment
echo "Installing Flask and dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip >/dev/null 2>&1
"$INSTALL_DIR/venv/bin/pip" install flask flask-cors >/dev/null 2>&1

# Create installation directory
echo "Creating installation directory: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

# Copy files
echo "Copying files..."
cp "$SCRIPT_DIR/license_server.py" "$INSTALL_DIR/"
chmod 644 "$INSTALL_DIR/license_server.py"

# Create www-data user if doesn't exist
if ! id -u www-data >/dev/null 2>&1; then
    echo "Creating www-data user..."
    useradd -r -s /bin/false www-data
fi

# Set ownership
chown -R www-data:www-data "$INSTALL_DIR"

# Create systemd service file
echo "Installing systemd service..."
cat > /etc/systemd/system/license-server.service << SERVICE
[Unit]
Description=Router Proxy License Server
After=network.target
Documentation=https://github.com/your-repo/router-proxy

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$INSTALL_DIR
Environment="ADMIN_TOKEN=$ADMIN_TOKEN"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/license_server.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=license-server

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
SERVICE

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload

# Enable service
echo "Enabling service..."
systemctl enable license-server.service

# Start service
echo "Starting service..."
systemctl start license-server.service

# Wait a moment for service to start
sleep 2

# Check status
echo ""
echo "=== Service Status ==="
systemctl status license-server.service --no-pager || true

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Service is running on: http://0.0.0.0:10001"
echo ""
echo "Admin Token: $ADMIN_TOKEN"
echo ""
echo "Save this token to a secure location!"
echo "You can also find it with: systemctl show license-server.service | grep ADMIN_TOKEN"
echo ""
echo "=== Service Management Commands ==="
echo "  Start:   sudo systemctl start license-server"
echo "  Stop:    sudo systemctl stop license-server"
echo "  Restart: sudo systemctl restart license-server"
echo "  Status:  sudo systemctl status license-server"
echo "  Logs:    sudo journalctl -u license-server -f"
echo ""
echo "=== Create Your First License ==="
echo "curl -X POST http://localhost:10001/api/admin/create-license \\"
echo "  -H 'Content-Type: application/json' \\"
echo "  -H 'X-Admin-Token: $ADMIN_TOKEN' \\"
echo "  -d '{\"customer_name\": \"Test User\", \"duration_days\": 365}'"
echo ""
