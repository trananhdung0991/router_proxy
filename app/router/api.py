from time import sleep
import threading
import subprocess  # Add this
import time        # Add this
import logging     # Add this
import psutil      # Add this - install with: pip3 install psutil
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from pathlib import Path
from router.global_vars import proxy
from flask_cors import CORS, cross_origin
from router.passwall2 import Passwall2Manager
from router.openwrt_router import OpenWrtRouterManager
from router.license import get_license_manager

logger = logging.getLogger(__name__)


app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)  # widen CORS
app.config['JSON_SORT_KEYS'] = False

# Global OPTIONS handler (preflight)
@app.before_request
def handle_global_options():
    if request.method == 'OPTIONS':
        resp = app.make_response(('', 204))
        h = resp.headers
        h['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        h['Access-Control-Allow-Methods'] = 'GET,POST,PUT,DELETE,OPTIONS'
        h['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', 'Content-Type, Authorization')
        h['Access-Control-Allow-Credentials'] = 'true'
        return resp


def flask_start():
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=False, port=8080, host='0.0.0.0')

def flask_init():
    flask_init = threading.Thread(target=flask_start, args=[])
    flask_init.daemon = True
    flask_init.start()

def parse_dhcp_leases(path="/tmp/dhcp.leases"):
    """
    dnsmasq lease format:
      <expiry> <mac> <ip> <hostname> <client-id>
    """
    leases_path = Path(path)
    if not leases_path.exists():
        return []

    entries_by_ip = {}
    with leases_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            try:
                expiry = int(parts[0])
            except ValueError:
                expiry = 0
            mac = parts[1].lower()
            ip = parts[2]
            hostname = parts[3]
            if hostname in ("*", "-"):
                hostname = None
            prev = entries_by_ip.get(ip)
            if not prev or expiry > prev["expiry"]:
                entries_by_ip[ip] = {"ip": ip, "mac": mac, "hostname": hostname, "expiry": expiry}

    # drop expiry from the response
    return [{"ip": v["ip"], "mac": v["mac"], "hostname": v["hostname"]} for v in entries_by_ip.values()]


import re
from urllib.parse import urlparse

class LinuxUtil:
    def get_linux_resource(self):
        data = {}
        dict(psutil.virtual_memory()._asdict())
        data['memory'] = psutil.virtual_memory().percent
        data['cpu'] = psutil.cpu_percent()
        data['time'] = int((time.time() - psutil.boot_time()) / 3600)
        return data

@app.route("/dhcp_clients", methods=['GET'])
def dhcp_clients():
    return jsonify(parse_dhcp_leases())


@app.route('/manufacture_information', methods=['GET'])
def web_manufacture_information():
    # check new version every 30m
    data = {}
    data['name'] = 'Router Proxy'
    data['identity_name'] = 'xproxy'
    data['api_ref'] = "xproxy.io"
    return jsonify({'status': True, 'data': data})

@app.route('/linux_resource', methods=['GET'])
def web_linux_resource_config():
    # check new version every 30m
    data = {}
    data = LinuxUtil().get_linux_resource()
    data['version'] = '0.1'
    return jsonify({'status': True, 'data': data})

@app.route('/v2/footer_ads', methods=['GET'])
def web_footer_ads_get():
    return jsonify({'status': False})

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})

