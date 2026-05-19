"""
License Server - Simple Flask-based license verification server
Run this on your server to manage licenses
"""

from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import sqlite3
import secrets
import hmac
import hashlib
import json
from datetime import datetime, timedelta
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

DATABASE = 'licenses.db'
PACKAGES_DIR = os.environ.get('PACKAGES_DIR', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'packages'))
UPDATE_SIGNING_KEY = os.environ.get('UPDATE_SIGNING_KEY', '')
MAX_PACKAGE_BYTES = 200 * 1024 * 1024  # 200 MB

os.makedirs(PACKAGES_DIR, exist_ok=True)

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

        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'stable',
            version TEXT NOT NULL,
            filename TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            size INTEGER NOT NULL,
            signature TEXT,
            notes TEXT,
            published_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(product, channel, version)
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


# === Software update / packages ============================================

def _check_admin():
    admin_token = request.headers.get('X-Admin-Token')
    if admin_token != os.getenv('ADMIN_TOKEN', 'change-me-in-production'):
        return jsonify({"error": "Unauthorized"}), 401
    return None

def _license_valid(license_key, hardware_id, product='router_proxy'):
    if not license_key or not hardware_id:
        return False, "missing license_key or hardware_id"
    db = get_db()
    row = db.execute(
        'SELECT * FROM licenses WHERE license_key = ? AND product_name = ?',
        (license_key, product),
    ).fetchone()
    if not row:
        return False, "invalid license"
    d = dict(row)
    if d['status'] != 'active':
        return False, f"license {d['status']}"
    if datetime.now() > datetime.fromisoformat(d['expiry_date']):
        return False, "license expired"
    # Device must have activated previously (or accept first-touch — keep simple: accept)
    return True, d

def _compute_signature(version, sha256, size):
    if not UPDATE_SIGNING_KEY:
        return ""
    msg = f"{version}|{sha256}|{size}".encode()
    return hmac.new(UPDATE_SIGNING_KEY.encode(), msg, hashlib.sha256).hexdigest()

def _package_row_to_manifest(row):
    base = request.host_url.rstrip('/')
    return {
        "product": row["product"],
        "channel": row["channel"],
        "version": row["version"],
        "filename": row["filename"],
        "sha256": row["sha256"],
        "size": row["size"],
        "signature": row["signature"],
        "notes": row["notes"],
        "published_at": row["published_at"],
        "download_url": f"{base}/downloads/{row['filename']}",
    }


