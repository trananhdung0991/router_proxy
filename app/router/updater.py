"""
Online updater for router_proxy.

Workflow (apply_update):
  1. download tarball from license server to /tmp/ru_dl/
  2. verify SHA-256 against manifest
  3. verify HMAC-SHA256 signature using UPDATE_SIGNING_KEY
  4. extract to /tmp/ru_stage/ and sanity-check layout
  5. swap /root/router  -> /root/router.bak (rotate .bak -> .bak.old)
     copy new payload  -> /root/router
     swap /www/router-app -> /www/router-app.bak
     copy new web      -> /www/router-app
  6. /etc/init.d/router_proxy restart (delayed so HTTP response can return)

State is held in a module-level dict guarded by a lock so the API can poll
progress via GET /system/update/status.
"""

import os
import hmac
import json
import time
import shutil
import hashlib
import logging
import tarfile
import threading
import subprocess
import urllib.parse
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# --- paths -------------------------------------------------------------------
APP_ROOT = "/root/router"
WEB_ROOT = "/www/router-app"
VERSION_FILE = os.path.join(APP_ROOT, "VERSION")
SIGNING_KEY_FILE = os.path.join(APP_ROOT, "UPDATE_SIGNING_KEY")
INIT_SCRIPT = "/etc/init.d/router_proxy"
MAIN_SCRIPT = os.path.join(APP_ROOT, "main.py")
DL_DIR = "/tmp/ru_dl"
STAGE_DIR = "/tmp/ru_stage"

# --- license server endpoints -----------------------------------------------
LICENSE_SERVER = "https://routerlic.xproxy.io"
LATEST_URL = LICENSE_SERVER + "/api/latest-version"
LIST_URL = LICENSE_SERVER + "/api/versions"

# --- state -------------------------------------------------------------------
_state_lock = threading.Lock()
_state = {
    "phase": "idle",        # idle|downloading|verifying|installing|restarting|done|error
    "percent": 0,
    "message": "",
    "version": None,
    "started_at": None,
    "finished_at": None,
}
_worker_thread = None

# --- helpers ----------------------------------------------------------------
def _set_state(**kw):
    with _state_lock:
        _state.update(kw)
        logger.info("updater state: %s", _state)

def get_state():
    with _state_lock:
        return dict(_state)

def get_current_version():
    try:
        with open(VERSION_FILE) as f:
            return f.read().strip() or "unknown"
    except Exception:
        return "unknown"

def _load_signing_key():
    try:
        with open(SIGNING_KEY_FILE) as f:
            return f.read().strip()
    except Exception:
        return ""

def _license_headers():
    # Lazy import to avoid circular import on module load
    from router.license import get_license_manager
    lm = get_license_manager()
    return {
        "X-License-Key": lm.license_key or "",
        "X-Hardware-Id": lm._get_hardware_id(),
    }

def _has_backup():
    return os.path.isdir(APP_ROOT + ".bak")