@app.route("/license/info", methods=["GET"])
def get_license_info():
    """Get current license information"""
    try:
        lm = get_license_manager()
        # Ensure we perform a license check (uses cache if available)
        lm.check_license()
        if lm.is_license_valid():
            info = lm.get_license_info()
            return jsonify({
                "valid": True,
                "product_name": info.get('product_name', 'Unknown'),
                "customer_name": info.get('customer_name', 'Unknown'),
                "expiry_date": info.get('expiry_date', 'Unknown'),
                "days_remaining": info.get('days_remaining', 'Unknown')
            })
        else:
            return jsonify({
                "valid": False,
                "message": "No valid license"
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/license/verify", methods=["POST"])
def verify_license():
    """Force license re-verification"""
    try:
        lm = get_license_manager()
        success = lm.verify_license(force=True)
        if success:
            info = lm.get_license_info()
            return jsonify({
                "success": True,
                "valid": True,
                "message": "License verified successfully",
                "info": info
            })
        else:
            return jsonify({
                "success": False,
                "valid": False,
                "message": "License verification failed"
            }), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/license/save", methods=["POST"])
def save_license_key():
    """Save license key to /etc/license.key and reload license manager"""
    try:
        data = request.get_json() or {}
        license_key = data.get('license_key', '').strip()
        if not license_key:
            return jsonify({"success": False, "message": "No license key provided"}), 400
        # Save to /etc/license.key
        try:
            with open("/etc/license.key", "w") as f:
                f.write(license_key + "\n")
        except Exception as e:
            return jsonify({"success": False, "message": f"Failed to write license file: {e}"}), 500
        # Reload license manager
        lm = get_license_manager()
        lm.license_key = license_key
        lm.is_valid = False
        lm.license_info = {}
        return jsonify({"success": True, "message": "License key saved."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/client_proxy", methods=["POST"])
def set_client_proxy():
    """Set or clear proxy for a client"""
    try:
        # Check license first
        lm = get_license_manager()
        lm.check_license()
        if not lm.is_license_valid():
            return jsonify({
                "status": False,
                "error": "Valid license required"
            }), 403
        
        data = request.get_json() or {}
        ip = data.get('ip', '').strip()
        proxy_url = data.get('proxy', '').strip()
        proxy_type = data.get('proxy_type', 'HTTP').strip().upper()
        hostname = data.get('hostname', '').strip()
        remote_fakedns = data.get('remote_fakedns', False)
        exit_ip = data.get('exit_ip', '').strip()
        
        if not ip:
            return jsonify({"status": False, "error": "IP address required"}), 400
        
        success = proxy.set_client_proxy(ip, proxy_url, hostname, remote_fakedns, proxy_type, exit_ip)
        
        if success:
            if proxy_url:
                return jsonify({
                    "status": True, 
                    "message": f"Proxy set for {ip}",
                    "data": {
                        "ip": ip,
                        "proxy": proxy_url,
                        "proxy_type": proxy_type,
                        "hostname": hostname,
                        "remote_fakedns": remote_fakedns
                    }
                })
            else:
                return jsonify({
                    "status": True, 
                    "message": f"Proxy cleared for {ip}",
                    "data": {"ip": ip}
                })
        else:
            return jsonify({"status": False, "error": "Failed to configure proxy"}), 500
            
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/stun/register", methods=["POST"])
def stun_register():
    """Directly register a device IP → proxy exit IP in the fake STUN server"""
    try:
        from router.stun_server import get_stun_server
        data = request.get_json() or {}
        ip = data.get('ip', '').strip()
        proxy_ip = data.get('proxy_ip', '').strip()
        if not ip or not proxy_ip:
            return jsonify({"status": False, "error": "ip and proxy_ip required"}), 400
        get_stun_server().register(ip, proxy_ip)
        return jsonify({"status": True, "message": f"STUN registered {ip} -> {proxy_ip}"})
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/stun/registrations", methods=["GET"])
def stun_registrations():
    """List all STUN device registrations"""
    try:
        from router.stun_server import get_stun_server
        return jsonify({"status": True, "data": get_stun_server().get_all()})
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/clients", methods=["GET"])
def get_clients():
    """Get all clients with their proxy configurations"""
    try:
        clients = proxy.get_all_client_proxies()
        client_list = list(clients.values())
        
        return jsonify({
            "status": True,
            "data": client_list,
            "count": len(client_list)
        })
        
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/client_proxy/<ip>", methods=["GET"])
def get_client_proxy(ip):
    """Get proxy configuration for a specific client"""
    try:
        # Check license first
        lm = get_license_manager()
        lm.check_license()
        if not lm.is_license_valid():
            return jsonify({
                "status": False,
                "error": "Valid license required"
            }), 403
        
        client = proxy.client_proxy_db.get_client_proxy(ip)
        
        if client:
            return jsonify({
                "status": True,
                "data": client
            })
        else:
            return jsonify({
                "status": False,
                "error": f"Client {ip} not found"
            }), 404
            
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/client/bind_ip_mac", methods=["POST"])
def bind_ip_to_mac():
    """Bind IP address to MAC address in OpenWrt DHCP reservations"""
    try:
        data = request.get_json()
        ip = data.get("ip")
        mac = data.get("mac")
        hostname = data.get("hostname", "")
        bind_enabled = data.get("bind", True)
        
        if not ip or not mac:
            return jsonify({
                "status": False,
                "error": "IP and MAC address are required"
            }), 400
            
        # Validate IP format
        import re
        ip_pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        if not re.match(ip_pattern, ip):
            return jsonify({
                "status": False,
                "error": "Invalid IP address format"
            }), 400
            
        # Validate MAC format
        mac_pattern = r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$'
        if not re.match(mac_pattern, mac):
            return jsonify({
                "status": False,
                "error": "Invalid MAC address format"
            }), 400
        
        if bind_enabled:
            # Add DHCP reservation
            success = add_dhcp_reservation(ip, mac, hostname)
            if success:
                return jsonify({
                    "status": True,
                    "message": f"IP {ip} successfully bound to MAC {mac}"
                })
            else:
                return jsonify({
                    "status": False,
                    "error": "Failed to add DHCP reservation"
                }), 500
        else:
            # Remove DHCP reservation
            success = remove_dhcp_reservation(ip, mac)
            if success:
                return jsonify({
                    "status": True,
                    "message": f"IP {ip} binding to MAC {mac} removed"
                })
            else:
                return jsonify({
                    "status": False,
                    "error": "Failed to remove DHCP reservation"
                }), 500
                
    except Exception as e:
        return jsonify({"status": False, "error": str(e)}), 500

def add_dhcp_reservation(ip, mac, hostname=""):
    """Add DHCP reservation using UCI commands"""
    try:
        import subprocess
        
        # Normalize MAC address format (use lowercase with colons)
        mac = mac.lower().replace('-', ':')
        
        # Create UCI section for DHCP reservation
        section_name = f"reservation_{mac.replace(':', '')}"
        
        # Add new dhcp host section
        cmd1 = f"uci add dhcp host"
        result1 = subprocess.run(cmd1, shell=True, capture_output=True, text=True)
        
        if result1.returncode != 0:
            logger.error(f"Failed to add dhcp host: {result1.stderr}")
            return False
            
        # Get the section name that was created
        cmd2 = f"uci show dhcp | grep 'dhcp.@host\\[' | tail -1 | cut -d'=' -f1 | cut -d'.' -f2"
        result2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True)
        
        if result2.returncode != 0:
            logger.error(f"Failed to get section name: {result2.stderr}")
            return False
            
        section = result2.stdout.strip()
        
        # Set the MAC address
        cmd3 = f"uci set dhcp.{section}.mac='{mac}'"
        result3 = subprocess.run(cmd3, shell=True, capture_output=True, text=True)
        
        # Set the IP address  
        cmd4 = f"uci set dhcp.{section}.ip='{ip}'"
        result4 = subprocess.run(cmd4, shell=True, capture_output=True, text=True)
        
        # Set hostname if provided
        if hostname:
            cmd5 = f"uci set dhcp.{section}.name='{hostname}'"
            result5 = subprocess.run(cmd5, shell=True, capture_output=True, text=True)
        
        # Commit changes
        cmd6 = f"uci commit dhcp"
        result6 = subprocess.run(cmd6, shell=True, capture_output=True, text=True)
        
        if result6.returncode != 0:
            logger.error(f"Failed to commit UCI changes: {result6.stderr}")
            return False
            
        # Restart dnsmasq to apply changes
        cmd7 = f"/etc/init.d/dnsmasq restart"
        result7 = subprocess.run(cmd7, shell=True, capture_output=True, text=True)
        
        if result7.returncode != 0:
            logger.error(f"Failed to restart dnsmasq: {result7.stderr}")
            return False
            
        logger.info(f"Successfully added DHCP reservation: IP={ip}, MAC={mac}, hostname={hostname}")
        return True
        
    except Exception as e:
        logger.error(f"Error adding DHCP reservation: {e}")
        return False

def remove_dhcp_reservation(ip, mac):
    """Remove DHCP reservation using UCI commands"""
    try:
        import subprocess
        
        # Normalize MAC address format
        mac = mac.lower().replace('-', ':')
        
        # Find the section with matching MAC or IP
        cmd1 = f"uci show dhcp | grep -E '(mac=.{mac}.|ip=.{ip}.)'  | head -1 | cut -d'.' -f2"
        result1 = subprocess.run(cmd1, shell=True, capture_output=True, text=True)
        
        if result1.returncode != 0 or not result1.stdout.strip():
            logger.warning(f"DHCP reservation not found for IP={ip}, MAC={mac}")
            return True  # Consider it success if reservation doesn't exist
            
        section = result1.stdout.strip()
        
        # Remove the section
        cmd2 = f"uci delete dhcp.{section}"
        result2 = subprocess.run(cmd2, shell=True, capture_output=True, text=True)
        
        if result2.returncode != 0:
            logger.error(f"Failed to delete DHCP section: {result2.stderr}")
            return False
            
        # Commit changes
        cmd3 = f"uci commit dhcp"
        result3 = subprocess.run(cmd3, shell=True, capture_output=True, text=True)
        
        if result3.returncode != 0:
            logger.error(f"Failed to commit UCI changes: {result3.stderr}")
            return False
            
        # Restart dnsmasq to apply changes
        cmd4 = f"/etc/init.d/dnsmasq restart"
        result4 = subprocess.run(cmd4, shell=True, capture_output=True, text=True)
        
        if result4.returncode != 0:
            logger.error(f"Failed to restart dnsmasq: {result4.stderr}")
            return False
            
        logger.info(f"Successfully removed DHCP reservation: IP={ip}, MAC={mac}")
        return True
        
    except Exception as e:
        logger.error(f"Error removing DHCP reservation: {e}")
        return False

@app.route("/client/dhcp_reservations", methods=["GET"])
def get_dhcp_reservations():
    """Get all current DHCP reservations"""
    try:
        import subprocess
        
        # Get all DHCP host sections using uci show
        cmd = "uci show dhcp"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            return jsonify({
                "status": True,
                "data": [],
                "bindings": {},
                "message": "No DHCP configuration found"
            })
        
        reservations = {}
        lines = result.stdout.strip().split('\n')
        
        # Parse UCI output to find host sections
        current_section = None
        for line in lines:
            line = line.strip()
            if not line or '=' not in line:
                continue
                
            # Look for host section entries
            if 'dhcp.@host[' in line and '].mac=' in line:
                # Extract section number: dhcp.@host[0].mac='xx:xx:xx:xx:xx:xx'
                section_match = line.split('dhcp.@host[')[1].split(']')[0]
                mac_value = line.split('=')[1].strip().strip("'\"")
                
                if section_match not in reservations:
                    reservations[section_match] = {}
                reservations[section_match]['mac'] = mac_value.lower().replace('-', ':')
                
            elif 'dhcp.@host[' in line and '].ip=' in line:
                # Extract IP address
                section_match = line.split('dhcp.@host[')[1].split(']')[0]
                ip_value = line.split('=')[1].strip().strip("'\"")
                
                if section_match not in reservations:
                    reservations[section_match] = {}
                reservations[section_match]['ip'] = ip_value
                
            elif 'dhcp.@host[' in line and '].name=' in line:
                # Extract hostname
                section_match = line.split('dhcp.@host[')[1].split(']')[0]
                name_value = line.split('=')[1].strip().strip("'\"")
                
                if section_match not in reservations:
                    reservations[section_match] = {}
                reservations[section_match]['name'] = name_value
        
        # Convert to list format and create IP->MAC mapping
        reservation_list = []
        ip_mac_bindings = {}
        
        for section, data in reservations.items():
            if 'ip' in data and 'mac' in data:
                reservation = {
                    'ip': data['ip'],
                    'mac': data['mac'],
                    'hostname': data.get('name', '')
                }
                reservation_list.append(reservation)
                ip_mac_bindings[data['ip']] = True
                
                logger.debug(f"Found DHCP reservation: IP={data['ip']}, MAC={data['mac']}, Name={data.get('name', '')}")
        
        logger.debug(f"Total DHCP reservations found: {len(reservation_list)}")
        logger.debug(f"IP bindings: {ip_mac_bindings}")
        
        return jsonify({
            "status": True,
            "data": reservation_list,
            "bindings": ip_mac_bindings
        })
        
    except Exception as e:
        logger.error(f"Error getting DHCP reservations: {e}")
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/passwall2/nodes", methods=["GET"])
def get_passwall2_nodes():
    """Get all Passwall2 proxy nodes"""
    try:
        passwall2 = Passwall2Manager()
        nodes = passwall2.get_nodes()
        return jsonify({"status": True, "data": nodes})
    except Exception as e:
        logger.error(f"Error getting Passwall2 nodes: {e}")
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/passwall2/status", methods=["GET"])
def get_passwall2_status():
    """Get Passwall2 service status"""
    try:
        result = subprocess.run(['service', 'passwall2', 'status'], 
                              capture_output=True, text=True)
        running = result.returncode == 0
        return jsonify({"status": True, "running": running, "output": result.stdout})
    except Exception as e:
        return jsonify({"status": False, "error": str(e)})

@app.route("/passwall2/acls", methods=["GET"])
def get_passwall2_acls():
    """Get all Passwall2 ACL rules with resolved node information"""
    try:
        passwall2 = Passwall2Manager()
        acls = passwall2.get_acl_rules()
        return jsonify({"status": True, "data": acls})
    except Exception as e:
        logger.error(f"Error getting Passwall2 ACLs: {e}")
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/passwall2/global", methods=["GET"])
def get_passwall2_global():
    """Get Passwall2 global configuration"""
    try:
        passwall2 = Passwall2Manager()
        config = passwall2.get_global_config()
        return jsonify({"status": True, "data": config})
    except Exception as e:
        logger.error(f"Error getting Passwall2 global config: {e}")
        return jsonify({"status": False, "error": str(e)}), 500

@app.route("/passwall2/fix_main_nodes", methods=["POST"])
def fix_passwall2_main_nodes():
    """Fix main TCP/UDP nodes if they're invalid"""
    try:
        passwall2 = Passwall2Manager()
        success = passwall2.ensure_valid_main_nodes()
        
        # Get updated config
        config = passwall2.get_global_config()
        
        return jsonify({
            "status": success,
            "data": config,
            "message": "Main nodes fixed" if success else "Failed to fix main nodes"
        })
    except Exception as e:
        logger.error(f"Error fixing main nodes: {e}")
        return jsonify({"status": False, "error": str(e)}), 500


# OpenWrt Router IP Configuration Endpoints

@app.route('/api/openwrt/router/current-config', methods=['GET'])
@cross_origin()
def get_current_router_config():
    """Get current OpenWrt router IP configuration"""
    try:
        router_manager = OpenWrtRouterManager()
        config = router_manager.get_current_config()
        
        return jsonify({
            "success": True,
            "data": config
        })
        
    except Exception as e:
        logger.error(f"Error getting router config: {e}")
        return jsonify({
            "success": False,
            "message": f"Error getting router configuration: {str(e)}"
        }), 500


@app.route('/api/openwrt/router/change-ip', methods=['POST'])
@cross_origin()
def change_router_ip():
    """Change OpenWrt router IP configuration"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
            
        new_ip = data.get('newIP')
        netmask = data.get('netmask', '255.255.255.0')
        dhcp_start = data.get('dhcpStart')
        dhcp_end = data.get('dhcpEnd')
        
        if not new_ip:
            return jsonify({
                "success": False,
                "message": "New IP address is required"
            }), 400
        
        router_manager = OpenWrtRouterManager()
        
        # Backup current configuration
        backup_config = router_manager.backup_current_config()
        
        # Change router IP
        success = router_manager.change_router_ip(new_ip, netmask, dhcp_start, dhcp_end)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"Router IP changed to {new_ip} successfully",
                "data": {
                    "newIP": new_ip,
                    "netmask": netmask,
                    "dhcpStart": dhcp_start,
                    "dhcpEnd": dhcp_end
                }
            })
        else:
            return jsonify({
                "success": False,
                "message": "Failed to change router IP"
            }), 500
        
    except Exception as e:
        logger.error(f"Error changing router IP: {e}")
        return jsonify({
            "success": False,
            "message": f"Error changing router IP: {str(e)}"
        }), 500


@app.route('/api/openwrt/router/test-ip', methods=['POST'])
@cross_origin()
def test_router_ip():
    """Test if an IP address is available/reachable"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
            
        test_ip = data.get('testIP')
        
        if not test_ip:
            return jsonify({
                "success": False,
                "message": "Test IP address is required"
            }), 400
        
        router_manager = OpenWrtRouterManager()
        available, message = router_manager.test_ip_availability(test_ip)
        
        return jsonify({
            "success": available,
            "message": message
        })
        
    except Exception as e:
        logger.error(f"Error testing IP: {e}")
        return jsonify({
            "success": False,
            "message": f"Error testing IP: {str(e)}"
        }), 500


@app.route('/system/reboot', methods=['POST'])
@cross_origin()
def system_reboot():
    """Reboot the device. Requires root privileges."""
    def delayed_reboot():
        """Execute reboot after a short delay to allow response to be sent"""
        time.sleep(2)  # Wait 2 seconds for response to be sent
        try:
            import subprocess
            # Flush filesystem buffers first
            subprocess.run(['sync'])
            # Trigger reboot
            subprocess.run(['reboot'])
        except Exception as e:
            logger.error(f"Error in delayed reboot: {e}")
    
    try:
        # Start reboot in background thread
        reboot_thread = threading.Thread(target=delayed_reboot, daemon=True)
        reboot_thread.start()
        
        # Return success immediately before system reboots
        return jsonify({
            "success": True,
            "message": "System reboot initiated. The device will reboot in 2 seconds."
        })
        
    except Exception as e:
        logger.error(f"Error initiating reboot: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/system/restart', methods=['POST'])
@cross_origin()
def system_restart_service():
    """Restart the router proxy service using init script if available."""
    def delayed_restart():
        """Execute restart after a short delay to allow response to be sent"""
        time.sleep(2)  # Wait 2 seconds for response to be sent
        try:
            import subprocess
            init_script = '/etc/init.d/router_proxy'
            if os.path.exists(init_script):
                subprocess.run([init_script, 'restart'], check=False)
            else:
                # Fallback: kill and relaunch
                subprocess.run(['pkill', '-f', 'python3 .*main.py'], check=False)
                time.sleep(1)
                main_script = '/root/router/main.py'
                if os.path.exists(main_script):
                    subprocess.Popen(['python3', main_script])
        except Exception as e:
            logger.error(f"Error in delayed restart: {e}")
    
    try:
        # Check if restart script exists
        init_script = '/etc/init.d/router_proxy'
        main_script = '/root/router/main.py'
        
        if not os.path.exists(init_script) and not os.path.exists(main_script):
            return jsonify({
                "success": False, 
                "message": "No init script or main script found to restart"
            }), 500
        
        # Start restart in background thread
        restart_thread = threading.Thread(target=delayed_restart, daemon=True)
        restart_thread.start()
        
        # Return success immediately before service is killed
        return jsonify({
            "success": True,
            "message": "Service restart initiated. The service will restart in 2 seconds."
        })
        
    except Exception as e:
        logger.error(f"Error restarting service: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/dashboard/status', methods=['GET'])
@cross_origin()
def dashboard_port80_status():
    """Get current dashboard port 80 status"""
    try:
        result = subprocess.run(
            "uci get uhttpd.router_app.listen_http 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        listeners = result.stdout.strip().split()
        app_enabled = any(l.endswith(":80") or l == "80" for l in listeners)
        main_result = subprocess.run(
            "uci get uhttpd.main.listen_http 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        main_listeners = main_result.stdout.strip().split()
        main_enabled = any(l.endswith(":80") or l == "80" for l in main_listeners)
        enabled = app_enabled or main_enabled
        return jsonify({"success": True, "port80_enabled": enabled, "listeners": listeners, "main_listeners": main_listeners})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/dashboard/enable', methods=['POST'])
@cross_origin()
def dashboard_port80_enable():
    """Add port 80 to dashboard (uhttpd router_app) and restore on uhttpd.main"""
    try:
        changed = False
        # Enable on router_app section
        result = subprocess.run(
            "uci get uhttpd.router_app.listen_http 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        listeners = result.stdout.strip().split()
        if not any(l.endswith(":80") or l == "80" for l in listeners):
            subprocess.run(
                "uci add_list uhttpd.router_app.listen_http='0.0.0.0:80'",
                shell=True, check=True
            )
            changed = True
        # Enable on main (LuCI) section
        main_result = subprocess.run(
            "uci get uhttpd.main.listen_http 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        main_listeners = main_result.stdout.strip().split()
        if not any(l.endswith(":80") or l == "80" for l in main_listeners):
            subprocess.run(
                "uci add_list uhttpd.main.listen_http='0.0.0.0:80'",
                shell=True, check=True
            )
            changed = True
        if not changed:
            return jsonify({"success": True, "message": "Port 80 already enabled"})
        subprocess.run("uci commit uhttpd", shell=True, check=True)
        subprocess.run("/etc/init.d/uhttpd restart", shell=True, check=True)
        return jsonify({"success": True, "message": "Dashboard port 80 enabled"})
    except Exception as e:
        logger.error(f"Error enabling dashboard port 80: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/dashboard/disable', methods=['POST'])
@cross_origin()
def dashboard_port80_disable():
    """Remove port 80 from dashboard (uhttpd router_app) and from uhttpd.main (LuCI)"""
    try:
        changed = False
        # Disable on router_app section
        result = subprocess.run(
            "uci get uhttpd.router_app.listen_http 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        listeners = result.stdout.strip().split()
        if any(l.endswith(":80") or l == "80" for l in listeners):
            subprocess.run(
                "uci del_list uhttpd.router_app.listen_http='0.0.0.0:80'",
                shell=True, check=True
            )
            changed = True
        # Disable on main (LuCI) section
        main_result = subprocess.run(
            "uci get uhttpd.main.listen_http 2>/dev/null",
            shell=True, capture_output=True, text=True
        )
        main_listeners = main_result.stdout.strip().split()
        for l in main_listeners:
            if l.endswith(":80") or l == "80":
                subprocess.run(
                    f"uci del_list uhttpd.main.listen_http='{l}'",
                    shell=True, check=True
                )
                changed = True
        if not changed:
            return jsonify({"success": True, "message": "Port 80 already disabled"})
        subprocess.run("uci commit uhttpd", shell=True, check=True)
        subprocess.run("/etc/init.d/uhttpd restart", shell=True, check=True)
        return jsonify({"success": True, "message": "Dashboard port 80 disabled"})
    except Exception as e:
        logger.error(f"Error disabling dashboard port 80: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == '__main__':
    logger.info("flask_init")
    flask_init()
    while True:
        sleep(2)
