"""
License Server - Simple Flask-based license verification server
Run this on your server to manage licenses
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import secrets
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

DATABASE = 'licenses.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with schema"""
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS licenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            customer_email TEXT,
            product_name TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            expiry_date TEXT NOT NULL,
            max_devices INTEGER DEFAULT 1,
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        
        CREATE TABLE IF NOT EXISTS device_activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_id INTEGER NOT NULL,
            hardware_id TEXT NOT NULL,
            first_activated TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            activation_count INTEGER DEFAULT 1,
            FOREIGN KEY (license_id) REFERENCES licenses(id),
            UNIQUE(license_id, hardware_id)
        );
        
        CREATE TABLE IF NOT EXISTS verification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            license_key TEXT NOT NULL,
            hardware_id TEXT,
            ip_address TEXT,
            status TEXT,
            message TEXT,
            verified_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    db.commit()

def log_verification(license_key, hardware_id, ip_address, status, message):
    db = get_db()
    db.execute('''
        INSERT INTO verification_logs 
        (license_key, hardware_id, ip_address, status, message)
        VALUES (?, ?, ?, ?, ?)
    ''', (license_key, hardware_id, ip_address, status, message))
    db.commit()

@app.route('/api/verify-license', methods=['POST'])
def verify_license():
    """Verify license key"""
    data = request.json
    license_key = data.get('license_key')
    hardware_id = data.get('hardware_id')
    product = data.get('product', 'router_proxy')
    ip_address = request.remote_addr
    
    if not license_key or not hardware_id:
        return jsonify({
            "valid": False,
            "message": "Missing license_key or hardware_id"
        }), 400
    
    db = get_db()
    license_row = db.execute('''
        SELECT * FROM licenses 
        WHERE license_key = ? AND product_name = ?
    ''', (license_key, product)).fetchone()
    
    if not license_row:
        log_verification(license_key, hardware_id, ip_address, 'failed', 'Invalid license key')
        return jsonify({"valid": False, "message": "Invalid license key"})
    
    license_dict = dict(license_row)
    
    if license_dict['status'] != 'active':
        log_verification(license_key, hardware_id, ip_address, 'failed', f"License {license_dict['status']}")
        return jsonify({"valid": False, "message": f"License is {license_dict['status']}"})
    
    expiry_date = datetime.fromisoformat(license_dict['expiry_date'])
    if datetime.now() > expiry_date:
        db.execute('UPDATE licenses SET status = ? WHERE id = ?', ('expired', license_dict['id']))
        db.commit()
        log_verification(license_key, hardware_id, ip_address, 'expired', 'License expired')
        return jsonify({"valid": False, "message": "License expired"})
    
    device = db.execute('''
        SELECT * FROM device_activations 
        WHERE license_id = ? AND hardware_id = ?
    ''', (license_dict['id'], hardware_id)).fetchone()
    
    if device:
        db.execute('''
            UPDATE device_activations 
            SET last_seen = ?, activation_count = activation_count + 1
            WHERE license_id = ? AND hardware_id = ?
        ''', (datetime.now().isoformat(), license_dict['id'], hardware_id))
        db.commit()
    else:
        device_count = db.execute('''
            SELECT COUNT(*) as count FROM device_activations 
            WHERE license_id = ?
        ''', (license_dict['id'],)).fetchone()['count']
        
        if device_count >= license_dict['max_devices']:
            log_verification(license_key, hardware_id, ip_address, 'failed', 'Device limit reached')
            return jsonify({"valid": False, "message": f"Device limit ({license_dict['max_devices']}) reached"})
        
        db.execute('''
            INSERT INTO device_activations 
            (license_id, hardware_id, first_activated, last_seen)
            VALUES (?, ?, ?, ?)
        ''', (license_dict['id'], hardware_id, datetime.now().isoformat(), datetime.now().isoformat()))
        db.commit()
    
    days_remaining = (expiry_date - datetime.now()).days
    log_verification(license_key, hardware_id, ip_address, 'success', 'Verified')
    
    return jsonify({
        "valid": True,
        "product_name": license_dict['product_name'],
        "customer_name": license_dict['customer_name'],
        "expiry_date": license_dict['expiry_date'],
        "days_remaining": days_remaining,
        "message": "License verified successfully"
    })

@app.route('/api/admin/create-license', methods=['POST'])
def create_license():
    """Create new license"""
    # Simple admin token check (use proper auth in production)
    admin_token = request.headers.get('X-Admin-Token')
    if admin_token != os.getenv('ADMIN_TOKEN', 'change-me-in-production'):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    customer_name = data.get('customer_name')
    customer_email = data.get('customer_email')
    product_name = data.get('product_name', 'router_proxy')
    duration_days = data.get('duration_days', 365)
    max_devices = data.get('max_devices', 1)
    
    if not customer_name:
        return jsonify({"error": "customer_name required"}), 400
    
    license_key = f"RP-{secrets.token_hex(8).upper()}-{secrets.token_hex(4).upper()}"
    issue_date = datetime.now()
    expiry_date = issue_date + timedelta(days=duration_days)
    
    db = get_db()
    db.execute('''
        INSERT INTO licenses 
        (license_key, customer_name, customer_email, product_name, 
         issue_date, expiry_date, max_devices, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (license_key, customer_name, customer_email, product_name,
          issue_date.isoformat(), expiry_date.isoformat(), 
          max_devices, 'active'))
    db.commit()
    
    return jsonify({
        "success": True,
        "license_key": license_key,
        "customer_name": customer_name,
        "expiry_date": expiry_date.isoformat(),
        "max_devices": max_devices
    })

@app.route('/api/admin/licenses', methods=['GET'])
def list_licenses():
    """List all licenses"""
    admin_token = request.headers.get('X-Admin-Token')
    if admin_token != os.getenv('ADMIN_TOKEN', 'change-me-in-production'):
        return jsonify({"error": "Unauthorized"}), 401
    
    db = get_db()
    licenses = db.execute('''
        SELECT l.*, COUNT(d.id) as device_count
        FROM licenses l
        LEFT JOIN device_activations d ON l.id = d.license_id
        GROUP BY l.id
        ORDER BY l.created_at DESC
    ''').fetchall()
    
    return jsonify({"licenses": [dict(row) for row in licenses]})

if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print("Initializing database...")
        init_db()
        print("Database initialized!")
    
    print("Starting License Server on port 10001...")
    print("Admin token:", os.getenv('ADMIN_TOKEN', 'change-me-in-production'))
    app.run(host='0.0.0.0', port=10001, debug=True)
