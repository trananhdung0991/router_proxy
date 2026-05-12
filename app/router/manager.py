from router.api import flask_init
from router.main_proxy import TinyproxyMultiManager  # Using TinyproxyMultiManager from main_proxy
from router.passwall2 import Passwall2Manager
from router.stun_server import get_stun_server
from router.license import get_license_manager
import time
import sys
import logging

# Set up logging
logger = logging.getLogger(__name__)

def restore_stun_registrations():
    """Re-register existing proxy clients with the STUN server after a service restart.
    Tries DB first; falls back to reading passwall2 UCI ACL rules directly."""
    stun = get_stun_server()
    count = 0

    # --- 1. Try DB ---
    try:
        from router.db.db_init import DBInit
        from urllib.parse import urlparse
        db = DBInit()
        clients = db.clients_db.get_all_clients()
        for ip, data in clients.items():
            proxy_url = data.get('proxy_url', '')
            if proxy_url:
                parsed = urlparse(proxy_url)
                if parsed.hostname:
                    stun.register(ip, parsed.hostname)
                    count += 1
    except Exception as e:
        logger.debug(f"DB restore skipped: {e}")

    # --- 2. Fallback: scan passwall2 UCI ACL rules ---
    if count == 0:
        try:
            import subprocess
            result = subprocess.run(
                ['uci', 'show', 'passwall2'],
                capture_output=True, text=True, timeout=5
            )
            lines = result.stdout.splitlines()
            # Parse all ACL rules: sources → node
            acl: dict = {}      # section_idx → {'sources': ip, 'node': node_id}
            nodes: dict = {}    # node_id → address
            for line in lines:
                # nodes: passwall2.PrU7msE7.address='45.77.248.141'
                parts = line.split('=', 1)
                if len(parts) != 2:
                    continue
                key = parts[0]
                val = parts[1].strip().strip("'\"")
                segs = key.split('.')
                if len(segs) == 3 and segs[0] == 'passwall2' and segs[2] == 'address':
                    nodes[segs[1]] = val
                # acl rules: passwall2.@acl_rule[N].sources / .node
                if len(segs) == 3 and segs[0] == 'passwall2' and segs[2] in ('sources', 'node'):
                    idx = segs[1]  # e.g. '@acl_rule[0]'
                    acl.setdefault(idx, {})[segs[2]] = val
            for _idx, rule in acl.items():
                device_ip = rule.get('sources', '')
                node_id = rule.get('node', '')
                server_ip = nodes.get(node_id, '')
                if device_ip and server_ip:
                    stun.register(device_ip, server_ip)
                    count += 1
                    logger.info(f"UCI restore: STUN {device_ip} → {server_ip}")
        except Exception as e:
            logger.warning(f"UCI fallback STUN restore failed: {e}")

    if count:
        logger.info(f"Restored {count} STUN registration(s)")
    else:
        logger.debug("No active proxy clients found for STUN restore")


def create_main_proxy(proxy_manager: TinyproxyMultiManager):
    
    local_proxy = proxy_manager.create_proxy(name='local_proxy',
                                             host='0.0.0.0',
                                             port=4001)
    logger.info("Starting HTTP proxy (Tinyproxy)...")
    if proxy_manager.start_proxy('local_proxy'):
        proxy_status = local_proxy.get_status()
        logger.info(f"    Local HTTP proxy started successfully!")
        logger.info(f"   - URL: {proxy_status['proxy_url']}")
        logger.info(f"   - Host: {proxy_status['host']}")
        logger.info(f"   - Port: {proxy_status['port']}")
        logger.info(f"   - PID: {proxy_status['pid']}")
        logger.info(f"   - Running: {proxy_status['running']}")
        return True
    else:
        logger.error("Failed to start local HTTP proxy")
        return False

def configure_passwall2():
    """Configure passwall2 for per-device ACL mode:
    - Remove legacy 'Local HTTP Proxy' node if present
    - Set global default to direct (unassigned devices bypass proxy)
    - Enable ACL so per-device rules still apply
    - Restart passwall2 to apply
    """
    try:
        logger.info("Configuring Passwall2 (global default = direct)...")
        passwall2_manager = Passwall2Manager()

        # Clean up legacy Local HTTP Proxy node from previous design
        passwall2_manager._remove_local_proxy_node()

        # Set global routing to direct, enable ACL
        passwall2_manager.set_global_direct()

        # Restart to apply
        passwall2_manager._restart_passwall2()
        logger.info("Passwall2 configured: global=direct, ACL enabled")
        return True
    except Exception as e:
        logger.error(f"Error configuring passwall2: {e}")
        return False

def run():
    logger.info("=" * 60)
    logger.info("Router Proxy Service Starting...")
    logger.info("=" * 60)
    
    
    # Initialize Flask API
    logger.info("Initializing Flask API...")
    flask_init()

    # Start fake STUN server for WebRTC IP spoofing (Option A)
    stun = get_stun_server()
    stun.start()
    logger.info("Fake STUN server started on 0.0.0.0:3478")
    restore_stun_registrations()
    
    # Start proxy first (before license check)
    logger.info("Starting HTTP proxy...")
    proxy_manager = TinyproxyMultiManager()
    proxy_manager.stop_all()
    proxy_started = create_main_proxy(proxy_manager)
    
    if not proxy_started:
        logger.error("✗ Failed to start HTTP proxy - will retry after license check")
    
    if proxy_started:
        logger.info("Configuring Passwall2...")
        if configure_passwall2():
            logger.info("✓ Passwall2 configured (global=direct, ACL enabled)")
        else:
            logger.warning("✗ Failed to configure Passwall2")
    else:
        logger.warning("⚠ Proxy not running, skipping Passwall2 configuration")

    # Verify license (with direct internet or cache)
    logger.info("Verifying license...")
    license_manager = get_license_manager()
    license_valid = license_manager.verify_license()

    if license_valid:
        logger.info("✓ License verified successfully")
    else:
        logger.error("✗ License verification failed")
        logger.warning("⚠ Proxy is running but Passwall2 integration disabled")
    
    logger.info("=" * 60)
    logger.info("Service initialization complete")
    logger.info("=" * 60)
    
    while True:
        time.sleep(2)


