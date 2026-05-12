# License Server Setup

## Overview
This is a license verification server that manages software licenses for the Router Proxy application.

## Features
- License key generation
- Expiry date management
- Hardware ID binding
- Device limit enforcement
- Verification logging
- SQLite database backend

## Setup License Server

### 1. Install Dependencies
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install flask flask-cors
```

### 2. Set Admin Token (Important!)
```bash
export ADMIN_TOKEN="your-secret-admin-token-here"
```

### 3. Run Server
```bash
# Activate venv and run
source venv/bin/activate
python license_server.py

# Or use full path without activation
./venv/bin/python license_server.py
```

Server will start on: `http://0.0.0.0:10001`

## API Endpoints

### Create License (Admin)
```bash
curl -X POST http://your-server.com:10001/api/admin/create-license \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: your-secret-admin-token-here" \
  -d '{
    "customer_name": "John Doe",
    "customer_email": "john@example.com",
    "product_name": "router_proxy",
    "duration_days": 365,
    "max_devices": 1
  }'
```

Response:
```json
{
  "success": true,
  "license_key": "RP-XXXXXXXXXXXXXXXX-XXXXXXXX",
  "customer_name": "John Doe",
  "expiry_date": "2026-12-19T10:00:00",
  "max_devices": 1
}
```

### List All Licenses (Admin)
```bash
curl http://your-server.com:10001/api/admin/licenses \
  -H "X-Admin-Token: your-secret-admin-token-here"
```

### Verify License (Client)
```bash
curl -X POST http://your-server.com:10001/api/verify-license \
  -H "Content-Type: application/json" \
  -d '{
    "license_key": "RP-XXXXXXXXXXXXXXXX-XXXXXXXX",
    "hardware_id": "abc123def456",
    "product": "router_proxy",
    "version": "1.0.0"
  }'
```

## Client Setup (Router Proxy)

### 1. Update License Server URL
Edit `router/license.py` and change:
```python
self.server_url = server_url or "http://your-actual-server.com:10001/api/verify-license"
```

### 2. Create License Key File on OpenWrt
```bash
ssh root@192.168.1.1
echo "RP-XXXXXXXXXXXXXXXX-XXXXXXXX" > /root/router/license.key
```

### 3. Restart Router Proxy
```bash
/etc/init.d/router_proxy restart
```

## Testing Locally

### 1. Start License Server
```bash
cd server_lic

# Create venv if not exists
python3 -m venv venv
source venv/bin/activate
pip install flask flask-cors

# Run server
export ADMIN_TOKEN="test-token"
python license_server.py
```

### 2. Create License
```bash
curl -X POST http://localhost:10001/api/admin/create-license \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: test-token" \
  -d '{
    "customer_name": "Test User",
    "duration_days": 30,
    "max_devices": 1
  }'
```

### 3. Test Client
Update `router/license.py`:
```python
self.server_url = "http://localhost:10001/api/verify-license"
```

Create license file:
```bash
echo "RP-YOUR-LICENSE-KEY" > /root/router/license.key
```

Run router proxy:
```bash
cd app
python3 main.py
```

## Database Schema

### licenses table
- id: Primary key
- license_key: Unique license key
- customer_name: Customer name
- customer_email: Customer email
- product_name: Product name
- issue_date: Issue date
- expiry_date: Expiration date
- max_devices: Maximum number of devices
- status: License status (active/suspended/expired)

### device_activations table
- id: Primary key
- license_id: Foreign key to licenses
- hardware_id: Unique device identifier
- first_activated: First activation time
- last_seen: Last verification time
- activation_count: Number of verifications

### verification_logs table
- id: Primary key
- license_key: License key
- hardware_id: Device ID
- ip_address: Client IP
- status: Verification status
- message: Log message
- verified_at: Timestamp

## Production Deployment

### 1. Use HTTPS
Deploy behind nginx with SSL certificate.

### 2. Secure Admin Token
Use environment variables or secrets management:
```bash
export ADMIN_TOKEN=$(openssl rand -hex 32)
```

### 3. Database Backup
```bash
# Backup
cp licenses.db licenses.db.backup

# Restore
cp licenses.db.backup licenses.db
```

### 4. Run as Service
Create systemd service file:
```ini
[Unit]
Description=License Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/license-server
Environment="ADMIN_TOKEN=your-secret-token"
ExecStart=/usr/bin/python3 license_server.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Production Deployment

### Option 1: Systemd Service (Recommended)

**Quick Install:**
```bash
cd server_lic
sudo ./install_service.sh
```

**Service Management:**
```bash
sudo systemctl start license-server
sudo systemctl stop license-server
sudo systemctl restart license-server
sudo systemctl status license-server
sudo journalctl -u license-server -f  # View logs
```

### Option 2: Docker

```bash
cd server_lic
echo "ADMIN_TOKEN=$(openssl rand -hex 32)" > .env
docker-compose up -d

# View logs
docker-compose logs -f
```

### Option 3: Nginx Reverse Proxy

```bash
# Setup nginx
sudo cp nginx.conf /etc/nginx/sites-available/license-server
sudo ln -s /etc/nginx/sites-available/license-server /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Setup SSL
sudo certbot --nginx -d license.example.com
```

## Monitoring

View verification logs:
```bash
sqlite3 licenses.db "SELECT * FROM verification_logs ORDER BY verified_at DESC LIMIT 10"
```

Check active licenses:
```bash
sqlite3 licenses.db "SELECT license_key, customer_name, expiry_date, status FROM licenses WHERE status='active'"
```

Service logs:
```bash
sudo journalctl -u license-server -f --since today
```

## Troubleshooting

### License verification fails
1. Check server URL in `router/license.py`
2. Verify license key file exists: `/root/router/license.key`
3. Check server logs
4. Test manually with curl

### Device limit reached
Query devices:
```bash
sqlite3 licenses.db "SELECT * FROM device_activations WHERE license_id=X"
```

Reset device:
```bash
sqlite3 licenses.db "DELETE FROM device_activations WHERE license_id=X AND hardware_id='xxx'"
```

### License expired
Extend expiry:
```bash
sqlite3 licenses.db "UPDATE licenses SET expiry_date='2027-12-31T23:59:59', status='active' WHERE license_key='RP-XXX'"
```