@app.route('/api/admin/publish-package', methods=['POST'])
def publish_package():
    """Upload a new OTA package + manifest. multipart form fields:
       - manifest: JSON file (built by build.sh)
       - package : .tar.gz file
    """
    err = _check_admin()
    if err: return err

    if 'package' not in request.files or 'manifest' not in request.files:
        return jsonify({"error": "missing 'package' or 'manifest' file part"}), 400

    manifest_raw = request.files['manifest'].read()
    try:
        m = json.loads(manifest_raw.decode('utf-8'))
    except Exception as e:
        return jsonify({"error": f"invalid manifest JSON: {e}"}), 400

    required = ['product', 'channel', 'version', 'filename', 'sha256', 'size']
    if any(k not in m for k in required):
        return jsonify({"error": f"manifest missing fields; required: {required}"}), 400

    pkg = request.files['package']
    safe_name = secure_filename(m['filename'])
    if not safe_name or safe_name != m['filename']:
        return jsonify({"error": "unsafe filename"}), 400
    dest = os.path.join(PACKAGES_DIR, safe_name)
    pkg.save(dest)

    actual_size = os.path.getsize(dest)
    if actual_size > MAX_PACKAGE_BYTES:
        os.remove(dest)
        return jsonify({"error": "package too large"}), 413
    if actual_size != int(m['size']):
        os.remove(dest)
        return jsonify({"error": f"size mismatch (got {actual_size}, manifest {m['size']})"}), 400

    h = hashlib.sha256()
    with open(dest, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    actual_sha = h.hexdigest()
    if actual_sha.lower() != m['sha256'].lower():
        os.remove(dest)
        return jsonify({"error": f"sha256 mismatch (got {actual_sha}, manifest {m['sha256']})"}), 400

    # Recompute signature server-side using our authoritative key.
    signature = _compute_signature(m['version'], actual_sha, actual_size)
    if not signature:
        os.remove(dest)
        return jsonify({"error": "server UPDATE_SIGNING_KEY not configured"}), 500

    notes = m.get('notes', '')
    db = get_db()
    try:
        db.execute(
            '''INSERT INTO packages
               (product, channel, version, filename, sha256, size, signature, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (m['product'], m['channel'], m['version'], safe_name,
             actual_sha, actual_size, signature, notes),
        )
        db.commit()
    except sqlite3.IntegrityError:
        # Already published — update row to keep filename in sync
        db.execute(
            '''UPDATE packages SET filename=?, sha256=?, size=?, signature=?, notes=?,
               published_at=CURRENT_TIMESTAMP
               WHERE product=? AND channel=? AND version=?''',
            (safe_name, actual_sha, actual_size, signature, notes,
             m['product'], m['channel'], m['version']),
        )
        db.commit()

    return jsonify({
        "success": True,
        "version": m['version'],
        "sha256": actual_sha,
        "size": actual_size,
        "signature": signature,
        "filename": safe_name,
    })


@app.route('/api/admin/packages', methods=['GET'])
def admin_list_packages():
    err = _check_admin()
    if err: return err
    db = get_db()
    rows = db.execute('SELECT * FROM packages ORDER BY published_at DESC').fetchall()
    return jsonify({"packages": [_package_row_to_manifest(r) for r in rows]})


@app.route('/api/admin/packages/<int:pkg_id>', methods=['DELETE'])
def admin_delete_package(pkg_id):
    err = _check_admin()
    if err: return err
    db = get_db()
    row = db.execute('SELECT * FROM packages WHERE id = ?', (pkg_id,)).fetchone()
    if not row:
        return jsonify({"error": "not found"}), 404
    try:
        os.remove(os.path.join(PACKAGES_DIR, row['filename']))
    except FileNotFoundError:
        pass
    db.execute('DELETE FROM packages WHERE id = ?', (pkg_id,))
    db.commit()
    return jsonify({"success": True, "deleted": pkg_id})


def _select_package(product, channel, version=None):
    db = get_db()
    if version:
        return db.execute(
            'SELECT * FROM packages WHERE product=? AND channel=? AND version=?',
            (product, channel, version),
        ).fetchone()
    # Latest by published_at — fallback ordering by id desc
    return db.execute(
        '''SELECT * FROM packages WHERE product=? AND channel=?
           ORDER BY datetime(published_at) DESC, id DESC LIMIT 1''',
        (product, channel),
    ).fetchone()


@app.route('/api/latest-version', methods=['GET'])
def latest_version():
    license_key = request.headers.get('X-License-Key')
    hardware_id = request.headers.get('X-Hardware-Id')
    product = request.args.get('product', 'router_proxy')
    channel = request.args.get('channel', 'stable')
    version = request.args.get('version')  # optional pin

    ok, info = _license_valid(license_key, hardware_id, product)
    if not ok:
        return jsonify({"error": info}), 403

    row = _select_package(product, channel, version)
    if not row:
        return jsonify({"error": "no package available"}), 404
    return jsonify(_package_row_to_manifest(row))


@app.route('/api/versions', methods=['GET'])
def list_package_versions():
    license_key = request.headers.get('X-License-Key')
    hardware_id = request.headers.get('X-Hardware-Id')
    product = request.args.get('product', 'router_proxy')
    channel = request.args.get('channel', 'stable')

    ok, info = _license_valid(license_key, hardware_id, product)
    if not ok:
        return jsonify({"error": info}), 403

    db = get_db()
    rows = db.execute(
        '''SELECT * FROM packages WHERE product=? AND channel=?
           ORDER BY datetime(published_at) DESC, id DESC''',
        (product, channel),
    ).fetchall()
    return jsonify({"versions": [_package_row_to_manifest(r) for r in rows]})


@app.route('/downloads/<path:filename>', methods=['GET'])
def download_package(filename):
    """Authenticated download endpoint. Requires X-License-Key + X-Hardware-Id."""
    license_key = request.headers.get('X-License-Key')
    hardware_id = request.headers.get('X-Hardware-Id')
    ok, info = _license_valid(license_key, hardware_id)
    if not ok:
        return jsonify({"error": info}), 403
    safe = secure_filename(filename)
    if safe != filename:
        abort(400)
    return send_from_directory(PACKAGES_DIR, safe, as_attachment=True)


if __name__ == '__main__':
    if not os.path.exists(DATABASE):
        print("Initializing database...")
    # init_db is idempotent (CREATE TABLE IF NOT EXISTS) — always run so
    # schema upgrades (e.g. new packages table) apply.
    init_db()
    print("Database ready!")
    
    print("Starting License Server on port 10001...")
    print("Admin token:", os.getenv('ADMIN_TOKEN', 'change-me-in-production'))
    app.run(host='0.0.0.0', port=10001, debug=True)