# --- public API -------------------------------------------------------------
def check_update(version=None):
    """Query license server for the latest (or a specific) version manifest."""
    params = {"product": "router_proxy", "channel": "stable"}
    if version:
        params["version"] = version
    r = requests.get(LATEST_URL, params=params, headers=_license_headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    return data

def list_versions():
    r = requests.get(
        LIST_URL,
        params={"product": "router_proxy", "channel": "stable"},
        headers=_license_headers(),
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

def apply_update_async(version=None):
    """Launch a background thread that performs the update. Idempotent: returns
    early if an update is already in flight."""
    global _worker_thread
    with _state_lock:
        phase = _state["phase"]
        if phase in ("downloading", "verifying", "installing", "restarting"):
            return False, "update already in progress"
    _set_state(phase="downloading", percent=0, message="starting", version=version,
               started_at=time.time(), finished_at=None)
    _worker_thread = threading.Thread(target=_worker, args=(version,), daemon=True)
    _worker_thread.start()
    return True, "started"

def rollback():
    """Swap /root/router with /root/router.bak (and the web dir) then restart."""
    if not _has_backup():
        return False, "no backup available"
    try:
        _set_state(phase="installing", percent=50, message="rolling back",
                   version=None, started_at=time.time(), finished_at=None)
        tmp = APP_ROOT + ".rollback_tmp"
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        os.rename(APP_ROOT, tmp)
        os.rename(APP_ROOT + ".bak", APP_ROOT)
        os.rename(tmp, APP_ROOT + ".bak")
        # web
        if os.path.isdir(WEB_ROOT + ".bak"):
            wtmp = WEB_ROOT + ".rollback_tmp"
            if os.path.exists(wtmp):
                shutil.rmtree(wtmp)
            os.rename(WEB_ROOT, wtmp)
            os.rename(WEB_ROOT + ".bak", WEB_ROOT)
            os.rename(wtmp, WEB_ROOT + ".bak")
        _set_state(phase="restarting", percent=90, message="restarting service",
                   version=get_current_version())
        _schedule_restart()
        _set_state(phase="done", percent=100, message="rollback complete",
                   version=get_current_version(), finished_at=time.time())
        return True, "rollback complete"
    except Exception as e:
        logger.exception("rollback failed")
        _set_state(phase="error", message=f"rollback failed: {e}",
                   finished_at=time.time())
        return False, str(e)

# --- worker -----------------------------------------------------------------
def _worker(version):
    try:
        manifest = check_update(version)
        if not manifest or not manifest.get("filename"):
            raise RuntimeError("license server returned no manifest")
        target_version = manifest.get("version")
        _set_state(phase="downloading", percent=5,
                   message=f"downloading {target_version}", version=target_version)

        os.makedirs(DL_DIR, exist_ok=True)
        local_path = os.path.join(DL_DIR, manifest["filename"])
        _download(manifest, local_path)

        _set_state(phase="verifying", percent=60, message="verifying")
        _verify(local_path, manifest)

        _set_state(phase="installing", percent=75, message="installing")
        _install(local_path)

        _set_state(phase="restarting", percent=95, message="restarting service",
                   version=get_current_version())
        _schedule_restart()

        _set_state(phase="done", percent=100, message="update complete",
                   version=get_current_version(), finished_at=time.time())
    except Exception as e:
        logger.exception("update failed")
        _set_state(phase="error", message=str(e), finished_at=time.time())

def _download(manifest, local_path):
    url = manifest.get("download_url")
    if not url:
        # build a default download URL on the same host as latest endpoint
        url = f"{LICENSE_SERVER}/downloads/{manifest['filename']}"
    size = int(manifest.get("size") or 0)
    headers = _license_headers()
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        r.raise_for_status()
        wrote = 0
        with open(local_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if chunk:
                    f.write(chunk)
                    wrote += len(chunk)
                    if size:
                        pct = 5 + int(50 * wrote / size)
                        if pct > 55:
                            pct = 55
                        _set_state(phase="downloading", percent=pct,
                                   message=f"downloaded {wrote}/{size}")
    if size and os.path.getsize(local_path) != size:
        raise RuntimeError(
            f"size mismatch: got {os.path.getsize(local_path)} expected {size}"
        )

def _verify(local_path, manifest):
    # SHA-256
    expected = (manifest.get("sha256") or "").lower()
    if not expected:
        raise RuntimeError("manifest missing sha256")
    h = hashlib.sha256()
    with open(local_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise RuntimeError(f"sha256 mismatch: {actual} != {expected}")

    # HMAC signature
    sig = (manifest.get("signature") or "").lower()
    key = _load_signing_key()
    if not sig:
        raise RuntimeError("manifest missing signature")
    if not key:
        raise RuntimeError("UPDATE_SIGNING_KEY not present on device")
    msg = f"{manifest['version']}|{expected}|{manifest['size']}".encode()
    expected_sig = hmac.new(key.encode(), msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise RuntimeError("signature verification failed")

def _safe_extract(tar, dest):
    dest_abs = os.path.realpath(dest)
    for m in tar.getmembers():
        # disallow absolute paths and traversal
        if m.name.startswith("/") or ".." in Path(m.name).parts:
            raise RuntimeError(f"unsafe tar entry: {m.name}")
        target = os.path.realpath(os.path.join(dest, m.name))
        if not target.startswith(dest_abs):
            raise RuntimeError(f"tar entry escapes dest: {m.name}")
    tar.extractall(dest)

def _install(local_path):
    # Extract to stage
    if os.path.exists(STAGE_DIR):
        shutil.rmtree(STAGE_DIR)
    os.makedirs(STAGE_DIR, exist_ok=True)
    with tarfile.open(local_path, "r:gz") as tar:
        _safe_extract(tar, STAGE_DIR)

    # Validate expected entries (pyarmor_runtime_005235 is optional: unobfuscated builds omit it)
    required = ["main.py", "router", "VERSION"]
    missing = [r for r in required if not os.path.exists(os.path.join(STAGE_DIR, r))]
    if missing:
        raise RuntimeError(f"staged payload missing: {missing}")

    # Rotate app backup: .bak.old <- .bak <- live
    bak = APP_ROOT + ".bak"
    bak_old = APP_ROOT + ".bak.old"
    if os.path.isdir(bak_old):
        shutil.rmtree(bak_old)
    if os.path.isdir(bak):
        os.rename(bak, bak_old)
    # Copy current /root/router to .bak (preserves runtime files like .pyarmor caches)
    shutil.copytree(APP_ROOT, bak, symlinks=True)

    # Swap app files: remove old top-level entries we are about to replace, then copy new
    replace_entries = ["main.py", "resource_path.py", "router",
                       "pyarmor_runtime_005235", "VERSION", "UPDATE_SIGNING_KEY"]
    for name in replace_entries:
        p = os.path.join(APP_ROOT, name)
        if os.path.isdir(p) and not os.path.islink(p):
            shutil.rmtree(p)
        elif os.path.exists(p) or os.path.islink(p):
            os.remove(p)
        src = os.path.join(STAGE_DIR, name)
        if os.path.exists(src):
            if os.path.isdir(src):
                shutil.copytree(src, p, symlinks=True)
            else:
                shutil.copy2(src, p)

    # Web swap (only if payload contains web/)
    stage_web = os.path.join(STAGE_DIR, "web")
    if os.path.isdir(stage_web):
        web_bak = WEB_ROOT + ".bak"
        if os.path.isdir(web_bak):
            shutil.rmtree(web_bak)
        if os.path.isdir(WEB_ROOT):
            shutil.copytree(WEB_ROOT, web_bak, symlinks=True)
            # clear contents but keep dir
            for n in os.listdir(WEB_ROOT):
                p = os.path.join(WEB_ROOT, n)
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)
        else:
            os.makedirs(WEB_ROOT, exist_ok=True)
        for n in os.listdir(stage_web):
            s = os.path.join(stage_web, n)
            d = os.path.join(WEB_ROOT, n)
            if os.path.isdir(s):
                shutil.copytree(s, d, symlinks=True)
            else:
                shutil.copy2(s, d)

def _schedule_restart():
    def _do():
        time.sleep(3)
        try:
            if os.path.exists(INIT_SCRIPT):
                subprocess.run([INIT_SCRIPT, "restart"], check=False)
            else:
                subprocess.run(["pkill", "-f", "python3 .*main.py"], check=False)
                time.sleep(1)
                if os.path.exists(MAIN_SCRIPT):
                    subprocess.Popen(["python3", MAIN_SCRIPT])
        except Exception as e:
            logger.error("restart failed: %s", e)
    threading.Thread(target=_do, daemon=True).start()
